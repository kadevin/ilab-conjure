from __future__ import annotations

import base64
import json
import re
import time
import uuid
from collections.abc import Mapping, Sequence
from io import BytesIO
from os import PathLike
from typing import Any

from .client_types import (
    DEFAULT_IMAGE_MODEL,
    DEFAULT_MAIN_MODEL,
    DEFAULT_OPENAI_API_BASE_URL,
    OPENAI_COMPATIBLE_USER_AGENT,
    ImageResult,
    image_model_supports_input_fidelity,
    normalize_openai_base_url,
)
from .http import HTTPResponse, Transport, UrllibTransport
from .providers.result_assets import AssetLoadError, LoadedAsset, load_response_asset


_DIMENSION_SIZE_RE = re.compile(r"^\s*(\d{1,5})\s*[xX×]\s*(\d{1,5})\s*$")


class PartialImageResultsError(RuntimeError):
    def __init__(self, results, outcomes, completed_at) -> None:
        super().__init__("Image batch interrupted after partial results")
        self.results = list(results)
        self.outcomes = list(outcomes)
        self.completed_at = tuple(completed_at)


def build_openai_images_headers(api_key: str, *, content_type: str) -> dict[str, str]:
    return {
        "Content-Type": content_type,
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": OPENAI_COMPATIBLE_USER_AGENT,
    }


def raise_for_openai_images_response(response: HTTPResponse) -> None:
    if response.status < 200 or response.status >= 300:
        raise RuntimeError(
            "OpenAI-compatible images request failed: "
            f"HTTP {response.status}: {response.body.decode('utf-8', errors='replace')}"
        )


def build_openai_images_payload(
    *,
    prompt: str,
    action: str = "generate",
    model: str | None = None,
    default_model: str = DEFAULT_IMAGE_MODEL,
    input_images: list[str] | None = None,
    mask_image: str | None = None,
    markup_image: str | None = None,
    size: str | None = None,
    quality: str | None = None,
    complexity: str | None = None,
    frame_count: int | None = None,
    frame_duration_ms: int | None = None,
    background: str | None = None,
    output_format: str = "png",
    input_fidelity: str | None = None,
    moderation: str | None = None,
    output_compression: int | None = None,
    n: int = 1,
) -> dict[str, Any]:
    image_model = str(model or default_model or DEFAULT_IMAGE_MODEL).strip() or DEFAULT_IMAGE_MODEL
    images = list(input_images or [])
    count = OpenAIImagesImageClient._normalize_image_count(n)
    payload: dict[str, Any] = {
        "endpoint": "/images/edits" if action == "edit" or images else "/images/generations",
        "model": image_model,
        "prompt": prompt,
        "n": count,
        "output_format": output_format,
    }
    for key, value in (("size", size), ("quality", quality), ("background", background)):
        if value:
            payload[key] = value
    if input_fidelity and image_model_supports_input_fidelity(image_model):
        payload["input_fidelity"] = input_fidelity
    if moderation:
        payload["moderation"] = moderation
    if output_compression is not None:
        payload["output_compression"] = output_compression
    for key, value in (("complexity", complexity), ("frame_count", frame_count),
                       ("frame_duration_ms", frame_duration_ms)):
        if value is not None:
            payload[key] = value
    if images:
        payload["images"] = [{"image_url": image_url} for image_url in images]
    if mask_image:
        payload["mask"] = {"image_url": mask_image}
    if markup_image:
        payload["markup"] = {"image_url": markup_image}
    return payload


