from __future__ import annotations

import base64
from io import BytesIO
import json
import mimetypes
import re
import zipfile
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlsplit

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from codex_image.client import (
    DEFAULT_IMAGE_MODEL,
    DEFAULT_MAIN_MODEL,
    CodexImageClient,
    CodexImagesImageClient,
    ImageResult,
    OpenAIImagesImageClient,
    OpenAIResponsesImageClient,
    image_model_supports_input_fidelity,
)
from codex_image.prompt_guard import (
    build_guarded_prompt,
    build_original_prompt_instructions,
    build_prompt_guard_instructions,
    extract_prompt_constraints,
)

from .auth_routing import (
    API_MODES,
    AUTH_SOURCES,
    BACKEND_CODEX_IMAGES,
    BACKEND_CODEX_RESPONSES,
    BACKEND_OPENAI_IMAGES,
    BACKEND_OPENAI_RESPONSES,
    DEFAULT_API_IMAGES_CONCURRENCY,
    DEFAULT_API_MODE,
    MAX_API_IMAGES_CONCURRENCY,
    MIN_API_IMAGES_CONCURRENCY,
    _api_queue_channel_count,
    _apply_retry_api_provider,
    _auth_status,
    _backend_for_api_mode,
    _backend_for_submit,
    _client_for_auth_source,
    _codex_auth_available,
    _default_auth_source,
    _normalize_api_mode,
    _normalize_codex_mode,
    _queue_channels_for_source,
    _request_api_images_concurrency,
    _request_api_mode,
    _request_api_provider_id,
    _request_api_provider_name,
    _request_codex_mode,
    _task_metadata_uses_api,
    _update_stored_request_api_provider,
)
from .queue_runtime import (
    _client_for_queue_channel,
    _ensure_queue_worker_running,
    _queue_channel_available,
    _queue_channel_worker_loop,
    _queue_max_attempts_for_channels,
    _queue_worker_loop,
    execute_task,
    install_queue_runtime,
    queue_lifespan,
)
from .network_egress import NetworkEgressManager, NetworkEgressSettings
from .recovery import (
    _disk_output_paths,
    _is_legacy_auto_retry_queue_task,
    _materialize_orphaned_running_failure,
    _migrate_legacy_gallery_directory,
    _migrate_legacy_inputs,
    _migrate_legacy_mask,
    _migrate_legacy_outputs,
    _migrate_legacy_task_directories,
    _output_index_from_path,
    _prune_duplicate_request_payloads,
    _prune_missing_queue_tasks,
    _recover_completed_outputs_from_disk,
    _recover_queue_state,
    _recoverable_total_count,
)
from .schemas import (
    DEFAULT_WEBUI_AUTH_SETTINGS_PATH,
    DEFAULT_WEBUI_API_SETTINGS_PATH,
    DEFAULT_WEBUI_NETWORK_EGRESS_SETTINGS_PATH,
    DEFAULT_WEBUI_COLOR_SETTINGS_PATH,
    DEFAULT_WEBUI_GALLERY_SUBDIR,
    DEFAULT_WEBUI_OUTPUT_ROOT,
    DEFAULT_WEBUI_PROMPT_SNIPPETS_PATH,
    DEFAULT_WEBUI_PROMPT_TEMPLATES_PATH,
    DEFAULT_WEBUI_REFERENCE_ASSET_SUBDIR,
    DEFAULT_WEBUI_REFERENCE_FILE_SUBDIR,
    DEFAULT_WEBUI_SETTINGS_PATH,
    DEFAULT_WEBUI_SOURCE_DATA_SUBDIR,
)
from .storage import GalleryStorage, QueueStorage, ReferenceAssetStorage, SQLiteQueueStorage, TaskStorage, _guess_mime_type, utc_now
from .reference_files import ReferenceFileStorage
from .settings_store import (
    ApiSettings,
    AuthSettings,
    ColorPaletteSettings,
    MAX_COLOR_IMPORT_BYTES,
    PromptSnippetSettings,
    PromptTemplateSettings,
    WebUISettings,
    _color_palette_css,
    _mask_api_key,
    _parse_color_palette_import,
)
from .context import WebUIContext
from .events import event_key, event_snapshot, queue_snapshot, queued_or_running_task_ids, sse_message, task_event
from .routes import register_webui_routes
from .executor import (
    _call_image_client,
    _debug_sse_path,
    _direct_images_concurrent_enabled,
    _file_to_data_url,
    _image_mime_type,
    _image_request_timeout_seconds,
    _instructions_for_transport,
    _normalize_compression,
    _normalize_prompt_fidelity,
    _noop_request_context,
    _parse_optional_int,
    _prompt_for_transport,
    _raise_if_task_cancelled,
    _restore_completed_output_progress,
    _resolve_gallery_refs,
    _resolve_reference_assets,
    _sniff_image_mime_type,
)
from .task_metadata import (
    _accept_partial_task_successes,
    _append_output_record_state,
    _api_images_concurrency_metadata_value,
    _apply_api_provider_metadata,
    _complete_task,
    _completed_output_records_for_accept,
    _dedupe_preserve_order,
    _downloadable_output_paths,
    _enrich_gallery_refs,
    _enrich_reference_assets,
    _fail_task,
    _finalize_generated_task,
    _gallery_category_response,
    _gallery_item_response,
    _gallery_ref_response,
    _infer_gallery_refs_from_prompt,
    _input_sources,
    _input_urls,
    _ordered_output_progress,
    _output_file_from_url,
    _output_url,
    _params,
    _partial_failure_message,
    _positive_int,
    _reference_asset_response,
    _retryable_failed_output_indexes,
    _with_file_urls,
    _write_progress_metadata,
    _write_queued_metadata,
    _write_running_metadata,
)

