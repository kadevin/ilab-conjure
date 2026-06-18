from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncContextManager, Callable

from codex_image.client import DEFAULT_MAIN_MODEL, CodexImagesImageClient, ImageResult, OpenAIImagesImageClient
from codex_image.prompt_guard import build_original_prompt_instructions, build_prompt_guard_instructions

from .executor_inputs import (
    _file_to_data_url,
    _image_mime_type,
    _raise_if_task_cancelled,
    _resolve_gallery_refs,
    _resolve_reference_assets,
    _sniff_image_mime_type,
    _task_cancel_requested,
)
from .executor_progress import _restore_completed_output_progress
from .executor_transport import (
    DEFAULT_API_IMAGES_CONCURRENCY,
    DEFAULT_API_MODE,
    DEFAULT_IMAGE_REQUEST_TIMEOUT_SECONDS,
    DEFAULT_PROMPT_FIDELITY,
    MAX_API_IMAGES_CONCURRENCY,
    MIN_API_IMAGES_CONCURRENCY,
    PROMPT_FIDELITY_MODES,
    _call_image_client,
    _debug_sse_path,
    _direct_images_concurrent_enabled,
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
from .storage import GalleryStorage, ReferenceAssetStorage, TaskStorage
from .task_metadata import (
    _append_output_record_state,
    _finalize_generated_task,
    _is_non_retryable_error,
    _output_thumbnail_fields,
    _output_url,
    _positive_int,
    _write_progress_metadata,
)


async def _execute_stored_task(
    *,
    storage: TaskStorage,
    gallery_storage: GalleryStorage,
    reference_asset_storage: ReferenceAssetStorage,
    task_id: str,
    client: Any,
    batch_delay_seconds: float,
    request_context: Callable[[dict[str, Any]], AsyncContextManager[None]] | None = None,
) -> dict[str, Any]:
    metadata = storage.read_metadata(task_id)
    request = json.loads(storage.request_path(task_id).read_text(encoding="utf-8"))
    params = dict(metadata.get("params") or {})
    mode = str(metadata["mode"])
    prompt = str(metadata["prompt"])
    model_prompt = append_ratio_prompt_instruction(str(metadata.get("prompt_for_model") or prompt), params.get("ratio"))
    prompt_fidelity = _normalize_prompt_fidelity(params.get("prompt_fidelity") or "off")
    raw_constraints = metadata.get("prompt_constraints")
    prompt_constraints = [str(item) for item in raw_constraints] if isinstance(raw_constraints, list) else []
    if prompt_fidelity == "strict":
        guard_instructions = build_prompt_guard_instructions(prompt_constraints)
    elif prompt_fidelity == "original":
        guard_instructions = build_original_prompt_instructions()
    else:
        guard_instructions = ""
    assigned_auth_source = str(metadata.get("assigned_auth_source") or "")
    metadata_backend = str(metadata.get("requested_backend") or metadata.get("backend") or "")
    if assigned_auth_source == "codex":
        if params.get("codex_mode") is not None:
            effective_api_mode = _normalize_api_mode(params.get("codex_mode"))
        elif metadata_backend == "codex_responses":
            effective_api_mode = "responses"
        elif metadata_backend == "codex_images":
            effective_api_mode = "images"
        else:
            effective_api_mode = DEFAULT_API_MODE
    else:
        effective_api_mode = str(params.get("api_mode") or DEFAULT_API_MODE)
    web_search_enabled = bool(params.get("web_search")) and effective_api_mode == "responses"
    transport_prompt = _prompt_for_transport(
        model_prompt,
        auth_source=assigned_auth_source,
        api_mode=effective_api_mode,
        prompt_fidelity=prompt_fidelity,
        instructions=guard_instructions,
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
    gallery_refs, gallery_data_urls = _resolve_gallery_refs(
        gallery_storage,
        [str(ref.get("id")) for ref in metadata.get("gallery_refs", []) if isinstance(ref, dict)],
    )
    data_urls = [_file_to_data_url(path) for path in input_paths if path.exists()] + reference_asset_data_urls + gallery_data_urls
    count = int(params.get("n") or 1)
    debug_sse_path = _debug_sse_path(storage, task_id)
    image_request_timeout_seconds = _image_request_timeout_seconds()
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
                request_payload=request,
                params=params,
                output_records=output_records,
            )

        async def run_single_output(output_number: int) -> dict[str, Any]:
            try:
                async with semaphore:
                    _append_output_record_state(output_records, {"index": output_number, "status": "running"})
                    write_progress_metadata()
                    prompt_kwargs = image_prompt_kwargs()
                    if mode == "edit":
                        result = await _call_image_client(
                            request_context,
                            params,
                            client.edit_image,
                            timeout_seconds=image_request_timeout_seconds,
                            prompt=transport_prompt,
                            images=data_urls,
                            mask_image=mask_data_url,
                            **prompt_kwargs,
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
                            timeout_seconds=image_request_timeout_seconds,
                            prompt=transport_prompt,
                            **prompt_kwargs,
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
                    if result.tool_usage:
                        output_record["tool_usage"] = result.tool_usage
                    output_record.update(_output_thumbnail_fields(storage, task_id, output_number, output_path))
                    _append_output_record_state(output_records, output_record)
                    completed_output_numbers.add(output_number)
                    write_progress_metadata()
                    return {"index": output_number}
            except Exception as exc:
                _raise_if_task_cancelled(storage, task_id)
                failed_record = {
                    "index": output_number,
                    "status": "failed",
                    "error": str(exc),
                    "attempts": 1,
                }
                _append_output_record_state(output_records, failed_record)
                write_progress_metadata()
                if _is_non_retryable_error(exc) or _is_usage_limit_error(exc):
                    return {"index": output_number, "fatal_error": exc, "failed_record": failed_record}
                return {"index": output_number, "failed_record": failed_record}

        tasks = [asyncio.create_task(run_single_output(output_number)) for output_number in remaining_output_numbers]
        fatal_error: Exception | None = None
        try:
            for completed_task in asyncio.as_completed(tasks):
                item = await completed_task
                if isinstance(item.get("fatal_error"), Exception):
                    fatal_error = fatal_error or item["fatal_error"]
        except BaseException:
            for task in tasks:
                if not task.done():
                    task.cancel()
            raise
        if fatal_error is not None and not results:
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
                try:
                    prompt_kwargs = image_prompt_kwargs()
                    if mode == "edit":
                        result = await _call_image_client(
                            request_context,
                            params,
                            client.edit_image,
                            timeout_seconds=image_request_timeout_seconds,
                            prompt=transport_prompt,
                            images=data_urls,
                            mask_image=mask_data_url,
                            **prompt_kwargs,
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
                            timeout_seconds=image_request_timeout_seconds,
                            prompt=transport_prompt,
                            **prompt_kwargs,
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
                    _raise_if_task_cancelled(storage, task_id)
                    break
                except Exception as exc:
                    _raise_if_task_cancelled(storage, task_id)
                    if _is_non_retryable_error(exc):
                        raise
                    if _is_usage_limit_error(exc):
                        raise
                    if attempt >= max_output_attempts:
                        output_records.append(
                            {
                                "index": output_number,
                                "status": "failed",
                                "error": str(exc),
                                "attempts": attempt,
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
            if result.tool_usage:
                output_record["tool_usage"] = result.tool_usage
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
    )
