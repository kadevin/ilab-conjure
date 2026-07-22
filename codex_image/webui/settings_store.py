from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .color_settings import (
    DEFAULT_COLOR_FAVORITES,
    DEFAULT_COLOR_RECENT_LIMIT,
    MAX_COLOR_FAVORITES,
    MAX_COLOR_IMPORT_BYTES,
    MAX_COLOR_IMPORT_RECORDS,
    MAX_COLOR_RECENT_LIMIT,
    ColorPaletteSettings,
    _aco_color_to_hex,
    _color_name_from_slug,
    _color_palette_css,
    _css_color_slug,
    _normalize_color_favorites,
    _normalize_color_list,
    _normalize_color_name,
    _normalize_color_palette_payload,
    _normalize_color_recent_limit,
    _normalize_hex_color,
    _parse_aco_color_palette,
    _parse_aco_color_records,
    _parse_color_palette_import,
    _parse_text_color_palette,
    _read_aco_unicode_string,
)
from .prompt_snippets import (
    MAX_PROMPT_SNIPPETS,
    MAX_PROMPT_SNIPPET_CATEGORY_LENGTH,
    MAX_PROMPT_SNIPPET_CONTENT_LENGTH,
    MAX_PROMPT_SNIPPET_TAG_LENGTH,
    MAX_PROMPT_SNIPPET_TITLE_LENGTH,
    PromptSnippetSettings,
    _clean_prompt_snippet_category,
    _clean_prompt_snippet_content,
    _clean_prompt_snippet_id,
    _clean_prompt_snippet_order,
    _clean_prompt_snippet_tag,
    _clean_prompt_snippet_title,
    _ensure_unique_prompt_snippet_tag,
    _normalize_prompt_snippet_payload,
    _normalize_prompt_snippets_payload,
)
from .prompt_templates import (
    MAX_PROMPT_TEMPLATE_CATEGORY_LENGTH,
    MAX_PROMPT_TEMPLATE_CONTENT_LENGTH,
    MAX_PROMPT_TEMPLATE_IMPORT_BYTES,
    MAX_PROMPT_TEMPLATE_NOTES_LENGTH,
    MAX_PROMPT_TEMPLATE_SHORT_TITLE_LENGTH,
    MAX_PROMPT_TEMPLATE_TAGS,
    MAX_PROMPT_TEMPLATE_TAG_LENGTH,
    MAX_PROMPT_TEMPLATE_THUMBNAIL_URL_LENGTH,
    MAX_PROMPT_TEMPLATE_TITLE_LENGTH,
    MAX_PROMPT_TEMPLATES,
    PROMPT_TEMPLATE_MODES,
    SUPPORTED_PROMPT_TEMPLATE_MODEL_HINTS,
    PromptTemplateSettings,
    _clean_prompt_template_category,
    _clean_prompt_template_category_order,
    _clean_prompt_template_content,
    _clean_prompt_template_id,
    _clean_prompt_template_mode,
    _clean_prompt_template_model_hint,
    _clean_prompt_template_notes,
    _clean_prompt_template_short_title,
    _clean_prompt_template_tags,
    _clean_prompt_template_thumbnail_url,
    _clean_prompt_template_title,
    _clean_prompt_template_usage_count,
    _extract_prompt_template_variables,
    _normalize_prompt_template_category_payload,
    _normalize_prompt_template_categories_payload,
    _normalize_prompt_template_payload,
    _normalize_prompt_templates_payload,
    _parse_prompt_template_import,
)
from .provider_settings import ProviderSettings
from .schemas import (
    DEFAULT_WEBUI_GALLERY_ROOT,
    DEFAULT_WEBUI_INPUT_ROOT,
    DEFAULT_WEBUI_OUTPUT_ROOT,
    DEFAULT_WEBUI_SOURCE_DATA_ROOT,
)
from .startup_auth import AUTH_SOURCES, detect_startup_auth_source

SUPPORTED_LOCALES = ("zh-CN", "zh-TW", "zh-HK", "ja", "ko", "en", "es", "pt", "fr", "de", "ru", "it", "hi")
_SUPPORTED_LOCALE_BY_LOWER = {locale.lower(): locale for locale in SUPPORTED_LOCALES}


