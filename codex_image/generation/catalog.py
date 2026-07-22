from __future__ import annotations

from .types import (
    InputConstraints,
    ModelFamily,
    ModelManifest,
    ObjectChoiceRow,
    ObjectPreset,
    ParameterCondition,
    ParameterDefinition,
)

MODEL_MANIFEST_VERSION = 1

_ALL_OPERATIONS = frozenset({"generate", "edit"})
_GENERATE_ONLY = frozenset({"generate"})
_NANO_COMMON_ASPECT_RATIOS = (
    "1:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "4:5",
    "5:4",
    "9:16",
    "16:9",
    "21:9",
)
_GEMINI_SAFETY_THRESHOLDS = (
    "HARM_BLOCK_THRESHOLD_UNSPECIFIED",
    "OFF",
    "BLOCK_NONE",
    "BLOCK_ONLY_HIGH",
    "BLOCK_MEDIUM_AND_ABOVE",
    "BLOCK_LOW_AND_ABOVE",
)
_GEMINI_SAFETY_THRESHOLD_LABEL_KEYS = (
    "gemini.safety.threshold.unspecified",
    "gemini.safety.threshold.off",
    "gemini.safety.threshold.blockNone",
    "gemini.safety.threshold.blockOnlyHigh",
    "gemini.safety.threshold.blockMediumAndAbove",
    "gemini.safety.threshold.blockLowAndAbove",
)
_GEMINI_SAFETY_CATEGORIES = (
    ("HARM_CATEGORY_HARASSMENT", "gemini.safety.harassment"),
    ("HARM_CATEGORY_HATE_SPEECH", "gemini.safety.hateSpeech"),
    ("HARM_CATEGORY_SEXUALLY_EXPLICIT", "gemini.safety.sexuallyExplicit"),
    ("HARM_CATEGORY_DANGEROUS_CONTENT", "gemini.safety.dangerousContent"),
)
_GEMINI_SAFETY_ROWS = tuple(
    ObjectChoiceRow(
        key=category,
        label_key=label_key,
        default="HARM_BLOCK_THRESHOLD_UNSPECIFIED",
        allowed_values=_GEMINI_SAFETY_THRESHOLDS,
        label_keys=_GEMINI_SAFETY_THRESHOLD_LABEL_KEYS,
    )
    for category, label_key in _GEMINI_SAFETY_CATEGORIES
)
_GEMINI_SAFETY_OFF = {
    category: "OFF" for category, _label_key in _GEMINI_SAFETY_CATEGORIES
}
_GEMINI_SAFETY_BLOCK_ALL = {
    category: "BLOCK_LOW_AND_ABOVE"
    for category, _label_key in _GEMINI_SAFETY_CATEGORIES
}
_GEMINI_SAFETY_PRESETS = (
    ObjectPreset(
        id="off",
        label_key="gemini.safety.threshold.off",
        value=_GEMINI_SAFETY_OFF,
        matches_empty=True,
    ),
    ObjectPreset(
        id="block_all",
        label_key="gemini.safety.threshold.blockLowAndAbove",
        value=_GEMINI_SAFETY_BLOCK_ALL,
    ),
)

MODEL_FAMILIES = (
    ModelFamily("gpt-image", "GPT Image", "GPT", "modelFamily.gptImage"),
    ModelFamily("gemini-image", "Gemini", "Gemini", "modelFamily.gemini"),
)


def _output_count(maximum: int = 4, *, control: str = "number") -> ParameterDefinition:
    return ParameterDefinition(
        id="output.count",
        label_key="output.quantity",
        group="generation",
        control=control,
        value_type="integer",
        default=1,
        allowed_values=tuple(range(1, maximum + 1)) if control == "segmented" else (),
        scope="application",
        minimum=1,
        maximum=maximum,
        step=1,
    )


def _select(
    parameter_id: str,
    label_key: str,
    group: str,
    default: str,
    allowed_values: tuple[str, ...],
    *,
    control: str = "select",
    full_width: bool = False,
) -> ParameterDefinition:
    return ParameterDefinition(
        id=parameter_id,
        label_key=label_key,
        group=group,
        control=control,
        value_type="string",
        default=default,
        allowed_values=allowed_values,
        full_width=full_width,
    )


def _toggle(parameter_id: str, label_key: str, *, group: str = "advanced") -> ParameterDefinition:
    return ParameterDefinition(
        id=parameter_id,
        label_key=label_key,
        group=group,
        control="toggle",
        value_type="boolean",
        default=False,
    )


def _boolean_segmented(
    parameter_id: str,
    label_key: str,
    *,
    group: str = "advanced",
) -> ParameterDefinition:
    return ParameterDefinition(
        id=parameter_id,
        label_key=label_key,
        group=group,
        control="boolean_segmented",
        value_type="boolean",
        default=False,
    )


def _object_presets(
    parameter_id: str,
    label_key: str,
    rows: tuple[ObjectChoiceRow, ...],
    presets: tuple[ObjectPreset, ...],
    default: dict[str, str],
    *,
    group: str = "advanced",
    full_width: bool = True,
) -> ParameterDefinition:
    return ParameterDefinition(
        id=parameter_id,
        label_key=label_key,
        group=group,
        control="object_presets",
        value_type="object",
        default=default,
        full_width=full_width,
        object_choices=rows,
        object_presets=presets,
    )


