from __future__ import annotations
import hashlib
import json
from pathlib import Path, PureWindowsPath
import stat
import unicodedata
import zipfile
from codex_image.raster_validation import MAX_RASTER_BYTES
from .history_backup_format import BackupFileEntry, BackupManifest, parse_backup_manifest
from .image_uploads import InvalidRasterImage, validate_raster_image
from .reference_files import MAX_REFERENCE_FILE_BYTES, validate_reference_file


_JSON_ROLES = frozenset({"metadata", "request", "organization"})


_RASTER_ROLES = frozenset({"output", "input", "mask", "reference_asset", "gallery_reference"})


_SUPPORTED_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})


_STREAM_BYTES = 1024 * 1024


def _validated_member_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("backup_import_member_path_invalid")
    if value.startswith("/") or PureWindowsPath(value).is_absolute():
        raise ValueError("backup_import_member_path_invalid")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("backup_import_member_path_invalid")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("backup_import_member_path_invalid")
    return "/".join(parts)


def _declared_entries(
    manifest_payload: bytes,
    manifest: BackupManifest,
) -> tuple[dict[str, BackupFileEntry], dict[str, str]]:
    # parse_backup_manifest already validated every raw file record, including
    # paths and hashes for future optional roles that it intentionally omits.
    raw = json.loads(manifest_payload.decode("utf-8"))
    known = {entry.path: entry for task in manifest.tasks for entry in task.files}
    entries: dict[str, BackupFileEntry] = {}
    task_for_path: dict[str, str] = {}
    for raw_task in raw["tasks"]:
        task_id = raw_task["task_id"]
        for raw_file in raw_task["files"]:
            path = raw_file["path"]
            entry = known.get(path)
            if entry is None:
                entry = BackupFileEntry(
                    path=path,
                    role=raw_file["role"],
                    required=raw_file["required"],
                    size_bytes=raw_file["size_bytes"],
                    sha256=raw_file["sha256"].lower(),
                    source_index=raw_file.get("source_index"),
                )
            entries[path] = entry
            task_for_path[path] = task_id
    return entries, task_for_path


