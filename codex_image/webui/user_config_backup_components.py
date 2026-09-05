from __future__ import annotations

from collections.abc import Collection
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator, Literal, cast, get_args
from urllib.parse import urlsplit

from codex_image.version import APP_VERSION

from .color_settings import ColorPaletteSettings
from .gallery_storage import GallerySnapshot, GalleryStorage
from .image_uploads import InvalidRasterImage, validate_raster_image
from .network_egress import NetworkEgressSettings
from .prompt_snippets import PromptSnippetSettings
from .prompt_template_assets import (
    PromptTemplateAssetStorage,
    PromptTemplateThumbnailResolver,
)
from .prompt_templates import PromptTemplateSettings
from .provider_settings import ProviderSettings
from .settings_store import AuthSettings, WebUISettings
from .user_config_backup_format import (
    USER_CONFIG_BACKUP_FORMAT,
    USER_CONFIG_BACKUP_FORMAT_VERSION,
    UserConfigBackupManifest,
    UserConfigBackupMember,
    UserConfigSection,
    safe_user_config_member_path,
)


_SECTION_ORDER: tuple[UserConfigSection, ...] = get_args(UserConfigSection)
_SECTION_SET = frozenset(_SECTION_ORDER)
_MIME_SUFFIXES = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


@dataclass(frozen=True)
class ClientPreferences:
    theme: Literal["system", "light", "dark"]
    notifications_in_app: bool
    notifications_system: bool

    def __post_init__(self) -> None:
        if self.theme not in {"system", "light", "dark"}:
            raise ValueError("client_preferences_invalid")
        if not isinstance(self.notifications_in_app, bool) or not isinstance(
            self.notifications_system,
            bool,
        ):
            raise ValueError("client_preferences_invalid")


@dataclass(frozen=True)
class UserConfigSectionSummary:
    section: UserConfigSection
    item_count: int
    size_bytes: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class FileIdentity:
    size_bytes: int
    mtime_ns: int
    device: int
    inode: int
    sha256: str


@dataclass(frozen=True)
class PlannedUserConfigMember:
    entry: UserConfigBackupMember
    data: bytes | None
    source_path: Path | None
    source_identity: FileIdentity | None


@dataclass(frozen=True)
class UserConfigWarning:
    section: UserConfigSection
    code: str
    item_id: str | None = None


@dataclass(frozen=True)
class UserConfigBackupPlan:
    manifest: UserConfigBackupManifest
    members: tuple[PlannedUserConfigMember, ...]
    warnings: tuple[UserConfigWarning, ...]