def build_multipart_body(
    form_fields: Mapping[str, Any],
    files: Sequence[tuple[str, str, str, bytes]],
) -> tuple[bytes, str]:
    boundary = f"----codex-image-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in form_fields.items():
        if value is None:
            continue
        if not isinstance(value, (str, int, float, bool)):
            raise TypeError(f"Multipart form field {name} must be a scalar")
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    for name, filename, mime_type, data in files:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(
                "utf-8"
            )
        )
        chunks.append(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
        chunks.append(bytes(data))
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


class OpenAIImagesImageClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_OPENAI_API_BASE_URL,
        image_model: str = DEFAULT_IMAGE_MODEL,
        transport: Transport | None = None,
    ) -> None:
        clean_key = str(api_key or "").strip()
        if not clean_key:
            raise RuntimeError("OpenAI-compatible API key is required")
        self.api_key = clean_key
        self.base_url = self._normalize_base_url(base_url)
        self.image_model = str(image_model or DEFAULT_IMAGE_MODEL).strip() or DEFAULT_IMAGE_MODEL
        self.transport = transport or UrllibTransport()
        self.generations_url = f"{self.base_url}/images/generations"
        self.edits_url = f"{self.base_url}/images/edits"

    def generate_image(
        self,
        *,
        prompt: str,
        main_model: str = DEFAULT_MAIN_MODEL,
        model: str | None = None,
        reference_images: list[str] | None = None,
        size: str | None = None,
        quality: str | None = None,
        background: str | None = None,
        output_format: str = "png",
        moderation: str | None = None,
        output_compression: int | None = None,
        partial_images: int | None = None,
        debug_sse_path: str | PathLike[str] | None = None,
    ) -> ImageResult:
        return self.generate_images(
            prompt=prompt,
            main_model=main_model,
            model=model,
            reference_images=reference_images,
            size=size,
            quality=quality,
            background=background,
            output_format=output_format,
            moderation=moderation,
            output_compression=output_compression,
            partial_images=partial_images,
            debug_sse_path=debug_sse_path,
            n=1,
        )[0]

    def generate_images(
        self,
        *,
        prompt: str,
        main_model: str = DEFAULT_MAIN_MODEL,
        model: str | None = None,
        reference_images: list[str] | None = None,
        size: str | None = None,
        quality: str | None = None,
        background: str | None = None,
        output_format: str = "png",
        moderation: str | None = None,
        output_compression: int | None = None,
        partial_images: int | None = None,
        debug_sse_path: str | PathLike[str] | None = None,
        n: int = 1,
    ) -> list[ImageResult]:
        del partial_images, debug_sse_path
        action = "edit" if reference_images else "generate"
        payload = self.build_payload(
            prompt=prompt,
            action=action,
            main_model=main_model,
            model=model,
            input_images=reference_images or [],
            size=size,
            quality=quality,
            background=background,
            output_format=output_format,
            moderation=moderation,
            output_compression=output_compression,
            n=n,
        )
        return self._request_and_parse_many(payload)

    def edit_image(
        self,
        *,
        prompt: str,
        images: list[str],
        mask_image: str | None = None,
        main_model: str = DEFAULT_MAIN_MODEL,
        model: str | None = None,
        size: str | None = None,
        quality: str | None = None,
        background: str | None = None,
        output_format: str = "png",
        input_fidelity: str | None = None,
        moderation: str | None = None,
        output_compression: int | None = None,
        partial_images: int | None = None,
        debug_sse_path: str | PathLike[str] | None = None,
    ) -> ImageResult:
        return self.edit_images(
            prompt=prompt,
            images=images,
            mask_image=mask_image,
            main_model=main_model,
            model=model,
            size=size,
            quality=quality,
            background=background,
            output_format=output_format,
            input_fidelity=input_fidelity,
            moderation=moderation,
            output_compression=output_compression,
            partial_images=partial_images,
            debug_sse_path=debug_sse_path,
            n=1,
        )[0]

    def edit_images(
        self,
        *,
        prompt: str,
        images: list[str],
        mask_image: str | None = None,
        main_model: str = DEFAULT_MAIN_MODEL,
        model: str | None = None,
        size: str | None = None,
        quality: str | None = None,
        background: str | None = None,
        output_format: str = "png",
        input_fidelity: str | None = None,
        moderation: str | None = None,
        output_compression: int | None = None,
        partial_images: int | None = None,
        debug_sse_path: str | PathLike[str] | None = None,
        n: int = 1,
    ) -> list[ImageResult]:
        del partial_images, debug_sse_path
        if not images:
            raise RuntimeError("edit_image requires at least one input image")

        payload = self.build_payload(
            prompt=prompt,
            action="edit",
            main_model=main_model,
            model=model,
            input_images=images,
            mask_image=mask_image,
            size=size,
            quality=quality,
            background=background,
            output_format=output_format,
            input_fidelity=input_fidelity,
            moderation=moderation,
            output_compression=output_compression,
            n=n,
        )
        return self._request_and_parse_many(payload)

    def build_payload(
        self,
        *,
        prompt: str,
        action: str = "generate",
        main_model: str = DEFAULT_MAIN_MODEL,
        model: str | None = None,
        input_images: list[str] | None = None,
        mask_image: str | None = None,
        size: str | None = None,
        quality: str | None = None,
        background: str | None = None,
        output_format: str = "png",
        input_fidelity: str | None = None,
        moderation: str | None = None,
        output_compression: int | None = None,
        n: int = 1,
    ) -> dict[str, Any]:
        del main_model
        return build_openai_images_payload(
            prompt=prompt, action=action, model=model, default_model=self.image_model,
            input_images=input_images, mask_image=mask_image, size=size, quality=quality,
            background=background, output_format=output_format,
            input_fidelity=input_fidelity, moderation=moderation,
            output_compression=output_compression, n=n,
        )

    def _request_and_parse(self, payload: dict[str, Any]) -> ImageResult:
        return self._request_and_parse_many(payload)[0]

    def _request_and_parse_many(self, payload: dict[str, Any]) -> list[ImageResult]:
        endpoint = str(payload.get("endpoint") or "/images/generations")
        if endpoint == "/images/edits":
            body, content_type = self._build_multipart_edit_body(payload)
            url = self.edits_url
            headers = self._build_headers(content_type=content_type)
        else:
            request_payload = self._json_request_payload(payload)
            body = json.dumps(request_payload).encode("utf-8")
            url = self.generations_url
            headers = self._build_headers(content_type="application/json")

        response = self.transport.request(
            method="POST",
            url=url,
            headers=headers,
            body=body,
        )
        raise_for_openai_images_response(response)
        return self.parse_response_json_items(response.body, request_payload=payload, url_fetcher=lambda url: self._fetch_image_url(url, allow_svg=payload.get("output_format") == "svg"))

    def _build_headers(self, *, content_type: str) -> dict[str, str]:
        return build_openai_images_headers(self.api_key, content_type=content_type)

    @staticmethod
    def _json_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
        omitted = {"endpoint", "images", "mask", "markup"}
        return {key: value for key, value in payload.items() if key not in omitted and value is not None}

    @classmethod
    def _build_multipart_edit_body(cls, payload: dict[str, Any]) -> tuple[bytes, str]:
        omitted = {"endpoint", "images", "mask", "markup"}
        form_fields = {
            key: value
            for key, value in payload.items()
            if key not in omitted and value is not None
        }
        files: list[tuple[str, str, str, bytes]] = []

        images = payload.get("images")
        if not isinstance(images, list) or not images:
            raise RuntimeError("OpenAI-compatible images edit requires at least one input image")
        for index, image in enumerate(images, start=1):
            image_url = image.get("image_url") if isinstance(image, dict) else None
            mime_type, data = cls._decode_data_url(str(image_url or ""))
            files.append(
                (
                    "image",
                    f"image-{index}{cls._extension_for_mime_type(mime_type)}",
                    mime_type,
                    data,
                )
            )

        mask = payload.get("mask")
        if isinstance(mask, dict) and mask.get("image_url"):
            mime_type, data = cls._decode_data_url(str(mask["image_url"]))
            files.append(
                ("mask", f"mask{cls._extension_for_mime_type(mime_type)}", mime_type, data)
            )
        markup = payload.get("markup")
        if isinstance(markup, dict) and markup.get("image_url"):
            mime_type, data = cls._decode_data_url(str(markup["image_url"]))
            files.append(("markup", "markup.png", mime_type, data))
        return build_multipart_body(form_fields, files)

    @staticmethod
    def _decode_data_url(image_url: str) -> tuple[str, bytes]:
        match = re.fullmatch(r"data:([^;,]+)?(;base64)?,(.*)", image_url, flags=re.DOTALL)
        if match is None or match.group(2) != ";base64":
            raise RuntimeError("OpenAI-compatible images edit requires base64 data URL input images")
        mime_type = match.group(1) or "image/png"
        try:
            return mime_type, base64.b64decode(match.group(3), validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise RuntimeError("OpenAI-compatible images edit received invalid base64 image data") from exc

    @staticmethod
    def _extension_for_mime_type(mime_type: str) -> str:
        if mime_type == "image/jpeg":
            return ".jpg"
        if mime_type == "image/webp":
            return ".webp"
        if mime_type == "image/gif":
            return ".gif"
        return ".png"

    def _fetch_image_url(self, url: str, *, allow_svg: bool = False) -> bytes:
        from codex_image.providers.result_assets import AssetLoadError, download_asset_url

        try:
            return download_asset_url(
                url,
                transport=self.transport,
                provider_base_url=self.base_url,
                allow_svg=allow_svg,
                authorization=self._build_image_download_headers(include_auth=True).get("Authorization", ""),
            ).image_bytes
        except AssetLoadError as exc:
            raise RuntimeError(f"OpenAI-compatible images returned an invalid image URL asset: {exc}") from exc

    def _build_image_download_headers(self, *, include_auth: bool = False) -> dict[str, str]:
        headers = {
            "Accept": "image/*,*/*",
            "User-Agent": OPENAI_COMPATIBLE_USER_AGENT,
        }
        if include_auth:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def parse_response_json(
        body: bytes,
        *,
        request_payload: dict[str, Any] | None = None,
        url_fetcher: Any | None = None,
    ) -> ImageResult:
        return OpenAIImagesImageClient.parse_response_json_items(
            body,
            request_payload=request_payload,
            url_fetcher=url_fetcher,
        )[0]

    @staticmethod
    def parse_response_json_items(
        body: bytes,
        *,
        request_payload: dict[str, Any] | None = None,
        url_fetcher: Any | None = None,
        asset_outcomes: list[ImageResult | Exception] | None = None,
    ) -> list[ImageResult]:
        try:
            response = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AssetLoadError("OpenAI-compatible images returned invalid JSON") from exc
        if not isinstance(response, dict):
            raise AssetLoadError("OpenAI-compatible images returned non-object JSON")
        if isinstance(response.get("error"), dict):
            raise AssetLoadError(OpenAIImagesImageClient._format_api_error(response["error"]))

        data = response.get("data")
        if not isinstance(data, list):
            raise AssetLoadError("OpenAI-compatible images completed without image data")
        usage = response.get("usage", {})
        request_payload = request_payload or {}
        response_usage = usage if isinstance(usage, dict) else {}
        results: list[ImageResult] = []
        completed_at: list[float] = []
        for item in data:
            if not isinstance(item, dict) or not (item.get("b64_json") or item.get("url")):
                if asset_outcomes is not None:
                    asset_outcomes.append(AssetLoadError("generated response item has no image asset"))
                    completed_at.append(time.monotonic())
                continue
            try:
                asset = OpenAIImagesImageClient._asset_from_response_item(item, url_fetcher=url_fetcher, allow_svg=request_payload.get("output_format") == "svg")
                image_bytes = asset.image_bytes
            except Exception as exc:
                from concurrent.futures import CancelledError
                if isinstance(exc, CancelledError) and results and asset_outcomes is not None:
                    raise PartialImageResultsError(results, asset_outcomes, completed_at) from exc
                if asset_outcomes is None or isinstance(exc, CancelledError):
                    raise
                failure = AssetLoadError("generated asset could not be loaded")
                failure.__cause__ = exc
                asset_outcomes.append(failure)
                completed_at.append(time.monotonic())
                continue
            results.append(
                ImageResult(
                    image_bytes=image_bytes,
                    revised_prompt=str(item.get("revised_prompt", "")),
                    # Persist the decoded format, even when provider/request
                    # metadata names a different format or URL extension.
                    output_format=("svg" if asset.mime_type == "image/svg+xml" else asset.mime_type.removeprefix("image/")),
                    size=OpenAIImagesImageClient._result_size(
                        image_bytes,
                        f"{asset.width}x{asset.height}" if asset.width and asset.height else None,
                        item.get("size"),
                        response.get("size"),
                        request_payload.get("size"),
                    ),
                    background=str(item.get("background") or response.get("background") or request_payload.get("background") or ""),
                    quality=str(item.get("quality") or response.get("quality") or request_payload.get("quality") or ""),
                    usage=response_usage,
                )
            )
            if asset_outcomes is not None:
                asset_outcomes.append(results[-1])
                completed_at.append(time.monotonic())
        if not results and not asset_outcomes:
            raise AssetLoadError("OpenAI-compatible images completed without image data")
        return results

    @staticmethod
    def _result_size(image_bytes: bytes, *candidates: Any) -> str:
        image_size = OpenAIImagesImageClient._image_pixel_size(image_bytes)
        if image_size:
            return image_size
        for candidate in candidates:
            normalized = OpenAIImagesImageClient._normalize_dimension_size(candidate)
            if normalized:
                return normalized
        return ""

    @staticmethod
    def _normalize_dimension_size(value: Any) -> str:
        match = _DIMENSION_SIZE_RE.match(str(value or ""))
        if not match:
            return ""
        width = int(match.group(1))
        height = int(match.group(2))
        if width <= 0 or height <= 0:
            return ""
        return f"{width}x{height}"

    @staticmethod
    def _image_pixel_size(image_bytes: bytes) -> str:
        if not image_bytes:
            return ""
        try:
            from PIL import Image

            with Image.open(BytesIO(image_bytes)) as image:
                width, height = image.size
        except Exception:
            return ""
        if width <= 0 or height <= 0:
            return ""
        return f"{int(width)}x{int(height)}"

    @staticmethod
    def _image_bytes_from_response_item(item: dict[str, Any], *, url_fetcher: Any | None = None) -> bytes:
        return OpenAIImagesImageClient._asset_from_response_item(item, url_fetcher=url_fetcher).image_bytes

    @staticmethod
    def _asset_from_response_item(item: dict[str, Any], *, url_fetcher: Any | None = None, allow_svg: bool = False) -> LoadedAsset:
        try:
            return load_response_asset(item, url_loader=url_fetcher, allow_svg=allow_svg)
        except AssetLoadError as exc:
            raise RuntimeError("OpenAI-compatible images completed without valid image data") from exc

    @staticmethod
    def _normalize_image_count(value: int) -> int:
        try:
            count = int(value)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("OpenAI-compatible images n must be an integer") from exc
        if count < 1:
            raise RuntimeError("OpenAI-compatible images n must be at least 1")
        return count

    @staticmethod
    def _format_api_error(error: dict[str, Any]) -> str:
        code = str(error.get("code") or error.get("type") or "").strip()
        message = str(error.get("message") or "").strip()
        if code and message:
            return f"OpenAI-compatible images error: {code}: {message}"
        if message:
            return f"OpenAI-compatible images error: {message}"
        if code:
            return f"OpenAI-compatible images error: {code}"
        return f"OpenAI-compatible images error: {json.dumps(error, ensure_ascii=False)}"

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        try:
            return normalize_openai_base_url(base_url)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
