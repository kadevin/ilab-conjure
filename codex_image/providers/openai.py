from __future__ import annotations

import json

from codex_image import openai_images_client as openai_images_transport
from codex_image.client_types import ImageResult, _collect_responses_file_data_values
from codex_image.generation.types import GeneratedAsset, GenerationResult
from codex_image.generation.errors import (
    GenerationProviderError,
    provider_error,
    provider_error_from_exception,
)
from codex_image.openai_images_client import OpenAIImagesImageClient, build_multipart_body
from codex_image.openai_responses_client import OpenAIResponsesImageClient
from codex_image.providers.contracts import ExecutionPlan


def image_results_to_generation(results: list[ImageResult]) -> GenerationResult:
    assets = tuple(_asset_from_image_result(result) for result in results)
    usage = results[0].usage if len(results) == 1 else {"images": [dict(item.usage) for item in results]}
    tool_usage = (
        results[0].tool_usage
        if len(results) == 1
        else {"images": [dict(item.tool_usage) for item in results]}
    )
    return GenerationResult(assets=assets, usage=usage, provider_metadata={"tool_usage": tool_usage})


def _asset_from_image_result(result: ImageResult) -> GeneratedAsset:
    width, height = _parse_size(result.size)
    output_format = str(result.output_format or "png").lower()
    mime_type = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
    }.get(output_format, "image/png")
    return GeneratedAsset(
        image_bytes=result.image_bytes,
        mime_type=mime_type,
        width=width,
        height=height,
        revised_prompt=result.revised_prompt,
        metadata={
            "output_format": result.output_format,
            "size": result.size,
            "background": result.background,
            "quality": result.quality,
        },
    )


def _parse_size(value: str) -> tuple[int | None, int | None]:
    try:
        width, height = str(value).lower().split("x", 1)
        return int(width), int(height)
    except (TypeError, ValueError):
        return None, None


class OpenAIImagesAdapter:
    def __init__(self, *, transport=None) -> None:
        self._transport = transport

    def execute(self, plan: ExecutionPlan) -> GenerationResult:
        client = OpenAIImagesImageClient(
            api_key=plan.provider.api_key,
            base_url=plan.provider.base_url,
            image_model=plan.binding.remote_model_id,
            transport=self._transport,
        )
        request = plan.protocol_request
        payload = dict(request.json_body or {})
        path = request.path or str(payload.get("endpoint") or "/images/generations")
        if request.files or request.form_fields:
            body, content_type = build_multipart_body(request.form_fields, request.files)
        elif path == "/images/edits" or request.content_type.startswith("multipart/form-data"):
            body, content_type = client._build_multipart_edit_body(payload)
        else:
            body = json.dumps(client._json_request_payload(payload)).encode("utf-8")
            content_type = "application/json"
        canonical_error_contract = not plan.binding.parameter_codec.startswith("gpt_")
        try:
            response = client.transport.request(
                method=request.method,
                url=f"{client.base_url}{path}",
                headers=client._build_headers(content_type=content_type),
                body=body,
            )
            if canonical_error_contract and not 200 <= response.status < 300:
                raise _canonical_openai_images_http_error(plan, response.status)
            openai_images_transport.raise_for_openai_images_response(response)
            results = client.parse_response_json_items(
                response.body,
                request_payload=payload,
                url_fetcher=client._fetch_image_url,
            )
        except Exception as exc:
            if not canonical_error_contract or isinstance(exc, GenerationProviderError):
                raise
            raise provider_error_from_exception(
                exc,
                provider_id=plan.provider.id,
                canonical_model_id=plan.model.id,
                protocol_profile=plan.binding.protocol_profile,
            ) from exc
        generation = image_results_to_generation(results)
        if not canonical_error_contract:
            return generation
        try:
            response_payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            response_payload = {}
        provider_metadata = dict(generation.provider_metadata)
        provider_metadata["requested_parameters"] = dict(plan.command.parameters)
        if isinstance(response_payload, dict):
            for field in ("model", "moderation", "respect_moderation", "created"):
                if field in response_payload:
                    provider_metadata[field] = response_payload[field]
        return GenerationResult(
            assets=generation.assets,
            text_parts=generation.text_parts,
            usage=generation.usage,
            provider_metadata=provider_metadata,
        )


def _canonical_openai_images_http_error(plan: ExecutionPlan, status: int):
    if status in {400, 422}:
        code, public_status, retryable = "invalid_parameters", 400, False
    elif status in {401, 403}:
        code, public_status, retryable = "authentication_failed", 502, False
    elif status == 429:
        code, public_status, retryable = "rate_limited", 503, True
    elif status >= 500:
        code, public_status, retryable = "upstream_error", 502, True
    else:
        code, public_status, retryable = "upstream_error", 502, False
    return provider_error(
        code,
        provider_id=plan.provider.id,
        canonical_model_id=plan.model.id,
        protocol_profile=plan.binding.protocol_profile,
        status_code=public_status,
        retryable=retryable,
    )


class OpenAIResponsesAdapter:
    def __init__(self, *, transport=None) -> None:
        self._transport = transport

    def execute(self, plan: ExecutionPlan) -> GenerationResult:
        client = OpenAIResponsesImageClient(
            api_key=plan.provider.api_key,
            base_url=plan.provider.base_url,
            image_model=plan.binding.remote_model_id,
            transport=self._transport,
        )
        payload = dict(plan.protocol_request.json_body or {})
        body = json.dumps(client._json_request_payload(payload)).encode("utf-8")
        response = client.transport.request(
            method=plan.protocol_request.method,
            url=f"{client.base_url}{plan.protocol_request.path}",
            headers=client._build_headers(),
            body=body,
        )
        if response.status < 200 or response.status >= 300:
            body_text = response.body.decode("utf-8", errors="replace")
            from codex_image.client_types import ResponsesRequestError, safe_responses_error_message

            raise ResponsesRequestError(
                safe_responses_error_message(response.status, body_text),
                status=response.status,
                body=body_text,
                sensitive_values=_collect_responses_file_data_values(payload),
            )
        result = client.parse_sse_response(
            response.body,
            sensitive_values=_collect_responses_file_data_values(payload),
        )
        return image_results_to_generation([result])


__all__ = (
    "OpenAIImagesAdapter",
    "OpenAIResponsesAdapter",
    "image_results_to_generation",
)
