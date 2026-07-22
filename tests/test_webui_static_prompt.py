from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from tests.webui_helpers import WebUIStaticTestCase


class WebUIStaticPromptTests(WebUIStaticTestCase):
    def test_color_palette_feature_has_typescript_source_contract(self) -> None:
        color_palette_source = self._color_palette_source()
        legacy_source = self._bootstrap_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertIn('import { initColorPaletteFeature } from "./color-palette"', main_source)
        self.assertLess(main_source.index("initStorageSettingsFeature()"), main_source.index("initColorPaletteFeature()"))
        self.assertLess(main_source.index("initColorPaletteFeature()"), main_source.index("initPromptFeature()"))
        self.assertIn("export function initColorPaletteFeature", color_palette_source)
        self.assertIn("const DEFAULT_COLOR_SWATCHES", color_palette_source)
        self.assertIn("const COLOR_PALETTE_ENDPOINT", color_palette_source)
        self.assertIn("function defaultColorPalette()", color_palette_source)
        self.assertIn("async function refreshColorPalette()", color_palette_source)
        self.assertIn("function normalizeHexColor(value)", color_palette_source)
        self.assertIn("Object.assign(getLegacyBridge().methods", color_palette_source)
        for function_name in [
            "defaultColorPalette",
            "normalizeColorPalette",
            "refreshColorPalette",
            "persistColorPalette",
            "importColorPalette",
            "toggleColorPaletteManageMode",
            "favoriteColorsForDisplay",
            "recentColorsForDisplay",
            "rememberRecentColor",
            "saveFavoriteColor",
            "removeFavoriteColor",
            "normalizeHexColor",
        ]:
            self.assertNotRegex(legacy_source, rf"\n(?:async\s+)?function {function_name}\(")
        for function_name in [
            "refreshColorPalette",
            "importColorPalette",
            "toggleColorPaletteManageMode",
            "favoriteColorsForDisplay",
            "recentColorsForDisplay",
            "rememberRecentColor",
            "saveFavoriteColor",
            "removeFavoriteColor",
            "normalizeHexColor",
        ]:
            self._assert_bootstrap_proxy(legacy_source, function_name)
    def test_prompt_fidelity_control_supports_original_mode_and_is_submitted(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()

        self.assertIn('id="promptFidelity"', html)
        self.assertRegex(
            html,
            r'data-val="original" type="button"[^>]*>原文</button>\s*<button class="radio-btn active" data-val="strict" type="button"[^>]*>保真</button>',
        )
        self.assertIn('value="strict" selected', html)
        self.assertIn('value="original"', html)
        self.assertIn('data-val="original"', html)
        self.assertRegex(html, r'data-val="off" type="button"[^>]*>自动</button>')
        self.assertRegex(html, r'<option value="off"[^>]*>自动</option>')
        self.assertNotIn('<option value="off">关闭</option>', html)
        self.assertIn("promptFidelity: document.querySelector", script)
        self.assertIn("function currentPromptFidelity()", script)
        self.assertIn("function currentPromptForModel()", script)
        self.assertIn('currentPromptFidelity() === "original" ? expandPromptSnippets(getPromptText()) : buildPromptForModel()', script)
        self.assertIn("prompt_fidelity: currentPromptFidelity()", script)
        self.assertIn('form.append("prompt_fidelity", currentPromptFidelity())', script)

    def test_prompt_fidelity_help_explains_each_transport_without_adding_a_layout_row(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        source = Path("codex_image/webui/frontend/src/prompt-fidelity-help.ts").read_text(encoding="utf-8")
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('data-i18n="output.promptMode">提示词处理</span>', html)
        self.assertIn('id="promptFidelityHelpButton"', html)
        self.assertIn('aria-controls="promptFidelityHelpPopover"', html)
        self.assertIn('aria-describedby="promptFidelityHelpPopover"', html)
        self.assertIn('import { initPromptFidelityHelpFeature } from "./prompt-fidelity-help"', main_source)
        self.assertIn("initPromptFidelityHelpFeature();", main_source)
        self.assertIn('return currentApiMode() === "responses" ? "responses" : "images";', source)
        self.assertIn('return currentCodexMode() === "responses" ? "responses" : "images";', source)
        self.assertIn('return `output.promptHelp.${transport}.${modeKey}`;', source)
        dictionaries = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(Path("codex_image/webui/frontend/src/i18n").glob("*.ts"))
            if path.name not in {"dictionaries.ts", "types.ts"}
        )
        for key in [
            "output.promptHelp.responses.original",
            "output.promptHelp.responses.strict",
            "output.promptHelp.responses.automatic",
            "output.promptHelp.images.original",
            "output.promptHelp.images.strict",
            "output.promptHelp.images.automatic",
        ]:
            self.assertIn(key, dictionaries)
        self.assertIn('trigger.addEventListener("pointerenter"', source)
        self.assertIn('trigger.addEventListener("focus"', source)
        self.assertIn('trigger.addEventListener("click"', source)
        self.assertIn('event.key !== "Escape"', source)
        self.assertRegex(styles, r"\.prompt-fidelity-help-popover\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.prompt-fidelity-help-popover\s*\{[^}]*z-index:\s*1400")
        self.assertRegex(styles, r"\.prompt-fidelity-help-button\s*\{[^}]*border-radius:\s*50%")
        self.assertRegex(styles, r"\.prompt-fidelity-help-button\s*\{[^}]*box-shadow:\s*none")
        self.assertRegex(
            styles,
            r"\.prompt-fidelity-help-button:hover,\s*\.prompt-fidelity-help-button:focus-visible,\s*"
            r"\.prompt-fidelity-help-button\[aria-expanded=\"true\"\]\s*\{[^}]*"
            r"background:\s*transparent[^}]*box-shadow:\s*none",
        )
        self.assertNotIn("prompt-fidelity-help-panel", html)
    def test_prompt_chip_logic_has_typescript_source_contract(self) -> None:
        prompt_source = self._prompt_source()
        core_source = "\n".join(
            [
                prompt_source,
                self._prompt_serialization_source(),
                self._prompt_gallery_chips_source(),
                self._prompt_editor_events_source(),
                self._prompt_model_source(),
            ]
        )
        legacy_source = self._bootstrap_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertNotIn("@ts-nocheck", prompt_source)
        self.assertIn('from "./prompt-serialization"', prompt_source)
        self.assertIn('from "./prompt-gallery-chips"', prompt_source)
        self.assertIn('from "./prompt-editor-events"', prompt_source)
        self.assertIn('from "./prompt-model"', prompt_source)
        for marker in [
            "export function initPromptFeature",
            "function createGalleryChip",
            "function buildPromptForModel",
            "function galleryReferenceInstruction",
            "function syncPromptGalleryMentionsFromInputs",
            "function handlePromptChipDrop",
            "function getPromptText",
            "function normalizePromptEditorText",
            "function createPromptTextFragment",
            "function setPromptWithGalleryRefs",
            "function currentPromptFidelity",
        ]:
            self.assertIn(marker, core_source)
        self.assertIn('return String(value || "").replace(/\\r\\n?/g, "\\n");', core_source)
        self.assertIn('document.createElement("br")', core_source)
        self.assertIn("document.createDocumentFragment()", core_source)
        self.assertRegex(
            core_source,
            r"function setPromptText\(text: any\): void\s*\{[\s\S]*normalizePromptEditorText\(text\)[\s\S]*createPromptTextFragment\(normalized\)",
        )
        self.assertRegex(
            core_source,
            r"function setPromptWithGalleryRefs\(text: any,\s*refs: any\): void\s*\{[\s\S]*const promptText = normalizePromptEditorText\(text\)",
        )

        for function_name in [
            "getPromptText",
            "setPromptWithGalleryRefs",
            "syncPromptFromEditor",
            "createGalleryChip",
            "createPromptSnippetChip",
            "buildPromptForModel",
            "currentPromptForModel",
            "currentPromptFidelity",
            "syncGalleryInputsFromPrompt",
            "syncPromptGalleryMentionsFromInputs",
        ]:
            self._assert_bootstrap_proxy(legacy_source, function_name)

        self.assertIn("Object.assign(getLegacyBridge().methods", core_source)
        self.assertIn('addEventListener("copy", handlePromptEditorCopy)', core_source)
        self.assertIn('addEventListener("dragstart", handlePromptChipDragStart)', core_source)
        self.assertLess(main_source.index('import "../legacy-app.js"'), main_source.index('import { initInputSourcesFeature } from "./input-sources"'))
        self.assertLess(main_source.index("initInputSourcesFeature()"), main_source.index("initImageEditorFeature()"))
        self.assertLess(main_source.index("initImageEditorFeature()"), main_source.index("initPromptFeature()"))
        self.assertLess(main_source.index("initPromptFeature()"), main_source.index("initTaskListControlsFeature()"))
        self.assertLess(main_source.index("initTaskListControlsFeature()"), main_source.index("initTaskFeature()"))
        self.assertLess(main_source.index("initTaskFeature()"), main_source.index("initializeQueueFeature()"))
    def test_prompt_colors_feature_has_typescript_source_contract(self) -> None:
        source = self._prompt_colors_source()
        prompt_source = self._prompt_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertNotIn("@ts-nocheck", source)
        self.assertIn('import { initPromptColorsFeature } from "./prompt-colors"', main_source)
        self.assertLess(main_source.index("initPromptColorsFeature()"), main_source.index("initPromptFeature()"))
        for marker in [
            "DEFAULT_COLOR_CODE",
            "COLOR_PALETTE_EXPORT_CSS_ENDPOINT",
            "export function initPromptColorsFeature",
            "function activeColorMatch",
            "function renderColorSuggest",
            "function insertColorCode",
            "function createColorChip",
            "function readableTextColor",
            "function hideColorSuggest",
        ]:
            self.assertIn(marker, source)
        for function_name in [
            "updateColorSuggest",
            "activeColorMatch",
            "renderColorSuggest",
            "bindColorSuggestEvents",
            "insertColorCode",
            "positionColorSuggestAtCaret",
            "openColorChipEditor",
            "positionColorSuggestAtChip",
            "colorNameForHex",
            "colorSwatchButton",
            "createColorChip",
            "updateColorChip",
            "readableTextColor",
            "hexToRgb",
            "mixRgbWithWhite",
            "relativeLuminance",
            "contrastRatio",
            "hideColorSuggest",
        ]:
            self.assertRegex(source, rf"\nfunction {function_name}\(")
            self.assertNotRegex(prompt_source, rf"\nfunction {function_name}\(")
        self.assertIn("Object.assign(getLegacyBridge().methods", source)
    def test_prompt_snippets_feature_has_typescript_source_contract(self) -> None:
        source = self._prompt_snippets_source()
        prompt_source = self._prompt_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertNotIn("@ts-nocheck", source)
        self.assertIn('import { initPromptSnippetsFeature } from "./prompt-snippets"', main_source)
        self.assertLess(main_source.index("initPromptSnippetsFeature()"), main_source.index("initPromptFeature()"))
        for marker in [
            "PROMPT_SNIPPETS_ENDPOINT",
            "PROMPT_SNIPPET_TRIGGER_PATTERN",
            "export function initPromptSnippetsFeature",
            "function createPromptSnippetChip",
            "function expandPromptSnippets",
            "function updatePromptSnippetSuggest",
            "function getPromptSelectionForSnippet",
            "function openPromptSnippetSavePopover",
            "function closePromptSnippetPopover",
        ]:
            self.assertIn(marker, source)
        self.assertIn('candidate.length === 1 && PROMPT_SNIPPET_TRIGGER_CHARS.includes(candidate)', source)
        for function_name in [
            "normalizePromptSnippet",
            "refreshPromptSnippets",
            "activePromptSnippetMatch",
            "insertPromptSnippet",
            "createPromptSnippetChip",
            "findPromptSnippetRefAt",
            "findPromptSnippetById",
            "findPromptSnippetByTag",
            "expandPromptSnippets",
            "updatePromptSnippetSelectionButton",
            "showPromptSnippetSelectionButton",
            "openPromptSnippetSavePopover",
            "openPromptSnippetChipPopover",
            "savePromptSnippetFromPopover",
            "closePromptSnippetPopover",
            "hidePromptSnippetSuggest",
        ]:
            self.assertRegex(source, rf"\n(?:async\s+)?function {function_name}\(")
            self.assertNotRegex(prompt_source, rf"\n(?:async\s+)?function {function_name}\(")
        self.assertIn("Object.assign(getLegacyBridge().methods", source)
    def test_prompt_templates_feature_has_typescript_source_contract(self) -> None:
        source = self._prompt_templates_source()
        prompt_source = self._prompt_source()
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")
        boot_source = Path("codex_image/webui/frontend/src/boot.ts").read_text(encoding="utf-8")
        bootstrap_source = self._bootstrap_source()

        self.assertNotIn("@ts-nocheck", source)
        self.assertIn('import { initPromptTemplatesFeature } from "./prompt-templates"', main_source)
        self.assertLess(main_source.index("initPromptSnippetsFeature()"), main_source.index("initPromptTemplatesFeature()"))
        self.assertLess(main_source.index("initPromptTemplatesFeature()"), main_source.index("initPromptFeature()"))
        self.assertIn('call(methods, "refreshPromptTemplates")', boot_source)
        self._assert_bootstrap_proxy(bootstrap_source, "refreshPromptTemplates")
        for marker in [
            "PROMPT_TEMPLATES_ENDPOINT",
            "PROMPT_TEMPLATE_CATEGORIES_ENDPOINT",
            "export function initPromptTemplatesFeature",
            "function normalizePromptTemplate",
            "function normalizePromptTemplateCategory",
            "function refreshPromptTemplates",
            "function syncPromptTemplateSearchInput",
            "function setPromptTemplateSearchLocked",
            "function guardPromptTemplateSearchInput",
            "function openPromptTemplateDrawer",
            "function renderPromptTemplateCategories",
            "function renderPromptTemplateList",
            "function historyTemplateThumbnails",
            "function renderPromptTemplateThumbnailPicker",
            "function applyPromptTemplate",
            "function importPromptTemplatePack",
            "function exportPromptTemplatePack",
            "function setPromptTemplateSummary",
            "function savePromptTemplateFromDrawer",
        ]:
            self.assertIn(marker, source)
        for function_name in [
            "normalizePromptTemplate",
            "normalizePromptTemplateCategory",
            "refreshPromptTemplates",
            "openPromptTemplateDrawer",
            "closePromptTemplateDrawer",
            "renderPromptTemplateCategories",
            "renderPromptTemplateList",
            "renderPromptTemplateRecentDock",
            "selectPromptTemplate",
            "applyPromptTemplate",
            "copyPromptTemplateContent",
            "historyTemplateThumbnails",
            "renderPromptTemplateThumbnailPicker",
            "importPromptTemplatePack",
            "exportPromptTemplatePack",
            "setPromptTemplateSummary",
            "createPromptTemplateCategory",
            "updatePromptTemplateCategory",
            "deletePromptTemplateCategory",
            "renderPromptTemplateForm",
            "savePromptTemplateFromDrawer",
            "deletePromptTemplate",
        ]:
            self.assertRegex(source, rf"\n(?:async\s+)?function {function_name}\(")
            self.assertNotRegex(prompt_source, rf"\n(?:async\s+)?function {function_name}\(")
        self.assertIn("Object.assign(getLegacyBridge().methods", source)
        overlay_source = Path("codex_image/webui/frontend/src/overlay-popovers.ts").read_text(encoding="utf-8")
        self.assertIn("function closePromptTemplateDrawer()", overlay_source)
        self.assertIn("closePromptTemplateDrawer();", overlay_source)
        self.assertIn('legacyMethod("closeGallery", { restoreFocus: false })', source)
    def test_prompt_template_library_has_compact_entry_and_drawer(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        script = self._frontend_script_source()

        prompt_section = re.search(r"<section class=\"panel prompt-panel\">[\s\S]*?</section>", html)
        self.assertIsNotNone(prompt_section)
        prompt_html = prompt_section.group(0)
        heading_html = re.search(r"<div class=\"panel-heading prompt-heading\">[\s\S]*?</div>", prompt_html)
        self.assertIsNotNone(heading_html)
        self.assertRegex(heading_html.group(0), r"<div class=\"prompt-heading-main\">[\s\S]*<h2[^>]*>提示词</h2>[\s\S]*id=\"charCount\"")
        self.assertNotIn("promptTemplateButton", heading_html.group(0))
        self.assertNotIn("prompt-editor-toolbar", prompt_html)
        self.assertNotIn("prompt-run-toolbar", prompt_html)
        self.assertRegex(prompt_html, r"<div class=\"prompt-compose\">[\s\S]*id=\"promptEditor\"[\s\S]*id=\"runButton\"")
        self.assertIn('aria-keyshortcuts="Meta+Enter"', prompt_html)
        self.assertIn('title="开始生成（Cmd+Enter）"', prompt_html)
        self.assertRegex(
            prompt_html,
            r"id=\"runButton\"[\s\S]*<div class=\"prompt-template-row\">[\s\S]*<div class=\"prompt-footer\">[\s\S]*id=\"clearPromptButton\"[\s\S]*id=\"promptTemplateRecentDock\"[\s\S]*id=\"promptTemplateButton\"",
        )
        self.assertIn('class="ghost-button text-sm icon-text-button resource-manage-button prompt-template-button"', prompt_html)
        self.assertIn('title="管理模板库"', prompt_html)
        self.assertRegex(prompt_html, r"<span[^>]*>管理模板库</span>")
        self.assertIn('id="promptTemplateRecentDock"', html)
        self.assertIn('id="promptTemplateDrawer"', html)
        self.assertIn('id="promptTemplateDrawerBackdrop"', html)
        self.assertIn('class="resource-sheet prompt-template-drawer"', html)
        self.assertIn('class="resource-sheet-backdrop prompt-template-drawer-backdrop hidden"', html)
        self.assertIn('id="promptTemplateSummary" class="prompt-template-summary"', html)
        self.assertIn('class="prompt-template-search-wrap"', html)
        self.assertIn('id="promptTemplateSearch"', html)
        self.assertIn('id="promptTemplateSearch" class="control" type="text"', html)
        self.assertIn('id="promptTemplateSearchClearButton"', html)
        self.assertIn('class="prompt-template-search-clear-button"', html)
        self.assertIn('data-i18n-attr="aria-label:action.clear;title:action.clear"', html)
        self.assertRegex(html, r'id="promptTemplateSearchClearButton"[\s\S]*hidden')
        self.assertIn('name="prompt-template-search"', html)
        self.assertIn('inputmode="search"', html)
        self.assertIn('autocomplete="new-password"', html)
        self.assertIn('autocapitalize="off"', html)
        self.assertIn('spellcheck="false"', html)
        self.assertIn('readonly', html)
        self.assertIn('data-prompt-template-filter="favorite"', html)
        self.assertIn('id="promptTemplateImportButton"', html)
        self.assertIn('id="promptTemplateImportInput"', html)
        self.assertIn('id="promptTemplateExportButton" class="ghost-button text-sm" type="button"', html)
        self.assertNotIn('id="promptTemplateExportButton" class="ghost-button text-sm" href=', html)
        self.assertIn('id="promptTemplateCategoryList"', html)
        self.assertIn('id="promptTemplateCategoryManageButton"', html)
        self.assertIn('id="promptTemplateCategoryPanel"', html)
        self.assertIn('id="promptTemplateList"', html)
        self.assertIn('id="promptTemplateDetail"', html)
        self.assertIn('id="promptTemplateForm"', html)
        gallery_panel = re.search(r'<div id="galleryManagePanel"[\s\S]*?</div>', html)
        self.assertIsNotNone(gallery_panel)
        self.assertNotIn("promptTemplateButton", gallery_panel.group(0))
        self.assertRegex(styles, r":root\s*\{[^}]*--workspace-side-action-width:\s*164px")
        self.assertRegex(styles, r"\.prompt-panel\s*\{[^}]*--prompt-action-column-width:\s*var\(--workspace-side-action-width\)")
        self.assertRegex(styles, r"\.prompt-panel\s*\{[^}]*--prompt-action-gap:\s*12px")
        self.assertRegex(styles, r"\.prompt-panel\s*\{[^}]*--prompt-secondary-action-height:\s*40px")
        self.assertRegex(styles, r"\.prompt-heading\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.prompt-heading\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+var\(--prompt-action-column-width\)")
        self.assertRegex(styles, r"\.prompt-heading-main\s*\{[^}]*align-items:\s*flex-end")
        self.assertRegex(styles, r"\.prompt-template-row\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.prompt-template-row\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+var\(--prompt-action-column-width\)")
        self.assertRegex(styles, r"\.prompt-template-row\s*\{[^}]*align-items:\s*center")
        self.assertRegex(styles, r"\.prompt-template-entry\s*\{[^}]*justify-content:\s*flex-end")
        self.assertRegex(styles, r"\.prompt-template-recent-cell\s*\{[^}]*justify-content:\s*space-between")
        self.assertRegex(styles, r"\.prompt-template-recent-cell\s*\{[^}]*align-items:\s*center")
        self.assertNotIn(".prompt-template-row .prompt-template-button", styles)
        resource_button_styles = self._extract_css_block(styles, ".resource-manage-button")
        self.assertIn("width: 100%", resource_button_styles)
        self.assertIn("background: var(--primary)", resource_button_styles)
        self.assertIn("color: var(--primary-foreground)", resource_button_styles)
        template_button_styles = self._extract_css_block(styles, ".prompt-template-entry .prompt-template-button")
        self.assertIn("width: 100%", template_button_styles)
        self.assertIn("height: var(--prompt-secondary-action-height)", template_button_styles)
        self.assertNotIn("position: absolute", self._extract_css_block(styles, ".prompt-count"))
        self.assertRegex(styles, r"\.prompt-template-recent-dock\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.prompt-template-recent-dock\s*\{[^}]*justify-content:\s*flex-end")
        self.assertRegex(styles, r"\.prompt-template-summary\.ok\s*\{[^}]*color:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.prompt-template-summary\.error\s*\{[^}]*color:\s*var\(--danger\)")
        toolbar_styles = self._extract_css_block(styles, ".prompt-template-toolbar")
        self.assertIn("grid-template-columns: minmax(0, 1fr) repeat(3, 64px)", toolbar_styles)
        self.assertIn("align-items: stretch", toolbar_styles)
        search_wrap_styles = self._extract_css_block(styles, ".prompt-template-search-wrap")
        self.assertIn("position: relative", search_wrap_styles)
        self.assertIn("min-width: 0", search_wrap_styles)
        search_input_styles = self._extract_css_block(styles, ".prompt-template-search-wrap .control")
        self.assertIn("width: 100%", search_input_styles)
        self.assertIn("padding-right: 34px", search_input_styles)
        clear_button_styles = self._extract_css_block(styles, ".prompt-template-search-clear-button")
        self.assertIn("position: absolute", clear_button_styles)
        self.assertIn("right: 6px", clear_button_styles)
        self.assertIn("width: 24px", clear_button_styles)
        self.assertIn("height: 24px", clear_button_styles)
        self.assertRegex(styles, r"\.prompt-template-search-clear-button\[hidden\]\s*\{[^}]*display:\s*none")
        self.assertRegex(
            styles,
            r"\.prompt-template-toolbar \.control,\s*\.prompt-template-toolbar \.ghost-button\s*\{[^}]*height:\s*36px",
        )
        self.assertIn('syncPromptTemplateSearchInput();', self._prompt_templates_source())
        self.assertRegex(
            styles,
            r"\.prompt-template-toolbar \.control,\s*\.prompt-template-toolbar \.ghost-button\s*\{[^}]*min-height:\s*36px",
        )
        self.assertRegex(styles, r"\.prompt-template-toolbar \.ghost-button\s*\{[^}]*width:\s*100%")
        self.assertRegex(styles, r"\.prompt-template-toolbar \.ghost-button\s*\{[^}]*white-space:\s*nowrap")
        category_row_styles = self._extract_css_block(styles, ".prompt-template-category-row")
        self.assertIn("flex-wrap: wrap", category_row_styles)
        self.assertIn("overflow-x: visible", category_row_styles)
        self.assertNotIn("overflow-x: auto", category_row_styles)
        self.assertIn("guardPromptTemplateSearchInput();", self._prompt_templates_source())
        self.assertIn("let promptTemplateSearchAcceptManualInput = false;", self._prompt_templates_source())
        self.assertIn("promptTemplateSearchClearButton: document.querySelector(\"#promptTemplateSearchClearButton\")", script)
        self.assertIn("function updatePromptTemplateSearchClearButton()", self._prompt_templates_source())
        self.assertIn("function clearPromptTemplateSearch()", self._prompt_templates_source())
        self.assertIn("els.promptTemplateSearchClearButton?.addEventListener(\"click\", clearPromptTemplateSearch)", self._prompt_templates_source())
        self.assertRegex(self._prompt_templates_source(), r"function syncPromptTemplateSearchInput\(\)\s*\{[\s\S]*updatePromptTemplateSearchClearButton\(\)")
        self.assertRegex(self._prompt_templates_source(), r"function clearPromptTemplateSearch\(\)\s*\{[\s\S]*state\.promptTemplateQuery = \"\"[\s\S]*renderPromptTemplateList\(\)")
        self.assertIn("setPromptTemplateSearchLocked(true);", self._prompt_templates_source())
        self.assertIn('els.promptTemplateSearch?.addEventListener("keydown"', self._prompt_templates_source())
        self.assertIn('els.promptTemplateSearch?.addEventListener("pointerdown"', self._prompt_templates_source())
        self.assertIn('guardPromptTemplateSearchInput([120, 360, 900]);', self._prompt_templates_source())
        self.assertIn('els.promptTemplateDrawerClose?.focus({ preventScroll: true })', self._prompt_templates_source())
        self.assertNotIn('els.promptTemplateSearch?.focus()', self._prompt_templates_source())
        self.assertRegex(styles, r"\.resource-sheet\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.resource-sheet-backdrop\s*\{[^}]*inset:\s*0")
        self.assertRegex(styles, r"\.prompt-template-drawer\s*\{[^}]*width:\s*min\(420px,\s*calc\(100vw - 24px\)\)")
        self.assertRegex(styles, r"\.prompt-template-grid\s*\{[^}]*column-count:\s*2")
        self.assertRegex(styles, r"\.prompt-template-grid\s*\{[^}]*column-gap:\s*8px")
        self.assertRegex(styles, r"\.prompt-template-card\s*\{[^}]*border-radius:\s*8px")
        self.assertRegex(styles, r"\.prompt-template-card\s*\{[^}]*break-inside:\s*avoid")
        self.assertRegex(styles, r"\.prompt-template-card-thumb\s*\{[^}]*width:\s*100%")
        self.assertNotRegex(self._extract_css_block(styles, ".prompt-template-card-thumb"), r"aspect-ratio")
        self.assertRegex(styles, r"\.prompt-template-card-thumb img\s*\{[^}]*height:\s*auto")
        self.assertRegex(styles, r"\.prompt-template-card-thumb img\s*\{[^}]*object-fit:\s*contain")
        self.assertRegex(styles, r"\.prompt-template-empty\s*\{[^}]*column-span:\s*all")
        self.assertIn("function promptTemplateCardTitle(template", self._prompt_templates_source())
        self.assertIn("function promptTemplateCardSubtitle(template", self._prompt_templates_source())
        self.assertIn("promptTemplateCardSubtitle(template) ? `<span class=\"prompt-template-card-subtitle\"", self._prompt_templates_source())
        self.assertIn("return title && title !== primaryTitle ? title : \"\";", self._prompt_templates_source())
        self.assertIn("prompt-template-detail-back", self._prompt_templates_source())
        self.assertIn("prompt-template-detail-edit", self._prompt_templates_source())
        self.assertIn("prompt-template-detail-secondary-actions", self._prompt_templates_source())
        self.assertIn("prompt-template-detail-replace", self._prompt_templates_source())
        self.assertNotIn("class=\"run-button\" type=\"button\" data-prompt-template-replace", self._prompt_templates_source())
        detail_header_styles = self._extract_css_block(styles, ".prompt-template-detail-header")
        self.assertIn("padding: 0 0 10px", detail_header_styles)
        self.assertIn("border-bottom: 1px solid var(--line)", detail_header_styles)
        self.assertNotIn("background: var(--primary-light)", detail_header_styles)
        self.assertNotIn("border: 1px solid color-mix(in srgb, var(--primary) 24%, var(--line))", detail_header_styles)
        self.assertRegex(styles, r"\.prompt-template-detail-header \.ghost-button\s*\{[^}]*height:\s*36px")
        self.assertRegex(styles, r"\.prompt-template-detail-header \.ghost-button\s*\{[^}]*font-weight:\s*700")
        self.assertRegex(styles, r"\.prompt-template-detail-header \.prompt-template-detail-edit\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.prompt-template-detail-actions\s*\{[^}]*border-top:\s*1px solid var\(--line\)")
        self.assertRegex(styles, r"\.prompt-template-detail-secondary-actions\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.prompt-template-detail-actions \.prompt-template-detail-replace\s*\{[^}]*font-weight:\s*700")
        self.assertRegex(styles, r"\.prompt-template-thumbnail-picker\s*\{[^}]*grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)")
        self.assertRegex(styles, r"\.prompt-template-category-manage-panel\s*\{[^}]*border:\s*1px solid var\(--line\)")
    def test_prompt_template_actions_preserve_prompt_editor_contracts(self) -> None:
        source = self._prompt_templates_source()
        script = self._frontend_script_source()

        self.assertIn("function appendPromptText", source)
        self.assertIn("function setPromptText", source)
        self.assertIn("function syncPromptFromEditor", source)
        self.assertIn("function updatePromptCount", source)
        self.assertIn("function updateRequestPreview", source)
        self.assertIn('applyPromptTemplate(template, "insert")', source)
        self.assertIn('applyPromptTemplate(template, "replace")', source)
        self.assertIn("syncPromptFromEditor();", source)
        self.assertIn('fetch(`${PROMPT_TEMPLATES_ENDPOINT}/${encodeURIComponent(template.id)}/use`', source)
        self.assertIn("navigator.clipboard.writeText", source)
        self.assertIn("thumbnail_url", source)
        self.assertIn('translate("templates.back")', source)
        self.assertIn('translate("action.delete")', source)
        self.assertIn('translate("templates.formTitle")', source)
        self.assertIn('translate("templates.formShortTitle")', source)
        self.assertIn('translate("templates.formCategory")', source)
        self.assertIn('translate("templates.formTags")', source)
        self.assertIn('translate("templates.formThumbnail")', source)
        self.assertIn('translate("templates.formContent")', source)
        self.assertIn('translate("templates.formNotes")', source)
        self.assertIn('translate("templates.formFavorite")', source)
        self.assertIn('translate("templates.thumbnailClear")', source)
        self.assertIn('translate("action.save")', source)
        self.assertIn("/api/prompt-templates/import", source)
        self.assertIn("/api/prompt-templates/export.json", source)
        self.assertIn('els.promptTemplateExportButton?.addEventListener("click"', source)
        self.assertIn("URL.createObjectURL(blob)", source)
        self.assertIn('link.download = "webui-prompt-templates.json"', source)
        self.assertIn('setPromptTemplateSummary(translate("templates.exported"), "ok")', source)
        self.assertIn('setStatus(translate("templates.exported"), "ok")', source)
        self.assertNotIn("localStorage", source)
        self.assertNotIn("currentPromptForModel", source)
        self.assertIn("promptTemplates", script)
        self.assertIn("promptSnippets", script)
    def test_prompt_find_replace_is_inline_and_preserves_atomic_chips(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        source = Path("codex_image/webui/frontend/src/prompt-find-replace.ts").read_text(encoding="utf-8")
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        prompt_section = re.search(r"<section class=\"panel prompt-panel\">[\s\S]*?</section>", html)
        self.assertIsNotNone(prompt_section)
        prompt_html = prompt_section.group(0)
        self.assertRegex(
            prompt_html,
            r"<div class=\"prompt-footer\">[\s\S]*id=\"clearPromptButton\"[\s\S]*id=\"promptFindButton\"[\s\S]*<span[^>]*>查找</span>[\s\S]*id=\"promptFindPanel\"",
        )
        self.assertIn('id="promptFindButton" class="ghost-button icon-text-button text-sm prompt-find-button"', prompt_html)
        self.assertIn('id="promptFindPanel" class="prompt-find-panel hidden"', prompt_html)
        self.assertIn('id="promptFindInput"', prompt_html)
        self.assertIn('id="promptReplaceInput"', prompt_html)
        self.assertIn('id="promptFindCount"', prompt_html)
        self.assertIn('data-prompt-find-action="count"', prompt_html)
        self.assertIn('data-prompt-find-action="replace-all"', prompt_html)
        self.assertNotIn('data-prompt-find-action="prev"', prompt_html)
        self.assertNotIn('data-prompt-find-action="next"', prompt_html)
        self.assertNotIn('data-prompt-find-action="replace"', prompt_html)
        self.assertNotIn('data-prompt-find-action="undo"', prompt_html)
        self.assertNotIn('>上</button>', prompt_html)
        self.assertNotIn('>下</button>', prompt_html)
        self.assertNotIn('>全部</button>', prompt_html)
        self.assertNotIn('>撤销</button>', prompt_html)
        self.assertIn('aria-label="关闭查找替换"', prompt_html)

        self.assertIn('import { initPromptFindReplaceFeature } from "./prompt-find-replace"', main_source)
        self.assertLess(main_source.index("initPromptFeature()"), main_source.index("initPromptFindReplaceFeature()"))
        self.assertIn("export function initPromptFindReplaceFeature", source)
        self.assertIn("function collectPromptFindMatches", source)
        self.assertIn("function collectPromptFindMatchesFromNode", source)
        self.assertIn("function isNodeInsidePromptAtomicChip", source)
        self.assertIn('closest(".gallery-chip, .color-chip, .prompt-snippet-chip")', source)
        self.assertIn("root.normalize()", source)
        self.assertNotIn("document.createTreeWalker", source)
        self.assertNotIn("NodeFilter", source)
        self.assertIn("function countPromptFindMatches", source)
        self.assertIn("function replaceAllPromptMatches", source)
        self.assertIn("function bindPromptFindActionButtons", source)
        self.assertIn('button.addEventListener("click"', source)
        self.assertIn('els.promptFindClose?.addEventListener("click"', source)
        self.assertIn('legacyMethod("syncPromptFromEditor")', source)
        self.assertIn('legacyMethod("syncGalleryInputsFromPrompt")', source)
        self.assertIn('legacyMethod("updatePromptCount")', source)
        self.assertIn('legacyMethod("updateRequestPreview")', source)
        self.assertNotIn("function selectPromptFindMatch", source)
        self.assertNotIn("window.getSelection()", source)
        self.assertNotIn("function replaceCurrentPromptMatch", source)
        self.assertNotIn("function restorePromptFindSnapshot", source)
        self.assertNotIn("promptFindLastSnapshot", source)
        self.assertNotIn("function movePromptFindSelection", source)
        self.assertNotIn('event.key === "Enter"', source)
        self.assertNotIn('els.promptFindInput.addEventListener("input", () => {\n    setPromptFindStatus("");\n    refreshPromptFindMatches();', source)
        self.assertNotIn('els.promptEditor?.addEventListener("input"', source)
        self.assertIn('event.key.toLowerCase() === "f"', source)
        self.assertNotIn("new RegExp", source)

        find_panel_styles = self._extract_css_block(styles, ".prompt-find-panel")
        self.assertIn("display: grid", find_panel_styles)
        self.assertIn("grid-template-columns: minmax(78px, 1fr) minmax(78px, 1fr) max-content", find_panel_styles)
        self.assertIn("min-width: 0", find_panel_styles)
        self.assertRegex(styles, r"\.prompt-find-panel \.control\s*\{[^}]*height:\s*calc\(var\(--prompt-secondary-action-height\) - 4px\)")
        self.assertRegex(styles, r"\.prompt-find-panel \.ghost-button\s*\{[^}]*height:\s*calc\(var\(--prompt-secondary-action-height\) - 4px\)")
        self.assertRegex(styles, r"\.prompt-template-recent-cell\.find-active \.prompt-template-recent-dock\s*\{[^}]*display:\s*none")
        self.assertRegex(
            styles,
            r"@media \(max-height:\s*1390px\) and \(min-width:\s*900px\)\s*\{[\s\S]*\.prompt-find-panel\s*\{[\s\S]*grid-template-columns:\s*minmax\(68px,\s*1fr\)\s+minmax\(68px,\s*1fr\)\s+max-content",
        )
    def test_prompt_editor_core_modules_have_typescript_source_contract(self) -> None:
        prompt_source = self._prompt_source()
        serialization_source = self._prompt_serialization_source()
        gallery_chips_source = self._prompt_gallery_chips_source()
        editor_events_source = self._prompt_editor_events_source()
        model_source = self._prompt_model_source()

        for source in (
            serialization_source,
            gallery_chips_source,
            editor_events_source,
            model_source,
        ):
            self.assertNotIn("@ts-nocheck", source)
            self.assertIn('import { getLegacyBridge } from "./state"', source)
            self.assertIn("Object.assign(getLegacyBridge().methods", source)

        for symbol in (
            "getPromptText",
            "promptTextFromNode",
            "promptSelectionText",
            "promptTextFromRange",
            "rangeIntersectsNode",
            "selectPromptEditorContents",
        ):
            self.assertIn(f"export function {symbol}", serialization_source)
            self.assertIn(symbol, prompt_source)

        for symbol in (
            "createGalleryChip",
            "findGalleryRefMentionAt",
            "syncGalleryInputsFromPrompt",
            "syncPromptGalleryMentionsFromInputs",
            "insertGalleryMention",
            "hideMentionSuggest",
        ):
            self.assertIn(f"export function {symbol}", gallery_chips_source)
            self.assertIn(symbol, prompt_source)

        for symbol in (
            "handlePromptEditorCopy",
            "updatePromptChipSelectionState",
            "handlePromptEditorDrop",
            "bindPromptEditorEvents",
            "syncPromptFromEditor",
        ):
            self.assertIn(f"export function {symbol}", editor_events_source)
            self.assertIn(symbol, prompt_source)

        for symbol in (
            "currentPromptForModel",
            "promptTokenReplacement",
            "galleryPromptText",
        ):
            self.assertIn(f"export function {symbol}", model_source)
            self.assertIn(symbol, prompt_source)

        self.assertIn('from "./prompt-serialization"', prompt_source)
        self.assertIn('from "./prompt-gallery-chips"', prompt_source)
        self.assertIn('from "./prompt-editor-events"', prompt_source)
        self.assertIn('from "./prompt-model"', prompt_source)
        self.assertLessEqual(len(prompt_source.splitlines()), 220)
    def test_prompt_editor_supports_gallery_mentions(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('id="promptEditor"', html)
        self.assertIn('id="prompt"', html)
        self.assertIn('type="hidden"', html)
        self.assertIn("insertGalleryMention", script)
        self.assertIn("ensurePromptGalleryMention", script)
        self.assertIn("syncGalleryInputsFromPrompt", script)
        self.assertIn("syncPromptGalleryMentionsFromInputs", script)
        self.assertIn("currentPromptGalleryIds", script)
        self.assertIn("removePromptGalleryChip", script)
        self.assertIn("promptChipAtCaretForDeletion", script)
        self.assertIn("promptChipFallbackForDeletion", script)
        self.assertIn("addGalleryInput(item, { syncPrompt: false })", script)
        self.assertIn('if (options.syncPrompt !== false) legacyMethod("ensurePromptGalleryMention", item)', script)
        self.assertIn('event.key === "Backspace" || event.key === "Delete"', script)
        self.assertIn("data-remove-gallery-chip", script)
        self.assertIn("prompt_for_model", script)
        self.assertIn("function galleryReferenceInstruction", script)
        self.assertIn('translate("promptModel.galleryHeader")', script)
        self.assertIn('formatTranslation("promptModel.galleryInstruction"', script)
        self.assertIn("categoryPromptRole(source.category)", script)
        self.assertIn("source.prompt_note", script)
        self.assertIn("syncGalleryInputsFromPrompt()", script)
        self.assertIn("syncPromptGalleryMentionsFromInputs()", script)
        self.assertIn('form.append("gallery_image_ids"', script)
        self.assertIn("gallery-chip", script)
        self.assertRegex(styles, r"\.gallery-chip\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(styles, r"\.gallery-chip-remove\s*\{[^}]*cursor:\s*pointer")
        self.assertRegex(styles, r"\.mention-suggest\s*\{[^}]*position:\s*fixed")
    def test_prompt_gallery_chip_sync_rehydrates_missing_gallery_inputs(self) -> None:
        script = self._frontend_script_source()

        self.assertIn('querySelectorAll(".gallery-chip[data-gallery-id]")', script)
        self.assertIn("const existingById = new Map", script)
        self.assertIn("const item = findGalleryItem(itemId)", script)
        self.assertIn("if (item) return gallerySource(item)", script)
        self.assertIn("state.images = [...uploads, ...galleries]", script)
        self.assertIn("function imageSourcesKey", script)
    def test_prompt_dragged_gallery_chips_keep_text_boundaries(self) -> None:
        script = self._frontend_script_source()

        self.assertIn("function normalizePromptChipBoundaries(chip)", script)
        self.assertRegex(script, r"function handlePromptChipDrop\(event\)\s*\{[\s\S]*normalizePromptChipBoundaries\(chip\)")
        self.assertRegex(script, r"function normalizePromptChipBoundaries\(chip\)\s*\{[\s\S]*ensurePromptChipLeadingBoundary\(chip\)[\s\S]*ensurePromptChipTrailingBoundary\(chip\)")
        self.assertRegex(script, r"function ensurePromptChipLeadingBoundary\(chip\)\s*\{[\s\S]*previousSibling[\s\S]*insertBefore\(document\.createTextNode\(\" \"\), chip\)")
        self.assertRegex(script, r"function ensurePromptChipTrailingBoundary\(chip\)\s*\{[\s\S]*nextSibling[\s\S]*insertBefore\(document\.createTextNode\(\" \"\), nextNode\)")
    def test_prompt_restore_prefers_gallery_ref_names_for_mention_chips(self) -> None:
        script = self._frontend_script_source()

        self.assertIn("function galleryRefsByMentionLength(refs)", script)
        self.assertIn("function findGalleryRefMentionAt(promptText, cursor, refs)", script)
        self.assertRegex(script, r"function setPromptWithGalleryRefs\(text, refs\)\s*\{[\s\S]*const sortedRefs = galleryRefsByMentionLength\(refList\)")
        self.assertRegex(script, r"function setPromptWithGalleryRefs\(text, refs\)\s*\{[\s\S]*const refMatch = findGalleryRefMentionAt\(promptText, cursor, sortedRefs\)")
        self.assertRegex(script, r"function setPromptWithGalleryRefs\(text, refs\)\s*\{[\s\S]*if \(refMatch\) \{[\s\S]*els\.promptEditor\.append\(createGalleryChip\(refMatch\.ref\)\)")
        self.assertIn("cursor = refMatch.end", script)
    def test_prompt_mention_suggestions_close_after_insert_and_follow_caret(self) -> None:
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("positionMentionSuggestAtCaret(match)", script)
        self.assertIn("function setCaretAfterNode(node)", script)
        self.assertRegex(script, r"function setCaretAfterNode\(node\)\s*\{[\s\S]*node\.nodeType === Node\.TEXT_NODE[\s\S]*range\.setStart\(node,\s*\(node\.textContent \|\| \"\"\)\.length\)")
        self.assertIn('if (event.key === "Escape") return;', script)
        self.assertRegex(script, r"function activeMentionMatch\(\)\s*\{[\s\S]*window\.getSelection\(\)")
        self.assertRegex(script, r"function activeMentionMatch\(\)\s*\{[\s\S]*range\.setStart\(container,\s*tokenStart\)")
        self.assertNotRegex(script, r"function activeMentionMatch\(\)\s*\{[\s\S]{0,260}getPromptText\(\)")
        self.assertRegex(script, r"function insertGalleryMention\(item\)\s*\{[\s\S]*match\.range\.deleteContents\(\)")
        self.assertRegex(script, r"function insertGalleryMention\(item\)\s*\{[\s\S]*setCaretAfterNode\(trailingSpace\)")
        self.assertRegex(script, r"function ensurePromptGalleryMention\(item\)\s*\{[\s\S]*hideMentionSuggest\(\)")
        self.assertRegex(script, r"function handleDocumentKeydown\(event\)\s*\{[\s\S]*hideMentionSuggest\(\)")
        self.assertRegex(styles, r"\.mention-suggest\s*\{[^}]*left:\s*var\(--mention-left")
        self.assertRegex(styles, r"\.mention-suggest\s*\{[^}]*top:\s*var\(--mention-top")
        self.assertNotRegex(styles, r"\.mention-suggest\s*\{[^}]*right:\s*10px")
    def test_prompt_token_popovers_escape_short_screen_editor_clipping(self) -> None:
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('from "./prompt-popover-position"', script)
        self.assertIn("function positionPromptPopoverAtAnchor(", script)
        self.assertIn("window.innerHeight", script)
        self.assertIn("--prompt-popover-max-height", script)
        self.assertRegex(script, r"positionPromptPopoverAtAnchor\(\s*els\.mentionSuggest")
        self.assertRegex(script, r"positionPromptPopoverAtAnchor\(\s*els\.colorSuggest")
        self.assertRegex(script, r"positionPromptPopoverAtAnchor\(\s*suggest")
        self.assertRegex(script, r"positionPromptPopoverAtAnchor\(\s*popover")
        for selector in [
            "mention-suggest",
            "prompt-snippet-suggest",
            "color-suggest",
            "prompt-snippet-save-button",
            "prompt-snippet-popover",
        ]:
            self.assertRegex(
                styles,
                rf"\.{selector}\s*\{{[^}}]*position:\s*fixed",
                f"{selector} must not be clipped by the short-screen prompt editor",
            )
        for selector in ["mention-suggest", "prompt-snippet-suggest", "color-suggest", "prompt-snippet-popover"]:
            self.assertRegex(styles, rf"\.{selector}\s*\{{[^}}]*max-height:\s*var\(--prompt-popover-max-height")
            self.assertRegex(styles, rf"\.{selector}\s*\{{[^}}]*overflow-y:\s*auto")
    def test_prompt_editor_supports_hex_color_code_picker(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('id="colorSuggest"', html)
        self.assertIn("输入 # 可插入颜色码", html)
        self.assertIn("colorSuggest: document.querySelector(\"#colorSuggest\")", script)
        self.assertIn("COLOR_PALETTE_ENDPOINT", script)
        self.assertIn("COLOR_PALETTE_EXPORT_CSS_ENDPOINT", script)
        self.assertIn("COLOR_PALETTE_IMPORT_ENDPOINT", script)
        self.assertIn("DEFAULT_COLOR_SWATCHES", script)
        self.assertIn("colorPalette", script)
        self.assertIn("defaultColorPalette", script)
        self.assertIn("refreshColorPalette", script)
        self.assertIn("persistColorPalette", script)
        self.assertIn("importColorPalette", script)
        self.assertIn("colorPaletteManageMode: false", script)
        self.assertIn("toggleColorPaletteManageMode", script)
        self.assertIn("saveFavoriteColor", script)
        self.assertIn("removeFavoriteColor", script)
        self.assertIn("updateColorSuggest", script)
        self.assertIn("activeColorMatch", script)
        self.assertIn("renderColorSuggest", script)
        self.assertIn("positionColorSuggestAtCaret(match)", script)
        self.assertIn("insertColorCode", script)
        self.assertIn("createColorChip", script)
        self.assertIn("normalizeHexColor", script)
        self.assertIn("hideColorSuggest", script)
        self.assertIn("data-color-code", script)
        self.assertIn("data-remove-color-chip", script)
        self.assertIn("promptTextFromNode", script)
        self.assertRegex(script, r"promptTextFromNode\(node\)\s*\{[\s\S]*child\.classList\.contains\(\"color-chip\"\)[\s\S]*child\.dataset\.colorCode")
        self.assertRegex(script, r"function activeColorMatch\(\)\s*\{[\s\S]*window\.getSelection\(\)")
        self.assertIn("textBeforeCaret.match(/#([0-9a-fA-F]{0,6})$/)", script)
        self.assertRegex(script, r"function insertColorCode\(colorCode\)\s*\{[\s\S]*match\.range\.deleteContents\(\)")
        self.assertRegex(script, r"function createColorChip\(colorCode\)\s*\{[\s\S]*label\.textContent = normalized")
        self.assertIn("data-save-favorite-color", script)
        self.assertNotIn("data-color-name-input", script)
        self.assertNotIn("color-name-input", script)
        self.assertIn("name: normalized", script)
        self.assertIn("data-color-value-control", script)
        self.assertIn("const swatchButtons = [", script)
        self.assertIn("...favoriteColors.map", script)
        self.assertIn("...recentColors.map", script)
        self.assertNotIn("color-recent-row", script)
        self.assertIn("color-picker-icon", script)
        self.assertIn('translate("colors.hexValue")', script)
        self.assertIn('translate("colors.pendingUpdate")', script)
        self.assertIn("const updateDraftState = ", script)
        self.assertRegex(script, r"if \(insert && originalColor\) insert\.disabled = !isDirty")
        self.assertRegex(script, r"if \(state\.activeColorChip\) \{[\s\S]*syncColor\(button\.dataset\.colorSwatch\)")
        self.assertIn('translate("colors.save")', script)
        self.assertNotIn("保存常用", script)
        self.assertIn("data-remove-favorite-color", script)
        self.assertIn("color-swatch-remove-icon", script)
        self.assertNotRegex(script, r"class=\"color-swatch-remove\"[\s\S]{0,260}>×</button>")
        self.assertIn("data-color-palette-export", script)
        self.assertIn("data-color-palette-import", script)
        self.assertIn("data-color-palette-import-input", script)
        self.assertIn("data-color-palette-manage", script)
        self.assertIn('aria-pressed="${state.colorPaletteManageMode ? "true" : "false"}"', script)
        self.assertIn('colorSwatchButton(item.hex, item.name, { removable: state.colorPaletteManageMode })', script)
        self.assertIn('fetch(COLOR_PALETTE_ENDPOINT', script)
        self.assertIn('fetch(COLOR_PALETTE_IMPORT_ENDPOINT', script)
        self.assertIn('href="${COLOR_PALETTE_EXPORT_CSS_ENDPOINT}"', script)
        self.assertIn('accept=".aco,.css,.html,.htm,.svg,.txt"', script)
        self.assertNotIn("导出 PS", script)
        self.assertNotIn("导入 PS", script)
        self.assertNotIn("COLOR_RECENTS_STORAGE_KEY", script)
        self.assertNotIn("codex-image-recent-colors", script)
        self.assertNotIn("背景色", script)
        self.assertRegex(styles, r"\.color-suggest\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.color-suggest\s*\{[^}]*box-sizing:\s*border-box")
        self.assertRegex(styles, r"\.color-suggest\s*\{[^}]*overflow-x:\s*hidden")
        self.assertRegex(styles, r"\.color-chip\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(styles, r"\.color-chip-swatch\s*\{[^}]*background:\s*var\(--color-code\)")
        self.assertRegex(styles, r"\.color-suggest-main\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.color-suggest-main\s*\{[^}]*grid-template-columns:\s*auto auto minmax\(128px,\s*1fr\)")
        self.assertRegex(styles, r"\.color-suggest-main\s*\{[^}]*grid-template-rows:\s*repeat\(2,\s*28px\)")
        self.assertRegex(script, r"<div class=\"color-suggest-actions\">[\s\S]*<div class=\"color-update-hint")
        self.assertNotRegex(script, r"</div>\s*<div class=\"color-suggest-actions\">")
        self.assertRegex(styles, r"\.color-value-control\s*\{[^}]*--color-picker-width:\s*52px")
        self.assertRegex(styles, r"\.color-value-control\s*\{[^}]*--color-hex-input-width:\s*calc\(7ch \+ 20px\)")
        self.assertRegex(styles, r"\.color-value-control\s*\{[^}]*grid-template-columns:\s*var\(--color-picker-width\) var\(--color-hex-input-width\)")
        self.assertRegex(styles, r"\.color-value-control\s*\{[^}]*grid-row:\s*1 / span 2")
        self.assertRegex(styles, r"\.color-value-control\s*\{[^}]*height:\s*64px")
        self.assertRegex(styles, r"\.color-picker-control\s*\{[^}]*width:\s*var\(--color-picker-width\)")
        self.assertRegex(styles, r"\.color-picker-input\s*\{[^}]*opacity:\s*0\.01")
        self.assertRegex(styles, r"\.color-picker-swatch\s*\{[^}]*width:\s*42px")
        self.assertRegex(styles, r"\.color-picker-swatch\s*\{[^}]*background:\s*var\(--active-color\)")
        self.assertRegex(styles, r"\.color-picker-icon\s*\{[^}]*right:\s*-3px")
        self.assertRegex(styles, r"\.color-insert-button\s*\{[^}]*grid-row:\s*1 / span 2")
        self.assertRegex(styles, r"\.color-insert-button\s*\{[^}]*height:\s*64px")
        self.assertRegex(styles, r"\.color-insert-button\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.color-update-hint\s*\{[^}]*grid-column:\s*1 / -1")
        self.assertRegex(styles, r"\.color-swatch-button\s*\{[^}]*background:\s*var\(--swatch-color\)")
        self.assertRegex(styles, r"\.color-suggest-actions\s*\{[^}]*grid-column:\s*3")
        self.assertRegex(styles, r"\.color-suggest-actions\s*\{[^}]*grid-row:\s*1 / span 2")
        self.assertRegex(styles, r"\.color-suggest-actions\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)")
        self.assertRegex(styles, r"\.color-suggest-actions\s*\{[^}]*grid-template-rows:\s*repeat\(2,\s*28px\)")
        self.assertRegex(styles, r"\.color-suggest-actions\s*\{[^}]*width:\s*100%")
        self.assertNotIn(".color-name-input", styles)
        self.assertRegex(styles, r"\.color-swatch-item\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.color-swatch-remove\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.color-swatch-remove\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(styles, r"\.color-swatch-remove-icon path\s*\{[^}]*stroke:\s*currentColor")
        self.assertRegex(styles, r"\.color-swatch-row\.is-managing\s+\.color-swatch-button\s*\{[^}]*border-color:\s*var\(--primary")
        self.assertRegex(styles, r"\.color-import-input\s*\{[^}]*display:\s*none")
    def test_history_prompt_restore_rebuilds_hex_color_chips(self) -> None:
        script = self._frontend_script_source()

        self.assertRegex(script, r"function setPromptWithGalleryRefs\(text,\s*refs\)\s*\{[\s\S]*createColorChip\(colorCode\)")
        self.assertRegex(script, r"function setPromptWithGalleryRefs\(text,\s*refs\)\s*\{[\s\S]*normalizeHexColor\(match\[0\]\)")
        self.assertIn("/@([^\\s@，。,.#~～〜∼˜]+)|#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F])|(?:^|[\\s\\n，。,.；;：:！？!?、（）()\\[\\]【】\"'“”‘’])([~～〜∼˜]+)([^\\s~～〜∼˜@#，。,.；;：:！？!?、（）()\\[\\]【】\"'“”‘’]+)/g", script)
        self.assertNotRegex(script, r"function setPromptWithGalleryRefs\(text,\s*refs\)\s*\{[\s\S]{0,160}!Array\.isArray\(refs\) \|\| !refs\.length")
    def test_color_chip_swatch_reopens_picker_for_editing(self) -> None:
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("activeColorChip", script)
        self.assertIn("data-edit-color-chip", script)
        self.assertIn("openColorChipEditor", script)
        self.assertIn("positionColorSuggestAtChip", script)
        self.assertIn("updateColorChip", script)
        self.assertRegex(script, r"function createColorChip\(colorCode\)\s*\{[\s\S]*swatch\.setAttribute\(\"data-edit-color-chip\"")
        self.assertRegex(script, r"function handlePromptEditorClick\(event\)\s*\{[\s\S]*data-edit-color-chip[\s\S]*openColorChipEditor")
        self.assertRegex(script, r"function insertColorCode\(colorCode\)\s*\{[\s\S]*state\.activeColorChip[\s\S]*updateColorChip")
        self.assertIn("promptEditorFocusInside", script)
        self.assertRegex(script, r"promptEditorFocusInside\(\)[\s\S]*hideColorSuggest")
        self.assertRegex(styles, r"\.color-chip-swatch\s*\{[^}]*cursor:\s*pointer")
    def test_prompt_editor_supports_prompt_snippet_chips(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("输入 ~ 或 ～ 可调用提示词片段", html)
        self.assertIn("PROMPT_SNIPPETS_ENDPOINT", script)
        self.assertIn("promptSnippets: []", script)
        self.assertIn("refreshPromptSnippets", script)
        self.assertIn("updatePromptSnippetSuggest", script)
        self.assertIn("activePromptSnippetMatch", script)
        self.assertIn("insertPromptSnippet", script)
        self.assertIn("createPromptSnippetChip", script)
        self.assertIn("expandPromptSnippets", script)
        self.assertIn("hidePromptSnippetSuggest", script)
        self.assertIn("data-prompt-snippet-id", script)
        self.assertIn("data-remove-prompt-snippet-chip", script)
        self.assertIn("PROMPT_SNIPPET_TRIGGER_PATTERN", script)
        self.assertIn("PROMPT_SNIPPET_TRIGGER_CHARS", script)
        self.assertIn("PROMPT_SNIPPET_BOUNDARY_CHARS", script)
        self.assertIn("normalizePromptSnippetTrigger", script)
        self.assertRegex(script, r"PROMPT_SNIPPET_TRIGGER_PATTERN\s*=\s*/\(\^\|\[\\s\\n，。")
        self.assertRegex(script, r"PROMPT_SNIPPET_TRIGGER_PATTERN\s*=\s*/[\s\S]*\(\[~～〜∼˜\]\+\)")
        self.assertRegex(script, r"function activePromptSnippetMatch\(\)\s*\{[\s\S]*normalizePromptSnippetTrigger\(match\[2\]\)")
        self.assertRegex(script, r"promptTextFromNode\(node\)\s*\{[\s\S]*child\.classList\.contains\(\"prompt-snippet-chip\"\)[\s\S]*`~\$\{child\.dataset\.promptSnippetTag")
        self.assertRegex(script, r"function currentPromptForModel\(\)\s*\{[\s\S]*expandPromptSnippets\(getPromptText\(\)\)")
        self.assertRegex(script, r"function buildPromptForModel\(\)\s*\{[\s\S]*expandPromptSnippets\(getPromptText\(\)\)")
        self.assertRegex(styles, r"\.prompt-snippet-chip\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(styles, r"\.prompt-snippet-suggest\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.prompt-snippet-option\s*\{[^}]*cursor:\s*pointer")
    def test_prompt_snippet_chip_popover_actions_do_not_self_close(self) -> None:
        script = self._frontend_script_source()

        chip_block = script.split("function openPromptSnippetChipPopover(chip) {", 1)[1].split(
            "\n}\n\nfunction renderPromptSnippetForm", 1
        )[0]
        self.assertRegex(chip_block, r"function handlePopoverActionClick\(event,\s*action[^)]*\)")
        self.assertIn("event.preventDefault()", chip_block)
        self.assertIn("event.stopPropagation()", chip_block)
        self.assertRegex(chip_block, r"data-prompt-snippet-edit[\s\S]*handlePopoverActionClick\(event, \(\) => renderPromptSnippetForm")
    def test_prompt_selection_uses_floating_snippet_save_button(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertNotIn('id="promptSnippetSaveButton"', html)
        self.assertNotIn("promptSnippetSaveButton: document.querySelector", script)
        self.assertIn("promptSnippetSelectionRange: null", script)
        self.assertIn("getPromptSelectionForSnippet", script)
        self.assertIn("showPromptSnippetSelectionButton", script)
        self.assertIn("hidePromptSnippetSelectionButton", script)
        self.assertIn("openPromptSnippetSavePopover", script)
        self.assertIn("selectionContainsPromptAtomicChip", script)
        self.assertIn("replacePromptSelectionWithSnippet", script)
        self.assertIn("promptSnippetSelectionAnchorRect", script)
        show_button_block = script.split("function showPromptSnippetSelectionButton(selection) {", 1)[1].split(
            "\n}\n\nfunction promptSnippetSelectionAnchorRect", 1
        )[0]
        self.assertRegex(script, r"document\.addEventListener\(\"selectionchange\",[\s\S]*updatePromptSnippetSelectionButton")
        self.assertIn("promptSnippetSelectionAnchorRect(selection, editorRect)", show_button_block)
        self.assertNotIn("mentionRangeRect(selection.range)", show_button_block)
        self.assertRegex(styles, r"\.prompt-snippet-save-button\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.prompt-snippet-popover\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.prompt-snippet-popover-actions\s*\{[^}]*display:\s*flex")

    def test_prompt_selection_save_button_stays_inside_visible_editor_rect(self) -> None:
        script = self._frontend_script_source()

        show_button_block = script.split("function showPromptSnippetSelectionButton(selection) {", 1)[1].split(
            "\n}\n\nfunction promptSnippetSelectionAnchorRect", 1
        )[0]
        anchor_block = script.split("function promptSnippetSelectionAnchorRect", 1)[1].split(
            "\n}\n\nfunction hidePromptSnippetSelectionButton", 1
        )[0]
        self.assertIn("promptSnippetVisibleEditorRect()", show_button_block)
        self.assertIn("promptSnippetSelectionAnchorRect(selection, editorRect)", show_button_block)
        self.assertIn("promptSnippetSelectionVisibleRects(selection.range, editorRect)", anchor_block)
        self.assertIn("clipRectToBounds", script)
        self.assertIn("promptSnippetFallbackVisibleAnchorRect(editorRect)", anchor_block)
        self.assertNotIn("return rects.length ? rects[rects.length - 1] : mentionRangeRect(selection.range)", anchor_block)

    def test_prompt_editor_copy_serializes_selected_chips(self) -> None:
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('addEventListener("copy", handlePromptEditorCopy)', script)
        self.assertRegex(script, r'document\.addEventListener\("selectionchange",\s*\(\)\s*=>\s*\{[\s\S]*updatePromptChipSelectionState\(\)')
        self.assertRegex(script, r"function handlePromptEditorCopy\(event\)\s*\{[\s\S]*promptSelectionText\(\)[\s\S]*event\.clipboardData\.setData\(\"text/plain\", text\)")
        self.assertRegex(script, r"function promptSelectionText\(\)\s*\{[\s\S]*window\.getSelection\(\)[\s\S]*promptTextFromRange\(range\)")
        self.assertRegex(script, r"function promptTextFromRange\(range\)\s*\{[\s\S]*range\.cloneContents\(\)[\s\S]*promptTextFromNode\(fragment\)")
        self.assertRegex(script, r"function rangeIntersectsNode\(range,\s*node\)\s*\{[\s\S]*range\.intersectsNode\(node\)")
        self.assertRegex(script, r"function updatePromptChipSelectionState\(\)\s*\{[\s\S]*\.gallery-chip,\s*\.color-chip,\s*\.prompt-snippet-chip[\s\S]*prompt-chip-selected")
        self.assertRegex(script, r"function selectPromptEditorContents\(\)\s*\{[\s\S]*range\.selectNodeContents\(els\.promptEditor\)")
        self.assertIn("function isPromptEditorArrowKey(key)", script)
        self.assertRegex(script, r"function handlePromptEditorKeydown\(event\)\s*\{[\s\S]*isPromptEditorArrowKey\(event\.key\)[\s\S]*event\.stopPropagation\(\)[\s\S]*return;")
        self.assertRegex(script, r"function handlePromptEditorKeydown\(event\)\s*\{[\s\S]*event\.key\.toLowerCase\(\) === \"a\"[\s\S]*selectPromptEditorContents\(\)")
        self.assertRegex(styles, r"\.gallery-chip\.prompt-chip-selected\s*,\s*\.color-chip\.prompt-chip-selected\s*,\s*\.prompt-snippet-chip\.prompt-chip-selected\s*\{[^}]*box-shadow:")
        self.assertRegex(styles, r"\.gallery-chip-remove\s*,\s*\.color-chip-swatch\s*,\s*\.color-chip-remove\s*,\s*\.prompt-snippet-chip-remove\s*\{[^}]*user-select:\s*none")
    def test_prompt_editor_paste_strips_web_html_styles(self) -> None:
        events_source = Path("codex_image/webui/frontend/src/prompt-editor-events.ts").read_text(encoding="utf-8")
        source = Path("codex_image/webui/frontend/src/prompt-editor-paste.ts").read_text(encoding="utf-8")
        script = self._frontend_script_source()

        self.assertLessEqual(len(events_source.splitlines()), 500)
        self.assertIn('from "./prompt-editor-paste"', events_source)
        self.assertIn('addEventListener("paste", handlePromptEditorPaste)', script)
        self.assertIn("function handlePromptEditorPaste(event)", script)
        self.assertRegex(source, r"function clipboardHasImageFile\(data:\s*DataTransfer\)[\s\S]*item\.kind === \"file\"[\s\S]*item\.type\?\.startsWith\(\"image/\"\)")
        self.assertRegex(source, r"function handlePromptEditorPaste\(event:\s*any\)[\s\S]*if \(clipboardHasImageFile\(event\.clipboardData\)\) return")
        self.assertRegex(source, r"function promptPasteTextFromClipboard\(data:\s*DataTransfer\)[\s\S]*data\.getData\(\"text/plain\"\)[\s\S]*data\.getData\(\"text/html\"\)")
        self.assertRegex(source, r"function promptPlainTextFromHtml\(html:\s*any\)[\s\S]*document\.createElement\(\"div\"\)[\s\S]*promptPlainTextFromHtmlNode\(container\)")
        self.assertIn("normalizePromptPasteText", source)
        self.assertIn('replace(/\\u00a0/g, " ")', source)
        self.assertIn("createPromptTextFragment(normalized)", source)
        self.assertIn("range.insertNode(fragment)", source)
        self.assertIn("setCaretAfterNode(lastNode)", source)
        self.assertRegex(source, r"function handlePromptEditorPaste\(event:\s*any\)[\s\S]*event\.preventDefault\(\)[\s\S]*insertPlainPromptText\(text\)[\s\S]*syncPromptAfterChipMutation\(\)")
        self.assertNotIn("insertHTML", source)
        self.assertNotIn("createContextualFragment", source)
    def test_color_chip_text_uses_actual_mixed_background_contrast(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for readable color checks")

        script = self._frontend_bundle_source()
        normalize_hex_match = re.search(
            r"function readableTextColor\(colorCode\)\s*\{[\s\S]*?const normalized = (normalizeHexColor\d*)\(colorCode\);",
            script,
        )
        self.assertIsNotNone(normalize_hex_match)
        normalize_hex_function = normalize_hex_match.group(1)
        function_source = "\n".join(
            self._extract_javascript_function(script, function_name)
            for function_name in (
                "hexToRgb",
                "mixRgbWithWhite",
                "relativeLuminance",
                "contrastRatio",
                "readableTextColor",
            )
        )
        check_script = f"""
function {normalize_hex_function}(value) {{
  const raw = String(value || "").trim().replace(/^#/, "");
  if (/^[0-9a-fA-F]{{3}}$/.test(raw)) {{
    return `#${{raw.split("").map((char) => char + char).join("").toUpperCase()}}`;
  }}
  if (/^[0-9a-fA-F]{{6}}$/.test(raw)) return `#${{raw.toUpperCase()}}`;
  return "";
}}
{function_source}
const cases = ["#00BFFF", "#E9FA00", "#000000", "zzzzzz"];
console.log(cases.map((color) => readableTextColor(color)).join("\\n"));
"""
        result = subprocess.run(
            [node, "-e", check_script],
            check=False,
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            ["#1f352f", "#1f352f", "#1f352f", "var(--text)"],
        )
    def test_prompt_chips_can_be_dragged_within_editor(self) -> None:
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('addEventListener("dragstart", handlePromptChipDragStart)', script)
        self.assertIn('addEventListener("dragover", handlePromptChipDragOver)', script)
        self.assertIn('addEventListener("drop", handlePromptChipDrop)', script)
        self.assertIn('addEventListener("dragend", handlePromptChipDragEnd)', script)
        self.assertIn("draggedPromptChip", script)
        self.assertIn("promptRangeFromPoint", script)
        self.assertIn("syncPromptAfterChipMutation", script)
        self.assertRegex(script, r"function createGalleryChip\(item\)\s*\{[\s\S]*chip\.draggable = true")
        self.assertRegex(script, r"function createColorChip\(colorCode\)\s*\{[\s\S]*chip\.draggable = true")
        self.assertRegex(script, r"function handlePromptChipDrop\(event\)\s*\{[\s\S]*insertBefore")
        self.assertRegex(styles, r"\.prompt-chip-dragging\s*\{[^}]*opacity")
        self.assertRegex(styles, r"\.prompt-chip-drop-before::before\s*,\s*\.prompt-chip-drop-after::after")
    def test_ui_polish_for_sidebar_upload_and_prompt_clear(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertRegex(styles, r"\.sidebar-content\s*,[\s\S]*\.dashboard\s*,[\s\S]*\.prompt-editor\s*,[\s\S]*\.modal-panel\s*\{[^}]*scrollbar-color:\s*var\(--scrollbar-thumb\)")
        self.assertRegex(styles, r"\.sidebar-content::-webkit-scrollbar-thumb\s*,[\s\S]*\.dashboard::-webkit-scrollbar-thumb")
        self.assertRegex(styles, r"\.image-uploader-grid\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.image-thumb-list\s*\{[^}]*overflow-x:\s*auto")
        self.assertRegex(styles, r"\.upload-tile\s*\{[^}]*height:\s*100%")
        self.assertRegex(html, r'<span class="icon" aria-hidden="true">\s*<svg[\s\S]*<path d="M12 5v14M5 12h14"')
        self.assertNotIn('<span class="icon">+</span>', html)
        self.assertRegex(styles, r"\.upload-tile\s+\.icon\s*\{[^}]*line-height:\s*0")
        self.assertRegex(styles, r"\.upload-tile\s+\.icon\s+svg\s*\{[^}]*display:\s*block")
        self.assertRegex(styles, r"\.image-input-workspace\s*\{[^}]*--image-input-thumb-size:\s*116px")
        self.assertRegex(styles, r"\.thumb\s*\{[^}]*width:\s*var\(--image-input-thumb-size\)")
        prompt_section = re.search(r"<section class=\"panel prompt-panel\">[\s\S]*?</section>", html)
        self.assertIsNotNone(prompt_section)
        prompt_heading = re.search(r"<div class=\"panel-heading prompt-heading\">[\s\S]*?</div>", prompt_section.group(0))
        self.assertIsNotNone(prompt_heading)
        self.assertIn("charCount", prompt_heading.group(0))
        self.assertRegex(html, r"<div class=\"prompt-compose\">[\s\S]*id=\"promptEditor\"[\s\S]*id=\"runButton\"")
        self.assertRegex(html, r"<div class=\"prompt-footer\">\s*<button id=\"clearPromptButton\" class=\"ghost-button icon-text-button text-sm quiet-danger-button\"[\s\S]*<svg[\s\S]*<span[^>]*>清空</span>")
        self.assertNotRegex(html, r"<div class=\"panel-heading prompt-heading\">\s*<h2>提示词</h2>\s*<button id=\"clearPromptButton\"")
        self.assertRegex(styles, r"\.prompt-compose\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.prompt-compose\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+var\(--prompt-action-column-width\)")
        self.assertRegex(styles, r"\.prompt-compose\s+\.run-button\s*\{[^}]*height:\s*140px")
        self.assertRegex(styles, r"\.prompt-footer\s*\{[^}]*justify-content:\s*flex-start")
        self.assertRegex(styles, r"\.prompt-footer\s+\.ghost-button\s*\{[^}]*height:\s*var\(--prompt-secondary-action-height\)")
        self.assertRegex(styles, r"\.prompt-footer\s*>\s*\.icon-text-button\s*\{[^}]*flex:\s*0 0 auto")
        self.assertRegex(styles, r"\.prompt-footer\s*>\s*\.icon-text-button\s*\{[^}]*white-space:\s*nowrap")
        self.assertRegex(styles, r"\.prompt-footer\s*>\s*\.icon-text-button\s+span\s*\{[^}]*white-space:\s*nowrap")
        self.assertRegex(styles, r"\.icon-text-button\s*\{[^}]*gap:\s*6px")
        self.assertRegex(styles, r"\.button-icon\s*\{[^}]*width:\s*14px")
        self.assertRegex(styles, r"\.quiet-danger-button\s*\{[^}]*color:\s*var\(--text-secondary\)")
        self.assertRegex(styles, r"\.quiet-danger-button:hover\s*,\s*\.quiet-danger-button:focus-visible\s*\{[^}]*color:\s*var\(--danger\)")
    def test_preview_shows_prompt_popover_for_each_output(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertNotIn('id="promptTrace"', html)
        self.assertNotIn("promptTrace:", script)
        self.assertNotIn("renderPromptTrace", script)
        self.assertIn('class="prompt-action-row"', script)
        self.assertIn('data-prompt-popover-index=""', script)
        self.assertIn("promptButton.dataset.promptPopoverIndex = String(index)", script)
        self.assertIn("promptPopoverData(state.previewTask, index)", script)
        self.assertIn("const originalPrompt = task.prompt || task.prompt_for_model || \"\"", script)
        self.assertIn("task.prompt_for_model", script)
        self.assertIn("task.revised_prompt", script)
        self.assertIn("task.revised_prompts?.[index]", script)
        self.assertIn("openPromptPopover", script)
        self.assertIn("closePromptPopover", script)
        self.assertIn("copyOptimizedPrompt", script)
        self.assertIn("navigator.clipboard.writeText", script)
        self.assertIn('translate("promptPopover.copyOptimized")', script)
        self.assertIn('translate("templates.copy")', script)
        self.assertIn('translate("promptPopover.title")', script)
        self.assertIn('translate("promptPopover.original")', script)
        self.assertIn("prompt-popover-compare", script)
        self.assertIn("prompt-popover-section-tools", script)
        self.assertIn("prompt-copy-inline", script)
        self.assertIn("promptLengthLabel", script)
        self.assertIn('translate("promptPopover.submitted")', script)
        self.assertIn('translate("promptPopover.optimized")', script)
        self.assertIn('translate("promptPopover.noOptimized")', script)
        self.assertRegex(styles, r"\.preview-card\s*\{[^}]*container-type:\s*inline-size")
        self.assertRegex(styles, r"\.prompt-action-row\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.prompt-action-row\s*\{[^}]*grid-template-columns:\s*repeat\(4,\s*max-content\)")
        self.assertNotRegex(styles, r"\.prompt-action-row\s*\{[^}]*flex-wrap:\s*wrap")
        self.assertRegex(styles, r"\.prompt-action-row\s*\{[^}]*width:\s*max-content")
        self.assertRegex(styles, r"\.prompt-action-row\s*\{[^}]*max-width:\s*calc\(100% - 16px\)")
        self.assertIn("@container (max-width: 380px)", styles)
        self.assertRegex(styles, r"@container \(max-width:\s*380px\)\s*\{[\s\S]*?\.prompt-action-row\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)")
        self.assertRegex(styles, r"@container \(max-width:\s*380px\)\s*\{[\s\S]*?\.prompt-action-row\s*>\s*\.add-to-input-btn[\s\S]*?width:\s*100%")
        self.assertRegex(styles, r"\.prompt-popover\s*\{[^}]*position:\s*fixed")
        self.assertRegex(styles, r"\.prompt-popover\s*\{[^}]*width:\s*min\(760px,\s*calc\(100vw - 24px\)\)")
        self.assertRegex(styles, r"\.prompt-popover-body\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(styles, r"\.prompt-popover-compare\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)")
        self.assertRegex(styles, r"\.prompt-popover-section-tools\s*\{[^}]*display:\s*inline-flex")
        self.assertRegex(styles, r"\.prompt-copy-inline\s*\{[^}]*min-height:\s*24px")
        self.assertRegex(styles, r"\.prompt-popover-text\s*\{[^}]*overflow:\s*auto")
        self.assertRegex(styles, r"\.prompt-popover-submitted\s*\{[^}]*border-top:\s*1px solid var\(--line\)")
        self.assertRegex(styles, r"\.prompt-popover-text\s*,\s*\.prompt-popover-submitted-text\s*\{[^}]*scrollbar-color:\s*var\(--scrollbar-thumb\)\s+var\(--scrollbar-track\)")
        self.assertRegex(styles, r"\.prompt-popover-text::\-webkit-scrollbar-thumb\s*,\s*\.prompt-popover-submitted-text::\-webkit-scrollbar-thumb\s*\{[^}]*background:\s*var\(--scrollbar-thumb\)")
        self.assertRegex(styles, r"\.add-to-input-btn\s*,\s*\.collect-input-btn\s*,\s*\.prompt-popover-button\s*,\s*\.preview-download-link\s*\{[^}]*width:\s*auto")
        self.assertRegex(styles, r"\.add-to-input-btn\s*,\s*\.collect-input-btn\s*,\s*\.prompt-popover-button\s*,\s*\.preview-download-link\s*\{[^}]*min-height:\s*32px")
        self.assertRegex(styles, r"\.add-to-input-btn\s*,\s*\.collect-input-btn\s*,\s*\.prompt-popover-button\s*,\s*\.preview-download-link\s*\{[^}]*font-size:\s*12px")
        self.assertRegex(styles, r"\.add-to-input-btn\s*,\s*\.collect-input-btn\s*,\s*\.prompt-popover-button\s*,\s*\.preview-download-link\s*\{[^}]*background:\s*color-mix\(in srgb,\s*var\(--surface\) 90%,\s*var\(--primary-light\) 10%\)")
        self.assertRegex(styles, r"\.add-to-input-btn\s*\{[^}]*min-width:\s*92px")
        self.assertRegex(styles, r"\.add-to-input-btn\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.add-to-input-btn\s*\{[^}]*color:\s*var\(--primary-foreground\)")
        self.assertRegex(styles, r"\.collect-input-btn\s*,\s*\.prompt-popover-button\s*,\s*\.preview-download-link\s*\{[^}]*min-width:\s*64px")
        self.assertNotRegex(styles, r"\.prompt-popover-button\s*\{[^}]*background:\s*var\(--primary\)")
        self.assertRegex(styles, r"\.add-to-input-btn:hover\s*,\s*\.collect-input-btn:hover\s*,\s*\.prompt-popover-button:hover\s*,\s*\.preview-download-link:hover\s*\{[^}]*color:\s*var\(--primary-foreground\)")
    def test_prompt_popover_is_centered_on_preview_image_and_clamped_to_viewport(self) -> None:
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn("clampPopoverPosition", script)
        self.assertIn("anchor.getBoundingClientRect()", script)
        self.assertIn("promptPopoverHorizontalAnchorRect(anchor)", script)
        self.assertIn('anchor.closest?.(".preview-card")?.querySelector?.("img[data-lightbox-url]")', script)
        self.assertIn("image.naturalWidth", script)
        self.assertIn("imageRect.left + (imageRect.width - width) / 2", script)
        self.assertIn("const horizontalAnchorCenter = horizontalAnchorRect.left + horizontalAnchorRect.width / 2", script)
        self.assertNotIn("centeredMaxWidth", script)
        self.assertIn("horizontalAnchorCenter - width / 2", script)
        self.assertIn("window.innerWidth - width - margin", script)
        self.assertIn("window.innerHeight - height - margin", script)
        self.assertIn("const width = Math.min(760, viewportWidth)", script)
        self.assertRegex(styles, r"\.prompt-popover\s*\{[^}]*width:\s*min\(760px,\s*calc\(100vw - 24px\)\)")
    def test_main_model_control_is_persisted_and_submitted(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('id="mainModel"', html)
        self.assertIn('id="mainModelCombobox"', html)
        self.assertIn('role="combobox"', html)
        self.assertIn('id="mainModelToggle"', html)
        self.assertIn('id="mainModelOptions"', html)
        self.assertIn('role="listbox"', html)
        self.assertIn('/static/app.js?v=runtime-568', html)
        self.assertIn('/static/styles.css?v=runtime-568', html)
        self.assertIn("mainModel: document.querySelector", script)
        self.assertIn("mainModelCombobox: document.querySelector", script)
        self.assertIn("mainModelToggle: document.querySelector", script)
        self.assertIn("mainModelOptions: document.querySelector", script)
        self.assertIn("mainModelShowAllOptions: false", script)
        self.assertIn('"gpt-5.6-sol",', script)
        self.assertIn('"gpt-5.6-terra",', script)
        self.assertIn('"gpt-5.6-luna",', script)
        self.assertLess(script.index('"gpt-5.6-sol"'), script.index('"gpt-5.6-terra"'))
        self.assertLess(script.index('"gpt-5.6-terra"'), script.index('"gpt-5.6-luna"'))
        self.assertLess(script.index('"gpt-5.6-luna"'), script.index('"gpt-5.5"'))
        self.assertIn('const RETIRED_MAIN_MODEL_OPTIONS = new Set(["gpt-5.3-codex-spark"]);', script)
        self.assertIn("function mainModelOptionsForQuery", script)
        self.assertIn("function openMainModelCombobox", script)
        self.assertIn("function selectMainModelOption", script)
        self.assertIn("function handleMainModelKeydown", script)
        self.assertIn("openMainModelCombobox({ showAll: true })", script)
        self.assertIn('els.mainModel?.addEventListener("click"', script)
        self.assertIn("if (!state.mainModelComboboxOpen) openMainModelCombobox({ showAll: true });", script)
        self.assertIn('const query = state.mainModelShowAllOptions ? "" : els.mainModel.value;', script)
        self.assertIn('localStorage.getItem(MAIN_MODEL_STORAGE_KEY)', script)
        self.assertIn('localStorage.setItem(MAIN_MODEL_STORAGE_KEY', script)
        self.assertIn("main_model: currentMainModel()", script)
        self.assertIn('form.append("main_model", currentMainModel())', script)
        self.assertIn('params.main_model || request.main_model || (usesResponses ? request.model : "")', script)
        self.assertRegex(styles, r"\.model-combobox\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.model-combobox-options\s*\{[^}]*position:\s*absolute")
        self.assertRegex(styles, r"\.model-combobox-option\s*\{[^}]*display:\s*flex")
        self.assertRegex(styles, r"\.mode-settings-slot\s*\{[^}]*overflow:\s*visible")
        self.assertRegex(styles, r"\.mode-settings-slot\s*\{[^}]*position:\s*relative")
        self.assertRegex(styles, r"\.mode-settings-slot\s*\{[^}]*z-index:\s*2")
        self.assertNotIn(".mode-settings-slot.is-transitioning", styles)
    def test_main_model_combobox_filters_builtin_options_and_keeps_custom_input(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        script = Path("codex_image/webui/frontend/src/main-model-combobox.ts").read_text(encoding="utf-8")
        harness = "\n".join(
            [
                'const MAIN_MODEL_OPTIONS = ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex", "gpt-5.2"];',
                self._extract_javascript_function(script, "mainModelOptionsForQuery"),
                """
                const codexMatches = mainModelOptionsForQuery("codex");
                const gpt56Matches = mainModelOptionsForQuery("gpt-5.6");
                const customMatches = mainModelOptionsForQuery("future-model-x");
                const expectedGpt56 = ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"];
                if (JSON.stringify(gpt56Matches) !== JSON.stringify(expectedGpt56)) {
                  throw new Error(`expected GPT-5.6 model family, got ${gpt56Matches.join(",")}`);
                }
                if (!codexMatches.includes("gpt-5.3-codex")) {
                  throw new Error(`expected codex model matches, got ${codexMatches.join(",")}`);
                }
                if (codexMatches.includes("gpt-5.3-codex-spark")) {
                  throw new Error(`spark should not be a built-in image tool option, got ${codexMatches.join(",")}`);
                }
                if (customMatches.length !== 0) {
                  throw new Error(`custom input should remain valid without forced option, got ${customMatches.join(",")}`);
                }
                """,
            ]
        )
        result = subprocess.run([node, "-e", harness], check=False, text=True, capture_output=True)

        self.assertEqual(result.returncode, 0, result.stderr)
    def test_main_model_restore_resets_retired_builtin_option(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        script = Path("codex_image/webui/frontend/src/main-model-combobox.ts").read_text(encoding="utf-8")
        harness = "\n".join(
            [
                'const DEFAULT_MAIN_MODEL = "gpt-5.4-mini";',
                'const MAIN_MODEL_STORAGE_KEY = "codex-image-main-model";',
                'const RETIRED_MAIN_MODEL_OPTIONS = new Set(["gpt-5.3-codex-spark"]);',
                """
                const els = { mainModel: { value: "" } };
                const storedValues = { [MAIN_MODEL_STORAGE_KEY]: "gpt-5.3-codex-spark" };
                const localStorage = {
                  getItem(key) { return storedValues[key] ?? null; },
                  setItem(key, value) { storedValues[key] = value; },
                };
                let renderCount = 0;
                function renderMainModelOptions() { renderCount += 1; }
                """,
                self._extract_javascript_function(script, "restoreMainModel"),
                """
                restoreMainModel();
                if (els.mainModel.value !== DEFAULT_MAIN_MODEL) {
                  throw new Error(`expected retired saved model to reset, got ${els.mainModel.value}`);
                }
                if (storedValues[MAIN_MODEL_STORAGE_KEY] !== DEFAULT_MAIN_MODEL) {
                  throw new Error(`expected storage migration to default, got ${storedValues[MAIN_MODEL_STORAGE_KEY]}`);
                }
                if (renderCount !== 1) {
                  throw new Error(`expected options render once, got ${renderCount}`);
                }
                """,
            ]
        )
        result = subprocess.run([node, "-e", harness], check=False, text=True, capture_output=True)

        self.assertEqual(result.returncode, 0, result.stderr)
    def test_api_direct_mode_hides_non_applicable_main_model_but_keeps_prompt_fidelity(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()
        auth_source = Path("codex_image/webui/frontend/src/auth-source.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('id="mainModelField"', html)
        self.assertIn('id="promptFidelityField"', html)
        self.assertIn('id="apiDirectSettingsNotice"', html)
        self.assertIn('id="modeSpecificSettings"', html)
        self.assertIn('id="modeSettingsSlot"', html)
        self.assertIn('class="mode-settings-slot full-width"', html)
        self.assertIn('class="mode-specific-settings mode-transition"', html)
        self.assertIn('class="model-tool-row"', html)
        self.assertIn('class="field api-direct-settings-notice mode-transition mode-collapsed hidden"', html)
        self.assertRegex(
            html,
            r'id="modeSpecificSettings"[\s\S]*id="mainModelField"[\s\S]*id="apiDirectSettingsNotice"[\s\S]*id="promptFidelityField"',
        )
        self.assertIn("使用 API 图像生成模型", html)
        self.assertIn("API 设置", html)
        self.assertIn("不参与本次请求", html)
        self.assertNotIn("原始/保真/创意可用，保真规则随 prompt 发送", html)
        self.assertNotIn("<span>提示词模式</span>\n                      <strong>原始/保真/创意可用", html)
        self.assertIn("modeSettingsSlot: document.querySelector(\"#modeSettingsSlot\")", script)
        self.assertIn("modeSpecificSettings: document.querySelector(\"#modeSpecificSettings\")", script)
        self.assertIn("mainModelField: document.querySelector(\"#mainModelField\")", script)
        self.assertIn("promptFidelityField: document.querySelector(\"#promptFidelityField\")", script)
        self.assertIn("apiDirectSettingsNotice: document.querySelector(\"#apiDirectSettingsNotice\")", script)
        self.assertIn("pendingAuthSource: null", script)
        self.assertIn("function applyAuthSourceSelection", script)
        self.assertIn("function setModeSpecificElementVisibility", script)
        self.assertIn("function applyModeSettingsVisibility", script)
        self.assertIn("function setModeSettingsVariant", script)
        self.assertIn("function isDirectApiMode(authSource = currentAuthSource())", script)
        self.assertIn("function updateModeSpecificSettings(authSource = currentAuthSource())", script)
        self.assertIn('authSource === "api" && currentApiMode() !== "responses"', script)
        self.assertIn('authSource === "codex" && currentCodexMode() !== "responses"', script)
        self.assertIn("setModeSettingsVariant(isDirectApi)", script)
        self.assertNotIn("slot.style.height = `${fromHeight}px`;", script)
        self.assertNotIn("slot.style.height = `${targetHeight}px`;", script)
        self.assertNotIn("modeTransitionTimers", script)
        self.assertRegex(
            auth_source,
            r"async function applyAuthSource\(source[^)]*\)[^{]*\{[\s\S]*state\.pendingAuthSource = source;[\s\S]*applyAuthSourceSelection\(source\);[\s\S]*const response = await fetch",
        )
        self.assertRegex(
            script,
            r"function applyModeSettingsVisibility\(isDirectApi[^)]*\)[\s\S]*setModeSpecificElementVisibility\(els\.mainModelField,\s*!isDirectApi\);[\s\S]*setModeSpecificElementVisibility\(els\.apiDirectSettingsNotice,\s*isDirectApi\);[\s\S]*setModeSpecificElementVisibility\(els\.promptFidelityField,\s*true\);",
        )
        self.assertIn("state.pendingAuthSource = null;", auth_source)
        self.assertIn("renderAuthSource(state.authStatus);", auth_source)
        self.assertNotIn('element.classList.toggle("hidden", isDirectApi)', script)
        self.assertNotIn('els.apiDirectSettingsNotice?.classList.toggle("hidden", !isDirectApi)', script)
        self.assertNotIn('if (isDirectApiMode()) return "off";', script)
        self.assertNotIn("if (isDirectApiMode()) return buildPromptForModel();", script)
        self.assertIn('const value = els.promptFidelity?.value || "strict";', script)
        self.assertIn("updateModeSpecificSettings();", script)
        self.assertRegex(styles, r"\.api-direct-settings-notice\s*\{[^}]*min-height:\s*60px")
        self.assertRegex(styles, r"\.api-direct-settings-control\s*\{[^}]*height:\s*36px")
        self.assertRegex(styles, r"\.api-direct-settings-control\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\) max-content")
        self.assertRegex(styles, r"\.api-direct-settings-header\s*\{[^}]*grid-template-columns:\s*max-content minmax\(0,\s*1fr\)")
        self.assertRegex(styles, r"\.api-direct-settings-button\s*\{[^}]*min-height:\s*28px")
        self.assertNotIn(".api-direct-settings-grid", styles)
        self.assertRegex(styles, r"\.mode-settings-slot\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.mode-settings-slot\s*\{[^}]*--mode-settings-stable-height:\s*144px")
        self.assertRegex(styles, r"\.mode-settings-slot\s*\{[^}]*min-height:\s*var\(--mode-settings-stable-height\)")
        self.assertNotRegex(styles, r"\.mode-settings-slot\s*\{[^}]*transition:\s*height")
        self.assertNotRegex(styles, r"\.mode-settings-slot\s*>\s*\.mode-transition\s*\{[^}]*grid-area:\s*1\s*/\s*1")
        self.assertRegex(styles, r"\.mode-specific-settings\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.model-tool-row\s*\{[^}]*display:\s*grid")
        self.assertRegex(styles, r"\.model-tool-row\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(104px,\s*max-content\)")
        self.assertRegex(styles, r"\.mode-transition\s*\{[^}]*transition:")
        self.assertNotIn("max-height: var(--mode-transition-max-height", styles)
    def test_javascript_uses_official_gpt_image_2_size_presets(self) -> None:
        script = self._frontend_script_source()

        self.assertIn("GPT_IMAGE_2_SIZE_PRESETS", script)
        self.assertIn("2160, 3840", script)
        self.assertIn("3840x2160", script)
    def test_gpt_image_2_webui_hides_unsupported_input_fidelity(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        script = self._frontend_script_source()

        self.assertNotIn('id="inputFidelity"', html)
        self.assertNotIn('id="fidelityField"', html)
        self.assertNotIn("inputFidelity", script)
        self.assertNotIn("input_fidelity: state.mode", script)
        self.assertNotIn('payload.input_fidelity', script)
        self.assertNotIn('form.append("input_fidelity"', script)
        self.assertIn('els.size.value = "1024x1024"', script)
