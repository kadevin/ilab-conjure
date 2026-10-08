from __future__ import annotations

import asyncio
import base64
from collections import Counter
from contextlib import asynccontextmanager, chdir
import errno
from io import BytesIO
from pathlib import Path
import socket
import ssl
import tempfile
import unittest
from unittest.mock import patch

import httpx
from PIL import Image

from codex_image.auth import AuthState
from codex_image.codex_images_client import CodexImagesImageClient
from codex_image.http_connection import HTTPTransportFailure
from codex_image.openai_images_client import OpenAIImagesImageClient
from codex_image.webui.executor_transport import _call_image_client
from codex_image.webui.network_egress import NetworkEgressManager, NetworkEgressSettings


class HTTPConnectionRetryTests(unittest.TestCase):
    def setUp(self):
        delay = patch("codex_image.http_connection.connection_retry_delay", return_value=0)
        delay.start()
        self.addCleanup(delay.stop)

    def transport(self, retries=2, fake_ip=False):
        with tempfile.TemporaryDirectory() as tmp:
            settings = NetworkEgressSettings(Path(tmp) / "network.json")
            settings.write({"mode": "direct", "image_request_retry_count": retries,
                            "asset_fake_ip_dns_fallback": fake_ip})
            manager = NetworkEgressManager(settings)
            return manager.transport(manager.snapshot())

    def mock_client(self, handler):
        client_class = httpx.AsyncClient
        return patch("codex_image.httpx_transport.httpx.AsyncClient", side_effect=lambda **options:
                     client_class(transport=httpx.MockTransport(handler), **options))

    def test_first_connection_failure_recovers_using_configured_retries(self):
        for error_type in (httpx.ConnectError, httpx.ConnectTimeout):
            calls = []

            def handler(request):
                calls.append(request)
                if len(calls) == 1:
                    raise error_type("All connection attempts failed")
                return httpx.Response(200, content=b"synthetic")

            with self.subTest(error=error_type.__name__), self.mock_client(handler):
                result = self.transport().request(method="POST", url="https://upstream.example/generate",
                                                  headers={}, body=b"synthetic")
                self.assertEqual(result.body, b"synthetic")
                self.assertEqual(len(calls), 2)
                self.assertEqual(calls[0].content, calls[1].content)

    def test_exhausted_connections_do_not_multiply_with_image_retries_and_redact_secrets(self):
        for retries in (0, 2, 5):
            calls = []

            def handler(request):
                calls.append(request)
                raise httpx.ConnectError("secret-token private-prompt /private-path") from ConnectionRefusedError(errno.ECONNREFUSED, "secret")

            transport = self.transport(retries)
            with self.subTest(retries=retries), self.mock_client(handler), self.assertRaises(Exception) as caught:
                asyncio.run(_call_image_client(None, {}, lambda **_: transport.request(
                    method="POST", url="https://upstream.example/private-path?token=secret-token",
                    headers={"Authorization": "Bearer secret-token"}, body=b"private-prompt"),
                    timeout_seconds=10, retry_count=retries))
            self.assertEqual(len(calls), retries + 1)
            message = str(caught.exception)
            for part in ("stage=upstream_request", "host=upstream.example", f"attempts={retries + 1}", "ECONNREFUSED"):
                self.assertIn(part, message)
            for secret in ("secret-token", "private-prompt", "/private-path"):
                self.assertNotIn(secret, message)

    def test_certificate_failure_is_diagnosed_without_retry(self):
        calls = []

        def handler(request):
            calls.append(request)
            raise httpx.ConnectError("CERTIFICATE_VERIFY_FAILED") from ssl.SSLCertVerificationError(1, "synthetic")

        with self.mock_client(handler), self.assertRaisesRegex(Exception, "TLS_CERTIFICATE_VERIFY_FAILED"):
            self.transport().request(method="POST", url="https://upstream.example", headers={}, body=b"")
        self.assertEqual(len(calls), 1)

    def test_redirect_destination_failure_does_not_replay_original_post(self):
        for status in (302, 307):
            calls = []

            def handler(request):
                calls.append(request)
                if request.url.path == "/generate":
                    return httpx.Response(status, headers={"Location": "/result"})
                if len(calls) == 2:
                    raise httpx.ConnectError("All connection attempts failed")
                return httpx.Response(200, content=b"synthetic")

            with self.subTest(status=status), self.mock_client(handler):
                result = self.transport().request(method="POST", url="https://upstream.example/generate",
                                                  headers={}, body=b"synthetic")
                self.assertEqual(result.body, b"synthetic")
                self.assertEqual([request.url.path for request in calls], ["/generate", "/result", "/result"])
                self.assertEqual([request.method for request in calls], ["POST", *(["GET" if status == 302 else "POST"] * 2)])

    def test_read_write_and_http_errors_are_not_connection_retries(self):
        for failure in (httpx.ReadTimeout, httpx.WriteError, 400, 503):
            calls = []

            def handler(request):
                calls.append(request)
                if isinstance(failure, int):
                    return httpx.Response(failure)
                raise failure("synthetic")

            with self.subTest(failure=failure), self.mock_client(handler):
                if isinstance(failure, int):
                    result = self.transport().request(method="POST", url="https://upstream.example", headers={}, body=b"")
                    self.assertEqual(result.status, failure)
                else:
                    with self.assertRaises((TimeoutError, httpx.WriteError)):
                        self.transport().request(method="POST", url="https://upstream.example", headers={}, body=b"")
            self.assertEqual(len(calls), 1)

    def test_cancellation_and_total_timeout_stop_connection_backoff_and_release_slot(self):
        for cancel in (True, False):
            calls = []
            slots = []

            def handler(request):
                calls.append(request)
                raise httpx.ConnectError("All connection attempts failed")

            @asynccontextmanager
            async def slot(_params):
                slots.append("acquired")
                try:
                    yield
                finally:
                    slots.append("released")

            async def run():
                backoff_started = asyncio.Event()

                def delay(_round):
                    backoff_started.set()
                    return 60

                transport = self.transport()
                with patch("codex_image.http_connection.connection_retry_delay", side_effect=delay):
                    task = asyncio.create_task(_call_image_client(slot, {}, lambda **_: transport.request(
                        method="POST", url="https://upstream.example", headers={}, body=b""),
                        timeout_seconds=2 if cancel else 0.2, retry_count=2))
                    await asyncio.wait_for(backoff_started.wait(), 1)
                    if cancel:
                        task.cancel()
                    with self.assertRaises(asyncio.CancelledError if cancel else TimeoutError):
                        await task

            with self.subTest(cancel=cancel), self.mock_client(handler):
                asyncio.run(run())
            self.assertEqual(len(calls), 1)
            self.assertEqual(slots, ["acquired", "released"])

    def test_partial_download_read_failure_never_replays_generation(self):
        calls = Counter()
        closed = []

        class BrokenStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"partial"
                raise httpx.ReadError("secret") from ConnectionResetError(errno.ECONNRESET, "synthetic")

            async def aclose(self):
                closed.append(True)

        def handler(request):
            calls[request.method] += 1
            if request.method == "POST":
                return httpx.Response(200, json={"data": [{"url": "https://cdn.example/image"}]})
            return httpx.Response(200, stream=BrokenStream())

        client = OpenAIImagesImageClient(api_key="synthetic", base_url="https://upstream.example/v1", transport=self.transport())
        with self.mock_client(handler), patch("socket.getaddrinfo", return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))
        ]), self.assertRaisesRegex(HTTPTransportFailure, "stage=image_download"):
            asyncio.run(_call_image_client(None, {}, client.generate_image, timeout_seconds=10,
                                          retry_count=2, prompt="synthetic", size="1024x1024"))
        self.assertEqual(calls, {"POST": 1, "GET": 1})
        self.assertEqual(closed, [True])

    def test_codex_generate_edit_queue_recovery_and_exhausted_error_persistence(self):
        from fastapi.testclient import TestClient

        png = BytesIO()
        Image.new("RGB", (2, 2), (30, 60, 90)).save(png, format="PNG")
        for mode in ("generate", "edit"):
            for failure in ("first_connection", "all_connections", "download", "dns"):
                calls = Counter()

                def handler(request):
                    calls[request.method] += 1
                    if request.method == "POST":
                        if failure == "all_connections" or (failure == "first_connection" and calls["POST"] == 1):
                            raise httpx.ConnectError("secret-token private-prompt")
                        result = ({"url": "https://cdn.example/image?token=secret-token"} if failure in {"download", "dns"}
                                  else {"b64_json": base64.b64encode(png.getvalue()).decode()})
                        return httpx.Response(200, json={"data": [result]})
                    raise httpx.ConnectError("secret-token private-prompt") from ConnectionResetError(errno.ECONNRESET, "synthetic")

                with self.subTest(mode=mode, failure=failure), tempfile.TemporaryDirectory() as tmp, chdir(tmp):
                    from codex_image.webui.app import create_app

                    root = Path(tmp)
                    auth = AuthState(root / "synthetic-auth", "synthetic-token", "", "", "synthetic-account", None, {})
                    image_client = CodexImagesImageClient(auth, transport=self.transport(fake_ip=failure == "dns"))
                    app = create_app(output_root=root / "tasks", client_factory=lambda: image_client,
                                     auth_checker=lambda: True, batch_delay_seconds=0,
                                     auto_start_queue=False, auto_retry=True)
                    app.state.queue_manager.max_attempts = 3
                    with TestClient(app) as client, self.mock_client(handler), patch("socket.getaddrinfo", return_value=[
                        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.1.2" if failure == "dns" else "8.8.8.8", 443))
                    ]), patch("codex_image.webui.executor._direct_images_concurrent_enabled", return_value=mode == "generate"):
                        files = {"images": ("synthetic.png", png.getvalue(), "image/png")} if mode == "edit" else None
                        created = client.post(f"/api/{mode}", data={"prompt": "private-prompt", "size": "1024x1024",
                                                                  "codex_mode": "images"}, files=files)
                        self.assertEqual(created.status_code, 200, created.text)
                        task_id = created.json()["task"]["task_id"]
                        if failure == "first_connection":
                            asyncio.run(app.state.queue_manager.run_available_once())
                        else:
                            with self.assertRaises(RuntimeError):
                                asyncio.run(app.state.queue_manager.run_available_once())
                        asyncio.run(app.state.queue_manager.run_available_once())
                        task = client.get(f"/api/tasks/{task_id}").json()["task"]
                        stored = app.state.storage.read_metadata(task_id)
                        self.assertEqual(app.state.queue_storage.read_state()["waiting"], [])
                        self.assertFalse(app.state.ctx.active_task_ids)
                        self.assertFalse(app.state.ctx.api_task_slot_reservations)
                        self.assertEqual(task["status"], "completed" if failure == "first_connection" else "failed")
                        self.assertEqual(calls["POST"], {"first_connection": 2, "all_connections": 3, "download": 1, "dns": 1}[failure])
                        if failure == "dns":
                            self.assertGreaterEqual(calls["GET"], 3)
                            self.assertLessEqual(calls["GET"], 6)
                        else:
                            self.assertEqual(calls["GET"], 3 if failure == "download" else 0)
                        if failure != "first_connection":
                            stage = {"download": "image_download", "dns": "image_dns_lookup"}.get(failure, "upstream_request")
                            for message in (task["last_error"], stored["error"], stored["outputs"][0]["error"]):
                                self.assertIn(f"stage={stage}", message)
                                self.assertIn("attempts=3", message)
                                self.assertNotIn("secret-token", message)
                                self.assertNotIn("private-prompt", message)
                            # Exhausted automatic retries must not disable a later
                            # user-requested retry after the network recovers.
                            previous_posts = calls["POST"]
                            failure = "recovered"
                            retried = client.post(f"/api/tasks/{task_id}/retry-failed")
                            self.assertEqual(retried.status_code, 200, retried.text)
                            asyncio.run(app.state.queue_manager.run_available_once())
                            self.assertEqual(client.get(f"/api/tasks/{task_id}").json()["task"]["status"], "completed")
                            self.assertEqual(calls["POST"], previous_posts + 1)

    def test_image_download_retries_only_download_and_never_resubmits_generation(self):
        png = BytesIO()
        Image.new("RGB", (2, 2), (30, 60, 90)).save(png, format="PNG")
        for failures in (1, 10):
            calls = Counter()

            def handler(request):
                calls[request.method] += 1
                if request.method == "POST":
                    return httpx.Response(200, json={"data": [{"url": "https://cdn.example/private-image?token=secret"}]})
                if calls["GET"] <= failures:
                    raise httpx.ConnectError("All connection attempts failed") from ConnectionResetError(errno.ECONNRESET, "synthetic")
                return httpx.Response(200, content=png.getvalue(), headers={"Content-Type": "image/png"})

            client = OpenAIImagesImageClient(api_key="synthetic", base_url="https://upstream.example/v1", transport=self.transport())
            with self.subTest(failures=failures), self.mock_client(handler), patch("socket.getaddrinfo", return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))
            ]):
                operation = _call_image_client(None, {}, client.generate_image, timeout_seconds=10,
                                              retry_count=2, prompt="synthetic", size="1024x1024")
                if failures == 1:
                    self.assertEqual(asyncio.run(operation).image_bytes, png.getvalue())
                else:
                    with self.assertRaisesRegex(Exception, "stage=image_download"):
                        asyncio.run(operation)
            self.assertEqual(calls["POST"], 1)
            self.assertEqual(calls["GET"], 2 if failures == 1 else 3)
