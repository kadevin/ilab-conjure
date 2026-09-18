from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal
from .user_config_backup_components import ClientPreferences
from .user_config_backup_format import UserConfigSection


UserConfigRestoreStatus = Literal[
    "uploading",
    "uploaded",
    "validated",
    "restoring",
    "restored",
    "interrupted",
]


@dataclass(frozen=True)
class UserConfigRestoreSession:
    session_id: str
    filename: str
    size_bytes: int
    uploaded_bytes: int
    status: UserConfigRestoreStatus
    created_at: str
    updated_at: str
    archive_sha256: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class UserConfigRestoreGroupPreview:
    group: str
    archive_count: int
    current_count: int


@dataclass(frozen=True)
class UserConfigRestoreSectionPreview:
    section: UserConfigSection
    archive_count: int
    identical_count: int
    conflicts: int
    missing_assets: int
    replace_existing_count: int
    estimated_write_bytes: int
    warnings: tuple[str, ...]
    current_fingerprint: str
    groups: tuple[UserConfigRestoreGroupPreview, ...]


@dataclass(frozen=True)
class UserConfigRestorePreview:
    session_id: str
    archive_sha256: str
    preview_revision: str
    format_version: int
    restorable: bool
    contains_secrets: bool
    sections: tuple[UserConfigRestoreSectionPreview, ...]
    path_fields: dict[str, str]
    keyed_provider_retention_count: int
    gallery_history_reference_impact: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class UserConfigRestoreSnapshot:
    session: UserConfigRestoreSession
    preview: UserConfigRestorePreview | None
    result: UserConfigRestoreResult | None = None


@dataclass(frozen=True)
class SectionRestoreStats:
    added: int = 0
    replaced: int = 0
    skipped: int = 0
    recovery_copies: int = 0
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class UserConfigRestoreResult:
    session_id: str
    status: Literal["restored"]
    sections: tuple[UserConfigSection, ...]
    mode: Literal["incremental", "replace"]
    section_stats: dict[UserConfigSection, SectionRestoreStats]
    client_preferences: ClientPreferences | None
    restart_required: bool


@dataclass
class _SessionRecord:
    session: UserConfigRestoreSession
    digest: Any
    preview: UserConfigRestorePreview | None = None
    result: UserConfigRestoreResult | None = None
    last_offset: int | None = None
    last_size: int = 0
    last_sha256: str | None = None
