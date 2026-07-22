from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from codex_image.generation.catalog import get_model_manifest
from codex_image.generation.errors import provider_error
from codex_image.generation.resolver import validate_command_inputs
from codex_image.generation.service import redacted_protocol_request
from codex_image.generation.types import GenerationCommand
from codex_image.providers.contracts import (
    ExecutionPlan,
    ProtocolRequest,
    ProviderConnection,
    ProviderModelBinding,
)
from codex_image.providers.registry import ProviderRegistry


SNAPSHOT_SCHEMA_VERSION = 1


def _request_dict(request: ProtocolRequest) -> dict[str, Any]:
    def without_prompt(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                str(key): ("<redacted prompt>" if str(key).lower() in {"prompt", "instructions", "input", "text"} else without_prompt(item))
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [without_prompt(item) for item in value]
        return value

    return {
        "method": request.method,
        "path": request.path,
        "content_type": request.content_type,
        "json_body": without_prompt(request.json_body),
        "form_fields": without_prompt(request.form_fields),
        "files": [
            {"field": field, "filename": filename, "mime_type": mime_type, "data": "<redacted>"}
            for field, filename, mime_type, _ in request.files
        ],
        "repeat_count": request.repeat_count,
    }


def generation_snapshot(plan: ExecutionPlan) -> dict[str, Any]:
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "family_id": plan.model.family_id,
        "canonical_model_id": plan.model.id,
        "model_manifest_version": plan.model.version,
        "provider_id": plan.provider.id,
        "provider_name": plan.provider.name,
        "provider_base_url": plan.provider.base_url,
        "provider_concurrency": plan.provider.concurrency,
        "binding_id": plan.binding.id,
        "remote_model_id": plan.binding.remote_model_id,
        "protocol_profile": plan.binding.protocol_profile,
        "parameter_codec": plan.binding.parameter_codec,
        "binding_operations": sorted(plan.binding.operations),
        "append_aspect_ratio_prompt": plan.binding.append_aspect_ratio_prompt,
        "requested_parameters": dict(plan.command.parameters),
        "mapped_request": _request_dict(redacted_protocol_request(plan)),
    }
    if plan.command.legacy_compat_parameters:
        snapshot["legacy_compat_parameters"] = dict(plan.command.legacy_compat_parameters)
    return snapshot


def provider_binding_from_snapshot(snapshot: Mapping[str, Any]) -> ProviderModelBinding:
    return ProviderModelBinding(
        id=str(snapshot["binding_id"]),
        provider_id=str(snapshot["provider_id"]),
        canonical_model_id=str(snapshot["canonical_model_id"]),
        remote_model_id=str(snapshot["remote_model_id"]),
        protocol_profile=str(snapshot["protocol_profile"]),
        parameter_codec=str(snapshot["parameter_codec"]),
        operations=frozenset(str(item) for item in snapshot.get("binding_operations") or ()),
        append_aspect_ratio_prompt=bool(snapshot.get("append_aspect_ratio_prompt", False)),
    )


def provider_connection_from_snapshot(
    snapshot: Mapping[str, Any], *, api_key: str
) -> ProviderConnection:
    binding = provider_binding_from_snapshot(snapshot)
    return ProviderConnection(
        id=str(snapshot["provider_id"]),
        name=str(snapshot["provider_name"]),
        base_url=str(snapshot["provider_base_url"]),
        api_key=api_key,
        concurrency=int(snapshot["provider_concurrency"]),
        bindings=(binding,),
        builtin=str(snapshot["provider_id"]) == "codex",
    )


def execution_plan_from_snapshot(
    *,
    snapshot: Mapping[str, Any],
    command: GenerationCommand,
    api_key: str,
    registry: ProviderRegistry,
) -> ExecutionPlan:
    identity = {
        "provider_id": str(snapshot.get("provider_id") or ""),
        "canonical_model_id": str(snapshot.get("canonical_model_id") or ""),
        "protocol_profile": str(snapshot.get("protocol_profile") or ""),
    }
    try:
        if int(snapshot.get("schema_version") or 0) != SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("unsupported snapshot schema")
        model = get_model_manifest(identity["canonical_model_id"])
        if int(snapshot.get("model_manifest_version") or 0) != model.version:
            raise ValueError("manifest version changed")
        binding = provider_binding_from_snapshot(snapshot)
        if command.canonical_model_id != model.id or command.provider_id != binding.provider_id:
            raise ValueError("command identity changed")
        if dict(command.parameters) != dict(snapshot.get("requested_parameters") or {}):
            raise ValueError("command parameters changed")
        if dict(command.legacy_compat_parameters) != dict(snapshot.get("legacy_compat_parameters") or {}):
            raise ValueError("legacy compatibility parameters changed")
        validate_command_inputs(command, model)
        provider = provider_connection_from_snapshot(snapshot, api_key=api_key)
        registry.protocol(binding.protocol_profile)
        codec = registry.codec(binding.parameter_codec)
        request = codec.encode(command, model, binding)
        return ExecutionPlan(command, model, provider, binding, request)
    except Exception as exc:
        if getattr(exc, "detail", None) is not None:
            raise
        raise provider_error(
            "snapshot_manifest_incompatible",
            **identity,
            status_code=400,
            retryable=False,
        ) from exc


__all__ = (
    "SNAPSHOT_SCHEMA_VERSION",
    "execution_plan_from_snapshot",
    "generation_snapshot",
    "provider_binding_from_snapshot",
    "provider_connection_from_snapshot",
)