ClientFactory = Callable[[], Any]
AuthChecker = Callable[[], bool]
DEFAULT_IMAGE_REQUEST_TIMEOUT_SECONDS = 600.0
EVENT_STREAM_CHECK_INTERVAL_SECONDS = 1.0
PROMPT_FIDELITY_MODES = {"strict", "original", "off"}
DEFAULT_PROMPT_FIDELITY = "strict"


class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: dict[str, Any]) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response


def create_app(
    *,
    input_root: Path | str | None = None,
    output_root: Path | str = DEFAULT_WEBUI_OUTPUT_ROOT,
    gallery_root: Path | str | None = None,
    reference_asset_root: Path | str | None = None,
    reference_file_root: Path | str | None = None,
    source_data_root: Path | str | None = None,
    client_factory: ClientFactory | None = None,
    auth_checker: AuthChecker | None = None,
    static_dir: Path | str | None = None,
    batch_delay_seconds: float = 5.0,
    auth_settings_path: Path | str = DEFAULT_WEBUI_AUTH_SETTINGS_PATH,
    api_settings_path: Path | str = DEFAULT_WEBUI_API_SETTINGS_PATH,
    network_egress_settings_path: Path | str = DEFAULT_WEBUI_NETWORK_EGRESS_SETTINGS_PATH,
    color_settings_path: Path | str = DEFAULT_WEBUI_COLOR_SETTINGS_PATH,
    prompt_snippets_path: Path | str = DEFAULT_WEBUI_PROMPT_SNIPPETS_PATH,
    prompt_templates_path: Path | str = DEFAULT_WEBUI_PROMPT_TEMPLATES_PATH,
    webui_settings_path: Path | str = DEFAULT_WEBUI_SETTINGS_PATH,
    queue_path: Path | str | None = None,
    auto_start_queue: bool = True,
    auto_retry: bool = False,
) -> FastAPI:
    settings = WebUISettings(Path(webui_settings_path))
    configured_paths = settings.read_paths()
    custom_output = Path(output_root) != DEFAULT_WEBUI_OUTPUT_ROOT
    output_path = Path(output_root) if custom_output else configured_paths["output_root"]
    input_path = Path(input_root) if input_root is not None else (output_path / "inputs" if custom_output else configured_paths["input_root"])
    gallery_path = Path(gallery_root) if gallery_root is not None else (input_path / DEFAULT_WEBUI_GALLERY_SUBDIR if custom_output else configured_paths["gallery_root"])
    reference_asset_path = Path(reference_asset_root) if reference_asset_root is not None else input_path / DEFAULT_WEBUI_REFERENCE_ASSET_SUBDIR
    reference_file_path = Path(reference_file_root) if reference_file_root is not None else input_path / DEFAULT_WEBUI_REFERENCE_FILE_SUBDIR
    source_data_path = (
        Path(source_data_root)
        if source_data_root is not None
        else (output_path / DEFAULT_WEBUI_SOURCE_DATA_SUBDIR if custom_output else configured_paths["source_data_root"])
    )
    storage = TaskStorage(output_path, input_root=input_path, source_data_root=source_data_path)
    _migrate_legacy_gallery_directory(gallery_path, [Path("output") / "webui-gallery"])
    gallery_storage = GalleryStorage(gallery_path)
    reference_asset_storage = ReferenceAssetStorage(reference_asset_path)
    reference_file_storage = ReferenceFileStorage(reference_file_path)
    queue_storage = (
        QueueStorage(Path(queue_path))
        if queue_path is not None
        else SQLiteQueueStorage(source_data_path / "webui.db", legacy_json_path=source_data_path / "webui-queue.json")
    )
    _migrate_legacy_task_directories(storage, [Path("output") / "webui", Path(output_root)])
    _prune_duplicate_request_payloads(storage)
    _prune_missing_queue_tasks(queue_storage, storage)
    _recover_queue_state(storage, queue_storage)
    auth_settings = AuthSettings(Path(auth_settings_path))
    api_settings = ApiSettings(Path(api_settings_path))
    network_egress_settings = NetworkEgressSettings(Path(network_egress_settings_path))
    network_egress_manager = NetworkEgressManager(network_egress_settings)
    color_settings = ColorPaletteSettings(Path(color_settings_path))
    prompt_snippet_settings = PromptSnippetSettings(Path(prompt_snippets_path))
    prompt_template_settings = PromptTemplateSettings(Path(prompt_templates_path))
    static_path = Path(static_dir) if static_dir is not None else Path(__file__).parent / "static"
    make_client = client_factory or (
        lambda: _client_for_auth_source(
            auth_settings.read_source(),
            api_settings=api_settings,
            transport=network_egress_manager.transport(),
        )
    )
    check_auth = auth_checker or (lambda: bool(_auth_status(auth_settings.read_source(), api_settings=api_settings)["auth_available"]))

    app = FastAPI(title="iLab GPT CONJURE", lifespan=queue_lifespan)
    ctx = WebUIContext(
        app=app,
        storage=storage,
        gallery_storage=gallery_storage,
        reference_asset_storage=reference_asset_storage,
        reference_file_storage=reference_file_storage,
        queue_storage=queue_storage,
        webui_settings=settings,
        auth_settings=auth_settings,
        api_settings=api_settings,
        network_egress_settings=network_egress_settings,
        network_egress_manager=network_egress_manager,
        color_settings=color_settings,
        prompt_snippet_settings=prompt_snippet_settings,
        prompt_template_settings=prompt_template_settings,
        client_factory=make_client,
        auth_checker=check_auth,
        input_root=input_path,
        output_root=output_path,
        gallery_root=gallery_path,
        reference_asset_root=reference_asset_path,
        reference_file_root=reference_file_path,
        source_data_root=source_data_path,
        auto_start_queue=auto_start_queue,
    )
    ctx.install_on_app_state()

    queue_runtime = install_queue_runtime(
        ctx,
        batch_delay_seconds=batch_delay_seconds,
        auto_retry=auto_retry,
        client_factory_overridden=client_factory is not None,
    )
    app.mount("/inputs", StaticFiles(directory=input_path, check_dir=False), name="inputs")
    app.mount("/outputs", StaticFiles(directory=output_path, check_dir=False), name="outputs")
    app.mount("/static", NoCacheStaticFiles(directory=static_path, check_dir=False), name="static")

    @app.get("/", response_model=None)
    def index() -> Response:
        index_path = static_path / "index.html"
        if index_path.exists():
            return FileResponse(index_path, headers={"Cache-Control": "no-store"})
        return HTMLResponse(
            "<!doctype html><title>iLab GPT CONJURE</title><h1>iLab GPT CONJURE</h1>",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/history", response_model=None)
    def history() -> Response:
        history_path = static_path / "history.html"
        if history_path.exists():
            return FileResponse(history_path, headers={"Cache-Control": "no-store"})
        return HTMLResponse(
            "<!doctype html><title>History - iLab GPT CONJURE</title><h1>History</h1>",
            headers={"Cache-Control": "no-store"},
        )

    @app.api_route("/manifest.webmanifest", methods=["GET", "HEAD"], response_model=None)
    def web_app_manifest() -> Response:
        manifest_path = static_path / "manifest.webmanifest"
        if manifest_path.exists():
            return FileResponse(
                manifest_path,
                media_type="application/manifest+json",
                headers={"Cache-Control": "no-store"},
            )
        raise HTTPException(status_code=404, detail="Web app manifest not found")

    @app.api_route("/service-worker.js", methods=["GET", "HEAD"], response_model=None)
    def service_worker() -> Response:
        worker_path = static_path / "service-worker.js"
        if worker_path.exists():
            return FileResponse(
                worker_path,
                media_type="text/javascript",
                headers={"Cache-Control": "no-store", "Service-Worker-Allowed": "/"},
            )
        raise HTTPException(status_code=404, detail="Service worker not found")

    ctx.route_helpers.update(
        {
            "ensure_queue_worker_running": queue_runtime.ensure_queue_worker_running,
            "queue_channel_available": queue_runtime.queue_channel_available,
            "auth_status": lambda source: _auth_status(source, api_settings=api_settings),
            "auth_event_payload": lambda: (
                _auth_status(auth_settings.read_source(), api_settings=api_settings)
                if auth_checker is None
                else {"auth_available": bool(check_auth())}
            ),
            "queue_channels_for_source": lambda source: _queue_channels_for_source(source, api_settings=api_settings),
            "queue_max_attempts_for_channels": _queue_max_attempts_for_channels,
            "visible_running_task_ids": lambda: _visible_running_task_ids(app.state.active_task_ids, queue_storage),
            "queue_has_running_task": lambda task_id: _queue_has_running_task(queue_storage, task_id),
            "running_channel_for_task": lambda task_id: _running_channel_for_task(queue_storage, task_id),
            "with_stored_request_payload": lambda task_id, metadata: _with_stored_request_payload(storage, task_id, metadata),
            "set_task_archived": lambda task_id, archived: _set_task_archived(storage, task_id, archived),
            "mark_task_cancelled": lambda task_id: _mark_task_cancelled(storage, task_id),
            "materialize_orphaned_running_failure": lambda task_id, metadata: _materialize_orphaned_running_failure(storage, task_id, metadata),
            "apply_retry_api_provider": lambda task_id, metadata, api_provider_id=None: _apply_retry_api_provider(
                storage, task_id, metadata, api_settings, api_provider_id
            ),
            "save_uploads": lambda task_id, files, kind="input": _save_uploads(storage, task_id, files, kind=kind),
            "save_reference_assets": lambda files: _save_reference_assets(reference_asset_storage, files),
            "dedupe_reference_assets": _dedupe_reference_assets,
            "build_image_request_payload": lambda **kwargs: _build_image_request_payload(**kwargs),
            "slim_request_payload": lambda request_payload, **kwargs: _slim_request_payload(request_payload, **kwargs),
            "prompt_guard_context": lambda prompt, prompt_fidelity: _prompt_guard_context(prompt, prompt_fidelity),
            "model_prompt_for_fidelity": lambda prompt, prompt_for_model, prompt_fidelity: _model_prompt_for_fidelity(
                prompt, prompt_for_model, prompt_fidelity
            ),
            "backend_for_submit": _backend_for_submit,
            "request_api_provider_id": lambda auth_source, api_provider_id: _request_api_provider_id(
                auth_source, api_provider_id, api_settings
            ),
            "request_api_provider_name": lambda auth_source, api_provider_id: _request_api_provider_name(
                auth_source, api_provider_id, api_settings
            ),
            "request_api_mode": lambda auth_source, api_mode, api_provider_id=None: _request_api_mode(
                auth_source, api_mode, api_settings, api_provider_id
            ),
            "request_codex_mode": lambda auth_source, codex_mode=None: _request_codex_mode(
                auth_source, codex_mode, api_settings
            ),
            "request_api_images_concurrency": lambda auth_source, api_provider_id=None: _request_api_images_concurrency(
                auth_source, api_settings, api_provider_id
            ),
            "client_factory_overridden": client_factory is not None,
        }
    )
    register_webui_routes(app, ctx)

    return app


def _default_client_factory() -> CodexImageClient:
    return _client_for_auth_source(_default_auth_source())


def _default_auth_checker() -> bool:
    return bool(_auth_status(_default_auth_source())["auth_available"])


def _queue_has_running_task(queue_storage: QueueStorage, task_id: str) -> bool:
    return _running_channel_for_task(queue_storage, task_id) is not None


def _running_channel_for_task(queue_storage: QueueStorage, task_id: str) -> str | None:
    running = queue_storage.read_state()["running"]
    for channel_id, item in running.items():
        if isinstance(item, dict) and str(item.get("task_id") or "") == task_id:
            return str(channel_id)
    return None


def _visible_running_task_ids(active_task_ids: set[str], queue_storage: QueueStorage) -> set[str]:
    visible = {str(task_id) for task_id in active_task_ids}
    for item in queue_storage.read_state()["running"].values():
        if isinstance(item, dict) and item.get("task_id"):
            visible.add(str(item["task_id"]))
    return visible


def _with_stored_request_payload(storage: TaskStorage, task_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
    if isinstance(metadata.get("request"), dict):
        return metadata
    request_path = storage.request_path(task_id)
    try:
        request_payload = json.loads(request_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return metadata
    if not isinstance(request_payload, dict):
        return metadata
    enriched = dict(metadata)
    enriched["request"] = request_payload
    return enriched


def _prompt_guard_context(prompt: str, prompt_fidelity: str) -> tuple[list[str], str]:
    mode = _normalize_prompt_fidelity(prompt_fidelity)
    if mode == "original":
        return [], build_original_prompt_instructions()
    if mode != "strict":
        return [], ""
    constraints = extract_prompt_constraints(prompt)
    return constraints, build_prompt_guard_instructions(constraints)


def _model_prompt_for_fidelity(prompt: str, prompt_for_model: str | None, prompt_fidelity: str) -> str:
    if _normalize_prompt_fidelity(prompt_fidelity) == "original":
        return prompt
    return prompt_for_model or prompt


def _build_image_request_payload(**kwargs: Any) -> dict[str, Any]:
    auth_source = str(kwargs.pop("auth_source", "auto"))
    api_mode = _normalize_api_mode(kwargs.pop("api_mode", None))
    codex_mode = _normalize_codex_mode(kwargs.pop("codex_mode", None))
    # Queued submit only needs a request preview; avoid auth/client side effects.
    if auth_source == "api":
        client_class = OpenAIResponsesImageClient if api_mode == "responses" else OpenAIImagesImageClient
        client = object.__new__(client_class)
        client.image_model = str(kwargs.get("model") or DEFAULT_IMAGE_MODEL)
        return client_class.build_payload(client, **kwargs)
    client_class = CodexImageClient if codex_mode == "responses" else CodexImagesImageClient
    client = object.__new__(client_class)
    if client_class is CodexImagesImageClient:
        client.image_model = str(kwargs.get("model") or DEFAULT_IMAGE_MODEL)
    return client_class.build_payload(client, **kwargs)


def _slim_request_payload(
    request_payload: dict[str, Any],
    *,
    input_files: list[str],
    gallery_refs: list[dict[str, Any]],
    reference_assets: list[dict[str, Any]],
    reference_files: list[dict[str, Any]] | None = None,
    mask_file: str | None = None,
) -> dict[str, Any]:
    slim = _redact_request_data(request_payload)
    if isinstance(slim, dict):
        refs: dict[str, Any] = {
            "input_files": list(input_files),
            "gallery_refs": gallery_refs,
            "reference_assets": reference_assets,
        }
        if mask_file:
            refs["mask_file"] = mask_file
        slim["webui_image_refs"] = refs
        slim["webui_file_refs"] = {
            "reference_files": reference_files or [],
        }
    return slim if isinstance(slim, dict) else {}


def _redact_request_data(value: Any, *, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {
            str(item_key): _redact_request_data(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_request_data(item) for item in value]
    if isinstance(value, str) and (key == "file_data" or re.match(r"^data:[^;,]+;base64,", value)):
        label = "image data url" if value.startswith("data:image/") else "data url"
        return f"<redacted {label}, {len(value)} chars>"
    return value


async def _save_uploads(storage: TaskStorage, task_id: str, files: list[UploadFile], *, kind: str = "input") -> list[Path]:
    saved: list[Path] = []
    for index, upload in enumerate(files, start=1):
        data = await upload.read()
        if not data:
            continue
        if upload.content_type and not upload.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail=f"Unsupported image type: {upload.content_type}")
        saved.append(storage.write_input(task_id, upload.filename or "image.png", data, kind=kind, index=index))
    return saved


async def _save_reference_assets(storage: ReferenceAssetStorage, files: list[UploadFile]) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for upload in files:
        data = await upload.read()
        if not data:
            continue
        mime_type = _image_mime_type(upload.content_type, upload.filename or "image.png", data)
        if upload.content_type and not upload.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail=f"Unsupported image type: {upload.content_type}")
        if mime_type is None:
            raise HTTPException(status_code=400, detail=f"Unsupported image type: {upload.content_type or 'application/octet-stream'}")
        item = storage.create_or_touch(upload.filename or "image.png", data, mime_type)
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        assets.append(_reference_asset_response(item))
    return assets


def _dedupe_reference_assets(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        asset_id = str(item.get("id") or "")
        if not asset_id or asset_id in seen:
            continue
        seen.add(asset_id)
        result.append(item)
    return result


def _set_task_archived(storage: TaskStorage, task_id: str, archived: bool) -> dict[str, Any]:
    metadata = storage.read_metadata(task_id)
    if archived:
        metadata["archived_at"] = str(metadata.get("archived_at") or utc_now())
    else:
        metadata.pop("archived_at", None)
    storage.write_metadata(task_id, metadata)
    return metadata


def _mark_task_cancelled(storage: TaskStorage, task_id: str) -> dict[str, Any]:
    metadata = storage.read_metadata(task_id)
    cancelled_at = utc_now()
    metadata.update(
        {
            "status": "failed",
            "updated_at": cancelled_at,
            "cancelled_at": cancelled_at,
            "cancel_requested": True,
            "error": "Task cancelled by user.",
            "last_error": "Task cancelled by user.",
        }
    )
    metadata.pop("request", None)
    storage.write_metadata(task_id, metadata)
    return metadata


app = create_app()
