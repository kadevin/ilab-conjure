from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncContextManager, Callable

from codex_image.client import DEFAULT_MAIN_MODEL, CodexImagesImageClient, ImageResult, OpenAIImagesImageClient
from codex_image.prompt_guard import build_prompt_guard_instructions

from .executor_inputs import (
    _file_to_data_url,
    _image_mime_type,
    _is_reference_file_missing_error,
    _raise_if_task_cancelled,
    _resolve_gallery_refs,
    _resolve_reference_assets,
    _resolve_reference_files,
    _sniff_image_mime_type,
    _task_cancel_requested,
)
from .executor_progress import _restore_completed_output_progress
from .executor_transport import (
    DEFAULT_API_IMAGES_CONCURRENCY,
    DEFAULT_API_MODE,
    DEFAULT_IMAGE_REQUEST_RETRY_COUNT,
    DEFAULT_IMAGE_REQUEST_TIMEOUT_SECONDS,
    DEFAULT_PROMPT_FIDELITY,
    MAX_API_IMAGES_CONCURRENCY,
    MIN_API_IMAGES_CONCURRENCY,
    PROMPT_FIDELITY_MODES,
    _call_image_client,
    _debug_sse_path,
    _direct_images_concurrent_enabled,
    _image_request_attempts,
    _image_request_timeout_seconds,
    _instructions_for_transport,
    _is_usage_limit_error,
    _noop_request_context,
    _normalize_api_images_concurrency,
    _normalize_api_mode,
    _normalize_compression,
    _normalize_prompt_fidelity,
    _parse_optional_int,
    _prompt_for_transport,
)
from .prompt_ratio import append_ratio_prompt_instruction
from .reference_file_capabilities import effective_reference_file_main_model, is_explicit_file_input_rejection
from .reference_files import ReferenceFileStorage
from .storage import GalleryStorage, ReferenceAssetStorage, TaskStorage, utc_now
from .task_metadata import (
    _append_output_record_state,
    _finalize_generated_task,
    _is_non_retryable_error,
    _output_thumbnail_fields,
    _output_url,
    _positive_int,
    _write_progress_metadata,
)


def _format_elapsed_seconds(seconds: float) -> str:
    return f"{max(0.0, seconds):.2f}".rstrip("0").rstrip(".")


def _elapsed_seconds(started_at: float) -> float:
    return round(max(0.0, time.monotonic() - started_at), 3)


def _output_error_message(exc: Exception, *, elapsed_seconds: float, timeout_seconds: float | None) -> str:
    message = str(exc)
    if timeout_seconds is None:
        return message
    legacy_timeout = f"Image request timed out after {timeout_seconds:g}s"
    if message.strip() == legacy_timeout:
        elapsed = _format_elapsed_seconds(elapsed_seconds)
        return f"Image request failed after {elapsed}s (timeout limit {timeout_seconds:g}s): {message}"
    return message


