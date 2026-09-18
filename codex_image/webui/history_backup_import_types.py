from __future__ import annotations
from dataclasses import dataclass
from typing import Literal


BackupImportStatus = Literal["uploading", "uploaded", "validated", "restoring", "restored", "failed", "interrupted"]


BackupImportClassification = Literal[
    "restorable",
    "restored",
    "duplicate",
    "conflict",
    "invalid",
    "failed",
    "thumbnail_warning",
    "cleanup_warning",
]


@dataclass(frozen=True)
class BackupImportTaskResult:
    task_id: str
    classification: BackupImportClassification
    reason: str | None = None


@dataclass(frozen=True)
class BackupImportPreview:
    session_id: str
    whole_file_sha256: str
    restorable: tuple[BackupImportTaskResult, ...]
    duplicate: tuple[BackupImportTaskResult, ...]
    conflict: tuple[BackupImportTaskResult, ...]
    invalid: tuple[BackupImportTaskResult, ...]


@dataclass(frozen=True)
class BackupImportResult:
    restored: tuple[BackupImportTaskResult, ...]
    duplicates: tuple[BackupImportTaskResult, ...]
    conflicts: tuple[BackupImportTaskResult, ...]
    invalid: tuple[BackupImportTaskResult, ...]
    failed: tuple[BackupImportTaskResult, ...]
    thumbnail_warnings: tuple[BackupImportTaskResult, ...]
    cleanup_warnings: tuple[BackupImportTaskResult, ...] = ()


@dataclass(frozen=True)
class BackupImportSession:
    session_id: str
    filename: str
    size_bytes: int
    uploaded_bytes: int
    status: BackupImportStatus
    created_at: str
    updated_at: str
    whole_file_sha256: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class BackupImportSnapshot:
    session: BackupImportSession
    result: BackupImportResult | None = None


@dataclass
class _SessionRecord:
    session: BackupImportSession
    digest: object
    last_offset: int | None = None
    last_size: int = 0
    last_sha256: str | None = None
    preview: BackupImportPreview | None = None
    result: BackupImportResult | None = None
