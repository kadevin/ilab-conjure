from __future__ import annotations

from pathlib import Path
import re
import unittest


class OutputSettingsOverlayLayoutContractTests(unittest.TestCase):
    def test_locked_summary_overlays_the_original_settings_grid(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        styles = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")
        source = Path("codex_image/webui/frontend/src/output-settings-lock.ts").read_text(encoding="utf-8")

        stage_start = html.index('id="outputSettingsStage"')
        stage_end = html.index('class="dashboard-col preview-col"', stage_start)
        stage = html[stage_start:stage_end]
        self.assertLess(stage.index('id="outputSettingsLockedSummary"'), stage.index('id="settingsGrid"'))

        self.assertRegex(
            styles,
            r"\.output-settings-stage\s*\{[^}]*position:\s*relative",
        )
        self.assertRegex(
            styles,
            r"\.output-settings-locked-summary\s*\{[^}]*position:\s*absolute[^}]*inset:\s*0",
        )
        self.assertRegex(
            styles,
            r"\.output-panel\.is-locked-view\s+\.settings-grid\s*\{[^}]*visibility:\s*hidden[^}]*pointer-events:\s*none",
        )

        self.assertIn('els.settingsGrid?.toggleAttribute("inert", visible)', source)
        self.assertNotIn('els.settingsGrid?.classList.toggle("hidden", visible)', source)
        self.assertNotIn("measureEditorHeight", source)
        self.assertNotIn("getBoundingClientRect", source)
        self.assertNotIn("--output-settings-editor-height", source)

        compact_marker = "@media (max-height: 1390px) and (min-width: 900px)"
        compact_start = responsive.index(compact_marker)
        compact_end = responsive.index("@media (max-width: 640px)", compact_start)
        compact_block = responsive[compact_start:compact_end]
        self.assertNotRegex(compact_block, r"\.output-settings-stage\s*\{[^}]*display:\s*flex")
        self.assertNotIn("align-content: space-between", compact_block)

    def test_remote_geometry_remains_the_page_layout_authority(self) -> None:
        layout = Path("codex_image/webui/static/styles/30-layout-top-nav-panels.css").read_text(encoding="utf-8")
        responsive = Path("codex_image/webui/static/styles/80-utilities-responsive.css").read_text(encoding="utf-8")

        self.assertRegex(layout, r"\.dashboard\s*\{[^}]*width:\s*min\(100%,\s*1760px\)")
        self.assertRegex(
            layout,
            r"\.dashboard\s*\{[^}]*grid-template-columns:\s*minmax\(520px,\s*760px\)\s+minmax\(520px,\s*1fr\)",
        )
        self.assertRegex(layout, r"\.controls-col\s*\{[^}]*max-width:\s*760px")
        self.assertNotIn("Ultra-wide workspaces grow both columns", responsive)
        self.assertNotRegex(responsive, r"clamp\(760px,\s*42%,\s*1120px\)")

        # Empty-reference disclosure also responds to landscape height, but does
        # not establish a page-height or locked-summary layout band.
        responsive = responsive.replace(
            "@media (max-width: 600px), (max-height: 500px)", "@media (max-width: 600px)"
        )
        height_queries = re.findall(r"@media\s*\([^\n{]*height[^\n{]*\)", responsive)
        self.assertLessEqual(
            len(height_queries),
            4,
            "the lock summary must not create a stack of overlapping page-height bands",
        )


if __name__ == "__main__":
    unittest.main()
