from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .schemas import (
    CreatedTask,
    DEFAULT_WEBUI_OUTPUT_ROOT,
    DEFAULT_WEBUI_REFERENCE_FILE_SUBDIR,
)
from .gallery_storage import (
    DEFAULT_GALLERY_CATEGORIES,
    GALLERY_CATEGORIES,
    GalleryStorage,
    _clean_gallery_category,
    _clean_gallery_category_id,
    _clean_gallery_category_name,
    _clean_gallery_name,
    _clean_gallery_prompt_note,
    _clean_gallery_prompt_role,
    _gallery_name_key,
    _normalize_gallery_category,
)
from .reference_assets import (
    MAX_REFERENCE_ASSETS,
    REFERENCE_ASSET_SUFFIXES,
    ReferenceAssetStorage,
    _reference_asset_suffix,
)
from .reference_files import (
    MAX_REFERENCE_FILE_BYTES,
    MAX_REFERENCE_FILES_TOTAL_BYTES,
    ReferenceFileStorage,
)
from .queue_storage import QueueStorage, SQLiteQueueStorage
from .task_index import SQLiteTaskIndex, project_task_generation_snapshot
from .storage_utils import (
    _guess_mime_type,
    _safe_extension,
    _safe_filename,
    _safe_output_relative_path,
    _task_date_directory,
    utc_now,
)
from .thumbnails import create_image_thumbnail, input_thumbnail_filename, output_thumbnail_filename


TASK_SOURCE_DATA_SUBDIR = "tasks"
TASK_SOURCE_DATA_SUFFIXES = ("metadata.json", "request.json", "debug-sse.jsonl")
DIMENSION_SIZE_RE = re.compile(r"^\s*(\d{1,5})\s*[xX×]\s*(\d{1,5})\s*$")


