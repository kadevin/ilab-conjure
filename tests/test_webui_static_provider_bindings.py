from __future__ import annotations

from pathlib import Path
import re
import unittest


class WebUIStaticProviderBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = Path(
            "codex_image/webui/frontend/src/provider-model-bindings.ts"
        )
        self.provider_editor = Path(
            "codex_image/webui/frontend/src/api-provider-settings.ts"
        ).read_text(encoding="utf-8")
        self.html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        self.styles = Path(
            "codex_image/webui/static/styles/74-api-system-settings.css"
        ).read_text(encoding="utf-8")
        self.modal_styles = Path(
            "codex_image/webui/static/styles/72-queue-modals.css"
        ).read_text(encoding="utf-8")

    def test_binding_editor_has_three_direct_protocols_with_explicit_model_mapping(self) -> None:
        source = self.module.read_text(encoding="utf-8")
        expected = {
            "gpt_openai_images": ("openai_images", "gpt_openai_images"),
            "gpt_openai_responses": ("openai_responses", "gpt_openai_responses"),
            "gemini_generate_content": ("gemini_generate_content", "gemini_generate_content_image"),
            "gemini_openai_images": ("openai_images", "gemini_openai_images"),
        }
        for template, (protocol, codec) in expected.items():
            with self.subTest(template=template):
                self.assertRegex(
                    source,
                    rf"{template}:[\s\S]*?protocol_profile:\s*\"{protocol}\"[\s\S]*?parameter_codec:\s*\"{codec}\"",
                )
        self.assertIn(
            'export type BindingProtocol = "gemini" | "openai_images" | "openai_responses"',
            source,
        )
        self.assertIn("availableProtocolsForModel", source)
        self.assertIn('gemini: "Gemini"', source)
        self.assertIn('openai_images: "OpenAI Images"', source)
        self.assertIn('openai_responses: "OpenAI Responses"', source)
        self.assertNotIn("openai_compatible", source)
        self.assertNotIn("Gemini Interactions", source)
        self.assertNotIn("xAI 官方", source)
        self.assertNotIn("grok", source.lower())
        self.assertNotRegex(source, r"remote_model_id[^\n]*(includes|match|startsWith)")

    def test_provider_editor_renders_connection_and_binding_fields(self) -> None:
        for element_id in (
            "apiProviderBindings",
            "addProviderBindingButton",
        ):
            self.assertIn(f'id="{element_id}"', self.html)
        self.assertNotIn('id="apiAuthScheme"', self.html)
        self.assertNotIn('data-i18n="apiSettings.authScheme"', self.html)
        self.assertNotIn('class="field api-auth-scheme-field"', self.html)
        self.assertNotIn('id="apiModeGroup"', self.html)
        self.assertNotIn('id="apiImageModel"', self.html)
        source = self.module.read_text(encoding="utf-8")
        self.assertNotIn("BindingApiMode", source)
        self.assertNotIn("availableApiModesForModel", source)
        self.assertNotIn("dataset.bindingApiMode", source)
        self.assertNotIn("provider-binding-api-mode", source)
        self.assertNotIn("调用方式", source)

    def test_provider_summary_uses_model_binding_language_not_legacy_request_mode(self) -> None:
        self.assertIn(
            '<dt data-i18n="apiSettings.modelBindings">模型绑定</dt>',
            self.html,
        )
        self.assertNotIn('<dt data-i18n="apiSettings.mode">调用方式</dt>', self.html)
        self.assertIn('translate("apiSettings.modelBindings")', self.provider_editor)
        self.assertNotRegex(self.provider_editor, r'`\$\{provider\?\.bindings\?\.length \|\| 0\} bindings`')
        self.assertNotRegex(self.provider_editor, r'`\$\{bindingCount\} binding')

    def test_binding_cards_freeze_legacy_protocol_until_user_changes_it(self) -> None:
        source = self.module.read_text(encoding="utf-8")
        for marker in (
            "bindingOriginalProtocolProfile",
            "bindingOriginalParameterCodec",
            "bindingProtocolChanged",
        ):
            self.assertIn(marker, source)

    def test_binding_cards_are_responsive_and_remote_model_cannot_widen_modal(self) -> None:
        self.assertRegex(
            self.styles,
            r"\.provider-binding-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(0,\s*1fr\)",
        )
        self.assertRegex(
            self.styles,
            r"\.provider-binding-remote-model\s*\{[^}]*min-width:\s*0[^}]*grid-column:\s*auto",
        )
        source = self.module.read_text(encoding="utf-8")
        self.assertIn('compatibilityLabel.textContent = "兼容层"', source)
        self.assertIn('compatibilitySelect.dataset.bindingCompatibility = ""', source)
        self.assertRegex(
            source,
            r"grid\.append\(modelField,\s*protocolField,\s*remoteField,\s*compatibilityField,\s*footer\)",
        )
        self.assertRegex(
            self.styles,
            r"\.provider-binding-compatibility\s*\{[^}]*min-width:\s*0[^}]*grid-column:\s*auto",
        )
        self.assertRegex(
            self.styles,
            r"@media \(max-width:\s*620px\)[\s\S]*?\.provider-binding-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)",
        )
        self.assertRegex(
            self.styles,
            r"@media \(max-width:\s*520px\)[\s\S]*?"
            r"\.api-provider-detail-actions\s*\{[^}]*"
            r"grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)",
        )
        self.assertRegex(
            self.styles,
            r"@media \(max-width:\s*520px\)[\s\S]*?"
            r"\.api-provider-detail-actions\s+\.(?:ghost-button|danger-button)[^}]*"
            r"min-width:\s*0",
        )

    def test_codex_protocols_no_longer_own_a_system_settings_tab(self) -> None:
        self.assertNotIn('id="systemSettingsCodexTab"', self.html)
        self.assertNotIn('id="systemSettingsCodexPanel"', self.html)
        self.assertIn('id="apiProviderIconEmoji"', self.html)
        self.assertIn('aria-label:apiSettings.providerIcon', self.html)

    def test_provider_editor_keeps_icon_guidance_and_actions_available_while_scrolling(self) -> None:
        dictionary = Path("codex_image/webui/frontend/src/i18n/zh-cn.ts").read_text(encoding="utf-8")

        self.assertRegex(
            self.html,
            r'class="field api-provider-name-field"[\s\S]*?'
            r'class="api-provider-name-inputs"[\s\S]*?'
            r'class="api-provider-icon-input"[\s\S]*?'
            r'<span data-i18n="apiSettings.providerIcon">Emoji 图标</span>[\s\S]*?'
            r'id="apiProviderIconEmoji"[\s\S]*?id="apiProviderName"',
        )
        self.assertIn(
            'placeholder="🪄"',
            self.html,
        )
        self.assertIn(
            'data-i18n-attr="aria-label:apiSettings.providerIcon;title:apiSettings.providerIconPlaceholder"',
            self.html,
        )
        self.assertIn('"apiSettings.providerIcon": "Emoji 图标"', dictionary)
        self.assertIn('"apiSettings.providerIconPlaceholder": "可选，例如 🪄"', dictionary)
        self.assertRegex(
            self.styles,
            r"\.api-provider-name-inputs\s*\{[^}]*display:\s*grid[^}]*"
            r"grid-template-columns:\s*minmax\(96px,\s*auto\)\s+minmax\(0,\s*1fr\)",
        )
        self.assertRegex(
            self.styles,
            r"\.api-provider-icon-input\s*\{[^}]*display:\s*grid[^}]*"
            r"grid-template-columns:\s*auto\s+24px[^}]*border:\s*1px\s+solid\s+var\(--line\)",
        )
        self.assertRegex(
            self.html,
            r'class="provider-bindings-title-row"[\s\S]*?'
            r'id="providerBindingsTitle"[\s\S]*?'
            r'id="addProviderBindingButton"\s+class="ghost-button provider-binding-add"',
        )
        self.assertNotIn('id="addProviderBindingButton" class="ghost-button text-sm"', self.html)
        self.assertRegex(
            self.styles,
            r"\.provider-binding-add\s*\{[^}]*min-height:\s*36px[^}]*font-size:\s*12px",
        )
        self.assertRegex(
            self.styles,
            r"\.api-provider-editor-actions\s*\{[^}]*position:\s*sticky[^}]*bottom:\s*0[^}]*z-index:\s*2[^}]*background:\s*var\(--surface\)[^}]*border-top:",
        )
        self.assertRegex(
            self.modal_styles,
            r"\.system-settings-section\s*\{[^}]*overflow-y:\s*auto",
        )
        self.assertRegex(
            self.styles,
            r"@media \(max-width:\s*520px\)[\s\S]*?\.api-provider-editor-actions\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)",
        )

    def test_binding_action_and_connection_preview_have_distinct_visual_roles(self) -> None:
        dictionary = Path("codex_image/webui/frontend/src/i18n/zh-cn.ts").read_text(encoding="utf-8")

        self.assertRegex(
            self.html,
            r'class="provider-bindings-connection"[\s\S]*?'
            r'data-i18n="apiSettings.connectionPreview">连接预览</span>[\s\S]*?'
            r'id="apiRequestEndpointPreview"',
        )
        self.assertIn('"apiSettings.connectionPreview": "连接预览"', dictionary)
        self.assertRegex(
            self.styles,
            r"\.provider-binding-add\s*\{[^}]*"
            r"background:\s*var\(--primary-light\)[^}]*"
            r"border-color:\s*color-mix\(in srgb,\s*var\(--primary\)",
        )
        self.assertRegex(
            self.styles,
            r"\.provider-bindings-connection\s*\{[^}]*"
            r"display:\s*grid[^}]*"
            r"grid-template-columns:\s*max-content\s+minmax\(0,\s*1fr\)[^}]*"
            r"min-height:\s*34px[^}]*"
            r"border-left:\s*3px\s+solid",
        )
        self.assertRegex(
            self.styles,
            r"\.provider-bindings-connection-label\s*\{[^}]*font-weight:\s*600",
        )
        self.assertRegex(
            self.styles,
            r"\.provider-bindings-connection code\s*\{[^}]*min-width:\s*0[^}]*text-overflow:\s*ellipsis",
        )

    def test_provider_editor_compacts_connection_fields_and_derives_binding_operations(self) -> None:
        source = self.module.read_text(encoding="utf-8")

        provider_name_field_start = self.html.index('class="field api-provider-name-field"')
        icon_input_start = self.html.index('id="apiProviderIconEmoji"')
        provider_name_input_start = self.html.index('id="apiProviderName"')
        base_url_input_start = self.html.index('id="apiBaseUrl"')

        self.assertNotIn('class="field api-provider-icon-field"', self.html)
        self.assertLess(provider_name_field_start, icon_input_start)
        self.assertLess(icon_input_start, provider_name_input_start)
        self.assertLess(provider_name_input_start, base_url_input_start)
        self.assertLess(
            self.html.index('id="apiBaseUrl"'),
            self.html.index('id="apiKey"'),
        )
        self.assertRegex(
            self.styles,
            r"\.compact-api-settings-grid\s*\{[^}]*grid-template-columns:\s*repeat\(6,\s*minmax\(0,\s*1fr\)\)",
        )
        for field, column, span, row in (
            ("api-provider-name-field", 1, 4, 1),
            ("api-concurrency-field", 5, 2, 1),
            ("api-base-url-field", 1, 3, 2),
            ("api-key-field", 4, 3, 2),
        ):
            with self.subTest(field=field):
                self.assertRegex(
                    self.styles,
                    rf"\.compact-api-settings-grid > \.{field}\s*\{{[^}}]*"
                    rf"grid-column:\s*{column}\s*/\s*span\s+{span}[^}}]*"
                    rf"grid-row:\s*{row}",
                )
        self.assertRegex(
            self.styles,
            r"\.compact-api-settings-grid > \.api-provider-name-field,[\s\S]*?\.compact-api-settings-grid > \.api-concurrency-field\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:\s*max-content\s+minmax\(0,\s*1fr\)[^}]*align-items:\s*center",
        )
        self.assertNotIn("data-binding-operation", source)
        self.assertNotIn("支持操作", source)
        self.assertNotIn('model?.operations || ["generate", "edit"]', self.provider_editor)
        self.assertIn("model?.operations || existingOperations", self.provider_editor)
        self.assertIn("provider-binding-footer", source)
        self.assertIn('ratioPromptInput.dataset.bindingRatioPrompt = ""', source)
        self.assertRegex(source, r"footerSettings\.append\(ratioPromptField,\s*defaultField\)")
        self.assertRegex(source, r"footer\.append\(footerSettings,\s*remove\)")
        self.assertRegex(
            self.styles,
            r"\.provider-binding-footer\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto[^}]*border-top:\s*1px\s+solid\s+var\(--line\)",
        )
        self.assertRegex(
            self.styles,
            r"\.provider-binding-footer-settings\s*\{[^}]*display:\s*flex[^}]*flex-wrap:\s*nowrap[^}]*gap:\s*20px",
        )
        self.assertNotIn("provider-binding-footer-actions", source)

    def test_settings_tabs_stay_above_and_outside_the_scrolling_panel_content(self) -> None:
        self.assertRegex(
            self.modal_styles,
            r"\.system-settings-modal-panel\s*\{[^}]*overflow:\s*hidden",
        )
        self.assertRegex(
            self.modal_styles,
            r"\.system-settings-tabs\s*\{[^}]*position:\s*relative[^}]*z-index:\s*2",
        )
        self.assertRegex(
            self.modal_styles,
            r"\.system-settings-section\s*\{[^}]*position:\s*relative[^}]*z-index:\s*1[^}]*overflow-y:\s*auto",
        )

    def test_provider_editor_moves_focus_before_hiding_the_focused_form(self) -> None:
        cancel_start = self.provider_editor.index(
            "export function cancelApiProviderEdit()"
        )
        cancel_end = self.provider_editor.index(
            "export function toggleApiProviderSortMode()",
            cancel_start,
        )
        cancel_source = self.provider_editor[cancel_start:cancel_end]
        focus = cancel_source.index(
            "els.systemSettingsApiTab?.focus({ preventScroll: true })"
        )
        rerender = cancel_source.index("populateApiSettingsForm()")
        self.assertLess(focus, rerender)


if __name__ == "__main__":
    unittest.main()
