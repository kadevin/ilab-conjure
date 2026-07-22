from __future__ import annotations

import base64
import binascii
import json
from typing import Any, Mapping
from urllib.parse import quote

from codex_image.generation.types import GenerationCommand, GenerationOperation, ModelManifest
from codex_image.providers.contracts import ProtocolRequest, ProviderModelBinding


GEMINI_PARAMETER_IDS = frozenset(
    {
        "canvas.aspect_ratio",
        "canvas.resolution",
        "output.modalities",
        "gemini.safety_settings",
        "gemini.google_search",
        "gemini.google_image_search",
        "output.count",
    }
)


class _GeminiImageCodec:
    def mapped_parameter_ids(
        self,
        model: ModelManifest,
        operation: GenerationOperation,
    ) -> frozenset[str]:
        del model, operation
        return GEMINI_PARAMETER_IDS


def _parameters(command: GenerationCommand) -> dict[str, Any]:
    return {**command.parameters, **command.legacy_compat_parameters}


def _response_modalities(value: Any) -> list[str]:
    if value in (None, "", "image", "IMAGE"):
        return ["IMAGE"]
    if value in ("text_image", "TEXT + IMAGE"):
        return ["TEXT", "IMAGE"]
    raise ValueError("Unsupported Gemini output modality")


def _safety_settings(value: Any) -> list[dict[str, str]]:
    if value in (None, {}):
        return []
    if not isinstance(value, Mapping):
        raise ValueError("Gemini safety settings must be an object")
    settings: list[dict[str, str]] = []
    for category, threshold in sorted(value.items(), key=lambda item: str(item[0])):
        category_value = str(category).strip()
        threshold_value = str(threshold).strip()
        if category_value and threshold_value:
            settings.append({"category": category_value, "threshold": threshold_value})
    return settings


def _tools(params: Mapping[str, Any]) -> list[dict[str, Any]]:
    search_types: dict[str, dict[str, Any]] = {}
    if params.get("gemini.google_search") is True:
        search_types["webSearch"] = {}
    if params.get("gemini.google_image_search") is True:
        search_types["imageSearch"] = {}
    if not search_types:
        return []
    return [{"google_search": {"searchTypes": search_types}}]


def _generation_config(
    params: Mapping[str, Any],
    *,
    native: bool,
    image_config: bool = False,
) -> dict[str, Any]:
    image: dict[str, Any] = {}
    aspect_ratio = params.get("canvas.aspect_ratio")
    resolution = params.get("canvas.resolution")
    if aspect_ratio is not None:
        image["aspectRatio"] = aspect_ratio
    if resolution is not None:
        image["imageSize"] = resolution
    config: dict[str, Any] = {
        "responseModalities": _response_modalities(params.get("output.modalities")),
    }
    if image and image_config:
        config["imageConfig"] = image
    elif image:
        config["responseFormat"] = {"image": image}
    if native:
        config["candidateCount"] = int(params.get("output.count") or 1)
    return config


def _decode_data_url(data_url: str) -> tuple[str, bytes]:
    header, separator, encoded = str(data_url).partition(",")
    if not separator or not header.lower().startswith("data:") or ";base64" not in header.lower():
        raise ValueError("Gemini image inputs must be base64 data URLs")
    mime_type = header[5:].split(";", 1)[0].strip().lower() or "application/octet-stream"
    try:
        return mime_type, base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Gemini image input contains invalid base64") from exc


def _inline_parts(
    command: GenerationCommand,
    *,
    camel_case: bool = False,
) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [{"text": command.prompt}]
    for image in command.image_inputs:
        mime_type, image_bytes = _decode_data_url(image.data_url)
        encoded = base64.b64encode(image_bytes).decode("ascii")
        if camel_case:
            parts.append({"inlineData": {"mimeType": mime_type, "data": encoded}})
        else:
            parts.append({"inline_data": {"mime_type": mime_type, "data": encoded}})
    return parts


def _multipart_files(command: GenerationCommand) -> tuple[tuple[str, str, str, bytes], ...]:
    files: list[tuple[str, str, str, bytes]] = []
    for index, image in enumerate(command.image_inputs, start=1):
        mime_type, image_bytes = _decode_data_url(image.data_url)
        extension = {
            "image/jpeg": "jpg",
            "image/webp": "webp",
            "image/gif": "gif",
        }.get(mime_type, "png")
        files.append(("image", f"input-{index}.{extension}", mime_type, image_bytes))
    return tuple(files)


class GeminiGenerateContentImageCodec(_GeminiImageCodec):
    def encode(
        self,
        command: GenerationCommand,
        model: ModelManifest,
        binding: ProviderModelBinding,
    ) -> ProtocolRequest:
        del model
        params = _parameters(command)
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": _inline_parts(command)}],
            "generationConfig": _generation_config(params, native=True),
        }
        tools = _tools(params)
        if tools:
            body["tools"] = tools
        safety_settings = _safety_settings(params.get("gemini.safety_settings"))
        if safety_settings:
            body["safetySettings"] = safety_settings
        encoded_model = quote(binding.remote_model_id, safe="")
        return ProtocolRequest(
            method="POST",
            path=f"/models/{encoded_model}:generateContent",
            content_type="application/json",
            json_body=body,
            repeat_count=1,
        )


