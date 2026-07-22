from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncContextManager, Callable

from fastapi import FastAPI

from codex_image.auth import load_auth_state
from codex_image.client import CodexImageClient, CodexImagesImageClient
from codex_image.generation.errors import (
    GenerationProviderError,
    provider_error,
    provider_error_from_exception,
    sanitize_generation_error_text,
)
from codex_image.generation.snapshot import execution_plan_from_snapshot
from codex_image.generation.types import GenerationCommand, ImageInput
from codex_image.prompt_guard import build_original_prompt_instructions, build_prompt_guard_instructions
from codex_image.providers.registry import default_registry

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
from .execution_plan_client import ExecutionPlanImageClient
from .executor_inputs import _is_reference_file_missing_error
from .executor_inputs import (
    _file_to_data_url,
    _resolve_gallery_refs,
    _resolve_reference_assets,
    _resolve_reference_files,
)
from .executor_transport import (
    _instructions_for_transport,
    _normalize_prompt_fidelity,
    _prompt_for_transport,
)
from .queue import NonRetryableTaskError, QueueChannel, QueueManager
from .reference_file_capabilities import (
    CapabilityKey,
    effective_reference_file_main_model,
    is_explicit_file_input_rejection,
    reference_file_capability_key_for_resolved_backend,
)
from .prompt_ratio import append_ratio_prompt_instruction
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


def _queue_channels_with_pending(ctx: WebUIContext, source: str) -> list[QueueChannel]:
    channels = list(_queue_channels_for_source(source, api_settings=ctx.api_settings))
    required: dict[str, int] = {}
    try:
        waiting = ctx.queue_storage.read_state().get("waiting") or []
    except Exception:
        waiting = []
    needs_codex = source == "codex"
    for task_id in waiting:
        try:
            snapshot = ctx.storage.read_metadata(str(task_id)).get("generation_snapshot")
        except (FileNotFoundError, OSError, ValueError):
            continue
        if not isinstance(snapshot, dict):
            continue
        provider_id = str(snapshot.get("provider_id") or "")
        if provider_id == "codex":
            needs_codex = True
            continue
        try:
            limit = max(1, min(32, int(snapshot.get("provider_concurrency") or 1)))
        except (TypeError, ValueError):
            limit = 1
        required[provider_id] = max(required.get(provider_id, 0), limit)
    by_id = {channel.channel_id: channel for channel in channels}
    if needs_codex:
        by_id.setdefault("codex:local", QueueChannel("codex:local", "codex"))
    for provider_id, limit in required.items():
        for slot_index in range(limit):
            channel = QueueChannel(
                f"provider:{provider_id}:{slot_index}",
                "api",
                provider_id=provider_id,
                slot_index=slot_index,
            )
            by_id.setdefault(channel.channel_id, channel)
    return list(by_id.values())


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


def _configured_provider_exact(ctx: WebUIContext, provider_id: str) -> dict[str, Any] | None:
    settings = ctx.api_settings.read()
    for provider in settings.get("providers") or []:
        if isinstance(provider, dict) and str(provider.get("id") or "") == provider_id:
            return dict(provider)
    return None


