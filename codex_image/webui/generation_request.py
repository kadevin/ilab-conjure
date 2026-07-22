from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from codex_image.client_types import ResponsesInputFile
from codex_image.generation.types import GenerationCommand, GenerationOperation, ImageInput
from codex_image.generation.catalog import list_model_manifests
from codex_image.generation.resolver import BindingResolver
from codex_image.generation.service import GenerationService
from codex_image.providers.contracts import ProviderConnection, ProviderModelBinding
from codex_image.providers.registry import default_registry


LEGACY_ROUTING_FORM_FIELDS = frozenset({
    "model",
    "size",
    "resolution",
    "ratio",
    "orientation",
    "quality",
    "background",
    "output_format",
    "moderation",
    "output_compression",
    "input_fidelity",
    "n",
    "web_search",
    "codex_mode",
    "api_mode",
    "api_provider_id",
})


def parse_parameters_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("parameters_json must be a JSON object") from exc
    if not isinstance(value, dict):
        raise ValueError("parameters_json must be a JSON object")
    return {str(key): item for key, item in value.items()}


def legacy_gpt_request(legacy_fields: Mapping[str, Any]) -> tuple[str, str, dict[str, Any]]:
    parameters: dict[str, Any] = {
        "canvas.size": str(legacy_fields.get("size") or "auto"),
        "gpt.quality": str(legacy_fields.get("quality") or "low"),
        "gpt.background": str(legacy_fields.get("background") or "auto"),
        "output.format": str(legacy_fields.get("output_format") or "png"),
        "gpt.moderation": str(legacy_fields.get("moderation") or "auto"),
        "output.count": int(legacy_fields.get("n") or 1),
    }
    return (
        str(legacy_fields.get("model") or "gpt-image-2"),
        str(legacy_fields.get("resolved_provider_id") or "codex"),
        parameters,
    )


def legacy_gpt_compat_parameters(legacy_fields: Mapping[str, Any]) -> dict[str, Any]:
    compat: dict[str, Any] = {}
    if legacy_fields.get("output_compression") is not None:
        compat["gpt.output_compression"] = legacy_fields["output_compression"]
    if legacy_fields.get("input_fidelity") is not None:
        compat["gpt.input_fidelity"] = legacy_fields["input_fidelity"]
    if bool(legacy_fields.get("web_search")):
        compat["gpt.web_search"] = True
    return compat


def generation_command_from_form(
    *,
    operation: GenerationOperation,
    canonical_model_id: str | None,
    provider_id: str | None,
    parameters_json: str | None,
    prompt: str,
    image_inputs: tuple[ImageInput, ...] = (),
    reference_files: tuple[ResponsesInputFile, ...] = (),
    mask_image: str | None = None,
    main_model: str | None = None,
    instructions: str | None = None,
    legacy_fields: Mapping[str, Any],
    explicit_form_fields: frozenset[str] = frozenset(),
    binding_id: str | None = None,
) -> GenerationCommand:
    supplied = (canonical_model_id is not None, provider_id is not None, parameters_json is not None)
    if any(supplied):
        if not all(supplied) or not str(canonical_model_id).strip() or not str(provider_id).strip():
            raise ValueError("canonical_model_id, provider_id and parameters_json are required together")
        mixed = sorted(explicit_form_fields.intersection(LEGACY_ROUTING_FORM_FIELDS))
        if mixed:
            raise ValueError("canonical fields cannot be mixed with legacy routing fields")
        parameters = parse_parameters_json(parameters_json)
        model_id = str(canonical_model_id).strip()
        resolved_provider_id = str(provider_id).strip()
        resolved_binding_id = str(binding_id or "").strip() or None
        legacy_compat: dict[str, Any] = {}
    else:
        model_id, resolved_provider_id, parameters = legacy_gpt_request(legacy_fields)
        resolved_binding_id = None
        legacy_compat = legacy_gpt_compat_parameters(legacy_fields)
    return GenerationCommand(
        operation=operation,
        canonical_model_id=model_id,
        provider_id=resolved_provider_id,
        binding_id=resolved_binding_id,
        prompt=prompt,
        parameters=parameters,
        image_inputs=image_inputs,
        reference_files=reference_files,
        mask_image=mask_image,
        main_model=main_model,
        instructions=instructions,
        legacy_compat_parameters=legacy_compat,
    )


def codex_provider_connection(codex_mode: str) -> ProviderConnection:
    del codex_mode
    bindings = tuple(
        ProviderModelBinding(
            id=f"codex-gpt-image-2-{mode}",
            provider_id="codex",
            canonical_model_id="gpt-image-2",
            remote_model_id="gpt-image-2",
            protocol_profile=f"codex_{mode}",
            parameter_codec=f"gpt_codex_{mode}",
            operations=frozenset({"generate", "edit"}),
            is_default=mode == "images",
        )
        for mode in ("images", "responses")
    )
    return ProviderConnection(
        id="codex",
        name="Codex",
        base_url="https://chatgpt.com/backend-api/codex",
        api_key="",
        concurrency=1,
        bindings=bindings,
        builtin=True,
    )


def preview_generation_command(
    command: GenerationCommand,
    *,
    codex_mode: str,
    provider_connections: list[ProviderConnection],
):
    mode = "responses" if str(codex_mode).strip().lower() == "responses" else "images"
    if command.provider_id == "codex" and not command.binding_id:
        command = replace(command, binding_id=f"codex-gpt-image-2-{mode}")
    registry = default_registry()
    providers = {provider.id: provider for provider in provider_connections}
    providers["codex"] = codex_provider_connection(codex_mode)
    resolver = BindingResolver(
        models={model.id: model for model in list_model_manifests()},
        providers=providers,
        registry=registry,
    )
    return GenerationService(resolver, registry).preview(command)


__all__ = (
    "codex_provider_connection",
    "generation_command_from_form",
    "legacy_gpt_request",
    "legacy_gpt_compat_parameters",
    "LEGACY_ROUTING_FORM_FIELDS",
    "parse_parameters_json",
    "preview_generation_command",
)
