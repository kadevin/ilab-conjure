from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .schemas import DEFAULT_WEBUI_GALLERY_ROOT
from .storage_utils import _guess_mime_type, _safe_filename, utc_now
from .atomic_files import _fsync_parent, atomic_write_bytes, atomic_write_text
from .image_uploads import InvalidRasterImage, validate_raster_image
from .store_locks import StoreLockMixin


DEFAULT_GALLERY_CATEGORIES = [
    {"id": "portrait", "name": "人像", "prompt_role": "人像参考", "order": 10, "locked": False},
    {"id": "character", "name": "角色", "prompt_role": "角色参考", "order": 20, "locked": False},
    {"id": "product", "name": "产品", "prompt_role": "产品参考", "order": 30, "locked": False},
]
GALLERY_CATEGORIES = {category["id"] for category in DEFAULT_GALLERY_CATEGORIES}
_GALLERY_DERIVED_ITEM_FIELDS = frozenset({"category_name", "category_prompt_role"})


@dataclass(frozen=True)
class GalleryRestore:
    record: dict[str, Any]
    created: bool
    version: int
    restore_token: str | None = None


@dataclass(frozen=True)
class GallerySnapshotItem:
    metadata: dict[str, Any]
    image_path: Path
    mime_type: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class GallerySnapshot:
    categories: tuple[dict[str, Any], ...]
    items: tuple[GallerySnapshotItem, ...]


