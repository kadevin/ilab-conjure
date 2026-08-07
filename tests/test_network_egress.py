from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib import request

from codex_image.http import UrllibTransport
from codex_image.http import HTTPResponse
from codex_image.webui.network_egress import NetworkEgressManager, NetworkEgressSettings


class _FakeUrlopenResponse:
    status = 200
    headers = {"content-type": "text/plain"}

    @staticmethod
    def getcode() -> int:
        return 200

    @staticmethod
    def read(_size: int = -1) -> bytes:
        return b"ok"

    def __enter__(self) -> "_FakeUrlopenResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class NetworkEgressSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "network-egress.json"
        self.settings = NetworkEgressSettings(self.path)

    def test_network_settings_default_to_system(self) -> None:
        self.assertEqual(
            self.settings.read(),
            {
                "mode": "system",
                "custom_proxy_url": "",
                "image_request_timeout_seconds": 600,
                "image_request_retry_count": 2,
            },
        )

    def test_network_settings_accept_direct_and_custom_http_origins(self) -> None:
        self.assertEqual(
            self.settings.write({"mode": "direct"}),
            {
                "mode": "direct",
                "custom_proxy_url": "",
                "image_request_timeout_seconds": 600,
                "image_request_retry_count": 2,
            },
        )
        self.assertEqual(
            self.settings.write(
                {
                    "mode": "custom",
                    "custom_proxy_url": " HTTPS://proxy.example.test:8443/ ",
                }
            ),
            {
                "mode": "custom",
                "custom_proxy_url": "https://proxy.example.test:8443",
                "image_request_timeout_seconds": 600,
                "image_request_retry_count": 2,
            },
        )
        self.assertEqual(
            NetworkEgressSettings(self.path).read(),
            {
                "mode": "custom",
                "custom_proxy_url": "https://proxy.example.test:8443",
                "image_request_timeout_seconds": 600,
                "image_request_retry_count": 2,
            },
        )

    def test_network_settings_accept_request_policy_boundaries(self) -> None:
        for timeout_seconds, retry_count in ((60, 0), (600, 2), (1800, 5)):
            with self.subTest(
                timeout_seconds=timeout_seconds,
                retry_count=retry_count,
            ):
                saved = self.settings.write(
                    {
                        "mode": "direct",
                        "image_request_timeout_seconds": timeout_seconds,
                        "image_request_retry_count": retry_count,
                    }
                )
                self.assertEqual(
                    saved["image_request_timeout_seconds"],
                    timeout_seconds,
                )
                self.assertEqual(saved["image_request_retry_count"], retry_count)

    def test_network_settings_reject_invalid_request_policy_values(self) -> None:
        invalid_values = {
            "image_request_timeout_seconds": (
                True,
                "600",
                600.0,
                "",
                None,
                59,
                1801,
            ),
            "image_request_retry_count": (
                True,
                "2",
                2.0,
                "",
                None,
                -1,
                6,
            ),
        }
        for field, values in invalid_values.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, field):
                        self.settings.write({"mode": "direct", field: value})

    def test_invalid_persisted_policy_preserves_valid_network_route(self) -> None:
        self.path.write_text(
            json.dumps(
                {
                    "mode": "custom",
                    "custom_proxy_url": "https://proxy.example.test:8443",
                    "image_request_timeout_seconds": "slow",
                    "image_request_retry_count": 99,
                }
            ),
            encoding="utf-8",
        )

        self.assertEqual(
            self.settings.read(),
            {
                "mode": "custom",
                "custom_proxy_url": "https://proxy.example.test:8443",
                "image_request_timeout_seconds": 600,
                "image_request_retry_count": 2,
            },
        )

    def test_environment_timeout_remains_effective_until_explicitly_saved(self) -> None:
        with patch.dict(
            "os.environ",
            {"CODEX_IMAGE_REQUEST_TIMEOUT_SECONDS": "2400.5"},
        ):
            initial = self.settings.request_policy()
            self.settings.write(
                {
                    "mode": "direct",
                    "image_request_retry_count": 5,
                }
            )
            after_mode_only_save = self.settings.request_policy()
            persisted = json.loads(self.path.read_text(encoding="utf-8"))
            self.settings.write(
                {
                    "image_request_timeout_seconds": 900,
                    "image_request_retry_count": 4,
                }
            )
            after_explicit_save = self.settings.request_policy()

        self.assertEqual(initial.timeout_seconds, 2400.5)
        self.assertEqual(initial.retry_count, 2)
        self.assertEqual(initial.timeout_source, "environment")
        self.assertNotIn("image_request_timeout_seconds", persisted)
        self.assertEqual(after_mode_only_save.timeout_seconds, 2400.5)
        self.assertEqual(after_mode_only_save.retry_count, 5)
        self.assertEqual(after_mode_only_save.timeout_source, "environment")
        self.assertEqual(after_explicit_save.timeout_seconds, 900)
        self.assertEqual(after_explicit_save.retry_count, 4)
        self.assertEqual(after_explicit_save.timeout_source, "settings")

    def test_invalid_environment_timeout_falls_back_to_default(self) -> None:
        for value in ("", "slow", "0", "-1", "nan", "inf", "Infinity"):
            with (
                self.subTest(value=value),
                patch.dict(
                    "os.environ",
                    {"CODEX_IMAGE_REQUEST_TIMEOUT_SECONDS": value},
                ),
            ):
                policy = self.settings.request_policy()
                self.assertEqual(policy.timeout_seconds, 600)
                self.assertEqual(policy.retry_count, 2)
                self.assertEqual(policy.timeout_source, "default")

    def test_network_settings_reject_credentials_paths_queries_and_socks(self) -> None:
        rejected_urls = (
            "http://user:secret@proxy.example.test:8080",
            "http://proxy.example.test:8080/path",
            "http://proxy.example.test:8080/?route=one",
            "http://proxy.example.test:8080/#fragment",
            "socks5://proxy.example.test:1080",
        )
        for proxy_url in rejected_urls:
            with self.subTest(proxy_url=proxy_url):
                with self.assertRaises(ValueError):
                    self.settings.write(
                        {
                            "mode": "custom",
                            "custom_proxy_url": proxy_url,
                        }
                    )


