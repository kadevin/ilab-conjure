from __future__ import annotations

import asyncio
import base64
import json
import os
import threading
import time
import tempfile
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx
from PIL import Image


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
    def test_queue_stop_interrupts_all_requests_keeps_outputs_and_runs_next_task(self) -> None:
        from codex_image.httpx_transport import HttpxTransport
        from codex_image.webui.app import create_app
        from codex_image.webui.network_egress import NetworkEgressSettings
        from codex_image.webui.settings_store import ApiSettings, AuthSettings

        image_buffer = BytesIO()
        Image.new("RGB", (12, 8), (70, 120, 170)).save(image_buffer, format="PNG")
        png = base64.b64encode(image_buffer.getvalue()).decode()
        for stop_route in ("single", "batch"):
            with self.subTest(stop_route=stop_route):
                held_requests_started = threading.Event()
                all_target_calls_finished = threading.Event()
                next_request_started = threading.Event()
                late_responses_finished = threading.Event()
                release_responses = threading.Event()
                lock = threading.Lock()
                target_calls = 0
                held_calls = 0
                finished_target_calls = 0
                finished_held_responses = 0

                class TrackedTransport(HttpxTransport):
                    def request(self, **kwargs):
                        payload = json.loads(kwargs.get("body") or b"{}")
                        try:
                            return super().request(**kwargs)
                        finally:
                            nonlocal finished_target_calls
                            if "cancel-contract-target" in payload.get("prompt", ""):
                                with lock:
                                    finished_target_calls += 1
                                    if finished_target_calls == 3:
                                        all_target_calls_finished.set()

                class HeldImagesHandler(BaseHTTPRequestHandler):
                    protocol_version = "HTTP/1.1"

                    def do_POST(self) -> None:  # noqa: N802 - stdlib contract
                        nonlocal target_calls, held_calls, finished_held_responses
                        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                        target = "cancel-contract-target" in payload.get("prompt", "")
                        with lock:
                            if target:
                                target_calls += 1
                            hold = target and target_calls > 1
                        body = json.dumps({"data": [{"b64_json": png}]}).encode()
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(body)))
                        self.send_header("Connection", "close")
                        self.end_headers()
                        if hold:
                            self.wfile.write(body[:1])
                            self.wfile.flush()
                            with lock:
                                held_calls += 1
                                if held_calls == 2:
                                    held_requests_started.set()
                            release_responses.wait(5)
                            body = body[1:]
                        elif not target:
                            next_request_started.set()
                        try:
                            self.wfile.write(body)
                            self.wfile.flush()
                        except OSError:
                            pass
                        finally:
                            if hold:
                                with lock:
                                    finished_held_responses += 1
                                    if finished_held_responses == 2:
                                        late_responses_finished.set()

                    def log_message(self, _format: str, *_args: object) -> None:
                        return None

                with _running_server(HeldImagesHandler) as server, tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    # The fixture server must not inherit the host's system proxy.
                    NetworkEgressSettings(root / "network.json").write({"mode": "direct"})
                    AuthSettings(root / "auth.json").write_source("api")
                    ApiSettings(root / "api.json").write({
                        "base_url": f"http://127.0.0.1:{server.server_port}/v1",
                        "api_key": "fixture-key",
                        "image_model": "gpt-image-2",
                        "api_mode": "images",
                        "images_concurrency": 2,
                    })
                    with patch("codex_image.webui.network_egress.HttpxTransport", TrackedTransport):
                        app = create_app(
                            output_root=root / "tasks",
                            auth_settings_path=root / "auth.json",
                            api_settings_path=root / "api.json",
                            network_egress_settings_path=root / "network.json",
                            auth_checker=lambda: True,
                            batch_delay_seconds=0,
                            auto_retry=False,
                        )
                        try:
                            with TestClient(app) as client:
                                created = client.post("/api/generate", data={
                                    "prompt": "cancel-contract-target", "size": "1024x1024", "n": "4",
                                })
                                self.assertEqual(created.status_code, 200, created.text)
                                task_id = created.json()["task"]["task_id"]
                                self.assertTrue(held_requests_started.wait(3))
                                deadline = time.monotonic() + 1
                                while True:
                                    before = client.get(f"/api/tasks/{task_id}").json()["task"]
                                    completed = [o for o in before["outputs"] if o["status"] == "completed"]
                                    if completed or time.monotonic() >= deadline:
                                        break
                                    time.sleep(0.01)
                                self.assertEqual(len(completed), 1, before["outputs"])
                                queued = client.post("/api/generate", data={
                                    "prompt": "cancel-contract-next", "size": "1024x1024", "n": "1",
                                }).json()["task"]
                                self.assertFalse(next_request_started.is_set())
                                started_at = time.monotonic()
                                if stop_route == "single":
                                    stopped = client.delete(f"/api/queue/{task_id}")
                                else:
                                    stopped = client.post("/api/queue/cancel-batch", json={"task_ids": [task_id]})
                                self.assertEqual(stopped.status_code, 200)
                                self.assertTrue(
                                    all_target_calls_finished.wait(1),
                                    "stop did not close the in-flight provider calls",
                                )
                                self.assertTrue(next_request_started.wait(1), "provider slots were not released")
                                self.assertLess(time.monotonic() - started_at, 2)
                                self.assertFalse(release_responses.is_set())
                                cancelled = client.get(f"/api/tasks/{task_id}").json()["task"]
                                self.assertTrue(cancelled.get("cancelled_at"))
                                self.assertEqual(cancelled["error"], "Task cancelled by user.")
                                self.assertIn(completed[0], cancelled["outputs"])
                                self.assertEqual(sorted(o["status"] for o in cancelled["outputs"]), ["completed", "failed", "failed", "failed"])
                                self.assertTrue(app.state.storage.output_path(completed[0]["file"]).exists())
                                self.assertNotIn(task_id, app.state.running_worker_tasks)
                                self.assertFalse(any(item["task_id"] == task_id for item in app.state.queue_storage.read_state()["running"].values()))
                                self.assertFalse(app.state.queue_worker_task.done())
                                self.assertIn(client.get(f"/api/tasks/{queued['task_id']}").json()["task"]["status"], {"running", "completed"})
                                release_responses.set()
                                self.assertTrue(late_responses_finished.wait(1))
                                late = client.get(f"/api/tasks/{task_id}").json()["task"]
                                self.assertEqual(late["outputs"], cancelled["outputs"])
                                self.assertEqual(target_calls, 3, "a cancelled waiting output sent a request")
                        finally:
                            release_responses.set()

    def test_transient_retry_count_means_retries_after_the_first_attempt(self) -> None:
        from codex_image.webui.executor_transport import _call_image_client

        for retry_count, expected_attempts in ((0, 1), (2, 3), (5, 6)):
            calls = 0

            def fail_transiently(**_kwargs: object) -> object:
                nonlocal calls
                calls += 1
                raise httpx.ConnectError("Connection could not be established")

            with self.subTest(retry_count=retry_count):
                with (
                    patch(
                        "codex_image.webui.executor_transport._transient_image_retry_delay_seconds",
                        return_value=0,
                    ),
                    self.assertRaises(httpx.ConnectError),
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

    def test_cancellation_during_retry_backoff_does_not_send_another_request(self) -> None:
        from codex_image.webui.executor_transport import _call_image_client

        calls = 0

        def transient_failure() -> object:
            nonlocal calls
            calls += 1
            raise httpx.ConnectError("Connection could not be established")

        async def cancel_backoff() -> None:
            backoff_started = asyncio.Event()

            def retry_delay(_attempt: int) -> float:
                backoff_started.set()
                return 60

            with patch("codex_image.webui.executor_transport._transient_image_retry_delay_seconds", retry_delay):
                call = asyncio.create_task(_call_image_client(None, {}, transient_failure, timeout_seconds=5))
                await asyncio.wait_for(backoff_started.wait(), 1)
                call.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await call

        asyncio.run(cancel_backoff())
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
                network_egress_settings_path=root / "network-settings.json",
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
                        timeout_seconds=request_timeout,
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
                for request_timeout in (5, None):
                    with self.subTest(timeout_seconds=request_timeout):
                        request_started.clear()
                        method_finished.clear()
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
