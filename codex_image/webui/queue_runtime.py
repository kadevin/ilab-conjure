from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncContextManager, Callable

from fastapi import FastAPI

from codex_image.auth import load_auth_state
from codex_image.client import CodexImageClient, CodexImagesImageClient

from .auth_routing import (
    DEFAULT_API_PROVIDER_ID,
    _apply_api_execution_snapshot,
    _api_client_from_settings,
    _backend_for_api_mode,
    _backend_for_codex_mode,
    _codex_mode_for_task_metadata,
    _normalize_api_images_concurrency,
    _normalize_api_mode,
    _queue_channels_for_source,
)
from .context import WebUIContext
from .executor import (
    _execute_stored_task,
    _is_non_retryable_error,
    _is_usage_limit_error,
    _task_cancel_requested,
)
from .executor_inputs import _is_reference_file_missing_error
from .queue import NonRetryableTaskError, QueueChannel, QueueManager
from .reference_file_capabilities import (
    CapabilityKey,
    effective_reference_file_main_model,
    is_explicit_file_input_rejection,
    reference_file_capability_key_for_resolved_backend,
)
from .storage import utc_now


@dataclass(frozen=True)
class QueueRuntimeResult:
    lifespan: Callable[[FastAPI], AsyncContextManager[None]]
    ensure_queue_worker_running: Callable[[], None]
    queue_channel_available: Callable[[QueueChannel], bool]


@dataclass(frozen=True)
class QueueExecutionContract:
    client: Any
    backend: str
    reference_file_capability_key: CapabilityKey
    network_egress: dict[str, Any]


def _queue_channel_by_id(app_instance: FastAPI, channel_id: str) -> QueueChannel | None:
    return next(
        (channel for channel in app_instance.state.queue_manager.channels if channel.channel_id == channel_id),
        None,
    )


async def _queue_channel_worker_loop(app_instance: FastAPI, channel_id: str) -> None:
    while True:
        channel = _queue_channel_by_id(app_instance, channel_id)
        if channel is None:
            return
        try:
            started = await app_instance.state.queue_manager.run_channel_once(channel)
        except Exception:
            started = True
        await asyncio.sleep(0.1 if started else 1.0)


async def _queue_worker_loop(app_instance: FastAPI) -> None:
    workers: dict[str, asyncio.Task[None]] = {}
    while True:
        active_channel_ids = {channel.channel_id for channel in app_instance.state.queue_manager.channels}
        for channel_id in active_channel_ids:
            worker = workers.get(channel_id)
            if worker is None or worker.done():
                workers[channel_id] = asyncio.create_task(_queue_channel_worker_loop(app_instance, channel_id))
        for channel_id, worker in list(workers.items()):
            if worker.done() and channel_id not in active_channel_ids:
                workers.pop(channel_id, None)
        try:
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            for worker in workers.values():
                worker.cancel()
            await asyncio.gather(*workers.values(), return_exceptions=True)
            raise


@asynccontextmanager
async def queue_lifespan(app_instance: FastAPI):
    if app_instance.state.auto_start_queue:
        app_instance.state.queue_worker_task = asyncio.create_task(_queue_worker_loop(app_instance))
    try:
        yield
    finally:
        worker = getattr(app_instance.state, "queue_worker_task", None)
        if worker is not None:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass


def _ensure_queue_worker_running(app_instance: FastAPI) -> None:
    if not app_instance.state.auto_start_queue:
        return
    worker = getattr(app_instance.state, "queue_worker_task", None)
    if worker is not None and worker.done():
        app_instance.state.queue_worker_task = asyncio.create_task(_queue_worker_loop(app_instance))


def _queue_channel_available(ctx: WebUIContext, channel: QueueChannel) -> bool:
    return True


