from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import re
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

from codex_image.webui.context import WebUIContext
from codex_image.webui.history_export import (
    HistoryExportNotFoundError,
    HistoryExportTaskNotFoundError,
    HistoryExportValidationError,
)
from codex_image.webui.history_organizer import (
    HistoryOrganization,
    HistoryTag,
    InvalidTagNameError,
    TagNameConflictError,
    TagNotFoundError,
)
from codex_image.webui.history_query import HistoryFilter
from codex_image.webui.storage import HistoryTaskNotFoundError


_SAFE_ANCHOR_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _unique_nonempty(values: list[str]) -> list[str]:
    return list(
        dict.fromkeys(
            value
            for item in values
            if (value := str(item or "").strip())
        )
    )


class TagMutation(BaseModel):
    name: str


class RefreshHistoryTasksRequest(BaseModel):
    task_ids: list[str] = Field(min_length=1, max_length=300)

    @field_validator("task_ids")
    @classmethod
    def validate_task_ids(cls, values: list[str]) -> list[str]:
        ids = _unique_nonempty(values)
        if not ids or any(not _SAFE_ANCHOR_TASK_ID_RE.fullmatch(task_id) for task_id in ids):
            raise ValueError("Invalid task ids")
        return ids


class OrganizeHistoryTasksRequest(BaseModel):
    task_ids: list[str]
    favorite: bool | None = None
    add_tag_ids: list[str] = Field(default_factory=list)
    remove_tag_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_request(self) -> OrganizeHistoryTasksRequest:
        self.task_ids = _unique_nonempty(self.task_ids)
        self.add_tag_ids = _unique_nonempty(self.add_tag_ids)
        self.remove_tag_ids = _unique_nonempty(
            self.remove_tag_ids
        )
        if not self.task_ids:
            raise ValueError("At least one task id is required")
        if len(self.task_ids) > 300:
            raise ValueError(
                "At most 300 tasks can be organized at once"
            )
        if set(self.add_tag_ids) & set(self.remove_tag_ids):
            raise ValueError(
                "A tag cannot be added and removed in one request"
            )
        return self


class CreateHistoryExportRequest(BaseModel):
    task_ids: list[str]
    mode: Literal["images_only", "images_with_prompts"]

    @field_validator("task_ids")
    @classmethod
    def validate_task_ids(
        cls,
        values: list[str],
    ) -> list[str]:
        task_ids = _unique_nonempty(values)
        if not task_ids:
            raise ValueError("At least one task id is required")
        if len(task_ids) > 300:
            raise ValueError(
                "At most 300 tasks can be exported at once"
            )
        return task_ids


class OneTimeHistoryExportResponse(FileResponse):
    def __init__(
        self,
        path: Path,
        *,
        filename: str,
        cleanup: Any,
    ) -> None:
        self._cleanup_export_file = cleanup
        self._export_path = path
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
            self._cleanup_export_file(self._export_path)


def tag_payload(
    tag: HistoryTag,
    *,
    count: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tag_id": tag.tag_id,
        "name": tag.name,
    }
    if count is not None:
        payload["count"] = count
    return payload


def organization_payload(
    organization: HistoryOrganization,
) -> dict[str, Any]:
    return {
        "favorite": organization.favorite,
        "tags": [tag_payload(tag) for tag in organization.tags],
    }


