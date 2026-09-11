from __future__ import annotations

from contextlib import contextmanager
import threading
from typing import Iterator
import uuid


class StateSyncClock:
    """Serialize snapshot reads so their revisions also order their contents."""

    def __init__(self) -> None:
        self.instance = uuid.uuid4().hex
        self._revision = 0
        self._lock = threading.Lock()

    @contextmanager
    def capture(self) -> Iterator[dict[str, str | int]]:
        with self._lock:
            self._revision += 1
            yield {"instance": self.instance, "revision": self._revision}