def _validated_snapshot_plan(ctx: WebUIContext, metadata: dict[str, Any]):
    snapshot = metadata.get("generation_snapshot")
    if not isinstance(snapshot, dict):
        return None
    provider_id = str(snapshot.get("provider_id") or "")
    api_key = ""
    if provider_id != "codex":
        configured = _configured_provider_exact(ctx, provider_id)
        if configured is None or not str(configured.get("api_key") or ""):
            raise provider_error(
                "provider_credentials_missing",
                provider_id=provider_id,
                canonical_model_id=str(snapshot.get("canonical_model_id") or ""),
                protocol_profile=str(snapshot.get("protocol_profile") or ""),
                status_code=400,
                retryable=False,
            )
        api_key = str(configured["api_key"])
    params = metadata.get("params") if isinstance(metadata.get("params"), dict) else {}
    raw_constraints = metadata.get("prompt_constraints")
    constraints = [str(item) for item in raw_constraints] if isinstance(raw_constraints, list) else []
    fidelity = _normalize_prompt_fidelity(params.get("prompt_fidelity") or "off")
    if fidelity == "strict":
        guard_instructions = build_prompt_guard_instructions(constraints)
    elif fidelity == "original":
        guard_instructions = build_original_prompt_instructions()
    else:
        guard_instructions = ""
    profile = str(snapshot.get("protocol_profile") or "")
    auth_source = "codex" if provider_id == "codex" else "api"
    api_mode = "responses" if profile.endswith("responses") else "images"
    model_prompt = append_ratio_prompt_instruction(
        str(metadata.get("prompt_for_model") or metadata.get("prompt") or ""),
        params.get("ratio"),
    )
    transport_prompt = _prompt_for_transport(
        model_prompt,
        auth_source=auth_source,
        api_mode=api_mode,
        prompt_fidelity=fidelity,
        instructions=guard_instructions,
    )
    transport_instructions = _instructions_for_transport(
        auth_source=auth_source,
        api_mode=api_mode,
        instructions=guard_instructions,
    )
    input_paths = [ctx.storage.input_path(str(name)) for name in metadata.get("input_files") or ()]
    raw_assets = metadata.get("reference_assets")
    asset_ids = [
        str(item.get("id"))
        for item in raw_assets if isinstance(item, dict) and item.get("id")
    ] if isinstance(raw_assets, list) else []
    _, asset_data_urls = _resolve_reference_assets(
        ctx.reference_asset_storage, asset_ids, touch=False
    )
    _, gallery_data_urls = _resolve_gallery_refs(
        ctx.gallery_storage,
        [
            str(item.get("id"))
            for item in metadata.get("gallery_refs") or ()
            if isinstance(item, dict) and item.get("id")
        ],
    )
    image_data_urls = [
        _file_to_data_url(path) for path in input_paths if path.exists()
    ] + asset_data_urls + gallery_data_urls
    mask_data_url = None
    mask_name = metadata.get("mask_file")
    if isinstance(mask_name, str) and mask_name:
        mask_path = ctx.storage.input_path(mask_name)
        if mask_path.exists():
            mask_data_url = _file_to_data_url(mask_path)
    _, reference_file_inputs = _resolve_reference_files(
        ctx.reference_file_storage,
        metadata.get("reference_files"),
    )
    command = GenerationCommand(
        operation=str(metadata.get("mode") or "generate"),  # type: ignore[arg-type]
        canonical_model_id=str(snapshot.get("canonical_model_id") or ""),
        provider_id=provider_id,
        prompt=transport_prompt,
        parameters=dict(snapshot.get("requested_parameters") or {}),
        image_inputs=tuple(ImageInput(item) for item in image_data_urls),
        reference_files=tuple(reference_file_inputs),
        mask_image=mask_data_url,
        main_model=str(params.get("main_model") or "") or None,
        instructions=transport_instructions,
        legacy_compat_parameters=dict(snapshot.get("legacy_compat_parameters") or {}),
    )
    return execution_plan_from_snapshot(
        snapshot=snapshot,
        command=command,
        api_key=api_key,
        registry=default_registry(),
    )


