"""Bounded, credential-scrubbed provider replies, separate from task projections."""
from __future__ import annotations

from collections import deque
import json
import logging
import math
import os
from pathlib import Path
import re
import stat
from typing import Any
from urllib.parse import urlsplit

from .atomic_files import atomic_write_text
from .storage_utils import utc_now

SUFFIX = "provider-responses.json"
MAX_BODY_BYTES = 96 * 1024 * 1024
MAX_RECORD_BYTES = 256 * 1024
MAX_FILE_BYTES = 1024 * 1024
MAX_RECORDS = 16
MAX_EVENTS = 64
_SECRET_KEYS = {
    "authorization", "proxyauthorization", "apikey", "xapikey", "xgoogapikey",
    "token", "accesstoken", "refreshtoken", "idtoken", "clientsecret",
    "password", "secret", "cookie", "setcookie",
}
_BINARY_KEYS = {"b64json", "imagedata", "imageb64", "partialimageb64", "filedata"}
_AUTH_TEXT = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+")
_QUERY_SECRET = re.compile(
    r"(?i)([?&](?:access_?token|auth|authorization|api_?key|key|signature|sig|secret|token|x-amz-signature|x-goog-signature)=)[^&#\s]+"
)
_KEY_TEXT = re.compile(
    r"(?i)\b(authorization|proxy-authorization|api[-_ ]?key|x-goog-api-key|x-api-key|access_token|refresh_token|password|secret)\s*[:=]\s*[^\s,;]+"
)
_URL_USERINFO = re.compile(r"(https?://)[^/\s@]+@", re.IGNORECASE)


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _scrub(value: Any, secrets: tuple[str, ...] = ()) -> Any:
    remaining = 8000

    def text(value: str) -> str:
        # Redact before truncating, including credentials echoed in error messages.
        for secret in secrets:
            value = value.replace(secret, "[redacted]")
        value = _AUTH_TEXT.sub(r"\1 [redacted]", value)
        value = _QUERY_SECRET.sub(r"\1[redacted]", value)
        value = _KEY_TEXT.sub(r"\1=[redacted]", value)
        value = _URL_USERINFO.sub(r"\1[redacted]@", value)
        if len(value) > 16384:
            return value[:16384] + "\n[omitted: text limit]"
        return value

    def visit(value: Any, depth: int = 0, parent: str = "") -> Any:
        nonlocal remaining
        remaining -= 1
        if depth > 24 or remaining < 0:
            return "[omitted: structure limit]"
        if isinstance(value, dict):
            result = {}
            for name, item in value.items():
                if remaining <= 0:
                    result["_omitted"] = "structure limit"
                    break
                normalized = _key(name)
                if normalized in _SECRET_KEYS:
                    item = "[redacted: credential]"
                elif (
                    normalized in _BINARY_KEYS
                    or (normalized == "data" and parent in {"inlinedata", "audio"})
                    or (normalized == "result" and value.get("type") == "image_generation_call")
                ):
                    item = "[omitted: binary data]"
                result[text(name)] = visit(item, depth + 1, normalized)
            return result
        if isinstance(value, list):
            result = []
            for item in value:
                if remaining <= 0:
                    result.append("[omitted: structure limit]")
                    break
                result.append(visit(item, depth + 1, parent))
            return result
        if isinstance(value, str):
            if value.startswith("data:") or (
                len(value) >= 512 and re.fullmatch(r"[A-Za-z0-9+/=]+", value)
            ):
                return "[omitted: binary data]"
            return text(value)
        if isinstance(value, float) and not math.isfinite(value):
            return "[omitted: non-finite number]"
        return value

    return visit(value)


