from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit, urlunsplit

from codex_image.generation import get_model_manifest
from codex_image.providers import capabilities as provider_capabilities

_OPERATIONS = frozenset({"generate", "edit"})
_EMOJI_JOINER = "\u200d"
_KEYCAP = "\u20e3"


def normalize_provider_icon_emoji(value: Any) -> str:
    icon = str(value or "").strip()
    if not icon:
        return ""
    if len(icon) > 16 or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in icon):
        raise ValueError("invalid_icon_emoji")

    symbol = lambda char: unicodedata.category(char) == "So"
    extender = lambda char: (
        unicodedata.category(char).startswith("M")
        or char in {"\ufe0e", "\ufe0f"}
        or 0x1F3FB <= ord(char) <= 0x1F3FF
        or 0xE0020 <= ord(char) <= 0xE007F
    )
    symbols = [char for char in icon if symbol(char)]
    if _KEYCAP in icon:
        keycap_bases = [char for char in icon if char in "#*0123456789"]
        if (
            len(keycap_bases) == 1
            and not symbols
            and all(char in keycap_bases or char == _KEYCAP or extender(char) for char in icon)
        ):
            return icon
        raise ValueError("invalid_icon_emoji")
    if not symbols or any(not (symbol(char) or extender(char) or char == _EMOJI_JOINER) for char in icon):
        raise ValueError("invalid_icon_emoji")

    regional_indicators = all(0x1F1E6 <= ord(char) <= 0x1F1FF for char in symbols)
    if regional_indicators:
        if len(symbols) == 2 and _EMOJI_JOINER not in icon:
            return icon
        raise ValueError("invalid_icon_emoji")
    if len(symbols) == 1 and _EMOJI_JOINER not in icon:
        return icon
    if (
        icon.count(_EMOJI_JOINER) >= len(symbols) - 1
        and not icon.startswith(_EMOJI_JOINER)
        and not icon.endswith(_EMOJI_JOINER)
        and _EMOJI_JOINER * 2 not in icon
    ):
        return icon
    raise ValueError("invalid_icon_emoji")


def normalize_slug(value: Any, *, fallback: str) -> str:
    raw = str(value or fallback).strip().lower()
    normalized = re.sub(r"[^a-z0-9_-]+", "-", raw).strip("-")
    return normalized or fallback


def normalize_remote_model_id(value: Any) -> str:
    model_id = str(value or "").strip()
    if not model_id:
        raise ValueError("invalid_remote_model_id")
    return model_id


def normalize_v2_base_url(value: Any) -> str:
    raw = str(value or "").strip()
    if any(ord(char) < 32 or ord(char) == 127 for char in raw):
        raise ValueError("invalid_base_url")
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid_base_url") from exc
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port is not None and not 1 <= port <= 65535
    ):
        raise ValueError("invalid_base_url")
    host = parsed.hostname.lower()
    decoded_host = unquote(host)
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in decoded_host):
        raise ValueError("invalid_base_url")
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = f"{host}:{port}" if port is not None else host
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