async def _execute_stored_task(
    *,
    storage: TaskStorage,
    gallery_storage: GalleryStorage,
    reference_asset_storage: ReferenceAssetStorage,
    reference_file_storage: ReferenceFileStorage,
    task_id: str,
    client: Any,
    batch_delay_seconds: float,
    request_context: Callable[[dict[str, Any]], AsyncContextManager[None]] | None = None,
    image_request_timeout_seconds: float | None = None,
    image_request_retry_count: int = DEFAULT_IMAGE_REQUEST_RETRY_COUNT,
) -> dict[str, Any]:
    metadata = storage.read_metadata(task_id)
    request = json.loads(storage.request_path(task_id).read_text(encoding="utf-8"))
    params = dict(metadata.get("params") or {})
    params["main_model"] = effective_reference_file_main_model(params.get("main_model"))
    mode = str(metadata["mode"])
    prompt = str(metadata["prompt"])
    prompt_fidelity = _normalize_prompt_fidelity(params.get("prompt_fidelity") or "off")
    prompt_locale = str(metadata.get("prompt_locale") or "zh-CN")
    raw_constraints = metadata.get("prompt_constraints")
    prompt_constraints = [str(item) for item in raw_constraints] if isinstance(raw_constraints, list) else []
    assigned_auth_source = str(metadata.get("assigned_auth_source") or "")
    resolved_backend = str(metadata.get("backend") or metadata.get("requested_backend") or "")
    if resolved_backend in {"codex_responses", "openai_responses"}:
        effective_api_mode = "responses"
    elif resolved_backend in {"codex_images", "openai_images"}:
        effective_api_mode = "images"
    elif assigned_auth_source == "codex":
        effective_api_mode = _normalize_api_mode(params.get("codex_mode"))
    else:
        effective_api_mode = _normalize_api_mode(params.get("api_mode"))
    web_search_enabled = bool(params.get("web_search")) and effective_api_mode == "responses"
    if "execution_prompt" in metadata:
        model_prompt = str(
            metadata.get("execution_model_prompt")
            or metadata.get("prompt_for_model")
            or prompt
        )
        transport_prompt = str(metadata.get("execution_prompt") or "")
        transport_instructions = (
            str(metadata.get("execution_instructions") or "") or None
        )
    else:
        if prompt_fidelity == "original":
            model_prompt = prompt
            guard_instructions = ""
        else:
            model_prompt = append_ratio_prompt_instruction(
                str(metadata.get("prompt_for_model") or prompt),
                params.get("ratio"),
                locale=prompt_locale,
            )
            guard_instructions = (
                build_prompt_guard_instructions(
                    prompt_constraints,
                    locale=prompt_locale,
                )
                if prompt_fidelity == "strict"
                else ""
            )
        transport_prompt = _prompt_for_transport(
            model_prompt,
            auth_source=assigned_auth_source,
            api_mode=effective_api_mode,
            prompt_fidelity=prompt_fidelity,
            instructions=guard_instructions,
            locale=prompt_locale,
        )
        transport_instructions = _instructions_for_transport(
            auth_source=assigned_auth_source,
            api_mode=effective_api_mode,
            instructions=guard_instructions,
        )
    input_paths = [storage.input_path(str(name)) for name in metadata.get("input_files", [])]

    mask_name = metadata.get("mask_file")
    mask_data_url = None
    if isinstance(mask_name, str) and mask_name:
        mask_path = storage.input_path(mask_name)
        mask_data_url = _file_to_data_url(mask_path) if mask_path.exists() else None

    raw_reference_assets = metadata.get("reference_assets")
    reference_asset_items = raw_reference_assets if isinstance(raw_reference_assets, list) else []
    reference_asset_ids = [
        str(item.get("id"))
        for item in reference_asset_items
        if isinstance(item, dict) and item.get("id")
    ]
    reference_assets, reference_asset_data_urls = _resolve_reference_assets(reference_asset_storage, reference_asset_ids, touch=False)
    raw_reference_files = metadata.get("reference_files")
    reference_files = raw_reference_files if isinstance(raw_reference_files, list) else []
    gallery_refs, gallery_data_urls = _resolve_gallery_refs(
        gallery_storage,
        [str(ref.get("id")) for ref in metadata.get("gallery_refs", []) if isinstance(ref, dict)],
    )
    data_urls = [_file_to_data_url(path) for path in input_paths if path.exists()] + reference_asset_data_urls + gallery_data_urls
    count = int(params.get("n") or 1)
    debug_sse_path = _debug_sse_path(storage, task_id)
    effective_image_request_timeout_seconds = (
        _image_request_timeout_seconds()
        if image_request_timeout_seconds is None
        else image_request_timeout_seconds
    )
    results, output_paths, output_records = _restore_completed_output_progress(storage, metadata, params, count)
    completed_output_numbers = {
        int(record["index"])
        for record in output_records
        if isinstance(record.get("index"), int) and record.get("status") == "completed"
    }
    retrying_failed_slots = [
        index
        for index in (_positive_int(value) for value in metadata.get("retrying_failed_slots", []))
        if index is not None and 1 <= index <= count
    ]
    _raise_if_task_cancelled(storage, task_id)
    _write_progress_metadata(
        storage,
        task_id,
        created_at=str(metadata["created_at"]),
        mode=mode,
        prompt=prompt,
        prompt_for_model=model_prompt,
        total_count=count,
        results=results,
        output_paths=output_paths,
        input_files=input_paths,
        gallery_refs=gallery_refs,
        reference_assets=reference_assets,
        reference_files=reference_files,
        request_payload=request,
        params=params,
        output_records=output_records,
    )

    def image_prompt_kwargs() -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if transport_instructions:
            kwargs["instructions"] = transport_instructions
        if web_search_enabled:
            kwargs["web_search"] = True
        return kwargs

    candidate_output_numbers = retrying_failed_slots or list(range(1, count + 1))
    remaining_output_numbers = [index for index in candidate_output_numbers if index not in completed_output_numbers]
    if _direct_images_concurrent_enabled(client, assigned_auth_source, effective_api_mode) and remaining_output_numbers:
        concurrency_limit = _normalize_api_images_concurrency(params.get("api_images_concurrency"))
        semaphore = asyncio.Semaphore(concurrency_limit)

        def write_progress_metadata() -> None:
            _write_progress_metadata(
                storage,
                task_id,
                created_at=str(metadata["created_at"]),
                mode=mode,
                prompt=prompt,
                prompt_for_model=model_prompt,
                total_count=count,
                results=results,
                output_paths=output_paths,
                input_files=input_paths,
                gallery_refs=gallery_refs,
                reference_assets=reference_assets,
                reference_files=reference_files,
                request_payload=request,
                params=params,
                output_records=output_records,
            )

        async def run_single_output(output_number: int) -> dict[str, Any]:
            slot_started_at = utc_now()
            slot_started_monotonic = time.monotonic()

            def failed_output(exc: Exception) -> dict[str, Any]:
                _raise_if_task_cancelled(storage, task_id)
                elapsed_seconds = _elapsed_seconds(slot_started_monotonic)
                failed_at = utc_now()
                failed_record = {
                    "index": output_number,
                    "status": "failed",
                    "error": _output_error_message(
                        exc,
                        elapsed_seconds=elapsed_seconds,
                        timeout_seconds=effective_image_request_timeout_seconds,
                    ),
                    "attempts": _image_request_attempts(exc),
                    "started_at": slot_started_at,
                    "updated_at": failed_at,
                    "failed_at": failed_at,
                    "elapsed_seconds": elapsed_seconds,
                }
                _append_output_record_state(output_records, failed_record)
                write_progress_metadata()
                if _is_non_retryable_error(exc) or _is_usage_limit_error(exc):
                    return {"index": output_number, "fatal_error": exc, "failed_record": failed_record}
                return {"index": output_number, "failed_record": failed_record}

            try:
                async with semaphore:
                    _raise_if_task_cancelled(storage, task_id)
                    request_slot = request_context(params) if request_context is not None else _noop_request_context()
                    async with request_slot:
                        slot_started_at = utc_now()
                        slot_started_monotonic = time.monotonic()
                        try:
                            _append_output_record_state(
                                output_records,
                                {"index": output_number, "status": "running", "started_at": slot_started_at},
                            )
                            write_progress_metadata()
                            prompt_kwargs = image_prompt_kwargs()
                            response_input_files = []
                            try:
                                response_file_kwargs: dict[str, Any] = {}
                                if effective_api_mode == "responses":
                                    _, response_input_files = _resolve_reference_files(
                                        reference_file_storage,
                                        raw_reference_files,
                                    )
                                    response_file_kwargs["reference_files"] = response_input_files
                                if mode == "edit":
                                    result = await _call_image_client(
                                        None,
                                        params,
                                        client.edit_image,
                                        timeout_seconds=effective_image_request_timeout_seconds,
                                        retry_count=image_request_retry_count,
                                        prompt=transport_prompt,
                                        images=data_urls,
                                        mask_image=mask_data_url,
                                        **prompt_kwargs,
                                        **response_file_kwargs,
                                        main_model=params.get("main_model", DEFAULT_MAIN_MODEL),
                                        model=params.get("model", "gpt-image-2"),
                                        size=params.get("size"),
                                        quality=params.get("quality"),
                                        background=params.get("background"),
                                        output_format=params.get("output_format", "png"),
                                        input_fidelity=params.get("input_fidelity"),
                                        moderation=params.get("moderation"),
                                        output_compression=params.get("output_compression"),
                                        debug_sse_path=debug_sse_path,
                                    )
                                else:
                                    result = await _call_image_client(
                                        None,
                                        params,
                                        client.generate_image,
                                        timeout_seconds=effective_image_request_timeout_seconds,
                                        retry_count=image_request_retry_count,
                                        prompt=transport_prompt,
                                        **prompt_kwargs,
                                        **response_file_kwargs,
                                        main_model=params.get("main_model", DEFAULT_MAIN_MODEL),
                                        model=params.get("model", "gpt-image-2"),
                                        reference_images=data_urls,
                                        size=params.get("size"),
                                        quality=params.get("quality"),
                                        background=params.get("background"),
                                        output_format=params.get("output_format", "png"),
                                        moderation=params.get("moderation"),
                                        output_compression=params.get("output_compression"),
                                        debug_sse_path=debug_sse_path,
                                    )
                            finally:
                                response_input_files.clear()
                            _raise_if_task_cancelled(storage, task_id)
                            if not isinstance(result, ImageResult):
                                return {"index": output_number}
                            results.append(result)
                            output_path = storage.write_output(
                                task_id,
                                result.image_bytes,
                                result.output_format or str(params.get("output_format") or "png"),
                                index=output_number,
                            )
                            output_paths.append(output_path)
                            output_record = {
                                "index": output_number,
                                "status": "completed",
                                "file": storage.output_file(output_path),
                                "url": _output_url(storage, output_path),
                                "size": result.size,
                                "format": result.output_format,
                                "quality": result.quality,
                                "background": result.background,
                                "revised_prompt": result.revised_prompt,
                                "usage": result.usage,
                            }
                            request_attempts = _image_request_attempts(result)
                            if request_attempts > 1:
                                output_record["attempts"] = request_attempts
                            if result.tool_usage:
                                output_record["tool_usage"] = result.tool_usage
                            completed_at = utc_now()
                            output_record.update(
                                {
                                    "started_at": slot_started_at,
                                    "updated_at": completed_at,
                                    "completed_at": completed_at,
                                    "elapsed_seconds": _elapsed_seconds(slot_started_monotonic),
                                }
                            )
                            output_record.update(_output_thumbnail_fields(storage, task_id, output_number, output_path))
                            _append_output_record_state(output_records, output_record)
                            completed_output_numbers.add(output_number)
                            write_progress_metadata()
                            return {"index": output_number}
                        except Exception as exc:
                            if is_explicit_file_input_rejection(exc) or _is_reference_file_missing_error(exc):
                                return {"index": output_number, "fatal_error": exc}
                            return failed_output(exc)
            except Exception as exc:
                return failed_output(exc)

        tasks = [asyncio.create_task(run_single_output(output_number)) for output_number in remaining_output_numbers]
        fatal_error: Exception | None = None
        try:
            for completed_task in asyncio.as_completed(tasks):
                item = await completed_task
                if isinstance(item.get("fatal_error"), Exception):
                    fatal_error = fatal_error or item["fatal_error"]
        except BaseException:
            current_task = asyncio.current_task()
            externally_cancelled = bool(
                current_task is not None and current_task.cancelling()
            )
            if _task_cancel_requested(storage, task_id) and not externally_cancelled:
                await asyncio.gather(*tasks, return_exceptions=True)
            else:
                for task in tasks:
                    if not task.done():
                        task.cancel()
            raise
        if fatal_error is not None and (
            not results
            or is_explicit_file_input_rejection(fatal_error)
            or _is_reference_file_missing_error(fatal_error)
        ):
            raise fatal_error
    else:
        for output_index in range(count):
            output_number = output_index + 1
            if output_number in completed_output_numbers:
                continue
            _raise_if_task_cancelled(storage, task_id)
            if output_index > 0 and batch_delay_seconds > 0:
                await asyncio.sleep(batch_delay_seconds)
                _raise_if_task_cancelled(storage, task_id)
            result: ImageResult | None = None
            max_output_attempts = 1
            for attempt in range(1, max_output_attempts + 1):
                slot_started_at = utc_now()
                slot_started_monotonic = time.monotonic()
                try:
                    prompt_kwargs = image_prompt_kwargs()
                    response_input_files = []
                    try:
                        response_file_kwargs: dict[str, Any] = {}
                        if effective_api_mode == "responses":
                            _, response_input_files = _resolve_reference_files(
                                reference_file_storage,
                                raw_reference_files,
                            )
                            response_file_kwargs["reference_files"] = response_input_files
                        if mode == "edit":
                            result = await _call_image_client(
                                request_context,
                                params,
                                client.edit_image,
                                timeout_seconds=effective_image_request_timeout_seconds,
                                retry_count=image_request_retry_count,
                                prompt=transport_prompt,
                                images=data_urls,
                                mask_image=mask_data_url,
                                **prompt_kwargs,
                                **response_file_kwargs,
                                main_model=params.get("main_model", DEFAULT_MAIN_MODEL),
                                model=params.get("model", "gpt-image-2"),
                                size=params.get("size"),
                                quality=params.get("quality"),
                                background=params.get("background"),
                                output_format=params.get("output_format", "png"),
                                input_fidelity=params.get("input_fidelity"),
                                moderation=params.get("moderation"),
                                output_compression=params.get("output_compression"),
                                debug_sse_path=debug_sse_path,
                            )
                        else:
                            result = await _call_image_client(
                                request_context,
                                params,
                                client.generate_image,
                                timeout_seconds=effective_image_request_timeout_seconds,
                                retry_count=image_request_retry_count,
                                prompt=transport_prompt,
                                **prompt_kwargs,
                                **response_file_kwargs,
                                main_model=params.get("main_model", DEFAULT_MAIN_MODEL),
                                model=params.get("model", "gpt-image-2"),
                                reference_images=data_urls,
                                size=params.get("size"),
                                quality=params.get("quality"),
                                background=params.get("background"),
                                output_format=params.get("output_format", "png"),
                                moderation=params.get("moderation"),
                                output_compression=params.get("output_compression"),
                                debug_sse_path=debug_sse_path,
                            )
                    finally:
                        response_input_files.clear()
                    _raise_if_task_cancelled(storage, task_id)
                    break
                except Exception as exc:
                    _raise_if_task_cancelled(storage, task_id)
                    if is_explicit_file_input_rejection(exc) or _is_reference_file_missing_error(exc):
                        raise
                    if _is_non_retryable_error(exc):
                        raise
                    if _is_usage_limit_error(exc):
                        raise
                    if attempt >= max_output_attempts:
                        elapsed_seconds = _elapsed_seconds(slot_started_monotonic)
                        failed_at = utc_now()
                        output_records.append(
                            {
                                "index": output_number,
                                "status": "failed",
                                "error": _output_error_message(
                                    exc,
                                    elapsed_seconds=elapsed_seconds,
                                    timeout_seconds=effective_image_request_timeout_seconds,
                                ),
                                "attempts": _image_request_attempts(exc, attempt),
                                "started_at": slot_started_at,
                                "updated_at": failed_at,
                                "failed_at": failed_at,
                                "elapsed_seconds": elapsed_seconds,
                            }
                        )
                        _write_progress_metadata(
                            storage,
                            task_id,
                            created_at=str(metadata["created_at"]),
                            mode=mode,
                            prompt=prompt,
                            prompt_for_model=model_prompt,
                            total_count=count,
                            results=results,
                            output_paths=output_paths,
                            input_files=input_paths,
                            gallery_refs=gallery_refs,
                            reference_assets=reference_assets,
                            reference_files=reference_files,
                            request_payload=request,
                            params=params,
                            output_records=output_records,
                        )
                    else:
                        continue
            if result is None:
                continue
            results.append(result)
            output_path = storage.write_output(
                task_id,
                result.image_bytes,
                result.output_format or str(params.get("output_format") or "png"),
                index=output_number,
            )
            output_paths.append(output_path)
            output_record = {
                "index": output_number,
                "status": "completed",
                "file": storage.output_file(output_path),
                "url": _output_url(storage, output_path),
                "size": result.size,
                "format": result.output_format,
                "quality": result.quality,
                "background": result.background,
                "revised_prompt": result.revised_prompt,
                "usage": result.usage,
            }
            request_attempts = _image_request_attempts(result)
            if request_attempts > 1:
                output_record["attempts"] = request_attempts
            if result.tool_usage:
                output_record["tool_usage"] = result.tool_usage
            completed_at = utc_now()
            output_record.update(
                {
                    "started_at": slot_started_at,
                    "updated_at": completed_at,
                    "completed_at": completed_at,
                    "elapsed_seconds": _elapsed_seconds(slot_started_monotonic),
                }
            )
            output_record.update(_output_thumbnail_fields(storage, task_id, output_number, output_path))
            output_records.append(output_record)
            completed_output_numbers.add(output_number)
            _write_progress_metadata(
                storage,
                task_id,
                created_at=str(metadata["created_at"]),
                mode=mode,
                prompt=prompt,
                prompt_for_model=model_prompt,
                total_count=count,
                results=results,
                output_paths=output_paths,
                input_files=input_paths,
                gallery_refs=gallery_refs,
                reference_assets=reference_assets,
                reference_files=reference_files,
                request_payload=request,
                params=params,
                output_records=output_records,
            )

    if not results and any(record.get("status") == "failed" for record in output_records):
        failure_messages = [str(record.get("error") or "") for record in output_records if record.get("status") == "failed"]
        raise RuntimeError("; ".join(message for message in failure_messages if message) or "All outputs failed")

    return _finalize_generated_task(
        storage,
        task_id,
        str(metadata["created_at"]),
        mode,
        prompt,
        model_prompt,
        results,
        input_paths,
        gallery_refs,
        reference_assets,
        request,
        params,
        output_paths,
        output_records,
        reference_files,
    )
