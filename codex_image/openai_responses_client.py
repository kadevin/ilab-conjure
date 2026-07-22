from __future__ import annotations

import json
from os import PathLike
from typing import Any

from .client_types import (
    DEFAULT_IMAGE_MODEL,
    DEFAULT_MAIN_MODEL,
    DEFAULT_OPENAI_API_BASE_URL,
    OPENAI_COMPATIBLE_USER_AGENT,
    ImageResult,
    ResponsesInputFile,
    ResponsesRequestError,
    _collect_responses_file_data_values,
    image_model_supports_input_fidelity,
    safe_responses_error_message,
)
from .codex_responses_client import CodexImageClient, responses_instructions_with_web_search
from .http import Transport, UrllibTransport
from .openai_images_client import OpenAIImagesImageClient


def build_openai_responses_headers(api_key: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": OPENAI_COMPATIBLE_USER_AGENT,
    }


def build_openai_responses_payload(
    *,
    prompt: str,
    instructions: str | None = None,
    action: str = "generate",
    main_model: str = DEFAULT_MAIN_MODEL,
    model: str | None = None,
    default_model: str = DEFAULT_IMAGE_MODEL,
    input_images: list[str] | None = None,
    input_files: list[ResponsesInputFile] | None = None,
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
    image_model = str(model or default_model or DEFAULT_IMAGE_MODEL).strip() or DEFAULT_IMAGE_MODEL
    tool: dict[str, Any] = {
        "type": "image_generation", "action": action, "model": image_model,
        "output_format": output_format,
    }
    for key, value in (("size", size), ("quality", quality), ("background", background)):
        if value:
            tool[key] = value
    if input_fidelity and image_model_supports_input_fidelity(image_model):
        tool["input_fidelity"] = input_fidelity
    if moderation:
        tool["moderation"] = moderation
    if output_compression is not None:
        tool["output_compression"] = output_compression
    if partial_images is not None:
        tool["partial_images"] = partial_images
    if mask_image:
        tool["input_image_mask"] = {"image_url": mask_image}
    content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    content.extend({"type": "input_image", "image_url": item} for item in input_images or [])
    content.extend(item.to_content_part() for item in input_files or [])
    tools: list[dict[str, Any]] = [tool]
    tool_choice: Any = {"type": "image_generation"}
    if web_search:
        tools.insert(0, {"type": "web_search", "search_context_size": "low"})
        tool_choice = "required"
    payload: dict[str, Any] = {
        "endpoint": "/responses", "stream": True,
        "model": main_model or DEFAULT_MAIN_MODEL, "store": False,
        "tool_choice": tool_choice,
        "input": [{"type": "message", "role": "user", "content": content}],
        "tools": tools,
    }
    if web_search:
        payload["parallel_tool_calls"] = False
    if instructions or web_search:
        payload["instructions"] = responses_instructions_with_web_search(
            instructions, web_search=web_search
        )
    return payload


class OpenAIResponsesImageClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_OPENAI_API_BASE_URL,
        image_model: str = DEFAULT_IMAGE_MODEL,
        transport: Transport | None = None,
    ) -> None:
        clean_key = str(api_key or "").strip()
        if not clean_key:
            raise RuntimeError("OpenAI-compatible API key is required")
        self.api_key = clean_key
        self.base_url = OpenAIImagesImageClient._normalize_base_url(base_url)
        self.image_model = str(image_model or DEFAULT_IMAGE_MODEL).strip() or DEFAULT_IMAGE_MODEL
        self.transport = transport or UrllibTransport()
        self.responses_url = f"{self.base_url}/responses"

    def generate_image(
        self,
        *,
        prompt: str,
        instructions: str | None = None,
        main_model: str = DEFAULT_MAIN_MODEL,
        model: str | None = None,
        reference_images: list[str] | None = None,
        reference_files: list[ResponsesInputFile] | None = None,
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
        action = "edit" if reference_images else "generate"
        payload = self.build_payload(
            prompt=prompt,
            instructions=instructions,
            action=action,
            main_model=main_model,
            model=model,
            input_images=reference_images or [],
            input_files=reference_files,
            size=size,
            quality=quality,
            background=background,
            output_format=output_format,
            moderation=moderation,
            output_compression=output_compression,
            partial_images=partial_images,
            web_search=web_search,
        )
        return self._request_and_parse(payload, debug_sse_path=debug_sse_path)

    def edit_image(
        self,
        *,
        prompt: str,
        images: list[str],
        reference_files: list[ResponsesInputFile] | None = None,
        mask_image: str | None = None,
        instructions: str | None = None,
        main_model: str = DEFAULT_MAIN_MODEL,
        model: str | None = None,
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
            input_files=reference_files,
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
        return self._request_and_parse(payload, debug_sse_path=debug_sse_path)

    def build_payload(
        self,
        *,
        prompt: str,
        instructions: str | None = None,
        action: str = "generate",
        main_model: str = DEFAULT_MAIN_MODEL,
        model: str | None = None,
        input_images: list[str] | None = None,
        input_files: list[ResponsesInputFile] | None = None,
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
        return build_openai_responses_payload(
            prompt=prompt, instructions=instructions, action=action,
            main_model=main_model, model=model, default_model=self.image_model,
            input_images=input_images, input_files=input_files, mask_image=mask_image,
            size=size, quality=quality, background=background,
            output_format=output_format, input_fidelity=input_fidelity,
            moderation=moderation, output_compression=output_compression,
            partial_images=partial_images, web_search=web_search,
        )

    def _request_and_parse(
        self,
        payload: dict[str, Any],
        *,
        debug_sse_path: str | PathLike[str] | None = None,
    ) -> ImageResult:
        body = json.dumps(self._json_request_payload(payload)).encode("utf-8")
        response = self.transport.request(
            method="POST",
            url=self.responses_url,
            headers=self._build_headers(),
            body=body,
        )
        if response.status < 200 or response.status >= 300:
            body_text = response.body.decode("utf-8", errors="replace")
            raise ResponsesRequestError(
                safe_responses_error_message(response.status, body_text),
                status=response.status,
                body=body_text,
                sensitive_values=_collect_responses_file_data_values(payload),
            )
        return self.parse_sse_response(
            response.body,
            debug_sse_path=debug_sse_path,
            sensitive_values=_collect_responses_file_data_values(payload),
        )

    @staticmethod
    def _json_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if key != "endpoint" and value is not None}

    def _build_headers(self) -> dict[str, str]:
        return build_openai_responses_headers(self.api_key)

    parse_sse_response = CodexImageClient.parse_sse_response

    @staticmethod
    def _reconstruct_output(
        output_items_by_index: dict[int, dict[str, Any]],
        output_items_fallback: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return CodexImageClient._reconstruct_output(output_items_by_index, output_items_fallback)

    @staticmethod
    def _format_sse_error(event: dict[str, Any]) -> str:
        return CodexImageClient._format_sse_error(event)

    @staticmethod
    def _format_response_terminal_error(event: dict[str, Any]) -> str:
        return CodexImageClient._format_response_terminal_error(event)

    @staticmethod
    def _extract_image_call(output: Any) -> dict[str, Any] | None:
        return CodexImageClient._extract_image_call(output)

    @staticmethod
    def _format_missing_image_call_error(output: Any) -> str:
        message = CodexImageClient._extract_output_failure_message(output)
        if message:
            return f"OpenAI-compatible responses image generation failed: {message}"
        return "OpenAI-compatible responses completed without image_generation_call output"

    @staticmethod
    def _write_sse_debug_event(
        path: str | PathLike[str],
        event: dict[str, Any],
        *,
        sensitive_values: set[str] | None = None,
    ) -> None:
        CodexImageClient._write_sse_debug_event(
            path,
            event,
            sensitive_values=sensitive_values,
        )