class UserConfigBackupPlanner:
    """Build immutable backup plans while holding stores in one lock order."""

    def __init__(
        self,
        *,
        color_settings: ColorPaletteSettings,
        prompt_snippet_settings: PromptSnippetSettings,
        gallery_storage: GalleryStorage,
        prompt_template_settings: PromptTemplateSettings,
        prompt_template_asset_storage: PromptTemplateAssetStorage,
        prompt_template_thumbnail_resolver: PromptTemplateThumbnailResolver,
        webui_settings: WebUISettings,
        auth_settings: AuthSettings,
        provider_settings: ProviderSettings,
        network_egress_settings: NetworkEgressSettings,
    ) -> None:
        self.color_settings = color_settings
        self.prompt_snippet_settings = prompt_snippet_settings
        self.gallery_storage = gallery_storage
        self.prompt_template_settings = prompt_template_settings
        self.prompt_template_asset_storage = prompt_template_asset_storage
        self.prompt_template_thumbnail_resolver = prompt_template_thumbnail_resolver
        self.webui_settings = webui_settings
        self.auth_settings = auth_settings
        self.provider_settings = provider_settings
        self.network_egress_settings = network_egress_settings

    def summary(self) -> tuple[UserConfigSectionSummary, ...]:
        with self._exclusive(_SECTION_ORDER):
            colors = self.color_settings.read()
            snippets = self.prompt_snippet_settings.read()
            gallery = self._gallery_snapshot()
            template_payload, template_members, template_warnings = (
                self._template_snapshot()
            )
            settings_payloads, api_keys_available = self._settings_payloads(
                include_api_keys=False,
                client_preferences=ClientPreferences("system", True, False),
            )

            chip_count = (
                len(colors.get("favorites", []))
                + len(colors.get("recent_colors", []))
                + len(snippets.get("snippets", []))
            )
            gallery_bytes = sum(item.size_bytes for item in gallery.items)
            thumbnail_bytes = sum(
                member.entry.size_bytes for member in template_members
            )
            template_warning_codes = tuple(
                dict.fromkeys(warning.code for warning in template_warnings)
            )
            settings_warnings = (
                ("api_keys_available",) if api_keys_available else ()
            )
            return (
                UserConfigSectionSummary(
                    "chips",
                    chip_count,
                    len(_json_bytes(colors)) + len(_json_bytes(snippets)),
                    (),
                ),
                UserConfigSectionSummary(
                    "gallery",
                    len(gallery.items),
                    gallery_bytes,
                    (),
                ),
                UserConfigSectionSummary(
                    "templates",
                    len(template_payload.get("templates", []))
                    + len(template_members),
                    len(_json_bytes(template_payload)) + thumbnail_bytes,
                    template_warning_codes,
                ),
                UserConfigSectionSummary(
                    "settings",
                    len(settings_payloads),
                    sum(len(_json_bytes(payload)) for payload in settings_payloads.values()),
                    settings_warnings,
                ),
            )

    def plan(
        self,
        sections: Collection[UserConfigSection],
        *,
        include_api_keys: bool,
        client_preferences: ClientPreferences | None,
    ) -> UserConfigBackupPlan:
        selected = _normalize_sections(sections)
        if not isinstance(include_api_keys, bool):
            raise ValueError("include_api_keys_invalid")
        settings_selected = "settings" in selected
        if settings_selected != (client_preferences is not None):
            raise ValueError("client_preferences_required_for_settings")
        if include_api_keys and not settings_selected:
            raise ValueError("include_api_keys_requires_settings")
        if client_preferences is not None and not isinstance(
            client_preferences,
            ClientPreferences,
        ):
            raise ValueError("client_preferences_invalid")

        members: list[PlannedUserConfigMember] = []
        warnings: list[UserConfigWarning] = []
        with self._exclusive(selected):
            if "chips" in selected:
                members.extend(
                    (
                        _data_member(
                            "chips",
                            "colors.json",
                            _json_bytes(self.color_settings.read()),
                        ),
                        _data_member(
                            "chips",
                            "prompt-snippets.json",
                            _json_bytes(self.prompt_snippet_settings.read()),
                        ),
                    )
                )
            if "gallery" in selected:
                members.extend(self._gallery_members(self._gallery_snapshot()))
            if "templates" in selected:
                template_payload, thumbnail_members, template_warnings = (
                    self._template_snapshot()
                )
                members.append(
                    _data_member(
                        "templates",
                        "prompt-templates.json",
                        _json_bytes(template_payload),
                    )
                )
                members.extend(thumbnail_members)
                warnings.extend(template_warnings)
            if "settings" in selected:
                assert client_preferences is not None
                settings_payloads, _ = self._settings_payloads(
                    include_api_keys=include_api_keys,
                    client_preferences=client_preferences,
                )
                for filename, payload in settings_payloads.items():
                    members.append(
                        _data_member(
                            "settings",
                            filename,
                            _json_bytes(payload),
                        )
                    )

        manifest = UserConfigBackupManifest(
            format=USER_CONFIG_BACKUP_FORMAT,
            format_version=USER_CONFIG_BACKUP_FORMAT_VERSION,
            app_version=APP_VERSION,
            created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            sections=selected,
            contains_secrets=bool(include_api_keys),
            members=tuple(member.entry for member in members),
        )
        return UserConfigBackupPlan(
            manifest=manifest,
            members=tuple(members),
            warnings=tuple(warnings),
        )

    @contextmanager
    def _exclusive(
        self,
        sections: Collection[UserConfigSection],
    ) -> Iterator[None]:
        selected = set(sections)
        stores: list[Any] = []
        if "chips" in selected:
            stores.extend((self.color_settings, self.prompt_snippet_settings))
        if "gallery" in selected:
            stores.append(self.gallery_storage)
        if "templates" in selected:
            stores.extend(
                (
                    self.prompt_template_settings,
                    self.prompt_template_asset_storage,
                )
            )
        if "settings" in selected:
            stores.extend(
                (
                    self.webui_settings,
                    self.auth_settings,
                    self.provider_settings,
                    self.network_egress_settings,
                )
            )
        with ExitStack() as stack:
            for store in stores:
                stack.enter_context(store.exclusive())
            yield

    def _gallery_members(
        self,
        snapshot: GallerySnapshot,
    ) -> tuple[PlannedUserConfigMember, ...]:
        members: list[PlannedUserConfigMember] = [
            _data_member(
                "gallery",
                "categories.json",
                _json_bytes(list(snapshot.categories)),
            )
        ]
        for item in snapshot.items:
            item_id = str(item.metadata["id"])
            metadata = dict(item.metadata)
            filename = str(metadata.get("filename") or "")
            try:
                image_member_path = safe_user_config_member_path(
                    "gallery",
                    "items",
                    item_id,
                    filename,
                )
            except ValueError:
                metadata["filename"] = f"image{_MIME_SUFFIXES[item.mime_type]}"
                try:
                    image_member_path = safe_user_config_member_path(
                        "gallery",
                        "items",
                        item_id,
                        str(metadata["filename"]),
                    )
                except ValueError as exc:
                    raise ValueError("user_config_backup_gallery_invalid") from exc
            members.append(
                _data_member(
                    "gallery",
                    f"items/{item_id}/metadata.json",
                    _json_bytes(metadata),
                )
            )
            members.append(
                _file_member_for_path(
                    "gallery",
                    image_member_path,
                    item.image_path,
                )
            )
        return tuple(members)

    def _gallery_snapshot(self) -> GallerySnapshot:
        try:
            return self.gallery_storage.snapshot()
        except ValueError as exc:
            raise ValueError("user_config_backup_gallery_invalid") from exc

    def _template_snapshot(
        self,
    ) -> tuple[
        dict[str, Any],
        tuple[PlannedUserConfigMember, ...],
        tuple[UserConfigWarning, ...],
    ]:
        payload = self.prompt_template_settings.read()
        templates: list[dict[str, Any]] = []
        thumbnails: dict[str, PlannedUserConfigMember] = {}
        warnings: list[UserConfigWarning] = []
        for raw_template in payload.get("templates", []):
            template = dict(raw_template)
            template.pop("thumbnail_member", None)
            thumbnail_url = str(template.get("thumbnail_url") or "").strip()
            if not thumbnail_url:
                templates.append(template)
                continue
            parsed = urlsplit(thumbnail_url)
            if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
                templates.append(template)
                continue
            path = self.prompt_template_thumbnail_resolver.resolve(thumbnail_url)
            if path is None:
                template.pop("thumbnail_url", None)
                warnings.append(
                    UserConfigWarning(
                        "templates",
                        "template_thumbnail_missing",
                        str(template.get("id") or "") or None,
                    )
                )
                templates.append(template)
                continue
            try:
                data = path.read_bytes()
                validated = validate_raster_image(data, filename=path.name)
            except (InvalidRasterImage, OSError):
                template.pop("thumbnail_url", None)
                warnings.append(
                    UserConfigWarning(
                        "templates",
                        "template_thumbnail_missing",
                        str(template.get("id") or "") or None,
                    )
                )
                templates.append(template)
                continue
            suffix = _MIME_SUFFIXES[validated.mime_type]
            member_path = safe_user_config_member_path(
                "templates",
                "thumbnails",
                f"{validated.sha256}{suffix}",
            )
            if validated.sha256 not in thumbnails:
                thumbnails[validated.sha256] = _file_member_for_path(
                    "templates",
                    member_path,
                    path,
                )
            template.pop("thumbnail_url", None)
            template["thumbnail_member"] = member_path
            templates.append(template)
        return (
            {**payload, "templates": templates},
            tuple(thumbnails.values()),
            tuple(warnings),
        )

    def _settings_payloads(
        self,
        *,
        include_api_keys: bool,
        client_preferences: ClientPreferences,
    ) -> tuple[dict[str, Any], bool]:
        full_provider_snapshot = self.provider_settings.backup_snapshot(
            include_api_keys=True
        )
        api_keys_available = any(
            bool(provider.get("api_key"))
            for provider in full_provider_snapshot.get("providers", [])
            if isinstance(provider, dict)
        )
        providers = (
            full_provider_snapshot
            if include_api_keys
            else self.provider_settings.backup_snapshot(include_api_keys=False)
        )
        return (
            {
                "webui.json": self.webui_settings.snapshot(),
                "auth-source.json": self.auth_settings.snapshot(),
                "providers.json": providers,
                "network.json": self.network_egress_settings.snapshot_payload(),
                "client-preferences.json": {
                    "theme": client_preferences.theme,
                    "notifications_in_app": client_preferences.notifications_in_app,
                    "notifications_system": client_preferences.notifications_system,
                },
            },
            api_keys_available,
        )


