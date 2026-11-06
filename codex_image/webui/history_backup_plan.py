from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Iterator, Literal

from .gallery_storage import GalleryStorage
from .history_backup_format import (
    BackupFileEntry,
    BackupFileRole,
    BackupTaskEntry,
    canonical_task_fingerprint,
    safe_backup_member_path,
)
from .history_query import HistoryFilter
from .reference_assets import ReferenceAssetStorage
from .reference_files import ReferenceFileStorage
from .storage import TaskStorage
from .task_index import TERMINAL_TASK_STATUSES


_MAX_TASK_JSON_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class PlannedBackupFile:
    entry: BackupFileEntry
    source_path: Path | None
    inline_bytes: bytes | None


@dataclass(frozen=True)
class PlannedBackupTask:
    entry: BackupTaskEntry
    files: tuple[PlannedBackupFile, ...]
    missing_input_files: int = 0


@dataclass(frozen=True)
class BackupScopeSummary:
    selected_count: int
    eligible_count: int
    excluded_nonterminal: int


@dataclass(frozen=True)
class BackupScopePlan(BackupScopeSummary):
    plan_path: Path


@dataclass(frozen=True)
class BackupExportScope:
    kind: Literal["selected", "filtered", "all"]
    task_ids: tuple[str, ...] = ()
    filters: HistoryFilter | None = None

    def __post_init__(self) -> None:
        clean_ids = tuple(
            dict.fromkeys(
                task_id
                for value in self.task_ids
                if (task_id := str(value or "").strip())
            )
        )
        object.__setattr__(self, "task_ids", clean_ids)
        valid = (
            (self.kind == "selected" and bool(clean_ids) and self.filters is None)
            or (self.kind == "filtered" and not clean_ids and isinstance(self.filters, HistoryFilter))
            or (self.kind == "all" and not clean_ids and self.filters is None)
        )
        if not valid:
            raise ValueError("backup_scope_invalid")

    @classmethod
    def selected(cls, ids: object) -> BackupExportScope:
        if not isinstance(ids, (list, tuple)):
            raise ValueError("backup_scope_invalid")
        return cls(kind="selected", task_ids=tuple(ids))

    @classmethod
    def filtered(cls, filters: HistoryFilter) -> BackupExportScope:
        return cls(kind="filtered", filters=filters)

    @classmethod
    def all(cls) -> BackupExportScope:
        return cls(kind="all")


