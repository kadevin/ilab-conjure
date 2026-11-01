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
from codex_image.generation.partial_results import PartialGenerationError
from codex_image.openai_images_client import (
    OpenAIImagesImageClient,
    PartialImageResultsError,
    build_multipart_body,
)
from codex_image.providers.contracts import ExecutionPlan
from codex_image.providers.openai import image_results_to_generation
from codex_image.providers.result_assets import AssetLoadError


_SUCCESS_STATUSES = frozenset({"completed", "success", "done", "finished"})
_FAILURE_STATUSES = frozenset({"failed", "failure", "error", "cancelled", "canceled"})


def _http_error(plan: ExecutionPlan, status: int, *, generation_request: bool = False) -> GenerationProviderError:
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
    if generation_request and status >= 500:
        retryable = False
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
        raise AssetLoadError("invalid T8 response JSON") from exc
    if not isinstance(value, dict):
        raise AssetLoadError("invalid T8 response object")
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
        progress = plan.progress
        identity = {"provider_id": plan.provider.id, "base_url": plan.provider.base_url,
                    "binding_id": plan.binding.id, "model": plan.binding.remote_model_id}
        state = dict(progress.state) if progress is not None else {}
        if state.get("identity") != identity:
            state = {"identity": identity, "tasks": []}
        slots = progress.output_slots if progress is not None else ()
        tasks = state.setdefault("tasks", [])
        saved = next((item for item in tasks if slots and slots[0] in item.get("output_slots", [])
                      and not item.get("failed")), None)

        def checkpoint() -> None:
            if progress is not None:
                try:
                    progress.checkpoint(state)
                except Exception as exc:
                    raise AssetLoadError("remote task checkpoint could not be saved locally") from exc

        def terminal_failure() -> None:
            if saved is not None:
                saved["failed"] = True
                checkpoint()

        def select_pending_outputs(result_payload: dict[str, Any]) -> dict[str, Any]:
            items = result_payload.get("data")
            if saved is None or not slots or not isinstance(items, list):
                return result_payload
            # Persist the remote result's slot mapping before downloading any
            # image. Completed local slots never need their remote URL again.
            saved["output_slots"] = saved["output_slots"][:len(items)]
            checkpoint()
            selected = [item for slot, item in zip(saved["output_slots"], items) if slot in slots]
            if not selected:
                raise AssetLoadError("remote task returned no image for the requested slot")
            return {**result_payload, "data": selected}

        if request.files or request.form_fields:
            body, content_type = build_multipart_body(request.form_fields, request.files)
        else:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            content_type = "application/json"
        try:
            if saved is None:
                response = client.transport.request(
                    method=request.method,
                    url=f"{client.base_url}{request.path}",
                    headers=client._build_headers(content_type=content_type),
                    body=body,
                )
                if not 200 <= response.status < 300:
                    raise _http_error(plan, response.status, generation_request=True)
                submitted = _json_object(response.body)
                task_id = str(submitted.get("task_id") or "").strip()
                if not task_id:
                    result = self._parse_result(client, plan, submitted, request_payload=payload)
                    if not result.assets and result.asset_outcomes:
                        raise result.asset_outcomes[0]
                    return result
                saved = {"task_id": task_id, "output_slots": list(slots)}
                tasks.append(saved)
                # Persist acceptance before the first poll, including on cancellation.
                checkpoint()
            result = self._poll(client, plan, saved["task_id"], request_payload=payload,
                                on_failure=terminal_failure, select_outputs=select_pending_outputs)
            if not result.assets and result.asset_outcomes:
                raise result.asset_outcomes[0]
            return result
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
        on_failure: Callable[[], None] | None = None,
        select_outputs: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
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
                if on_failure is not None:
                    on_failure()
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
                if select_outputs is not None:
                    result_payload = select_outputs(result_payload)
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
        outcomes = []
        try:
            results = client.parse_response_json_items(
                json.dumps(normalized, separators=(",", ":")).encode("utf-8"),
                request_payload=request_payload,
                url_fetcher=client._fetch_image_url,
                asset_outcomes=outcomes,
            )
        except PartialImageResultsError as exc:
            raise PartialGenerationError(
                image_results_to_generation(exc.results, asset_outcomes=exc.outcomes), exc.completed_at,
            ) from exc
        generation = image_results_to_generation(results, asset_outcomes=outcomes)
        metadata = dict(generation.provider_metadata)
        metadata["requested_parameters"] = dict(plan.command.parameters)
        return GenerationResult(
            assets=generation.assets,
            text_parts=generation.text_parts,
            usage=generation.usage,
            provider_metadata=metadata,
            asset_outcomes=generation.asset_outcomes,
        )


__all__ = ("T8ImagesAdapter",)
