from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class HistoryFrontendTests(unittest.TestCase):
    """Run the history controllers through the same bundler as the WebUI."""

    def run_typescript(self, name: str) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / f"{name}.test.mjs"
            build = subprocess.run(
                [str(esbuild), f"tests/frontend/{name}.test.ts", "--bundle",
                 "--platform=node", "--format=esm", "--target=node20",
                 f"--outfile={output}", "--log-level=warning"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run(
                [node, "--test", str(output)], capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_backup(self) -> None:
        self.run_typescript("history_backup")

    def test_import(self) -> None:
        self.run_typescript("history_import")

    def test_position_restore(self) -> None:
        self.run_typescript("history_position_restore")

    def test_scroll_memory(self) -> None:
        self.run_typescript("history_scroll_memory")

    def test_controllers(self) -> None:
        self.run_typescript("history_controllers")
