from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from tests.webui_helpers import FakeImageClient


class _ClosableConnection:
    def close(self) -> None:
        return None


class _FakeHTTPResponse:
    status = 204
    headers = {"content-type": "text/plain"}

    def getcode(self) -> int:
        return self.status

    def read(self) -> bytes:
        return b""

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None


class NetworkEgressTests(unittest.TestCase):
    def test_static_settings_panel_exposes_network_egress_controls(self) -> None:
        html = Path("codex_image/webui/static/index.html").read_text(encoding="utf-8")
        system_settings = Path("codex_image/webui/frontend/src/system-settings.ts").read_text(encoding="utf-8")
        main_source = Path("codex_image/webui/frontend/src/main.ts").read_text(encoding="utf-8")

        self.assertIn('id="systemSettingsNetworkTab"', html)
        self.assertIn('data-system-settings-tab="network"', html)
        self.assertIn('id="systemSettingsNetworkPanel"', html)
        self.assertIn('id="networkEgressModeGroup"', html)
        self.assertIn('id="networkEgressCustomProxyUrl"', html)
        self.assertIn('id="testNetworkEgressButton"', html)
        self.assertIn('id="saveNetworkEgressButton"', html)
        self.assertIn('"network"', system_settings)
        self.assertIn('maybeCall("refreshNetworkEgressSettings")', system_settings)
        self.assertIn('initNetworkEgressSettingsFeature();', main_source)

    def test_settings_default_to_system_and_reject_proxy_credentials(self) -> None:
        from codex_image.webui.network_egress import NetworkEgressSettings

        with tempfile.TemporaryDirectory() as tmp:
            settings = NetworkEgressSettings(Path(tmp) / "network.json")

            self.assertEqual(settings.read(), {"mode": "system", "custom_proxy_url": ""})
            with self.assertRaisesRegex(ValueError, "credentials are not supported"):
                settings.write({"mode": "custom", "custom_proxy_url": "http://user:secret@127.0.0.1:10808"})

    def test_direct_transport_uses_empty_proxy_handler_instead_of_system_proxy(self) -> None:
        from codex_image.http import UrllibTransport

        captured: dict[str, object] = {}

        class FakeOpener:
            def open(self, _request: object, timeout: float | None = None) -> _FakeHTTPResponse:
                captured["timeout"] = timeout
                return _FakeHTTPResponse()

        def fake_build_opener(*handlers: object) -> FakeOpener:
            captured["handlers"] = handlers
            return FakeOpener()

        with patch("codex_image.http.request.build_opener", fake_build_opener), patch(
            "codex_image.http.request.urlopen",
            side_effect=AssertionError("explicit direct route must not use system-aware urlopen"),
        ):
            response = UrllibTransport(timeout=2, proxy_map={}).request(
                method="HEAD",
                url="https://example.test/",
                headers={},
                body=b"",
            )

        proxy_handler = captured["handlers"][0]  # type: ignore[index]
        self.assertEqual(getattr(proxy_handler, "proxies"), {})
        self.assertEqual(captured["timeout"], 2)
        self.assertEqual(response.status, 204)

    def test_auto_prefers_reachable_custom_proxy_then_system_then_direct(self) -> None:
        from codex_image.webui.network_egress import NetworkEgressManager, NetworkEgressSettings

        with tempfile.TemporaryDirectory() as tmp:
            settings = NetworkEgressSettings(Path(tmp) / "network.json")
            settings.write({"mode": "auto", "custom_proxy_url": "http://127.0.0.1:10808"})

            def custom_reachable(endpoint: tuple[str, int], _timeout: float) -> _ClosableConnection:
                if endpoint == ("127.0.0.1", 10808):
                    return _ClosableConnection()
                raise OSError("closed")

            with patch("codex_image.webui.network_egress.request.getproxies", return_value={"https": "http://127.0.0.1:7890"}):
                custom = NetworkEgressManager(settings, proxy_connector=custom_reachable).resolve()

            self.assertEqual(custom.source, "custom")
            self.assertEqual(custom.proxy_url, "http://127.0.0.1:10808")

            settings.write({"mode": "auto", "custom_proxy_url": "http://127.0.0.1:10809"})

            def system_reachable(endpoint: tuple[str, int], _timeout: float) -> _ClosableConnection:
                if endpoint == ("127.0.0.1", 7890):
                    return _ClosableConnection()
                raise OSError("closed")

            with patch("codex_image.webui.network_egress.request.getproxies", return_value={"https": "http://127.0.0.1:7890"}):
                system = NetworkEgressManager(settings, proxy_connector=system_reachable).resolve()
                direct = NetworkEgressManager(
                    settings,
                    proxy_connector=lambda *_: (_ for _ in ()).throw(OSError("closed")),
                ).resolve()

            self.assertEqual(system.source, "system")
            self.assertEqual(system.route, "proxy")
            self.assertEqual(direct.source, "auto")
            self.assertEqual(direct.route, "direct")

    def test_network_api_saves_without_restart_and_tests_unsaved_values(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "tasks",
                network_egress_settings_path=root / "network.json",
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            client = TestClient(app)

            saved = client.patch("/api/network-egress", json={"mode": "direct"})
            current = client.get("/api/network-egress")

            self.assertEqual(saved.status_code, 200)
            self.assertFalse(saved.json()["restart_required"])
            self.assertEqual(current.json()["settings"]["mode"], "direct")
            self.assertEqual(current.json()["resolved"]["route"], "direct")

            with patch.object(
                app.state.network_egress_manager,
                "probe",
                return_value={"ok": True, "resolved": {"requested_mode": "custom", "source": "custom", "route": "proxy"}},
            ) as probe:
                tested = client.post(
                    "/api/network-egress/test",
                    json={"mode": "custom", "custom_proxy_url": "http://127.0.0.1:10808"},
                )

            self.assertEqual(tested.status_code, 200)
            probe.assert_called_once_with({"mode": "custom", "custom_proxy_url": "http://127.0.0.1:10808"})

    def test_queue_attempt_records_resolved_network_egress(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth_settings_path = root / "auth.json"
            auth_settings_path.write_text(json.dumps({"source": "codex"}), encoding="utf-8")
            network_settings_path = root / "network.json"
            network_settings_path.write_text(json.dumps({"mode": "direct", "custom_proxy_url": ""}), encoding="utf-8")
            app = create_app(
                output_root=root / "tasks",
                auth_settings_path=auth_settings_path,
                network_egress_settings_path=network_settings_path,
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            client = TestClient(app)
            created = client.post(
                "/api/generate",
                data={"prompt": "network snapshot", "size": "1024x1024", "quality": "low"},
            )
            task_id = created.json()["task"]["task_id"]

            asyncio.run(app.state.queue_manager.run_available_once())
            task = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertEqual(task["status"], "completed")
        self.assertEqual(
            task["network_egress"],
            {"requested_mode": "direct", "route": "direct", "source": "direct", "proxy_url": ""},
        )


if __name__ == "__main__":
    unittest.main()
