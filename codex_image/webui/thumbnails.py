from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError


THUMBNAIL_MAX_EDGE = 768
THUMBNAIL_QUALITY = 88
THUMBNAIL_EXTENSION = "jpg"
SIDEBAR_THUMBNAIL_MAX_EDGE = 256
SIDEBAR_THUMBNAIL_QUALITY = 82
SIDEBAR_THUMBNAIL_EXTENSION = "webp"


def image_has_transparency(image: Image.Image) -> bool:
    if "A" not in image.getbands() and "transparency" not in image.info:
        return False
    return image.convert("RGBA").getchannel("A").getextrema()[0] < 255


def inspect_image_transparency(source_path: Path) -> bool | None:
    """Check pixels, not upstream claims or the mere presence of an alpha channel."""
    try:
        with Image.open(source_path) as image:
            return image_has_transparency(image)
    except (OSError, UnidentifiedImageError, ValueError, Image.DecompressionBombError):
        return None


def create_image_thumbnail(
    source_path: Path,
    thumbnail_path: Path,
    *,
    max_edge: int = THUMBNAIL_MAX_EDGE,
    quality: int = THUMBNAIL_QUALITY,
) -> Path | None:
    try:
        with Image.open(source_path) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
            thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
            if thumbnail_path.suffix.lower() == ".webp":
                image.convert("RGBA").save(thumbnail_path, "WEBP", quality=quality, method=4)
            else:
                thumbnail = _flatten_for_jpeg(image)
                thumbnail.save(thumbnail_path, "JPEG", quality=quality, optimize=True)
            return thumbnail_path
    except (OSError, UnidentifiedImageError, ValueError):
        return None


def create_sidebar_thumbnail(source_path: Path, thumbnail_path: Path) -> Path | None:
    try:
        with Image.open(source_path) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail(
                (SIDEBAR_THUMBNAIL_MAX_EDGE, SIDEBAR_THUMBNAIL_MAX_EDGE),
                Image.Resampling.LANCZOS,
            )
            thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
            if "A" in image.getbands() or "transparency" in image.info:
                thumbnail = image.convert("RGBA")
            else:
                thumbnail = image.convert("RGB")
            thumbnail.save(
                thumbnail_path,
                "WEBP",
                quality=SIDEBAR_THUMBNAIL_QUALITY,
                method=4,
            )
            return thumbnail_path
    except (OSError, UnidentifiedImageError, ValueError):
        return None


def thumbnail_needs_refresh(
    source_path: Path,
    thumbnail_path: Path,
    *,
    max_edge: int = THUMBNAIL_MAX_EDGE,
) -> bool:
    if not thumbnail_path.exists():
        return True
    try:
        if thumbnail_path.stat().st_mtime < source_path.stat().st_mtime:
            return True
        with Image.open(source_path) as source, Image.open(thumbnail_path) as thumbnail:
            source = ImageOps.exif_transpose(source)
            expected_edge = min(max(source.size), max_edge)
            return max(thumbnail.size) != expected_edge
    except (OSError, UnidentifiedImageError, ValueError):
        return True


def _flatten_for_jpeg(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    if "A" not in image.getbands() and "transparency" not in image.info:
        return image.convert("RGB")
    rgba = image.convert("RGBA")
    background = Image.new("RGB", rgba.size, (255, 255, 255))
    background.paste(rgba, mask=rgba.getchannel("A"))
    return background


def output_thumbnail_filename(task_id: str, output_index: int) -> str:
    return f"{task_id}-image-{output_index}-thumb.{THUMBNAIL_EXTENSION}"


def output_sidebar_thumbnail_filename(task_id: str, output_index: int) -> str:
    return f"{task_id}-image-{output_index}-sidebar.{SIDEBAR_THUMBNAIL_EXTENSION}"


def input_thumbnail_filename(task_id: str, input_index: int) -> str:
    return f"{task_id}-input-{input_index:02d}-thumb.{THUMBNAIL_EXTENSION}"


def clean_thumbnail_record(record: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(record)
    for key in ("thumbnail_file", "thumbnail_url", "sidebar_thumbnail_file", "sidebar_thumbnail_url"):
        value = cleaned.get(key)
        if value is not None:
            cleaned[key] = str(value)
    return cleaned
