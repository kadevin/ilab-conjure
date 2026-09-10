from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from math import gcd
from pathlib import Path
from typing import Any, Iterator

from codex_image.generation.catalog import GPT_IMAGE_MODEL_IDS

from .history_organizer import HistoryOrganizer
from .history_query import (
    HistoryFilter,
    HistoryQueryService,
    RATIO_OTHER_VALUE,
    encode_history_cursor as _encode_cursor,
)


SUMMARY_KEYS = {
    "task_id",
    "created_at",
    "updated_at",
    "viewed_at",
    "queued_at",
    "started_at",
    "attempt_started_at",
    "retry_requested_at",
    "completed_at",
    "terminal_at",
    "mode",
    "status",
    "prompt",
    "prompt_for_model",
    "prompt_constraints",
    "params",
    "input_files",
    "input_urls",
    "input_thumbnail_urls",
    "input_sources",
    "mask_file",
    "gallery_refs",
    "reference_assets",
    "reference_file_count",
    "generated_count",
    "failed_count",
    "total_count",
    "original_total_count",
    "cleared_failed_count",
    "partial_failure_cleared_at",
    "pruned_output_count",
    "output_file",
    "output_files",
    "output_url",
    "output_urls",
    "thumbnail_urls",
    "outputs",
    "output_size",
    "output_sizes",
    "output_format",
    "output_formats",
    "quality",
    "qualities",
    "background",
    "backgrounds",
    "revised_prompt",
    "revised_prompts",
    "usage",
    "usages",
    "attempts",
    "max_attempts",
    "retrying_failed_slots",
    "retry_failed_slots",
    "last_error",
    "error",
    "cancel_requested",
    "cancel_requested_at",
    "cancelled_at",
    "orphaned_running",
    "archived_at",
    "selected_output_indexes",
    "deleted_output_indexes",
    "api_provider_id",
    "api_provider_name",
    "api_images_concurrency",
    "requested_backend",
    "backend",
    "assigned_auth_source",
}

TASK_INDEX_SCHEMA_VERSION = 9
TERMINAL_TASK_STATUSES = frozenset({"completed", "failed", "partial_failed"})
TASK_CARD_PARAMETER_KEYS = ("canvas.aspect_ratio", "canvas.resolution")
KNOWN_RATIO_ORIENTATIONS = {
    "1:1": "square",
    "4:5": "portrait",
    "5:4": "landscape",
    "3:4": "portrait",
    "4:3": "landscape",
    "2:3": "portrait",
    "3:2": "landscape",
    "9:16": "portrait",
    "16:9": "landscape",
    "9:21": "portrait",
    "21:9": "landscape",
}
GPT_IMAGE_2_PRESET_SIZES_BY_RESOLUTION = {
    "1K": frozenset(
        {
            "1024x1024",
            "1024x1280",
            "1280x1024",
            "1152x1536",
            "1536x1152",
            "1024x1536",
            "1536x1024",
            "864x1536",
            "1536x864",
            "672x1568",
            "1568x672",
        }
    ),
    "2K": frozenset(
        {
            "2048x2048",
            "1600x2000",
            "2000x1600",
            "1536x2048",
            "2048x1536",
            "1344x2016",
            "2016x1344",
            "1152x2048",
            "2048x1152",
            "1152x2688",
            "2688x1152",
        }
    ),
    "4K": frozenset(
        {
            "2880x2880",
            "2560x3200",
            "3200x2560",
            "2448x3264",
            "3264x2448",
            "2336x3504",
            "3504x2336",
            "2160x3840",
            "3840x2160",
            "1632x3808",
            "3808x1632",
        }
    ),
}


