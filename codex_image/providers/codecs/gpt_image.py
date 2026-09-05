from __future__ import annotations

from typing import Any

from codex_image.codex_responses_client import build_codex_responses_payload
from codex_image.generation.types import GenerationCommand, GenerationOperation, ModelManifest
from codex_image.openai_images_client import build_openai_images_payload
from codex_image.openai_responses_client import build_openai_responses_payload
from codex_image.providers.contracts import ProtocolRequest, ProviderModelBinding

GPT_PARAMETER_IDS = frozenset(
    {
        "canvas.size",
        "gpt.quality",
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
    return build_openai_images_payload(
        prompt=command.prompt,
        action=command.operation,
        model=binding.remote_model_id, default_model=binding.remote_model_id,
        input_images=[image.data_url for image in command.image_inputs],
        mask_image=command.mask_image,
        size=parameters["size"],
        quality=parameters["quality"],
        background=parameters["background"],
        output_format=parameters["output_format"],
        input_fidelity=parameters["input_fidelity"],
        moderation=parameters["moderation"],
        output_compression=parameters["output_compression"],
        n=parameters["n"],
    )


def _responses_payload(
    command: GenerationCommand,
    binding: ProviderModelBinding,
    *,
    codex: bool,
) -> dict[str, Any]:
    parameters = gpt_image_parameters(command)
    builder = build_codex_responses_payload if codex else build_openai_responses_payload
    kwargs = dict(
        prompt=command.prompt,
        instructions=command.instructions,
        action=command.operation,
        main_model=command.main_model or "",
        model=binding.remote_model_id,
        input_images=[image.data_url for image in command.image_inputs],
        input_files=list(command.reference_files),
        mask_image=command.mask_image,
        size=parameters["size"],
        quality=parameters["quality"],
        background=parameters["background"],
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
            repeat_count=1,
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


class GptAtlasCloudImagesCodec(_GptCodec):
    def encode(
        self,
        command: GenerationCommand,
        model: ModelManifest,
        binding: ProviderModelBinding,
    ) -> ProtocolRequest:
        del model
        params = gpt_image_parameters(command)
        if command.mask_image:
            raise ValueError("Atlas Cloud GPT Image does not support mask inputs")
        if command.reference_files:
            raise ValueError("Atlas Cloud GPT Image does not support reference files")
        if params["background"] == "transparent":
            raise ValueError(
                "Atlas Cloud GPT Image does not support transparent backgrounds"
            )
        if params["output_format"] == "webp":
            raise ValueError("Atlas Cloud GPT Image supports PNG or JPEG output")
        if params["output_compression"] not in (None, 80):
            raise ValueError(
                "Atlas Cloud GPT Image does not support output compression"
            )
        if params["input_fidelity"] not in (None, "low"):
            raise ValueError(
                "Atlas Cloud GPT Image does not support input fidelity controls"
            )
        if params["web_search"]:
            raise ValueError("Atlas Cloud GPT Image does not support web search")

        model_id = binding.remote_model_id
        for suffix in ("/text-to-image", "/edit"):
            if model_id.endswith(suffix):
                model_id = model_id[: -len(suffix)]
                break
        model_id += "/edit" if command.operation == "edit" else "/text-to-image"
        body: dict[str, Any] = {
            "model": model_id,
            "prompt": command.prompt,
            "size": params["size"],
            "output_format": params["output_format"],
        }
        if params["quality"] not in (None, "auto"):
            body["quality"] = params["quality"]
        if params["moderation"] not in (None, "auto"):
            body["moderation"] = params["moderation"]
        if command.operation == "edit":
            if not command.image_inputs:
                raise ValueError(
                    "Atlas Cloud GPT Image edit requires at least one input image"
                )
            if len(command.image_inputs) > 10:
                raise ValueError(
                    "Atlas Cloud GPT Image edit supports at most 10 input images"
                )
            body["images"] = [image.data_url for image in command.image_inputs]
        return ProtocolRequest(
            method="POST",
            path="/api/v1/model/generateImage",
            content_type="application/json",
            json_body=body,
            repeat_count=int(params["n"] or 1),
        )