class HistoryBackupArchiveValidator:
    def __init__(self, max_entries: int, max_manifest_bytes: int, max_member_bytes: int, max_expanded_bytes: int, max_compression_ratio: float, max_task_json_bytes: int) -> None:
        self._max_entries = max_entries
        self._max_manifest_bytes = max_manifest_bytes
        self._max_member_bytes = max_member_bytes
        self._max_expanded_bytes = max_expanded_bytes
        self._max_compression_ratio = max_compression_ratio
        self._max_task_json_bytes = max_task_json_bytes

    def _validate_zip(
        self,
        upload_path: Path,
    ) -> tuple[BackupManifest, dict[str, dict[str, object]], dict[str, str]]:
        try:
            with zipfile.ZipFile(upload_path, "r", allowZip64=True) as archive:
                infos = archive.infolist()
                info_by_path = self._validate_central_directory(infos)
                manifest_info = info_by_path.get("manifest.json")
                if manifest_info is None:
                    raise ValueError("backup_import_manifest_missing")
                if manifest_info.file_size > self._max_manifest_bytes:
                    raise ValueError("backup_import_manifest_too_large")
                with archive.open(manifest_info, "r") as source:
                    manifest_payload = source.read(self._max_manifest_bytes + 1)
                if len(manifest_payload) > self._max_manifest_bytes:
                    raise ValueError("backup_import_manifest_too_large")
                manifest = parse_backup_manifest(manifest_payload)
                entries, task_for_path = _declared_entries(manifest_payload, manifest)
                archive_members = set(info_by_path) - {"manifest.json"}
                declared_members = set(entries)
                if archive_members - declared_members:
                    raise ValueError("backup_import_member_undeclared")
                if declared_members - archive_members:
                    raise ValueError("backup_import_member_missing")
                if manifest.file_count > self._max_entries - 1:
                    raise ValueError("backup_import_too_many_entries")
                if manifest.uncompressed_bytes > self._max_expanded_bytes:
                    raise ValueError("backup_import_expanded_too_large")
                for entry in entries.values():
                    if entry.size_bytes > self._max_member_bytes:
                        raise ValueError("backup_import_member_too_large")
                return self._validate_members(
                    archive,
                    manifest,
                    info_by_path,
                    entries,
                    task_for_path,
                )
        except ValueError:
            raise
        except (OSError, RuntimeError, NotImplementedError, zipfile.BadZipFile, zipfile.LargeZipFile):
            raise ValueError("backup_import_zip_invalid") from None


    def _validate_central_directory(self, infos: list[zipfile.ZipInfo]) -> dict[str, zipfile.ZipInfo]:
        if len(infos) > self._max_entries:
            raise ValueError("backup_import_too_many_entries")
        paths: dict[str, zipfile.ZipInfo] = {}
        normalized_paths: set[str] = set()
        expanded = 0
        for info in infos:
            path = _validated_member_path(info.filename)
            normalized_path = unicodedata.normalize("NFC", path).casefold()
            if path in paths or normalized_path in normalized_paths:
                raise ValueError("backup_import_duplicate_member_path")
            paths[path] = info
            normalized_paths.add(normalized_path)
            mode = (info.external_attr >> 16) & 0xFFFF
            file_type = stat.S_IFMT(mode)
            if file_type == stat.S_IFLNK:
                raise ValueError("backup_import_symlink_forbidden")
            if file_type not in {0, stat.S_IFREG}:
                raise ValueError("backup_import_special_file_forbidden")
            if info.flag_bits & 0x1:
                raise ValueError("backup_import_encrypted_forbidden")
            if info.compress_type not in _SUPPORTED_COMPRESSION:
                raise ValueError("backup_import_compression_unsupported")
            if info.file_size < 0 or info.compress_size < 0:
                raise ValueError("backup_import_zip_invalid")
            if info.filename == "manifest.json" and info.file_size > self._max_manifest_bytes:
                raise ValueError("backup_import_manifest_too_large")
            if info.file_size > self._max_member_bytes:
                raise ValueError("backup_import_member_too_large")
            expanded += info.file_size
            if expanded > self._max_expanded_bytes:
                raise ValueError("backup_import_expanded_too_large")
            ratio = info.file_size / max(1, info.compress_size)
            if ratio > self._max_compression_ratio:
                raise ValueError("backup_import_compression_ratio_too_high")
        return paths


    def _validate_members(
        self,
        archive: zipfile.ZipFile,
        manifest: BackupManifest,
        infos: dict[str, zipfile.ZipInfo],
        entries: dict[str, BackupFileEntry],
        task_for_path: dict[str, str],
    ) -> tuple[BackupManifest, dict[str, dict[str, object]], dict[str, str]]:
        task_json: dict[str, dict[str, object]] = {task.task_id: {} for task in manifest.tasks}
        invalid_reasons: dict[str, str] = {}
        expanded = 0
        for path, entry in entries.items():
            info = infos[path]
            digest = hashlib.sha256()
            actual_size = 0
            collect_member = False
            if entry.role in _JSON_ROLES:
                collect_member = entry.size_bytes <= self._max_task_json_bytes
                if not collect_member:
                    invalid_reasons.setdefault(task_for_path[path], "backup_import_task_json_too_large")
            elif entry.role in _RASTER_ROLES:
                collect_member = entry.size_bytes <= MAX_RASTER_BYTES
                if not collect_member:
                    invalid_reasons.setdefault(task_for_path[path], "backup_import_raster_invalid")
            elif entry.role == "reference_file":
                collect_member = entry.size_bytes < MAX_REFERENCE_FILE_BYTES
                if not collect_member:
                    invalid_reasons.setdefault(task_for_path[path], "backup_import_reference_file_invalid")
            collected = bytearray() if collect_member else None
            try:
                with archive.open(info, "r") as source:
                    while True:
                        chunk = source.read(_STREAM_BYTES)
                        if not chunk:
                            break
                        actual_size += len(chunk)
                        expanded += len(chunk)
                        if actual_size > entry.size_bytes:
                            raise ValueError("backup_import_member_size_mismatch")
                        if actual_size > self._max_member_bytes:
                            raise ValueError("backup_import_member_too_large")
                        if expanded > self._max_expanded_bytes:
                            raise ValueError("backup_import_expanded_too_large")
                        digest.update(chunk)
                        if collected is not None:
                            collected.extend(chunk)
            except ValueError:
                raise
            except (OSError, RuntimeError, NotImplementedError, zipfile.BadZipFile):
                raise ValueError("backup_import_zip_invalid") from None
            if actual_size != entry.size_bytes:
                raise ValueError("backup_import_member_size_mismatch")
            if digest.hexdigest() != entry.sha256:
                raise ValueError("backup_import_member_hash_mismatch")
            task_id = task_for_path[path]
            if collected is None:
                continue
            payload = bytes(collected)
            if entry.role in _JSON_ROLES:
                if len(payload) > self._max_task_json_bytes:
                    invalid_reasons.setdefault(task_id, "backup_import_task_json_too_large")
                    continue
                try:
                    parsed = json.loads(payload.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    invalid_reasons.setdefault(task_id, "backup_import_task_json_invalid")
                    continue
                if not isinstance(parsed, dict):
                    invalid_reasons.setdefault(task_id, "backup_import_task_json_invalid")
                    continue
                task_json[task_id][entry.role] = parsed
            elif entry.role in _RASTER_ROLES:
                try:
                    validate_raster_image(payload, filename=Path(path).name)
                except InvalidRasterImage:
                    invalid_reasons.setdefault(task_id, "backup_import_raster_invalid")
            elif entry.role == "reference_file":
                try:
                    validate_reference_file(
                        Path(path).name,
                        payload,
                        None,
                        max_bytes=MAX_REFERENCE_FILE_BYTES,
                    )
                except ValueError:
                    invalid_reasons.setdefault(task_id, "backup_import_reference_file_invalid")
        return manifest, task_json, invalid_reasons
