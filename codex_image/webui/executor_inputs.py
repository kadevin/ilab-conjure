from __future__ import annotations

import asyncio
import base64
import mimetypes
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

from .storage import GalleryStorage, ReferenceAssetStorage, TaskStorage
from .task_metadata import _dedupe_preserve_order, _gallery_ref_response, _reference_asset_response

_SUPPORTED_REQUEST_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
_PIL_FORMAT_MIME_TYPES = {
    "GIF": "image/gif",
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


def _file_to_data_url(path: Path, *, mime_type: str | None = None) -> str:
    data = path.read_bytes()
    resolved_mime_type = _image_mime_type(mime_type, path.name, data) or "application/octet-stream"
    request_data, request_mime_type = _request_image_payload(data, resolved_mime_type)
    return f"data:{request_mime_type};base64,{base64.b64encode(request_data).decode('ascii')}"


def _image_mime_type(declared_mime_type: str | None, filename: str, data: bytes) -> str | None:
    candidates = [
        str(declared_mime_type or "").strip(),
        str(mimetypes.guess_type(filename)[0] or "").strip(),
        _sniff_image_mime_type(data),
    ]
    for candidate in candidates:
        normalized = _normalize_mime_type(candidate)
        if normalized.startswith("image/"):
            return normalized
    return None


def _normalize_mime_type(value: str | None) -> str:
    return str(value or "").split(";", 1)[0].strip().lower()


def _request_image_payload(data: bytes, mime_type: str) -> tuple[bytes, str]:
    normalized_mime_type = _normalize_mime_type(mime_type)
    detected_mime_type, is_animated, image_was_decoded = _detect_pillow_request_mime_type(data)
    if detected_mime_type in _SUPPORTED_REQUEST_IMAGE_MIME_TYPES and not (detected_mime_type == "image/gif" and is_animated):
        return data, detected_mime_type
    if normalized_mime_type in _SUPPORTED_REQUEST_IMAGE_MIME_TYPES and not image_was_decoded:
        return data, normalized_mime_type
    if normalized_mime_type not in _SUPPORTED_REQUEST_IMAGE_MIME_TYPES or detected_mime_type is None or is_animated:
        return _convert_image_to_png(data), "image/png"
    return data, normalized_mime_type


def _detect_pillow_request_mime_type(data: bytes) -> tuple[str | None, bool, bool]:
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = str(image.format or "").upper()
            return _PIL_FORMAT_MIME_TYPES.get(image_format), bool(getattr(image, "is_animated", False)), True
    except (OSError, UnidentifiedImageError):
        return None, False, False


def _convert_image_to_png(data: bytes) -> bytes:
    try:
        with Image.open(BytesIO(data)) as image:
            image.seek(0)
            converted = ImageOps.exif_transpose(image)
            if converted.mode in {"P", "LA"} or "transparency" in converted.info:
                converted = converted.convert("RGBA")
            elif converted.mode not in {"1", "L", "RGB", "RGBA"}:
                converted = converted.convert("RGB")
            buffer = BytesIO()
            converted.save(buffer, format="PNG")
            return buffer.getvalue()
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Unsupported image type: could not decode image") from exc


def _sniff_image_mime_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _resolve_reference_assets(
    storage: ReferenceAssetStorage,
    asset_ids: list[str],
    *,
    touch: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    refs: list[dict[str, Any]] = []
    data_urls: list[str] = []
    for asset_id in _dedupe_preserve_order(asset_ids):
        try:
            item = storage.touch(asset_id) if touch else storage.read_item(asset_id)
            path = storage.image_path(asset_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid reference asset id: {asset_id}") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Reference asset not found: {asset_id}") from exc
        refs.append(_reference_asset_response(item))
        data_urls.append(_file_to_data_url(path, mime_type=str(item.get("mime_type") or "")))
    return refs, data_urls


def _resolve_gallery_refs(gallery_storage: GalleryStorage, item_ids: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    refs: list[dict[str, Any]] = []
    data_urls: list[str] = []
    for item_id in _dedupe_preserve_order(item_ids):
        try:
            item = gallery_storage.read_item(item_id)
            path = gallery_storage.image_path(item_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=f"Gallery item not found: {item_id}") from exc
        refs.append(_gallery_ref_response(item))
        data_urls.append(_file_to_data_url(path, mime_type=str(item.get("mime_type") or "")))
    return refs, data_urls


def _task_cancel_requested(storage: TaskStorage, task_id: str) -> bool:
    try:
        metadata = storage.read_metadata(task_id)
    except FileNotFoundError:
        return True
    return bool(metadata.get("cancel_requested"))


def _raise_if_task_cancelled(storage: TaskStorage, task_id: str) -> None:
    if _task_cancel_requested(storage, task_id):
        raise asyncio.CancelledError()
