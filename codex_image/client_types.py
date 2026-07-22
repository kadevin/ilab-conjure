from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit, urlunsplit

from .auth import AuthState
from .version import APP_VERSION

DEFAULT_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
DEFAULT_CODEX_IMAGES_BASE_URL = "https://chatgpt.com/backend-api/codex"
DEFAULT_OPENAI_API_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MAIN_MODEL = "gpt-5.4-mini"
DEFAULT_IMAGE_MODEL = "gpt-image-2"
OPENAI_COMPATIBLE_USER_AGENT = f"iLab-CONJURE/{APP_VERSION}"
RESPONSES_ERROR_MESSAGE_LIMIT = 2_000
RESPONSES_SENSITIVE_MARKER = "<redacted file data>"
_RESPONSES_DATA_URL_RE = re.compile(r"data:[^,\s]*;base64,[A-Za-z0-9+/=_-]+", re.IGNORECASE)
_RESPONSES_DATA_URL_FULL_RE = re.compile(
    r"data:[^,\s]*;base64,([A-Za-z0-9+/]+={0,2})",
    re.IGNORECASE,
)


def normalize_openai_base_url(value: Any) -> str:
    raw = str(value or DEFAULT_OPENAI_API_BASE_URL).strip().rstrip("/")
    if not raw:
        raw = DEFAULT_OPENAI_API_BASE_URL
    parts = urlsplit(raw)
    if not parts.scheme or not parts.netloc:
        raise ValueError("OpenAI-compatible base_url must be an absolute URL")
    path = parts.path.rstrip("/")
    for suffix in ("/responses", "/images/generations", "/images/edits"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def image_model_supports_input_fidelity(model: str | None) -> bool:
    return (model or "").lower() != "gpt-image-2"


@dataclass
class ImageResult:
    image_bytes: bytes
    revised_prompt: str
    output_format: str
    size: str
    background: str
    quality: str
    usage: dict[str, Any]
    tool_usage: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResponsesInputFile:
    filename: str
    mime_type: str
    file_data: str
    detail: Literal["auto", "low", "high"] | None = None

    def to_content_part(self) -> dict[str, str]:
        part = {
            "type": "input_file",
            "filename": self.filename,
            "file_data": self.file_data,
        }
        if self.detail is not None:
            part["detail"] = self.detail
        return part


class ResponsesRequestError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status: int,
        body: str,
        sensitive_values: Any = None,
    ) -> None:
        body_text = str(body)
        outbound_sensitive: set[str] = set()
        for value in _iter_responses_string_values(sensitive_values):
            outbound_sensitive.update(_responses_sensitive_variants(value))
        safe_message = _redact_responses_message_from_body(
            str(message),
            body_text,
            sensitive_values=outbound_sensitive,
        )
        if len(safe_message) > RESPONSES_ERROR_MESSAGE_LIMIT:
            safe_message = f"{safe_message[: RESPONSES_ERROR_MESSAGE_LIMIT - 3]}..."
        super().__init__(safe_message)
        self.status = int(status)
        self.body = body_text


