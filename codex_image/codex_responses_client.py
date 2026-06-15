from __future__ import annotations

import base64
import json
import re
import uuid
from datetime import UTC, datetime
from os import PathLike
from pathlib import Path
from typing import Any

from .auth import AuthState, refresh_auth_state
from .client_errors import _format_codex_usage_limit_error, _response_body_text, _usage_limit_error
from .client_types import (
    DEFAULT_IMAGE_MODEL,
    DEFAULT_MAIN_MODEL,
    DEFAULT_RESPONSES_URL,
    AuthProvider,
    ImageResult,
    image_model_supports_input_fidelity,
)
from .http import HTTPResponse, Transport, UrllibTransport

CODEX_USER_AGENT = "codex-tui/0.118.0 (Mac OS 26.3.1; arm64) Codex Desktop"
CODEX_ORIGINATOR = "codex-tui"
WEB_SEARCH_INSTRUCTIONS = (
    "Web search image workflow:\n"
    "First call web_search to research the user's topic. Do not call image_generation until web_search has returned. "
    "Then call image_generation exactly once to create the requested image. Do not answer with text only.\n"
    "When calling image_generation, keep the user's original creative directions intact, but include a concise factual "
    "context block from web_search in the image prompt. This is an explicit exception to original or strict "
    "prompt-fidelity rules; prompt fidelity must not be used as a reason to omit search findings.\n"
    "If web_search finds an official or commonly used English title, person name, date, place, or other factual label, "
    "use that searched fact in the image prompt instead of a literal translation or guess."
)


