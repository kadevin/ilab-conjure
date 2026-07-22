from __future__ import annotations

import json
from typing import Any

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response

from codex_image.webui.context import WebUIContext
from codex_image.webui.app_version import app_version_payload, dismiss_post_update_onboarding, open_portable_updater
from codex_image.webui.settings_store import (
    MAX_COLOR_IMPORT_BYTES,
    MAX_PROMPT_TEMPLATE_IMPORT_BYTES,
    _color_palette_css,
    _parse_color_palette_import,
)
from codex_image.webui.startup_auth import AUTH_SOURCES


def register_settings_routes(app: FastAPI, ctx: WebUIContext) -> None:
    h = ctx.route_helpers

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        auth_available = bool(ctx.auth_checker())
        queue_worker = getattr(app, "state", None) and getattr(app.state, "queue_worker_task", None)
        auth = h["auth_event_payload"]()
        return {
            "ok": True,
            "auth_available": auth_available,
            "auth": auth,
            "input_root": str(ctx.input_root),
            "output_root": str(ctx.output_root),
            "gallery_root": str(ctx.gallery_root),
            "source_data_root": str(ctx.source_data_root),
            "queue_worker_running": bool(queue_worker is not None and not queue_worker.done()),
            "network_egress": ctx.network_egress_manager.resolve().public_snapshot(),
        }

    @app.get("/api/app-version")
    def get_app_version() -> dict[str, Any]:
        return app_version_payload(ctx.output_root)

    @app.post("/api/app-version/open-updater")
    def open_app_updater() -> dict[str, Any]:
        try:
            return open_portable_updater(ctx.output_root)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/app-version/dismiss-onboarding")
    def dismiss_app_version_onboarding() -> dict[str, Any]:
        try:
            return dismiss_post_update_onboarding(ctx.output_root)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        return {
            "settings": {
                "input_root": str(ctx.input_root),
                "output_root": str(ctx.output_root),
                "gallery_root": str(ctx.gallery_root),
                "source_data_root": str(ctx.source_data_root),
                "locale": ctx.webui_settings.read_locale(),
            },
            "restart_required": False,
        }

    @app.patch("/api/settings")
    def update_settings(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        path_keys = {"input_root", "output_root", "gallery_root", "source_data_root"}
        restart_required = any(key in payload for key in path_keys)
        try:
            if restart_required:
                saved = ctx.webui_settings.write_paths(payload)
            else:
                saved = {
                    "input_root": ctx.input_root,
                    "output_root": ctx.output_root,
                    "gallery_root": ctx.gallery_root,
                    "source_data_root": ctx.source_data_root,
                }
            locale = ctx.webui_settings.write_locale(payload["locale"]) if "locale" in payload else ctx.webui_settings.read_locale()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        settings = {key: str(value) for key, value in saved.items()}
        settings["locale"] = locale
        return {"settings": settings, "restart_required": restart_required}

    @app.get("/api/color-palette")
    def get_color_palette() -> dict[str, Any]:
        return {"palette": ctx.color_settings.read(), "restart_required": False}

    @app.patch("/api/color-palette")
    def update_color_palette(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            saved = ctx.color_settings.write(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"palette": saved, "restart_required": False}

    @app.get("/api/color-palette/export.css")
    def export_color_palette_css() -> Response:
        return Response(
            _color_palette_css(ctx.color_settings.read()),
            media_type="text/css",
            headers={"Content-Disposition": 'attachment; filename="ilab-color-palette.css"'},
        )

    @app.post("/api/color-palette/import")
    async def import_color_palette(file: UploadFile = File(...)) -> dict[str, Any]:
        payload = await file.read(MAX_COLOR_IMPORT_BYTES + 1)
        if len(payload) > MAX_COLOR_IMPORT_BYTES:
            raise HTTPException(status_code=400, detail="Color palette file is too large")
        try:
            items = _parse_color_palette_import(file.filename or "palette", payload, file.content_type)
            saved, imported, skipped = ctx.color_settings.import_favorites(items)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"palette": saved, "imported": imported, "skipped": skipped, "restart_required": False}

    @app.get("/api/prompt-snippets")
    def get_prompt_snippets() -> dict[str, Any]:
        return {"snippets": ctx.prompt_snippet_settings.list(), "restart_required": False}

    @app.post("/api/prompt-snippets")
    def create_prompt_snippet(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            snippet = ctx.prompt_snippet_settings.create(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"snippet": snippet, "snippets": ctx.prompt_snippet_settings.list(), "restart_required": False}

    @app.patch("/api/prompt-snippets/{snippet_id}")
    def update_prompt_snippet(snippet_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            snippet = ctx.prompt_snippet_settings.update(snippet_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"snippet": snippet, "snippets": ctx.prompt_snippet_settings.list(), "restart_required": False}

    @app.delete("/api/prompt-snippets/{snippet_id}")
    def delete_prompt_snippet(snippet_id: str) -> dict[str, Any]:
        try:
            ctx.prompt_snippet_settings.delete(snippet_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"snippets": ctx.prompt_snippet_settings.list(), "restart_required": False}

    @app.get("/api/prompt-templates")
    def get_prompt_templates() -> dict[str, Any]:
        return {
            "templates": ctx.prompt_template_settings.list(),
            "categories": ctx.prompt_template_settings.list_categories(),
            "restart_required": False,
        }

    @app.post("/api/prompt-templates")
    def create_prompt_template(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            template = ctx.prompt_template_settings.create(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "template": template,
            "templates": ctx.prompt_template_settings.list(),
            "categories": ctx.prompt_template_settings.list_categories(),
            "restart_required": False,
        }

    @app.get("/api/prompt-templates/export.json")
    def export_prompt_templates() -> Response:
        return Response(
            json.dumps(ctx.prompt_template_settings.export_pack(), ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="webui-prompt-templates.json"'},
        )

    @app.post("/api/prompt-templates/import")
    async def import_prompt_templates(file: UploadFile = File(...)) -> dict[str, Any]:
        payload = await file.read(MAX_PROMPT_TEMPLATE_IMPORT_BYTES + 1)
        if len(payload) > MAX_PROMPT_TEMPLATE_IMPORT_BYTES:
            raise HTTPException(status_code=400, detail="Prompt template pack is too large")
        try:
            settings, imported, skipped = ctx.prompt_template_settings.import_pack(file.filename or "prompt-pack", payload, file.content_type)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "templates": settings["templates"],
            "categories": settings["categories"],
            "imported": imported,
            "skipped": skipped,
            "restart_required": False,
        }

    @app.patch("/api/prompt-templates/{template_id}")
    def update_prompt_template(template_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            template = ctx.prompt_template_settings.update(template_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "template": template,
            "templates": ctx.prompt_template_settings.list(),
            "categories": ctx.prompt_template_settings.list_categories(),
            "restart_required": False,
        }

    @app.post("/api/prompt-templates/{template_id}/use")
    def use_prompt_template(template_id: str) -> dict[str, Any]:
        try:
            template = ctx.prompt_template_settings.mark_used(template_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "template": template,
            "templates": ctx.prompt_template_settings.list(),
            "categories": ctx.prompt_template_settings.list_categories(),
            "restart_required": False,
        }

    @app.delete("/api/prompt-templates/{template_id}")
    def delete_prompt_template(template_id: str) -> dict[str, Any]:
        try:
            ctx.prompt_template_settings.delete(template_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "templates": ctx.prompt_template_settings.list(),
            "categories": ctx.prompt_template_settings.list_categories(),
            "restart_required": False,
        }

    @app.post("/api/prompt-template-categories")
    def create_prompt_template_category(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            category = ctx.prompt_template_settings.create_category(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "category": category,
            "templates": ctx.prompt_template_settings.list(),
            "categories": ctx.prompt_template_settings.list_categories(),
            "restart_required": False,
        }

    @app.patch("/api/prompt-template-categories/{category_id}")
    def update_prompt_template_category(category_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            category = ctx.prompt_template_settings.update_category(category_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "category": category,
            "templates": ctx.prompt_template_settings.list(),
            "categories": ctx.prompt_template_settings.list_categories(),
            "restart_required": False,
        }

    @app.delete("/api/prompt-template-categories/{category_id}")
    def delete_prompt_template_category(category_id: str) -> dict[str, Any]:
        try:
            settings = ctx.prompt_template_settings.delete_category(category_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"templates": settings["templates"], "categories": settings["categories"], "restart_required": False}

    @app.get("/api/auth")
    def get_auth() -> dict[str, Any]:
        return h["auth_status"](ctx.auth_settings.read_source())

    @app.patch("/api/auth")
    def update_auth(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        source = str(payload.get("source") or "").strip().lower()
        if source not in AUTH_SOURCES:
            raise HTTPException(status_code=400, detail="source must be codex or api")
        ctx.auth_settings.write_source(source)
        channels = h["queue_channels_for_source"](source)
        if ctx.queue_manager is not None:
            ctx.queue_manager.channels = channels
            ctx.queue_manager.max_attempts = h["queue_max_attempts_for_channels"](channels)
        return h["auth_status"](source)

    @app.get("/api/api-settings")
    def get_api_settings() -> dict[str, Any]:
        return {"settings": ctx.api_settings.public_settings()}

    @app.patch("/api/api-settings")
    def update_api_settings(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            ctx.api_settings.write(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if ctx.auth_settings.read_source() == "api" and ctx.queue_manager is not None:
            channels = h["queue_channels_for_source"]("api")
            ctx.queue_manager.channels = channels
            ctx.queue_manager.max_attempts = h["queue_max_attempts_for_channels"](channels)
        return {"settings": ctx.api_settings.public_settings()}

    @app.get("/api/network-egress")
    def get_network_egress() -> dict[str, Any]:
        return ctx.network_egress_manager.public_settings()

    @app.patch("/api/network-egress")
    def update_network_egress(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            ctx.network_egress_settings.write(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ctx.network_egress_manager.public_settings()

    @app.post("/api/network-egress/test")
    def test_network_egress(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        try:
            return ctx.network_egress_manager.probe(payload or None)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
