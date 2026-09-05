from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hmac
from pathlib import Path, PurePosixPath
import re
import threading
from collections.abc import Iterator
from urllib.parse import unquote, urlsplit

from .atomic_files import atomic_write_bytes
from .image_uploads import InvalidRasterImage, validate_raster_image
from .storage import TaskStorage
from .task_metadata import (
    _output_record_filename,
    _safe_output_path,
    _visible_completed_output_records,
)


_ASSET_ID_RE = re.compile(r"^[0-9a-f]{64}$")
_TASK_ID_PATTERN = r"\d{14}-[0-9a-f]{8}"
_TASK_INPUT_URL_RE = re.compile(
    rf"^/api/tasks/(?P<task_id>{_TASK_ID_PATTERN})/inputs/(?P<index>[1-9]\d*)/image$",
    re.IGNORECASE,
)
_TASK_OUTPUT_URL_RE = re.compile(
    rf"^/api/tasks/(?P<task_id>{_TASK_ID_PATTERN})/outputs/(?P<index>[1-9]\d*)/image$",
    re.IGNORECASE,
)
_ASSET_URL_RE = re.compile(
    r"^/api/prompt-template-assets/(?P<asset_id>[0-9a-f]{64})/image$"
)
_TASK_INPUT_FILENAME_RE = re.compile(
    rf"^(?P<task_id>{_TASK_ID_PATTERN})-(?:input|mask)-\d+-",
    re.IGNORECASE,
)
_TASK_OUTPUT_FILENAME_RE = re.compile(
    rf"^(?P<task_id>{_TASK_ID_PATTERN})-image-\d+\.[a-z0-9]+$",
    re.IGNORECASE,
)
_CANONICAL_SUFFIXES = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


@dataclass(frozen=True)
class PromptTemplateAsset:
    asset_id: str
    path: Path
    mime_type: str
    size_bytes: int
    sha256: str


class PromptTemplateAssetStorage:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self._lock = threading.RLock()

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        with self._lock:
            yield

    def store(self, data: bytes, *, filename: str) -> PromptTemplateAsset:
        validated = validate_raster_image(data, filename=filename)
        asset_id = validated.sha256
        suffix = _CANONICAL_SUFFIXES[validated.mime_type]
        path = self.root / f"{asset_id}{suffix}"
        with self._lock:
            existing = self.resolve(asset_id)
            if existing is not None:
                existing.path.chmod(0o600)
                return existing
            atomic_write_bytes(path, validated.data, mode=0o600)
            asset = self.resolve(asset_id)
            if asset is None:
                raise OSError("prompt_template_asset_write_failed")
            return asset

    def resolve(self, asset_id: str) -> PromptTemplateAsset | None:
        normalized_id = str(asset_id or "")
        if _ASSET_ID_RE.fullmatch(normalized_id) is None:
            return None
        with self._lock:
            for mime_type, suffix in _CANONICAL_SUFFIXES.items():
                path = self.root / f"{normalized_id}{suffix}"
                if path.is_symlink():
                    continue
                try:
                    resolved = path.resolve(strict=True)
                    resolved.relative_to(self.root.resolve(strict=True))
                    if not resolved.is_file():
                        continue
                    data = resolved.read_bytes()
                    validated = validate_raster_image(data, filename=resolved.name)
                except (FileNotFoundError, InvalidRasterImage, OSError, ValueError):
                    continue
                if validated.mime_type != mime_type:
                    continue
                if not hmac.compare_digest(validated.sha256, normalized_id):
                    continue
                return PromptTemplateAsset(
                    asset_id=normalized_id,
                    path=path,
                    mime_type=validated.mime_type,
                    size_bytes=len(data),
                    sha256=validated.sha256,
                )
        return None

    def list_managed(self) -> tuple[PromptTemplateAsset, ...]:
        if not self.root.is_dir():
            return ()
        asset_ids = {
            path.stem
            for path in self.root.iterdir()
            if path.suffix.lower() in _CANONICAL_SUFFIXES.values()
            and _ASSET_ID_RE.fullmatch(path.stem) is not None
        }
        with self._lock:
            assets = [
                asset
                for asset_id in sorted(asset_ids)
                if (asset := self.resolve(asset_id)) is not None
            ]
        return tuple(assets)


