from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from codex_image.generation.types import (
    GenerationCommand,
    GenerationOperation,
    GenerationResult,
    ModelManifest,
)


@dataclass(frozen=True)
class ProviderModelBinding:
    id: str
    provider_id: str
    canonical_model_id: str
    remote_model_id: str
    protocol_profile: str
    parameter_codec: str
    operations: frozenset[GenerationOperation]
    is_default: bool = False
    append_aspect_ratio_prompt: bool = False


@dataclass(frozen=True)
class ProviderConnection:
    id: str
    name: str
    base_url: str
    api_key: str
    concurrency: int
    bindings: tuple[ProviderModelBinding, ...]
    builtin: bool = False

    def __post_init__(self) -> None:
        claimed_operations: set[tuple[str, GenerationOperation]] = set()
        for binding in self.bindings:
            if binding.provider_id != self.id:
                raise ValueError(
                    f"Provider binding {binding.id} belongs to {binding.provider_id}, not {self.id}"
                )
            for operation in binding.operations:
                claim = (binding.canonical_model_id, operation)
                if claim in claimed_operations and not self.builtin:
                    raise ValueError(
                        "ambiguous provider binding: "
                        f"{self.id}/{binding.canonical_model_id}/{operation}"
                    )
                claimed_operations.add(claim)


@dataclass(frozen=True)
class ProtocolRequest:
    method: str
    path: str
    content_type: str
    json_body: Mapping[str, Any] | None = None
    form_fields: Mapping[str, Any] = field(default_factory=dict)
    files: tuple[tuple[str, str, str, bytes], ...] = ()
    repeat_count: int = 1


@dataclass(frozen=True)
class ExecutionPlan:
    command: GenerationCommand
    model: ModelManifest
    provider: ProviderConnection
    binding: ProviderModelBinding
    protocol_request: ProtocolRequest


class ParameterCodec(Protocol):
    def mapped_parameter_ids(
        self,
        model: ModelManifest,
        operation: GenerationOperation,
    ) -> frozenset[str]:
        raise NotImplementedError

    def encode(
        self,
        command: GenerationCommand,
        model: ModelManifest,
        binding: ProviderModelBinding,
    ) -> ProtocolRequest:
        raise NotImplementedError


class ProtocolAdapter(Protocol):
    def execute(self, plan: ExecutionPlan) -> GenerationResult:
        raise NotImplementedError