def _iter_responses_string_values(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_responses_string_values(item)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from _iter_responses_string_values(item)


def _responses_sensitive_variants(value: str) -> set[str]:
    variants = {value} if value else set()
    match = _RESPONSES_DATA_URL_FULL_RE.fullmatch(value)
    if match is None:
        return variants

    payload = match.group(1)
    if payload:
        variants.add(payload)
    try:
        decoded = base64.b64decode(payload, validate=True).decode("utf-8", errors="strict")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return variants
    if decoded:
        variants.add(decoded)
    return variants


def _collect_responses_file_data_values(value: Any) -> set[str]:
    sensitive_values: set[str] = set()
    if isinstance(value, dict):
        for item_key, item_value in value.items():
            if str(item_key).lower() == "file_data":
                for string_value in _iter_responses_string_values(item_value):
                    sensitive_values.update(_responses_sensitive_variants(string_value))
            sensitive_values.update(_collect_responses_file_data_values(item_value))
    elif isinstance(value, list):
        for item in value:
            sensitive_values.update(_collect_responses_file_data_values(item))
    return sensitive_values


def _redact_responses_text(value: str, sensitive_values: set[str]) -> str:
    redacted = value
    for sensitive_value in sorted(sensitive_values, key=len, reverse=True):
        if sensitive_value and sensitive_value != RESPONSES_SENSITIVE_MARKER:
            if len(sensitive_value) >= 8:
                redacted = redacted.replace(sensitive_value, RESPONSES_SENSITIVE_MARKER)
            else:
                redacted = re.sub(
                    rf"(?<![A-Za-z0-9_]){re.escape(sensitive_value)}(?![A-Za-z0-9_])",
                    RESPONSES_SENSITIVE_MARKER,
                    redacted,
                )
    return _RESPONSES_DATA_URL_RE.sub(RESPONSES_SENSITIVE_MARKER, redacted)


def _redact_responses_message_from_body(
    message: str,
    body: str,
    *,
    sensitive_values: set[str] | None = None,
) -> str:
    safe_message = message
    if body and body in safe_message:
        safe_message = safe_message.replace(body, "<redacted response body>")
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, TypeError, ValueError):
        body_sensitive_values: set[str] = set()
    else:
        body_sensitive_values = _collect_responses_file_data_values(parsed)
    return _redact_responses_text(
        safe_message,
        set(sensitive_values or ()).union(body_sensitive_values),
    )


def _redact_responses_value(
    value: Any,
    *,
    key: str | None = None,
    sensitive_values: set[str] | None = None,
) -> Any:
    if sensitive_values is None:
        sensitive_values = _collect_responses_file_data_values(value)
    if key is not None and key.lower() == "file_data":
        return RESPONSES_SENSITIVE_MARKER
    if isinstance(value, dict):
        return {
            str(item_key): _redact_responses_value(
                item_value,
                key=str(item_key),
                sensitive_values=sensitive_values,
            )
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [
            _redact_responses_value(item, sensitive_values=sensitive_values)
            for item in value
        ]
    if isinstance(value, str):
        return _redact_responses_text(value, sensitive_values)
    return value


def _find_responses_error(value: Any) -> Any:
    if isinstance(value, dict):
        if value.get("error") is not None:
            return value["error"]
        for item in value.values():
            error = _find_responses_error(item)
            if error is not None:
                return error
    elif isinstance(value, list):
        for item in value:
            error = _find_responses_error(item)
            if error is not None:
                return error
    return None


def _responses_summary_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value).strip()


def safe_responses_error_message(status: int, body: str) -> str:
    prefix = f"Responses request failed: HTTP {int(status)}"
    try:
        parsed = json.loads(str(body))
    except (json.JSONDecodeError, TypeError, ValueError):
        return prefix

    sensitive_values = _collect_responses_file_data_values(parsed)
    sanitized = _redact_responses_value(parsed, sensitive_values=sensitive_values)
    error = _find_responses_error(sanitized)
    summary = ""
    if isinstance(error, dict):
        code = _responses_summary_text(error.get("code") or error.get("type"))
        message = _responses_summary_text(error.get("message"))
        summary = ": ".join(part for part in (code, message) if part)
    elif error is not None:
        summary = _responses_summary_text(error)

    result = f"{prefix}: {summary}" if summary else prefix
    if len(result) > RESPONSES_ERROR_MESSAGE_LIMIT:
        result = f"{result[: RESPONSES_ERROR_MESSAGE_LIMIT - 3]}..."
    return result


class AuthProvider(Protocol):
    def next_auth_state(self) -> AuthState:
        ...

    def next_auth_state_after_unauthorized(self, current_state: AuthState) -> AuthState | None:
        ...

    def available_count(self) -> int:
        ...
