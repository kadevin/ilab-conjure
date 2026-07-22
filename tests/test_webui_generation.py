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


class WebUIGenerationTests(unittest.TestCase):
    def _png_bytes(self, size: tuple[int, int] = (400, 640)) -> bytes:
        image = Image.new("RGB", size, (120, 180, 160))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def test_ratio_prompt_instruction_matches_every_supported_interface_language(self) -> None:
        from codex_image.webui.prompt_ratio import ratio_prompt_instruction

        expected = {
            "zh-CN": "将宽高比设为 9:16",
            "zh-TW": "將寬高比設為 9:16",
            "zh-HK": "將寬高比設為 9:16",
            "ja": "アスペクト比を 9:16 に設定してください。",
            "ko": "화면 비율을 9:16로 설정하세요.",
            "en": "Set the aspect ratio to 9:16.",
            "es": "Establece la relación de aspecto en 9:16.",
            "pt": "Defina a proporção da imagem como 9:16.",
            "fr": "Réglez le rapport largeur/hauteur sur 9:16.",
            "de": "Stelle das Seitenverhältnis auf 9:16 ein.",
            "ru": "Установите соотношение сторон 9:16.",
            "it": "Imposta le proporzioni su 9:16.",
            "hi": "पक्षानुपात को 9:16 पर सेट करें।",
        }

        for locale, instruction in expected.items():
            with self.subTest(locale=locale):
                self.assertEqual(ratio_prompt_instruction("9:16", locale=locale), instruction)

    def test_generate_route_persists_task_and_passes_parameters(self) -> None:
        from codex_image.webui.app import create_app

        fake = FakeImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: fake, auth_checker=lambda: True, auto_start_queue=False)
            response = TestClient(app).post(
                "/api/generate",
                data={
                    "prompt": "draw a mug",
                    "model": "gpt-image-2",
                    "main_model": "gpt-5.4",
                    "size": "3840x2160",
                    "quality": "low",
                    "background": "auto",
                    "output_format": "webp",
                    "moderation": "low",
                    "output_compression": "80",
                    "codex_mode": "responses",
                },
            )

            body = response.json()
            metadata = json.loads(metadata_path(Path(tmp), body["task"]["task_id"]).read_text(encoding="utf-8"))
            request_path_text = request_path(Path(tmp), body["task"]["task_id"]).read_text(encoding="utf-8")
            request_tool = body["request"]["tools"][0]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["request"]["model"], "gpt-5.4")
        self.assertNotIn("data:image/", request_path_text)
        self.assertNotIn("base64", request_path_text)
        self.assertEqual(metadata["params"]["main_model"], "gpt-5.4")
        self.assertEqual(request_tool["moderation"], "low")
        self.assertEqual(request_tool["output_compression"], 80)
        self.assertEqual(metadata["status"], "queued")
        self.assertEqual(fake.generate_calls, [])

    def test_generate_route_persists_web_search_for_codex_responses(self) -> None:
        from codex_image.webui.app import create_app

        fake = FakeImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: fake, auth_checker=lambda: True, auto_start_queue=False)
            response = TestClient(app).post(
                "/api/generate",
                data={
                    "prompt": "search then draw",
                    "model": "gpt-image-2",
                    "main_model": "gpt-5.4-mini",
                    "size": "1536x864",
                    "quality": "low",
                    "web_search": "true",
                    "codex_mode": "responses",
                },
            )

            body = response.json()
            metadata = json.loads(metadata_path(Path(tmp), body["task"]["task_id"]).read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(metadata["params"]["web_search"])
        self.assertTrue(body["task"]["params"]["web_search"])
        self.assertEqual([tool["type"] for tool in body["request"]["tools"]], ["web_search", "image_generation"])
        self.assertEqual(body["request"]["tools"][1]["quality"], "low")
        self.assertEqual(body["request"]["tool_choice"], "required")
        self.assertFalse(body["request"]["parallel_tool_calls"])

    def test_queue_worker_generates_output_thumbnail_metadata(self) -> None:
        from codex_image.client import ImageResult
        from codex_image.webui.app import create_app

        class ThumbnailImageClient(FakeImageClient):
            def generate_image(inner_self, **kwargs: Any):
                inner_self.generate_calls.append(kwargs)
                return ImageResult(self._png_bytes(), "revised", "png", kwargs["size"], "auto", kwargs["quality"], {})

        fake = ThumbnailImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root,
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                auth_settings_path=root / "auth-settings.json",
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            client = TestClient(app)
            created = client.post("/api/generate", data={"prompt": "thumb", "size": "1024x1024", "quality": "low"})
            task_id = created.json()["task"]["task_id"]

            asyncio.run(app.state.queue_manager.run_available_once())
            task = client.get(f"/api/tasks/{task_id}").json()["task"]
            metadata = json.loads(metadata_path(root, task_id).read_text(encoding="utf-8"))
            thumbnail_file_exists = (root / task["outputs"][0]["thumbnail_file"]).is_file()

        output = task["outputs"][0]
        self.assertEqual(task["status"], "completed")
        self.assertIn("thumbnail_file", output)
        self.assertRegex(output["thumbnail_url"], rf"^/outputs/thumbnails/{task_id[:4]}-{task_id[4:6]}-{task_id[6:8]}/{task_id}-image-1-thumb\.jpg$")
        self.assertEqual(metadata["outputs"][0]["thumbnail_file"], output["thumbnail_file"])
        self.assertTrue(thumbnail_file_exists)

    def test_queue_worker_persists_web_search_tool_usage(self) -> None:
        from codex_image.client import ImageResult
        from codex_image.webui.app import create_app
        from codex_image.webui.queue import QueueChannel

        class WebSearchUsageClient(FakeImageClient):
            def generate_image(inner_self, **kwargs: Any):
                inner_self.generate_calls.append(kwargs)
                return ImageResult(
                    self._png_bytes(),
                    "revised with search facts",
                    "png",
                    kwargs["size"],
                    "auto",
                    kwargs["quality"],
                    {"input_tokens": 4, "output_tokens": 5, "total_tokens": 9},
                    {"image_gen": {"total_tokens": 9}, "web_search": {"num_requests": 1}},
                )

        fake = WebSearchUsageClient()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root,
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                auth_settings_path=root / "auth-settings.json",
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            app.state.queue_manager.channels = [QueueChannel(channel_id="codex:local", auth_source="codex")]
            client = TestClient(app)
            created = client.post(
                "/api/generate",
                data={
                    "prompt": "search then poster",
                    "size": "1024x1024",
                    "quality": "low",
                    "web_search": "true",
                    "prompt_fidelity": "original",
                    "codex_mode": "responses",
                },
            )
            task_id = created.json()["task"]["task_id"]

            asyncio.run(app.state.queue_manager.run_available_once())
            metadata = json.loads(metadata_path(root, task_id).read_text(encoding="utf-8"))

        self.assertTrue(fake.generate_calls[0]["web_search"])
        self.assertIn("原始提示词模式", fake.generate_calls[0]["instructions"])
        self.assertEqual(metadata["outputs"][0]["tool_usage"]["web_search"], {"num_requests": 1})
        self.assertEqual(metadata["tool_usages"][0]["web_search"], {"num_requests": 1})
    def test_index_and_static_assets_disable_browser_cache(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)
            index_response = client.get("/")
            history_response = client.get("/history")
            script_response = client.get("/static/app.js")

        self.assertEqual(index_response.status_code, 200)
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(script_response.status_code, 200)
        self.assertEqual(index_response.headers["cache-control"], "no-store")
        self.assertEqual(history_response.headers["cache-control"], "no-store")
        self.assertEqual(script_response.headers["cache-control"], "no-store")
        self.assertIn("/static/history.js", history_response.text)
    def test_generate_route_omits_png_compression(self) -> None:
        from codex_image.webui.app import create_app

        fake = FakeImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: fake, auth_checker=lambda: True)
            response = TestClient(app).post(
                "/api/generate",
                data={
                    "prompt": "draw a mug",
                    "model": "gpt-image-2",
                    "size": "1024x1024",
                    "quality": "low",
                    "output_format": "png",
                    "output_compression": "80",
                    "codex_mode": "responses",
                },
            )
            body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("output_compression", body["request"]["tools"][0])
        self.assertEqual(fake.generate_calls, [])
    def test_generate_route_uses_late_patched_request_payload_builder(self) -> None:
        from codex_image.webui.app import create_app

        calls: list[dict[str, Any]] = []

        def patched_payload(**kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return {"patched": True, "prompt": kwargs["prompt"]}

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            with patch("codex_image.webui.app._build_image_request_payload", patched_payload):
                response = TestClient(app).post(
                    "/api/generate",
                    data={"prompt": "patched builder", "model": "gpt-image-2", "size": "1024x1024", "quality": "low", "codex_mode": "responses"},
                )
            body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(calls), 1)
        self.assertTrue(body["request"]["patched"])
        self.assertEqual(body["request"]["prompt"], "patched builder")
    def test_generate_route_stores_slim_request_without_image_base64(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            response = TestClient(app).post(
                "/api/generate",
                data={"prompt": "reference", "size": "1024x1024", "codex_mode": "responses"},
                files={"reference_images": ("input.png", b"input-bytes", "image/png")},
            )
            task_id = response.json()["task"]["task_id"]
            request_text = request_path(root, task_id).read_text(encoding="utf-8")
            request_payload = json.loads(request_text)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("data:image/", request_text)
        self.assertNotIn("base64", request_text)
        self.assertEqual(request_payload["input"][0]["content"][1]["image_url"], "<redacted image data url, 38 chars>")
        self.assertEqual(request_payload["webui_image_refs"]["input_files"], [])
        self.assertEqual(request_payload["webui_image_refs"]["reference_assets"][0]["filename"], "input.png")
    def test_edit_route_stores_slim_request_with_mask_reference(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            response = TestClient(app).post(
                "/api/edit",
                data={"prompt": "edit reference", "size": "1024x1024", "codex_mode": "responses"},
                files={
                    "images": ("input.png", b"input-bytes", "image/png"),
                    "mask": ("mask.png", b"mask-bytes", "image/png"),
                },
            )
            task_id = response.json()["task"]["task_id"]
            request_text = request_path(root, task_id).read_text(encoding="utf-8")
            request_payload = json.loads(request_text)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("data:image/", request_text)
        self.assertNotIn("base64", request_text)
        self.assertEqual(request_payload["webui_image_refs"]["input_files"], [])
        self.assertEqual(request_payload["webui_image_refs"]["reference_assets"][0]["filename"], "input.png")
        self.assertEqual(request_payload["webui_image_refs"]["mask_file"], input_name(task_id, "mask.png", kind="mask"))
    def test_generate_route_enqueues_without_calling_client_inline(self) -> None:
        from codex_image.webui.app import create_app

        fake = FakeImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: fake, auth_checker=lambda: True, auto_start_queue=False)
            response = TestClient(app).post(
                "/api/generate",
                data={"prompt": "queued mug", "model": "gpt-image-2", "size": "1024x1024", "quality": "low", "output_format": "png"},
            )
            task = response.json()["task"]
            metadata = json.loads(metadata_path(Path(tmp), task["task_id"]).read_text(encoding="utf-8"))
            queue_state = app.state.queue_storage.read_state()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(task["status"], "queued")
        self.assertEqual(metadata["status"], "queued")
        self.assertEqual(queue_state["waiting"], [task["task_id"]])
        self.assertEqual(fake.generate_calls, [])
    def test_generate_route_defaults_to_strict_prompt_fidelity(self) -> None:
        from codex_image.webui.app import create_app

        prompt = "产品目标人群是宝妈为主，文案标题设计偏儿童Q版卡通化，色彩偏淡彩"
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            response = TestClient(app).post(
                "/api/generate",
                data={"prompt": prompt, "model": "gpt-image-2", "size": "1024x1024", "quality": "low", "output_format": "png", "codex_mode": "responses"},
            )
            body = response.json()
            task = body["task"]
            metadata = json.loads(metadata_path(Path(tmp), task["task_id"]).read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(task["params"]["prompt_fidelity"], "strict")
        self.assertIn("标题字体/标题设计：文案标题设计偏儿童Q版卡通化", task["prompt_constraints"])
        self.assertIn("标题字体/标题设计：文案标题设计偏儿童Q版卡通化", metadata["prompt_constraints"])
        self.assertIn("只能扩写用户提示词", body["request"]["instructions"])
        self.assertEqual(body["request"]["input"][0]["content"][0]["text"], prompt)
    def test_generate_route_prompt_fidelity_off_keeps_plain_request(self) -> None:
        from codex_image.webui.app import create_app

        prompt = "文案标题设计偏儿童Q版卡通化"
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            response = TestClient(app).post(
                "/api/generate",
                data={
                    "prompt": prompt,
                    "model": "gpt-image-2",
                    "size": "1024x1024",
                    "quality": "low",
                    "output_format": "png",
                    "prompt_fidelity": "off",
                    "codex_mode": "responses",
                },
            )
            body = response.json()
            task = body["task"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(task["params"]["prompt_fidelity"], "off")
        self.assertNotIn("prompt_constraints", task)
        self.assertEqual(body["request"]["instructions"], "")
    def test_generate_route_appends_ratio_instruction_to_model_prompt(self) -> None:
        from codex_image.webui.app import create_app

        prompt = "生成一张极简电影海报"
        expected_model_prompt = f"{prompt}\n\n将宽高比设为 16:9"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            response = TestClient(app).post(
                "/api/generate",
                data={
                    "prompt": prompt,
                    "model": "gpt-image-2",
                    "size": "1536x864",
                    "ratio": "16:9",
                    "orientation": "landscape",
                    "quality": "low",
                    "output_format": "png",
                    "prompt_fidelity": "off",
                    "codex_mode": "responses",
                },
            )
            body = response.json()
            task = body["task"]
            metadata = json.loads(metadata_path(root, task["task_id"]).read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(task["prompt"], prompt)
        self.assertEqual(task["prompt_for_model"], expected_model_prompt)
        self.assertEqual(task["params"]["ratio"], "16:9")
        self.assertEqual(metadata["prompt"], prompt)
        self.assertEqual(metadata["prompt_for_model"], expected_model_prompt)
        self.assertEqual(body["request"]["input"][0]["content"][0]["text"], expected_model_prompt)
    def test_generate_route_original_prompt_fidelity_uses_raw_prompt(self) -> None:
        from codex_image.webui.app import create_app

        prompt = "让 @小美 做产品模特，文案标题设计偏儿童Q版卡通化"
        prompt_for_model = f"{prompt}\n\n参考图 1 为「小美」（人像），提示词中的 @小美 指这张图。"
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            response = TestClient(app).post(
                "/api/generate",
                data={
                    "prompt": prompt,
                    "prompt_for_model": prompt_for_model,
                    "model": "gpt-image-2",
                    "size": "1024x1024",
                    "quality": "low",
                    "output_format": "png",
                    "prompt_fidelity": "original",
                    "codex_mode": "responses",
                },
            )
            body = response.json()
            task = body["task"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(task["params"]["prompt_fidelity"], "original")
        self.assertEqual(task["prompt_for_model"], prompt)
        self.assertNotIn("prompt_constraints", task)
        self.assertEqual(body["request"]["input"][0]["content"][0]["text"], prompt)
        self.assertIn("原始提示词模式", body["request"]["instructions"])
        self.assertIn("不得优化", body["request"]["instructions"])
        self.assertNotIn("参考图 1", body["request"]["input"][0]["content"][0]["text"])
    def test_edit_route_enqueues_without_calling_client_inline(self) -> None:
        from codex_image.webui.app import create_app

        fake = FakeImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: fake, auth_checker=lambda: True, auto_start_queue=False)
            response = TestClient(app).post(
                "/api/edit",
                data={"prompt": "queued edit", "model": "gpt-image-2", "size": "1024x1024", "quality": "low", "output_format": "png"},
                files={"images": ("input.png", b"input", "image/png")},
            )
            task = response.json()["task"]
            metadata = json.loads(metadata_path(Path(tmp), task["task_id"]).read_text(encoding="utf-8"))
            queue_state = app.state.queue_storage.read_state()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(task["status"], "queued")
        self.assertEqual(metadata["status"], "queued")
        self.assertEqual(queue_state["waiting"], [task["task_id"]])
        self.assertEqual(fake.edit_calls, [])
    def test_edit_route_appends_ratio_instruction_to_model_prompt(self) -> None:
        from codex_image.webui.app import create_app

        prompt = "把参考图改成横版电影海报"
        expected_model_prompt = f"{prompt}\n\n将宽高比设为 16:9"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            response = TestClient(app).post(
                "/api/edit",
                data={
                    "prompt": prompt,
                    "model": "gpt-image-2",
                    "size": "1536x864",
                    "ratio": "16:9",
                    "orientation": "landscape",
                    "quality": "low",
                    "output_format": "png",
                    "prompt_fidelity": "off",
                    "codex_mode": "responses",
                },
                files={"images": ("input.png", self._png_bytes(), "image/png")},
            )
            body = response.json()
            task = body["task"]
            metadata = json.loads(metadata_path(root, task["task_id"]).read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(task["prompt"], prompt)
        self.assertEqual(task["prompt_for_model"], expected_model_prompt)
        self.assertEqual(task["params"]["ratio"], "16:9")
        self.assertEqual(metadata["prompt"], prompt)
        self.assertEqual(metadata["prompt_for_model"], expected_model_prompt)
        self.assertEqual(body["request"]["input"][0]["content"][0]["text"], expected_model_prompt)
    def test_generate_route_enqueues_without_client_factory(self) -> None:
        from codex_image.webui.app import create_app

        def fail_factory() -> FakeImageClient:
            raise AssertionError("client factory should not be called")

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=fail_factory, auth_checker=lambda: True, auto_start_queue=False)
            response = TestClient(app, raise_server_exceptions=False).post(
                "/api/generate",
                data={"prompt": "queued without client", "model": "gpt-image-2", "size": "1024x1024", "quality": "low", "output_format": "png"},
            )
            task = response.json()["task"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(task["status"], "queued")
    def test_edit_route_enqueues_without_client_factory(self) -> None:
        from codex_image.webui.app import create_app

        def fail_factory() -> FakeImageClient:
            raise AssertionError("client factory should not be called")

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=fail_factory, auth_checker=lambda: True, auto_start_queue=False)
            response = TestClient(app, raise_server_exceptions=False).post(
                "/api/edit",
                data={"prompt": "queued edit without client", "model": "gpt-image-2", "size": "1024x1024", "quality": "low", "output_format": "png"},
                files={"images": ("input.png", b"input", "image/png")},
            )
            task = response.json()["task"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(task["status"], "queued")
    def test_edit_route_without_image_does_not_create_task_directory(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            response = TestClient(app).post(
                "/api/edit",
                data={"prompt": "missing image", "model": "gpt-image-2", "size": "1024x1024", "quality": "low", "output_format": "png"},
            )
            task_files = list((root / "source-data").rglob("*.metadata.json")) if (root / "source-data").exists() else []

        self.assertEqual(response.status_code, 400)
        self.assertEqual(task_files, [])
    def test_generate_route_exposes_input_urls(self) -> None:
        from codex_image.webui.app import create_app

        fake = FakeImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: fake, auth_checker=lambda: True)
            client = TestClient(app)
            response = client.post(
                "/api/generate",
                data={
                    "prompt": "use reference",
                    "model": "gpt-image-2",
                    "size": "1024x1024",
                    "quality": "low",
                    "output_format": "png",
                },
                files={"reference_images": ("input.png", b"input-bytes", "image/png")},
            )
            task = response.json()["task"]
            list_response = client.get("/api/tasks")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(task["input_files"], [])
        self.assertEqual(task["input_urls"], [])
        self.assertEqual(task["input_sources"][0]["kind"], "asset")
        self.assertEqual(task["reference_assets"][0]["filename"], "input.png")
        self.assertEqual(list_response.json()["tasks"][0]["reference_assets"], task["reference_assets"])
    def test_generate_route_dedupes_duplicate_reference_uploads_into_one_asset(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(output_root=root, client_factory=lambda: FakeImageClient(), auth_checker=lambda: True, auto_start_queue=False)
            response = TestClient(app).post(
                "/api/generate",
                data={"prompt": "dedupe reference", "size": "1024x1024"},
                files=[
                    ("reference_images", ("one.png", b"same-image-bytes", "image/png")),
                    ("reference_images", ("two.png", b"same-image-bytes", "image/png")),
                ],
            )
            body = response.json()
            task = body["task"]
            task_id = task["task_id"]
            asset_id = task["reference_assets"][0]["id"]
            asset_images = [path for path in (root / "inputs" / "reference-assets").glob("*/*") if path.suffix != ".json"]
            metadata = json.loads(metadata_path(root, task_id).read_text(encoding="utf-8"))
            request_payload = json.loads(request_path(root, task_id).read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(task["input_files"], [])
        self.assertEqual(len(task["reference_assets"]), 1)
        self.assertEqual(metadata["reference_assets"][0]["id"], asset_id)
        self.assertEqual(metadata["input_sources"][0]["kind"], "asset")
        self.assertEqual(request_payload["webui_image_refs"]["reference_assets"][0]["id"], asset_id)
        self.assertEqual(len(asset_images), 1)
    def test_generate_route_batches_multiple_outputs_in_one_task(self) -> None:
        from codex_image.webui.app import create_app

        fake = FakeImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                output_root=Path(tmp),
                queue_path=Path(tmp) / "queue.json",
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
            )
            response = TestClient(app).post(
                "/api/generate",
                data={
                    "prompt": "draw three mugs",
                    "model": "gpt-image-2",
                    "size": "1024x1024",
                    "quality": "low",
                    "output_format": "png",
                    "n": "3",
                },
            )
            task = response.json()["task"]
            output_files_exist = [(Path(tmp) / output_name(task["task_id"], index)).exists() for index in (1, 2, 3)]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake.generate_calls, [])
        self.assertEqual(task["status"], "queued")
        self.assertEqual(task["params"]["n"], 3)
        self.assertNotIn("output_files", task)
        self.assertNotIn("output_urls", task)
        self.assertEqual(output_files_exist, [False, False, False])
    def test_edit_route_requires_image_passes_mask_and_omits_gpt_image_2_input_fidelity(self) -> None:
        from codex_image.webui.app import create_app

        fake = FakeImageClient()
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), client_factory=lambda: fake, auth_checker=lambda: True)
            client = TestClient(app)
            response = client.post(
                "/api/edit",
                data={
                    "prompt": "change background",
                    "model": "gpt-image-2",
                    "size": "1536x1024",
                    "quality": "low",
                    "output_format": "png",
                    "input_fidelity": "high",
                    "codex_mode": "responses",
                },
                files={
                    "images": ("input.png", b"input-bytes", "image/png"),
                    "mask": ("mask.png", b"mask-bytes", "image/png"),
                },
            )
            body = response.json()
            request_tool = body["request"]["tools"][0]
            input_content = body["request"]["input"][0]["content"]
            task = body["task"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len([item for item in input_content if item["type"] == "input_image"]), 1)
        self.assertTrue(request_tool["input_image_mask"]["image_url"].startswith("<redacted image data url, "))
        self.assertEqual(body["request"]["webui_image_refs"]["mask_file"], input_name(task["task_id"], "mask.png", kind="mask"))
        self.assertNotIn("input_fidelity", request_tool)
        self.assertNotIn("input_fidelity", task["params"])
        self.assertNotIn(
            "gpt.input_fidelity",
            task["generation_snapshot"].get("legacy_compat_parameters", {}),
        )
        self.assertEqual(task["input_files"], [])
        self.assertEqual(task["input_sources"][0]["kind"], "asset")
        self.assertEqual(task["mask_file"], input_name(task["task_id"], "mask.png", kind="mask"))
        self.assertEqual(fake.edit_calls, [])
