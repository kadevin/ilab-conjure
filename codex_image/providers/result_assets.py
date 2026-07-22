from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable, Mapping
from urllib.parse import urljoin, urlsplit

from codex_image.client_types import OPENAI_COMPATIBLE_USER_AGENT
from codex_image.http import HTTPResponse, Transport


MAX_ASSET_BYTES = 50 * 1024 * 1024


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
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(image_bytes) >= 12 and image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    if len(image_bytes) >= 12 and image_bytes[4:8] == b"ftyp" and image_bytes[8:12] in {
        b"avif",
        b"avis",
    }:
        return "image/avif"
    return None


def _dimensions(image_bytes: bytes) -> tuple[int | None, int | None]:
    try:
        from PIL import Image

        with Image.open(BytesIO(image_bytes)) as image:
            width, height = image.size
        if width > 0 and height > 0:
            return int(width), int(height)
    except Exception:
        pass
    return None, None


def _header(headers: Mapping[str, str], name: str) -> str:
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).lower() == wanted:
            return str(value)
    return ""


def _validated_download(response: HTTPResponse) -> LoadedAsset:
    if not 200 <= response.status < 300:
        raise AssetLoadError(f"asset download failed with HTTP {response.status}")
    image_bytes = bytes(response.body)
    if not image_bytes:
        raise AssetLoadError("asset download returned an empty body")
    if len(image_bytes) > MAX_ASSET_BYTES:
        raise AssetLoadError("asset download exceeded the 50 MiB limit")
    sniffed = sniff_image_mime(image_bytes)
    if sniffed is None:
        raise AssetLoadError("asset download did not contain a recognized image")
    content_type = _header(response.headers, "content-type").split(";", 1)[0].strip().lower()
    if content_type and content_type not in {"application/octet-stream", sniffed}:
        raise AssetLoadError("asset content type does not match its image bytes")
    width, height = _dimensions(image_bytes)
    return LoadedAsset(image_bytes, sniffed, width, height)


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
) -> HTTPResponse:
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
    parsed = urlsplit(str(url))
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise AssetLoadError("generated asset URL must use HTTP or HTTPS")

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
        )
        if 300 <= response.status < 400:
            location = _header(response.headers, "location")
            redirected = urljoin(url, location) if location else ""
            if not redirected or not same_origin(url, redirected):
                raise AssetLoadError("authenticated asset download refused a cross-origin redirect")
    return _validated_download(response)


def _decode_base64(value: str) -> bytes:
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
        mime_type = declared_mime or encoded_mime or sniff_image_mime(image_bytes) or "image/png"
        width, height = _dimensions(image_bytes)
        return LoadedAsset(image_bytes, mime_type, width, height)

    image_url = str(item.get("url") or "")
    if image_url.startswith("data:image/"):
        mime_type, image_bytes = _decode_data_url(image_url)
        width, height = _dimensions(image_bytes)
        return LoadedAsset(image_bytes, declared_mime or mime_type, width, height)
    parsed = urlsplit(image_url)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        if url_loader is None:
            raise AssetLoadError("generated asset URL has no downloader")
        loaded = url_loader(image_url)
        if isinstance(loaded, LoadedAsset):
            return loaded
        image_bytes = bytes(loaded)
        if not image_bytes or len(image_bytes) > MAX_ASSET_BYTES:
            raise AssetLoadError("generated asset download returned invalid bytes")
        mime_type = declared_mime or sniff_image_mime(image_bytes) or "image/png"
        width, height = _dimensions(image_bytes)
        return LoadedAsset(image_bytes, mime_type, width, height)
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
