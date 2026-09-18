from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat
from typing import Any
import unicodedata
import zipfile
from .color_settings import _normalize_color_palette_payload
from .image_uploads import InvalidRasterImage, validate_raster_image
from .prompt_snippets import _normalize_prompt_snippets_payload
from .provider_validation import validate_v2_payload
from .user_config_backup_components import ClientPreferences
from .user_config_backup_format import UserConfigBackupManifest


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


class UserConfigArchiveValidator:
    def __init__(self, max_entries: int, max_member_bytes: int, max_expanded_bytes: int, max_compression_ratio: float) -> None:
        self._max_entries = max_entries
        self._max_member_bytes = max_member_bytes
        self._max_expanded_bytes = max_expanded_bytes
        self._max_compression_ratio = max_compression_ratio

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
