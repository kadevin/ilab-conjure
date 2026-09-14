from __future__ import annotations

from pathlib import Path
import unittest


class WebUIShortHeightContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.responsive = Path(
            "codex_image/webui/static/styles/80-utilities-responsive.css"
        ).read_text(encoding="utf-8")
        self.layout = Path(
            "codex_image/webui/static/styles/30-layout-top-nav-panels.css"
        ).read_text(encoding="utf-8")

    def test_short_workspace_uses_one_remote_density_rule(self) -> None:
        marker = "@media (max-height: 1390px) and (min-width: 900px)"
        self.assertIn(marker, self.responsive)
        self.assertEqual(self.responsive.count(f"{marker} {{"), 1)
        start = self.responsive.index(marker)
        end = self.responsive.index("@media (max-width: 640px)", start)
        block = self.responsive[start:end]

        self.assertRegex(
            block,
            r"\.controls-col\s*\{[^}]*--compact-image-panel-height:\s*clamp\("
            r"[\s\S]*--compact-prompt-panel-height:\s*clamp\(",
        )
        self.assertRegex(
            block,
            r"\.controls-col\s+\.image-panel\s*\{[^}]*flex:\s*1\s+1\s+var\(--compact-image-panel-height\)"
            r"[^}]*min-height:\s*var\(--compact-image-panel-height\)",
        )
        self.assertRegex(
            block,
            r"\.controls-col\s+\.prompt-panel\s*\{[^}]*flex:\s*1\.15\s+1\s+var\(--compact-prompt-panel-height\)"
            r"[^}]*min-height:\s*var\(--compact-prompt-panel-height\)",
        )
        self.assertRegex(
            block,
            r"\.controls-col\s+\.output-panel\s*\{[^}]*flex:\s*0\s+0\s+auto",
        )
        self.assertNotRegex(block, r"\.controls-col\s+\.output-settings-stage\s*\{")
        self.assertNotIn("align-content: space-between", block)
        self.assertIn("grid-template-rows: repeat(2, var(--compact-settings-segment-height))", block)
        self.assertNotIn("--mode-settings-stable-height", block)
        self.assertNotIn("output-settings-editor-height", block)

    def test_short_workspace_compacts_without_reflowing_output_settings(self) -> None:
        marker = "@media (max-height: 1390px) and (min-width: 900px)"
        start = self.responsive.index(marker)
        end = self.responsive.index("@media (max-width: 640px)", start)
        block = self.responsive[start:end]
        narrow_height_marker = "@media (max-height: 1100px) and (min-width: 900px)"
        container_marker = "@container workspace (max-width: 1180px)"
        self.assertIn(narrow_height_marker, block)
        narrow_height_start = self.responsive.index(narrow_height_marker, start)
        container_start = self.responsive.index(container_marker, narrow_height_start)
        top_level = self.responsive[start:container_start]
        narrow_container = self.responsive[container_start:end]

        self.assertRegex(
            block,
            r"\.dashboard\s*\{[^}]*--compact-dashboard-padding:\s*clamp\(",
        )
        self.assertRegex(
            block,
            r"\.controls-col\s+\.image-panel\s*\{[^}]*flex:\s*1\s+1\s+var\(--compact-image-panel-height\)",
        )
        self.assertRegex(
            block,
            r"\.controls-col\s+\.prompt-panel\s*\{[^}]*flex:\s*1\.15\s+1\s+var\(--compact-prompt-panel-height\)",
        )
        self.assertRegex(
            block,
            r"\.controls-col\s+\.output-panel\s*\{[^}]*flex:\s*0\s+0\s+auto",
        )
        self.assertNotRegex(top_level, r"\.mode-specific-settings\s*\{[^}]*grid-template-columns")
        self.assertNotRegex(top_level, r"\.quantity-quality-row\s*\{[^}]*display:\s*contents")
        self.assertNotRegex(top_level, r"\.(?:orientation|resolution|ratio|quantity|quality|moderation)-field\s*\{[^}]*grid-row")
        self.assertNotRegex(top_level, r"#(?:promptFidelityField|pixelPreview|outputFormatField)\s*\{[^}]*grid-row")
        self.assertNotRegex(narrow_container, r"\.mode-specific-settings\s*\{[^}]*grid-template-columns")
        output_styles = Path("codex_image/webui/static/styles/70-output-settings.css").read_text(encoding="utf-8")
        self.assertRegex(output_styles, r"\.model-tool-row\s*\{[^}]*display:\s*flex[^}]*flex-wrap:\s*wrap")
        self.assertRegex(
            narrow_container,
            r"\.settings-grid\.custom-size-mode\s*\{[^}]*--custom-size-mode-card-height:\s*clamp\(\s*105px",
        )
        self.assertRegex(
            narrow_container,
            r"--custom-size-mode-card-height:\s*clamp\(\s*105px,\s*calc\(14\.76dvh\s*-\s*8\.4px\),\s*154px",
        )
        self.assertNotIn("--mode-settings-stable-height", narrow_container)

    def test_short_workspace_keeps_all_section_headings_visible(self) -> None:
        self.assertNotIn("@media (max-height: 860px)", self.responsive)
        self.assertNotRegex(
            self.responsive,
            r"\.controls-col\s+\.image-panel\s+\.panel-heading\s*\{[^}]*height:\s*0",
        )
        self.assertNotRegex(
            self.responsive,
            r"\.controls-col\s+\.output-settings-header\s*\{[^}]*height:\s*0",
        )
        self.assertNotRegex(
            self.responsive,
            r"\.controls-col\s+\.panel-heading h2[\s\S]*clip-path:\s*inset\(50%\)",
        )

    def test_compact_topbar_subtracts_its_real_height_from_both_columns(self) -> None:
        marker = "@media (max-height: 1390px) and (min-width: 900px) and (max-width: 1180px)"
        self.assertIn(marker, self.responsive)
        block = self.responsive[self.responsive.index(marker):]
        formula = (
            r"calc\(\s*100dvh\s*-\s*var\(--header-height\)\s*-\s*64px\s*-\s*"
            r"var\(--compact-dashboard-padding\)\s*-\s*var\(--compact-dashboard-padding\)\s*\)"
        )
        self.assertRegex(
            block,
            rf"\.preview-col,\s*\.controls-col\s*\{{[^}}]*min-height:\s*{formula}[^}}]*height:\s*{formula}",
        )
        self.assertRegex(
            self.responsive,
            r"@media\s*\(max-width:\s*1180px\)[\s\S]*"
            r"\.sidebar\s*\{[^}]*height:\s*64px[^}]*flex:\s*0\s+0\s+64px",
        )
        self.assertRegex(
            self.responsive,
            r"@media\s*\(max-width:\s*1180px\)[\s\S]*"
            r"\.main-wrapper\s*\{[^}]*--compact-prompt-panel-min:\s*124px",
        )

    def test_compact_shell_adjustments_fade_out_at_the_height_boundary(self) -> None:
        shell = self.responsive[
            self.responsive.index("@media (max-width: 1180px)") :
            self.responsive.index("@container workspace (max-width: 1100px)")
        ]
        for name, maximum in (
            ("panel", 15),
            ("settings", 4),
            ("image", 12),
            ("action", 2),
        ):
            self.assertRegex(
                shell,
                rf"--compact-{name}-shell-adjustment:\s*clamp\(0px,\s*calc\([^;]*dvh\),\s*{maximum}px\)",
            )
            self.assertNotIn(
                f"--compact-{name}-shell-adjustment: {maximum}px;",
                shell,
            )

    def test_page_geometry_remains_natural_outside_short_density(self) -> None:
        self.assertRegex(
            self.layout,
            r"\.dashboard\s*\{[^}]*overflow-y:\s*auto[^}]*align-content:\s*safe\s+center",
        )
        controls = self.layout[
            self.layout.index(".controls-col {"):self.layout.index(".preview-col {")
        ]
        self.assertNotIn("overflow-y", controls)
        self.assertNotIn("height: 100%", controls)
        self.assertNotIn("Tall two-column workspaces", self.responsive)
        self.assertRegex(
            self.layout,
            r"\.nav-actions\s*\{[^}]*justify-content:\s*flex-end",
        )
        self.assertRegex(
            self.responsive,
            r"@container workspace \(max-width:\s*899px\)[\s\S]*"
            r"\.controls-col\s*\{[^}]*height:\s*auto[^}]*min-height:\s*auto[^}]*overflow:\s*visible",
        )
        self.assertRegex(
            self.responsive,
            r"@container workspace \(max-width:\s*899px\)[\s\S]*"
            r"\.preview-col\s*\{[^}]*height:\s*auto[^}]*min-height:\s*260px[^}]*overflow:\s*visible",
        )


if __name__ == "__main__":
    unittest.main()
