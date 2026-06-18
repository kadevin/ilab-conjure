from __future__ import annotations

import asyncio
import json
import os
import struct
import tempfile
import threading
import time
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from tests.webui_helpers import (
    AlwaysFailQueueTestExecutor,
    BlockingActiveConcurrentApiImageClient,
    BlockingConcurrentApiImageClient,
    BlockingFirstImageClient,
    BlockingFirstQueueTestExecutor,
    BlockingFourthImageClient,
    BlockingSecondImageClient,
    CancelQueueTestExecutor,
    CancelsTaskBeforeReturningImageClient,
    CapturingApiImageClient,
    CapturingApiResponsesImageClient,
    ConcurrentApiImageClient,
    FailFastSlowCompleteQueueTestExecutor,
    FailsSecondImageClient,
    FakeImageClient,
    InvalidRequestImageClient,
    PartiallyFailingConcurrentApiImageClient,
    ProviderSwitchRetryApiImageClient,
    QueueTestExecutor,
    QuotaLimitedAfterFirstImageClient,
    QuotaLimitedApiImageClient,
    QuotaLimitedImageClient,
    QuotaLimitedOnceImageClient,
    SharedConcurrentApiImageClient,
    SlowFourthImageClient,
    SlowImageClient,
    input_name,
    metadata_path,
    output_name,
    output_url,
    request_path,
)