class NetworkEgressSnapshotTests(unittest.TestCase):
    def test_network_snapshot_redacts_custom_proxy_from_task_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = NetworkEgressSettings(Path(temp_dir) / "network-egress.json")
            settings.write(
                {
                    "mode": "system",
                    "image_request_timeout_seconds": 900,
                    "image_request_retry_count": 4,
                }
            )
            manager = NetworkEgressManager(settings)
            snapshot = manager.snapshot(
                {
                    "mode": "custom",
                    "custom_proxy_url": "http://proxy.example.test:8080",
                }
            )

        self.assertEqual(snapshot.mode, "custom")
        self.assertEqual(snapshot.route, "proxy")
        self.assertEqual(snapshot.image_request_timeout_seconds, 900)
        self.assertEqual(snapshot.image_request_retry_count, 4)
        self.assertEqual(snapshot.image_request_timeout_source, "settings")
        self.assertEqual(
            dict(snapshot.proxy_map or {}),
            {
                "http": "http://proxy.example.test:8080",
                "https": "http://proxy.example.test:8080",
            },
        )
        self.assertEqual(
            snapshot.task_metadata(),
            {
                "mode": "custom",
                "route": "proxy",
                "image_request_timeout_seconds": 900,
                "image_request_retry_count": 4,
                "image_request_timeout_source": "settings",
            },
        )
        self.assertNotIn("proxy.example.test", repr(snapshot.task_metadata()))
        self.assertEqual(manager.transport(snapshot).timeout, 900)


