from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta
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


class WebUITaskTests(unittest.TestCase):
    def test_viewed_mutation_reads_latest_state_after_acquiring_task_lock(self) -> None:
        from codex_image.webui.app import create_app

        for action, change in ((action, change) for action in ("viewed", "archive") for change in ("complete", "cancel", "delete")):
            with self.subTest(action=action, change=change), tempfile.TemporaryDirectory() as tmp:
                app = create_app(output_root=Path(tmp), auth_checker=lambda: True, auto_start_queue=False)
                storage = app.state.storage
                task_id = storage.create_task("generate").task_id
                first = storage.output_file(storage.write_output(task_id, self._png_bytes(), "png", index=1))
                initial = {"task_id": task_id, "status": "running", "generated_count": 1,
                           "total_count": 2, "output_files": [first],
                           "outputs": [{"index": 1, "status": "completed", "file": first}]}
                storage.write_metadata(task_id, initial)
                waiting, release = threading.Event(), threading.Event()
                main = threading.current_thread()
                original_lock = storage._task_write_lock

                @contextmanager
                def gated_lock(current_id):
                    if threading.current_thread() is not main and not waiting.is_set():
                        waiting.set()
                        if not release.wait(5):
                            raise RuntimeError("viewed test barrier timed out")
                    with original_lock(current_id):
                        yield

                client = TestClient(app)
                responses = []
                with patch.object(storage, "_task_write_lock", side_effect=gated_lock):
                    viewer = threading.Thread(target=lambda: responses.append(client.patch(f"/api/tasks/{task_id}/{action}", json={"archived": True})))
                    viewer.start()
                    try:
                        self.assertTrue(waiting.wait(5))
                        if change == "delete":
                            storage.delete_task(task_id)
                        else:
                            second = storage.output_file(storage.write_output(task_id, self._png_bytes(), "png", index=2))
                            completed = {**initial, "status": "completed", "generated_count": 2,
                                         "output_files": [first, second],
                                         "outputs": [*initial["outputs"], {"index": 2, "status": "completed", "file": second}]}
                            if change == "cancel":
                                completed.update(cancel_requested=True, cancelled_at="2026-09-16T00:00:00Z")
                            storage.write_metadata(task_id, completed)
                    finally:
                        release.set()
                        viewer.join(5)
                self.assertFalse(viewer.is_alive())
                self.assertEqual(responses[0].status_code, 404 if change == "delete" else 200)
                if change == "delete":
                    self.assertFalse(storage.metadata_path(task_id).exists())
                    continue
                final = storage.read_metadata(task_id)
                self.assertEqual(final["generated_count"], 2)
                self.assertEqual(final["status"], completed["status"])
                self.assertTrue(final["viewed_at" if action == "viewed" else "archived_at"])
                self.assertEqual(storage.task_index.list_summaries()[0]["generated_count"], 2)
                self.assertEqual(client.get(f"/api/tasks/{task_id}/outputs/2/image").status_code, 200)
                if change == "cancel":
                    self.assertTrue(final["cancel_requested"])

    def test_batch_delete_rejects_unsafe_ids_before_touching_any_task(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root / "outputs", auth_checker=lambda: True, auto_start_queue=False)
            storage = app.state.storage
            storage.legacy_task_roots = (root / "outputs",)
            task_id = storage.create_task("generate").task_id
            storage.write_metadata(task_id, {"task_id": task_id, "status": "completed"})
            image = storage.write_output(task_id, self._png_bytes(), "png")
            sentinel = root / "unrelated.txt"
            sentinel.write_text("keep")
            before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
            client = TestClient(app, raise_server_exceptions=False)
            for invalid in ("..", ".", "*", "?", "[abc]", "a/b", "a\\b", "bad\x00id"):
                with self.subTest(task_id=invalid):
                    response = client.post("/api/tasks/delete-batch", json={"task_ids": [task_id, invalid]})
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual({path: path.read_bytes() for path in before}, before)
            response = client.post("/api/tasks/delete-batch", json={"task_ids": [task_id[:-1]]})
            self.assertEqual(response.json()["failed"], [task_id[:-1]])
            self.assertTrue(image.exists())
            self.assertEqual(sentinel.read_text(), "keep")

    def _png_bytes(self, size: tuple[int, int] = (400, 640)) -> bytes:
        image = Image.new("RGB", size, (120, 180, 160))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def test_task_history_api_returns_summary_and_cursor_pages(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.storage import TaskStorage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            storage = TaskStorage(root, input_root=root / "inputs", source_data_root=root / "source-data")
            for index, task_id in enumerate(["20260510101010-bbbbbbbb", "20260510101010-aaaaaaaa", "20260409101010-cccccccc"]):
                metadata = {
                    "task_id": task_id,
                    "created_at": "2026-05-10T10:10:10+00:00" if index < 2 else "2026-04-09T10:10:10+00:00",
                    "updated_at": "2026-05-10T10:11:10+00:00" if index < 2 else "2026-04-09T10:11:10+00:00",
                    "status": "completed" if index != 1 else "failed",
                    "mode": "generate" if index == 0 else "edit",
                    "prompt": "green portrait searchable" if index == 0 else "square product",
                    "prompt_for_model": "expanded hidden searchable text" if index == 0 else "",
                    "params": {
                        "size": "1152x2048" if index == 0 else "1024x1024",
                        "quality": "high" if index == 0 else "low",
                        "ratio": "9:16" if index == 0 else "1:1",
                        "orientation": "portrait" if index == 0 else "square",
                        "prompt_fidelity": "strict" if index == 0 else "original",
                    },
                    "backend": "openai_images" if index == 0 else "codex_responses",
                    "api_provider_name": "openai" if index == 0 else "codex",
                    "outputs": [{"index": 1, "status": "completed", "thumbnail_url": f"/thumb-{index}.jpg"}],
                    "generated_count": 1 if index != 1 else 0,
                    "failed_count": 0 if index != 1 else 1,
                    "total_count": 1,
                }
                if index == 1:
                    metadata["archived_at"] = "2026-05-11T00:00:00+00:00"
                storage.write_metadata(task_id, metadata)

            client = TestClient(app)
            summary = client.get("/api/task-history/summary").json()
            first = client.get("/api/task-history/tasks", params={"month": "2026-05", "limit": 1}).json()
            second = client.get("/api/task-history/tasks", params={"month": "2026-05", "limit": 2, "cursor": first["next_cursor"]}).json()
            visible = client.get("/api/task-history/tasks", params={"month": "2026-05", "limit": 10, "archived": "false"}).json()
            searched = client.get("/api/task-history/tasks", params={"q": "hidden searchable", "limit": 10}).json()
            image_to_image = client.get("/api/task-history/tasks", params={"mode": "edit", "limit": 10}).json()
            backend = client.get("/api/task-history/tasks", params={"backend": "openai_images", "limit": 10}).json()
            provider = client.get("/api/task-history/tasks", params={"provider": "openai", "limit": 10}).json()
            prompt_mode = client.get("/api/task-history/tasks", params={"prompt_mode": "strict", "limit": 10}).json()
            size = client.get("/api/task-history/tasks", params={"size": "1152x2048", "limit": 10}).json()
            quality = client.get("/api/task-history/tasks", params={"quality": "high", "limit": 10}).json()
            oldest = client.get("/api/task-history/tasks", params={"sort": "oldest", "limit": 1}).json()
            from codex_image.webui.task_index import _encode_cursor
            previous = client.get(
                "/api/task-history/tasks",
                params={
                    "month": "2026-05",
                    "limit": 1,
                    "cursor": _encode_cursor("2026-05-10T10:10:10+00:00", "20260510101010-aaaaaaaa"),
                    "direction": "previous",
                },
            ).json()
            recent = client.get("/api/tasks/recent", params={"limit": 1}).json()

        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["archived_total"], 1)
        self.assertEqual(summary["months"][0], {"month": "2026-05", "count": 2})
        self.assertIn({"value": "generate", "count": 1}, summary["modes"])
        self.assertIn({"value": "edit", "count": 2}, summary["modes"])
        self.assertEqual([task["task_id"] for task in first["tasks"]], ["20260510101010-bbbbbbbb"])
        self.assertIsNotNone(first["next_cursor"])
        self.assertEqual([task["task_id"] for task in second["tasks"]], ["20260510101010-aaaaaaaa"])
        self.assertIsNone(second["next_cursor"])
        self.assertEqual([task["task_id"] for task in visible["tasks"]], ["20260510101010-bbbbbbbb"])
        self.assertEqual([task["task_id"] for task in searched["tasks"]], ["20260510101010-bbbbbbbb"])
        self.assertEqual(
            [task["task_id"] for task in image_to_image["tasks"]],
            ["20260510101010-aaaaaaaa", "20260409101010-cccccccc"],
        )
        self.assertIn({"value": "openai", "count": 1}, summary["providers"])
        self.assertIn({"value": "strict", "count": 1}, summary["prompt_modes"])
        self.assertIn({"value": "1152x2048", "count": 1}, summary["sizes"])
        self.assertIn({"value": "high", "count": 1}, summary["qualities"])
        self.assertEqual([task["task_id"] for task in backend["tasks"]], ["20260510101010-bbbbbbbb"])
        self.assertEqual([task["task_id"] for task in provider["tasks"]], ["20260510101010-bbbbbbbb"])
        self.assertEqual([task["task_id"] for task in prompt_mode["tasks"]], ["20260510101010-bbbbbbbb"])
        self.assertEqual([task["task_id"] for task in size["tasks"]], ["20260510101010-bbbbbbbb"])
        self.assertEqual([task["task_id"] for task in quality["tasks"]], ["20260510101010-bbbbbbbb"])
        self.assertEqual(first["tasks"][0]["prompt_mode"], "strict")
        self.assertEqual(first["tasks"][0]["quality"], "high")
        self.assertEqual([task["task_id"] for task in oldest["tasks"]], ["20260409101010-cccccccc"])
        self.assertEqual([task["task_id"] for task in previous["tasks"]], ["20260510101010-bbbbbbbb"])
        self.assertNotIn("outputs", first["tasks"][0])
        self.assertNotIn("prompt_for_model", first["tasks"][0])
        self.assertEqual(len(recent["tasks"]), 1)
        self.assertEqual(recent["tasks"][0]["task_id"], "20260510101010-bbbbbbbb")

    def test_recent_tasks_api_returns_lightweight_sidebar_cards(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.storage import TaskStorage

        task_id = "20260510101010-aaaaaaaa"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            storage = TaskStorage(root, input_root=root / "inputs", source_data_root=root / "source-data")
            storage.write_metadata(
                task_id,
                {
                    "task_id": task_id,
                    "created_at": "2026-05-10T10:10:10+00:00",
                    "updated_at": "2026-05-10T10:11:10+00:00",
                    "viewed_at": "2026-05-10T10:10:30+00:00",
                    "status": "completed",
                    "mode": "edit",
                    "prompt": "sidebar card prompt",
                    "prompt_for_model": "expanded prompt should not ship to the main sidebar",
                    "params": {"size": "1152x2048", "n": 2},
                    "generation_snapshot": {
                        "canonical_model_id": "nano-banana-2",
                        "provider_base_url": "https://private.example/v1",
                        "remote_model_id": "private/model-name",
                        "requested_parameters": {
                            "canvas.aspect_ratio": "16:9",
                            "canvas.resolution": "2K",
                            "output.count": 2,
                        },
                        "mapped_request": {"json_body": {"prompt": "private"}},
                    },
                    "input_sources": [
                        {
                            "kind": "asset",
                            "id": "asset-1",
                            "image_url": "/api/reference-assets/asset-1/image",
                        }
                    ],
                    "outputs": [
                        {"index": 1, "status": "completed", "url": output_url(task_id, 1), "thumbnail_url": "/thumb-1.jpg"},
                        {"index": 2, "status": "completed", "url": output_url(task_id, 2), "thumbnail_url": "/thumb-2.jpg"},
                    ],
                    "generated_count": 2,
                    "failed_count": 0,
                    "total_count": 2,
                },
            )

            client = TestClient(app)
            response = client.get("/api/tasks/recent", params={"limit": 10})

        self.assertEqual(response.status_code, 200)
        task = response.json()["tasks"][0]
        self.assertEqual(task["task_id"], task_id)
        self.assertEqual(task["prompt"], "sidebar card prompt")
        self.assertEqual(task["output_size"], "1152x2048")
        self.assertEqual(task["thumbnail_urls"], [f"/api/tasks/{task_id}/outputs/1/sidebar-thumbnail"])
        self.assertEqual(task["input_thumbnail_urls"], ["/api/reference-assets/asset-1/image"])
        self.assertEqual(task["generated_count"], 2)
        self.assertEqual(task["generation_snapshot"], {
            "canonical_model_id": "nano-banana-2",
            "requested_parameters": {
                "canvas.aspect_ratio": "16:9",
                "canvas.resolution": "2K",
            },
        })
        self.assertTrue(task["summary_only"])
        self.assertNotIn("outputs", task)
        self.assertNotIn("output_urls", task)
        self.assertNotIn("input_sources", task)
        self.assertNotIn("prompt_for_model", task)
        self.assertNotIn("request", task)
        serialized = str(task)
        self.assertNotIn("private.example", serialized)
        self.assertNotIn("private/model-name", serialized)
        self.assertNotIn("output.count", serialized)
        self.assertNotIn("mapped_request", serialized)

    def test_recent_tasks_api_falls_back_to_requested_size_when_output_size_is_numeric(self) -> None:
        from codex_image.webui.app import create_app

        task_id = "20260624095053-12bdaf0e"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            metadata_path(root, task_id).parent.mkdir(parents=True, exist_ok=True)
            metadata_path(root, task_id).write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "created_at": "2026-06-24T09:50:53+00:00",
                        "status": "completed",
                        "prompt": "sidebar numeric output size",
                        "params": {"size": "2336x3504", "n": 1},
                        "output_size": "952614",
                        "output_sizes": ["952614"],
                        "outputs": [
                            {
                                "index": 1,
                                "status": "completed",
                                "size": "952614",
                                "url": output_url(task_id, 1, "jpg"),
                            }
                        ],
                        "generated_count": 1,
                        "failed_count": 0,
                        "total_count": 1,
                    }
                ),
                encoding="utf-8",
            )

            client = TestClient(app)
            response = client.get("/api/tasks/recent", params={"limit": 10})

        self.assertEqual(response.status_code, 200)
        task = response.json()["tasks"][0]
        self.assertEqual(task["output_size"], "2336x3504")
        self.assertEqual(task["params"]["size"], "2336x3504")

    def test_recent_tasks_api_preserves_requested_size_when_output_dimensions_differ(self) -> None:
        from codex_image.webui.app import create_app

        task_id = "20260705145007-1b903c99"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            metadata_path(root, task_id).parent.mkdir(parents=True, exist_ok=True)
            metadata_path(root, task_id).write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "created_at": "2026-07-05T14:50:07+00:00",
                        "status": "completed",
                        "prompt": "requested 9:16 but provider returned 2:3",
                        "params": {"size": "864x1536", "ratio": "9:16", "n": 2},
                        "output_size": "832x1248",
                        "output_sizes": ["832x1248", "832x1248"],
                        "outputs": [
                            {"index": 1, "status": "completed", "size": "832x1248", "url": output_url(task_id, 1, "jpg")},
                            {"index": 2, "status": "completed", "size": "832x1248", "url": output_url(task_id, 2, "jpg")},
                        ],
                        "generated_count": 2,
                        "failed_count": 0,
                        "total_count": 2,
                    }
                ),
                encoding="utf-8",
            )

            client = TestClient(app)
            response = client.get("/api/tasks/recent", params={"limit": 10})

        self.assertEqual(response.status_code, 200)
        task = response.json()["tasks"][0]
        self.assertEqual(task["output_size"], "832x1248")
        self.assertEqual(task["params"]["size"], "864x1536")
        self.assertEqual(task["params"]["ratio"], "9:16")

    def test_task_outputs_zip_downloads_multiple_outputs(self) -> None:
        from codex_image.webui.app import create_app

        task_id = "20260726010203-abcdef01"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_temp_root = root / "archive-temp"
            first = root / output_name(task_id, 1)
            second = root / output_name(task_id, 2, "webp")
            first.parent.mkdir(parents=True, exist_ok=True)
            first.write_bytes(b"first-image")
            second.write_bytes(b"second-image")
            metadata_path(root, task_id).parent.mkdir(parents=True, exist_ok=True)
            metadata_path(root, task_id).write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "status": "completed",
                        "output_files": [output_name(task_id, 1), output_name(task_id, 2, "webp")],
                        "output_urls": [output_url(task_id, 1), output_url(task_id, 2, "webp")],
                    }
                ),
                encoding="utf-8",
            )

            app = create_app(
                output_root=root,
                auth_checker=lambda: True,
                auto_start_queue=False,
                history_export_temp_root=archive_temp_root,
            )
            response = TestClient(app).get(f"/api/tasks/{task_id}/outputs.zip")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "application/zip")
            self.assertIn(f'filename="{task_id}-images.zip"', response.headers["content-disposition"])
            with zipfile.ZipFile(BytesIO(response.content)) as archive:
                self.assertEqual(
                    sorted(archive.namelist()),
                    [f"{task_id}-image-1.png", f"{task_id}-image-2.webp"],
                )
                self.assertEqual(archive.read(f"{task_id}-image-1.png"), b"first-image")
                self.assertEqual(archive.read(f"{task_id}-image-2.webp"), b"second-image")
            self.assertEqual(list(archive_temp_root.iterdir()), [])

    def test_task_outputs_zip_rejects_total_input_over_limit_without_modifying_sources(self) -> None:
        from codex_image.webui.app import create_app

        task_id = "20260726010203-abcdef01"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_temp_root = root / "archive-temp"
            first = root / output_name(task_id, 1)
            second = root / output_name(task_id, 2)
            first.parent.mkdir(parents=True, exist_ok=True)
            first.write_bytes(b"first-image")
            second.write_bytes(b"second-image")
            metadata_path(root, task_id).parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            metadata_path(root, task_id).write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "status": "completed",
                        "output_files": [
                            output_name(task_id, 1),
                            output_name(task_id, 2),
                        ],
                        "output_urls": [
                            output_url(task_id, 1),
                            output_url(task_id, 2),
                        ],
                    }
                ),
                encoding="utf-8",
            )
            app = create_app(
                output_root=root,
                auth_checker=lambda: True,
                auto_start_queue=False,
                history_export_temp_root=archive_temp_root,
            )

            with patch(
                "codex_image.webui.routes.tasks.MAX_TASK_ARCHIVE_INPUT_BYTES",
                10,
            ):
                response = TestClient(app).get(
                    f"/api/tasks/{task_id}/outputs.zip"
                )

            first_bytes = first.read_bytes()
            second_bytes = second.read_bytes()
            temporary_files = list(archive_temp_root.iterdir())

        self.assertEqual(response.status_code, 413)
        self.assertEqual(
            response.json()["detail"],
            {
                "code": "task_archive_too_large",
                "message": "The task outputs are too large to archive.",
                "max_input_bytes": 10,
            },
        )
        self.assertEqual(first_bytes, b"first-image")
        self.assertEqual(second_bytes, b"second-image")
        self.assertEqual(temporary_files, [])

    def test_task_reveal_output_endpoint_opens_output_directory(self) -> None:
        from codex_image.webui.app import create_app

        task_id = "20260726010203-abcdef01"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_path = root / output_name(task_id, 1)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"image")
            metadata_path(root, task_id).parent.mkdir(parents=True, exist_ok=True)
            metadata_path(root, task_id).write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "status": "completed",
                        "output_files": [output_name(task_id, 1)],
                        "output_urls": [output_url(task_id, 1)],
                    }
                ),
                encoding="utf-8",
            )

            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            with patch("codex_image.webui.routes.tasks._open_path_in_file_manager") as open_path:
                response = TestClient(app).post(
                    f"/api/tasks/{task_id}/reveal-output",
                    headers={"X-Requested-With": "codex-image-webui"},
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["ok"], True)
            open_path.assert_called_once_with(output_path.parent)

    def test_task_reveal_output_endpoint_requires_webui_header(self) -> None:
        from codex_image.webui.app import create_app

        task_id = "20260505010203-abcdef01"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_path = root / output_name(task_id, 1)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"image")
            metadata_path(root, task_id).parent.mkdir(parents=True, exist_ok=True)
            metadata_path(root, task_id).write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "status": "completed",
                        "output_files": [output_name(task_id, 1)],
                    }
                ),
                encoding="utf-8",
            )

            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            with patch("codex_image.webui.routes.tasks._open_path_in_file_manager") as open_path:
                response = TestClient(app).post(f"/api/tasks/{task_id}/reveal-output")

            self.assertEqual(response.status_code, 403)
            open_path.assert_not_called()

    def test_task_outputs_can_select_and_prune_unselected_results(self) -> None:
        from codex_image.webui.app import create_app

        task_id = "20260505010203-abcdef01"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_files = [output_name(task_id, index) for index in (1, 2, 3)]
            for index, filename in enumerate(output_files, start=1):
                path = root / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(self._png_bytes())
                thumb = root / "thumbnails" / "2026-05-05" / f"{task_id}-image-{index}-thumb.jpg"
                thumb.parent.mkdir(parents=True, exist_ok=True)
                thumb.write_bytes(f"thumb-{index}".encode("utf-8"))
            metadata_path(root, task_id).parent.mkdir(parents=True, exist_ok=True)
            metadata_path(root, task_id).write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "status": "completed",
                        "generated_count": 3,
                        "total_count": 3,
                        "output_file": output_files[0],
                        "output_files": output_files,
                        "output_url": output_url(task_id, 1),
                        "output_urls": [output_url(task_id, index) for index in (1, 2, 3)],
                        "outputs": [
                            {
                                "index": index,
                                "status": "completed",
                                "file": output_files[index - 1],
                                "url": output_url(task_id, index),
                                "thumbnail_file": f"thumbnails/2026-05-05/{task_id}-image-{index}-thumb.jpg",
                                "thumbnail_url": f"/outputs/thumbnails/2026-05-05/{task_id}-image-{index}-thumb.jpg",
                            }
                            for index in (1, 2, 3)
                        ],
                    }
                ),
                encoding="utf-8",
            )

            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)
            first_selection = client.patch(f"/api/tasks/{task_id}/outputs/1/selected", json={"selected": True})
            third_selection = client.patch(f"/api/tasks/{task_id}/outputs/3/selected", json={"selected": True})

            self.assertEqual(first_selection.status_code, 200)
            self.assertEqual(third_selection.status_code, 200)
            self.assertEqual(
                first_selection.json()["task"]["viewed_at"],
                first_selection.json()["task"]["updated_at"],
            )
            self.assertEqual(
                third_selection.json()["task"]["viewed_at"],
                third_selection.json()["task"]["updated_at"],
            )
            self.assertEqual(third_selection.json()["task"]["selected_output_indexes"], [1, 3])

            selected_zip = client.get(f"/api/tasks/{task_id}/outputs.zip?selected=1")
            self.assertEqual(selected_zip.status_code, 200)
            with zipfile.ZipFile(BytesIO(selected_zip.content)) as archive:
                self.assertEqual(
                    sorted(archive.namelist()),
                    [f"{task_id}-image-1.png", f"{task_id}-image-3.png"],
                )

            pruned = client.post(f"/api/tasks/{task_id}/outputs/delete-unselected")

            self.assertEqual(pruned.status_code, 200)
            task = pruned.json()["task"]
            self.assertEqual(task["output_urls"], [output_url(task_id, 1), output_url(task_id, 3)])
            self.assertEqual(task["output_files"], [output_files[0], output_files[2]])
            self.assertEqual([(item["index"], item["url"]) for item in task["outputs"]], [(1, output_url(task_id, 1)), (2, output_url(task_id, 3))])
            self.assertEqual(task["generated_count"], 2)
            self.assertEqual(task["total_count"], 2)
            self.assertEqual(task["selected_output_indexes"], [])
            self.assertEqual(task["viewed_at"], task["updated_at"])
            self.assertTrue((root / output_files[0]).is_file())
            self.assertFalse((root / output_files[1]).exists())
            self.assertTrue((root / output_files[2]).is_file())
            self.assertTrue((root / "thumbnails" / "2026-05-05" / f"{task_id}-image-1-thumb.jpg").is_file())
            self.assertTrue((root / "thumbnails" / "2026-05-05" / f"{task_id}-image-2-thumb.jpg").is_file())
            self.assertFalse((root / "thumbnails" / "2026-05-05" / f"{task_id}-image-3-thumb.jpg").exists())

    def test_delete_unselected_outputs_removes_unreferenced_task_images_and_thumbnails(self) -> None:
        from codex_image.webui.app import create_app

        task_id = "20260505010203-abcdef01"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_files = [output_name(task_id, index) for index in (1, 2)]
            for filename in output_files:
                path = root / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(self._png_bytes())
            orphan_output = root / output_name(task_id, 99)
            orphan_output.write_bytes(self._png_bytes())
            orphan_thumbnail = root / "thumbnails" / "2026-05-05" / f"{task_id}-image-99-thumb.jpg"
            orphan_thumbnail.parent.mkdir(parents=True, exist_ok=True)
            orphan_thumbnail.write_bytes(b"orphan-thumb")

            task_metadata = metadata_path(root, task_id)
            task_metadata.parent.mkdir(parents=True, exist_ok=True)
            task_metadata.write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "status": "completed",
                        "generated_count": 2,
                        "total_count": 2,
                        "output_files": output_files,
                        "output_urls": [output_url(task_id, index) for index in (1, 2)],
                        "outputs": [
                            {
                                "index": index,
                                "status": "completed",
                                "file": output_files[index - 1],
                                "url": output_url(task_id, index),
                            }
                            for index in (1, 2)
                        ],
                    }
                ),
                encoding="utf-8",
            )
            task_request = request_path(root, task_id)
            task_request.write_text("{}", encoding="utf-8")

            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)
            selected = client.patch(f"/api/tasks/{task_id}/outputs/1/selected", json={"selected": True})
            pruned = client.post(f"/api/tasks/{task_id}/outputs/delete-unselected")

            self.assertEqual(selected.status_code, 200)
            self.assertEqual(pruned.status_code, 200)
            self.assertTrue((root / output_files[0]).is_file())
            self.assertFalse((root / output_files[1]).exists())
            self.assertFalse(orphan_output.exists())
            self.assertFalse(orphan_thumbnail.exists())
            self.assertTrue(task_metadata.is_file())
            self.assertTrue(task_request.is_file())

    def test_delete_unselected_outputs_restores_files_when_metadata_update_fails(self) -> None:
        from codex_image.webui.app import create_app

        task_id = "20260505010203-abcdef01"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_files = [output_name(task_id, index) for index in (1, 2)]
            output_paths = [root / filename for filename in output_files]
            thumbnail_paths = [
                root / "thumbnails" / "2026-05-05" / f"{task_id}-image-{index}-thumb.jpg"
                for index in (1, 2)
            ]
            for path in output_paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(self._png_bytes())
            for index, path in enumerate(thumbnail_paths, start=1):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"original-thumb-{index}".encode("utf-8"))
            task_metadata = metadata_path(root, task_id)
            task_metadata.parent.mkdir(parents=True, exist_ok=True)
            task_metadata.write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "status": "completed",
                        "generated_count": 2,
                        "total_count": 2,
                        "output_files": output_files,
                        "output_urls": [output_url(task_id, index) for index in (1, 2)],
                        "outputs": [
                            {
                                "index": index,
                                "status": "completed",
                                "file": output_files[index - 1],
                                "url": output_url(task_id, index),
                            }
                            for index in (1, 2)
                        ],
                    }
                ),
                encoding="utf-8",
            )

            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app, raise_server_exceptions=False)
            selected = client.patch(f"/api/tasks/{task_id}/outputs/1/selected", json={"selected": True})
            with patch.object(app.state.storage, "write_metadata", side_effect=OSError("simulated metadata failure")):
                pruned = client.post(f"/api/tasks/{task_id}/outputs/delete-unselected")

            stored_metadata = json.loads(task_metadata.read_text(encoding="utf-8"))
            output_exists = [path.is_file() for path in output_paths]
            thumbnail_bytes = [path.read_bytes() if path.is_file() else None for path in thumbnail_paths]

        self.assertEqual(selected.status_code, 200)
        self.assertEqual(pruned.status_code, 500)
        self.assertEqual(output_exists, [True, True])
        self.assertEqual(thumbnail_bytes, [b"original-thumb-1", b"original-thumb-2"])
        self.assertEqual(stored_metadata["output_files"], output_files)
        self.assertEqual(stored_metadata["selected_output_indexes"], [1])

    def test_task_detail_api_backfills_image_url_for_restored_file_only_output(self) -> None:
        from codex_image.webui.app import create_app

        task_id = "20260801074820-57f7da69"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_file = output_name(task_id, 1)
            output_path = root / output_file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(self._png_bytes())
            metadata_path(root, task_id).parent.mkdir(parents=True, exist_ok=True)
            metadata_path(root, task_id).write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "created_at": "2026-08-01T07:48:20+00:00",
                        "status": "completed",
                        "generated_count": 1,
                        "total_count": 1,
                        "output_file": output_file,
                        "output_files": [output_file],
                        "outputs": [
                            {
                                "index": 1,
                                "status": "completed",
                                "file": output_file,
                            }
                        ],
                        "backup_import_fingerprint": "sha256:" + "a" * 64,
                    }
                ),
                encoding="utf-8",
            )

            app = create_app(
                output_root=root,
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            client = TestClient(app)
            task_response = client.get(f"/api/tasks/{task_id}")
            task = task_response.json()["task"]
            image_url = task["outputs"][0]["url"]
            image_response = client.get(image_url)

        self.assertEqual(task_response.status_code, 200)
        self.assertEqual(
            image_url,
            f"/api/tasks/{task_id}/outputs/1/image",
        )
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response.headers["content-type"], "image/png")

    def test_task_thumbnail_route_backfills_legacy_output_thumbnail(self) -> None:
        from codex_image.webui.app import create_app

        task_id = "20260505010203-abcdef01"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_file = output_name(task_id, 1)
            output_path = root / output_file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(self._png_bytes())
            original_size = output_path.stat().st_size
            metadata_path(root, task_id).parent.mkdir(parents=True, exist_ok=True)
            metadata_path(root, task_id).write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "status": "completed",
                        "generated_count": 1,
                        "total_count": 1,
                        "output_file": output_file,
                        "output_files": [output_file],
                        "output_url": output_url(task_id, 1),
                        "output_urls": [output_url(task_id, 1)],
                    }
                ),
                encoding="utf-8",
            )

            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)
            task_response = client.get(f"/api/tasks/{task_id}")
            thumbnail_response = client.get(f"/api/tasks/{task_id}/outputs/1/thumbnail")
            thumbnail_file_exists = (root / "thumbnails" / "2026-05-05" / f"{task_id}-image-1-thumb.jpg").is_file()

        task = task_response.json()["task"]
        self.assertEqual(task_response.status_code, 200)
        self.assertEqual(task["thumbnail_urls"], [f"/api/tasks/{task_id}/outputs/1/thumbnail"])
        self.assertEqual(thumbnail_response.status_code, 200)
        self.assertEqual(thumbnail_response.headers["content-type"], "image/jpeg")
        self.assertLess(len(thumbnail_response.content), original_size)
        self.assertTrue(thumbnail_file_exists)

    def test_sidebar_thumbnail_route_uses_cached_256px_webp(self) -> None:
        from codex_image.webui.app import create_app

        task_time = datetime.now().astimezone().replace(hour=1, minute=2, second=3, microsecond=0)
        task_id = f"{task_time:%Y%m%d%H%M%S}-abcdef01"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_file = output_name(task_id, 1)
            output_path = root / output_file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(self._png_bytes((900, 1440)))
            metadata_path(root, task_id).parent.mkdir(parents=True, exist_ok=True)
            metadata_path(root, task_id).write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "created_at": task_time.isoformat(),
                        "updated_at": (task_time + timedelta(minutes=1)).isoformat(),
                        "status": "completed",
                        "generated_count": 1,
                        "total_count": 1,
                        "output_file": output_file,
                        "output_files": [output_file],
                        "output_url": output_url(task_id, 1),
                        "output_urls": [output_url(task_id, 1)],
                    }
                ),
                encoding="utf-8",
            )

            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)
            sidebar = client.get("/api/tasks/sidebar", params={"limit": 50}).json()
            thumbnail_url = sidebar["tasks"][0]["thumbnail_urls"][0]
            thumbnail_response = client.get(thumbnail_url)
            thumbnail_path = root / "thumbnails" / f"{task_time:%Y-%m-%d}" / f"{task_id}-image-1-sidebar.webp"
            with Image.open(thumbnail_path) as thumbnail:
                thumbnail_size = thumbnail.size
                thumbnail_format = thumbnail.format
            thumbnail_exists = thumbnail_path.is_file()

        self.assertEqual(thumbnail_url, f"/api/tasks/{task_id}/outputs/1/sidebar-thumbnail")
        self.assertEqual(thumbnail_response.status_code, 200)
        self.assertEqual(thumbnail_response.headers["content-type"], "image/webp")
        self.assertEqual(max(thumbnail_size), 256)
        self.assertEqual(thumbnail_format, "WEBP")
        self.assertTrue(thumbnail_exists)

    def test_sidebar_group_api_and_selection_cover_unloaded_matching_tasks(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.storage import TaskStorage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            storage = TaskStorage(root, input_root=root / "inputs", source_data_root=root / "source-data")
            base_time = datetime.now().astimezone().replace(hour=8, minute=0, second=0, microsecond=0)
            for number in range(75):
                task_time = base_time + timedelta(seconds=number)
                task_id = f"{task_time:%Y%m%d%H%M%S}-{number:08d}"
                timestamp = task_time.isoformat()
                storage.write_metadata(
                    task_id,
                    {
                        "task_id": task_id,
                        "created_at": timestamp,
                        "updated_at": timestamp,
                        "terminal_at": timestamp,
                        "status": "failed" if number % 2 else "completed",
                        "params": {"ratio": "1:1", "orientation": "square"},
                    },
                )
                if number == 10:
                    hidden_task_id = task_id

            client = TestClient(app)
            page = client.get(
                "/api/tasks/sidebar/groups/today",
                params={"offset": 50, "limit": 50},
            )
            selection = client.get(
                "/api/tasks/sidebar/groups/today/selection",
                params={"status": "failed", "ratio": "1:1"},
            )
            position = client.get(
                f"/api/tasks/sidebar/groups/today/position/{hidden_task_id}",
            )

        self.assertEqual(page.status_code, 200)
        self.assertEqual(len(page.json()["tasks"]), 25)
        self.assertFalse(page.json()["has_more"])
        self.assertEqual(selection.status_code, 200)
        self.assertEqual(selection.json()["count"], 37)
        self.assertEqual(len(selection.json()["task_ids"]), 37)
        self.assertEqual(position.status_code, 200)
        self.assertEqual(position.json()["count"], 75)
        self.assertTrue(position.json()["found"])
        self.assertEqual(position.json()["position"], 64)

    def test_batch_delete_route_deletes_explicit_terminal_tasks_and_skips_running(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.storage import TaskStorage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            storage = TaskStorage(root, input_root=root / "inputs", source_data_root=root / "source-data")
            terminal_ids = ["20260726080100-aaaaaaaa", "20260726080200-bbbbbbbb"]
            running_id = "20260726080300-cccccccc"
            for task_id, status in [*(zip(terminal_ids, ["completed", "failed"])), (running_id, "running")]:
                storage.write_metadata(
                    task_id,
                    {
                        "task_id": task_id,
                        "created_at": "2026-07-26T08:00:00+08:00",
                        "updated_at": "2026-07-26T08:01:00+08:00",
                        "status": status,
                    },
                )
            app.state.active_task_ids.add(running_id)

            response = TestClient(app).post(
                "/api/tasks/delete-batch",
                json={"task_ids": [*terminal_ids, running_id]},
            )
            remaining = [storage.metadata_path(task_id).exists() for task_id in [*terminal_ids, running_id]]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted"], terminal_ids)
        self.assertEqual(response.json()["skipped"], [running_id])
        self.assertEqual(response.json()["failed"], [])
        self.assertEqual(remaining, [False, False, True])

    def test_task_thumbnail_route_refreshes_small_cached_thumbnail(self) -> None:
        from codex_image.webui.app import create_app

        task_id = "20260505010203-abcdef01"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_file = output_name(task_id, 1)
            output_path = root / output_file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(self._png_bytes((400, 640)))
            thumbnail_path = root / "thumbnails" / "2026-05-05" / f"{task_id}-image-1-thumb.jpg"
            thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (96, 96), (120, 180, 160)).save(thumbnail_path, format="JPEG")
            metadata_path(root, task_id).parent.mkdir(parents=True, exist_ok=True)
            metadata_path(root, task_id).write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "status": "completed",
                        "generated_count": 1,
                        "total_count": 1,
                        "output_file": output_file,
                        "output_files": [output_file],
                        "output_url": output_url(task_id, 1),
                        "output_urls": [output_url(task_id, 1)],
                    }
                ),
                encoding="utf-8",
            )

            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)
            thumbnail_response = client.get(f"/api/tasks/{task_id}/outputs/1/thumbnail")
            with Image.open(thumbnail_path) as refreshed:
                refreshed_size = refreshed.size

        self.assertEqual(thumbnail_response.status_code, 200)
        self.assertEqual(max(refreshed_size), 640)

    def test_task_input_thumbnail_route_backfills_legacy_input_thumbnail(self) -> None:
        from codex_image.webui.app import create_app

        task_id = "20260505010203-abcdef01"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_file = input_name(task_id, "input.png")
            input_path = root / "inputs" / input_file
            input_path.parent.mkdir(parents=True, exist_ok=True)
            input_path.write_bytes(self._png_bytes())
            original_size = input_path.stat().st_size
            metadata_path(root, task_id).parent.mkdir(parents=True, exist_ok=True)
            metadata_path(root, task_id).write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "status": "completed",
                        "input_files": [input_file],
                    }
                ),
                encoding="utf-8",
            )

            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)
            task_response = client.get(f"/api/tasks/{task_id}")
            thumbnail_response = client.get(f"/api/tasks/{task_id}/inputs/1/thumbnail")
            thumbnail_file_exists = (root / "thumbnails" / "2026-05-05" / f"{task_id}-input-01-thumb.jpg").is_file()

        task = task_response.json()["task"]
        self.assertEqual(task_response.status_code, 200)
        self.assertEqual(task["input_thumbnail_urls"], [f"/api/tasks/{task_id}/inputs/1/thumbnail"])
        self.assertEqual(thumbnail_response.status_code, 200)
        self.assertEqual(thumbnail_response.headers["content-type"], "image/jpeg")
        self.assertLess(len(thumbnail_response.content), original_size)
        self.assertTrue(thumbnail_file_exists)

    def test_delete_unselected_outputs_requires_a_selection(self) -> None:
        from codex_image.webui.app import create_app

        task_id = "20260505010203-abcdef01"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / output_name(task_id, 1)
            first.parent.mkdir(parents=True, exist_ok=True)
            first.write_bytes(b"image")
            metadata_path(root, task_id).parent.mkdir(parents=True, exist_ok=True)
            metadata_path(root, task_id).write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "status": "completed",
                        "output_files": [output_name(task_id, 1)],
                        "output_urls": [output_url(task_id, 1)],
                    }
                ),
                encoding="utf-8",
            )

            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            response = TestClient(app).post(f"/api/tasks/{task_id}/outputs/delete-unselected")

            self.assertEqual(response.status_code, 409)
            self.assertIn("Select at least one output", response.json()["detail"])
    def test_task_response_backfills_main_model_from_stored_request(self) -> None:
        from codex_image.webui.app import _with_file_urls

        task = _with_file_urls(
            {
                "task_id": "task-1",
                "status": "completed",
                "params": {"model": "gpt-image-2"},
                "request": {"model": "gpt-5.5"},
            }
        )

        self.assertEqual(task["params"]["main_model"], "gpt-5.5")
    def test_tasks_list_omits_stored_request_payloads(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.storage import TaskStorage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = TaskStorage(root)
            created = storage.create_task("edit")
            storage.write_metadata(
                created.task_id,
                {
                    "task_id": created.task_id,
                    "created_at": "2026-05-01T00:00:00+00:00",
                    "updated_at": "2026-05-01T00:00:00+00:00",
                    "mode": "edit",
                    "status": "completed",
                    "prompt": "heavy request",
                    "params": {"model": "gpt-image-2"},
                    "request": {
                        "model": "gpt-5.5",
                        "input": [{"content": [{"type": "input_image", "image_url": "data:image/png;base64," + "a" * 1000}]}],
                    },
                },
            )
            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            response = TestClient(app).get("/api/tasks")

        task = response.json()["tasks"][0]
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("request", task)
        self.assertEqual(task["params"]["main_model"], "gpt-5.5")
    def test_task_viewed_route_marks_metadata_and_returns_task(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.storage import TaskStorage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = TaskStorage(root)
            created = storage.create_task("generate")
            storage.write_metadata(
                created.task_id,
                {
                    "task_id": created.task_id,
                    "created_at": "2026-05-18T00:00:00+00:00",
                    "updated_at": "2026-05-18T00:05:00+00:00",
                    "status": "completed",
                    "prompt": "finished task",
                    "viewed_at": "2026-05-18T00:00:00+00:00",
                },
            )
            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)

            response = client.patch(f"/api/tasks/{created.task_id}/viewed")
            metadata = storage.read_metadata(created.task_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["task"]["task_id"], created.task_id)
        self.assertGreater(metadata["viewed_at"], "2026-05-18T00:05:00+00:00")
        self.assertEqual(response.json()["task"]["viewed_at"], metadata["viewed_at"])
    def test_task_detail_keeps_stored_request_payload(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.storage import TaskStorage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = TaskStorage(root)
            created = storage.create_task("edit")
            storage.write_metadata(
                created.task_id,
                {
                    "task_id": created.task_id,
                    "created_at": "2026-05-01T00:00:00+00:00",
                    "updated_at": "2026-05-01T00:00:00+00:00",
                    "mode": "edit",
                    "status": "completed",
                    "prompt": "heavy request detail",
                    "params": {"model": "gpt-image-2"},
                    "request": {"model": "gpt-5.5", "input": [{"content": [{"image_url": "data:image/png;base64,aaa"}]}]},
                },
            )
            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            response = TestClient(app).get(f"/api/tasks/{created.task_id}")

        task = response.json()["task"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(task["request"]["model"], "gpt-5.5")
    def test_task_archive_route_persists_archived_at(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.storage import TaskStorage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = TaskStorage(root)
            created = storage.create_task("generate")
            storage.write_metadata(
                created.task_id,
                {
                    "task_id": created.task_id,
                    "mode": "generate",
                    "prompt": "archive me",
                    "status": "completed",
                    "created_at": "2026-05-16T01:00:00Z",
                },
            )
            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)

            response = client.patch(f"/api/tasks/{created.task_id}/archive", json={"archived": True})

            self.assertEqual(response.status_code, 200)
            task = response.json()["task"]
            self.assertEqual(task["task_id"], created.task_id)
            self.assertIn("archived_at", task)
            self.assertTrue(task["archived_at"])

            stored = storage.read_metadata(created.task_id)
            self.assertEqual(stored["archived_at"], task["archived_at"])

            listed = client.get("/api/tasks").json()["tasks"][0]
            self.assertEqual(listed["archived_at"], task["archived_at"])
    def test_task_archive_route_restores_archived_task(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.storage import TaskStorage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = TaskStorage(root)
            created = storage.create_task("generate")
            storage.write_metadata(
                created.task_id,
                {
                    "task_id": created.task_id,
                    "mode": "generate",
                    "prompt": "restore me",
                    "status": "completed",
                    "created_at": "2026-05-16T01:00:00Z",
                    "archived_at": "2026-05-16T02:00:00Z",
                },
            )
            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)

            response = client.patch(f"/api/tasks/{created.task_id}/archive", json={"archived": False})

            self.assertEqual(response.status_code, 200)
            task = response.json()["task"]
            self.assertNotIn("archived_at", task)
            self.assertNotIn("archived_at", storage.read_metadata(created.task_id))
    def test_startup_prunes_duplicate_request_payload_from_metadata(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.storage import TaskStorage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = TaskStorage(root)
            created = storage.create_task("edit")
            request_payload = {"model": "gpt-5.5", "input": [{"content": [{"image_url": "data:image/png;base64,aaa"}]}]}
            storage.write_request(created.task_id, request_payload)
            storage.write_metadata(
                created.task_id,
                {
                    "task_id": created.task_id,
                    "created_at": "2026-05-01T00:00:00+00:00",
                    "updated_at": "2026-05-01T00:00:00+00:00",
                    "mode": "edit",
                    "status": "completed",
                    "prompt": "duplicate request",
                    "params": {"model": "gpt-image-2"},
                    "request": request_payload,
                },
            )

            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            metadata = storage.read_metadata(created.task_id)
            detail = TestClient(app).get(f"/api/tasks/{created.task_id}").json()["task"]

        self.assertNotIn("request", metadata)
        self.assertEqual(detail["request"], request_payload)
    def test_queue_delete_waiting_task_removes_directory(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)
            created = client.post("/api/generate", data={"prompt": "delete me", "size": "1024x1024"})
            task_id = created.json()["task"]["task_id"]

            deleted = client.delete(f"/api/queue/{task_id}")

            task_exists = metadata_path(Path(tmp), task_id).exists()

        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(task_exists)
    def test_delete_task_route_removes_waiting_queue_entry(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)
            first = client.post("/api/generate", data={"prompt": "first", "size": "1024x1024"}).json()["task"]["task_id"]
            second = client.post("/api/generate", data={"prompt": "second", "size": "1024x1024"}).json()["task"]["task_id"]

            deleted = client.delete(f"/api/tasks/{first}")
            queue = client.get("/api/queue").json()
            reordered = client.patch("/api/queue/reorder", json={"task_ids": [second]})

        self.assertEqual(deleted.status_code, 200)
        self.assertEqual([task["task_id"] for task in queue["waiting"]], [second])
        self.assertEqual(reordered.status_code, 200)

    def test_waiting_task_stays_queued_when_physical_delete_fails(self) -> None:
        from codex_image.webui.app import create_app

        for endpoint in ("/api/tasks/{task_id}", "/api/queue/{task_id}"):
            with self.subTest(endpoint=endpoint), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                app = create_app(
                    output_root=root,
                    client_factory=lambda: FakeImageClient(),
                    auth_checker=lambda: True,
                    auto_start_queue=False,
                )
                client = TestClient(app, raise_server_exceptions=False)
                created = client.post("/api/generate", data={"prompt": "keep queued on failure", "size": "1024x1024"})
                task_id = created.json()["task"]["task_id"]
                output_path = root / output_name(task_id)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"image")
                original_unlink = Path.unlink

                def fail_output_unlink(path: Path, *args: object, **kwargs: object) -> None:
                    if path == output_path:
                        raise OSError("simulated output cleanup failure")
                    original_unlink(path, *args, **kwargs)

                with patch.object(Path, "unlink", new=fail_output_unlink):
                    response = client.delete(endpoint.format(task_id=task_id))

                queue_state = app.state.queue_storage.read_state()
                task_metadata_exists = app.state.storage.metadata_path(task_id).is_file()

            self.assertEqual(response.status_code, 500)
            self.assertIn(task_id, queue_state["waiting"])
            self.assertTrue(task_metadata_exists)

    def test_delete_task_route_rejects_queue_running_task(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)
            created = client.post("/api/generate", data={"prompt": "running race", "size": "1024x1024"})
            task_id = created.json()["task"]["task_id"]
            app.state.queue_storage.remove_waiting(task_id)
            app.state.queue_storage.set_running("codex:local", task_id, auth_source="codex")

            deleted = client.delete(f"/api/tasks/{task_id}")
            task_exists = metadata_path(Path(tmp), task_id).exists()
            running = app.state.queue_storage.read_state()["running"]

        self.assertEqual(deleted.status_code, 409)
        self.assertTrue(task_exists)
        self.assertEqual(running["codex:local"]["task_id"], task_id)
    def test_queue_promote_and_reorder_waiting_tasks(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)
            first = client.post("/api/generate", data={"prompt": "first", "size": "1024x1024"}).json()["task"]["task_id"]
            second = client.post("/api/generate", data={"prompt": "second", "size": "1024x1024"}).json()["task"]["task_id"]
            third = client.post("/api/generate", data={"prompt": "third", "size": "1024x1024"}).json()["task"]["task_id"]

            promoted = client.post(f"/api/queue/{third}/promote").json()
            reordered = client.patch("/api/queue/reorder", json={"task_ids": [second, third, first]}).json()

        self.assertEqual([task["task_id"] for task in promoted["waiting"]], [third, first, second])
        self.assertEqual([task["task_id"] for task in reordered["waiting"]], [second, third, first])
    def test_queue_delete_running_task_requests_cancellation_and_keeps_history(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)
            created = client.post("/api/generate", data={"prompt": "running", "size": "1024x1024"})
            task_id = created.json()["task"]["task_id"]
            app.state.queue_storage.remove_waiting(task_id)
            app.state.queue_storage.set_running("codex:local", task_id, auth_source="codex")

            deleted = client.delete(f"/api/queue/{task_id}")
            task = client.get(f"/api/tasks/{task_id}").json()["task"]
            queue = client.get("/api/queue").json()

        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()["cancellation_pending"])
        self.assertEqual(task["status"], "cancelling")
        self.assertTrue(task["cancel_requested"])
        self.assertNotIn("cancelled_at", task)
        self.assertEqual(queue["running"][0]["task_id"], task_id)

    def test_queue_batch_cancel_keeps_waiting_and_running_history_and_skips_inactive_tasks(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root,
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            client = TestClient(app)
            running_id = client.post(
                "/api/generate",
                data={"prompt": "running batch cancel", "size": "1024x1024"},
            ).json()["task"]["task_id"]
            waiting_id = client.post(
                "/api/generate",
                data={"prompt": "waiting batch cancel", "size": "1024x1024"},
            ).json()["task"]["task_id"]
            completed_id = client.post(
                "/api/generate",
                data={"prompt": "already completed", "size": "1024x1024"},
            ).json()["task"]["task_id"]
            app.state.queue_storage.remove_waiting(running_id)
            app.state.queue_storage.set_running("codex:local", running_id, auth_source="codex")
            app.state.queue_storage.remove_waiting(completed_id)
            completed = app.state.storage.read_metadata(completed_id)
            completed["status"] = "completed"
            app.state.storage.write_metadata(completed_id, completed)

            response = client.post(
                "/api/queue/cancel-batch",
                json={"task_ids": [waiting_id, running_id, completed_id, "missing-task", waiting_id]},
            )
            queue = client.get("/api/queue").json()
            waiting_task = client.get(f"/api/tasks/{waiting_id}").json()["task"]
            running_task = client.get(f"/api/tasks/{running_id}").json()["task"]
            completed_task = client.get(f"/api/tasks/{completed_id}").json()["task"]

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["summary"],
            {
                "cancelled": 1,
                "cancellation_requested": 1,
                "skipped": 2,
                "failed": 0,
            },
        )
        self.assertEqual(
            payload["results"],
            [
                {
                    "task_id": waiting_id,
                    "result": "cancelled",
                    "previous_state": "waiting",
                    "cancellation_pending": False,
                },
                {
                    "task_id": running_id,
                    "result": "cancellation_requested",
                    "previous_state": "running",
                    "cancellation_pending": True,
                },
                {"task_id": completed_id, "result": "skipped", "reason": "not_active"},
                {"task_id": "missing-task", "result": "skipped", "reason": "not_active"},
            ],
        )
        self.assertEqual(queue["waiting"], [])
        self.assertEqual(queue["running"][0]["task_id"], running_id)
        self.assertEqual(waiting_task["status"], "failed")
        self.assertEqual(waiting_task["error"], "Task cancelled by user.")
        self.assertTrue(waiting_task["cancel_requested"])
        self.assertTrue(waiting_task["cancelled_at"])
        self.assertEqual(running_task["status"], "cancelling")
        self.assertTrue(running_task["cancel_requested"])
        self.assertNotIn("cancelled_at", running_task)
        self.assertEqual(completed_task["status"], "completed")

    def test_queue_batch_cancel_requires_at_least_one_task_id(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), auth_checker=lambda: True, auto_start_queue=False)
            response = TestClient(app).post("/api/queue/cancel-batch", json={"task_ids": []})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "At least one task id is required")
    def test_accept_partial_task_successes_marks_completed_and_reindexes_outputs(self) -> None:
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
            created = client.post("/api/generate", data={"prompt": "accept partial", "size": "1024x1024", "quality": "low", "n": "4"})
            task_id = created.json()["task"]["task_id"]

            asyncio.run(app.state.queue_manager.run_available_once())
            partial = client.get(f"/api/tasks/{task_id}").json()["task"]
            response = client.post(f"/api/tasks/{task_id}/accept-successes")
            accepted = response.json()["task"]
            stored = client.get(f"/api/tasks/{task_id}").json()["task"]
            output_files_exist = [(root / output_name(task_id, index)).exists() for index in (1, 2, 3, 4)]

        partial_completed_indices = [
            item["index"] for item in partial["outputs"] if item["status"] == "completed"
        ]
        self.assertEqual(partial["status"], "partial_failed")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(accepted["status"], "completed")
        self.assertEqual(accepted["generated_count"], 2)
        self.assertEqual(accepted["failed_count"], 0)
        self.assertEqual(accepted["total_count"], 2)
        self.assertEqual(accepted["original_total_count"], 4)
        self.assertEqual(accepted["cleared_failed_count"], 2)
        self.assertIn("partial_failure_cleared_at", accepted)
        self.assertEqual(accepted["terminal_at"], partial["terminal_at"])
        self.assertNotEqual(accepted["terminal_at"], accepted["updated_at"])
        self.assertEqual(accepted["viewed_at"], accepted["updated_at"])
        self.assertEqual(accepted["partial_failure_cleared_at"], accepted["updated_at"])
        self.assertNotIn("error", accepted)
        self.assertNotIn("last_error", accepted)
        self.assertNotIn("retrying_failed_slots", accepted)
        self.assertEqual(
            [(item["index"], item["status"]) for item in accepted["outputs"]],
            [(1, "completed"), (2, "completed")],
        )
        self.assertEqual(
            accepted["output_urls"],
            [output_url(task_id, index) for index in partial_completed_indices],
        )
        self.assertEqual(stored["status"], "completed")
        self.assertEqual(stored["total_count"], 2)
        self.assertEqual(stored["terminal_at"], partial["terminal_at"])
        self.assertEqual(stored["viewed_at"], stored["updated_at"])
        self.assertEqual(
            output_files_exist,
            [index in partial_completed_indices for index in (1, 2, 3, 4)],
        )
    def test_accept_failed_task_successes_after_interruption(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root,
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            storage = app.state.storage
            task_id = "20260517150500-interrupted"
            output_paths = {index: storage.write_output(task_id, b"image", "png", index=index) for index in (1, 2, 3)}
            output_records = [
                {
                    "index": index,
                    "status": "completed",
                    "file": storage.output_file(output_paths[index]),
                    "url": output_url(task_id, index),
                }
                for index in (1, 2, 3)
            ]
            storage.write_metadata(
                task_id,
                {
                    "task_id": task_id,
                    "created_at": "2026-05-17T00:00:00+00:00",
                    "updated_at": "2026-05-17T00:01:00+00:00",
                    "mode": "generate",
                    "status": "failed",
                    "prompt": "interrupted partial outputs",
                    "prompt_for_model": "interrupted partial outputs",
                    "params": {"size": "1024x1024", "quality": "low", "n": 4},
                    "input_files": [],
                    "gallery_refs": [],
                    "reference_assets": [],
                    "generated_count": 3,
                    "failed_count": 0,
                    "total_count": 4,
                    "output_file": storage.output_file(output_paths[1]),
                    "output_files": [storage.output_file(output_paths[index]) for index in (1, 2, 3)],
                    "output_url": output_url(task_id, 1),
                    "output_urls": [output_url(task_id, index) for index in (1, 2, 3)],
                    "outputs": output_records,
                    "last_error": "Service restarted before this task completed.",
                    "error": "Service restarted before this task completed.",
                },
            )
            client = TestClient(app)
            response = client.post(f"/api/tasks/{task_id}/accept-successes")
            self.assertEqual(response.status_code, 200, response.text)
            accepted = response.json()["task"]

        self.assertEqual(accepted["status"], "completed")
        self.assertEqual(accepted["generated_count"], 3)
        self.assertEqual(accepted["failed_count"], 0)
        self.assertEqual(accepted["total_count"], 3)
        self.assertEqual(accepted["original_total_count"], 4)
        self.assertEqual(accepted["cleared_failed_count"], 1)
        self.assertNotIn("error", accepted)
        self.assertNotIn("last_error", accepted)
        self.assertEqual(
            [(item["index"], item["status"]) for item in accepted["outputs"]],
            [(1, "completed"), (2, "completed"), (3, "completed")],
        )
    def test_accept_orphaned_running_task_successes_after_interruption(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root,
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            storage = app.state.storage
            task_id = "20260520103352-orphaned"
            output_path = storage.write_output(task_id, b"image", "png", index=1)
            storage.write_metadata(
                task_id,
                {
                    "task_id": task_id,
                    "created_at": "2026-05-20T02:33:52+00:00",
                    "updated_at": "2026-05-20T02:36:23+00:00",
                    "mode": "generate",
                    "status": "running",
                    "prompt": "orphaned partial output",
                    "prompt_for_model": "orphaned partial output",
                    "params": {"size": "1024x1024", "quality": "low", "n": 2},
                    "input_files": [],
                    "gallery_refs": [],
                    "reference_assets": [],
                    "generated_count": 1,
                    "failed_count": 0,
                    "total_count": 2,
                    "output_file": storage.output_file(output_path),
                    "output_files": [storage.output_file(output_path)],
                    "output_url": output_url(task_id, 1),
                    "output_urls": [output_url(task_id, 1)],
                    "outputs": [
                        {
                            "index": 1,
                            "status": "completed",
                            "file": storage.output_file(output_path),
                            "url": output_url(task_id, 1),
                        }
                    ],
                    "last_error": "Service restarted before this task completed.",
                    "error": "Service restarted before this task completed.",
                },
            )

            client = TestClient(app)
            response = client.post(f"/api/tasks/{task_id}/accept-successes")

        self.assertEqual(response.status_code, 200, response.text)
        accepted = response.json()["task"]
        self.assertEqual(accepted["status"], "completed")
        self.assertEqual(accepted["generated_count"], 1)
        self.assertEqual(accepted["failed_count"], 0)
        self.assertEqual(accepted["total_count"], 1)
        self.assertEqual(accepted["original_total_count"], 2)
        self.assertNotIn("error", accepted)
        self.assertNotIn("last_error", accepted)
    def test_orphaned_running_task_list_marks_running_slots_failed(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root,
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            task_id = "20260520103800-orphaned-running-slot"
            app.state.storage.write_metadata(
                task_id,
                {
                    "task_id": task_id,
                    "created_at": "2026-05-20T02:38:00+00:00",
                    "updated_at": "2026-05-20T02:39:00+00:00",
                    "mode": "generate",
                    "status": "running",
                    "prompt": "orphaned running output slot",
                    "prompt_for_model": "orphaned running output slot",
                    "params": {"size": "1024x1024", "quality": "low", "n": 1},
                    "generated_count": 0,
                    "failed_count": 0,
                    "total_count": 1,
                    "outputs": [{"index": 1, "status": "running", "started_at": "2026-05-20T02:38:01+00:00"}],
                },
            )

            client = TestClient(app)
            response = client.get("/api/tasks")

        self.assertEqual(response.status_code, 200, response.text)
        task = response.json()["tasks"][0]
        self.assertEqual(task["status"], "failed")
        self.assertTrue(task["orphaned_running"])
        self.assertEqual(task["generated_count"], 0)
        self.assertEqual(task["failed_count"], 1)
        self.assertEqual(task["outputs"][0]["status"], "failed")
        self.assertIn("任务已中断", task["outputs"][0]["error"])
    def test_failed_task_list_marks_stale_running_slots_failed(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root,
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            task_id = "20260520103900-failed-stale-running-slot"
            app.state.storage.write_metadata(
                task_id,
                {
                    "task_id": task_id,
                    "created_at": "2026-05-20T02:39:00+00:00",
                    "updated_at": "2026-05-20T02:40:00+00:00",
                    "mode": "generate",
                    "status": "failed",
                    "prompt": "failed with stale running output slot",
                    "prompt_for_model": "failed with stale running output slot",
                    "params": {"size": "1024x1024", "quality": "low", "n": 1},
                    "generated_count": 0,
                    "failed_count": 0,
                    "total_count": 1,
                    "outputs": [{"index": 1, "status": "running", "started_at": "2026-05-20T02:39:01+00:00"}],
                    "error": "Service restarted before this task completed.",
                    "last_error": "Service restarted before this task completed.",
                },
            )

            client = TestClient(app)
            response = client.get("/api/tasks")

        self.assertEqual(response.status_code, 200, response.text)
        task = response.json()["tasks"][0]
        self.assertEqual(task["status"], "failed")
        self.assertEqual(task["generated_count"], 0)
        self.assertEqual(task["failed_count"], 1)
        self.assertEqual(task["outputs"][0]["status"], "failed")
        self.assertEqual(task["outputs"][0]["error"], "Service restarted before this task completed.")
    def test_retry_failed_outputs_requeues_only_failed_slots(self) -> None:
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
            created = client.post("/api/generate", data={"prompt": "retry failed slot", "size": "1024x1024", "quality": "low", "n": "4"})
            task_id = created.json()["task"]["task_id"]

            asyncio.run(app.state.queue_manager.run_available_once())
            partial = client.get(f"/api/tasks/{task_id}").json()["task"]
            retry_response = client.post(f"/api/tasks/{task_id}/retry-failed")
            queued = retry_response.json()["task"]
            queue_after_retry = app.state.queue_storage.read_state()

            asyncio.run(app.state.queue_manager.run_available_once())
            retried = client.get(f"/api/tasks/{task_id}").json()["task"]
            output_files_exist = [(root / output_name(task_id, index)).exists() for index in (1, 2, 3, 4)]

        partial_completed_indices = [
            item["index"] for item in partial["outputs"] if item["status"] == "completed"
        ]
        partial_failed_indices = [
            item["index"] for item in partial["outputs"] if item["status"] == "failed"
        ]
        self.assertEqual(partial["status"], "partial_failed")
        self.assertEqual(
            partial["output_urls"],
            [output_url(task_id, index) for index in partial_completed_indices],
        )
        self.assertEqual(retry_response.status_code, 200)
        self.assertEqual(queued["status"], "queued")
        self.assertEqual(queued["retrying_failed_slots"], partial_failed_indices)
        self.assertEqual(queued["attempts"], 0)
        self.assertIn(task_id, queue_after_retry["waiting"])
        self.assertEqual(len(fake.generate_calls), 6)
        self.assertEqual(retried["status"], "completed")
        self.assertEqual(retried["generated_count"], 4)
        self.assertEqual(retried["failed_count"], 0)
        self.assertEqual(
            retried["output_urls"],
            [output_url(task_id, 1), output_url(task_id, 2), output_url(task_id, 3), output_url(task_id, 4)],
        )
        self.assertEqual(
            [(item["index"], item["status"]) for item in retried["outputs"]],
            [(1, "completed"), (2, "completed"), (3, "completed"), (4, "completed")],
        )
        self.assertEqual(output_files_exist, [True, True, True, True])
    def test_retry_failed_outputs_allows_partial_generic_invalid_request(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root,
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            storage = app.state.storage
            task_id = "20260611065711-19806368"
            output_path = storage.write_output(task_id, b"generated-1", "png", index=1)
            generic_error = (
                'OpenAI-compatible images request failed: HTTP 400: {"error":'
                '{"message":"err","type":"invalid_request_error","param":"","code":"ERR-99E8C62955"}}'
            )
            storage.write_metadata(
                task_id,
                {
                    "task_id": task_id,
                    "created_at": "2026-06-11T06:57:11+00:00",
                    "updated_at": "2026-06-11T06:59:08+00:00",
                    "mode": "generate",
                    "status": "partial_failed",
                    "prompt": "retry generic invalid request",
                    "prompt_for_model": "retry generic invalid request",
                    "params": {"size": "1024x1024", "quality": "low", "n": 2},
                    "input_files": [],
                    "gallery_refs": [],
                    "reference_assets": [],
                    "generated_count": 1,
                    "failed_count": 1,
                    "total_count": 2,
                    "output_file": storage.output_file(output_path),
                    "output_files": [storage.output_file(output_path)],
                    "output_url": output_url(task_id, 1),
                    "output_urls": [output_url(task_id, 1)],
                    "outputs": [
                        {"index": 1, "status": "completed", "file": storage.output_file(output_path), "url": output_url(task_id, 1)},
                        {"index": 2, "status": "failed", "error": generic_error, "attempts": 1},
                    ],
                    "last_error": f"1 of 2 images failed: {generic_error}",
                },
            )
            client = TestClient(app)
            partial = client.get(f"/api/tasks/{task_id}").json()["task"]
            retry_response = client.post(f"/api/tasks/{task_id}/retry-failed")
            queued = retry_response.json()["task"]
            queue_after_retry = app.state.queue_storage.read_state()

        self.assertEqual(partial["status"], "partial_failed")
        self.assertEqual(partial["generated_count"], 1)
        self.assertEqual(partial["failed_count"], 1)
        self.assertIn("invalid_request_error", partial["last_error"])
        self.assertEqual(retry_response.status_code, 200, retry_response.text)
        self.assertEqual(queued["status"], "queued")
        self.assertEqual(queued["retrying_failed_slots"], [2])
        self.assertEqual(queue_after_retry["waiting"], [task_id])
    def test_task_metadata_accept_successes_reindexes_completed_outputs(self) -> None:
        from codex_image.webui.task_metadata import _accept_partial_task_successes
        from codex_image.webui.storage import TaskStorage

        with tempfile.TemporaryDirectory() as tmp:
            storage = TaskStorage(Path(tmp) / "outputs")
            task = storage.create_task("generate")
            metadata = {
                "task_id": task.task_id,
                "created_at": "2026-05-21T00:00:00Z",
                "updated_at": "2026-05-21T00:00:00Z",
                "viewed_at": "2026-05-21T00:00:00Z",
                "mode": "generate",
                "status": "partial_failed",
                "prompt": "test",
                "prompt_for_model": "test",
                "params": {"n": 3},
                "outputs": [
                    {"index": 1, "status": "completed", "file": "20260521/a.png", "url": "/outputs/20260521/a.png"},
                    {"index": 2, "status": "failed", "error": "bad"},
                    {"index": 3, "status": "completed", "file": "20260521/c.png", "url": "/outputs/20260521/c.png"},
                ],
                "generated_count": 2,
                "failed_count": 1,
                "total_count": 3,
            }
            storage.write_metadata(task.task_id, metadata)

            accepted = _accept_partial_task_successes(storage, task.task_id, metadata)

        self.assertEqual(accepted["status"], "completed")
        self.assertEqual(accepted["generated_count"], 2)
        self.assertEqual(accepted["failed_count"], 0)
        self.assertEqual([item["index"] for item in accepted["outputs"]], [1, 2])
        self.assertEqual(accepted["original_total_count"], 3)
        self.assertEqual(accepted["cleared_failed_count"], 1)
        self.assertEqual(accepted["viewed_at"], accepted["updated_at"])
        self.assertEqual(accepted["partial_failure_cleared_at"], accepted["updated_at"])
    def test_retry_failed_orphaned_running_task_requeues_missing_slots_only(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root,
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            storage = app.state.storage
            task_id = "20260520103420-orphaned-retry"
            output_path = storage.write_output(task_id, b"image", "png", index=1)
            storage.write_metadata(
                task_id,
                {
                    "task_id": task_id,
                    "created_at": "2026-05-20T02:34:20+00:00",
                    "updated_at": "2026-05-20T02:36:23+00:00",
                    "mode": "generate",
                    "status": "running",
                    "prompt": "orphaned retry missing slot",
                    "prompt_for_model": "orphaned retry missing slot",
                    "params": {"size": "1024x1024", "quality": "low", "n": 2},
                    "input_files": [],
                    "gallery_refs": [],
                    "reference_assets": [],
                    "generated_count": 1,
                    "failed_count": 0,
                    "total_count": 2,
                    "output_file": storage.output_file(output_path),
                    "output_files": [storage.output_file(output_path)],
                    "output_url": output_url(task_id, 1),
                    "output_urls": [output_url(task_id, 1)],
                    "outputs": [
                        {
                            "index": 1,
                            "status": "completed",
                            "file": storage.output_file(output_path),
                            "url": output_url(task_id, 1),
                        }
                    ],
                    "last_error": "Service restarted before this task completed.",
                    "error": "Service restarted before this task completed.",
                },
            )

            client = TestClient(app)
            response = client.post(f"/api/tasks/{task_id}/retry-failed")
            queue_after_retry = app.state.queue_storage.read_state()

        self.assertEqual(response.status_code, 200, response.text)
        queued = response.json()["task"]
        self.assertEqual(queued["status"], "queued")
        self.assertEqual(queued["retrying_failed_slots"], [2])
        self.assertEqual(queue_after_retry["waiting"], [task_id])
    def test_retry_failed_outputs_rejects_non_retryable_error(self) -> None:
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
            client = TestClient(app)
            created = client.post(
                "/api/generate",
                data={"prompt": "bad retry", "size": "1024x1024", "quality": "low", "n": "2", "codex_mode": "responses"},
            )
            task_id = created.json()["task"]["task_id"]

            with self.assertRaisesRegex(RuntimeError, "invalid_request_error"):
                asyncio.run(app.state.queue_manager.run_available_once())
            retry_response = client.post(f"/api/tasks/{task_id}/retry-failed")
            queue_state = app.state.queue_storage.read_state()

        self.assertEqual(retry_response.status_code, 409)
        self.assertIn("No retryable failed image slots", retry_response.json()["detail"])
        self.assertEqual(queue_state["waiting"], [])
        self.assertEqual(len(fake.generate_calls), 1)
    def test_api_provider_metadata_is_returned_for_cards_detail_and_request_preview_without_key(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "tasks",
                auth_settings_path=root / "auth-settings.json",
                api_settings_path=root / "api-settings.json",
                auto_start_queue=False,
            )
            client = TestClient(app)
            client.patch(
                "/api/api-settings",
                json={
                    "active_provider_id": "vendor-a",
                    "providers": [
                        {
                            "id": "vendor-a",
                            "name": "Vendor A",
                            "base_url": "https://vendor-a.example.com/v1",
                            "api_key": "test-api-key-vendor-a-secret",
                            "image_model": "vendor-a-image",
                            "api_mode": "images",
                        },
                        {
                            "id": "vendor-b",
                            "name": "Vendor B",
                            "base_url": "https://vendor-b.example.com/v1",
                            "api_key": "test-api-key-vendor-b-secret",
                            "image_model": "vendor-b-image",
                            "api_mode": "images",
                        },
                    ],
                },
            )
            client.patch("/api/auth", json={"source": "api"})

            response = client.post(
                "/api/generate",
                data={
                    "prompt": "api provider visible",
                    "size": "1024x1024",
                    "quality": "low",
                    "api_provider_id": "vendor-b",
                },
            )
            body = response.json()
            task_id = body["task"]["task_id"]
            listed_task = client.get("/api/tasks").json()["tasks"][0]
            detail_task = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertEqual(response.status_code, 200)
        for task in (body["task"], listed_task, detail_task):
            self.assertEqual(task["api_provider_id"], "vendor-b")
            self.assertEqual(task["api_provider_name"], "Vendor B")
            self.assertEqual(task["params"]["api_provider_id"], "vendor-b")
            self.assertNotIn("api_key", task)
        for request_payload in (body["request"], detail_task["request"]):
            self.assertEqual(request_payload["webui_api_provider_id"], "vendor-b")
            self.assertEqual(request_payload["webui_api_provider_name"], "Vendor B")
            self.assertNotIn("api_key", request_payload)
        payload_text = json.dumps({"body": body, "listed": listed_task, "detail": detail_task}, ensure_ascii=False)
        self.assertNotIn("test-api-key-vendor-a-secret", payload_text)
        self.assertNotIn("test-api-key-vendor-b-secret", payload_text)
    def test_startup_migrates_legacy_task_directory_to_dated_output_storage(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_id = "20260501000000-legacy1"
            task_dir = root / task_id
            (task_dir / "inputs").mkdir(parents=True)
            (task_dir / "inputs" / "input.png").write_bytes(b"input")
            (task_dir / "image-1.png").write_bytes(b"output")
            (task_dir / "request.json").write_text(json.dumps({"model": "gpt-5.4"}), encoding="utf-8")
            (task_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "created_at": "2026-05-01T00:00:00+00:00",
                        "updated_at": "2026-05-01T00:00:00+00:00",
                        "mode": "generate",
                        "status": "completed",
                        "prompt": "legacy",
                        "params": {"output_format": "png"},
                        "input_files": ["input.png"],
                        "output_files": ["image-1.png"],
                        "output_file": "image-1.png",
                    }
                ),
                encoding="utf-8",
            )

            app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            task = TestClient(app).get(f"/api/tasks/{task_id}").json()["task"]
            task_dir_exists = task_dir.exists()
            migrated_input_exists = (root / "inputs" / input_name(task_id, "input.png")).exists()
            migrated_output_exists = (root / output_name(task_id)).exists()
            migrated_request_exists = request_path(root, task_id).exists()

        self.assertFalse(task_dir_exists)
        self.assertEqual(task["input_files"], [input_name(task_id, "input.png")])
        self.assertEqual(task["input_urls"], [f"/inputs/{input_name(task_id, 'input.png')}"])
        self.assertEqual(task["output_files"], [output_name(task_id)])
        self.assertEqual(task["output_urls"], [output_url(task_id)])
        self.assertTrue(migrated_input_exists)
        self.assertTrue(migrated_output_exists)
        self.assertTrue(migrated_request_exists)
    def test_delete_completed_task_removes_task_directory(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: FakeImageClient(), auth_checker=lambda: True)
            task = app.state.storage.create_task("generate")
            app.state.storage.write_metadata(
                task.task_id,
                {
                    "task_id": task.task_id,
                    "created_at": "2026-04-24T01:00:00+00:00",
                    "status": "completed",
                    "input_files": [],
                },
            )

            response = TestClient(app).delete(f"/api/tasks/{task.task_id}")

            task_exists = app.state.storage.metadata_path(task.task_id).exists()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(task_exists)

    def test_delete_task_removes_duplicate_legacy_directory_and_prevents_restart_recovery(self) -> None:
        from codex_image.webui.app import create_app

        task_id = "20260726010203-abcdef01"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            modern_metadata = metadata_path(root, task_id)
            modern_metadata.parent.mkdir(parents=True, exist_ok=True)
            modern_metadata.write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "created_at": "2026-07-26T01:02:03+00:00",
                        "updated_at": "2026-07-26T01:03:03+00:00",
                        "status": "completed",
                        "output_files": [output_name(task_id)],
                        "output_urls": [output_url(task_id)],
                    }
                ),
                encoding="utf-8",
            )
            modern_output = root / output_name(task_id)
            modern_output.parent.mkdir(parents=True, exist_ok=True)
            modern_output.write_bytes(b"modern")

            legacy_dir = root / task_id
            legacy_dir.mkdir()
            (legacy_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "created_at": "2026-07-26T01:02:03+00:00",
                        "status": "completed",
                        "output_files": ["legacy-image.png"],
                    }
                ),
                encoding="utf-8",
            )
            (legacy_dir / "request.json").write_text("{}", encoding="utf-8")
            (legacy_dir / "legacy-image.png").write_bytes(b"legacy")

            first_app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            deleted = TestClient(first_app).delete(f"/api/tasks/{task_id}")
            legacy_dir_exists_after_delete = legacy_dir.exists()

            restarted_app = create_app(output_root=root, auth_checker=lambda: True, auto_start_queue=False)
            restored = TestClient(restarted_app).get(f"/api/tasks/{task_id}")

        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(modern_output.exists())
        self.assertFalse(legacy_dir_exists_after_delete)
        self.assertEqual(restored.status_code, 404)

    def test_delete_running_task_is_rejected(self) -> None:
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
                    "status": "running",
                    "input_files": [],
                },
            )

            response = TestClient(app).delete(f"/api/tasks/{task.task_id}")

            task_exists = app.state.storage.metadata_path(task.task_id).exists()

        self.assertEqual(response.status_code, 409)
        self.assertTrue(task_exists)
