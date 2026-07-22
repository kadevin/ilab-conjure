from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


DEFAULT_COLOR_RECENT_LIMIT = 6
MAX_COLOR_RECENT_LIMIT = 24
MAX_COLOR_FAVORITES = 64
MAX_COLOR_IMPORT_BYTES = 1024 * 1024
MAX_COLOR_IMPORT_RECORDS = 4096
DEFAULT_COLOR_FAVORITES = [
    {"name": "白色", "hex": "#FFFFFF", "order": 10},
    {"name": "黑色", "hex": "#111111", "order": 20},
    {"name": "暖米色", "hex": "#F6E8D8", "order": 30},
    {"name": "浅绿", "hex": "#E6F0EC", "order": 40},
    {"name": "品牌绿", "hex": "#457B66", "order": 50},
    {"name": "桃橙", "hex": "#F4B183", "order": 60},
    {"name": "浅蓝", "hex": "#B7D7F0", "order": 70},
    {"name": "浅粉", "hex": "#F8D7DA", "order": 80},
]


class ColorPaletteSettings:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return self.default_settings()
        if not isinstance(payload, dict):
            return self.default_settings()
        try:
            return _normalize_color_palette_payload(payload, default_when_missing=True)
        except ValueError:
            return self.default_settings()

    def write(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Color palette payload must be an object")
        current = self.read()
        merged = {
            "version": 1,
            "favorites": payload.get("favorites", current["favorites"]),
            "recent_colors": payload.get("recent_colors", current["recent_colors"]),
            "recent_limit": payload.get("recent_limit", current["recent_limit"]),
        }
        settings = _normalize_color_palette_payload(merged, default_when_missing=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
        return settings

    def import_favorites(self, items: list[dict[str, Any]]) -> tuple[dict[str, Any], int, int]:
        if not items:
            raise ValueError("No importable colors found in palette file")
        current = self.read()
        favorites = [dict(item) for item in current["favorites"]]
        seen = {item["hex"] for item in favorites}
        imported = 0
        skipped = 0
        for item in items:
            try:
                color = _normalize_hex_color(item.get("hex"))
            except ValueError:
                skipped += 1
                continue
            if color in seen or len(favorites) >= MAX_COLOR_FAVORITES:
                skipped += 1
                continue
            seen.add(color)
            imported += 1
            favorites.append(
                {
                    "name": _normalize_color_name(item.get("name"), fallback=f"Imported {imported}"),
                    "hex": color,
                    "order": len(favorites) * 10 + 10,
                }
            )
        saved = self.write({"favorites": favorites})
        return saved, imported, skipped

    @staticmethod
    def default_settings() -> dict[str, Any]:
        return {
            "version": 1,
            "favorites": [dict(item) for item in DEFAULT_COLOR_FAVORITES],
            "recent_colors": [],
            "recent_limit": DEFAULT_COLOR_RECENT_LIMIT,
        }


def _normalize_color_palette_payload(payload: dict[str, Any], *, default_when_missing: bool) -> dict[str, Any]:
    recent_limit = _normalize_color_recent_limit(payload.get("recent_limit"))
    favorites_value = payload.get("favorites")
    if favorites_value is None and default_when_missing:
        favorites_value = DEFAULT_COLOR_FAVORITES
    favorites = _normalize_color_favorites(favorites_value or [])
    recent_colors = _normalize_color_list(payload.get("recent_colors") or [], limit=recent_limit)
    return {
        "version": 1,
        "favorites": favorites,
        "recent_colors": recent_colors,
        "recent_limit": recent_limit,
    }


def _normalize_color_favorites(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise ValueError("Color palette favorites must be an array")
    favorites: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items[:MAX_COLOR_FAVORITES]:
        if not isinstance(item, dict):
            continue
        color = _normalize_hex_color(item.get("hex"))
        if color in seen:
            continue
        seen.add(color)
        order = (len(favorites) + 1) * 10
        favorites.append(
            {
                "name": _normalize_color_name(item.get("name"), fallback=f"Color {len(favorites) + 1}"),
                "hex": color,
                "order": order,
            }
        )
    return favorites


def _normalize_color_list(items: Any, *, limit: int) -> list[str]:
    if not isinstance(items, list):
        raise ValueError("Recent colors must be an array")
    colors: list[str] = []
    seen: set[str] = set()
    for item in items:
        color = _normalize_hex_color(item)
        if color in seen:
            continue
        seen.add(color)
        colors.append(color)
        if len(colors) >= limit:
            break
    return colors


def _normalize_hex_color(value: Any) -> str:
    raw = str(value or "").strip().removeprefix("#")
    if re.fullmatch(r"[0-9a-fA-F]{3}", raw):
        return "#" + "".join(char + char for char in raw).upper()
    if re.fullmatch(r"[0-9a-fA-F]{6}", raw):
        return f"#{raw.upper()}"
    raise ValueError(f"Invalid hex color: {value}")


def _normalize_color_name(value: Any, *, fallback: str) -> str:
    name = re.sub(r"\s+", " ", str(value or "").strip())
    return name[:48] if name else fallback


def _normalize_color_recent_limit(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_COLOR_RECENT_LIMIT
    return min(MAX_COLOR_RECENT_LIMIT, max(0, parsed))


def _color_palette_css(settings: dict[str, Any]) -> str:
    favorites = settings.get("favorites") if isinstance(settings, dict) else []
    if not isinstance(favorites, list):
        favorites = []
    slug_counts: dict[str, int] = {}
    swatches: list[tuple[str, str, str]] = []
    for index, item in enumerate(favorites, start=1):
        if not isinstance(item, dict):
            continue
        try:
            color = _normalize_hex_color(item.get("hex"))
        except ValueError:
            continue
        name = _normalize_color_name(item.get("name"), fallback=f"Color {index}")
        slug_base = _css_color_slug(name, fallback=f"color-{index}")
        count = slug_counts.get(slug_base, 0) + 1
        slug_counts[slug_base] = count
        slug = slug_base if count == 1 else f"{slug_base}-{count}"
        swatches.append((slug, name, color))

    lines = [
        "/* iLab CONJURE color palette.",
        "   Load this file from Photoshop's Swatches panel. */",
        ":root {",
    ]
    for slug, name, color in swatches:
        lines.append(f"  /* {name} */")
        lines.append(f"  --{slug}: {color};")
    lines.append("}")
    lines.append("")
    for slug, name, color in swatches:
        lines.append(f"/* {name} */")
        lines.append(f".swatch-{slug} {{ color: {color}; }}")
    lines.append("")
    return "\n".join(lines)


def _css_color_slug(name: str, *, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        return fallback
    if slug[0].isdigit():
        return f"color-{slug}"
    return slug


def _parse_color_palette_import(filename: str, payload: bytes, content_type: str | None) -> list[dict[str, Any]]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".aco":
        return _parse_aco_color_palette(payload)
    if suffix in {".css", ".html", ".htm", ".svg", ".txt"} or (content_type or "").startswith("text/"):
        return _parse_text_color_palette(payload)
    raise ValueError("Unsupported color palette file type")


def _parse_text_color_palette(payload: bytes) -> list[dict[str, Any]]:
    text = payload.decode("utf-8-sig", errors="replace")
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_color(color_value: Any, name: str | None = None) -> None:
        try:
            color = _normalize_hex_color(color_value)
        except ValueError:
            return
        if color in seen:
            return
        seen.add(color)
        items.append({"name": name or f"Imported {len(items) + 1}", "hex": color})

    for match in re.finditer(r"--([a-zA-Z0-9_-]+)\s*:\s*(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})\b", text):
        add_color(match.group(2), _color_name_from_slug(match.group(1)))

    for match in re.finditer(r"(?<![0-9a-fA-F])#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F])", text):
        add_color(f"#{match.group(1)}")

    for match in re.finditer(
        r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(?:\s*,\s*[^)]*)?\)",
        text,
        flags=re.IGNORECASE,
    ):
        channels = [int(match.group(index)) for index in range(1, 4)]
        if any(channel > 255 for channel in channels):
            continue
        add_color("#" + "".join(f"{channel:02X}" for channel in channels))

    if not items:
        raise ValueError("No importable colors found in palette file")
    return items


def _color_name_from_slug(value: str) -> str:
    return re.sub(r"[-_]+", " ", value).strip()[:48] or "Imported color"


def _parse_aco_color_palette(payload: bytes) -> list[dict[str, Any]]:
    offset = 0

    def read_u16() -> int:
        nonlocal offset
        if offset + 2 > len(payload):
            raise ValueError("Invalid ACO color palette")
        value = int.from_bytes(payload[offset : offset + 2], "big")
        offset += 2
        return value

    version = read_u16()
    if version not in {1, 2}:
        raise ValueError("Invalid ACO color palette")
    count = read_u16()
    if count > MAX_COLOR_IMPORT_RECORDS:
        raise ValueError("ACO color palette contains too many colors")
    if version == 1:
        version_one_items = _parse_aco_color_records(payload, offset, count, include_names=False)[0]
        offset += count * 10
        if offset + 4 <= len(payload) and int.from_bytes(payload[offset : offset + 2], "big") == 2:
            version_two_count = int.from_bytes(payload[offset + 2 : offset + 4], "big")
            if version_two_count > MAX_COLOR_IMPORT_RECORDS:
                raise ValueError("ACO color palette contains too many colors")
            version_two_items, _ = _parse_aco_color_records(payload, offset + 4, version_two_count, include_names=True)
            return version_two_items or version_one_items
        return version_one_items
    items, _ = _parse_aco_color_records(payload, offset, count, include_names=True)
    if not items:
        raise ValueError("No importable colors found in palette file")
    return items


def _parse_aco_color_records(payload: bytes, offset: int, count: int, *, include_names: bool) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index in range(count):
        if offset + 10 > len(payload):
            raise ValueError("Invalid ACO color palette")
        color_space = int.from_bytes(payload[offset : offset + 2], "big")
        components = [int.from_bytes(payload[offset + 2 + component * 2 : offset + 4 + component * 2], "big") for component in range(4)]
        offset += 10
        name = f"Imported {index + 1}"
        if include_names:
            name, offset = _read_aco_unicode_string(payload, offset)
            name = name or f"Imported {index + 1}"
        color = _aco_color_to_hex(color_space, components)
        if not color or color in seen:
            continue
        seen.add(color)
        items.append({"name": name, "hex": color})
    if not items:
        raise ValueError("No importable colors found in palette file")
    return items, offset


def _read_aco_unicode_string(payload: bytes, offset: int) -> tuple[str, int]:
    if offset + 4 > len(payload):
        raise ValueError("Invalid ACO color palette")
    length = int.from_bytes(payload[offset : offset + 4], "big")
    offset += 4
    byte_count = length * 2
    if offset + byte_count > len(payload):
        raise ValueError("Invalid ACO color palette")
    raw = payload[offset : offset + byte_count]
    offset += byte_count
    return raw.decode("utf-16-be", errors="replace").rstrip("\0"), offset


def _aco_color_to_hex(color_space: int, components: list[int]) -> str | None:
    if color_space == 0:
        channels = [round(value * 255 / 65535) for value in components[:3]]
    elif color_space == 8:
        gray = round(min(10000, components[0]) * 255 / 10000)
        channels = [gray, gray, gray]
    else:
        return None
    return "#" + "".join(f"{max(0, min(255, channel)):02X}" for channel in channels)
