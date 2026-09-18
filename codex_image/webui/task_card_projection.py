from __future__ import annotations

import re
from typing import Any
from .task_index import project_task_generation_snapshot

DIMENSION_SIZE_RE = re.compile(r"^\s*(\d{1,5})\s*[xX×]\s*(\d{1,5})\s*$")

def _sidebar_task_card(metadata: dict[str, Any]) -> dict[str, Any]:
    task_id = str(metadata.get("task_id") or "")
    params = metadata.get("params") if isinstance(metadata.get("params"), dict) else {}
    generation_snapshot = project_task_generation_snapshot(metadata.get("generation_snapshot"))
    size = _sidebar_display_size(metadata, params)
    requested_size = _sidebar_requested_size(params) or size
    thumbnail_url = _first_sidebar_thumbnail_url(metadata)
    card = {
        "task_id": task_id,
        "summary_only": True,
        "created_at": metadata.get("created_at") or "",
        "updated_at": metadata.get("updated_at") or "",
        "viewed_at": metadata.get("viewed_at") or "",
        "queued_at": metadata.get("queued_at") or "",
        "started_at": metadata.get("started_at") or "",
        "attempt_started_at": metadata.get("attempt_started_at") or "",
        "completed_at": metadata.get("completed_at") or "",
        "terminal_at": metadata.get("terminal_at") or metadata.get("completed_at") or "",
        "archived_at": metadata.get("archived_at") or "",
        "status": metadata.get("status") or "",
        "mode": metadata.get("mode") or "",
        "prompt": _truncate_text(metadata.get("prompt") or metadata.get("prompt_for_model") or "", 260),
        "output_size": size,
        "params": {
            "size": requested_size,
            "ratio": params.get("ratio") or "",
            "resolution": params.get("resolution") or "",
            "orientation": params.get("orientation") or "",
            "n": _nonnegative_int(metadata.get("total_count") or params.get("n") or 1, 1),
            "prompt_fidelity": params.get("prompt_fidelity") or "",
            "api_provider_id": params.get("api_provider_id") or "",
            "api_provider_name": params.get("api_provider_name") or "",
        },
        "generation_snapshot": generation_snapshot,
        "backend": metadata.get("backend") or metadata.get("requested_backend") or "",
        "requested_backend": metadata.get("requested_backend") or metadata.get("backend") or "",
        "api_provider_id": metadata.get("api_provider_id") or params.get("api_provider_id") or "",
        "api_provider_name": metadata.get("api_provider_name") or params.get("api_provider_name") or "",
        "generated_count": _nonnegative_int(metadata.get("generated_count"), 0),
        "failed_count": _nonnegative_int(metadata.get("failed_count"), 0),
        "total_count": _nonnegative_int(metadata.get("total_count") or params.get("n"), 1),
        "attempts": _nonnegative_int(metadata.get("attempts"), 0),
        "max_attempts": _nonnegative_int(metadata.get("max_attempts"), 0),
        "last_error": metadata.get("last_error") or metadata.get("error") or "",
        "error": metadata.get("error") or "",
        "cancel_requested": bool(metadata.get("cancel_requested")),
        "cancelled_at": metadata.get("cancelled_at") or "",
        "retrying_failed_slots": metadata.get("retrying_failed_slots") if isinstance(metadata.get("retrying_failed_slots"), list) else [],
        "input_thumbnail_urls": _sidebar_input_thumbnail_urls(metadata),
        "thumbnail_urls": [thumbnail_url] if thumbnail_url else [],
    }
    return {key: value for key, value in card.items() if value not in ("", [], {}) or key in {"task_id", "summary_only", "params"}}


def _sidebar_display_size(metadata: dict[str, Any], params: dict[str, Any]) -> str:
    for value in (
        metadata.get("output_size"),
        _first_dimension_list_value(metadata.get("output_sizes")),
        _first_output_dimension_value(metadata),
        params.get("size"),
    ):
        size = _normalize_dimension_size(value)
        if size:
            return size
    requested_size = str(params.get("size") or "")
    return requested_size if requested_size and not requested_size.isdigit() else ""


def _sidebar_requested_size(params: dict[str, Any]) -> str:
    return _normalize_dimension_size(params.get("size"))


def _normalize_dimension_size(value: Any) -> str:
    match = DIMENSION_SIZE_RE.match(str(value or ""))
    if not match:
        return ""
    width = int(match.group(1))
    height = int(match.group(2))
    if width <= 0 or height <= 0:
        return ""
    return f"{width}x{height}"


