from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from codex_image.webui.lan_access import LanAccessRuntime, lan_ipv4_addresses
from codex_image.webui.routes.lan_access import register_lan_access_routes
from codex_image.webui.security import LocalWebUISecurityMiddleware
from codex_image.webui.server import WebUIServer, main
from codex_image.webui.settings_store import WebUISettings
from codex_image.webui.shutdown_control import ShutdownCoordinator


class WebUILanAccessTests(unittest.TestCase):
    def app(self, path: Path, *, host: str | None = None) -> FastAPI:
        settings = WebUISettings(path)
        app = FastAPI()
        app.state.lan_access = LanAccessRuntime(settings.read_lan_access_enabled(), host, 8787)
        app.state.webui_shutdown_coordinator = ShutdownCoordinator()
        app.add_middleware(LocalWebUISecurityMiddleware, lan_access=app.state.lan_access)
        register_lan_access_routes(app, SimpleNamespace(webui_settings=settings))
        return app

    def remote(self, app: FastAPI) -> TestClient:
        return TestClient(app, base_url="http://192.168.1.10:8787", client=("192.168.1.20", 1234))

    def test_toggle_is_persisted_but_access_changes_only_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "codex_image.webui.routes.lan_access.lan_ipv4_addresses", return_value=["192.168.1.10"]
        ):
            path = Path(directory) / "settings.json"
            app = self.app(path, host="127.0.0.1")
            local = TestClient(app)
            self.assertFalse(local.get("/api/lan-access").json()["enabled"])
            self.assertEqual(self.remote(app).get("/api/lan-access").status_code, 400)
            saved = local.patch("/api/lan-access", json={"enabled": True}).json()
            self.assertTrue(saved["enabled"])
            self.assertFalse(saved["active"])
            self.assertTrue(saved["restart_required"])
            self.assertEqual(saved["addresses"], ["http://192.168.1.10:8787/"])
            self.assertEqual(self.remote(app).get("/api/lan-access").status_code, 400)
            restarted = self.app(path)
            remote = self.remote(restarted)
            active = remote.get("/api/lan-access")
            self.assertEqual(active.status_code, 200)
            self.assertTrue(active.json()["active"])
            self.assertFalse(active.json()["restart_required"])
            off = remote.patch("/api/lan-access", json={"enabled": False}).json()
            self.assertTrue(off["active"])
            self.assertTrue(off["restart_required"])
            self.assertEqual(self.remote(self.app(path)).get("/api/lan-access").status_code, 400)

    def test_lan_preserves_same_origin_and_payload_validation_without_login(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            WebUISettings(path).write_lan_access_enabled(True)
            remote = self.remote(self.app(path))
            self.assertEqual(remote.patch("/api/lan-access", json={"enabled": "true"}).status_code, 400)
            self.assertEqual(remote.patch("/api/lan-access", json={"enabled": True}, headers={"Origin": "https://foreign.example"}).status_code, 403)
            self.assertEqual(remote.patch("/api/lan-access", json={"enabled": True}, headers={"Origin": "http://192.168.1.10:8787"}).status_code, 200)
            self.assertEqual(remote.get("/api/lan-access", headers={"Host": "bad/path"}).status_code, 400)
            self.assertEqual(remote.get("/api/lan-access", headers={"Host": "studio.local:8787"}).status_code, 200)

    def test_other_settings_do_not_erase_lan_flag_and_backups_do_not_enable_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = WebUISettings(root / "settings.json")
            settings.write_lan_access_enabled(True)
            settings.write_locale("en")
            settings.write_paths({
                "input_root": str(root / "inputs"), "output_root": str(root / "outputs"),
                "gallery_root": str(root / "inputs/gallery"), "source_data_root": str(root / "outputs/source-data"),
            })
            self.assertTrue(settings.read_lan_access_enabled())
            self.assertEqual(settings.read_locale(), "en")
            self.assertNotIn("lan_access_enabled", settings.snapshot()["values"])
            settings.path.write_text(json.dumps({"lan_access_enabled": "true"}))
            self.assertFalse(settings.read_lan_access_enabled())

    def test_server_selects_configured_listener_and_honors_explicit_host(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            for enabled, override, expected in [(False, None, "127.0.0.1"), (True, None, "0.0.0.0"), (True, "127.0.0.1", "127.0.0.1")]:
                WebUISettings(path).write_lan_access_enabled(enabled)
                app = self.app(path)
                def run(server: WebUIServer) -> None:
                    self.assertEqual(server.config.host, expected)
                    self.assertFalse(server.config.proxy_headers)
                    server.started = True
                with patch("codex_image.webui.server.import_from_string", return_value=app), patch.object(WebUIServer, "run", run):
                    args = ["fixture:app", "--port", "8787"] + (["--host", override] if override else [])
                    self.assertEqual(main(args), 0)
                self.assertEqual(app.state.lan_access.active, enabled and override is None)
                if override:
                    self.assertTrue(TestClient(app).get("/api/lan-access").json()["host_override"])

    def test_address_discovery_excludes_loopback_and_deduplicates(self) -> None:
        with patch("socket.getaddrinfo", return_value=[
            (None, None, None, None, (address, 0))
            for address in ["127.0.0.1", "192.168.2.20", "192.168.2.20", "0.0.0.0", "8.8.8.8"]
        ]), patch("socket.socket", side_effect=OSError):
            self.assertEqual(lan_ipv4_addresses(), ["192.168.2.20"])
