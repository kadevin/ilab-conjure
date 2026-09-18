"""Compatibility imports for the shared atomic file primitives."""
from ..atomic_files import _fsync_parent, atomic_write_bytes, atomic_write_text

__all__ = ["_fsync_parent", "atomic_write_bytes", "atomic_write_text"]