class NetworkEgressTransportTests(unittest.TestCase):
    @staticmethod
    def _proxy_maps(captured_handlers: list[tuple[object, ...]]) -> list[dict[str, str]]:
        return [
            dict(handler.proxies)
            for handlers in captured_handlers
            for handler in handlers
            if isinstance(handler, request.ProxyHandler)
        ]

    def _capture_openers(self) -> tuple[list[tuple[object, ...]], object]:
        captured_handlers: list[tuple[object, ...]] = []

        class FakeOpener:
            @staticmethod
            def open(req: object, timeout: float | None = None) -> _FakeUrlopenResponse:
                return _FakeUrlopenResponse()

        def fake_build_opener(*handlers: object) -> FakeOpener:
            captured_handlers.append(handlers)
            return FakeOpener()

        return captured_handlers, fake_build_opener

    def test_direct_transport_bypasses_environment_proxy_for_requests_and_redirects(self) -> None:
        captured_handlers, fake_build_opener = self._capture_openers()
        transport = UrllibTransport(proxy_map={})

        with patch("codex_image.http.request.build_opener", fake_build_opener):
            transport.request(
                method="POST",
                url="https://example.test/responses",
                headers={},
                body=b"{}",
            )
            transport.request_same_origin_redirects(
                method="GET",
                url="https://example.test/image.png",
                headers={},
                body=b"",
            )

        self.assertEqual(self._proxy_maps(captured_handlers), [{}, {}])

    def test_custom_transport_applies_proxy_to_http_and_https(self) -> None:
        proxy_map = {
            "http": "http://proxy.example.test:8080",
            "https": "http://proxy.example.test:8080",
        }
        captured_handlers, fake_build_opener = self._capture_openers()
        transport = UrllibTransport(proxy_map=proxy_map)

        with patch("codex_image.http.request.build_opener", fake_build_opener):
            transport.request(
                method="POST",
                url="https://example.test/responses",
                headers={},
                body=b"{}",
            )
            transport.request_same_origin_redirects(
                method="GET",
                url="http://example.test/image.png",
                headers={},
                body=b"",
            )

        self.assertEqual(self._proxy_maps(captured_handlers), [proxy_map, proxy_map])

    def test_system_transport_preserves_existing_urlopen_behavior(self) -> None:
        with (
            patch(
                "codex_image.http.request.urlopen",
                return_value=_FakeUrlopenResponse(),
            ) as mocked_urlopen,
            patch("codex_image.http.request.build_opener") as mocked_build_opener,
        ):
            response = UrllibTransport().request(
                method="POST",
                url="https://example.test/responses",
                headers={},
                body=b"{}",
            )

        self.assertEqual(response.body, b"ok")
        mocked_urlopen.assert_called_once()
        mocked_build_opener.assert_not_called()

    def test_credentialed_transport_rejects_cross_origin_redirects(self) -> None:
        from codex_image.http import _SameOriginRedirectHandler

        for header_name in ("Authorization", "x-goog-api-key", "X-Api-Key", "Api-Key"):
            with self.subTest(header_name=header_name):
                captured_handlers, fake_build_opener = self._capture_openers()
                with (
                    patch(
                        "codex_image.http.request.urlopen",
                        return_value=_FakeUrlopenResponse(),
                    ) as mocked_urlopen,
                    patch(
                        "codex_image.http.request.build_opener",
                        fake_build_opener,
                    ),
                ):
                    response = UrllibTransport().request(
                        method="POST",
                        url="https://provider.example/v1/images",
                        headers={header_name: "secret"},
                        body=b"{}",
                    )

                redirect_handler = next(
                    handler
                    for handlers in captured_handlers
                    for handler in handlers
                    if isinstance(handler, _SameOriginRedirectHandler)
                )
                redirected = redirect_handler.redirect_request(
                    request.Request("https://provider.example/v1/images"),
                    None,
                    302,
                    "Found",
                    {},
                    "https://attacker.example/collect",
                )

                self.assertEqual(response.body, b"ok")
                self.assertIsNone(redirected)
                mocked_urlopen.assert_not_called()


