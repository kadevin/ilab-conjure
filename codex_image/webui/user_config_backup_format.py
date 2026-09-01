from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import PureWindowsPath
from typing import Literal, Mapping, get_args


USER_CONFIG_BACKUP_FORMAT = "ilab-conjure-user-config-backup"
USER_CONFIG_BACKUP_FORMAT_VERSION = 1

UserConfigSection = Literal["chips", "gallery", "templates", "settings"]

_SECTION_ORDER: tuple[UserConfigSection, ...] = get_args(UserConfigSection)
_SECTIONS = frozenset(_SECTION_ORDER)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_RASTER_SUFFIXES = frozenset({".gif", ".jpeg", ".jpg", ".png", ".webp"})
_SETTINGS_FILENAMES = frozenset({
    "webui.json",
    "auth-source.json",
    "providers.json",
    "network.json",
    "client-preferences.json",
})
_ROOT_FIELDS = frozenset({
    "format",
    "format_version",
    "app_version",
    "created_at",
    "sections",
    "contains_secrets",
    "members",
})
_MEMBER_FIELDS = frozenset({"section", "path", "size_bytes", "sha256"})


@dataclass(frozen=True)
class UserConfigBackupMember:
    section: UserConfigSection
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class UserConfigBackupManifest:
    format: str
    format_version: int
    app_version: str
    created_at: str
    sections: tuple[UserConfigSection, ...]
    contains_secrets: bool
    members: tuple[UserConfigBackupMember, ...]


def safe_user_config_member_path(
    section: UserConfigSection,
    *parts: str,
) -> str:
    if section not in _SECTIONS or not parts:
        raise ValueError("user_config_member_path_invalid")
    path = "/".join((section, *parts))
    try:
        clean = _validated_member_path(path)
        _validate_member_layout(section, clean)
    except ValueError:
        raise ValueError("user_config_member_path_invalid") from None
    return clean


def serialize_user_config_manifest(manifest: UserConfigBackupManifest) -> bytes:
    if not isinstance(manifest, UserConfigBackupManifest):
        raise ValueError("user_config_manifest_invalid")
    raw = {
        "format": manifest.format,
        "format_version": manifest.format_version,
        "app_version": manifest.app_version,
        "created_at": manifest.created_at,
        "sections": list(manifest.sections),
        "contains_secrets": manifest.contains_secrets,
        "members": [
            {
                "section": member.section,
                "path": member.path,
                "size_bytes": member.size_bytes,
                "sha256": member.sha256,
            }
            for member in manifest.members
        ],
    }
    parsed = _parse_user_config_manifest_object(raw)
    canonical = _manifest_object(parsed)
    return (
        json.dumps(
            canonical,
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
        )
        + "\n"
    ).encode("utf-8")


