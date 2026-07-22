from __future__ import annotations

import base64
import binascii
import json
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit, urlunsplit

from codex_image.client_types import OPENAI_COMPATIBLE_USER_AGENT
from codex_image.generation.errors import (
    GenerationProviderError,
    provider_error,
    provider_error_from_exception,
)
from codex_image.generation.types import GeneratedAsset, GenerationResult
from codex_image.http import UrllibTransport
from codex_image.providers.auth import auth_scheme_for_protocol
from codex_image.providers.contracts import ExecutionPlan
from codex_image.providers.result_assets import (
    AssetLoadError,
    LoadedAsset,
    download_asset_url,
    load_response_asset,
)


def _field(value: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in value:
            return value[name]
    return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _grounding_entry(value: Any) -> dict[str, Any] | None:
    metadata = _mapping(value)
    if not metadata:
        return None
    search_entry = _mapping(_field(metadata, "searchEntryPoint", "search_entry_point"))
    rendered_content = _field(search_entry, "renderedContent", "rendered_content")
    sources: list[dict[str, str]] = []
    chunks = _field(metadata, "groundingChunks", "grounding_chunks")
    if isinstance(chunks, list):
        for chunk in chunks:
            chunk_value = _mapping(chunk)
            image = _mapping(_field(chunk_value, "image"))
            web = _mapping(_field(chunk_value, "web"))
            source = image or web
            if not source:
                continue
            page_uri = _field(source, "uri", "pageUri", "page_uri")
            image_uri = _field(source, "imageUri", "image_uri")
            title = _field(source, "title")
            normalized = {
                key: str(item)
                for key, item in (
                    ("page_uri", page_uri),
                    ("image_uri", image_uri),
                    ("title", title),
                )
                if item
            }
            if normalized:
                sources.append(normalized)
    entry: dict[str, Any] = {}
    if isinstance(rendered_content, str) and rendered_content.strip():
        entry["rendered_content"] = rendered_content
    if sources:
        entry["sources"] = sources
    return entry or None


def parse_gemini_generate_content_response(
    body: bytes,
    *,
    provider_id: str,
    canonical_model_id: str,
    protocol_profile: str,
    url_loader: Callable[[str], LoadedAsset | bytes] | None = None,
) -> GenerationResult:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise provider_error(
            "upstream_error",
            provider_id=provider_id,
            canonical_model_id=canonical_model_id,
            protocol_profile=protocol_profile,
        ) from exc

    assets: list[GeneratedAsset] = []
    text_parts: list[str] = []
    grounding: list[dict[str, Any]] = []
    candidates = payload.get("candidates") if isinstance(payload, dict) else None
    if isinstance(candidates, list):
        for candidate in candidates:
            candidate_value = _mapping(candidate)
            content = _mapping(_field(candidate_value, "content"))
            parts = _field(content, "parts")
            if isinstance(parts, list):
                for part in parts:
                    part_value = _mapping(part)
                    text = _field(part_value, "text")
                    if isinstance(text, str) and text:
                        text_parts.append(text)
                    if _field(part_value, "thought") is True:
                        continue
                    inline_data = _mapping(_field(part_value, "inlineData", "inline_data"))
                    encoded = _field(inline_data, "data")
                    mime_type = str(
                        _field(inline_data, "mimeType", "mime_type") or "image/png"
                    )
                    if isinstance(encoded, str) and encoded and mime_type.lower().startswith("image/"):
                        try:
                            image_bytes = base64.b64decode(encoded, validate=True)
                        except (binascii.Error, ValueError):
                            image_bytes = b""
                        if image_bytes:
                            assets.append(
                                GeneratedAsset(
                                    image_bytes=image_bytes,
                                    mime_type=mime_type,
                                )
                            )
                    file_data = _mapping(_field(part_value, "fileData", "file_data"))
                    file_uri = _field(file_data, "fileUri", "file_uri", "uri", "url")
                    file_mime_type = str(
                        _field(file_data, "mimeType", "mime_type") or ""
                    )
                    if not file_uri or not file_mime_type.lower().startswith("image/"):
                        continue
                    try:
                        loaded = load_response_asset(
                            {"url": str(file_uri), "mime_type": file_mime_type},
                            url_loader=url_loader,
                        )
                    except AssetLoadError:
                        continue
                    assets.append(
                        GeneratedAsset(
                            image_bytes=loaded.image_bytes,
                            mime_type=loaded.mime_type,
                            width=loaded.width,
                            height=loaded.height,
                        )
                    )
            item = _grounding_entry(
                _field(candidate_value, "groundingMetadata", "grounding_metadata")
            )
            if item:
                grounding.append(item)

    if not assets:
        raise provider_error(
            "upstream_error",
            provider_id=provider_id,
            canonical_model_id=canonical_model_id,
            protocol_profile=protocol_profile,
        )

    usage = _mapping(_field(payload, "usageMetadata", "usage_metadata"))
    provider_metadata: dict[str, Any] = {}
    if grounding:
        provider_metadata["grounding"] = grounding
    model_version = _field(payload, "modelVersion", "model_version")
    if model_version:
        provider_metadata["model_version"] = str(model_version)
    return GenerationResult(
        assets=tuple(assets),
        text_parts=tuple(text_parts),
        usage=dict(usage),
        provider_metadata=provider_metadata,
    )


def _http_error(plan: ExecutionPlan, status: int) -> GenerationProviderError:
    if status in {400, 422}:
        code, public_status = "invalid_parameters", 400
    elif status in {401, 403}:
        code, public_status = "authentication_failed", 502
    elif status == 429:
        code, public_status = "rate_limited", 503
    else:
        code, public_status = "upstream_error", 502
    return provider_error(
        code,
        provider_id=plan.provider.id,
        canonical_model_id=plan.model.id,
        protocol_profile=plan.binding.protocol_profile,
        status_code=public_status,
    )


class GeminiGenerateContentAdapter:
    def __init__(self, *, transport=None) -> None:
        self._transport = transport or UrllibTransport()

    def execute(self, plan: ExecutionPlan) -> GenerationResult:
        scheme = auth_scheme_for_protocol(plan.binding.protocol_profile)
        if scheme != "x-goog-api-key":
            raise ValueError("Gemini generateContent requires x-goog-api-key authentication")
        request = plan.protocol_request
        body = json.dumps(request.json_body or {}, separators=(",", ":")).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": OPENAI_COMPATIBLE_USER_AGENT,
            "x-goog-api-key": plan.provider.api_key,
        }
        try:
            response = self._transport.request(
                method=request.method,
                url=self._request_url(plan),
                headers=headers,
                body=body,
            )
        except GenerationProviderError:
            raise
        except Exception as exc:
            raise provider_error_from_exception(
                exc,
                provider_id=plan.provider.id,
                canonical_model_id=plan.model.id,
                protocol_profile=plan.binding.protocol_profile,
            ) from exc
        if response.status < 200 or response.status >= 300:
            raise _http_error(plan, response.status)

        def load_url(url: str) -> LoadedAsset:
            return download_asset_url(
                url,
                transport=self._transport,
                provider_base_url=plan.provider.base_url,
                authorization=None,
            )

        return parse_gemini_generate_content_response(
            response.body,
            provider_id=plan.provider.id,
            canonical_model_id=plan.model.id,
            protocol_profile=plan.binding.protocol_profile,
            url_loader=load_url,
        )

    def _request_url(self, plan: ExecutionPlan) -> str:
        return f"{plan.provider.base_url.rstrip('/')}{plan.protocol_request.path}"


class Change2ProGeminiAdapter(GeminiGenerateContentAdapter):
    """Route a shared OpenAI ``/v1`` provider base to Change2Pro Gemini ``/v1beta``."""

    def _request_url(self, plan: ExecutionPlan) -> str:
        parsed = urlsplit(plan.provider.base_url)
        base_path = parsed.path.rstrip("/")
        if base_path.endswith("/v1") or base_path.endswith("/v1beta"):
            base_path = base_path.rsplit("/", 1)[0]
        root = urlunsplit((parsed.scheme, parsed.netloc, base_path, "", "")).rstrip("/")
        return f"{root}/v1beta{plan.protocol_request.path}"


__all__ = (
    "Change2ProGeminiAdapter",
    "GeminiGenerateContentAdapter",
    "parse_gemini_generate_content_response",
)