class TaskStorage:
    def __init__(
        self,
        output_root: Path | str = DEFAULT_WEBUI_OUTPUT_ROOT,
        *,
        input_root: Path | str | None = None,
        source_data_root: Path | str | None = None,
    ) -> None:
        self.output_root = Path(output_root)
        self.input_root = Path(input_root) if input_root is not None else self.output_root.parent / "webui-inputs"
        self.source_data_root = Path(source_data_root) if source_data_root is not None else self.output_root / "source-data"
        # `root` is kept as a compatibility alias for existing app code while
        # paths are migrated to the explicit roots above.
        self.root = self.output_root
        self.task_index = SQLiteTaskIndex(self.source_data_root / "webui-task-index.db")

    def create_task(self, mode: str) -> CreatedTask:
        task_id = datetime.now(UTC).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
        self.input_root.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.source_data_root.mkdir(parents=True, exist_ok=True)
        task_source_dir = self._task_source_data_dir(task_id)
        task_source_dir.mkdir(parents=True, exist_ok=True)
        return CreatedTask(task_id=task_id, path=task_source_dir, mode=mode)

    def write_metadata(self, task_id: str, metadata: dict[str, Any]) -> Path:
        path = self.metadata_path(task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        self.task_index.upsert(metadata)
        return path

    def read_metadata(self, task_id: str) -> dict[str, Any]:
        path = self.metadata_path(task_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def write_request(self, task_id: str, request: dict[str, Any]) -> Path:
        path = self.request_path(task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(request, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def write_input(self, task_id: str, filename: str, data: bytes, *, kind: str = "input", index: int | None = None) -> Path:
        if kind not in {"input", "mask"}:
            raise ValueError("Input kind must be input or mask")
        self._validate_task_id(task_id)
        next_index = index if index is not None else self._next_input_index(task_id, kind)
        prefix = f"{task_id}-{kind}-{next_index:02d}-"
        safe_name = _safe_filename(filename, max_bytes=255 - len(prefix.encode("utf-8")))
        path = self.input_root / f"{prefix}{safe_name}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if kind == "input":
            create_image_thumbnail(path, self.input_thumbnail_path(task_id, next_index))
        return path

    def write_output(self, task_id: str, data: bytes, output_format: str, *, index: int | None = None) -> Path:
        self._validate_task_id(task_id)
        suffix = _safe_extension(output_format)
        output_index = index if index is not None else 1
        filename = f"{task_id}-image-{output_index}.{suffix}"
        path = self.output_root / _task_date_directory(task_id) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def delete_task(self, task_id: str) -> None:
        self._validate_task_id(task_id)
        thumbnail_root = self.output_root / "thumbnails"
        output_paths = []
        if self.output_root.exists():
            output_paths = [
                path for path in self.output_root.rglob(f"{task_id}-*")
                if path.is_file()
                and not path.is_relative_to(thumbnail_root)
                and not path.is_relative_to(self.source_data_root)
            ]
        thumbnail_paths = list(thumbnail_root.rglob(f"{task_id}-*-thumb.*")) if thumbnail_root.exists() else []
        paths = [
            *self.input_root.glob(f"{task_id}-input-*"),
            *self.input_root.glob(f"{task_id}-mask-*"),
            *output_paths,
            *thumbnail_paths,
            *self._task_source_data_paths(task_id),
        ]
        if not paths:
            raise FileNotFoundError(task_id)
        output_dirs = {path.parent for path in [*output_paths, *thumbnail_paths]}
        source_data_dirs = {path.parent for path in self._task_source_data_paths(task_id)}
        for path in paths:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        self.task_index.delete(task_id)
        for path in output_dirs:
            self._prune_empty_output_dir(path)
        for path in source_data_dirs:
            self._prune_empty_source_data_dir(path)

    def list_tasks(self) -> list[dict[str, Any]]:
        indexed_tasks = self.task_index.list_summaries()
        if indexed_tasks:
            return indexed_tasks
        if not self.source_data_root.exists():
            return []
        return self.rebuild_task_index()

    def list_recent_tasks(self, limit: int = 200) -> list[dict[str, Any]]:
        indexed_tasks = self.task_index.list_summaries(limit=limit)
        if indexed_tasks:
            return indexed_tasks
        return self.rebuild_task_index()[: max(0, limit)]

    def list_recent_task_cards(self, limit: int = 200) -> list[dict[str, Any]]:
        indexed_tasks = self.task_index.list_summaries(limit=limit)
        if not indexed_tasks:
            indexed_tasks = self.rebuild_task_index()[: max(0, limit)]
        return [_sidebar_task_card(task) for task in indexed_tasks]

    def task_sidebar_card(self, task_id: str) -> dict[str, Any]:
        return _sidebar_task_card(self.read_metadata(task_id))

    def task_history_summary(self) -> dict[str, Any]:
        self.refresh_stale_task_index()
        return self.task_index.history_summary()

    def query_task_history(
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
        self.refresh_stale_task_index()
        return self.task_index.query_history(
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
            sort=sort,
            direction=direction,
        )

    def refresh_stale_task_index(self, *, limit: int = 500) -> int:
        refreshed = 0
        for task_id in self.task_index.stale_completed_task_ids(limit=limit):
            try:
                metadata = self.read_metadata(task_id)
            except (FileNotFoundError, OSError, json.JSONDecodeError):
                continue
            if not isinstance(metadata, dict):
                continue
            metadata["task_id"] = str(metadata.get("task_id") or task_id)
            self.task_index.upsert(metadata)
            refreshed += 1
        return refreshed

    def rebuild_task_index(self) -> list[dict[str, Any]]:
        if not self.source_data_root.exists():
            return []
        return self._list_tasks_from_metadata(list(self.iter_metadata_paths()))

    def iter_metadata_paths(self) -> list[Path]:
        if not self.source_data_root.exists():
            return []
        flat_paths = list(self.source_data_root.glob("*.metadata.json"))
        sharded_root = self.source_data_root / TASK_SOURCE_DATA_SUBDIR
        sharded_paths = list(sharded_root.glob("*/*.metadata.json")) if sharded_root.exists() else []
        return [*flat_paths, *sharded_paths]

    def migrate_source_data_files(self) -> dict[str, int]:
        self.source_data_root.mkdir(parents=True, exist_ok=True)
        result = {
            "moved": 0,
            "metadata_moved": 0,
            "request_moved": 0,
            "debug_sse_moved": 0,
            "skipped": 0,
            "duplicates_removed": 0,
        }
        for suffix in TASK_SOURCE_DATA_SUFFIXES:
            pattern = f"*.{suffix}"
            for legacy_path in sorted(self.source_data_root.glob(pattern)):
                task_id = legacy_path.name.removesuffix(f".{suffix}")
                try:
                    target_path = self._sharded_source_data_path(task_id, suffix)
                except ValueError:
                    result["skipped"] += 1
                    continue
                if legacy_path == target_path:
                    continue
                target_path.parent.mkdir(parents=True, exist_ok=True)
                if target_path.exists():
                    if _same_file_bytes(legacy_path, target_path):
                        try:
                            legacy_path.unlink()
                            result["duplicates_removed"] += 1
                        except OSError:
                            result["skipped"] += 1
                    else:
                        result["skipped"] += 1
                    continue
                try:
                    legacy_path.replace(target_path)
                except OSError:
                    result["skipped"] += 1
                    continue
                result["moved"] += 1
                if suffix == "metadata.json":
                    result["metadata_moved"] += 1
                    try:
                        metadata = json.loads(target_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    if isinstance(metadata, dict):
                        self.task_index.upsert(metadata)
                elif suffix == "request.json":
                    result["request_moved"] += 1
                elif suffix == "debug-sse.jsonl":
                    result["debug_sse_moved"] += 1
        return result

    def _list_tasks_from_metadata(self, metadata_paths: list[Path]) -> list[dict[str, Any]]:
        tasks_by_id: dict[str, dict[str, Any]] = {}
        for metadata_path in metadata_paths:
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            task_id = str(metadata.get("task_id") or metadata_path.name.removesuffix(".metadata.json"))
            if not task_id:
                continue
            metadata["task_id"] = task_id
            self.task_index.upsert(metadata)
            tasks_by_id[task_id] = metadata

        return sorted(tasks_by_id.values(), key=lambda task: str(task.get("created_at", "")), reverse=True)

    def metadata_path(self, task_id: str) -> Path:
        return self._source_data_path(task_id, "metadata.json")

    def request_path(self, task_id: str) -> Path:
        return self._source_data_path(task_id, "request.json")

    def debug_sse_path(self, task_id: str) -> Path:
        return self._source_data_path(task_id, "debug-sse.jsonl")

    def input_path(self, filename: str) -> Path:
        return self.input_root / Path(filename).name

    def output_path(self, filename: str) -> Path:
        return self.output_root / _safe_output_relative_path(filename)

    def output_file(self, path: Path) -> str:
        try:
            return path.resolve(strict=False).relative_to(self.output_root.resolve(strict=False)).as_posix()
        except ValueError:
            return path.name

    def output_thumbnail_path(self, task_id: str, output_index: int) -> Path:
        self._validate_task_id(task_id)
        return self.output_root / "thumbnails" / _task_date_directory(task_id) / output_thumbnail_filename(task_id, output_index)

    def input_thumbnail_path(self, task_id: str, input_index: int) -> Path:
        self._validate_task_id(task_id)
        return self.output_root / "thumbnails" / _task_date_directory(task_id) / input_thumbnail_filename(task_id, input_index)

    def _source_data_path(self, task_id: str, suffix: str) -> Path:
        legacy_path = self._legacy_source_data_path(task_id, suffix)
        sharded_path = self._sharded_source_data_path(task_id, suffix)
        if legacy_path.exists() and not sharded_path.exists():
            return legacy_path
        return sharded_path

    def _legacy_source_data_path(self, task_id: str, suffix: str) -> Path:
        self._validate_task_id(task_id)
        if suffix not in TASK_SOURCE_DATA_SUFFIXES:
            raise ValueError("Invalid source data suffix")
        return self.source_data_root / f"{task_id}.{suffix}"

    def _sharded_source_data_path(self, task_id: str, suffix: str) -> Path:
        self._validate_task_id(task_id)
        if suffix not in TASK_SOURCE_DATA_SUFFIXES:
            raise ValueError("Invalid source data suffix")
        return self._task_source_data_dir(task_id) / f"{task_id}.{suffix}"

    def _task_source_data_dir(self, task_id: str) -> Path:
        self._validate_task_id(task_id)
        return self.source_data_root / TASK_SOURCE_DATA_SUBDIR / _task_date_directory(task_id)

    def _task_source_data_paths(self, task_id: str) -> list[Path]:
        paths: list[Path] = []
        for suffix in TASK_SOURCE_DATA_SUFFIXES:
            paths.append(self._legacy_source_data_path(task_id, suffix))
            paths.append(self._sharded_source_data_path(task_id, suffix))
        return paths

    def _next_input_index(self, task_id: str, kind: str) -> int:
        existing = list(self.input_root.glob(f"{task_id}-{kind}-*-*"))
        return len(existing) + 1

    def _validate_task_id(self, task_id: str) -> None:
        if not task_id or "/" in task_id or "\\" in task_id:
            raise ValueError("Invalid task id")

    def _prune_empty_output_dir(self, path: Path) -> None:
        if path == self.output_root:
            return
        try:
            path.relative_to(self.output_root)
        except ValueError:
            return
        try:
            path.rmdir()
        except OSError:
            pass

    def _prune_empty_source_data_dir(self, path: Path) -> None:
        if path in {self.source_data_root, self.source_data_root / TASK_SOURCE_DATA_SUBDIR}:
            return
        try:
            path.relative_to(self.source_data_root / TASK_SOURCE_DATA_SUBDIR)
        except ValueError:
            return
        try:
            path.rmdir()
        except OSError:
            return
        try:
            (self.source_data_root / TASK_SOURCE_DATA_SUBDIR).rmdir()
        except OSError:
            pass


def _sidebar_task_card(metadata: dict[str, Any]) -> dict[str, Any]:
    task_id = str(metadata.get("task_id") or "")
    params = metadata.get("params") if isinstance(metadata.get("params"), dict) else {}
    generation_snapshot = project_task_generation_snapshot(metadata.get("generation_snapshot"))
    size = _sidebar_display_size(metadata, params)
    requested_size = _sidebar_requested_size(params) or size
    thumbnail_url = _first_sidebar_thumbnail_url(metadata)
    card = {
        "task_id": task_id,
        "summary_only": True,
        "created_at": metadata.get("created_at") or "",
        "updated_at": metadata.get("updated_at") or "",
        "viewed_at": metadata.get("viewed_at") or "",
        "queued_at": metadata.get("queued_at") or "",
        "started_at": metadata.get("started_at") or "",
        "attempt_started_at": metadata.get("attempt_started_at") or "",
        "completed_at": metadata.get("completed_at") or "",
        "archived_at": metadata.get("archived_at") or "",
        "status": metadata.get("status") or "",
        "mode": metadata.get("mode") or "",
        "prompt": _truncate_text(metadata.get("prompt") or metadata.get("prompt_for_model") or "", 260),
        "output_size": size,
        "params": {
            "size": requested_size,
            "ratio": params.get("ratio") or "",
            "resolution": params.get("resolution") or "",
            "orientation": params.get("orientation") or "",
            "n": _nonnegative_int(metadata.get("total_count") or params.get("n") or 1, 1),
            "prompt_fidelity": params.get("prompt_fidelity") or "",
            "api_provider_id": params.get("api_provider_id") or "",
            "api_provider_name": params.get("api_provider_name") or "",
        },
        "generation_snapshot": generation_snapshot,
        "backend": metadata.get("backend") or metadata.get("requested_backend") or "",
        "requested_backend": metadata.get("requested_backend") or metadata.get("backend") or "",
        "api_provider_id": metadata.get("api_provider_id") or params.get("api_provider_id") or "",
        "api_provider_name": metadata.get("api_provider_name") or params.get("api_provider_name") or "",
        "generated_count": _nonnegative_int(metadata.get("generated_count"), 0),
        "failed_count": _nonnegative_int(metadata.get("failed_count"), 0),
        "total_count": _nonnegative_int(metadata.get("total_count") or params.get("n"), 1),
        "attempts": _nonnegative_int(metadata.get("attempts"), 0),
        "max_attempts": _nonnegative_int(metadata.get("max_attempts"), 0),
        "last_error": metadata.get("last_error") or metadata.get("error") or "",
        "error": metadata.get("error") or "",
        "retrying_failed_slots": metadata.get("retrying_failed_slots") if isinstance(metadata.get("retrying_failed_slots"), list) else [],
        "input_thumbnail_urls": _sidebar_input_thumbnail_urls(metadata),
        "thumbnail_urls": [thumbnail_url] if thumbnail_url else [],
    }
    return {key: value for key, value in card.items() if value not in ("", [], {}) or key in {"task_id", "summary_only", "params"}}


def _sidebar_display_size(metadata: dict[str, Any], params: dict[str, Any]) -> str:
    for value in (
        metadata.get("output_size"),
        _first_dimension_list_value(metadata.get("output_sizes")),
        _first_output_dimension_value(metadata),
        params.get("size"),
    ):
        size = _normalize_dimension_size(value)
        if size:
            return size
    requested_size = str(params.get("size") or "")
    return requested_size if requested_size and not requested_size.isdigit() else ""


def _sidebar_requested_size(params: dict[str, Any]) -> str:
    return _normalize_dimension_size(params.get("size"))


def _normalize_dimension_size(value: Any) -> str:
    match = DIMENSION_SIZE_RE.match(str(value or ""))
    if not match:
        return ""
    width = int(match.group(1))
    height = int(match.group(2))
    if width <= 0 or height <= 0:
        return ""
    return f"{width}x{height}"


def _first_dimension_list_value(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    for item in value:
        size = _normalize_dimension_size(item)
        if size:
            return size
    return ""


def _first_output_dimension_value(metadata: dict[str, Any]) -> str:
    outputs = metadata.get("outputs")
    if not isinstance(outputs, list):
        return ""
    for output in outputs:
        if not isinstance(output, dict):
            continue
        size = _normalize_dimension_size(output.get("size"))
        if size:
            return size
    return ""


def _sidebar_input_thumbnail_urls(metadata: dict[str, Any]) -> list[str]:
    urls = metadata.get("input_thumbnail_urls")
    if isinstance(urls, list):
        clean_urls = [str(url) for url in urls if url]
        if clean_urls:
            return clean_urls
    input_sources = metadata.get("input_sources")
    if isinstance(input_sources, list):
        source_urls: list[str] = []
        for source in input_sources:
            if not isinstance(source, dict) or source.get("missing"):
                continue
            url = source.get("thumbnail_url") or source.get("image_url")
            if url:
                source_urls.append(str(url))
        if source_urls:
            return source_urls
    task_id = str(metadata.get("task_id") or "")
    input_files = metadata.get("input_files")
    if not task_id or not isinstance(input_files, list):
        return []
    return [f"/api/tasks/{task_id}/inputs/{index}/thumbnail" for index, _ in enumerate(input_files, start=1)]


def _first_sidebar_thumbnail_url(metadata: dict[str, Any]) -> str:
    thumbnail_route = _first_output_thumbnail_route(metadata)
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
            if not isinstance(output, dict):
                continue
            thumbnail_url = output.get("thumbnail_url") or _output_file_url(output.get("thumbnail_file"))
            if thumbnail_url:
                return thumbnail_url
    task_id = str(metadata.get("task_id") or "")
    output_files = metadata.get("output_files")
    if task_id and isinstance(output_files, list) and output_files:
        return f"/api/tasks/{task_id}/outputs/1/thumbnail"
    output_file = metadata.get("output_file")
    if task_id and output_file:
        return f"/api/tasks/{task_id}/outputs/1/thumbnail"
    return ""


def _first_output_thumbnail_route(metadata: dict[str, Any]) -> str:
    task_id = str(metadata.get("task_id") or "")
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
    output_file = metadata.get("output_file")
    if output_file:
        return f"/api/tasks/{task_id}/outputs/1/thumbnail"
    if _is_local_output_url(metadata.get("output_url")):
        return f"/api/tasks/{task_id}/outputs/1/thumbnail"
    return ""


def _is_local_output_url(value: Any) -> bool:
    return str(value or "").startswith("/outputs/")


def _output_file_url(filename: Any) -> str:
    parts = [part for part in str(filename or "").split("/") if part]
    return "/outputs/" + "/".join(parts) if parts else ""


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _truncate_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _nonnegative_int(value: Any, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return number if number >= 0 else fallback


def _same_file_bytes(first: Path, second: Path) -> bool:
    try:
        return first.read_bytes() == second.read_bytes()
    except OSError:
        return False
