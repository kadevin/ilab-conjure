from __future__ import annotations

import re
from typing import Any

from codex_image.codex_responses_client import build_codex_responses_payload
from codex_image.generation.types import GenerationCommand, GenerationOperation, ModelManifest
from codex_image.openai_images_client import build_openai_images_payload
from codex_image.openai_responses_client import build_openai_responses_payload
from codex_image.providers.contracts import ProtocolRequest, ProviderModelBinding
from codex_image.providers.transparency import transparency_request

GPT_PARAMETER_IDS = frozenset(
    {
        "canvas.size",
        "gpt.quality",
        "gpt.complexity",
        "gpt.frame_count",
        "gpt.frame_duration_ms",
        "gpt.background",
        "output.format",
        "gpt.moderation",
        "gpt.output_compression",
        "gpt.input_fidelity",
        "gpt.partial_images",
        "gpt.web_search",
        "output.count",
    }
)


def gpt_image_parameters(command: GenerationCommand) -> dict[str, Any]:
    params = {**command.parameters, **command.legacy_compat_parameters}
    return {
        "size": params.get("canvas.size"),
        "quality": params.get("gpt.quality"),
        "complexity": params.get("gpt.complexity"),
        "frame_count": params.get("gpt.frame_count"),
        "frame_duration_ms": params.get("gpt.frame_duration_ms"),
        "background": params.get("gpt.background"),
        "output_format": params.get("output.format", "png"),
        "moderation": params.get("gpt.moderation"),
        "output_compression": params.get("gpt.output_compression"),
        "input_fidelity": params.get("gpt.input_fidelity"),
        "partial_images": params.get("gpt.partial_images"),
        "web_search": params.get("gpt.web_search", False),
        "n": params.get("output.count", 1),
    }


class _GptCodec:
    def mapped_parameter_ids(
        self,
        model: ModelManifest,
        operation: GenerationOperation,
    ) -> frozenset[str]:
        del model, operation
        return GPT_PARAMETER_IDS


def _images_payload(
    command: GenerationCommand,
    binding: ProviderModelBinding,
) -> dict[str, Any]:
    parameters = gpt_image_parameters(command)
    if (command.operation == "edit" or command.image_inputs) and parameters["output_format"] in {"svg", "gif"}:
        raise ValueError("output_format_requires_generation")
    if (command.canonical_model_id.startswith("gpt-image-2.6-") or command.markup_image) and binding.protocol_profile != "openai_images":
        raise ValueError("image_feature_requires_openai_images")
    if parameters["output_format"] == "gif":
        from codex_image.raster_validation import MAX_RASTER_TOTAL_FRAME_PIXELS
        size = re.fullmatch(r"(\d+)x(\d+)", str(parameters["size"] or ""))
        if size and int(size[1]) * int(size[2]) * int(parameters["frame_count"] or 9) > MAX_RASTER_TOTAL_FRAME_PIXELS:
            raise ValueError("gif_frame_pixel_limit_exceeded")
    transparency = transparency_request(command, binding)
    return build_openai_images_payload(
        prompt=transparency.prompt,
        action=command.operation,
        model=binding.remote_model_id, default_model=binding.remote_model_id,
        input_images=[image.data_url for image in command.image_inputs],
        mask_image=command.mask_image,
        markup_image=command.markup_image,
        size=parameters["size"],
        quality=parameters["quality"],
        complexity=parameters["complexity"],
        frame_count=parameters["frame_count"],
        frame_duration_ms=parameters["frame_duration_ms"],
        background=transparency.background,
        output_format=parameters["output_format"],
        input_fidelity=parameters["input_fidelity"],
        moderation=parameters["moderation"],
        output_compression=parameters["output_compression"],
        n=1 if parameters["output_format"] == "svg" else parameters["n"],
    )


def _responses_payload(
    command: GenerationCommand,
    binding: ProviderModelBinding,
    *,
    codex: bool,
) -> dict[str, Any]:
    if command.canonical_model_id.startswith("gpt-image-2.6-") or command.markup_image:
        raise ValueError("image_feature_requires_openai_images")
    parameters = gpt_image_parameters(command)
    transparency = transparency_request(command, binding)
    builder = build_codex_responses_payload if codex else build_openai_responses_payload
    kwargs = dict(
        prompt=transparency.prompt,
        instructions=transparency.instructions,
        action=command.operation,
        main_model=command.main_model or "",
        model=binding.remote_model_id,
        input_images=[image.data_url for image in command.image_inputs],
        input_files=list(command.reference_files),
        mask_image=command.mask_image,
        size=parameters["size"],
        quality=parameters["quality"],
        background=transparency.background,
        output_format=parameters["output_format"],
        input_fidelity=parameters["input_fidelity"],
        moderation=parameters["moderation"],
        output_compression=parameters["output_compression"],
        partial_images=parameters["partial_images"],
        web_search=parameters["web_search"],
    )
    if not codex:
        kwargs["default_model"] = binding.remote_model_id
    return builder(**kwargs)


class GptCodexImagesCodec(_GptCodec):
    def encode(
        self, command: GenerationCommand, model: ModelManifest, binding: ProviderModelBinding
    ) -> ProtocolRequest:
        del model
        payload = _images_payload(command, binding)
        return ProtocolRequest(
            method="POST",
            path=str(payload["endpoint"]),
            content_type="application/json",
            json_body=payload,
            repeat_count=1,
        )


class GptOpenAIImagesCodec(_GptCodec):
    def encode(
        self, command: GenerationCommand, model: ModelManifest, binding: ProviderModelBinding
    ) -> ProtocolRequest:
        del model
        payload = _images_payload(command, binding)
        return ProtocolRequest(
            method="POST",
            path=str(payload["endpoint"]),
            content_type=(
                "multipart/form-data" if payload["endpoint"] == "/images/edits" else "application/json"
            ),
            json_body=payload,
            repeat_count=int(command.parameters.get("output.count", 1)) if payload.get("output_format") == "svg" else 1,
        )


class GptCodexResponsesCodec(_GptCodec):
    def encode(
        self, command: GenerationCommand, model: ModelManifest, binding: ProviderModelBinding
    ) -> ProtocolRequest:
        del model
        return ProtocolRequest(
            method="POST",
            path="/responses",
            content_type="application/json",
            json_body=_responses_payload(command, binding, codex=True),
            repeat_count=int(command.parameters.get("output.count", 1)),
        )


class GptOpenAIResponsesCodec(_GptCodec):
    def encode(
        self, command: GenerationCommand, model: ModelManifest, binding: ProviderModelBinding
    ) -> ProtocolRequest:
        del model
        payload = _responses_payload(command, binding, codex=False)
        return ProtocolRequest(
            method="POST",
            path=str(payload["endpoint"]),
            content_type="application/json",
            json_body=payload,
            repeat_count=int(command.parameters.get("output.count", 1)),
        )
