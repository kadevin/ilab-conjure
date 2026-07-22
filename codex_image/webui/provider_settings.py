from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from codex_image.client_types import (
    DEFAULT_IMAGE_MODEL,
    DEFAULT_OPENAI_API_BASE_URL,
    normalize_openai_base_url,
)
from codex_image.providers import ProviderConnection, ProviderModelBinding

from .provider_validation import (
    normalize_provider_icon_emoji as _normalize_provider_icon_emoji,
    normalize_remote_model_id as _normalize_remote_model_id,
    normalize_slug as _normalize_slug,
    validate_v2_payload,
)


_CODEX_MODES = frozenset({"images", "responses"})
def _mask_api_key(api_key: str) -> str:
    clean = str(api_key or "").strip()
    if not clean:
        return ""
    if len(clean) <= 8:
        return "********"
    return f"{clean[:3]}...{clean[-4:]}"


def _normalize_codex_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in _CODEX_MODES else "images"


def _normalize_api_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in _CODEX_MODES else "images"


def _normalize_legacy_concurrency(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 4
    return min(32, max(1, parsed))


def _normalize_legacy_base_url(value: Any) -> str:
    try:
        return normalize_openai_base_url(value)
    except ValueError:
        return DEFAULT_OPENAI_API_BASE_URL


def migrate_legacy_provider(raw: Mapping[str, Any]) -> dict[str, Any]:
    provider_id = _normalize_slug(raw.get("id"), fallback="default")
    api_mode = _normalize_api_mode(raw.get("api_mode"))
    provider = {
        "id": provider_id,
        "name": str(raw.get("name") or provider_id).strip() or provider_id,
        "base_url": _normalize_legacy_base_url(raw.get("base_url")),
        "api_key": str(raw.get("api_key") or "").strip(),
        "concurrency": _normalize_legacy_concurrency(raw.get("images_concurrency")),
        "bindings": [
            {
                "id": f"{provider_id}-gpt-image-2",
                "canonical_model_id": "gpt-image-2",
                "remote_model_id": _normalize_remote_model_id(
                    raw.get("image_model") or DEFAULT_IMAGE_MODEL
                ),
                "protocol_profile": (
                    "openai_responses" if api_mode == "responses" else "openai_images"
                ),
                "parameter_codec": (
                    "gpt_openai_responses" if api_mode == "responses" else "gpt_openai_images"
                ),
                "operations": ["generate", "edit"],
            }
        ],
    }
    icon_emoji = _normalize_provider_icon_emoji(raw.get("icon_emoji"))
    if icon_emoji:
        provider["icon_emoji"] = icon_emoji
    return provider


def _without_api_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_api_keys(nested)
            for key, nested in value.items()
            if key != "api_key"
        }
    if isinstance(value, list):
        return [_without_api_keys(nested) for nested in value]
    return value


