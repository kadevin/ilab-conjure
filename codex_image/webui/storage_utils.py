from __future__ import annotations

import mimetypes
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_filename(filename: str, *, max_bytes: int = 180) -> str:
    name = Path(filename or "input.bin").name
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    safe = safe or "input.bin"
    if len(safe.encode("utf-8")) <= max_bytes:
        return safe

    suffix = Path(safe).suffix
    if suffix and len(suffix.encode("utf-8")) >= max_bytes:
        suffix = ""
    stem = safe[: -len(suffix)] if suffix else safe
    stem = stem.rstrip(".-") or "input"
    stem_bytes = max(1, max_bytes - len(suffix.encode("utf-8")))
    return f"{stem[:stem_bytes].rstrip('.-') or 'input'}{suffix}"


def _safe_extension(output_format: str) -> str:
    normalized = (output_format or "png").lower().strip().lstrip(".")
    if normalized in {"jpg", "jpeg"}:
        return "jpg"
    if normalized in {"png", "webp", "gif", "svg"}:
        return normalized
    return "png"


def _task_date_directory(task_id: str) -> str:
    match = re.match(r"^(\d{4})(\d{2})(\d{2})", task_id)
    if not match:
        return "undated"
    year, month, day = match.groups()
    try:
        datetime(int(year), int(month), int(day), tzinfo=UTC)
    except ValueError:
        return "undated"
    return f"{year}-{month}-{day}"


def _safe_output_relative_path(filename: str) -> Path:
    raw = str(filename or "").strip().replace("\\", "/")
    candidate = PurePosixPath(raw)
    if not raw or candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        return Path(Path(raw).name)
    return Path(*candidate.parts)


def _guess_mime_type(filename: str) -> str:
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"
