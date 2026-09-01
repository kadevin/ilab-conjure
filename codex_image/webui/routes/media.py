from __future__ import annotations

from pathlib import Path, PurePosixPath
import re
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from codex_image.webui.context import WebUIContext
from codex_image.webui.image_uploads import SUPPORTED_RASTER_MIME_TYPES
from codex_image.webui.storage import _guess_mime_type
from codex_image.webui.task_metadata import (
    _output_record_filename,
    _safe_output_path,
    _visible_completed_output_records,
)


_TASK_ID_PATTERN = r"\d{14}-[0-9a-f]{8}"
_TASK_INPUT_FILENAME_RE = re.compile(
    rf"^(?P<task_id>{_TASK_ID_PATTERN})-(?:input|mask)-\d+-",
    re.IGNORECASE,
)
_TASK_OUTPUT_FILENAME_RE = re.compile(
    rf"^(?P<task_id>{_TASK_ID_PATTERN})-image-(?P<index>\d+)\.[a-z0-9]+$",
    re.IGNORECASE,
)
_TASK_OUTPUT_THUMBNAIL_RE = re.compile(
    rf"^(?P<task_id>{_TASK_ID_PATTERN})-image-(?P<index>\d+)-(?P<kind>thumb|sidebar)\.[a-z0-9]+$",
    re.IGNORECASE,
)
_TASK_INPUT_THUMBNAIL_RE = re.compile(
    rf"^(?P<task_id>{_TASK_ID_PATTERN})-input-(?P<index>\d+)-thumb\.[a-z0-9]+$",
    re.IGNORECASE,
)
_PRIVATE_MEDIA_CACHE = {"Cache-Control": "private, max-age=3600"}


