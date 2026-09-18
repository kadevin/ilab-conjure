from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


def _fsync_parent(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(path.parent, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def atomic_write_bytes(
    path: Path,
    data: bytes,
    *,
    mode: int | None = None,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_prefix = f".{target.name}."
    if len(temporary_prefix.encode("utf-8")) > 160:
        digest = hashlib.sha256(target.name.encode("utf-8")).hexdigest()[:16]
        temporary_prefix = f".atomic-{digest}."
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=temporary_prefix,
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    descriptor_open = True
    try:
        fchmod = getattr(os, "fchmod", None)
        if mode is not None and callable(fchmod):
            fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor_open = False
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temporary_path, mode)
        os.replace(temporary_path, target)
        _fsync_parent(target)
    finally:
        if descriptor_open:
            os.close(descriptor)
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def atomic_write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    mode: int | None = None,
) -> None:
    atomic_write_bytes(path, text.encode(encoding), mode=mode)
