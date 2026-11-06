from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image, ImageOps

from codex_image.raster_validation import MAX_RASTER_BYTES, inspect_raster_image


def validate_markup_image(markup_url: str, first_image_url: str) -> None:
    def decode(url: str) -> bytes:
        header, separator, data = url.partition(",")
        if not separator or not header.startswith("data:image/") or not header.endswith(";base64"):
            raise ValueError("markup_requires_local_image_data")
        if len(data) > ((MAX_RASTER_BYTES + 2) // 3) * 4:
            raise ValueError("markup_exceeds_byte_limit")
        return base64.b64decode(data, validate=True)
    markup = decode(markup_url)
    first = decode(first_image_url)
    overlay = inspect_raster_image(markup, max_pixels=16_777_216)
    inspect_raster_image(first, max_pixels=16_777_216)
    if overlay.mime_type != "image/png":
        raise ValueError("markup_requires_transparent_png")
    with Image.open(BytesIO(first)) as source, Image.open(BytesIO(markup)) as annotation:
        if ImageOps.exif_transpose(source).size != annotation.size:
            raise ValueError("markup_dimensions_must_match_first_image")
        if annotation.convert("RGBA").getchannel("A").getextrema()[0] == 255:
            raise ValueError("markup_requires_transparent_png")
