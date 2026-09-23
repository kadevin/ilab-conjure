from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .schemas import DEFAULT_WEBUI_INPUT_ROOT, DEFAULT_WEBUI_REFERENCE_ASSET_SUBDIR
from .storage_utils import _guess_mime_type, _safe_filename, utc_now
from .atomic_files import _fsync_parent, atomic_write_bytes, atomic_write_text
from .thumbnails import create_sidebar_thumbnail

REFERENCE_ASSET_SUFFIXES = {".png", ".jpg", ".webp", ".gif"}
MAX_REFERENCE_ASSETS = 50


@dataclass(frozen=True)
class ReferenceAssetRestore:
    record: dict[str, Any]
    created: bool
    version: int
    restore_token: str | None = None


class ReferenceAssetInUseError(RuntimeError):
    def __init__(self, asset_id: str, reference_count: int) -> None:
        self.asset_id = asset_id
        self.reference_count = max(1, int(reference_count))
        super().__init__("Reference asset is used by existing tasks")


class ReferenceAssetProtectionUnavailableError(RuntimeError):
    pass


class ReferenceAssetStorage:
    def __init__(
        self,
        root: Path | str = DEFAULT_WEBUI_INPUT_ROOT / DEFAULT_WEBUI_REFERENCE_ASSET_SUBDIR,
        *,
        max_items: int = MAX_REFERENCE_ASSETS,
        reference_counts_provider: Callable[[], Mapping[str, int]] | None = None,
    ) -> None:
        self.root = Path(root)
        self.max_items = max(1, int(max_items))
        self._reference_counts_provider = reference_counts_provider
        self._lock = threading.RLock()
        self._restore_versions: dict[str, int] = {}

    def create_or_touch(
        self,
        filename: str,
        data: bytes,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        asset_id = hashlib.sha256(data).hexdigest()
        with self._lock:
            self._invalidate_restore_ownership(asset_id)
            self._restore_versions[asset_id] = self._restore_versions.get(asset_id, 0) + 1
            existing = self._read_valid_item(asset_id)
            if existing is not None:
                touched = self._touch_metadata(existing, restore_to_recent=True)
                self._prune_to_limit(preserve_ids={asset_id})
                return touched

            suffix = _reference_asset_suffix(filename, content_type)
            stored_filename = f"{asset_id}{suffix}"
            shard_path = self._shard_path(asset_id)
            image_path = shard_path / stored_filename
            now = utc_now()
            metadata = {
                "id": asset_id,
                "sha256": asset_id,
                "filename": _safe_filename(filename),
                "stored_filename": stored_filename,
                "mime_type": content_type or _guess_mime_type(stored_filename),
                "size_bytes": len(data),
                "created_at": now,
                "last_used_at": now,
                "used_count": 1,
            }
            shard_path.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(data)
            self._write_item_metadata(asset_id, metadata)
            self._prune_to_limit(preserve_ids={asset_id})
            return metadata

    def restore_content(
        self,
        filename: str,
        data: bytes,
        content_type: str | None = None,
    ) -> ReferenceAssetRestore:
        asset_id = hashlib.sha256(data).hexdigest()
        with self._lock:
            version = self._restore_versions.get(asset_id, 0) + 1
            self._restore_versions[asset_id] = version
            existing = self._read_valid_item(asset_id)
            if existing is not None:
                path = self._stored_image_path(asset_id, existing)
                if path is None or path.stat().st_size != len(data) or _sha256_file(path) != asset_id:
                    raise ValueError("reference_asset_invalid")
                self._invalidate_restore_ownership(asset_id)
                return ReferenceAssetRestore(dict(existing), False, version, None)
            suffix = _reference_asset_suffix(filename, content_type)
            stored_filename = f"{asset_id}{suffix}"
            shard = self._shard_path(asset_id)
            image_path = shard / stored_filename
            metadata_path = self._metadata_path(asset_id)
            now = utc_now()
            record = {
                "id": asset_id,
                "sha256": asset_id,
                "filename": _safe_filename(filename),
                "stored_filename": stored_filename,
                "mime_type": content_type or _guess_mime_type(stored_filename),
                "size_bytes": len(data),
                "created_at": now,
                "last_used_at": now,
                "used_count": 1,
            }
            if image_path.exists() or metadata_path.exists():
                raise ValueError("reference_asset_invalid")
            try:
                atomic_write_bytes(image_path, data, mode=0o600)
                atomic_write_text(metadata_path, json.dumps(record, indent=2, ensure_ascii=False), mode=0o600)
                restore_token = uuid.uuid4().hex
                atomic_write_text(self._restore_token_path(asset_id), restore_token, mode=0o600)
            except Exception:
                image_path.unlink(missing_ok=True)
                metadata_path.unlink(missing_ok=True)
                try:
                    shard.rmdir()
                except OSError:
                    pass
                raise
            return ReferenceAssetRestore(record, True, version, restore_token)

    def rollback_restore(self, handle: ReferenceAssetRestore) -> bool:
        if not isinstance(handle, ReferenceAssetRestore) or not handle.created:
            return False
        asset_id = str(handle.record.get("id") or "")
        with self._lock:
            if not self.restore_identity_matches(handle):
                return False
            try:
                metadata = self.read_item(asset_id)
            except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
                return False
            if metadata.get("sha256") != asset_id:
                return False
            self._delete_item_files(asset_id, metadata)
            self._restore_versions.pop(asset_id, None)
            return True

    def restore_identity_matches(self, handle: ReferenceAssetRestore) -> bool:
        if not isinstance(handle, ReferenceAssetRestore) or not handle.created or not handle.restore_token:
            return False
        asset_id = str(handle.record.get("id") or "")
        try:
            return self._restore_token_path(asset_id).read_text(encoding="utf-8") == handle.restore_token
        except OSError:
            return False

    def restore_target_exists(self, handle: ReferenceAssetRestore) -> bool:
        asset_id = str(handle.record.get("id") or "")
        try:
            self._validate_asset_id(asset_id)
        except ValueError:
            return True
        stored_filename = str(handle.record.get("stored_filename") or "")
        return any((
            self._metadata_path(asset_id).exists(),
            self._restore_token_path(asset_id).exists(),
            bool(stored_filename) and (self._shard_path(asset_id) / stored_filename).exists(),
        ))

    def release_restore_ownership(self, handle: ReferenceAssetRestore) -> bool:
        if not isinstance(handle, ReferenceAssetRestore) or not handle.created or not handle.restore_token:
            return True
        with self._lock:
            path = self._restore_token_path(str(handle.record.get("id") or ""))
            try:
                current = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                return True
            except OSError:
                return False
            if current != handle.restore_token:
                return True
            try:
                path.unlink()
                _fsync_parent(path)
            except OSError:
                return False
            return True

    def _invalidate_restore_ownership(self, asset_id: str) -> None:
        path = self._restore_token_path(asset_id)
        try:
            path.unlink()
        except FileNotFoundError:
            return
        _fsync_parent(path)

    def touch(self, asset_id: str) -> dict[str, Any]:
        with self._lock:
            self._invalidate_restore_ownership(asset_id)
            touched = self._touch_metadata(self.read_item(asset_id))
            self._prune_to_limit(preserve_ids={asset_id})
            return touched

    def list_recent(
        self,
        limit: int = 20,
        *,
        include_hidden: bool = False,
    ) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        items: list[dict[str, Any]] = []
        for metadata_path in self.root.glob("*/*.json"):
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(metadata, dict):
                continue
            asset_id = str(metadata.get("id") or "")
            try:
                self._validate_asset_id(asset_id)
            except ValueError:
                continue
            if metadata.get("sha256") != asset_id:
                continue
            if self._stored_image_path(asset_id, metadata) is None:
                continue
            if metadata.get("hidden_from_recent_at") and not include_hidden:
                continue
            items.append(metadata)
        return sorted(items, key=lambda item: str(item.get("last_used_at", "")), reverse=True)[: max(0, limit)]

    def read_item(self, asset_id: str) -> dict[str, Any]:
        self._validate_asset_id(asset_id)
        return json.loads(self._metadata_path(asset_id).read_text(encoding="utf-8"))

    def delete_item(self, asset_id: str) -> None:
        self._validate_asset_id(asset_id)
        with self._lock:
            metadata = self.read_item(asset_id)
            try:
                reference_count = self._reference_counts().get(asset_id, 0)
            except Exception as exc:
                raise ReferenceAssetProtectionUnavailableError(
                    "Reference asset protection could not be checked"
                ) from exc
            if reference_count > 0:
                raise ReferenceAssetInUseError(asset_id, reference_count)
            self._delete_item_files(asset_id, metadata)

    def hide_item(self, asset_id: str) -> dict[str, Any]:
        self._validate_asset_id(asset_id)
        with self._lock:
            metadata = dict(self.read_item(asset_id))
            metadata["hidden_from_recent_at"] = utc_now()
            self._write_item_metadata(asset_id, metadata)
            return metadata

    def reference_counts(self) -> dict[str, int]:
        with self._lock:
            return self._reference_counts()

    def image_path(self, asset_id: str) -> Path:
        metadata = self.read_item(asset_id)
        path = self._stored_image_path(asset_id, metadata)
        if path is None:
            raise FileNotFoundError(asset_id)
        return path

    def thumbnail_path(self, asset_id: str) -> Path:
        with self._lock:
            source = self.image_path(asset_id)
            thumbnail = self._shard_path(asset_id) / f"{asset_id}-recent.webp"
            if thumbnail.is_file():
                return thumbnail
            temporary = thumbnail.with_name(f".{asset_id}-{uuid.uuid4().hex}-recent.webp")
            try:
                if create_sidebar_thumbnail(source, temporary) is None:
                    raise ValueError("Reference asset thumbnail unavailable")
                temporary.replace(thumbnail)
            finally:
                temporary.unlink(missing_ok=True)
            return thumbnail

    def _touch_metadata(
        self,
        metadata: dict[str, Any],
        *,
        restore_to_recent: bool = False,
    ) -> dict[str, Any]:
        asset_id = str(metadata.get("id") or "")
        self._validate_asset_id(asset_id)
        metadata = dict(metadata)
        if restore_to_recent:
            metadata.pop("hidden_from_recent_at", None)
        metadata["last_used_at"] = utc_now()
        try:
            used_count = int(metadata.get("used_count", 0))
        except (TypeError, ValueError):
            used_count = 0
        metadata["used_count"] = used_count + 1
        self._write_item_metadata(asset_id, metadata)
        return metadata

    def _read_valid_item(self, asset_id: str) -> dict[str, Any] | None:
        try:
            metadata = self.read_item(asset_id)
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
            return None
        if not isinstance(metadata, dict):
            return None
        if metadata.get("id") != asset_id or metadata.get("sha256") != asset_id:
            return None
        if self._stored_image_path(asset_id, metadata) is None:
            return None
        return metadata

    def _prune_to_limit(self, *, preserve_ids: set[str] | None = None) -> None:
        items = self.list_recent(limit=10_000, include_hidden=True)
        excess = len(items) - self.max_items
        if excess <= 0:
            return
        try:
            reference_counts = self._reference_counts()
        except Exception:
            # Failing closed may temporarily exceed the cache limit, but it
            # cannot delete an asset whose task references could not be read.
            return
        preserved = preserve_ids or set()
        for metadata in sorted(
            items,
            key=lambda item: (str(item.get("last_used_at", "")), str(item.get("id", ""))),
        ):
            if excess <= 0:
                break
            asset_id = str(metadata.get("id") or "")
            if asset_id in preserved or reference_counts.get(asset_id, 0) > 0:
                continue
            try:
                self._delete_item_files(asset_id, metadata)
            except (OSError, ValueError):
                continue
            excess -= 1

    def _reference_counts(self) -> dict[str, int]:
        if self._reference_counts_provider is None:
            return {}
        raw_counts = self._reference_counts_provider()
        counts: dict[str, int] = {}
        for raw_asset_id, raw_count in raw_counts.items():
            asset_id = str(raw_asset_id or "")
            if not re.fullmatch(r"[0-9a-f]{64}", asset_id):
                continue
            try:
                count = int(raw_count)
            except (TypeError, ValueError):
                continue
            if count > 0:
                counts[asset_id] = count
        return counts

    def _delete_item_files(self, asset_id: str, metadata: dict[str, Any]) -> None:
        self._validate_asset_id(asset_id)
        image_path = self._stored_image_path(asset_id, metadata)
        metadata_path = self._metadata_path(asset_id)
        if image_path is not None:
            image_path.unlink(missing_ok=True)
        (self._shard_path(asset_id) / f"{asset_id}-recent.webp").unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        self._restore_token_path(asset_id).unlink(missing_ok=True)
        shard_path = self._shard_path(asset_id)
        try:
            next(shard_path.iterdir())
        except StopIteration:
            shard_path.rmdir()
        except FileNotFoundError:
            pass

    def _restore_token_path(self, asset_id: str) -> Path:
        return self._shard_path(asset_id) / f".{asset_id}.restore-owner"

    def _stored_image_path(self, asset_id: str, metadata: Any) -> Path | None:
        if not isinstance(metadata, dict):
            return None
        stored_filename = metadata.get("stored_filename")
        if not isinstance(stored_filename, str):
            return None
        if "/" in stored_filename or "\\" in stored_filename:
            return None
        suffix = Path(stored_filename).suffix.lower()
        if suffix not in REFERENCE_ASSET_SUFFIXES:
            return None
        if stored_filename != f"{asset_id}{suffix}":
            return None
        path = self._shard_path(asset_id) / stored_filename
        if not path.is_file():
            return None
        return path

    def _write_item_metadata(self, asset_id: str, metadata: dict[str, Any]) -> Path:
        path = self._metadata_path(asset_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def _metadata_path(self, asset_id: str) -> Path:
        self._validate_asset_id(asset_id)
        return self._shard_path(asset_id) / f"{asset_id}.json"

    def _shard_path(self, asset_id: str) -> Path:
        self._validate_asset_id(asset_id)
        return self.root / asset_id[:2]

    @staticmethod
    def _validate_asset_id(asset_id: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", asset_id or ""):
            raise ValueError("Invalid reference asset id")


def _reference_asset_suffix(filename: str, content_type: str | None = None) -> str:
    suffix = Path(_safe_filename(filename)).suffix.lower()
    if suffix == ".jpeg":
        return ".jpg"
    if suffix in REFERENCE_ASSET_SUFFIXES:
        return suffix

    guessed = mimetypes.guess_extension(content_type or "")
    guessed = (guessed or "").lower()
    if guessed in {".jpe", ".jpeg"}:
        return ".jpg"
    if guessed in REFERENCE_ASSET_SUFFIXES:
        return guessed
    return ".png"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
