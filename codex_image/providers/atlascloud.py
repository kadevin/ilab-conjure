from __future__ import annotations

import json
import time
from collections.abc import Mapping
from typing import Any, Callable
from urllib.parse import quote, urljoin

from codex_image.generation.errors import (
    GenerationProviderError,
    provider_error,
    provider_error_from_exception,
)
from codex_image.generation.types import GenerationResult
from codex_image.openai_images_client import OpenAIImagesImageClient
from codex_image.providers.contracts import ExecutionPlan
from codex_image.providers.openai import image_results_to_generation


_SUCCESS_STATUSES = frozenset({"completed", "succeeded", "success", "done"})
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
        raise ValueError("invalid Atlas Cloud response JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("invalid Atlas Cloud response object")
    if "code" in value and str(value.get("code")) != "200":
        raise ValueError("Atlas Cloud returned an unsuccessful response code")
    return value


def _prediction(value: Mapping[str, Any]) -> dict[str, Any]:
    nested = value.get("data")
    return dict(nested) if isinstance(nested, Mapping) else dict(value)


class AtlasCloudImagesAdapter:
    """Execute Atlas Cloud asynchronous image predictions."""

    def __init__(
        self,
        *,
        transport=None,
        sleep: Callable[[float], None] = time.sleep,
        poll_interval: float = 3.0,
        poll_attempts: int = 200,
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
        try:
            response = client.transport.request(
                method=request.method,
                url=urljoin(f"{client.base_url}/", request.path.lstrip("/")),
                headers=client._build_headers(content_type="application/json"),
                body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            )
            if not 200 <= response.status < 300:
                raise _http_error(plan, response.status)
            submitted = _prediction(_json_object(response.body))
            if self._outputs(submitted):
                return self._parse_result(
                    client, plan, submitted, request_payload=payload
                )
            prediction_id = str(
                submitted.get("id") or submitted.get("request_id") or ""
            ).strip()
            if not prediction_id:
                raise ValueError("Atlas Cloud response is missing a prediction id")
            return self._poll(
                client, plan, submitted, prediction_id, request_payload=payload
            )
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
        submitted: Mapping[str, Any],
        prediction_id: str,
        *,
        request_payload: dict[str, Any],
    ) -> GenerationResult:
        urls = submitted.get("urls")
        result_path = (
            str(urls.get("get") or "").strip() if isinstance(urls, Mapping) else ""
        )
        result_url = (
            result_path
            if result_path.startswith(("http://", "https://"))
            else urljoin(
                f"{client.base_url}/",
                (
                    result_path
                    or f"/api/v1/model/result/{quote(prediction_id, safe='')}"
                ).lstrip("/"),
            )
        )
        headers = client._build_headers(content_type="application/json")
        for _attempt in range(self._poll_attempts):
            self._sleep(self._poll_interval)
            response = client.transport.request(
                method="GET",
                url=result_url,
                headers=headers,
                body=b"",
            )
            if not 200 <= response.status < 300:
                raise _http_error(plan, response.status)
            prediction = _prediction(_json_object(response.body))
            status = str(prediction.get("status") or "").strip().lower()
            if status in _FAILURE_STATUSES:
                raise provider_error(
                    "upstream_error",
                    provider_id=plan.provider.id,
                    canonical_model_id=plan.model.id,
                    protocol_profile=plan.binding.protocol_profile,
                    retryable=False,
                )
            if status in _SUCCESS_STATUSES or self._outputs(prediction):
                return self._parse_result(
                    client,
                    plan,
                    prediction,
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
    def _outputs(prediction: Mapping[str, Any]) -> list[str]:
        outputs = prediction.get("outputs")
        if not isinstance(outputs, list):
            output = prediction.get("output")
            outputs = output if isinstance(output, list) else [output] if output else []
        return [str(item).strip() for item in outputs if str(item).strip()]

    @classmethod
    def _parse_result(
        cls,
        client: OpenAIImagesImageClient,
        plan: ExecutionPlan,
        prediction: Mapping[str, Any],
        *,
        request_payload: dict[str, Any],
    ) -> GenerationResult:
        outputs = cls._outputs(prediction)
        if not outputs:
            raise ValueError("Atlas Cloud prediction completed without image outputs")
        items = []
        for output in outputs:
            header, separator, encoded = output.partition(",")
            if (
                separator
                and header.lower().startswith("data:image/")
                and ";base64" in header.lower()
            ):
                items.append(
                    {"b64_json": encoded, "media_type": header[5:].split(";", 1)[0]}
                )
            else:
                items.append({"url": output})
        normalized = {"data": items}
        results = client.parse_response_json_items(
            json.dumps(normalized, separators=(",", ":")).encode("utf-8"),
            request_payload=request_payload,
            url_fetcher=client._fetch_image_url,
        )
        generation = image_results_to_generation(results)
        metadata = dict(generation.provider_metadata)
        metadata.update(
            {
                "prediction_id": str(
                    prediction.get("id") or prediction.get("request_id") or ""
                ),
                "status": str(prediction.get("status") or ""),
                "requested_parameters": dict(plan.command.parameters),
            }
        )
        return GenerationResult(
            assets=generation.assets,
            text_parts=generation.text_parts,
            usage=generation.usage,
            provider_metadata=metadata,
        )


__all__ = ("AtlasCloudImagesAdapter",)