def _tag_http_error(exc: ValueError) -> HTTPException:
    if isinstance(exc, InvalidTagNameError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, TagNameConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, TagNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


def register_history_routes(
    app: FastAPI,
    ctx: WebUIContext,
) -> None:
    @app.get("/api/task-history/summary")
    def task_history_summary() -> dict[str, Any]:
        return ctx.storage.task_history_summary()

    @app.post("/api/task-history/tasks/refresh")
    def refresh_history_tasks(payload: RefreshHistoryTasksRequest) -> dict[str, Any]:
        return {"tasks": ctx.storage.task_history_summaries(payload.task_ids)}

    @app.get("/api/task-history/tasks")
    def task_history_tasks(
        limit: int = Query(50, ge=1, le=100),
        cursor: str | None = Query(None),
        anchor_task_id: str | None = Query(None, max_length=128),
        q: str = Query(""),
        month: str = Query(""),
        mode: str = Query(""),
        status: str = Query(""),
        prompt_mode: str = Query(""),
        size: str = Query(""),
        quality: str = Query(""),
        ratio: str = Query(""),
        orientation: str = Query(""),
        backend: str = Query(""),
        provider: str = Query(""),
        archived: bool | None = Query(None),
        favorite: bool | None = Query(None),
        tag_ids: list[str] = Query(default=[], alias="tag"),
        untagged: bool = Query(False),
        sort: str = Query("newest"),
        direction: str = Query("next"),
    ) -> dict[str, Any]:
        if untagged and tag_ids:
            raise HTTPException(
                status_code=422,
                detail=(
                    "untagged cannot be combined with tag filters"
                ),
            )
        if anchor_task_id is not None:
            clean_anchor = anchor_task_id.strip()
            if not _SAFE_ANCHOR_TASK_ID_RE.fullmatch(clean_anchor):
                raise HTTPException(
                    status_code=422,
                    detail="anchor_task_id is invalid",
                )
            if cursor is not None or direction == "previous":
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "anchor_task_id cannot be combined with cursor "
                        "or previous direction"
                    ),
                )
            try:
                filters = HistoryFilter(
                    q=q,
                    month=month,
                    mode=mode,
                    status=status,
                    prompt_mode=prompt_mode,
                    size=size,
                    quality=quality,
                    ratio=ratio,
                    orientation=orientation,
                    backend=backend,
                    provider=provider,
                    archived=archived,
                    favorite=favorite,
                    tag_ids=tuple(tag_ids),
                    untagged=untagged,
                    sort="oldest" if sort == "oldest" else "newest",
                )
                ctx.storage.refresh_stale_task_index()
                return ctx.storage.task_index.query_history_around(
                    clean_anchor,
                    filters,
                    limit=limit,
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=str(exc),
                ) from exc
        try:
            return ctx.storage.query_task_history(
                limit=limit,
                cursor=cursor,
                q=q,
                month=month,
                mode=mode,
                status=status,
                prompt_mode=prompt_mode,
                size=size,
                quality=quality,
                ratio=ratio,
                orientation=orientation,
                backend=backend,
                provider=provider,
                archived=archived,
                favorite=favorite,
                tag_ids=tag_ids,
                untagged=untagged,
                sort=sort,
                direction=direction,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

    @app.get("/api/task-history/tags")
    def list_history_tags() -> dict[str, Any]:
        return {"tags": ctx.storage.task_history_summary()["tags"]}

    @app.post("/api/task-history/tags")
    def create_history_tag(
        payload: TagMutation,
    ) -> dict[str, Any]:
        try:
            tag = ctx.storage.history_organizer.create_tag(
                payload.name
            )
        except ValueError as exc:
            raise _tag_http_error(exc) from exc
        return {"tag": tag_payload(tag, count=0)}

    @app.patch("/api/task-history/tags/{tag_id}")
    def rename_history_tag(
        tag_id: str,
        payload: TagMutation,
    ) -> dict[str, Any]:
        try:
            tag = ctx.storage.history_organizer.rename_tag(
                tag_id,
                payload.name,
            )
        except ValueError as exc:
            raise _tag_http_error(exc) from exc
        counts = {
            item["tag_id"]: int(item["count"])
            for item in ctx.storage.task_history_summary()["tags"]
        }
        return {
            "tag": tag_payload(
                tag,
                count=counts.get(tag.tag_id, 0),
            )
        }

    @app.delete("/api/task-history/tags/{tag_id}")
    def delete_history_tag(tag_id: str) -> dict[str, Any]:
        try:
            affected = (
                ctx.storage.history_organizer.delete_tag(tag_id)
            )
        except ValueError as exc:
            raise _tag_http_error(exc) from exc
        return {
            "deleted": tag_id,
            "affected_task_count": affected,
        }

    @app.post("/api/task-history/organize")
    def organize_history_tasks(
        payload: OrganizeHistoryTasksRequest,
    ) -> dict[str, Any]:
        try:
            organizations = ctx.storage.organize_history_tasks(
                payload.task_ids,
                favorite=payload.favorite,
                add_tag_ids=payload.add_tag_ids,
                remove_tag_ids=payload.remove_tag_ids,
            )
        except HistoryTaskNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "message": "Task not found",
                    "task_ids": list(exc.task_ids),
                },
            ) from exc
        except TagNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc
        return {
            "organizations": {
                task_id: organization_payload(organization)
                for task_id, organization in organizations.items()
            }
        }

    @app.post("/api/task-history/exports")
    def create_history_export(
        payload: CreateHistoryExportRequest,
    ) -> dict[str, Any]:
        try:
            result = ctx.history_export_service.create(
                payload.task_ids,
                mode=payload.mode,
            )
        except HistoryExportTaskNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=exc.safe_detail,
            ) from exc
        except HistoryExportValidationError as exc:
            raise HTTPException(
                status_code=409,
                detail=exc.safe_detail,
            ) from exc
        return asdict(result)

    @app.get(
        "/api/task-history/exports/{export_id}",
        response_model=None,
    )
    def download_history_export(
        export_id: str,
    ) -> OneTimeHistoryExportResponse:
        try:
            pending = ctx.history_export_service.claim(export_id)
        except HistoryExportNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=exc.safe_detail,
            ) from exc
        try:
            return OneTimeHistoryExportResponse(
                pending.path,
                filename=pending.filename,
                cleanup=ctx.history_export_service.remove_file,
            )
        except Exception:
            ctx.history_export_service.remove_file(
                pending.path
            )
            raise
