from __future__ import annotations

import json
from typing import Any

from codex_image.auth import load_auth_state
from codex_image.client import CodexImageClient, CodexImagesImageClient, OpenAIImagesImageClient, OpenAIResponsesImageClient
from codex_image.http import Transport

from . import executor as _executor
from .queue import QueueChannel
from .schemas import DEFAULT_WEBUI_API_SETTINGS_PATH
from .settings_store import ApiSettings
from .startup_auth import AUTH_SOURCES, detect_startup_auth_source
from .storage import TaskStorage
from .task_metadata import _apply_api_images_concurrency_metadata

API_MODES = {"images", "responses"}
DEFAULT_API_MODE = "images"
CODEX_MODES = {"images", "responses"}
DEFAULT_CODEX_MODE = "images"
DEFAULT_API_PROVIDER_ID = "default"
DEFAULT_API_IMAGES_CONCURRENCY = 4
MIN_API_IMAGES_CONCURRENCY = 1
MAX_API_IMAGES_CONCURRENCY = 32
BACKEND_CODEX_IMAGES = "codex_images"
BACKEND_CODEX_RESPONSES = "codex_responses"
BACKEND_OPENAI_RESPONSES = "openai_responses"
BACKEND_OPENAI_IMAGES = "openai_images"


def _normalize_api_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in API_MODES else DEFAULT_API_MODE


def _normalize_codex_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in CODEX_MODES else DEFAULT_CODEX_MODE