def response_record(response: Any, request: dict[str, Any]) -> dict[str, Any]:
    secrets: set[str] = set()
    for name, value in (request.get("headers") or {}).items():
        if _key(str(name)) in _SECRET_KEYS and value:
            raw = str(value).strip()
            secrets.add(raw)
            if raw.lower().startswith(("bearer ", "basic ")):
                secrets.add(raw.split(" ", 1)[1].strip())
    secret_values = tuple(sorted(secrets, key=len, reverse=True))
    url = urlsplit(str(request.get("url") or ""))
    record: dict[str, Any] = {
        "received_at": utc_now(), "method": str(request.get("method") or ""),
        "endpoint": _scrub(f"{url.scheme}://{url.hostname or ''}{url.path}", secret_values),
        "status": response.status,
    }
    body = response.body
    if len(body) > MAX_BODY_BYTES:
        record.update(kind="unavailable", omitted="response exceeds capture limit")
        return record
    content_type = next((str(v) for k, v in response.headers.items() if k.lower() == "content-type"), "")
    if "text/event-stream" in content_type or body.lstrip().startswith((b"data:", b"event:")):
        events: deque[Any] = deque(maxlen=MAX_EVENTS)
        count = 0
        invalid = 0
        # SSE permits multiple data lines per event and CRLF line endings.
        data: list[bytes] = []
        for line in [*body.splitlines(), b""]:
            if line.startswith(b"data:"):
                data.append(line[5:].lstrip(b" "))
            elif not line and data:
                payload = b"\n".join(data)
                data.clear()
                if payload.strip() == b"[DONE]":
                    continue
                try:
                    parsed = [json.loads(payload)]
                except (ValueError, UnicodeError, RecursionError):
                    # Some compatible providers omit blank event separators,
                    # which the generation parser also accepts line by line.
                    parsed = []
                    for item in payload.splitlines():
                        if item.strip() == b"[DONE]":
                            continue
                        try:
                            parsed.append(json.loads(item))
                        except (ValueError, UnicodeError, RecursionError):
                            invalid += 1
                for event in parsed:
                    count += 1
                    events.append(_scrub(event, secret_values))
        record.update(kind="sse", events=list(events), omitted_events=max(0, count - MAX_EVENTS), invalid_events=invalid)
    else:
        try:
            record.update(kind="json", body=_scrub(json.loads(body), secret_values))
        except (ValueError, UnicodeError, RecursionError):
            record.update(kind="unavailable", omitted="response is not valid JSON or SSE")
    if len(json.dumps(record, ensure_ascii=False).encode("utf-8")) > MAX_RECORD_BYTES:
        record.pop("body", None)
        record.pop("events", None)
        record.update(kind="unavailable", omitted="decoded response exceeds capture limit")
    return record


def _checked_path(storage: Any, task_id: str) -> Path:
    storage._assert_source_data_trust_binding()
    path = storage._source_data_path(task_id, SUFFIX)
    root = storage.source_data_root.resolve(strict=True)
    relative = path.relative_to(storage.source_data_root)
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise OSError("provider_response_path_invalid")
    if not path.parent.resolve(strict=False).is_relative_to(root):
        raise OSError("provider_response_path_invalid")
    return path


def read_provider_responses(storage: Any, task_id: str) -> dict[str, Any]:
    path = _checked_path(storage, task_id)
    try:
        expected = path.lstat()
    except FileNotFoundError:
        return {"version": 1, "records": [], "omitted_records": 0}
    if not stat.S_ISREG(expected.st_mode) or expected.st_size > MAX_FILE_BYTES:
        raise OSError("provider_response_file_invalid")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as source:
        actual = os.fstat(source.fileno())
        if not stat.S_ISREG(actual.st_mode) or (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino):
            raise OSError("provider_response_file_changed")
        raw = source.read(MAX_FILE_BYTES + 1)
    _checked_path(storage, task_id)
    if len(raw) > MAX_FILE_BYTES:
        raise OSError("provider_response_file_invalid")
    result = json.loads(raw)
    if not isinstance(result, dict) or result.get("version") != 1 or not isinstance(result.get("records"), list):
        raise ValueError("provider_response_file_invalid")
    return result


def append_provider_response(storage: Any, task_id: str, record: dict[str, Any]) -> None:
    with storage._task_write_lock(task_id):
        # An in-flight reply must not resurrect a deleted task.
        if not storage.metadata_path(task_id).is_file():
            return
        path = _checked_path(storage, task_id)
        result = read_provider_responses(storage, task_id)
        result["records"].append(record)
        while True:
            encoded = json.dumps(result, ensure_ascii=False, indent=2)
            if len(result["records"]) <= MAX_RECORDS and len(encoded.encode("utf-8")) <= MAX_FILE_BYTES:
                break
            result["records"].pop(0)
            result["omitted_records"] = int(result.get("omitted_records", 0)) + 1
        atomic_write_text(path, encoded, mode=0o600)


class RecordingTransport:
    """Keep transport capabilities/retries/cancellation intact; observe replies only."""

    _REQUEST_METHODS = frozenset({
        "request", "request_bounded", "request_same_origin_redirects",
        "request_same_origin_redirects_bounded",
    })

    def __init__(self, transport: Any, storage: Any, task_id: str) -> None:
        self._transport = transport
        self._storage = storage
        self._task_id = task_id

    def __getattr__(self, name: str) -> Any:
        method = getattr(self._transport, name)
        if name not in self._REQUEST_METHODS or not callable(method):
            return method

        def request(**kwargs: Any) -> Any:
            response = method(**kwargs)
            try:
                append_provider_response(self._storage, self._task_id, response_record(response, kwargs))
            except Exception as exc:
                # Diagnostics must never fail or replay a paid generation request.
                logging.getLogger(__name__).warning("Provider reply capture unavailable (%s)", type(exc).__name__)
            return response

        return request
