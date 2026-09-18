from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class RuntimeFeedbackFrontendTests(unittest.TestCase):
    def test_runtime_feedback(self) -> None:
        node = shutil.which("node")
        esbuild = Path("node_modules/.bin/esbuild")
        if node is None or not esbuild.exists():
            self.skipTest("node and npm install are required for frontend behavior tests")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "runtime-feedback.test.mjs"
            build = subprocess.run(
                [str(esbuild), "tests/frontend/runtime_feedback.test.ts", "--bundle",
                 "--platform=node", "--format=esm", "--target=node20",
                 f"--outfile={output}", "--log-level=warning"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run(
                [node, "--test", str(output)], capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