def _queue_execution_contract(
    ctx: WebUIContext,
    channel: QueueChannel,
    metadata: dict[str, Any] | None = None,
    *,
    client_factory_overridden: bool = False,
) -> QueueExecutionContract:
    params = metadata.get("params") if isinstance(metadata, dict) and isinstance(metadata.get("params"), dict) else {}
    main_model = effective_reference_file_main_model(params.get("main_model"))
    snapshot_plan = _validated_snapshot_plan(ctx, metadata or {})
    if snapshot_plan is not None:
        if snapshot_plan.provider.id == "codex":
            channel_matches = channel.auth_source == "codex"
        else:
            channel_matches = (
                channel.auth_source == "api"
                and channel.provider_id == snapshot_plan.provider.id
                and channel.slot_index < snapshot_plan.provider.concurrency
            )
        if not channel_matches:
            raise provider_error(
                "snapshot_manifest_incompatible",
                provider_id=snapshot_plan.provider.id,
                canonical_model_id=snapshot_plan.model.id,
                protocol_profile=snapshot_plan.binding.protocol_profile,
                status_code=400,
                retryable=False,
            )
        profile = snapshot_plan.binding.protocol_profile
        backend = profile
        if snapshot_plan.provider.id == "codex":
            codex_mode = "responses" if profile == "codex_responses" else "images"
            if client_factory_overridden:
                client = ctx.client_factory()
            else:
                client_class = CodexImageClient if codex_mode == "responses" else CodexImagesImageClient
                client = client_class(load_auth_state())
            base_url = ""
        else:
            api_mode = "responses" if profile == "openai_responses" else "images"
            frozen = {
                "api_key": snapshot_plan.provider.api_key,
                "base_url": snapshot_plan.provider.base_url,
                "image_model": snapshot_plan.binding.remote_model_id,
                "api_mode": api_mode,
            }
            client = ctx.client_factory() if client_factory_overridden else _api_client_from_settings(frozen, api_mode=api_mode)
            base_url = snapshot_plan.provider.base_url
        return QueueExecutionContract(
            client=ExecutionPlanImageClient(snapshot_plan, client),
            backend=backend,
            reference_file_capability_key=reference_file_capability_key_for_resolved_backend(
                requested_backend=backend,
                provider_id=snapshot_plan.provider.id,
                base_url=base_url,
                main_model=main_model,
            ),
        )
    if channel.auth_source == "api":
        settings_payload = ctx.api_settings.read()
        provider_settings = _provider_from_settings_snapshot(
            settings_payload,
            str(params.get("api_provider_id") or settings_payload.get("active_provider_id") or ""),
        )
        api_mode = _normalize_api_mode(params.get("api_mode") or provider_settings.get("api_mode"))
        backend = _backend_for_api_mode(api_mode)
        client = ctx.client_factory() if client_factory_overridden else _api_client_from_settings(provider_settings, api_mode=api_mode)
        return QueueExecutionContract(
            client=client,
            backend=backend,
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
        client = client_class(load_auth_state())
    return QueueExecutionContract(
        client=client,
        backend=backend,
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
    try:
        metadata = ctx.storage.read_metadata(task_id)
    except FileNotFoundError:
        return True
    snapshot = metadata.get("generation_snapshot")
    if isinstance(snapshot, dict):
        provider_id = str(snapshot.get("provider_id") or "")
        if provider_id == "codex":
            return channel.auth_source == "codex"
        if channel.auth_source != "api" or channel.provider_id != provider_id:
            return False
        try:
            concurrency = max(1, min(32, int(snapshot.get("provider_concurrency") or 1)))
        except (TypeError, ValueError):
            concurrency = 1
        if channel.slot_index >= concurrency:
            return False
    elif channel.auth_source != "api":
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
    available = max(0, limit - used)
    if available <= 0:
        return False
    ctx.api_task_slot_reservations[task_id] = {
        "provider_id": provider_id,
        "api_mode": "responses",
        "slots": demand,
        "limit": limit,
    }
    return True


def _task_channel_matches(ctx: WebUIContext, task_id: str, channel: QueueChannel) -> bool:
    try:
        metadata = ctx.storage.read_metadata(task_id)
    except FileNotFoundError:
        return True
    snapshot = metadata.get("generation_snapshot")
    if not isinstance(snapshot, dict):
        return True
    provider_id = str(snapshot.get("provider_id") or "")
    if provider_id == "codex":
        return channel.auth_source == "codex"
    if channel.auth_source != "api" or channel.provider_id != provider_id:
        return False
    try:
        concurrency = max(1, min(32, int(snapshot.get("provider_concurrency") or 1)))
    except (TypeError, ValueError):
        concurrency = 1
    return channel.slot_index < concurrency


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


def _structured_task_error(ctx: WebUIContext, metadata: dict[str, Any], exc: BaseException):
    snapshot = metadata.get("generation_snapshot")
    if isinstance(snapshot, dict) and isinstance(exc, GenerationProviderError):
        error: GenerationProviderError | None = exc
    elif isinstance(snapshot, dict):
        error = provider_error_from_exception(
            exc,
            provider_id=str(snapshot.get("provider_id") or ""),
            canonical_model_id=str(snapshot.get("canonical_model_id") or ""),
            protocol_profile=str(snapshot.get("protocol_profile") or ""),
        )
    else:
        error = None
    credentials: list[str] = []
    try:
        for provider in ctx.api_settings.read_connections():
            if provider.api_key:
                credentials.append(provider.api_key)
    except Exception:
        pass
    prompts = tuple(
        str(item)
        for item in (metadata.get("prompt"), metadata.get("prompt_for_model"))
        if isinstance(item, str) and item
    )
    safe = sanitize_generation_error_text(
        exc,
        sensitive_values=tuple(credentials),
        prompt_values=prompts,
    )
    return error, safe


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
        attempt_started_at = utc_now()
        metadata["status"] = "running"
        metadata["started_at"] = metadata.get("started_at") or attempt_started_at
        metadata["attempt_started_at"] = attempt_started_at
        metadata["updated_at"] = attempt_started_at
        metadata["assigned_auth_source"] = channel.auth_source
        metadata["assigned_account_id"] = channel.account_id
        metadata["attempts"] = int(metadata.get("attempts") or 0) + 1
        ctx.storage.write_metadata(task_id, metadata)

        execution_contract = _queue_execution_contract(
            ctx,
            channel,
            metadata,
            client_factory_overridden=client_factory_overridden,
        )
        metadata["backend"] = execution_contract.backend
        if channel.auth_source == "api" and not isinstance(metadata.get("generation_snapshot"), dict):
            params = metadata.get("params") if isinstance(metadata.get("params"), dict) else {}
            _apply_api_execution_snapshot(
                ctx.storage,
                task_id,
                metadata,
                ctx.api_settings,
                str(params.get("api_provider_id") or "") or None,
            )
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
        structured_error, safe_error = _structured_task_error(ctx, metadata, exc)
        provider_non_retryable = isinstance(exc, GenerationProviderError) and not exc.detail.retryable
        non_retryable = reference_file_missing or explicit_file_rejection or provider_non_retryable or _is_non_retryable_error(exc) or local_usage_limit_error
        metadata["status"] = "failed" if is_final_attempt or non_retryable else "queued"
        metadata["updated_at"] = utc_now()
        metadata["last_error"] = safe_error
        metadata["error"] = safe_error if is_final_attempt or non_retryable else ""
        if structured_error is not None:
            metadata["generation_error"] = structured_error.detail.to_dict()
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
    retry_identities = {
        (channel.auth_source, channel.account_id, channel.provider_id)
        for channel in channels
    }
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
    task_channel_matches = lambda task_id, channel: _task_channel_matches(ctx, task_id, channel)
    task_executor = lambda task_id, channel, is_final_attempt: execute_task(
        ctx,
        task_id,
        channel,
        is_final_attempt,
        batch_delay_seconds=batch_delay_seconds,
        client_factory_overridden=client_factory_overridden,
    )
    initial_source = "codex" if client_factory_overridden else ctx.auth_settings.read_source()
    initial_channels = _queue_channels_with_pending(ctx, initial_source)
    ctx.queue_manager = QueueManager(
        queue_storage=ctx.queue_storage,
        channels=initial_channels,
        execute_task=task_executor,
        max_attempts=_queue_max_attempts_for_channels(initial_channels),
        channel_available=queue_channel_available,
        claim_task=queue_task_claim,
        task_channel_matches=task_channel_matches,
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
