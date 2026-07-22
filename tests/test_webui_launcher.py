from __future__ import annotations

import unittest
from pathlib import Path


class WebUILauncherTests(unittest.TestCase):
    def test_launcher_starts_uvicorn_on_localhost(self) -> None:
        launcher = Path("Start WebUI.command")
        text = launcher.read_text(encoding="utf-8")

        self.assertIn("uvicorn", text)
        self.assertIn("codex_image.webui.app:app", text)
        self.assertIn("--host 127.0.0.1", text)
        self.assertIn("--port 8787", text)
        self.assertIn("--no-access-log", text)

    def test_launcher_uses_project_venv(self) -> None:
        launcher = Path("Start WebUI.command")
        text = launcher.read_text(encoding="utf-8")

        self.assertIn(".venv", text)
        self.assertIn("requirements-webui.txt", text)

    def test_macos_launchers_wait_for_health_before_opening_browser(self) -> None:
        for launcher in (Path("Start WebUI.command"), Path("Start WebUI Debug.command")):
            text = launcher.read_text(encoding="utf-8")

            self.assertIn('HEALTH_URL="${URL}api/health"', text)
            self.assertIn("webui_is_ready()", text)
            self.assertIn("wait_for_webui()", text)
            self.assertIn("if webui_is_ready; then", text)
            self.assertIn('SERVER_PID="$!"', text)
            self.assertIn('if wait_for_webui; then\n  open "$URL"', text)
            self.assertNotIn('open "$URL" >/dev/null 2>&1 || true\n"$PYTHON_BIN" -m uvicorn', text)

    def test_windows_launcher_waits_for_health_before_opening_browser(self) -> None:
        text = Path("Start WebUI.bat").read_text(encoding="utf-8")

        self.assertIn('set "HEALTH_URL=%URL%api/health"', text)
        self.assertIn("call :is_webui_ready", text)
        self.assertIn("call :wait_for_webui", text)
        self.assertIn('start "iLab CONJURE WebUI" /b "%PYTHON_BIN%" -m uvicorn', text)
        self.assertIn('if %ERRORLEVEL% EQU 0 (\n  start "" "%URL%"', text)
        self.assertNotIn('start "" "%URL%"\n"%PYTHON_BIN%" -m uvicorn', text)
