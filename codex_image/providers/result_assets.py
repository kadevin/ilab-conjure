from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.parse import urljoin, urlsplit

from codex_image.asset_urls import UnsafeAssetURLError

from codex_image.client_types import OPENAI_COMPATIBLE_USER_AGENT
from codex_image.http import HTTPResponse, Transport
from codex_image.raster_validation import (
    MAX_RASTER_BYTES,
    RasterValidationError,
    inspect_raster_image,
)


MAX_ASSET_BYTES = MAX_RASTER_BYTES


class AssetLoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class LoadedAsset:
    image_bytes: bytes
    mime_type: str
    width: int | None = None
    height: int | None = None


def same_origin(left: str, right: str) -> bool:
    left_url = urlsplit(left)
    right_url = urlsplit(right)
    return (
        left_url.scheme.lower(),
        (left_url.hostname or "").lower(),
        left_url.port or (443 if left_url.scheme.lower() == "https" else 80),
    ) == (
        right_url.scheme.lower(),
        (right_url.hostname or "").lower(),
        right_url.port or (443 if right_url.scheme.lower() == "https" else 80),
    )


def sniff_image_mime(image_bytes: bytes) -> str | None:
    try:
        return inspect_raster_image(
            image_bytes,
            max_bytes=MAX_ASSET_BYTES,
        ).mime_type
    except (RasterValidationError, ValueError):
        return None


def _header(headers: Mapping[str, str], name: str) -> str:
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).lower() == wanted:
            return str(value)
    return ""


def _validated_download(response: HTTPResponse) -> LoadedAsset:
    if not 200 <= response.status < 300:
        raise AssetLoadError(f"asset download failed with HTTP {response.status}")
    content_type = _header(response.headers, "content-type").split(";", 1)[0].strip().lower()
    return _validated_asset(
        bytes(response.body),
        declared_mime_types=(content_type,),
        source="asset download",
    )


def _validated_asset(
    image_bytes: bytes,
    *,
    declared_mime_types: tuple[str, ...] = (),
    source: str = "generated asset",
) -> LoadedAsset:
    try:
        inspection = inspect_raster_image(
            image_bytes,
            max_bytes=MAX_ASSET_BYTES,
        )
    except RasterValidationError as exc:
        raise AssetLoadError(
            f"{source} did not contain a valid raster image: {exc}"
        ) from exc
    for declared in declared_mime_types:
        content_type = str(declared or "").split(";", 1)[0].strip().lower()
        if not content_type or content_type == "application/octet-stream":
            continue
        if content_type != inspection.mime_type:
            raise AssetLoadError(
                f"{source} content type does not match its image bytes"
            )
    return LoadedAsset(
        image_bytes=image_bytes,
        mime_type=inspection.mime_type,
        width=inspection.width,
        height=inspection.height,
    )


def _download_headers(*, authorization: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "image/*,*/*",
        "User-Agent": OPENAI_COMPATIBLE_USER_AGENT,
    }
    if authorization:
        headers["Authorization"] = authorization
    return headers


def _authenticated_request(
    transport: Transport,
    *,
    url: str,
    authorization: str,
    provider_base_url: str,
) -> HTTPResponse:
    asset_request = getattr(transport, "request_asset_bounded", None)
    if callable(asset_request):
        return asset_request(url=url, headers=_download_headers(authorization=authorization),
                             max_response_bytes=MAX_ASSET_BYTES, provider_base_url=provider_base_url)
    bounded_guarded = getattr(
        transport,
        "request_same_origin_redirects_bounded",
        None,
    )
    if callable(bounded_guarded):
        return bounded_guarded(
            method="GET",
            url=url,
            headers=_download_headers(authorization=authorization),
            body=b"",
            max_response_bytes=MAX_ASSET_BYTES,
        )
    guarded = getattr(transport, "request_same_origin_redirects", None)
    if callable(guarded):
        return guarded(
            method="GET",
            url=url,
            headers=_download_headers(authorization=authorization),
            body=b"",
        )
    return transport.request(
        method="GET",
        url=url,
        headers=_download_headers(authorization=authorization),
        body=b"",
    )


