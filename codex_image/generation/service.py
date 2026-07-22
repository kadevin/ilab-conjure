from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from codex_image.providers.contracts import ExecutionPlan, ProtocolRequest
from codex_image.providers.registry import ProviderRegistry

from .resolver import BindingResolver
from .types import GenerationCommand, GenerationResult

_SENSITIVE_FIELD_KEYS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "x-goog-api-key",
        "x-api-key",
        "api-key",
        "apikey",
        "key",
        "token",
        "access-token",
        "file-data",
        "inline-data",
        "bytes",
    }
)


class GenerationService:
    def __init__(self, resolver: BindingResolver, registry: ProviderRegistry) -> None:
        self._resolver = resolver
        self._registry = registry

    def preview(self, command: GenerationCommand) -> ExecutionPlan:
        return self._resolver.resolve(command)

    def execute_plan_once(self, plan: ExecutionPlan) -> GenerationResult:
        single_request = replace(plan.protocol_request, repeat_count=1)
        single_plan = replace(plan, protocol_request=single_request)
        return self._registry.protocol(plan.binding.protocol_profile).execute(single_plan)

    def execute(self, command: GenerationCommand) -> GenerationResult:
        plan = self._resolver.resolve(command)
        results = [
            self.execute_plan_once(plan) for _ in range(plan.protocol_request.repeat_count)
        ]
        return merge_generation_results(results)


def merge_generation_results(results: list[GenerationResult]) -> GenerationResult:
    if not results:
        raise ValueError("At least one generation result is required")
    return GenerationResult(
        assets=tuple(asset for result in results for asset in result.assets),
        text_parts=tuple(part for result in results for part in result.text_parts),
        usage=(
            results[0].usage
            if len(results) == 1
            else {"requests": [dict(result.usage) for result in results]}
        ),
        provider_metadata=(
            results[0].provider_metadata
            if len(results) == 1
            else {
                "requests": [dict(result.provider_metadata) for result in results]
            }
        ),
    )


def redacted_protocol_request(plan: ExecutionPlan) -> ProtocolRequest:
    request = plan.protocol_request
    return replace(
        request,
        path=_redacted_url(request.path),
        json_body=_redact_value(request.json_body),
        form_fields=_redact_value(request.form_fields),
        files=tuple((name, filename, mime_type, b"") for name, filename, mime_type, _ in request.files),
    )


def _redact_value(value: Any, *, key: str = "") -> Any:
    normalized_key = _normalize_sensitive_key(key)
    if normalized_key in _SENSITIVE_FIELD_KEYS:
        return "<redacted>"
    if isinstance(value, Mapping):
        return {item_key: _redact_value(item, key=str(item_key)) for item_key, item in value.items()}
    if isinstance(value, (list, tuple)):
        converted = [_redact_value(item) for item in value]
        return type(value)(converted)
    if isinstance(value, bytes):
        return b""
    if isinstance(value, str):
        if value.lower().startswith("data:"):
            return "<redacted inline data>"
        if value.startswith("http://") or value.startswith("https://"):
            return _redacted_url(value)
    return value


def _redacted_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    query = [
        (key, "<redacted>" if _is_sensitive_query_key(key) else item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
    ]
    fragment = parts.fragment
    if "=" in fragment:
        fragment_items = [
            (key, "<redacted>" if _is_sensitive_query_key(key) else item)
            for key, item in parse_qsl(fragment, keep_blank_values=True)
        ]
        fragment = urlencode(fragment_items)
    netloc = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parts.scheme, netloc, parts.path, urlencode(query), fragment))


def _is_sensitive_query_key(key: str) -> bool:
    normalized = _normalize_sensitive_key(key)
    parts = set(normalized.split("-"))
    return normalized in _SENSITIVE_FIELD_KEYS or bool(
        parts.intersection({"token", "key", "auth", "authorization", "signature", "secret"})
    )


def _normalize_sensitive_key(key: str) -> str:
    value = str(key).strip()
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", value)
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


__all__ = (
    "GenerationService",
    "merge_generation_results",
    "redacted_protocol_request",
)
