from __future__ import annotations

from .history_restore_metadata import (
    _record_at,
    _safe_asset_task_record,
    _safe_gallery_task_record,
    _rewrite_restored_metadata,
    _rewrite_restored_request,
    _drop_untrusted_local_paths,
    _is_untrusted_local_value,
)

from .history_backup_import_types import (
    BackupImportStatus,
    BackupImportClassification,
    BackupImportTaskResult,
    BackupImportPreview,
    BackupImportResult,
    BackupImportSession,
    BackupImportSnapshot,
    _SessionRecord,
)

from .history_backup_validation import (
    HistoryBackupArchiveValidator,
    _validated_member_path,
    _declared_entries,
    _SUPPORTED_COMPRESSION,
    _JSON_ROLES,
    _RASTER_ROLES,
    _STREAM_BYTES,
)

from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import stat
import tempfile
from threading import Condition, Lock, RLock
from typing import Any, Callable, Iterator, Literal
import unicodedata
from uuid import uuid4
import zipfile
from urllib.parse import urlparse

from codex_image.raster_validation import MAX_RASTER_BYTES

from .history_backup_format import BackupFileEntry, BackupManifest, BackupTaskEntry, canonical_task_fingerprint, parse_backup_manifest
from .history_backup_plan import TaskBackupPlanner, _contains_sensitive_request_key
from .history_organizer import HistoryOrganizerError
from .gallery_storage import GalleryRestore
from .image_uploads import InvalidRasterImage, validate_raster_image
from .reference_assets import ReferenceAssetRestore
from .reference_files import MAX_REFERENCE_FILE_BYTES, ReferenceFileRestore, validate_reference_file
from .storage import (
    RestoredTaskBinary,
    RestoredTaskFilesJournal,
    RestoredTaskFilesPlan,
    RestoredTaskRollbackIncomplete,
    RestoredTaskRollbackJournal,
)
from .storage_utils import _guess_mime_type, _task_date_directory
from .thumbnails import create_image_thumbnail, create_sidebar_thumbnail
from .resource_limits import (
    HISTORY_BACKUP_FREE_RATIO,
    HISTORY_BACKUP_MIN_FREE_BYTES,
    HISTORY_BACKUP_UPLOAD_CHUNK_BYTES,
    MAX_HISTORY_BACKUP_COMPRESSION_RATIO,
    MAX_HISTORY_BACKUP_ENTRIES,
    MAX_HISTORY_BACKUP_EXPANDED_BYTES,
    MAX_HISTORY_BACKUP_MANIFEST_BYTES,
    MAX_HISTORY_BACKUP_MEMBER_BYTES,
    MAX_HISTORY_BACKUP_UPLOAD_BYTES,
)
from .task_index import TERMINAL_TASK_STATUSES


_PREFIX = "history-backup-import-"
_SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_DEFAULT_TASK_JSON_BYTES = 16 * 1024 * 1024
_STAGING_RE = re.compile(
    r"^\.history-backup-import-(?P<task_id>[A-Za-z0-9][A-Za-z0-9._-]{0,127})\."
    r"(?P<nonce>[0-9a-f]{32})\.staging$"
)
_PERSISTED_SESSION_ERROR_CODES = frozenset({
    "backup_import_interrupted",
    "backup_import_restore_interrupted",
    "backup_import_restore_plan_invalid",
    "backup_import_restore_rollback_incomplete",
    "backup_import_upload_state_invalid",
})
_SAFE_RESULT_REASON_CODES = frozenset({
    "backup_import_duplicate",
    "backup_import_local_task_invalid",
    "backup_import_metadata_contains_sensitive_fields",
    "backup_import_raster_invalid",
    "backup_import_reference_file_invalid",
    "backup_import_request_contains_sensitive_fields",
    "backup_import_restore_failed",
    "backup_import_restore_rollback_incomplete",
    "backup_import_restored",
    "backup_import_staging_cleanup_incomplete",
    "backup_import_task_fingerprint_invalid",
    "backup_import_task_fingerprint_mismatch",
    "backup_import_task_id_conflict",
    "backup_import_task_id_mismatch",
    "backup_import_task_json_invalid",
    "backup_import_task_json_too_large",
    "backup_import_task_metadata_invalid",
    "backup_import_task_not_terminal",
    "backup_import_task_organization_conflict",
    "backup_import_task_organization_invalid",
    "backup_import_task_required_json_invalid",
    "backup_import_task_required_json_missing",
    "backup_import_thumbnail_failed",
})


