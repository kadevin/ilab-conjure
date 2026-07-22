from __future__ import annotations

from pathlib import Path

from tests.webui_helpers import WebUIStaticTestCase


class ModelParameterFrontendContractTests(WebUIStaticTestCase):
    def test_parameter_renderer_is_manifest_driven_and_closed(self) -> None:
        source = Path("codex_image/webui/frontend/src/model-parameters.ts").read_text(encoding="utf-8")

        self.assertIn("PARAMETER_RENDERERS", source)
        for control in ("select", "segmented", "boolean_segmented", "toggle", "slider", "number", "text", "notice", "choice_grid", "object_presets", "aspect_ratio_grid"):
            self.assertIn(f"{control}:", source)
        self.assertIn("textContent", source)
        self.assertNotIn("innerHTML", source)
        self.assertNotIn("insertAdjacentHTML", source)

    def test_output_panel_has_separate_composer_and_history_parameter_surfaces(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")

        self.assertIn('id="modelParameterGrid"', html)
        self.assertIn('id="taskParameterInspector"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn(".model-parameter-grid", styles)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", styles)
        self.assertIn("min-width: 0", styles)
        self.assertIn(".model-parameter-grid", responsive)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", responsive)

    def test_dynamic_parameters_reuse_compact_interactions_without_duplicate_values(self) -> None:
        source = Path("codex_image/webui/frontend/src/model-parameters.ts").read_text(encoding="utf-8")
        indicators = Path("codex_image/webui/frontend/src/segmented-indicator.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")

        self.assertIn("model-parameter-segmented-multiline", source)
        self.assertIn("model-parameter-choice-grid", source)
        self.assertIn("advancedParametersAreExpanded", source)
        self.assertIn("legacyParameterVisibility", source)
        self.assertIn("state.customSizeTransitionSeq += 1", source)
        self.assertIn("parameterAffectsVisibility", source)
        self.assertIn("renderInteractiveParameterDefinitionsInto", source)
        self.assertIn("parameterRenderFingerprint", source)
        self.assertIn("dataset.renderFingerprint", source)
        self.assertIn("interactiveModel", source)
        self.assertIn("refreshSegmentedIndicators()", source)
        self.assertIn('translate("apiSettings.advancedSettings")', source)
        self.assertIn("if (slider) field.append(input, output, error)", source)
        self.assertIn(":not(.model-parameter-segmented-multiline)", indicators)
        self.assertIn("initHost(host)", indicators)
        self.assertIn(".model-parameter-segmented-multiline", styles)
        self.assertIn(".model-parameter-advanced", styles)
        self.assertIn("model-parameter-advanced-grid-expanded", source)
        self.assertIn("repeat(auto-fit, minmax(156px, 1fr))", styles)
        self.assertIn(".model-parameter-advanced-grid-expanded > .full-width", styles)
        self.assertIn(".model-parameter-advanced-grid:not(.model-parameter-advanced-grid-expanded)", responsive)
        self.assertIn("@container workspace (max-width: 520px)", responsive)
        self.assertIn(".model-parameter-advanced-grid-expanded", responsive)
        self.assertIn("#apiDirectSettingsNotice .api-direct-settings-header span", responsive)
        self.assertIn("#apiDirectSettingsNotice .api-direct-settings-button > span", responsive)

    def test_collapsed_custom_size_has_no_minimum_height(self) -> None:
        styles = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")

        collapsed = styles.split(".custom-size.custom-size-collapsed {", 1)[1].split("}", 1)[0]
        self.assertIn("min-height: 0", collapsed)
        self.assertIn("max-height: 0", collapsed)

    def test_safety_presets_and_aspect_ratios_use_accessible_manifest_renderers(self) -> None:
        parameters = Path("codex_image/webui/frontend/src/model-parameters.ts").read_text(encoding="utf-8")
        ratios = Path("codex_image/webui/frontend/src/aspect-ratio-controls.ts").read_text(encoding="utf-8")
        main = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")

        self.assertIn("renderObjectPresets", parameters)
        self.assertIn("renderAspectRatioGrid", parameters)
        self.assertIn("matchingObjectPreset", parameters)
        self.assertIn('setAttribute("aria-pressed"', parameters)
        self.assertIn("createAspectRatioIcon", ratios)
        self.assertIn('setAttribute("aria-hidden", "true")', ratios)
        self.assertIn("decorateLegacyAspectRatioButtons", ratios)
        self.assertIn("initAspectRatioControlsFeature", main)
        self.assertIn(".model-aspect-ratio-grid", styles)
        self.assertIn(".aspect-ratio-slot", styles)

    def test_boolean_segmented_parameters_use_full_cell_accessible_choices(self) -> None:
        parameters = Path("codex_image/webui/frontend/src/model-parameters.ts").read_text(encoding="utf-8")
        catalog = Path("codex_image/webui/frontend/src/model-catalog.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")

        self.assertIn("renderBooleanSegmented", parameters)
        self.assertIn('translate("output.lock.disabled")', parameters)
        self.assertIn('translate("output.lock.enabled")', parameters)
        self.assertIn('setAttribute("aria-pressed"', parameters)
        self.assertIn('"boolean_segmented"', catalog)
        self.assertIn('item.control !== "boolean_segmented" || item.value_type === "boolean"', catalog)
        self.assertIn(".model-parameter-boolean-segmented", styles)
        boolean_segmented = styles.split(".model-parameter-boolean-segmented", 1)[1].split("}", 1)[0]
        self.assertIn("width: 100%", boolean_segmented)
        boolean_buttons = styles.split(".model-parameter-boolean-segmented .radio-btn", 1)[1].split("}", 1)[0]
        self.assertIn("min-height: 34px", boolean_buttons)

    def test_canonical_generation_request_uses_sorted_parameter_json(self) -> None:
        source = Path("codex_image/webui/frontend/src/generation-request.ts").read_text(encoding="utf-8")

        self.assertIn("appendCanonicalGenerationFields", source)
        self.assertIn('form.append("canonical_model_id"', source)
        self.assertIn('form.append("provider_id"', source)
        self.assertIn('form.append("parameters_json"', source)
        self.assertIn("Object.keys", source)
        self.assertIn(".sort()", source)
