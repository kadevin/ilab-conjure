from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from codex_image.client import DEFAULT_MAIN_MODEL

from .reference_files import ReferenceFileStorage, reference_file_task_record
from .storage import GalleryStorage, ReferenceAssetStorage


def _input_urls(task_id: str, input_files: list[str]) -> list[str]:
    return [f"/inputs/{quote(filename, safe='')}" for filename in input_files]


def _input_thumbnail_route_url(task_id: str, input_index: int) -> str:
    return f"/api/tasks/{quote(task_id, safe='')}/inputs/{input_index}/thumbnail"


def _input_thumbnail_urls(task_id: str, input_files: list[str]) -> list[str]:
    if not task_id:
        return []
    return [_input_thumbnail_route_url(task_id, index) for index, _ in enumerate(input_files, start=1)]


def _output_static_url(filename: str) -> str:
    return f"/outputs/{quote(filename, safe='/')}"


def _thumbnail_route_url(task_id: str, output_index: int) -> str:
    return f"/api/tasks/{quote(task_id, safe='')}/outputs/{output_index}/thumbnail"


def _output_image_route_url(task_id: str, output_index: int) -> str:
    return f"/api/tasks/{quote(task_id, safe='')}/outputs/{output_index}/image"


def _gallery_item_response(item: dict[str, Any]) -> dict[str, Any]:
    item_id = str(item.get("id") or "")
    enriched = dict(item)
    enriched["image_url"] = f"/api/gallery/{quote(item_id, safe='')}/image" if item_id else ""
    return enriched


def _gallery_category_response(category: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": category.get("id"),
        "name": category.get("name"),
        "prompt_role": category.get("prompt_role"),
        "order": category.get("order"),
        "locked": bool(category.get("locked", False)),
    }


def _gallery_ref_response(item: dict[str, Any]) -> dict[str, Any]:
    response = _gallery_item_response(item)
    return {
        "id": response.get("id"),
        "name": response.get("name"),
        "category": response.get("category"),
        "category_name": response.get("category_name"),
        "category_prompt_role": response.get("category_prompt_role"),
        "prompt_note": response.get("prompt_note", ""),
        "sha256": response.get("sha256"),
        "size_bytes": response.get("size_bytes"),
        "image_url": response.get("image_url"),
        "missing": False,
    }


def _reference_asset_response(item: dict[str, Any]) -> dict[str, Any]:
    asset_id = str(item.get("id") or "")
    enriched = dict(item)
    enriched["image_url"] = f"/api/reference-assets/{quote(asset_id, safe='')}/image" if asset_id else ""
    enriched["thumbnail_url"] = f"/api/reference-assets/{quote(asset_id, safe='')}/thumbnail" if asset_id else ""
    return enriched


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _enrich_gallery_refs(gallery_refs: Any, gallery_storage: GalleryStorage | None) -> list[dict[str, Any]]:
    if not isinstance(gallery_refs, list):
        return []
    enriched_refs: list[dict[str, Any]] = []
    for ref in gallery_refs:
        if not isinstance(ref, dict):
            continue
        item_id = str(ref.get("id") or "")
        enriched = dict(ref)
        if not item_id or gallery_storage is None:
            enriched["missing"] = True
            enriched["image_url"] = ""
            enriched_refs.append(enriched)
            continue
        try:
            item = gallery_storage.read_item(item_id)
            gallery_storage.image_path(item_id)
        except (FileNotFoundError, ValueError):
            enriched["missing"] = True
            enriched["image_url"] = ""
        else:
            enriched.update(_gallery_ref_response(item))
        enriched_refs.append(enriched)
    return enriched_refs


def _enrich_reference_assets(reference_assets: Any, storage: ReferenceAssetStorage | None) -> list[dict[str, Any]]:
    if not isinstance(reference_assets, list):
        return []
    enriched: list[dict[str, Any]] = []
    for item in reference_assets:
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("id") or "")
        fallback = dict(item)
        try:
            stored = storage.read_item(asset_id) if storage is not None else fallback
            if storage is not None:
                storage.image_path(asset_id)
        except (FileNotFoundError, ValueError):
            fallback["missing"] = True
            fallback["image_url"] = ""
            enriched.append(fallback)
            continue
        enriched.append(_reference_asset_response(stored))
    return enriched


