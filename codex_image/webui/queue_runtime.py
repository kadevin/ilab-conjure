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
    _api_client_from_settings,
    _backend_for_queue_channel,
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
from .queue import NonRetryableTaskError, QueueChannel, QueueManager
from .storage import utc_now


@dataclass(frozen=True)
class QueueRuntimeResult:
    lifespan: Callable[[FastAPI], AsyncContextManager[None]]
    ensure_queue_worker_running: Callable[[], None]
    queue_channel_available: Callable[[QueueChannel], bool]


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


def _client_for_queue_channel(ctx: WebUIContext, channel: QueueChannel, metadata: dict[str, Any] | None = None, *, client_factory_overridden: bool = False) -> Any:
    if client_factory_overridden:
        return ctx.client_factory()
    if channel.auth_source == "api":
        settings_payload = ctx.api_settings.read()
        params = metadata.get("params") if isinstance(metadata, dict) and isinstance(metadata.get("params"), dict) else {}
        provider_settings = ctx.api_settings.provider_settings(str(params.get("api_provider_id") or settings_payload.get("active_provider_id") or ""))
        api_mode = _normalize_api_mode(params.get("api_mode") or provider_settings.get("api_mode"))
        return _api_client_from_settings(provider_settings, api_mode=api_mode)
    codex_mode = _codex_mode_for_task_metadata(metadata, ctx.api_settings)
    client_class = CodexImageClient if codex_mode == "responses" else CodexImagesImageClient
    return client_class(load_auth_state())


def _api_provider_request_context(ctx: WebUIContext, params: dict[str, Any]) -> AsyncContextManager[None]:
    provider_id = str(params.get("api_provider_id") or DEFAULT_API_PROVIDER_ID).strip() or DEFAULT_API_PROVIDER_ID
    limit = _normalize_api_images_concurrency(params.get("api_images_concurrency"))
    record = ctx.api_request_semaphores.get(provider_id)
    if not isinstance(record, dict) or record.get("limit") != limit:
        record = {"limit": limit, "semaphore": asyncio.Semaphore(limit)}
        ctx.api_request_semaphores[provider_id] = record
    return record["semaphore"]


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
    if current_task is not None:
        ctx.running_worker_tasks[task_id] = current_task
    try:
        metadata = ctx.storage.read_metadata(task_id)
        attempt_started_at = utc_now()
        metadata["status"] = "running"
        metadata["started_at"] = metadata.get("started_at") or attempt_started_at
        metadata["attempt_started_at"] = attempt_started_at
        metadata["updated_at"] = attempt_started_at
        metadata["assigned_auth_source"] = channel.auth_source
        metadata["assigned_account_id"] = channel.account_id
        metadata["backend"] = _backend_for_queue_channel(channel, metadata, api_settings=ctx.api_settings)
        metadata["attempts"] = int(metadata.get("attempts") or 0) + 1
        ctx.storage.write_metadata(task_id, metadata)

        client = _client_for_queue_channel(ctx, channel, metadata, client_factory_overridden=client_factory_overridden)
        await _execute_stored_task(
            storage=ctx.storage,
            gallery_storage=ctx.gallery_storage,
            reference_asset_storage=ctx.reference_asset_storage,
            task_id=task_id,
            client=client,
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
        non_retryable = _is_non_retryable_error(exc) or local_usage_limit_error
        metadata["status"] = "failed" if is_final_attempt or non_retryable else "queued"
        metadata["updated_at"] = utc_now()
        metadata["last_error"] = str(exc)
        metadata["error"] = str(exc) if is_final_attempt or non_retryable else ""
        ctx.storage.write_metadata(task_id, metadata)
        if non_retryable:
            raise NonRetryableTaskError(str(exc)) from exc
        raise
    finally:
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
    task_executor = lambda task_id, channel, is_final_attempt: execute_task(
        ctx,
        task_id,
        channel,
        is_final_attempt,
        batch_delay_seconds=batch_delay_seconds,
        client_factory_overridden=client_factory_overridden,
    )
    initial_channels = _queue_channels_for_source(ctx.auth_settings.read_source(), api_settings=ctx.api_settings)
    ctx.queue_manager = QueueManager(
        queue_storage=ctx.queue_storage,
        channels=initial_channels,
        execute_task=task_executor,
        max_attempts=_queue_max_attempts_for_channels(initial_channels),
        channel_available=queue_channel_available,
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
