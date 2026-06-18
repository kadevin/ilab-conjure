from __future__ import annotations

import json
import uuid
from os import PathLike
from typing import Any

from .auth import AuthState, refresh_auth_state
from .client_errors import _format_codex_usage_limit_error, _response_body_text, _usage_limit_error
from .client_types import (
    DEFAULT_CODEX_IMAGES_BASE_URL,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_MAIN_MODEL,
    AuthProvider,
    ImageResult,
)
from .codex_responses_client import CODEX_ORIGINATOR, CODEX_USER_AGENT
from .http import HTTPResponse, Transport, UrllibTransport
from .openai_images_client import OpenAIImagesImageClient


class CodexImagesImageClient(OpenAIImagesImageClient):
    def __init__(
        self,
        auth_state: AuthState | None = None,
        *,
        auth_provider: AuthProvider | None = None,
        transport: Transport | None = None,
        base_url: str = DEFAULT_CODEX_IMAGES_BASE_URL,
        image_model: str = DEFAULT_IMAGE_MODEL,
    ) -> None:
        if auth_state is None:
            if auth_provider is None:
                raise TypeError("CodexImagesImageClient requires auth_state or auth_provider")
            auth_state = auth_provider.next_auth_state()
        self.auth_state = auth_state
        self.auth_provider = auth_provider
        self.transport = transport or UrllibTransport()
        self.base_url = self._normalize_base_url(base_url)
        self.image_model = str(image_model or DEFAULT_IMAGE_MODEL).strip() or DEFAULT_IMAGE_MODEL
        self.generations_url = f"{self.base_url}/images/generations"
        self.edits_url = f"{self.base_url}/images/edits"

    def _request_and_parse_many(self, payload: dict[str, Any]) -> list[ImageResult]:
        endpoint = str(payload.get("endpoint") or "/images/generations")
        url = self.edits_url if endpoint == "/images/edits" else self.generations_url
        request_payload = self._json_request_payload(payload)
        response = self._images_request_with_auth_retry(url, request_payload)
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(self._format_http_error(response))
        return self.parse_response_json_items(response.body, request_payload=payload, url_fetcher=self._fetch_image_url)

    def _images_request(self, url: str, payload: dict[str, Any]) -> HTTPResponse:
        body = json.dumps(payload).encode("utf-8")
        return self.transport.request(
            method="POST",
            url=url,
            headers=self._build_headers(),
            body=body,
        )

    def _images_request_with_auth_retry(self, url: str, payload: dict[str, Any]) -> HTTPResponse:
        response = self._images_request(url, payload)
        if self.auth_provider is not None and self._auth_provider_retryable_response(response):
            return self._retry_with_auth_provider(url, payload, response)

        if response.status != 401:
            return response

        if self.auth_state.refresh_token:
            self.auth_state = refresh_auth_state(self.auth_state, transport=self.transport)
            return self._images_request(url, payload)

        return response

    def _retry_with_auth_provider(self, url: str, payload: dict[str, Any], response: HTTPResponse) -> HTTPResponse:
        seen_states = {(str(self.auth_state.path), self.auth_state.access_token)}
        retries_remaining = max(1, self.auth_provider.available_count()) if self.auth_provider is not None else 0

        while self._auth_provider_retryable_response(response) and retries_remaining > 0:
            if self.auth_provider is None:
                break
            replacement = self.auth_provider.next_auth_state_after_unauthorized(self.auth_state)
            if replacement is None:
                break
            state_key = (str(replacement.path), replacement.access_token)
            if state_key in seen_states:
                break

            self.auth_state = replacement
            seen_states.add(state_key)
            response = self._images_request(url, payload)
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
        return f"Codex images request failed: HTTP {response.status}: {_response_body_text(response)}"

    @staticmethod
    def _json_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if key != "endpoint" and value is not None}

    def _build_headers(self, *, content_type: str = "application/json") -> dict[str, str]:
        headers = {
            "Content-Type": content_type,
            "Accept": "application/json",
            "Authorization": f"Bearer {self.auth_state.access_token}",
            "Connection": "Keep-Alive",
            "Originator": CODEX_ORIGINATOR,
            "User-Agent": CODEX_USER_AGENT,
            "Session_id": str(uuid.uuid4()),
            "X-Client-Request-Id": str(uuid.uuid4()),
        }
        if self.auth_state.account_id:
            headers["Chatgpt-Account-Id"] = self.auth_state.account_id
        return headers

    def _build_image_download_headers(self, *, include_auth: bool = False) -> dict[str, str]:
        headers = {
            "Accept": "image/*,*/*",
            "User-Agent": CODEX_USER_AGENT,
        }
        if include_auth:
            headers["Authorization"] = f"Bearer {self.auth_state.access_token}"
            if self.auth_state.account_id:
                headers["Chatgpt-Account-Id"] = self.auth_state.account_id
        return headers

    def generate_image(
        self,
        *,
        prompt: str,
        main_model: str = DEFAULT_MAIN_MODEL,
        model: str | None = None,
        reference_images: list[str] | None = None,
        size: str | None = None,
        quality: str | None = None,
        background: str | None = None,
        output_format: str = "png",
        moderation: str | None = None,
        output_compression: int | None = None,
        partial_images: int | None = None,
        debug_sse_path: str | PathLike[str] | None = None,
        instructions: str | None = None,
        web_search: bool = False,
    ) -> ImageResult:
        del instructions, web_search
        return super().generate_image(
            prompt=prompt,
            main_model=main_model,
            model=model,
            reference_images=reference_images,
            size=size,
            quality=quality,
            background=background,
            output_format=output_format,
            moderation=moderation,
            output_compression=output_compression,
            partial_images=partial_images,
            debug_sse_path=debug_sse_path,
        )

    def edit_image(
        self,
        *,
        prompt: str,
        images: list[str],
        mask_image: str | None = None,
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
        debug_sse_path: str | PathLike[str] | None = None,
        instructions: str | None = None,
        web_search: bool = False,
    ) -> ImageResult:
        del instructions, web_search
        return super().edit_image(
            prompt=prompt,
            images=images,
            mask_image=mask_image,
            main_model=main_model,
            model=model,
            size=size,
            quality=quality,
            background=background,
            output_format=output_format,
            input_fidelity=input_fidelity,
            moderation=moderation,
            output_compression=output_compression,
            partial_images=partial_images,
            debug_sse_path=debug_sse_path,
        )