def download_asset_url(
    url: str,
    *,
    transport: Transport,
    provider_base_url: str,
    authorization: str | None,
) -> LoadedAsset:
    try:
        return _download_asset_url(url, transport=transport,
                                   provider_base_url=provider_base_url, authorization=authorization)
    except UnsafeAssetURLError as exc:
        raise AssetLoadError(str(exc)) from exc


def _download_asset_url(
    url: str, *, transport: Transport, provider_base_url: str, authorization: str | None,
) -> LoadedAsset:
    parsed = urlsplit(str(url))
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise AssetLoadError("generated asset URL must use HTTP or HTTPS")

    bounded = getattr(transport, "request_bounded", None)
    asset_request = getattr(transport, "request_asset_bounded", None)
    if callable(asset_request):
        response = asset_request(url=url, headers=_download_headers(),
                                 max_response_bytes=MAX_ASSET_BYTES, provider_base_url=provider_base_url)
    elif callable(bounded):
        response = bounded(
            method="GET",
            url=url,
            headers=_download_headers(),
            body=b"",
            max_response_bytes=MAX_ASSET_BYTES,
        )
    else:
        response = transport.request(
            method="GET",
            url=url,
            headers=_download_headers(),
            body=b"",
        )
    if response.status in {401, 403} and authorization and same_origin(url, provider_base_url):
        response = _authenticated_request(
            transport,
            url=url,
            authorization=authorization,
            provider_base_url=provider_base_url,
        )
        if 300 <= response.status < 400:
            location = _header(response.headers, "location")
            redirected = urljoin(url, location) if location else ""
            if not redirected or not same_origin(url, redirected):
                raise AssetLoadError("authenticated asset download refused a cross-origin redirect")
    return _validated_download(response)


def _decode_base64(value: str) -> bytes:
    maximum_encoded_bytes = ((MAX_ASSET_BYTES + 2) // 3) * 4
    if len(value) > maximum_encoded_bytes:
        raise AssetLoadError("generated asset exceeded the 50 MiB limit")
    try:
        image_bytes = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AssetLoadError("generated asset contained invalid base64") from exc
    if not image_bytes:
        raise AssetLoadError("generated asset contained empty base64")
    if len(image_bytes) > MAX_ASSET_BYTES:
        raise AssetLoadError("generated asset exceeded the 50 MiB limit")
    return image_bytes


def _decode_data_url(value: str) -> tuple[str, bytes]:
    header, separator, encoded = str(value).partition(",")
    if not separator or not header.lower().startswith("data:image/") or ";base64" not in header.lower():
        raise AssetLoadError("generated asset data URL is not a base64 image")
    mime_type = header[5:].split(";", 1)[0].strip().lower()
    return mime_type, _decode_base64(encoded)


def load_response_asset(
    item: Mapping[str, Any],
    *,
    url_loader: Callable[[str], LoadedAsset | bytes] | None = None,
) -> LoadedAsset:
    declared_mime = str(
        item.get("mime_type") or item.get("mimeType") or item.get("media_type") or ""
    ).lower()
    if item.get("b64_json"):
        encoded = str(item["b64_json"])
        if encoded.startswith("data:image/"):
            encoded_mime, image_bytes = _decode_data_url(encoded)
        else:
            encoded_mime, image_bytes = "", _decode_base64(encoded)
        return _validated_asset(
            image_bytes,
            declared_mime_types=(declared_mime, encoded_mime),
        )

    image_url = str(item.get("url") or "")
    if image_url.startswith("data:image/"):
        encoded_mime, image_bytes = _decode_data_url(image_url)
        return _validated_asset(
            image_bytes,
            declared_mime_types=(declared_mime, encoded_mime),
        )
    parsed = urlsplit(image_url)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        if url_loader is None:
            raise AssetLoadError("generated asset URL has no downloader")
        loaded = url_loader(image_url)
        if isinstance(loaded, LoadedAsset):
            return _validated_asset(
                loaded.image_bytes,
                declared_mime_types=(declared_mime, loaded.mime_type),
                source="generated asset download",
            )
        return _validated_asset(
            bytes(loaded),
            declared_mime_types=(declared_mime,),
            source="generated asset download",
        )
    raise AssetLoadError("generated response completed without a supported image asset")


__all__ = (
    "AssetLoadError",
    "LoadedAsset",
    "MAX_ASSET_BYTES",
    "download_asset_url",
    "load_response_asset",
    "same_origin",
    "sniff_image_mime",
)
