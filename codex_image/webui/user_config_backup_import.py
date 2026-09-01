from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import stat
from threading import RLock
from typing import Any, Callable, Literal
import unicodedata
from uuid import uuid4
import zipfile

from .atomic_files import atomic_write_bytes, atomic_write_text
from .color_settings import _normalize_color_palette_payload
from .image_uploads import InvalidRasterImage, validate_raster_image
from .prompt_snippets import _normalize_prompt_snippets_payload
from .provider_validation import provider_url_origin, validate_v2_payload
from .gallery_storage import GallerySnapshot, GallerySnapshotItem
from .resource_limits import (
    MAX_USER_CONFIG_BACKUP_COMPRESSION_RATIO,
    MAX_USER_CONFIG_BACKUP_ENTRIES,
    MAX_USER_CONFIG_BACKUP_EXPANDED_BYTES,
    MAX_USER_CONFIG_BACKUP_MANIFEST_BYTES,
    MAX_USER_CONFIG_BACKUP_MEMBER_BYTES,
    MAX_USER_CONFIG_BACKUP_UPLOAD_BYTES,
    USER_CONFIG_BACKUP_FREE_RATIO,
    USER_CONFIG_BACKUP_MIN_FREE_BYTES,
    USER_CONFIG_BACKUP_UPLOAD_CHUNK_BYTES,
)
from .user_config_backup_components import (
    ClientPreferences,
    UserConfigBackupPlanner,
)
from .user_config_backup_format import (
    USER_CONFIG_BACKUP_FORMAT,
    USER_CONFIG_BACKUP_FORMAT_VERSION,
    UserConfigBackupManifest,
    UserConfigSection,
    parse_user_config_manifest,
)


UserConfigRestoreStatus = Literal[
    "uploading",
    "uploaded",
    "validated",
    "restoring",
    "restored",
    "interrupted",
]

_SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ACTIVE_STATUSES = frozenset({"uploading", "uploaded", "validated", "restoring"})
_ALLOWED_COMPRESSIONS = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
_JSON_SUFFIX = ".json"
_SETTINGS_MEMBERS = frozenset(
    {
        "settings/webui.json",
        "settings/auth-source.json",
        "settings/providers.json",
        "settings/network.json",
        "settings/client-preferences.json",
    }
)
_FORBIDDEN_SECRET_KEYS = frozenset(
    {
        "access_token",
        "authorization",
        "cookie",
        "cookies",
        "oauth",
        "refresh_token",
        "token",
    }
)


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


