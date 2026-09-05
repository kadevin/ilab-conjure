"""Storage paths for standard packages and their copied portable data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .atomic_files import atomic_write_text
from .settings_store import _settings_path, _validate_webui_paths


def standard_storage_defaults(data_dir: Path) -> dict[str, Path]:
    return {
        "input_root": data_dir / "webui-inputs",
        "output_root": data_dir / "webui-outputs",
        "gallery_root": data_dir / "webui-inputs/gallery",
        "source_data_root": data_dir / "webui-outputs/source-data",
    }


def previous_default_storage_paths(
    settings_path: Path, current: dict[str, Path]
) -> dict[str, str]:
    """Locate retained default directories without inspecting or moving their files."""
    previous = {}
    for key, path in standard_storage_defaults(settings_path.parent).items():
        try:
            if path.is_dir() and path.resolve() != current[key].resolve():
                previous[key] = str(path)
        except (OSError, RuntimeError):
            # This optional hint must not block settings when an old disk is offline.
            continue
    return previous


def load_standard_storage_paths(data_dir: Path) -> dict[str, Path]:
    settings_path = data_dir / "webui-settings.json"
    try:
        original = settings_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        original = "{}"
    saved = json.loads(original)
    if not isinstance(saved, dict):
        raise ValueError("WebUI settings must be a JSON object")
    defaults = standard_storage_defaults(data_dir)
    input_root = _settings_path(saved.get("input_root"), defaults["input_root"])
    output_root = _settings_path(saved.get("output_root"), defaults["output_root"])
    paths = {
        "input_root": input_root,
        "output_root": output_root,
        "gallery_root": _settings_path(saved.get("gallery_root"), input_root / "gallery"),
        "source_data_root": _settings_path(saved.get("source_data_root"), output_root / "source-data"),
    }
    _validate_webui_paths(paths)

    marker_path = data_dir / ".migration/portable-data-copied-v1.json"
    marker = _portable_copy_record(marker_path)
    if marker is None or marker.get("storage_paths_rebased") is True:
        return paths
    source = Path(marker["source"]).expanduser().resolve()
    target = data_dir.resolve()
    # A copy record must describe two separate data trees.
    if source.is_relative_to(target) or target.is_relative_to(source):
        return paths
    rebased = dict(paths)
    for key, path in paths.items():
        if not path.is_absolute():
            continue
        try:
            relative = path.resolve().relative_to(source)
        except ValueError:
            continue
        rebased[key] = target / relative
    _validate_webui_paths(rebased)
    if rebased != paths:
        # Preserve an exact recovery copy before changing only the target config.
        backup = marker_path.parent / "webui-settings-before-path-rebase.json"
        if not backup.exists():
            atomic_write_text(backup, original, mode=0o600)
        saved.update({key: str(path) for key, path in rebased.items()})
        atomic_write_text(settings_path, json.dumps(saved, indent=2, ensure_ascii=False), mode=0o600)
    # Complete this once, including when all paths were already external/current.
    # Subsequent explicit choices, even paths back into the portable tree, win.
    marker["storage_paths_rebased"] = True
    atomic_write_text(marker_path, json.dumps(marker, indent=2, ensure_ascii=False), mode=0o600)
    return rebased


def _portable_copy_record(path: Path) -> dict[str, Any] | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict):
        return None
    source = record.get("source")
    if (
        record.get("schema_version") != 1
        or record.get("mode") != "copy"
        or not isinstance(source, str)
        or not source.strip()
        or not Path(source).expanduser().is_absolute()
    ):
        return None
    return record
