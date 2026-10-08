from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

from codex_image.raster_validation import (
    MAX_RASTER_BYTES,
    MAX_RASTER_FRAMES,
    MAX_RASTER_HEIGHT,
    MAX_RASTER_PIXELS,
    MAX_RASTER_TOTAL_FRAME_PIXELS,
    MAX_RASTER_WIDTH,
    RasterValidationError,
    SUPPORTED_RASTER_MIME_TYPES,
    inspect_raster_image,
)


_MIME_SUFFIXES = {
    "image/gif": (".gif", frozenset({".gif"})),
    "image/jpeg": (".jpg", frozenset({".jpg", ".jpeg"})),
    "image/png": (".png", frozenset({".png"})),
    "image/webp": (".webp", frozenset({".webp"})),
}


class InvalidRasterImage(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedRasterImage:
    filename: str
    data: bytes
    mime_type: str
    sha256: str
    width: int
    height: int
    frames: int


def _canonical_filename(filename: str | None, mime_type: str) -> str:
    original = Path(str(filename or "image")).name or "image"
    canonical_suffix, matching_suffixes = _MIME_SUFFIXES[mime_type]
    if Path(original).suffix.lower() in matching_suffixes:
        return original
    stem = Path(original).stem.strip(".") or "image"
    return f"{stem}{canonical_suffix}"


def validate_raster_image(
    data: bytes,
    *,
    filename: str | None,
    max_bytes: int = MAX_RASTER_BYTES,
    max_width: int = MAX_RASTER_WIDTH,
    max_height: int = MAX_RASTER_HEIGHT,
    max_pixels: int = MAX_RASTER_PIXELS,
    max_frames: int = MAX_RASTER_FRAMES,
    max_total_frame_pixels: int = MAX_RASTER_TOTAL_FRAME_PIXELS,
) -> ValidatedRasterImage:
    try:
        inspection = inspect_raster_image(
            data,
            max_bytes=max_bytes,
            max_width=max_width,
            max_height=max_height,
            max_pixels=max_pixels,
            max_frames=max_frames,
            max_total_frame_pixels=max_total_frame_pixels,
        )
    except RasterValidationError as exc:
        raise InvalidRasterImage(str(exc)) from exc
    return ValidatedRasterImage(
        filename=_canonical_filename(filename, inspection.mime_type),
        data=data,
        mime_type=inspection.mime_type,
        sha256=hashlib.sha256(data).hexdigest(),
        width=inspection.width,
        height=inspection.height,
        frames=inspection.frames,
    )


async def read_validated_raster_upload(
    upload: Any,
    *,
    max_bytes: int = MAX_RASTER_BYTES,
) -> ValidatedRasterImage:
    try:
        data = await upload.read(max_bytes + 1)
        return validate_raster_image(
            data,
            filename=getattr(upload, "filename", None),
            max_bytes=max_bytes,
        )
    finally:
        close = getattr(upload, "close", None)
        if callable(close):
            await close()


async def read_validated_raster_uploads(
    uploads: list[Any],
    *,
    max_bytes: int = MAX_RASTER_BYTES,
    deduplicate: bool = True,
) -> list[ValidatedRasterImage]:
    validated: list[ValidatedRasterImage] = []
    seen: dict[str, ValidatedRasterImage] = {}
    try:
        for upload in uploads:
            try:
                image = await read_validated_raster_upload(
                    upload,
                    max_bytes=max_bytes,
                )
            except InvalidRasterImage as exc:
                if str(exc) == "Image is required":
                    continue
                raise
            if deduplicate and image.sha256 in seen:
                continue
            # Preserve multipart positions without letting a later duplicate replace its filename.
            validated.append(seen.setdefault(image.sha256, image))
        return validated
    finally:
        for upload in uploads:
            close = getattr(upload, "close", None)
            if callable(close):
                try:
                    await close()
                except Exception:
                    pass


__all__ = (
    "InvalidRasterImage",
    "SUPPORTED_RASTER_MIME_TYPES",
    "ValidatedRasterImage",
    "read_validated_raster_upload",
    "read_validated_raster_uploads",
    "validate_raster_image",
)