class TaskBackupPlanner:
    def __init__(
        self,
        task_storage: TaskStorage,
        gallery_storage: GalleryStorage,
        reference_asset_storage: ReferenceAssetStorage,
        reference_file_storage: ReferenceFileStorage,
    ) -> None:
        self.task_storage = task_storage
        self.gallery_storage = gallery_storage
        self.reference_asset_storage = reference_asset_storage
        self.reference_file_storage = reference_file_storage

    def plan_task(self, task_id: str) -> PlannedBackupTask:
        try:
            metadata_path = self.task_storage.metadata_path(task_id)
            metadata, metadata_raw = _read_json_object_once(
                metadata_path,
                missing_code="history_task_not_found",
                invalid_code="task_backup_metadata_invalid",
            )
        except FileNotFoundError as exc:
            raise ValueError("history_task_not_found") from exc
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            if isinstance(exc, ValueError) and str(exc) in {
                "history_task_not_found",
                "task_backup_metadata_invalid",
            }:
                raise
            raise ValueError("task_backup_metadata_invalid") from exc
        if not isinstance(metadata, dict) or str(metadata.get("task_id") or task_id) != task_id:
            raise ValueError("task_backup_metadata_invalid")
        if not str(metadata.get("created_at") or "").strip():
            raise ValueError("task_backup_metadata_invalid")
        if str(metadata.get("status") or "") not in TERMINAL_TASK_STATUSES:
            raise ValueError("task_backup_not_terminal")
        if _contains_sensitive_request_key(metadata):
            raise ValueError("metadata_contains_sensitive_fields")
        try:
            request_path = self.task_storage.request_path(task_id)
            request, request_raw = _read_json_object_once(
                request_path,
                missing_code="backup_source_missing",
                invalid_code="task_backup_request_invalid",
            )
        except FileNotFoundError as exc:
            raise ValueError("backup_source_missing") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("task_backup_request_invalid") from exc
        if not isinstance(request, dict):
            raise ValueError("task_backup_request_invalid")
        if _contains_sensitive_request_key(request):
            raise ValueError("request_contains_sensitive_fields")

        organization_state = self.task_storage.history_organizer.organizations_for_tasks([task_id])[task_id]
        organization = {
            "favorite": organization_state.favorite,
            "tags": [
                {"name": tag.name}
                for tag in organization_state.tags
            ],
        }
        organization_bytes = _canonical_json_bytes(organization)

        files: list[PlannedBackupFile] = [
            self._snapshot_path_file(task_id, "metadata", metadata_path, metadata_raw),
            self._snapshot_path_file(task_id, "request", request_path, request_raw),
            self._inline_file(task_id, "organization", organization_bytes),
        ]
        for source_index, filename in _output_sources(metadata):
            try:
                path = self.task_storage.output_path(filename)
            except ValueError as exc:
                raise ValueError("backup_source_path_invalid") from exc
            if _unsafe_relative_path(filename):
                raise ValueError("backup_source_path_invalid")
            _require_within_root(path, self.task_storage.output_root)
            if not path.name.startswith(f"{task_id}-"):
                raise ValueError("task_output_not_owned")
            files.append(self._path_file(task_id, "output", path, source_index))
        missing_input_files = 0
        for source_index, filename in enumerate(_string_list(metadata.get("input_files")), start=1):
            path = self.task_storage.task_owned_input_path(task_id, filename)
            planned_file = self._optional_input_file(task_id, "input", path, source_index)
            if planned_file is None:
                missing_input_files += 1
            else:
                files.append(planned_file)
        mask_file = str(metadata.get("mask_file") or "").strip()
        if mask_file:
            path = self.task_storage.task_owned_input_path(task_id, mask_file)
            planned_file = self._optional_input_file(task_id, "mask", path, 1)
            if planned_file is None:
                missing_input_files += 1
            else:
                files.append(planned_file)
        markup_file = str(metadata.get("markup_file") or "").strip()
        if markup_file:
            path = self.task_storage.task_owned_input_path(task_id, markup_file)
            planned_file = self._optional_input_file(task_id, "markup", path, 1)
            if planned_file is None:
                missing_input_files += 1
            else:
                files.append(planned_file)
        for source_index, record in enumerate(_record_list(metadata.get("reference_assets")), start=1):
            try:
                path = self.reference_asset_storage.image_path(_record_id(record))
            except FileNotFoundError:
                missing_input_files += 1
                continue
            except OSError as exc:
                raise ValueError("backup_source_unreadable") from exc
            _require_within_root(path, self.reference_asset_storage.root)
            planned_file = self._optional_input_file(
                task_id, "reference_asset", path, source_index
            )
            if planned_file is None:
                missing_input_files += 1
            else:
                files.append(planned_file)
        for source_index, record in enumerate(_record_list(metadata.get("gallery_refs")), start=1):
            try:
                path = self.gallery_storage.image_path(_record_id(record))
            except FileNotFoundError:
                missing_input_files += 1
                continue
            except OSError as exc:
                raise ValueError("backup_source_unreadable") from exc
            _require_within_root(path, self.gallery_storage.root)
            planned_file = self._optional_input_file(
                task_id, "gallery_reference", path, source_index
            )
            if planned_file is None:
                missing_input_files += 1
            else:
                files.append(planned_file)
        for source_index, record in enumerate(_record_list(metadata.get("reference_files")), start=1):
            expected_size = record.get("size_bytes")
            if isinstance(expected_size, bool) or not isinstance(expected_size, int):
                raise ValueError("reference_file_invalid")
            try:
                path = self.reference_file_storage.verified_file_path(
                    _record_id(record),
                    expected_size=expected_size,
                )
            except FileNotFoundError:
                missing_input_files += 1
                continue
            except OSError as exc:
                raise ValueError("backup_source_unreadable") from exc
            except ValueError as exc:
                if str(exc) == "Invalid reference file path":
                    raise ValueError("backup_source_path_invalid") from exc
                raise
            _require_within_root(path, self.reference_file_storage.root)
            planned_file = self._optional_input_file(
                task_id,
                "reference_file",
                path,
                source_index,
                extension_source=str(record.get("filename") or path.name),
            )
            if planned_file is None:
                missing_input_files += 1
            else:
                files.append(planned_file)

        entries = tuple(file.entry for file in files)
        fingerprint = canonical_task_fingerprint(metadata, request, entries, organization)
        entry = BackupTaskEntry(
            task_id=task_id,
            created_at=str(metadata.get("created_at") or ""),
            fingerprint=fingerprint,
            files=entries,
        )
        return PlannedBackupTask(
            entry=entry,
            files=tuple(files),
            missing_input_files=missing_input_files,
        )

    def current_task_fingerprint(self, task_id: str) -> str | None:
        try:
            metadata_exists = self.task_storage.metadata_path(task_id).is_file()
        except ValueError:
            metadata_exists = False
        indexed = task_id in self.task_storage.task_index.existing_task_ids([task_id])
        if not metadata_exists and not indexed:
            return None
        return self.plan_task(task_id).entry.fingerprint

    def plan_scope(self, scope: BackupExportScope, plan_path: Path) -> BackupScopePlan:
        if not isinstance(scope, BackupExportScope):
            raise ValueError("backup_scope_invalid")
        plan_path = Path(plan_path)
        scope_rows = self._scope_rows(scope)

        plan_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{plan_path.name}.",
            suffix=".tmp",
            dir=plan_path.parent,
        )
        temporary = Path(temporary_name)
        selected_count = 0
        eligible_count = 0
        try:
            os.fchmod(descriptor, 0o600)
            if os.fstat(descriptor).st_mode & 0o777 != 0o600:
                raise OSError("backup_plan_private_mode_failed")
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as destination:
                descriptor = -1
                for task_id, status in scope_rows:
                    selected_count += 1
                    if status not in TERMINAL_TASK_STATUSES:
                        continue
                    destination.write(json.dumps({"task_id": task_id}, separators=(",", ":")))
                    destination.write("\n")
                    eligible_count += 1
                destination.flush()
                os.fsync(destination.fileno())
            result = BackupScopePlan(
                selected_count=selected_count,
                eligible_count=eligible_count,
                excluded_nonterminal=selected_count - eligible_count,
                plan_path=plan_path,
            )
            os.replace(temporary, plan_path)
        except Exception:
            if descriptor >= 0:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)
            raise
        return result

    def summarize_scope(self, scope: BackupExportScope) -> BackupScopeSummary:
        if not isinstance(scope, BackupExportScope):
            raise ValueError("backup_scope_invalid")
        if scope.kind != "selected":
            filters = scope.filters if scope.kind == "filtered" else HistoryFilter()
            assert filters is not None
            selected_count = self.task_storage.history_query.count_task_ids(filters)
            eligible_count = self.task_storage.history_query.count_task_ids(
                filters,
                terminal_only=True,
            )
            return BackupScopeSummary(
                selected_count=selected_count,
                eligible_count=eligible_count,
                excluded_nonterminal=selected_count - eligible_count,
            )
        selected_count = 0
        eligible_count = 0
        for _, status in self._scope_rows(scope):
            selected_count += 1
            if status in TERMINAL_TASK_STATUSES:
                eligible_count += 1
        return BackupScopeSummary(
            selected_count=selected_count,
            eligible_count=eligible_count,
            excluded_nonterminal=selected_count - eligible_count,
        )

    def _scope_rows(self, scope: BackupExportScope) -> Iterator[tuple[str, str]]:
        if scope.kind == "selected":
            existing: set[str] = set()
            for offset in range(0, len(scope.task_ids), 512):
                existing.update(
                    self.task_storage.task_index.existing_task_ids(
                        list(scope.task_ids[offset : offset + 512])
                    )
                )
            missing = [task_id for task_id in scope.task_ids if task_id not in existing]
            if missing:
                raise ValueError("history_task_not_found")
            return self._selected_task_statuses(scope.task_ids)
        filters = scope.filters if scope.kind == "filtered" else HistoryFilter()
        assert filters is not None
        return self.task_storage.history_query.iter_matching_task_statuses(filters)

    def _selected_task_statuses(
        self,
        task_ids: tuple[str, ...],
    ) -> Iterator[tuple[str, str]]:
        for task_id in task_ids:
            try:
                metadata = self.task_storage.read_metadata(task_id)
            except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
                raise ValueError("task_backup_metadata_invalid") from exc
            yield task_id, str(metadata.get("status") or "")

    def _path_file(
        self,
        task_id: str,
        role: BackupFileRole,
        path: Path,
        source_index: int | None,
        *,
        extension_source: str | None = None,
    ) -> PlannedBackupFile:
        try:
            if not path.is_file():
                raise FileNotFoundError(path)
            size_bytes, digest = _file_digest(path)
        except FileNotFoundError as exc:
            raise ValueError("backup_source_missing") from exc
        except OSError as exc:
            raise ValueError("backup_source_unreadable") from exc
        filename = _archive_filename(role, source_index, extension_source or path.name)
        entry = BackupFileEntry(
            path=safe_backup_member_path(task_id, role, filename),
            role=role,
            required=True,
            size_bytes=size_bytes,
            sha256=digest,
            source_index=source_index,
        )
        return PlannedBackupFile(entry=entry, source_path=path, inline_bytes=None)

    def _optional_input_file(
        self,
        task_id: str,
        role: BackupFileRole,
        path: Path,
        source_index: int,
        *,
        extension_source: str | None = None,
    ) -> PlannedBackupFile | None:
        try:
            return self._path_file(
                task_id,
                role,
                path,
                source_index,
                extension_source=extension_source,
            )
        except ValueError as exc:
            if str(exc) == "backup_source_missing":
                return None
            raise

    def _snapshot_path_file(
        self,
        task_id: str,
        role: BackupFileRole,
        path: Path,
        payload: bytes,
    ) -> PlannedBackupFile:
        filename = _archive_filename(role, None, path.name)
        entry = BackupFileEntry(
            path=safe_backup_member_path(task_id, role, filename),
            role=role,
            required=True,
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            source_index=None,
        )
        return PlannedBackupFile(entry=entry, source_path=path, inline_bytes=None)

    def _inline_file(
        self,
        task_id: str,
        role: BackupFileRole,
        payload: bytes,
    ) -> PlannedBackupFile:
        entry = BackupFileEntry(
            path=safe_backup_member_path(task_id, role, f"{role}.json"),
            role=role,
            required=True,
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            source_index=None,
        )
        return PlannedBackupFile(entry=entry, source_path=None, inline_bytes=payload)


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _read_json_object_once(
    path: Path,
    *,
    missing_code: str,
    invalid_code: str,
) -> tuple[dict[str, object], bytes]:
    try:
        chunks: list[bytes] = []
        total = 0
        with path.open("rb") as source:
            while total <= _MAX_TASK_JSON_BYTES:
                chunk = source.read(min(1024 * 1024, _MAX_TASK_JSON_BYTES + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
        if total > _MAX_TASK_JSON_BYTES:
            raise ValueError(invalid_code)
        payload = b"".join(chunks)
    except FileNotFoundError as exc:
        raise ValueError(missing_code) from exc
    except OSError as exc:
        raise ValueError(invalid_code) from exc
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(invalid_code) from exc
    if not isinstance(parsed, dict):
        raise ValueError(invalid_code)
    return parsed, payload


def _file_digest(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _archive_filename(role: BackupFileRole, source_index: int | None, source_name: str) -> str:
    if source_index is None:
        return f"{role}.json"
    suffix = Path(source_name).suffix.lower()
    if suffix in {".jpeg", ".jpe"}:
        suffix = ".jpg"
    if not re.fullmatch(r"\.[a-z0-9]{1,16}", suffix):
        suffix = ".bin"
    return f"{role}-{source_index:04d}{suffix}"


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("task_backup_metadata_invalid")
    values: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if not text:
            raise ValueError("task_backup_metadata_invalid")
        values.append(text)
    return values


def _record_list(value: object) -> list[dict[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("task_backup_metadata_invalid")
    return value


def _record_id(record: dict[str, object]) -> str:
    value = str(record.get("id") or "").strip()
    if not value:
        raise ValueError("task_backup_metadata_invalid")
    return value


def _output_sources(metadata: dict[str, object]) -> list[tuple[int, str]]:
    outputs = metadata.get("outputs")
    if outputs is not None and not isinstance(outputs, list):
        raise ValueError("task_backup_metadata_invalid")
    if outputs:
        result: list[tuple[int, str]] = []
        indexes: set[int] = set()
        for fallback_index, output in enumerate(outputs, start=1):
            if not isinstance(output, dict) or str(output.get("status") or "") != "completed":
                continue
            index = output.get("index", fallback_index)
            if isinstance(index, bool) or not isinstance(index, int) or index < 1 or index in indexes:
                raise ValueError("task_backup_metadata_invalid")
            filename = str(output.get("file") or "").strip()
            if not filename:
                raise ValueError("task_backup_metadata_invalid")
            indexes.add(index)
            result.append((index, filename))
        return result
    output_files = _string_list(metadata.get("output_files"))
    if output_files:
        return list(enumerate(output_files, start=1))
    output_file = str(metadata.get("output_file") or "").strip()
    return [(1, output_file)] if output_file else []


def _unsafe_relative_path(value: str) -> bool:
    raw = str(value or "").strip().replace("\\", "/")
    candidate = PurePosixPath(raw)
    return not raw or candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts)


def _require_within_root(path: Path, root: Path) -> None:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError as exc:
        raise ValueError("backup_source_path_invalid") from exc


_SENSITIVE_REQUEST_KEYS = frozenset(
    {
        "api_key",
        "access_token",
        "refresh_token",
        "authorization",
        "proxy_authorization",
        "cookie",
        "set_cookie",
        "password",
        "client_secret",
        "secret_key",
        "bearer_token",
    }
)
_EXACT_SENSITIVE_REQUEST_KEYS = frozenset({"token", "secret", "apikey"})


def _contains_sensitive_request_key(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            separated_key = re.sub(
                r"(?<=[a-z0-9])(?=[A-Z])",
                "_",
                str(key),
            )
            normalized = re.sub(
                r"[^a-z0-9]+",
                "_",
                separated_key.casefold(),
            ).strip("_")
            if normalized in _EXACT_SENSITIVE_REQUEST_KEYS or any(
                normalized == sensitive
                or normalized.endswith(f"_{sensitive}")
                for sensitive in _SENSITIVE_REQUEST_KEYS
            ):
                return True
            if _contains_sensitive_request_key(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_sensitive_request_key(item) for item in value)
    return False
