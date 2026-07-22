from __future__ import annotations

from pathlib import Path

from tests.webui_helpers import WebUIStaticTestCase


class GeminiAttributionFrontendContractTests(WebUIStaticTestCase):
    def test_untrusted_search_html_is_confined_to_a_sandboxed_iframe(self) -> None:
        source = Path(
            "codex_image/webui/frontend/src/grounding-attribution.ts"
        ).read_text(encoding="utf-8")

        self.assertIn('createElement("iframe")', source)
        self.assertIn("srcdoc", source)
        self.assertIn("Content-Security-Policy", source)
        self.assertIn('<base target="_blank">', source)
        self.assertIn("sandbox", source)
        self.assertNotIn("allow-scripts", source)
        self.assertNotIn("allow-same-origin", source)
        self.assertNotIn(".innerHTML", source)

    def test_only_https_containing_page_links_are_rendered(self) -> None:
        source = Path(
            "codex_image/webui/frontend/src/grounding-attribution.ts"
        ).read_text(encoding="utf-8")

        self.assertIn('url.protocol !== "https:"', source)
        self.assertIn('link.rel = "noopener noreferrer"', source)
        self.assertIn("page_uri", source)
        self.assertIn("image_uri", source)

    def test_preview_sidebar_and_full_history_integrate_attribution(self) -> None:
        preview = Path("codex_image/webui/frontend/src/task-preview.ts").read_text(
            encoding="utf-8"
        )
        task_list = Path(
            "codex_image/webui/frontend/src/task-list-render.ts"
        ).read_text(encoding="utf-8")
        history = Path("codex_image/webui/frontend/src/history.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("syncGroundingAttribution", preview)
        self.assertIn("groundingAttributionKey", preview)
        self.assertIn("groundingSourceCount", task_list)
        self.assertIn("createGroundingAttribution", history)

    def test_attribution_module_is_part_of_both_frontend_bundles(self) -> None:
        for source_map_path in (
            "codex_image/webui/static/app.js.map",
            "codex_image/webui/static/history.js.map",
        ):
            source = Path(source_map_path).read_text(encoding="utf-8")
            self.assertIn("grounding-attribution.ts", source)
