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
