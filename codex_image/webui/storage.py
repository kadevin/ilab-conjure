from __future__ import annotations

from .storage_metadata_scan import SourceMetadataScanner
from .task_card_projection import (
    _sidebar_task_card,
    _sidebar_display_size,
    _sidebar_requested_size,
    _normalize_dimension_size,
    _first_dimension_list_value,
    _first_output_dimension_value,
    _sidebar_input_thumbnail_urls,
    _first_sidebar_thumbnail_url,
    _first_output_thumbnail_route,
    _is_local_output_url,
    _output_file_url,
    _positive_int,
    _truncate_text,
    _nonnegative_int,
)

import hashlib
import json
import os
import re
import shutil
import stat
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from collections.abc import Callable

from .atomic_files import _fsync_parent, atomic_write_bytes, atomic_write_text
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
from .history_organizer import HistoryOrganization, HistoryOrganizer
from .history_query import HistoryQueryService
from .task_index import TERMINAL_TASK_STATUSES, SQLiteTaskIndex, project_task_generation_snapshot
from .storage_utils import (
    _guess_mime_type,
    _safe_extension,
    _safe_filename,
    _safe_output_relative_path,
    _task_date_directory,
    utc_now,
)
from .thumbnails import (
    create_image_thumbnail,
    input_thumbnail_filename,
    output_sidebar_thumbnail_filename,
    output_thumbnail_filename,
)


TASK_SOURCE_DATA_SUBDIR = "tasks"
TASK_SOURCE_DATA_SUFFIXES = ("metadata.json", "request.json", "debug-sse.jsonl")
DIMENSION_SIZE_RE = re.compile(r"^\s*(\d{1,5})\s*[xX×]\s*(\d{1,5})\s*$")


@dataclass(frozen=True)
class RestoredTaskBinary:
    role: str
    source_index: int
    filename: str
    data: bytes | None = None
    staged_path: Path | None = None
    expected_size: int | None = None
    expected_sha256: str | None = None


@dataclass(frozen=True)
class RestoredTaskFilesPlan:
    task_id: str
    metadata: dict[str, Any]
    request: dict[str, Any]
    binaries: tuple[RestoredTaskBinary, ...]
    staging_root: Path | None = None
    failure_injector: Any = None


@dataclass(frozen=True)
class RestoredTaskFilesJournal:
    task_id: str
    created_paths: tuple[Path, ...]
    restore_token: str | None = None


@dataclass(frozen=True)
class RestoredTaskRollbackJournal:
    task_id: str
    restore_token: str | None = None
    pending_paths: tuple[Path, ...] = ()
    index_pending: bool = False
    pending_resources: tuple[dict[str, Any], ...] = ()
    pending_staging_paths: tuple[Path, ...] = ()
    organization_pending: bool = False
    ownership_pending: bool = True


class RestoredTaskRollbackIncomplete(RuntimeError):
    def __init__(self, journal: RestoredTaskRollbackJournal) -> None:
        self.journal = journal
        super().__init__("backup_import_restore_rollback_incomplete")


class HistoryTaskNotFoundError(ValueError):
    def __init__(self, task_ids: list[str]) -> None:
        self.task_ids = tuple(task_ids)
        super().__init__("Task not found: " + ", ".join(self.task_ids))


def _normalized_history_task_ids(
    task_ids: list[str],
    *,
    maximum: int = 300,
) -> list[str]:
    normalized = list(
        dict.fromkeys(
            task_id
            for value in task_ids
            if (task_id := str(value or "").strip())
        )
    )
    if not normalized:
        raise ValueError("At least one task id is required")
    if len(normalized) > maximum:
        raise ValueError(
            f"At most {maximum} tasks can be organized at once"
        )
    return normalized


