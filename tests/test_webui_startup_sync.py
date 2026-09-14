from pathlib import Path
import shutil
import subprocess
import unittest


class WebUIStartupSyncTests(unittest.TestCase):
    def test_http_and_realtime_state_reconciliation(self) -> None:
        node = shutil.which("node")
        if not node or not Path("node_modules/typescript").exists():
            self.skipTest("node and npm install are required for frontend behavior tests")
        result = subprocess.run(
            [node, "--test", "tests/frontend/startup_sync.test.cjs"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
