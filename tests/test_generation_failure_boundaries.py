from __future__ import annotations

import asyncio
from collections import Counter
from contextlib import chdir, contextmanager
import errno
from io import BytesIO
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from PIL import Image

from codex_image.providers.registry import default_registry
from codex_image.http import MAX_HTTP_RESPONSE_BYTES
from codex_image.providers.result_assets import MAX_ASSET_BYTES
from codex_image.providers.t8 import T8ImagesAdapter
from codex_image.webui.app import create_app
from codex_image.webui.queue import QueueTaskError
from codex_image.webui.storage import TaskStorage
from tests.helpers import TEST_PNG_BASE64, TEST_PNG_BYTES, TEST_WEBP_BASE64, TEST_WEBP_BYTES


class GenerationFailureBoundaryTests(unittest.TestCase):
    @contextmanager
    def task(self, handler, *, profile="openai_images", codec="gpt_openai_images", count=1,
             canonical_model=None, requested_parameters=None, edit_files=None):
        model = canonical_model or ("gpt-image-2" if codec.startswith("gpt_") else "nano-banana-pro")
        client_class = httpx.AsyncClient
        with tempfile.TemporaryDirectory(prefix="conjure-failure-test-") as tmp, chdir(tmp):
            root = Path(tmp)
            settings = {"schema_version": 2, "active_provider_id": "relay", "codex_mode": "images",
                        "default_provider_by_model": {model: "relay"}, "providers": [{
                            "id": "relay", "name": "Relay", "base_url": "https://relay.example/v1",
                            "api_key": "synthetic-only", "concurrency": 1, "bindings": [{
                                "id": "image", "canonical_model_id": model, "remote_model_id": "image",
                                "protocol_profile": profile, "parameter_codec": codec, "operations": ["generate", "edit"] if edit_files else ["generate"],
                            }],
                        }]}
            (root / "api.json").write_text(json.dumps(settings))
            (root / "network.json").write_text(json.dumps({"mode": "direct", "image_request_retry_count": 2}))
            options = dict(output_root=root / "outputs", api_settings_path=root / "api.json",
                           auth_settings_path=root / "auth.json", webui_settings_path=root / "webui.json",
                           network_egress_settings_path=root / "network.json", auth_checker=lambda: True,
                           auto_start_queue=False, auto_retry=True, batch_delay_seconds=0)
            app = create_app(**options)
            app.state.reopen_for_test = lambda: create_app(**options)

            def registry(**kwargs):
                result = default_registry(**kwargs)
                if profile == "t8_images":
                    result._protocols[profile] = T8ImagesAdapter(
                        transport=kwargs.get("transport"), sleep=lambda _: None, poll_attempts=2)
                return result

            with patch("codex_image.httpx_transport.httpx.AsyncClient", side_effect=lambda **options:
                       client_class(transport=httpx.MockTransport(handler), **options)), \
                 patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]), \
                 patch("codex_image.webui.queue_runtime.default_registry", side_effect=registry), \
                 patch("codex_image.webui.executor_transport._transient_image_retry_delay_seconds", return_value=0):
                client = TestClient(app)
                parameters = {"canvas.size": "1024x1024"} if model.startswith("gpt") else {
                    "canvas.aspect_ratio": "1:1", "canvas.resolution": "1K"}
                response = client.post("/api/edit" if edit_files else "/api/generate", files=edit_files, data={
                    "prompt": "synthetic audit", "canonical_model_id": model, "provider_id": "relay",
                    "parameters_json": json.dumps({**parameters, "output.count": count, **(requested_parameters or {})}),
                })
                self.assertEqual(response.status_code, 200, response.text)
                yield app, client, response.json()["task"]["task_id"]

    @staticmethod
    def run_queue(app, task_id):
        try:
            asyncio.run(app.state.queue_manager.run_available_once())
        except QueueTaskError:
            pass
        return app.state.storage.read_metadata(task_id)

    def test_ambiguous_post_failure_never_replays_generation(self):
        for error in (httpx.ReadError, httpx.WriteError, httpx.ReadTimeout):
            calls = Counter()

            def handler(request):
                calls[request.method] += 1
                raise error("synthetic") from ConnectionResetError(errno.ECONNRESET, "synthetic")

            with self.subTest(error=error.__name__), self.task(handler) as (app, _, task_id):
                first = self.run_queue(app, task_id)
                self.run_queue(app, task_id)
                self.assertEqual(first["status"], "failed")
                self.assertEqual(calls["POST"], 1)

    def test_mislabeled_rasters_keep_actual_format_through_task_download(self):
        for image_format, suffix, mime in (
            ("PNG", ".png", "image/png"), ("JPEG", ".jpg", "image/jpeg"),
            ("WEBP", ".webp", "image/webp"), ("GIF", ".gif", "image/gif"),
        ):
            buffer = BytesIO()
            image = Image.new("RGB", (4, 3), "white")
            options = {"save_all": True, "append_images": [Image.new("RGB", (4, 3), "black")],
                       "duration": 20} if image_format == "GIF" else {}
            image.save(buffer, format=image_format, **options)
            image_bytes = buffer.getvalue()
            calls = Counter()

            def handler(request):
                calls[request.method] += 1
                if request.method == "POST":
                    return httpx.Response(200, json={"data": [{"url": "https://cdn.example/wrong.png"}]})
                return httpx.Response(200, content=image_bytes, headers={"Content-Type": "image/png"})

            with self.subTest(image_format=image_format), self.task(handler) as (app, client, task_id):
                task = self.run_queue(app, task_id)
                self.assertEqual(task["status"], "completed")
                self.assertEqual(task["output_format"], image_format.lower())
                path = app.state.storage.output_path(task["output_file"])
                self.assertEqual(path.suffix, suffix)
                self.assertEqual(path.read_bytes(), image_bytes)
                downloaded = client.get(task["output_url"])
                self.assertEqual(downloaded.status_code, 200)
                self.assertEqual(downloaded.headers["content-type"], mime)
                self.assertEqual(downloaded.content, image_bytes)
                with Image.open(BytesIO(downloaded.content)) as decoded:
                    self.assertEqual(decoded.format, image_format)
                    self.assertEqual(getattr(decoded, "n_frames", 1), 2 if image_format == "GIF" else 1)
                thumbnail = client.get(f"/api/tasks/{task_id}/outputs/1/thumbnail")
                self.assertEqual(thumbnail.status_code, 200)
                with Image.open(BytesIO(thumbnail.content)) as decoded:
                    self.assertGreater(decoded.width, 0)
                reopened = app.state.reopen_for_test()
                restored = reopened.state.storage.read_metadata(task_id)
                self.assertEqual(restored["output_format"], image_format.lower())
                self.assertEqual(reopened.state.storage.output_path(restored["output_file"]), path)
                self.assertEqual(calls, Counter({"POST": 1, "GET": 1}))

    def test_asset_limits_and_malformed_urls_never_replay_generation(self):
        for failure in ("oversized", "malformed"):
            calls = Counter()

            def handler(request):
                calls[request.method] += 1
                if request.method == "POST":
                    url = "https://[invalid" if failure == "malformed" else "https://cdn.example/image"
                    return httpx.Response(200, json={"data": [{"url": url}]})
                return httpx.Response(200, headers={"Content-Length": str(MAX_ASSET_BYTES + 1)})

            with self.subTest(failure=failure), self.task(handler) as (app, _, task_id):
                first = self.run_queue(app, task_id)
                self.run_queue(app, task_id)
                self.assertEqual(first["status"], "failed")
                self.assertEqual(calls["POST"], 1)

    def test_completed_but_unusable_response_never_replays_generation(self):
        for profile, codec in (("openai_images", "gpt_openai_images"),
                               ("gemini_generate_content", "gemini_generate_content_image")):
            for failure in ("invalid_json", "empty", "oversized"):
                calls = Counter()

                def handler(request):
                    calls[request.method] += 1
                    if failure == "invalid_json":
                        return httpx.Response(200, content=b"not-json")
                    if failure == "oversized":
                        return httpx.Response(200, headers={"Content-Length": str(MAX_HTTP_RESPONSE_BYTES + 1)})
                    return httpx.Response(200, json={"data": [], "candidates": []})

                with self.subTest(profile=profile, failure=failure), self.task(handler, profile=profile, codec=codec) as (app, _, task_id):
                    first = self.run_queue(app, task_id)
                    self.run_queue(app, task_id)
                    self.assertEqual(first["status"], "failed")
                    self.assertEqual(calls["POST"], 1)

    def test_output_write_failure_is_terminal_and_not_counted_as_saved(self):
        calls = Counter()

        def handler(request):
            calls[request.method] += 1
            return httpx.Response(200, json={"data": [{"b64_json": TEST_PNG_BASE64}]})

        with self.task(handler) as (app, _, task_id), patch.object(
            TaskStorage, "write_output", side_effect=OSError(errno.ENOSPC, "No space left on device")
        ):
            first = self.run_queue(app, task_id)
            self.run_queue(app, task_id)
            self.assertEqual(first["status"], "failed")
            self.assertEqual(first["generated_count"], 0)
            self.assertEqual(calls["POST"], 1)

    def test_provider_terminal_error_survives_output_aggregation(self):
        for status in (400, 401, 403):
            calls = Counter()

            def handler(request):
                calls[request.method] += 1
                return httpx.Response(status)

            with self.subTest(status=status), self.task(handler, profile="gemini_generate_content",
                    codec="gemini_generate_content_image") as (app, _, task_id):
                first = self.run_queue(app, task_id)
                self.run_queue(app, task_id)
                self.assertEqual(first["status"], "failed")
                self.assertFalse(first["generation_error"]["retryable"])
                self.assertEqual(calls["POST"], 1)

    def test_mixed_output_errors_retain_the_terminal_transport_boundary(self):
        calls = Counter()

        def handler(request):
            calls[request.method] += 1
            if request.method == "POST":
                if calls["POST"] == 1:
                    return httpx.Response(503)
                return httpx.Response(200, json={"data": [{"url": "https://cdn.example/image"}]})
            raise httpx.ReadError("synthetic")

        with self.task(handler, count=2) as (app, _, task_id):
            first = self.run_queue(app, task_id)
            self.run_queue(app, task_id)
            self.assertEqual(first["status"], "failed")
            self.assertEqual(calls["POST"], 2)

    def test_batch_keeps_successes_and_does_not_regenerate_failed_assets(self):
        for profile, codec in (("gemini_generate_content", "gemini_generate_content_image"),
                               ("openai_images", "gemini_openai_images")):
            for failure in ("http", "read"):
                for bad_first in (False, True):
                    calls = Counter()

                    def handler(request):
                        calls[request.method] += 1
                        if request.method != "POST":
                            if failure == "read":
                                raise httpx.ReadError("synthetic")
                            return httpx.Response(503)
                        if profile == "gemini_generate_content":
                            parts = [{"inlineData": {"mimeType": "image/png", "data": TEST_PNG_BASE64}},
                                     {"fileData": {"mimeType": "image/png", "fileUri": "https://cdn.example/bad"}}]
                            body = {"candidates": [{"content": {"parts": parts[::-1] if bad_first else parts}}]}
                        else:
                            parts = [{"b64_json": TEST_PNG_BASE64}, {"url": "https://cdn.example/bad"}]
                            body = {"data": parts[::-1] if bad_first else parts}
                        return httpx.Response(200, json=body)

                    with self.subTest(profile=profile, failure=failure, bad_first=bad_first), \
                         self.task(handler, profile=profile, codec=codec, count=2) as (app, _, task_id):
                        result = self.run_queue(app, task_id)
                        self.run_queue(app, task_id)
                        self.assertEqual(result["status"], "partial_failed")
                        self.assertEqual(result["generated_count"], 1)
                        self.assertEqual(result["failed_count"], 1)
                        self.assertEqual(calls["POST"], 1)
                        saved = next(item for item in result["outputs"] if item["status"] == "completed")
                        self.assertEqual(app.state.storage.output_path(saved["file"]).read_bytes(), TEST_PNG_BYTES)

    def test_t8_retries_resume_the_persisted_task(self):
        for failure in ("pending", "http"):
            calls = Counter()
            ready = False

            def handler(request):
                calls[request.method] += 1
                if request.method == "POST":
                    return httpx.Response(200, json={"task_id": "remote-synthetic"})
                self.assertTrue(request.url.path.endswith("/images/tasks/remote-synthetic"))
                if not ready:
                    return httpx.Response(503) if failure == "http" else httpx.Response(200, json={"data": {"status": "running"}})
                return httpx.Response(200, json={"data": {"status": "SUCCESS", "data": {"data": [{"b64_json": TEST_PNG_BASE64}]}}})

            with self.subTest(failure=failure), self.task(handler, profile="t8_images", codec="gemini_t8_images") as (app, _, task_id):
                first = self.run_queue(app, task_id)
                self.assertEqual(first.get("provider_task", {}).get("tasks", [{}])[0].get("task_id"), "remote-synthetic")
                ready = True
                final = self.run_queue(app, task_id)
                self.assertEqual(final["status"], "completed")
                self.assertEqual(calls["POST"], 1)

    def test_t8_partial_manual_retry_preserves_slot_identity(self):
        calls = Counter()
        ready = False

        def handler(request):
            calls[request.method] += 1
            if request.method == "POST":
                return httpx.Response(200, json={"task_id": "remote-synthetic"})
            if request.url.path.endswith("/images/tasks/remote-synthetic"):
                return httpx.Response(200, json={"data": {"status": "SUCCESS", "data": {"data": [
                    {"url": "https://cdn.example/first"}, {"b64_json": TEST_WEBP_BASE64},
                ]}}})
            return httpx.Response(200, content=TEST_PNG_BYTES) if ready else httpx.Response(503)

        with self.task(handler, profile="t8_images", codec="gemini_t8_images", count=2) as (app, client, task_id):
            first = self.run_queue(app, task_id)
            self.assertEqual(first["status"], "partial_failed")
            self.assertEqual(first["outputs"][1]["status"], "completed")
            ready = True
            self.assertEqual(client.post(f"/api/tasks/{task_id}/retry-failed").status_code, 200)
            final = self.run_queue(app, task_id)
            self.assertEqual(final["status"], "completed")
            self.assertEqual(calls["POST"], 1)
            self.assertEqual([app.state.storage.output_path(item["file"]).read_bytes() for item in final["outputs"]],
                             [TEST_PNG_BYTES, TEST_WEBP_BYTES])

    def test_t8_remote_task_survives_app_restart(self):
        calls = Counter()
        ready = False

        def handler(request):
            calls[request.method] += 1
            if request.method == "POST":
                return httpx.Response(200, json={"task_id": "durable-synthetic"})
            self.assertTrue(request.url.path.endswith("/images/tasks/durable-synthetic"))
            if not ready:
                return httpx.Response(200, json={"data": {"status": "running"}})
            return httpx.Response(200, json={"data": {"status": "SUCCESS", "data": {"data": [{"b64_json": TEST_PNG_BASE64}]}}})

        with self.task(handler, profile="t8_images", codec="gemini_t8_images") as (app, _, task_id):
            self.run_queue(app, task_id)
            self.run_queue(app, task_id)
            reopened = app.state.reopen_for_test()
            ready = True
            self.assertEqual(TestClient(reopened).post(f"/api/tasks/{task_id}/retry-failed").status_code, 200)
            final = self.run_queue(reopened, task_id)
            self.assertEqual(final["status"], "completed")
            self.assertEqual(calls["POST"], 1)

    def test_t8_one_image_per_job_still_fulfils_requested_batch(self):
        calls = Counter()

        def handler(request):
            calls[request.method] += 1
            if request.method == "POST":
                return httpx.Response(200, json={"task_id": f"job-{calls['POST']}"})
            encoded = TEST_PNG_BASE64 if request.url.path.endswith("job-1") else TEST_WEBP_BASE64
            return httpx.Response(200, json={"data": {"status": "SUCCESS", "data": {"data": [{"b64_json": encoded}]}}})

        with self.task(handler, profile="t8_images", codec="gemini_t8_images", count=2) as (app, _, task_id):
            final = self.run_queue(app, task_id)
            self.assertEqual(final["status"], "completed")
            self.assertEqual(calls["POST"], 2)
            self.assertEqual([app.state.storage.output_path(item["file"]).read_bytes() for item in final["outputs"]],
                             [TEST_PNG_BYTES, TEST_WEBP_BYTES])