def _provider_from_settings_snapshot(settings: dict[str, Any], provider_id: str) -> dict[str, Any]:
    providers = settings.get("providers") if isinstance(settings.get("providers"), list) else []
    target_id = str(provider_id or settings.get("active_provider_id") or "")
    provider = next(
        (item for item in providers if isinstance(item, dict) and str(item.get("id") or "") == target_id),
        None,
    )
    if provider is None:
        active_provider_id = str(settings.get("active_provider_id") or "")
        provider = next(
            (item for item in providers if isinstance(item, dict) and str(item.get("id") or "") == active_provider_id),
            None,
        )
    if provider is None:
        provider = next((item for item in providers if isinstance(item, dict)), settings)
    return dict(provider)


def _queue_execution_contract(
    ctx: WebUIContext,
    channel: QueueChannel,
    metadata: dict[str, Any] | None = None,
    *,
    client_factory_overridden: bool = False,
) -> QueueExecutionContract:
    params = metadata.get("params") if isinstance(metadata, dict) and isinstance(metadata.get("params"), dict) else {}
    main_model = effective_reference_file_main_model(params.get("main_model"))
    resolved_egress = ctx.network_egress_manager.resolve()
    transport = ctx.network_egress_manager.transport_for(resolved_egress)
    if channel.auth_source == "api":
        settings_payload = ctx.api_settings.read()
        provider_settings = _provider_from_settings_snapshot(
            settings_payload,
            str(params.get("api_provider_id") or settings_payload.get("active_provider_id") or ""),
        )
        api_mode = _normalize_api_mode(params.get("api_mode") or provider_settings.get("api_mode"))
        backend = _backend_for_api_mode(api_mode)
        client = (
            ctx.client_factory()
            if client_factory_overridden
            else _api_client_from_settings(provider_settings, api_mode=api_mode, transport=transport)
        )
        return QueueExecutionContract(
            client=client,
            backend=backend,
            network_egress=resolved_egress.public_snapshot(),
            reference_file_capability_key=reference_file_capability_key_for_resolved_backend(
                requested_backend=backend,
                provider_id=str(provider_settings.get("id") or ""),
                base_url=str(provider_settings.get("base_url") or ""),
                main_model=main_model,
            ),
        )
    codex_mode = _codex_mode_for_task_metadata(metadata, ctx.api_settings)
    backend = _backend_for_codex_mode(codex_mode)
    if client_factory_overridden:
        client = ctx.client_factory()
    else:
        client_class = CodexImageClient if codex_mode == "responses" else CodexImagesImageClient
        client = client_class(load_auth_state(), transport=transport)
    return QueueExecutionContract(
        client=client,
        backend=backend,
        network_egress=resolved_egress.public_snapshot(),
        reference_file_capability_key=reference_file_capability_key_for_resolved_backend(
            requested_backend=backend,
            provider_id="codex",
            base_url="",
            main_model=main_model,
        ),
    )


def _client_for_queue_channel(ctx: WebUIContext, channel: QueueChannel, metadata: dict[str, Any] | None = None, *, client_factory_overridden: bool = False) -> Any:
    return _queue_execution_contract(
        ctx,
        channel,
        metadata,
        client_factory_overridden=client_factory_overridden,
    ).client


def _api_provider_request_context(ctx: WebUIContext, params: dict[str, Any]) -> AsyncContextManager[None]:
    provider_id = str(params.get("api_provider_id") or DEFAULT_API_PROVIDER_ID).strip() or DEFAULT_API_PROVIDER_ID
    limit = _normalize_api_images_concurrency(params.get("api_images_concurrency"))
    record = ctx.api_request_semaphores.get(provider_id)
    if not isinstance(record, dict) or record.get("limit") != limit:
        record = {"limit": limit, "semaphore": asyncio.Semaphore(limit)}
        ctx.api_request_semaphores[provider_id] = record
    return record["semaphore"]


def _positive_int(value: Any, default: int = 1) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _completed_output_numbers(metadata: dict[str, Any]) -> set[int]:
    completed: set[int] = set()
    for output in metadata.get("outputs") or []:
        if not isinstance(output, dict) or output.get("status") != "completed":
            continue
        index = _positive_int(output.get("index"), 0)
        if index > 0:
            completed.add(index)
    return completed


