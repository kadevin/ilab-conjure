from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any
import zipfile

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse

from codex_image.webui.context import WebUIContext
from codex_image.webui.events import generation_page_payload
from codex_image.webui.resource_limits import (
    MAX_TASK_ARCHIVE_INPUT_BYTES,
)
from codex_image.webui.storage import utc_now
from codex_image.webui.task_metadata import (
    _accept_partial_task_successes,
    _delete_unselected_task_outputs,
    _downloadable_output_paths,
    _output_record_filename,
    _output_thumbnail_fields,
    _retryable_failed_output_indexes,
    _safe_output_path,
    _set_task_output_selected,
    _visible_completed_output_records,
    _with_file_urls,
)
from codex_image.webui.thumbnails import create_image_thumbnail, thumbnail_needs_refresh
from .history import organization_payload


class TaskArchiveTooLargeError(ValueError):
    pass


class OneTimeTaskArchiveResponse(FileResponse):
    def __init__(self, path: Path, *, filename: str) -> None:
        self._archive_path = path
        super().__init__(
            path,
            media_type="application/zip",
            filename=filename,
        )

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._archive_path.unlink(missing_ok=True)


def _write_task_output_archive(
    *,
    task_id: str,
    output_paths: list[Path],
    temp_root: Path,
    max_input_bytes: int = MAX_TASK_ARCHIVE_INPUT_BYTES,
) -> Path:
    total_size = 0
    for path in output_paths:
        total_size += path.stat().st_size
        if total_size > max_input_bytes:
            raise TaskArchiveTooLargeError(
                "Task archive input exceeds the configured limit"
            )

    descriptor, temporary_name = tempfile.mkstemp(
        prefix="ilab-conjure-task-output-",
        suffix=".zip",
        dir=temp_root,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        copied_size = 0
        with zipfile.ZipFile(
            temporary_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            used_names: set[str] = set()
            for index, path in enumerate(output_paths, start=1):
                archive_name = path.name
                if archive_name in used_names:
                    archive_name = (
                        f"{task_id}-image-{index}{path.suffix}"
                    )
                used_names.add(archive_name)
                with path.open("rb") as source, archive.open(
                    archive_name,
                    mode="w",
                    force_zip64=True,
                ) as destination:
                    while chunk := source.read(1024 * 1024):
                        copied_size += len(chunk)
                        if copied_size > max_input_bytes:
                            raise TaskArchiveTooLargeError(
                                "Task archive input exceeds the configured limit"
                            )
                        destination.write(chunk)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return temporary_path


def register_task_routes(app: FastAPI, ctx: WebUIContext) -> None:
    h = ctx.route_helpers

    @app.get("/api/tasks")
    def list_tasks() -> dict[str, Any]:
        active_ids = h["visible_running_task_ids"]()
        return {
            "tasks": [
                _with_file_urls(
                    task,
                    active_ids,
                    ctx.gallery_storage,
                    ctx.reference_asset_storage,
                    ctx.reference_file_storage,
                    include_request=False,
                )
                for task in ctx.storage.list_tasks()
            ]
        }

    @app.get("/api/tasks/recent")
    def list_recent_tasks(limit: int = Query(200, ge=1, le=500)) -> dict[str, Any]:
        tasks = ctx.storage.list_recent_task_cards(limit=limit)
        tasks_by_id = {str(task.get("task_id") or ""): task for task in tasks}
        queue_state = ctx.queue_storage.read_state()
        active_ids = [
            *[str(task_id) for task_id in queue_state.get("waiting", []) if task_id],
            *[str(item.get("task_id")) for item in queue_state.get("running", {}).values() if isinstance(item, dict) and item.get("task_id")],
        ]
        for task_id in active_ids:
            if task_id in tasks_by_id:
                continue
            try:
                task = ctx.storage.task_sidebar_card(task_id)
            except (FileNotFoundError, ValueError):
                continue
            tasks_by_id[task_id] = task
            tasks.append(task)
        return {"tasks": tasks}

    @app.get("/api/tasks/sidebar")
    def list_sidebar_tasks(limit: int = Query(50, ge=1, le=100)) -> dict[str, Any]:
        with app.state.state_sync_clock.capture() as sync:
            return {**generation_page_payload(ctx, limit_per_group=limit), "sync": sync}

    @app.get("/api/tasks/sidebar/groups/{group_key}")
    def list_sidebar_task_group(
        group_key: str,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        status: str = Query(""),
        prompt_mode: str = Query(""),
        ratio: str = Query(""),
        orientation: str = Query(""),
        resolution: str = Query(""),
    ) -> dict[str, Any]:
        try:
            return ctx.storage.generation_sidebar_group(
                group_key,
                offset=offset,
                limit=limit,
                status=status,
                prompt_mode=prompt_mode,
                ratio=ratio,
                orientation=orientation,
                resolution=resolution,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Task group not found") from exc

    @app.get("/api/tasks/sidebar/groups/{group_key}/selection")
    def select_sidebar_task_group(
        group_key: str,
        status: str = Query(""),
        prompt_mode: str = Query(""),
        ratio: str = Query(""),
        orientation: str = Query(""),
        resolution: str = Query(""),
    ) -> dict[str, Any]:
        try:
            result = ctx.storage.generation_sidebar_group_task_ids(
                group_key,
                status=status,
                prompt_mode=prompt_mode,
                ratio=ratio,
                orientation=orientation,
                resolution=resolution,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Task group not found") from exc
        if result.get("truncated"):
            raise HTTPException(status_code=409, detail="Too many matching tasks; narrow the filters first")
        return result

    @app.get("/api/tasks/sidebar/groups/{group_key}/position/{task_id}")
    def locate_sidebar_task_group_position(group_key: str, task_id: str) -> dict[str, Any]:
        try:
            return ctx.storage.generation_sidebar_group_task_position(group_key, task_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Task group not found") from exc

    @app.post("/api/tasks/delete-batch")
    def delete_tasks_batch(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        raw_ids = payload.get("task_ids")
        if not isinstance(raw_ids, list):
            raise HTTPException(status_code=400, detail="task_ids must be a list")
        task_ids = list(dict.fromkeys(str(task_id or "").strip() for task_id in raw_ids if str(task_id or "").strip()))
        if not task_ids:
            raise HTTPException(status_code=400, detail="At least one task id is required")
        if len(task_ids) > 5000:
            raise HTTPException(status_code=400, detail="At most 5000 tasks can be deleted at once")

        deleted: list[str] = []
        skipped: list[str] = []
        failed: list[str] = []
        for task_id in task_ids:
            if task_id in ctx.active_task_ids or h["queue_has_running_task"](task_id):
                skipped.append(task_id)
                continue
            try:
                ctx.storage.delete_task(task_id)
                ctx.queue_storage.remove_waiting(task_id)
                deleted.append(task_id)
            except (FileNotFoundError, ValueError, OSError):
                failed.append(task_id)
        return {"deleted": deleted, "skipped": skipped, "failed": failed}

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, Any]:
        try:
            metadata = h["with_stored_request_payload"](task_id, ctx.storage.read_metadata(task_id))
            return {
                "task": _with_file_urls(
                    metadata,
                    h["visible_running_task_ids"](),
                    ctx.gallery_storage,
                    ctx.reference_asset_storage,
                    ctx.reference_file_storage,
                ),
                "organization": organization_payload(
                    ctx.storage.history_organizations([task_id])[
                        task_id
                    ]
                ),
            }
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc

    @app.patch("/api/tasks/{task_id}/viewed")
    def mark_task_viewed(task_id: str) -> dict[str, Any]:
        try:
            metadata = ctx.storage.read_metadata(task_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        metadata["viewed_at"] = utc_now()
        ctx.storage.write_metadata(task_id, metadata)
        return {
            "task": _with_file_urls(
                metadata,
                h["visible_running_task_ids"](),
                ctx.gallery_storage,
                ctx.reference_asset_storage,
                ctx.reference_file_storage,
                include_request=False,
            )
        }

    @app.get("/api/tasks/{task_id}/outputs.zip")
    def download_task_outputs_zip(
        task_id: str,
        selected: bool = Query(False),
    ) -> OneTimeTaskArchiveResponse:
        try:
            metadata = ctx.storage.read_metadata(task_id)
            output_paths = _downloadable_output_paths(ctx.storage, metadata, selected_only=selected)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        if len(output_paths) < 2:
            detail = "Task has fewer than two selected outputs" if selected else "Task has fewer than two downloadable outputs"
            raise HTTPException(status_code=400, detail=detail)

        try:
            archive_path = _write_task_output_archive(
                task_id=task_id,
                output_paths=output_paths,
                temp_root=ctx.history_export_service.temp_root,
                max_input_bytes=MAX_TASK_ARCHIVE_INPUT_BYTES,
            )
        except TaskArchiveTooLargeError as exc:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "task_archive_too_large",
                    "message": "The task outputs are too large to archive.",
                    "max_input_bytes": MAX_TASK_ARCHIVE_INPUT_BYTES,
                },
            ) from exc
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail="Task output not found",
            ) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail="Task archive could not be created",
            ) from exc
        try:
            return OneTimeTaskArchiveResponse(
                archive_path,
                filename=f"{task_id}-images.zip",
            )
        except Exception:
            archive_path.unlink(missing_ok=True)
            raise

    @app.post("/api/tasks/{task_id}/reveal-output")
    def reveal_task_output_directory(task_id: str, request: Request) -> dict[str, Any]:
        if request.headers.get("x-requested-with") != "codex-image-webui":
            raise HTTPException(status_code=403, detail="WebUI request header required")
        try:
            metadata = ctx.storage.read_metadata(task_id)
            output_paths = _downloadable_output_paths(ctx.storage, metadata, selected_only=False)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        if not output_paths:
            raise HTTPException(status_code=409, detail="Task has no local output files")
        output_directory = output_paths[0].parent
        try:
            _open_path_in_file_manager(output_directory)
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Could not open output directory") from exc
        return {"ok": True, "path": str(output_directory)}

    @app.get("/api/tasks/{task_id}/inputs/{input_index}/thumbnail")
    def get_task_input_thumbnail(task_id: str, input_index: int) -> FileResponse:
        try:
            metadata = ctx.storage.read_metadata(task_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        if input_index < 1:
            raise HTTPException(status_code=404, detail="Input not found")

        input_files = metadata.get("input_files") if isinstance(metadata.get("input_files"), list) else []
        if input_index > len(input_files):
            raise HTTPException(status_code=404, detail="Input not found")
        input_path = ctx.storage.input_path(str(input_files[input_index - 1]))
        if not input_path.is_file():
            raise HTTPException(status_code=404, detail="Input not found")

        thumbnail_path = ctx.storage.input_thumbnail_path(task_id, input_index)
        if thumbnail_needs_refresh(input_path, thumbnail_path):
            create_image_thumbnail(input_path, thumbnail_path)
        if not thumbnail_path.exists():
            raise HTTPException(status_code=404, detail="Thumbnail unavailable")
        return FileResponse(
            thumbnail_path,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    @app.get("/api/tasks/{task_id}/outputs/{output_index}/thumbnail")
    def get_task_output_thumbnail(task_id: str, output_index: int) -> FileResponse:
        try:
            metadata = ctx.storage.read_metadata(task_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        if output_index < 1:
            raise HTTPException(status_code=404, detail="Output not found")

        records = _visible_completed_output_records(metadata)
        record = next((item for item in records if item.get("index") == output_index), None)
        if record is None:
            raise HTTPException(status_code=404, detail="Output not found")
        output_path = _safe_output_path(ctx.storage, task_id, _output_record_filename(record))
        if output_path is None or not output_path.is_file():
            raise HTTPException(status_code=404, detail="Output not found")

        fields = _output_thumbnail_fields(ctx.storage, task_id, output_index, output_path)
        thumbnail_file = fields.get("thumbnail_file")
        if not thumbnail_file:
            raise HTTPException(status_code=404, detail="Thumbnail unavailable")
        thumbnail_path = ctx.storage.output_path(thumbnail_file)
        return FileResponse(
            thumbnail_path,
            media_type="image/webp" if thumbnail_path.suffix == ".webp" else "image/jpeg",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    @app.get("/api/tasks/{task_id}/outputs/{output_index}/sidebar-thumbnail")
    def get_task_output_sidebar_thumbnail(task_id: str, output_index: int) -> FileResponse:
        try:
            metadata = ctx.storage.read_metadata(task_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        if output_index < 1:
            raise HTTPException(status_code=404, detail="Output not found")

        records = _visible_completed_output_records(metadata)
        record = next((item for item in records if item.get("index") == output_index), None)
        if record is None:
            raise HTTPException(status_code=404, detail="Output not found")
        output_path = _safe_output_path(ctx.storage, task_id, _output_record_filename(record))
        if output_path is None or not output_path.is_file():
            raise HTTPException(status_code=404, detail="Output not found")

        fields = _output_thumbnail_fields(ctx.storage, task_id, output_index, output_path)
        thumbnail_file = fields.get("sidebar_thumbnail_file")
        if not thumbnail_file:
            raise HTTPException(status_code=404, detail="Thumbnail unavailable")
        thumbnail_path = ctx.storage.output_path(thumbnail_file)
        return FileResponse(
            thumbnail_path,
            media_type="image/webp",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    @app.patch("/api/tasks/{task_id}/outputs/{output_index}/selected")
    def update_task_output_selection(task_id: str, output_index: int, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            metadata = ctx.storage.read_metadata(task_id)
            _ensure_outputs_mutable(task_id, metadata)
            metadata = _set_task_output_selected(ctx.storage, task_id, metadata, output_index, bool(payload.get("selected")))
            return {
                "task": _with_file_urls(
                    metadata,
                    h["visible_running_task_ids"](),
                    ctx.gallery_storage,
                    ctx.reference_asset_storage,
                    ctx.reference_file_storage,
                )
            }
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/tasks/{task_id}/outputs/delete-unselected")
    def delete_unselected_task_outputs(task_id: str) -> dict[str, Any]:
        try:
            metadata = ctx.storage.read_metadata(task_id)
            _ensure_outputs_mutable(task_id, metadata)
            metadata = _delete_unselected_task_outputs(ctx.storage, task_id, metadata)
            return {
                "task": _with_file_urls(
                    metadata,
                    h["visible_running_task_ids"](),
                    ctx.gallery_storage,
                    ctx.reference_asset_storage,
                    ctx.reference_file_storage,
                )
            }
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.patch("/api/tasks/{task_id}/archive")
    def update_task_archive(task_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            metadata = h["set_task_archived"](task_id, bool(payload.get("archived")))
            return {
                "task": _with_file_urls(
                    metadata,
                    h["visible_running_task_ids"](),
                    ctx.gallery_storage,
                    ctx.reference_asset_storage,
                    ctx.reference_file_storage,
                )
            }
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc

    @app.post("/api/tasks/{task_id}/retry-failed")
    def retry_failed_task(task_id: str, payload: dict[str, Any] | None = Body(None)) -> dict[str, Any]:
        try:
            metadata = ctx.storage.read_metadata(task_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        if h["queue_has_running_task"](task_id) or task_id in ctx.active_task_ids:
            raise HTTPException(status_code=409, detail="Running task cannot be retried")
        if task_id in ctx.queue_storage.read_state()["waiting"]:
            raise HTTPException(status_code=409, detail="Task is already queued")
        metadata = h["materialize_orphaned_running_failure"](task_id, metadata)
        if metadata.get("status") not in {"failed", "partial_failed"}:
            raise HTTPException(status_code=409, detail="Only failed tasks can retry failed image slots")

        retry_slots = _retryable_failed_output_indexes(metadata)
        if not retry_slots:
            raise HTTPException(status_code=409, detail="No retryable failed image slots")

        now = utc_now()
        metadata["status"] = "queued"
        metadata["queued_at"] = now
        metadata["updated_at"] = now
        metadata["attempts"] = 0
        metadata["max_attempts"] = ctx.queue_manager.max_attempts if ctx.queue_manager is not None else 1
        metadata["retrying_failed_slots"] = retry_slots
        metadata["retry_failed_slots"] = retry_slots
        metadata["retry_requested_at"] = now
        metadata["error"] = ""
        h["apply_retry_api_provider"](task_id, metadata, str((payload or {}).get("api_provider_id") or "").strip() or None)
        ctx.storage.write_metadata(task_id, metadata)
        if ctx.queue_manager is not None:
            ctx.queue_manager.attempts.pop(task_id, None)
            ctx.queue_manager.failed_channels.pop(task_id, None)
        ctx.queue_storage.enqueue(task_id)
        if ctx.queue_manager is not None:
            snapshot = (
                metadata.get("generation_snapshot")
                if isinstance(metadata.get("generation_snapshot"), dict)
                else {}
            )
            source = (
                "codex"
                if str(snapshot.get("provider_id") or "") == "codex"
                else "api"
            )
            channels = h["queue_channels_for_source"](source)
            ctx.queue_manager.channels = channels
            ctx.queue_manager.max_attempts = h["queue_max_attempts_for_channels"](
                channels
            )
        h["wake_queue_worker"]()
        return {
            "task": _with_file_urls(
                metadata,
                h["visible_running_task_ids"](),
                ctx.gallery_storage,
                ctx.reference_asset_storage,
                ctx.reference_file_storage,
            )
        }

    @app.post("/api/tasks/{task_id}/accept-successes")
    def accept_task_successes(task_id: str) -> dict[str, Any]:
        try:
            metadata = ctx.storage.read_metadata(task_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        if h["queue_has_running_task"](task_id) or task_id in ctx.active_task_ids:
            raise HTTPException(status_code=409, detail="Running task cannot be accepted")
        if task_id in ctx.queue_storage.read_state()["waiting"]:
            raise HTTPException(status_code=409, detail="Queued task cannot be accepted")
        metadata = h["materialize_orphaned_running_failure"](task_id, metadata)
        if metadata.get("status") not in {"failed", "partial_failed"}:
            raise HTTPException(status_code=409, detail="Only failed tasks can accept successful outputs")

        try:
            metadata = _accept_partial_task_successes(ctx.storage, task_id, metadata)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "task": _with_file_urls(
                metadata,
                h["visible_running_task_ids"](),
                ctx.gallery_storage,
                ctx.reference_asset_storage,
                ctx.reference_file_storage,
            )
        }

    @app.delete("/api/tasks/{task_id}")
    def delete_task(task_id: str) -> dict[str, Any]:
        if task_id in ctx.active_task_ids or h["queue_has_running_task"](task_id):
            raise HTTPException(status_code=409, detail="Running task cannot be deleted")
        try:
            ctx.storage.delete_task(task_id)
            ctx.queue_storage.remove_waiting(task_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        return {"ok": True, "task_id": task_id}

    def _ensure_outputs_mutable(task_id: str, metadata: dict[str, Any]) -> None:
        if task_id in ctx.active_task_ids or h["queue_has_running_task"](task_id):
            raise ValueError("Running task outputs cannot be changed")
        if task_id in ctx.queue_storage.read_state()["waiting"]:
            raise ValueError("Queued task outputs cannot be changed")
        if metadata.get("status") in {"running", "submitting", "queued"}:
            raise ValueError("Unfinished task outputs cannot be changed")


def _open_path_in_file_manager(path: Path) -> None:
    target = path.resolve(strict=False)
    if sys.platform == "darwin":
        command = ["open", str(target)]
    elif sys.platform.startswith("win"):
        command = ["explorer", str(target)]
    else:
        command = ["xdg-open", str(target)]
    subprocess.Popen(command)
