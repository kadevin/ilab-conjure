from __future__ import annotations

from dataclasses import asdict
import json
import re
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from codex_image.webui.context import WebUIContext
from codex_image.webui.user_config_backup_components import ClientPreferences
from codex_image.webui.resource_limits import USER_CONFIG_BACKUP_UPLOAD_CHUNK_BYTES


_CONTROL_JSON_BYTES = 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class _ExactModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class NotificationPreferencesPayload(_ExactModel):
    in_app: bool
    system: bool


class ClientPreferencesPayload(_ExactModel):
    theme: Literal["system", "light", "dark"]
    notifications: NotificationPreferencesPayload

    def to_domain(self) -> ClientPreferences:
        return ClientPreferences(
            self.theme,
            self.notifications.in_app,
            self.notifications.system,
        )


class CreateUserConfigBackupRequest(_ExactModel):
    sections: list[Literal["chips", "gallery", "templates", "settings"]]
    include_api_keys: bool = False
    client_preferences: ClientPreferencesPayload | None = None

    @field_validator("sections")
    @classmethod
    def validate_sections(cls, values: list[str]) -> list[str]:
        if not values or len(values) != len(set(values)):
            raise ValueError("user_config_backup_sections_invalid")
        return values

    @model_validator(mode="after")
    def validate_options(self) -> CreateUserConfigBackupRequest:
        settings_selected = "settings" in self.sections
        if settings_selected != (self.client_preferences is not None):
            raise ValueError("user_config_backup_client_preferences_invalid")
        if self.include_api_keys and not settings_selected:
            raise ValueError("user_config_backup_include_api_keys_invalid")
        return self


class CreateUserConfigRestoreRequest(_ExactModel):
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)


class ApplyUserConfigRestoreRequest(_ExactModel):
    sections: list[Literal["chips", "gallery", "templates", "settings"]]
    mode: Literal["incremental", "replace"]
    archive_sha256: str
    preview_revision: str
    confirm_replace: bool = False

    @field_validator("sections")
    @classmethod
    def validate_sections(cls, values: list[str]) -> list[str]:
        if not values or len(values) != len(set(values)):
            raise ValueError("user_config_restore_sections_invalid")
        return values

    @field_validator("archive_sha256", "preview_revision")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if _SHA256_RE.fullmatch(value) is None:
            raise ValueError("user_config_restore_digest_invalid")
        return value