def _first_dimension_list_value(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    for item in value:
        size = _normalize_dimension_size(item)
        if size:
            return size
    return ""


def _first_output_dimension_value(metadata: dict[str, Any]) -> str:
    outputs = metadata.get("outputs")
    if not isinstance(outputs, list):
        return ""
    for output in outputs:
        if not isinstance(output, dict):
            continue
        size = _normalize_dimension_size(output.get("size"))
        if size:
            return size
    return ""


def _sidebar_input_thumbnail_urls(metadata: dict[str, Any]) -> list[str]:
    urls = metadata.get("input_thumbnail_urls")
    if isinstance(urls, list):
        clean_urls = [str(url) for url in urls if url]
        if clean_urls:
            return clean_urls
    input_sources = metadata.get("input_sources")
    if isinstance(input_sources, list):
        source_urls: list[str] = []
        for source in input_sources:
            if not isinstance(source, dict) or source.get("missing"):
                continue
            url = source.get("thumbnail_url") or source.get("image_url")
            if url:
                source_urls.append(str(url))
        if source_urls:
            return source_urls
    task_id = str(metadata.get("task_id") or "")
    input_files = metadata.get("input_files")
    if not task_id or not isinstance(input_files, list):
        return []
    return [f"/api/tasks/{task_id}/inputs/{index}/thumbnail" for index, _ in enumerate(input_files, start=1)]


def _first_sidebar_thumbnail_url(metadata: dict[str, Any]) -> str:
    thumbnail_route = _first_output_thumbnail_route(metadata)
    if thumbnail_route:
        return thumbnail_route
    thumbnail_urls = metadata.get("thumbnail_urls")
    if isinstance(thumbnail_urls, list):
        for url in thumbnail_urls:
            if url:
                return str(url)
    outputs = metadata.get("outputs")
    if isinstance(outputs, list):
        for output in outputs:
            if not isinstance(output, dict):
                continue
            thumbnail_url = output.get("thumbnail_url") or _output_file_url(output.get("thumbnail_file"))
            if thumbnail_url:
                return thumbnail_url
    task_id = str(metadata.get("task_id") or "")
    output_files = metadata.get("output_files")
    if task_id and isinstance(output_files, list) and output_files:
        return f"/api/tasks/{task_id}/outputs/1/thumbnail"
    output_file = metadata.get("output_file")
    if task_id and output_file:
        return f"/api/tasks/{task_id}/outputs/1/thumbnail"
    return ""


def _first_output_thumbnail_route(metadata: dict[str, Any]) -> str:
    task_id = str(metadata.get("task_id") or "")
    if not task_id:
        return ""
    output_files = metadata.get("output_files") if isinstance(metadata.get("output_files"), list) else []
    output_urls = metadata.get("output_urls") if isinstance(metadata.get("output_urls"), list) else []
    outputs = metadata.get("outputs")
    if isinstance(outputs, list):
        for fallback_index, output in enumerate(outputs, start=1):
            if not isinstance(output, dict):
                continue
            status = str(output.get("status") or "completed")
            if status != "completed":
                continue
            index = _positive_int(output.get("index")) or fallback_index
            if (
                output.get("file")
                or (index <= len(output_files) and output_files[index - 1])
                or _is_local_output_url(output.get("url"))
                or (index <= len(output_urls) and _is_local_output_url(output_urls[index - 1]))
            ):
                return f"/api/tasks/{task_id}/outputs/{index}/sidebar-thumbnail"
    if output_files:
        return f"/api/tasks/{task_id}/outputs/1/sidebar-thumbnail"
    if output_urls and _is_local_output_url(output_urls[0]):
        return f"/api/tasks/{task_id}/outputs/1/sidebar-thumbnail"
    output_file = metadata.get("output_file")
    if output_file:
        return f"/api/tasks/{task_id}/outputs/1/sidebar-thumbnail"
    if _is_local_output_url(metadata.get("output_url")):
        return f"/api/tasks/{task_id}/outputs/1/sidebar-thumbnail"
    return ""


def _is_local_output_url(value: Any) -> bool:
    return str(value or "").startswith("/outputs/")


def _output_file_url(filename: Any) -> str:
    parts = [part for part in str(filename or "").split("/") if part]
    return "/outputs/" + "/".join(parts) if parts else ""


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _truncate_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _nonnegative_int(value: Any, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return number if number >= 0 else fallback
