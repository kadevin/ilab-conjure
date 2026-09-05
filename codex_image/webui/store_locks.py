from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import wraps
from typing import Any, TypeVar


_Result = TypeVar("_Result")


class StoreLockMixin:
    @contextmanager
    def exclusive(self) -> Iterator[None]:
        with self._lock:  # type: ignore[attr-defined]
            yield


def store_locked(
    method: Callable[..., _Result],
) -> Callable[..., _Result]:
    @wraps(method)
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> _Result:
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapped


__all__ = ("StoreLockMixin", "store_locked")