class UserConfigBackupImportService:
    def __init__(
        self,
        planner: UserConfigBackupPlanner | None,
        root: Path | str,
        *,
        queue_storage: Any | None = None,
        clock: Callable[[], datetime] | None = None,
        disk_usage: Callable[[Path], object] = shutil.disk_usage,
        max_upload_bytes: int = MAX_USER_CONFIG_BACKUP_UPLOAD_BYTES,
        max_expanded_bytes: int = MAX_USER_CONFIG_BACKUP_EXPANDED_BYTES,
        max_member_bytes: int = MAX_USER_CONFIG_BACKUP_MEMBER_BYTES,
        max_manifest_bytes: int = MAX_USER_CONFIG_BACKUP_MANIFEST_BYTES,
        max_entries: int = MAX_USER_CONFIG_BACKUP_ENTRIES,
        max_compression_ratio: int = MAX_USER_CONFIG_BACKUP_COMPRESSION_RATIO,
        max_chunk_bytes: int = USER_CONFIG_BACKUP_UPLOAD_CHUNK_BYTES,
        min_free_bytes: int = USER_CONFIG_BACKUP_MIN_FREE_BYTES,
        free_ratio: float = USER_CONFIG_BACKUP_FREE_RATIO,
        ttl_seconds: int = 24 * 60 * 60,
        recover_on_init: bool = True,
    ) -> None:
        limits = (
            max_upload_bytes,
            max_expanded_bytes,
            max_member_bytes,
            max_manifest_bytes,
            max_entries,
            max_compression_ratio,
            max_chunk_bytes,
            ttl_seconds,
        )
        if any(value <= 0 for value in limits) or min_free_bytes < 0:
            raise ValueError("user_config_restore_runtime_config_invalid")
        if not 0 <= free_ratio < 1:
            raise ValueError("user_config_restore_capacity_config_invalid")
        self.planner = planner
        self.queue_storage = queue_storage
        self.root = Path(root)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._disk_usage = disk_usage
        self._max_upload_bytes = max_upload_bytes
        self._max_expanded_bytes = max_expanded_bytes
        self._max_member_bytes = max_member_bytes
        self._max_manifest_bytes = max_manifest_bytes
        self._max_entries = max_entries
        self._max_compression_ratio = max_compression_ratio
        self._max_chunk_bytes = max_chunk_bytes
        self._min_free_bytes = min_free_bytes
        self._free_ratio = free_ratio
        self._ttl_seconds = ttl_seconds
        self._lock = RLock()
        self._records: dict[str, _SessionRecord] = {}
        self._accepting = False
        self._recovered = False
        if recover_on_init:
            self.recover_startup()

    def recover_startup(self) -> None:
        with self._lock:
            if self._recovered:
                return
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            if self.root.is_symlink() or not self.root.is_dir():
                raise ValueError("user_config_restore_root_invalid")
            os.chmod(self.root, 0o700)
            self._recover_rollback_journals()
            for status_path in self.root.glob("*.json"):
                self._recover_status(status_path)
            self._recovered = True
            self._accepting = True
        self.cleanup_expired()

    def create(self, filename: str, size_bytes: int) -> UserConfigRestoreSession:
        self.cleanup_expired()
        safe_filename = _validated_filename(filename)
        if (
            isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or size_bytes <= 0
        ):
            raise ValueError("user_config_restore_size_invalid")
        if size_bytes > self._max_upload_bytes:
            raise ValueError("user_config_restore_upload_too_large")
        self._preflight_capacity(size_bytes)
        with self._lock:
            if not self._accepting:
                raise ValueError("user_config_restore_lifecycle_conflict")
            if any(record.session.status in _ACTIVE_STATUSES for record in self._records.values()):
                raise ValueError("user_config_restore_active")
            session_id = uuid4().hex
            now = _timestamp(self._now())
            session = UserConfigRestoreSession(
                session_id,
                safe_filename,
                size_bytes,
                0,
                "uploading",
                now,
                now,
            )
            upload_path = self._upload_path(session_id)
            descriptor = os.open(
                upload_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            os.fchmod(descriptor, 0o600)
            os.close(descriptor)
            record = _SessionRecord(session, hashlib.sha256())
            self._records[session_id] = record
            try:
                self._write_status(record)
            except Exception:
                self._records.pop(session_id, None)
                upload_path.unlink(missing_ok=True)
                raise
            return session

    def append_chunk(
        self,
        session_id: str,
        offset: int,
        data: bytes,
        sha256: str,
    ) -> UserConfigRestoreSession:
        normalized_id = _validated_session_id(session_id)
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("user_config_restore_offset_invalid")
        if not isinstance(data, bytes) or not data:
            raise ValueError("user_config_restore_chunk_invalid")
        if len(data) > self._max_chunk_bytes:
            raise ValueError("user_config_restore_chunk_too_large")
        if not isinstance(sha256, str) or _SHA256_RE.fullmatch(sha256) is None:
            raise ValueError("user_config_restore_chunk_hash_mismatch")
        actual = hashlib.sha256(data).hexdigest()
        if actual != sha256:
            raise ValueError("user_config_restore_chunk_hash_mismatch")
        with self._lock:
            record = self._require_record(normalized_id)
            current = record.session
            if current.status not in {"uploading", "uploaded"}:
                raise ValueError("user_config_restore_lifecycle_conflict")
            if offset != current.uploaded_bytes:
                if record.last_offset == offset:
                    if record.last_size == len(data) and record.last_sha256 == actual:
                        return current
                    raise ValueError("user_config_restore_chunk_retry_mismatch")
                raise ValueError("user_config_restore_offset_invalid")
            if offset + len(data) > current.size_bytes:
                raise ValueError("user_config_restore_upload_overflow")
            path = self._upload_path(normalized_id)
            with path.open("r+b") as destination:
                destination.seek(0, os.SEEK_END)
                if destination.tell() != offset:
                    raise ValueError("user_config_restore_upload_state_invalid")
                destination.write(data)
                destination.flush()
                os.fsync(destination.fileno())
            uploaded = offset + len(data)
            updated = replace(
                current,
                uploaded_bytes=uploaded,
                status="uploaded" if uploaded == current.size_bytes else "uploading",
                updated_at=_timestamp(self._now()),
            )
            record.digest.update(data)
            record.last_offset = offset
            record.last_size = len(data)
            record.last_sha256 = actual
            record.session = updated
            self._write_status(record)
            return updated

    def get_snapshot(self, session_id: str) -> UserConfigRestoreSnapshot | None:
        if not isinstance(session_id, str) or _SESSION_ID_RE.fullmatch(session_id) is None:
            return None
        self.cleanup_expired()
        with self._lock:
            record = self._records.get(session_id)
            if record is None:
                return None
            return UserConfigRestoreSnapshot(
                record.session,
                record.preview,
                record.result,
            )

    def cancel(self, session_id: str) -> bool:
        if not isinstance(session_id, str) or _SESSION_ID_RE.fullmatch(session_id) is None:
            return False
        with self._lock:
            if session_id not in self._records:
                return False
            self._delete_owned(session_id)
            self._records.pop(session_id, None)
            return True

    def validate(self, session_id: str) -> UserConfigRestorePreview:
        normalized_id = _validated_session_id(session_id)
        with self._lock:
            record = self._require_record(normalized_id)
            if record.preview is not None:
                return record.preview
            if record.session.status != "uploaded":
                raise ValueError("user_config_restore_upload_incomplete")
            upload_path = self._upload_path(normalized_id)
            archive_sha256 = _file_sha256(upload_path)
            if archive_sha256 != record.digest.hexdigest():
                raise ValueError("user_config_restore_upload_state_invalid")
        preview = self._validate_archive(normalized_id, upload_path, archive_sha256)
        with self._lock:
            record = self._require_record(normalized_id)
            record.preview = preview
            record.session = replace(
                record.session,
                status="validated",
                updated_at=_timestamp(self._now()),
                archive_sha256=archive_sha256,
            )
            self._write_status(record)
            atomic_write_text(
                self._plan_path(normalized_id),
                json.dumps(asdict(preview), indent=2, ensure_ascii=False),
                mode=0o600,
            )
            return preview

    def restore(
        self,
        session_id: str,
        *,
        sections,
        mode: Literal["incremental", "replace"],
        archive_sha256: str,
        preview_revision: str,
        confirm_replace: bool,
    ) -> UserConfigRestoreResult:
        normalized_id = _validated_session_id(session_id)
        selected = tuple(dict.fromkeys(sections))
        if (
            not selected
            or any(
                section not in {"chips", "gallery", "templates", "settings"}
                for section in selected
            )
        ):
            raise ValueError("user_config_restore_sections_invalid")
        if mode not in {"incremental", "replace"}:
            raise ValueError("user_config_restore_mode_invalid")
        if not isinstance(confirm_replace, bool):
            raise ValueError("user_config_restore_confirm_replace_invalid")
        if mode == "replace" and not confirm_replace:
            raise ValueError("user_config_restore_confirm_replace_required")
        if (
            mode == "replace"
            and any(section in {"gallery", "settings"} for section in selected)
            and self.queue_storage is not None
        ):
            with self.queue_storage.exclusive():
                queue_state = self.queue_storage.read_state()
                if queue_state.get("waiting") or queue_state.get("running"):
                    raise ValueError("user_config_restore_active_tasks")
        with self._lock:
            record = self._require_record(normalized_id)
            if record.result is not None:
                return record.result
            preview = record.preview
            if preview is None or record.session.status != "validated":
                raise ValueError("user_config_restore_not_validated")
            if not preview.restorable:
                raise ValueError("user_config_restore_version_unsupported")
            if archive_sha256 != preview.archive_sha256:
                raise ValueError("user_config_restore_archive_mismatch")
            if preview_revision != preview.preview_revision:
                raise ValueError("user_config_restore_preview_stale")
            available = {section.section for section in preview.sections}
            if any(section not in available for section in selected):
                raise ValueError("user_config_restore_sections_invalid")
            if mode == "replace" and any(
                group.archive_count == 0 and group.current_count > 0
                for section_preview in preview.sections
                if section_preview.section in selected
                for group in section_preview.groups
            ):
                raise ValueError("user_config_restore_empty_replace_blocked")

        if self.planner is None:
            raise ValueError("user_config_restore_planner_unavailable")
        for section_preview in preview.sections:
            if section_preview.section not in selected:
                continue
            current = self._current_fingerprint(
                section_preview.section,
                self._staged_client_preferences(normalized_id),
            )
            if current != section_preview.current_fingerprint:
                raise ValueError("user_config_restore_preview_stale")

        with ExitStack() as apply_stack:
            apply_stack.enter_context(self.planner._exclusive(selected))
            if (
                mode == "replace"
                and any(section in {"gallery", "settings"} for section in selected)
                and self.queue_storage is not None
            ):
                apply_stack.enter_context(self.queue_storage.exclusive())
                queue_state = self.queue_storage.read_state()
                if queue_state.get("waiting") or queue_state.get("running"):
                    raise ValueError("user_config_restore_active_tasks")
            backups = self._capture_selected_json_backups(selected)
            directory_backups = self._capture_selected_directory_backups(
                normalized_id,
                selected,
            )
            self._write_rollback_journal(
                normalized_id,
                backups,
                directory_backups,
            )
            stats: dict[UserConfigSection, SectionRestoreStats] = {}
            client_preferences: ClientPreferences | None = None
            restart_required = False
            with self._lock:
                record = self._require_record(normalized_id)
                record.session = replace(
                    record.session,
                    status="restoring",
                    updated_at=_timestamp(self._now()),
                )
                self._write_status(record)
            try:
                if "chips" in selected:
                    stats["chips"] = self._restore_chips(normalized_id, mode)
                if "gallery" in selected:
                    stats["gallery"] = self._restore_gallery(normalized_id, mode)
                if "templates" in selected:
                    stats["templates"] = self._restore_templates(normalized_id, mode)
                if "settings" in selected:
                    (
                        stats["settings"],
                        client_preferences,
                        restart_required,
                    ) = self._restore_settings(normalized_id, mode)
                result = UserConfigRestoreResult(
                    session_id=normalized_id,
                    status="restored",
                    sections=selected,
                    mode=mode,
                    section_stats=stats,
                    client_preferences=client_preferences,
                    restart_required=restart_required,
                )
                with self._lock:
                    record = self._require_record(normalized_id)
                    record.result = result
                    record.session = replace(
                        record.session,
                        status="restored",
                        updated_at=_timestamp(self._now()),
                    )
                    self._write_status(record)
            except Exception as exc:
                self._restore_json_backups(backups)
                self._restore_directory_backups(directory_backups)
                self._discard_rollback(normalized_id)
                with self._lock:
                    record = self._require_record(normalized_id)
                    record.result = None
                    record.session = replace(
                        record.session,
                        status="validated",
                        updated_at=_timestamp(self._now()),
                    )
                    self._write_status(record)
                if isinstance(exc, ValueError) and str(exc).startswith(
                    "user_config_restore_"
                ):
                    raise
                raise ValueError("user_config_restore_apply_failed") from None
            self._discard_directory_backups(directory_backups)
            self._discard_rollback(normalized_id)
        return result

    def _restore_chips(
        self,
        session_id: str,
        mode: Literal["incremental", "replace"],
    ) -> SectionRestoreStats:
        colors = self._staged_json(session_id, "chips/colors.json")
        snippets = self._staged_json(
            session_id,
            "chips/prompt-snippets.json",
        )
        if mode == "replace":
            current_count = (
                len(self.planner.color_settings.read()["favorites"])
                + len(self.planner.color_settings.read()["recent_colors"])
                + len(self.planner.prompt_snippet_settings.read()["snippets"])
            )
            self.planner.color_settings.write(colors)
            self.planner.prompt_snippet_settings.write(snippets)
            imported_count = (
                len(colors["favorites"])
                + len(colors["recent_colors"])
                + len(snippets["snippets"])
            )
            return SectionRestoreStats(
                added=max(0, imported_count - current_count),
                replaced=min(current_count, imported_count),
            )

        current_colors = self.planner.color_settings.read()
        favorites = [dict(item) for item in current_colors["favorites"]]
        seen_colors = {item["hex"] for item in favorites}
        added = 0
        skipped = 0
        for imported in colors["favorites"]:
            if imported["hex"] in seen_colors:
                skipped += 1
                continue
            seen_colors.add(imported["hex"])
            favorites.append(dict(imported))
            added += 1
        recent = list(current_colors["recent_colors"])
        for color in colors["recent_colors"]:
            if color in recent:
                skipped += 1
                continue
            recent.append(color)
            added += 1
        self.planner.color_settings.write(
            {
                "favorites": favorites,
                "recent_colors": recent[-current_colors["recent_limit"] :],
                "recent_limit": current_colors["recent_limit"],
            }
        )

        current_snippets = self.planner.prompt_snippet_settings.read()
        merged = [dict(item) for item in current_snippets["snippets"]]
        recovery_copies = 0
        for imported in snippets["snippets"]:
            tag = str(imported["tag"])
            identical = next(
                (
                    item
                    for item in merged
                    if item["tag"].casefold() == tag.casefold()
                    and item["content"] == imported["content"]
                ),
                None,
            )
            if identical is not None:
                skipped += 1
                continue
            candidate = dict(imported)
            ids = {str(item["id"]) for item in merged}
            tags = {str(item["tag"]).casefold() for item in merged}
            if candidate["id"] in ids or tag.casefold() in tags:
                recovery_copies += 1
                digest = hashlib.sha256(
                    json.dumps(candidate, sort_keys=True, ensure_ascii=False).encode()
                ).hexdigest()[:16]
                candidate["id"] = f"restored-{digest}"
                base_tag = tag[:14]
                index = 2
                new_tag = f"{base_tag}-restored"
                while new_tag.casefold() in tags:
                    new_tag = f"{base_tag}-restored-{index}"
                    index += 1
                candidate["tag"] = new_tag[:24]
                candidate["title"] = (
                    str(candidate["title"])[:68] + "（恢复副本）"
                )[:80]
            merged.append(candidate)
            added += 1
        self.planner.prompt_snippet_settings.write(
            {**current_snippets, "snippets": merged}
        )
        return SectionRestoreStats(
            added=added,
            skipped=skipped,
            recovery_copies=recovery_copies,
        )

    def _restore_gallery(self, session_id, mode):
        assert self.planner is not None
        imported_categories = self._staged_json(
            session_id,
            "gallery/categories.json",
        )
        staging = self._staging_path(session_id)
        imported_items: list[GallerySnapshotItem] = []
        for metadata_path in sorted(
            (staging / "gallery" / "items").glob("*/metadata.json")
        ):
            metadata = _json_value(metadata_path.read_bytes(), metadata_path.name)
            image_path = metadata_path.parent / str(metadata["filename"])
            imported_items.append(
                GallerySnapshotItem(
                    metadata=metadata,
                    image_path=image_path,
                    mime_type=str(metadata["mime_type"]),
                    size_bytes=int(metadata["size_bytes"]),
                    sha256=str(metadata["sha256"]),
                )
            )
        current = self.planner.gallery_storage.snapshot()
        if mode == "replace":
            self._remove_managed_gallery_paths()
            self.planner.gallery_storage.write_snapshot(
                GallerySnapshot(
                    categories=tuple(imported_categories),
                    items=tuple(imported_items),
                )
            )
            return SectionRestoreStats(
                added=max(0, len(imported_items) - len(current.items)),
                replaced=min(len(imported_items), len(current.items)),
            )

        categories = [dict(item) for item in current.categories]
        category_ids = {str(item["id"]) for item in categories}
        category_map: dict[str, str] = {}
        for imported in imported_categories:
            imported_id = str(imported["id"])
            if imported_id in category_ids:
                category_map[imported_id] = imported_id
                continue
            candidate = dict(imported)
            categories.append(candidate)
            category_ids.add(imported_id)
            category_map[imported_id] = imported_id

        merged = list(current.items)
        digests = {item.sha256 for item in merged}
        ids = {str(item.metadata["id"]) for item in merged}
        names = {str(item.metadata["name"]).casefold() for item in merged}
        added = skipped = recovery_copies = 0
        for imported in imported_items:
            if imported.sha256 in digests:
                skipped += 1
                continue
            metadata = dict(imported.metadata)
            metadata["category"] = category_map[str(metadata["category"])]
            if (
                str(metadata["id"]) in ids
                or str(metadata["name"]).casefold() in names
            ):
                recovery_copies += 1
                digest = imported.sha256[:16]
                metadata["id"] = f"restored-{digest}"
                base_name = str(metadata["name"])[:48]
                candidate_name = f"{base_name}（恢复副本）"
                index = 2
                while candidate_name.casefold() in names:
                    candidate_name = f"{base_name}（恢复副本 {index}）"
                    index += 1
                metadata["name"] = candidate_name[:64]
                metadata["name_key"] = metadata["name"].casefold()
            restored_item = GallerySnapshotItem(
                metadata=metadata,
                image_path=imported.image_path,
                mime_type=imported.mime_type,
                size_bytes=imported.size_bytes,
                sha256=imported.sha256,
            )
            merged.append(restored_item)
            ids.add(str(metadata["id"]))
            names.add(str(metadata["name"]).casefold())
            digests.add(imported.sha256)
            added += 1
        self.planner.gallery_storage.write_snapshot(
            GallerySnapshot(tuple(categories), tuple(merged))
        )
        return SectionRestoreStats(
            added=added,
            skipped=skipped,
            recovery_copies=recovery_copies,
        )

    def _restore_templates(self, session_id, mode):
        assert self.planner is not None
        payload = self._staged_json(
            session_id,
            "templates/prompt-templates.json",
        )
        staging = self._staging_path(session_id)
        restored_templates: list[dict[str, Any]] = []
        for raw in payload["templates"]:
            template = dict(raw)
            thumbnail_member = template.pop("thumbnail_member", None)
            if thumbnail_member:
                source = staging.joinpath(*PurePosixPath(thumbnail_member).parts)
                asset = self.planner.prompt_template_asset_storage.store(
                    source.read_bytes(),
                    filename=source.name,
                )
                template["thumbnail_url"] = (
                    f"/api/prompt-template-assets/{asset.asset_id}/image"
                )
            restored_templates.append(template)
        imported_payload = {**payload, "templates": restored_templates}
        current = self.planner.prompt_template_settings.read()
        if mode == "replace":
            for asset in self.planner.prompt_template_asset_storage.list_managed():
                asset.path.unlink(missing_ok=True)
            # Re-store thumbnails after clearing managed assets.
            for template, raw in zip(restored_templates, payload["templates"]):
                member = raw.get("thumbnail_member")
                if not member:
                    continue
                source = staging.joinpath(*PurePosixPath(member).parts)
                asset = self.planner.prompt_template_asset_storage.store(
                    source.read_bytes(),
                    filename=source.name,
                )
                template["thumbnail_url"] = (
                    f"/api/prompt-template-assets/{asset.asset_id}/image"
                )
            self.planner.prompt_template_settings.write(imported_payload)
            return SectionRestoreStats(
                added=max(0, len(restored_templates) - len(current["templates"])),
                replaced=min(len(restored_templates), len(current["templates"])),
            )

        categories = [dict(item) for item in current["categories"]]
        category_ids = {str(item["id"]) for item in categories}
        for category in payload["categories"]:
            if str(category["id"]) not in category_ids:
                categories.append(dict(category))
                category_ids.add(str(category["id"]))
        merged = [dict(item) for item in current["templates"]]
        identities = {
            (str(item["title"]).casefold(), str(item["content"]))
            for item in merged
        }
        ids = {str(item["id"]) for item in merged}
        titles = {str(item["title"]).casefold() for item in merged}
        added = skipped = copies = 0
        for imported in restored_templates:
            identity = (
                str(imported["title"]).casefold(),
                str(imported["content"]),
            )
            if identity in identities:
                skipped += 1
                continue
            candidate = dict(imported)
            if candidate["id"] in ids or identity[0] in titles:
                copies += 1
                digest = hashlib.sha256(
                    json.dumps(candidate, sort_keys=True, ensure_ascii=False).encode()
                ).hexdigest()[:16]
                candidate["id"] = f"restored-{digest}"
                candidate["title"] = (
                    str(candidate["title"])[:68] + "（恢复副本）"
                )[:80]
            merged.append(candidate)
            identities.add(identity)
            ids.add(str(candidate["id"]))
            titles.add(str(candidate["title"]).casefold())
            added += 1
        self.planner.prompt_template_settings.write(
            {"version": 1, "categories": categories, "templates": merged}
        )
        return SectionRestoreStats(
            added=added,
            skipped=skipped,
            recovery_copies=copies,
        )

    def _restore_settings(self, session_id, mode):
        assert self.planner is not None
        webui = self._staged_json(session_id, "settings/webui.json")
        auth = self._staged_json(session_id, "settings/auth-source.json")
        providers = self._staged_json(session_id, "settings/providers.json")
        network = self._staged_json(session_id, "settings/network.json")
        preferences = self._staged_client_preferences(session_id)
        before_paths = self.planner.webui_settings.read_paths()
        current_webui = self.planner.webui_settings._read_payload()
        current_network = self.planner.network_egress_settings._read_payload()
        current_auth = self.planner.auth_settings.snapshot()

        if mode == "replace":
            webui_candidate = {
                field: webui["values"][field]
                for field in webui["present_fields"]
                if field in webui["values"]
            }
            network_candidate = {
                field: network["values"][field]
                for field in network["present_fields"]
                if field in network["values"]
            }
            imported_providers = providers
        else:
            webui_candidate = dict(current_webui)
            for field in webui["present_fields"]:
                if field not in webui_candidate and field in webui["values"]:
                    webui_candidate[field] = webui["values"][field]
            network_candidate = dict(current_network)
            for field in network["present_fields"]:
                if field not in network_candidate and field in network["values"]:
                    network_candidate[field] = network["values"][field]
            imported_providers = self._merge_providers(providers)

        atomic_write_text(
            self.planner.webui_settings.path,
            json.dumps(webui_candidate, indent=2, ensure_ascii=False),
            mode=0o600,
        )
        if mode == "replace":
            if auth.get("present"):
                self.planner.auth_settings.write_source(str(auth["source"]))
            else:
                self.planner.auth_settings.path.unlink(missing_ok=True)
        elif not current_auth["present"] and auth.get("present"):
            self.planner.auth_settings.write_source(str(auth["source"]))
        atomic_write_text(
            self.planner.network_egress_settings.path,
            json.dumps(network_candidate, indent=2, ensure_ascii=False),
            mode=0o600,
        )
        if mode == "replace":
            imported_providers = self._preserve_current_provider_keys(
                imported_providers
            )
        self.planner.provider_settings.replace_snapshot(imported_providers)
        after_paths = self.planner.webui_settings.read_paths()
        return (
            SectionRestoreStats(replaced=5 if mode == "replace" else 0),
            preferences,
            before_paths != after_paths,
        )

    def _merge_providers(self, imported: dict[str, Any]) -> dict[str, Any]:
        assert self.planner is not None
        current = self.planner.provider_settings.backup_snapshot(
            include_api_keys=True
        )
        merged = json.loads(json.dumps(current))
        by_id = {provider["id"]: provider for provider in merged["providers"]}
        for provider in imported["providers"]:
            existing = by_id.get(provider["id"])
            if existing is None:
                merged["providers"].append(dict(provider))
                by_id[provider["id"]] = merged["providers"][-1]
                continue
            imported_key = str(provider.get("api_key") or "")
            if (
                not existing.get("api_key")
                and imported_key
                and provider_url_origin(existing["base_url"])
                == provider_url_origin(provider["base_url"])
            ):
                existing["api_key"] = imported_key
        return merged

    def _preserve_current_provider_keys(
        self,
        imported: dict[str, Any],
    ) -> dict[str, Any]:
        assert self.planner is not None
        candidate = json.loads(json.dumps(imported))
        current = self.planner.provider_settings.backup_snapshot(
            include_api_keys=True
        )
        imported_by_id = {
            provider["id"]: provider for provider in candidate["providers"]
        }
        for provider in current["providers"]:
            key = str(provider.get("api_key") or "")
            if not key:
                continue
            target = imported_by_id.get(provider["id"])
            if target is None:
                candidate["providers"].append(provider)
                imported_by_id[provider["id"]] = provider
            elif not target.get("api_key"):
                target["api_key"] = key
        # Repair defaults for retained keyed providers only if their models are absent.
        validated = validate_v2_payload(candidate)
        return validated

    def _remove_managed_gallery_paths(self) -> None:
        assert self.planner is not None
        root = self.planner.gallery_storage.root
        paths = sorted(
            self.planner.gallery_storage.managed_paths(),
            key=lambda path: len(path.parts),
            reverse=True,
        )
        parents: set[Path] = set()
        for path in paths:
            parents.add(path.parent)
            path.unlink(missing_ok=True)
        for parent in sorted(parents, key=lambda path: len(path.parts), reverse=True):
            if parent != root:
                try:
                    parent.rmdir()
                except OSError:
                    pass

    def _capture_selected_json_backups(self, sections) -> dict[Path, bytes | None]:
        assert self.planner is not None
        paths: list[Path] = []
        if "chips" in sections:
            paths.extend(
                (
                    self.planner.color_settings.path,
                    self.planner.prompt_snippet_settings.path,
                )
            )
        if "templates" in sections:
            paths.append(self.planner.prompt_template_settings.path)
        if "settings" in sections:
            paths.extend(
                (
                    self.planner.webui_settings.path,
                    self.planner.auth_settings.path,
                    self.planner.provider_settings.path,
                    self.planner.network_egress_settings.path,
                )
            )
        return {
            path: path.read_bytes() if path.exists() else None
            for path in paths
        }

    def _restore_json_backups(self, backups: dict[Path, bytes | None]) -> None:
        for path, data in backups.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write_bytes(path, data, mode=0o600)

    def _capture_selected_directory_backups(
        self,
        session_id: str,
        sections,
    ) -> dict[Path, Path]:
        assert self.planner is not None
        targets: list[Path] = []
        if "gallery" in sections:
            targets.append(self.planner.gallery_storage.root)
        if "templates" in sections:
            targets.append(self.planner.prompt_template_asset_storage.root)
        if not targets:
            return {}
        rollback_root = self.root / f"{session_id}.rollback"
        rollback_root.mkdir(mode=0o700, exist_ok=True)
        backups: dict[Path, Path] = {}
        for index, target in enumerate(targets):
            backup = rollback_root / str(index)
            if target.exists():
                shutil.copytree(target, backup, symlinks=True)
            backups[target] = backup
        return backups

    def _restore_directory_backups(self, backups: dict[Path, Path]) -> None:
        for target, backup in backups.items():
            if target.exists():
                shutil.rmtree(target)
            if backup.exists():
                shutil.copytree(backup, target, symlinks=True)
        self._discard_directory_backups(backups)

    def _discard_directory_backups(self, backups: dict[Path, Path]) -> None:
        roots = {backup.parent for backup in backups.values()}
        for root in roots:
            if root.exists():
                shutil.rmtree(root)

    def _discard_rollback(self, session_id: str) -> None:
        rollback_root = self.root / f"{session_id}.rollback"
        if rollback_root.exists() and rollback_root.parent == self.root:
            shutil.rmtree(rollback_root)

    def _write_rollback_journal(
        self,
        session_id: str,
        json_backups: dict[Path, bytes | None],
        directory_backups: dict[Path, Path],
    ) -> None:
        rollback_root = self.root / f"{session_id}.rollback"
        rollback_root.mkdir(mode=0o700, exist_ok=True)
        json_root = rollback_root / "json"
        json_root.mkdir(mode=0o700, exist_ok=True)
        json_entries: list[dict[str, Any]] = []
        for index, (target, data) in enumerate(json_backups.items()):
            backup = json_root / str(index)
            if data is not None:
                atomic_write_bytes(backup, data, mode=0o600)
            json_entries.append(
                {
                    "target": str(target),
                    "backup": str(backup.relative_to(rollback_root)),
                    "existed": data is not None,
                }
            )
        directory_entries = [
            {
                "target": str(target),
                "backup": str(backup.relative_to(rollback_root)),
                "existed": backup.exists(),
            }
            for target, backup in directory_backups.items()
        ]
        atomic_write_text(
            rollback_root / "journal.json",
            json.dumps(
                {
                    "version": 1,
                    "session_id": session_id,
                    "json": json_entries,
                    "directories": directory_entries,
                },
                ensure_ascii=False,
                indent=2,
            ),
            mode=0o600,
        )

    def _recover_rollback_journals(self) -> None:
        if self.planner is None:
            return
        allowed_json, allowed_directories = self._allowed_rollback_targets()
        for rollback_root in self.root.glob("*.rollback"):
            if rollback_root.is_symlink() or not rollback_root.is_dir():
                continue
            session_id = rollback_root.name.removesuffix(".rollback")
            if _SESSION_ID_RE.fullmatch(session_id) is None:
                continue
            journal_path = rollback_root / "journal.json"
            status_path = self._status_path(session_id)
            try:
                status_payload = (
                    json.loads(status_path.read_text(encoding="utf-8"))
                    if status_path.is_file()
                    else {}
                )
                if status_payload.get("status") == "restored":
                    shutil.rmtree(rollback_root)
                    continue
                journal = json.loads(journal_path.read_text(encoding="utf-8"))
                if journal.get("version") != 1 or journal.get("session_id") != session_id:
                    continue
                json_backups: dict[Path, bytes | None] = {}
                for entry in journal.get("json", []):
                    target = Path(entry["target"])
                    if target not in allowed_json:
                        raise ValueError("rollback_target_invalid")
                    backup = rollback_root / PurePosixPath(entry["backup"])
                    if not backup.is_relative_to(rollback_root) or backup.is_symlink():
                        raise ValueError("rollback_backup_invalid")
                    json_backups[target] = (
                        backup.read_bytes() if entry.get("existed") else None
                    )
                directory_backups: dict[Path, Path] = {}
                for entry in journal.get("directories", []):
                    target = Path(entry["target"])
                    if target not in allowed_directories:
                        raise ValueError("rollback_target_invalid")
                    backup = rollback_root / PurePosixPath(entry["backup"])
                    if not backup.is_relative_to(rollback_root) or backup.is_symlink():
                        raise ValueError("rollback_backup_invalid")
                    directory_backups[target] = backup
                self._restore_json_backups(json_backups)
                self._restore_directory_backups(directory_backups)
                self._discard_rollback(session_id)
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                continue

    def _allowed_rollback_targets(self) -> tuple[set[Path], set[Path]]:
        assert self.planner is not None
        return (
            {
                self.planner.color_settings.path,
                self.planner.prompt_snippet_settings.path,
                self.planner.prompt_template_settings.path,
                self.planner.webui_settings.path,
                self.planner.auth_settings.path,
                self.planner.provider_settings.path,
                self.planner.network_egress_settings.path,
            },
            {
                self.planner.gallery_storage.root,
                self.planner.prompt_template_asset_storage.root,
            },
        )

    def _staged_json(self, session_id: str, member_path: str) -> Any:
        path = self._staging_path(session_id).joinpath(
            *PurePosixPath(member_path).parts
        )
        return _json_value(path.read_bytes(), member_path)

    def _staged_client_preferences(
        self,
        session_id: str,
    ) -> ClientPreferences | None:
        path = self._staging_path(session_id) / "settings" / "client-preferences.json"
        if not path.is_file():
            return None
        payload = _json_value(path.read_bytes(), str(path.name))
        return ClientPreferences(
            payload["theme"],
            payload["notifications_in_app"],
            payload["notifications_system"],
        )

    def cleanup_expired(self) -> int:
        now = self._now()
        expired: list[str] = []
        with self._lock:
            for session_id, record in self._records.items():
                updated = _parse_timestamp(record.session.updated_at)
                if (now - updated).total_seconds() > self._ttl_seconds:
                    expired.append(session_id)
            for session_id in expired:
                self._delete_owned(session_id)
                self._records.pop(session_id, None)
        return len(expired)

    def close(self) -> None:
        with self._lock:
            self._accepting = False

    def _validate_archive(
        self,
        session_id: str,
        upload_path: Path,
        archive_sha256: str,
    ) -> UserConfigRestorePreview:
        staging = self._staging_path(session_id)
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(mode=0o700)
        try:
            with zipfile.ZipFile(upload_path) as archive:
                infos = archive.infolist()
                info_by_name = self._validate_central_directory(infos)
                manifest_info = info_by_name.get("manifest.json")
                if manifest_info is None:
                    raise ValueError("user_config_restore_manifest_missing")
                if manifest_info.file_size > self._max_manifest_bytes:
                    raise ValueError("user_config_restore_manifest_too_large")
                manifest_bytes = _read_zip_member(
                    archive,
                    manifest_info,
                    self._max_manifest_bytes,
                )
                raw_manifest = _json_object(manifest_bytes, "manifest")
                if raw_manifest.get("format") != USER_CONFIG_BACKUP_FORMAT:
                    raise ValueError("user_config_restore_format_unsupported")
                format_version = raw_manifest.get("format_version")
                if isinstance(format_version, bool) or not isinstance(format_version, int):
                    raise ValueError("user_config_restore_manifest_invalid")
                if format_version > USER_CONFIG_BACKUP_FORMAT_VERSION:
                    return UserConfigRestorePreview(
                        session_id=session_id,
                        archive_sha256=archive_sha256,
                        preview_revision=hashlib.sha256(
                            (archive_sha256 + f":{format_version}").encode()
                        ).hexdigest(),
                        format_version=format_version,
                        restorable=False,
                        contains_secrets=bool(raw_manifest.get("contains_secrets")),
                        sections=(),
                        path_fields={},
                        keyed_provider_retention_count=0,
                        gallery_history_reference_impact=0,
                        warnings=("user_config_restore_version_unsupported",),
                    )
                manifest = parse_user_config_manifest(manifest_bytes)
                declared = {member.path: member for member in manifest.members}
                actual = set(info_by_name) - {"manifest.json"}
                if actual - set(declared):
                    raise ValueError("user_config_restore_undeclared_member")
                if set(declared) - actual:
                    raise ValueError("user_config_restore_member_missing")
                for member in manifest.members:
                    info = info_by_name[member.path]
                    if info.file_size != member.size_bytes:
                        raise ValueError("user_config_restore_member_size_mismatch")
                    self._extract_member(
                        archive,
                        info,
                        staging,
                        member.size_bytes,
                        member.sha256,
                    )
            semantic = self._validate_semantics(manifest, staging)
            return self._build_preview(
                session_id,
                archive_sha256,
                manifest,
                semantic,
            )
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise

    def _validate_central_directory(
        self,
        infos: list[zipfile.ZipInfo],
    ) -> dict[str, zipfile.ZipInfo]:
        if len(infos) > self._max_entries:
            raise ValueError("user_config_restore_entries_too_many")
        total_expanded = 0
        result: dict[str, zipfile.ZipInfo] = {}
        for info in infos:
            name = _validated_zip_member_name(info.filename)
            if name in result:
                raise ValueError("user_config_restore_duplicate_entry")
            if info.is_dir():
                raise ValueError("user_config_restore_non_regular_entry")
            mode = (info.external_attr >> 16) & 0xFFFF
            file_type = stat.S_IFMT(mode)
            if file_type not in {0, stat.S_IFREG}:
                raise ValueError("user_config_restore_non_regular_entry")
            if info.flag_bits & 0x1:
                raise ValueError("user_config_restore_encrypted_entry")
            if info.compress_type not in _ALLOWED_COMPRESSIONS:
                raise ValueError("user_config_restore_compression_unsupported")
            if info.file_size > self._max_member_bytes:
                raise ValueError("user_config_restore_member_too_large")
            total_expanded += info.file_size
            if total_expanded > self._max_expanded_bytes:
                raise ValueError("user_config_restore_expanded_too_large")
            if (
                info.file_size > 0
                and info.file_size / max(1, info.compress_size)
                > self._max_compression_ratio
            ):
                raise ValueError("user_config_restore_compression_ratio")
            result[name] = info
        return result

    def _extract_member(
        self,
        archive: zipfile.ZipFile,
        info: zipfile.ZipInfo,
        staging: Path,
        expected_size: int,
        expected_sha256: str,
    ) -> None:
        target = staging.joinpath(*PurePosixPath(info.filename).parts)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            target.parent.resolve(strict=True).relative_to(staging.resolve(strict=True))
        except (OSError, ValueError) as exc:
            raise ValueError("user_config_restore_member_path_invalid") from exc
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(target, flags, 0o600)
        digest = hashlib.sha256()
        written = 0
        try:
            with os.fdopen(descriptor, "wb") as destination, archive.open(info) as source:
                descriptor = -1
                while chunk := source.read(min(1024 * 1024, self._max_member_bytes + 1)):
                    written += len(chunk)
                    if written > expected_size or written > self._max_member_bytes:
                        raise ValueError("user_config_restore_member_size_mismatch")
                    destination.write(chunk)
                    digest.update(chunk)
                destination.flush()
                os.fsync(destination.fileno())
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        if written != expected_size:
            raise ValueError("user_config_restore_member_size_mismatch")
        if digest.hexdigest() != expected_sha256:
            raise ValueError("user_config_restore_member_hash_mismatch")
        os.chmod(target, 0o600)

    def _validate_semantics(
        self,
        manifest: UserConfigBackupManifest,
        staging: Path,
    ) -> dict[str, Any]:
        json_payloads: dict[str, Any] = {}
        for member in manifest.members:
            path = staging.joinpath(*PurePosixPath(member.path).parts)
            if member.path.endswith(_JSON_SUFFIX):
                payload = _json_value(path.read_bytes(), member.path)
                _reject_forbidden_secrets(
                    payload,
                    allow_provider_api_keys=(
                        manifest.contains_secrets
                        and member.path == "settings/providers.json"
                    ),
                )
                if (
                    not manifest.contains_secrets
                    and _contains_key(payload, "api_key")
                ):
                    raise ValueError("user_config_restore_secret_declaration_mismatch")
                json_payloads[member.path] = payload

        self._validate_chips(json_payloads)
        self._validate_gallery(manifest, staging, json_payloads)
        self._validate_templates(manifest, staging, json_payloads)
        client_preferences = self._validate_settings(manifest, json_payloads)
        return {
            "json_payloads": json_payloads,
            "client_preferences": client_preferences,
        }

    def _validate_chips(self, payloads: dict[str, Any]) -> None:
        colors = payloads.get("chips/colors.json")
        snippets = payloads.get("chips/prompt-snippets.json")
        if colors is not None:
            if not isinstance(colors, dict):
                raise ValueError("user_config_restore_json_shape_invalid")
            _normalize_color_palette_payload(colors, default_when_missing=False)
        if snippets is not None:
            if not isinstance(snippets, dict):
                raise ValueError("user_config_restore_json_shape_invalid")
            _normalize_prompt_snippets_payload(snippets, default_when_missing=False)

    def _validate_gallery(
        self,
        manifest: UserConfigBackupManifest,
        staging: Path,
        payloads: dict[str, Any],
    ) -> None:
        categories = payloads.get("gallery/categories.json")
        if categories is not None and not isinstance(categories, list):
            raise ValueError("user_config_restore_json_shape_invalid")
        metadata_paths = {
            member.path: payloads[member.path]
            for member in manifest.members
            if member.path.startswith("gallery/items/")
            and member.path.endswith("/metadata.json")
        }
        for metadata_path, metadata in metadata_paths.items():
            if not isinstance(metadata, dict):
                raise ValueError("user_config_restore_json_shape_invalid")
            parts = PurePosixPath(metadata_path).parts
            item_id = parts[2]
            if str(metadata.get("id") or "") != item_id:
                raise ValueError("user_config_restore_gallery_metadata_invalid")
            filename = str(metadata.get("filename") or "")
            image_member = f"gallery/items/{item_id}/{filename}"
            entry = next(
                (member for member in manifest.members if member.path == image_member),
                None,
            )
            if entry is None:
                raise ValueError("user_config_restore_gallery_asset_missing")
            image_path = staging.joinpath(*PurePosixPath(image_member).parts)
            try:
                validated = validate_raster_image(
                    image_path.read_bytes(),
                    filename=filename,
                )
            except (InvalidRasterImage, OSError) as exc:
                raise ValueError("user_config_restore_raster_invalid") from exc
            if (
                metadata.get("sha256") != validated.sha256
                or metadata.get("size_bytes") != entry.size_bytes
                or metadata.get("mime_type") != validated.mime_type
            ):
                raise ValueError("user_config_restore_gallery_metadata_invalid")

    def _validate_templates(
        self,
        manifest: UserConfigBackupManifest,
        staging: Path,
        payloads: dict[str, Any],
    ) -> None:
        template_payload = payloads.get("templates/prompt-templates.json")
        if template_payload is None:
            return
        if not isinstance(template_payload, dict) or not isinstance(
            template_payload.get("templates"),
            list,
        ):
            raise ValueError("user_config_restore_json_shape_invalid")
        declared = {member.path: member for member in manifest.members}
        for template in template_payload["templates"]:
            if not isinstance(template, dict):
                raise ValueError("user_config_restore_json_shape_invalid")
            thumbnail_member = template.get("thumbnail_member")
            thumbnail_url = template.get("thumbnail_url")
            if thumbnail_member and thumbnail_url:
                raise ValueError("user_config_restore_template_thumbnail_ambiguous")
            if thumbnail_member:
                if not isinstance(thumbnail_member, str) or thumbnail_member not in declared:
                    raise ValueError("user_config_restore_template_thumbnail_missing")
        for member in manifest.members:
            if not member.path.startswith("templates/thumbnails/"):
                continue
            path = staging.joinpath(*PurePosixPath(member.path).parts)
            try:
                validated = validate_raster_image(path.read_bytes(), filename=path.name)
            except (InvalidRasterImage, OSError) as exc:
                raise ValueError("user_config_restore_raster_invalid") from exc
            if PurePosixPath(member.path).stem != validated.sha256:
                raise ValueError("user_config_restore_template_thumbnail_digest_invalid")

    def _validate_settings(
        self,
        manifest: UserConfigBackupManifest,
        payloads: dict[str, Any],
    ) -> ClientPreferences | None:
        if "settings" not in manifest.sections:
            return None
        if set(path for path in payloads if path.startswith("settings/")) != _SETTINGS_MEMBERS:
            raise ValueError("user_config_restore_settings_members_invalid")
        webui = payloads["settings/webui.json"]
        auth = payloads["settings/auth-source.json"]
        providers = payloads["settings/providers.json"]
        network = payloads["settings/network.json"]
        preferences = payloads["settings/client-preferences.json"]
        if (
            not isinstance(webui, dict)
            or set(webui) != {"values", "present_fields"}
            or not isinstance(webui["values"], dict)
            or not isinstance(webui["present_fields"], list)
            or not isinstance(auth, dict)
            or set(auth) != {"source", "present"}
            or not isinstance(auth["present"], bool)
            or not isinstance(network, dict)
            or set(network) != {"values", "present_fields"}
            or not isinstance(preferences, dict)
        ):
            raise ValueError("user_config_restore_json_shape_invalid")
        validated_providers = validate_v2_payload(providers)
        if not manifest.contains_secrets and any(
            provider.get("api_key")
            for provider in validated_providers["providers"]
        ):
            raise ValueError("user_config_restore_secret_declaration_mismatch")
        if set(preferences) != {
            "theme",
            "notifications_in_app",
            "notifications_system",
        }:
            raise ValueError("user_config_restore_json_shape_invalid")
        try:
            return ClientPreferences(
                preferences["theme"],
                preferences["notifications_in_app"],
                preferences["notifications_system"],
            )
        except (KeyError, ValueError) as exc:
            raise ValueError("user_config_restore_json_shape_invalid") from exc

    def _build_preview(
        self,
        session_id: str,
        archive_sha256: str,
        manifest: UserConfigBackupManifest,
        semantic: dict[str, Any],
    ) -> UserConfigRestorePreview:
        payloads = semantic["json_payloads"]
        section_previews: list[UserConfigRestoreSectionPreview] = []
        current_fingerprints: dict[str, str] = {}
        for section in manifest.sections:
            members = [member for member in manifest.members if member.section == section]
            archive_count = _section_archive_count(section, payloads, members)
            archive_groups = _section_group_counts(section, payloads, members)
            (
                current_count,
                current_groups,
                current_fingerprint,
            ) = self._current_section_state(
                section,
                semantic.get("client_preferences"),
            )
            current_fingerprints[section] = current_fingerprint
            section_previews.append(
                UserConfigRestoreSectionPreview(
                    section=section,
                    archive_count=archive_count,
                    identical_count=0,
                    conflicts=0,
                    missing_assets=0,
                    replace_existing_count=current_count,
                    estimated_write_bytes=sum(member.size_bytes for member in members),
                    warnings=(),
                    current_fingerprint=current_fingerprint,
                    groups=tuple(
                        UserConfigRestoreGroupPreview(
                            group=group,
                            archive_count=count,
                            current_count=current_groups.get(group, 0),
                        )
                        for group, count in archive_groups.items()
                    ),
                )
            )
        path_fields = _path_field_classifications(payloads.get("settings/webui.json"))
        keyed_retention = self._keyed_provider_count()
        revision_payload = json.dumps(
            {
                "archive_sha256": archive_sha256,
                "members": [asdict(member) for member in manifest.members],
                "current": current_fingerprints,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return UserConfigRestorePreview(
            session_id=session_id,
            archive_sha256=archive_sha256,
            preview_revision=hashlib.sha256(revision_payload).hexdigest(),
            format_version=manifest.format_version,
            restorable=True,
            contains_secrets=manifest.contains_secrets,
            sections=tuple(section_previews),
            path_fields=path_fields,
            keyed_provider_retention_count=keyed_retention,
            gallery_history_reference_impact=0,
            warnings=(),
        )

    def _current_fingerprint(
        self,
        section: UserConfigSection,
        preferences: ClientPreferences | None,
    ) -> str:
        return self._current_section_state(section, preferences)[2]

    def _current_section_state(
        self,
        section: UserConfigSection,
        preferences: ClientPreferences | None,
    ) -> tuple[int, dict[str, int], str]:
        if self.planner is None:
            groups = _section_group_counts(section, {}, ())
            return (
                0,
                groups,
                hashlib.sha256(f"empty:{section}".encode()).hexdigest(),
            )
        try:
            plan = self.planner.plan(
                (section,),
                include_api_keys=False,
                client_preferences=(preferences if section == "settings" else None),
            )
            members = [member.entry for member in plan.members]
            payloads = {
                member.entry.path: _json_value(member.data, member.entry.path)
                for member in plan.members
                if member.data is not None and member.entry.path.endswith(".json")
            }
            fingerprint_payload = json.dumps(
                [(member.entry.path, member.entry.sha256) for member in plan.members],
                separators=(",", ":"),
            ).encode()
        except Exception as exc:
            raise ValueError("user_config_restore_preview_unavailable") from exc
        return (
            _section_archive_count(section, payloads, members),
            _section_group_counts(section, payloads, members),
            hashlib.sha256(fingerprint_payload).hexdigest(),
        )

    def _keyed_provider_count(self) -> int:
        if self.planner is None:
            return 0
        try:
            providers = self.planner.provider_settings.backup_snapshot(
                include_api_keys=True
            )["providers"]
        except Exception:
            return 0
        return sum(
            1
            for provider in providers
            if isinstance(provider, dict) and provider.get("api_key")
        )

    def _preflight_capacity(self, size_bytes: int) -> None:
        try:
            free = int(getattr(self._disk_usage(self.root.parent), "free"))
        except (OSError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError("user_config_restore_capacity_unavailable") from exc
        reserve = max(self._min_free_bytes, math.ceil(size_bytes * self._free_ratio))
        if free < size_bytes + reserve:
            raise ValueError("user_config_restore_insufficient_space")

    def _recover_status(self, path: Path) -> None:
        session_id = path.stem
        if _SESSION_ID_RE.fullmatch(session_id) is None or path.is_symlink():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            status = str(payload["status"])
            session = UserConfigRestoreSession(
                session_id=session_id,
                filename=_validated_filename(payload["filename"]),
                size_bytes=int(payload["size_bytes"]),
                uploaded_bytes=int(payload["uploaded_bytes"]),
                status=(
                    "interrupted"
                    if status in _ACTIVE_STATUSES
                    else status
                ),
                created_at=str(payload["created_at"]),
                updated_at=(
                    _timestamp(self._now())
                    if status in _ACTIVE_STATUSES
                    else str(payload["updated_at"])
                ),
                archive_sha256=payload.get("archive_sha256"),
                error_code=(
                    "user_config_restore_interrupted"
                    if status in _ACTIVE_STATUSES
                    else payload.get("error_code")
                ),
            )
            _parse_timestamp(session.created_at)
            _parse_timestamp(session.updated_at)
        except Exception:
            return
        result = None
        if status == "restored" and isinstance(payload.get("result"), dict):
            try:
                raw_result = payload["result"]
                raw_preferences = raw_result.get("client_preferences")
                preferences = (
                    ClientPreferences(
                        raw_preferences["theme"],
                        raw_preferences["notifications_in_app"],
                        raw_preferences["notifications_system"],
                    )
                    if isinstance(raw_preferences, dict)
                    else None
                )
                section_stats = {
                    section: SectionRestoreStats(**stats)
                    for section, stats in raw_result["section_stats"].items()
                }
                result = UserConfigRestoreResult(
                    session_id=session_id,
                    status="restored",
                    sections=tuple(raw_result["sections"]),
                    mode=raw_result["mode"],
                    section_stats=section_stats,
                    client_preferences=preferences,
                    restart_required=raw_result["restart_required"],
                )
            except (KeyError, TypeError, ValueError):
                result = None
        record = _SessionRecord(session, hashlib.sha256(), result=result)
        self._records[session_id] = record
        if status in _ACTIVE_STATUSES:
            self._write_status(record)

    def _write_status(self, record: _SessionRecord) -> None:
        payload = asdict(record.session)
        if record.result is not None:
            payload["result"] = asdict(record.result)
        atomic_write_text(
            self._status_path(record.session.session_id),
            json.dumps(payload, indent=2, ensure_ascii=False),
            mode=0o600,
        )

    def _require_record(self, session_id: str) -> _SessionRecord:
        record = self._records.get(session_id)
        if record is None:
            raise ValueError("user_config_restore_not_found")
        return record

    def _delete_owned(self, session_id: str) -> None:
        for path in (
            self._upload_path(session_id),
            self._status_path(session_id),
            self._plan_path(session_id),
        ):
            path.unlink(missing_ok=True)
        staging = self._staging_path(session_id)
        if staging.exists() and staging.parent == self.root:
            shutil.rmtree(staging)
        rollback = self.root / f"{session_id}.rollback"
        if rollback.exists() and rollback.parent == self.root:
            shutil.rmtree(rollback)

    def _upload_path(self, session_id: str) -> Path:
        return self.root / f"{session_id}.upload"

    def _status_path(self, session_id: str) -> Path:
        return self.root / f"{session_id}.json"

    def _plan_path(self, session_id: str) -> Path:
        return self.root / f"{session_id}.plan.json"

    def _staging_path(self, session_id: str) -> Path:
        return self.root / f"{session_id}.staging"

    def _now(self) -> datetime:
        now = self._clock()
        return now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)


def _validated_filename(filename: Any) -> str:
    clean = str(filename or "").strip()
    if (
        not clean
        or len(clean.encode("utf-8")) > 255
        or Path(clean).name != clean
        or not clean.lower().endswith(".zip")
        or any(ord(character) < 32 for character in clean)
    ):
        raise ValueError("user_config_restore_filename_invalid")
    return clean


def _validated_session_id(session_id: Any) -> str:
    clean = str(session_id or "")
    if _SESSION_ID_RE.fullmatch(clean) is None:
        raise ValueError("user_config_restore_not_found")
    return clean


def _validated_zip_member_name(name: Any) -> str:
    raw = str(name or "")
    normalized = unicodedata.normalize("NFKC", raw)
    candidate = PurePosixPath(raw)
    windows = PureWindowsPath(raw)
    if (
        not raw
        or normalized != raw
        or "\\" in raw
        or candidate.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or any(ord(character) < 32 or ord(character) == 127 for character in raw)
    ):
        raise ValueError("user_config_restore_member_path_invalid")
    return candidate.as_posix()


def _read_zip_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    maximum: int,
) -> bytes:
    with archive.open(info) as source:
        data = source.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError("user_config_restore_manifest_too_large")
    return data


def _json_value(payload: bytes, label: str) -> Any:
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("user_config_restore_json_invalid") from exc


def _json_object(payload: bytes, label: str) -> dict[str, Any]:
    value = _json_value(payload, label)
    if not isinstance(value, dict):
        raise ValueError("user_config_restore_json_shape_invalid")
    return value


def _contains_key(value: Any, target: str) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).casefold() == target
            or _contains_key(nested, target)
            for key, nested in value.items()
        )
    if isinstance(value, list):
        return any(_contains_key(item, target) for item in value)
    return False