def _api_task_slot_demand(metadata: dict[str, Any], limit: int) -> int:
    params = metadata.get("params") if isinstance(metadata.get("params"), dict) else {}
    count = _positive_int(params.get("n") or metadata.get("total_count"), 1)
    retry_slots = [
        index
        for index in (_positive_int(value, 0) for value in metadata.get("retrying_failed_slots") or [])
        if 1 <= index <= count
    ]
    candidates = retry_slots or list(range(1, count + 1))
    completed = _completed_output_numbers(metadata)
    remaining = [index for index in candidates if index not in completed]
    if not remaining:
        return 0
    return max(1, min(len(remaining), limit))


def _api_responses_task_slot_claim(ctx: WebUIContext, task_id: str, channel: QueueChannel) -> bool:
    if channel.auth_source != "api":
        return True
    try:
        metadata = ctx.storage.read_metadata(task_id)
    except FileNotFoundError:
        return True
    params = metadata.get("params") if isinstance(metadata.get("params"), dict) else {}
    if _normalize_api_mode(params.get("api_mode")) != "responses":
        return True
    provider_id = str(params.get("api_provider_id") or DEFAULT_API_PROVIDER_ID).strip() or DEFAULT_API_PROVIDER_ID
    limit = _normalize_api_images_concurrency(params.get("api_images_concurrency"))
    demand = _api_task_slot_demand(metadata, limit)
    if demand <= 0:
        return True
    used = sum(
        int(record.get("slots") or 0)
        for reserved_task_id, record in ctx.api_task_slot_reservations.items()
        if reserved_task_id != task_id and record.get("provider_id") == provider_id and record.get("api_mode") == "responses"
    )
    if used + demand > limit:
        return False
    ctx.api_task_slot_reservations[task_id] = {
        "provider_id": provider_id,
        "api_mode": "responses",
        "slots": demand,
        "limit": limit,
    }
    return True


def _mark_task_cancelled(ctx: WebUIContext, task_id: str) -> dict[str, Any]:
    metadata = ctx.storage.read_metadata(task_id)
    cancelled_at = utc_now()
    metadata.update(
        {
            "status": "failed",
            "updated_at": cancelled_at,
            "cancelled_at": cancelled_at,
            "cancel_requested": True,
            "error": "Task cancelled by user.",
            "last_error": "Task cancelled by user.",
        }
    )
    metadata.pop("request", None)
    ctx.storage.write_metadata(task_id, metadata)
    return metadata


