from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient


class WebUIFrontendBehaviorTests(unittest.TestCase):
    def test_task_submission_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "task-submission-behavior.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/task_submission_behavior.test.ts",
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

    def test_user_config_backup_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "user-config-backup.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/user_config_backup.test.ts",
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

    def test_history_selection_shortcuts_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "history-selection-shortcuts.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/history_selection_shortcuts.test.ts",
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

    def test_history_action_panel_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "history-action-panel.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/history_action_panel.test.ts",
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

    def test_history_grid_resize_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "history-grid-resize.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/history_grid_resize.test.ts",
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

    def test_api_provider_sort_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "api-provider-sort.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/api_provider_sort.test.ts",
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

    def test_api_provider_credentials_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "api-provider-credentials.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/api_provider_credentials.test.ts",
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

    def test_history_task_reveal_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "history-task-reveal.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/history_task_reveal.test.ts",
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

    def test_history_active_filter_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "history-active-filters.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/history_active_filters.test.ts",
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

    def test_adjacent_prompt_snippet_chips_expand_before_submission(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "prompt-snippet-expansion.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/prompt_snippet_expansion.test.ts",
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

    def test_lightbox_zoom_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "lightbox-zoom.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/lightbox_zoom.test.ts",
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

    def test_task_card_swipe_logic(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "task-card-swipe-logic.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/task_card_swipe_logic.test.ts",
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

    def test_task_batch_selection_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "task-batch-selection.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/task_batch_selection.test.ts",
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

    def test_staged_references_survive_history_round_trip(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "staged-references-session.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/staged_references_session.test.ts",
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

    def test_queue_transition_render_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "queue-transition-render.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/queue_transition_render.test.ts",
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

    def test_history_realtime_refresh_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "history-realtime-refresh.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/history_realtime_refresh.test.ts",
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

    def test_task_snapshot_reconcile_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "task-snapshot-reconcile.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/task_snapshot_reconcile.test.ts",
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

    def test_task_sidebar_auto_load_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "task-sidebar-auto-load.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/task_sidebar_auto_load.test.ts",
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

    def test_segmented_indicator_initial_position_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "segmented-indicator-behavior.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/segmented_indicator_behavior.test.ts",
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

    def test_task_model_summary_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "task-model-summary.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/task_model_summary.test.ts",
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

    def test_provider_binding_editor_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "provider-binding-editor.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/provider_binding_editor.test.ts",
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

    def test_network_request_policy_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "network-request-policy.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/network_request_policy.test.ts",
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

    def test_real_nano_defaults_survive_fixed_controls_and_resolve(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        from codex_image.webui.app import create_app
        from tests.test_provider_registry import command_fixture, resolver_fixture

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "outputs",
                api_settings_path=root / "api-settings.json",
                auth_settings_path=root / "auth-settings.json",
                webui_settings_path=root / "webui-settings.json",
                client_factory=lambda: object(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            with TestClient(app) as client:
                payload = client.get("/api/generation-catalog").json()
            fixture = root / "generation-catalog.json"
            fixture.write_text(json.dumps(payload), encoding="utf-8")
            output = root / "catalog-default-parameters.mjs"
            build = subprocess.run(
                [str(esbuild), "tests/frontend/catalog_default_parameters.ts", "--bundle", "--platform=node",
                 "--format=esm", "--target=node20", f"--outfile={output}", "--log-level=warning"],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run(
                [node, str(output)], check=False, capture_output=True, text=True,
                env={**os.environ, "GENERATION_CATALOG_FIXTURE": str(fixture)},
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            parameters_by_model = json.loads(result.stdout)

        self.assertEqual(parameters_by_model["nano-banana-pro"]["canvas.resolution"], "1K")
        for model_id, parameters in parameters_by_model.items():
            with self.subTest(model=model_id):
                resolver = resolver_fixture(
                    canonical_model_id=model_id,
                    mapped_parameter_ids=frozenset(parameters),
                )
                plan = resolver.resolve(command_fixture(
                    canonical_model_id=model_id,
                    parameters=parameters,
                ))
                self.assertEqual(dict(plan.command.parameters), parameters)

    def test_real_generation_catalog_payload_matches_frontend_validator(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "outputs",
                api_settings_path=root / "api-settings.json",
                auth_settings_path=root / "auth-settings.json",
                webui_settings_path=root / "webui-settings.json",
                client_factory=lambda: object(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            with TestClient(app) as client:
                payload = client.get("/api/generation-catalog").json()
            fixture = root / "generation-catalog.json"
            fixture.write_text(json.dumps(payload), encoding="utf-8")
            output = root / "catalog-payload-parity.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/catalog_payload_parity.test.ts",
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
            env = {**os.environ, "GENERATION_CATALOG_FIXTURE": str(fixture)}
            result = subprocess.run(
                [node, "--test", str(output)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_model_provider_selection_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "model-provider-behavior.test.mjs"
            build = subprocess.run(
                [
                    str(esbuild),
                    "tests/frontend/model_provider_behavior.test.ts",
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
