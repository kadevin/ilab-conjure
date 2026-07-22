from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from tests.webui_helpers import WebUIStaticTestCase


class TaskParameterHistoryFrontendTests(WebUIStaticTestCase):
    def test_parameter_migration_feedback_is_transient_and_only_follows_task_adoption(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        parameters_source = Path("codex_image/webui/frontend/src/model-parameters.ts").read_text(encoding="utf-8")
        inspector_source = Path("codex_image/webui/frontend/src/task-parameter-inspector.ts").read_text(encoding="utf-8")
        notifications_source = Path("codex_image/webui/frontend/src/task-notifications.ts").read_text(encoding="utf-8")
        layout_styles = Path("codex_image/webui/static/styles/30-layout-top-nav-panels.css").read_text(encoding="utf-8")

        self.assertNotIn("parameterMigrationNotice", html)
        self.assertNotIn("migrationNotice(", parameters_source)
        self.assertIn("notifyParameterMigration(report)", inspector_source)
        self.assertIn("showTransientNotice,", notifications_source)
        self.assertIn(".transient-notice-toast", layout_styles)

    def test_history_inspection_is_separate_from_explicit_adoption(self) -> None:
        source = Path("codex_image/webui/frontend/src/task-parameter-inspector.ts").read_text(encoding="utf-8")

        self.assertIn("inspectTaskParameters", source)
        self.assertIn("clearTaskParameterInspection", source)
        self.assertIn("adoptTaskParameters", source)
        self.assertIn("legacyGenerationSnapshot", source)
        inspect_body = source[source.index("export function inspectTaskParameters"):source.index("export function clearTaskParameterInspection")]
        self.assertNotIn("selectConcreteModel", inspect_body)
        self.assertNotIn("selectGenerationProvider", inspect_body)
        self.assertNotIn("parameterDraftsByModel", inspect_body)

    def test_history_and_parameter_migration_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "model-parameters-history.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/model_parameters_history.test.ts",
                    "--bundle",
                    "--platform=node",
                    "--format=esm",
                    "--target=node20",
                    f"--outfile={output}",
                    "--log-level=warning",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run(
                [node, "--test", str(output)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