def _default_auth_source() -> str:
    return detect_startup_auth_source()


class WebUISettings:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _read_payload(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def read_paths(self) -> dict[str, Path]:
        defaults = {
            "input_root": DEFAULT_WEBUI_INPUT_ROOT,
            "output_root": DEFAULT_WEBUI_OUTPUT_ROOT,
            "gallery_root": DEFAULT_WEBUI_GALLERY_ROOT,
            "source_data_root": DEFAULT_WEBUI_SOURCE_DATA_ROOT,
        }
        payload = self._read_payload()
        if not payload:
            return defaults
        try:
            paths = {
                key: _settings_path(payload.get(key), default)
                for key, default in defaults.items()
            }
            _validate_webui_paths(paths)
        except ValueError:
            return defaults
        return paths

    def read_locale(self) -> str | None:
        return _settings_locale(self._read_payload().get("locale"), allow_empty=True)

    def write_paths(self, payload: dict[str, Any]) -> dict[str, Path]:
        current = self.read_paths()
        paths = {
            "input_root": _settings_path(payload.get("input_root"), current["input_root"]),
            "output_root": _settings_path(payload.get("output_root"), current["output_root"]),
            "gallery_root": _settings_path(payload.get("gallery_root"), current["gallery_root"]),
            "source_data_root": _settings_path(payload.get("source_data_root"), current["source_data_root"]),
        }
        _validate_webui_paths(paths)
        locale = self.read_locale()
        persisted: dict[str, str] = {key: str(value) for key, value in paths.items()}
        if locale:
            persisted["locale"] = locale
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(persisted, indent=2, ensure_ascii=False), encoding="utf-8")
        return paths

    def write_locale(self, locale: Any) -> str:
        normalized = _settings_locale(locale)
        payload = self._read_payload()
        payload["locale"] = normalized
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return normalized


def _settings_path(value: Any, default: Path) -> Path:
    raw = str(value).strip() if value not in (None, "") else str(default)
    if not raw:
        raise ValueError("Directory path cannot be empty")
    return Path(raw).expanduser()


def _settings_locale(value: Any, *, allow_empty: bool = False) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        if allow_empty:
            return None
        raise ValueError("Unsupported locale")
    normalized = raw.replace("_", "-").split(".", 1)[0].lower()
    exact = _SUPPORTED_LOCALE_BY_LOWER.get(normalized)
    if exact:
        return exact
    if normalized.startswith(("zh-hk", "zh-mo")):
        return "zh-HK"
    if normalized.startswith("zh-tw") or normalized.startswith("zh-hant"):
        return "zh-TW"
    if normalized.startswith(("zh-cn", "zh-sg", "zh-hans")) or normalized == "zh":
        return "zh-CN"
    for locale in ("ja", "ko", "en", "es", "pt", "fr", "de", "ru", "it", "hi"):
        if normalized.startswith(locale):
            return locale
    if allow_empty:
        return None
    raise ValueError("Unsupported locale")


def _validate_webui_paths(paths: dict[str, Path]) -> None:
    input_root = paths["input_root"]
    output_root = paths["output_root"]
    gallery_root = paths["gallery_root"]
    source_data_root = paths["source_data_root"]
    if str(input_root).strip() == "" or str(output_root).strip() == "":
        raise ValueError("Input and output directories are required")
    if not _is_relative_to(gallery_root, input_root):
        raise ValueError("Gallery directory must be inside the input directory")
    if not _is_relative_to(source_data_root, output_root):
        raise ValueError("Source data directory must be inside the output directory")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
    except ValueError:
        return False
    return True


def _mask_api_key(api_key: str) -> str:
    clean = str(api_key or "").strip()
    if not clean:
        return ""
    if len(clean) <= 8:
        return "********"
    return f"{clean[:3]}...{clean[-4:]}"


class AuthSettings:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read_source(self) -> str:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return _default_auth_source()
        source = str(payload.get("source") or "").strip().lower()
        return source if source in AUTH_SOURCES else _default_auth_source()

    def write_source(self, source: str) -> None:
        if source not in AUTH_SOURCES:
            raise ValueError(f"Unsupported auth source: {source}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"source": source}, indent=2), encoding="utf-8")


ApiSettings = ProviderSettings