class CodexImageClient:
    def __init__(
        self,
        auth_state: AuthState | None = None,
        *,
        auth_provider: AuthProvider | None = None,
        transport: Transport | None = None,
        responses_url: str = DEFAULT_RESPONSES_URL,
    ) -> None:
        if auth_state is None:
            if auth_provider is None:
                raise TypeError("CodexImageClient requires auth_state or auth_provider")
            auth_state = auth_provider.next_auth_state()
        self.auth_state = auth_state
        self.auth_provider = auth_provider
        self.transport = transport or UrllibTransport()
        self.responses_url = responses_url

    def generate_image(
        self,
        *,
        prompt: str,
        instructions: str | None = None,
        main_model: str = DEFAULT_MAIN_MODEL,
        model: str = DEFAULT_IMAGE_MODEL,
        reference_images: list[str] | None = None,
        size: str | None = None,
        quality: str | None = None,
        background: str | None = None,
        output_format: str = "png",
        moderation: str | None = None,
        output_compression: int | None = None,
        partial_images: int | None = None,
        web_search: bool = False,
        debug_sse_path: str | PathLike[str] | None = None,
    ) -> ImageResult:
        payload = self.build_payload(
            prompt=prompt,
            instructions=instructions,
            action="generate",
            main_model=main_model,
            model=model,
            input_images=reference_images or [],
            size=size,
            quality=quality,
            background=background,
            output_format=output_format,
            moderation=moderation,
            output_compression=output_compression,
            partial_images=partial_images,
            web_search=web_search,
        )
        response = self._responses_request_with_auth_retry(payload)
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(self._format_http_error(response))
        return self.parse_sse_response(response.body, debug_sse_path=debug_sse_path)

    def edit_image(
        self,
        *,
        prompt: str,
        images: list[str],
        mask_image: str | None = None,
        instructions: str | None = None,
        main_model: str = DEFAULT_MAIN_MODEL,
        model: str = DEFAULT_IMAGE_MODEL,
        size: str | None = None,
        quality: str | None = None,
        background: str | None = None,
        output_format: str = "png",
        input_fidelity: str | None = None,
        moderation: str | None = None,
        output_compression: int | None = None,
        partial_images: int | None = None,
        web_search: bool = False,
        debug_sse_path: str | PathLike[str] | None = None,
    ) -> ImageResult:
        if not images:
            raise RuntimeError("edit_image requires at least one input image")

        payload = self.build_payload(
            prompt=prompt,
            instructions=instructions,
            action="edit",
            main_model=main_model,
            model=model,
            input_images=images,
            mask_image=mask_image,
            size=size,
            quality=quality,
            background=background,
            output_format=output_format,
            input_fidelity=input_fidelity,
            moderation=moderation,
            output_compression=output_compression,
            partial_images=partial_images,
            web_search=web_search,
        )
        response = self._responses_request_with_auth_retry(payload)
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(self._format_http_error(response))
        return self.parse_sse_response(response.body, debug_sse_path=debug_sse_path)

    def build_payload(
        self,
        *,
        prompt: str,
        instructions: str | None = None,
        action: str = "generate",
        main_model: str = DEFAULT_MAIN_MODEL,
        model: str = DEFAULT_IMAGE_MODEL,
        input_images: list[str] | None = None,
        mask_image: str | None = None,
        size: str | None = None,
        quality: str | None = None,
        background: str | None = None,
        output_format: str = "png",
        input_fidelity: str | None = None,
        moderation: str | None = None,
        output_compression: int | None = None,
        partial_images: int | None = None,
        web_search: bool = False,
    ) -> dict[str, Any]:
        tool: dict[str, Any] = {
            "type": "image_generation",
            "action": action,
            "model": model,
            "output_format": output_format,
        }
        if size:
            tool["size"] = size
        if quality:
            tool["quality"] = quality
        if background:
            tool["background"] = background
        if input_fidelity and image_model_supports_input_fidelity(model):
            tool["input_fidelity"] = input_fidelity
        if moderation:
            tool["moderation"] = moderation
        if output_compression is not None:
            tool["output_compression"] = output_compression
        if partial_images is not None:
            tool["partial_images"] = partial_images
        if mask_image:
            tool["input_image_mask"] = {"image_url": mask_image}

        content: list[dict[str, str]] = [{"type": "input_text", "text": prompt}]
        for image_url in input_images or []:
            content.append({"type": "input_image", "image_url": image_url})

        tools: list[dict[str, Any]] = [tool]
        tool_choice: Any = {"type": "image_generation"}
        parallel_tool_calls = True
        if web_search:
            tools.insert(0, {"type": "web_search", "search_context_size": "low"})
            tool_choice = "required"
            parallel_tool_calls = False

        return {
            "instructions": self._instructions_with_web_search(instructions, web_search=web_search),
            "stream": True,
            "reasoning": {"effort": "medium", "summary": "auto"},
            "parallel_tool_calls": parallel_tool_calls,
            "include": ["reasoning.encrypted_content"],
            "model": main_model or DEFAULT_MAIN_MODEL,
            "store": False,
            "tool_choice": tool_choice,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": content,
                }
            ],
            "tools": tools,
        }

    @staticmethod
    def _instructions_with_web_search(instructions: str | None, *, web_search: bool) -> str:
        base = str(instructions or "")
        if not web_search:
            return base
        return f"{base}\n\n{WEB_SEARCH_INSTRUCTIONS}".strip()

    def parse_sse_response(self, body: bytes, *, debug_sse_path: str | PathLike[str] | None = None) -> ImageResult:
        output_items_by_index: dict[int, dict[str, Any]] = {}
        output_items_fallback: list[dict[str, Any]] = []

        for raw_line in body.splitlines():
            line = raw_line.strip()
            if not line.startswith(b"data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == b"[DONE]":
                continue
            event = json.loads(payload.decode("utf-8"))
            if debug_sse_path is not None:
                self._write_sse_debug_event(debug_sse_path, event)
            event_type = event.get("type")

            if event_type == "error":
                raise RuntimeError(self._format_sse_error(event))

            if event_type in {"response.failed", "response.incomplete"}:
                raise RuntimeError(self._format_response_terminal_error(event))

            if event_type == "response.output_item.done":
                item = event.get("item")
                if not isinstance(item, dict):
                    continue
                index = event.get("output_index")
                if isinstance(index, int):
                    output_items_by_index[index] = item
                else:
                    output_items_fallback.append(item)
                continue

            if event_type != "response.completed":
                continue

            response = event.get("response", {})
            output = response.get("output") or self._reconstruct_output(output_items_by_index, output_items_fallback)
            result = self._extract_image_call(output)
            if result is None:
                raise RuntimeError(self._format_missing_image_call_error(output))
            image_bytes = base64.b64decode(result["result"])
            usage: dict[str, Any] = {}
            tool_usage = response.get("tool_usage")
            full_tool_usage = dict(tool_usage) if isinstance(tool_usage, dict) else {}
            image_usage = full_tool_usage.get("image_gen")
            if isinstance(image_usage, dict) and image_usage:
                usage = image_usage
            elif isinstance(response.get("usage"), dict):
                usage = response["usage"]
            elif isinstance(image_usage, dict):
                usage = image_usage
            return ImageResult(
                image_bytes=image_bytes,
                revised_prompt=str(result.get("revised_prompt", "")),
                output_format=str(result.get("output_format", "")),
                size=str(result.get("size", "")),
                background=str(result.get("background", "")),
                quality=str(result.get("quality", "")),
                usage=usage,
                tool_usage=full_tool_usage,
            )

        raise RuntimeError("No response.completed event found in SSE stream")

    def _responses_request(self, payload: dict[str, Any]) -> HTTPResponse:
        body = json.dumps(payload).encode("utf-8")
        return self.transport.request(
            method="POST",
            url=self.responses_url,
            headers=self._build_headers(),
            body=body,
        )

    def _responses_request_with_auth_retry(self, payload: dict[str, Any]) -> HTTPResponse:
        response = self._responses_request(payload)
        if self.auth_provider is not None and self._auth_provider_retryable_response(response):
            return self._retry_with_auth_provider(payload, response)

        if response.status != 401:
            return response

        if self.auth_state.refresh_token:
            self.auth_state = refresh_auth_state(self.auth_state, transport=self.transport)
            return self._responses_request(payload)

        return response

    def _retry_with_auth_provider(self, payload: dict[str, Any], response: HTTPResponse) -> HTTPResponse:
        seen_states = {(str(self.auth_state.path), self.auth_state.access_token)}
        retries_remaining = max(1, self.auth_provider.available_count())

        while self._auth_provider_retryable_response(response) and retries_remaining > 0:
            replacement = self.auth_provider.next_auth_state_after_unauthorized(self.auth_state)
            if replacement is None:
                break
            state_key = (str(replacement.path), replacement.access_token)
            if state_key in seen_states:
                break

            self.auth_state = replacement
            seen_states.add(state_key)
            response = self._responses_request(payload)
            retries_remaining -= 1

        return response

    @staticmethod
    def _auth_provider_retryable_response(response: HTTPResponse) -> bool:
        return response.status == 401 or _usage_limit_error(response) is not None

    @staticmethod
    def _format_http_error(response: HTTPResponse) -> str:
        usage_error = _usage_limit_error(response)
        if usage_error is not None:
            return _format_codex_usage_limit_error(usage_error)
        return f"Codex responses request failed: HTTP {response.status}: {_response_body_text(response)}"

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.auth_state.access_token}",
            "Accept": "text/event-stream",
            "Connection": "Keep-Alive",
            "Originator": CODEX_ORIGINATOR,
            "User-Agent": CODEX_USER_AGENT,
            "Session_id": str(uuid.uuid4()),
            "X-Client-Request-Id": str(uuid.uuid4()),
        }
        if self.auth_state.account_id:
            headers["Chatgpt-Account-Id"] = self.auth_state.account_id
        return headers

    @staticmethod
    def _reconstruct_output(
        output_items_by_index: dict[int, dict[str, Any]],
        output_items_fallback: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        ordered = [output_items_by_index[index] for index in sorted(output_items_by_index)]
        ordered.extend(output_items_fallback)
        return ordered

    @staticmethod
    def _format_sse_error(event: dict[str, Any]) -> str:
        error = event.get("error")
        if not isinstance(error, dict):
            return f"Codex SSE error: {json.dumps(event, ensure_ascii=False)}"

        error_type = str(error.get("type") or "").strip()
        code = str(error.get("code") or "").strip()
        message = str(error.get("message") or "").strip()
        prefix = "/".join(part for part in (error_type, code) if part)
        if prefix and message:
            return f"Codex SSE error: {prefix}: {message}"
        if message:
            return f"Codex SSE error: {message}"
        if prefix:
            return f"Codex SSE error: {prefix}"
        return f"Codex SSE error: {json.dumps(error, ensure_ascii=False)}"

    @staticmethod
    def _format_response_terminal_error(event: dict[str, Any]) -> str:
        response = event.get("response")
        error: Any = event.get("error")
        status = str(event.get("type") or "response terminal event")
        if isinstance(response, dict):
            error = response.get("error", error)
            status = str(response.get("status") or status)

        if isinstance(error, dict):
            code = str(error.get("code") or error.get("type") or "").strip()
            message = str(error.get("message") or "").strip()
            if code and message:
                return f"Codex response {status}: {code}: {message}"
            if message:
                return f"Codex response {status}: {message}"
            if code:
                return f"Codex response {status}: {code}"
        if error:
            return f"Codex response {status}: {error}"
        return f"Codex response {status}: {json.dumps(event, ensure_ascii=False)}"

    @staticmethod
    def _extract_image_call(output: Any) -> dict[str, Any] | None:
        if not isinstance(output, list):
            return None
        for item in output:
            if isinstance(item, dict) and item.get("type") == "image_generation_call" and item.get("result"):
                return item
        return None

    @classmethod
    def _format_missing_image_call_error(cls, output: Any) -> str:
        message = cls._extract_output_failure_message(output)
        if message:
            return f"Codex image generation failed: {message}"
        return "Codex completed without image_generation_call output"

    @classmethod
    def _extract_output_failure_message(cls, output: Any) -> str:
        if not isinstance(output, list):
            return ""

        text_parts: list[str] = []
        tool_parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "message":
                text_parts.extend(cls._extract_message_text_parts(item))
            elif item_type == "image_generation_call":
                tool_message = cls._extract_tool_failure_message(item)
                if tool_message:
                    tool_parts.append(tool_message)

        message = cls._join_unique_text_parts(text_parts)
        if message:
            return message
        return cls._join_unique_text_parts(tool_parts)

    @classmethod
    def _extract_message_text_parts(cls, item: dict[str, Any]) -> list[str]:
        parts: list[str] = []
        content = item.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    parts.extend(cls._extract_text_fields(part, ("text", "refusal", "summary")))
                elif isinstance(part, str):
                    parts.append(part)
        elif isinstance(content, str):
            parts.append(content)
        parts.extend(cls._extract_text_fields(item, ("text", "refusal", "summary")))
        return parts

    @classmethod
    def _extract_tool_failure_message(cls, item: dict[str, Any]) -> str:
        error = item.get("error")
        if isinstance(error, dict):
            message = cls._join_unique_text_parts(cls._extract_text_fields(error, ("message", "code", "type")))
            if message:
                return message
        elif isinstance(error, str) and error.strip():
            return error.strip()

        status = str(item.get("status") or "").strip()
        if status and status not in {"completed", "succeeded"}:
            return f"image_generation_call status={status}"
        return ""

    @staticmethod
    def _extract_text_fields(item: dict[str, Any], field_names: tuple[str, ...]) -> list[str]:
        parts: list[str] = []
        for field_name in field_names:
            value = item.get(field_name)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        return parts

    @staticmethod
    def _join_unique_text_parts(parts: list[str]) -> str:
        unique_parts: list[str] = []
        seen: set[str] = set()
        for part in parts:
            text = " ".join(part.split())
            if not text or text in seen:
                continue
            seen.add(text)
            unique_parts.append(text)
        return " ".join(unique_parts)

    @classmethod
    def _write_sse_debug_event(cls, path: str | PathLike[str], event: dict[str, Any]) -> None:
        debug_path = Path(path)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "logged_at": datetime.now(UTC).isoformat(),
            "event": cls._redact_debug_value(event),
        }
        with debug_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")

    @classmethod
    def _redact_debug_value(cls, value: Any, *, key: str | None = None) -> Any:
        if isinstance(value, dict):
            return {str(item_key): cls._redact_debug_value(item_value, key=str(item_key)) for item_key, item_value in value.items()}
        if isinstance(value, list):
            return [cls._redact_debug_value(item) for item in value]
        if isinstance(value, str):
            if key == "result" or key in {"partial_image_b64", "image_b64"}:
                return f"<redacted image base64, {len(value)} chars>"
            if value.startswith("data:image/"):
                return f"<redacted image data url, {len(value)} chars>"
            if cls._looks_like_long_base64(value):
                return f"<redacted probable base64, {len(value)} chars>"
        return value

    @staticmethod
    def _looks_like_long_base64(value: str) -> bool:
        return len(value) >= 512 and re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", value) is not None
