from __future__ import annotations

import json
import time
from collections.abc import Mapping
from typing import Any, Callable
from urllib.parse import quote

from codex_image.generation.errors import (
    GenerationProviderError,
    provider_error,
    provider_error_from_exception,
)
from codex_image.generation.types import GenerationResult
from codex_image.openai_images_client import (
    OpenAIImagesImageClient,
    build_multipart_body,
)
from codex_image.providers.contracts import ExecutionPlan
from codex_image.providers.openai import image_results_to_generation


_SUCCESS_STATUSES = frozenset({"completed", "success", "done", "finished"})
_FAILURE_STATUSES = frozenset({"failed", "failure", "error", "cancelled", "canceled"})


def _http_error(plan: ExecutionPlan, status: int) -> GenerationProviderError:
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


def _json_object(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("invalid T8 response JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("invalid T8 response object")
    return value


def _normalized_result_payload(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        nested = value.get("data")
        if isinstance(nested, list):
            return {"data": nested, "usage": value.get("usage", {})}
        if value.get("b64_json") or value.get("url"):
            return {"data": [dict(value)]}
    if isinstance(value, list):
        return {"data": value}
    return None


class T8ImagesAdapter:
    """Execute the T8/NewAPI async Images extension and normalize its result."""

    def __init__(
        self,
        *,
        transport=None,
        sleep: Callable[[float], None] = time.sleep,
        poll_interval: float = 10.0,
        poll_attempts: int = 60,
    ) -> None:
        self._transport = transport
        self._sleep = sleep
        self._poll_interval = max(0.0, float(poll_interval))
        self._poll_attempts = max(1, int(poll_attempts))

    def execute(self, plan: ExecutionPlan) -> GenerationResult:
        client = OpenAIImagesImageClient(
            api_key=plan.provider.api_key,
            base_url=plan.provider.base_url,
            image_model=plan.binding.remote_model_id,
            transport=self._transport,
        )
        request = plan.protocol_request
        payload = dict(request.json_body or {})
        if request.files or request.form_fields:
            body, content_type = build_multipart_body(request.form_fields, request.files)
        else:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            content_type = "application/json"
        try:
            response = client.transport.request(
                method=request.method,
                url=f"{client.base_url}{request.path}",
                headers=client._build_headers(content_type=content_type),
                body=body,
            )
            if not 200 <= response.status < 300:
                raise _http_error(plan, response.status)
            submitted = _json_object(response.body)
            task_id = str(submitted.get("task_id") or "").strip()
            if not task_id:
                return self._parse_result(client, plan, submitted, request_payload=payload)
            return self._poll(client, plan, task_id, request_payload=payload)
        except GenerationProviderError:
            raise
        except Exception as exc:
            raise provider_error_from_exception(
                exc,
                provider_id=plan.provider.id,
                canonical_model_id=plan.model.id,
                protocol_profile=plan.binding.protocol_profile,
            ) from exc

    def _poll(
        self,
        client: OpenAIImagesImageClient,
        plan: ExecutionPlan,
        task_id: str,
        *,
        request_payload: dict[str, Any],
    ) -> GenerationResult:
        headers = client._build_headers(content_type="application/json")
        task_url = f"{client.base_url}/images/tasks/{quote(task_id, safe='')}"
        for _attempt in range(self._poll_attempts):
            self._sleep(self._poll_interval)
            response = client.transport.request(
                method="GET",
                url=task_url,
                headers=headers,
                body=b"",
            )
            if not 200 <= response.status < 300:
                raise _http_error(plan, response.status)
            payload = _json_object(response.body)
            envelope = payload.get("data")
            if not isinstance(envelope, Mapping):
                continue
            status = str(envelope.get("status") or "").strip().lower()
            result_payload = _normalized_result_payload(envelope.get("data"))
            if status in _FAILURE_STATUSES:
                raise provider_error(
                    "upstream_error",
                    provider_id=plan.provider.id,
                    canonical_model_id=plan.model.id,
                    protocol_profile=plan.binding.protocol_profile,
                    retryable=False,
                )
            if status in _SUCCESS_STATUSES or result_payload is not None:
                if result_payload is None:
                    break
                return self._parse_result(
                    client,
                    plan,
                    result_payload,
                    request_payload=request_payload,
                )
        raise provider_error(
            "request_timeout",
            provider_id=plan.provider.id,
            canonical_model_id=plan.model.id,
            protocol_profile=plan.binding.protocol_profile,
            status_code=504,
            retryable=True,
        )

    @staticmethod
    def _parse_result(
        client: OpenAIImagesImageClient,
        plan: ExecutionPlan,
        payload: Mapping[str, Any],
        *,
        request_payload: dict[str, Any],
    ) -> GenerationResult:
        normalized = _normalized_result_payload(payload) or dict(payload)
        results = client.parse_response_json_items(
            json.dumps(normalized, separators=(",", ":")).encode("utf-8"),
            request_payload=request_payload,
            url_fetcher=client._fetch_image_url,
        )
        generation = image_results_to_generation(results)
        metadata = dict(generation.provider_metadata)
        metadata["requested_parameters"] = dict(plan.command.parameters)
        return GenerationResult(
            assets=generation.assets,
            text_parts=generation.text_parts,
            usage=generation.usage,
            provider_metadata=metadata,
        )


__all__ = ("T8ImagesAdapter",)