class WebUIQueueTests(unittest.TestCase):
    def test_queue_api_reports_waiting_tasks(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)
            created = client.post("/api/generate", data={"prompt": "queue item", "size": "1024x1024"})
            queue = client.get("/api/queue").json()

        self.assertEqual(created.status_code, 200)
        self.assertEqual(queue["summary"]["waiting_count"], 1)
        self.assertEqual(queue["waiting"][0]["task_id"], created.json()["task"]["task_id"])
    def test_queue_api_restarts_stopped_background_worker(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: FakeImageClient(), auth_checker=lambda: True)
            with TestClient(app) as client:
                original_worker = app.state.queue_worker_task
                original_worker.cancel()
                for _ in range(50):
                    if original_worker.done():
                        break
                    time.sleep(0.02)
                self.assertTrue(original_worker.done())

                response = client.get("/api/queue")
                restarted_worker = app.state.queue_worker_task
                self.assertIsNot(restarted_worker, original_worker)
                self.assertFalse(restarted_worker.done())

        self.assertEqual(response.status_code, 200)
    def test_events_endpoint_streams_initial_snapshot(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            app.state.storage.write_metadata(
                "20260510101010-aaaaaaaa",
                {
                    "task_id": "20260510101010-aaaaaaaa",
                    "created_at": "2026-05-10T10:10:10+00:00",
                    "status": "completed",
                    "prompt": "event snapshot",
                    "prompt_for_model": "expanded event prompt should stay out of the main snapshot",
                    "outputs": [{"index": 1, "status": "completed", "thumbnail_url": "/thumb.jpg"}],
                    "generated_count": 1,
                    "total_count": 1,
                },
            )
            client = TestClient(app)
            response = client.get("/api/events")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])
        self.assertIn('"type": "snapshot"', response.text)
        self.assertIn('"tasks"', response.text)
        self.assertIn('"queue"', response.text)
        self.assertIn('"summary_only": true', response.text)
        self.assertIn('"thumbnail_urls": ["/thumb.jpg"]', response.text)
        self.assertNotIn("expanded event prompt", response.text)
        self.assertNotIn('"outputs"', response.text)
    def test_events_endpoint_restarts_stopped_background_worker(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: FakeImageClient(), auth_checker=lambda: True)
            with TestClient(app) as client:
                original_worker = app.state.queue_worker_task
                original_worker.cancel()
                for _ in range(50):
                    if original_worker.done():
                        break
                    time.sleep(0.02)
                self.assertTrue(original_worker.done())

                response = client.get("/api/events")
                restarted_worker = app.state.queue_worker_task
                self.assertIsNot(restarted_worker, original_worker)
                self.assertFalse(restarted_worker.done())

        self.assertEqual(response.status_code, 200)
    def test_create_app_uses_sqlite_queue_storage_by_default(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.storage import SQLiteQueueStorage

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), auth_checker=lambda: True, auto_start_queue=False)

        self.assertIsInstance(app.state.queue_storage, SQLiteQueueStorage)
    def test_queue_worker_executes_queued_generate_task(self) -> None:
        from codex_image.webui.app import create_app

        fake = FakeImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            auth_settings_path = Path(tmp) / "auth-settings.json"
            auth_settings_path.write_text(json.dumps({"source": "codex"}), encoding="utf-8")
            app = create_app(
                output_root=Path(tmp),
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                auth_settings_path=auth_settings_path,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            client = TestClient(app)
            created = client.post(
                "/api/generate",
                data={"prompt": "run queued", "main_model": "gpt-5.4", "size": "1024x1024", "quality": "low"},
            )
            task_id = created.json()["task"]["task_id"]

            asyncio.run(app.state.queue_manager.run_available_once())
            task = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["requested_backend"], "codex_images")
        self.assertEqual(task["backend"], "codex_images")
        self.assertEqual(task["params"]["codex_mode"], "images")
        self.assertEqual(len(fake.generate_calls), 1)
        self.assertEqual(fake.generate_calls[0]["main_model"], "gpt-5.4")
        self.assertEqual(task["output_urls"], [output_url(task_id)])
    def test_queue_worker_appends_ratio_instruction_for_older_queued_task_metadata(self) -> None:
        from codex_image.webui.app import create_app

        fake = FakeImageClient()
        prompt = "生成一张横版电影海报"
        expected_model_prompt = f"{prompt}\n\n将宽高比设为 16:9"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth_settings_path = root / "auth-settings.json"
            auth_settings_path.write_text(json.dumps({"source": "codex"}), encoding="utf-8")
            app = create_app(
                output_root=root,
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                auth_settings_path=auth_settings_path,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            client = TestClient(app)
            created = client.post(
                "/api/generate",
                data={
                    "prompt": prompt,
                    "size": "1536x864",
                    "ratio": "16:9",
                    "quality": "low",
                    "prompt_fidelity": "off",
                },
            )
            task_id = created.json()["task"]["task_id"]
            metadata_file = metadata_path(root, task_id)
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            metadata["prompt_for_model"] = prompt
            metadata_file.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

            asyncio.run(app.state.queue_manager.run_available_once())
            task = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertEqual(created.status_code, 200)
        self.assertEqual(task["status"], "completed")
        self.assertEqual(len(fake.generate_calls), 1)
        self.assertEqual(fake.generate_calls[0]["prompt"], expected_model_prompt)
        self.assertEqual(task["prompt_for_model"], expected_model_prompt)
    def test_queue_worker_passes_prompt_guard_instructions_for_strict_tasks(self) -> None:
        from codex_image.webui.app import create_app

        fake = FakeImageClient()
        prompt = "文案标题设计偏儿童Q版卡通化，色彩偏淡彩"
        with tempfile.TemporaryDirectory() as tmp:
            auth_settings_path = Path(tmp) / "auth-settings.json"
            auth_settings_path.write_text(json.dumps({"source": "codex"}), encoding="utf-8")
            app = create_app(
                output_root=Path(tmp),
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                auth_settings_path=auth_settings_path,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            client = TestClient(app)
            client.post("/api/generate", data={"prompt": prompt, "size": "1024x1024", "quality": "low", "codex_mode": "responses"})

            asyncio.run(app.state.queue_manager.run_available_once())

        self.assertEqual(len(fake.generate_calls), 1)
        self.assertIn("只能扩写用户提示词", fake.generate_calls[0]["instructions"])
        self.assertIn("标题字体/标题设计：文案标题设计偏儿童Q版卡通化", fake.generate_calls[0]["instructions"])
    def test_queue_worker_does_not_block_queue_visibility_during_slow_generation(self) -> None:
        from codex_image.webui.app import create_app

        fake = SlowImageClient(delay_seconds=0.2)
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                output_root=Path(tmp),
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                auth_settings_path=Path(tmp) / "auth-settings.json",
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            client = TestClient(app)
            created = client.post("/api/generate", data={"prompt": "slow queued", "size": "1024x1024", "quality": "low"})
            task_id = created.json()["task"]["task_id"]

            async def observe_running_state() -> tuple[float, dict[str, Any]]:
                started_at = time.monotonic()
                worker = asyncio.create_task(app.state.queue_manager.run_available_once())
                await asyncio.sleep(0.05)
                elapsed = time.monotonic() - started_at
                state = app.state.queue_storage.read_state()
                await worker
                return elapsed, state

            elapsed, state = asyncio.run(observe_running_state())

        self.assertLess(elapsed, 0.15)
        self.assertEqual([item["task_id"] for item in state["running"].values()], [task_id])
    def test_queue_cancel_running_task_unblocks_channel_worker(self) -> None:
        from codex_image.webui.app import create_app

        fake = BlockingFirstImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                output_root=Path(tmp),
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
            )
            with TestClient(app) as client:
                first = client.post("/api/generate", data={"prompt": "blocked first", "size": "1024x1024"}).json()["task"]
                second = client.post("/api/generate", data={"prompt": "next task", "size": "1024x1024"}).json()["task"]
                self.assertTrue(fake.first_call_started.wait(timeout=5))

                deleted = client.delete(f"/api/queue/{first['task_id']}")
                try:
                    self.assertTrue(fake.second_call_started.wait(timeout=3))
                finally:
                    fake.release_first_call.set()
                cancelled = client.get(f"/api/tasks/{first['task_id']}").json()["task"]
                next_task = client.get(f"/api/tasks/{second['task_id']}").json()["task"]

        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(cancelled["status"], "failed")
        self.assertTrue(cancelled["cancel_requested"])
        self.assertIn(next_task["status"], {"running", "completed"})
    def test_queue_cancel_running_fourth_slot_persists_cancel_and_releases_next_task(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.queue import QueueChannel

        fake = BlockingFourthImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                output_root=Path(tmp),
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
            )
            app.state.queue_manager.channels = [QueueChannel(channel_id="codex:local", auth_source="codex")]
            with TestClient(app) as client:
                first = client.post(
                    "/api/generate",
                    data={"prompt": "blocked fourth", "size": "1024x1024", "quality": "low", "n": "4"},
                ).json()["task"]
                second = client.post(
                    "/api/generate",
                    data={"prompt": "next after cancel", "size": "1024x1024", "quality": "low", "n": "1"},
                ).json()["task"]
                self.assertTrue(fake.fourth_call_started.wait(timeout=5))

                deleted = client.delete(f"/api/queue/{first['task_id']}")
                try:
                    self.assertTrue(fake.second_task_started.wait(timeout=3))
                finally:
                    fake.release_fourth_call.set()
                cancelled = client.get(f"/api/tasks/{first['task_id']}").json()["task"]
                next_task = client.get(f"/api/tasks/{second['task_id']}").json()["task"]
                queue = client.get("/api/queue").json()

        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(cancelled["status"], "failed")
        self.assertEqual(cancelled["error"], "Task cancelled by user.")
        self.assertTrue(cancelled["cancel_requested"])
        self.assertFalse(any(task["task_id"] == first["task_id"] for task in queue["running"]))
        self.assertIn(next_task["status"], {"running", "completed"})
    def test_queue_worker_does_not_overwrite_cancelled_task_when_request_returns(self) -> None:
        from codex_image.webui.app import create_app

        fake = CancelsTaskBeforeReturningImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root,
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            fake.storage = app.state.storage
            client = TestClient(app)
            created = client.post("/api/generate", data={"prompt": "cancel late return", "size": "1024x1024", "quality": "low"})
            task_id = created.json()["task"]["task_id"]
            fake.task_id = task_id

            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(app.state.queue_manager.run_available_once())
            task = client.get(f"/api/tasks/{task_id}").json()["task"]
            output_exists = (root / output_name(task_id)).exists()
            queue_state = app.state.queue_storage.read_state()

        self.assertEqual(task["status"], "failed")
        self.assertEqual(task["error"], "Task cancelled by user.")
        self.assertTrue(task["cancel_requested"])
        self.assertNotIn("output_url", task)
        self.assertFalse(output_exists)
        self.assertEqual(queue_state["running"], {})
    def test_startup_recovery_fails_old_running_and_preserves_waiting(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_app = create_app(output_root=root, client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            first_client = TestClient(first_app)
            waiting = first_client.post("/api/generate", data={"prompt": "waiting", "size": "1024x1024"}).json()["task"]
            running = first_client.post("/api/generate", data={"prompt": "running", "size": "1024x1024"}).json()["task"]
            running_metadata = json.loads(metadata_path(root, running["task_id"]).read_text(encoding="utf-8"))
            running_metadata["status"] = "running"
            metadata_path(root, running["task_id"]).write_text(json.dumps(running_metadata), encoding="utf-8")
            first_app.state.queue_storage.remove_waiting(running["task_id"])
            first_app.state.queue_storage.set_running("codex:local", running["task_id"], auth_source="codex")

            second_app = create_app(output_root=root, client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            second_client = TestClient(second_app)
            waiting_task = second_client.get(f"/api/tasks/{waiting['task_id']}").json()["task"]
            running_task = second_client.get(f"/api/tasks/{running['task_id']}").json()["task"]
            queue_state = second_app.state.queue_storage.read_state()

        self.assertEqual(waiting_task["status"], "queued")
        self.assertEqual(running_task["status"], "failed")
        self.assertIn("Service restarted", running_task["error"])
        self.assertEqual(queue_state["running"], {})
        self.assertIn(waiting["task_id"], queue_state["waiting"])
        self.assertNotIn(running["task_id"], queue_state["waiting"])
    def test_startup_recovery_fails_old_queued_auto_retry(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_app = create_app(output_root=root, client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            first_client = TestClient(first_app)
            queued = first_client.post("/api/generate", data={"prompt": "old retry", "size": "1024x1024"}).json()["task"]
            task_id = queued["task_id"]
            metadata = json.loads(metadata_path(root, task_id).read_text(encoding="utf-8"))
            metadata.update(
                {
                    "status": "queued",
                    "attempts": 1,
                    "max_attempts": 2,
                    "last_error": "temporary server failure",
                    "error": "",
                }
            )
            metadata_path(root, task_id).write_text(json.dumps(metadata), encoding="utf-8")

            second_app = create_app(output_root=root, client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            second_client = TestClient(second_app)
            recovered = second_client.get(f"/api/tasks/{task_id}").json()["task"]
            queue_state = second_app.state.queue_storage.read_state()

        self.assertEqual(recovered["status"], "failed")
        self.assertEqual(recovered["error"], "temporary server failure")
        self.assertEqual(queue_state["waiting"], [])
        self.assertEqual(queue_state["running"], {})
    def test_startup_recovery_marks_running_task_completed_when_outputs_exist(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.storage import TaskStorage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = TaskStorage(root)
            created = storage.create_task("generate")
            task_id = created.task_id
            storage.write_metadata(
                task_id,
                {
                    "task_id": task_id,
                    "created_at": "2026-05-03T07:31:57+00:00",
                    "updated_at": "2026-05-03T07:32:30+00:00",
                    "mode": "generate",
                    "status": "running",
                    "prompt": "interrupted",
                    "prompt_for_model": "interrupted",
                    "params": {"n": 2, "size": "1024x1024", "output_format": "png"},
                    "input_files": [],
                    "gallery_refs": [],
                    "generated_count": 1,
                    "total_count": 2,
                    "output_files": [output_name(task_id, 1)],
                    "output_urls": [output_url(task_id, 1)],
                },
            )
            storage.write_output(task_id, b"first", "png", index=1)
            storage.write_output(task_id, b"second", "png", index=2)

            app = create_app(output_root=root, client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)
            task = client.get(f"/api/tasks/{task_id}").json()["task"]
            queue = client.get("/api/queue").json()

        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["generated_count"], 2)
        self.assertEqual(task["total_count"], 2)
        self.assertEqual(task["output_files"], [output_name(task_id, 1), output_name(task_id, 2)])
        self.assertEqual(task["output_urls"], [output_url(task_id, 1), output_url(task_id, 2)])
        self.assertEqual(
            [(item["index"], item["status"]) for item in task["outputs"]],
            [(1, "completed"), (2, "completed")],
        )
        self.assertEqual(queue["waiting"], [])
        self.assertEqual(queue["running"], [])

    def test_startup_recovery_does_not_count_thumbnails_as_outputs(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.storage import TaskStorage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = TaskStorage(root)
            created = storage.create_task("generate")
            task_id = created.task_id
            first_output = storage.write_output(task_id, b"first", "jpg", index=1)
            thumbnail_path = storage.output_thumbnail_path(task_id, 1)
            thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
            thumbnail_path.write_bytes(b"first-thumb")
            first_output_file = storage.output_file(first_output)
            first_output_url = output_url(task_id, 1, "jpg")
            thumbnail_file = storage.output_file(thumbnail_path)
            thumbnail_url = f"/outputs/{thumbnail_file}"
            storage.write_metadata(
                task_id,
                {
                    "task_id": task_id,
                    "created_at": "2026-05-03T07:31:57+00:00",
                    "updated_at": "2026-05-03T07:32:30+00:00",
                    "mode": "generate",
                    "status": "running",
                    "prompt": "interrupted",
                    "prompt_for_model": "interrupted",
                    "params": {"n": 2, "size": "1024x1024", "output_format": "jpg"},
                    "input_files": [],
                    "gallery_refs": [],
                    "generated_count": 1,
                    "total_count": 2,
                    "output_files": [first_output_file],
                    "output_urls": [first_output_url],
                    "outputs": [
                        {
                            "index": 1,
                            "status": "completed",
                            "file": first_output_file,
                            "url": first_output_url,
                            "thumbnail_file": thumbnail_file,
                            "thumbnail_url": thumbnail_url,
                        }
                    ],
                },
            )

            app = create_app(output_root=root, client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            task = TestClient(app).get(f"/api/tasks/{task_id}").json()["task"]

        self.assertEqual(task["status"], "failed")
        self.assertEqual(task["generated_count"], 1)
        self.assertEqual(task["total_count"], 2)
        self.assertEqual(task["output_files"], [first_output_file])
        self.assertEqual([record["file"] for record in task["outputs"]], [first_output_file])
        self.assertIn("Service restarted", task["error"])

    def test_queue_worker_executes_queued_edit_task_with_mask(self) -> None:
        from codex_image.webui.app import create_app

        fake = FakeImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                output_root=Path(tmp),
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            client = TestClient(app)
            created = client.post(
                "/api/edit",
                data={"prompt": "edit queued", "size": "1024x1024", "quality": "low"},
                files={
                    "images": ("input.png", b"input", "image/png"),
                    "mask": ("mask.png", b"mask", "image/png"),
                },
            )
            task_id = created.json()["task"]["task_id"]

            asyncio.run(app.state.queue_manager.run_available_once())
            task = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertEqual(task["status"], "completed")
        self.assertEqual(len(fake.edit_calls), 1)
        self.assertEqual(task["input_files"], [])
        self.assertEqual(task["input_sources"][0]["kind"], "asset")
        self.assertNotIn("mask.png", task["input_files"])
        self.assertTrue(fake.edit_calls[0]["mask_image"].startswith("data:image/png;base64,"))
    def test_queue_worker_executes_multiple_outputs(self) -> None:
        from codex_image.webui.app import create_app

        fake = FakeImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                output_root=Path(tmp),
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            client = TestClient(app)
            created = client.post("/api/generate", data={"prompt": "many", "size": "1024x1024", "quality": "low", "n": "3"})
            task_id = created.json()["task"]["task_id"]

            asyncio.run(app.state.queue_manager.run_available_once())
            task = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertEqual(task["status"], "completed")
        self.assertEqual(len(fake.generate_calls), 3)
        self.assertEqual(
            task["output_urls"],
            [output_url(task_id, 1), output_url(task_id, 2), output_url(task_id, 3)],
        )
    def test_queue_worker_does_not_retry_usage_limit_on_same_channel(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.queue import QueueChannel

        fake = QuotaLimitedImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                output_root=Path(tmp),
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            app.state.queue_manager.channels = [QueueChannel(channel_id="codex:local", auth_source="codex")]
            app.state.queue_manager.max_attempts = 2
            client = TestClient(app)
            created = client.post("/api/generate", data={"prompt": "quota limited", "size": "1024x1024", "quality": "low"})
            task_id = created.json()["task"]["task_id"]

            with self.assertRaisesRegex(RuntimeError, "usage limit"):
                asyncio.run(app.state.queue_manager.run_available_once())
            asyncio.run(app.state.queue_manager.run_available_once())
            task = client.get(f"/api/tasks/{task_id}").json()["task"]
            queue_state = app.state.queue_storage.read_state()

        self.assertEqual(len(fake.generate_calls), 1)
        self.assertEqual(task["status"], "failed")
        self.assertIn("usage limit", task["last_error"])
        self.assertEqual(queue_state["waiting"], [])
        self.assertEqual(queue_state["running"], {})
    def test_queue_worker_does_not_requeue_non_retryable_invalid_request(self) -> None:
        from codex_image.webui.app import create_app

        fake = InvalidRequestImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                output_root=Path(tmp),
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            app.state.queue_manager.max_attempts = 3
            client = TestClient(app)
            created = client.post("/api/generate", data={"prompt": "bad request", "size": "1024x1024", "quality": "low", "n": "4"})
            task_id = created.json()["task"]["task_id"]

            with self.assertRaisesRegex(RuntimeError, "invalid_request_error"):
                asyncio.run(app.state.queue_manager.run_available_once())
            task = client.get(f"/api/tasks/{task_id}").json()["task"]
            queue_state = app.state.queue_storage.read_state()

        self.assertEqual(len(fake.generate_calls), 1)
        self.assertEqual(task["status"], "failed")
        self.assertIn("invalid_request_error", task["last_error"])
        self.assertEqual(queue_state["waiting"], [])
        self.assertEqual(queue_state["running"], {})
    def test_queue_worker_stops_after_failure_until_manual_retry(self) -> None:
        from codex_image.webui.app import create_app

        class FailsFirstThenSucceedsImageClient(FakeImageClient):
            def generate_image(self, **kwargs: Any):
                if not self.generate_calls:
                    self.generate_calls.append(kwargs)
                    raise RuntimeError("temporary server failure")
                return super().generate_image(**kwargs)

        fake = FailsFirstThenSucceedsImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                output_root=Path(tmp),
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            app.state.queue_manager.max_attempts = 2
            client = TestClient(app)
            created = client.post("/api/generate", data={"prompt": "manual retry only", "size": "1024x1024", "quality": "low"})
            task_id = created.json()["task"]["task_id"]

            with self.assertRaisesRegex(RuntimeError, "temporary server failure"):
                asyncio.run(app.state.queue_manager.run_available_once())
            failed = client.get(f"/api/tasks/{task_id}").json()["task"]
            stopped_queue = app.state.queue_storage.read_state()

            retry_response = client.post(f"/api/tasks/{task_id}/retry-failed")
            queued = retry_response.json()["task"]
            retry_queue = app.state.queue_storage.read_state()
            asyncio.run(app.state.queue_manager.run_available_once())
            completed = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertEqual(failed["status"], "failed")
        self.assertIn("temporary server failure", failed["last_error"])
        self.assertEqual(stopped_queue["waiting"], [])
        self.assertEqual(stopped_queue["running"], {})
        self.assertEqual(retry_response.status_code, 200)
        self.assertEqual(queued["status"], "queued")
        self.assertEqual(retry_queue["waiting"], [task_id])
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(len(fake.generate_calls), 2)
    def test_queue_worker_preserves_partial_outputs_when_usage_limit_stops_queue(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.queue import QueueChannel

        fake = QuotaLimitedAfterFirstImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root,
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            app.state.queue_manager.channels = [QueueChannel(channel_id="codex:local", auth_source="codex")]
            app.state.queue_manager.max_attempts = 3
            client = TestClient(app)
            created = client.post("/api/generate", data={"prompt": "many", "size": "1024x1024", "quality": "low", "n": "4"})
            task_id = created.json()["task"]["task_id"]

            with self.assertRaisesRegex(RuntimeError, "usage limit"):
                asyncio.run(app.state.queue_manager.run_available_once())
            failed_task = client.get(f"/api/tasks/{task_id}").json()["task"]
            queue_state = app.state.queue_storage.read_state()
            output_exists = (root / output_name(task_id, 1)).exists()

        self.assertEqual(failed_task["status"], "failed")
        self.assertEqual(failed_task["generated_count"], 1)
        self.assertEqual(failed_task["total_count"], 4)
        self.assertEqual(failed_task["output_urls"], [output_url(task_id, 1)])
        self.assertEqual(
            [(item["index"], item["status"]) for item in failed_task["outputs"]],
            [(1, "completed")],
        )
        self.assertEqual(queue_state["waiting"], [])
        self.assertTrue(output_exists)
    def test_queue_worker_continues_after_output_failures_without_retrying_slots(self) -> None:
        from codex_image.webui.app import create_app

        fake = FailsSecondImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root,
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            client = TestClient(app)
            created = client.post("/api/generate", data={"prompt": "many", "size": "1024x1024", "quality": "low", "n": "4"})
            task_id = created.json()["task"]["task_id"]

            asyncio.run(app.state.queue_manager.run_available_once())
            task = client.get(f"/api/tasks/{task_id}").json()["task"]
            output_files_exist = [(root / output_name(task_id, index)).exists() for index in (1, 2, 3, 4)]

        self.assertEqual(task["status"], "partial_failed")
        self.assertEqual(len(fake.generate_calls), 4)
        self.assertEqual(task["generated_count"], 2)
        self.assertEqual(task["failed_count"], 2)
        self.assertEqual(task["total_count"], 4)
        self.assertEqual(
            task["output_urls"],
            [output_url(task_id, 1), output_url(task_id, 4)],
        )
        self.assertEqual(
            [(item["index"], item["status"]) for item in task["outputs"]],
            [(1, "completed"), (2, "failed"), (3, "failed"), (4, "completed")],
        )
        self.assertIn("temporary server failure", task["outputs"][1]["error"])
        self.assertEqual(output_files_exist, [True, False, False, True])
    def test_queue_worker_times_out_single_output_and_runs_next_task(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.queue import QueueChannel

        fake = SlowFourthImageClient(delay_seconds=0.2)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {"CODEX_IMAGE_REQUEST_TIMEOUT_SECONDS": "0.12"}):
                app = create_app(
                    output_root=root,
                    client_factory=lambda: fake,
                    auth_checker=lambda: True,
                    batch_delay_seconds=0,
                    auto_start_queue=False,
                )
                app.state.queue_manager.channels = [QueueChannel(channel_id="codex:local", auth_source="codex")]
                client = TestClient(app)
                first = client.post(
                    "/api/generate",
                    data={"prompt": "four images", "size": "1024x1024", "quality": "low", "n": "4"},
                ).json()["task"]
                second = client.post(
                    "/api/generate",
                    data={"prompt": "next image", "size": "1024x1024", "quality": "low", "n": "1"},
                ).json()["task"]

                asyncio.run(app.state.queue_manager.run_available_once())
                asyncio.run(app.state.queue_manager.run_available_once())

                first_task = client.get(f"/api/tasks/{first['task_id']}").json()["task"]
                second_task = client.get(f"/api/tasks/{second['task_id']}").json()["task"]
                queue_state = app.state.queue_storage.read_state()
                output_files_exist = [(root / output_name(first["task_id"], index)).exists() for index in (1, 2, 3, 4)]

        self.assertEqual(first_task["status"], "partial_failed")
        self.assertEqual(first_task["generated_count"], 3)
        self.assertEqual(first_task["failed_count"], 1)
        self.assertEqual(first_task["total_count"], 4)
        self.assertIn("Image request timed out after 0.12s", first_task["last_error"])
        self.assertEqual(
            [(item["index"], item["status"]) for item in first_task["outputs"]],
            [(1, "completed"), (2, "completed"), (3, "completed"), (4, "failed")],
        )
        self.assertEqual(second_task["status"], "completed")
        self.assertEqual(queue_state["waiting"], [])
        self.assertEqual(queue_state["running"], {})
        self.assertEqual(output_files_exist, [True, True, True, False])
    def test_queue_worker_publishes_partial_outputs_while_running(self) -> None:
        from codex_image.webui.app import create_app

        fake = BlockingSecondImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root,
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            client = TestClient(app)
            created = client.post("/api/generate", data={"prompt": "many", "size": "1024x1024", "quality": "low", "n": "2"})
            task_id = created.json()["task"]["task_id"]

            worker_error: list[BaseException] = []

            def run_worker() -> None:
                try:
                    asyncio.run(app.state.queue_manager.run_available_once())
                except BaseException as exc:  # pragma: no cover - surfaced below
                    worker_error.append(exc)

            worker = threading.Thread(target=run_worker)
            worker.start()
            try:
                self.assertTrue(fake.second_call_started.wait(timeout=5))
                running = json.loads(metadata_path(root, task_id).read_text(encoding="utf-8"))

                self.assertEqual(running["status"], "running")
                self.assertEqual(running["generated_count"], 1)
                self.assertEqual(running["total_count"], 2)
                self.assertEqual(running["output_files"], [output_name(task_id)])
                self.assertEqual(running["output_urls"], [output_url(task_id)])
                self.assertEqual(running["revised_prompts"], ["revised-1"])
                self.assertTrue((root / output_name(task_id)).exists())
            finally:
                fake.release_second_call.set()
                worker.join(timeout=5)

            task = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertFalse(worker_error)
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["generated_count"], 2)
        self.assertEqual(task["total_count"], 2)
        self.assertEqual(task["revised_prompts"], ["revised-1", "revised-2"])
    def test_queue_manager_starts_one_task_per_channel(self) -> None:
        from codex_image.webui.queue import QueueChannel, QueueManager
        from codex_image.webui.storage import QueueStorage

        with tempfile.TemporaryDirectory() as tmp:
            queue_storage = QueueStorage(Path(tmp) / "queue.json")
            queue_storage.enqueue("task-a")
            queue_storage.enqueue("task-b")
            executor = QueueTestExecutor()
            manager = QueueManager(
                queue_storage=queue_storage,
                channels=[
                    QueueChannel(channel_id="api:slot-a", auth_source="api", account_id=None),
                    QueueChannel(channel_id="api:slot-b", auth_source="api", account_id=None),
                ],
                execute_task=executor,
            )

            asyncio.run(manager.run_available_once())

            state = queue_storage.read_state()

        self.assertEqual(executor.started, [("task-a", "api:slot-a"), ("task-b", "api:slot-b")])
        self.assertEqual(state["waiting"], [])
        self.assertEqual(state["running"], {})
    def test_queue_manager_channel_worker_can_start_while_another_channel_is_busy(self) -> None:
        from codex_image.webui.queue import QueueChannel, QueueManager
        from codex_image.webui.storage import QueueStorage

        with tempfile.TemporaryDirectory() as tmp:
            queue_storage = QueueStorage(Path(tmp) / "queue.json")
            queue_storage.enqueue("task-a")
            queue_storage.enqueue("task-b")
            channel_a = QueueChannel(channel_id="api:slot-a", auth_source="api", account_id=None)
            channel_b = QueueChannel(channel_id="api:slot-b", auth_source="api", account_id=None)
            executor = BlockingFirstQueueTestExecutor()
            manager = QueueManager(
                queue_storage=queue_storage,
                channels=[channel_a, channel_b],
                execute_task=executor,
            )

            async def run_workers() -> dict[str, Any]:
                executor.first_started = asyncio.Event()
                executor.release_first = asyncio.Event()
                first = asyncio.create_task(manager.run_channel_once(channel_a))
                await asyncio.wait_for(executor.first_started.wait(), timeout=1)
                second = asyncio.create_task(manager.run_channel_once(channel_b))
                await asyncio.wait_for(second, timeout=1)
                state_while_first_runs = queue_storage.read_state()
                executor.release_first.set()
                await asyncio.wait_for(first, timeout=1)
                return state_while_first_runs

            state_while_first_runs = asyncio.run(run_workers())
            final_state = queue_storage.read_state()

        self.assertEqual(executor.started, [("task-a", "api:slot-a"), ("task-b", "api:slot-b")])
        self.assertEqual(executor.completed, ["task-b", "task-a"])
        self.assertEqual(state_while_first_runs["waiting"], [])
        self.assertEqual(list(state_while_first_runs["running"]), ["api:slot-a"])
        self.assertEqual(final_state["running"], {})
    def test_queue_manager_requeues_failed_task_once_on_next_channel(self) -> None:
        from codex_image.webui.queue import QueueChannel, QueueManager
        from codex_image.webui.storage import QueueStorage

        with tempfile.TemporaryDirectory() as tmp:
            queue_storage = QueueStorage(Path(tmp) / "queue.json")
            queue_storage.enqueue("task-a")
            executor = QueueTestExecutor()
            executor.fail_once_for.add("task-a")
            manager = QueueManager(
                queue_storage=queue_storage,
                channels=[
                    QueueChannel(channel_id="api:slot-a", auth_source="api", account_id=None),
                    QueueChannel(channel_id="api:slot-b", auth_source="api", account_id=None),
                ],
                execute_task=executor,
                max_attempts=2,
            )

            with self.assertRaises(RuntimeError):
                asyncio.run(manager.run_available_once())
            asyncio.run(manager.run_available_once())

            state = queue_storage.read_state()

        self.assertEqual(executor.started, [("task-a", "api:slot-a"), ("task-a", "api:slot-b")])
        self.assertEqual(state["running"], {})
    def test_queue_manager_skips_unavailable_channel_when_alternative_exists(self) -> None:
        from codex_image.webui.queue import QueueChannel, QueueManager
        from codex_image.webui.storage import QueueStorage

        with tempfile.TemporaryDirectory() as tmp:
            queue_storage = QueueStorage(Path(tmp) / "queue.json")
            queue_storage.enqueue("task-a")
            executor = QueueTestExecutor()
            channel_a = QueueChannel(channel_id="api:slot-a", auth_source="api", account_id=None)
            channel_b = QueueChannel(channel_id="api:slot-b", auth_source="api", account_id=None)
            manager = QueueManager(
                queue_storage=queue_storage,
                channels=[channel_a, channel_b],
                execute_task=executor,
                channel_available=lambda channel: channel.channel_id != "api:slot-a",
            )

            asyncio.run(manager.run_available_once())
            state = queue_storage.read_state()

        self.assertEqual(executor.started, [("task-a", "api:slot-b")])
        self.assertEqual(state["waiting"], [])
        self.assertEqual(state["running"], {})
    def test_queue_manager_leaves_task_waiting_when_all_channels_unavailable(self) -> None:
        from codex_image.webui.queue import QueueChannel, QueueManager
        from codex_image.webui.storage import QueueStorage

        with tempfile.TemporaryDirectory() as tmp:
            queue_storage = QueueStorage(Path(tmp) / "queue.json")
            queue_storage.enqueue("task-a")
            executor = QueueTestExecutor()
            manager = QueueManager(
                queue_storage=queue_storage,
                channels=[QueueChannel(channel_id="api:slot-a", auth_source="api", account_id=None)],
                execute_task=executor,
                channel_available=lambda channel: False,
            )

            asyncio.run(manager.run_available_once())
            state = queue_storage.read_state()

        self.assertEqual(executor.started, [])
        self.assertEqual(state["waiting"], ["task-a"])
        self.assertEqual(state["running"], {})
    def test_queue_manager_retries_single_channel_when_no_alternative_available(self) -> None:
        from codex_image.webui.queue import QueueChannel, QueueManager
        from codex_image.webui.storage import QueueStorage

        with tempfile.TemporaryDirectory() as tmp:
            queue_storage = QueueStorage(Path(tmp) / "queue.json")
            queue_storage.enqueue("task-a")
            executor = QueueTestExecutor()
            executor.fail_once_for.add("task-a")
            manager = QueueManager(
                queue_storage=queue_storage,
                channels=[QueueChannel(channel_id="codex:local", auth_source="codex")],
                execute_task=executor,
                max_attempts=2,
            )

            with self.assertRaises(RuntimeError):
                asyncio.run(manager.run_available_once())
            asyncio.run(manager.run_available_once())

            state = queue_storage.read_state()

        self.assertEqual(executor.started, [("task-a", "codex:local"), ("task-a", "codex:local")])
        self.assertEqual(state["waiting"], [])
        self.assertEqual(state["running"], {})
    def test_queue_manager_marks_second_failure_as_final_attempt(self) -> None:
        from codex_image.webui.queue import QueueChannel, QueueManager
        from codex_image.webui.storage import QueueStorage

        with tempfile.TemporaryDirectory() as tmp:
            queue_storage = QueueStorage(Path(tmp) / "queue.json")
            queue_storage.enqueue("task-a")
            executor = AlwaysFailQueueTestExecutor()
            manager = QueueManager(
                queue_storage=queue_storage,
                channels=[
                    QueueChannel(channel_id="api:slot-a", auth_source="api", account_id=None),
                    QueueChannel(channel_id="api:slot-b", auth_source="api", account_id=None),
                ],
                execute_task=executor,
                max_attempts=2,
            )

            with self.assertRaises(RuntimeError):
                asyncio.run(manager.run_available_once())
            with self.assertRaises(RuntimeError):
                asyncio.run(manager.run_available_once())

            state = queue_storage.read_state()

        self.assertEqual(executor.final_attempts, [False, True])
        self.assertEqual(state["waiting"], [])
        self.assertEqual(state["running"], {})
    def test_queue_manager_waits_for_scheduled_jobs_before_reraising(self) -> None:
        from codex_image.webui.queue import QueueChannel, QueueManager
        from codex_image.webui.storage import QueueStorage

        with tempfile.TemporaryDirectory() as tmp:
            queue_storage = QueueStorage(Path(tmp) / "queue.json")
            queue_storage.enqueue("task-a")
            queue_storage.enqueue("task-b")
            executor = FailFastSlowCompleteQueueTestExecutor()
            manager = QueueManager(
                queue_storage=queue_storage,
                channels=[
                    QueueChannel(channel_id="api:slot-a", auth_source="api", account_id=None),
                    QueueChannel(channel_id="api:slot-b", auth_source="api", account_id=None),
                ],
                execute_task=executor,
            )

            with self.assertRaises(RuntimeError):
                asyncio.run(manager.run_available_once())

            state = queue_storage.read_state()

        self.assertEqual(executor.completed, ["task-b"])
        self.assertEqual(state["waiting"], ["task-a"])
        self.assertEqual(state["running"], {})
    def test_queue_manager_does_not_requeue_cancelled_task_on_shutdown(self) -> None:
        from codex_image.webui.queue import QueueChannel, QueueManager
        from codex_image.webui.storage import QueueStorage

        with tempfile.TemporaryDirectory() as tmp:
            queue_storage = QueueStorage(Path(tmp) / "queue.json")
            queue_storage.enqueue("task-a")
            manager = QueueManager(
                queue_storage=queue_storage,
                channels=[QueueChannel(channel_id="api:slot-a", auth_source="api", account_id=None)],
                execute_task=CancelQueueTestExecutor(),
            )

            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(manager.run_available_once())

            state = queue_storage.read_state()

        self.assertEqual(state["waiting"], [])
        self.assertEqual(state["running"], {})
        self.assertNotIn("task-a", manager.attempts)
        self.assertEqual(manager.failed_channels, {})
    def test_queue_recovery_fails_interrupted_running_task(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_id = "task-running"
            task_dir = root / task_id
            task_dir.mkdir()
            (task_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "created_at": "2026-05-01T00:00:00+00:00",
                        "updated_at": "2026-05-01T00:00:00+00:00",
                        "status": "running",
                        "prompt": "interrupted",
                        "params": {"size": "1024x1024"},
                    }
                ),
                encoding="utf-8",
            )
            queue_path = root / "queue.json"
            queue_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "waiting": [],
                        "running": {
                            "api:slot-a": {
                                "task_id": task_id,
                                "started_at": "2026-05-01T00:00:02+00:00",
                                "auth_source": "api",
                                "account_id": None,
                            }
                        },
                        "updated_at": "2026-05-01T00:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )

            app = create_app(output_root=root, queue_path=queue_path, auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)
            task = client.get(f"/api/tasks/{task_id}").json()["task"]
            queue = client.get("/api/queue").json()

        self.assertEqual(task["status"], "failed")
        self.assertIn("Service restarted", task["error"])
        self.assertEqual(queue["waiting"], [])
        self.assertEqual(queue["running"], [])
    def test_queue_worker_preserves_first_started_at_across_retry(self) -> None:
        from codex_image.webui.app import create_app

        class FailsFirstOutputAttemptThenSucceedsOnQueueRetryClient(FakeImageClient):
            def generate_image(self, **kwargs: Any):
                if not self.generate_calls:
                    self.generate_calls.append(kwargs)
                    raise RuntimeError("temporary stream failure")
                return super().generate_image(**kwargs)

        fake = FailsFirstOutputAttemptThenSucceedsOnQueueRetryClient()
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                output_root=Path(tmp),
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                auth_settings_path=Path(tmp) / "auth-settings.json",
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            client = TestClient(app)
            created = client.post("/api/generate", data={"prompt": "retry timer", "size": "1024x1024"})
            task_id = created.json()["task"]["task_id"]

            with self.assertRaises(RuntimeError):
                asyncio.run(app.state.queue_manager.run_available_once())
            failed_attempt = client.get(f"/api/tasks/{task_id}").json()["task"]
            time.sleep(0.001)
            retry_response = client.post(f"/api/tasks/{task_id}/retry-failed")
            asyncio.run(app.state.queue_manager.run_available_once())
            completed = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertEqual(retry_response.status_code, 200)
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["started_at"], failed_attempt["started_at"])
        self.assertIn("attempt_started_at", failed_attempt)
        self.assertIn("attempt_started_at", completed)
        self.assertNotEqual(completed["attempt_started_at"], failed_attempt["attempt_started_at"])
    def test_orphaned_running_task_is_reported_as_failed(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: FakeImageClient(), auth_checker=lambda: True)
            task = app.state.storage.create_task("generate")
            app.state.storage.write_metadata(
                task.task_id,
                {
                    "task_id": task.task_id,
                    "created_at": "2026-04-24T01:00:00+00:00",
                    "updated_at": "2026-04-24T01:00:00+00:00",
                    "mode": "generate",
                    "status": "running",
                    "prompt": "orphan",
                    "params": {"size": "1024x1024"},
                    "input_files": [],
                },
            )
            response = TestClient(app).get("/api/tasks")

        returned = response.json()["tasks"][0]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(returned["status"], "failed")
        self.assertIn("任务已中断", returned["error"])
    def test_queue_tracked_running_task_is_not_reported_as_orphaned(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: FakeImageClient(), auth_checker=lambda: True)
            task = app.state.storage.create_task("generate")
            app.state.storage.write_metadata(
                task.task_id,
                {
                    "task_id": task.task_id,
                    "created_at": "2026-04-24T01:00:00+00:00",
                    "updated_at": "2026-04-24T01:00:00+00:00",
                    "mode": "generate",
                    "status": "running",
                    "prompt": "tracked running",
                    "params": {"size": "1024x1024"},
                    "input_files": [],
                },
            )
            app.state.queue_storage.set_running("api:default", task.task_id, auth_source="api")
            client = TestClient(app)
            listed = client.get("/api/tasks").json()["tasks"][0]
            queued = client.get("/api/queue").json()["running"][0]

        self.assertEqual(listed["status"], "running")
        self.assertNotIn("orphaned_running", listed)
        self.assertEqual(queued["status"], "running")
        self.assertNotIn("orphaned_running", queued)
    def test_active_running_task_stays_running(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: FakeImageClient(), auth_checker=lambda: True)
            task = app.state.storage.create_task("generate")
            app.state.active_task_ids.add(task.task_id)
            app.state.storage.write_metadata(
                task.task_id,
                {
                    "task_id": task.task_id,
                    "created_at": "2026-04-24T01:00:00+00:00",
                    "updated_at": "2026-04-24T01:00:00+00:00",
                    "mode": "generate",
                    "status": "running",
                    "prompt": "active",
                    "params": {"size": "1024x1024"},
                    "input_files": [],
                },
            )
            response = TestClient(app).get("/api/tasks")

        returned = response.json()["tasks"][0]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(returned["status"], "running")