def parse_user_config_manifest(payload: bytes) -> UserConfigBackupManifest:
    try:
        raw = json.loads(payload.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("user_config_manifest_invalid_json") from exc
    return _parse_user_config_manifest_object(raw)


def _parse_user_config_manifest_object(raw: object) -> UserConfigBackupManifest:
    root = _require_exact_mapping(raw, _ROOT_FIELDS)
    backup_format = _require_string(root.get("format"))
    if backup_format != USER_CONFIG_BACKUP_FORMAT:
        raise ValueError("user_config_manifest_format_unsupported")
    format_version = _require_integer(root.get("format_version"))
    if format_version != USER_CONFIG_BACKUP_FORMAT_VERSION:
        raise ValueError("user_config_manifest_version_unsupported")

    raw_sections = root.get("sections")
    if not isinstance(raw_sections, list) or not raw_sections:
        raise ValueError("user_config_manifest_invalid")
    sections: list[UserConfigSection] = []
    for raw_section in raw_sections:
        if not isinstance(raw_section, str) or raw_section not in _SECTIONS:
            raise ValueError("user_config_manifest_invalid")
        sections.append(raw_section)  # type: ignore[arg-type]
    if len(sections) != len(set(sections)):
        raise ValueError("user_config_manifest_invalid")
    canonical_sections = tuple(section for section in _SECTION_ORDER if section in sections)
    if tuple(sections) != canonical_sections:
        raise ValueError("user_config_manifest_invalid")

    contains_secrets = root.get("contains_secrets")
    if not isinstance(contains_secrets, bool):
        raise ValueError("user_config_manifest_invalid")

    raw_members = root.get("members")
    if not isinstance(raw_members, list) or not raw_members:
        raise ValueError("user_config_manifest_invalid")
    members: list[UserConfigBackupMember] = []
    member_paths: set[str] = set()
    member_sections: set[UserConfigSection] = set()
    for raw_member in raw_members:
        member_data = _require_exact_mapping(raw_member, _MEMBER_FIELDS)
        raw_section = member_data.get("section")
        if not isinstance(raw_section, str) or raw_section not in sections:
            raise ValueError("user_config_manifest_invalid")
        section: UserConfigSection = raw_section  # type: ignore[assignment]
        try:
            path = _validated_member_path(member_data.get("path"))
            _validate_member_layout(section, path)
        except ValueError:
            raise ValueError("user_config_manifest_member_path_invalid") from None
        if path in member_paths:
            raise ValueError("user_config_manifest_invalid")
        member_paths.add(path)
        member_sections.add(section)
        size_bytes = _require_integer(member_data.get("size_bytes"))
        if size_bytes < 0:
            raise ValueError("user_config_manifest_invalid")
        sha256 = member_data.get("sha256")
        if not isinstance(sha256, str) or _SHA256_RE.fullmatch(sha256) is None:
            raise ValueError("user_config_manifest_invalid")
        members.append(UserConfigBackupMember(section, path, size_bytes, sha256))
    if member_sections != set(sections):
        raise ValueError("user_config_manifest_invalid")

    return UserConfigBackupManifest(
        format=USER_CONFIG_BACKUP_FORMAT,
        format_version=USER_CONFIG_BACKUP_FORMAT_VERSION,
        app_version=_require_string(root.get("app_version")),
        created_at=_require_string(root.get("created_at")),
        sections=tuple(sections),
        contains_secrets=contains_secrets,
        members=tuple(members),
    )


def _manifest_object(manifest: UserConfigBackupManifest) -> dict[str, object]:
    return {
        "format": manifest.format,
        "format_version": manifest.format_version,
        "app_version": manifest.app_version,
        "created_at": manifest.created_at,
        "sections": list(manifest.sections),
        "contains_secrets": manifest.contains_secrets,
        "members": [
            {
                "section": member.section,
                "path": member.path,
                "size_bytes": member.size_bytes,
                "sha256": member.sha256,
            }
            for member in manifest.members
        ],
    }


def _require_exact_mapping(
    value: object,
    fields: frozenset[str],
) -> Mapping[str, object]:
    if (
        not isinstance(value, dict)
        or not all(isinstance(key, str) for key in value)
        or frozenset(value) != fields
    ):
        raise ValueError("user_config_manifest_invalid")
    return value


def _require_string(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("user_config_manifest_invalid")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("user_config_manifest_invalid")
    return value


def _require_integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("user_config_manifest_invalid")
    return value


def _validated_member_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("user_config_manifest_member_path_invalid")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("user_config_manifest_member_path_invalid")
    if "\\" in value or value.startswith("/") or PureWindowsPath(value).is_absolute():
        raise ValueError("user_config_manifest_member_path_invalid")
    if _WINDOWS_DRIVE_RE.match(value):
        raise ValueError("user_config_manifest_member_path_invalid")
    raw_parts = value.split("/")
    normalized = unicodedata.normalize("NFKC", value)
    normalized_parts = normalized.split("/")
    if (
        "\\" in normalized
        or normalized.startswith("/")
        or PureWindowsPath(normalized).is_absolute()
        or _WINDOWS_DRIVE_RE.match(normalized)
        or len(raw_parts) != len(normalized_parts)
        or any(part in {"", ".", ".."} for part in raw_parts)
        or any(part in {"", ".", ".."} for part in normalized_parts)
    ):
        raise ValueError("user_config_manifest_member_path_invalid")
    return value


def _validate_member_layout(section: UserConfigSection, path: str) -> None:
    parts = path.split("/")
    if not parts or parts[0] != section:
        raise ValueError("user_config_manifest_member_path_invalid")
    relative = parts[1:]
    if section == "chips":
        if relative not in (["colors.json"], ["prompt-snippets.json"]):
            raise ValueError("user_config_manifest_member_path_invalid")
        return
    if section == "settings":
        if len(relative) != 1 or relative[0] not in _SETTINGS_FILENAMES:
            raise ValueError("user_config_manifest_member_path_invalid")
        return
    if section == "templates":
        if relative == ["prompt-templates.json"]:
            return
        if len(relative) != 2 or relative[0] != "thumbnails":
            raise ValueError("user_config_manifest_member_path_invalid")
        filename = relative[1]
        suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        digest = filename[: -len(suffix)] if suffix else filename
        if _SHA256_RE.fullmatch(digest) is None or suffix not in _RASTER_SUFFIXES:
            raise ValueError("user_config_manifest_member_path_invalid")
        return
    if section == "gallery":
        if relative == ["categories.json"]:
            return
        if len(relative) != 3 or relative[0] != "items":
            raise ValueError("user_config_manifest_member_path_invalid")
        item_id, filename = relative[1:]
        if _SAFE_ID_RE.fullmatch(item_id) is None or item_id in {".", ".."}:
            raise ValueError("user_config_manifest_member_path_invalid")
        if filename == "metadata.json":
            return
        _validate_portable_filename(filename)
        if not any(filename.lower().endswith(suffix) for suffix in _RASTER_SUFFIXES):
            raise ValueError("user_config_manifest_member_path_invalid")
        return
    raise ValueError("user_config_manifest_member_path_invalid")


def _validate_portable_filename(filename: str) -> None:
    if (
        not filename
        or len(filename) > 255
        or filename in {".", ".."}
        or any(character in '<>:"/\\|?*' for character in filename)
        or any(ord(character) < 32 or ord(character) == 127 for character in filename)
    ):
        raise ValueError("user_config_manifest_member_path_invalid")
    normalized = unicodedata.normalize("NFKC", filename)
    if normalized in {".", ".."} or any(character in "/\\" for character in normalized):
        raise ValueError("user_config_manifest_member_path_invalid")


__all__ = (
    "USER_CONFIG_BACKUP_FORMAT",
    "USER_CONFIG_BACKUP_FORMAT_VERSION",
    "UserConfigBackupManifest",
    "UserConfigBackupMember",
    "UserConfigSection",
    "parse_user_config_manifest",
    "safe_user_config_member_path",
    "serialize_user_config_manifest",
)
