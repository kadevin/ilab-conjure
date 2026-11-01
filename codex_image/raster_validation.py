from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import warnings

from PIL import Image, UnidentifiedImageError


MAX_RASTER_BYTES = 50 * 1024 * 1024
MAX_RASTER_WIDTH = 16_384
MAX_RASTER_HEIGHT = 16_384
MAX_RASTER_PIXELS = 64 * 1024 * 1024
MAX_RASTER_FRAMES = 100
MAX_RASTER_TOTAL_FRAME_PIXELS = 128 * 1024 * 1024

RASTER_FORMAT_MIME_TYPES = {
    "GIF": "image/gif",
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
SUPPORTED_RASTER_MIME_TYPES = frozenset(RASTER_FORMAT_MIME_TYPES.values())


class RasterValidationError(ValueError):
    pass


@dataclass(frozen=True)
class RasterInspection:
    image_format: str
    mime_type: str
    width: int
    height: int
    frames: int


def inspect_raster_image(
    data: bytes,
    *,
    max_bytes: int = MAX_RASTER_BYTES,
    max_width: int = MAX_RASTER_WIDTH,
    max_height: int = MAX_RASTER_HEIGHT,
    max_pixels: int = MAX_RASTER_PIXELS,
    max_frames: int = MAX_RASTER_FRAMES,
    max_total_frame_pixels: int = MAX_RASTER_TOTAL_FRAME_PIXELS,
) -> RasterInspection:
    if not data:
        raise RasterValidationError("Image is required")
    if len(data) > max_bytes:
        raise RasterValidationError("Image exceeds the byte limit")
    if min(
        max_bytes,
        max_width,
        max_height,
        max_pixels,
        max_frames,
        max_total_frame_pixels,
    ) <= 0:
        raise ValueError("Raster limits must be positive")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=tuple(RASTER_FORMAT_MIME_TYPES)) as image:
                image_format = str(image.format or "").upper()
                mime_type = RASTER_FORMAT_MIME_TYPES.get(image_format)
                if mime_type is None:
                    raise RasterValidationError("Unsupported or invalid raster image")
                width, height = (int(image.size[0]), int(image.size[1]))
                frames = max(1, int(getattr(image, "n_frames", 1)))
                pixels = width * height
                if width <= 0 or height <= 0:
                    raise RasterValidationError("Unsupported or invalid raster image")
                if width > max_width or height > max_height:
                    raise RasterValidationError("Image dimensions exceed the supported limit")
                if pixels > max_pixels:
                    raise RasterValidationError("Image exceeds the pixel limit")
                if frames > max_frames:
                    raise RasterValidationError("Image exceeds the frame limit")
                if pixels * frames > max_total_frame_pixels:
                    raise RasterValidationError("Image exceeds the frame pixel limit")
                image.verify()

            with Image.open(BytesIO(data), formats=tuple(RASTER_FORMAT_MIME_TYPES)) as image:
                image.seek(0)
                image.load()
    except RasterValidationError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        EOFError,
        OSError,
        SyntaxError,
        UnidentifiedImageError,
        ValueError,
    ) as exc:
        raise RasterValidationError("Unsupported or invalid raster image") from exc

    return RasterInspection(
        image_format=image_format,
        mime_type=mime_type,
        width=width,
        height=height,
        frames=frames,
    )


__all__ = (
    "MAX_RASTER_BYTES",
    "MAX_RASTER_FRAMES",
    "MAX_RASTER_HEIGHT",
    "MAX_RASTER_PIXELS",
    "MAX_RASTER_TOTAL_FRAME_PIXELS",
    "MAX_RASTER_WIDTH",
    "RASTER_FORMAT_MIME_TYPES",
    "RasterInspection",
    "RasterValidationError",
    "SUPPORTED_RASTER_MIME_TYPES",
    "inspect_raster_image",
)