def _reject_forbidden_secrets(
    value: Any,
    *,
    allow_provider_api_keys: bool,
    inside_provider: bool = False,
) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).casefold()
            if normalized in _FORBIDDEN_SECRET_KEYS:
                raise ValueError("user_config_restore_forbidden_secret_field")
            if normalized == "api_key" and not (
                allow_provider_api_keys and inside_provider
            ):
                raise ValueError("user_config_restore_secret_declaration_mismatch")
            child_inside_provider = inside_provider
            if normalized == "providers" and isinstance(nested, list):
                for provider in nested:
                    _reject_forbidden_secrets(
                        provider,
                        allow_provider_api_keys=allow_provider_api_keys,
                        inside_provider=True,
                    )
                continue
            _reject_forbidden_secrets(
                nested,
                allow_provider_api_keys=allow_provider_api_keys,
                inside_provider=child_inside_provider,
            )
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden_secrets(
                item,
                allow_provider_api_keys=allow_provider_api_keys,
                inside_provider=inside_provider,
            )


def _section_archive_count(section, payloads, members) -> int:
    if section == "chips":
        colors = payloads.get("chips/colors.json", {})
        snippets = payloads.get("chips/prompt-snippets.json", {})
        return (
            len(colors.get("favorites", []))
            + len(colors.get("recent_colors", []))
            + len(snippets.get("snippets", []))
        )
    if section == "gallery":
        return sum(
            1
            for member in members
            if member.path.endswith("/metadata.json")
        )
    if section == "templates":
        templates = payloads.get("templates/prompt-templates.json", {})
        return len(templates.get("templates", [])) + sum(
            1 for member in members if member.path.startswith("templates/thumbnails/")
        )
    return len(members)


