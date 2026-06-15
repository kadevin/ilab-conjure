from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_image.client import ImageResult

from .storage import TaskStorage
from .task_metadata import _output_file_from_url, _output_url, _positive_int


def _restore_completed_output_progress(
    storage: TaskStorage,
    metadata: dict[str, Any],
    params: dict[str, Any],
    total_count: int,
) -> tuple[list[ImageResult], list[Path], list[dict[str, Any]]]:
    raw_records = [
        dict(record)
        for record in metadata.get("outputs", [])
        if isinstance(record, dict)
    ]
    if not raw_records:
        output_files = metadata.get("output_files") if isinstance(metadata.get("output_files"), list) else []
        output_urls = metadata.get("output_urls") if isinstance(metadata.get("output_urls"), list) else []
        raw_records = [
            {
                "index": index,
                "status": "completed",
                "file": str(filename),
                "url": str(output_urls[index - 1]) if index <= len(output_urls) else "",
            }
            for index, filename in enumerate(output_files, start=1)
        ]

    restored: dict[int, tuple[ImageResult, Path, dict[str, Any]]] = {}
    for fallback_index, record in enumerate(raw_records, start=1):
        if record.get("status") not in {None, "", "completed"}:
            continue
        index = _positive_int(record.get("index")) or fallback_index
        if index < 1 or index > total_count or index in restored:
            continue
        filename = str(record.get("file") or "").strip()
        if not filename and record.get("url"):
            filename = _output_file_from_url(str(record["url"]))
        if not filename:
            continue
        path = storage.output_path(filename)
        if not path.exists():
            continue
        try:
            image_bytes = path.read_bytes()
        except OSError:
            continue

        output_format = str(record.get("format") or path.suffix.lstrip(".") or params.get("output_format") or "png")
        size = str(record.get("size") or params.get("size") or "")
        quality = str(record.get("quality") or params.get("quality") or "")
        background = str(record.get("background") or params.get("background") or "")
        usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
        tool_usage = record.get("tool_usage") if isinstance(record.get("tool_usage"), dict) else {}
        restored_record = dict(record)
        restored_record.update(
            {
                "index": index,
                "status": "completed",
                "file": storage.output_file(path),
                "url": _output_url(storage, path),
                "size": size,
                "format": output_format,
                "quality": quality,
                "background": background,
                "usage": usage,
            }
        )
        if tool_usage:
            restored_record["tool_usage"] = tool_usage
        restored[index] = (
            ImageResult(
                image_bytes=image_bytes,
                revised_prompt=str(record.get("revised_prompt") or ""),
                output_format=output_format,
                size=size,
                background=background,
                quality=quality,
                usage=usage,
                tool_usage=tool_usage,
            ),
            path,
            restored_record,
        )

    ordered = [restored[index] for index in sorted(restored)]
    return (
        [result for result, _, _ in ordered],
        [path for _, path, _ in ordered],
        [record for _, _, record in ordered],
    )
