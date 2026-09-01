from __future__ import annotations

from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
from threading import Event, RLock
from typing import Callable, Literal
from uuid import uuid4
import zipfile

from .atomic_files import atomic_write_text
from .resource_limits import (
    MAX_USER_CONFIG_BACKUP_MANIFEST_BYTES,
    USER_CONFIG_BACKUP_FREE_RATIO,
    USER_CONFIG_BACKUP_MIN_FREE_BYTES,
)
from .user_config_backup_components import (
    ClientPreferences,
    FileIdentity,
    PlannedUserConfigMember,
    UserConfigBackupPlan,
    UserConfigBackupPlanner,
)
from .user_config_backup_format import (
    UserConfigSection,
    serialize_user_config_manifest,
)


UserConfigBackupStatus = Literal[
    "queued",
    "planning",
    "packing",
    "ready",
    "failed",
    "cancelled",
    "expired",
    "interrupted",
]

_ACTIVE_STATUSES = frozenset({"queued", "planning", "packing"})
_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class UserConfigBackupJob:
    job_id: str
    status: UserConfigBackupStatus
    created_at: str
    updated_at: str
    sections: tuple[UserConfigSection, ...]
    total_members: int
    completed_members: int
    total_bytes: int
    completed_bytes: int
    warnings: tuple[str, ...]
    filename: str | None
    download_url: str | None
    error_code: str | None


@dataclass
class _JobRecord:
    job: UserConfigBackupJob
    include_api_keys: bool
    client_preferences: ClientPreferences | None
    cancelled: Event
    ready_at: datetime | None = None


class _Cancelled(Exception):
    pass


