from __future__ import annotations

from dataclasses import dataclass

from codex_image.generation.types import GenerationCommand
from codex_image.providers.contracts import ProviderModelBinding


# Versions are immutable: queued tasks retain their original output instruction.
_PROMPTS = {
    1: (
        "Output requirement selected by the user: generate an image with a real alpha "
        "channel and a transparent background, retaining the subject and its natural "
        "semi-transparent details. Do not draw a white background, a checkerboard, "
        "or any other imitation of transparency."
    ),
}


@dataclass(frozen=True)
class TransparencyRequest:
    prompt: str
    instructions: str | None
    background: str | None


def transparency_instruction(version: int = 1) -> str:
    try:
        return _PROMPTS[version]
    except KeyError as exc:
        raise ValueError("unsupported_transparency_prompt_version") from exc


def transparency_request(
    command: GenerationCommand, binding: ProviderModelBinding,
) -> TransparencyRequest:
    parameters = {**command.parameters, **command.legacy_compat_parameters}
    background = parameters.get("gpt.background")
    if background != "transparent":
        return TransparencyRequest(command.prompt, command.instructions, background)
    if parameters.get("output.format", "png") not in {"png", "webp"}:
        raise ValueError("transparent_background_requires_png_or_webp")
    if binding.transparency_mode == "native":
        return TransparencyRequest(command.prompt, command.instructions, background)
    if binding.transparency_mode != "prompt":
        raise ValueError("invalid_transparency_mode")
    requirement = transparency_instruction(binding.transparency_prompt_version)
    # Do not mutate the canonical command or the user's editable prompt.
    prompt = f"{command.prompt}\n\n{requirement}"
    instructions = "\n\n".join(filter(None, (
        command.instructions,
        "The transparent-background output requirement is explicitly selected by the "
        "user. Pass it to the image generation tool even in original or strict prompt "
        "fidelity mode; preserve the rest of the user's prompt. " + requirement,
    )))
    return TransparencyRequest(prompt, instructions, None)
