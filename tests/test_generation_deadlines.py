from __future__ import annotations

import asyncio
from collections import Counter
import threading
import time
import unittest
from unittest.mock import patch

import httpx

from codex_image.webui.executor_transport import _call_image_client
from codex_image.generation.errors import GenerationTimeoutError
from codex_image.generation.partial_results import PartialGenerationError
from codex_image.generation.types import GeneratedAsset, GenerationResult
from codex_image.webui.task_outputs import _write_progress_metadata
from tests import test_generation_failure_boundaries as boundaries
from tests.helpers import TEST_PNG_BASE64, TEST_PNG_BYTES, TEST_WEBP_BYTES


class GenerationDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.fixture = boundaries.GenerationFailureBoundaryTests()

    @staticmethod
    async def short_deadline(*args, **kwargs):
        kwargs["timeout_seconds"] = 0.15
        return await _call_image_client(*args, **kwargs)

    def test_502_and_total_timeout_cannot_replay_a_submitted_generation(self):
        cases = [(profile, codec, failure)
                 for profile, codec in (("openai_images", "gpt_openai_images"),
                                        ("openai_images", "gemini_openai_images"),
                                        ("gemini_generate_content", "gemini_generate_content_image"),
                                        ("t8_images", "gemini_t8_images"))
                 for failure in ("502", "timeout")]
        for profile, codec, failure in cases:
            calls = Counter()

            async def handler(request):
                calls[request.method] += 1
                if failure == "timeout":
                    await asyncio.Future()
                return httpx.Response(502, json={"error": {"code": "upstream_error", "message": "upstream service temporarily unavailable"}})

            with self.subTest(profile=profile, codec=codec, failure=failure), \
                 self.fixture.task(handler, profile=profile, codec=codec) as (app, _, task_id), \
                 patch("codex_image.webui.executor._call_image_client", side_effect=self.short_deadline):
                first = self.fixture.run_queue(app, task_id)
                self.fixture.run_queue(app, task_id)
                self.assertEqual(first["status"], "failed")
                self.assertEqual(calls["POST"], 1)

    def test_batch_timeout_keeps_images_loaded_before_the_deadline(self):
        for profile, codec in (("gemini_generate_content", "gemini_generate_content_image"),
                               ("openai_images", "gemini_openai_images"),
                               ("t8_images", "gemini_t8_images")):
            calls = Counter()

            async def handler(request):
                calls[request.method] += 1
                if profile == "t8_images" and request.method == "POST":
                    return httpx.Response(200, json={"task_id": "remote-synthetic"})
                if request.method != "POST" and not request.url.path.endswith("/images/tasks/remote-synthetic"):
                    await asyncio.Future()
                if profile == "gemini_generate_content":
                    body = {"candidates": [{"content": {"parts": [
                        {"inlineData": {"mimeType": "image/png", "data": TEST_PNG_BASE64}},
                        {"fileData": {"mimeType": "image/png", "fileUri": "https://cdn.example/slow"}},
                    ]}}]}
                else:
                    body = {"data": [{"b64_json": TEST_PNG_BASE64}, {"url": "https://cdn.example/slow"}]}
                    if profile == "t8_images":
                        body = {"data": {"status": "SUCCESS", "data": body}}
                return httpx.Response(200, json=body)

            with self.subTest(profile=profile), self.fixture.task(handler, profile=profile, codec=codec, count=2) as (app, _, task_id), \
                 patch("codex_image.webui.executor._call_image_client", side_effect=self.short_deadline):
                result = self.fixture.run_queue(app, task_id)
                self.fixture.run_queue(app, task_id)
                self.assertEqual(result["status"], "partial_failed")
                self.assertEqual(result["generated_count"], 1)
                self.assertEqual(result["failed_count"], 1)
                self.assertEqual(calls["POST"], 1)
                saved = next(item for item in result["outputs"] if item["status"] == "completed")
                self.assertEqual(app.state.storage.output_path(saved["file"]).read_bytes(), TEST_PNG_BYTES)

    def test_timeout_discards_late_partial_images_and_cancellation_discards_all(self):
        for cancel in (False, True):
            entered, release = threading.Event(), threading.Event()

            def partial_response():
                early_at = time.monotonic()
                entered.set()
                if not release.wait(2):
                    raise RuntimeError("partial response barrier timed out")
                assets = (GeneratedAsset(TEST_PNG_BYTES, "image/png"), GeneratedAsset(TEST_WEBP_BYTES, "image/webp"))
                raise PartialGenerationError(
                    GenerationResult(assets=assets, asset_outcomes=assets), (early_at, time.monotonic()),
                )

            async def run():
                request = asyncio.create_task(_call_image_client(None, {}, partial_response, timeout_seconds=0.03))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                    if cancel:
                        request.cancel()
                    await asyncio.sleep(0.06)
                    self.assertFalse(request.done())
                finally:
                    release.set()
                if cancel:
                    with self.assertRaises(asyncio.CancelledError):
                        await request
                else:
                    with self.assertRaises(GenerationTimeoutError) as raised:
                        await request
                    self.assertEqual([asset.image_bytes for asset in raised.exception.partial_result.assets], [TEST_PNG_BYTES])

            with self.subTest(cancel=cancel):
                asyncio.run(run())

    def test_empty_gemini_image_parts_are_failed_slots(self):
        for invalid in ({"inlineData": {"mimeType": "image/png", "data": ""}},
                        {"inlineData": {"mimeType": "image/png"}},
                        {"fileData": {"mimeType": "image/png", "fileUri": ""}}):
            calls = Counter()

            def handler(request):
                calls[request.method] += 1
                return httpx.Response(200, json={"candidates": [{"content": {"parts": [
                    {"inlineData": {"mimeType": "image/png", "data": TEST_PNG_BASE64}}, invalid,
                ]}}]})

            with self.subTest(invalid=invalid), self.fixture.task(handler, profile="gemini_generate_content",
                    codec="gemini_generate_content_image", count=2) as (app, _, task_id):
                result = self.fixture.run_queue(app, task_id)
                self.assertEqual(result["status"], "partial_failed")
                self.assertEqual(result["generated_count"], 1)
                self.assertEqual(calls["POST"], 1)

    def test_t8_retry_does_not_download_an_already_saved_slot(self):
        calls = Counter()
        retry = False

        async def handler(request):
            calls[request.method] += 1
            if request.method == "POST":
                return httpx.Response(200, json={"task_id": "remote-synthetic"})
            if request.url.path.endswith("/images/tasks/remote-synthetic"):
                return httpx.Response(200, json={"data": {"status": "SUCCESS", "data": {"data": [
                    {"url": "https://cdn.example/saved"}, {"url": "https://cdn.example/retry"},
                ]}}})
            calls[request.url.path] += 1
            if request.url.path == "/saved":
                if retry:
                    await asyncio.Future()
                return httpx.Response(200, content=TEST_PNG_BYTES)
            return httpx.Response(200, content=TEST_WEBP_BYTES) if retry else httpx.Response(503)

        with self.fixture.task(handler, profile="t8_images", codec="gemini_t8_images", count=2) as (app, client, task_id):
            first = self.fixture.run_queue(app, task_id)
            self.assertEqual(first["status"], "partial_failed")
            before = calls["/saved"]
            retry = True
            self.assertEqual(client.post(f"/api/tasks/{task_id}/retry-failed").status_code, 200)
            with patch("codex_image.webui.executor._call_image_client", side_effect=self.short_deadline):
                result = self.fixture.run_queue(app, task_id)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(calls["POST"], 1)
            self.assertEqual(calls["/saved"], before)
            self.assertEqual([app.state.storage.output_path(item["file"]).read_bytes() for item in result["outputs"]],
                             [TEST_PNG_BYTES, TEST_WEBP_BYTES])

    def test_progress_write_cannot_overwrite_a_concurrent_remote_checkpoint(self):
        def handler(request):
            raise AssertionError("No network request is needed")

        with self.fixture.task(handler) as (app, _, task_id):
            storage = app.state.storage
            initial = storage.read_metadata(task_id)
            snapshot_read, release, checkpoint_done = threading.Event(), threading.Event(), threading.Event()
            original_read = storage.read_metadata
            failures = []

            def paused_read(value):
                result = original_read(value)
                if threading.current_thread().name == "progress-writer" and not snapshot_read.is_set():
                    snapshot_read.set()
                    if not release.wait(3):
                        raise RuntimeError("progress barrier timed out")
                return result

            def progress_write():
                try:
                    _write_progress_metadata(storage, task_id, created_at=initial["created_at"], mode="generate",
                        prompt="synthetic", prompt_for_model="synthetic", total_count=1, results=[], output_paths=[],
                        input_files=[], gallery_refs=[], reference_assets=[], request_payload={}, params=initial["params"])
                except BaseException as exc:
                    failures.append(exc)

            def checkpoint_write():
                try:
                    storage.mutate_metadata(task_id, lambda value: value.update(provider_task={"task_id": "remote-synthetic"}))
                    checkpoint_done.set()
                except BaseException as exc:
                    failures.append(exc)

            writer = threading.Thread(target=progress_write, name="progress-writer")
            checkpoint = threading.Thread(target=checkpoint_write)
            with patch.object(storage, "read_metadata", side_effect=paused_read):
                writer.start()
                try:
                    self.assertTrue(snapshot_read.wait(2))
                    checkpoint.start()
                    checkpoint_done.wait(0.05)
                finally:
                    release.set()
                    writer.join(3)
                    checkpoint.join(3)
            self.assertFalse(writer.is_alive() or checkpoint.is_alive())
            self.assertEqual(failures, [])
            self.assertEqual(storage.read_metadata(task_id).get("provider_task"), {"task_id": "remote-synthetic"})