class UserConfigBackupExportService:
    def __init__(
        self,
        planner: UserConfigBackupPlanner,
        root: Path | str,
        *,
        executor: Executor | None = None,
        clock: Callable[[], datetime] | None = None,
        disk_usage: Callable[[Path], object] = shutil.disk_usage,
        min_free_bytes: int = USER_CONFIG_BACKUP_MIN_FREE_BYTES,
        free_ratio: float = USER_CONFIG_BACKUP_FREE_RATIO,
        ttl_seconds: int = 24 * 60 * 60,
        chunk_bytes: int = 1024 * 1024,
        max_manifest_bytes: int = MAX_USER_CONFIG_BACKUP_MANIFEST_BYTES,
        recover_on_init: bool = True,
    ) -> None:
        if min_free_bytes < 0 or not 0 <= free_ratio < 1:
            raise ValueError("user_config_backup_capacity_config_invalid")
        if ttl_seconds <= 0 or chunk_bytes <= 0 or max_manifest_bytes <= 0:
            raise ValueError("user_config_backup_runtime_config_invalid")
        self.planner = planner
        self.root = Path(root)
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="user-config-backup",
        )
        self._owns_executor = executor is None
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._disk_usage = disk_usage
        self._min_free_bytes = min_free_bytes
        self._free_ratio = free_ratio
        self._ttl_seconds = ttl_seconds
        self._chunk_bytes = chunk_bytes
        self._max_manifest_bytes = max_manifest_bytes
        self._lock = RLock()
        self._records: dict[str, _JobRecord] = {}
        self._accepting = False
        self._recovered = False
        self._progress_observer: Callable[[UserConfigBackupJob], None] | None = None
        if recover_on_init:
            self.recover_startup()

    def recover_startup(self) -> None:
        with self._lock:
            if self._recovered:
                return
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            if self.root.is_symlink() or not self.root.is_dir():
                raise ValueError("user_config_backup_root_invalid")
            os.chmod(self.root, 0o700)
            for status_path in self.root.glob("*.json"):
                self._recover_status(status_path)
            for partial in self.root.glob("*.partial"):
                partial.unlink(missing_ok=True)
            self._recovered = True
            self._accepting = True
        self.cleanup_expired()

    def create(
        self,
        sections,
        include_api_keys: bool,
        client_preferences: ClientPreferences | None,
    ) -> UserConfigBackupJob:
        self.cleanup_expired()
        now = self._now()
        job_id = uuid4().hex
        normalized_sections = tuple(sections)
        job = UserConfigBackupJob(
            job_id=job_id,
            status="queued",
            created_at=_timestamp(now),
            updated_at=_timestamp(now),
            sections=normalized_sections,
            total_members=0,
            completed_members=0,
            total_bytes=0,
            completed_bytes=0,
            warnings=(),
            filename=None,
            download_url=None,
            error_code=None,
        )
        with self._lock:
            if not self._accepting:
                raise ValueError("user_config_backup_lifecycle_conflict")
            if any(record.job.status in _ACTIVE_STATUSES for record in self._records.values()):
                raise ValueError("user_config_backup_active")
            record = _JobRecord(
                job=job,
                include_api_keys=include_api_keys,
                client_preferences=client_preferences,
                cancelled=Event(),
            )
            self._records[job_id] = record
            self._write_status(record)
            try:
                self._executor.submit(self._run, job_id)
            except Exception:
                self._fail(job_id, "user_config_backup_executor_unavailable")
        return self.get(job_id) or job

    def get(self, job_id: str) -> UserConfigBackupJob | None:
        self.cleanup_expired()
        with self._lock:
            record = self._records.get(str(job_id))
            return record.job if record is not None else None

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            record = self._records.get(str(job_id))
            if record is None or record.job.status not in _ACTIVE_STATUSES:
                return False
            record.cancelled.set()
            if record.job.status == "queued":
                record.job = self._changed(record.job, status="cancelled")
                self._write_status(record)
                self._delete_archive_files(record.job.job_id)
            return True

    def discard(self, job_id: str) -> UserConfigBackupJob | None:
        normalized = str(job_id)
        with self._lock:
            record = self._records.get(normalized)
            if record is None or record.job.status in _ACTIVE_STATUSES:
                return None
            snapshot = self._changed(
                record.job,
                status="expired",
                filename=None,
                download_url=None,
            )
            self._delete_job_files(normalized)
            self._records.pop(normalized, None)
            return snapshot

    def download_path(self, job_id: str) -> Path:
        self.cleanup_expired()
        normalized = str(job_id)
        with self._lock:
            record = self._records.get(normalized)
            if record is None:
                raise ValueError("user_config_backup_not_found")
            if record.job.status != "ready":
                raise ValueError("user_config_backup_not_ready")
            ready_path = self.root / f"{normalized}.zip"
            if not ready_path.is_file() or ready_path.is_symlink():
                raise ValueError("user_config_backup_not_ready")
            return ready_path

    def cleanup_expired(self) -> int:
        now = self._now()
        expired: list[str] = []
        with self._lock:
            for job_id, record in self._records.items():
                if record.job.status in _ACTIVE_STATUSES:
                    continue
                updated = _parse_timestamp(record.job.updated_at)
                if (now - updated).total_seconds() > self._ttl_seconds:
                    expired.append(job_id)
            for job_id in expired:
                self._delete_job_files(job_id)
                self._records.pop(job_id, None)
        return len(expired)

    def close(self) -> None:
        with self._lock:
            self._accepting = False
        if self._owns_executor:
            shutdown = getattr(self._executor, "shutdown", None)
            if callable(shutdown):
                shutdown(wait=True, cancel_futures=False)

    def _run(self, job_id: str) -> None:
        try:
            record = self._record(job_id)
            self._raise_if_cancelled(record)
            self._update(job_id, status="planning")
            plan = self.planner.plan(
                record.job.sections,
                include_api_keys=record.include_api_keys,
                client_preferences=record.client_preferences,
            )
            self._raise_if_cancelled(record)
            manifest_bytes = serialize_user_config_manifest(plan.manifest)
            if len(manifest_bytes) > self._max_manifest_bytes:
                raise ValueError("user_config_backup_manifest_too_large")
            total_bytes = sum(member.entry.size_bytes for member in plan.members)
            self._ensure_capacity(total_bytes + len(manifest_bytes))
            self._update(
                job_id,
                status="packing",
                total_members=len(plan.members),
                total_bytes=total_bytes,
                warnings=tuple(dict.fromkeys(warning.code for warning in plan.warnings)),
            )
            self._write_archive(job_id, plan, manifest_bytes)
            self._raise_if_cancelled(record)
            now = self._now()
            filename = _backup_filename(now)
            with self._lock:
                record = self._records[job_id]
                record.ready_at = now
                record.job = self._changed(
                    record.job,
                    status="ready",
                    filename=filename,
                    download_url=f"/api/user-config-backups/{job_id}/download",
                )
                self._write_status(record)
                self._notify(record.job)
        except _Cancelled:
            self._cancelled(job_id)
        except ValueError as exc:
            code = str(exc)
            safe_code = (
                code
                if code.startswith("user_config_backup_")
                else "user_config_backup_failed"
            )
            self._fail(job_id, safe_code)
        except Exception:
            self._fail(job_id, "user_config_backup_failed")

    def _write_archive(
        self,
        job_id: str,
        plan: UserConfigBackupPlan,
        manifest_bytes: bytes,
    ) -> None:
        partial_path = self.root / f"{job_id}.partial"
        ready_path = self.root / f"{job_id}.zip"
        try:
            with zipfile.ZipFile(
                partial_path,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                allowZip64=True,
            ) as archive:
                for member in plan.members:
                    record = self._record(job_id)
                    self._raise_if_cancelled(record)
                    if member.data is not None:
                        archive.writestr(member.entry.path, member.data)
                        written = len(member.data)
                    else:
                        written = self._write_source_member(archive, member)
                    self._advance(job_id, written)
                archive.writestr("manifest.json", manifest_bytes)
            os.chmod(partial_path, 0o600)
            os.replace(partial_path, ready_path)
            os.chmod(ready_path, 0o600)
        finally:
            partial_path.unlink(missing_ok=True)

    def _write_source_member(
        self,
        archive: zipfile.ZipFile,
        member: PlannedUserConfigMember,
    ) -> int:
        if member.source_path is None or member.source_identity is None:
            raise ValueError("user_config_backup_plan_invalid")
        if not _source_identity_matches(member.source_path, member.source_identity):
            raise ValueError("user_config_backup_source_changed")
        digest = hashlib.sha256()
        written = 0
        try:
            with member.source_path.open("rb") as source, archive.open(
                member.entry.path,
                "w",
                force_zip64=True,
            ) as destination:
                while chunk := source.read(self._chunk_bytes):
                    destination.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)
        except OSError as exc:
            raise ValueError("user_config_backup_source_unreadable") from exc
        if (
            written != member.entry.size_bytes
            or digest.hexdigest() != member.entry.sha256
            or not _source_stat_matches(member.source_path, member.source_identity)
        ):
            raise ValueError("user_config_backup_source_changed")
        return written

    def _ensure_capacity(self, archive_bytes: int) -> None:
        try:
            usage = self._disk_usage(self.root)
            free = int(getattr(usage, "free"))
        except (OSError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError("user_config_backup_capacity_unavailable") from exc
        reserve = max(
            self._min_free_bytes,
            math.ceil(archive_bytes * self._free_ratio),
        )
        if free < archive_bytes + reserve:
            raise ValueError("user_config_backup_insufficient_space")

    def _record(self, job_id: str) -> _JobRecord:
        with self._lock:
            record = self._records.get(job_id)
            if record is None:
                raise _Cancelled
            return record

    def _raise_if_cancelled(self, record: _JobRecord) -> None:
        if record.cancelled.is_set() or record.job.status == "cancelled":
            raise _Cancelled

    def _update(self, job_id: str, **changes) -> None:
        with self._lock:
            record = self._records[job_id]
            record.job = self._changed(record.job, **changes)
            self._write_status(record)
            self._notify(record.job)

    def _advance(self, job_id: str, written: int) -> None:
        with self._lock:
            record = self._records[job_id]
            record.job = self._changed(
                record.job,
                completed_members=record.job.completed_members + 1,
                completed_bytes=record.job.completed_bytes + written,
            )
            self._write_status(record)
            self._notify(record.job)

    def _cancelled(self, job_id: str) -> None:
        with self._lock:
            record = self._records.get(job_id)
            if record is None:
                return
            record.job = self._changed(
                record.job,
                status="cancelled",
                filename=None,
                download_url=None,
            )
            self._write_status(record)
            self._delete_archive_files(job_id)

    def _fail(self, job_id: str, error_code: str) -> None:
        with self._lock:
            record = self._records.get(job_id)
            if record is None:
                return
            record.job = self._changed(
                record.job,
                status="failed",
                filename=None,
                download_url=None,
                error_code=error_code,
            )
            self._write_status(record)
            self._delete_archive_files(job_id)
            self._notify(record.job)

    def _changed(self, job: UserConfigBackupJob, **changes) -> UserConfigBackupJob:
        return replace(job, updated_at=_timestamp(self._now()), **changes)

    def _write_status(self, record: _JobRecord) -> None:
        payload = {
            **asdict(record.job),
            "sections": list(record.job.sections),
            "warnings": list(record.job.warnings),
        }
        atomic_write_text(
            self.root / f"{record.job.job_id}.json",
            json.dumps(payload, indent=2, ensure_ascii=False),
            mode=0o600,
        )

    def _recover_status(self, path: Path) -> None:
        job_id = path.stem
        if _JOB_ID_RE.fullmatch(job_id) is None or path.is_symlink():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            sections = tuple(payload.get("sections", []))
            status = str(payload.get("status") or "")
            created_at = str(payload.get("created_at") or "")
            updated_at = str(payload.get("updated_at") or created_at)
            _parse_timestamp(created_at)
            _parse_timestamp(updated_at)
        except (OSError, ValueError, json.JSONDecodeError, TypeError):
            return
        if status in _ACTIVE_STATUSES:
            status = "interrupted"
            error_code = "user_config_backup_interrupted"
        else:
            error_code = payload.get("error_code")
        if status not in {
            "ready",
            "failed",
            "cancelled",
            "interrupted",
        }:
            return
        ready_exists = (self.root / f"{job_id}.zip").is_file()
        if status == "ready" and not ready_exists:
            status = "interrupted"
            error_code = "user_config_backup_interrupted"
        job = UserConfigBackupJob(
            job_id=job_id,
            status=status,
            created_at=created_at,
            updated_at=_timestamp(self._now()) if status == "interrupted" else updated_at,
            sections=sections,
            total_members=int(payload.get("total_members") or 0),
            completed_members=int(payload.get("completed_members") or 0),
            total_bytes=int(payload.get("total_bytes") or 0),
            completed_bytes=int(payload.get("completed_bytes") or 0),
            warnings=tuple(str(item) for item in payload.get("warnings", [])),
            filename=payload.get("filename") if status == "ready" else None,
            download_url=payload.get("download_url") if status == "ready" else None,
            error_code=str(error_code) if error_code else None,
        )
        record = _JobRecord(
            job=job,
            include_api_keys=False,
            client_preferences=None,
            cancelled=Event(),
        )
        self._records[job_id] = record
        if status == "interrupted":
            self._write_status(record)

    def _delete_archive_files(self, job_id: str) -> None:
        for suffix in (".partial", ".zip"):
            (self.root / f"{job_id}{suffix}").unlink(missing_ok=True)

    def _delete_job_files(self, job_id: str) -> None:
        for suffix in (".partial", ".zip", ".claimed", ".json"):
            (self.root / f"{job_id}{suffix}").unlink(missing_ok=True)

    def _notify(self, job: UserConfigBackupJob) -> None:
        if self._progress_observer is not None:
            self._progress_observer(job)

    def _now(self) -> datetime:
        now = self._clock()
        return now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)


def _source_stat_matches(path: Path, identity: FileIdentity) -> bool:
    try:
        current = path.stat()
    except OSError:
        return False
    return (
        current.st_size == identity.size_bytes
        and current.st_mtime_ns == identity.mtime_ns
        and current.st_dev == identity.device
        and current.st_ino == identity.inode
        and path.is_file()
        and not path.is_symlink()
    )


def _source_identity_matches(path: Path, identity: FileIdentity) -> bool:
    if not _source_stat_matches(path, identity):
        return False
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    except OSError:
        return False
    return digest.hexdigest() == identity.sha256 and _source_stat_matches(path, identity)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _backup_filename(value: datetime) -> str:
    stamp = value.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"ilab-conjure-user-config-{stamp}.zip"


__all__ = (
    "UserConfigBackupExportService",
    "UserConfigBackupJob",
    "UserConfigBackupStatus",
)