def _enrich_reference_files(
    task_id: str,
    reference_files: Any,
    storage: ReferenceFileStorage | None,
) -> list[dict[str, Any]]:
    if not isinstance(reference_files, list):
        return []
    enriched: list[dict[str, Any]] = []
    encoded_task_id = quote(task_id, safe="")
    for index, item in enumerate(reference_files, start=1):
        if not isinstance(item, dict):
            continue
        record = dict(item)
        missing = storage is None
        if storage is not None:
            try:
                task_record = reference_file_task_record(record)
                storage.verified_file_path(
                    str(task_record["id"]),
                    expected_size=int(task_record["size_bytes"]),
                )
            except (FileNotFoundError, OSError, ValueError):
                missing = True
        record["missing"] = missing
        record["download_url"] = f"/api/tasks/{encoded_task_id}/reference-files/{index}/download"
        enriched.append(record)
    return enriched


def _input_sources(
    task_id: str,
    input_files: list[str],
    gallery_refs: list[dict[str, Any]],
    reference_assets: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    sources = [
        {
            "kind": "upload",
            "filename": filename,
            "image_url": url,
            "thumbnail_url": _input_thumbnail_route_url(task_id, index),
        }
        for index, (filename, url) in enumerate(
            zip(input_files, _input_urls(task_id, input_files), strict=False),
            start=1,
        )
    ]
    sources.extend(
        {
            "kind": "asset",
            "id": item.get("id"),
            "filename": item.get("filename"),
            "mime_type": item.get("mime_type"),
            "image_url": item.get("image_url", ""),
            "missing": bool(item.get("missing")),
        }
        for item in (reference_assets or [])
    )
    sources.extend(
        {
            "kind": "gallery",
            "id": ref.get("id"),
            "name": ref.get("name"),
            "category": ref.get("category"),
            "category_name": ref.get("category_name"),
            "category_prompt_role": ref.get("category_prompt_role"),
            "prompt_note": ref.get("prompt_note", ""),
            "image_url": ref.get("image_url", ""),
            "missing": bool(ref.get("missing")),
        }
        for ref in gallery_refs
    )
    return sources


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _output_index_from_url(url: Any) -> int | None:
    match = re.search(r"-image-(\d+)(?=\.[a-z0-9]+(?:[?#].*)?$|$)", str(url or ""), re.IGNORECASE)
    return _positive_int(match.group(1) if match else None)


def _output_file_from_url(url: Any) -> str:
    parsed = urlsplit(str(url or ""))
    path = unquote(parsed.path or "")
    if path.startswith("/outputs/"):
        return path.removeprefix("/outputs/")
    return path.lstrip("/")


def _task_deleted_output_indexes(metadata: dict[str, Any]) -> set[int]:
    indexes: set[int] = set()
    raw_indexes = metadata.get("deleted_output_indexes")
    if isinstance(raw_indexes, list):
        indexes.update(index for value in raw_indexes if (index := _positive_int(value)) is not None)
    raw_outputs = metadata.get("outputs")
    if isinstance(raw_outputs, list):
        for fallback_index, record in enumerate(raw_outputs, start=1):
            if not isinstance(record, dict):
                continue
            if not (record.get("deleted") or record.get("status") == "deleted"):
                continue
            indexes.add(_positive_int(record.get("index")) or fallback_index)
    return indexes


def _output_record_thumbnail_url(task_id: str, record: dict[str, Any], fallback_index: int) -> str:
    existing_url = str(record.get("thumbnail_url") or "").strip()
    if existing_url:
        return existing_url
    thumbnail_file = str(record.get("thumbnail_file") or "").strip()
    if thumbnail_file:
        return _output_static_url(thumbnail_file)
    index = _positive_int(record.get("index")) or fallback_index
    return _thumbnail_route_url(task_id, index) if task_id and index else ""


def _with_output_thumbnail_urls(enriched: dict[str, Any], metadata: dict[str, Any], task_id: str) -> None:
    if not task_id:
        return
    deleted_indexes = _task_deleted_output_indexes(metadata)
    thumbnail_urls_by_index: dict[int, str] = {}
    raw_outputs = enriched.get("outputs")
    if isinstance(raw_outputs, list):
        enriched_outputs: list[Any] = []
        for fallback_index, raw_record in enumerate(raw_outputs, start=1):
            if not isinstance(raw_record, dict):
                enriched_outputs.append(raw_record)
                continue
            record = dict(raw_record)
            index = _positive_int(record.get("index")) or fallback_index
            if record.get("status") == "completed" and index not in deleted_indexes and (record.get("url") or record.get("file")):
                if not record.get("url") and record.get("file"):
                    record["url"] = _output_image_route_url(task_id, index)
                thumbnail_url = _output_record_thumbnail_url(task_id, record, fallback_index)
                if thumbnail_url:
                    record["thumbnail_url"] = thumbnail_url
                    thumbnail_urls_by_index[index] = thumbnail_url
            enriched_outputs.append(record)
        enriched["outputs"] = enriched_outputs

    output_urls = metadata.get("output_urls") if isinstance(metadata.get("output_urls"), list) else []
    if not output_urls and metadata.get("output_url"):
        output_urls = [metadata.get("output_url")]
    for fallback_index, url in enumerate(output_urls, start=1):
        if not url:
            continue
        index = _output_index_from_url(url) or fallback_index
        if index in deleted_indexes:
            continue
        thumbnail_urls_by_index.setdefault(index, _thumbnail_route_url(task_id, index))

    output_files = metadata.get("output_files") if isinstance(metadata.get("output_files"), list) else []
    if not output_files and metadata.get("output_file"):
        output_files = [metadata.get("output_file")]
    for fallback_index, filename in enumerate(output_files, start=1):
        if not filename:
            continue
        index = _output_index_from_url(filename) or fallback_index
        if index in deleted_indexes:
            continue
        thumbnail_urls_by_index.setdefault(index, _thumbnail_route_url(task_id, index))

    if thumbnail_urls_by_index:
        enriched["thumbnail_urls"] = [thumbnail_urls_by_index[index] for index in sorted(thumbnail_urls_by_index)]


def _mark_orphaned_running_outputs_failed(enriched: dict[str, Any], message: str) -> None:
    total = _positive_int(enriched.get("total_count")) or _positive_int((enriched.get("params") or {}).get("n")) or 1
    completed_count = 0
    failed_count = 0
    raw_outputs = enriched.get("outputs")
    if isinstance(raw_outputs, list):
        normalized_outputs: list[Any] = []
        for fallback_index, raw_record in enumerate(raw_outputs, start=1):
            if not isinstance(raw_record, dict):
                normalized_outputs.append(raw_record)
                continue
            record = dict(raw_record)
            status = str(record.get("status") or "")
            if status in {"running", "queued", "waiting", ""}:
                record["status"] = "failed"
                record.setdefault("error", message)
            if record.get("status") == "completed":
                completed_count += 1
            elif record.get("status") == "failed":
                failed_count += 1
            normalized_outputs.append(record)
        enriched["outputs"] = normalized_outputs

    missing_count = max(0, total - completed_count - failed_count)
    if missing_count:
        failed_count += missing_count
    enriched["generated_count"] = completed_count
    enriched["failed_count"] = failed_count


def _has_stale_running_output_record(metadata: dict[str, Any]) -> bool:
    raw_outputs = metadata.get("outputs")
    if not isinstance(raw_outputs, list):
        return False
    return any(
        isinstance(record, dict) and str(record.get("status") or "") in {"running", "queued", "waiting", ""}
        for record in raw_outputs
    )


def _with_file_urls(
    metadata: dict[str, Any],
    active_task_ids: set[str] | None = None,
    gallery_storage: GalleryStorage | None = None,
    reference_asset_storage: ReferenceAssetStorage | None = None,
    reference_file_storage: ReferenceFileStorage | None = None,
    *,
    include_request: bool = True,
) -> dict[str, Any]:
    task_id = str(metadata.get("task_id") or "")
    enriched = dict(metadata)
    params = enriched.get("params")
    request_payload = enriched.get("request")
    if isinstance(params, dict) and not params.get("main_model") and isinstance(request_payload, dict) and request_payload.get("model"):
        enriched["params"] = {**params, "main_model": str(request_payload["model"])}
    if not include_request:
        enriched.pop("request", None)
    if enriched.get("status") == "running" and active_task_ids is not None and task_id not in active_task_ids:
        message = "任务已中断：服务重启或请求中断后没有收到 Codex 返回结果。"
        enriched["status"] = "failed"
        enriched["orphaned_running"] = True
        enriched["error"] = message
        _mark_orphaned_running_outputs_failed(enriched, message)
    elif enriched.get("status") in {"failed", "partial_failed"} and _has_stale_running_output_record(enriched):
        message = str(enriched.get("error") or enriched.get("last_error") or "Task failed before all image slots completed.")
        _mark_orphaned_running_outputs_failed(enriched, message)

    input_files = metadata.get("input_files")
    input_names: list[str] = []
    if task_id and isinstance(input_files, list):
        input_names = [str(filename) for filename in input_files]
        enriched["input_urls"] = _input_urls(task_id, input_names)
        enriched["input_thumbnail_urls"] = _input_thumbnail_urls(task_id, input_names)

    raw_gallery_refs = metadata.get("gallery_refs")
    if (not isinstance(raw_gallery_refs, list) or not raw_gallery_refs) and gallery_storage is not None:
        raw_gallery_refs = _infer_gallery_refs_from_prompt(metadata, gallery_storage)
    gallery_refs = _enrich_gallery_refs(raw_gallery_refs, gallery_storage)

    reference_assets = _enrich_reference_assets(metadata.get("reference_assets"), reference_asset_storage)
    reference_files = _enrich_reference_files(task_id, metadata.get("reference_files"), reference_file_storage)
    if reference_assets:
        enriched["reference_assets"] = reference_assets
    if reference_files:
        enriched["reference_files"] = reference_files
        enriched["reference_file_count"] = len(reference_files)
    else:
        enriched.pop("reference_files", None)
        enriched.pop("reference_file_count", None)
    if gallery_refs:
        enriched["gallery_refs"] = gallery_refs
    if reference_assets or gallery_refs:
        enriched["input_sources"] = _input_sources(task_id, input_names, gallery_refs, reference_assets)
    _with_output_thumbnail_urls(enriched, metadata, task_id)
    return enriched


def _infer_gallery_refs_from_prompt(metadata: dict[str, Any], gallery_storage: GalleryStorage) -> list[dict[str, Any]]:
    prompt = f"{metadata.get('prompt') or ''}\n{metadata.get('prompt_for_model') or ''}"
    names = _dedupe_preserve_order(re.findall(r"@([^\s@，。,.#：:]+)", prompt))
    if not names:
        return []
    items_by_name = {str(item.get("name") or ""): item for item in gallery_storage.list_items()}
    refs: list[dict[str, Any]] = []
    for name in names:
        item = items_by_name.get(name)
        if item is not None:
            refs.append(_gallery_ref_response(item))
    return refs


def _params(
    main_model: str,
    model: str,
    size: str,
    quality: str,
    background: str | None,
    output_format: str,
    moderation: str | None,
    output_compression: int | None,
    n: int = 1,
) -> dict[str, Any]:
    return {
        "main_model": main_model or DEFAULT_MAIN_MODEL,
        "model": model,
        "size": size,
        "quality": quality,
        "background": background,
        "output_format": output_format,
        "moderation": moderation,
        "output_compression": output_compression,
        "n": n,
    }
