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
             patch.object(runner, "inline_frontend_tests", return_value=[]), \
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

    def test_local_discovery_executes_every_node_suite_once(self) -> None:
        from tests.test_frontend_suites import load_tests

        suite = load_tests(unittest.TestLoader(), unittest.TestSuite(), "test*.py")
        with patch.object(runner, "run_frontend") as run:
            result = unittest.TestResult()
            suite.run(result)
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
        names = [call.args[1] for call in run.call_args_list]
        self.assertCountEqual(names, runner.pure_frontend_suites())
        self.assertIn("api_provider_delete.test.ts", names)
        self.assertEqual(len(names), len(set(names)))

    def test_new_node_file_is_collected_without_a_manual_wrapper(self) -> None:
        with TemporaryDirectory() as directory, patch.object(runner, "FRONTEND", Path(directory)):
            (Path(directory) / "new_behavior.test.ts").touch()
            with patch.object(runner, "run_frontend") as run:
                runner.node_suite().run(unittest.TestResult())
            self.assertEqual(run.call_args.args[1], "new_behavior.test.ts")

    def test_compatibility_modules_do_not_duplicate_discovery(self) -> None:
        load_tests = runner.compatibility_load_tests(("api_provider_delete.test.ts",))
        self.assertEqual(load_tests(None, unittest.TestSuite(), "test*.py").countTestCases(), 0)
        self.assertEqual(load_tests(None, unittest.TestSuite(), None).countTestCases(), 1)

    def test_duplicate_node_stems_cannot_silently_hide_a_suite(self) -> None:
        with self.assertRaisesRegex(ValueError, "Duplicate frontend test name"):
            runner.node_suite(["behavior.test.ts", "behavior.test.cjs"])

    def test_inline_harnesses_skip_only_in_python_matrix(self) -> None:
        calls = []

        class Example(unittest.TestCase):
            @runner.frontend_test
            def test_inline(self):
                calls.append("executed")

        for flag, skipped in (("1", 1), ("0", 0)):
            with self.subTest(flag=flag), patch.dict(os.environ, {runner.SKIP_FRONTEND_ENV: flag}):
                result = unittest.TestResult()
                Example("test_inline").run(result)
                self.assertTrue(result.wasSuccessful())
                self.assertEqual(len(result.skipped), skipped)
        self.assertEqual(calls, ["executed"])

    def test_frontend_entrypoint_includes_marked_harnesses(self) -> None:
        names = runner.inline_frontend_tests()
        self.assertTrue(names)
        self.assertEqual(len(names), len(set(names)))
        suite = unittest.TestLoader().loadTestsFromNames(names)
        self.assertEqual(suite.countTestCases(), len(names))
        with patch.dict(os.environ, {runner.SKIP_FRONTEND_ENV: "1"}):
            result = unittest.TestResult()
            suite.run(result)
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
        self.assertEqual(len(result.skipped), len(names))

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
