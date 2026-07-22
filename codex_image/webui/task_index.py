from __future__ import annotations

import base64
import json
import sqlite3
from contextlib import closing
from math import gcd
from pathlib import Path
from typing import Any


SUMMARY_KEYS = {
    "task_id",
    "created_at",
    "updated_at",
    "viewed_at",
    "queued_at",
    "started_at",
    "attempt_started_at",
    "retry_requested_at",
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

TASK_INDEX_SCHEMA_VERSION = 7
TASK_CARD_PARAMETER_KEYS = ("canvas.aspect_ratio", "canvas.resolution")
RATIO_OTHER_VALUE = "__other__"
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
            "month_key": "text not null default ''",
            "mode": "text not null default ''",
            "size": "text not null default ''",
            "quality": "text not null default ''",
            "prompt_mode": "text not null default ''",
            "ratio": "text not null default ''",
            "orientation": "text not null default ''",
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
        connection.execute("create index if not exists idx_task_index_month_created on task_index(month_key, created_at desc, task_id desc)")
        connection.execute("create index if not exists idx_task_index_status on task_index(status)")
        connection.execute("create index if not exists idx_task_index_archived on task_index(archived_at)")
        connection.execute("create index if not exists idx_task_index_size on task_index(size)")
        connection.execute("create index if not exists idx_task_index_quality on task_index(quality)")
        connection.execute("create index if not exists idx_task_index_prompt_mode on task_index(prompt_mode)")
        connection.execute("create index if not exists idx_task_index_ratio on task_index(ratio)")
        connection.execute("create index if not exists idx_task_index_orientation on task_index(orientation)")
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
            select task_id, summary_json
            from task_index
            where schema_version < ? or search_text = '' or month_key = '' or prompt_preview = ''
            """
        , (TASK_INDEX_SCHEMA_VERSION,)).fetchall()
        for row in rows:
            try:
                summary = json.loads(str(row["summary_json"]))
            except json.JSONDecodeError:
                continue
            if not isinstance(summary, dict):
                continue
            fields = _history_fields_for_metadata(summary)
            connection.execute(
                """
                update task_index
                set completed_at = ?, month_key = ?, mode = ?, size = ?, quality = ?, prompt_mode = ?, ratio = ?, orientation = ?,
                    backend = ?, provider = ?, archived_at = ?, generated_count = ?, failed_count = ?,
                    total_count = ?, thumbnail_url = ?, prompt_preview = ?, search_text = ?, schema_version = ?
                where task_id = ?
                """,
                (
                    fields["completed_at"],
                    fields["month_key"],
                    fields["mode"],
                    fields["size"],
                    fields["quality"],
                    fields["prompt_mode"],
                    fields["ratio"],
                    fields["orientation"],
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
                        completed_at, month_key, mode, size, quality, prompt_mode, ratio, orientation, backend, provider,
                        archived_at, generated_count, failed_count, total_count, thumbnail_url,
                        prompt_preview, search_text, schema_version
                    )
                    values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    on conflict(task_id) do update set
                        created_at = excluded.created_at,
                        updated_at = excluded.updated_at,
                        status = excluded.status,
                        prompt = excluded.prompt,
                        summary_json = excluded.summary_json,
                        completed_at = excluded.completed_at,
                        month_key = excluded.month_key,
                        mode = excluded.mode,
                        size = excluded.size,
                        quality = excluded.quality,
                        prompt_mode = excluded.prompt_mode,
                        ratio = excluded.ratio,
                        orientation = excluded.orientation,
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
                        fields["month_key"],
                        fields["mode"],
                        fields["size"],
                        fields["quality"],
                        fields["prompt_mode"],
                        fields["ratio"],
                        fields["orientation"],
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
        sort: str = "newest",
        direction: str = "next",
    ) -> dict[str, Any]:
        safe_limit = min(100, max(1, int(limit or 50)))
        sort_order = "oldest" if sort == "oldest" else "newest"
        page_direction = "previous" if direction == "previous" else "next"
        where: list[str] = []
        params: list[Any] = []
        if month:
            where.append("month_key = ?")
            params.append(month)
        if mode == "generate":
            where.append("mode = 'generate'")
        elif mode == "edit":
            where.append("mode != '' and mode != 'generate'")
        elif mode:
            where.append("mode = ?")
            params.append(mode)
        if status:
            where.append("status = ?")
            params.append(status)
        if prompt_mode:
            where.append("prompt_mode = ?")
            params.append(prompt_mode)
        if size:
            where.append("size = ?")
            params.append(size)
        if quality:
            where.append("quality = ?")
            params.append(quality)
        if ratio:
            if ratio == RATIO_OTHER_VALUE:
                where.append("ratio = ''")
            else:
                where.append("ratio = ?")
                params.append(ratio)
        if orientation:
            where.append("orientation = ?")
            params.append(orientation)
        if backend:
            where.append("backend = ?")
            params.append(backend)
        if provider:
            where.append("provider = ?")
            params.append(provider)
        if archived is True:
            where.append("archived_at != ''")
        elif archived is False:
            where.append("archived_at = ''")
        cursor_values = _decode_cursor(cursor)
        if cursor_values is not None:
            cursor_created_at, cursor_task_id = cursor_values
            if page_direction == "previous":
                if sort_order == "oldest":
                    where.append("(created_at < ? or (created_at = ? and task_id < ?))")
                else:
                    where.append("(created_at > ? or (created_at = ? and task_id > ?))")
            elif sort_order == "oldest":
                where.append("(created_at > ? or (created_at = ? and task_id > ?))")
            else:
                where.append("(created_at < ? or (created_at = ? and task_id < ?))")
            params.extend([cursor_created_at, cursor_created_at, cursor_task_id])
        clean_query = q.strip()
        search_param_count = 0
        if clean_query:
            search_like = f"%{clean_query}%"
            if self.fts_enabled:
                where.append(
                    "(task_id like ? or search_text like ? or "
                    "task_id in (select task_id from task_index_fts where task_index_fts match ?))"
                )
                params.extend([search_like, search_like, _fts_query(clean_query)])
                search_param_count = 3
            else:
                where.append("(task_id like ? or search_text like ?)")
                params.extend([search_like, search_like])
                search_param_count = 2
        sql = (
            "select task_id, created_at, updated_at, completed_at, status, mode, size, quality, prompt_mode, ratio, orientation, "
            "backend, provider, archived_at, generated_count, failed_count, total_count, thumbnail_url, prompt_preview "
            "from task_index"
        )
        if where:
            sql += " where " + " and ".join(where)
        if page_direction == "previous":
            order_clause = " order by created_at desc, task_id desc limit ?" if sort_order == "oldest" else " order by created_at asc, task_id asc limit ?"
        else:
            order_clause = " order by created_at asc, task_id asc limit ?" if sort_order == "oldest" else " order by created_at desc, task_id desc limit ?"
        sql += order_clause
        params.append(safe_limit + 1)
        try:
            rows = self._history_rows(sql, params)
        except sqlite3.OperationalError:
            if not clean_query or not self.fts_enabled:
                raise
            where = [clause for clause in where if "task_index_fts" not in clause]
            params_without_limit = params[:-1] if params else []
            params = params_without_limit[:-search_param_count] if search_param_count else params_without_limit
            search_like = f"%{clean_query}%"
            where.append("(task_id like ? or search_text like ?)")
            params.extend([search_like, search_like])
            params.append(safe_limit + 1)
            fallback_sql = sql.split(" where ")[0]
            fallback_sql += " where " + " and ".join(where)
            fallback_sql += order_clause
            rows = self._history_rows(fallback_sql, params)
        has_more = len(rows) > safe_limit
        page_rows = rows[:safe_limit]
        if page_direction == "previous":
            page_rows = list(reversed(page_rows))
        next_cursor = _encode_cursor(str(page_rows[-1]["created_at"]), str(page_rows[-1]["task_id"])) if page_direction == "next" and has_more and page_rows else None
        previous_cursor = _encode_cursor(str(page_rows[0]["created_at"]), str(page_rows[0]["task_id"])) if page_direction == "previous" and has_more and page_rows else None
        return {
            "tasks": [_history_row_response(row) for row in page_rows],
            "next_cursor": next_cursor,
            "previous_cursor": previous_cursor,
        }

    def _history_rows(self, sql: str, params: list[Any]) -> list[sqlite3.Row]:
        with closing(self._connect()) as connection:
            return connection.execute(sql, tuple(params)).fetchall()

    def history_summary(self) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            total = int(connection.execute("select count(*) from task_index").fetchone()[0])
            archived_total = int(connection.execute("select count(*) from task_index where archived_at != ''").fetchone()[0])
            months = _count_rows(connection, "month_key", "month_key != ''", order_by="month_key desc")
            modes = _mode_count_rows(connection)
            statuses = _count_rows(connection, "status", "status != ''")
            prompt_modes = _count_rows(connection, "prompt_mode", "prompt_mode != ''")
            sizes = _count_rows(connection, "size", "size != ''")
            qualities = _count_rows(connection, "quality", "quality != ''")
            ratios = _ratio_count_rows(connection)
            orientations = _count_rows(connection, "orientation", "orientation != ''")
            backends = _count_rows(connection, "backend", "backend != ''")
            providers = _count_rows(connection, "provider", "provider != ''")
        return {
            "total": total,
            "archived_total": archived_total,
            "months": [{"month": item["value"], "count": item["count"]} for item in months],
            "modes": modes,
            "statuses": statuses,
            "prompt_modes": prompt_modes,
            "sizes": sizes,
            "qualities": qualities,
            "ratios": ratios,
            "orientations": orientations,
            "backends": backends,
            "providers": providers,
        }

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
    if str(generation_snapshot.get("canonical_model_id") or "").strip() == "gpt-image-2":
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
    return {
        "completed_at": str(metadata.get("completed_at") or ""),
        "month_key": created_at[:7] if len(created_at) >= 7 else "",
        "mode": str(metadata.get("mode") or ""),
        "size": size,
        "quality": str(params.get("quality") or metadata.get("quality") or _first_list_value(metadata.get("qualities")) or _first_output_value(metadata, "quality") or ""),
        "prompt_mode": str(params.get("prompt_fidelity") or metadata.get("prompt_fidelity") or ""),
        "ratio": ratio,
        "orientation": _history_orientation(params, size, ratio),
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


def _encode_cursor(created_at: str, task_id: str) -> str:
    raw = json.dumps({"created_at": created_at, "task_id": task_id}, ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None) -> tuple[str, str] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    created_at = str(payload.get("created_at") or "")
    task_id = str(payload.get("task_id") or "")
    return (created_at, task_id) if created_at and task_id else None


def _fts_query(query: str) -> str:
    terms = [term.replace('"', '""') for term in query.split() if term.strip()]
    return " AND ".join(f'"{term}"' for term in terms) if terms else '""'


def _history_row_response(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "task_id": str(row["task_id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "completed_at": str(row["completed_at"]),
        "status": str(row["status"]),
        "mode": str(row["mode"]),
        "size": str(row["size"]),
        "quality": str(row["quality"]),
        "prompt_mode": str(row["prompt_mode"]),
        "ratio": str(row["ratio"]),
        "orientation": str(row["orientation"]),
        "backend": str(row["backend"]),
        "provider": str(row["provider"]),
        "archived": bool(str(row["archived_at"])),
        "generated_count": int(row["generated_count"]),
        "failed_count": int(row["failed_count"]),
        "total_count": int(row["total_count"]),
        "thumbnail_url": str(row["thumbnail_url"]),
        "prompt_preview": str(row["prompt_preview"]),
    }


def _count_rows(connection: sqlite3.Connection, column: str, where: str, *, order_by: str = "count(*) desc, value") -> list[dict[str, Any]]:
    rows = connection.execute(
        f"select {column} as value, count(*) as count from task_index where {where} group by {column} order by {order_by}"
    ).fetchall()
    return [{"value": str(row["value"]), "count": int(row["count"])} for row in rows]


def _mode_count_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        select case when mode = 'generate' then 'generate' else 'edit' end as value, count(*) as count
        from task_index
        where mode != ''
        group by value
        order by case value when 'generate' then 0 else 1 end
        """
    ).fetchall()
    return [{"value": str(row["value"]), "count": int(row["count"])} for row in rows]


def _ratio_count_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = _count_rows(connection, "ratio", "ratio != ''")
    other_count = int(connection.execute("select count(*) from task_index where ratio = ''").fetchone()[0])
    if other_count:
        rows.append({"value": RATIO_OTHER_VALUE, "count": other_count})
    return rows