class QueueAttemptNetworkEgressTests(unittest.TestCase):
    @staticmethod
    def _recording_client_type(observed_clients: list[Any]):
        class RecordingClient:
            def __init__(
                self,
                auth_state: object,
                *,
                transport: object,
            ) -> None:
                self.transport = transport
                observed_clients.append(self)

        return RecordingClient

    def test_queue_attempt_uses_one_network_snapshot_for_automatic_retries(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.queue import QueueChannel
        from codex_image.webui.queue_runtime import execute_task

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = create_app(
                output_root=root,
                network_egress_settings_path=root / "network-egress.json",
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            app.state.network_egress_settings.write(
                {
                    "mode": "custom",
                    "custom_proxy_url": "http://proxy.example.test:8080",
                    "image_request_timeout_seconds": 900,
                    "image_request_retry_count": 4,
                }
            )
            task_id = "20260726120000-network"
            app.state.storage.write_metadata(
                task_id,
                {
                    "task_id": task_id,
                    "status": "queued",
                    "mode": "generate",
                    "params": {"codex_mode": "images"},
                },
            )
            observed_clients: list[Any] = []
            observed_transports: list[object] = []
            observed_policies: list[tuple[object, object]] = []

            async def fake_execute_stored_task(**kwargs: Any) -> None:
                client = kwargs["client"]
                observed_transports.extend([client.transport, client.transport])
                observed_policies.append(
                    (
                        kwargs.get("image_request_timeout_seconds"),
                        kwargs.get("image_request_retry_count"),
                    )
                )

            manager = app.state.network_egress_manager
            with (
                patch.object(manager, "snapshot", wraps=manager.snapshot) as snapshot,
                patch(
                    "codex_image.webui.queue_runtime.load_auth_state",
                    return_value=object(),
                ),
                patch(
                    "codex_image.webui.queue_runtime.CodexImagesImageClient",
                    self._recording_client_type(observed_clients),
                ),
                patch(
                    "codex_image.webui.queue_runtime._execute_stored_task",
                    fake_execute_stored_task,
                ),
            ):
                asyncio.run(
                    execute_task(
                        app.state.ctx,
                        task_id,
                        QueueChannel(
                            channel_id="codex:local",
                            auth_source="codex",
                        ),
                        True,
                        batch_delay_seconds=0,
                    )
                )

            metadata = app.state.storage.read_metadata(task_id)

        snapshot.assert_called_once_with()
        self.assertEqual(len(observed_clients), 1)
        self.assertIs(observed_transports[0], observed_transports[1])
        self.assertEqual(observed_policies, [(900, 4)])
        self.assertEqual(observed_clients[0].transport.timeout, 900)
        self.assertEqual(
            observed_clients[0].transport.proxy_map,
            {
                "http": "http://proxy.example.test:8080",
                "https": "http://proxy.example.test:8080",
            },
        )
        self.assertEqual(
            metadata["network_egress"],
            {
                "mode": "custom",
                "route": "proxy",
                "image_request_timeout_seconds": 900,
                "image_request_retry_count": 4,
                "image_request_timeout_source": "settings",
            },
        )

    def test_saved_network_change_affects_only_later_attempts(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.queue import QueueChannel
        from codex_image.webui.queue_runtime import _queue_execution_contract

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = create_app(
                output_root=root,
                network_egress_settings_path=root / "network-egress.json",
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            settings = app.state.network_egress_settings
            settings.write(
                {
                    "mode": "custom",
                    "custom_proxy_url": "http://proxy.example.test:8080",
                    "image_request_timeout_seconds": 900,
                    "image_request_retry_count": 4,
                }
            )
            channel = QueueChannel(channel_id="codex:local", auth_source="codex")
            observed_clients: list[Any] = []
            with (
                patch(
                    "codex_image.webui.queue_runtime.load_auth_state",
                    return_value=object(),
                ),
                patch(
                    "codex_image.webui.queue_runtime.CodexImagesImageClient",
                    self._recording_client_type(observed_clients),
                ),
            ):
                first = _queue_execution_contract(
                    app.state.ctx,
                    channel,
                    {"params": {"codex_mode": "images"}},
                )
                settings.write(
                    {
                        "mode": "direct",
                        "image_request_timeout_seconds": 1200,
                        "image_request_retry_count": 1,
                    }
                )
                second = _queue_execution_contract(
                    app.state.ctx,
                    channel,
                    {"params": {"codex_mode": "images"}},
                )

        self.assertEqual(
            first.client.transport.proxy_map,
            {
                "http": "http://proxy.example.test:8080",
                "https": "http://proxy.example.test:8080",
            },
        )
        self.assertEqual(first.client.transport.proxy_map, observed_clients[0].transport.proxy_map)
        self.assertEqual(second.client.transport.proxy_map, {})
        self.assertEqual(first.client.transport.timeout, 900)
        self.assertEqual(second.client.transport.timeout, 1200)
        self.assertEqual(
            getattr(first, "image_request_timeout_seconds", None),
            900,
        )
        self.assertEqual(getattr(first, "image_request_retry_count", None), 4)
        self.assertEqual(
            getattr(second, "image_request_timeout_seconds", None),
            1200,
        )
        self.assertEqual(getattr(second, "image_request_retry_count", None), 1)

    def test_task_metadata_contains_request_policy_but_not_proxy(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.queue import QueueChannel
        from codex_image.webui.queue_runtime import _queue_execution_contract

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = create_app(
                output_root=root,
                network_egress_settings_path=root / "network-egress.json",
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            app.state.network_egress_settings.write(
                {
                    "mode": "custom",
                    "custom_proxy_url": "https://proxy.example.test:8443",
                    "image_request_timeout_seconds": 1200,
                    "image_request_retry_count": 3,
                }
            )
            metadata: dict[str, Any] = {"params": {"codex_mode": "images"}}
            with (
                patch(
                    "codex_image.webui.queue_runtime.load_auth_state",
                    return_value=object(),
                ),
                patch(
                    "codex_image.webui.queue_runtime.CodexImagesImageClient",
                    self._recording_client_type([]),
                ),
            ):
                _queue_execution_contract(
                    app.state.ctx,
                    QueueChannel(channel_id="codex:local", auth_source="codex"),
                    metadata,
                )

        self.assertEqual(
            metadata["network_egress"],
            {
                "mode": "custom",
                "route": "proxy",
                "image_request_timeout_seconds": 1200,
                "image_request_retry_count": 3,
                "image_request_timeout_source": "settings",
            },
        )
        self.assertNotIn("proxy.example.test", repr(metadata))


class NetworkEgressApiTests(unittest.TestCase):
    def test_network_api_reads_and_saves_without_restart(self) -> None:
        from fastapi.testclient import TestClient

        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = create_app(
                output_root=root,
                network_egress_settings_path=root / "network-egress.json",
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            client = TestClient(app)

            initial = client.get("/api/network-egress")
            saved = client.patch(
                "/api/network-egress",
                json={
                    "mode": "direct",
                    "image_request_timeout_seconds": 1800,
                    "image_request_retry_count": 5,
                },
            )
            reread = client.get("/api/network-egress")

        self.assertEqual(initial.status_code, 200)
        self.assertEqual(
            initial.json(),
            {
                "settings": {
                    "mode": "system",
                    "custom_proxy_url": "",
                    "image_request_timeout_seconds": 600,
                    "image_request_retry_count": 2,
                },
                "resolved": {
                    "mode": "system",
                    "route": "system",
                    "image_request_timeout_seconds": 600,
                    "image_request_retry_count": 2,
                    "image_request_timeout_source": "default",
                },
                "restart_required": False,
            },
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(
            saved.json()["resolved"],
            {
                "mode": "direct",
                "route": "direct",
                "image_request_timeout_seconds": 1800,
                "image_request_retry_count": 5,
                "image_request_timeout_source": "settings",
            },
        )
        self.assertFalse(saved.json()["restart_required"])
        self.assertEqual(reread.json()["settings"]["mode"], "direct")
        self.assertEqual(
            reread.json()["settings"]["image_request_timeout_seconds"],
            1800,
        )
        self.assertEqual(reread.json()["settings"]["image_request_retry_count"], 5)

    def test_network_api_rejects_invalid_request_policy_values(self) -> None:
        from fastapi.testclient import TestClient

        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client = TestClient(
                create_app(
                    output_root=root,
                    network_egress_settings_path=root / "network-egress.json",
                    auth_checker=lambda: True,
                    auto_start_queue=False,
                )
            )
            invalid_values = (
                ("image_request_timeout_seconds", 59),
                ("image_request_timeout_seconds", 1801),
                ("image_request_timeout_seconds", 600.0),
                ("image_request_timeout_seconds", True),
                ("image_request_retry_count", -1),
                ("image_request_retry_count", 6),
                ("image_request_retry_count", 2.0),
                ("image_request_retry_count", True),
            )
            responses = [
                (
                    field,
                    client.patch("/api/network-egress", json={field: value}),
                )
                for field, value in invalid_values
            ]

        for field, response in responses:
            with self.subTest(field=field, detail=response.json().get("detail")):
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json()["detail"])

    def test_network_api_reports_environment_timeout_until_explicit_save(self) -> None:
        from fastapi.testclient import TestClient

        from codex_image.webui.app import create_app

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.dict(
                "os.environ",
                {"CODEX_IMAGE_REQUEST_TIMEOUT_SECONDS": "2400.5"},
            ),
        ):
            root = Path(temp_dir)
            client = TestClient(
                create_app(
                    output_root=root,
                    network_egress_settings_path=root / "network-egress.json",
                    auth_checker=lambda: True,
                    auto_start_queue=False,
                )
            )
            initial = client.get("/api/network-egress").json()
            mode_only = client.patch(
                "/api/network-egress",
                json={"mode": "direct"},
            ).json()
            explicit = client.patch(
                "/api/network-egress",
                json={"image_request_timeout_seconds": 900},
            ).json()

        self.assertEqual(initial["settings"]["image_request_timeout_seconds"], 600)
        self.assertEqual(initial["resolved"]["image_request_timeout_seconds"], 2400.5)
        self.assertEqual(initial["resolved"]["image_request_timeout_source"], "environment")
        self.assertEqual(mode_only["resolved"]["image_request_timeout_seconds"], 2400.5)
        self.assertEqual(mode_only["resolved"]["image_request_timeout_source"], "environment")
        self.assertEqual(explicit["resolved"]["image_request_timeout_seconds"], 900)
        self.assertEqual(explicit["resolved"]["image_request_timeout_source"], "settings")

    def test_network_test_uses_configured_provider_origin_not_arbitrary_url(self) -> None:
        from fastapi.testclient import TestClient

        from codex_image.webui.app import create_app

        class CapturingTransport:
            def __init__(self) -> None:
                self.calls: list[dict[str, Any]] = []

            def request(self, **kwargs: Any) -> HTTPResponse:
                self.calls.append(kwargs)
                return HTTPResponse(status=401, body=b"", headers={})

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = create_app(
                output_root=root,
                api_settings_path=root / "api-settings.json",
                auth_settings_path=root / "auth-settings.json",
                network_egress_settings_path=root / "network-egress.json",
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            app.state.auth_settings.write_source("api")
            app.state.api_settings.write(
                {
                    "api_key": "provider-secret",
                    "base_url": "https://relay.example.test/v1",
                    "image_model": "gpt-image-2",
                    "api_mode": "images",
                }
            )
            app.state.network_egress_settings.write(
                {
                    "mode": "system",
                    "image_request_timeout_seconds": 1800,
                    "image_request_retry_count": 5,
                }
            )
            transport = CapturingTransport()
            with patch.object(
                app.state.network_egress_manager,
                "transport",
                return_value=transport,
            ) as transport_factory:
                response = TestClient(app).post(
                    "/api/network-egress/test",
                    json={
                        "mode": "direct",
                        "target_url": "https://attacker.example.test/collect",
                    },
                )

        transport_factory.assert_called_once()
        self.assertEqual(
            transport_factory.call_args.kwargs,
            {"timeout_seconds": 10.0},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["target"], "https://relay.example.test")
        self.assertEqual(transport.calls[0]["url"], "https://relay.example.test")
        self.assertNotIn("Authorization", transport.calls[0]["headers"])
        self.assertNotIn("provider-secret", repr(transport.calls))
        self.assertNotIn("attacker.example.test", repr(transport.calls))

    def test_network_test_uses_current_generation_provider_instead_of_active_api_provider(self) -> None:
        from fastapi.testclient import TestClient

        from codex_image.webui.app import create_app

        class CapturingTransport:
            def __init__(self) -> None:
                self.calls: list[dict[str, Any]] = []

            def request(self, **kwargs: Any) -> HTTPResponse:
                self.calls.append(kwargs)
                return HTTPResponse(status=401, body=b"", headers={})

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = create_app(
                output_root=root,
                api_settings_path=root / "api-settings.json",
                auth_settings_path=root / "auth-settings.json",
                network_egress_settings_path=root / "network-egress.json",
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            app.state.auth_settings.write_source("api")
            app.state.api_settings.write(
                {
                    "active_provider_id": "provider-a",
                    "providers": [
                        {
                            "id": "provider-a",
                            "name": "Provider A",
                            "base_url": "https://a.example.test/v1",
                            "api_key": "provider-a-secret",
                            "image_model": "gpt-image-2",
                            "api_mode": "images",
                        },
                        {
                            "id": "provider-b",
                            "name": "Provider B",
                            "base_url": "https://b.example.test/v1",
                            "api_key": "provider-b-secret",
                            "image_model": "gpt-image-2",
                            "api_mode": "images",
                        },
                    ],
                }
            )
            transport = CapturingTransport()
            with patch.object(
                app.state.network_egress_manager,
                "transport",
                return_value=transport,
            ):
                response = TestClient(app).post(
                    "/api/network-egress/test",
                    json={"mode": "direct", "provider_id": "provider-b"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["target"], "https://b.example.test")
        self.assertEqual(response.json()["provider_id"], "provider-b")
        self.assertEqual(transport.calls[0]["url"], "https://b.example.test")
        self.assertNotIn("provider-b-secret", repr(transport.calls))

    def test_network_test_maps_selected_codex_provider_to_chatgpt_origin(self) -> None:
        from fastapi.testclient import TestClient

        from codex_image.webui.app import create_app

        class CapturingTransport:
            def __init__(self) -> None:
                self.calls: list[dict[str, Any]] = []

            def request(self, **kwargs: Any) -> HTTPResponse:
                self.calls.append(kwargs)
                return HTTPResponse(status=401, body=b"", headers={})

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = create_app(
                output_root=root,
                api_settings_path=root / "api-settings.json",
                auth_settings_path=root / "auth-settings.json",
                network_egress_settings_path=root / "network-egress.json",
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            app.state.auth_settings.write_source("api")
            app.state.api_settings.write(
                {
                    "api_key": "provider-secret",
                    "base_url": "https://relay.example.test/v1",
                    "image_model": "gpt-image-2",
                    "api_mode": "images",
                }
            )
            transport = CapturingTransport()
            with patch.object(
                app.state.network_egress_manager,
                "transport",
                return_value=transport,
            ):
                response = TestClient(app).post(
                    "/api/network-egress/test",
                    json={"mode": "direct", "provider_id": "codex"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["target"], "https://chatgpt.com")
        self.assertEqual(response.json()["provider_id"], "codex")
        self.assertEqual(transport.calls[0]["url"], "https://chatgpt.com")

    def test_network_test_rejects_unknown_selected_provider_instead_of_falling_back(self) -> None:
        from fastapi.testclient import TestClient

        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = create_app(
                output_root=root,
                api_settings_path=root / "api-settings.json",
                auth_settings_path=root / "auth-settings.json",
                network_egress_settings_path=root / "network-egress.json",
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            response = TestClient(app).post(
                "/api/network-egress/test",
                json={"mode": "direct", "provider_id": "missing-provider"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Selected provider is unavailable")

    def test_network_test_treats_any_http_response_as_transport_reachable(self) -> None:
        from fastapi.testclient import TestClient

        from codex_image.webui.app import create_app

        class UnavailableServiceTransport:
            @staticmethod
            def request(**kwargs: Any) -> HTTPResponse:
                return HTTPResponse(
                    status=503,
                    body=b"temporarily unavailable",
                    headers={},
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = create_app(
                output_root=root,
                network_egress_settings_path=root / "network-egress.json",
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            with patch.object(
                app.state.network_egress_manager,
                "transport",
                return_value=UnavailableServiceTransport(),
            ):
                response = TestClient(app).post(
                    "/api/network-egress/test",
                    json={"mode": "system"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["status_code"], 503)


if __name__ == "__main__":
    unittest.main()
