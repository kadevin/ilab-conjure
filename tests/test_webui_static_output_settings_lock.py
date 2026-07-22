from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import textwrap

from tests.webui_helpers import WebUIStaticTestCase


class OutputSettingsLockFrontendContractTests(WebUIStaticTestCase):
    def test_optional_reference_title_and_task_adoption_copy_are_explicit(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        zh_cn = Path("codex_image/webui/frontend/src/i18n/zh-cn.ts").read_text(encoding="utf-8")
        en = Path("codex_image/webui/frontend/src/i18n/en.ts").read_text(encoding="utf-8")

        self.assertIn('<h2 data-i18n="imageInput.referenceTitle">参考输入（可选）</h2>', html)
        self.assertIn('data-i18n="output.lock.adoptTask">使用此任务参数</button>', html)
        self.assertIn('"imageInput.referenceTitle": "参考输入（可选）"', zh_cn)
        self.assertIn('"output.lock.adoptTask": "使用此任务参数"', zh_cn)
        self.assertIn('使用后不改变系统通道', zh_cn)
        self.assertIn('"imageInput.referenceTitle": "Reference input (optional)"', en)
        self.assertIn('does not change the system channel', en)

    def test_summary_model_keeps_four_visible_outputs_and_mode_specific_details(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend behavior checks")
        module_path = Path("codex_image/webui/frontend/src/output-settings-lock.ts").resolve()
        harness = textwrap.dedent(
            f"""
            const fs = require("fs");
            const ts = require("typescript");
            const vm = require("vm");
            const code = ts.transpileModule(fs.readFileSync({str(module_path)!r}, "utf8"), {{
              compilerOptions: {{ module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }},
            }}).outputText;
            const module = {{ exports: {{}} }};
            vm.runInNewContext(code, {{
              module, exports: module.exports, console,
              require(name) {{
                if (name === "./i18n") return {{ LOCALE_CHANGE_EVENT: "locale-change", translate: (key) => key }};
                if (name === "./state") return {{ getLegacyBridge: () => {{ throw new Error("bridge must not be used by pure model tests"); }} }};
                throw new Error(`unexpected require: ${{name}}`);
              }},
            }});
            const snapshot = module.exports.normalizeOutputSettingsSnapshot({{
              main_model: "gpt-5.6-terra", model: "gpt-image-2", size: "1280x1024", ratio: "5:4",
              n: 4, prompt_fidelity: "strict", quality: "high", output_format: "png",
              moderation: "auto", web_search: true,
            }});
            if (snapshot.n !== 4 || snapshot.ratio !== "5:4") throw new Error("snapshot lost the four-output frame");
            const responses = module.exports.buildOutputSettingsSummaryModel(snapshot, {{ responses: true, task: false, callLabel: "" }});
            const images = module.exports.buildOutputSettingsSummaryModel(snapshot, {{ responses: false, task: false, callLabel: "Images API" }});
            const task = module.exports.buildOutputSettingsSummaryModel(snapshot, {{ responses: true, task: true, callLabel: "" }});
            const imageTask = module.exports.buildOutputSettingsSummaryModel(snapshot, {{ responses: false, task: true, callLabel: "Images API" }});
            if (responses.count !== 4 || responses.details.length !== 4) throw new Error("Responses summary contract changed");
            if (images.count !== 4 || images.details.length !== 4) throw new Error("Image summary contract changed");
            if (!responses.showModel) throw new Error("Responses summary must retain the main model");
            if (images.showModel || imageTask.showModel) throw new Error("Image summary must hide the image model");
            if (responses.contextLabel !== "") throw new Error("Current summary must omit the redundant context label");
            if (task.contextLabel !== "output.lock.task") throw new Error("Task summary must retain its context label");
            if (imageTask.contextLabel !== "output.lock.task") throw new Error("Image task summary lost its context label");
            if (!responses.details.some((item) => item.label === "output.lock.search")) throw new Error("Search label missing");
            if (responses.details.some((item) => item.label === "output.lock.imageModel")) throw new Error("Responses summary exposed the image model");
            if (images.details.some((item) => item.label === "output.lock.search")) throw new Error("Image summary exposed Search");
            if (module.exports.outputCountCardRatio("5:4") !== 1.25) throw new Error("5:4 count-card ratio changed");
            if (module.exports.outputCountCardRatio("9:16") !== 9 / 16) throw new Error("9:16 count-card ratio changed");
            if (module.exports.outputCountCardRatio("invalid") !== 1) throw new Error("invalid count-card ratio must fall back to square");
            if (!module.exports.usesWideFourGrid(4, "16:9")) throw new Error("16:9 four-output grid missing");
            if (!module.exports.usesWideFourGrid(4, "21:9")) throw new Error("21:9 four-output grid missing");
            if (module.exports.usesWideFourGrid(3, "21:9")) throw new Error("three outputs must remain a row");
            if (module.exports.usesWideFourGrid(4, "5:4")) throw new Error("non-wide four outputs must remain a row");

            const safetyOff = {{
              HARM_CATEGORY_HARASSMENT: "OFF",
              HARM_CATEGORY_HATE_SPEECH: "OFF",
              HARM_CATEGORY_SEXUALLY_EXPLICIT: "OFF",
              HARM_CATEGORY_DANGEROUS_CONTENT: "OFF",
            }};
            const nano = module.exports.normalizeOutputSettingsSnapshot({{
              canonical_model_id: "nano-banana-2",
              model_display_name: "Nano Banana 2",
              parameters: {{
                "canvas.aspect_ratio": "16:9",
                "canvas.resolution": "2K",
                "output.count": 3,
                "gemini.safety_settings": safetyOff,
                "gemini.google_search": true,
              }},
            }});
            const nanoSummary = module.exports.buildOutputSettingsSummaryModel(nano, {{ responses: false, task: false, callLabel: "Gemini" }});
            if (!nanoSummary.showModel || nanoSummary.modelValue !== "Nano Banana 2") throw new Error("Nano model identity missing");
            if (nanoSummary.modelLabel !== "") throw new Error("Nano model must not repeat a concrete-model label");
            if (nanoSummary.thirdCard.kind !== "resolution" || nanoSummary.thirdCard.value !== "2K") throw new Error("Nano resolution card missing");
            if (nanoSummary.ratio !== "16:9" || nanoSummary.count !== 3) throw new Error("Nano frame summary is stale");
            if (!nanoSummary.details.some((item) => item.label === "gemini.safetySettings" && item.value === "gemini.safety.threshold.off")) throw new Error("Nano safety summary missing");
            if (!nanoSummary.details.some((item) => item.label === "gemini.googleSearch" && item.value === "output.lock.enabled")) throw new Error("Nano search summary missing");
            if (nanoSummary.details.some((item) => ["output.lock.prompt", "output.quality", "output.moderation"].includes(item.label))) throw new Error("Nano summary leaked GPT fields");

            const lite = module.exports.normalizeOutputSettingsSnapshot({{
              canonical_model_id: "nano-banana-2-lite",
              model_display_name: "Nano Banana 2 Lite",
              parameters: {{
                "canvas.aspect_ratio": "1:1",
                "canvas.resolution": "1K",
                "output.count": 1,
                "gemini.safety_settings": {{}},
              }},
            }});
            const liteSummary = module.exports.buildOutputSettingsSummaryModel(lite, {{ responses: false, task: false, callLabel: "Gemini" }});
            if (!liteSummary.details.some((item) => item.label === "gemini.safetySettings" && item.value === "gemini.safety.threshold.off")) throw new Error("Lite empty safety preset must summarize as filtering off");
            if (liteSummary.details.some((item) => item.label === "gemini.googleSearch")) throw new Error("Lite exposed unsupported search");

            """
        )
        result = subprocess.run([node, "-e", harness], check=False, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_output_settings_lock_markup_has_one_action_and_no_channel_control(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        panel_start = html.index('class="panel output-panel"')
        panel_end = html.index('class="dashboard-col preview-col"')
        panel = html[panel_start:panel_end]

        self.assertIn('id="outputSettingsHeader"', panel)
        self.assertIn('id="outputSettingsLockButton"', panel)
        self.assertIn('id="outputSettingsLockedSummary"', panel)
        self.assertIn('id="outputSettingsSummaryContent"', panel)
        self.assertIn('id="outputSettingsTaskAction"', panel)
        self.assertIn('id="adoptTaskOutputSettingsButton"', panel)
        self.assertNotIn('id="outputSettingsChannel', panel)
        self.assertNotIn("data-output-settings-channel", panel)
        self.assertNotIn("Codex 通道", panel)

    def test_all_locale_dictionaries_include_output_lock_copy(self) -> None:
        locale_dir = Path("codex_image/webui/frontend/src/i18n")
        locale_files = sorted(
            path
            for path in locale_dir.glob("*.ts")
            if path.name not in {"dictionaries.ts", "index.ts", "types.ts"}
        )
        self.assertEqual(13, len(locale_files))
        required_keys = (
            "output.lock.lock",
            "output.lock.unlock",
            "output.lock.current",
            "output.lock.task",
            "output.lock.adoptTask",
            "output.lock.frame",
            "output.lock.outputCount",
            "output.lock.output",
            "output.lock.search",
            "output.lock.custom",
        )
        for path in locale_files:
            source = path.read_text(encoding="utf-8")
            for key in required_keys:
                self.assertIn(f'"{key}"', source, f"{path.name} is missing {key}")

    def test_lock_module_uses_system_context_without_exposing_channel_control(self) -> None:
        source = Path("codex_image/webui/frontend/src/output-settings-lock.ts").read_text(encoding="utf-8")
        self.assertIn("export function normalizeOutputSettingsSnapshot", source)
        self.assertIn("export function buildOutputSettingsSummaryModel", source)
        self.assertIn("currentCodexMode", source)
        self.assertIn("currentApiMode", source)
        self.assertIn('model && model.id !== "gpt-image-2"', source)
        self.assertIn("bridge.methods.activeParameterValues(model)", source)
        self.assertIn("codex-image-output-settings-lock-v1", source)
        self.assertNotIn("data-output-settings-channel", source)
        self.assertNotIn("selectCodexMode", source)

    def test_lock_feature_is_initialized_and_restored_after_form_boot(self) -> None:
        main = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")
        boot = Path("codex_image/webui/frontend/src/boot.ts").read_text(encoding="utf-8")
        self.assertIn('import { initOutputSettingsLockFeature } from "./output-settings-lock"', main)
        self.assertIn("initOutputSettingsLockFeature()", main)
        self.assertIn('call(methods, "restoreOutputSettingsLock")', boot)
        self.assertGreater(
            boot.index('call(methods, "restoreOutputSettingsLock")'),
            boot.index('call(methods, "updateCustomSize")'),
        )

    def test_locked_task_selection_preserves_output_controls_and_offers_explicit_adoption(self) -> None:
        submit = Path("codex_image/webui/frontend/src/task-submit.ts").read_text(encoding="utf-8")
        selection = Path("codex_image/webui/frontend/src/task-selection.ts").read_text(encoding="utf-8")
        shell = Path("codex_image/webui/frontend/src/shell-ui.ts").read_text(encoding="utf-8")
        mode = Path("codex_image/webui/frontend/src/api-mode-settings.ts").read_text(encoding="utf-8")

        self.assertIn("export function applyTaskOutputParams", submit)
        self.assertIn("preserveOutputSettings", submit)
        self.assertIn("isOutputSettingsLocked", selection)
        self.assertIn("taskOutputSettingsView", selection)
        self.assertIn('if (outputView === "locked-summary")', selection)
        self.assertIn("clearTaskParameterInspection()", selection)
        self.assertIn("showTaskOutputSettings", selection)
        self.assertIn("showLockedOutputSettings", selection)
        self.assertIn("isOutputSettingsLocked", shell)
        self.assertIn("refreshOutputSettingsLock", mode)

    def test_summary_styles_keep_visual_cards_and_stable_panel_footprint(self) -> None:
        source = Path("codex_image/webui/frontend/src/output-settings-lock.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")
        self.assertIn(".output-settings-header", styles)
        self.assertIn(".output-settings-stage", styles)
        self.assertIn(".output-settings-lock-button", styles)
        self.assertIn(".output-settings-locked-summary", styles)
        self.assertIn(".output-settings-summary-cards", styles)
        self.assertIn(".output-settings-summary-details", styles)
        self.assertNotIn("--output-settings-editor-height", styles)
        self.assertNotIn("measureEditorHeight", source)
        self.assertNotIn("getBoundingClientRect", source)
        self.assertIn('els.settingsGrid?.toggleAttribute("inert", visible)', source)
        self.assertIn('context.task ? translate("output.lock.task") : ""', source)
        self.assertIn("if (model.contextLabel)", source)
        self.assertIn('visual.style.setProperty("--output-settings-count-ratio"', source)
        self.assertRegex(styles, r"\.output-settings-count-card\s*\{[^}]*aspect-ratio:\s*var\(--output-settings-count-ratio,\s*1\)")
        self.assertRegex(styles, r"\.output-settings-summary-detail\s*\{[^}]*justify-items:\s*center")
        self.assertRegex(styles, r"\.output-settings-summary-detail\s*\{[^}]*text-align:\s*center")

    def test_gpt_image_hides_model_while_responses_and_non_gpt_use_a_quiet_model_line(self) -> None:
        source = Path("codex_image/webui/frontend/src/output-settings-lock.ts").read_text(encoding="utf-8")
        selection = Path("codex_image/webui/frontend/src/model-selection.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")

        self.assertIn("showModel: gptImage ? context.responses : context.task || geminiImage", source)
        self.assertIn("if (model.showModel)", source)
        self.assertIn("if (model.modelLabel)", source)
        self.assertIn('createElement("div", "output-settings-summary-model-line")', source)
        self.assertIn("if (intro.childElementCount)", source)
        self.assertRegex(styles, r"\.output-settings-summary-model-line\s*\{[^}]*justify-content:\s*center")
        self.assertRegex(styles, r"\.output-settings-summary-model\s*\{[^}]*color:\s*var\(--text-secondary\)[^}]*font-size:\s*14px")
        self.assertIn(".output-settings-summary-main > .output-settings-summary-cards:first-child", styles)
        self.assertGreaterEqual(
            selection.count("getLegacyBridge().methods.refreshOutputSettingsLock?.();"),
            2,
            "family and concrete-model changes must refresh a locked Gemini identity",
        )

    def test_locked_summary_centers_its_main_group_and_uses_a_fading_divider(self) -> None:
        source = Path("codex_image/webui/frontend/src/output-settings-lock.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")

        self.assertIn('const main = createElement("div", "output-settings-summary-main")', source)
        self.assertIn("if (intro.childElementCount) main.append(intro)", source)
        self.assertIn("main.append(cards, details)", source)
        self.assertIn("root.append(main, footer)", source)
        self.assertRegex(styles, r"\.output-settings-summary-main\s*\{[^}]*flex:\s*1[^}]*justify-content:\s*center")
        self.assertRegex(styles, r"\.output-settings-summary-details\s*\{[^}]*border-top:\s*0")
        self.assertIn(".output-settings-summary-details::before", styles)
        self.assertRegex(styles, r"linear-gradient\(\s*90deg,[^;]*transparent\s+0%[^;]*transparent\s+100%")
        self.assertIn(".controls-col .output-settings-summary-main", responsive)

    def test_summary_card_supporting_values_share_a_centered_vertical_axis(self) -> None:
        styles = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")

        self.assertRegex(styles, r"\.output-settings-card-meta\s*\{[^}]*justify-self:\s*center")
        self.assertRegex(styles, r"\.output-settings-card-meta\s*\{[^}]*text-align:\s*center")

    def test_summary_card_visuals_share_one_stroke_weight_and_color(self) -> None:
        styles = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")
        shared_border = r"border:\s*1px\s+solid\s+color-mix\(in srgb,\s*var\(--primary\)\s*40%,\s*var\(--line\)\)"

        self.assertRegex(styles, rf"\.output-settings-ratio-frame\s*\{{[^}}]*{shared_border}")
        self.assertRegex(styles, rf"\.output-settings-count-card\s*\{{[^}}]*{shared_border}")
        self.assertRegex(styles, rf"\.output-settings-format-visual,\s*\.output-settings-resolution-visual\s*\{{[^}}]*{shared_border}")

    def test_four_wide_outputs_use_a_two_by_two_count_grid(self) -> None:
        source = Path("codex_image/webui/frontend/src/output-settings-lock.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")

        self.assertIn('visual.classList.toggle("is-wide-four", wideFour)', source)
        self.assertRegex(styles, r"\.output-settings-count-visual\.is-wide-four\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:\s*repeat\(2,\s*max-content\)")
        self.assertRegex(styles, r"\.output-settings-count-visual\.is-wide-four\s+\.output-settings-count-card\s*\{[^}]*max-width:\s*46px")

    def test_ratio_value_has_no_pill_background_or_shadow(self) -> None:
        styles = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")

        self.assertRegex(styles, r"\.output-settings-ratio-value\s*\{[^}]*padding:\s*0")
        self.assertRegex(styles, r"\.output-settings-ratio-value\s*\{[^}]*border-radius:\s*0")
        self.assertRegex(styles, r"\.output-settings-ratio-value\s*\{[^}]*background:\s*transparent")
        self.assertRegex(styles, r"\.output-settings-ratio-value\s*\{[^}]*box-shadow:\s*none")

    def test_locked_summary_overlays_the_unchanged_editor_stage(self) -> None:
        source = Path("codex_image/webui/frontend/src/output-settings-lock.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")

        self.assertIn('panel?.classList.toggle("is-locked-view", visible)', source)
        self.assertRegex(
            styles,
            r"\.output-settings-stage\s*\{[^}]*position:\s*relative",
        )
        self.assertRegex(
            styles,
            r"\.output-settings-locked-summary\s*\{[^}]*position:\s*absolute[^}]*inset:\s*0[^}]*min-height:\s*0",
        )
        self.assertRegex(
            styles,
            r"\.output-panel\.is-locked-view\s+\.settings-grid\s*\{[^}]*visibility:\s*hidden[^}]*pointer-events:\s*none",
        )
        self.assertNotIn('els.settingsGrid?.classList.toggle("hidden", visible)', source)

    def test_unlocked_output_panel_keeps_the_remote_natural_flow(self) -> None:
        styles = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")
        self.assertNotRegex(styles, r"\.output-panel:not\(\.is-locked-view\)\s*\{")
        self.assertNotRegex(
            styles,
            r"\.output-panel:not\(\.is-locked-view\)\s+\.settings-grid\s*\{[^}]*overflow-y:\s*auto",
        )

    def test_extra_short_summary_compacts_inside_the_original_grid_budget(self) -> None:
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")
        marker = "/* Continuous locked-summary density; viewport height changes do not create a new layout band. */"
        desktop_marker = "@media (max-height: 1390px) and (min-width: 900px)"
        block = responsive[responsive.index(marker):responsive.index(desktop_marker)]
        self.assertRegex(
            block,
            r"\.controls-col\s+\.output-settings-summary-card\s*\{[^}]*"
            r"min-height:\s*clamp\(82px,[^}]*166px\)",
        )
        self.assertRegex(
            block,
            r"\.controls-col\s+\.output-settings-ratio-visual,\s*"
            r"\.controls-col\s+\.output-settings-count-visual\s*\{[^}]*"
            r"min-height:\s*clamp\(40px,[^}]*92px\)",
        )
        self.assertNotIn("output-settings-editor-height", responsive)

    def test_short_height_summary_compaction_is_not_limited_to_desktop_widths(self) -> None:
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")
        marker = "/* Continuous locked-summary density; viewport height changes do not create a new layout band. */"
        desktop_marker = "@media (max-height: 1390px) and (min-width: 900px)"

        self.assertIn(marker, responsive)
        block = responsive[responsive.index(marker):responsive.index(desktop_marker)]
        self.assertNotIn("@media", block)
        self.assertRegex(
            block,
            r"\.controls-col\s+\.output-settings-summary-card\s*\{[^}]*"
            r"min-height:\s*clamp\(82px,[^}]*166px\)",
        )
        self.assertRegex(
            block,
            r"\.controls-col\s+\.output-settings-format-visual,\s*"
            r"\.controls-col\s+\.output-settings-resolution-visual\s*\{[^}]*"
            r"width:\s*clamp\(46px,[^}]*86px\)",
        )
        self.assertRegex(
            block,
            r"\.controls-col\s+\.output-settings-summary-details\s*\{[^}]*"
            r"margin-top:\s*clamp\(4px,[^}]*18px\)[^}]*"
            r"padding-top:\s*clamp\(4px,[^}]*18px\)",
        )

    def test_task_summary_footer_keeps_hint_and_adoption_action_in_flow(self) -> None:
        source = Path("codex_image/webui/frontend/src/output-settings-lock.ts").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")

        self.assertIn('const footer = createElement("div", "output-settings-summary-footer")', source)
        self.assertIn("footer.append(hint)", source)
        self.assertIn("footer.append(els.outputSettingsTaskAction)", source)
        self.assertIn("root.append(main, footer)", source)
        self.assertRegex(
            styles,
            r"\.output-settings-summary-footer\s*\{[^}]*"
            r"grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto",
        )
        self.assertRegex(
            styles,
            r"\.output-settings-task-action\s*\{[^}]*position:\s*static",
        )
        self.assertNotIn("padding-right: 190px", styles)


if __name__ == "__main__":
    import unittest

    unittest.main()
