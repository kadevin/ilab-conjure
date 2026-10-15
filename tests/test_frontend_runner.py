from __future__ import annotations

from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tests import frontend_runner as runner


class FrontendRunnerTests(unittest.TestCase):
    def test_cli_fails_when_discovery_finds_no_suites(self) -> None:
        with TemporaryDirectory() as directory, \
             patch.object(runner, "FRONTEND", Path(directory)), \
             patch("sys.argv", ["frontend_runner"]), \
             redirect_stderr(io.StringIO()) as diagnostics:
            with self.assertRaises(SystemExit) as raised:
                runner.main()
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("no pure frontend suites found", diagnostics.getvalue())

    def test_pure_discovery_excludes_only_backend_fixture_suites(self) -> None:
        discovered = set(runner.pure_frontend_suites())
        all_suites = {
            path.name for path in runner.FRONTEND.iterdir()
            if path.name.endswith((".test.ts", ".test.cjs"))
        }
        self.assertTrue(discovered)
        self.assertEqual(all_suites - discovered, runner.BACKEND_FIXTURE_SUITES)

    def test_python_matrix_skips_pure_suites_but_still_executes_backend_contracts(self) -> None:
        with patch.dict(os.environ, {runner.SKIP_FRONTEND_ENV: "1"}):
            with self.assertRaises(unittest.SkipTest):
                runner.run_frontend(self, "ux_recovery.test.ts")
            with patch.object(runner, "frontend_tools", return_value=("node", Path("esbuild"))), \
                 patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
                runner.run_frontend(self, "catalog_payload_parity.test.ts", backend_fixture=True)
                self.assertEqual(run.call_count, 2)

    def test_failed_bundle_stops_execution_and_surfaces_diagnostics(self) -> None:
        with patch.dict(os.environ, {runner.SKIP_FRONTEND_ENV: "0"}), \
             patch.object(runner, "frontend_tools", return_value=("node", Path("esbuild"))), \
             patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "invalid TypeScript")) as run:
            with self.assertRaisesRegex(AssertionError, "invalid TypeScript"):
                runner.run_frontend(self, "ux_recovery.test.ts")
            self.assertEqual(run.call_count, 1)

    def test_failed_node_suite_is_not_reported_as_success(self) -> None:
        with patch.dict(os.environ, {runner.SKIP_FRONTEND_ENV: "0"}), \
             patch.object(runner, "frontend_tools", return_value=("node", Path("esbuild"))), \
             patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "failing assertion", "")):
            with self.assertRaisesRegex(AssertionError, "failing assertion"):
                runner.run_frontend(self, "startup_sync.test.cjs")