def _normalize_api_images_concurrency(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_API_IMAGES_CONCURRENCY
    return min(MAX_API_IMAGES_CONCURRENCY, max(MIN_API_IMAGES_CONCURRENCY, parsed))


def _api_client_from_settings(
    settings: dict[str, Any],
    *,
    api_mode: str | None = None,
    transport: Transport | None = None,
) -> Any:
    mode = _normalize_api_mode(api_mode or settings.get("api_mode"))
    client_class = OpenAIResponsesImageClient if mode == "responses" else OpenAIImagesImageClient
    if mode == "images":
        _executor.OpenAIImagesImageClient = OpenAIImagesImageClient
    else:
        _executor.OpenAIResponsesImageClient = OpenAIResponsesImageClient
    return client_class(
        api_key=str(settings["api_key"]),
        base_url=str(settings["base_url"]),
        image_model=str(settings["image_model"]),
        transport=transport,
    )


def _backend_for_api_mode(api_mode: Any) -> str:
    return BACKEND_OPENAI_RESPONSES if _normalize_api_mode(api_mode) == "responses" else BACKEND_OPENAI_IMAGES


def _backend_for_codex_mode(codex_mode: Any) -> str:
    return BACKEND_CODEX_RESPONSES if _normalize_codex_mode(codex_mode) == "responses" else BACKEND_CODEX_IMAGES


def _codex_mode_for_task_metadata(metadata: dict[str, Any] | None, api_settings: ApiSettings | None = None) -> str:
    params = metadata.get("params") if isinstance(metadata, dict) and isinstance(metadata.get("params"), dict) else {}
    if params.get("codex_mode") is not None:
        return _normalize_codex_mode(params.get("codex_mode"))
    backend = str(
        (metadata or {}).get("requested_backend")
        or (metadata or {}).get("backend")
        or ""
    ).strip()
    if backend == BACKEND_CODEX_RESPONSES:
        return "responses"
    if backend == BACKEND_CODEX_IMAGES:
        return "images"
    settings_mode = api_settings.read().get("codex_mode") if api_settings is not None else DEFAULT_CODEX_MODE
    return _normalize_codex_mode(settings_mode)


def _backend_for_queue_channel(
    channel: QueueChannel,
    metadata: dict[str, Any] | None = None,
    *,
    api_settings: ApiSettings | None = None,
) -> str:
    if channel.auth_source == "api":
        params = metadata.get("params") if isinstance(metadata, dict) and isinstance(metadata.get("params"), dict) else {}
        if api_settings is not None:
            settings = api_settings.read()
            provider = api_settings.provider_settings(str(params.get("api_provider_id") or settings.get("active_provider_id") or ""))
            settings_mode = provider.get("api_mode")
        else:
            settings_mode = DEFAULT_API_MODE
        return _backend_for_api_mode(params.get("api_mode") or settings_mode)
    return _backend_for_codex_mode(_codex_mode_for_task_metadata(metadata, api_settings))


def _backend_for_submit(auth_source: str, api_mode: str | None, codex_mode: str | None = None) -> str:
    return _backend_for_api_mode(api_mode) if auth_source == "api" else _backend_for_codex_mode(codex_mode)


def _request_api_provider_id(auth_source: str, api_provider_id: str | None, api_settings: ApiSettings) -> str | None:
    if auth_source != "api":
        return None
    settings = api_settings.read()
    provider = api_settings.provider_settings(api_provider_id or str(settings.get("active_provider_id") or ""))
    return str(provider["id"])


def _request_api_provider_name(auth_source: str, api_provider_id: str | None, api_settings: ApiSettings) -> str | None:
    if auth_source != "api":
        return None
    provider = api_settings.provider_settings(api_provider_id)
    return str(provider.get("name") or provider.get("id") or "").strip() or None


def _request_api_mode(auth_source: str, api_mode: str | None, api_settings: ApiSettings, api_provider_id: str | None = None) -> str | None:
    if auth_source != "api":
        return None
    if api_mode is not None and str(api_mode).strip():
        return _normalize_api_mode(api_mode)
    provider = api_settings.provider_settings(api_provider_id)
    return _normalize_api_mode(provider.get("api_mode"))


def _request_codex_mode(auth_source: str, codex_mode: str | None, api_settings: ApiSettings) -> str | None:
    if auth_source != "codex":
        return None
    if codex_mode is not None and str(codex_mode).strip():
        return _normalize_codex_mode(codex_mode)
    return _normalize_codex_mode(api_settings.read().get("codex_mode"))


def _request_api_images_concurrency(auth_source: str, api_settings: ApiSettings, api_provider_id: str | None = None) -> int:
    if auth_source != "api":
        return DEFAULT_API_IMAGES_CONCURRENCY
    provider = api_settings.provider_settings(api_provider_id)
    return _normalize_api_images_concurrency(provider.get("images_concurrency"))


def _task_metadata_uses_api(metadata: dict[str, Any]) -> bool:
    params = metadata.get("params") if isinstance(metadata.get("params"), dict) else {}
    return (
        str(metadata.get("assigned_auth_source") or "") == "api"
        or bool(metadata.get("api_provider_id"))
        or bool(params.get("api_provider_id"))
    )


def _apply_retry_api_provider(
    storage: TaskStorage,
    task_id: str,
    metadata: dict[str, Any],
    api_settings: ApiSettings,
    api_provider_id: str | None = None,
) -> None:
    if not _task_metadata_uses_api(metadata):
        return
    provider_id = _request_api_provider_id("api", api_provider_id, api_settings)
    provider_name = _request_api_provider_name("api", provider_id, api_settings)
    api_mode = _request_api_mode("api", None, api_settings, provider_id)
    params = dict(metadata.get("params") or {})
    params["api_provider_id"] = provider_id
    params["api_mode"] = api_mode
    if provider_name:
        params["api_provider_name"] = provider_name
    else:
        params.pop("api_provider_name", None)
    params["api_images_concurrency"] = _request_api_images_concurrency("api", api_settings, provider_id)
    metadata["params"] = params
    metadata["requested_backend"] = _backend_for_submit("api", api_mode)
    metadata["api_provider_id"] = provider_id
    if provider_name:
        metadata["api_provider_name"] = provider_name
    else:
        metadata.pop("api_provider_name", None)
    _apply_api_images_concurrency_metadata(metadata, params)
    _update_stored_request_api_provider(storage, task_id, params)


def _apply_api_execution_snapshot(
    storage: TaskStorage,
    task_id: str,
    metadata: dict[str, Any],
    api_settings: ApiSettings,
    api_provider_id: str | None = None,
) -> None:
    settings = api_settings.read()
    existing_params = metadata.get("params") if isinstance(metadata.get("params"), dict) else {}
    provider = api_settings.provider_settings(
        api_provider_id
        or str(existing_params.get("api_provider_id") or "")
        or str(settings.get("active_provider_id") or "")
    )
    provider_id = str(provider["id"])
    provider_name = str(existing_params.get("api_provider_name") or provider.get("name") or "")
    api_mode = _normalize_api_mode(existing_params.get("api_mode") or provider.get("api_mode"))
    params = dict(existing_params)
    params["api_provider_id"] = provider_id
    params["api_mode"] = api_mode
    params["api_images_concurrency"] = _normalize_api_images_concurrency(
        existing_params.get("api_images_concurrency") or provider.get("images_concurrency")
    )
    if provider_name:
        params["api_provider_name"] = provider_name
    else:
        params.pop("api_provider_name", None)
    metadata["params"] = params
    metadata["api_provider_id"] = provider_id
    if provider_name:
        metadata["api_provider_name"] = provider_name
    else:
        metadata.pop("api_provider_name", None)
    metadata["backend"] = _backend_for_api_mode(api_mode)
    _apply_api_images_concurrency_metadata(metadata, params)
    _update_stored_request_api_provider(storage, task_id, params)


def _update_stored_request_api_provider(storage: TaskStorage, task_id: str, params: dict[str, Any]) -> None:
    try:
        request_payload = json.loads(storage.request_path(task_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(request_payload, dict):
        return
    api_mode = _normalize_api_mode(params.get("api_mode"))
    request_payload["webui_requested_backend"] = _backend_for_api_mode(api_mode)
    request_payload["webui_api_provider_id"] = params.get("api_provider_id")
    if params.get("api_provider_name"):
        request_payload["webui_api_provider_name"] = params.get("api_provider_name")
    else:
        request_payload.pop("webui_api_provider_name", None)
    if params.get("api_images_concurrency") is not None:
        request_payload["webui_api_images_concurrency"] = _normalize_api_images_concurrency(params.get("api_images_concurrency"))
    else:
        request_payload.pop("webui_api_images_concurrency", None)
    storage.write_request(task_id, request_payload)


def _client_for_auth_source(
    source: str,
    *,
    api_settings: ApiSettings | None = None,
    codex_mode: str | None = None,
    transport: Transport | None = None,
) -> Any:
    normalized = source if source in AUTH_SOURCES else _default_auth_source()
    if normalized == "api":
        settings = (api_settings or ApiSettings(DEFAULT_WEBUI_API_SETTINGS_PATH)).read()
        provider = (api_settings or ApiSettings(DEFAULT_WEBUI_API_SETTINGS_PATH)).provider_settings(str(settings.get("active_provider_id") or ""))
        return _api_client_from_settings(
            provider,
            api_mode=str(provider.get("api_mode") or DEFAULT_API_MODE),
            transport=transport,
        )
    settings = (api_settings or ApiSettings(DEFAULT_WEBUI_API_SETTINGS_PATH)).read()
    mode = _normalize_codex_mode(codex_mode or settings.get("codex_mode"))
    client_class = CodexImageClient if mode == "responses" else CodexImagesImageClient
    return client_class(load_auth_state(), transport=transport)


def _api_queue_channel_count(api_settings: ApiSettings | None = None) -> int:
    if api_settings is None:
        return DEFAULT_API_IMAGES_CONCURRENCY
    settings = api_settings.read()
    provider = api_settings.provider_settings(str(settings.get("active_provider_id") or ""))
    return _normalize_api_images_concurrency(provider.get("images_concurrency"))


def _queue_channels_for_source(source: str, *, api_settings: ApiSettings | None = None) -> list[QueueChannel]:
    if source == "api":
        return [
            QueueChannel(channel_id=f"api:default:{index}", auth_source="api", account_id=None)
            for index in range(1, _api_queue_channel_count(api_settings) + 1)
        ]
    return [QueueChannel(channel_id="codex:local", auth_source="codex", account_id=None)]


def _auth_status(source: str, *, api_settings: ApiSettings | None = None) -> dict[str, Any]:
    selected = source if source in AUTH_SOURCES else _default_auth_source()
    codex_available = _codex_auth_available()
    api_public = (api_settings or ApiSettings(DEFAULT_WEBUI_API_SETTINGS_PATH)).public_settings()
    api_available = bool(api_public["base_url"] and api_public["api_key_set"])

    effective_source = ""
    auth_available = False
    if selected == "codex":
        effective_source = "codex" if codex_available else ""
        auth_available = codex_available
    elif selected == "api":
        effective_source = "api" if api_available else ""
        auth_available = api_available

    return {
        "selected_source": selected,
        "effective_source": effective_source,
        "auth_available": auth_available,
        "sources": {
            "codex": {
                "available": codex_available,
                "mode": api_public.get("codex_mode", DEFAULT_CODEX_MODE),
            },
            "api": {
                **api_public,
                "available": api_available,
            },
        },
    }


def _codex_auth_available() -> bool:
    try:
        state = load_auth_state()
    except Exception:
        return False
    return bool(state.access_token)


def _default_auth_source() -> str:
    return detect_startup_auth_source()