async def execute_task(
    ctx: WebUIContext,
    task_id: str,
    channel: QueueChannel,
    is_final_attempt: bool,
    *,
    batch_delay_seconds: float,
    client_factory_overridden: bool = False,
) -> None:
    ctx.active_task_ids.add(task_id)
    current_task = asyncio.current_task()
    execution_contract: QueueExecutionContract | None = None
    if current_task is not None:
        ctx.running_worker_tasks[task_id] = current_task
    try:
        metadata = ctx.storage.read_metadata(task_id)
        execution_contract = _queue_execution_contract(
            ctx,
            channel,
            metadata,
            client_factory_overridden=client_factory_overridden,
        )
        attempt_started_at = utc_now()
        metadata["status"] = "running"
        metadata["started_at"] = metadata.get("started_at") or attempt_started_at
        metadata["attempt_started_at"] = attempt_started_at
        metadata["updated_at"] = attempt_started_at
        metadata["assigned_auth_source"] = channel.auth_source
        metadata["assigned_account_id"] = channel.account_id
        metadata["backend"] = execution_contract.backend
        metadata["network_egress"] = execution_contract.network_egress
        if channel.auth_source == "api":
            params = metadata.get("params") if isinstance(metadata.get("params"), dict) else {}
            _apply_api_execution_snapshot(
                ctx.storage,
                task_id,
                metadata,
                ctx.api_settings,
                str(params.get("api_provider_id") or "") or None,
            )
        metadata["attempts"] = int(metadata.get("attempts") or 0) + 1
        ctx.storage.write_metadata(task_id, metadata)

        await _execute_stored_task(
            storage=ctx.storage,
            gallery_storage=ctx.gallery_storage,
            reference_asset_storage=ctx.reference_asset_storage,
            reference_file_storage=ctx.reference_file_storage,
            task_id=task_id,
            client=execution_contract.client,
            batch_delay_seconds=batch_delay_seconds,
            request_context=(lambda params: _api_provider_request_context(ctx, params)) if channel.auth_source == "api" else None,
        )
    except asyncio.CancelledError:
        try:
            if _task_cancel_requested(ctx.storage, task_id):
                _mark_task_cancelled(ctx, task_id)
        except FileNotFoundError:
            pass
        raise
    except Exception as exc:
        usage_limit_error = _is_usage_limit_error(exc)
        local_usage_limit_error = channel.auth_source != "api" and usage_limit_error
        metadata = ctx.storage.read_metadata(task_id)
        reference_file_missing = _is_reference_file_missing_error(exc)
        explicit_file_rejection = (
            execution_contract is not None
            and bool(metadata.get("reference_files"))
            and is_explicit_file_input_rejection(exc)
        )
        if reference_file_missing:
            exc = RuntimeError("reference_file_missing")
        elif explicit_file_rejection:
            ctx.responses_file_unsupported_keys.add(execution_contract.reference_file_capability_key)
            exc = RuntimeError("provider_reference_files_unsupported")
        non_retryable = reference_file_missing or explicit_file_rejection or _is_non_retryable_error(exc) or local_usage_limit_error
        metadata["status"] = "failed" if is_final_attempt or non_retryable else "queued"
        metadata["updated_at"] = utc_now()
        metadata["last_error"] = str(exc)
        metadata["error"] = str(exc) if is_final_attempt or non_retryable else ""
        ctx.storage.write_metadata(task_id, metadata)
        if non_retryable:
            raise NonRetryableTaskError(str(exc)) from exc
        raise
    finally:
        ctx.api_task_slot_reservations.pop(task_id, None)
        if ctx.running_worker_tasks.get(task_id) is current_task:
            ctx.running_worker_tasks.pop(task_id, None)
        ctx.active_task_ids.discard(task_id)


def _queue_max_attempts_for_channels(channels: list[QueueChannel]) -> int:
    retry_identities = {(channel.auth_source, channel.account_id) for channel in channels}
    return max(2, len(retry_identities))


def install_queue_runtime(
    ctx: WebUIContext,
    *,
    batch_delay_seconds: float,
    auto_retry: bool,
    client_factory_overridden: bool = False,
) -> QueueRuntimeResult:
    queue_channel_available = lambda channel: _queue_channel_available(ctx, channel)
    queue_task_claim = lambda task_id, channel: _api_responses_task_slot_claim(ctx, task_id, channel)
    task_executor = lambda task_id, channel, is_final_attempt: execute_task(
        ctx,
        task_id,
        channel,
        is_final_attempt,
        batch_delay_seconds=batch_delay_seconds,
        client_factory_overridden=client_factory_overridden,
    )
    initial_source = "codex" if client_factory_overridden else ctx.auth_settings.read_source()
    initial_channels = _queue_channels_for_source(initial_source, api_settings=ctx.api_settings)
    ctx.queue_manager = QueueManager(
        queue_storage=ctx.queue_storage,
        channels=initial_channels,
        execute_task=task_executor,
        max_attempts=_queue_max_attempts_for_channels(initial_channels),
        channel_available=queue_channel_available,
        claim_task=queue_task_claim,
        auto_retry=auto_retry,
    )
    ctx.install_on_app_state()

    result = QueueRuntimeResult(
        lifespan=queue_lifespan,
        ensure_queue_worker_running=lambda: _ensure_queue_worker_running(ctx.app),
        queue_channel_available=queue_channel_available,
    )
    ctx.route_helpers.update(
        {
            "ensure_queue_worker_running": result.ensure_queue_worker_running,
            "queue_channel_available": result.queue_channel_available,
            "queue_max_attempts_for_channels": _queue_max_attempts_for_channels,
        }
    )
    return result
