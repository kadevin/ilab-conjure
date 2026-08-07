from __future__ import annotations

import asyncio
import os
import threading
import time
import tempfile
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

from fastapi.testclient import TestClient


class _DaemonThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


@contextmanager
def _running_server(
    handler: type[BaseHTTPRequestHandler],
) -> Iterator[_DaemonThreadingHTTPServer]:
    server = _DaemonThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


class WebUICancellableTransportTests(unittest.TestCase):
    def test_transient_retry_count_means_retries_after_the_first_attempt(self) -> None:
        from codex_image.webui.executor_transport import _call_image_client

        for retry_count, expected_attempts in ((0, 1), (2, 3), (5, 6)):
            calls = 0

            def fail_transiently(**_kwargs: object) -> object:
                nonlocal calls
                calls += 1
                raise ConnectionResetError(54, "Connection reset by peer")

            with self.subTest(retry_count=retry_count):
                with (
                    patch(
                        "codex_image.webui.executor_transport._transient_image_retry_delay_seconds",
                        return_value=0,
                    ),
                    self.assertRaises(ConnectionResetError),
                ):
                    asyncio.run(
                        _call_image_client(
                            None,
                            {},
                            fail_transiently,
                            timeout_seconds=1,
                            retry_count=retry_count,
                        )
                    )
                self.assertEqual(calls, expected_attempts)

    def test_non_transient_failure_is_not_retried_when_retry_count_is_five(self) -> None:
        from codex_image.webui.executor_transport import _call_image_client

        calls = 0

        def fail_permanently(**_kwargs: object) -> object:
            nonlocal calls
            calls += 1
            raise ValueError("invalid request")

        with self.assertRaisesRegex(ValueError, "invalid request"):
            asyncio.run(
                _call_image_client(
                    None,
                    {},
                    fail_permanently,
                    timeout_seconds=1,
                    retry_count=5,
                )
            )

        self.assertEqual(calls, 1)

    def test_total_timeout_cancels_http_request_before_slow_response_finishes(self) -> None:
        from codex_image.httpx_transport import HttpxTransport
        from codex_image.webui.executor_transport import _call_image_client

        request_started = threading.Event()
        allow_response_to_finish = threading.Event()
        method_finished = threading.Event()

        class SlowResponseHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
                content_length = int(self.headers.get("Content-Length") or 0)
                if content_length:
                    self.rfile.read(content_length)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{")
                self.wfile.flush()
                request_started.set()
                allow_response_to_finish.wait(2)
                try:
                    self.wfile.write(b"}")
                    self.wfile.flush()
                except OSError:
                    pass

            def log_message(self, _format: str, *_args: object) -> None:
                return None

        with _running_server(SlowResponseHandler) as server:
            transport = HttpxTransport(timeout=5, proxy_map={})

            def slow_request() -> object:
                try:
                    return transport.request(
                        method="POST",
                        url=f"http://127.0.0.1:{server.server_port}/images/generations",
                        headers={"Content-Type": "application/json"},
                        body=b"{}",
                    )
                finally:
                    method_finished.set()

            async def run_call() -> float:
                call = asyncio.create_task(
                    _call_image_client(
                        None,
                        {},
                        slow_request,
                        timeout_seconds=0.5,
                    )
                )
                started = await asyncio.to_thread(request_started.wait, 1)
                self.assertTrue(started, "local slow response did not start")
                started_at = time.monotonic()
                with self.assertRaisesRegex(TimeoutError, "timeout limit 0.5s"):
                    await call
                return time.monotonic() - started_at

            try:
                elapsed_after_response_started = asyncio.run(run_call())
                self.assertTrue(
                    method_finished.is_set(),
                    "timed-out transport left its synchronous caller thread running",
                )
                self.assertFalse(allow_response_to_finish.is_set())
                self.assertLess(elapsed_after_response_started, 0.9)
            finally:
                allow_response_to_finish.set()

    def test_queue_task_becomes_failed_at_total_timeout_without_late_output(self) -> None:
        from codex_image.httpx_transport import HttpxTransport
        from codex_image.openai_images_client import OpenAIImagesImageClient
        from codex_image.webui.app import create_app

        request_started = threading.Event()
        allow_response_to_finish = threading.Event()

        class SlowImageHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
                content_length = int(self.headers.get("Content-Length") or 0)
                if content_length:
                    self.rfile.read(content_length)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", "30")
                self.end_headers()
                self.wfile.write(b'{"data":[')
                self.wfile.flush()
                request_started.set()
                allow_response_to_finish.wait(2)
                try:
                    self.wfile.write(b'{"b64_json":"late"}]}')
                    self.wfile.flush()
                except OSError:
                    pass

            def log_message(self, _format: str, *_args: object) -> None:
                return None

        with _running_server(SlowImageHandler) as server, tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider_url = f"http://127.0.0.1:{server.server_port}/v1"
            app = create_app(
                output_root=root,
                client_factory=lambda: OpenAIImagesImageClient(
                    api_key="test-key",
                    base_url=provider_url,
                    transport=HttpxTransport(timeout=5, proxy_map={}),
                ),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            client = TestClient(app)
            task_id = client.post(
                "/api/generate",
                data={
                    "prompt": "timeout contract",
                    "size": "1024x1024",
                    "codex_mode": "images",
                },
            ).json()["task"]["task_id"]

            try:
                with patch.dict(os.environ, {"CODEX_IMAGE_REQUEST_TIMEOUT_SECONDS": "0.5"}):
                    started_at = time.monotonic()
                    with self.assertRaisesRegex(RuntimeError, "timeout limit 0.5s"):
                        asyncio.run(app.state.queue_manager.run_available_once())
                    elapsed = time.monotonic() - started_at
                task = client.get(f"/api/tasks/{task_id}").json()["task"]

                self.assertTrue(request_started.is_set())
                self.assertFalse(allow_response_to_finish.is_set())
                self.assertLess(elapsed, 0.9)
                self.assertEqual(task["status"], "failed")
                self.assertEqual(task["generated_count"], 0)
                self.assertFalse(
                    any(output.get("status") == "completed" for output in task["outputs"])
                )
                self.assertFalse(any(output.get("file") for output in task["outputs"]))
                self.assertIn("timeout limit 0.5s", task["last_error"])
            finally:
                allow_response_to_finish.set()

    def test_task_cancellation_closes_http_request_before_response_finishes(self) -> None:
        from codex_image.httpx_transport import HttpxTransport
        from codex_image.webui.executor_transport import _call_image_client

        request_started = threading.Event()
        allow_response_to_finish = threading.Event()
        method_finished = threading.Event()

        class SlowResponseHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
                content_length = int(self.headers.get("Content-Length") or 0)
                if content_length:
                    self.rfile.read(content_length)
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{")
                self.wfile.flush()
                request_started.set()
                allow_response_to_finish.wait(2)
                try:
                    self.wfile.write(b"}")
                    self.wfile.flush()
                except OSError:
                    pass

            def log_message(self, _format: str, *_args: object) -> None:
                return None

        with _running_server(SlowResponseHandler) as server:
            transport = HttpxTransport(timeout=5, proxy_map={})

            def slow_request() -> object:
                try:
                    return transport.request(
                        method="POST",
                        url=f"http://127.0.0.1:{server.server_port}/images/generations",
                        headers={"Content-Type": "application/json"},
                        body=b"{}",
                    )
                finally:
                    method_finished.set()

            async def cancel_call() -> float:
                call = asyncio.create_task(
                    _call_image_client(
                        None,
                        {},
                        slow_request,
                        timeout_seconds=5,
                    )
                )
                started = await asyncio.to_thread(request_started.wait, 1)
                self.assertTrue(started, "local slow response did not start")
                started_at = time.monotonic()
                call.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await call
                return time.monotonic() - started_at

            try:
                cancellation_elapsed = asyncio.run(cancel_call())
                self.assertTrue(method_finished.is_set())
                self.assertFalse(allow_response_to_finish.is_set())
                self.assertLess(cancellation_elapsed, 0.4)
            finally:
                allow_response_to_finish.set()

    def test_credentialed_request_refuses_cross_origin_redirect(self) -> None:
        from codex_image.httpx_transport import HttpxTransport

        redirected_request_received = threading.Event()

        class RedirectTargetHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
                redirected_request_received.set()
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, _format: str, *_args: object) -> None:
                return None

        with _running_server(RedirectTargetHandler) as target:
            target_url = f"http://127.0.0.1:{target.server_port}/collect"

            class RedirectOriginHandler(BaseHTTPRequestHandler):
                def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
                    self.send_response(302)
                    self.send_header("Location", target_url)
                    self.send_header("Content-Length", "0")
                    self.end_headers()

                def log_message(self, _format: str, *_args: object) -> None:
                    return None

            with _running_server(RedirectOriginHandler) as origin:
                response = HttpxTransport(timeout=2, proxy_map={}).request(
                    method="GET",
                    url=f"http://127.0.0.1:{origin.server_port}/start",
                    headers={"Authorization": "Bearer secret"},
                    body=b"",
                )

        self.assertEqual(response.status, 302)
        self.assertFalse(redirected_request_received.is_set())

    def test_credentialed_request_follows_same_origin_redirect(self) -> None:
        from codex_image.httpx_transport import HttpxTransport

        observed_authorization: list[str] = []

        class SameOriginRedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
                if self.path == "/start":
                    self.send_response(302)
                    self.send_header("Location", "/final")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                observed_authorization.append(self.headers.get("Authorization") or "")
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, _format: str, *_args: object) -> None:
                return None

        with _running_server(SameOriginRedirectHandler) as server:
            response = HttpxTransport(timeout=2, proxy_map={}).request(
                method="GET",
                url=f"http://127.0.0.1:{server.server_port}/start",
                headers={"Authorization": "Bearer secret"},
                body=b"",
            )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b"ok")
        self.assertEqual(observed_authorization, ["Bearer secret"])

    def test_bounded_request_rejects_declared_oversized_success(self) -> None:
        from codex_image.http import HTTPResponseTooLarge
        from codex_image.httpx_transport import HttpxTransport

        class OversizedResponseHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
                self.send_response(200)
                self.send_header("Content-Length", "11")
                self.end_headers()
                try:
                    self.wfile.write(b"x" * 11)
                except OSError:
                    pass

            def log_message(self, _format: str, *_args: object) -> None:
                return None

        with _running_server(OversizedResponseHandler) as server:
            with self.assertRaisesRegex(HTTPResponseTooLarge, "10-byte limit"):
                HttpxTransport(timeout=2, proxy_map={}).request_bounded(
                    method="GET",
                    url=f"http://127.0.0.1:{server.server_port}/large",
                    headers={},
                    body=b"",
                    max_response_bytes=10,
                )


if __name__ == "__main__":
    unittest.main()
