from __future__ import annotations

from codex_image.codex_images_client import CodexImagesImageClient
from codex_image.codex_responses_client import CodexImageClient
from codex_image.providers.contracts import ExecutionPlan
from codex_image.providers.openai import image_results_to_generation


def _parameters(plan: ExecutionPlan) -> dict[str, object]:
    params = plan.command.parameters
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
    }


class CodexImagesAdapter:
    def __init__(self, *, auth_state=None, auth_provider=None, transport=None) -> None:
        self._auth_state = auth_state
        self._auth_provider = auth_provider
        self._transport = transport

    def execute(self, plan: ExecutionPlan):
        client = CodexImagesImageClient(
            self._auth_state,
            auth_provider=self._auth_provider,
            transport=self._transport,
            image_model=plan.binding.remote_model_id,
        )
        params = _parameters(plan)
        common = {
            "prompt": plan.command.prompt,
            "main_model": plan.command.main_model or "",
            "model": plan.binding.remote_model_id,
            "size": params["size"],
            "quality": params["quality"],
            "background": params["background"],
            "output_format": params["output_format"],
            "moderation": params["moderation"],
            "output_compression": params["output_compression"],
            "partial_images": params["partial_images"],
            "n": int(plan.command.parameters.get("output.count", 1)),
        }
        if plan.command.operation == "edit":
            results = client.edit_images(
                **common,
                images=[image.data_url for image in plan.command.image_inputs],
                mask_image=plan.command.mask_image,
                input_fidelity=params["input_fidelity"],
            )
        else:
            results = client.generate_images(
                **common,
                reference_images=[image.data_url for image in plan.command.image_inputs],
            )
        return image_results_to_generation(results)


class CodexResponsesAdapter:
    def __init__(self, *, auth_state=None, auth_provider=None, transport=None) -> None:
        self._auth_state = auth_state
        self._auth_provider = auth_provider
        self._transport = transport

    def execute(self, plan: ExecutionPlan):
        client = CodexImageClient(
            self._auth_state,
            auth_provider=self._auth_provider,
            transport=self._transport,
        )
        params = _parameters(plan)
        common = {
            "prompt": plan.command.prompt,
            "instructions": plan.command.instructions,
            "main_model": plan.command.main_model or "",
            "model": plan.binding.remote_model_id,
            "reference_files": list(plan.command.reference_files),
            "size": params["size"],
            "quality": params["quality"],
            "background": params["background"],
            "output_format": params["output_format"],
            "moderation": params["moderation"],
            "output_compression": params["output_compression"],
            "partial_images": params["partial_images"],
            "web_search": params["web_search"],
        }
        if plan.command.operation == "edit":
            result = client.edit_image(
                **common,
                images=[image.data_url for image in plan.command.image_inputs],
                mask_image=plan.command.mask_image,
                input_fidelity=params["input_fidelity"],
            )
        else:
            result = client.generate_image(
                **common,
                reference_images=[image.data_url for image in plan.command.image_inputs],
            )
        return image_results_to_generation([result])


__all__ = ("CodexImagesAdapter", "CodexResponsesAdapter")
