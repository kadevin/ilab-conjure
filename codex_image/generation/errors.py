from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any
import unicodedata


_MESSAGES = {
    "authentication_failed": "Provider authentication failed.",
    "rate_limited": "The provider rate limit was reached.",
    "invalid_parameters": "The provider rejected the request parameters.",
    "operation_unsupported": "The selected provider does not support this operation.",
    "input_limit_exceeded": "The selected model accepts fewer input images.",
    "upstream_error": "The provider request failed.",
    "asset_download_failed": "A generated asset could not be downloaded.",
    "request_timeout": "The provider request timed out.",
    "provider_credentials_missing": "The saved provider credentials are no longer available.",
    "snapshot_manifest_incompatible": "The queued request is incompatible with the current model manifest.",
}
_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|[@-_])")
_AUTH_VALUE_RE = re.compile(
    r"(?i)\b(authorization|proxy-authorization|api[-_ ]?key|x-goog-api-key|x-api-key|token)"
    r"\s*[:=]\s*(?:bearer\s+|basic\s+)?[^\s,;]+"
)
_BEARER_RE = re.compile(r"(?i)\b(bearer|basic)\s+[^\s,;]+")
_SENSITIVE_QUERY_RE = re.compile(
    r"(?i)([?&](?:access_?token|auth|authorization|api_?key|key|signature|secret|token)=)[^&#\s]+"
)


def sanitize_generation_error_text(
    value: Any,
    *,
    sensitive_values: tuple[str, ...] = (),
    prompt_values: tuple[str, ...] = (),
    limit: int = 2000,
) -> str:
    text = str(value)
    for prompt in prompt_values:
        if prompt:
            text = text.replace(prompt, "<redacted prompt>")
    for secret in sensitive_values:
        if secret:
            text = text.replace(secret, "<redacted credential>")
    text = _ANSI_ESCAPE_RE.sub("", text)
    text = _AUTH_VALUE_RE.sub(lambda match: f"{match.group(1)}=<redacted credential>", text)
    text = _BEARER_RE.sub("<redacted credential>", text)
    text = _SENSITIVE_QUERY_RE.sub(r"\1<redacted credential>", text)
    text = "".join(" " if unicodedata.category(char).startswith("C") else char for char in text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[: max(0, int(limit))]


@dataclass(frozen=True)
class GenerationErrorDetail:
    code: str
    message: str
    retryable: bool
    provider_id: str
    canonical_model_id: str
    protocol_profile: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GenerationProviderError(RuntimeError):
    def __init__(self, detail: GenerationErrorDetail, *, status_code: int = 502) -> None:
        super().__init__(detail.message)
        self.detail = detail
        self.status_code = status_code


def provider_error(
    code: str,
    *,
    provider_id: str,
    canonical_model_id: str,
    protocol_profile: str,
    status_code: int = 502,
    retryable: bool | None = None,
) -> GenerationProviderError:
    if code not in _MESSAGES:
        code = "upstream_error"
    if retryable is None:
        retryable = code in {"rate_limited", "upstream_error", "asset_download_failed", "request_timeout"}
    return GenerationProviderError(
        GenerationErrorDetail(
            code=code,
            message=_MESSAGES[code],
            retryable=retryable,
            provider_id=str(provider_id),
            canonical_model_id=str(canonical_model_id),
            protocol_profile=str(protocol_profile),
        ),
        status_code=status_code,
    )


def provider_error_from_exception(
    exc: BaseException,
    *,
    provider_id: str,
    canonical_model_id: str,
    protocol_profile: str,
) -> GenerationProviderError:
    text = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timed out" in text or "timeout" in text:
        code, status = "request_timeout", 504
    elif "401" in text or "403" in text or "unauthorized" in text or "authentication" in text:
        code, status = "authentication_failed", 502
    elif "429" in text or "rate limit" in text:
        code, status = "rate_limited", 503
    elif "400" in text or "422" in text or "invalid parameter" in text:
        code, status = "invalid_parameters", 400
    else:
        code, status = "upstream_error", 502
    return provider_error(
        code,
        provider_id=provider_id,
        canonical_model_id=canonical_model_id,
        protocol_profile=protocol_profile,
        status_code=status,
    )


__all__ = (
    "GenerationErrorDetail",
    "GenerationProviderError",
    "provider_error",
    "provider_error_from_exception",
    "sanitize_generation_error_text",
)
