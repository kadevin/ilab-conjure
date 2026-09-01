from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Iterable


MAX_HTTP_REQUEST_BYTES: Final = 192 * 1024 * 1024
MAX_TASK_IMAGE_BYTES: Final = 128 * 1024 * 1024
MAX_TASK_ARCHIVE_INPUT_BYTES: Final = 512 * 1024 * 1024
MAX_HISTORY_BACKUP_UPLOAD_BYTES: Final = 64 * 1024 * 1024 * 1024
MAX_HISTORY_BACKUP_EXPANDED_BYTES: Final = 128 * 1024 * 1024 * 1024
MAX_HISTORY_BACKUP_MEMBER_BYTES: Final = 4 * 1024 * 1024 * 1024
MAX_HISTORY_BACKUP_MANIFEST_BYTES: Final = 16 * 1024 * 1024
MAX_HISTORY_BACKUP_ENTRIES: Final = 1_000_000
MAX_HISTORY_BACKUP_COMPRESSION_RATIO: Final = 200
HISTORY_BACKUP_UPLOAD_CHUNK_BYTES: Final = 8 * 1024 * 1024
HISTORY_BACKUP_MIN_FREE_BYTES: Final = 2 * 1024 * 1024 * 1024
HISTORY_BACKUP_FREE_RATIO: Final = 0.10

# User-configuration archives intentionally share the task-history archive
# ceilings so both local ZIP workflows enforce one hardened resource policy.
MAX_USER_CONFIG_BACKUP_UPLOAD_BYTES: Final = MAX_HISTORY_BACKUP_UPLOAD_BYTES
MAX_USER_CONFIG_BACKUP_EXPANDED_BYTES: Final = MAX_HISTORY_BACKUP_EXPANDED_BYTES
MAX_USER_CONFIG_BACKUP_MEMBER_BYTES: Final = MAX_HISTORY_BACKUP_MEMBER_BYTES
MAX_USER_CONFIG_BACKUP_MANIFEST_BYTES: Final = MAX_HISTORY_BACKUP_MANIFEST_BYTES
MAX_USER_CONFIG_BACKUP_ENTRIES: Final = MAX_HISTORY_BACKUP_ENTRIES
MAX_USER_CONFIG_BACKUP_COMPRESSION_RATIO: Final = MAX_HISTORY_BACKUP_COMPRESSION_RATIO
USER_CONFIG_BACKUP_UPLOAD_CHUNK_BYTES: Final = HISTORY_BACKUP_UPLOAD_CHUNK_BYTES
USER_CONFIG_BACKUP_MIN_FREE_BYTES: Final = HISTORY_BACKUP_MIN_FREE_BYTES
USER_CONFIG_BACKUP_FREE_RATIO: Final = HISTORY_BACKUP_FREE_RATIO


class TaskImageLimitError(ValueError):
    pass


@dataclass(frozen=True)
class TaskImageResource:
    key: str
    size_bytes: int


def validate_task_image_total(
    resources: Iterable[TaskImageResource],
    *,
    max_total_bytes: int = MAX_TASK_IMAGE_BYTES,
) -> int:
    if max_total_bytes < 0:
        raise ValueError("max_total_bytes must not be negative")
    seen: set[str] = set()
    total_bytes = 0
    for resource in resources:
        key = str(resource.key or "").strip()
        if not key:
            raise ValueError("task_image_resource_invalid")
        try:
            size_bytes = int(resource.size_bytes)
        except (TypeError, ValueError) as exc:
            raise ValueError("task_image_resource_invalid") from exc
        if size_bytes < 0:
            raise ValueError("task_image_resource_invalid")
        if key in seen:
            continue
        seen.add(key)
        total_bytes += size_bytes
        if total_bytes > max_total_bytes:
            raise TaskImageLimitError("task_images_total_too_large")
    return total_bytes


__all__ = (
    "MAX_HTTP_REQUEST_BYTES",
    "MAX_HISTORY_BACKUP_COMPRESSION_RATIO",
    "MAX_HISTORY_BACKUP_ENTRIES",
    "MAX_HISTORY_BACKUP_EXPANDED_BYTES",
    "MAX_HISTORY_BACKUP_MEMBER_BYTES",
    "MAX_HISTORY_BACKUP_MANIFEST_BYTES",
    "MAX_HISTORY_BACKUP_UPLOAD_BYTES",
    "MAX_USER_CONFIG_BACKUP_COMPRESSION_RATIO",
    "MAX_USER_CONFIG_BACKUP_ENTRIES",
    "MAX_USER_CONFIG_BACKUP_EXPANDED_BYTES",
    "MAX_USER_CONFIG_BACKUP_MEMBER_BYTES",
    "MAX_USER_CONFIG_BACKUP_MANIFEST_BYTES",
    "MAX_USER_CONFIG_BACKUP_UPLOAD_BYTES",
    "MAX_TASK_ARCHIVE_INPUT_BYTES",
    "MAX_TASK_IMAGE_BYTES",
    "HISTORY_BACKUP_FREE_RATIO",
    "HISTORY_BACKUP_MIN_FREE_BYTES",
    "HISTORY_BACKUP_UPLOAD_CHUNK_BYTES",
    "USER_CONFIG_BACKUP_FREE_RATIO",
    "USER_CONFIG_BACKUP_MIN_FREE_BYTES",
    "USER_CONFIG_BACKUP_UPLOAD_CHUNK_BYTES",
    "TaskImageLimitError",
    "TaskImageResource",
    "validate_task_image_total",
)
