from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import PureWindowsPath
from typing import Any, Literal, Mapping


BACKUP_FORMAT = "ilab-conjure-task-backup"
BACKUP_FORMAT_VERSION = 1

BackupFileRole = Literal[
    "metadata",
    "request",
    "output",
    "input",
    "mask",
    "markup",
    "reference_asset",
    "gallery_reference",
    "reference_file",
    "organization",
]

_FILE_ROLES = frozenset(BackupFileRole.__args__)
_JSON_FILENAMES: dict[str, str] = {
    "metadata": "metadata.json",
    "request": "request.json",
    "organization": "organization.json",
}
_ROLE_DIRECTORIES: dict[str, str] = {
    "metadata": "source",
    "request": "source",
    "organization": "source",
    "output": "outputs",
    "input": "inputs/images",
    "reference_asset": "inputs/images",
    "gallery_reference": "inputs/images",
    "mask": "inputs/masks",
    "markup": "inputs/markups",
    "reference_file": "inputs/references",
}
_SAFE_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_BINARY_FILENAME_RE = re.compile(r"^([a-z_]+)-(\d{4})(\.[A-Za-z0-9]{1,16})$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class BackupFileEntry:
    path: str
    role: BackupFileRole
    required: bool
    size_bytes: int
    sha256: str
    source_index: int | None = None


@dataclass(frozen=True)
class BackupTaskEntry:
    task_id: str
    created_at: str
    fingerprint: str
    files: tuple[BackupFileEntry, ...]


@dataclass(frozen=True)
class BackupManifest:
    format: str
    version: int
    created_at: str
    app_version: str
    scope: dict[str, object]
    task_count: int
    file_count: int
    uncompressed_bytes: int
    tasks: tuple[BackupTaskEntry, ...]


_MANIFEST_STRUCTURAL_ERROR_CODES = frozenset({
    "backup_manifest_invalid",
    "format_invalid",
    "version_invalid",
    "tasks_invalid",
    "task_invalid",
    "files_invalid",
    "file_invalid",
    "file.role_invalid",
    "file.size_bytes_invalid",
    "file.sha256_invalid",
    "task.created_at_invalid",
    "task_count_invalid",
    "file_count_invalid",
    "uncompressed_bytes_invalid",
    "scope_invalid",
    "created_at_invalid",
    "app_version_invalid",
})


def parse_backup_manifest(payload: bytes) -> BackupManifest:
    try:
        return _parse_backup_manifest(payload)
    except ValueError as exc:
        if str(exc) in _MANIFEST_STRUCTURAL_ERROR_CODES:
            raise ValueError("backup_manifest_invalid") from None
        raise


def _parse_backup_manifest(payload: bytes) -> BackupManifest:
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("backup_manifest_invalid_json") from exc
    root = _require_mapping(parsed, "backup_manifest")

    if _require_string(root.get("format"), "format") != BACKUP_FORMAT:
        raise ValueError("backup_manifest_format_unsupported")
    if _require_integer(root.get("version"), "version") != BACKUP_FORMAT_VERSION:
        raise ValueError("backup_manifest_version_unsupported")

    raw_tasks = _require_list(root.get("tasks"), "tasks")
    tasks: list[BackupTaskEntry] = []
    task_ids: set[str] = set()
    member_paths: set[str] = set()
    aggregate_file_count = 0
    aggregate_uncompressed_bytes = 0
    for raw_task in raw_tasks:
        task = _require_mapping(raw_task, "task")
        task_id = _require_safe_task_id(task.get("task_id"))
        if task_id in task_ids:
            raise ValueError("backup_manifest_duplicate_task_id")
        task_ids.add(task_id)
        raw_files = _require_list(task.get("files"), "files")
        files: list[BackupFileEntry] = []
        for raw_file in raw_files:
            file_data = _require_mapping(raw_file, "file")
            path = _require_member_path(file_data.get("path"))
            if path in member_paths:
                raise ValueError("backup_manifest_duplicate_member_path")
            member_paths.add(path)
            role = _require_string(file_data.get("role"), "file.role")
            required = file_data.get("required")
            if not isinstance(required, bool):
                raise ValueError("backup_manifest_file_required_invalid")
            size_bytes = _require_integer(file_data.get("size_bytes"), "file.size_bytes")
            if size_bytes < 0:
                raise ValueError("backup_manifest_file_size_invalid")
            sha256 = _require_sha256(file_data.get("sha256"), "file.sha256")
            source_index = _optional_source_index(file_data.get("source_index"))
            aggregate_file_count += 1
            aggregate_uncompressed_bytes += size_bytes

            if role not in _FILE_ROLES:
                if required:
                    raise ValueError("backup_manifest_unknown_required_role")
                continue
            _validate_member_layout(task_id, role, path, source_index)
            files.append(
                BackupFileEntry(
                    path=path,
                    role=role,
                    required=required,
                    size_bytes=size_bytes,
                    sha256=sha256,
                    source_index=source_index,
                )
            )

        tasks.append(
            BackupTaskEntry(
                task_id=task_id,
                created_at=_require_string(task.get("created_at"), "task.created_at"),
                fingerprint=_require_fingerprint(task.get("fingerprint")),
                files=tuple(files),
            )
        )

    task_count = _require_integer(root.get("task_count"), "task_count")
    file_count = _require_integer(root.get("file_count"), "file_count")
    uncompressed_bytes = _require_integer(root.get("uncompressed_bytes"), "uncompressed_bytes")
    if task_count != len(tasks) or file_count != aggregate_file_count or uncompressed_bytes != aggregate_uncompressed_bytes:
        raise ValueError("backup_manifest_aggregate_counts_invalid")
    if task_count < 0 or file_count < 0 or uncompressed_bytes < 0:
        raise ValueError("backup_manifest_aggregate_counts_invalid")

    scope = _require_mapping(root.get("scope"), "scope")
    return BackupManifest(
        format=BACKUP_FORMAT,
        version=BACKUP_FORMAT_VERSION,
        created_at=_require_string(root.get("created_at"), "created_at"),
        app_version=_require_string(root.get("app_version"), "app_version"),
        scope=dict(scope),
        task_count=task_count,
        file_count=file_count,
        uncompressed_bytes=uncompressed_bytes,
        tasks=tuple(tasks),
    )


def safe_backup_member_path(task_id: str, role: BackupFileRole, filename: str) -> str:
    safe_task_id = _require_safe_task_id(task_id)
    if role not in _FILE_ROLES:
        raise ValueError("backup_member_role_invalid")
    if not isinstance(filename, str) or not filename:
        raise ValueError("backup_member_filename_invalid")
    _reject_unsafe_text(filename, "backup_member_filename_invalid")
    if "/" in filename or "\\" in filename:
        raise ValueError("backup_member_filename_invalid")

    expected_json_filename = _JSON_FILENAMES.get(role)
    if expected_json_filename is not None:
        if filename != expected_json_filename:
            raise ValueError("backup_member_filename_invalid")
    else:
        match = _BINARY_FILENAME_RE.fullmatch(filename)
        if match is None or match.group(1) != role or int(match.group(2)) < 1:
            raise ValueError("backup_member_filename_invalid")
    return f"tasks/{safe_task_id}/{_ROLE_DIRECTORIES[role]}/{filename}"


def canonical_task_fingerprint(
    metadata: Mapping[str, object],
    request: Mapping[str, object],
    files: object,
    organization: Mapping[str, object],
) -> str:
    file_tuples = sorted(_canonical_file_tuples(files), key=_file_tuple_sort_key)
    payload = {
        "metadata": _without_absolute_paths(metadata),
        "request": _without_absolute_paths(request),
        "organization": _canonical_organization(organization),
        "files": file_tuples,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _validate_member_layout(
    task_id: str,
    role: str,
    path: str,
    source_index: int | None,
) -> None:
    filename = path.rsplit("/", 1)[-1]
    expected_path = safe_backup_member_path(task_id, role, filename)
    if path != expected_path:
        raise ValueError("backup_manifest_member_path_invalid")
    if role in _JSON_FILENAMES:
        if source_index is not None:
            raise ValueError("backup_manifest_source_index_invalid")
        return
    match = _BINARY_FILENAME_RE.fullmatch(filename)
    assert match is not None
    if source_index != int(match.group(2)):
        raise ValueError("backup_manifest_source_index_invalid")


def _canonical_file_tuples(files: object) -> list[tuple[str, int | None, int, str]]:
    if not isinstance(files, (list, tuple)):
        raise ValueError("backup_fingerprint_files_invalid")
    canonical: list[tuple[str, int | None, int, str]] = []
    for file_data in files:
        if isinstance(file_data, BackupFileEntry):
            role = file_data.role
            source_index = file_data.source_index
            size_bytes = file_data.size_bytes
            sha256 = file_data.sha256
        else:
            entry = _require_mapping(file_data, "fingerprint_file")
            role = _require_string(entry.get("role"), "fingerprint_file.role")
            source_index = _optional_source_index(entry.get("source_index"))
            size_bytes = _require_integer(entry.get("size_bytes"), "fingerprint_file.size_bytes")
            sha256 = _require_sha256(entry.get("sha256"), "fingerprint_file.sha256")
        if role not in _FILE_ROLES or size_bytes < 0:
            raise ValueError("backup_fingerprint_file_invalid")
        canonical.append((role, source_index, size_bytes, sha256))
    return canonical


def _file_tuple_sort_key(item: tuple[str, int | None, int, str]) -> tuple[str, int, int, int, str]:
    role, source_index, size_bytes, sha256 = item
    return role, source_index is not None, source_index or 0, size_bytes, sha256


def _without_absolute_paths(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _without_absolute_paths(item)
            for key, item in value.items()
            if not (isinstance(key, str) and _is_absolute_path(key))
            if not (isinstance(item, str) and _is_absolute_path(item))
        }
    if isinstance(value, (list, tuple)):
        return [
            _without_absolute_paths(item)
            for item in value
            if not (isinstance(item, str) and _is_absolute_path(item))
        ]
    return value


def _canonical_organization(value: Mapping[str, object]) -> dict[str, object]:
    favorite = value.get("favorite", False)
    tags = value.get("tags", [])
    if not isinstance(favorite, bool) or not isinstance(tags, (list, tuple)):
        raise ValueError("backup_fingerprint_organization_invalid")
    normalized: dict[str, str] = {}
    for item in tags:
        if not isinstance(item, Mapping):
            raise ValueError("backup_fingerprint_organization_invalid")
        raw_name = item.get("name")
        if not isinstance(raw_name, str):
            raise ValueError("backup_fingerprint_organization_invalid")
        name = unicodedata.normalize("NFKC", raw_name).strip()
        if not name:
            raise ValueError("backup_fingerprint_organization_invalid")
        normalized.setdefault(name.casefold(), name)
    return {
        "favorite": favorite,
        "tags": [{"name": normalized[key]} for key in sorted(normalized)],
    }


def _is_absolute_path(value: str) -> bool:
    return value.startswith("/") or PureWindowsPath(value).is_absolute()


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label}_invalid")
    return value


def _require_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label}_invalid")
    return value


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label}_invalid")
    return value