class HistoryBackupImportService:
    def _archive_validator(self) -> HistoryBackupArchiveValidator:
        return HistoryBackupArchiveValidator(
            max_entries=self._max_entries,
            max_manifest_bytes=self._max_manifest_bytes,
            max_member_bytes=self._max_member_bytes,
            max_expanded_bytes=self._max_expanded_bytes,
            max_compression_ratio=self._max_compression_ratio,
            max_task_json_bytes=self._max_task_json_bytes,
        )

    def __init__(
        self,
        planner: TaskBackupPlanner,
        root: Path,
        *,
        max_upload_bytes: int = MAX_HISTORY_BACKUP_UPLOAD_BYTES,
        max_chunk_bytes: int = HISTORY_BACKUP_UPLOAD_CHUNK_BYTES,
        max_entries: int = MAX_HISTORY_BACKUP_ENTRIES,
        max_member_bytes: int = MAX_HISTORY_BACKUP_MEMBER_BYTES,
        max_expanded_bytes: int = MAX_HISTORY_BACKUP_EXPANDED_BYTES,
        max_compression_ratio: float = MAX_HISTORY_BACKUP_COMPRESSION_RATIO,
        max_manifest_bytes: int = MAX_HISTORY_BACKUP_MANIFEST_BYTES,
        max_task_json_bytes: int = _DEFAULT_TASK_JSON_BYTES,
        min_free_bytes: int = HISTORY_BACKUP_MIN_FREE_BYTES,
        free_ratio: float = HISTORY_BACKUP_FREE_RATIO,
        disk_usage=shutil.disk_usage,
        failure_injector: Callable[[str], None] | None = None,
        recover_on_init: bool = True,
    ) -> None:
        integer_limits = (
            max_upload_bytes,
            max_chunk_bytes,
            max_entries,
            max_member_bytes,
            max_expanded_bytes,
            max_manifest_bytes,
            max_task_json_bytes,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in integer_limits):
            raise ValueError("backup_import_limit_config_invalid")
        if max_compression_ratio <= 0 or min_free_bytes < 0 or not 0 <= free_ratio < 1:
            raise ValueError("backup_import_limit_config_invalid")
        if not callable(getattr(planner, "current_task_fingerprint", None)):
            raise ValueError("backup_import_planner_invalid")
        self.planner = planner
        self.root = Path(root)
        self._max_upload_bytes = max_upload_bytes
        self._max_chunk_bytes = max_chunk_bytes
        self._max_entries = max_entries
        self._max_member_bytes = max_member_bytes
        self._max_expanded_bytes = max_expanded_bytes
        self._max_compression_ratio = max_compression_ratio
        self._max_manifest_bytes = max_manifest_bytes
        self._max_task_json_bytes = max_task_json_bytes
        self._min_free_bytes = min_free_bytes
        self._free_ratio = free_ratio
        self._disk_usage = disk_usage
        self._failure_injector = failure_injector
        self._records: dict[str, _SessionRecord] = {}
        self._lock = RLock()
        self._operation_lock = Lock()
        self._lifecycle = Condition(RLock())
        self._inflight_operations = 0
        self._closing = False
        self._accepting = False
        self._recovered = False
        if recover_on_init:
            self.recover_startup()

    def recover_startup(self) -> None:
        with self._entered_operation(require_accepting=False):
            with self._lock:
                if self._recovered:
                    return
                self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
                if self.root.is_symlink() or not self.root.is_dir():
                    raise ValueError("backup_import_root_invalid")
                os.chmod(self.root, 0o700)
                self._recover_statuses()
                self._replay_private_journals()
                self._cleanup_orphan_staging()
                self._recovered = True
            with self._lifecycle:
                if self._closing:
                    raise ValueError("backup_import_lifecycle_conflict")
                self._accepting = True

    def close(self) -> None:
        with self._lifecycle:
            self._closing = True
            self._accepting = False
            while self._inflight_operations:
                self._lifecycle.wait()

    def _require_accepting(self) -> None:
        with self._lifecycle:
            if not self._accepting or self._closing:
                raise ValueError("backup_import_lifecycle_conflict")

    @contextmanager
    def _entered_operation(self, *, require_accepting: bool = True) -> Iterator[None]:
        with self._lifecycle:
            if self._closing or (require_accepting and not self._accepting):
                raise ValueError("backup_import_lifecycle_conflict")
            self._inflight_operations += 1
        try:
            yield
        finally:
            with self._lifecycle:
                self._inflight_operations -= 1
                if self._inflight_operations == 0:
                    self._lifecycle.notify_all()

    def create(self, filename: str, size_bytes: int) -> BackupImportSession:
        with self._entered_operation():
            return self._create(filename, size_bytes)

    def _create(self, filename: str, size_bytes: int) -> BackupImportSession:
        safe_filename = _validated_filename(filename)
        if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes <= 0:
            raise ValueError("backup_import_size_invalid")
        if size_bytes > self._max_upload_bytes:
            raise ValueError("backup_import_upload_too_large")
        self._preflight_capacity(size_bytes)
        session_id = uuid4().hex
        now = _timestamp()
        session = BackupImportSession(
            session_id=session_id,
            filename=safe_filename,
            size_bytes=size_bytes,
            uploaded_bytes=0,
            status="uploading",
            created_at=now,
            updated_at=now,
        )
        upload_path = self._upload_path(session_id)
        descriptor = os.open(upload_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            os.close(descriptor)
            descriptor = -1
            record = _SessionRecord(session=session, digest=hashlib.sha256())
            with self._lock:
                self._records[session_id] = record
                try:
                    self._write_status(session)
                except Exception:
                    del self._records[session_id]
                    raise
        except Exception:
            if descriptor >= 0:
                os.close(descriptor)
            upload_path.unlink(missing_ok=True)
            self._status_path(session_id).unlink(missing_ok=True)
            raise
        return session

    def append_chunk(self, session_id: str, offset: int, chunk: bytes, sha256: str) -> BackupImportSession:
        with self._entered_operation():
            return self._append_chunk(session_id, offset, chunk, sha256)

    def _append_chunk(self, session_id: str, offset: int, chunk: bytes, sha256: str) -> BackupImportSession:
        session_id = _validated_session_id(session_id)
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("backup_import_offset_invalid")
        if not isinstance(chunk, bytes) or not chunk:
            raise ValueError("backup_import_chunk_invalid")
        if len(chunk) > self._max_chunk_bytes:
            raise ValueError("backup_import_chunk_too_large")
        if not isinstance(sha256, str) or not _SHA256_RE.fullmatch(sha256):
            raise ValueError("backup_import_chunk_hash_mismatch")
        actual_sha256 = hashlib.sha256(chunk).hexdigest()
        if actual_sha256 != sha256.lower():
            raise ValueError("backup_import_chunk_hash_mismatch")

        with self._lock:
            record = self._require_record(session_id)
            current = record.session
            if current.status == "validated":
                raise ValueError("backup_import_already_validated")
            if current.status not in {"uploading", "uploaded"}:
                raise ValueError("backup_import_lifecycle_conflict")
            if offset != current.uploaded_bytes:
                if record.last_offset == offset:
                    return self._retry_last_chunk(record, chunk, actual_sha256)
                raise ValueError("backup_import_offset_invalid")
            if current.uploaded_bytes + len(chunk) > current.size_bytes:
                raise ValueError("backup_import_upload_overflow")
            self._preflight_capacity(len(chunk))
            path = self._upload_path(session_id)
            previous_size = current.uploaded_bytes
            try:
                with path.open("r+b") as destination:
                    destination.seek(0, os.SEEK_END)
                    if destination.tell() != previous_size:
                        raise ValueError("backup_import_upload_state_invalid")
                    destination.write(chunk)
                    destination.flush()
                    os.fsync(destination.fileno())
                updated_bytes = previous_size + len(chunk)
                updated = replace(
                    current,
                    uploaded_bytes=updated_bytes,
                    status="uploaded" if updated_bytes == current.size_bytes else "uploading",
                    updated_at=_timestamp(),
                )
                self._write_status(updated)
            except Exception:
                try:
                    with path.open("r+b") as destination:
                        destination.truncate(previous_size)
                        destination.flush()
                        os.fsync(destination.fileno())
                except OSError:
                    pass
                raise
            record.digest.update(chunk)
            record.last_offset = offset
            record.last_size = len(chunk)
            record.last_sha256 = actual_sha256
            record.session = updated
            return updated

    def validate(self, session_id: str) -> BackupImportPreview:
        with self._entered_operation():
            with self._operation_lock:
                self._require_accepting()
                return self._validate(session_id)

    def _validate(self, session_id: str) -> BackupImportPreview:
        session_id = _validated_session_id(session_id)
        with self._lock:
            record = self._require_record(session_id)
            if record.preview is not None:
                return record.preview
            if record.session.uploaded_bytes != record.session.size_bytes or record.session.status != "uploaded":
                raise ValueError("backup_import_upload_incomplete")
            upload_path = self._upload_path(session_id)
            whole_digest = _file_sha256(upload_path)
            if record.digest.hexdigest() != whole_digest:
                raise ValueError("backup_import_upload_state_invalid")
            manifest, task_json, invalid_reasons = self._validate_zip(upload_path)
            classifications = self._classify(manifest, task_json, invalid_reasons)
            preview = BackupImportPreview(
                session_id=session_id,
                whole_file_sha256=whole_digest,
                restorable=classifications["restorable"],
                duplicate=classifications["duplicate"],
                conflict=classifications["conflict"],
                invalid=classifications["invalid"],
            )
            plan_path = self._plan_path(session_id)
            self._write_plan(session_id, manifest, preview)
            updated = replace(
                record.session,
                status="validated",
                updated_at=_timestamp(),
                whole_file_sha256=whole_digest,
            )
            try:
                self._write_status(updated)
            except Exception:
                self._safe_unlink(plan_path)
                raise
            record.session = updated
            record.preview = preview
            return preview

    def get(self, session_id: str) -> BackupImportSession | None:
        if not isinstance(session_id, str) or not _SESSION_ID_RE.fullmatch(session_id):
            return None
        with self._lock:
            record = self._records.get(session_id)
            return record.session if record is not None else None

    def get_snapshot(self, session_id: str) -> BackupImportSnapshot | None:
        if not isinstance(session_id, str) or not _SESSION_ID_RE.fullmatch(session_id):
            return None
        with self._lock:
            record = self._records.get(session_id)
            if record is None:
                return None
            return BackupImportSnapshot(record.session, record.result)

    def cancel(self, session_id: str) -> bool:
        with self._entered_operation():
            return self._cancel(session_id)

    def _cancel(self, session_id: str) -> bool:
        if not isinstance(session_id, str) or not _SESSION_ID_RE.fullmatch(session_id):
            return False
        with self._lock:
            record = self._records.get(session_id)
            if record is None:
                return False
            if record.session.status in {"restoring", "restored"} or (
                record.session.status == "failed"
                and record.session.error_code == "backup_import_restore_rollback_incomplete"
            ):
                raise ValueError("backup_import_lifecycle_conflict")
            if not self._strict_cancel_cleanup(session_id):
                return False
            del self._records[session_id]
            return True

    def restore(self, session_id: str) -> BackupImportResult:
        with self._entered_operation():
            with self._operation_lock:
                self._require_accepting()
                return self._restore(session_id)

    def _restore(self, session_id: str) -> BackupImportResult:
        session_id = _validated_session_id(session_id)
        with self._lock:
            record = self._require_record(session_id)
            if record.result is not None:
                return record.result
            if record.session.status == "failed" and record.session.error_code:
                raise ValueError(record.session.error_code)
            if record.preview is None or record.session.status != "validated":
                raise ValueError("backup_import_not_validated")
            restoring = replace(record.session, status="restoring", updated_at=_timestamp())
            self._write_status(restoring)
            record.session = restoring
            preview = record.preview
        try:
            try:
                plan = json.loads(self._plan_path(session_id).read_text(encoding="utf-8"))
                manifest = parse_backup_manifest(
                    json.dumps(plan["manifest"], separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                )
            except Exception:
                self._mark_restore_failed(session_id, "backup_import_restore_plan_invalid")
                raise ValueError("backup_import_restore_plan_invalid") from None

            outcomes: dict[str, list[BackupImportTaskResult]] = {
                "restored": [], "duplicates": [], "conflicts": [], "invalid": [],
                "failed": [], "thumbnail_warnings": [], "cleanup_warnings": [],
            }
            outcomes["duplicates"].extend(
                BackupImportTaskResult(item.task_id, "duplicate", item.reason or "backup_import_duplicate")
                for item in preview.duplicate
            )
            outcomes["conflicts"].extend(
                BackupImportTaskResult(item.task_id, "conflict", item.reason or "backup_import_task_id_conflict")
                for item in preview.conflict
            )
            outcomes["invalid"].extend(preview.invalid)
            upload_path = self._upload_path(session_id)
            try:
                upload_digest = _file_sha256(upload_path)
            except Exception:
                self._mark_restore_failed(session_id, "backup_import_restore_interrupted")
                raise ValueError("backup_import_restore_interrupted") from None
            if upload_digest != preview.whole_file_sha256:
                self._mark_restore_failed(session_id, "backup_import_upload_state_invalid")
                raise ValueError("backup_import_upload_state_invalid")
            tasks_by_id = {task.task_id: task for task in manifest.tasks}
            if any(item.task_id not in tasks_by_id for item in preview.restorable):
                raise RuntimeError("backup_import_restore_plan_mismatch")
            for planned in preview.restorable:
                task = tasks_by_id[planned.task_id]
                try:
                    task_storage = getattr(self.planner, "task_storage", None)
                    if task_storage is None:
                        raise ValueError("backup_import_restore_storage_unavailable")
                    with task_storage._history_organization_lock:
                        with task_storage._task_write_lock(task.task_id):
                            current = self._current_task_fingerprint(task.task_id)
                            if current is not None:
                                target = "duplicates" if current == task.fingerprint else "conflicts"
                                classification = "duplicate" if current == task.fingerprint else "conflict"
                                code = "backup_import_duplicate" if current == task.fingerprint else "backup_import_task_id_conflict"
                                outcomes[target].append(BackupImportTaskResult(task.task_id, classification, code))
                                continue
                            if task_storage.history_organizer.has_task_state(task.task_id):
                                outcomes["conflicts"].append(
                                    BackupImportTaskResult(
                                        task.task_id,
                                        "conflict",
                                        "backup_import_task_organization_conflict",
                                    )
                                )
                                continue
                            thumbnail_warning, cleanup_pending, ownership_cleanup = self._restore_one_task(
                                upload_path, task
                            )
                    outcomes["restored"].append(BackupImportTaskResult(task.task_id, "restored", "backup_import_restored"))
                    if thumbnail_warning:
                        outcomes["thumbnail_warnings"].append(
                            BackupImportTaskResult(task.task_id, "thumbnail_warning", "backup_import_thumbnail_failed")
                        )
                    if cleanup_pending:
                        outcomes["cleanup_warnings"].append(
                            BackupImportTaskResult(
                                task.task_id,
                                "cleanup_warning",
                                "backup_import_staging_cleanup_incomplete",
                            )
                        )
                        try:
                            self._write_cleanup_journal(
                                session_id,
                                task.task_id,
                                cleanup_pending,
                            )
                        except Exception:
                            pass
                    if ownership_cleanup is not None:
                        persisted = False
                        for _ in range(2):
                            try:
                                self._write_ownership_cleanup_journal(
                                    session_id,
                                    ownership_cleanup,
                                )
                            except Exception:
                                continue
                            persisted = True
                            break
                        if not persisted:
                            outcomes["cleanup_warnings"].append(
                                BackupImportTaskResult(
                                    task.task_id,
                                    "cleanup_warning",
                                    "backup_import_restore_owner_cleanup_incomplete",
                                )
                            )
                except RestoredTaskRollbackIncomplete as exc:
                    try:
                        self._write_rollback_journal(session_id, task.task_id, exc.journal)
                    except Exception:
                        self._mark_restore_failed(
                            session_id,
                            "backup_import_restore_rollback_incomplete",
                        )
                        raise ValueError("backup_import_restore_rollback_incomplete") from None
                    outcomes["failed"].append(
                        BackupImportTaskResult(task.task_id, "failed", "backup_import_restore_rollback_incomplete")
                    )
                except HistoryOrganizerError as exc:
                    if str(exc) == "task_organization_conflict":
                        outcomes["conflicts"].append(
                            BackupImportTaskResult(
                                task.task_id,
                                "conflict",
                                "backup_import_task_organization_conflict",
                            )
                        )
                    else:
                        outcomes["failed"].append(
                            BackupImportTaskResult(task.task_id, "failed", "backup_import_restore_failed")
                        )
                except Exception:
                    outcomes["failed"].append(
                        BackupImportTaskResult(task.task_id, "failed", "backup_import_restore_failed")
                    )
            result = BackupImportResult(**{key: tuple(value) for key, value in outcomes.items()})
            with self._lock:
                record = self._require_record(session_id)
                rollback_incomplete = any(
                    item.reason == "backup_import_restore_rollback_incomplete"
                    for item in result.failed
                )
                terminal = replace(
                    record.session,
                    status="failed" if rollback_incomplete else "restored",
                    error_code="backup_import_restore_rollback_incomplete" if rollback_incomplete else None,
                    updated_at=_timestamp(),
                )
                try:
                    self._write_result(session_id, result)
                    self._write_status(terminal)
                except Exception:
                    self._mark_restore_failed(session_id, "backup_import_restore_interrupted")
                    raise ValueError("backup_import_restore_interrupted") from None
                record.session = terminal
                record.result = result
            return result
        except ValueError as exc:
            if str(exc) in {
                "backup_import_restore_plan_invalid",
                "backup_import_restore_interrupted",
                "backup_import_upload_state_invalid",
                "backup_import_restore_rollback_incomplete",
            }:
                raise
            self._mark_restore_failed(session_id, "backup_import_restore_interrupted")
            raise ValueError("backup_import_restore_interrupted") from None
        except Exception:
            self._mark_restore_failed(session_id, "backup_import_restore_interrupted")
            raise ValueError("backup_import_restore_interrupted") from None

    def _mark_restore_failed(self, session_id: str, code: str) -> None:
        with self._lock:
            record = self._require_record(session_id)
            failed = replace(
                record.session,
                status="failed",
                error_code=code,
                updated_at=_timestamp(),
            )
            try:
                self._write_status(failed)
            except Exception:
                pass
            record.session = failed
            record.result = None

    def _write_rollback_journal(
        self,
        session_id: str,
        task_id: str,
        journal: RestoredTaskRollbackJournal,
    ) -> None:
        path = self.root / f"{_PREFIX}{session_id}.rollback.json"
        task_record = {
            "task_id": task_id,
            "restore_token": journal.restore_token,
            "pending_paths": [str(item) for item in journal.pending_paths],
            "index_pending": journal.index_pending,
            "pending_resources": list(journal.pending_resources),
            "pending_staging_paths": [str(item) for item in journal.pending_staging_paths],
            "organization_pending": journal.organization_pending,
            "ownership_pending": journal.ownership_pending,
        }
        payload = {
            "session_id": session_id,
            "tasks": self._merged_private_journal_tasks(path, task_record),
            "code": "backup_import_restore_rollback_incomplete",
        }
        self._atomic_json(path, payload)

    def _write_cleanup_journal(
        self,
        session_id: str,
        task_id: str,
        pending_paths: tuple[Path, ...],
    ) -> None:
        path = self.root / f"{_PREFIX}{session_id}.cleanup.json"
        task_record = {
            "task_id": task_id,
            "pending_staging_paths": [str(item) for item in pending_paths],
        }
        self._atomic_json(path, {
            "session_id": session_id,
            "tasks": self._merged_private_journal_tasks(path, task_record),
            "code": "backup_import_staging_cleanup_incomplete",
        })

    def _write_ownership_cleanup_journal(
        self,
        session_id: str,
        task_record: dict[str, Any],
    ) -> None:
        path = self.root / f"{_PREFIX}{session_id}.ownership.json"
        self._atomic_json(path, {
            "session_id": session_id,
            "tasks": self._merged_private_journal_tasks(path, task_record),
            "code": "backup_import_restore_owner_cleanup_incomplete",
        })

    @staticmethod
    def _merged_private_journal_tasks(
        path: Path,
        task_record: dict[str, Any],
    ) -> list[dict[str, Any]]:
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            tasks: list[dict[str, Any]] = []
        else:
            if not isinstance(existing, dict) or not isinstance(existing.get("tasks"), list):
                raise ValueError("backup_import_private_journal_invalid")
            tasks = [
                item for item in existing["tasks"]
                if isinstance(item, dict) and item.get("task_id") != task_record["task_id"]
            ]
        tasks.append(task_record)
        return tasks

    def _restore_one_task(
        self,
        upload_path: Path,
        task: BackupTaskEntry,
    ) -> tuple[bool, tuple[Path, ...], dict[str, Any] | None]:
        task_storage = getattr(self.planner, "task_storage", None)
        gallery_storage = getattr(self.planner, "gallery_storage", None)
        reference_asset_storage = getattr(self.planner, "reference_asset_storage", None)
        reference_file_storage = getattr(self.planner, "reference_file_storage", None)
        if any(item is None for item in (task_storage, gallery_storage, reference_asset_storage, reference_file_storage)):
            raise ValueError("backup_import_restore_storage_unavailable")
        staging_dir = self.root / f".{_PREFIX}{task.task_id}.{uuid4().hex}.staging"
        staging_dir.mkdir(mode=0o700)
        members = {entry.role: [] for entry in task.files}
        try:
            with zipfile.ZipFile(upload_path, "r", allowZip64=True) as archive:
                for offset, entry in enumerate(task.files):
                    staged_path = staging_dir / f"member-{offset:04d}.staged"
                    digest = hashlib.sha256()
                    actual_size = 0
                    descriptor = os.open(staged_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    with os.fdopen(descriptor, "wb") as destination, archive.open(entry.path, "r") as source:
                        while chunk := source.read(_STREAM_BYTES):
                            actual_size += len(chunk)
                            if actual_size > entry.size_bytes:
                                raise ValueError("backup_import_member_changed")
                            digest.update(chunk)
                            destination.write(chunk)
                        destination.flush()
                        os.fsync(destination.fileno())
                    if actual_size != entry.size_bytes or digest.hexdigest() != entry.sha256:
                        raise ValueError("backup_import_member_changed")
                    members.setdefault(entry.role, []).append((entry, staged_path))
        except Exception as exc:
            pending = _cleanup_restore_staging(staging_dir)
            if pending:
                raise RestoredTaskRollbackIncomplete(
                    RestoredTaskRollbackJournal(
                        task.task_id,
                        pending_staging_paths=pending,
                    )
                ) from exc
            raise
        json_values: dict[str, dict[str, Any]] = {}
        try:
            for role in _JSON_ROLES:
                values = members.get(role, [])
                if len(values) != 1:
                    raise ValueError("backup_import_task_required_json_invalid")
                parsed = json.loads(values[0][1].read_text(encoding="utf-8"))
                if not isinstance(parsed, dict):
                    raise ValueError("backup_import_task_required_json_missing")
                json_values[role] = parsed
        except Exception as exc:
            pending = _cleanup_restore_staging(staging_dir)
            if pending:
                raise RestoredTaskRollbackIncomplete(
                    RestoredTaskRollbackJournal(
                        task.task_id,
                        pending_staging_paths=pending,
                    )
                ) from exc
            raise

        metadata = dict(json_values["metadata"])
        request = dict(json_values["request"])
        organization = json_values["organization"]
        journal: RestoredTaskFilesJournal | None = None
        asset_handles: list[Any] = []
        gallery_handles: list[Any] = []
        reference_file_handles: list[Any] = []
        ownership_cleanup: dict[str, Any] | None = None
        resource_locks = (
            reference_asset_storage._lock,
            gallery_storage._lock,
            reference_file_storage._lock,
        )
        for lock in resource_locks:
            lock.acquire()
        try:
            reference_records: list[dict[str, Any]] = []
            original_reference_records = metadata.get("reference_assets") if isinstance(metadata.get("reference_assets"), list) else []
            for entry, staged_path in sorted(members.get("reference_asset", []), key=lambda item: item[0].source_index or 0):
                data = _read_staged_member(staged_path, MAX_RASTER_BYTES)
                source = _record_at(original_reference_records, entry.source_index)
                filename = Path(str(source.get("filename") or entry.path.rsplit("/", 1)[-1])).name
                handle = reference_asset_storage.restore_content(filename, data, _guess_mime_type(filename))
                asset_handles.append(handle)
                record = handle.record
                reference_records.append(_safe_asset_task_record(record))

            gallery_records: list[dict[str, Any]] = []
            original_gallery_records = metadata.get("gallery_refs") if isinstance(metadata.get("gallery_refs"), list) else []
            for entry, staged_path in sorted(members.get("gallery_reference", []), key=lambda item: item[0].source_index or 0):
                data = _read_staged_member(staged_path, MAX_RASTER_BYTES)
                source = _record_at(original_gallery_records, entry.source_index)
                filename = Path(str(source.get("filename") or entry.path.rsplit("/", 1)[-1])).name
                handle = gallery_storage.restore_content(
                    str(source.get("name") or f"Restored {entry.sha256[:8]}"),
                    str(source.get("category") or "portrait"),
                    filename,
                    data,
                    _guess_mime_type(filename),
                )
                gallery_handles.append(handle)
                record = handle.record
                gallery_records.append(_safe_gallery_task_record(record))

            native_records: list[dict[str, Any]] = []
            original_native_records = metadata.get("reference_files") if isinstance(metadata.get("reference_files"), list) else []
            for entry, staged_path in sorted(members.get("reference_file", []), key=lambda item: item[0].source_index or 0):
                data = _read_staged_member(staged_path, MAX_REFERENCE_FILE_BYTES)
                source = _record_at(original_native_records, entry.source_index)
                filename = Path(str(source.get("filename") or entry.path.rsplit("/", 1)[-1])).name
                validated = validate_reference_file(filename, data, None)
                handle = reference_file_storage.restore_validated(validated)
                reference_file_handles.append(handle)
                record = handle.record
                native_records.append(record)

            binaries: list[RestoredTaskBinary] = []
            input_names: list[str] = []
            output_names: list[str] = []
            output_names_by_index: dict[int, str] = {}
            mask_name: str | None = None
            for role in ("input", "mask", "output"):
                for entry, staged_path in sorted(members.get(role, []), key=lambda item: item[0].source_index or 0):
                    index = int(entry.source_index or 1)
                    archive_name = entry.path.rsplit("/", 1)[-1]
                    binary = RestoredTaskBinary(
                        role=role,
                        source_index=index,
                        filename=archive_name,
                        staged_path=staged_path,
                        expected_size=entry.size_bytes,
                        expected_sha256=entry.sha256,
                    )
                    binaries.append(binary)
                    if role in {"input", "mask"}:
                        prefix = f"{task.task_id}-{role}-{index:02d}-"
                        local_name = prefix + archive_name
                        if role == "input":
                            input_names.append(local_name)
                        else:
                            mask_name = local_name
                    else:
                        suffix = Path(archive_name).suffix.lower().lstrip(".") or "png"
                        local_output_name = task_storage.output_file(
                                task_storage.output_root
                                / _task_date_directory(task.task_id)
                                / f"{task.task_id}-image-{index}.{suffix}"
                        )
                        output_names.append(local_output_name)
                        output_names_by_index[index] = local_output_name

            metadata = _rewrite_restored_metadata(
                metadata, task.task_id, input_names, mask_name, output_names,
                reference_records, gallery_records, native_records,
            )
            metadata["backup_import_fingerprint"] = task.fingerprint
            request = _rewrite_restored_request(
                request,
                input_names,
                mask_name,
                reference_records,
                gallery_records,
                native_records,
            )
            journal = task_storage.restore_task_files(RestoredTaskFilesPlan(
                task_id=task.task_id,
                metadata=metadata,
                request=request,
                binaries=tuple(binaries),
                staging_root=staging_dir,
                failure_injector=self._failure_injector,
            ))
            tags = organization.get("tags") if isinstance(organization.get("tags"), list) else []
            with task_storage._history_organization_lock:
                task_storage.history_organizer.restore_task_organization(
                    task.task_id,
                    bool(organization.get("favorite")),
                    [tag.get("name") for tag in tags if isinstance(tag, dict)],
                    failure_injector=self._failure_injector,
                )
            ownership_cleanup = self._release_committed_restore_ownership(
                task.task_id,
                journal,
                (
                    ("reference_asset", reference_asset_storage, asset_handles),
                    ("gallery", gallery_storage, gallery_handles),
                    ("reference_file", reference_file_storage, reference_file_handles),
                ),
            )
        except Exception as original:
            task_pending = (
                original.journal
                if isinstance(original, RestoredTaskRollbackIncomplete)
                else RestoredTaskRollbackJournal(
                    task.task_id,
                    restore_token=journal.restore_token if journal is not None else None,
                )
            )
            if journal is not None:
                try:
                    task_storage.rollback_restored_task_files(journal)
                except RestoredTaskRollbackIncomplete as exc:
                    task_pending = exc.journal
            pending_resources: list[dict[str, Any]] = list(task_pending.pending_resources)
            for kind, storage, handles in (
                ("reference_file", reference_file_storage, reference_file_handles),
                ("gallery", gallery_storage, gallery_handles),
                ("reference_asset", reference_asset_storage, asset_handles),
            ):
                for handle in reversed(handles):
                    try:
                        removed = storage.rollback_restore(handle)
                    except Exception:
                        if _restore_resource_is_pending(kind, storage, handle):
                            pending_resources.append({
                                "kind": kind,
                                "id": str(handle.record.get("id") or ""),
                                "created": bool(handle.created),
                                "version": int(handle.version),
                                "record": dict(handle.record),
                                "restore_token": handle.restore_token,
                            })
                    else:
                        if not removed and _restore_resource_is_pending(kind, storage, handle):
                            pending_resources.append({
                                "kind": kind,
                                "id": str(handle.record.get("id") or ""),
                                "created": bool(handle.created),
                                "version": int(handle.version),
                                "record": dict(handle.record),
                                "restore_token": handle.restore_token,
                            })
            pending_staging = tuple(dict.fromkeys((
                *task_pending.pending_staging_paths,
                *_cleanup_restore_staging(staging_dir),
            )))
            if (
                task_pending.pending_paths
                or task_pending.index_pending
                or pending_resources
                or pending_staging
                or task_pending.organization_pending
            ):
                raise RestoredTaskRollbackIncomplete(
                    RestoredTaskRollbackJournal(
                        task_id=task.task_id,
                        restore_token=task_pending.restore_token,
                        pending_paths=task_pending.pending_paths,
                        index_pending=task_pending.index_pending,
                        pending_resources=tuple(pending_resources),
                        pending_staging_paths=pending_staging,
                        organization_pending=task_pending.organization_pending,
                        ownership_pending=task_pending.ownership_pending,
                    )
                ) from original
            if journal is not None and not task_storage.clear_restore_ownership(
                task.task_id, journal.restore_token
            ):
                raise RestoredTaskRollbackIncomplete(
                    RestoredTaskRollbackJournal(
                        task.task_id,
                        restore_token=journal.restore_token,
                        ownership_pending=True,
                    )
                ) from original
            raise original
        finally:
            for lock in reversed(resource_locks):
                lock.release()

        warning = False
        for binary in binaries:
            try:
                if binary.role == "input":
                    source = task_storage.input_root / f"{task.task_id}-input-{binary.source_index:02d}-{binary.filename}"
                    if create_image_thumbnail(
                        source, task_storage.input_thumbnail_path(task.task_id, binary.source_index)
                    ) is None:
                        warning = True
                elif binary.role == "output":
                    source = task_storage.output_path(output_names_by_index[binary.source_index])
                    if create_image_thumbnail(
                        source, task_storage.output_thumbnail_path(task.task_id, binary.source_index)
                    ) is None:
                        warning = True
                    if create_sidebar_thumbnail(
                        source, task_storage.output_sidebar_thumbnail_path(task.task_id, binary.source_index)
                    ) is None:
                        warning = True
            except Exception:
                warning = True
        cleanup_pending = _cleanup_restore_staging(staging_dir)
        return warning, cleanup_pending, ownership_cleanup

    def _release_committed_restore_ownership(
        self,
        task_id: str,
        journal: RestoredTaskFilesJournal,
        resource_groups: tuple[tuple[str, Any, list[Any]], ...],
    ) -> dict[str, Any] | None:
        task_pending = True
        try:
            task_pending = not self.planner.task_storage.release_restore_ownership(
                task_id, journal.restore_token
            )
        except Exception:
            task_pending = True
        pending_resources: list[dict[str, Any]] = []
        for kind, storage, handles in resource_groups:
            for handle in handles:
                if not handle.created or not handle.restore_token:
                    continue
                try:
                    released = storage.release_restore_ownership(handle)
                except Exception:
                    released = False
                if not released:
                    pending_resources.append({
                        "kind": kind,
                        "id": str(handle.record.get("id") or ""),
                        "created": True,
                        "version": int(handle.version),
                        "record": dict(handle.record),
                        "restore_token": handle.restore_token,
                    })
        if not task_pending and not pending_resources:
            return None
        return {
            "task_id": task_id,
            "restore_token": journal.restore_token,
            "task_ownership_pending": task_pending,
            "pending_resources": pending_resources,
        }

    def _strict_cancel_cleanup(self, session_id: str) -> bool:
        paths = (
            self._plan_path(session_id),
            self._upload_path(session_id),
            self._result_path(session_id),
            self._status_path(session_id),
        )
        expected_names = {
            f"{_PREFIX}{session_id}.plan.json",
            f"{_PREFIX}{session_id}.upload.partial",
            f"{_PREFIX}{session_id}.result.json",
            f"{_PREFIX}{session_id}.status.json",
        }
        try:
            root = self.root.resolve()
            if any(path.parent.resolve() != root or path.name not in expected_names for path in paths):
                return False
            for path in paths:
                path.unlink(missing_ok=True)
                if path.exists():
                    return False
            _fsync_directory(self.root)
        except OSError:
            return False
        return True

    def _retry_last_chunk(self, record: _SessionRecord, chunk: bytes, digest: str) -> BackupImportSession:
        if record.last_sha256 != digest or record.last_size != len(chunk):
            raise ValueError("backup_import_chunk_retry_mismatch")
        path = self._upload_path(record.session.session_id)
        try:
            with path.open("rb") as source:
                source.seek(record.last_offset or 0)
                stored = source.read(len(chunk) + 1)
        except OSError as exc:
            raise ValueError("backup_import_upload_unreadable") from exc
        if stored != chunk:
            raise ValueError("backup_import_chunk_retry_mismatch")
        return record.session

    def _validate_zip(
        self,
        upload_path: Path,
    ) -> tuple[BackupManifest, dict[str, dict[str, object]], dict[str, str]]:
        return self._archive_validator()._validate_zip(upload_path)

    def _validate_central_directory(self, infos: list[zipfile.ZipInfo]) -> dict[str, zipfile.ZipInfo]:
        return self._archive_validator()._validate_central_directory(infos)

    def _validate_members(
        self,
        archive: zipfile.ZipFile,
        manifest: BackupManifest,
        infos: dict[str, zipfile.ZipInfo],
        entries: dict[str, BackupFileEntry],
        task_for_path: dict[str, str],
    ) -> tuple[BackupManifest, dict[str, dict[str, object]], dict[str, str]]:
        return self._archive_validator()._validate_members(archive, manifest, infos, entries, task_for_path)

    def _classify(
        self,
        manifest: BackupManifest,
        task_json: dict[str, dict[str, object]],
        invalid_reasons: dict[str, str],
    ) -> dict[str, tuple[BackupImportTaskResult, ...]]:
        result: dict[str, list[BackupImportTaskResult]] = {
            "restorable": [], "duplicate": [], "conflict": [], "invalid": []
        }
        for task in manifest.tasks:
            reason = invalid_reasons.get(task.task_id)
            values = task_json.get(task.task_id, {})
            metadata = values.get("metadata")
            request = values.get("request")
            organization = values.get("organization")
            if reason is None:
                reason = _task_semantic_error(task, metadata, request, organization)
            if reason is None:
                assert isinstance(metadata, dict) and isinstance(request, dict) and isinstance(organization, dict)
                try:
                    fingerprint = canonical_task_fingerprint(metadata, request, task.files, organization)
                except ValueError:
                    reason = "backup_import_task_fingerprint_invalid"
                else:
                    if fingerprint != task.fingerprint:
                        reason = "backup_import_task_fingerprint_mismatch"
            if reason is not None:
                result["invalid"].append(BackupImportTaskResult(task.task_id, "invalid", reason))
                continue
            try:
                local_fingerprint = self._current_task_fingerprint(task.task_id)
            except (OSError, ValueError):
                result["invalid"].append(
                    BackupImportTaskResult(task.task_id, "invalid", "backup_import_local_task_invalid")
                )
                continue
            if local_fingerprint is None:
                classification: BackupImportClassification = "restorable"
            elif local_fingerprint == task.fingerprint:
                classification = "duplicate"
            else:
                classification = "conflict"
            result[classification].append(BackupImportTaskResult(task.task_id, classification))
        return {key: tuple(value) for key, value in result.items()}

    def _current_task_fingerprint(self, task_id: str) -> str | None:
        task_storage = getattr(self.planner, "task_storage", None)
        if task_storage is not None:
            try:
                metadata = task_storage.read_metadata(task_id)
            except FileNotFoundError:
                pass
            else:
                restored = metadata.get("backup_import_fingerprint") if isinstance(metadata, dict) else None
                if isinstance(restored, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", restored):
                    return restored
        return self.planner.current_task_fingerprint(task_id)

    def _preflight_capacity(self, required_bytes: int) -> None:
        usage = self._disk_usage(self.root)
        try:
            total = int(getattr(usage, "total"))
            free = int(getattr(usage, "free"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("backup_import_capacity_unavailable") from exc
        reserve = max(self._min_free_bytes, int(total * self._free_ratio))
        if free - required_bytes < reserve:
            raise ValueError("backup_import_insufficient_space")

    def _write_status(self, session: BackupImportSession) -> None:
        self._atomic_json(self._status_path(session.session_id), asdict(session))

    def _write_result(self, session_id: str, result: BackupImportResult) -> None:
        self._atomic_json(self._result_path(session_id), asdict(result))

    def _recover_statuses(self) -> None:
        active = {"uploading", "uploaded", "validated", "restoring"}
        for path in self.root.glob(f"{_PREFIX}*.status.json"):
            session_id = path.name.removeprefix(_PREFIX).removesuffix(".status.json")
            if not _SESSION_ID_RE.fullmatch(session_id):
                continue
            try:
                session = _session_from_status(
                    json.loads(path.read_text(encoding="utf-8")), session_id
                )
                result = None
                if session.status in {"restored", "failed"} and self._result_path(session_id).is_file():
                    result = _result_from_json(
                        json.loads(self._result_path(session_id).read_text(encoding="utf-8"))
                    )
                    if not _result_matches_terminal(session, result):
                        raise ValueError("backup_import_result_invalid")
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
            if session.status in active:
                session = replace(
                    session,
                    status="interrupted",
                    updated_at=_timestamp(),
                    error_code="backup_import_interrupted",
                )
                self._write_status(session)
            self._records[session_id] = _SessionRecord(
                session=session,
                digest=hashlib.sha256(),
                result=result,
            )

    def _cleanup_orphan_staging(self) -> None:
        referenced = self._journal_referenced_staging()
        try:
            candidates = tuple(self.root.iterdir())
        except OSError:
            return
        for candidate in candidates:
            if _STAGING_RE.fullmatch(candidate.name) is None:
                continue
            absolute = Path(os.path.abspath(candidate))
            if any(reference == absolute or absolute in reference.parents for reference in referenced):
                continue
            try:
                mode = candidate.lstat().st_mode
                if stat.S_ISLNK(mode):
                    continue
                if stat.S_ISREG(mode):
                    candidate.unlink()
                elif stat.S_ISDIR(mode):
                    shutil.rmtree(candidate)
            except OSError:
                continue

    def _replay_private_journals(self) -> None:
        journal_re = re.compile(
            rf"^{re.escape(_PREFIX)}(?P<session>[0-9a-f]{{32}})\.(?P<kind>rollback|cleanup|ownership)\.json$"
        )
        try:
            paths = tuple(self.root.iterdir())
        except OSError:
            return
        for path in paths:
            match = journal_re.fullmatch(path.name)
            if match is None:
                continue
            try:
                if stat.S_ISLNK(path.lstat().st_mode) or not path.is_file():
                    continue
                payload = json.loads(path.read_text(encoding="utf-8"))
                parsed = self._validated_private_journal(
                    payload,
                    session_id=match.group("session"),
                    kind=match.group("kind"),
                )
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
            remaining: list[dict[str, Any]] = []
            for task in parsed:
                kind = match.group("kind")
                pending = (
                    self._replay_rollback_task(task)
                    if kind == "rollback"
                    else self._replay_ownership_task(task)
                    if kind == "ownership"
                    else self._replay_cleanup_task(task)
                )
                if pending is not None:
                    remaining.append(pending)
            try:
                if remaining:
                    self._atomic_json(path, {**payload, "tasks": remaining})
                else:
                    path.unlink(missing_ok=True)
                    _fsync_directory(self.root)
            except OSError:
                continue

    def _validated_private_journal(
        self,
        payload: object,
        *,
        session_id: str,
        kind: str,
    ) -> list[dict[str, Any]]:
        expected_code = (
            "backup_import_restore_rollback_incomplete"
            if kind == "rollback"
            else "backup_import_restore_owner_cleanup_incomplete"
            if kind == "ownership"
            else "backup_import_staging_cleanup_incomplete"
        )
        if (
            not isinstance(payload, dict)
            or set(payload) != {"session_id", "tasks", "code"}
            or payload.get("session_id") != session_id
            or payload.get("code") != expected_code
            or not isinstance(payload.get("tasks"), list)
            or not payload["tasks"]
        ):
            raise ValueError("backup_import_private_journal_invalid")
        parsed: list[dict[str, Any]] = []
        task_ids: set[str] = set()
        expected_task_keys = (
            {"task_id", "restore_token", "pending_paths", "index_pending", "pending_resources", "pending_staging_paths", "organization_pending", "ownership_pending"}
            if kind == "rollback"
            else {"task_id", "restore_token", "task_ownership_pending", "pending_resources"}
            if kind == "ownership"
            else {"task_id", "pending_staging_paths"}
        )
        for raw in payload["tasks"]:
            if not isinstance(raw, dict) or set(raw) != expected_task_keys:
                raise ValueError("backup_import_private_journal_invalid")
            task_id = raw.get("task_id")
            if not isinstance(task_id, str) or not _TASK_ID_RE.fullmatch(task_id) or task_id in task_ids:
                raise ValueError("backup_import_private_journal_invalid")
            task_ids.add(task_id)
            staging = (
                self._validated_journal_staging_paths(raw.get("pending_staging_paths"))
                if kind != "ownership"
                else []
            )
            task: dict[str, Any] = {"task_id": task_id, "pending_staging_paths": staging}
            if kind == "rollback":
                restore_token = raw.get("restore_token")
                paths = self._validated_journal_task_paths(task_id, raw.get("pending_paths"))
                index_pending = raw.get("index_pending")
                organization_pending = raw.get("organization_pending")
                ownership_pending = raw.get("ownership_pending")
                resources = raw.get("pending_resources")
                if (
                    not isinstance(restore_token, str)
                    or not re.fullmatch(r"[0-9a-f]{32}", restore_token)
                    or not isinstance(index_pending, bool)
                    or not isinstance(organization_pending, bool)
                    or not isinstance(ownership_pending, bool)
                    or not isinstance(resources, list)
                ):
                    raise ValueError("backup_import_private_journal_invalid")
                parsed_resources = self._validated_journal_resources(resources)
                task.update(
                    restore_token=restore_token,
                    pending_paths=paths,
                    index_pending=index_pending,
                    pending_resources=parsed_resources,
                    organization_pending=organization_pending,
                    ownership_pending=ownership_pending,
                )
            elif kind == "ownership":
                restore_token = raw.get("restore_token")
                task_ownership_pending = raw.get("task_ownership_pending")
                resources = raw.get("pending_resources")
                if (
                    not isinstance(restore_token, str)
                    or not re.fullmatch(r"[0-9a-f]{32}", restore_token)
                    or not isinstance(task_ownership_pending, bool)
                    or not isinstance(resources, list)
                ):
                    raise ValueError("backup_import_private_journal_invalid")
                task.update(
                    restore_token=restore_token,
                    task_ownership_pending=task_ownership_pending,
                    pending_resources=self._validated_journal_resources(resources),
                )
            parsed.append(task)
        return parsed

    @staticmethod
    def _validated_journal_resources(resources: list[object]) -> list[dict[str, Any]]:
        parsed: list[dict[str, Any]] = []
        for resource in resources:
            if not isinstance(resource, dict) or set(resource) != {"kind", "id", "created", "version", "record", "restore_token"}:
                raise ValueError("backup_import_private_journal_invalid")
            record = resource.get("record")
            if (
                resource.get("kind") not in {"reference_asset", "gallery", "reference_file"}
                or not isinstance(resource.get("id"), str)
                or not _TASK_ID_RE.fullmatch(resource["id"])
                or resource.get("created") is not True
                or isinstance(resource.get("version"), bool)
                or not isinstance(resource.get("version"), int)
                or resource["version"] < 1
                or not isinstance(resource.get("restore_token"), str)
                or not re.fullmatch(r"[0-9a-f]{32}", resource["restore_token"])
                or not isinstance(record, dict)
                or record.get("id") != resource.get("id")
            ):
                raise ValueError("backup_import_private_journal_invalid")
            required_record_keys = {
                "reference_asset": {"id", "filename", "size_bytes", "sha256"},
                "gallery": {"id", "name", "category", "filename", "size_bytes", "sha256"},
                "reference_file": {"id", "filename", "mime_type", "family", "size_bytes"},
            }[resource["kind"]]
            if not required_record_keys.issubset(record):
                raise ValueError("backup_import_private_journal_invalid")
            parsed.append(dict(resource))
        return parsed

    def _validated_journal_staging_paths(self, value: object) -> list[Path]:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError("backup_import_private_journal_invalid")
        root = Path(os.path.abspath(self.root))
        parsed: list[Path] = []
        for raw in value:
            candidate = Path(raw)
            if not candidate.is_absolute():
                raise ValueError("backup_import_private_journal_invalid")
            absolute = Path(os.path.abspath(candidate))
            try:
                relative = absolute.relative_to(root)
            except ValueError:
                raise ValueError("backup_import_private_journal_invalid") from None
            parts = relative.parts
            if not parts or _STAGING_RE.fullmatch(parts[0]) is None or len(parts) > 2:
                raise ValueError("backup_import_private_journal_invalid")
            if len(parts) == 2 and not (parts[1].startswith("member-") and parts[1].endswith(".staged")):
                raise ValueError("backup_import_private_journal_invalid")
            if any(part.is_symlink() for part in (root / parts[0], absolute) if part.exists()):
                raise ValueError("backup_import_private_journal_invalid")
            parsed.append(absolute)
        return parsed

    def _validated_journal_task_paths(self, task_id: str, value: object) -> list[Path]:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError("backup_import_private_journal_invalid")
        storage = getattr(self.planner, "task_storage", None)
        if storage is None:
            raise ValueError("backup_import_private_journal_invalid")
        exact = {
            Path(os.path.abspath(storage.metadata_path(task_id))),
            Path(os.path.abspath(storage.request_path(task_id))),
        }
        roots = tuple(Path(os.path.abspath(item)) for item in (storage.input_root, storage.output_root))
        parsed: list[Path] = []
        for raw in value:
            candidate = Path(raw)
            if not candidate.is_absolute():
                raise ValueError("backup_import_private_journal_invalid")
            absolute = Path(os.path.abspath(candidate))
            allowed = absolute in exact
            if not allowed:
                try:
                    root = next(root for root in roots if absolute.is_relative_to(root))
                except StopIteration:
                    raise ValueError("backup_import_private_journal_invalid") from None
                name = absolute.name
                allowed = (
                    (root == roots[0] and (name.startswith(f"{task_id}-input-") or name.startswith(f"{task_id}-mask-")))
                    or (root == roots[1] and name.startswith(f"{task_id}-image-"))
                )
            if not allowed or absolute.is_symlink():
                raise ValueError("backup_import_private_journal_invalid")
            parsed.append(absolute)
        return parsed

    def _replay_cleanup_task(self, task: dict[str, Any]) -> dict[str, Any] | None:
        pending: list[Path] = []
        staging_roots: set[Path] = set()
        for path in task["pending_staging_paths"]:
            relative = path.relative_to(Path(os.path.abspath(self.root)))
            staging_root = Path(os.path.abspath(self.root)) / relative.parts[0]
            staging_roots.add(staging_root)
            if path != staging_root:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    if path.exists() or path.is_symlink():
                        pending.append(path)
        for staging_root in staging_roots:
            pending.extend(_cleanup_restore_staging(staging_root))
        pending = list(dict.fromkeys(pending))
        if not pending:
            return None
        return {"task_id": task["task_id"], "pending_staging_paths": [str(item) for item in pending]}

    def _replay_ownership_task(self, task: dict[str, Any]) -> dict[str, Any] | None:
        task_pending = bool(task["task_ownership_pending"])
        if task_pending:
            try:
                task_pending = not self.planner.task_storage.release_restore_ownership(
                    task["task_id"], task["restore_token"]
                )
            except Exception:
                task_pending = True
        resources: list[dict[str, Any]] = []
        for resource in task["pending_resources"]:
            kind = resource["kind"]
            storage = {
                "reference_asset": getattr(self.planner, "reference_asset_storage", None),
                "gallery": getattr(self.planner, "gallery_storage", None),
                "reference_file": getattr(self.planner, "reference_file_storage", None),
            }[kind]
            if storage is None:
                resources.append(resource)
                continue
            handle_type = {
                "reference_asset": ReferenceAssetRestore,
                "gallery": GalleryRestore,
                "reference_file": ReferenceFileRestore,
            }[kind]
            handle = handle_type(
                resource["record"],
                True,
                resource["version"],
                resource["restore_token"],
            )
            try:
                released = storage.release_restore_ownership(handle)
            except Exception:
                released = False
            if not released:
                resources.append(resource)
        if not task_pending and not resources:
            return None
        return {
            "task_id": task["task_id"],
            "restore_token": task["restore_token"],
            "task_ownership_pending": task_pending,
            "pending_resources": resources,
        }

    def _replay_rollback_task(self, task: dict[str, Any]) -> dict[str, Any] | None:
        storage = self.planner.task_storage
        restore_token = task["restore_token"]
        if not storage.restore_ownership_matches(task["task_id"], restore_token):
            return self._serialized_rollback_task(task)
        pending_paths = tuple(task["pending_paths"])
        index_pending = bool(task["index_pending"])
        if pending_paths or index_pending:
            try:
                storage.rollback_restored_task_files(
                    RestoredTaskFilesJournal(task["task_id"], pending_paths, restore_token)
                )
            except RestoredTaskRollbackIncomplete as exc:
                pending_paths = exc.journal.pending_paths
                index_pending = exc.journal.index_pending
            except Exception:
                pass
            else:
                pending_paths = ()
                index_pending = False
        resources: list[dict[str, Any]] = []
        reference_snapshot: dict[str, dict[str, set[str]]] | None = None
        if task["pending_resources"]:
            try:
                reference_snapshot = storage.resource_reference_snapshot()
            except Exception:
                reference_snapshot = None
        for resource in task["pending_resources"]:
            if reference_snapshot is None or not self._replay_resource(
                resource,
                rollback_task_id=task["task_id"],
                reference_snapshot=reference_snapshot,
            ):
                resources.append(resource)
        organization_pending = bool(task["organization_pending"])
        if organization_pending:
            try:
                storage.history_organizer.delete_task_state(task["task_id"])
            except Exception:
                pass
            else:
                organization_pending = False
        cleanup = self._replay_cleanup_task(task)
        pending_staging = cleanup["pending_staging_paths"] if cleanup else []
        ownership_pending = bool(task["ownership_pending"])
        if not (pending_paths or index_pending or resources or pending_staging or organization_pending):
            try:
                ownership_pending = not storage.clear_restore_ownership(
                    task["task_id"], restore_token
                )
            except OSError:
                ownership_pending = True
        if not (pending_paths or index_pending or resources or pending_staging or organization_pending or ownership_pending):
            return None
        return {
            "task_id": task["task_id"],
            "restore_token": restore_token,
            "pending_paths": [str(item) for item in pending_paths],
            "index_pending": index_pending,
            "pending_resources": resources,
            "pending_staging_paths": pending_staging,
            "organization_pending": organization_pending,
            "ownership_pending": ownership_pending,
        }

    @staticmethod
    def _serialized_rollback_task(task: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": task["task_id"],
            "restore_token": task["restore_token"],
            "pending_paths": [str(item) for item in task["pending_paths"]],
            "index_pending": task["index_pending"],
            "pending_resources": task["pending_resources"],
            "pending_staging_paths": [str(item) for item in task["pending_staging_paths"]],
            "organization_pending": task["organization_pending"],
            "ownership_pending": task["ownership_pending"],
        }

    def _replay_resource(
        self,
        resource: dict[str, Any],
        *,
        rollback_task_id: str,
        reference_snapshot: dict[str, dict[str, set[str]]],
    ) -> bool:
        kind = resource["kind"]
        storage = {
            "reference_asset": getattr(self.planner, "reference_asset_storage", None),
            "gallery": getattr(self.planner, "gallery_storage", None),
            "reference_file": getattr(self.planner, "reference_file_storage", None),
        }[kind]
        if storage is None:
            return False
        try:
            expected = resource["record"]
            handle_type = {
                "reference_asset": ReferenceAssetRestore,
                "gallery": GalleryRestore,
                "reference_file": ReferenceFileRestore,
            }[kind]
            handle = handle_type(
                expected,
                True,
                resource["version"],
                resource["restore_token"],
            )
            with storage._lock:
                references = reference_snapshot[kind]
                referencing_tasks = references.get(resource["id"], set())
                if referencing_tasks - {rollback_task_id}:
                    return bool(storage.release_restore_ownership(handle))
                if referencing_tasks:
                    return False
                if not storage.restore_identity_matches(handle):
                    return True
                if storage.rollback_restore(handle):
                    return True
                return not storage.restore_target_exists(handle)
        except Exception:
            return False

    def _journal_referenced_staging(self) -> set[Path]:
        references: set[Path] = set()
        root = Path(os.path.abspath(self.root))
        journal_re = re.compile(
            rf"^{re.escape(_PREFIX)}(?P<session>[0-9a-f]{{32}})\.(?P<kind>rollback|cleanup)\.json$"
        )
        try:
            paths = tuple(self.root.iterdir())
        except OSError:
            return references
        for path in paths:
            match = journal_re.fullmatch(path.name)
            if match is None:
                continue
            try:
                if stat.S_ISLNK(path.lstat().st_mode) or not path.is_file():
                    continue
                payload = json.loads(path.read_text(encoding="utf-8"))
                expected_code = (
                    "backup_import_restore_rollback_incomplete"
                    if match.group("kind") == "rollback"
                    else "backup_import_staging_cleanup_incomplete"
                )
                if (
                    not isinstance(payload, dict)
                    or payload.get("session_id") != match.group("session")
                    or payload.get("code") != expected_code
                    or not isinstance(payload.get("tasks"), list)
                ):
                    continue
                pending: list[str] = []
                valid = True
                for task in payload["tasks"]:
                    values = task.get("pending_staging_paths") if isinstance(task, dict) else None
                    if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
                        valid = False
                        break
                    pending.extend(values)
                if not valid:
                    continue
                parsed: set[Path] = set()
                for raw in pending:
                    candidate = Path(raw)
                    if not candidate.is_absolute():
                        valid = False
                        break
                    absolute = Path(os.path.abspath(candidate))
                    try:
                        absolute.relative_to(root)
                    except ValueError:
                        valid = False
                        break
                    parsed.add(absolute)
                if valid:
                    references.update(parsed)
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return references

    def _write_plan(self, session_id: str, manifest: BackupManifest, preview: BackupImportPreview) -> None:
        classifications = {
            key: [asdict(item) for item in getattr(preview, key)]
            for key in ("restorable", "duplicate", "conflict", "invalid")
        }
        self._atomic_json(
            self._plan_path(session_id),
            {
                "session_id": session_id,
                "whole_file_sha256": preview.whole_file_sha256,
                "manifest": _manifest_json(manifest),
                "classifications": classifications,
            },
        )

    def _atomic_json(self, path: Path, payload: object) -> None:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=self.root)
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
                descriptor = -1
                json.dump(payload, destination, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
                destination.flush()
                os.fsync(destination.fileno())
            os.replace(temporary, path)
            _fsync_directory(self.root)
        except Exception:
            if descriptor >= 0:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)
            raise

    def _require_record(self, session_id: str) -> _SessionRecord:
        record = self._records.get(session_id)
        if record is None:
            raise ValueError("backup_import_not_found")
        return record

    def _safe_unlink(self, path: Path) -> None:
        try:
            if path.parent.resolve() != self.root.resolve():
                return
            if not path.name.startswith(_PREFIX):
                return
            if not path.name.endswith((".upload.partial", ".status.json", ".plan.json", ".result.json")):
                return
            path.unlink(missing_ok=True)
        except OSError:
            return

    def _upload_path(self, session_id: str) -> Path:
        return self.root / f"{_PREFIX}{session_id}.upload.partial"

    def _status_path(self, session_id: str) -> Path:
        return self.root / f"{_PREFIX}{session_id}.status.json"

    def _plan_path(self, session_id: str) -> Path:
        return self.root / f"{_PREFIX}{session_id}.plan.json"

    def _result_path(self, session_id: str) -> Path:
        return self.root / f"{_PREFIX}{session_id}.result.json"


def _validated_filename(filename: object) -> str:
    if not isinstance(filename, str) or not filename or len(filename) > 255:
        raise ValueError("backup_import_filename_invalid")
    if filename != Path(filename).name or "/" in filename or "\\" in filename:
        raise ValueError("backup_import_filename_invalid")
    if any(ord(character) < 32 or ord(character) == 127 for character in filename):
        raise ValueError("backup_import_filename_invalid")
    if Path(filename).suffix.lower() != ".zip":
        raise ValueError("backup_import_filename_invalid")
    return filename


def _session_from_status(payload: object, expected_session_id: str) -> BackupImportSession:
    if not isinstance(payload, dict) or payload.get("session_id") != expected_session_id:
        raise ValueError("backup_import_status_invalid")
    status = payload.get("status")
    if status not in {"uploading", "uploaded", "validated", "restoring", "restored", "failed", "interrupted"}:
        raise ValueError("backup_import_status_invalid")
    filename = _validated_filename(payload.get("filename"))
    size_bytes = payload.get("size_bytes")
    uploaded_bytes = payload.get("uploaded_bytes")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in (size_bytes, uploaded_bytes)):
        raise ValueError("backup_import_status_invalid")
    if size_bytes <= 0 or uploaded_bytes > size_bytes:
        raise ValueError("backup_import_status_invalid")
    created_at = payload.get("created_at")
    updated_at = payload.get("updated_at")
    if not isinstance(created_at, str) or not isinstance(updated_at, str):
        raise ValueError("backup_import_status_invalid")
    for value in (created_at, updated_at):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("backup_import_status_invalid")
    whole = payload.get("whole_file_sha256")
    if whole is not None and (not isinstance(whole, str) or not _SHA256_RE.fullmatch(whole)):
        raise ValueError("backup_import_status_invalid")
    error_code = payload.get("error_code")
    if error_code is not None and error_code not in _PERSISTED_SESSION_ERROR_CODES:
        raise ValueError("backup_import_status_invalid")
    return BackupImportSession(
        session_id=expected_session_id,
        filename=filename,
        size_bytes=size_bytes,
        uploaded_bytes=uploaded_bytes,
        status=status,
        created_at=created_at,
        updated_at=updated_at,
        whole_file_sha256=whole,
        error_code=error_code,
    )


def _result_from_json(payload: object) -> BackupImportResult:
    if not isinstance(payload, dict) or set(payload) != {
        "restored", "duplicates", "conflicts", "invalid", "failed",
        "thumbnail_warnings", "cleanup_warnings",
    }:
        raise ValueError("backup_import_result_invalid")
    parsed: dict[str, tuple[BackupImportTaskResult, ...]] = {}
    for key, values in payload.items():
        if not isinstance(values, list):
            raise ValueError("backup_import_result_invalid")
        items: list[BackupImportTaskResult] = []
        for value in values:
            if not isinstance(value, dict) or set(value) != {"task_id", "classification", "reason"}:
                raise ValueError("backup_import_result_invalid")
            task_id = value.get("task_id")
            classification = value.get("classification")
            reason = value.get("reason")
            if (
                not isinstance(task_id, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", task_id)
                or classification not in {"restorable", "restored", "duplicate", "conflict", "invalid", "failed", "thumbnail_warning", "cleanup_warning"}
                or (reason is not None and reason not in _SAFE_RESULT_REASON_CODES)
            ):
                raise ValueError("backup_import_result_invalid")
            items.append(BackupImportTaskResult(task_id, classification, reason))
        parsed[key] = tuple(items)
    return BackupImportResult(**parsed)


def _result_matches_terminal(
    session: BackupImportSession,
    result: BackupImportResult,
) -> bool:
    if session.status == "restored":
        return session.error_code is None
    if session.status == "failed":
        return (
            session.error_code == "backup_import_restore_rollback_incomplete"
            and any(
                item.reason == "backup_import_restore_rollback_incomplete"
                for item in result.failed
            )
        )
    return False


def _validated_session_id(session_id: object) -> str:
    if not isinstance(session_id, str) or not _SESSION_ID_RE.fullmatch(session_id):
        raise ValueError("backup_import_not_found")
    return session_id


def _task_semantic_error(
    task: BackupTaskEntry,
    metadata: object,
    request: object,
    organization: object,
) -> str | None:
    if not isinstance(metadata, dict) or not isinstance(request, dict) or not isinstance(organization, dict):
        return "backup_import_task_required_json_missing"
    metadata_task_id = metadata.get("task_id")
    if metadata_task_id is not None and metadata_task_id != task.task_id:
        return "backup_import_task_id_mismatch"
    if not str(metadata.get("created_at") or "").strip():
        return "backup_import_task_metadata_invalid"
    if str(metadata.get("status") or "") not in TERMINAL_TASK_STATUSES:
        return "backup_import_task_not_terminal"
    if _contains_sensitive_request_key(metadata):
        return "backup_import_metadata_contains_sensitive_fields"
    if _contains_sensitive_request_key(request):
        return "backup_import_request_contains_sensitive_fields"
    tags = organization.get("tags")
    if (
        not isinstance(organization.get("favorite"), bool)
        or not isinstance(tags, list)
        or any(
            not isinstance(tag, dict) or not str(tag.get("name") or "").strip()
            for tag in tags
        )
    ):
        return "backup_import_task_organization_invalid"
    role_counts = {role: 0 for role in _JSON_ROLES}
    for entry in task.files:
        if entry.role in role_counts:
            role_counts[entry.role] += 1
    if any(count != 1 for count in role_counts.values()):
        return "backup_import_task_required_json_invalid"
    return None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(_STREAM_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_json(manifest: BackupManifest) -> dict[str, object]:
    return {
        "format": manifest.format,
        "version": manifest.version,
        "created_at": manifest.created_at,
        "app_version": manifest.app_version,
        "scope": manifest.scope,
        "task_count": manifest.task_count,
        "file_count": manifest.file_count,
        "uncompressed_bytes": manifest.uncompressed_bytes,
        "tasks": [
            {
                "task_id": task.task_id,
                "created_at": task.created_at,
                "fingerprint": task.fingerprint,
                "files": [asdict(entry) for entry in task.files],
            }
            for task in manifest.tasks
        ],
    }


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _cleanup_restore_staging(path: Path) -> tuple[Path, ...]:
    pending: list[Path] = []
    try:
        items = tuple(path.iterdir())
    except FileNotFoundError:
        return ()
    except OSError:
        return (path,)
    for item in items:
        if not (
            item.name.startswith("member-")
            and item.name.endswith(".staged")
        ):
            pending.append(item)
            continue
        try:
            item.unlink(missing_ok=True)
        except OSError:
            if item.exists() or item.is_symlink():
                pending.append(item)
    if pending:
        return tuple(pending)
    try:
        path.rmdir()
    except FileNotFoundError:
        return ()
    except OSError:
        if path.exists():
            return (path,)
    return ()


def _restore_resource_is_pending(kind: str, storage: Any, handle: Any) -> bool:
    if not bool(getattr(handle, "created", False)):
        return False
    try:
        return bool(storage.restore_identity_matches(handle))
    except Exception:
        return True


def _read_staged_member(path: Path, maximum: int) -> bytes:
    payload = bytearray()
    with path.open("rb") as source:
        while chunk := source.read(min(_STREAM_BYTES, maximum + 1 - len(payload))):
            payload.extend(chunk)
            if len(payload) > maximum:
                raise ValueError("backup_import_member_too_large")
    return bytes(payload)


__all__ = (
    "BackupImportClassification",
    "BackupImportPreview",
    "BackupImportResult",
    "BackupImportSession",
    "BackupImportStatus",
    "BackupImportTaskResult",
    "HistoryBackupImportService",
)
