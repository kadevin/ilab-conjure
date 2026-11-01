import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CA_KEYS = ("SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE")


class PackagingSecurityTests(unittest.TestCase):
    def test_trimmed_package_retains_security_checks_without_pip(self):
        with tempfile.TemporaryDirectory(prefix="conjure trimmed probe ") as directory:
            root = Path(directory)
            app = root / "app"
            dependencies = app / ".deps"
            runtime = root / "python"
            runtime.mkdir()
            (app / "codex_image").mkdir(parents=True)
            check = app / "codex_image/runtime_security.py"
            shutil.copy2(ROOT / "codex_image/runtime_security.py", check)
            (dependencies / "pip").mkdir(parents=True)
            for package, version in (("Pillow", "13.0.0"), ("certifi", "2026.10.23")):
                metadata = dependencies / f"{package}-{version}.dist-info"
                metadata.mkdir()
                (metadata / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {package}\nVersion: {version}\n")
            cleanup = subprocess.run([sys.executable, str(ROOT / "packaging/cleanup-runtime.py"),
                                      "--app-dir", str(app), "--runtime-dir", str(runtime), "--platform", "macos"],
                                     capture_output=True, text=True, timeout=15)
            self.assertEqual(cleanup.returncode, 0, cleanup.stderr)
            self.assertFalse((dependencies / "pip").exists())
            env = {**os.environ, "PYTHONPATH": str(dependencies)}
            result = subprocess.run([sys.executable, "-S", str(check), "--runtime"],
                                    env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(sys.platform != "win32" and shutil.which("bash"), "Unix bash is required for macOS build gates")
    def test_macos_build_security_gates_stop_failed_checks(self):
        with tempfile.TemporaryDirectory(prefix="conjure build gates ") as directory:
            root = Path(directory)
            fake = root / "python"
            fake.write_text("#!/bin/sh\nexit 23\n")
            fake.chmod(0o700)
            for name in ("build-app.sh", "build-portable.sh"):
                source = (ROOT / "packaging/macos" / name).read_text().splitlines()
                gates = [(i, line) for i, line in enumerate(source)
                         if "runtime_security.py" in line or "-m codex_image.dependency_check" in line]
                self.assertEqual(len(gates), 3)
                bootstrap = next(i for i, line in enumerate(source) if "-m ensurepip" in line)
                cleanup = next(i for i, line in enumerate(source) if "--platform macos" in line)
                self.assertLess(gates[0][0], bootstrap)
                self.assertLess(cleanup, gates[1][0])
                self.assertLess(cleanup, gates[2][0])
                for _, line in gates:
                    with self.subTest(script=name, stage=line):
                        result = subprocess.run(["bash", "-c", 'set -e\n' + line + '\nprintf "UNEXPECTED_SUCCESS"\n'],
                                                env={**os.environ, "PYTHON_BIN": str(fake), "APP_DIR": str(root)},
                                                capture_output=True, text=True, timeout=15)
                        self.assertEqual(result.returncode, 23, result.stderr)
                        self.assertNotIn("UNEXPECTED_SUCCESS", result.stdout)

    def _check_ca_environment(self, windows):
        relative = ("packaging/windows/Start WebUI Portable.bat" if windows
                    else "packaging/macos/Start WebUI Portable.command")
        source = (ROOT / relative).read_text()
        start = source.index('set "CERTIFI_CA_BUNDLE=' if windows else 'CERTIFI_CA_BUNDLE=')
        end = source.index('set "AUTH_SETTINGS_PATH=' if windows else 'LOG_FILE=', start)
        block = source[start:end]
        with tempfile.TemporaryDirectory(prefix="conjure ca test ") as directory:
            root = Path(directory)
            app = root / "app"
            bundle = (root / "python/Lib/site-packages/certifi/cacert.pem" if windows
                      else app / ".deps/certifi/cacert.pem")
            bundle.parent.mkdir(parents=True)
            bundle.write_text("synthetic bundle")
            helper = root / "read_env.py"
            helper.write_text("import os,json;print(json.dumps({k:os.getenv(k,'') for k in " + repr(CA_KEYS) + "}))")
            script = root / ("fixture.bat" if windows else "fixture.command")
            script.write_text(("@echo off\n" if windows else "") + block +
                              f'\n"{sys.executable}" "{helper}"\n')
            file_ca, dir_ca, request_ca = (str(root / name) for name in ("explicit.pem", "ca-directory", "requests.pem"))
            cases = (
                ({}, {"SSL_CERT_FILE": str(bundle), "SSL_CERT_DIR": "", "REQUESTS_CA_BUNDLE": str(bundle)}),
                ({"SSL_CERT_FILE": file_ca}, {"SSL_CERT_FILE": file_ca, "SSL_CERT_DIR": "", "REQUESTS_CA_BUNDLE": file_ca}),
                ({"SSL_CERT_DIR": dir_ca}, {"SSL_CERT_FILE": "", "SSL_CERT_DIR": dir_ca, "REQUESTS_CA_BUNDLE": ""}),
                ({"REQUESTS_CA_BUNDLE": request_ca}, {"SSL_CERT_FILE": str(bundle), "SSL_CERT_DIR": "", "REQUESTS_CA_BUNDLE": request_ca}),
                (dict(zip(CA_KEYS, (file_ca, dir_ca, request_ca))), dict(zip(CA_KEYS, (file_ca, dir_ca, request_ca)))),
            )
            for configured, expected in cases:
                with self.subTest(configured=tuple(configured)):
                    env = {k: v for k, v in os.environ.items() if k not in CA_KEYS}
                    env.update(APP_DIR=str(app), BUNDLE_DIR=str(root) + os.sep, **configured)
                    command = ([os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(script)]
                               if windows else ["zsh", str(script)])
                    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout.strip()), expected)

    @unittest.skipUnless(shutil.which("zsh"), "zsh is required for the macOS launcher block")
    def test_macos_launcher_preserves_explicit_ca_choices(self):
        self._check_ca_environment(False)

    @unittest.skipUnless(sys.platform == "win32", "Windows cmd.exe acceptance")
    def test_windows_launcher_preserves_explicit_ca_choices(self):
        self._check_ca_environment(True)

    @unittest.skipUnless(sys.platform == "win32", "Windows PowerShell failure injection")
    def test_windows_packaging_stops_on_failed_python_checks(self):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        self.assertIsNotNone(shell, "PowerShell is required on Windows")
        with tempfile.TemporaryDirectory(prefix="conjure packaging test ") as directory:
            root = Path(directory)
            fake = root / "fail-python.cmd"
            fake.write_text('@echo off\n"%TEST_PYTHON%" -c "import sys;sys.exit(23)"\nexit /b %errorlevel%\n')
            for name in ("build-app.ps1", "build-portable.ps1"):
                source = (ROOT / "packaging/windows" / name).read_text().splitlines()
                markers = ('& $PythonExe -m pip freeze', '& $PythonExe -c "import fastapi', '& $PythonExe (Join-Path $ScriptDir',
                           '& $PythonExe (Join-Path $AppDir "codex_image\\runtime_security.py")',
                           '& $PythonExe -m codex_image.dependency_check')
                checks = [i for i, line in enumerate(source) if line.startswith(markers)]
                self.assertEqual(len(checks), 6)
                preflight = next(i for i in checks if 'runtime_security.py' in source[i])
                bootstrap = next(i for i, line in enumerate(source) if '-m zipfile' in line)
                cleanup = next(i for i, line in enumerate(source) if '--platform windows' in line)
                postflight = next(i for i in checks if '--runtime' in source[i])
                dependency_check = next(i for i in checks if '-m codex_image.dependency_check' in source[i])
                self.assertLess(preflight, bootstrap)
                self.assertLess(cleanup, postflight)
                self.assertLess(postflight, dependency_check)
                for index in checks:
                    with self.subTest(script=name, stage=source[index]):
                        end = index
                        while source[end].rstrip().endswith('`'):
                            end += 1
                        chunk = '\n'.join(source[index:end + 2])
                        fixture = root / "check.ps1"
                        fixture.write_text(
                            "$ErrorActionPreference = 'Stop'\n"
                            "$PythonExe = $env:TEST_FAKE_PYTHON\n"
                            "$ResourcesDir = $BundleRoot = $ScriptDir = $AppDir = $PythonDir = $env:TEST_ROOT\n"
                            + chunk + '\nWrite-Output "UNEXPECTED_SUCCESS"\n'
                        )
                        env = {**os.environ, "TEST_FAKE_PYTHON": str(fake), "TEST_ROOT": str(root), "TEST_PYTHON": sys.executable}
                        result = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-File", str(fixture)],
                                                env=env, capture_output=True, text=True, timeout=15)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertNotIn("UNEXPECTED_SUCCESS", result.stdout)
                        self.assertIn("failed", result.stderr.lower())