def _normalize_sections(
    sections: Collection[UserConfigSection],
) -> tuple[UserConfigSection, ...]:
    if isinstance(sections, (str, bytes)):
        raise ValueError("user_config_sections_invalid")
    raw = list(sections)
    if not raw or len(raw) != len(set(raw)):
        raise ValueError("user_config_sections_invalid")
    if any(section not in _SECTION_SET for section in raw):
        raise ValueError("user_config_sections_invalid")
    return tuple(section for section in _SECTION_ORDER if section in raw)


def _json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _data_member(
    section: UserConfigSection,
    relative_path: str,
    data: bytes,
) -> PlannedUserConfigMember:
    path = safe_user_config_member_path(section, *relative_path.split("/"))
    digest = hashlib.sha256(data).hexdigest()
    return PlannedUserConfigMember(
        entry=UserConfigBackupMember(section, path, len(data), digest),
        data=data,
        source_path=None,
        source_identity=None,
    )


def _file_member(
    section: UserConfigSection,
    relative_path: str,
    source_path: Path,
) -> PlannedUserConfigMember:
    path = safe_user_config_member_path(section, *relative_path.split("/"))
    return _file_member_for_path(section, path, source_path)


def _file_member_for_path(
    section: UserConfigSection,
    member_path: str,
    source_path: Path,
) -> PlannedUserConfigMember:
    identity = _file_identity(source_path)
    return PlannedUserConfigMember(
        entry=UserConfigBackupMember(
            section,
            member_path,
            identity.size_bytes,
            identity.sha256,
        ),
        data=None,
        source_path=source_path,
        source_identity=identity,
    )


def _file_identity(path: Path) -> FileIdentity:
    candidate = Path(path)
    if candidate.is_symlink():
        raise ValueError("user_config_source_file_invalid")
    try:
        before = candidate.stat()
        digest = hashlib.sha256()
        with candidate.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        after = candidate.stat()
    except OSError as exc:
        raise ValueError("user_config_source_file_invalid") from exc
    before_identity = (
        before.st_size,
        before.st_mtime_ns,
        before.st_dev,
        before.st_ino,
    )
    after_identity = (
        after.st_size,
        after.st_mtime_ns,
        after.st_dev,
        after.st_ino,
    )
    if before_identity != after_identity or not candidate.is_file():
        raise ValueError("user_config_source_file_changed")
    return FileIdentity(
        size_bytes=after.st_size,
        mtime_ns=after.st_mtime_ns,
        device=after.st_dev,
        inode=after.st_ino,
        sha256=digest.hexdigest(),
    )


__all__ = (
    "ClientPreferences",
    "FileIdentity",
    "PlannedUserConfigMember",
    "UserConfigBackupPlan",
    "UserConfigBackupPlanner",
    "UserConfigSectionSummary",
    "UserConfigWarning",
)