def normalize_v2_concurrency(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("invalid_concurrency")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_concurrency") from exc
    if parsed < 1 or parsed > 32:
        raise ValueError("invalid_concurrency")
    return parsed


def validate_v2_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != 2:
        raise ValueError("unsupported_schema_version")
    raw_providers = payload.get("providers")
    if not isinstance(raw_providers, list) or not raw_providers:
        raise ValueError("invalid_providers")
    providers: list[dict[str, Any]] = []
    provider_ids: set[str] = set()
    support: dict[str, set[str]] = {}
    for index, raw_provider in enumerate(raw_providers, start=1):
        if not isinstance(raw_provider, Mapping):
            raise ValueError("invalid_provider")
        provider = _validate_provider(raw_provider, index=index)
        provider_id = provider["id"]
        if provider_id == "codex":
            raise ValueError("codex_provider_not_allowed")
        if provider_id in provider_ids:
            raise ValueError("duplicate_provider_id")
        provider_ids.add(provider_id)
        providers.append(provider)
        for binding in provider["bindings"]:
            support.setdefault(binding["canonical_model_id"], set()).add(provider_id)
    raw_defaults = payload.get("default_provider_by_model")
    if not isinstance(raw_defaults, Mapping):
        raise ValueError("default_provider_mapping_missing")
    defaults = {
        str(model_id).strip(): normalize_slug(provider_id, fallback="")
        for model_id, provider_id in raw_defaults.items()
    }
    for model_id, provider_id in defaults.items():
        if model_id not in support or provider_id not in support[model_id]:
            raise ValueError("invalid_default_provider_mapping")
    for model_id, supporting_providers in support.items():
        if defaults.get(model_id) not in supporting_providers:
            raise ValueError("default_provider_mapping_missing")
    active_id = normalize_slug(
        payload.get("active_provider_id") or providers[0]["id"], fallback=providers[0]["id"]
    )
    if active_id not in provider_ids:
        active_id = providers[0]["id"]
    mode = str(payload.get("codex_mode") or "").strip().lower()
    return {
        "schema_version": 2,
        "codex_mode": mode if mode in {"images", "responses"} else "images",
        "active_provider_id": active_id,
        "default_provider_by_model": defaults,
        "providers": providers,
    }


def _validate_provider(raw: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    provider_id = normalize_slug(raw.get("id"), fallback=f"provider-{index}")
    name = str(raw.get("name") or provider_id).strip() or provider_id
    raw_bindings = raw.get("bindings")
    if not isinstance(raw_bindings, list) or not raw_bindings:
        raise ValueError("invalid_bindings")
    bindings: list[dict[str, Any]] = []
    binding_ids: set[str] = set()
    claims: set[tuple[str, str]] = set()
    for binding_index, raw_binding in enumerate(raw_bindings, start=1):
        if not isinstance(raw_binding, Mapping):
            raise ValueError("invalid_binding")
        binding = _validate_binding(raw_binding, fallback_id=f"{provider_id}-binding-{binding_index}")
        if binding["id"] in binding_ids:
            raise ValueError("duplicate_binding_id")
        binding_ids.add(binding["id"])
        for operation in binding["operations"]:
            claim = (binding["canonical_model_id"], operation)
            if claim in claims:
                raise ValueError("overlapping_binding")
            claims.add(claim)
        bindings.append(binding)
    provider = {
        "id": provider_id,
        "name": name,
        "base_url": normalize_v2_base_url(raw.get("base_url")),
        "api_key": str(raw.get("api_key") or "").strip(),
        "concurrency": normalize_v2_concurrency(raw.get("concurrency")),
        "bindings": bindings,
    }
    icon_emoji = normalize_provider_icon_emoji(raw.get("icon_emoji"))
    if icon_emoji:
        provider["icon_emoji"] = icon_emoji
    return provider


def _validate_binding(raw: Mapping[str, Any], *, fallback_id: str) -> dict[str, Any]:
    binding_id = normalize_slug(raw.get("id"), fallback=fallback_id)
    canonical_model_id = str(raw.get("canonical_model_id") or "").strip()
    try:
        manifest = get_model_manifest(canonical_model_id)
    except KeyError as exc:
        raise ValueError("unknown_canonical_model") from exc
    protocol = str(raw.get("protocol_profile") or "").strip()
    codec = str(raw.get("parameter_codec") or "").strip()
    pairs = frozenset(
        pair for pair in provider_capabilities.protocol_codec_pairs() if not pair[0].startswith("codex_")
    )
    if protocol not in {profile for profile, _codec in pairs}:
        raise ValueError("unknown_protocol_profile")
    if codec not in provider_capabilities.CODEC_CAPABILITIES:
        raise ValueError("unknown_parameter_codec")
    if (protocol, codec) not in pairs:
        raise ValueError("invalid_protocol_codec_pair")
    raw_operations = raw.get("operations")
    if not isinstance(raw_operations, (list, tuple, set, frozenset)):
        raise ValueError("invalid_operations")
    operations = frozenset(str(operation).strip() for operation in raw_operations)
    if not operations or not operations <= _OPERATIONS or not operations <= manifest.operations:
        raise ValueError("invalid_operations")
    required = {
        parameter.id
        for parameter in manifest.parameters
        if (
            parameter.scope == "model"
            and parameter.control != "notice"
            and parameter.operations & operations
        )
    }
    mapped = provider_capabilities.codec_capability(codec).mapped_parameter_ids
    missing = sorted(required - mapped)
    if missing:
        raise ValueError("codec_parameter_mapping_missing: " + ", ".join(missing))
    append_aspect_ratio_prompt = raw.get("append_aspect_ratio_prompt", False)
    if not isinstance(append_aspect_ratio_prompt, bool):
        raise ValueError("invalid_append_aspect_ratio_prompt")
    binding = {
        "id": binding_id,
        "canonical_model_id": canonical_model_id,
        "remote_model_id": normalize_remote_model_id(raw.get("remote_model_id")),
        "protocol_profile": protocol,
        "parameter_codec": codec,
        "operations": sorted(operations, key=("generate", "edit").index),
    }
    if append_aspect_ratio_prompt:
        binding["append_aspect_ratio_prompt"] = True
    return binding


__all__ = (
    "normalize_remote_model_id",
    "normalize_provider_icon_emoji",
    "normalize_slug",
    "normalize_v2_base_url",
    "normalize_v2_concurrency",
    "validate_v2_payload",
)
