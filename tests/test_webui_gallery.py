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


class WebUIGalleryTests(unittest.TestCase):
    def test_gallery_crud_routes_manage_public_library(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "tasks",
                gallery_root=root / "gallery",
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
            )
            client = TestClient(app)
            created = client.post(
                "/api/gallery",
                data={"name": "小美", "category": "portrait"},
                files={"image": ("portrait.png", b"gallery-bytes", "image/png")},
            )
            item = created.json()["item"]
            listed = client.get("/api/gallery", params={"category": "portrait"}).json()["items"]
            image_response = client.get(item["image_url"])
            renamed = client.patch(f"/api/gallery/{item['id']}", json={"name": "小美新版", "category": "character"})
            deleted = client.delete(f"/api/gallery/{item['id']}")
            after_delete = client.get("/api/gallery").json()["items"]

        self.assertEqual(created.status_code, 200)
        self.assertEqual(item["name"], "小美")
        self.assertEqual(item["category"], "portrait")
        self.assertEqual(listed[0]["image_url"], f"/api/gallery/{item['id']}/image")
        self.assertEqual(image_response.content, b"gallery-bytes")
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["item"]["category"], "character")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(after_delete, [])
    def test_gallery_route_replaces_item_image(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "tasks",
                gallery_root=root / "gallery",
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            client = TestClient(app)
            created = client.post(
                "/api/gallery",
                data={"name": "小美", "category": "portrait"},
                files={"image": ("portrait.png", b"old-bytes", "image/png")},
            )
            item = created.json()["item"]
            replaced = client.put(
                f"/api/gallery/{item['id']}/image",
                files={"image": ("replacement.webp", b"new-bytes", "image/webp")},
            )
            image_response = client.get(item["image_url"])

        self.assertEqual(replaced.status_code, 200)
        self.assertEqual(replaced.json()["item"]["id"], item["id"])
        self.assertEqual(replaced.json()["item"]["filename"], "replacement.webp")
        self.assertEqual(replaced.json()["item"]["mime_type"], "image/webp")
        self.assertEqual(image_response.content, b"new-bytes")
    def test_gallery_category_routes_manage_custom_categories_and_prompt_metadata(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "tasks",
                gallery_root=root / "gallery",
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            client = TestClient(app)
            created_category = client.post(
                "/api/gallery/categories",
                json={"name": "风格参考", "prompt_role": "风格参考"},
            )
            category = created_category.json()["category"]
            created_item = client.post(
                "/api/gallery",
                data={
                    "name": "冷调样片",
                    "category": category["id"],
                    "prompt_note": "只参考色调和光影，不参考构图。",
                },
                files={"image": ("style.png", b"style-bytes", "image/png")},
            )
            patched_category = client.patch(
                f"/api/gallery/categories/{category['id']}",
                json={"name": "常用风格", "prompt_role": "风格方向", "order": 5},
            )
            target_category = client.post(
                "/api/gallery/categories",
                json={"name": "迁移目标", "prompt_role": "角色参考"},
            ).json()["category"]
            deleted_category = client.delete(
                f"/api/gallery/categories/{category['id']}",
                params={"move_to": target_category["id"]},
            )
            listed = client.get("/api/gallery", params={"category": target_category["id"]}).json()

        self.assertEqual(created_category.status_code, 200)
        self.assertEqual(category["name"], "风格参考")
        self.assertEqual(category["prompt_role"], "风格参考")
        self.assertEqual(created_item.status_code, 200)
        self.assertEqual(created_item.json()["item"]["prompt_note"], "只参考色调和光影，不参考构图。")
        self.assertEqual(patched_category.status_code, 200)
        self.assertEqual(patched_category.json()["category"]["name"], "常用风格")
        self.assertEqual(patched_category.json()["category"]["prompt_role"], "风格方向")
        self.assertEqual(deleted_category.status_code, 200)
        self.assertEqual(listed["items"][0]["category"], target_category["id"])
        self.assertEqual(listed["items"][0]["category_prompt_role"], "角色参考")

    def test_gallery_reorder_routes_persist_category_and_item_order(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "tasks",
                gallery_root=root / "gallery",
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            client = TestClient(app)
            categories = client.get("/api/gallery/categories").json()["categories"]
            reordered_category_ids = ["product", "portrait", "character"]
            reordered_categories = client.patch(
                "/api/gallery/categories/reorder",
                json={"category_ids": reordered_category_ids},
            )
            first = client.post(
                "/api/gallery",
                data={"name": "一号模特", "category": "portrait"},
                files={"image": ("first.png", b"first", "image/png")},
            ).json()["item"]
            second = client.post(
                "/api/gallery",
                data={"name": "二号模特", "category": "portrait"},
                files={"image": ("second.png", b"second", "image/png")},
            ).json()["item"]
            third = client.post(
                "/api/gallery",
                data={"name": "三号模特", "category": "portrait"},
                files={"image": ("third.png", b"third", "image/png")},
            ).json()["item"]
            reordered_items = client.patch(
                "/api/gallery/reorder",
                json={"category": "portrait", "item_ids": [third["id"], first["id"], second["id"]]},
            )
            listed = client.get("/api/gallery", params={"category": "portrait"}).json()["items"]
            listed_categories = client.get("/api/gallery/categories").json()["categories"]

        self.assertEqual(categories[0]["id"], "portrait")
        self.assertEqual(reordered_categories.status_code, 200)
        self.assertEqual([category["id"] for category in reordered_categories.json()["categories"][:3]], reordered_category_ids)
        self.assertEqual(reordered_items.status_code, 200)
        self.assertEqual([item["id"] for item in reordered_items.json()["items"]], [third["id"], first["id"], second["id"]])
        self.assertEqual([item["id"] for item in listed], [third["id"], first["id"], second["id"]])
        self.assertEqual([category["id"] for category in listed_categories[:3]], reordered_category_ids)
    def test_gallery_route_rejects_duplicate_names(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "tasks",
                gallery_root=root / "gallery",
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
            )
            client = TestClient(app)
            first = client.post(
                "/api/gallery",
                data={"name": "产品图", "category": "product"},
                files={"image": ("product.png", b"one", "image/png")},
            )
            duplicate = client.post(
                "/api/gallery",
                data={"name": " 产品图 ", "category": "product"},
                files={"image": ("product2.png", b"two", "image/png")},
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(duplicate.status_code, 409)
    def test_reference_asset_routes_list_and_serve_recent_uploads(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)
            created = client.post(
                "/api/generate",
                data={"prompt": "asset upload", "size": "1024x1024"},
                files={"reference_images": ("source.png", b"same-image-bytes", "image/png")},
            )
            item = created.json()["task"]["reference_assets"][0]
            recent = client.get("/api/reference-assets/recent").json()["items"]
            image = client.get(item["image_url"])

        self.assertEqual(created.status_code, 200)
        self.assertEqual(recent[0]["id"], item["id"])
        self.assertEqual(recent[0]["image_url"], f"/api/reference-assets/{item['id']}/image")
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.content, b"same-image-bytes")
        self.assertEqual(image.headers["content-type"], "image/png")
    def test_reference_asset_route_deletes_recent_upload(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)
            created = client.post(
                "/api/generate",
                data={"prompt": "asset upload", "size": "1024x1024"},
                files={"reference_images": ("source.png", b"delete-me", "image/png")},
            )
            item = created.json()["task"]["reference_assets"][0]
            deleted = client.delete(f"/api/reference-assets/{item['id']}")
            recent = client.get("/api/reference-assets/recent?limit=50").json()["items"]
            image = client.get(item["image_url"])

        self.assertEqual(created.status_code, 200)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json(), {"ok": True})
        self.assertEqual(recent, [])
        self.assertEqual(image.status_code, 404)
    def test_edit_route_accepts_selected_reference_asset_without_upload(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)
            created = client.post(
                "/api/generate",
                data={"prompt": "seed asset", "size": "1024x1024"},
                files={"reference_images": ("source.png", b"asset-bytes", "image/png")},
            )
            asset_id = created.json()["task"]["reference_assets"][0]["id"]
            edited = client.post(
                "/api/edit",
                data={"prompt": "edit asset", "size": "1024x1024", "reference_asset_ids": asset_id},
            )
            task = edited.json()["task"]

        self.assertEqual(edited.status_code, 200)
        self.assertEqual(task["input_files"], [])
        self.assertEqual(task["reference_assets"][0]["id"], asset_id)
        self.assertEqual(task["input_sources"][0]["kind"], "asset")
    def test_queue_worker_does_not_touch_reference_asset_again(self) -> None:
        from codex_image.webui.app import create_app

        fake = FakeImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, client_factory=lambda: fake, auth_checker=lambda: True, batch_delay_seconds=0, auto_start_queue=False)
            client = TestClient(app)
            created = client.post(
                "/api/generate",
                data={"prompt": "use asset once", "size": "1024x1024", "quality": "low"},
                files={"reference_images": ("source.png", b"asset-once", "image/png")},
            )
            asset_id = created.json()["task"]["reference_assets"][0]["id"]
            used_count_after_submit = app.state.reference_asset_storage.read_item(asset_id)["used_count"]

            asyncio.run(app.state.queue_manager.run_available_once())
            used_count_after_run = app.state.reference_asset_storage.read_item(asset_id)["used_count"]

        self.assertEqual(used_count_after_run, used_count_after_submit)
        self.assertEqual(len(fake.generate_calls), 1)
    def test_queue_worker_does_not_requeue_missing_reference_asset(self) -> None:
        from codex_image.webui.app import create_app

        fake = FakeImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, client_factory=lambda: fake, auth_checker=lambda: True, batch_delay_seconds=0, auto_start_queue=False)
            app.state.queue_manager.max_attempts = 3
            client = TestClient(app)
            created = client.post(
                "/api/generate",
                data={"prompt": "missing asset", "size": "1024x1024", "quality": "low"},
                files={"reference_images": ("source.png", b"will-disappear", "image/png")},
            )
            task_id = created.json()["task"]["task_id"]
            asset_id = created.json()["task"]["reference_assets"][0]["id"]
            app.state.reference_asset_storage.image_path(asset_id).unlink()

            with self.assertRaisesRegex(RuntimeError, "Reference asset not found"):
                asyncio.run(app.state.queue_manager.run_available_once())
            task = client.get(f"/api/tasks/{task_id}").json()["task"]
            queue_state = app.state.queue_storage.read_state()

        self.assertEqual(fake.generate_calls, [])
        self.assertEqual(task["status"], "failed")
        self.assertEqual(task["attempts"], 1)
        self.assertIn("Reference asset not found", task["last_error"])
        self.assertEqual(queue_state["waiting"], [])
        self.assertEqual(queue_state["running"], {})
    def test_retry_failed_rejects_missing_reference_asset_failure(self) -> None:
        from codex_image.webui.app import create_app

        fake = FakeImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, client_factory=lambda: fake, auth_checker=lambda: True, batch_delay_seconds=0, auto_start_queue=False)
            app.state.queue_manager.max_attempts = 3
            client = TestClient(app)
            created = client.post(
                "/api/generate",
                data={"prompt": "missing asset retry", "size": "1024x1024", "quality": "low"},
                files={"reference_images": ("source.png", b"retry-disappear", "image/png")},
            )
            task_id = created.json()["task"]["task_id"]
            asset_id = created.json()["task"]["reference_assets"][0]["id"]
            app.state.reference_asset_storage.image_path(asset_id).unlink()

            with self.assertRaisesRegex(RuntimeError, "Reference asset not found"):
                asyncio.run(app.state.queue_manager.run_available_once())
            retry = client.post(f"/api/tasks/{task_id}/retry-failed")
            queue_state = app.state.queue_storage.read_state()

        self.assertEqual(retry.status_code, 409)
        self.assertEqual(queue_state["waiting"], [])
        self.assertEqual(queue_state["running"], {})
    def test_task_detail_preserves_missing_reference_asset_placeholder(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            task = app.state.storage.create_task("generate")
            missing_id = "0" * 64
            app.state.storage.write_metadata(
                task.task_id,
                {
                    "task_id": task.task_id,
                    "created_at": "2026-05-12T00:00:00+00:00",
                    "updated_at": "2026-05-12T00:00:00+00:00",
                    "mode": "generate",
                    "status": "completed",
                    "prompt": "missing historical asset",
                    "params": {"model": "gpt-image-2"},
                    "input_files": [],
                    "gallery_refs": [],
                    "reference_assets": [{"id": missing_id, "filename": "gone.png", "mime_type": "image/png"}],
                },
            )
            response = TestClient(app).get(f"/api/tasks/{task.task_id}")
            returned = response.json()["task"]

        self.assertEqual(response.status_code, 200)
        self.assertTrue(returned["reference_assets"][0]["missing"])
        self.assertEqual(returned["reference_assets"][0]["id"], missing_id)
        self.assertEqual(returned["reference_assets"][0]["filename"], "gone.png")
        self.assertEqual(returned["reference_assets"][0]["image_url"], "")
        self.assertEqual(returned["input_sources"][0]["kind"], "asset")
        self.assertTrue(returned["input_sources"][0]["missing"])
    def test_old_input_file_metadata_still_enriches_input_urls(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            task = app.state.storage.create_task("generate")
            input_path = app.state.storage.write_input(task.task_id, "legacy.png", b"legacy", index=1)
            app.state.storage.write_metadata(
                task.task_id,
                {"task_id": task.task_id, "created_at": "2026-05-12T00:00:00+00:00", "input_files": [input_path.name]},
            )
            response = TestClient(app).get(f"/api/tasks/{task.task_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["task"]["input_urls"], [f"/inputs/{input_path.name}"])
    def test_generate_route_uses_gallery_images_without_copying_to_task_inputs(self) -> None:
        from codex_image.webui.app import create_app

        fake = FakeImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "tasks",
                gallery_root=root / "gallery",
                client_factory=lambda: fake,
                auth_checker=lambda: True,
            )
            client = TestClient(app)
            gallery_response = client.post(
                "/api/gallery",
                data={"name": "小美", "category": "portrait"},
                files={"image": ("portrait.png", b"gallery-bytes", "image/png")},
            )
            gallery_item = gallery_response.json()["item"]
            response = client.post(
                "/api/generate",
                data={
                    "prompt": "让 @小美 做产品模特",
                    "prompt_for_model": "让 @小美 做产品模特\n\n参考图 1 为「小美」（人像），提示词中的 @小美 指这张图。",
                    "model": "gpt-image-2",
                    "size": "1024x1024",
                    "quality": "low",
                    "output_format": "png",
                    "gallery_image_ids": gallery_item["id"],
                    "codex_mode": "responses",
                },
            )
            body = response.json()
            task = body["task"]
            input_content = body["request"]["input"][0]["content"]
            input_dir = root / "tasks" / "inputs"
            input_dir_files = list(input_dir.glob(f"{task['task_id']}-input-*")) if input_dir.exists() else []

        self.assertEqual(response.status_code, 200)
        self.assertEqual(task["prompt"], "让 @小美 做产品模特")
        self.assertIn("参考图 1", task["prompt_for_model"])
        self.assertEqual(task["input_files"], [])
        self.assertEqual(input_dir_files, [])
        self.assertEqual(task["gallery_refs"][0]["id"], gallery_item["id"])
        self.assertEqual(task["input_sources"][0]["kind"], "gallery")
        self.assertTrue(input_content[1]["image_url"].startswith("<redacted image data url, "))
        self.assertEqual(body["request"]["webui_image_refs"]["gallery_refs"][0]["id"], gallery_item["id"])
        self.assertEqual(fake.generate_calls, [])
    def test_generate_route_keeps_gallery_prompt_layer_separate_from_raw_prompt(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "tasks",
                gallery_root=root / "gallery",
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            client = TestClient(app)
            style_category = client.post(
                "/api/gallery/categories",
                json={"name": "常用风格", "prompt_role": "风格方向"},
            ).json()["category"]
            gallery_item = client.post(
                "/api/gallery",
                data={
                    "name": "冷调样片",
                    "category": style_category["id"],
                    "prompt_note": "只参考色调和光影，不参考构图。",
                },
                files={"image": ("style.png", b"style-bytes", "image/png")},
            ).json()["item"]
            prompt = "让 @冷调样片 作为画面气质参考"
            prompt_for_model = (
                f"{prompt}\n\n"
                "参考图说明：\n"
                "- 参考图 1：图库「冷调样片」，用途：风格方向。提示词中的 @冷调样片 指这张图。"
                " 只参考色调和光影，不参考构图。"
            )
            response = client.post(
                "/api/generate",
                data={
                    "prompt": prompt,
                    "prompt_for_model": prompt_for_model,
                    "model": "gpt-image-2",
                    "size": "1024x1024",
                    "quality": "low",
                    "output_format": "png",
                    "gallery_image_ids": gallery_item["id"],
                },
            )
            task = response.json()["task"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(task["prompt"], prompt)
        self.assertEqual(task["prompt_for_model"], prompt_for_model)
        self.assertEqual(task["gallery_refs"][0]["prompt_note"], "只参考色调和光影，不参考构图。")
        self.assertEqual(task["gallery_refs"][0]["category_prompt_role"], "风格方向")
    def test_queue_worker_uses_gallery_mime_for_extensionless_image(self) -> None:
        from codex_image.webui.app import create_app

        fake = FakeImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "tasks",
                gallery_root=root / "gallery",
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            client = TestClient(app)
            gallery_item = client.post(
                "/api/gallery",
                data={"name": "产品图", "category": "product"},
                files={"image": ("jpg", b"\xff\xd8\xff\xe0jpeg-bytes", "image/jpeg")},
            ).json()["item"]
            client.post(
                "/api/generate",
                data={
                    "prompt": "参考 @产品图",
                    "model": "gpt-image-2",
                    "size": "1024x1024",
                    "quality": "low",
                    "output_format": "png",
                    "gallery_image_ids": gallery_item["id"],
                },
            )

            asyncio.run(app.state.queue_manager.run_available_once())

        self.assertEqual(fake.generate_calls[0]["reference_images"][0].split(",", 1)[0], "data:image/jpeg;base64")
    def test_tasks_report_deleted_gallery_references_as_missing(self) -> None:
        from codex_image.webui.app import create_app

        fake = FakeImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "tasks",
                gallery_root=root / "gallery",
                client_factory=lambda: fake,
                auth_checker=lambda: True,
            )
            client = TestClient(app)
            gallery_item = client.post(
                "/api/gallery",
                data={"name": "杯子", "category": "product"},
                files={"image": ("cup.png", b"cup", "image/png")},
            ).json()["item"]
            task = client.post(
                "/api/generate",
                data={
                    "prompt": "参考 @杯子",
                    "model": "gpt-image-2",
                    "size": "1024x1024",
                    "quality": "low",
                    "output_format": "png",
                    "gallery_image_ids": gallery_item["id"],
                },
            ).json()["task"]
            client.delete(f"/api/gallery/{gallery_item['id']}")
            returned = client.get(f"/api/tasks/{task['task_id']}").json()["task"]

        self.assertTrue(returned["gallery_refs"][0]["missing"])
        self.assertEqual(returned["gallery_refs"][0]["image_url"], "")
    def test_task_detail_infers_gallery_refs_from_prompt_when_metadata_lost_them(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.storage import GalleryStorage, TaskStorage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gallery = GalleryStorage(root / "gallery")
            item = gallery.create_item(
                name="2号模特",
                category="portrait",
                filename="portrait.png",
                data=b"portrait",
                content_type="image/png",
            )
            storage = TaskStorage(root / "tasks")
            created = storage.create_task("generate")
            storage.write_metadata(
                created.task_id,
                {
                    "task_id": created.task_id,
                    "created_at": "2026-05-01T00:00:00+00:00",
                    "updated_at": "2026-05-01T00:00:00+00:00",
                    "mode": "generate",
                    "status": "completed",
                    "prompt": "一张写实毕业舞会写真照@2号模特：俯拍七分身构图",
                    "prompt_for_model": "一张写实毕业舞会写真照@2号模特：俯拍七分身构图",
                    "params": {"model": "gpt-image-2"},
                    "gallery_refs": [],
                    "input_sources": [],
                },
            )
            app = create_app(output_root=root / "tasks", gallery_root=root / "gallery", auth_checker=lambda: True, auto_start_queue=False)
            returned = TestClient(app).get(f"/api/tasks/{created.task_id}").json()["task"]

        self.assertEqual(returned["gallery_refs"][0]["id"], item["id"])
        self.assertEqual(returned["gallery_refs"][0]["name"], "2号模特")
        self.assertEqual(returned["input_sources"][0]["kind"], "gallery")
    def test_retry_failed_rejects_missing_reference_asset_after_partial_failure(self) -> None:
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
            app.state.queue_manager.max_attempts = 3
            client = TestClient(app)
            created = client.post(
                "/api/generate",
                data={"prompt": "partial then missing asset", "size": "1024x1024", "quality": "low", "n": "4"},
                files={"reference_images": ("source.png", b"partial-missing", "image/png")},
            )
            task_id = created.json()["task"]["task_id"]
            asset_id = created.json()["task"]["reference_assets"][0]["id"]

            asyncio.run(app.state.queue_manager.run_available_once())
            partial = client.get(f"/api/tasks/{task_id}").json()["task"]
            app.state.reference_asset_storage.image_path(asset_id).unlink()
            first_retry = client.post(f"/api/tasks/{task_id}/retry-failed")
            with self.assertRaisesRegex(RuntimeError, "Reference asset not found"):
                asyncio.run(app.state.queue_manager.run_available_once())
            failed = client.get(f"/api/tasks/{task_id}").json()["task"]
            second_retry = client.post(f"/api/tasks/{task_id}/retry-failed")
            queue_state = app.state.queue_storage.read_state()

        self.assertEqual(partial["status"], "partial_failed")
        self.assertEqual(partial["outputs"][1]["status"], "failed")
        self.assertIn("temporary server failure", partial["outputs"][1]["error"])
        self.assertEqual(first_retry.status_code, 200)
        self.assertEqual(failed["status"], "failed")
        self.assertIn("Reference asset not found", failed["last_error"])
        self.assertEqual(second_retry.status_code, 409)
        self.assertEqual(queue_state["waiting"], [])
        self.assertEqual(queue_state["running"], {})
    def test_startup_migrates_legacy_default_gallery_directory(self) -> None:
        from codex_image.webui.app import create_app

        cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item_id = "20260501000000-gallery"
            old_item_dir = root / "output" / "webui-gallery" / item_id
            old_item_dir.mkdir(parents=True)
            (old_item_dir / "portrait.png").write_bytes(b"gallery-bytes")
            (old_item_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "id": item_id,
                        "name": "旧图库",
                        "name_key": "旧图库",
                        "category": "portrait",
                        "filename": "portrait.png",
                        "mime_type": "image/png",
                        "created_at": "2026-05-01T00:00:00+00:00",
                        "updated_at": "2026-05-01T00:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )
            try:
                os.chdir(root)
                app = create_app(auth_checker=lambda: True, auto_start_queue=False)
                client = TestClient(app)
                listed = client.get("/api/gallery", params={"category": "portrait"}).json()["items"]
                image_response = client.get(listed[0]["image_url"])
                new_item_dir = root / "output" / "webui-inputs" / "gallery" / item_id
                new_image_exists = (new_item_dir / "portrait.png").exists()
                old_item_exists = old_item_dir.exists()
            finally:
                os.chdir(cwd)

        self.assertEqual(listed[0]["id"], item_id)
        self.assertEqual(image_response.content, b"gallery-bytes")
        self.assertTrue(new_image_exists)
        self.assertFalse(old_item_exists)
