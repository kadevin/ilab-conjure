from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fastapi import Body, FastAPI, HTTPException

from codex_image.client_types import DEFAULT_CODEX_IMAGES_BASE_URL
from codex_image.webui.context import WebUIContext

NETWORK_EGRESS_TEST_TIMEOUT_SECONDS = 10.0


def _origin(value: Any) -> str:
    try:
        parsed = urlsplit(str(value or "").strip())
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Configured provider origin is invalid") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Configured provider origin is invalid")
    hostname = parsed.hostname
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = hostname if port is None else f"{hostname}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, "", "", ""))


def _probe_target(
    ctx: WebUIContext,
    provider_id: Any = None,
) -> tuple[str, str]:
    selected_provider_id = str(provider_id or "").strip()
    if selected_provider_id == "codex":
        return "codex", _origin(DEFAULT_CODEX_IMAGES_BASE_URL)

    settings = ctx.api_settings.read()
    if selected_provider_id:
        provider = next(
            (
                item
                for item in settings.get("providers", [])
                if str(item.get("id") or "") == selected_provider_id
            ),
            None,
        )
        if provider is None:
            raise ValueError("Selected provider is unavailable")
        return selected_provider_id, _origin(provider.get("base_url"))

    if ctx.auth_settings.read_source() != "api":
        return "codex", _origin(DEFAULT_CODEX_IMAGES_BASE_URL)
    active_provider_id = str(settings.get("active_provider_id") or "")
    provider = ctx.api_settings.provider_settings(active_provider_id)
    return active_provider_id, _origin(provider.get("base_url"))


def _settings_payload(ctx: WebUIContext) -> dict[str, Any]:
    settings = ctx.network_egress_settings.read()
    snapshot = ctx.network_egress_manager.snapshot()
    return {
        "settings": settings,
        "resolved": {
            "mode": snapshot.mode,
            "route": snapshot.route,
            "image_request_timeout_seconds": (
                snapshot.image_request_timeout_seconds
            ),
            "image_request_retry_count": snapshot.image_request_retry_count,
            "image_request_timeout_source": (
                snapshot.image_request_timeout_source
            ),
        },
        "restart_required": False,
    }


def register_network_egress_routes(app: FastAPI, ctx: WebUIContext) -> None:
    @app.get("/api/network-egress")
    def get_network_egress() -> dict[str, Any]:
        return _settings_payload(ctx)

    @app.patch("/api/network-egress")
    def update_network_egress(
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        try:
            ctx.network_egress_settings.write(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _settings_payload(ctx)

    @app.post("/api/network-egress/test")
    def test_network_egress(
        payload: dict[str, Any] = Body(default={}),
    ) -> dict[str, Any]:
        try:
            snapshot = ctx.network_egress_manager.snapshot(
                payload if "mode" in payload or "custom_proxy_url" in payload else None
            )
            transport = ctx.network_egress_manager.transport(
                snapshot,
                timeout_seconds=NETWORK_EGRESS_TEST_TIMEOUT_SECONDS,
            )
            provider_id, target = _probe_target(ctx, payload.get("provider_id"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        started_at = time.monotonic()
        try:
            response = transport.request(
                method="HEAD",
                url=target,
                headers={"Accept": "*/*"},
                body=b"",
            )
        except Exception as exc:
            return {
                "ok": False,
                "provider_id": provider_id,
                "target": target,
                "elapsed_ms": round((time.monotonic() - started_at) * 1_000),
                "error": type(exc).__name__,
                "resolved": {
                    "mode": snapshot.mode,
                    "route": snapshot.route,
                },
            }
        return {
            "ok": True,
            "provider_id": provider_id,
            "target": target,
            "elapsed_ms": round((time.monotonic() - started_at) * 1_000),
            "status_code": response.status,
            "resolved": {
                "mode": snapshot.mode,
                "route": snapshot.route,
            },
        }


__all__ = ("register_network_egress_routes",)