class GalleryStorage(StoreLockMixin):
    def __init__(self, root: Path | str = DEFAULT_WEBUI_GALLERY_ROOT) -> None:
        self.root = Path(root)
        self._lock = threading.RLock()
        self._restore_versions: dict[str, int] = {}

    def snapshot(self) -> GallerySnapshot:
        with self._lock:
            categories = tuple(dict(item) for item in self.list_categories())
            items: list[GallerySnapshotItem] = []
            for item in self.list_items():
                metadata = {
                    key: value
                    for key, value in item.items()
                    if key not in _GALLERY_DERIVED_ITEM_FIELDS
                }
                item_id = _clean_gallery_item_id(metadata.get("id"))
                image_path = self.image_path(item_id)
                try:
                    image_path.resolve(strict=True).relative_to(
                        self.root.resolve(strict=True)
                    )
                except (FileNotFoundError, OSError, ValueError) as exc:
                    raise ValueError("Gallery snapshot image is not owned") from exc
                asset = _validated_gallery_snapshot_asset(metadata, image_path)
                items.append(asset)
            return GallerySnapshot(categories=categories, items=tuple(items))

    def managed_paths(self) -> tuple[Path, ...]:
        with self._lock:
            paths: list[Path] = []
            categories_path = self._categories_path()
            if categories_path.is_file() and not categories_path.is_symlink():
                paths.append(categories_path)
            for item in self.snapshot().items:
                metadata_path = self._item_path(
                    str(item.metadata["id"])
                ) / "metadata.json"
                paths.extend((metadata_path, item.image_path))
            return tuple(dict.fromkeys(paths))

    def write_snapshot(self, snapshot: GallerySnapshot) -> None:
        if not isinstance(snapshot, GallerySnapshot):
            raise ValueError("Invalid gallery snapshot")
        with self._lock:
            categories = [_normalize_gallery_category(dict(item)) for item in snapshot.categories]
            category_ids = [str(item["id"]) for item in categories]
            if not categories or len(category_ids) != len(set(category_ids)):
                raise ValueError("Invalid gallery snapshot categories")
            prepared: list[tuple[dict[str, Any], bytes]] = []
            item_ids: set[str] = set()
            for item in snapshot.items:
                if not isinstance(item, GallerySnapshotItem):
                    raise ValueError("Invalid gallery snapshot item")
                metadata = dict(item.metadata)
                item_id = _clean_gallery_item_id(metadata.get("id"))
                if (
                    re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", item_id)
                    is None
                    or item_id in item_ids
                ):
                    raise ValueError("Invalid gallery snapshot item id")
                item_ids.add(item_id)
                if str(metadata.get("category") or "") not in category_ids:
                    raise ValueError("Gallery snapshot category reference is invalid")
                filename = str(metadata.get("filename") or "")
                if not filename or _safe_filename(filename) != filename:
                    raise ValueError("Gallery snapshot filename is invalid")
                try:
                    data = item.image_path.read_bytes()
                except OSError as exc:
                    raise ValueError("Gallery snapshot image is invalid") from exc
                validated = _validated_gallery_snapshot_asset(
                    metadata,
                    item.image_path,
                    data=data,
                )
                if (
                    item.sha256 != validated.sha256
                    or item.size_bytes != validated.size_bytes
                    or item.mime_type != validated.mime_type
                ):
                    raise ValueError("Gallery snapshot image digest or identity mismatch")
                clean_metadata = {
                    key: value
                    for key, value in metadata.items()
                    if key not in _GALLERY_DERIVED_ITEM_FIELDS
                }
                clean_metadata["id"] = item_id
                clean_metadata["name"] = _clean_gallery_name(metadata.get("name"))
                clean_metadata["name_key"] = _gallery_name_key(clean_metadata["name"])
                clean_metadata["category"] = str(metadata["category"])
                clean_metadata["filename"] = filename
                clean_metadata["mime_type"] = validated.mime_type
                clean_metadata["size_bytes"] = validated.size_bytes
                clean_metadata["sha256"] = validated.sha256
                clean_metadata["prompt_note"] = _clean_gallery_prompt_note(
                    metadata.get("prompt_note")
                )
                clean_metadata["order"] = _clean_gallery_item_order(
                    metadata.get("order"),
                    fallback=0,
                )
                prepared.append((clean_metadata, data))

            self._write_categories(categories)
            for metadata, data in prepared:
                item_path = self._item_path(str(metadata["id"]))
                atomic_write_bytes(
                    item_path / str(metadata["filename"]),
                    data,
                    mode=0o600,
                )
                self._write_item_metadata(str(metadata["id"]), metadata)
                self._bump_restore_version(str(metadata["id"]))

    def list_categories(self) -> list[dict[str, Any]]:
        categories = self._read_categories()
        return sorted(categories, key=lambda category: (int(category.get("order", 0)), str(category.get("name", ""))))

    def create_category(self, name: str, *, prompt_role: str | None = None, order: int | None = None) -> dict[str, Any]:
        with self._lock:
            categories = self._read_categories()
            clean_name = _clean_gallery_category_name(name)
            category_id = self._new_category_id(categories)
            now = utc_now()
            next_order = order if order is not None else (max([int(category.get("order", 0)) for category in categories] or [0]) + 10)
            category = {
                "id": category_id,
                "name": clean_name,
                "prompt_role": _clean_gallery_prompt_role(prompt_role, fallback=clean_name),
                "order": int(next_order),
                "locked": False,
                "created_at": now,
                "updated_at": now,
            }
            categories.append(category)
            self._write_categories(categories)
            return category

    def reorder_categories(self, category_ids: list[str]) -> list[dict[str, Any]]:
        with self._lock:
            categories = self._read_categories()
            current_ids = [str(category.get("id") or "") for category in self.list_categories()]
            reordered_ids = _clean_reorder_ids(category_ids, current_ids, clean_id=_clean_gallery_category_id, label="Gallery category")
            categories_by_id = {str(category.get("id") or ""): dict(category) for category in categories}
            updated: list[dict[str, Any]] = []
            now = utc_now()
            for index, category_id in enumerate(reordered_ids, start=1):
                category = categories_by_id[category_id]
                category["order"] = index * 10
                category["updated_at"] = now
                updated.append(category)
            self._write_categories(updated)
            return self.list_categories()

    def update_category(
        self,
        category_id: str,
        *,
        name: str | None = None,
        prompt_role: str | None = None,
        order: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            clean_id = _clean_gallery_category_id(category_id)
            categories = self._read_categories()
            for category in categories:
                if category["id"] != clean_id:
                    continue
                if name is not None:
                    category["name"] = _clean_gallery_category_name(name)
                if prompt_role is not None:
                    category["prompt_role"] = _clean_gallery_prompt_role(prompt_role, fallback=str(category.get("name") or "参考图"))
                if order is not None:
                    category["order"] = int(order)
                category["updated_at"] = utc_now()
                self._write_categories(categories)
                return dict(category)
            raise FileNotFoundError(category_id)

    def delete_category(self, category_id: str, *, move_to: str | None = None) -> None:
        with self._lock:
            clean_id = _clean_gallery_category_id(category_id)
            categories = self._read_categories()
            if not any(category["id"] == clean_id for category in categories):
                raise FileNotFoundError(category_id)
            target_id = _clean_gallery_category_id(move_to) if move_to is not None else None
            if target_id == clean_id:
                raise ValueError("Move target must be different from deleted category")
            if target_id is not None and not any(category["id"] == target_id for category in categories):
                raise ValueError("Move target category does not exist")

            items = [item for item in self.list_items() if item.get("category") == clean_id]
            if items and target_id is None:
                raise ValueError("Category is not empty")
            if len(categories) <= 1:
                raise ValueError("At least one gallery category is required")

            if target_id is not None:
                for item in items:
                    self.update_item(str(item["id"]), category=target_id)
            self._write_categories([category for category in categories if category["id"] != clean_id])

    def create_item(
        self,
        name: str,
        category: str,
        filename: str,
        data: bytes,
        content_type: str | None = None,
        prompt_note: str | None = None,
        order: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            record = self._create_item_unlocked(
                name, category, filename, data, content_type, prompt_note, order
            )
            self._bump_restore_version(str(record["id"]))
            return record

    def _create_item_unlocked(
        self,
        name: str,
        category: str,
        filename: str,
        data: bytes,
        content_type: str | None = None,
        prompt_note: str | None = None,
        order: int | None = None,
    ) -> dict[str, Any]:
        clean_name = _clean_gallery_name(name)
        clean_category = self._clean_category(category)
        self._ensure_unique_name(clean_name)
        item_id = datetime.now(UTC).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
        item_path = self._item_path(item_id)
        item_path.mkdir(parents=True, exist_ok=False)
        safe_name = _safe_filename(filename)
        image_path = item_path / safe_name
        try:
            atomic_write_bytes(image_path, data, mode=0o600)
            now = utc_now()
            metadata = {
                "id": item_id,
                "name": clean_name,
                "name_key": _gallery_name_key(clean_name),
                "category": clean_category,
                "filename": safe_name,
                "mime_type": content_type or _guess_mime_type(safe_name),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
                "prompt_note": _clean_gallery_prompt_note(prompt_note),
                "order": _clean_gallery_item_order(order, fallback=self._next_item_order(clean_category)),
                "created_at": now,
                "updated_at": now,
            }
            self._write_item_metadata(item_id, metadata)
            return self._normalize_item_metadata(metadata)
        except Exception:
            for path in list(item_path.iterdir()):
                if path.is_file():
                    path.unlink(missing_ok=True)
            try:
                item_path.rmdir()
            except OSError:
                pass
            raise

    def restore_content(
        self,
        name: str,
        category: str,
        filename: str,
        data: bytes,
        content_type: str | None = None,
    ) -> GalleryRestore:
        digest = hashlib.sha256(data).hexdigest()
        with self._lock:
            for item in self.list_items():
                if str(item.get("sha256") or "") != digest:
                    continue
                try:
                    path = self.image_path(str(item.get("id") or ""))
                except (FileNotFoundError, OSError, ValueError):
                    continue
                if path.stat().st_size == len(data) and _sha256_file(path) == digest:
                    item_id = str(item["id"])
                    version = self._restore_versions.get(item_id, 0) + 1
                    self._restore_versions[item_id] = version
                    self._invalidate_restore_ownership(item_id)
                    return GalleryRestore(dict(item), False, version, None)
            clean_name = _unique_restore_name(self, name)
            try:
                record = self._create_item_unlocked(clean_name, category, filename, data, content_type)
            except ValueError:
                record = self._create_item_unlocked(clean_name, "portrait", filename, data, content_type)
            item_id = str(record["id"])
            version = self._restore_versions.get(item_id, 0) + 1
            self._restore_versions[item_id] = version
            restore_token = uuid.uuid4().hex
            atomic_write_text(self._restore_token_path(item_id), restore_token, mode=0o600)
            return GalleryRestore(record, True, version, restore_token)

    def rollback_restore(self, handle: GalleryRestore) -> bool:
        if not isinstance(handle, GalleryRestore) or not handle.created or not handle.restore_token:
            return False
        item_id = str(handle.record.get("id") or "")
        with self._lock:
            if not self.restore_identity_matches(handle):
                return False
            item_path = self._item_path(item_id)
            token_path = self._restore_token_path(item_id)
            for path in list(item_path.iterdir()):
                if path == token_path:
                    continue
                if path.is_file():
                    path.unlink()
            token_path.unlink()
            item_path.rmdir()
            self._restore_versions.pop(item_id, None)
            return True

    def restore_identity_matches(self, handle: GalleryRestore) -> bool:
        if not isinstance(handle, GalleryRestore) or not handle.created:
            return False
        item_id = str(handle.record.get("id") or "")
        with self._lock:
            try:
                if self._restore_token_path(item_id).read_text(encoding="utf-8") != handle.restore_token:
                    return False
            except OSError:
                return False
            try:
                current = json.loads(
                    (self._item_path(item_id) / "metadata.json").read_text(encoding="utf-8")
                )
            except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
                return False
            if not isinstance(current, dict):
                return False
            expected = {
                key: value
                for key, value in handle.record.items()
                if key not in _GALLERY_DERIVED_ITEM_FIELDS
            }
            return current == expected

    def restore_target_exists(self, handle: GalleryRestore) -> bool:
        return self._item_path(str(handle.record.get("id") or "")).exists()

    def release_restore_ownership(self, handle: GalleryRestore) -> bool:
        if not isinstance(handle, GalleryRestore) or not handle.created or not handle.restore_token:
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

    def _invalidate_restore_ownership(self, item_id: str) -> None:
        path = self._restore_token_path(item_id)
        try:
            path.unlink()
        except FileNotFoundError:
            return
        _fsync_parent(path)

    def _restore_token_path(self, item_id: str) -> Path:
        return self._item_path(item_id) / ".restore-owner"

    def list_items(self, category: str | None = None) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        clean_category = self._clean_category(category) if category else None
        category_map = {item["id"]: item for item in self.list_categories()}
        items: list[dict[str, Any]] = []
        for metadata_path in self.root.glob("*/metadata.json"):
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            metadata = self._normalize_item_metadata(metadata, category_map=category_map)
            if clean_category and metadata.get("category") != clean_category:
                continue
            items.append(metadata)
        items.sort(key=lambda item: str(item.get("name", "")))
        items.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        items.sort(
            key=lambda item: (
                int(category_map.get(str(item.get("category") or ""), {}).get("order") or 0),
                0 if int(item.get("order") or 0) > 0 else 1,
                int(item.get("order") or 0) if int(item.get("order") or 0) > 0 else 0,
            )
        )
        return items

    def read_item(self, item_id: str) -> dict[str, Any]:
        path = self._item_path(item_id) / "metadata.json"
        return self._normalize_item_metadata(json.loads(path.read_text(encoding="utf-8")))

    def update_item(
        self,
        item_id: str,
        *,
        name: str | None = None,
        category: str | None = None,
        prompt_note: str | None = None,
        order: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            metadata = self.read_item(item_id)
            original_category = str(metadata.get("category") or "")
            target_category = original_category
            if name is not None:
                clean_name = _clean_gallery_name(name)
                if _gallery_name_key(clean_name) != metadata.get("name_key"):
                    self._ensure_unique_name(clean_name, ignore_id=item_id)
                metadata["name"] = clean_name
                metadata["name_key"] = _gallery_name_key(clean_name)
            if category is not None:
                target_category = self._clean_category(category)
                metadata["category"] = target_category
            if prompt_note is not None:
                metadata["prompt_note"] = _clean_gallery_prompt_note(prompt_note)
            if order is not None:
                metadata["order"] = _clean_gallery_item_order(order, fallback=int(metadata.get("order") or 0))
            elif category is not None and target_category != original_category:
                metadata["order"] = self._next_item_order(target_category)
            metadata["updated_at"] = utc_now()
            metadata.pop("category_name", None)
            metadata.pop("category_prompt_role", None)
            self._write_item_metadata(item_id, metadata)
            self._bump_restore_version(item_id)
            if category is not None and target_category != original_category:
                self._compact_category_item_orders(original_category)
            return self._normalize_item_metadata(metadata)

    def reorder_items(self, category: str, item_ids: list[str]) -> list[dict[str, Any]]:
        with self._lock:
            clean_category = self._clean_category(category)
            current_items = self.list_items(category=clean_category)
            current_ids = [str(item.get("id") or "") for item in current_items]
            reordered_ids = _clean_reorder_ids(item_ids, current_ids, clean_id=_clean_gallery_item_id, label="Gallery item")
            now = utc_now()
            for index, item_id in enumerate(reordered_ids, start=1):
                metadata = self.read_item(item_id)
                metadata["order"] = index * 10
                metadata["updated_at"] = now
                metadata.pop("category_name", None)
                metadata.pop("category_prompt_role", None)
                self._write_item_metadata(item_id, metadata)
                self._bump_restore_version(item_id)
            return self.list_items(category=clean_category)

    def replace_item_image(
        self,
        item_id: str,
        *,
        filename: str,
        data: bytes,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if not data:
                raise ValueError("Image is required")
            metadata = self.read_item(item_id)
            item_path = self._item_path(item_id)
            old_path = item_path / str(metadata.get("filename", ""))
            safe_name = _safe_filename(filename)
            image_path = item_path / safe_name
            atomic_write_bytes(image_path, data, mode=0o600)
            metadata["filename"] = safe_name
            metadata["mime_type"] = content_type or _guess_mime_type(safe_name)
            metadata["sha256"] = hashlib.sha256(data).hexdigest()
            metadata["size_bytes"] = len(data)
            metadata["updated_at"] = utc_now()
            metadata.pop("category_name", None)
            metadata.pop("category_prompt_role", None)
            self._write_item_metadata(item_id, metadata)
            self._bump_restore_version(item_id)
            if old_path != image_path and old_path.exists() and old_path.parent == item_path:
                old_path.unlink()
            return self._normalize_item_metadata(metadata)

    def delete_item(self, item_id: str) -> None:
        with self._lock:
            item_path = self._item_path(item_id)
            if not item_path.exists():
                raise FileNotFoundError(item_id)
            self._bump_restore_version(item_id)
            shutil.rmtree(item_path)

    def image_path(self, item_id: str) -> Path:
        metadata = self.read_item(item_id)
        path = self._item_path(item_id) / str(metadata.get("filename", ""))
        if not path.exists():
            raise FileNotFoundError(item_id)
        return path

    def _write_item_metadata(self, item_id: str, metadata: dict[str, Any]) -> Path:
        path = self._item_path(item_id) / "metadata.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, json.dumps(metadata, indent=2, ensure_ascii=False), mode=0o600)
        return path

    def _bump_restore_version(self, item_id: str) -> int:
        version = self._restore_versions.get(item_id, 0) + 1
        self._restore_versions[item_id] = version
        return version

    def _ensure_unique_name(self, name: str, *, ignore_id: str | None = None) -> None:
        name_key = _gallery_name_key(name)
        for item in self.list_items():
            if ignore_id and item.get("id") == ignore_id:
                continue
            if item.get("name_key") == name_key:
                raise FileExistsError(name)

    def _item_path(self, item_id: str) -> Path:
        if not item_id or "/" in item_id or "\\" in item_id:
            raise ValueError("Invalid gallery item id")
        return self.root / item_id

    def _categories_path(self) -> Path:
        return self.root / "categories.json"

    def _read_categories(self) -> list[dict[str, Any]]:
        try:
            payload = json.loads(self._categories_path().read_text(encoding="utf-8"))
        except FileNotFoundError:
            return [_normalize_gallery_category(category) for category in DEFAULT_GALLERY_CATEGORIES]
        except (OSError, json.JSONDecodeError):
            return [_normalize_gallery_category(category) for category in DEFAULT_GALLERY_CATEGORIES]
        if not isinstance(payload, list):
            return [_normalize_gallery_category(category) for category in DEFAULT_GALLERY_CATEGORIES]
        categories: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            try:
                category = _normalize_gallery_category(raw)
            except ValueError:
                continue
            if category["id"] in seen:
                continue
            seen.add(category["id"])
            categories.append(category)
        return categories or [_normalize_gallery_category(category) for category in DEFAULT_GALLERY_CATEGORIES]

    def _write_categories(self, categories: list[dict[str, Any]]) -> None:
        clean = [_normalize_gallery_category(category) for category in categories]
        atomic_write_text(
            self._categories_path(),
            json.dumps(clean, indent=2, ensure_ascii=False),
            mode=0o600,
        )

    def _new_category_id(self, categories: list[dict[str, Any]]) -> str:
        existing = {str(category.get("id") or "") for category in categories}
        while True:
            category_id = f"cat-{uuid.uuid4().hex[:10]}"
            if category_id not in existing:
                return category_id

    def _next_item_order(self, category: str) -> int:
        items = self._ensure_category_item_orders(category)
        current = [int(item.get("order") or 0) for item in items if int(item.get("order") or 0) > 0]
        return (max(current) if current else 0) + 10

    def _ensure_category_item_orders(self, category: str) -> list[dict[str, Any]]:
        items = self.list_items(category=category)
        if not any(int(item.get("order") or 0) <= 0 for item in items):
            return items
        category_map = {item["id"]: item for item in self.list_categories()}
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(items, start=1):
            metadata = self.read_item(str(item.get("id") or ""))
            metadata["order"] = index * 10
            metadata.pop("category_name", None)
            metadata.pop("category_prompt_role", None)
            self._write_item_metadata(str(item.get("id") or ""), metadata)
            self._bump_restore_version(str(item.get("id") or ""))
            normalized.append(self._normalize_item_metadata(metadata, category_map=category_map))
        return normalized

    def _compact_category_item_orders(self, category: str) -> list[dict[str, Any]]:
        items = self.list_items(category=category)
        category_map = {item["id"]: item for item in self.list_categories()}
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(items, start=1):
            metadata = self.read_item(str(item.get("id") or ""))
            metadata["order"] = index * 10
            metadata.pop("category_name", None)
            metadata.pop("category_prompt_role", None)
            self._write_item_metadata(str(item.get("id") or ""), metadata)
            self._bump_restore_version(str(item.get("id") or ""))
            normalized.append(self._normalize_item_metadata(metadata, category_map=category_map))
        return normalized

    def _clean_category(self, category: str | None) -> str:
        clean = _clean_gallery_category_id(category)
        if clean not in {item["id"] for item in self._read_categories()}:
            raise ValueError("Invalid gallery category")
        return clean

    def _normalize_item_metadata(
        self,
        metadata: dict[str, Any],
        *,
        category_map: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        item = dict(metadata)
        category_id = str(item.get("category") or "")
        categories = category_map if category_map is not None else {category["id"]: category for category in self.list_categories()}
        category = categories.get(category_id)
        item["order"] = _clean_gallery_item_order(item.get("order"), fallback=0)
        item["prompt_note"] = _clean_gallery_prompt_note(item.get("prompt_note"))
        item["category_name"] = str(category.get("name") or category_id) if category else category_id
        item["category_prompt_role"] = str(category.get("prompt_role") or item["category_name"] or "参考图") if category else "参考图"
        return item


def _clean_gallery_name(name: str) -> str:
    clean = " ".join(str(name or "").strip().split())
    if not clean:
        raise ValueError("Gallery name is required")
    if len(clean) > 64:
        raise ValueError("Gallery name is too long")
    return clean


def _gallery_name_key(name: str) -> str:
    return _clean_gallery_name(name).casefold()


def _unique_restore_name(storage: GalleryStorage, preferred: str) -> str:
    base = _clean_gallery_name(preferred)[:48]
    existing = {str(item.get("name") or "").casefold() for item in storage.list_items()}
    if base.casefold() not in existing:
        return base
    for index in range(2, 10_000):
        candidate = f"{base} ({index})"[:64]
        if candidate.casefold() not in existing:
            return candidate
    raise ValueError("Gallery name unavailable")


def _clean_gallery_category(category: str | None) -> str:
    clean = str(category or "").strip()
    if clean not in GALLERY_CATEGORIES:
        raise ValueError("Invalid gallery category")
    return clean


def _clean_gallery_category_id(category: str | None) -> str:
    clean = str(category or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", clean):
        raise ValueError("Invalid gallery category")
    return clean


def _clean_gallery_category_name(name: str) -> str:
    clean = " ".join(str(name or "").strip().split())
    if not clean:
        raise ValueError("Gallery category name is required")
    if len(clean) > 32:
        raise ValueError("Gallery category name is too long")
    return clean


def _clean_gallery_prompt_role(value: str | None, *, fallback: str = "参考图") -> str:
    clean = " ".join(str(value or "").strip().split())
    if not clean:
        clean = fallback
    if len(clean) > 48:
        raise ValueError("Gallery category prompt role is too long")
    return clean


def _clean_gallery_prompt_note(value: Any) -> str:
    clean = " ".join(str(value or "").strip().split())
    if len(clean) > 160:
        raise ValueError("Gallery prompt note is too long")
    return clean


def _clean_gallery_item_id(item_id: Any) -> str:
    clean = str(item_id or "").strip()
    if not clean or "/" in clean or "\\" in clean:
        raise ValueError("Invalid gallery item id")
    return clean


def _clean_gallery_item_order(value: Any, *, fallback: int = 0) -> int:
    try:
        order = int(value)
    except (TypeError, ValueError):
        return int(fallback)
    return order if order > 0 else int(fallback)


def _clean_reorder_ids(
    values: Any,
    expected_ids: list[str],
    *,
    clean_id,
    label: str,
) -> list[str]:
    if not isinstance(values, list):
        raise ValueError(f"{label} reorder list must be an array")
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values:
        item_id = clean_id(raw)
        if item_id in seen:
            raise ValueError(f"{label} reorder list contains duplicates")
        seen.add(item_id)
        cleaned.append(item_id)
    if cleaned != expected_ids and (len(cleaned) != len(expected_ids) or set(cleaned) != set(expected_ids)):
        raise ValueError(f"{label} reorder list must match current items")
    return cleaned


def _normalize_gallery_category(category: dict[str, Any]) -> dict[str, Any]:
    clean_id = _clean_gallery_category_id(str(category.get("id") or ""))
    clean_name = _clean_gallery_category_name(str(category.get("name") or clean_id))
    try:
        order = int(category.get("order", 0))
    except (TypeError, ValueError):
        order = 0
    return {
        "id": clean_id,
        "name": clean_name,
        "prompt_role": _clean_gallery_prompt_role(category.get("prompt_role"), fallback=clean_name),
        "order": order,
        "locked": bool(category.get("locked", False)),
        "created_at": str(category.get("created_at") or ""),
        "updated_at": str(category.get("updated_at") or ""),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _validated_gallery_snapshot_asset(
    metadata: dict[str, Any],
    image_path: Path,
    *,
    data: bytes | None = None,
) -> GallerySnapshotItem:
    path = Path(image_path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Gallery snapshot image is not a regular file")
    try:
        image_bytes = path.read_bytes() if data is None else data
        validated = validate_raster_image(
            image_bytes,
            filename=str(metadata.get("filename") or path.name),
        )
    except (InvalidRasterImage, OSError) as exc:
        raise ValueError("Gallery snapshot image is invalid") from exc
    expected_sha256 = str(metadata.get("sha256") or "")
    expected_size = metadata.get("size_bytes")
    expected_mime = str(metadata.get("mime_type") or "")
    legacy_identity = not expected_sha256 and expected_size is None
    if not legacy_identity and (
        expected_sha256 != validated.sha256
        or isinstance(expected_size, bool)
        or not isinstance(expected_size, int)
        or expected_size != len(image_bytes)
        or expected_mime != validated.mime_type
    ):
        raise ValueError("Gallery snapshot image digest or identity mismatch")
    normalized_metadata = dict(metadata)
    normalized_metadata["sha256"] = validated.sha256
    normalized_metadata["size_bytes"] = len(image_bytes)
    normalized_metadata["mime_type"] = validated.mime_type
    return GallerySnapshotItem(
        metadata=normalized_metadata,
        image_path=path,
        mime_type=validated.mime_type,
        size_bytes=len(image_bytes),
        sha256=validated.sha256,
    )
