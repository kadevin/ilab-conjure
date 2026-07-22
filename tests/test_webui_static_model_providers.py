from __future__ import annotations

import json
from pathlib import Path

from tests.webui_helpers import WebUIStaticTestCase


class WebUIStaticModelProviderTests(WebUIStaticTestCase):
    def test_brand_model_and_provider_controls_are_accessible(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")

        brand = html[html.index('<div class="brand"'):html.index('id="modelFamilyOptions"')]
        family_selector = html[html.index('id="modelFamilyOptions"'):html.index('<div class="sidebar-search">')]
        nav = html[html.index('<div class="nav-actions">'):html.index('<div id="taskNotificationCenter"')]
        output = html[html.index('<div id="settingsGrid"'):html.index('<div class="field-group full-width custom-size-control">')]
        self.assertIn("iLab", brand)
        self.assertIn("CONJURE", brand)
        self.assertNotIn('modelFamilyButton', brand)
        self.assertIn('role="radiogroup"', family_selector)
        self.assertIn('data-i18n-attr="aria-label:modelSelection.family"', family_selector)
        self.assertNotIn('role="menu"', family_selector)
        self.assertIn('id="concreteModelSelect"', output)
        self.assertIn('id="concreteModelOptions"', output)
        self.assertIn('role="group"', output)
        self.assertIn('data-i18n-attr="aria-label:modelSelection.concreteModel"', output)
        self.assertNotIn('<span data-i18n="modelSelection.concreteModel">', output)
        self.assertIn('id="generationProviderSelect"', nav)
        self.assertIn('data-i18n-attr="aria-label:modelSelection.provider"', nav)
        self.assertIn('id="generationProviderSettingsButton"', nav)
        self.assertNotIn('id="authSourceGroup"', nav)

    def test_catalog_modules_are_present_in_generated_source_map(self) -> None:
        source_map = json.loads(Path("codex_image/webui/static/app.js.map").read_text(encoding="utf-8"))
        sources = source_map.get("sources") or []
        for filename in ("model-catalog.ts", "model-selection.ts", "provider-selection.ts"):
            self.assertIn(f"../frontend/src/{filename}", sources)

    def test_model_provider_copy_exists_in_all_locale_dictionaries(self) -> None:
        required = (
            "modelSelection.family",
            "modelSelection.concreteModel",
            "modelSelection.provider",
            "modelSelection.providerUnavailable",
            "modelSelection.openSettings",
            "modelSelection.codexUnavailable",
            "modelSelection.catalogUnavailable",
        )
        locale_paths = sorted(Path("codex_image/webui/frontend/src/i18n").glob("*.ts"))
        locale_paths = [path for path in locale_paths if path.name not in {"types.ts", "dictionaries.ts"}]
        self.assertEqual(13, len(locale_paths))
        for path in locale_paths:
            source = path.read_text(encoding="utf-8")
            for key in required:
                self.assertIn(f'"{key}"', source, f"{path.name} missing {key}")

    def test_visible_catalog_state_never_persists_provider_secrets(self) -> None:
        source = Path("codex_image/webui/frontend/src/model-catalog.ts").read_text(encoding="utf-8")
        self.assertIn("MODEL_SELECTION_STORAGE_KEY", source)
        self.assertIn("parameterDraftsByModel", source)
        self.assertIn("lastProviderByModel", source)
        self.assertNotIn("remote_model_id:", source)
        self.assertNotIn("base_url:", source)
        self.assertNotIn("api_key:", source)

    def test_model_switches_and_mode_switch_recompute_binding_dependent_ui(self) -> None:
        model_selection = Path("codex_image/webui/frontend/src/model-selection.ts").read_text(encoding="utf-8")
        form_controls = Path("codex_image/webui/frontend/src/form-controls.ts").read_text(encoding="utf-8")
        self.assertGreaterEqual(model_selection.count("updateModeSpecificSettings"), 2)
        concrete_switch = model_selection[
            model_selection.index("export function selectConcreteModel"):
            model_selection.index("export function renderModelSelectors")
        ]
        self.assertIn("migratePortableModelDraft", concrete_switch)
        self.assertIn("const familyChanged = sourceModel?.family_id !== model.family_id;", concrete_switch)
        self.assertIn("if (familyChanged) renderModelSelectors();", concrete_switch)
        self.assertIn("else updateConcreteModelSelection(model.id);", concrete_switch)
        selector_render = model_selection[
            model_selection.index("export function renderModelSelectors"):
            model_selection.index("export function handleModelFamilyOptionsKeydown")
        ]
        self.assertIn('closest(".concrete-model-field")', selector_render)
        self.assertIn('classList.toggle("hidden", !expanded)', selector_render)
        self.assertIn('bridge.methods.updateModeSpecificSettings?.();', form_controls)
        self.assertIn('bridge.methods.updateRequestPreview?.();', form_controls)

    def test_model_family_selection_keeps_radio_focus_after_re_rendering(self) -> None:
        selection = Path("codex_image/webui/frontend/src/model-selection.ts").read_text(encoding="utf-8")
        switch = selection[
            selection.index("export function selectModelFamily"):
            selection.index("export function selectConcreteModel")
        ]

        self.assertIn("focusFamilyOption(familyId)", switch)
        self.assertNotIn("shouldRestoreFamilyFocus", switch)

    def test_model_parameter_drafts_are_saved_and_restored_by_control_events(self) -> None:
        form_controls = Path("codex_image/webui/frontend/src/form-controls.ts").read_text(encoding="utf-8")
        model_selection = Path("codex_image/webui/frontend/src/model-selection.ts").read_text(encoding="utf-8")
        self.assertIn("saveCurrentModelParameterDraft", form_controls)
        self.assertIn('addEventListener("change"', form_controls)
        self.assertGreaterEqual(model_selection.count("restoreCurrentModelParameterDraft"), 2)
        preset_block = form_controls[form_controls.index("[els.resolution, els.ratio, els.orientation]"):form_controls.index("els.sizeModeGroup")]
        self.assertGreaterEqual(preset_block.count("saveCurrentModelParameterDraft"), 2)

    def test_programmatic_size_actions_persist_the_active_model_draft(self) -> None:
        source = Path("codex_image/webui/frontend/src/custom-size-controls.ts").read_text(encoding="utf-8")
        main = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")
        size_mode = source[source.index("export function setCustomSizeMode"):source.index("export function swapCustomSizeDimensions")]
        swap = source[source.index("export function swapCustomSizeDimensions"):source.index("export function sanitizeCustomRatioInput")]
        first_image = source[source.index("export async function applyFirstReferenceImageAspectRatio"):source.index("export function handleCustomDimensionInput")]
        for block in (size_mode, swap, first_image):
            self.assertIn("saveCurrentModelParameterDraft", block)
        self.assertIn('import { initModelParameterDraftFeature } from "./model-parameter-drafts";', main)
        self.assertIn("initModelParameterDraftFeature();", main)

    def test_provider_settings_button_has_only_one_listener(self) -> None:
        bindings = Path("codex_image/webui/frontend/src/event-bindings.ts").read_text(encoding="utf-8")
        self.assertEqual(bindings.count('generationProviderSettingsButton?.addEventListener("click"'), 1)
        self.assertIn('call(methods, "openGenerationProviderSettings")', bindings)
        self.assertNotIn('apiSourceSettingsButton?.addEventListener("click"', bindings)

    def test_brand_accessible_name_is_not_fixed_to_gpt(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        brand = html[html.index('<div class="brand"'):html.index('id="modelFamilyOptions"')]
        self.assertIn('aria-label="iLab CONJURE"', brand)
        self.assertNotIn('aria-label="iLab GPT CONJURE"', brand)

    def test_legacy_provider_and_codex_mode_compatibility_recompute_catalog_selection(self) -> None:
        source = Path("codex_image/webui/frontend/src/api-provider-settings.ts").read_text(encoding="utf-8")
        provider_block = source[source.index("export function selectApiProvider"):source.index("export function apiModeLabel")]
        codex_block = source[source.index("export function selectCodexMode"):source.index("export function queueApiSettingsAutosave")]
        for block in (provider_block, codex_block):
            self.assertIn("renderProviderSelection", block)
            self.assertIn("updateModeSpecificSettings", block)
            self.assertIn("updateRequestPreview", block)

    def test_codex_protocols_are_top_level_binding_choices_and_provider_emoji_is_structured(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        selection = Path("codex_image/webui/frontend/src/provider-selection.ts").read_text(encoding="utf-8")
        request = Path("codex_image/webui/frontend/src/generation-request.ts").read_text(encoding="utf-8")

        self.assertNotIn('id="systemSettingsCodexTab"', html)
        self.assertNotIn('id="systemSettingsCodexPanel"', html)
        self.assertIn('id="apiProviderIconEmoji"', html)
        self.assertIn('form.append("binding_id", selection.bindingId)', request)
        self.assertIn('option.dataset.optionIcon = "/static/brand/codex-channel-mark.svg"', selection)
        self.assertIn("entry.provider.icon_emoji", selection)
