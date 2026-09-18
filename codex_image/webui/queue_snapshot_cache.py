from __future__ import annotations

from pathlib import Path
from time import monotonic
from typing import Any

from .context import WebUIContext
from .events import event_key, queue_snapshot, queued_or_running_task_ids


def _file_revision(path: Path) -> tuple[int, int, int] | None:
    try:
        info = path.stat()
        return info.st_ino, info.st_size, info.st_mtime_ns
    except FileNotFoundError:
        return None


class QueueSnapshotCache:
    """Shared by readers under StateSyncClock; never hold its lock across await."""

    def __init__(self, ctx: WebUIContext) -> None:
        self.ctx = ctx
        self._revision: tuple[Any, ...] | None = None
        self._expires = 0.0
        self._value: tuple[dict[str, Any], str, set[str]] | None = None

    def _source_revision(self) -> tuple[Any, ...]:
        ctx = self.ctx
        paths = (ctx.queue_storage.path, ctx.storage.task_index.path)
        channels = ctx.queue_manager.channels if ctx.queue_manager is not None else []
        return (
            *(_file_revision(path) for base in paths for path in (base, Path(str(base) + "-wal"))),
            frozenset(ctx.active_task_ids),
            tuple((c.channel_id, c.auth_source, ctx.route_helpers["queue_channel_available"](c)) for c in channels),
        )

    def get(self) -> tuple[dict[str, Any], str, set[str]]:
        revision = self._source_revision()
        if self._value is not None and revision == self._revision and monotonic() < self._expires:
            return self._value
        queue = queue_snapshot(self.ctx)
        value = queue, event_key(queue), queued_or_running_task_ids(queue)
        # Writers do not take StateSyncClock. If a writer overlapped this read,
        # don't label a possibly mixed snapshot as the new revision's cache.
        self._revision = revision if revision == self._source_revision() else None
        self._value = value
        # Reconcile out-of-band edits to metadata/assets that bypass the index.
        self._expires = monotonic() + 30.0
        return value