def _read_task_metadata(ctx: WebUIContext, task_id: str) -> dict[str, Any]:
    try:
        return ctx.storage.read_metadata(task_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


def _contained_file(path: Path, root: Path) -> Path | None:
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (FileNotFoundError, ValueError):
        return None
    return path if path.is_file() else None


def _task_input_path(
    ctx: WebUIContext,
    task_id: str,
    input_index: int,
    *,
    metadata: dict[str, Any] | None = None,
) -> Path | None:
    if input_index < 1:
        return None
    task_metadata = metadata if metadata is not None else _read_task_metadata(ctx, task_id)
    input_files = task_metadata.get("input_files")
    if not isinstance(input_files, list) or input_index > len(input_files):
        return None
    filename = str(input_files[input_index - 1] or "")
    if not filename or Path(filename).name != filename:
        return None
    return _contained_file(ctx.storage.input_path(filename), ctx.storage.input_root)


def _task_output_path(
    ctx: WebUIContext,
    task_id: str,
    output_index: int,
    *,
    metadata: dict[str, Any] | None = None,
) -> Path | None:
    if output_index < 1:
        return None
    task_metadata = metadata if metadata is not None else _read_task_metadata(ctx, task_id)
    record = next(
        (
            item
            for item in _visible_completed_output_records(task_metadata)
            if item.get("index") == output_index
        ),
        None,
    )
    if record is None:
        return None
    path = _safe_output_path(
        ctx.storage,
        task_id,
        _output_record_filename(record),
    )
    return path if path is not None and path.is_file() else None


def _media_response(path: Path) -> FileResponse:
    mime_type = _guess_mime_type(path.name).split(";", 1)[0].strip().lower()
    if mime_type not in SUPPORTED_RASTER_MIME_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported media type")
    return FileResponse(
        path,
        media_type=mime_type,
        headers=_PRIVATE_MEDIA_CACHE,
    )


def _legacy_input_path(ctx: WebUIContext, filename: str) -> Path | None:
    if not filename or Path(filename).name != filename:
        return None
    match = _TASK_INPUT_FILENAME_RE.match(filename)
    if match is None:
        return None
    task_id = match.group("task_id")
    try:
        metadata = _read_task_metadata(ctx, task_id)
    except HTTPException:
        return None
    allowed_names = {
        str(item)
        for item in metadata.get("input_files", [])
        if isinstance(metadata.get("input_files"), list) and item
    }
    mask_file = str(metadata.get("mask_file") or "")
    if mask_file:
        allowed_names.add(mask_file)
    if filename not in allowed_names:
        return None
    return _contained_file(ctx.storage.input_path(filename), ctx.storage.input_root)


def _normalized_output_filename(filename: str) -> str | None:
    raw = str(filename or "").strip().replace("\\", "/")
    candidate = PurePosixPath(raw)
    if (
        not raw
        or candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        return None
    return candidate.as_posix()


def _legacy_output_path(ctx: WebUIContext, filename: str) -> Path | None:
    normalized = _normalized_output_filename(filename)
    if normalized is None:
        return None
    basename = PurePosixPath(normalized).name

    output_match = _TASK_OUTPUT_FILENAME_RE.match(basename)
    if output_match is not None:
        task_id = output_match.group("task_id")
        try:
            metadata = _read_task_metadata(ctx, task_id)
        except HTTPException:
            return None
        for record in _visible_completed_output_records(metadata):
            path = _safe_output_path(
                ctx.storage,
                task_id,
                _output_record_filename(record),
            )
            if (
                path is not None
                and path.is_file()
                and ctx.storage.output_file(path) == normalized
            ):
                return path
        return None

    output_thumbnail_match = _TASK_OUTPUT_THUMBNAIL_RE.match(basename)
    if output_thumbnail_match is not None:
        task_id = output_thumbnail_match.group("task_id")
        output_index = int(output_thumbnail_match.group("index"))
        try:
            metadata = _read_task_metadata(ctx, task_id)
        except HTTPException:
            return None
        if _task_output_path(
            ctx,
            task_id,
            output_index,
            metadata=metadata,
        ) is None:
            return None
        if output_thumbnail_match.group("kind").lower() == "sidebar":
            expected = ctx.storage.output_sidebar_thumbnail_path(task_id, output_index)
        else:
            expected = ctx.storage.output_thumbnail_path(task_id, output_index)
        if ctx.storage.output_file(expected) != normalized:
            return None
        return _contained_file(expected, ctx.storage.output_root)

    input_thumbnail_match = _TASK_INPUT_THUMBNAIL_RE.match(basename)
    if input_thumbnail_match is not None:
        task_id = input_thumbnail_match.group("task_id")
        input_index = int(input_thumbnail_match.group("index"))
        try:
            metadata = _read_task_metadata(ctx, task_id)
        except HTTPException:
            return None
        if _task_input_path(
            ctx,
            task_id,
            input_index,
            metadata=metadata,
        ) is None:
            return None
        expected = ctx.storage.input_thumbnail_path(task_id, input_index)
        if ctx.storage.output_file(expected) != normalized:
            return None
        return _contained_file(expected, ctx.storage.output_root)

    return None


def register_media_routes(app: FastAPI, ctx: WebUIContext) -> None:
    @app.get("/api/prompt-template-assets/{asset_id}/image")
    def get_prompt_template_asset_image(asset_id: str) -> FileResponse:
        asset = ctx.prompt_template_asset_storage.resolve(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Template asset not found")
        return _media_response(asset.path)

    @app.get("/api/tasks/{task_id}/inputs/{input_index}/image")
    def get_task_input_image(task_id: str, input_index: int) -> FileResponse:
        path = _task_input_path(ctx, task_id, input_index)
        if path is None:
            raise HTTPException(status_code=404, detail="Input not found")
        return _media_response(path)

    @app.get("/api/tasks/{task_id}/outputs/{output_index}/image")
    def get_task_output_image(task_id: str, output_index: int) -> FileResponse:
        path = _task_output_path(ctx, task_id, output_index)
        if path is None:
            raise HTTPException(status_code=404, detail="Output not found")
        return _media_response(path)

    @app.get("/inputs/{filename:path}")
    def get_legacy_task_input(filename: str) -> FileResponse:
        path = _legacy_input_path(ctx, filename)
        if path is None:
            raise HTTPException(status_code=404, detail="Input not found")
        return _media_response(path)

    @app.get("/outputs/{filename:path}")
    def get_legacy_task_output(filename: str) -> FileResponse:
        path = _legacy_output_path(ctx, filename)
        if path is None:
            raise HTTPException(status_code=404, detail="Output not found")
        return _media_response(path)