class TaskStorage:
    def _metadata_scanner(self) -> SourceMetadataScanner:
        return SourceMetadataScanner(
            self.source_data_root, self._source_data_trust_root,
            self._source_data_trust_identity,
        )

    def __init__(
        self,
        output_root: Path | str = DEFAULT_WEBUI_OUTPUT_ROOT,
        *,
        input_root: Path | str | None = None,
        source_data_root: Path | str | None = None,
        legacy_task_roots: list[Path | str] | tuple[Path | str, ...] = (),
    ) -> None:
        self.output_root = Path(output_root)
        self.input_root = Path(input_root) if input_root is not None else self.output_root.parent / "webui-inputs"
        self.source_data_root = Path(source_data_root) if source_data_root is not None else self.output_root / "source-data"
        self.legacy_task_roots = tuple(dict.fromkeys(Path(root) for root in legacy_task_roots))
        # `root` is kept as a compatibility alias for existing app code while
        # paths are migrated to the explicit roots above.
        self.root = self.output_root
        self.task_index = SQLiteTaskIndex(self.source_data_root / "webui-task-index.db")
        self.history_organizer = HistoryOrganizer(
            self.source_data_root / "webui-history-organizer.db"
        )
        self.history_query = HistoryQueryService(
            self.task_index,
            self.history_organizer,
        )
        trust_root = self.source_data_root.resolve(strict=True)
        trust_stat = trust_root.stat()
        if not stat.S_ISDIR(trust_stat.st_mode):
            raise OSError("backup_restore_reference_scan_invalid")
        self._source_data_trust_root = trust_root
        self._source_data_trust_identity = (trust_stat.st_dev, trust_stat.st_ino)
        self._history_organization_lock = threading.RLock()
        self._task_index_repair_lock = threading.Lock()
        self._task_write_locks = tuple(threading.RLock() for _ in range(64))

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
        with self._task_write_lock(task_id):
            _preserve_sticky_task_cancellation(path, metadata)
            _stabilize_task_terminal_timestamp(path, metadata)
            atomic_write_text(
                path,
                json.dumps(metadata, indent=2, ensure_ascii=False),
                mode=0o600,
            )
            self.task_index.upsert(metadata)
        return path

    def read_metadata(self, task_id: str) -> dict[str, Any]:
        path = self.metadata_path(task_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def mutate_metadata(
        self, task_id: str, mutate: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        """Read, edit and persist a current task under one writer lock."""
        self._validate_task_id(task_id)
        with self._task_write_lock(task_id):
            metadata = self.read_metadata(task_id)
            mutate(metadata)
            self.write_metadata(task_id, metadata)
            return metadata

    def write_request(self, task_id: str, request: dict[str, Any]) -> Path:
        path = self.request_path(task_id)
        atomic_write_text(
            path,
            json.dumps(request, indent=2, ensure_ascii=False),
            mode=0o600,
        )
        return path

    def write_input(self, task_id: str, filename: str, data: bytes, *, kind: str = "input", index: int | None = None) -> Path:
        if kind not in {"input", "mask"}:
            raise ValueError("Input kind must be input or mask")
        self._validate_task_id(task_id)
        next_index = index if index is not None else self._next_input_index(task_id, kind)
        prefix = f"{task_id}-{kind}-{next_index:02d}-"
        safe_name = _safe_filename(filename, max_bytes=255 - len(prefix.encode("utf-8")))
        path = self.input_root / f"{prefix}{safe_name}"
        atomic_write_bytes(path, data, mode=0o600)
        if kind == "input":
            create_image_thumbnail(path, self.input_thumbnail_path(task_id, next_index))
        return path

    def write_output(self, task_id: str, data: bytes, output_format: str, *, index: int | None = None) -> Path:
        self._validate_task_id(task_id)
        suffix = _safe_extension(output_format)
        output_index = index if index is not None else 1
        filename = f"{task_id}-image-{output_index}.{suffix}"
        path = self.output_root / _task_date_directory(task_id) / filename
        atomic_write_bytes(path, data, mode=0o600)
        return path

    def _task_write_lock(self, task_id: str) -> threading.RLock:
        return self._task_write_locks[hash(task_id) % len(self._task_write_locks)]

    def restore_task_files(self, plan: RestoredTaskFilesPlan) -> RestoredTaskFilesJournal:
        if not isinstance(plan, RestoredTaskFilesPlan):
            raise ValueError("backup_restore_plan_invalid")
        task_id = plan.task_id
        self._validate_task_id(task_id)
        staged: list[tuple[Path, Path]] = []
        created: list[Path] = []
        restore_token = uuid.uuid4().hex
        with self._task_write_lock(task_id):
            if self.metadata_path(task_id).exists() or task_id in self.task_index.existing_task_ids([task_id]):
                raise ValueError("backup_restore_task_exists")
            finals: list[Path] = []
            for binary in plan.binaries:
                if binary.role in {"input", "mask"}:
                    prefix = f"{task_id}-{binary.role}-{binary.source_index:02d}-"
                    safe_name = _safe_filename(binary.filename, max_bytes=255 - len(prefix.encode("utf-8")))
                    final = self.input_root / f"{prefix}{safe_name}"
                elif binary.role == "output":
                    suffix = _safe_extension(Path(binary.filename).suffix.lstrip("."))
                    final = self.output_root / _task_date_directory(task_id) / f"{task_id}-image-{binary.source_index}.{suffix}"
                else:
                    raise ValueError("backup_restore_binary_role_invalid")
                finals.append(final)
            finals.extend((self.request_path(task_id), self.metadata_path(task_id)))
            if len(set(finals)) != len(finals) or any(path.exists() for path in finals):
                raise ValueError("backup_restore_target_exists")
            self._write_restore_ownership(task_id, restore_token)
            try:
                for binary, final in zip(plan.binaries, finals):
                    final.parent.mkdir(parents=True, exist_ok=True)
                    temporary = final.with_name(f".{final.name}.{uuid.uuid4().hex}.restore.tmp")
                    staged.append((temporary, final))
                    if binary.staged_path is not None:
                        if binary.data is not None:
                            raise ValueError("backup_restore_staged_binary_invalid")
                        source_path = self._validated_restore_staged_path(
                            binary,
                            plan.staging_root,
                        )
                        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                        source_descriptor = -1
                        try:
                            source_descriptor = os.open(
                                source_path,
                                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                            )
                            source_stat = os.fstat(source_descriptor)
                            if not stat.S_ISREG(source_stat.st_mode):
                                raise ValueError("backup_restore_staged_binary_invalid")
                            if source_stat.st_size != binary.expected_size:
                                raise ValueError("backup_restore_staged_binary_changed")
                            digest = hashlib.sha256()
                            actual_size = 0
                            with os.fdopen(descriptor, "wb") as destination, os.fdopen(source_descriptor, "rb") as source:
                                descriptor = -1
                                source_descriptor = -1
                                while chunk := source.read(1024 * 1024):
                                    actual_size += len(chunk)
                                    if actual_size > binary.expected_size:
                                        raise ValueError("backup_restore_staged_binary_changed")
                                    digest.update(chunk)
                                    destination.write(chunk)
                                destination.flush()
                                os.fsync(destination.fileno())
                            if (
                                actual_size != binary.expected_size
                                or digest.hexdigest() != binary.expected_sha256
                            ):
                                raise ValueError("backup_restore_staged_binary_changed")
                        finally:
                            if descriptor >= 0:
                                os.close(descriptor)
                            if source_descriptor >= 0:
                                os.close(source_descriptor)
                    elif isinstance(binary.data, bytes):
                        atomic_write_bytes(temporary, binary.data, mode=0o600)
                    else:
                        raise ValueError("backup_restore_staged_binary_invalid")
                if plan.failure_injector is not None:
                    plan.failure_injector("after_binary_staging")
                for temporary, final in staged:
                    if final.exists():
                        raise ValueError("backup_restore_target_exists")
                    temporary.replace(final)
                    _fsync_parent(final)
                    created.append(final)
                self.write_request(task_id, plan.request)
                created.append(self.request_path(task_id))
                self.write_metadata(task_id, plan.metadata)
                created.append(self.metadata_path(task_id))
                if plan.failure_injector is not None:
                    plan.failure_injector("after_metadata_write")
                return RestoredTaskFilesJournal(
                    task_id=task_id,
                    created_paths=tuple(created),
                    restore_token=restore_token,
                )
            except Exception:
                for source_path in (self.request_path(task_id), self.metadata_path(task_id)):
                    if source_path.exists() and source_path not in created:
                        created.append(source_path)
                self.rollback_restored_task_files(
                    RestoredTaskFilesJournal(
                        task_id=task_id,
                        created_paths=tuple(created),
                        restore_token=restore_token,
                    )
                )
                raise
            finally:
                for temporary, _ in staged:
                    temporary.unlink(missing_ok=True)

    def rollback_restored_task_files(
        self,
        journal: RestoredTaskFilesJournal,
    ) -> RestoredTaskRollbackJournal:
        if not isinstance(journal, RestoredTaskFilesJournal):
            return RestoredTaskRollbackJournal("")
        pending_paths: list[Path] = []
        index_pending = False
        with self._task_write_lock(journal.task_id):
            if not self.restore_ownership_matches(journal.task_id, journal.restore_token):
                raise RestoredTaskRollbackIncomplete(RestoredTaskRollbackJournal(
                    task_id=journal.task_id,
                    restore_token=journal.restore_token,
                    pending_paths=journal.created_paths,
                    index_pending=True,
                    ownership_pending=True,
                ))
            for path in reversed(journal.created_paths):
                try:
                    self._unlink_restored_task_path(journal.task_id, path)
                except OSError:
                    if path.exists() or path.is_symlink():
                        pending_paths.append(path)
            try:
                self.task_index.delete(journal.task_id)
            except Exception:
                index_pending = True
            for path in journal.created_paths:
                try:
                    if path.parent.is_relative_to(self.output_root):
                        self._prune_empty_output_dir(path.parent)
                    if path.parent.is_relative_to(self.source_data_root / TASK_SOURCE_DATA_SUBDIR):
                        self._prune_empty_source_data_dir(path.parent)
                except OSError:
                    pass
        pending = RestoredTaskRollbackJournal(
            task_id=journal.task_id,
            restore_token=journal.restore_token,
            pending_paths=tuple(reversed(pending_paths)),
            index_pending=index_pending,
            ownership_pending=True,
        )
        if pending.pending_paths or pending.index_pending:
            raise RestoredTaskRollbackIncomplete(pending)
        return pending

    def restore_ownership_path(self, task_id: str) -> Path:
        self._validate_task_id(task_id)
        return self._task_source_data_dir(task_id) / f"{task_id}.restore-owner"

    def _write_restore_ownership(self, task_id: str, token: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{32}", token):
            raise ValueError("backup_restore_token_invalid")
        atomic_write_text(self.restore_ownership_path(task_id), token, mode=0o600)

    def restore_ownership_matches(self, task_id: str, token: object) -> bool:
        if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
            return False
        try:
            return self.restore_ownership_path(task_id).read_text(encoding="utf-8") == token
        except (OSError, ValueError):
            return False

    def clear_restore_ownership(self, task_id: str, token: object) -> bool:
        with self._task_write_lock(task_id):
            if not self.restore_ownership_matches(task_id, token):
                return False
            path = self.restore_ownership_path(task_id)
            path.unlink(missing_ok=True)
            _fsync_parent(path)
            return True

    def release_restore_ownership(self, task_id: str, token: object) -> bool:
        if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
            return True
        with self._task_write_lock(task_id):
            path = self.restore_ownership_path(task_id)
            try:
                current = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                return True
            except OSError:
                return False
            if current != token:
                return True
            try:
                path.unlink()
                _fsync_parent(path)
            except OSError:
                return False
            return True

    def _unlink_restored_task_path(self, task_id: str, path: Path) -> None:
        candidate = Path(path)
        if not candidate.is_absolute() or candidate.is_symlink():
            raise OSError("backup_restore_path_invalid")
        allowed_roots = (self.input_root, self.output_root, self.source_data_root)
        lexical_root = next(
            (Path(os.path.abspath(root)) for root in allowed_roots if candidate.is_relative_to(Path(os.path.abspath(root)))),
            None,
        )
        if lexical_root is None:
            raise OSError("backup_restore_path_invalid")
        relative = candidate.relative_to(lexical_root)
        cursor = lexical_root
        for part in relative.parts[:-1]:
            cursor /= part
            if cursor.is_symlink():
                raise OSError("backup_restore_path_invalid")
        resolved_parent = candidate.parent.resolve(strict=True)
        if not resolved_parent.is_relative_to(lexical_root.resolve(strict=True)):
            raise OSError("backup_restore_path_invalid")
        name = candidate.name
        if not (
            candidate in {self.metadata_path(task_id), self.request_path(task_id)}
            or name.startswith(f"{task_id}-input-")
            or name.startswith(f"{task_id}-mask-")
            or name.startswith(f"{task_id}-image-")
        ):
            raise OSError("backup_restore_path_invalid")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(candidate.parent, flags)
        try:
            try:
                mode = os.stat(name, dir_fd=descriptor, follow_symlinks=False).st_mode
            except FileNotFoundError:
                return
            if not stat.S_ISREG(mode):
                raise OSError("backup_restore_path_invalid")
            os.unlink(name, dir_fd=descriptor)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _validated_restore_staged_path(
        binary: RestoredTaskBinary,
        staging_root: Path | None,
    ) -> Path:
        if (
            staging_root is None
            or binary.expected_size is None
            or isinstance(binary.expected_size, bool)
            or binary.expected_size < 0
            or not isinstance(binary.expected_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", binary.expected_sha256)
        ):
            raise ValueError("backup_restore_staged_binary_invalid")
        root = Path(staging_root)
        source = Path(binary.staged_path or "")
        if root.is_symlink() or source.is_symlink():
            raise ValueError("backup_restore_staged_binary_invalid")
        try:
            resolved_root = root.resolve(strict=True)
            resolved_parent = source.parent.resolve(strict=True)
        except OSError as exc:
            raise ValueError("backup_restore_staged_binary_invalid") from exc
        if not resolved_root.is_dir() or resolved_parent != resolved_root:
            raise ValueError("backup_restore_staged_binary_invalid")
        return source

    def delete_task(self, task_id: str) -> None:
        with self._history_organization_lock, self._task_write_lock(task_id):
            self._delete_task_unlocked(task_id)
            self.history_organizer.delete_task_state(task_id)

    def _delete_task_unlocked(self, task_id: str) -> None:
        self._validate_task_id(task_id)
        # A prefix or an orphan artifact is not authority to delete a task.
        metadata = self.read_metadata(task_id)
        if metadata.get("task_id") != task_id:
            raise ValueError("Task metadata identity mismatch")
        ownership_cache: dict[str, bool] = {}

        def owned_artifact(path: Path) -> bool:
            name = path.name
            if not name.startswith(task_id + "-"):
                return False
            # Historic/imported IDs can themselves contain '-' and '.'. A
            # shorter existing ID must not claim a longer task's files.
            for index in range(len(task_id) + 1, min(len(name), 129)):
                if name[index] not in "-.":
                    continue
                candidate = name[:index]
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", candidate):
                    continue
                if candidate not in ownership_cache:
                    ownership_cache[candidate] = self.metadata_path(candidate).is_file()
                if ownership_cache[candidate]:
                    return False
            return True

        thumbnail_root = self.output_root / "thumbnails"
        output_paths: list[Path] = []
        if self.output_root.exists():
            output_paths = [
                path for path in self.output_root.rglob("*")
                if owned_artifact(path) and path.is_file()
                and not path.is_relative_to(thumbnail_root)
                and not path.is_relative_to(self.source_data_root)
            ]
        thumbnail_paths = (
            [
                path for path in thumbnail_root.rglob("*")
                if owned_artifact(path) and path.is_file()
            ]
            if thumbnail_root.exists()
            else []
        )
        task_source_dir = self._task_source_data_dir(task_id)
        source_data_paths = [
            directory / f"{task_id}.{suffix}"
            for directory in (self.source_data_root, task_source_dir)
            for suffix in (*TASK_SOURCE_DATA_SUFFIXES, "restore-owner")
        ]
        source_data_paths = list(dict.fromkeys(path for path in source_data_paths if path.is_file() or path.is_symlink()))
        metadata_filename = f"{task_id}.metadata.json"
        metadata_paths = [path for path in source_data_paths if path.name == metadata_filename]
        nonmetadata_source_paths = [path for path in source_data_paths if path.name != metadata_filename]
        artifact_paths = list(dict.fromkeys([
            *(path for path in self.input_root.glob("*")
              if owned_artifact(path) and path.name.startswith((f"{task_id}-input-", f"{task_id}-mask-"))),
            *output_paths,
            *thumbnail_paths,
            *nonmetadata_source_paths,
        ]))
        legacy_task_entries = list(dict.fromkeys(
            root / task_id
            for root in self.legacy_task_roots
            if (root / task_id).exists() or (root / task_id).is_symlink()
        ))
        if not artifact_paths and not metadata_paths and not legacy_task_entries:
            raise FileNotFoundError(task_id)
        # Check every boundary before the first mutation, including legacy
        # directories and symlinked shard directories.
        for path in [*artifact_paths, *metadata_paths]:
            roots = (self.input_root, self.output_root, self.source_data_root)
            if not any(path.resolve().is_relative_to(root.resolve()) and path.resolve() != root.resolve() for root in roots):
                raise ValueError("Task artifact escapes storage roots")
        for path in legacy_task_entries:
            root = path.parent.resolve()
            target = path.resolve()
            if target == root or not target.is_relative_to(root):
                raise ValueError("Legacy task directory escapes storage root")
        output_dirs = {path.parent for path in [*output_paths, *thumbnail_paths]}
        source_data_dirs = {path.parent for path in source_data_paths}
        for path in artifact_paths:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        for legacy_task_entry in legacy_task_entries:
            try:
                if legacy_task_entry.is_symlink() or not legacy_task_entry.is_dir():
                    legacy_task_entry.unlink()
                else:
                    shutil.rmtree(legacy_task_entry)
            except FileNotFoundError:
                pass
        for path in metadata_paths:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        self.task_index.delete(task_id)
        for path in output_dirs:
            self._prune_empty_output_dir(path)
        for path in source_data_dirs:
            self._prune_empty_source_data_dir(path)

    def organize_history_tasks(
        self,
        task_ids: list[str],
        *,
        favorite: bool | None,
        add_tag_ids: list[str],
        remove_tag_ids: list[str],
    ) -> dict[str, HistoryOrganization]:
        normalized = _normalized_history_task_ids(task_ids)
        with self._history_organization_lock:
            existing = self.task_index.existing_task_ids(normalized)
            missing = [
                task_id
                for task_id in normalized
                if task_id not in existing
            ]
            if missing:
                raise HistoryTaskNotFoundError(missing)
            return self.history_organizer.organize(
                normalized,
                favorite=favorite,
                add_tag_ids=add_tag_ids,
                remove_tag_ids=remove_tag_ids,
            )

    def history_organizations(
        self,
        task_ids: list[str],
    ) -> dict[str, HistoryOrganization]:
        return self.history_organizer.organizations_for_tasks(task_ids)

    def list_tasks(self) -> list[dict[str, Any]]:
        indexed_tasks = self.task_index.list_summaries()
        if indexed_tasks:
            return indexed_tasks
        if not self.source_data_root.exists():
            return []
        return self.rebuild_task_index()

    def reference_asset_reference_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for task in self.task_index.list_summaries():
            raw_references = task.get("reference_assets")
            if not isinstance(raw_references, list):
                continue
            task_asset_ids: set[str] = set()
            for reference in raw_references:
                if not isinstance(reference, dict):
                    continue
                asset_id = str(reference.get("id") or "")
                if re.fullmatch(r"[0-9a-f]{64}", asset_id):
                    task_asset_ids.add(asset_id)
            for asset_id in task_asset_ids:
                counts[asset_id] = counts.get(asset_id, 0) + 1
        return counts

    def resource_reference_counts(self, kind: str) -> dict[str, int]:
        return {
            resource_id: len(task_ids)
            for resource_id, task_ids in self.resource_referencing_task_ids(kind).items()
        }

    def resource_referencing_task_ids(self, kind: str) -> dict[str, set[str]]:
        if kind not in {"reference_asset", "gallery", "reference_file"}:
            raise ValueError("backup_restore_resource_kind_invalid")
        return self.resource_reference_snapshot()[kind]

    def resource_reference_snapshot(self) -> dict[str, dict[str, set[str]]]:
        fields = {
            "reference_asset": "reference_assets",
            "gallery": "gallery_refs",
            "reference_file": "reference_files",
        }
        snapshot: dict[str, dict[str, set[str]]] = {kind: {} for kind in fields}
        for metadata in self._secure_source_metadata_records():
            if not isinstance(metadata, dict):
                raise OSError("backup_restore_reference_scan_invalid")
            task_id = str(metadata.get("task_id") or "")
            if not task_id:
                raise OSError("backup_restore_reference_scan_invalid")
            for kind, field in fields.items():
                references = metadata.get(field, [])
                if not isinstance(references, list):
                    raise OSError("backup_restore_reference_scan_invalid")
                resource_ids: set[str] = set()
                for reference in references:
                    if not isinstance(reference, dict):
                        raise OSError("backup_restore_reference_scan_invalid")
                    resource_id = str(reference.get("id") or "")
                    if not resource_id:
                        raise OSError("backup_restore_reference_scan_invalid")
                    resource_ids.add(resource_id)
                for resource_id in resource_ids:
                    snapshot[kind].setdefault(resource_id, set()).add(task_id)
        return snapshot

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

    def generation_sidebar_groups(
        self,
        *,
        limit_per_group: int = 50,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        indexed = self.task_index.generation_sidebar_groups(limit_per_group=limit_per_group, now=now)
        return {
            "groups": [
                {
                    **group,
                    "tasks": [_sidebar_task_card(task) for task in group.get("tasks", [])],
                }
                for group in indexed.get("groups", [])
            ]
        }

    def generation_sidebar_group(
        self,
        key: str,
        *,
        offset: int = 0,
        limit: int = 50,
        status: str = "",
        prompt_mode: str = "",
        ratio: str = "",
        orientation: str = "",
        resolution: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        group = self.task_index.generation_sidebar_group(
            key,
            offset=offset,
            limit=limit,
            status=status,
            prompt_mode=prompt_mode,
            ratio=ratio,
            orientation=orientation,
            resolution=resolution,
            now=now,
        )
        return {
            **group,
            "tasks": [_sidebar_task_card(task) for task in group.get("tasks", [])],
        }

    def generation_sidebar_group_task_position(
        self,
        key: str,
        task_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        return self.task_index.generation_sidebar_group_task_position(
            key,
            task_id,
            now=now,
        )

    def generation_sidebar_group_task_ids(
        self,
        key: str,
        *,
        status: str = "",
        prompt_mode: str = "",
        ratio: str = "",
        orientation: str = "",
        resolution: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        return self.task_index.generation_sidebar_group_task_ids(
            key,
            status=status,
            prompt_mode=prompt_mode,
            ratio=ratio,
            orientation=orientation,
            resolution=resolution,
            now=now,
        )

    def task_history_summary(self) -> dict[str, Any]:
        self.refresh_stale_task_index()
        return self.history_query.summary()

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
        favorite: bool | None = None,
        tag_ids: list[str] | None = None,
        untagged: bool = False,
        sort: str = "newest",
        direction: str = "next",
    ) -> dict[str, Any]:
        self.refresh_stale_task_index()
        return self.history_query.query(
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

    def refresh_stale_task_index(self, *, limit: int = 500) -> int:
        with self._task_index_repair_lock:
            refreshed = 0
            for task_id in self.task_index.stale_completed_task_ids(limit=limit):
                # Serialize with metadata writers: a later write resets the attempt
                # marker and must not be hidden by this repair's completion.
                with self._task_write_lock(task_id):
                    try:
                        metadata = self.read_metadata(task_id)
                    except (FileNotFoundError, json.JSONDecodeError):
                        self.task_index.mark_repair_attempted(task_id)
                        continue
                    except OSError:
                        # Transient I/O failures may recover without a metadata write.
                        continue
                    if isinstance(metadata, dict):
                        metadata["task_id"] = str(metadata.get("task_id") or task_id)
                        self.task_index.upsert(metadata, repair_attempted=True)
                        refreshed += 1
                    else:
                        self.task_index.mark_repair_attempted(task_id)
            return refreshed

    def rebuild_task_index(self) -> list[dict[str, Any]]:
        if not self.source_data_root.exists():
            return []
        return self._list_tasks_from_metadata(list(self.iter_metadata_paths()))

    def read_tasks_from_metadata(self) -> list[dict[str, Any]]:
        if not self.source_data_root.exists():
            return []
        return self._list_tasks_from_metadata(
            list(self.iter_metadata_paths()),
            update_index=False,
        )

    def iter_metadata_paths(self) -> list[Path]:
        if not self.source_data_root.exists():
            return []
        legacy = sorted(
            self.source_data_root.glob("*.metadata.json"),
            key=lambda path: path.as_posix(),
        )
        sharded_root = self.source_data_root / TASK_SOURCE_DATA_SUBDIR
        sharded = sorted(
            sharded_root.glob("*/*.metadata.json"),
            key=lambda path: path.as_posix(),
        ) if sharded_root.exists() else []
        return list(dict.fromkeys((*legacy, *sharded)))

    def _secure_source_metadata_records(self) -> list[dict[str, Any]]:
        _, records = self._secure_source_metadata_scan(read_records=True)
        return records

    def _secure_source_metadata_scan(
        self,
        *,
        read_records: bool,
    ) -> tuple[list[Path], list[dict[str, Any]]]:
        return self._metadata_scanner()._secure_source_metadata_scan(read_records=read_records)

    def _assert_source_data_trust_binding(self) -> None:
        return self._metadata_scanner()._assert_source_data_trust_binding()

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

    def _list_tasks_from_metadata(
        self,
        metadata_paths: list[Path],
        *,
        update_index: bool = True,
    ) -> list[dict[str, Any]]:
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
            if update_index:
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

    def task_owned_input_path(self, task_id: str, filename: str) -> Path:
        self._validate_task_id(task_id)
        candidate = (self.input_root / filename).resolve(strict=False)
        try:
            candidate.relative_to(self.input_root.resolve(strict=False))
        except ValueError as exc:
            raise ValueError("task_input_not_owned") from exc
        if not candidate.name.startswith(f"{task_id}-"):
            raise ValueError("task_input_not_owned")
        return candidate

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

    def output_sidebar_thumbnail_path(self, task_id: str, output_index: int) -> Path:
        self._validate_task_id(task_id)
        return self.output_root / "thumbnails" / _task_date_directory(task_id) / output_sidebar_thumbnail_filename(task_id, output_index)

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
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", task_id):
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


def _stabilize_task_terminal_timestamp(path: Path, metadata: dict[str, Any]) -> None:
    status = str(metadata.get("status") or "")
    if status not in TERMINAL_TASK_STATUSES:
        metadata.pop("terminal_at", None)
        return
    if metadata.get("terminal_at"):
        return

    existing: dict[str, Any] = {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            existing = loaded
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        pass

    existing_was_terminal = str(existing.get("status") or "") in TERMINAL_TASK_STATUSES
    terminal_at = (
        existing.get("terminal_at")
        or existing.get("completed_at")
        or (existing.get("created_at") if existing_was_terminal else "")
        or (existing.get("updated_at") if existing_was_terminal else "")
        or metadata.get("completed_at")
        or metadata.get("updated_at")
        or metadata.get("created_at")
    )
    if terminal_at:
        metadata["terminal_at"] = str(terminal_at)


def _preserve_sticky_task_cancellation(
    path: Path,
    metadata: dict[str, Any],
) -> None:
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return
    if not isinstance(existing, dict) or not existing.get("cancel_requested"):
        return

    metadata["cancel_requested"] = True
    if existing.get("cancel_requested_at"):
        metadata["cancel_requested_at"] = existing["cancel_requested_at"]
    existing_cancelled_at = existing.get("cancelled_at")
    proposed_cancelled_at = metadata.get("cancelled_at")
    if proposed_cancelled_at:
        return
    if existing_cancelled_at:
        metadata["cancelled_at"] = existing_cancelled_at
        metadata["status"] = str(existing.get("status") or "failed")
        for key in ("error", "last_error"):
            if existing.get(key):
                metadata[key] = existing[key]
        return
    metadata["status"] = "cancelling"
    metadata.pop("terminal_at", None)


def _same_file_bytes(first: Path, second: Path) -> bool:
    try:
        return first.read_bytes() == second.read_bytes()
    except OSError:
        return False
