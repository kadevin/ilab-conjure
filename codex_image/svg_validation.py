"""Validate generated SVG as a bounded, self-contained static image."""
from __future__ import annotations

import math
import re
from xml.etree import ElementTree  # nosec B405 — DTD/entities rejected before parsing

from codex_image.raster_validation import MAX_RASTER_BYTES, RasterInspection


_ELEMENTS = frozenset({
    "svg", "g", "defs", "title", "desc", "metadata", "path", "rect", "circle",
    "ellipse", "line", "polyline", "polygon", "text", "tspan", "textPath",
    "linearGradient", "radialGradient", "stop", "clipPath", "mask", "pattern",
    "symbol", "use", "marker", "style", "filter", "feBlend", "feColorMatrix",
    "feComponentTransfer", "feComposite", "feConvolveMatrix", "feDiffuseLighting",
    "feDisplacementMap", "feDistantLight", "feDropShadow", "feFlood", "feFuncA",
    "feFuncB", "feFuncG", "feFuncR", "feGaussianBlur", "feMerge", "feMergeNode",
    "feMorphology", "feOffset", "fePointLight", "feSpecularLighting", "feSpotLight",
    "feTile", "feTurbulence",
})
_NAMESPACE = "http://www.w3.org/2000/svg"
_XLINK = "http://www.w3.org/1999/xlink"


def inspect_static_svg(data: bytes) -> RasterInspection:
    if not data or len(data) > MAX_RASTER_BYTES:
        raise ValueError("SVG exceeds the byte limit")
    source = data.decode("utf-8-sig")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)|<\?(?!xml\s)", source, re.I):
        raise ValueError("SVG declarations are not supported")
    try:
        root = ElementTree.fromstring(source)  # nosec B314 — bounded UTF-8, no DTD/entities
    except ElementTree.ParseError as exc:
        raise ValueError("Invalid SVG XML") from exc
    if root.tag != f"{{{_NAMESPACE}}}svg":
        raise ValueError("Expected an SVG document")
    stack = [(root, 0)]
    count = 0
    while stack:
        element, depth = stack.pop()
        count += 1
        if count > 100_000 or depth > 64:
            raise ValueError("SVG exceeds the structural limit")
        name = element.tag.removeprefix(f"{{{_NAMESPACE}}}")
        if name not in _ELEMENTS:
            raise ValueError("SVG contains unsupported active or embedded content")
        if name == "style":
            _validate_css(element.text or "")
        for key, value in element.attrib.items():
            if key in {"{http://www.w3.org/XML/1998/namespace}space", "{http://www.w3.org/XML/1998/namespace}lang"}:
                continue
            local = key.removeprefix(f"{{{_XLINK}}}")
            if local.lower().startswith("on") or local in {"base", "src"} or "}" in local:
                raise ValueError("SVG contains an unsafe attribute")
            if local == "href" and not re.fullmatch(r"#[\w.:-]+", value.strip()):
                raise ValueError("SVG references must stay inside the image")
            _validate_css(value)
        stack.extend((child, depth + 1) for child in element)
    view_box = re.split(r"[\s,]+", root.get("viewBox", "").strip())
    def dimension(name: str, index: int) -> int:
        value = root.get(name, "")
        if re.fullmatch(r"[\d.]+(?:px)?", value):
            number = float(value.removesuffix("px"))
        elif len(view_box) == 4:
            number = float(view_box[index])
        else:
            raise ValueError("SVG requires intrinsic dimensions or a viewBox")
        if not math.isfinite(number) or not 0 < number <= 16_384:
            raise ValueError("SVG dimensions exceed the supported limit")
        return max(1, round(number))
    return RasterInspection("SVG", "image/svg+xml", dimension("width", 2), dimension("height", 3), 1)


def _validate_css(value: str) -> None:
    # No CSS escapes, imports, comments or external URLs; fragment paint servers
    # remain available for gradients, clipping and masks.
    if any(token in value for token in ("\\", "@", "/*", "*/")):
        raise ValueError("SVG contains unsupported CSS")
    for match in re.finditer(r"url\s*\((.*?)\)", value, re.I | re.S):
        if not re.fullmatch(r"['\"]?#[\w.:-]+['\"]?", match.group(1).strip()):
            raise ValueError("SVG references must stay inside the image")
