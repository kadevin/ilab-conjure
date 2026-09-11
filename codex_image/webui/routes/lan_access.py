from __future__ import annotations

from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request

from codex_image.webui.context import WebUIContext
from codex_image.webui.lan_access import LanAccessRuntime, lan_ipv4_addresses


def register_lan_access_routes(app: FastAPI, ctx: WebUIContext) -> None:
    def response_payload(request: Request) -> dict[str, Any]:
        runtime: LanAccessRuntime = app.state.lan_access
        enabled = ctx.webui_settings.read_lan_access_enabled()
        host = runtime.host or runtime.default_host
        port = runtime.port or request.url.port or 80
        addresses = lan_ipv4_addresses() if enabled or runtime.active else []
        if runtime.active and runtime.host and runtime.host not in {"0.0.0.0", "::"}:
            addresses = [address for address in addresses if address == runtime.host]
        return {
            "enabled": enabled,
            "active": runtime.active,
            "restart_required": enabled != runtime.active,
            "listen_host": host,
            "host_override": enabled and runtime.enabled and not runtime.active,
            "addresses": [f"http://{address}:{port}/" for address in addresses],
        }

    @app.get("/api/lan-access")
    def get_lan_access(request: Request) -> dict[str, Any]:
        return response_payload(request)

    @app.patch("/api/lan-access")
    def update_lan_access(
        request: Request,
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        try:
            ctx.webui_settings.write_lan_access_enabled(payload.get("enabled"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return response_payload(request)
