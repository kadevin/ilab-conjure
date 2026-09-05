from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from codex_image.webui.app import create_app


class StoragePathNoticeTests(unittest.TestCase):
    def test_retained_path_frontend_behavior(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "storage-settings.test.mjs"
            build = subprocess.run(
                [str(esbuild), "tests/frontend/storage_settings.test.ts", "--bundle",
                 "--platform=node", "--format=esm", "--target=node20",
                 f"--outfile={output}", "--log-level=warning"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run([node, "--test", str(output)], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unreadable_previous_directory_does_not_break_settings(self) -> None:
        from codex_image.webui.standard_storage import previous_default_storage_paths

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = {key: root / "current" for key in ("input_root", "output_root", "gallery_root", "source_data_root")}
            with patch.object(Path, "is_dir", side_effect=OSError("unavailable old volume")):
                self.assertEqual(previous_default_storage_paths(root / "webui-settings.json", current), {})

    def test_settings_reveal_existing_default_directories_without_moving_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            old = root / "webui-outputs"
            (old / "source-data").mkdir(parents=True)
            retained = old / "retained.txt"
            retained.write_text("synthetic old data")
            cwd = Path.cwd()
            try:
                os.chdir(root)
                app = create_app(
                    output_root=root / "selected-output",
                    webui_settings_path=root / "webui-settings.json",
                    auth_checker=lambda: False,
                    auto_start_queue=False,
                )
                with TestClient(app) as client:
                    response = client.get("/api/settings")
                    health = client.get("/api/health")
            finally:
                os.chdir(cwd)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json().get("previous_paths"), {
                "output_root": str(old),
                "source_data_root": str(old / "source-data"),
            })
            self.assertEqual(retained.read_text(), "synthetic old data")
            self.assertFalse((root / "selected-output/retained.txt").exists())
            self.assertNotIn(str(old), health.text)

    def test_current_default_directories_are_not_reported_as_previous(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            cwd = Path.cwd()
            try:
                os.chdir(root)
                app = create_app(
                    input_root=root / "webui-inputs",
                    output_root=root / "webui-outputs",
                    webui_settings_path=root / "webui-settings.json",
                    auth_checker=lambda: False,
                    auto_start_queue=False,
                )
                with TestClient(app) as client:
                    response = client.get("/api/settings")
            finally:
                os.chdir(cwd)
            self.assertEqual(response.json().get("previous_paths"), {})


if __name__ == "__main__":
    unittest.main()
