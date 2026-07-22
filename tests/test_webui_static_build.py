from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from tests.webui_helpers import WebUIStaticTestCase


class WebUIStaticBuildTests(WebUIStaticTestCase):
    def test_frontend_typescript_tooling_exists(self) -> None:
        package_json = Path("package.json").read_text(encoding="utf-8")
        tsconfig = Path("tsconfig.webui.json").read_text(encoding="utf-8")
        types = Path("codex_image/webui/frontend/src/types.ts").read_text(encoding="utf-8")

        self.assertIn('"typecheck:webui"', package_json)
        self.assertIn('"build:webui"', package_json)
        self.assertIn('"typescript"', package_json)
        self.assertIn('"esbuild"', package_json)
        self.assertIn('"strict": true', tsconfig)
        self.assertIn('"noUncheckedIndexedAccess": true', tsconfig)
        self.assertIn("export interface WebUITask", types)
        self.assertIn("export interface QueueState", types)
        self.assertIn("export interface TaskOutputRecord", types)
    def test_frontend_source_map_matches_typescript_entrypoint_sources(self) -> None:
        source_map = json.loads(Path("codex_image/webui/static/app.js.map").read_text(encoding="utf-8"))

        sources = source_map.get("sources") or []
        sources_content = source_map.get("sourcesContent") or []
        self.assertEqual(len(sources), len(sources_content))
        self.assertIn("../frontend/legacy-app.js", sources)
        self.assertIn("../frontend/src/main.ts", sources)
        self.assertIn("../frontend/src/bootstrap.ts", sources)
        self.assertIn("../frontend/src/boot.ts", sources)
        self.assertIn("../frontend/src/event-bindings.ts", sources)
        self.assertIn("../frontend/src/model-catalog.ts", sources)
        self.assertIn("../frontend/src/model-selection.ts", sources)
        self.assertIn("../frontend/src/provider-selection.ts", sources)
        self.assertIn("../frontend/src/legacy-bridge.ts", sources)
        self.assertIn("../frontend/src/state-defaults.ts", sources)
        self.assertIn("../frontend/src/elements.ts", sources)
        self.assertIn("../frontend/src/runtime-feedback.ts", sources)
        self.assertIn("../frontend/src/webui-utils.ts", sources)
        self.assertIn("../frontend/src/queue.ts", sources)
        self.assertIn("../frontend/src/tasks.ts", sources)
        self.assertIn("../frontend/src/prompt.ts", sources)
        self.assertIn("../frontend/src/input-sources.ts", sources)
        self.assertIn("../frontend/src/image-strip.ts", sources)
        self.assertIn("../frontend/src/gallery-categories.ts", sources)
        self.assertIn("../frontend/src/recent-assets.ts", sources)
        self.assertIn("../frontend/src/quick-gallery.ts", sources)
        self.assertIn("../frontend/src/gallery-grid.ts", sources)
        self.assertIn("../frontend/src/gallery-item-actions.ts", sources)
        self.assertIn("../frontend/src/gallery.ts", sources)
        self.assertIn("../frontend/src/api-settings.ts", sources)
        self.assertIn("../frontend/src/auth-source.ts", sources)
        self.assertIn("../frontend/src/api-provider-settings.ts", sources)
        self.assertIn("../frontend/src/api-mode-settings.ts", sources)
        self.assertNotIn("../frontend/src/account-quota.ts", sources)
        self.assertIn("../frontend/src/storage-settings.ts", sources)
        self.assertIn("../frontend/src/system-settings.ts", sources)
        self.assertIn("../frontend/src/color-palette.ts", sources)
        self.assertIn("../frontend/src/form-controls.ts", sources)
        self.assertIn("../frontend/src/size-presets.ts", sources)
        self.assertIn("../frontend/src/main-model-combobox.ts", sources)
        self.assertIn("../frontend/src/custom-size-controls.ts", sources)
        self.assertIn("../frontend/src/output-controls.ts", sources)
        self.assertIn("../frontend/src/segmented-indicator.ts", sources)
        self.assertIn("../frontend/src/prompt-colors.ts", sources)
        self.assertIn("../frontend/src/prompt-snippets.ts", sources)
        self.assertIn("../frontend/src/prompt-serialization.ts", sources)
        self.assertIn("../frontend/src/prompt-gallery-chips.ts", sources)
        self.assertIn("../frontend/src/prompt-editor-paste.ts", sources)
        self.assertIn("../frontend/src/prompt-editor-events.ts", sources)
        self.assertIn("../frontend/src/prompt-model.ts", sources)
        self.assertIn("../frontend/src/task-list-controls.ts", sources)
        self.assertIn("../frontend/src/task-context-menu.ts", sources)
        self.assertIn("../frontend/src/task-notifications.ts", sources)
        self.assertIn("../frontend/src/task-history-anchors.ts", sources)
        self.assertIn("../frontend/src/task-list-render.ts", sources)
        self.assertIn("../frontend/src/task-actions.ts", sources)
        self.assertIn("../frontend/src/task-submit.ts", sources)
        self.assertIn("../frontend/src/task-batch-controls.ts", sources)
        self.assertIn("../frontend/src/task-archive-controls.ts", sources)
        self.assertIn("../frontend/src/task-derived.ts", sources)
        self.assertIn("../frontend/src/task-preview.ts", sources)
        self.assertIn("../frontend/src/grounding-attribution.ts", sources)
        self.assertIn("../frontend/src/task-selection.ts", sources)
        self.assertIn("../frontend/src/overlay-popovers.ts", sources)
        self.assertIn("../frontend/src/shell-ui.ts", sources)
        self.assertIn("../frontend/src/lightbox.ts", sources)
        self.assertIn("../frontend/src/image-editor.ts", sources)
        source_root = Path("codex_image/webui/static")
        for source, source_content in zip(sources, sources_content):
            if "node_modules/" in source:
                self.assertNotEqual("", source_content)
                continue
            source_path = (source_root / source).resolve()
            self.assertEqual(source_path.read_text(encoding="utf-8"), source_content)

    def test_css_bundle_matches_manifest_sources(self) -> None:
        manifest_path = Path("codex_image/webui/static/styles/manifest.json")
        styles_dir = manifest_path.parent
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertIsInstance(manifest, list)
        self.assertGreater(len(manifest), 3)
        self.assertEqual(len(manifest), len(set(manifest)))

        expected_chunks = []
        for filename in manifest:
            self.assertIsInstance(filename, str)
            self.assertTrue(filename.endswith(".css"))
            source = (styles_dir / filename).read_text(encoding="utf-8").rstrip()
            expected_chunks.append(f"/* source: styles/{filename} */\n{source}")

        expected = "\n\n".join(expected_chunks) + "\n"
        actual = Path("codex_image/webui/static/styles.css").read_text(encoding="utf-8")
        self.assertEqual(expected, actual)

    def test_generated_frontend_bundle_matches_typescript_entrypoint(self) -> None:
        esbuild = Path("node_modules/.bin/esbuild")
        if not esbuild.exists():
            self.skipTest("npm install is required for frontend bundle parity checks")

        static_dir = Path("codex_image/webui/static")
        generated_app = static_dir / ".app.test-build.js"
        generated_map = static_dir / ".app.test-build.js.map"
        try:
            result = subprocess.run(
                [
                    str(esbuild),
                    "codex_image/webui/frontend/src/main.ts",
                    "--bundle",
                    "--format=iife",
                    "--target=es2020",
                    f"--outfile={generated_app}",
                    "--sourcemap",
                    "--log-level=warning",
                ],
                check=False,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            generated_js = generated_app.read_text(encoding="utf-8").replace(
                "//# sourceMappingURL=.app.test-build.js.map",
                "//# sourceMappingURL=app.js.map",
            )
            committed_js = (static_dir / "app.js").read_text(encoding="utf-8")
            self.assertEqual(committed_js, generated_js)
            self.assertEqual(
                (static_dir / "app.js.map").read_text(encoding="utf-8"),
                generated_map.read_text(encoding="utf-8"),
            )
        finally:
            generated_app.unlink(missing_ok=True)
            generated_map.unlink(missing_ok=True)
    def test_javascript_declares_model_element(self) -> None:
        script = self._frontend_script_source()

        self.assertIn("model: document.querySelector", script)
    def test_webui_launchers_write_server_log(self) -> None:
        launcher_sources = [
            Path("Start WebUI.command").read_text(encoding="utf-8"),
            Path("Start WebUI Debug.command").read_text(encoding="utf-8"),
            Path("Start WebUI.bat").read_text(encoding="utf-8"),
        ]

        for source in launcher_sources:
            self.assertIn("webui-server.log", source)
    def test_frontend_scripts_have_valid_javascript_syntax(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is required for frontend syntax checks")

        app_script = Path("codex_image/webui/static/app.js")
        self._assert_valid_javascript(node, app_script.read_text(encoding="utf-8"), str(app_script))

        index_html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        inline_scripts = re.findall(r"<script>(.*?)</script>", index_html, flags=re.DOTALL)
        for index, script in enumerate(inline_scripts, start=1):
            self._assert_valid_javascript(node, script, f"index.html inline script {index}")
