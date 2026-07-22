from __future__ import annotations

import json
import os
import platform
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codex_image.version import APP_VERSION, APP_VERSION_TAG

UPDATE_NOTICE_FILENAME = "update-notice.json"
POST_UPDATE_ONBOARDING_FILENAME = "post-update-onboarding.json"
STANDARD_APP_TRANSITION_KIND = "portable_standard_app_transition"
STANDARD_APP_TRANSITION_VERSION = "0.5.5"
RELEASES_URL = "https://github.com/kadevin/ilab-conjure/releases"


def _parse_semver(value: str | None) -> tuple[int, int, int] | None:
    match = re.match(r"^[vV]?(\d+)\.(\d+)\.(\d+)", str(value or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _normalize_version(value: str | None) -> str:
    parts = _parse_semver(value)
    if not parts:
        return APP_VERSION
    return ".".join(str(part) for part in parts)


def _optional_version(value: str | None) -> str | None:
    parts = _parse_semver(value)
    if not parts:
        return None
    return ".".join(str(part) for part in parts)


def _version_tag(value: str | None) -> str:
    return f"v{_normalize_version(value)}"


def _portable_bundle_dir() -> Path | None:
    raw = os.environ.get("ILAB_CONJURE_BUNDLE_DIR")
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.exists() else None


def _standard_app_dir() -> Path | None:
    if os.environ.get("APP_LAUNCHER_MODE") != "standard":
        return None
    raw = os.environ.get("ILAB_CONJURE_APP_DIR")
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.exists() else None


def _runtime_source(bundle_dir: Path | None, app_dir: Path | None) -> str:
    if bundle_dir is not None:
        return "portable"
    if app_dir is not None or os.environ.get("APP_LAUNCHER_MODE") == "standard":
        return "standard_app"
    return "source"


def _data_dir_from_output_root(output_root: Path) -> Path | None:
    raw = os.environ.get("ILAB_CONJURE_DATA_DIR")
    if raw:
        return Path(raw).expanduser()
    if output_root.name == "webui-outputs":
        return output_root.parent
    return None


def _portable_version(bundle_dir: Path | None) -> str:
    if not bundle_dir:
        return APP_VERSION
    version_file = bundle_dir / "portable-version.txt"
    try:
        raw = version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return APP_VERSION
    return _normalize_version(raw)


def _standard_app_version(app_dir: Path | None) -> str:
    if not app_dir:
        return APP_VERSION
    version_files = [
        app_dir.parent / "app-version.txt",
        app_dir / "app-version.txt",
    ]
    for version_file in version_files:
        try:
            raw = version_file.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        return _normalize_version(raw)
    return APP_VERSION


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_update_notice(data_dir: Path | None, current_version: str) -> dict[str, Any] | None:
    if not data_dir:
        return None
    notice_path = data_dir / UPDATE_NOTICE_FILENAME
    payload = _read_json_object(notice_path)
    if payload is None:
        return None
    latest_version = _normalize_version(str(payload.get("latest_version") or payload.get("latest") or ""))
    current_parts = _parse_semver(current_version)
    latest_parts = _parse_semver(latest_version)
    if not current_parts or not latest_parts or latest_parts <= current_parts:
        return None
    return {
        "latest_version": latest_version,
        "latest_version_label": _version_tag(latest_version),
        "checked_at": payload.get("checked_at"),
        "release_url": payload.get("release_url") or f"{RELEASES_URL}/tag/{_version_tag(latest_version)}",
        "download_url": str(payload.get("download_url") or "").strip() or None,
        "standard_download_url": str(payload.get("standard_download_url") or "").strip() or None,
    }


def _read_post_update_onboarding(data_dir: Path | None, current_version: str, *, portable: bool) -> dict[str, Any] | None:
    if not portable or not data_dir:
        return None
    current_parts = _parse_semver(current_version)
    transition_parts = _parse_semver(STANDARD_APP_TRANSITION_VERSION)
    if not current_parts or not transition_parts or current_parts < transition_parts:
        return None

    marker_path = data_dir / POST_UPDATE_ONBOARDING_FILENAME
    marker = _read_json_object(marker_path) or {}
    if marker.get("dismissed") is True:
        return None

    to_version = (
        _optional_version(str(marker.get("to_version") or ""))
        or _optional_version(str(marker.get("latest_version") or ""))
        or current_version
    )
    from_version = _optional_version(str(marker.get("from_version") or marker.get("current_version") or ""))
    release_url = str(marker.get("release_url") or "").strip() or f"{RELEASES_URL}/tag/{_version_tag(to_version)}"
    notice: dict[str, Any] = {
        "kind": str(marker.get("kind") or STANDARD_APP_TRANSITION_KIND),
        "notice_id": f"{STANDARD_APP_TRANSITION_KIND}:{_version_tag(to_version)}",
        "to_version": to_version,
        "to_version_label": _version_tag(to_version),
        "updated_at": marker.get("updated_at"),
        "release_url": release_url,
        "standard_download_url": str(marker.get("standard_download_url") or "").strip() or release_url,
        "data_dir": str(data_dir),
    }
    if from_version:
        notice["from_version"] = from_version
        notice["from_version_label"] = _version_tag(from_version)
    return notice


def _updater_script(bundle_dir: Path | None) -> Path | None:
    if not bundle_dir:
        return None
    system = platform.system().lower()
    if system == "darwin":
        candidate = bundle_dir / "Update WebUI Portable.command"
    elif system == "windows":
        candidate = bundle_dir / "Update WebUI Portable.bat"
    else:
        candidate = bundle_dir / "Update WebUI Portable.command"
    return candidate if candidate.exists() else None


def app_version_payload(output_root: Path) -> dict[str, Any]:
    bundle_dir = _portable_bundle_dir()
    app_dir = _standard_app_dir()
    data_dir = _data_dir_from_output_root(output_root)
    source = _runtime_source(bundle_dir, app_dir)
    current_version = _portable_version(bundle_dir) if source == "portable" else _standard_app_version(app_dir)
    notice = _read_update_notice(data_dir, current_version)
    updater = _updater_script(bundle_dir)
    portable = bundle_dir is not None
    onboarding = _read_post_update_onboarding(data_dir, current_version, portable=portable)
    latest_version = notice["latest_version"] if notice else current_version
    return {
        "current_version": current_version,
        "current_version_label": _version_tag(current_version),
        "source": source,
        "portable": portable,
        "standard_app": source == "standard_app",
        "update_available": bool(notice),
        "latest_version": latest_version,
        "latest_version_label": _version_tag(latest_version),
        "checked_at": notice.get("checked_at") if notice else None,
        "release_url": notice.get("release_url") if notice else RELEASES_URL,
        "download_url": notice.get("download_url") if notice else None,
        "standard_download_url": notice.get("standard_download_url") if notice else None,
        "updater_available": updater is not None,
        "updater_label": updater.name if updater else None,
        "post_update_onboarding": onboarding,
        "server_time": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "app_version": APP_VERSION,
        "app_version_label": APP_VERSION_TAG,
    }


def dismiss_post_update_onboarding(output_root: Path) -> dict[str, Any]:
    bundle_dir = _portable_bundle_dir()
    data_dir = _data_dir_from_output_root(output_root)
    if data_dir is None:
        raise FileNotFoundError("Portable data directory is not available")
    current_version = _portable_version(bundle_dir)
    marker_path = data_dir / POST_UPDATE_ONBOARDING_FILENAME
    marker = _read_json_object(marker_path) or {}
    to_version = (
        _optional_version(str(marker.get("to_version") or ""))
        or _optional_version(str(marker.get("latest_version") or ""))
        or current_version
    )
    release_url = str(marker.get("release_url") or "").strip() or f"{RELEASES_URL}/tag/{_version_tag(to_version)}"
    marker.update(
        {
            "kind": str(marker.get("kind") or STANDARD_APP_TRANSITION_KIND),
            "to_version": to_version,
            "to_version_label": _version_tag(to_version),
            "release_url": release_url,
            "dismissed": True,
            "dismissed_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
    )
    data_dir.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return app_version_payload(output_root)


def open_portable_updater(output_root: Path) -> dict[str, Any]:
    bundle_dir = _portable_bundle_dir()
    updater = _updater_script(bundle_dir)
    if not bundle_dir or not updater:
        raise FileNotFoundError("Portable updater script is not available")
    system = platform.system().lower()
    if system == "darwin":
        subprocess.Popen(["open", str(updater)])
    elif system == "windows":
        if hasattr(os, "startfile"):
            os.startfile(str(updater))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["cmd", "/c", "start", "", str(updater)])
    else:
        subprocess.Popen([str(updater)])
    return app_version_payload(output_root) | {"started": True}