def _require_integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label}_invalid")
    return value


def _optional_source_index(value: object) -> int | None:
    if value is None:
        return None
    source_index = _require_integer(value, "file.source_index")
    if source_index < 1:
        raise ValueError("backup_manifest_source_index_invalid")
    return source_index


def _require_safe_task_id(value: object) -> str:
    if not isinstance(value, str) or not _SAFE_TASK_ID_RE.fullmatch(value) or value in {".", ".."}:
        raise ValueError("backup_manifest_task_id_invalid")
    return value


def _reject_unsafe_text(value: str, message: str) -> None:
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(message)


def _require_member_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("backup_manifest_member_path_invalid")
    _reject_unsafe_text(value, "backup_manifest_member_path_invalid")
    if _is_absolute_path(value) or "\\" in value:
        raise ValueError("backup_manifest_member_path_invalid")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("backup_manifest_member_path_invalid")
    return value


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label}_invalid")
    return value.lower()


def _require_fingerprint(value: object) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or not _SHA256_RE.fullmatch(value[7:]):
        raise ValueError("backup_manifest_fingerprint_invalid")
    return "sha256:" + value[7:].lower()


__all__ = (
    "BACKUP_FORMAT",
    "BACKUP_FORMAT_VERSION",
    "BackupFileEntry",
    "BackupFileRole",
    "BackupManifest",
    "BackupTaskEntry",
    "canonical_task_fingerprint",
    "parse_backup_manifest",
    "safe_backup_member_path",
)