class PromptTemplateThumbnailResolver:
    def __init__(
        self,
        task_storage: TaskStorage,
        asset_storage: PromptTemplateAssetStorage,
    ) -> None:
        self.task_storage = task_storage
        self.asset_storage = asset_storage

    def resolve(self, url: str) -> Path | None:
        raw = str(url or "").strip()
        if not raw or "\\" in raw:
            return None
        parsed = urlsplit(raw)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            return None
        try:
            path = unquote(parsed.path, errors="strict")
        except (UnicodeDecodeError, ValueError):
            return None
        if not path.startswith("/") or any(ord(character) < 32 for character in path):
            return None

        asset_match = _ASSET_URL_RE.fullmatch(path)
        if asset_match is not None:
            asset = self.asset_storage.resolve(asset_match.group("asset_id"))
            return asset.path if asset is not None else None

        input_match = _TASK_INPUT_URL_RE.fullmatch(path)
        if input_match is not None:
            return self._task_input_path(
                input_match.group("task_id"),
                int(input_match.group("index")),
            )

        output_match = _TASK_OUTPUT_URL_RE.fullmatch(path)
        if output_match is not None:
            return self._task_output_path(
                output_match.group("task_id"),
                int(output_match.group("index")),
            )

        if path.startswith("/inputs/"):
            return self._legacy_input_path(path.removeprefix("/inputs/"))
        if path.startswith("/outputs/"):
            return self._legacy_output_path(path.removeprefix("/outputs/"))
        return None

    def _read_metadata(self, task_id: str) -> dict[str, object] | None:
        try:
            return self.task_storage.read_metadata(task_id)
        except (FileNotFoundError, OSError, ValueError):
            return None

    def _task_input_path(self, task_id: str, input_index: int) -> Path | None:
        metadata = self._read_metadata(task_id)
        if metadata is None:
            return None
        input_files = metadata.get("input_files")
        if not isinstance(input_files, list) or input_index > len(input_files):
            return None
        filename = str(input_files[input_index - 1] or "")
        if not filename or Path(filename).name != filename:
            return None
        return _contained_file(
            self.task_storage.input_path(filename),
            self.task_storage.input_root,
        )

    def _task_output_path(self, task_id: str, output_index: int) -> Path | None:
        metadata = self._read_metadata(task_id)
        if metadata is None:
            return None
        deleted_indexes, _ = _explicitly_deleted_outputs(metadata)
        if output_index in deleted_indexes:
            return None
        record = next(
            (
                item
                for item in _visible_completed_output_records(metadata)
                if item.get("index") == output_index
            ),
            None,
        )
        if record is None:
            return None
        path = _safe_output_path(
            self.task_storage,
            task_id,
            _output_record_filename(record),
        )
        if path is None:
            return None
        return _contained_file(path, self.task_storage.output_root)

    def _legacy_input_path(self, filename: str) -> Path | None:
        if not filename or Path(filename).name != filename:
            return None
        match = _TASK_INPUT_FILENAME_RE.match(filename)
        if match is None:
            return None
        task_id = match.group("task_id")
        metadata = self._read_metadata(task_id)
        if metadata is None:
            return None
        input_files = metadata.get("input_files")
        allowed_names = {
            str(item)
            for item in input_files
            if isinstance(input_files, list) and item
        }
        mask_file = str(metadata.get("mask_file") or "")
        if mask_file:
            allowed_names.add(mask_file)
        if filename not in allowed_names:
            return None
        return _contained_file(
            self.task_storage.input_path(filename),
            self.task_storage.input_root,
        )

    def _legacy_output_path(self, filename: str) -> Path | None:
        normalized = _normalized_output_filename(filename)
        if normalized is None:
            return None
        basename = PurePosixPath(normalized).name
        match = _TASK_OUTPUT_FILENAME_RE.fullmatch(basename)
        if match is None:
            return None
        task_id = match.group("task_id")
        metadata = self._read_metadata(task_id)
        if metadata is None:
            return None
        _, deleted_files = _explicitly_deleted_outputs(metadata)
        if normalized in deleted_files:
            return None
        for record in _visible_completed_output_records(metadata):
            path = _safe_output_path(
                self.task_storage,
                task_id,
                _output_record_filename(record),
            )
            contained = (
                _contained_file(path, self.task_storage.output_root)
                if path is not None
                else None
            )
            if (
                contained is not None
                and self.task_storage.output_file(contained) == normalized
            ):
                return contained
        return None


def _contained_file(path: Path, root: Path) -> Path | None:
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (FileNotFoundError, OSError, ValueError):
        return None
    return path if resolved.is_file() else None


def _normalized_output_filename(filename: str) -> str | None:
    raw = str(filename or "").strip()
    candidate = PurePosixPath(raw)
    if (
        not raw
        or candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        return None
    return candidate.as_posix()


def _explicitly_deleted_outputs(
    metadata: dict[str, object],
) -> tuple[set[int], set[str]]:
    deleted_indexes = {
        value
        for raw in metadata.get("deleted_output_indexes", [])
        if isinstance(metadata.get("deleted_output_indexes"), list)
        and isinstance(raw, int)
        and not isinstance(raw, bool)
        and (value := raw) > 0
    }
    deleted_files: set[str] = set()
    outputs = metadata.get("outputs")
    if not isinstance(outputs, list):
        return deleted_indexes, deleted_files
    for fallback_index, record in enumerate(outputs, start=1):
        if not isinstance(record, dict):
            continue
        index_value = record.get("index")
        index = (
            index_value
            if isinstance(index_value, int)
            and not isinstance(index_value, bool)
            and index_value > 0
            else fallback_index
        )
        if not record.get("deleted") and record.get("status") != "deleted":
            continue
        deleted_indexes.add(index)
        filename = _output_record_filename(record)
        normalized = _normalized_output_filename(filename)
        if normalized is not None:
            deleted_files.add(normalized)
    return deleted_indexes, deleted_files


__all__ = (
    "PromptTemplateAsset",
    "PromptTemplateAssetStorage",
    "PromptTemplateThumbnailResolver",
)
