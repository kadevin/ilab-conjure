from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from codex_image.client_types import ResponsesInputFile

GenerationOperation = Literal["generate", "edit"]
ParameterControl = Literal[
    "select",
    "segmented",
    "boolean_segmented",
    "toggle",
    "slider",
    "number",
    "text",
    "notice",
    "choice_grid",
    "object_presets",
    "aspect_ratio_grid",
]


@dataclass(frozen=True)
class ModelFamily:
    id: str
    display_name: str
    short_name: str
    label_key: str


@dataclass(frozen=True)
class ParameterCondition:
    parameter_id: str
    operator: Literal["equals", "not_equals", "in"]
    value: Any


@dataclass(frozen=True)
class ObjectChoiceRow:
    key: str
    label_key: str
    default: str
    allowed_values: tuple[str, ...]
    label_keys: tuple[str, ...]


@dataclass(frozen=True)
class ObjectPreset:
    id: str
    label_key: str
    value: Mapping[str, object]
    matches_empty: bool = False


@dataclass(frozen=True)
class ParameterDefinition:
    id: str
    label_key: str
    group: Literal["model", "canvas", "generation", "advanced"]
    control: ParameterControl
    value_type: Literal["string", "integer", "boolean", "object"]
    default: Any
    allowed_values: tuple[Any, ...] = ()
    scope: Literal["application", "model"] = "model"
    minimum: int | float | None = None
    maximum: int | float | None = None
    step: int | float | None = None
    visible_when: tuple[ParameterCondition, ...] = ()
    operations: frozenset[GenerationOperation] = frozenset({"generate", "edit"})
    full_width: bool = False
    object_choices: tuple[ObjectChoiceRow, ...] = ()
    object_presets: tuple[ObjectPreset, ...] = ()


@dataclass(frozen=True)
class InputConstraints:
    max_images: int
    supports_mask: bool
    supports_reference_files: bool


@dataclass(frozen=True)
class ModelManifest:
    id: str
    family_id: str
    display_name: str
    official_model_id: str
    version: int
    operations: frozenset[GenerationOperation]
    parameters: tuple[ParameterDefinition, ...]
    input_constraints: InputConstraints
    expand_advanced_parameters: bool = False

    def parameter(self, parameter_id: str) -> ParameterDefinition:
        for definition in self.parameters:
            if definition.id == parameter_id:
                return definition
        raise KeyError(parameter_id)


@dataclass(frozen=True)
class ImageInput:
    data_url: str
    role: str | None = None


@dataclass(frozen=True)
class GenerationCommand:
    operation: GenerationOperation
    canonical_model_id: str
    provider_id: str
    prompt: str
    parameters: Mapping[str, Any]
    binding_id: str | None = None
    image_inputs: tuple[ImageInput, ...] = ()
    reference_files: tuple[ResponsesInputFile, ...] = ()
    mask_image: str | None = None
    main_model: str | None = None
    instructions: str | None = None
    # Legacy-only transport options which are intentionally outside the
    # canonical model manifest. Canonical submissions must leave this empty.
    legacy_compat_parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GeneratedAsset:
    image_bytes: bytes
    mime_type: str
    width: int | None = None
    height: int | None = None
    revised_prompt: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GenerationResult:
    assets: tuple[GeneratedAsset, ...]
    text_parts: tuple[str, ...] = ()
    usage: Mapping[str, Any] = field(default_factory=dict)
    provider_metadata: Mapping[str, Any] = field(default_factory=dict)