def _nano_parameters(
    resolutions: tuple[str, ...],
    aspect_ratios: tuple[str, ...],
    *,
    google_search: bool,
) -> tuple[ParameterDefinition, ...]:
    parameters = [
        _select(
            "canvas.aspect_ratio",
            "canvas.aspectRatio",
            "canvas",
            "1:1",
            aspect_ratios,
            control="aspect_ratio_grid",
            full_width=True,
        ),
        _select(
            "canvas.resolution",
            "canvas.resolution",
            "canvas",
            "1K",
            resolutions,
            control="segmented",
        ),
        _output_count(control="segmented"),
        _object_presets(
            "gemini.safety_settings",
            "gemini.safetySettings",
            _GEMINI_SAFETY_ROWS,
            _GEMINI_SAFETY_PRESETS,
            _GEMINI_SAFETY_OFF,
            group="generation",
            full_width=False,
        ),
    ]
    if google_search:
        parameters.append(
            _boolean_segmented(
                "gemini.google_search",
                "gemini.googleSearch",
                group="generation",
            )
        )
    return tuple(parameters)


MODEL_MANIFESTS = (
    ModelManifest(
        id="gpt-image-2",
        family_id="gpt-image",
        display_name="GPT Image 2",
        official_model_id="gpt-image-2",
        version=MODEL_MANIFEST_VERSION,
        operations=_ALL_OPERATIONS,
        parameters=(
            # Empty allowed_values permits custom sizes only after the GPT-specific
            # size validator applies the compound dimension rules (Task 9 boundary).
            ParameterDefinition(
                id="canvas.size",
                label_key="output.size",
                group="canvas",
                control="text",
                value_type="string",
                default="1024x1024",
                full_width=True,
            ),
            _select(
                "gpt.quality",
                "output.quality",
                "generation",
                "auto",
                ("auto", "low", "medium", "high"),
                control="segmented",
            ),
            _select(
                "gpt.background",
                "output.background",
                "generation",
                "auto",
                ("auto", "transparent", "opaque"),
                control="segmented",
            ),
            _select(
                "output.format",
                "output.format",
                "generation",
                "png",
                ("png", "jpeg", "webp"),
                control="segmented",
            ),
            _select(
                "gpt.moderation",
                "output.moderation",
                "advanced",
                "auto",
                ("auto", "low"),
                control="segmented",
            ),
            ParameterDefinition(
                id="gpt.output_compression",
                label_key="output.compression",
                group="advanced",
                control="slider",
                value_type="integer",
                default=80,
                minimum=0,
                maximum=100,
                step=1,
                visible_when=(ParameterCondition("output.format", "in", ("jpeg", "webp")),),
            ),
            _toggle("gpt.web_search", "output.webSearch"),
            _output_count(),
        ),
        input_constraints=InputConstraints(
            max_images=16,
            supports_mask=True,
            supports_reference_files=True,
        ),
    ),
    ModelManifest(
        id="nano-banana-pro",
        family_id="gemini-image",
        display_name="Nano Banana Pro",
        official_model_id="gemini-3-pro-image",
        version=MODEL_MANIFEST_VERSION,
        operations=_ALL_OPERATIONS,
        parameters=_nano_parameters(
            ("1K", "2K", "4K"),
            _NANO_COMMON_ASPECT_RATIOS,
            google_search=True,
        ),
        input_constraints=InputConstraints(
            max_images=14,
            supports_mask=False,
            supports_reference_files=False,
        ),
        expand_advanced_parameters=True,
    ),
    ModelManifest(
        id="nano-banana-2",
        family_id="gemini-image",
        display_name="Nano Banana 2",
        official_model_id="gemini-3.1-flash-image",
        version=MODEL_MANIFEST_VERSION,
        operations=_ALL_OPERATIONS,
        parameters=_nano_parameters(
            ("512", "1K", "2K", "4K"),
            _NANO_COMMON_ASPECT_RATIOS + ("1:4", "1:8", "4:1", "8:1"),
            google_search=True,
        ),
        input_constraints=InputConstraints(
            max_images=14,
            supports_mask=False,
            supports_reference_files=False,
        ),
        expand_advanced_parameters=True,
    ),
    ModelManifest(
        id="nano-banana-2-lite",
        family_id="gemini-image",
        display_name="Nano Banana 2 Lite",
        official_model_id="gemini-3.1-flash-lite-image",
        version=MODEL_MANIFEST_VERSION,
        operations=_ALL_OPERATIONS,
        parameters=_nano_parameters(
            ("1K",),
            _NANO_COMMON_ASPECT_RATIOS,
            google_search=False,
        ),
        input_constraints=InputConstraints(
            max_images=14,
            supports_mask=False,
            supports_reference_files=False,
        ),
        expand_advanced_parameters=True,
    ),
)

MODEL_MANIFESTS_BY_ID = {model.id: model for model in MODEL_MANIFESTS}


def list_model_families() -> tuple[ModelFamily, ...]:
    return MODEL_FAMILIES


def list_model_manifests() -> tuple[ModelManifest, ...]:
    return MODEL_MANIFESTS


def get_model_manifest(model_id: str) -> ModelManifest:
    try:
        return MODEL_MANIFESTS_BY_ID[model_id]
    except KeyError as exc:
        raise KeyError(f"Unknown image model: {model_id}") from exc


def manifests_for_family(family_id: str) -> tuple[ModelManifest, ...]:
    return tuple(model for model in MODEL_MANIFESTS if model.family_id == family_id)
