import contextlib
from importlib.metadata import PackageNotFoundError
from io import StringIO
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from codex_image.runtime_security import dependency_security_error, main, pip_security_error, python_security_error


class RuntimeSecurityTests(unittest.TestCase):
    def test_python_patch_boundaries(self):
        for fixed in ((3, 11, 18), (3, 12, 16), (3, 13, 18), (3, 14, 10), (3, 15, 2)):
            with self.subTest(fixed=fixed):
                self.assertIsNone(python_security_error(fixed))
                self.assertIsNone(python_security_error((*fixed[:2], fixed[2] + 1)))
                error = python_security_error((*fixed[:2], fixed[2] - 1))
                self.assertIn("security baseline", error)
                self.assertIn("virtual environment", error)
        self.assertIsNotNone(python_security_error((3, 10, 99)))
        self.assertIsNotNone(python_security_error((3, 15, 0)))

    @staticmethod
    def _dependency_version(name, changed_name, changed_version):
        if name == changed_name:
            if changed_version is None:
                raise PackageNotFoundError(name)
            return changed_version
        return {"Pillow": "13.0.0", "certifi": "2026.10.23"}[name]

    def test_unsafe_dependencies_block_server_before_loading_app(self):
        from codex_image.webui import server
        for name, installed in (("Pillow", "12.3.0"), ("certifi", "2026.4.22"), ("certifi", None)):
            with self.subTest(package=name, installed=installed), \
                    patch("codex_image.runtime_security.version", side_effect=lambda key: self._dependency_version(key, name, installed)), \
                    patch.object(server, "import_from_string") as load, \
                    patch.object(server, "_shutdown_coordinator"), \
                    patch.object(server, "Config"), patch.object(server, "WebUIServer") as service, \
                    contextlib.redirect_stderr(StringIO()) as errors:
                service.return_value.started = True
                self.assertEqual(server.main(["fixture:app"]), 2)
                load.assert_not_called()
                service.assert_not_called()
                self.assertIn(name, errors.getvalue())

    def test_unsafe_dependencies_block_cli_before_credentials_or_network(self):
        from codex_image import cli
        for name, installed in (("Pillow", "12.3.0"), ("certifi", "2026.4.22"), ("Pillow", None)):
            with self.subTest(package=name, installed=installed), \
                    patch("codex_image.runtime_security.version", side_effect=lambda key: self._dependency_version(key, name, installed)), \
                    patch.object(cli, "_run_generate", return_value=0) as generate, \
                    contextlib.redirect_stderr(StringIO()) as errors:
                self.assertEqual(cli.main(["generate", "--prompt", "fixture", "--out", "unused.png"]), 2)
                generate.assert_not_called()
                self.assertIn(name, errors.getvalue())

    def test_pip_patch_boundary_and_missing_installer(self):
        for old in ("26.2.1", "25.3", "not installed", "26.2.2.dev0"):
            with self.subTest(version=old):
                self.assertIsNotNone(pip_security_error(old))
        for fixed in ("26.2.2", "26.3", "27.0.0"):
            with self.subTest(version=fixed):
                self.assertIsNone(pip_security_error(fixed))

    def test_runtime_dependency_boundaries(self):
        cases = (
            ("Pillow", "12.3.0", False), ("Pillow", "13.0.0rc1", False),
            ("Pillow", "13.0.0", True), ("Pillow", "13.0.0.post1", True),
            ("Pillow", "13.1.0", True), ("Pillow", None, False),
            ("certifi", "2026.10.18", False), ("certifi", "2026.10.19", True),
            ("certifi", "2026.10.23", True), ("certifi", "invalid", False),
        )
        for name, installed, accepted in cases:
            with self.subTest(package=name, installed=installed), \
                    patch("codex_image.runtime_security.version", side_effect=lambda key: self._dependency_version(key, name, installed)):
                error = dependency_security_error()
                self.assertEqual(error is None, accepted)
                if error:
                    self.assertIn(name, error)

    def test_runtime_mode_checks_packages_without_requiring_pip(self):
        with patch("codex_image.runtime_security.version", side_effect={"Pillow": "13.0.0", "certifi": "2026.10.23"}.__getitem__):
            self.assertEqual(main(["--runtime"]), 0)
        with patch("codex_image.runtime_security.version", return_value="12.3.0"), \
                contextlib.redirect_stderr(StringIO()) as errors:
            self.assertEqual(main(["--runtime"]), 2)
        self.assertIn("Pillow", errors.getvalue())

    def test_incomplete_distribution_metadata_reports_repair_instead_of_traceback(self):
        script = Path(__file__).resolve().parents[1] / "codex_image/runtime_security.py"
        with tempfile.TemporaryDirectory(prefix="conjure metadata test ") as directory:
            root = Path(directory)
            packages = {"Pillow": "13.0.0", "certifi": "2026.10.23", "pip": "26.2.2"}
            metadata_files = {}
            for name, installed in packages.items():
                info = root / f"{name}-{installed}.dist-info"
                info.mkdir()
                path = info / "METADATA"
                content = f"Metadata-Version: 2.1\nName: {name}\nVersion: {installed}\n"
                path.write_text(content)
                metadata_files[name] = (path, content)
            env = {**os.environ, "PYTHONPATH": str(root)}
            for name, (path, content) in metadata_files.items():
                flag = "--installer" if name == "pip" else "--runtime"
                for damaged in (None, f"Name: {name}\n", f"Name: {name}\nVersion: \n"):
                    with self.subTest(package=name, metadata=damaged):
                        if damaged is None:
                            path.unlink()
                        else:
                            path.write_text(damaged)
                        result = subprocess.run([sys.executable, "-S", str(script), flag],
                                                env=env, capture_output=True, text=True, timeout=10)
                        path.write_text(content)
                        self.assertEqual(result.returncode, 2, result.stderr)
                        self.assertNotIn("Traceback", result.stderr)
                        self.assertIn(name, result.stderr)
                        self.assertIn("version metadata", result.stderr)
                        self.assertIn("verified wheel" if name == "pip" else "requirements-webui.txt", result.stderr)
                result = subprocess.run([sys.executable, "-S", str(script), flag],
                                        env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_trimmed_runtime_does_not_require_pip(self):
        with patch("codex_image.runtime_security.python_security_error", return_value=None), \
                patch("codex_image.runtime_security.version", side_effect=AssertionError("pip lookup")):
            self.assertEqual(main([]), 0)

    def test_preflight_runs_without_site_packages(self):
        script = Path(__file__).resolve().parents[1] / "codex_image/runtime_security.py"
        result = subprocess.run([sys.executable, "-S", str(script)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unsafe_python_blocks_server_before_loading_app(self):
        from codex_image.webui.server import main as server_main
        with patch("codex_image.webui.server.python_security_error", return_value="unsafe Python"), \
                patch("codex_image.webui.server.import_from_string") as load, \
                contextlib.redirect_stderr(StringIO()):
            self.assertEqual(server_main(["fixture:app"]), 2)
        load.assert_not_called()

    def test_unsafe_python_blocks_cli_before_credentials_or_network(self):
        from codex_image.cli import main as cli_main
        with patch("codex_image.cli.python_security_error", return_value="unsafe Python"), \
                patch("codex_image.cli._run_generate") as generate, \
                contextlib.redirect_stderr(StringIO()):
            self.assertEqual(cli_main(["generate", "--prompt", "fixture", "--out", "unused.png"]), 2)
        generate.assert_not_called()

    def test_installer_check_reports_outdated_pip(self):
        with patch("codex_image.runtime_security.python_security_error", return_value=None), \
                patch("codex_image.runtime_security.version", return_value="26.2.1"), \
                contextlib.redirect_stderr(StringIO()) as errors:
            self.assertEqual(main(["--installer"]), 2)
        self.assertIn("pip 26.2.2 or newer", errors.getvalue())
