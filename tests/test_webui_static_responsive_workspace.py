from __future__ import annotations

from pathlib import Path
import unittest


class WebUIResponsiveWorkspaceContractTests(unittest.TestCase):
    def test_ultrawide_workspace_keeps_the_remote_bounded_geometry(self) -> None:
        layout = Path(
            "codex_image/webui/static/styles/30-layout-top-nav-panels.css"
        ).read_text(encoding="utf-8")
        responsive = Path(
            "codex_image/webui/static/styles/80-utilities-responsive.css"
        ).read_text(encoding="utf-8")

        self.assertRegex(
            layout,
            r"\.dashboard\s*\{[^}]*width:\s*min\(100%,\s*1760px\)[^}]*"
            r"grid-template-columns:\s*minmax\(520px,\s*760px\)\s+minmax\(520px,\s*1fr\)",
        )
        self.assertRegex(
            layout,
            r"\.controls-col\s*\{[^}]*max-width:\s*760px",
        )
        self.assertNotIn("@container workspace (min-width: 1761px)", responsive)
        self.assertNotIn("clamp(760px, 42%, 1120px)", responsive)

    def test_mobile_provider_selector_keeps_a_usable_width(self) -> None:
        responsive = Path(
            "codex_image/webui/static/styles/80-utilities-responsive.css"
        ).read_text(encoding="utf-8")

        self.assertRegex(
            responsive,
            r"@media \(max-width: 1180px\)[\s\S]*?"
            r"\.generation-provider-control\s*\{[^}]*"
            r"flex:\s*0\s+0\s+min\(280px,\s*78vw\)",
        )

    def test_dynamic_parameters_and_bindings_collapse_without_horizontal_overflow(self) -> None:
        output = Path(
            "codex_image/webui/static/styles/70-output-settings.css"
        ).read_text(encoding="utf-8")
        settings = Path(
            "codex_image/webui/static/styles/74-api-system-settings.css"
        ).read_text(encoding="utf-8")
        responsive = Path(
            "codex_image/webui/static/styles/80-utilities-responsive.css"
        ).read_text(encoding="utf-8")

        self.assertRegex(
            output,
            r"\.model-parameter-grid\s*\{[^}]*"
            r"grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)[^}]*"
            r"min-width:\s*0[^}]*width:\s*100%",
        )
        self.assertRegex(
            responsive,
            r"@container workspace \(max-width: 899px\)[\s\S]*?"
            r"\.model-parameter-grid\s*\{[^}]*"
            r"grid-template-columns:\s*minmax\(0,\s*1fr\)",
        )
        self.assertRegex(
            settings,
            r"@media \(max-width: 620px\)[\s\S]*?"
            r"\.provider-binding-grid\s*\{[^}]*"
            r"grid-template-columns:\s*minmax\(0,\s*1fr\)",
        )
        self.assertNotRegex(output, r"\.model-parameter-grid\s*\{[^}]*(?:height|max-height):")
        self.assertRegex(
            output,
            r"#modelParameterGrid\.model-parameter-grid\s*\{[^}]*"
            r"align-content:\s*start[^}]*"
            r"row-gap:\s*12px[^}]*"
            r"padding-block:\s*12px",
        )
        self.assertRegex(
            output,
            r"#modelParameterGrid\s+\.model-aspect-ratio-grid\s*\{[^}]*"
            r"padding-block:\s*10px",
        )
        self.assertRegex(
            output,
            r'#modelParameterGrid\s*>\s*\.model-parameter-field:not\(\[data-parameter-id="canvas\.aspect_ratio"\]\)\s*\{[^}]*'
            r"padding-block:\s*4px",
        )
        self.assertNotRegex(
            output,
            r"#modelParameterGrid\.model-parameter-grid\s*\{[^}]*"
            r"(?:align-content|justify-content):\s*(?:space-between|space-around|space-evenly)",
        )
        self.assertNotRegex(
            output,
            r'#modelParameterGrid\s*>\s*\.model-parameter-field\.full-width\[data-parameter-id="gemini\.safety_settings"\]',
        )
        self.assertRegex(
            output,
            r"\.model-aspect-ratio-grid\s*\{[^}]*"
            r"grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(62px,\s*1fr\)\)",
        )
        self.assertRegex(
            output,
            r"\.aspect-ratio-slot\s*\{[^}]*"
            r"grid-template-rows:\s*repeat\(2,\s*minmax\(34px,\s*1fr\)\)",
        )
        self.assertRegex(
            responsive,
            r"@container workspace \(max-width: 899px\)[\s\S]*?"
            r"\.model-aspect-ratio-grid\s*\{[^}]*"
            r"grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(62px,\s*1fr\)\)",
        )


if __name__ == "__main__":
    unittest.main()
