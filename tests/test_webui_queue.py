from __future__ import annotations

import asyncio
import json
import os
import subprocess
import struct
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

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
    FailsFirstWithLegacyTimeoutImageClient,
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
    def _png_bytes(self) -> bytes:
        image = Image.new("RGB", (12, 8), (70, 120, 170))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def _cancel_testclient_background_task(
        self,
        task: asyncio.Task[Any],
    ) -> None:
        completed = threading.Event()
        loop = task.get_loop()
        loop.call_soon_threadsafe(task.add_done_callback, lambda _task: completed.set())
        loop.call_soon_threadsafe(task.cancel)
        self.assertTrue(completed.wait(2), "background task did not stop after cancellation")

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

    def test_queue_api_orders_running_tasks_by_claim_time_not_channel_id(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                output_root=Path(tmp),
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            task_ids: list[str] = []
            for started_at in (
                "2026-07-29T06:50:14+00:00",
                "2026-07-29T06:50:48+00:00",
                "2026-07-29T06:51:27+00:00",
            ):
                task = app.state.storage.create_task("generate")
                task_ids.append(task.task_id)
                app.state.storage.write_metadata(
                    task.task_id,
                    {
                        "task_id": task.task_id,
                        "created_at": started_at,
                        "updated_at": started_at,
                        "started_at": started_at,
                        "status": "running",
                        "mode": "generate",
                        "prompt": "stable running order",
                    },
                )
            app.state.active_task_ids.update(task_ids)
            app.state.queue_storage.write_state(
                {
                    "waiting": [],
                    "running": {
                        "provider:test:10": {
                            "task_id": task_ids[0],
                            "started_at": "2026-07-29T06:50:14+00:00",
                            "auth_source": "api",
                            "account_id": None,
                        },
                        "provider:test:4": {
                            "task_id": task_ids[2],
                            "started_at": "2026-07-29T06:51:27+00:00",
                            "auth_source": "api",
                            "account_id": None,
                        },
                        "provider:test:6": {
                            "task_id": task_ids[1],
                            "started_at": "2026-07-29T06:50:48+00:00",
                            "auth_source": "api",
                            "account_id": None,
                        },
                    },
                }
            )

            response = TestClient(app).get("/api/queue")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["task_id"] for item in response.json()["running"]],
            task_ids,
        )

    def test_queue_channel_worker_uses_capped_backoff_and_resets_sanitized_health(self) -> None:
        from codex_image.webui.context import QueueWorkerHealth
        from codex_image.webui.queue import QueueChannel
        from codex_image.webui.queue_runtime import _queue_channel_worker_loop
        from fastapi import FastAPI

        channel = QueueChannel(channel_id="provider:test:0", auth_source="api")

        class RepeatedFailureManager:
            channels = [channel]
            calls = 0

            async def run_channel_once(self, _channel: QueueChannel) -> bool:
                self.calls += 1
                if self.calls <= 7:
                    raise RuntimeError(
                        "secret prompt and /Users/example/private/output must not leak"
                    )
                return False

        app = FastAPI()
        app.state.queue_manager = RepeatedFailureManager()
        app.state.queue_worker_health = QueueWorkerHealth()
        delays: list[float] = []
        snapshots: list[tuple[str, int, str | None]] = []

        async def sleeper(delay: float) -> None:
            delays.append(delay)
            health = app.state.queue_worker_health
            snapshots.append(
                (
                    health.status,
                    health.consecutive_failures,
                    health.last_error_type,
                )
            )
            if len(delays) == 8:
                await asyncio.Event().wait()
            await asyncio.sleep(0)

        async def run_worker() -> None:
            await _queue_channel_worker_loop(
                app,
                channel.channel_id,
                sleeper=sleeper,
            )

        with self.assertLogs("codex_image.webui.queue_runtime", level="ERROR") as logs:
            asyncio.run(asyncio.wait_for(run_worker(), timeout=0.2))

        self.assertEqual(delays, [0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0])
        self.assertEqual(snapshots[0], ("degraded", 1, "RuntimeError"))
        self.assertEqual(snapshots[2], ("unhealthy", 3, "RuntimeError"))
        self.assertEqual(app.state.queue_worker_health.snapshot()["status"], "healthy")
        log_text = "\n".join(logs.output)
        self.assertIn("provider:test:0", log_text)
        self.assertIn("RuntimeError", log_text)
        self.assertNotIn("secret prompt", log_text)
        self.assertNotIn("/Users/example/private/output", log_text)

    def test_queue_task_failures_log_safe_context_without_degrading_worker_health(self) -> None:
        from codex_image.webui.context import QueueWorkerHealth
        from codex_image.webui.queue import NonRetryableTaskError, QueueChannel, QueueManager
        from codex_image.webui.queue_runtime import _queue_channel_worker_loop
        from codex_image.webui.storage import QueueStorage
        from fastapi import FastAPI

        cases = (
            (RuntimeError("secret prompt at /Users/example/private/output"), "task_execution_failed", "true"),
            (NonRetryableTaskError("secret prompt at /Users/example/private/output"), "invalid_parameters", "false"),
        )
        for failure, expected_code, expected_retryable in cases:
            with self.subTest(expected_code=expected_code), tempfile.TemporaryDirectory() as tmp:
                if isinstance(failure, NonRetryableTaskError):
                    failure.error_code = expected_code
                storage = QueueStorage(Path(tmp) / "queue.json")
                storage.enqueue("task-a")
                channel = QueueChannel(channel_id="provider:test:0", auth_source="api")

                async def fail_task(
                    _task_id: str,
                    _channel: QueueChannel,
                    _is_final_attempt: bool,
                    *,
                    task_failure: Exception = failure,
                ) -> None:
                    raise task_failure

                manager = QueueManager(
                    queue_storage=storage,
                    channels=[channel],
                    execute_task=fail_task,
                    auto_retry=False,
                )
                app = FastAPI()
                app.state.queue_manager = manager
                app.state.queue_worker_health = QueueWorkerHealth()
                delays: list[float] = []
                health_snapshots: list[dict[str, Any]] = []

                async def sleeper(delay: float) -> None:
                    delays.append(delay)
                    health_snapshots.append(app.state.queue_worker_health.snapshot())
                    await asyncio.sleep(0)

                with self.assertLogs("codex_image.webui.queue_runtime", level="WARNING") as logs:
                    asyncio.run(
                        _queue_channel_worker_loop(
                            app,
                            channel.channel_id,
                            sleeper=sleeper,
                        )
                    )

                self.assertEqual(delays, [0.5])
                self.assertTrue(health_snapshots)
                self.assertTrue(all(item["status"] == "healthy" for item in health_snapshots))
                log_text = "\n".join(logs.output)
                self.assertIn("Queue task failure", log_text)
                self.assertIn("task_id=task-a", log_text)
                self.assertIn(f"error_code={expected_code}", log_text)
                self.assertIn(f"retryable={expected_retryable}", log_text)
                self.assertNotIn("Queue channel worker failure", log_text)
                self.assertNotIn("secret prompt", log_text)
                self.assertNotIn("/Users/example/private/output", log_text)

    def test_queue_channel_worker_returns_immediately_when_channel_is_idle(self) -> None:
        from codex_image.webui.queue import QueueChannel
        from codex_image.webui.queue_runtime import _queue_channel_worker_loop
        from fastapi import FastAPI

        channel = QueueChannel(channel_id="provider:test:0", auth_source="api")

        class IdleManager:
            channels = [channel]
            calls = 0

            async def run_channel_once(self, _channel: QueueChannel) -> bool:
                self.calls += 1
                return False

        app = FastAPI()
        app.state.queue_manager = IdleManager()

        async def forbidden_idle_sleep(_delay: float) -> None:
            raise AssertionError("An idle channel worker must stop instead of polling")

        asyncio.run(
            _queue_channel_worker_loop(
                app,
                channel.channel_id,
                sleeper=forbidden_idle_sleep,
            )
        )

        self.assertEqual(app.state.queue_manager.calls, 1)

    def test_queue_supervisor_stays_dormant_with_many_channels_and_an_empty_queue(self) -> None:
        from codex_image.webui.queue import QueueChannel
        from codex_image.webui.queue_runtime import _queue_worker_loop
        from fastapi import FastAPI

        class EmptyQueueStorage:
            def __init__(self) -> None:
                self.reads = 0
                self.inspected: asyncio.Event | None = None

            def read_state(self) -> dict[str, Any]:
                self.reads += 1
                if self.inspected is not None:
                    self.inspected.set()
                return {"waiting": [], "running": {}}

        class CountingManager:
            def __init__(self, storage: EmptyQueueStorage) -> None:
                self.queue_storage = storage
                self.channels = [
                    QueueChannel(
                        channel_id=f"provider:test:{index}",
                        auth_source="api",
                        provider_id="test",
                        slot_index=index,
                    )
                    for index in range(200)
                ]
                self.calls: list[str] = []

            async def run_channel_once(self, channel: QueueChannel) -> bool:
                self.calls.append(channel.channel_id)
                return False

        async def scenario() -> tuple[int, list[str]]:
            app = FastAPI()
            storage = EmptyQueueStorage()
            storage.inspected = asyncio.Event()
            app.state.queue_storage = storage
            app.state.queue_manager = CountingManager(storage)
            app.state.queue_wakeup_event = asyncio.Event()
            app.state.queue_wakeup_event.set()
            worker = asyncio.create_task(_queue_worker_loop(app))
            try:
                await asyncio.wait_for(storage.inspected.wait(), timeout=1)
                reads_after_idle = storage.reads
                for _ in range(10):
                    await asyncio.sleep(0)
                self.assertEqual(storage.reads, reads_after_idle)
                return storage.reads, app.state.queue_manager.calls
            finally:
                worker.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await worker

        reads, calls = asyncio.run(scenario())

        self.assertEqual(reads, 1)
        self.assertEqual(calls, [])

    def test_queue_supervisor_processes_an_explicit_wakeup_without_idle_polling(self) -> None:
        from codex_image.webui.queue import QueueChannel
        from codex_image.webui.queue_runtime import _queue_worker_loop
        from fastapi import FastAPI

        channel = QueueChannel(
            channel_id="provider:needed:0",
            auth_source="api",
            provider_id="needed",
        )

        class MutableQueueStorage:
            def __init__(self) -> None:
                self.waiting: list[str] = []
                self.reads = 0
                self.inspected = asyncio.Event()

            def read_state(self) -> dict[str, Any]:
                self.reads += 1
                self.inspected.set()
                return {"waiting": list(self.waiting), "running": {}}

        class WakeableManager:
            def __init__(self, storage: MutableQueueStorage) -> None:
                self.queue_storage = storage
                self.channels = [channel]
                self.started = asyncio.Event()
                self.calls = 0

            async def run_channel_once(self, _channel: QueueChannel) -> bool:
                self.calls += 1
                self.started.set()
                self.queue_storage.waiting.clear()
                return False

        async def scenario() -> tuple[int, int]:
            app = FastAPI()
            storage = MutableQueueStorage()
            manager = WakeableManager(storage)
            app.state.queue_storage = storage
            app.state.queue_manager = manager
            app.state.queue_wakeup_event = asyncio.Event()
            app.state.queue_wakeup_event.set()
            worker = asyncio.create_task(_queue_worker_loop(app))
            try:
                await asyncio.wait_for(storage.inspected.wait(), timeout=1)
                storage.inspected.clear()
                storage.waiting.append("task-a")
                app.state.queue_wakeup_event.set()
                await asyncio.wait_for(manager.started.wait(), timeout=1)
                await asyncio.wait_for(storage.inspected.wait(), timeout=1)
                reads_after_drain = storage.reads
                for _ in range(10):
                    await asyncio.sleep(0)
                self.assertEqual(storage.reads, reads_after_drain)
                return storage.reads, manager.calls
            finally:
                worker.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await worker

        reads, calls = asyncio.run(scenario())

        self.assertEqual(reads, 2)
        self.assertEqual(calls, 1)

    def test_queue_supervisor_retries_a_transient_state_read_without_polling_after_recovery(self) -> None:
        from codex_image.webui.context import QueueWorkerHealth
        from codex_image.webui.queue_runtime import _queue_worker_loop
        from fastapi import FastAPI

        class FlakyQueueStorage:
            def __init__(self) -> None:
                self.reads = 0
                self.recovered = asyncio.Event()

            def read_state(self) -> dict[str, Any]:
                self.reads += 1
                if self.reads == 1:
                    raise OSError("temporary queue read failure")
                self.recovered.set()
                return {"waiting": [], "running": {}}

        class EmptyManager:
            channels: list[Any] = []

        async def scenario() -> tuple[list[float], dict[str, Any], int]:
            app = FastAPI()
            storage = FlakyQueueStorage()
            app.state.queue_storage = storage
            app.state.queue_manager = EmptyManager()
            app.state.queue_worker_health = QueueWorkerHealth()
            app.state.queue_wakeup_event = asyncio.Event()
            app.state.queue_wakeup_event.set()
            delays: list[float] = []

            async def sleeper(delay: float) -> None:
                delays.append(delay)
                await asyncio.sleep(0)

            worker = asyncio.create_task(
                _queue_worker_loop(app, sleeper=sleeper)
            )
            try:
                await asyncio.wait_for(storage.recovered.wait(), timeout=1)
                reads_after_recovery = storage.reads
                for _ in range(10):
                    await asyncio.sleep(0)
                self.assertEqual(storage.reads, reads_after_recovery)
                return (
                    delays,
                    app.state.queue_worker_health.snapshot(),
                    storage.reads,
                )
            finally:
                worker.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await worker

        with self.assertLogs(
            "codex_image.webui.queue_runtime",
            level="ERROR",
        ) as logs:
            delays, health, reads = asyncio.run(scenario())

        self.assertEqual(delays, [0.5])
        self.assertEqual(health["status"], "healthy")
        self.assertEqual(reads, 2)
        self.assertNotIn("temporary queue read failure", "\n".join(logs.output))

    def test_queue_channels_with_pending_only_materializes_required_snapshot_providers(self) -> None:
        from types import SimpleNamespace

        from codex_image.webui.queue_runtime import _queue_channels_with_pending

        class QueueState:
            def read_state(self) -> dict[str, Any]:
                return {
                    "waiting": ["task-waiting"],
                    "running": {
                        "provider:running-only:1": {
                            "task_id": "task-running",
                            "auth_source": "api",
                            "account_id": None,
                        }
                    },
                }

        class MetadataStorage:
            def read_metadata(self, task_id: str) -> dict[str, Any]:
                if task_id == "task-waiting":
                    return {
                        "generation_snapshot": {
                            "provider_id": "needed",
                            "provider_concurrency": 2,
                        }
                    }
                if task_id == "task-running":
                    return {
                        "generation_snapshot": {
                            "provider_id": "running-only",
                            "provider_concurrency": 2,
                        }
                    }
                raise FileNotFoundError(task_id)

        class ApiSettings:
            def read_connections(self) -> list[Any]:
                return [
                    SimpleNamespace(id="needed", concurrency=2),
                    SimpleNamespace(id="unrelated-a", concurrency=20),
                    SimpleNamespace(id="unrelated-b", concurrency=20),
                ]

        ctx = SimpleNamespace(
            queue_storage=QueueState(),
            storage=MetadataStorage(),
            api_settings=ApiSettings(),
        )

        channels = _queue_channels_with_pending(ctx, "api")

        self.assertEqual(
            {channel.channel_id for channel in channels},
            {
                "provider:needed:0",
                "provider:needed:1",
                "provider:running-only:0",
                "provider:running-only:1",
            },
        )

    def test_queue_manager_channel_claim_reads_queue_state_once(self) -> None:
        from codex_image.webui.queue import QueueChannel, QueueManager

        class CountingStorage:
            def __init__(self) -> None:
                self.reads = 0
                self.cleared: list[str] = []

            def read_state(self) -> dict[str, Any]:
                self.reads += 1
                return {"waiting": ["task-a"], "running": {}}

            def claim_waiting(
                self,
                task_id: str,
                channel_id: str,
                *,
                auth_source: str,
                account_id: str | None = None,
            ) -> bool:
                return task_id == "task-a" and channel_id == "provider:test:0"

            def clear_running(self, channel_id: str) -> None:
                self.cleared.append(channel_id)

        storage = CountingStorage()
        channel = QueueChannel(
            channel_id="provider:test:0",
            auth_source="api",
            provider_id="test",
        )

        async def execute_task(
            _task_id: str,
            _channel: QueueChannel,
            _is_final_attempt: bool,
        ) -> None:
            return None

        manager = QueueManager(
            queue_storage=storage,  # type: ignore[arg-type]
            channels=[channel],
            execute_task=execute_task,
        )

        started = asyncio.run(manager.run_channel_once(channel))

        self.assertTrue(started)
        self.assertEqual(storage.reads, 1)
        self.assertEqual(storage.cleared, [channel.channel_id])

    def test_queue_api_restarts_stopped_background_worker(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: FakeImageClient(), auth_checker=lambda: True)
            with TestClient(app) as client:
                original_worker = app.state.queue_worker_task
                self._cancel_testclient_background_task(original_worker)

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
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                    "completed_at": datetime.now(UTC).isoformat(),
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
                self._cancel_testclient_background_task(original_worker)

                response = client.get("/api/events")
                restarted_worker = app.state.queue_worker_task
                self.assertIsNot(restarted_worker, original_worker)
                self.assertFalse(restarted_worker.done())

        self.assertEqual(response.status_code, 200)

    def test_queue_event_embeds_finished_tasks_for_terminal_realtime_update(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.events import queue_event, task_events

        task_id = "20260630101010-timeout"
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            app.state.storage.write_metadata(
                task_id,
                {
                    "task_id": task_id,
                    "created_at": "2026-06-30T10:10:10+00:00",
                    "updated_at": "2026-06-30T10:20:10+00:00",
                    "status": "failed",
                    "prompt": "timeout task",
                    "size": "1024x1024",
                    "error": "Image request timed out after 600s",
                },
            )

            finished_events = task_events(app.state.ctx, {task_id})
            payload = queue_event(
                {"waiting": [], "running": [], "summary": {"waiting_count": 0, "running_count": 0, "channel_count": 1}},
                finished_events,
            )

        self.assertEqual(payload["type"], "queue")
        self.assertEqual(payload["queue"]["summary"]["running_count"], 0)
        self.assertEqual(payload["tasks"][0]["task_id"], task_id)
        self.assertEqual(payload["tasks"][0]["status"], "failed")
        self.assertIn("timed out", payload["tasks"][0]["error"])

    def test_create_app_uses_sqlite_queue_storage_by_default(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.storage import SQLiteQueueStorage

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), auth_checker=lambda: True, auto_start_queue=False)

        self.assertIsInstance(app.state.queue_storage, SQLiteQueueStorage)

    def test_single_instance_lock_rejects_second_process_for_same_data_root(self) -> None:
        from codex_image.webui.instance_lock import WebUIInstanceLock

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source-data"
            lock = WebUIInstanceLock.acquire(root)
            try:
                script = """
import sys
from pathlib import Path
from codex_image.webui.instance_lock import WebUIAlreadyRunningError, WebUIInstanceLock

try:
    WebUIInstanceLock.acquire(Path(sys.argv[1]))
except WebUIAlreadyRunningError:
    raise SystemExit(0)
raise SystemExit(1)
"""
                result = subprocess.run(
                    [sys.executable, "-c", script, str(root)],
                    cwd=Path.cwd(),
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
            finally:
                lock.release()

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_create_app_single_instance_rejects_before_queue_recovery(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.instance_lock import WebUIAlreadyRunningError

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = create_app(
                output_root=root / "outputs",
                source_data_root=root / "outputs" / "source-data",
                auth_checker=lambda: True,
                auto_start_queue=False,
                enforce_single_instance=True,
            )
            try:
                with patch("codex_image.webui.app._recover_queue_state") as recovery:
                    with self.assertRaises(WebUIAlreadyRunningError):
                        create_app(
                            output_root=root / "outputs",
                            source_data_root=root / "outputs" / "source-data",
                            auth_checker=lambda: True,
                            auto_start_queue=False,
                            enforce_single_instance=True,
                        )
                    recovery.assert_not_called()
            finally:
                first.state.webui_instance_lock.release()

    def test_create_app_rejects_multi_worker_environment_before_recovery(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.instance_lock import WebUIWorkerConfigurationError

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.dict(os.environ, {"WEB_CONCURRENCY": "2"}),
                patch("codex_image.webui.app._recover_queue_state") as recovery,
            ):
                with self.assertRaises(WebUIWorkerConfigurationError):
                    create_app(
                        output_root=root / "outputs",
                        source_data_root=root / "outputs" / "source-data",
                        auth_checker=lambda: True,
                        auto_start_queue=False,
                        enforce_single_instance=True,
                    )
                recovery.assert_not_called()

    def test_single_instance_lock_is_released_after_lifespan_shutdown(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.instance_lock import WebUIInstanceLock

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_data_root = root / "outputs" / "source-data"
            app = create_app(
                output_root=root / "outputs",
                source_data_root=source_data_root,
                auth_checker=lambda: True,
                auto_start_queue=False,
                enforce_single_instance=True,
            )
            with TestClient(app) as client:
                self.assertEqual(client.get("/api/health").status_code, 200)

            reacquired = WebUIInstanceLock.acquire(source_data_root)
            reacquired.release()

    def test_single_instance_lock_is_released_when_app_construction_fails(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.instance_lock import WebUIInstanceLock

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_data_root = root / "outputs" / "source-data"
            with patch(
                "codex_image.webui.app._migrate_legacy_gallery_directory",
                side_effect=RuntimeError("construction failed"),
            ):
                with self.assertRaisesRegex(RuntimeError, "construction failed"):
                    create_app(
                        output_root=root / "outputs",
                        source_data_root=source_data_root,
                        auth_checker=lambda: True,
                        auto_start_queue=False,
                        enforce_single_instance=True,
                    )

            reacquired = WebUIInstanceLock.acquire(source_data_root)
            reacquired.release()
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
                api_settings_path=Path(tmp) / "api-settings.json",
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
    def test_queue_cancel_running_task_keeps_channel_until_provider_returns(self) -> None:
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
                    self.assertFalse(fake.second_call_started.wait(timeout=0.2))
                    pending = client.get(f"/api/tasks/{first['task_id']}").json()["task"]
                    pending_queue = client.get("/api/queue").json()
                finally:
                    fake.release_first_call.set()
                self.assertTrue(fake.second_call_started.wait(timeout=3))
                for _ in range(100):
                    cancelled = client.get(f"/api/tasks/{first['task_id']}").json()["task"]
                    if cancelled.get("cancelled_at"):
                        break
                    time.sleep(0.02)
                next_task = client.get(f"/api/tasks/{second['task_id']}").json()["task"]

        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()["cancellation_pending"])
        self.assertEqual(pending["status"], "cancelling")
        self.assertTrue(pending["cancel_requested"])
        self.assertNotIn("cancelled_at", pending)
        self.assertTrue(any(task["task_id"] == first["task_id"] for task in pending_queue["running"]))
        self.assertEqual(cancelled["status"], "failed")
        self.assertTrue(cancelled["cancel_requested"])
        self.assertIn(next_task["status"], {"running", "completed"})

    def test_queue_cancel_running_fourth_slot_waits_for_inflight_slot_before_next_task(self) -> None:
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
                    self.assertFalse(fake.second_task_started.wait(timeout=0.2))
                    pending = client.get(f"/api/tasks/{first['task_id']}").json()["task"]
                    pending_queue = client.get("/api/queue").json()
                finally:
                    fake.release_fourth_call.set()
                self.assertTrue(fake.second_task_started.wait(timeout=3))
                for _ in range(100):
                    cancelled = client.get(f"/api/tasks/{first['task_id']}").json()["task"]
                    if cancelled.get("cancelled_at"):
                        break
                    time.sleep(0.02)
                next_task = client.get(f"/api/tasks/{second['task_id']}").json()["task"]
                queue = client.get("/api/queue").json()

        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()["cancellation_pending"])
        self.assertEqual(pending["status"], "cancelling")
        self.assertNotIn("cancelled_at", pending)
        self.assertTrue(any(task["task_id"] == first["task_id"] for task in pending_queue["running"]))
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

    def test_startup_recovery_does_not_rewrite_unchanged_terminal_task_index(self) -> None:
        from codex_image.webui.recovery import _recover_queue_state
        from codex_image.webui.storage import SQLiteQueueStorage, TaskStorage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = TaskStorage(root)
            for index in range(3):
                task = storage.create_task("generate")
                storage.write_metadata(
                    task.task_id,
                    {
                        "task_id": task.task_id,
                        "created_at": f"2026-07-29T10:00:0{index}+00:00",
                        "updated_at": f"2026-07-29T10:01:0{index}+00:00",
                        "status": "completed",
                        "prompt": f"completed task {index}",
                    },
                )
            queue_storage = SQLiteQueueStorage(
                storage.source_data_root / "webui.db"
            )

            with patch.object(
                storage.task_index,
                "upsert",
                wraps=storage.task_index.upsert,
            ) as upsert:
                _recover_queue_state(storage, queue_storage)

        upsert.assert_not_called()

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
                    "images": ("input.png", self._png_bytes(), "image/png"),
                    "mask": ("mask.png", self._png_bytes(), "image/png"),
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
            created = client.post(
                "/api/generate",
                data={"prompt": "bad request", "size": "1024x1024", "quality": "low", "n": "4", "codex_mode": "responses"},
            )
            task_id = created.json()["task"]["task_id"]

            with self.assertRaisesRegex(RuntimeError, "invalid_request_error") as raised:
                asyncio.run(app.state.queue_manager.run_available_once())
            task = client.get(f"/api/tasks/{task_id}").json()["task"]
            queue_state = app.state.queue_storage.read_state()

        self.assertEqual(len(fake.generate_calls), 1)
        self.assertEqual(task["status"], "failed")
        self.assertIn("invalid_request_error", task["last_error"])
        self.assertEqual(queue_state["waiting"], [])
        self.assertEqual(queue_state["running"], {})
        self.assertEqual(getattr(raised.exception, "task_id", None), task_id)
        self.assertEqual(getattr(raised.exception, "error_code", None), "invalid_parameters")
        self.assertFalse(getattr(raised.exception, "retryable", True))
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

            with self.assertRaisesRegex(RuntimeError, "temporary server failure") as raised:
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
        self.assertEqual(getattr(raised.exception, "task_id", None), task_id)
        self.assertEqual(getattr(raised.exception, "error_code", None), "upstream_error")
        self.assertTrue(getattr(raised.exception, "retryable", False))
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
            created = client.post(
                "/api/generate",
                data={"prompt": "many", "size": "1024x1024", "quality": "low", "n": "4", "codex_mode": "responses"},
            )
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

        completed_indices = [item["index"] for item in task["outputs"] if item["status"] == "completed"]
        failed_outputs = [item for item in task["outputs"] if item["status"] == "failed"]
        self.assertEqual(task["status"], "partial_failed")
        self.assertEqual(len(fake.generate_calls), 4)
        self.assertEqual(task["generated_count"], 2)
        self.assertEqual(task["failed_count"], 2)
        self.assertEqual(task["total_count"], 4)
        self.assertEqual(
            task["output_urls"],
            [output_url(task_id, index) for index in completed_indices],
        )
        self.assertEqual(
            [item["index"] for item in task["outputs"]],
            [1, 2, 3, 4],
        )
        self.assertEqual(len(failed_outputs), 2)
        self.assertTrue(all("temporary server failure" in item["error"] for item in failed_outputs))
        self.assertEqual(output_files_exist, [index in completed_indices for index in (1, 2, 3, 4)])

    def test_queue_worker_records_elapsed_for_fast_legacy_timeout_message(self) -> None:
        from codex_image.webui.app import create_app

        fake = FailsFirstWithLegacyTimeoutImageClient()
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

            asyncio.run(app.state.queue_manager.run_available_once())
            task = client.get(f"/api/tasks/{task_id}").json()["task"]

        failed = task["outputs"][0]
        self.assertEqual(task["status"], "partial_failed")
        self.assertIn("timeout limit 600s", failed["error"])
        self.assertIn("failed after", failed["error"])
        self.assertNotEqual(failed["error"], "Image request timed out after 600s")
        self.assertIsInstance(failed["elapsed_seconds"], float)
        self.assertGreaterEqual(failed["elapsed_seconds"], 0)
        self.assertEqual(task["outputs"][1]["status"], "completed")

    def test_queue_worker_times_out_single_output_and_runs_next_task(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.queue import QueueChannel

        fake = SlowFourthImageClient(delay_seconds=2)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {"CODEX_IMAGE_REQUEST_TIMEOUT_SECONDS": "1"}):
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
        self.assertIn("Image request timed out after ", first_task["last_error"])
        self.assertIn("timeout limit 1s", first_task["last_error"])
        self.assertEqual(
            [(item["index"], item["status"]) for item in first_task["outputs"]],
            [(1, "completed"), (2, "completed"), (3, "completed"), (4, "failed")],
        )
        self.assertEqual(second_task["status"], "completed")
        self.assertEqual(queue_state["waiting"], [])
        self.assertEqual(queue_state["running"], {})
        self.assertEqual(output_files_exist, [True, True, True, False])

    def test_call_image_client_preserves_inner_timeout_error(self) -> None:
        from codex_image.webui.executor_transport import _call_image_client

        def fail_with_http_timeout() -> object:
            raise TimeoutError("HTTP request timed out after 0.2s (timeout limit 600s)")

        async def run_call() -> None:
            await _call_image_client(None, {}, fail_with_http_timeout, timeout_seconds=600)

        with self.assertRaisesRegex(TimeoutError, "HTTP request timed out after 0.2s"):
            asyncio.run(run_call())

    def test_call_image_client_timeout_waits_for_synchronous_call_to_exit(self) -> None:
        from codex_image.webui.executor_transport import _call_image_client

        call_finished = threading.Event()

        def slow_call() -> object:
            time.sleep(0.08)
            call_finished.set()
            return object()

        async def run_call() -> None:
            await _call_image_client(None, {}, slow_call, timeout_seconds=0.01)

        started_at = time.monotonic()
        with self.assertRaisesRegex(TimeoutError, "timeout limit 0.01s"):
            asyncio.run(run_call())
        elapsed = time.monotonic() - started_at

        self.assertTrue(call_finished.is_set())
        self.assertGreaterEqual(elapsed, 0.07)

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
            created = client.post(
                "/api/generate",
                data={"prompt": "many", "size": "1024x1024", "quality": "low", "n": "2", "codex_mode": "responses"},
            )
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

    def test_queue_manager_requeues_external_cancellation_without_consuming_attempt(self) -> None:
        from codex_image.webui.queue import QueueChannel, QueueManager
        from codex_image.webui.storage import QueueStorage

        with tempfile.TemporaryDirectory() as tmp:
            queue_storage = QueueStorage(Path(tmp) / "queue.json")
            queue_storage.enqueue("task-a")
            manager = QueueManager(
                queue_storage=queue_storage,
                channels=[QueueChannel(channel_id="api:slot-a", auth_source="api")],
                execute_task=CancelQueueTestExecutor(),
                should_requeue_cancelled=lambda _task_id: True,
            )

            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(manager.run_available_once())

            state = queue_storage.read_state()

        self.assertEqual(state["waiting"], ["task-a"])
        self.assertEqual(state["running"], {})
        self.assertNotIn("task-a", manager.attempts)

    def test_runtime_shutdown_requeues_inflight_task_and_preserves_it_on_restart(self) -> None:
        from codex_image.webui.app import create_app

        fake = BlockingFirstImageClient()
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
            task_id = client.post(
                "/api/generate",
                data={"prompt": "shutdown recovery", "size": "1024x1024"},
            ).json()["task"]["task_id"]

            async def cancel_running_worker() -> None:
                worker = asyncio.create_task(app.state.queue_manager.run_available_once())
                started = await asyncio.to_thread(fake.first_call_started.wait, 2)
                self.assertTrue(started)
                worker.cancel()
                try:
                    with self.assertRaises(asyncio.CancelledError):
                        await worker
                finally:
                    fake.release_first_call.set()

            asyncio.run(cancel_running_worker())

            queued = app.state.storage.read_metadata(task_id)
            queue_state = app.state.queue_storage.read_state()
            restarted = create_app(
                output_root=root,
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            recovered = restarted.state.storage.read_metadata(task_id)
            recovered_queue = restarted.state.queue_storage.read_state()

        self.assertEqual(queued["status"], "queued")
        self.assertEqual(queued["attempts"], 0)
        self.assertEqual(queue_state["waiting"], [task_id])
        self.assertEqual(recovered["status"], "queued")
        self.assertEqual(recovered_queue["waiting"], [task_id])
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
    def test_queue_snapshot_prunes_running_tasks_from_inactive_response_channels(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.settings_store import ApiSettings, AuthSettings

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth_settings_path = root / "auth-settings.json"
            api_settings_path = root / "api-settings.json"
            AuthSettings(auth_settings_path).write_source("api")
            ApiSettings(api_settings_path).write(
                {
                    "base_url": "https://api.example.com/v1",
                    "api_key": "test-api-key-responses-secret",
                    "image_model": "gpt-image-2",
                    "api_mode": "responses",
                    "images_concurrency": 4,
                }
            )
            app = create_app(
                output_root=root / "tasks",
                auth_settings_path=auth_settings_path,
                api_settings_path=api_settings_path,
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            task = app.state.storage.create_task("generate")
            app.state.storage.write_metadata(
                task.task_id,
                {
                    "task_id": task.task_id,
                    "created_at": "2026-07-09T09:00:00+00:00",
                    "updated_at": "2026-07-09T09:00:00+00:00",
                    "started_at": "2026-07-09T09:00:00+00:00",
                    "mode": "generate",
                    "status": "running",
                    "prompt": "stale responses channel",
                    "params": {"api_mode": "responses", "api_images_concurrency": 4},
                    "requested_backend": "openai_responses",
                    "backend": "openai_responses",
                    "input_files": [],
                },
            )
            app.state.queue_storage.write_state(
                {
                    "waiting": [],
                    "running": {
                        "api:default:5": {
                            "task_id": task.task_id,
                            "started_at": "2026-07-09T09:00:00+00:00",
                            "auth_source": "api",
                            "account_id": None,
                        }
                    },
                }
            )

            response = TestClient(app).get("/api/queue")
            queue_state = app.state.queue_storage.read_state()
            metadata = app.state.storage.read_metadata(task.task_id)

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["summary"]["channel_count"], 4)
        self.assertEqual(payload["running"], [])
        self.assertEqual(queue_state["running"], {})
        self.assertEqual(metadata["status"], "failed")
        self.assertEqual(metadata["error"], "Service restarted before this task completed.")
    def test_queue_snapshot_keeps_active_task_on_inactive_channel(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.settings_store import ApiSettings, AuthSettings

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth_settings_path = root / "auth-settings.json"
            api_settings_path = root / "api-settings.json"
            AuthSettings(auth_settings_path).write_source("api")
            ApiSettings(api_settings_path).write(
                {
                    "base_url": "https://api.example.com/v1",
                    "api_key": "test-api-key-responses-secret",
                    "image_model": "gpt-image-2",
                    "api_mode": "responses",
                    "images_concurrency": 4,
                }
            )
            app = create_app(
                output_root=root / "tasks",
                auth_settings_path=auth_settings_path,
                api_settings_path=api_settings_path,
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            task = app.state.storage.create_task("generate")
            app.state.active_task_ids.add(task.task_id)
            app.state.storage.write_metadata(
                task.task_id,
                {
                    "task_id": task.task_id,
                    "created_at": "2026-07-09T09:00:00+00:00",
                    "updated_at": "2026-07-09T09:00:00+00:00",
                    "started_at": "2026-07-09T09:00:00+00:00",
                    "mode": "generate",
                    "status": "running",
                    "prompt": "active responses channel",
                    "params": {"api_mode": "responses", "api_images_concurrency": 4},
                    "requested_backend": "openai_responses",
                    "backend": "openai_responses",
                    "input_files": [],
                },
            )
            app.state.queue_storage.write_state(
                {
                    "waiting": [],
                    "running": {
                        "api:default:5": {
                            "task_id": task.task_id,
                            "started_at": "2026-07-09T09:00:00+00:00",
                            "auth_source": "api",
                            "account_id": None,
                        }
                    },
                }
            )

            response = TestClient(app).get("/api/queue")
            queue_state = app.state.queue_storage.read_state()
            metadata = app.state.storage.read_metadata(task.task_id)

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["summary"]["channel_count"], 4)
        self.assertEqual([item["channel_id"] for item in payload["running"]], ["api:default:5"])
        self.assertIn("api:default:5", queue_state["running"])
        self.assertEqual(metadata["status"], "running")
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