class SQLiteTaskIndex:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fts_enabled = False
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    create table if not exists task_index (
                        task_id text primary key,
                        created_at text not null default '',
                        updated_at text not null default '',
                        status text not null default '',
                        prompt text not null default '',
                        summary_json text not null
                    )
                    """
                )
                connection.execute("create index if not exists idx_task_index_created_at on task_index(created_at desc)")
                self._ensure_structured_columns(connection)
                self._ensure_structured_indexes(connection)
                self.fts_enabled = self._ensure_fts(connection)
                self._backfill_structured_columns(connection)

    def _ensure_structured_columns(self, connection: sqlite3.Connection) -> None:
        existing = {row["name"] for row in connection.execute("pragma table_info(task_index)").fetchall()}
        columns = {
            "completed_at": "text not null default ''",
            "terminal_at": "text not null default ''",
            "activity_at": "text not null default ''",
            "month_key": "text not null default ''",
            "mode": "text not null default ''",
            "size": "text not null default ''",
            "quality": "text not null default ''",
            "prompt_mode": "text not null default ''",
            "ratio": "text not null default ''",
            "orientation": "text not null default ''",
            "resolution": "text not null default ''",
            "backend": "text not null default ''",
            "provider": "text not null default ''",
            "archived_at": "text not null default ''",
            "generated_count": "integer not null default 0",
            "failed_count": "integer not null default 0",
            "total_count": "integer not null default 0",
            "thumbnail_url": "text not null default ''",
            "prompt_preview": "text not null default ''",
            "search_text": "text not null default ''",
            "schema_version": "integer not null default 0",
        }
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(f"alter table task_index add column {name} {definition}")

    def _ensure_structured_indexes(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            "create index if not exists idx_task_index_history_cursor "
            "on task_index(created_at desc, task_id desc)"
        )
        connection.execute("create index if not exists idx_task_index_month_created on task_index(month_key, created_at desc, task_id desc)")
        connection.execute("create index if not exists idx_task_index_status on task_index(status)")
        connection.execute("create index if not exists idx_task_index_archived on task_index(archived_at)")
        connection.execute(
            "create index if not exists idx_task_index_sidebar_activity "
            "on task_index(archived_at, activity_at desc, created_at desc, task_id desc)"
        )
        connection.execute("create index if not exists idx_task_index_size on task_index(size)")
        connection.execute("create index if not exists idx_task_index_quality on task_index(quality)")
        connection.execute("create index if not exists idx_task_index_prompt_mode on task_index(prompt_mode)")
        connection.execute("create index if not exists idx_task_index_ratio on task_index(ratio)")
        connection.execute("create index if not exists idx_task_index_orientation on task_index(orientation)")
        connection.execute("create index if not exists idx_task_index_resolution on task_index(resolution)")
        connection.execute("create index if not exists idx_task_index_backend on task_index(backend)")
        connection.execute("create index if not exists idx_task_index_provider on task_index(provider)")

    def _ensure_fts(self, connection: sqlite3.Connection) -> bool:
        try:
            connection.execute(
                """
                create virtual table if not exists task_index_fts
                using fts5(task_id unindexed, search_text)
                """
            )
        except sqlite3.OperationalError:
            return False
        return True

    def _backfill_structured_columns(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            select task_id, summary_json, completed_at, terminal_at
            from task_index
            where schema_version < ? or search_text = '' or month_key = '' or prompt_preview = '' or activity_at = ''
            """
        , (TASK_INDEX_SCHEMA_VERSION,)).fetchall()
        for row in rows:
            try:
                summary = json.loads(str(row["summary_json"]))
            except json.JSONDecodeError:
                continue
            if not isinstance(summary, dict):
                continue
            if not summary.get("completed_at") and row["completed_at"]:
                summary["completed_at"] = str(row["completed_at"])
            if not summary.get("terminal_at") and row["terminal_at"]:
                summary["terminal_at"] = str(row["terminal_at"])
            fields = _history_fields_for_metadata(summary)
            connection.execute(
                """
                update task_index
                set completed_at = ?, terminal_at = ?, activity_at = ?, month_key = ?, mode = ?, size = ?, quality = ?, prompt_mode = ?, ratio = ?, orientation = ?, resolution = ?,
                    backend = ?, provider = ?, archived_at = ?, generated_count = ?, failed_count = ?,
                    total_count = ?, thumbnail_url = ?, prompt_preview = ?, search_text = ?, schema_version = ?
                where task_id = ?
                """,
                (
                    fields["completed_at"],
                    fields["terminal_at"],
                    fields["activity_at"],
                    fields["month_key"],
                    fields["mode"],
                    fields["size"],
                    fields["quality"],
                    fields["prompt_mode"],
                    fields["ratio"],
                    fields["orientation"],
                    fields["resolution"],
                    fields["backend"],
                    fields["provider"],
                    fields["archived_at"],
                    fields["generated_count"],
                    fields["failed_count"],
                    fields["total_count"],
                    fields["thumbnail_url"],
                    fields["prompt_preview"],
                    fields["search_text"],
                    TASK_INDEX_SCHEMA_VERSION,
                    str(row["task_id"]),
                ),
            )
            self._upsert_fts_row(connection, str(row["task_id"]), fields["search_text"])

    def upsert(self, metadata: dict[str, Any]) -> None:
        task_id = str(metadata.get("task_id") or "")
        if not task_id:
            return
        summary = _summary_for_metadata(metadata)
        fields = _history_fields_for_metadata(metadata)
        created_at = str(metadata.get("created_at") or "")
        updated_at = str(metadata.get("updated_at") or "")
        status = str(metadata.get("status") or "")
        prompt = str(metadata.get("prompt") or "")
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    insert into task_index(
                        task_id, created_at, updated_at, status, prompt, summary_json,
                        completed_at, terminal_at, activity_at, month_key, mode, size, quality, prompt_mode, ratio, orientation, resolution, backend, provider,
                        archived_at, generated_count, failed_count, total_count, thumbnail_url,
                        prompt_preview, search_text, schema_version
                    )
                    values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    on conflict(task_id) do update set
                        created_at = excluded.created_at,
                        updated_at = excluded.updated_at,
                        status = excluded.status,
                        prompt = excluded.prompt,
                        summary_json = excluded.summary_json,
                        completed_at = excluded.completed_at,
                        terminal_at = excluded.terminal_at,
                        activity_at = excluded.activity_at,
                        month_key = excluded.month_key,
                        mode = excluded.mode,
                        size = excluded.size,
                        quality = excluded.quality,
                        prompt_mode = excluded.prompt_mode,
                        ratio = excluded.ratio,
                        orientation = excluded.orientation,
                        resolution = excluded.resolution,
                        backend = excluded.backend,
                        provider = excluded.provider,
                        archived_at = excluded.archived_at,
                        generated_count = excluded.generated_count,
                        failed_count = excluded.failed_count,
                        total_count = excluded.total_count,
                        thumbnail_url = excluded.thumbnail_url,
                        prompt_preview = excluded.prompt_preview,
                        search_text = excluded.search_text,
                        schema_version = excluded.schema_version
                    """,
                    (
                        task_id,
                        created_at,
                        updated_at,
                        status,
                        prompt,
                        json.dumps(summary, ensure_ascii=False),
                        fields["completed_at"],
                        fields["terminal_at"],
                        fields["activity_at"],
                        fields["month_key"],
                        fields["mode"],
                        fields["size"],
                        fields["quality"],
                        fields["prompt_mode"],
                        fields["ratio"],
                        fields["orientation"],
                        fields["resolution"],
                        fields["backend"],
                        fields["provider"],
                        fields["archived_at"],
                        fields["generated_count"],
                        fields["failed_count"],
                        fields["total_count"],
                        fields["thumbnail_url"],
                        fields["prompt_preview"],
                        fields["search_text"],
                        TASK_INDEX_SCHEMA_VERSION,
                    ),
                )
                self._upsert_fts_row(connection, task_id, fields["search_text"])

    def delete(self, task_id: str) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("delete from task_index where task_id = ?", (task_id,))
                self._delete_fts_row(connection, task_id)

    def existing_task_ids(self, task_ids: list[str]) -> set[str]:
        normalized = list(
            dict.fromkeys(
                task_id
                for value in task_ids
                if (task_id := str(value or "").strip())
            )
        )
        if not normalized:
            return set()
        placeholders = ", ".join("?" for _ in normalized)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"""
                select task_id
                from task_index
                where task_id in ({placeholders})
                """,
                tuple(normalized),
            ).fetchall()
        return {str(row["task_id"]) for row in rows}

    def all_task_ids(self) -> set[str]:
        with closing(self._connect()) as connection:
            rows = connection.execute("select task_id from task_index").fetchall()
        return {str(row["task_id"]) for row in rows}

    def list_summaries(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            sql = "select summary_json from task_index order by created_at desc, task_id desc"
            params: tuple[Any, ...] = ()
            if limit is not None:
                sql += " limit ?"
                params = (max(0, int(limit)),)
            rows = connection.execute(sql, params).fetchall()
        summaries: list[dict[str, Any]] = []
        for row in rows:
            try:
                summary = json.loads(str(row["summary_json"]))
            except json.JSONDecodeError:
                continue
            if isinstance(summary, dict):
                summary["reference_file_count"] = _nonnegative_int(summary.get("reference_file_count"))
                summaries.append(summary)
        return summaries

    def generation_sidebar_groups(
        self,
        *,
        limit_per_group: int = 50,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        return {
            "groups": [
                self.generation_sidebar_group(key, limit=limit_per_group, now=now)
                for key in ("today", "yesterday", "last7")
            ]
        }

    def generation_sidebar_group(
        self,
        key: str,
        *,
        offset: int = 0,
        limit: int = 50,
        now: datetime | None = None,
        status: str = "",
        prompt_mode: str = "",
        ratio: str = "",
        orientation: str = "",
        resolution: str = "",
    ) -> dict[str, Any]:
        safe_limit = min(100, max(1, int(limit or 50)))
        safe_offset = max(0, int(offset or 0))
        where, params = self._generation_sidebar_group_query(
            key,
            now=now,
            status=status,
            prompt_mode=prompt_mode,
            ratio=ratio,
            orientation=orientation,
            resolution=resolution,
        )
        with closing(self._connect()) as connection:
            count = int(
                connection.execute(
                    f"select count(*) from task_index where {' and '.join(where)}",
                    tuple(params),
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                select summary_json, completed_at, terminal_at from task_index
                where {' and '.join(where)}
                order by activity_at desc, created_at desc, task_id desc
                limit ? offset ?
                """,
                (*params, safe_limit, safe_offset),
            ).fetchall()
        tasks = []
        for row in rows:
            try:
                summary = json.loads(str(row["summary_json"]))
            except json.JSONDecodeError:
                continue
            if not isinstance(summary, dict):
                continue
            if not summary.get("completed_at") and row["completed_at"]:
                summary["completed_at"] = str(row["completed_at"])
            if not summary.get("terminal_at") and row["terminal_at"]:
                summary["terminal_at"] = str(row["terminal_at"])
            summary["reference_file_count"] = _nonnegative_int(summary.get("reference_file_count"))
            tasks.append(summary)
        return {
            "key": key,
            "count": count,
            "tasks": tasks,
            "offset": safe_offset,
            "next_offset": safe_offset + len(tasks),
            "has_more": safe_offset + len(tasks) < count,
        }

    def generation_sidebar_group_task_ids(
        self,
        key: str,
        *,
        now: datetime | None = None,
        status: str = "",
        prompt_mode: str = "",
        ratio: str = "",
        orientation: str = "",
        resolution: str = "",
        limit: int = 5000,
    ) -> dict[str, Any]:
        safe_limit = min(5000, max(1, int(limit or 5000)))
        where, params = self._generation_sidebar_group_query(
            key,
            now=now,
            status=status,
            prompt_mode=prompt_mode,
            ratio=ratio,
            orientation=orientation,
            resolution=resolution,
        )
        with closing(self._connect()) as connection:
            count = int(
                connection.execute(
                    f"select count(*) from task_index where {' and '.join(where)}",
                    tuple(params),
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                select task_id from task_index
                where {' and '.join(where)}
                order by activity_at desc, created_at desc, task_id desc
                limit ?
                """,
                (*params, safe_limit),
            ).fetchall()
        return {
            "key": key,
            "count": count,
            "task_ids": [str(row["task_id"]) for row in rows],
            "truncated": count > safe_limit,
        }

    def generation_sidebar_group_task_position(
        self,
        key: str,
        task_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        where, params = self._generation_sidebar_group_query(
            key,
            now=now,
            status="",
            prompt_mode="",
            ratio="",
            orientation="",
            resolution="",
        )
        with closing(self._connect()) as connection:
            count = int(
                connection.execute(
                    f"select count(*) from task_index where {' and '.join(where)}",
                    tuple(params),
                ).fetchone()[0]
            )
            row = connection.execute(
                f"""
                with ranked as (
                    select
                        task_id,
                        row_number() over (
                            order by activity_at desc, created_at desc, task_id desc
                        ) - 1 as position
                    from task_index
                    where {' and '.join(where)}
                )
                select position from ranked where task_id = ?
                """,
                (*params, str(task_id or "")),
            ).fetchone()
        return {
            "key": key,
            "count": count,
            "found": row is not None,
            "position": int(row["position"]) if row is not None else None,
        }

    def _generation_sidebar_group_query(
        self,
        key: str,
        *,
        now: datetime | None,
        status: str,
        prompt_mode: str,
        ratio: str,
        orientation: str,
        resolution: str,
    ) -> tuple[list[str], list[Any]]:
        local_start, local_end = _generation_sidebar_group_range(key, now)
        where = [
            "archived_at = ''",
            "status not in ('submitting', 'queued', 'running', 'cancelling')",
            "activity_at >= ?",
            "activity_at < ?",
        ]
        params: list[Any] = [
            _normalized_utc_timestamp(local_start),
            _normalized_utc_timestamp(local_end),
        ]
        for column, value in (
            ("status", status),
            ("prompt_mode", prompt_mode),
            ("ratio", ratio),
            ("orientation", orientation),
            ("resolution", resolution),
        ):
            clean_value = str(value or "").strip()
            if clean_value:
                where.append(f"{column} = ?")
                params.append(clean_value)
        return where, params

    def stale_completed_task_ids(self, *, limit: int = 500) -> list[str]:
        safe_limit = min(1000, max(1, int(limit or 500)))
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                select task_id from task_index
                where status in ('completed', 'partial_failed')
                  and (thumbnail_url = '' or generated_count = 0 or total_count = 0)
                order by updated_at desc, created_at desc, task_id desc
                limit ?
                """,
                (safe_limit,),
            ).fetchall()
        return [str(row["task_id"]) for row in rows]

    def query_history(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        q: str = "",
        month: str = "",
        mode: str = "",
        status: str = "",
        prompt_mode: str = "",
        size: str = "",
        quality: str = "",
        ratio: str = "",
        orientation: str = "",
        backend: str = "",
        provider: str = "",
        archived: bool | None = None,
        favorite: bool | None = None,
        tag_ids: list[str] | None = None,
        untagged: bool = False,
        sort: str = "newest",
        direction: str = "next",
    ) -> dict[str, Any]:
        return self._history_query_service().query(
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

    def iter_history_task_ids(
        self,
        filters: HistoryFilter,
    ) -> Iterator[str]:
        return self._history_query_service().iter_task_ids(filters)

    def query_history_around(
        self,
        anchor_task_id: str,
        filters: HistoryFilter,
        *,
        limit: int = 50,
    ) -> dict[str, Any]:
        return self._history_query_service().query_around(
            anchor_task_id,
            filters,
            limit=limit,
        )

    def history_summary(self) -> dict[str, Any]:
        return self._history_query_service().summary()

    def _history_query_service(self) -> HistoryQueryService:
        organizer = HistoryOrganizer(
            self.path.with_name("webui-history-organizer.db")
        )
        return HistoryQueryService(self, organizer)

    def _upsert_fts_row(self, connection: sqlite3.Connection, task_id: str, search_text: str) -> None:
        if not self.fts_enabled:
            return
        try:
            connection.execute("delete from task_index_fts where task_id = ?", (task_id,))
            connection.execute("insert into task_index_fts(task_id, search_text) values(?, ?)", (task_id, search_text))
        except sqlite3.OperationalError:
            self.fts_enabled = False

    def _delete_fts_row(self, connection: sqlite3.Connection, task_id: str) -> None:
        if not self.fts_enabled:
            return
        try:
            connection.execute("delete from task_index_fts where task_id = ?", (task_id,))
        except sqlite3.OperationalError:
            self.fts_enabled = False


def safe_task_canvas_parameters(generation_snapshot: object) -> dict[str, str]:
    if not isinstance(generation_snapshot, dict):
        return {}
    requested_parameters = generation_snapshot.get("requested_parameters")
    if not isinstance(requested_parameters, dict):
        return {}
    safe: dict[str, str] = {}
    for key in TASK_CARD_PARAMETER_KEYS:
        value = requested_parameters.get(key)
        if isinstance(value, str) and value.strip():
            safe[key] = value.strip()
    if str(generation_snapshot.get("canonical_model_id") or "").strip() in GPT_IMAGE_MODEL_IDS:
        for key, value in _gpt_image_2_card_canvas_parameters(requested_parameters).items():
            safe.setdefault(key, value)
    return safe


def _gpt_image_2_card_canvas_parameters(requested_parameters: dict[str, Any]) -> dict[str, str]:
    size = _normalize_dimension_size(requested_parameters.get("canvas.size"))
    if not size:
        return {}
    parameters: dict[str, str] = {}
    ratio = _known_ratio_from_size(size)
    if ratio:
        parameters["canvas.aspect_ratio"] = ratio
    for resolution, preset_sizes in GPT_IMAGE_2_PRESET_SIZES_BY_RESOLUTION.items():
        if size in preset_sizes:
            parameters["canvas.resolution"] = resolution
            break
    return parameters


def project_task_generation_snapshot(generation_snapshot: object) -> dict[str, Any]:
    if not isinstance(generation_snapshot, dict):
        return {}
    projected: dict[str, Any] = {}
    canonical_model_id = str(generation_snapshot.get("canonical_model_id") or "").strip()
    if canonical_model_id:
        projected["canonical_model_id"] = canonical_model_id
    requested_parameters = safe_task_canvas_parameters(generation_snapshot)
    if requested_parameters:
        projected["requested_parameters"] = requested_parameters
    return projected


def _summary_for_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    summary = {key: metadata[key] for key in SUMMARY_KEYS if key in metadata}
    summary["reference_file_count"] = _nonnegative_int(metadata.get("reference_file_count"))
    generation_snapshot = metadata.get("generation_snapshot")
    projected_snapshot = project_task_generation_snapshot(generation_snapshot)
    if projected_snapshot:
        summary["generation_snapshot"] = projected_snapshot
    params = summary.get("params")
    request_payload = metadata.get("request")
    if isinstance(params, dict) and not params.get("main_model") and isinstance(request_payload, dict) and request_payload.get("model"):
        summary["params"] = {**params, "main_model": str(request_payload["model"])}
    return summary


def _history_fields_for_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    task_id = str(metadata.get("task_id") or "")
    params = metadata.get("params") if isinstance(metadata.get("params"), dict) else {}
    prompt = str(metadata.get("prompt") or "")
    prompt_for_model = str(metadata.get("prompt_for_model") or "")
    created_at = str(metadata.get("created_at") or "")
    backend = str(metadata.get("backend") or metadata.get("requested_backend") or "")
    provider = str(metadata.get("api_provider_name") or params.get("api_provider_name") or metadata.get("api_provider_id") or params.get("api_provider_id") or "")
    size = _history_display_size(metadata, params)
    ratio = _history_ratio(params, size)
    failed_count = _nonnegative_int(metadata.get("failed_count"))
    generated_count = _nonnegative_int(metadata.get("generated_count"))
    completed_output_count = _completed_output_count(metadata)
    if generated_count == 0 and completed_output_count:
        generated_count = completed_output_count
    total_count = _nonnegative_int(metadata.get("total_count"))
    if total_count == 0:
        total_count = _nonnegative_int(params.get("n")) or generated_count + failed_count
    terminal_at = _terminal_timestamp_for_metadata(metadata)
    return {
        "completed_at": str(metadata.get("completed_at") or ""),
        "terminal_at": terminal_at,
        "activity_at": _normalized_utc_timestamp(
            terminal_at or metadata.get("updated_at") or metadata.get("created_at")
        ),
        "month_key": created_at[:7] if len(created_at) >= 7 else "",
        "mode": str(metadata.get("mode") or ""),
        "size": size,
        "quality": str(params.get("quality") or metadata.get("quality") or _first_list_value(metadata.get("qualities")) or _first_output_value(metadata, "quality") or ""),
        "prompt_mode": str(params.get("prompt_fidelity") or metadata.get("prompt_fidelity") or ""),
        "ratio": ratio,
        "orientation": _history_orientation(params, size, ratio),
        "resolution": _history_resolution(metadata, params),
        "backend": backend,
        "provider": provider,
        "archived_at": str(metadata.get("archived_at") or ""),
        "generated_count": generated_count,
        "failed_count": failed_count,
        "total_count": total_count,
        "thumbnail_url": _first_thumbnail_url(task_id, metadata),
        "prompt_preview": _truncate(prompt, 240),
        "search_text": "\n".join(value for value in [task_id, prompt, prompt_for_model] if value),
    }


def _terminal_timestamp_for_metadata(metadata: dict[str, Any]) -> str:
    explicit = str(metadata.get("terminal_at") or metadata.get("completed_at") or "")
    if explicit:
        return explicit
    if str(metadata.get("status") or "") in TERMINAL_TASK_STATUSES:
        return str(metadata.get("created_at") or metadata.get("updated_at") or "")
    return ""


def _history_resolution(metadata: dict[str, Any], params: dict[str, Any]) -> str:
    generation_snapshot = project_task_generation_snapshot(metadata.get("generation_snapshot"))
    requested = generation_snapshot.get("requested_parameters") if isinstance(generation_snapshot, dict) else {}
    value = (
        (requested.get("canvas.resolution") if isinstance(requested, dict) else "")
        or params.get("resolution")
        or ""
    )
    normalized = str(value).strip().lower()
    return {"1k": "standard", "standard": "standard", "2k": "2k", "4k": "4k"}.get(normalized, normalized)


def _generation_sidebar_group_range(key: str, now: datetime | None) -> tuple[datetime, datetime]:
    local_now = now or datetime.now().astimezone()
    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=UTC).astimezone()
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    ranges = {
        "today": (today_start, today_start + timedelta(days=1)),
        "yesterday": (today_start - timedelta(days=1), today_start),
        "last7": (today_start - timedelta(days=6), today_start - timedelta(days=1)),
    }
    if key not in ranges:
        raise ValueError("Invalid sidebar task group")
    return ranges[key]


def _normalized_utc_timestamp(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat(timespec="microseconds")


def _history_ratio(params: dict[str, Any], size: str) -> str:
    known = _known_ratio_from_size(size)
    if known:
        return known
    explicit = str(params.get("ratio") or "").strip()
    if explicit:
        return explicit
    return ""


def _history_orientation(params: dict[str, Any], size: str, ratio: str) -> str:
    from_size = _orientation_from_size(size)
    if from_size:
        return from_size
    if ratio in KNOWN_RATIO_ORIENTATIONS:
        return KNOWN_RATIO_ORIENTATIONS[ratio]
    explicit = str(params.get("orientation") or "").strip()
    if explicit:
        return explicit
    return _orientation_from_size(size)


def _history_display_size(metadata: dict[str, Any], params: dict[str, Any]) -> str:
    for value in (
        metadata.get("output_size"),
        _first_list_value(metadata.get("output_sizes")),
        _first_output_value(metadata, "size"),
        params.get("size"),
    ):
        size = _normalize_dimension_size(value)
        if size:
            return size
    requested_size = str(params.get("size") or "")
    return requested_size if requested_size and not requested_size.isdigit() else ""


def _normalize_dimension_size(value: Any) -> str:
    text = str(value or "").strip().lower()
    dimensions = _size_dimensions(text)
    if dimensions is None:
        return ""
    return f"{dimensions[0]}x{dimensions[1]}"


def _known_ratio_from_size(size: str) -> str:
    dimensions = _size_dimensions(size)
    if dimensions is None:
        return ""
    width, height = dimensions
    divisor = gcd(width, height)
    ratio = f"{width // divisor}:{height // divisor}"
    return ratio if ratio in KNOWN_RATIO_ORIENTATIONS else ""


def _orientation_from_size(size: str) -> str:
    dimensions = _size_dimensions(size)
    if dimensions is None:
        return ""
    width, height = dimensions
    if width == height:
        return "square"
    return "landscape" if width > height else "portrait"


def _size_dimensions(size: str) -> tuple[int, int] | None:
    if "x" not in size:
        return None
    raw_width, raw_height = size.lower().split("x", 1)
    try:
        width = int(raw_width)
        height = int(raw_height)
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _completed_output_count(metadata: dict[str, Any]) -> int:
    outputs = metadata.get("outputs")
    if isinstance(outputs, list):
        return sum(1 for output in outputs if isinstance(output, dict) and str(output.get("status") or "completed") == "completed")
    output_urls = metadata.get("output_urls")
    if isinstance(output_urls, list):
        return sum(1 for url in output_urls if url)
    return 1 if metadata.get("output_url") or metadata.get("output_file") else 0


def _first_thumbnail_url(task_id: str, metadata: dict[str, Any]) -> str:
    thumbnail_route = _first_output_thumbnail_route(task_id, metadata)
    if thumbnail_route:
        return thumbnail_route
    thumbnail_urls = metadata.get("thumbnail_urls")
    if isinstance(thumbnail_urls, list):
        for url in thumbnail_urls:
            if url:
                return str(url)
    outputs = metadata.get("outputs")
    if isinstance(outputs, list):
        for output in outputs:
            if isinstance(output, dict):
                url = str(output.get("thumbnail_url") or output.get("url") or "")
                if url:
                    return url
    output_urls = metadata.get("output_urls")
    if isinstance(output_urls, list):
        for url in output_urls:
            if url:
                return str(url)
    return str(metadata.get("output_url") or metadata.get("preview_url") or "")


def _first_output_thumbnail_route(task_id: str, metadata: dict[str, Any]) -> str:
    if not task_id:
        return ""
    output_files = metadata.get("output_files") if isinstance(metadata.get("output_files"), list) else []
    output_urls = metadata.get("output_urls") if isinstance(metadata.get("output_urls"), list) else []
    outputs = metadata.get("outputs")
    if isinstance(outputs, list):
        for fallback_index, output in enumerate(outputs, start=1):
            if not isinstance(output, dict):
                continue
            status = str(output.get("status") or "completed")
            if status != "completed":
                continue
            index = _positive_int(output.get("index")) or fallback_index
            if (
                output.get("file")
                or (index <= len(output_files) and output_files[index - 1])
                or _is_local_output_url(output.get("url"))
                or (index <= len(output_urls) and _is_local_output_url(output_urls[index - 1]))
            ):
                return f"/api/tasks/{task_id}/outputs/{index}/thumbnail"
    if output_files:
        return f"/api/tasks/{task_id}/outputs/1/thumbnail"
    if output_urls and _is_local_output_url(output_urls[0]):
        return f"/api/tasks/{task_id}/outputs/1/thumbnail"
    if metadata.get("output_file"):
        return f"/api/tasks/{task_id}/outputs/1/thumbnail"
    if _is_local_output_url(metadata.get("output_url")):
        return f"/api/tasks/{task_id}/outputs/1/thumbnail"
    return ""


def _is_local_output_url(value: Any) -> bool:
    return str(value or "").startswith("/outputs/")


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _first_list_value(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    for item in value:
        if item:
            return str(item)
    return ""


def _first_output_value(metadata: dict[str, Any], key: str) -> str:
    outputs = metadata.get("outputs")
    if not isinstance(outputs, list):
        return ""
    for output in outputs:
        if isinstance(output, dict) and output.get(key):
            return str(output[key])
    return ""


def _nonnegative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def _truncate(value: str, limit: int) -> str:
    text = " ".join(value.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