def register_user_config_backup_routes(app: FastAPI, ctx: WebUIContext) -> None:
    @app.get("/api/user-config-backups/summary")
    def get_user_config_backup_summary() -> dict[str, Any]:
        try:
            summaries = ctx.user_config_backup_planner.summary()
        except (ValueError, OSError) as exc:
            raise _service_http_error(exc) from None
        return {"sections": [asdict(summary) for summary in summaries]}

    @app.post("/api/user-config-backups")
    async def create_user_config_backup(request: Request) -> dict[str, Any]:
        payload = await _validated_json_body(
            request,
            CreateUserConfigBackupRequest,
        )
        _require_accepting(ctx)
        try:
            job = ctx.user_config_backup_export_service.create(
                payload.sections,
                payload.include_api_keys,
                (
                    payload.client_preferences.to_domain()
                    if payload.client_preferences is not None
                    else None
                ),
            )
        except (ValueError, OSError) as exc:
            raise _service_http_error(exc) from None
        return {"job": _job_payload(job)}

    @app.get("/api/user-config-backups/{job_id}")
    def get_user_config_backup(job_id: str) -> dict[str, Any]:
        job = ctx.user_config_backup_export_service.get(job_id)
        if job is None:
            raise _safe_http_error(404, "user_config_backup_not_found")
        return {"job": _job_payload(job)}

    @app.delete("/api/user-config-backups/{job_id}")
    def cancel_user_config_backup(job_id: str) -> dict[str, Any]:
        job = ctx.user_config_backup_export_service.get(job_id)
        if job is None:
            raise _safe_http_error(404, "user_config_backup_not_found")
        try:
            if ctx.user_config_backup_export_service.cancel(job_id):
                current = ctx.user_config_backup_export_service.get(job_id)
                return {"job": _job_payload(current or job)}
            discarded = ctx.user_config_backup_export_service.discard(job_id)
        except (ValueError, OSError) as exc:
            raise _service_http_error(exc) from None
        if discarded is None:
            raise _safe_http_error(409, "user_config_backup_lifecycle_conflict")
        return {"job": _job_payload(discarded)}

    @app.get("/api/user-config-backups/{job_id}/download", response_model=None)
    def download_user_config_backup(job_id: str) -> FileResponse:
        job = ctx.user_config_backup_export_service.get(job_id)
        if job is None:
            raise _safe_http_error(404, "user_config_backup_not_found")
        try:
            path = ctx.user_config_backup_export_service.download_path(job_id)
            return FileResponse(
                path,
                media_type="application/zip",
                filename=job.filename or "ilab-conjure-user-config.zip",
                headers={"cache-control": "no-store", "pragma": "no-cache"},
            )
        except (ValueError, OSError) as exc:
            raise _service_http_error(exc) from None

    @app.post("/api/user-config-restores")
    async def create_user_config_restore(request: Request) -> dict[str, Any]:
        payload = await _validated_json_body(
            request,
            CreateUserConfigRestoreRequest,
        )
        _require_accepting(ctx)
        try:
            session = ctx.user_config_backup_import_service.create(
                payload.filename,
                payload.size_bytes,
            )
        except (ValueError, OSError) as exc:
            raise _service_http_error(exc) from None
        return {
            "session": asdict(session),
            "upload_chunk_bytes": USER_CONFIG_BACKUP_UPLOAD_CHUNK_BYTES,
        }

    @app.put("/api/user-config-restores/{session_id}/chunks")
    async def append_user_config_restore_chunk(
        session_id: str,
        request: Request,
    ) -> dict[str, Any]:
        _require_accepting(ctx)
        try:
            offset = _integer_header(request, "x-upload-offset")
            sha256 = str(request.headers.get("x-chunk-sha256") or "")
            data = await _bounded_body(
                request,
                USER_CONFIG_BACKUP_UPLOAD_CHUNK_BYTES,
            )
            session = ctx.user_config_backup_import_service.append_chunk(
                session_id,
                offset,
                data,
                sha256,
            )
        except HTTPException:
            raise
        except (ValueError, OSError) as exc:
            raise _service_http_error(exc) from None
        return {"session": asdict(session)}

    @app.get("/api/user-config-restores/{session_id}")
    def get_user_config_restore(session_id: str) -> dict[str, Any]:
        snapshot = ctx.user_config_backup_import_service.get_snapshot(session_id)
        if snapshot is None:
            raise _safe_http_error(404, "user_config_restore_not_found")
        return asdict(snapshot)

    @app.delete("/api/user-config-restores/{session_id}")
    def cancel_user_config_restore(session_id: str) -> dict[str, Any]:
        try:
            cancelled = ctx.user_config_backup_import_service.cancel(session_id)
        except (ValueError, OSError) as exc:
            raise _service_http_error(exc) from None
        if not cancelled:
            raise _safe_http_error(404, "user_config_restore_not_found")
        return {"cancelled": True}

    @app.post("/api/user-config-restores/{session_id}/validate")
    def validate_user_config_restore(session_id: str) -> dict[str, Any]:
        _require_accepting(ctx)
        try:
            preview = ctx.user_config_backup_import_service.validate(session_id)
        except (ValueError, OSError) as exc:
            raise _service_http_error(exc) from None
        return {"preview": asdict(preview)}

    @app.post("/api/user-config-restores/{session_id}/restore")
    async def apply_user_config_restore(
        session_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = await _validated_json_body(
            request,
            ApplyUserConfigRestoreRequest,
        )
        _require_accepting(ctx)
        try:
            result = ctx.user_config_backup_import_service.restore(
                session_id,
                sections=payload.sections,
                mode=payload.mode,
                archive_sha256=payload.archive_sha256,
                preview_revision=payload.preview_revision,
                confirm_replace=payload.confirm_replace,
            )
        except (ValueError, OSError) as exc:
            raise _service_http_error(exc) from None
        return {"result": asdict(result)}


async def _validated_json_body(
    request: Request,
    model: type[_ExactModel],
) -> Any:
    try:
        declared = request.headers.get("content-length")
        if declared is not None and int(declared) > _CONTROL_JSON_BYTES:
            raise _safe_http_error(413, "user_config_backup_request_too_large")
        body = bytearray()
        async for piece in request.stream():
            if len(body) + len(piece) > _CONTROL_JSON_BYTES:
                raise _safe_http_error(
                    413,
                    "user_config_backup_request_too_large",
                )
            body.extend(piece)
        return model.model_validate(json.loads(body))
    except HTTPException:
        raise
    except (ValidationError, ValueError, TypeError, json.JSONDecodeError):
        raise _safe_http_error(422, "user_config_backup_request_invalid") from None


async def _bounded_body(request: Request, maximum: int) -> bytes:
    declared = request.headers.get("content-length")
    try:
        if declared is not None and int(declared) > maximum:
            raise _safe_http_error(413, "user_config_restore_chunk_too_large")
    except ValueError:
        raise _safe_http_error(422, "user_config_restore_request_invalid") from None
    body = bytearray()
    async for piece in request.stream():
        if len(body) + len(piece) > maximum:
            raise _safe_http_error(413, "user_config_restore_chunk_too_large")
        body.extend(piece)
    return bytes(body)


def _integer_header(request: Request, name: str) -> int:
    try:
        value = int(request.headers.get(name) or "")
    except ValueError:
        raise _safe_http_error(422, "user_config_restore_request_invalid") from None
    if value < 0:
        raise _safe_http_error(422, "user_config_restore_request_invalid")
    return value


def _require_accepting(ctx: WebUIContext) -> None:
    if not ctx.user_config_backup_accepting_jobs:
        raise _safe_http_error(409, "user_config_backup_lifecycle_conflict")


def _job_payload(job: Any) -> dict[str, Any]:
    payload = asdict(job)
    payload["sections"] = list(job.sections)
    payload["warnings"] = list(job.warnings)
    error_code = payload.get("error_code")
    if error_code and not str(error_code).startswith("user_config_backup_"):
        payload["error_code"] = "user_config_backup_failed"
    return payload


def _service_http_error(error: BaseException) -> HTTPException:
    if isinstance(error, OSError):
        return _safe_http_error(507, "user_config_backup_io_error")
    code = str(error) if isinstance(error, ValueError) else ""
    status = _ERROR_STATUS_BY_CODE.get(code)
    if status is None and code.startswith("user_config_restore_"):
        status = 422
    if status is None:
        return _safe_http_error(500, "user_config_backup_internal_error")
    return _safe_http_error(status, code)


_ERROR_STATUS_BY_CODE = {
    "user_config_backup_not_found": 404,
    "user_config_backup_claimed": 409,
    "user_config_backup_not_ready": 409,
    "user_config_backup_active": 409,
    "user_config_backup_lifecycle_conflict": 409,
    "user_config_backup_gallery_invalid": 409,
    "user_config_backup_request_too_large": 413,
    "user_config_backup_manifest_too_large": 413,
    "user_config_backup_insufficient_space": 507,
    "user_config_backup_capacity_unavailable": 507,
    "user_config_backup_executor_unavailable": 503,
    "user_config_restore_not_found": 404,
    "user_config_restore_active": 409,
    "user_config_restore_lifecycle_conflict": 409,
    "user_config_restore_upload_incomplete": 409,
    "user_config_restore_offset_invalid": 409,
    "user_config_restore_chunk_retry_mismatch": 409,
    "user_config_restore_upload_state_invalid": 409,
    "user_config_restore_not_validated": 409,
    "user_config_restore_preview_stale": 409,
    "user_config_restore_archive_mismatch": 409,
    "user_config_restore_confirm_replace_required": 409,
    "user_config_restore_empty_replace_blocked": 409,
    "user_config_restore_active_tasks": 409,
    "user_config_restore_size_invalid": 413,
    "user_config_restore_upload_too_large": 413,
    "user_config_restore_upload_overflow": 413,
    "user_config_restore_chunk_too_large": 413,
    "user_config_restore_manifest_too_large": 413,
    "user_config_restore_member_too_large": 413,
    "user_config_restore_expanded_too_large": 413,
    "user_config_restore_entries_too_many": 413,
    "user_config_restore_compression_ratio": 413,
    "user_config_restore_insufficient_space": 507,
    "user_config_restore_capacity_unavailable": 507,
}


def _safe_http_error(status: int, code: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code})


__all__ = (
    "CreateUserConfigBackupRequest",
    "CreateUserConfigRestoreRequest",
    "ApplyUserConfigRestoreRequest",
    "register_user_config_backup_routes",
)
