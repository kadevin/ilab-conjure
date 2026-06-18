from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from codex_image.client import DEFAULT_IMAGE_MODEL, DEFAULT_OPENAI_API_BASE_URL

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
from .schemas import (
    DEFAULT_WEBUI_GALLERY_ROOT,
    DEFAULT_WEBUI_INPUT_ROOT,
    DEFAULT_WEBUI_OUTPUT_ROOT,
    DEFAULT_WEBUI_SOURCE_DATA_ROOT,
)
from .startup_auth import AUTH_SOURCES, detect_startup_auth_source


def _default_auth_source() -> str:
    return detect_startup_auth_source()


class WebUISettings:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read_paths(self) -> dict[str, Path]:
        defaults = {
            "input_root": DEFAULT_WEBUI_INPUT_ROOT,
            "output_root": DEFAULT_WEBUI_OUTPUT_ROOT,
            "gallery_root": DEFAULT_WEBUI_GALLERY_ROOT,
            "source_data_root": DEFAULT_WEBUI_SOURCE_DATA_ROOT,
        }
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return defaults
        if not isinstance(payload, dict):
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

    def write_paths(self, payload: dict[str, Any]) -> dict[str, Path]:
        current = self.read_paths()
        paths = {
            "input_root": _settings_path(payload.get("input_root"), current["input_root"]),
            "output_root": _settings_path(payload.get("output_root"), current["output_root"]),
            "gallery_root": _settings_path(payload.get("gallery_root"), current["gallery_root"]),
            "source_data_root": _settings_path(payload.get("source_data_root"), current["source_data_root"]),
        }
        _validate_webui_paths(paths)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({key: str(value) for key, value in paths.items()}, indent=2, ensure_ascii=False), encoding="utf-8")
        return paths


def _settings_path(value: Any, default: Path) -> Path:
    raw = str(value).strip() if value not in (None, "") else str(default)
    if not raw:
        raise ValueError("Directory path cannot be empty")
    return Path(raw).expanduser()


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


