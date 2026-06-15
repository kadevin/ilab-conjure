from __future__ import annotations

from pathlib import Path
import re
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from fastapi import HTTPException

from codex_image.client import ImageResult

from .storage import TaskStorage, utc_now
from .task_enrichment import _input_sources, _input_urls
from .thumbnails import create_image_thumbnail, thumbnail_needs_refresh


def _normalize_api_images_concurrency_for_metadata(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 4
    return min(32, max(1, parsed))


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _safe_nonnegative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def _append_output_record_state(output_records: list[dict[str, Any]], record: dict[str, Any]) -> None:
    index = _positive_int(record.get("index"))
    if index is not None:
        output_records[:] = [
            item
            for item in output_records
            if _positive_int(item.get("index")) != index
        ]
    output_records.append(record)


def _completed_output_records_for_accept(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    output_records = metadata.get("outputs")
    if isinstance(output_records, list):
        completed = [
            dict(record)
            for record in output_records
            if isinstance(record, dict) and record.get("status") == "completed"
        ]
        if completed:
            return completed

    urls = metadata.get("output_urls") if isinstance(metadata.get("output_urls"), list) else []
    files = metadata.get("output_files") if isinstance(metadata.get("output_files"), list) else []
    if not urls and metadata.get("output_url"):
        urls = [metadata.get("output_url")]
    if not files and metadata.get("output_file"):
        files = [metadata.get("output_file")]
    completed = []
    for index, url in enumerate(urls, start=1):
        record: dict[str, Any] = {"index": index, "status": "completed", "url": url}
        if index <= len(files):
            record["file"] = files[index - 1]
        completed.append(record)
    return completed


def _accept_partial_task_successes(storage: TaskStorage, task_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
    completed_records = _completed_output_records_for_accept(metadata)
    if not completed_records:
        raise ValueError("Task has no successful outputs to accept")

    raw_outputs = metadata.get("outputs") if isinstance(metadata.get("outputs"), list) else []
    failed_records = [
        record
        for record in raw_outputs
        if isinstance(record, dict) and record.get("status") == "failed"
    ]
    success_count = len(completed_records)
    original_total_count = (
        _positive_int(metadata.get("original_total_count"))
        or _positive_int(metadata.get("total_count"))
        or success_count + len(failed_records)
    )
    cleared_failed_count = len(failed_records) or _safe_nonnegative_int(metadata.get("failed_count"))
    if cleared_failed_count <= 0:
        cleared_failed_count = max(0, original_total_count - success_count)

    accepted_outputs: list[dict[str, Any]] = []
    for new_index, record in enumerate(completed_records, start=1):
        accepted_record = dict(record)
        accepted_record["index"] = new_index
        accepted_record["status"] = "completed"
        accepted_record.pop("error", None)
        accepted_outputs.append(accepted_record)

    output_files = [str(record.get("file")) for record in accepted_outputs if record.get("file")]
    output_urls = [str(record.get("url")) for record in accepted_outputs if record.get("url")]
    accepted_at = utc_now()
    metadata.update(
        {
            "status": "completed",
            "updated_at": accepted_at,
            "viewed_at": accepted_at,
            "generated_count": success_count,
            "failed_count": 0,
            "total_count": success_count,
            "outputs": accepted_outputs,
            "output_files": output_files,
            "output_urls": output_urls,
            "original_total_count": original_total_count,
            "cleared_failed_count": cleared_failed_count,
            "partial_failure_cleared_at": accepted_at,
        }
    )
    if output_files:
        metadata["output_file"] = output_files[0]
    else:
        metadata.pop("output_file", None)
    if output_urls:
        metadata["output_url"] = output_urls[0]
    else:
        metadata.pop("output_url", None)

    for key in ("output_sizes", "output_formats", "qualities", "backgrounds", "revised_prompts", "usages", "tool_usages"):
        if isinstance(metadata.get(key), list):
            metadata[key] = metadata[key][:success_count]
    scalar_sources = {
        "output_size": "output_sizes",
        "output_format": "output_formats",
        "quality": "qualities",
        "background": "backgrounds",
        "revised_prompt": "revised_prompts",
        "usage": "usages",
        "tool_usage": "tool_usages",
    }
    for scalar_key, list_key in scalar_sources.items():
        values = metadata.get(list_key)
        if isinstance(values, list) and values:
            metadata[scalar_key] = values[0]

    for key in ("error", "last_error", "retrying_failed_slots", "retry_failed_slots", "retry_requested_at"):
        metadata.pop(key, None)
    storage.write_metadata(task_id, metadata)
    return metadata


def _retryable_failed_output_indexes(metadata: dict[str, Any]) -> list[int]:
    total = _positive_int(metadata.get("total_count")) or _positive_int((metadata.get("params") or {}).get("n")) or 1
    task_error = str(metadata.get("error") or metadata.get("last_error") or "")
    if _is_non_retryable_task_error(metadata, task_error):
        return []
    failed_records = [
        record
        for record in metadata.get("outputs", [])
        if isinstance(record, dict) and record.get("status") == "failed"
    ]
    retryable: list[int] = []
    if failed_records:
        for fallback_index, record in enumerate(failed_records, start=1):
            error = str(record.get("error") or metadata.get("last_error") or metadata.get("error") or "")
            if _is_non_retryable_failed_slot_error(metadata, error):
                continue
            index = _positive_int(record.get("index")) or fallback_index
            if 1 <= index <= total and index not in retryable:
                retryable.append(index)
        return sorted(retryable)

    if metadata.get("status") == "failed":
        completed_indexes: set[int] = set()
        outputs = metadata.get("outputs")
        if isinstance(outputs, list):
            for fallback_index, record in enumerate(outputs, start=1):
                if not isinstance(record, dict) or record.get("status") != "completed":
                    continue
                index = _positive_int(record.get("index")) or fallback_index
                if 1 <= index <= total:
                    completed_indexes.add(index)
        if completed_indexes:
            return [index for index in range(1, total + 1) if index not in completed_indexes]
        return list(range(1, total + 1))
    return []


def _ordered_output_progress(
    results: list[ImageResult],
    output_paths: list[Path],
    output_records: list[dict[str, Any]],
) -> tuple[list[ImageResult], list[Path], list[dict[str, Any]]]:
    indexed_records = list(enumerate(output_records))
    ordered_records = [
        record
        for _, record in sorted(
            indexed_records,
            key=lambda item: (_positive_int(item[1].get("index")) or len(output_records) + item[0] + 1, item[0]),
        )
    ]
    completed_records = [record for record in output_records if record.get("status") == "completed"]
    if len(completed_records) != len(results) or len(results) != len(output_paths):
        return results, output_paths, ordered_records
    completed_pairs = list(zip(completed_records, results, output_paths))
    ordered_pairs = sorted(
        completed_pairs,
        key=lambda item: (_positive_int(item[0].get("index")) or len(completed_pairs) + 1),
    )
    return (
        [result for _, result, _ in ordered_pairs],
        [path for _, _, path in ordered_pairs],
        ordered_records,
    )


def _is_non_retryable_error(exc: BaseException) -> bool:
    if isinstance(exc, HTTPException):
        detail = str(exc.detail or "").lower()
        return exc.status_code in {400, 404} and "reference asset" in detail
    message = str(exc).lower()
    if "reference asset" in message and (
        "404:" in message
        or "400:" in message
        or "not found" in message
        or "invalid reference asset id" in message
    ):
        return True
    if "http 400" not in message:
        return False
    return (
        "invalid_request_error" in message
        or "invalid_value" in message
        or "expected a base64-encoded data url" in message
        or "unsupported mime type" in message
    )


def _is_non_retryable_task_error(metadata: dict[str, Any], error: str) -> bool:
    if not _is_non_retryable_error(RuntimeError(error)):
        return False
    if metadata.get("status") != "partial_failed":
        return True
    return _successful_output_count(metadata) <= 0


def _is_non_retryable_failed_slot_error(metadata: dict[str, Any], error: str) -> bool:
    if not _is_non_retryable_error(RuntimeError(error)):
        return False
    if metadata.get("status") == "partial_failed" and _successful_output_count(metadata) > 0 and _is_generic_invalid_request_error(error):
        return False
    return True


def _successful_output_count(metadata: dict[str, Any]) -> int:
    outputs = metadata.get("outputs")
    if isinstance(outputs, list):
        return sum(1 for record in outputs if isinstance(record, dict) and record.get("status") == "completed")
    return _positive_int(metadata.get("generated_count")) or 0


def _is_generic_invalid_request_error(error: str) -> bool:
    message = str(error or "").lower()
    return (
        "http 400" in message
        and "invalid_request_error" in message
        and "invalid_value" not in message
        and "expected a base64-encoded data url" not in message
        and "unsupported mime type" not in message
        and "reference asset" not in message
    )


def _output_url(storage: TaskStorage, path: Path) -> str:
    return f"/outputs/{quote(storage.output_file(path), safe='/')}"


def _output_thumbnail_fields(storage: TaskStorage, task_id: str, output_index: int, output_path: Path) -> dict[str, str]:
    thumbnail_path = storage.output_thumbnail_path(task_id, output_index)
    if thumbnail_needs_refresh(output_path, thumbnail_path):
        create_image_thumbnail(output_path, thumbnail_path)
    if not thumbnail_path.exists():
        return {}
    return {
        "thumbnail_file": storage.output_file(thumbnail_path),
        "thumbnail_url": _output_url(storage, thumbnail_path),
    }


def _output_file_from_url(url: str) -> str:
    parsed = urlsplit(str(url))
    path = unquote(parsed.path or "")
    if path.startswith("/outputs/"):
        return path.removeprefix("/outputs/")
    return Path(path).name


def _output_index_from_url(url: Any) -> int | None:
    match = re.search(r"-image-(\d+)(?=\.[a-z0-9]+(?:[?#].*)?$|$)", str(url or ""), re.IGNORECASE)
    return _positive_int(match.group(1) if match else None)


def _task_selected_output_indexes(metadata: dict[str, Any]) -> list[int]:
    raw_indexes = metadata.get("selected_output_indexes")
    if not isinstance(raw_indexes, list):
        return []
    indexes: list[int] = []
    for value in raw_indexes:
        index = _positive_int(value)
        if index is not None and index not in indexes:
            indexes.append(index)
    return sorted(indexes)


def _task_deleted_output_indexes(metadata: dict[str, Any]) -> set[int]:
    raw_indexes = metadata.get("deleted_output_indexes")
    if not isinstance(raw_indexes, list):
        return set()
    return {index for value in raw_indexes if (index := _positive_int(value)) is not None}


def _output_record_is_deleted(record: dict[str, Any], deleted_indexes: set[int], fallback_index: int) -> bool:
    index = _positive_int(record.get("index")) or fallback_index
    return bool(record.get("deleted")) or record.get("status") == "deleted" or index in deleted_indexes


def _metadata_list_value(metadata: dict[str, Any], key: str, position: int | None) -> Any:
    values = metadata.get(key)
    if position is None or not isinstance(values, list) or position < 0 or position >= len(values):
        return None
    return values[position]


def _visible_completed_output_records(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    deleted_indexes = _task_deleted_output_indexes(metadata)
    output_urls = metadata.get("output_urls") if isinstance(metadata.get("output_urls"), list) else []
    output_files = metadata.get("output_files") if isinstance(metadata.get("output_files"), list) else []
    if not output_urls and metadata.get("output_url"):
        output_urls = [metadata.get("output_url")]
    if not output_files and metadata.get("output_file"):
        output_files = [metadata.get("output_file")]

    records_by_index: dict[int, dict[str, Any]] = {}
    structured_outputs = metadata.get("outputs") if isinstance(metadata.get("outputs"), list) else []
    for fallback_index, raw_record in enumerate(structured_outputs, start=1):
        if not isinstance(raw_record, dict):
            continue
        if _output_record_is_deleted(raw_record, deleted_indexes, fallback_index):
            continue
        status = str(raw_record.get("status") or "completed")
        if status != "completed":
            continue
        index = _positive_int(raw_record.get("index")) or fallback_index
        record = dict(raw_record)
        record["index"] = index
        if not record.get("url") and index <= len(output_urls):
            record["url"] = output_urls[index - 1]
        if not record.get("file") and index <= len(output_files):
            record["file"] = output_files[index - 1]
        url_position = output_urls.index(record["url"]) if record.get("url") in output_urls else None
        for record_key, list_key in (
            ("size", "output_sizes"),
            ("format", "output_formats"),
            ("quality", "qualities"),
            ("background", "backgrounds"),
            ("revised_prompt", "revised_prompts"),
            ("usage", "usages"),
            ("tool_usage", "tool_usages"),
        ):
            if record.get(record_key) is None:
                value = _metadata_list_value(metadata, list_key, url_position)
                if value is not None:
                    record[record_key] = value
        records_by_index[index] = record

    existing_urls = {str(record.get("url")) for record in records_by_index.values() if record.get("url")}
    for fallback_index, url in enumerate(output_urls, start=1):
        if not url:
            continue
        index = _output_index_from_url(url) or fallback_index
        if index in deleted_indexes or str(url) in existing_urls:
            continue
        record: dict[str, Any] = {"index": index, "status": "completed", "url": url}
        if fallback_index <= len(output_files):
            record["file"] = output_files[fallback_index - 1]
        for record_key, list_key in (
            ("size", "output_sizes"),
            ("format", "output_formats"),
            ("quality", "qualities"),
            ("background", "backgrounds"),
            ("revised_prompt", "revised_prompts"),
            ("usage", "usages"),
            ("tool_usage", "tool_usages"),
        ):
            value = _metadata_list_value(metadata, list_key, fallback_index - 1)
            if value is not None:
                record[record_key] = value
        records_by_index[index] = record

    if not records_by_index and output_files:
        for fallback_index, filename in enumerate(output_files, start=1):
            if not filename:
                continue
            index = _positive_int(fallback_index) or fallback_index
            if index in deleted_indexes:
                continue
            record = {"index": index, "status": "completed", "file": filename}
            if fallback_index <= len(output_urls):
                record["url"] = output_urls[fallback_index - 1]
            records_by_index[index] = record

    return [records_by_index[index] for index in sorted(records_by_index)]


def _output_record_filename(record: dict[str, Any]) -> str:
    filename = str(record.get("file") or "").strip()
    if not filename and record.get("url"):
        filename = _output_file_from_url(str(record["url"]))
    return filename


def _safe_output_path(storage: TaskStorage, task_id: str, filename: str) -> Path | None:
    if not filename:
        return None
    path = storage.output_path(filename)
    root = storage.output_root.resolve(strict=False)
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError:
        return None
    if not path.name.startswith(f"{task_id}-image-"):
        return None
    return path


def _delete_output_thumbnail_files(storage: TaskStorage, task_id: str, output_index: int, record: dict[str, Any]) -> None:
    candidates: set[Path] = {storage.output_thumbnail_path(task_id, output_index)}
    thumbnail_file = str(record.get("thumbnail_file") or "").strip()
    thumbnail_path = _safe_output_path(storage, task_id, thumbnail_file)
    if thumbnail_path is not None:
        candidates.add(thumbnail_path)
    for path in candidates:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        storage._prune_empty_output_dir(path.parent)


def _downloadable_output_paths(storage: TaskStorage, metadata: dict[str, Any], *, selected_only: bool = False) -> list[Path]:
    task_id = str(metadata.get("task_id") or "")
    selected_indexes = set(_task_selected_output_indexes(metadata)) if selected_only else set()
    raw_records = _visible_completed_output_records(metadata)
    raw_files = [
        _output_record_filename(record)
        for record in raw_records
        if not selected_only or (_positive_int(record.get("index")) in selected_indexes)
    ]

    paths: list[Path] = []
    seen: set[str] = set()
    for filename in raw_files:
        path = _safe_output_path(storage, task_id, filename)
        if path is None or not path.is_file():
            continue
        key = path.resolve(strict=False).as_posix()
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return paths


def _set_task_output_selected(storage: TaskStorage, task_id: str, metadata: dict[str, Any], output_index: Any, selected: bool) -> dict[str, Any]:
    index = _positive_int(output_index)
    if index is None:
        raise ValueError("Invalid output index")
    visible_indexes = {
        _positive_int(record.get("index"))
        for record in _visible_completed_output_records(metadata)
    }
    if index not in visible_indexes:
        raise ValueError("Output does not exist")

    selected_indexes = set(_task_selected_output_indexes(metadata))
    if selected:
        selected_indexes.add(index)
    else:
        selected_indexes.discard(index)
    metadata["selected_output_indexes"] = sorted(selected_indexes)
    metadata["updated_at"] = utc_now()
    storage.write_metadata(task_id, metadata)
    return metadata


def _delete_unselected_task_outputs(storage: TaskStorage, task_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
    selected_indexes = set(_task_selected_output_indexes(metadata))
    if not selected_indexes:
        raise ValueError("Select at least one output before deleting the rest")

    records = _visible_completed_output_records(metadata)
    kept_records = [record for record in records if _positive_int(record.get("index")) in selected_indexes]
    removed_records = [record for record in records if _positive_int(record.get("index")) not in selected_indexes]
    if not kept_records:
        raise ValueError("Selected outputs no longer exist")
    if not removed_records:
        raise ValueError("No unselected outputs to delete")

    for record in records:
        old_index = _positive_int(record.get("index"))
        if old_index is not None:
            _delete_output_thumbnail_files(storage, task_id, old_index, record)

    for record in removed_records:
        path = _safe_output_path(storage, task_id, _output_record_filename(record))
        if path is None:
            continue
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        storage._prune_empty_output_dir(path.parent)

    accepted_outputs: list[dict[str, Any]] = []
    for new_index, record in enumerate(kept_records, start=1):
        accepted_record = dict(record)
        accepted_record["index"] = new_index
        accepted_record["status"] = "completed"
        accepted_record.pop("deleted", None)
        accepted_record.pop("error", None)
        accepted_record.pop("thumbnail_file", None)
        accepted_record.pop("thumbnail_url", None)
        output_path = _safe_output_path(storage, task_id, _output_record_filename(record))
        if output_path is not None and output_path.is_file():
            accepted_record.update(_output_thumbnail_fields(storage, task_id, new_index, output_path))
        accepted_outputs.append(accepted_record)

    output_files = [str(record.get("file")) for record in accepted_outputs if record.get("file")]
    output_urls = [str(record.get("url")) for record in accepted_outputs if record.get("url")]
    original_total_count = (
        _positive_int(metadata.get("original_total_count"))
        or _positive_int(metadata.get("total_count"))
        or len(records)
    )
    now = utc_now()
    metadata.update(
        {
            "status": "completed",
            "updated_at": now,
            "generated_count": len(accepted_outputs),
            "failed_count": 0,
            "total_count": len(accepted_outputs),
            "outputs": accepted_outputs,
            "output_files": output_files,
            "output_urls": output_urls,
            "selected_output_indexes": [],
            "deleted_output_indexes": [],
            "original_total_count": original_total_count,
            "pruned_output_count": len(removed_records),
            "outputs_pruned_at": now,
        }
    )
    if output_files:
        metadata["output_file"] = output_files[0]
    else:
        metadata.pop("output_file", None)
    if output_urls:
        metadata["output_url"] = output_urls[0]
    else:
        metadata.pop("output_url", None)

    list_sources = {
        "output_sizes": "size",
        "output_formats": "format",
        "qualities": "quality",
        "backgrounds": "background",
        "revised_prompts": "revised_prompt",
        "usages": "usage",
        "tool_usages": "tool_usage",
    }
    scalar_sources = {
        "output_size": "output_sizes",
        "output_format": "output_formats",
        "quality": "qualities",
        "background": "backgrounds",
        "revised_prompt": "revised_prompts",
        "usage": "usages",
        "tool_usage": "tool_usages",
    }
    for list_key, record_key in list_sources.items():
        values = [record[record_key] for record in accepted_outputs if record.get(record_key) is not None]
        if values:
            metadata[list_key] = values
        else:
            metadata.pop(list_key, None)
    for scalar_key, list_key in scalar_sources.items():
        values = metadata.get(list_key)
        if isinstance(values, list) and values:
            metadata[scalar_key] = values[0]
        else:
            metadata.pop(scalar_key, None)

    for key in ("error", "last_error", "retrying_failed_slots", "retry_failed_slots", "retry_requested_at"):
        metadata.pop(key, None)
    storage.write_metadata(task_id, metadata)
    return metadata


def _write_running_metadata(
    storage: TaskStorage,
    task_id: str,
    *,
    created_at: str,
    mode: str,
    prompt: str,
    prompt_for_model: str,
    params: dict[str, Any],
    input_files: list[str],
    gallery_refs: list[dict[str, Any]],
    reference_assets: list[dict[str, Any]] | None = None,
) -> None:
    input_urls = _input_urls(task_id, input_files)
    storage.write_metadata(
        task_id,
        {
            "task_id": task_id,
            "created_at": created_at,
            "updated_at": utc_now(),
            "viewed_at": created_at,
            "mode": mode,
            "status": "running",
            "prompt": prompt,
            "prompt_for_model": prompt_for_model,
            "params": params,
            "input_files": input_files,
            "input_urls": input_urls,
            "gallery_refs": gallery_refs,
            "reference_assets": reference_assets or [],
            "input_sources": _input_sources(task_id, input_files, gallery_refs, reference_assets or []),
        },
    )


def _write_queued_metadata(
    storage: TaskStorage,
    task_id: str,
    *,
    created_at: str,
    mode: str,
    prompt: str,
    prompt_for_model: str,
    params: dict[str, Any],
    input_files: list[str],
    mask_file: str | None,
    gallery_refs: list[dict[str, Any]],
    reference_assets: list[dict[str, Any]] | None = None,
    prompt_constraints: list[str] | None = None,
    requested_backend: str | None = None,
    max_attempts: int = 2,
) -> dict[str, Any]:
    metadata = {
        "task_id": task_id,
        "created_at": created_at,
        "updated_at": created_at,
        "viewed_at": created_at,
        "queued_at": created_at,
        "mode": mode,
        "status": "queued",
        "prompt": prompt,
        "prompt_for_model": prompt_for_model,
        "params": params,
        "input_files": input_files,
        "mask_file": mask_file,
        "input_urls": _input_urls(task_id, input_files),
        "gallery_refs": gallery_refs,
        "reference_assets": reference_assets or [],
        "input_sources": _input_sources(task_id, input_files, gallery_refs, reference_assets or []),
        "attempts": 0,
        "max_attempts": max_attempts,
        "last_error": "",
    }
    if requested_backend:
        metadata["requested_backend"] = requested_backend
    _apply_api_provider_metadata(metadata, params)
    _apply_api_images_concurrency_metadata(metadata, params)
    if prompt_constraints:
        metadata["prompt_constraints"] = list(prompt_constraints)
    storage.write_metadata(task_id, metadata)
    return metadata


def _write_progress_metadata(
    storage: TaskStorage,
    task_id: str,
    *,
    created_at: str,
    mode: str,
    prompt: str,
    prompt_for_model: str,
    total_count: int,
    results: list[ImageResult],
    output_paths: list[Path],
    input_files: list[Path],
    gallery_refs: list[dict[str, Any]],
    reference_assets: list[dict[str, Any]] | None,
    request_payload: dict[str, Any],
    params: dict[str, Any],
    output_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    input_names = [path.name for path in input_files]
    results, output_paths, output_records = _ordered_output_progress(results, output_paths, output_records or [])
    failed_records = [record for record in output_records if record.get("status") == "failed"]
    metadata = storage.read_metadata(task_id)
    metadata.update(
        {
            "task_id": task_id,
            "created_at": created_at,
            "updated_at": utc_now(),
            "mode": mode,
            "status": "running",
            "prompt": prompt,
            "prompt_for_model": prompt_for_model,
            "params": params,
            "input_files": input_names,
            "input_urls": _input_urls(task_id, input_names),
            "gallery_refs": gallery_refs,
            "reference_assets": reference_assets or [],
            "input_sources": _input_sources(task_id, input_names, gallery_refs, reference_assets or []),
            "generated_count": len(results),
            "failed_count": len(failed_records),
            "total_count": total_count,
            "output_files": [storage.output_file(path) for path in output_paths],
            "output_urls": [_output_url(storage, path) for path in output_paths],
            "outputs": output_records,
            "output_sizes": [result.size for result in results],
            "output_formats": [result.output_format for result in results],
            "qualities": [result.quality for result in results],
            "backgrounds": [result.background for result in results],
            "revised_prompts": [result.revised_prompt for result in results],
            "usages": [result.usage for result in results],
            "tool_usages": [result.tool_usage for result in results],
        }
    )
    _apply_api_provider_metadata(metadata, params)
    if failed_records:
        metadata["last_error"] = _partial_failure_message(len(failed_records), total_count, failed_records[-1].get("error"))
    else:
        metadata.pop("retrying_failed_slots", None)
        metadata.pop("retry_failed_slots", None)
    _apply_api_images_concurrency_metadata(metadata, params)
    metadata.pop("request", None)

    if results and output_paths:
        first_result = results[0]
        first_output_path = output_paths[0]
        metadata.update(
            {
                "output_file": storage.output_file(first_output_path),
                "output_url": _output_url(storage, first_output_path),
                "output_size": first_result.size,
                "output_format": first_result.output_format,
                "quality": first_result.quality,
                "background": first_result.background,
                "revised_prompt": first_result.revised_prompt,
                "usage": first_result.usage,
                "tool_usage": first_result.tool_usage,
            }
        )
    else:
        for key in (
            "output_file",
            "output_url",
            "output_size",
            "output_format",
            "quality",
            "background",
            "revised_prompt",
            "usage",
            "tool_usage",
        ):
            metadata.pop(key, None)

    storage.write_metadata(task_id, metadata)
    return metadata


def _partial_failure_message(failed_count: int, total_count: int, last_error: Any = None) -> str:
    detail = str(last_error or "").strip()
    prefix = f"{failed_count} of {total_count} images failed"
    return f"{prefix}: {detail}" if detail else prefix


def _apply_api_provider_metadata(metadata: dict[str, Any], params: dict[str, Any]) -> None:
    provider_id = str(params.get("api_provider_id") or "").strip()
    provider_name = str(params.get("api_provider_name") or "").strip()
    if provider_id:
        metadata["api_provider_id"] = provider_id
    if provider_name:
        metadata["api_provider_name"] = provider_name


def _api_images_concurrency_metadata_value(params: dict[str, Any]) -> int | None:
    if params.get("api_images_concurrency") is None:
        return None
    return _normalize_api_images_concurrency_for_metadata(params["api_images_concurrency"])


def _apply_api_images_concurrency_metadata(metadata: dict[str, Any], params: dict[str, Any]) -> None:
    value = _api_images_concurrency_metadata_value(params)
    if value is None:
        metadata.pop("api_images_concurrency", None)
    else:
        metadata["api_images_concurrency"] = value


def _finalize_generated_task(
    storage: TaskStorage,
    task_id: str,
    created_at: str,
    mode: str,
    prompt: str,
    prompt_for_model: str,
    results: list[ImageResult],
    input_files: list[Path],
    gallery_refs: list[dict[str, Any]],
    reference_assets: list[dict[str, Any]] | None,
    request_payload: dict[str, Any],
    params: dict[str, Any],
    output_paths: list[Path],
    output_records: list[dict[str, Any]],
) -> dict[str, Any]:
    del request_payload
    if not results or not output_paths:
        raise RuntimeError("No images were generated")

    input_names = [path.name for path in input_files]
    results, output_paths, output_records = _ordered_output_progress(results, output_paths, output_records)
    failed_records = [record for record in output_records if record.get("status") == "failed"]
    first_result = results[0]
    first_output_path = output_paths[0]
    total_count = int(params.get("n") or len(output_records) or len(results) or 1)
    metadata = storage.read_metadata(task_id)
    metadata.update(
        {
            "task_id": task_id,
            "created_at": created_at,
            "updated_at": utc_now(),
            "mode": mode,
            "status": "partial_failed" if failed_records else "completed",
            "prompt": prompt,
            "prompt_for_model": prompt_for_model,
            "params": params,
            "input_files": input_names,
            "input_urls": _input_urls(task_id, input_names),
            "gallery_refs": gallery_refs,
            "reference_assets": reference_assets or [],
            "input_sources": _input_sources(task_id, input_names, gallery_refs, reference_assets or []),
            "generated_count": len(results),
            "failed_count": len(failed_records),
            "total_count": total_count,
            "output_file": storage.output_file(first_output_path),
            "output_files": [storage.output_file(path) for path in output_paths],
            "output_url": _output_url(storage, first_output_path),
            "output_urls": [_output_url(storage, path) for path in output_paths],
            "outputs": output_records,
            "output_size": first_result.size,
            "output_sizes": [result.size for result in results],
            "output_format": first_result.output_format,
            "output_formats": [result.output_format for result in results],
            "quality": first_result.quality,
            "qualities": [result.quality for result in results],
            "background": first_result.background,
            "backgrounds": [result.background for result in results],
            "revised_prompt": first_result.revised_prompt,
            "revised_prompts": [result.revised_prompt for result in results],
            "usage": first_result.usage,
            "usages": [result.usage for result in results],
            "tool_usage": first_result.tool_usage,
            "tool_usages": [result.tool_usage for result in results],
        }
    )
    _apply_api_provider_metadata(metadata, params)
    metadata.pop("request", None)
    metadata.pop("error", None)
    _apply_api_images_concurrency_metadata(metadata, params)
    if failed_records:
        metadata["last_error"] = _partial_failure_message(len(failed_records), total_count, failed_records[-1].get("error"))
    else:
        metadata.pop("last_error", None)
    metadata.pop("retrying_failed_slots", None)
    metadata.pop("retry_failed_slots", None)
    storage.write_metadata(task_id, metadata)
    return metadata


def _complete_task(
    storage: TaskStorage,
    task_id: str,
    created_at: str,
    mode: str,
    prompt: str,
    prompt_for_model: str,
    results: ImageResult | list[ImageResult],
    input_files: list[Path],
    gallery_refs: list[dict[str, Any]],
    reference_assets: list[dict[str, Any]] | None,
    request_payload: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any]:
    result_list = results if isinstance(results, list) else [results]
    output_paths: list[Path] = []
    output_sizes: list[str] = []
    output_formats: list[str] = []
    output_backgrounds: list[str] = []
    output_qualities: list[str] = []
    revised_prompts: list[str] = []
    usages: list[dict[str, Any]] = []
    tool_usages: list[dict[str, Any]] = []

    multiple_outputs = isinstance(results, list)
    for index, result in enumerate(result_list, start=1):
        output_path = storage.write_output(
            task_id,
            result.image_bytes,
            result.output_format or str(params.get("output_format") or "png"),
            index=index if multiple_outputs else None,
        )
        output_paths.append(output_path)
        output_sizes.append(result.size)
        output_formats.append(result.output_format)
        output_backgrounds.append(result.background)
        output_qualities.append(result.quality)
        revised_prompts.append(result.revised_prompt)
        usages.append(result.usage)
        tool_usages.append(result.tool_usage)

    first_result = result_list[0]
    first_output_path = output_paths[0]
    input_names = [path.name for path in input_files]
    total_count = int(params.get("n") or len(result_list) or 1)
    metadata = storage.read_metadata(task_id)
    metadata.update(
        {
            "task_id": task_id,
            "created_at": created_at,
            "updated_at": utc_now(),
            "mode": mode,
            "status": "completed",
            "prompt": prompt,
            "prompt_for_model": prompt_for_model,
            "params": params,
            "input_files": input_names,
            "input_urls": _input_urls(task_id, input_names),
            "gallery_refs": gallery_refs,
            "reference_assets": reference_assets or [],
            "input_sources": _input_sources(task_id, input_names, gallery_refs, reference_assets or []),
            "generated_count": len(result_list),
            "total_count": total_count,
            "output_file": storage.output_file(first_output_path),
            "output_files": [storage.output_file(path) for path in output_paths],
            "output_url": _output_url(storage, first_output_path),
            "output_urls": [_output_url(storage, path) for path in output_paths],
            "output_size": first_result.size,
            "output_sizes": output_sizes,
            "output_format": first_result.output_format,
            "output_formats": output_formats,
            "quality": first_result.quality,
            "qualities": output_qualities,
            "background": first_result.background,
            "backgrounds": output_backgrounds,
            "revised_prompt": first_result.revised_prompt,
            "revised_prompts": revised_prompts,
            "usage": first_result.usage,
            "usages": usages,
            "tool_usage": first_result.tool_usage,
            "tool_usages": tool_usages,
        }
    )
    _apply_api_provider_metadata(metadata, params)
    metadata.pop("request", None)
    metadata.pop("error", None)
    metadata.pop("last_error", None)
    storage.write_metadata(task_id, metadata)
    return metadata


def _fail_task(
    storage: TaskStorage,
    task_id: str,
    created_at: str,
    mode: str,
    prompt: str,
    prompt_for_model: str,
    input_files: list[Path],
    gallery_refs: list[dict[str, Any]],
    reference_assets: list[dict[str, Any]] | None,
    request_payload: dict[str, Any],
    params: dict[str, Any],
    exc: Exception,
) -> dict[str, Any]:
    input_names = [path.name for path in input_files]
    metadata = {
        "task_id": task_id,
        "created_at": created_at,
        "updated_at": utc_now(),
        "mode": mode,
        "status": "failed",
        "prompt": prompt,
        "prompt_for_model": prompt_for_model,
        "params": params,
        "input_files": input_names,
        "input_urls": _input_urls(task_id, input_names),
        "gallery_refs": gallery_refs,
        "reference_assets": reference_assets or [],
        "input_sources": _input_sources(task_id, input_names, gallery_refs, reference_assets or []),
        "error": str(exc),
    }
    storage.write_metadata(task_id, metadata)
    return metadata