class GeminiGenerateContentImageConfigCodec(_GeminiImageCodec):
    """Gemini generateContent compatibility used by ImageConfig relays."""

    def encode(
        self,
        command: GenerationCommand,
        model: ModelManifest,
        binding: ProviderModelBinding,
    ) -> ProtocolRequest:
        del model
        params = _parameters(command)
        body: dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": _inline_parts(command, camel_case=True),
                }
            ],
            "generationConfig": _generation_config(
                params,
                native=True,
                image_config=True,
            ),
        }
        tools = _tools(params)
        if tools:
            body["tools"] = tools
        safety_settings = _safety_settings(params.get("gemini.safety_settings"))
        if safety_settings:
            body["safetySettings"] = safety_settings
        encoded_model = quote(binding.remote_model_id, safe="")
        return ProtocolRequest(
            method="POST",
            path=f"/models/{encoded_model}:generateContent",
            content_type="application/json",
            json_body=body,
            repeat_count=1,
        )


class GeminiOpenAIImagesCodec(_GeminiImageCodec):
    def encode(
        self,
        command: GenerationCommand,
        model: ModelManifest,
        binding: ProviderModelBinding,
    ) -> ProtocolRequest:
        del model
        params = _parameters(command)
        generation_config = _generation_config(params, native=False)
        tools = _tools(params)
        safety_settings = _safety_settings(params.get("gemini.safety_settings"))
        common: dict[str, Any] = {
            "model": binding.remote_model_id,
            "prompt": command.prompt,
            "n": int(params.get("output.count") or 1),
            "response_format": "b64_json",
        }
        aspect_ratio = params.get("canvas.aspect_ratio")
        if aspect_ratio is not None:
            common["aspect_ratio"] = aspect_ratio
        common["generation_config"] = generation_config
        if safety_settings:
            common["safety_settings"] = safety_settings
        if tools:
            common["tools"] = tools

        if command.operation == "edit":
            form_fields = {
                key: json.dumps(value, separators=(",", ":"))
                if isinstance(value, (dict, list))
                else value
                for key, value in common.items()
            }
            return ProtocolRequest(
                method="POST",
                path="/images/edits",
                content_type="multipart/form-data",
                form_fields=form_fields,
                files=_multipart_files(command),
                repeat_count=1,
            )

        return ProtocolRequest(
            method="POST",
            path="/images/generations",
            content_type="application/json",
            json_body=common,
            repeat_count=1,
        )


class GeminiT8ImagesCodec(_GeminiImageCodec):
    """T8/NewAPI async Images compatibility without Gemini extension fields."""

    def encode(
        self,
        command: GenerationCommand,
        model: ModelManifest,
        binding: ProviderModelBinding,
    ) -> ProtocolRequest:
        del model
        params = _parameters(command)
        common: dict[str, Any] = {
            "model": binding.remote_model_id,
            "prompt": command.prompt,
        }
        aspect_ratio = params.get("canvas.aspect_ratio")
        resolution = params.get("canvas.resolution")
        if aspect_ratio is not None:
            common["aspect_ratio"] = aspect_ratio
        if resolution is not None:
            common["image_size"] = resolution
        common["response_format"] = "b64_json"

        if command.operation == "edit":
            return ProtocolRequest(
                method="POST",
                path="/images/edits?async=true",
                content_type="multipart/form-data",
                form_fields=common,
                files=_multipart_files(command),
                repeat_count=1,
            )
        return ProtocolRequest(
            method="POST",
            path="/images/generations?async=true",
            content_type="application/json",
            json_body=common,
            repeat_count=1,
        )


class GeminiOpenRouterImagesCodec(_GeminiImageCodec):
    """OpenRouter Image API mapping for Gemini image models."""

    def encode(
        self,
        command: GenerationCommand,
        model: ModelManifest,
        binding: ProviderModelBinding,
    ) -> ProtocolRequest:
        del model
        params = _parameters(command)
        body: dict[str, Any] = {
            "model": binding.remote_model_id,
            "prompt": command.prompt,
            "n": int(params.get("output.count") or 1),
        }
        aspect_ratio = params.get("canvas.aspect_ratio")
        resolution = params.get("canvas.resolution")
        if aspect_ratio is not None:
            body["aspect_ratio"] = aspect_ratio
        if resolution is not None:
            body["resolution"] = resolution
        if command.image_inputs:
            body["input_references"] = [
                {
                    "type": "image_url",
                    "image_url": {"url": image.data_url},
                }
                for image in command.image_inputs
            ]
        return ProtocolRequest(
            method="POST",
            path="/images",
            content_type="application/json",
            json_body=body,
            repeat_count=1,
        )


__all__ = (
    "GEMINI_PARAMETER_IDS",
    "GeminiGenerateContentImageCodec",
    "GeminiGenerateContentImageConfigCodec",
    "GeminiOpenAIImagesCodec",
    "GeminiOpenRouterImagesCodec",
    "GeminiT8ImagesCodec",
)