class ApiSettings:
    _PERSISTED_API_MODES = {"images", "responses"}
    _PERSISTED_API_MODE_DEFAULT = "images"
    _PERSISTED_CODEX_MODES = {"images", "responses"}
    _PERSISTED_CODEX_MODE_DEFAULT = "images"
    _PERSISTED_PROVIDER_ID_DEFAULT = "default"
    _PERSISTED_IMAGES_CONCURRENCY_DEFAULT = 4
    _PERSISTED_IMAGES_CONCURRENCY_MIN = 1
    _PERSISTED_IMAGES_CONCURRENCY_MAX = 32

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return self._settings_from_providers(
                [self.default_provider()],
                self._PERSISTED_PROVIDER_ID_DEFAULT,
                codex_mode=self._PERSISTED_CODEX_MODE_DEFAULT,
            )
        if not isinstance(payload, dict):
            return self._settings_from_providers(
                [self.default_provider()],
                self._PERSISTED_PROVIDER_ID_DEFAULT,
                codex_mode=self._PERSISTED_CODEX_MODE_DEFAULT,
            )
        try:
            codex_mode = self._normalize_persisted_codex_mode(payload.get("codex_mode"))
            if isinstance(payload.get("providers"), list):
                providers = self._normalize_providers(payload["providers"])
                active_provider_id = self._normalize_provider_id(payload.get("active_provider_id") or providers[0]["id"])
                return self._settings_from_providers(providers, active_provider_id, codex_mode=codex_mode)
            provider = self._normalize_provider(payload, fallback_id=self._PERSISTED_PROVIDER_ID_DEFAULT, fallback_name="Default")
            return self._settings_from_providers([provider], provider["id"], codex_mode=codex_mode)
        except ValueError:
            return self._settings_from_providers(
                [self.default_provider()],
                self._PERSISTED_PROVIDER_ID_DEFAULT,
                codex_mode=self._PERSISTED_CODEX_MODE_DEFAULT,
            )

    def write(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.read()
        if not isinstance(payload, dict):
            raise ValueError("API settings payload must be an object")
        codex_mode = self._normalize_persisted_codex_mode(payload.get("codex_mode", current.get("codex_mode")))
        if isinstance(payload.get("providers"), list):
            next_settings = self._write_provider_payload(payload, current, codex_mode=codex_mode)
        else:
            next_settings = self._write_active_provider_payload(payload, current, codex_mode=codex_mode)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(next_settings, indent=2, ensure_ascii=False), encoding="utf-8")
        return self.read()

    def public_settings(self) -> dict[str, Any]:
        settings = self.read()
        api_key = str(settings.get("api_key") or "")
        return {
            "active_provider_id": settings["active_provider_id"],
            "base_url": settings["base_url"],
            "image_model": settings["image_model"],
            "codex_mode": settings["codex_mode"],
            "api_mode": settings["api_mode"],
            "images_concurrency": settings["images_concurrency"],
            "api_key_set": bool(api_key),
            "api_key_masked": _mask_api_key(api_key) if api_key else "",
            "providers": [self._public_provider(provider) for provider in settings["providers"]],
        }

    def has_api_credentials(self) -> bool:
        settings = self.read()
        return bool(str(settings.get("base_url") or "").strip() and str(settings.get("api_key") or "").strip())

    def provider_settings(self, provider_id: str | None = None) -> dict[str, Any]:
        settings = self.read()
        target_id = self._normalize_provider_id(provider_id or settings["active_provider_id"])
        provider = next((item for item in settings["providers"] if item["id"] == target_id), None)
        if provider is None:
            provider = next((item for item in settings["providers"] if item["id"] == settings["active_provider_id"]), settings["providers"][0])
        return dict(provider)

    @staticmethod
    def default_settings() -> dict[str, Any]:
        return {
            "base_url": DEFAULT_OPENAI_API_BASE_URL,
            "api_key": "",
            "image_model": DEFAULT_IMAGE_MODEL,
            "api_mode": ApiSettings._PERSISTED_API_MODE_DEFAULT,
            "images_concurrency": ApiSettings._PERSISTED_IMAGES_CONCURRENCY_DEFAULT,
        }

    @classmethod
    def default_provider(cls) -> dict[str, Any]:
        return {
            "id": cls._PERSISTED_PROVIDER_ID_DEFAULT,
            "name": "Default",
            **cls.default_settings(),
        }

    @classmethod
    def _settings_from_providers(
        cls,
        providers: list[dict[str, Any]],
        active_provider_id: str,
        *,
        codex_mode: Any | None = None,
    ) -> dict[str, Any]:
        if not providers:
            providers = [cls.default_provider()]
        active_id = cls._normalize_provider_id(active_provider_id)
        active = next((provider for provider in providers if provider["id"] == active_id), providers[0])
        return {
            **active,
            "codex_mode": cls._normalize_persisted_codex_mode(codex_mode),
            "active_provider_id": active["id"],
            "providers": providers,
        }

    def _write_provider_payload(self, payload: dict[str, Any], current: dict[str, Any], *, codex_mode: str) -> dict[str, Any]:
        current_by_id = {provider["id"]: provider for provider in current["providers"]}
        providers: list[dict[str, Any]] = []
        for index, raw_provider in enumerate(payload.get("providers") or [], start=1):
            if not isinstance(raw_provider, dict):
                continue
            provider_id = self._normalize_provider_id(raw_provider.get("id") or f"provider-{index}")
            existing = current_by_id.get(provider_id)
            if existing is None and "api_key" not in raw_provider and index == 1 and len(current["providers"]) == 1:
                existing = current["providers"][0]
            providers.append(
                self._normalize_provider(
                    raw_provider,
                    fallback_id=provider_id,
                    fallback_name=f"Provider {index}",
                    existing=existing,
                )
            )
        if not providers:
            providers = [self.default_provider()]
        active_provider_id = self._normalize_provider_id(payload.get("active_provider_id") or current.get("active_provider_id") or providers[0]["id"])
        if not any(provider["id"] == active_provider_id for provider in providers):
            active_provider_id = providers[0]["id"]
        return self._persisted_settings(providers, active_provider_id, codex_mode=codex_mode)

    def _write_active_provider_payload(self, payload: dict[str, Any], current: dict[str, Any], *, codex_mode: str) -> dict[str, Any]:
        providers = [dict(provider) for provider in current["providers"]]
        active_provider_id = self._normalize_provider_id(payload.get("active_provider_id") or current["active_provider_id"])
        if not any(provider["id"] == active_provider_id for provider in providers):
            active_provider_id = providers[0]["id"]
        for index, provider in enumerate(providers):
            if provider["id"] != active_provider_id:
                continue
            merged = dict(provider)
            for key in ("name", "base_url", "api_key", "image_model", "api_mode", "images_concurrency"):
                if key in payload:
                    merged[key] = payload[key]
            providers[index] = self._normalize_provider(merged, fallback_id=provider["id"], fallback_name=provider["name"], existing=provider)
            break
        return self._persisted_settings(providers, active_provider_id, codex_mode=codex_mode)

    @classmethod
    def _persisted_settings(cls, providers: list[dict[str, Any]], active_provider_id: str, *, codex_mode: str) -> dict[str, Any]:
        settings = cls._settings_from_providers(providers, active_provider_id, codex_mode=codex_mode)
        return {
            "active_provider_id": settings["active_provider_id"],
            "codex_mode": settings["codex_mode"],
            "base_url": settings["base_url"],
            "api_key": settings["api_key"],
            "image_model": settings["image_model"],
            "api_mode": settings["api_mode"],
            "images_concurrency": settings["images_concurrency"],
            "providers": settings["providers"],
        }

    @classmethod
    def _normalize_providers(cls, providers: list[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, raw_provider in enumerate(providers, start=1):
            if not isinstance(raw_provider, dict):
                continue
            provider = cls._normalize_provider(raw_provider, fallback_id=f"provider-{index}", fallback_name=f"Provider {index}")
            if provider["id"] in seen:
                continue
            seen.add(provider["id"])
            normalized.append(provider)
        return normalized or [cls.default_provider()]

    @classmethod
    def _normalize_provider(
        cls,
        payload: dict[str, Any],
        *,
        fallback_id: str,
        fallback_name: str,
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        existing = existing or {}
        provider_id = cls._normalize_provider_id(payload.get("id") or fallback_id)
        name = str(payload.get("name") or existing.get("name") or fallback_name or provider_id).strip() or provider_id
        return {
            "id": provider_id,
            "name": name,
            "base_url": cls._normalize_base_url(payload.get("base_url", existing.get("base_url", DEFAULT_OPENAI_API_BASE_URL))),
            "api_key": str(payload.get("api_key", existing.get("api_key", "")) or "").strip(),
            "image_model": cls._normalize_image_model(payload.get("image_model", existing.get("image_model", DEFAULT_IMAGE_MODEL))),
            "api_mode": cls._normalize_persisted_api_mode(
                payload.get("api_mode", existing.get("api_mode", cls._PERSISTED_API_MODE_DEFAULT))
            ),
            "images_concurrency": cls._normalize_persisted_images_concurrency(
                payload.get("images_concurrency", existing.get("images_concurrency", cls._PERSISTED_IMAGES_CONCURRENCY_DEFAULT))
            ),
        }

    @classmethod
    def _normalize_provider_id(cls, value: Any) -> str:
        raw = str(value or cls._PERSISTED_PROVIDER_ID_DEFAULT).strip().lower()
        normalized = re.sub(r"[^a-z0-9_-]+", "-", raw).strip("-")
        return normalized or cls._PERSISTED_PROVIDER_ID_DEFAULT

    @classmethod
    def _public_provider(cls, provider: dict[str, Any]) -> dict[str, Any]:
        api_key = str(provider.get("api_key") or "")
        return {
            "id": provider["id"],
            "name": provider["name"],
            "base_url": provider["base_url"],
            "image_model": provider["image_model"],
            "api_mode": provider["api_mode"],
            "images_concurrency": cls._normalize_persisted_images_concurrency(provider.get("images_concurrency")),
            "api_key_set": bool(api_key),
            "api_key_masked": _mask_api_key(api_key) if api_key else "",
        }

    @classmethod
    def _normalize_persisted_api_mode(cls, value: Any) -> str:
        mode = str(value or "").strip().lower()
        return mode if mode in cls._PERSISTED_API_MODES else cls._PERSISTED_API_MODE_DEFAULT

    @classmethod
    def _normalize_persisted_codex_mode(cls, value: Any) -> str:
        mode = str(value or "").strip().lower()
        return mode if mode in cls._PERSISTED_CODEX_MODES else cls._PERSISTED_CODEX_MODE_DEFAULT

    @classmethod
    def _normalize_persisted_images_concurrency(cls, value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = cls._PERSISTED_IMAGES_CONCURRENCY_DEFAULT
        return min(cls._PERSISTED_IMAGES_CONCURRENCY_MAX, max(cls._PERSISTED_IMAGES_CONCURRENCY_MIN, parsed))

    @staticmethod
    def _normalize_base_url(value: Any) -> str:
        raw = str(value or DEFAULT_OPENAI_API_BASE_URL).strip().rstrip("/")
        if not raw:
            raw = DEFAULT_OPENAI_API_BASE_URL
        parts = urlsplit(raw)
        if not parts.scheme or not parts.netloc:
            raise ValueError("OpenAI-compatible base_url must be an absolute URL")
        path = parts.path.rstrip("/")
        for suffix in ("/responses", "/images/generations", "/images/edits"):
            if path.endswith(suffix):
                path = path[: -len(suffix)]
                break
        if not path:
            path = "/v1"
        return urlunsplit((parts.scheme, parts.netloc, path, "", ""))

    @staticmethod
    def _normalize_image_model(value: Any) -> str:
        model = str(value or DEFAULT_IMAGE_MODEL).strip()
        if not model:
            raise ValueError("Image model cannot be empty")
        return model