class ProviderSettings:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return self._default_settings()
        if not isinstance(payload, dict):
            return self._default_settings()
        if payload.get("schema_version") == 2:
            return self._validate_v2(payload)
        if "schema_version" in payload:
            raise ValueError("unsupported_schema_version")
        return self._validate_v2(self._migrate_v1(payload))

    def write(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("API settings payload must be an object")
        current = self.read()
        if self._is_v2_payload(payload):
            candidate = self._prepare_v2_write(payload, current)
        elif isinstance(payload.get("providers"), list):
            candidate = self._prepare_legacy_provider_write(payload, current)
        else:
            candidate = self._prepare_legacy_active_write(payload, current)
        settings = self._validate_v2(candidate)
        persisted = self._persisted(settings)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(persisted, indent=2, ensure_ascii=False), encoding="utf-8")
        return self.read()

    def public_settings(self) -> dict[str, Any]:
        settings = deepcopy(self.read())
        for provider in settings["providers"]:
            api_key = str(provider.get("api_key") or "")
            provider["api_key_set"] = bool(api_key)
            provider["api_key_masked"] = _mask_api_key(api_key) if api_key else ""
        active = self._active_provider(settings)
        api_key = str(active.get("api_key") or "")
        settings["api_key_set"] = bool(api_key)
        settings["api_key_masked"] = _mask_api_key(api_key) if api_key else ""
        return _without_api_keys(settings)

    def read_connections(self) -> list[ProviderConnection]:
        settings = self.read()
        defaults = settings["default_provider_by_model"]
        connections: list[ProviderConnection] = []
        for provider in settings["providers"]:
            bindings = tuple(
                ProviderModelBinding(
                    id=binding["id"],
                    provider_id=provider["id"],
                    canonical_model_id=binding["canonical_model_id"],
                    remote_model_id=binding["remote_model_id"],
                    protocol_profile=binding["protocol_profile"],
                    parameter_codec=binding["parameter_codec"],
                    operations=frozenset(binding["operations"]),
                    is_default=defaults.get(binding["canonical_model_id"]) == provider["id"],
                    append_aspect_ratio_prompt=bool(
                        binding.get("append_aspect_ratio_prompt", False)
                    ),
                )
                for binding in provider["bindings"]
            )
            connections.append(
                ProviderConnection(
                    id=provider["id"],
                    name=provider["name"],
                    base_url=provider["base_url"],
                    api_key=provider["api_key"],
                    concurrency=provider["concurrency"],
                    bindings=bindings,
                )
            )
        return connections

    def has_api_credentials(self) -> bool:
        provider = self.provider_settings()
        return bool(provider["base_url"] and provider["api_key"])

    def provider_settings(self, provider_id: str | None = None) -> dict[str, Any]:
        settings = self.read()
        target_id = _normalize_slug(
            provider_id or settings["active_provider_id"], fallback="default"
        )
        provider = next(
            (item for item in settings["providers"] if item["id"] == target_id),
            self._active_provider(settings),
        )
        return self._legacy_provider_projection(provider)

    @staticmethod
    def default_settings() -> dict[str, Any]:
        return {
            "base_url": DEFAULT_OPENAI_API_BASE_URL,
            "api_key": "",
            "image_model": DEFAULT_IMAGE_MODEL,
            "api_mode": "images",
            "images_concurrency": 4,
        }

    @classmethod
    def default_provider(cls) -> dict[str, Any]:
        return migrate_legacy_provider({"id": "default", "name": "Default", **cls.default_settings()})

    @classmethod
    def _default_settings(cls) -> dict[str, Any]:
        return cls._project_legacy(
            {
                "schema_version": 2,
                "codex_mode": "images",
                "active_provider_id": "default",
                "default_provider_by_model": {"gpt-image-2": "default"},
                "providers": [cls.default_provider()],
            }
        )

    @staticmethod
    def _is_v2_payload(payload: Mapping[str, Any]) -> bool:
        if payload.get("schema_version") == 2 or "default_provider_by_model" in payload:
            return True
        providers = payload.get("providers")
        return isinstance(providers, list) and any(
            isinstance(provider, dict) and "bindings" in provider for provider in providers
        )

    @classmethod
    def _migrate_v1(cls, payload: Mapping[str, Any]) -> dict[str, Any]:
        raw_providers = payload.get("providers")
        if isinstance(raw_providers, list):
            providers = [
                migrate_legacy_provider(provider)
                for provider in raw_providers
                if isinstance(provider, Mapping)
            ]
        else:
            providers = [migrate_legacy_provider(payload)]
        if not providers:
            providers = [cls.default_provider()]
        active_id = _normalize_slug(
            payload.get("active_provider_id") or providers[0]["id"], fallback="default"
        )
        if not any(provider["id"] == active_id for provider in providers):
            active_id = providers[0]["id"]
        return {
            "schema_version": 2,
            "codex_mode": _normalize_codex_mode(payload.get("codex_mode")),
            "active_provider_id": active_id,
            "default_provider_by_model": {"gpt-image-2": active_id},
            "providers": providers,
        }

    def _prepare_v2_write(
        self, payload: Mapping[str, Any], current: Mapping[str, Any]
    ) -> dict[str, Any]:
        candidate = deepcopy(dict(payload))
        candidate["schema_version"] = 2
        candidate.setdefault("codex_mode", current.get("codex_mode", "images"))
        candidate.setdefault("active_provider_id", current.get("active_provider_id", "default"))
        current_by_id = {provider["id"]: provider for provider in current["providers"]}
        providers = candidate.get("providers")
        if not isinstance(providers, list):
            providers = deepcopy(current["providers"])
        candidate["providers"] = self._apply_key_copy_semantics(providers, current_by_id)
        return candidate

    def _prepare_legacy_provider_write(
        self, payload: Mapping[str, Any], current: Mapping[str, Any]
    ) -> dict[str, Any]:
        current_by_id = {provider["id"]: provider for provider in current["providers"]}
        providers: list[dict[str, Any]] = []
        for index, raw in enumerate(payload.get("providers") or [], start=1):
            if not isinstance(raw, Mapping):
                continue
            provider_id = _normalize_slug(raw.get("id"), fallback=f"provider-{index}")
            existing = current_by_id.get(provider_id)
            merged = dict(raw)
            copied_api_key: str | None = None
            if "api_key" not in merged:
                source_id = _normalize_slug(
                    merged.get("api_key_source_provider_id"), fallback=""
                )
                source = current_by_id.get(source_id)
                if source is not None:
                    copied_api_key = str(source["api_key"])
                elif existing is not None:
                    copied_api_key = str(existing["api_key"])
                elif index == 1 and len(current["providers"]) == 1:
                    copied_api_key = str(current["providers"][0]["api_key"])
            if copied_api_key is not None:
                merged["api_key"] = copied_api_key
            if existing is None:
                providers.append(migrate_legacy_provider(merged))
                continue
            provider = deepcopy(existing)
            provider["name"] = str(merged.get("name") or provider["name"]).strip() or provider_id
            if "base_url" in merged:
                provider["base_url"] = _normalize_legacy_base_url(merged.get("base_url"))
            if "api_key" in merged:
                provider["api_key"] = str(merged.get("api_key") or "").strip()
            if "images_concurrency" in merged:
                provider["concurrency"] = _normalize_legacy_concurrency(
                    merged.get("images_concurrency")
                )
            gpt_binding = next(
                (
                    binding
                    for binding in provider["bindings"]
                    if binding["canonical_model_id"] == "gpt-image-2"
                ),
                None,
            )
            if gpt_binding is not None:
                if "image_model" in merged:
                    gpt_binding["remote_model_id"] = _normalize_remote_model_id(
                        merged.get("image_model")
                    )
                if "api_mode" in merged:
                    api_mode = _normalize_api_mode(merged.get("api_mode"))
                    gpt_binding["protocol_profile"] = (
                        "openai_responses" if api_mode == "responses" else "openai_images"
                    )
                    gpt_binding["parameter_codec"] = (
                        "gpt_openai_responses" if api_mode == "responses" else "gpt_openai_images"
                    )
            providers.append(provider)
        if not providers:
            providers = [self.default_provider()]
        active_id = _normalize_slug(
            payload.get("active_provider_id") or current.get("active_provider_id"),
            fallback=providers[0]["id"],
        )
        if not any(provider["id"] == active_id for provider in providers):
            active_id = providers[0]["id"]
        defaults = {
            model_id: provider_id
            for model_id, provider_id in current["default_provider_by_model"].items()
            if any(
                provider["id"] == provider_id
                and any(binding["canonical_model_id"] == model_id for binding in provider["bindings"])
                for provider in providers
            )
        }
        if any(
            provider["id"] == active_id
            and any(binding["canonical_model_id"] == "gpt-image-2" for binding in provider["bindings"])
            for provider in providers
        ):
            defaults["gpt-image-2"] = active_id
        ordered_support: dict[str, list[str]] = {}
        for provider in providers:
            for binding in provider["bindings"]:
                supporters = ordered_support.setdefault(binding["canonical_model_id"], [])
                if provider["id"] not in supporters:
                    supporters.append(provider["id"])
        for model_id, supporters in ordered_support.items():
            if model_id in defaults:
                continue
            defaults[model_id] = active_id if active_id in supporters else supporters[0]
        return {
            "schema_version": 2,
            "codex_mode": _normalize_codex_mode(
                payload.get("codex_mode", current.get("codex_mode"))
            ),
            "active_provider_id": active_id,
            "default_provider_by_model": defaults,
            "providers": providers,
        }

    def _prepare_legacy_active_write(
        self, payload: Mapping[str, Any], current: Mapping[str, Any]
    ) -> dict[str, Any]:
        candidate = self._persisted(current)
        candidate["codex_mode"] = _normalize_codex_mode(
            payload.get("codex_mode", current.get("codex_mode"))
        )
        target_id = _normalize_slug(
            payload.get("active_provider_id") or current["active_provider_id"],
            fallback="default",
        )
        if not any(provider["id"] == target_id for provider in candidate["providers"]):
            target_id = candidate["providers"][0]["id"]
        candidate["active_provider_id"] = target_id
        legacy_provider_fields = {
            "name",
            "base_url",
            "api_key",
            "image_model",
            "api_mode",
            "images_concurrency",
        }
        if not legacy_provider_fields.intersection(payload):
            return candidate
        for provider in candidate["providers"]:
            if provider["id"] != target_id:
                continue
            if "name" in payload:
                provider["name"] = str(payload.get("name") or provider["id"]).strip() or provider["id"]
            if "base_url" in payload:
                provider["base_url"] = _normalize_legacy_base_url(payload.get("base_url"))
            if "api_key" in payload:
                provider["api_key"] = str(payload.get("api_key") or "").strip()
            if "images_concurrency" in payload:
                provider["concurrency"] = _normalize_legacy_concurrency(
                    payload.get("images_concurrency")
                )
            if "image_model" in payload or "api_mode" in payload:
                gpt_binding = next(
                    (
                        binding
                        for binding in provider["bindings"]
                        if binding["canonical_model_id"] == "gpt-image-2"
                    ),
                    None,
                )
                if gpt_binding is not None:
                    if "image_model" in payload:
                        gpt_binding["remote_model_id"] = _normalize_remote_model_id(
                            payload.get("image_model")
                        )
                    if "api_mode" in payload:
                        api_mode = _normalize_api_mode(payload.get("api_mode"))
                        gpt_binding["protocol_profile"] = (
                            "openai_responses" if api_mode == "responses" else "openai_images"
                        )
                        gpt_binding["parameter_codec"] = (
                            "gpt_openai_responses"
                            if api_mode == "responses"
                            else "gpt_openai_images"
                        )
            break
        if any(
            binding["canonical_model_id"] == "gpt-image-2"
            for provider in candidate["providers"]
            if provider["id"] == target_id
            for binding in provider["bindings"]
        ):
            candidate["default_provider_by_model"]["gpt-image-2"] = target_id
        return candidate

    @staticmethod
    def _apply_key_copy_semantics(
        providers: list[Any], current_by_id: Mapping[str, Mapping[str, Any]]
    ) -> list[Any]:
        prepared = deepcopy(providers)
        for provider in prepared:
            if not isinstance(provider, dict) or "api_key" in provider:
                continue
            provider_id = _normalize_slug(provider.get("id"), fallback="default")
            source_id = _normalize_slug(
                provider.pop("api_key_source_provider_id", None), fallback=""
            )
            source = current_by_id.get(source_id) or current_by_id.get(provider_id)
            provider["api_key"] = str((source or {}).get("api_key") or "")
        return prepared

    @classmethod
    def _validate_v2(cls, payload: Mapping[str, Any]) -> dict[str, Any]:
        return cls._project_legacy(validate_v2_payload(payload))

    @classmethod
    def _project_legacy(cls, settings: Mapping[str, Any]) -> dict[str, Any]:
        result = deepcopy(dict(settings))
        result["providers"] = [
            {**provider, **cls._legacy_provider_projection(provider)}
            for provider in result["providers"]
        ]
        active = cls._active_provider(result)
        result.update(cls._legacy_provider_projection(active))
        return result

    @staticmethod
    def _active_provider(settings: Mapping[str, Any]) -> dict[str, Any]:
        providers = settings["providers"]
        active_id = settings.get("active_provider_id")
        return next((provider for provider in providers if provider["id"] == active_id), providers[0])

    @staticmethod
    def _legacy_provider_projection(provider: Mapping[str, Any]) -> dict[str, Any]:
        binding = next(
            (
                item
                for item in provider["bindings"]
                if item["canonical_model_id"] == "gpt-image-2"
            ),
            provider["bindings"][0],
        )
        return {
            "id": provider["id"],
            "name": provider["name"],
            "base_url": provider["base_url"],
            "api_key": provider["api_key"],
            "image_model": binding["remote_model_id"],
            "api_mode": (
                "responses" if binding["protocol_profile"] == "openai_responses" else "images"
            ),
            "images_concurrency": provider["concurrency"],
        }

    @staticmethod
    def _persisted(settings: Mapping[str, Any]) -> dict[str, Any]:
        active = ProviderSettings._active_provider(settings)
        legacy = ProviderSettings._legacy_provider_projection(active)
        return {
            "schema_version": 2,
            "codex_mode": settings["codex_mode"],
            "active_provider_id": settings["active_provider_id"],
            "default_provider_by_model": deepcopy(settings["default_provider_by_model"]),
            "providers": deepcopy(settings["providers"]),
            "base_url": legacy["base_url"],
            "api_key": legacy["api_key"],
            "image_model": legacy["image_model"],
            "api_mode": legacy["api_mode"],
            "images_concurrency": legacy["images_concurrency"],
        }


ApiSettings = ProviderSettings


__all__ = (
    "ApiSettings",
    "ProviderSettings",
    "migrate_legacy_provider",
)
