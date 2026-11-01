from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from codex_image.http import HTTPResponse
from codex_image.webui.provider_responses import (
    MAX_FILE_BYTES, MAX_RECORDS, RecordingTransport, SUFFIX,
    append_provider_response, read_provider_responses, response_record,
)
from codex_image.webui.storage import TaskStorage


def reply(value, status=200):
    return HTTPResponse(status=status, body=json.dumps(value).encode(), headers={"content-type": "application/json"})


class ProviderResponseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.storage = TaskStorage(self.root / "outputs", input_root=self.root / "inputs")
        self.task_id = self.storage.create_task("generate").task_id
        self.storage.write_metadata(self.task_id, {"task_id": self.task_id, "status": "completed", "params": {}})

    def record(self, payload, **kwargs):
        return response_record(reply(payload), {"method": "POST", "url": "https://provider.test/v1/images", **kwargs})

    def test_protocols_retain_actual_fields_without_image_payloads(self):
        for payload in (
            {"data": [{"b64_json": "tiny-binary", "revised_prompt": "A real revised prompt\nwith lines"}], "usage": {"input_tokens": 4}},
            {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": "tiny-binary"}}]}}]},
            {"id": "remote-task", "status": "completed", "result": {"data": [{"url": "https://image.test/a.png?token=private"}] }},
        ):
            with self.subTest(payload=tuple(payload)):
                record = self.record(payload)
                self.assertEqual(record["kind"], "json")
                self.assertEqual(set(record["body"]), set(payload))
                self.assertNotIn("tiny-binary", json.dumps(record))
                self.assertNotIn("token=private", json.dumps(record))
        self.assertEqual(self.record({"usage": {"input_tokens": 4}})["body"]["usage"]["input_tokens"], 4)

    def test_credentials_are_scrubbed_in_fields_urls_and_echoes(self):
        payload = {"access_token": "private-value", "error": "echo my-key / Bearer a-token / api_key=another-key",
                   "url": "https://user:pass@example.test/a?X-Amz-Signature=signed&ok=yes"}
        record = self.record(payload, headers={"X-API-Key": "my-key"})
        encoded = json.dumps(record)
        for secret in ("private-value", "my-key", "a-token", "another-key", "user:pass", "=signed"):
            self.assertNotIn(secret, encoded)
        self.assertIn("ok=yes", encoded)

    def test_sse_retains_terminal_event_and_marks_retention(self):
        events = [{"type": "response.created", "sequence_number": n} for n in range(70)]
        events.append({"type": "response.completed", "response": {"output": [{"type": "image_generation_call", "result": "tiny-binary"}], "usage": {"total_tokens": 9}}})
        body = b"".join(b"event: reply\r\ndata: " + json.dumps(e).encode() + b"\r\n\r\n" for e in events) + b"data: [DONE]\n\n"
        record = response_record(HTTPResponse(200, body, {"content-type": "text/event-stream"}), {})
        self.assertEqual(record["kind"], "sse")
        self.assertEqual(len(record["events"]), 64)
        self.assertEqual(record["omitted_events"], 7)
        self.assertEqual(record["events"][-1]["response"]["usage"]["total_tokens"], 9)
        self.assertNotIn("tiny-binary", json.dumps(record))

    def test_multiline_sse_and_malformed_response_are_explicit(self):
        response = HTTPResponse(200, b'data: {"type":\ndata: "response.completed"}\n\n', {})
        self.assertEqual(response_record(response, {})["events"], [{"type": "response.completed"}])
        malformed = response_record(HTTPResponse(502, b"<html>not JSON</html>", {}), {})
        self.assertEqual(malformed["kind"], "unavailable")
        self.assertEqual(malformed["status"], 502)
        self.assertNotIn("<html>", json.dumps(malformed))
        compatible = HTTPResponse(200, b'data: {"id":1}\ndata: {"id":2}\ndata: [DONE]', {})
        self.assertEqual(response_record(compatible, {})["events"], [{"id": 1}, {"id": 2}])
        self.assertIn("non-finite", str(self.record({"invalid": float("nan")})))

    def test_bounds_are_explicit_and_normal_text_is_preserved(self):
        text = "A descriptive prompt with spaces.\n" * 40
        self.assertEqual(self.record({"text": text})["body"]["text"], text)
        self.assertIn("text limit", self.record({"text": "words " * 4000})["body"]["text"])
        deep = {}
        for _ in range(40):
            deep = {"nested": deep}
        self.assertIn("structure limit", json.dumps(self.record(deep)))
        with patch("codex_image.webui.provider_responses.MAX_BODY_BYTES", 5):
            self.assertEqual(self.record({"answer": 123})["kind"], "unavailable")

    def test_transport_observes_once_and_does_not_wrap_asset_requests(self):
        response = reply({"data": [{"url": "https://image.test/a.png"}]})
        calls = []

        class Transport:
            timeout = 37
            proxy_map = {"https": "http://proxy.test"}
            def request(self, **kwargs):
                calls.append(kwargs)
                return response
            def request_asset_bounded(self, **kwargs):
                raise OSError("download failure")

        original = Transport()
        transport = RecordingTransport(original, self.storage, self.task_id)
        self.assertFalse(hasattr(transport, "request_bounded"))
        self.assertEqual(transport.timeout, original.timeout)
        self.assertIs(transport.proxy_map, original.proxy_map)
        self.assertIs(transport.request(method="POST", url="https://provider.test/v1/images"), response)
        with self.assertRaises(OSError):
            transport.request_asset_bounded(url="https://image.test/a.png")
        self.assertEqual(len(calls), 1)
        records = read_provider_responses(self.storage, self.task_id)["records"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["body"]["data"][0]["url"], "https://image.test/a.png")

    def test_capture_failure_never_retries_or_changes_transport_result(self):
        class Transport:
            def request(self, **kwargs):
                return response
        response = reply({"error": "provider error"}, status=400)
        transport = RecordingTransport(Transport(), self.storage, self.task_id)
        with patch("codex_image.webui.provider_responses.append_provider_response", side_effect=OSError), self.assertLogs(level="WARNING"):
            self.assertIs(transport.request(method="POST", url="https://provider.test"), response)
        with patch.object(transport._transport, "request", side_effect=RuntimeError("cancelled")):
            with self.assertRaisesRegex(RuntimeError, "cancelled"):
                transport.request()

    def test_concurrent_replies_bounded_and_deleted_with_task(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: append_provider_response(self.storage, self.task_id, self.record({"id": i})), range(24)))
        data = read_provider_responses(self.storage, self.task_id)
        self.assertEqual(len(data["records"]), MAX_RECORDS)
        self.assertEqual(data["omitted_records"], 24 - MAX_RECORDS)
        path = self.storage._source_data_path(self.task_id, SUFFIX)
        self.assertLessEqual(path.stat().st_size, MAX_FILE_BYTES)
        self.storage.delete_task(self.task_id)
        self.assertFalse(path.exists())
        append_provider_response(self.storage, self.task_id, self.record({"id": "late"}))
        self.assertFalse(path.exists())

    def test_legacy_task_without_response_is_empty(self):
        legacy = "20000101000000-old"
        self.storage._legacy_source_data_path(legacy, "metadata.json").write_text("{}")
        self.assertEqual(read_provider_responses(self.storage, legacy)["records"], [])

    def test_symlink_and_oversized_sidecar_are_rejected(self):
        path = self.storage._source_data_path(self.task_id, SUFFIX)
        secret = self.root / "private.json"
        secret.write_text('{"private": "never read"}')
        path.symlink_to(secret)
        with self.assertRaises(OSError):
            read_provider_responses(self.storage, self.task_id)
        with self.assertRaises(OSError):
            append_provider_response(self.storage, self.task_id, self.record({}))
        path.unlink()
        path.write_bytes(b"x" * (MAX_FILE_BYTES + 1))
        with self.assertRaises(OSError):
            read_provider_responses(self.storage, self.task_id)
        self.assertEqual(json.loads(secret.read_text()), {"private": "never read"})

    def test_route_returns_saved_reply_without_polluting_task_details(self):
        from codex_image.webui.app import create_app
        app = create_app(output_root=self.root / "app", input_root=self.root / "app-input", auth_checker=lambda: True, auto_start_queue=False)
        storage = app.state.storage
        task_id = storage.create_task("generate").task_id
        storage.write_metadata(task_id, {"task_id": task_id, "status": "completed", "params": {}})
        with TestClient(app) as client:
            url = f"/api/tasks/{task_id}/provider-responses"
            self.assertEqual(client.get(url).json()["records"], [])
            append_provider_response(storage, task_id, self.record({"provider_id": "actual-reply"}))
            response = client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.json()["records"][0]["body"], {"provider_id": "actual-reply"})
            self.assertNotIn("actual-reply", client.get(f"/api/tasks/{task_id}").text)
            self.assertEqual(client.get("/api/tasks/missing/provider-responses").status_code, 404)
            storage._source_data_path(task_id, SUFFIX).write_text("not JSON")
            self.assertEqual(client.get(url).status_code, 503)

    def test_queue_client_uses_the_recording_transport(self):
        from codex_image.webui.app import create_app
        from codex_image.webui.queue import QueueChannel
        from codex_image.webui.queue_runtime import _queue_execution_contract
        app = create_app(output_root=self.root / "queue-app", auth_checker=lambda: True, auto_start_queue=False)
        storage = app.state.storage
        task_id = storage.create_task("generate").task_id
        metadata = {"task_id": task_id, "status": "running", "params": {"codex_mode": "images"}}
        storage.write_metadata(task_id, metadata)
        observed = []

        class Client:
            def __init__(self, auth_state, *, transport):
                observed.append(transport)

        class Transport:
            def request(self, **kwargs):
                return reply({"id": "through-queue"})

        with (
            patch("codex_image.webui.queue_runtime.load_auth_state", return_value=object()),
            patch("codex_image.webui.queue_runtime.CodexImagesImageClient", Client),
            patch.object(app.state.ctx.network_egress_manager, "transport", return_value=Transport()),
        ):
            _queue_execution_contract(app.state.ctx, QueueChannel(channel_id="codex:local", auth_source="codex"), metadata)
        observed[0].request(method="POST", url="https://provider.test/v1/images")
        self.assertEqual(read_provider_responses(storage, task_id)["records"][0]["body"], {"id": "through-queue"})