def _section_group_counts(section, payloads, members) -> dict[str, int]:
    if section == "chips":
        colors = payloads.get("chips/colors.json", {})
        snippets = payloads.get("chips/prompt-snippets.json", {})
        return {
            "colors": len(colors.get("favorites", []))
            + len(colors.get("recent_colors", [])),
            "prompt_snippets": len(snippets.get("snippets", [])),
        }
    if section == "gallery":
        return {
            "gallery_items": sum(
                1
                for member in members
                if member.path.endswith("/metadata.json")
            )
        }
    if section == "templates":
        templates = payloads.get("templates/prompt-templates.json", {})
        return {"prompt_templates": len(templates.get("templates", []))}
    return {"settings": len(members)}


def _path_field_classifications(webui: Any) -> dict[str, str]:
    if not isinstance(webui, dict) or not isinstance(webui.get("values"), dict):
        return {}
    result: dict[str, str] = {}
    for field in ("input_root", "output_root", "gallery_root", "source_data_root"):
        if field not in webui["values"]:
            continue
        value = webui["values"][field]
        result[field] = (
            "valid"
            if isinstance(value, str) and bool(value.strip()) and "\x00" not in value
            else "invalid_value"
        )
    return result


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


__all__ = (
    "UserConfigBackupImportService",
    "UserConfigRestorePreview",
    "UserConfigRestoreSectionPreview",
    "UserConfigRestoreSession",
    "UserConfigRestoreSnapshot",
)
