from __future__ import annotations

from fastapi import FastAPI

from codex_image.webui.context import WebUIContext

from .gallery import register_gallery_routes
from .network_egress import register_network_egress_routes
from .generation_catalog import register_generation_catalog_routes
from .generation import register_generation_routes
from .history import register_history_routes
from .history_backup import register_history_backup_routes
from .media import register_media_routes
from .queue import register_queue_routes
from .reference_files import register_reference_file_routes
from .settings import register_settings_routes
from .tasks import register_task_routes
from .user_config_backup import register_user_config_backup_routes


def register_webui_routes(app: FastAPI, ctx: WebUIContext) -> None:
    register_settings_routes(app, ctx)
    register_network_egress_routes(app, ctx)
    register_media_routes(app, ctx)
    register_task_routes(app, ctx)
    register_history_routes(app, ctx)
    register_history_backup_routes(app, ctx)
    register_user_config_backup_routes(app, ctx)
    register_queue_routes(app, ctx)
    register_gallery_routes(app, ctx)
    register_reference_file_routes(app, ctx)
    register_generation_catalog_routes(app, ctx)
    register_generation_routes(app, ctx)
