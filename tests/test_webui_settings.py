from __future__ import annotations

import asyncio
import base64
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


def _fake_jwt(payload: dict[str, object]) -> str:
    def encode(data: dict[str, object]) -> str:
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f"{encode({'alg': 'none', 'typ': 'JWT'})}.{encode(payload)}.sig"


class WebUISettingsTests(unittest.TestCase):
    def test_health_reports_missing_auth(self) -> None:
        from codex_image.webui.app import create_app

        app = create_app(output_root=Path(tempfile.mkdtemp()), client_factory=lambda: FakeImageClient(), auth_checker=lambda: False)
        response = TestClient(app).get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["auth_available"])

    def test_app_version_reports_source_version_without_portable_notice(self) -> None:
        from codex_image.version import APP_VERSION
        from codex_image.webui.app import create_app

        with patch.dict(os.environ, {"ILAB_CONJURE_BUNDLE_DIR": "", "ILAB_CONJURE_DATA_DIR": ""}):
            app = create_app(output_root=Path(tempfile.mkdtemp()), auto_start_queue=False)
            response = TestClient(app).get("/api/app-version")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["current_version"], APP_VERSION)
        self.assertEqual(payload["current_version_label"], f"v{APP_VERSION}")
        self.assertFalse(payload["portable"])
        self.assertFalse(payload["update_available"])
        self.assertFalse(payload["updater_available"])

    def test_app_version_reports_portable_update_notice(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_dir = root / "bundle"
            data_dir = bundle_dir / "data"
            output_root = data_dir / "webui-outputs"
            bundle_dir.mkdir()
            data_dir.mkdir()
            output_root.mkdir()
            (bundle_dir / "portable-version.txt").write_text("0.3.6\n", encoding="utf-8")
            (bundle_dir / "Update WebUI Portable.command").write_text("#!/bin/zsh\n", encoding="utf-8")
            (bundle_dir / "Update WebUI Portable.bat").write_text("@echo off\n", encoding="utf-8")
            (data_dir / "update-notice.json").write_text(
                json.dumps(
                    {
                        "current_version": "0.3.6",
                        "latest_version": "0.3.7",
                        "checked_at": "2026-06-14T00:00:00Z",
                        "release_url": "https://github.com/kadevin/ilab-gpt-conjure/releases/tag/v0.3.7",
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"ILAB_CONJURE_BUNDLE_DIR": str(bundle_dir), "ILAB_CONJURE_DATA_DIR": str(data_dir)},
            ):
                app = create_app(output_root=output_root, auto_start_queue=False)
                response = TestClient(app).get("/api/app-version")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["portable"])
        self.assertEqual(payload["current_version"], "0.3.6")
        self.assertEqual(payload["latest_version"], "0.3.7")
        self.assertTrue(payload["update_available"])
        self.assertTrue(payload["updater_available"])
        self.assertEqual(payload["updater_label"], "Update WebUI Portable.command")

    def test_auth_routes_report_and_persist_codex_or_api_source(self) -> None:
        from codex_image.auth import AuthState
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings_path = root / "auth-settings.json"
            settings_path.write_text(json.dumps({"source": "codex"}), encoding="utf-8")
            api_settings_path = root / "api-settings.json"
            api_settings_path.write_text(
                json.dumps(
                    {
                        "base_url": "https://api.example.com/v1",
                        "api_key": "test-api-key-test-secret",
                        "image_model": "gpt-image-2",
                        "api_mode": "images",
                    }
                ),
                encoding="utf-8",
            )
            auth_state = AuthState(
                path=root / "auth.json",
                access_token="codex-access",
                refresh_token=None,
                id_token=None,
                account_id="acct-local",
                last_refresh=None,
                raw={},
            )
            with patch("codex_image.webui.auth_routing.load_auth_state", return_value=auth_state):
                app = create_app(
                    output_root=root / "tasks",
                    auth_settings_path=settings_path,
                    api_settings_path=api_settings_path,
                    auto_start_queue=False,
                )
                client = TestClient(app)

                initial = client.get("/api/auth")
                switched = client.patch("/api/auth", json={"source": "api"})
                invalid_auto = client.patch("/api/auth", json={"source": "auto"})
                invalid_pool = client.patch("/api/auth", json={"source": "cock" + "pit"})
                invalid_bad = client.patch("/api/auth", json={"source": "bad"})
                health = client.get("/api/health")
                persisted = json.loads(settings_path.read_text(encoding="utf-8"))

        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()["selected_source"], "codex")
        self.assertEqual(initial.json()["effective_source"], "codex")
        self.assertEqual(set(initial.json()["sources"]), {"codex", "api"})
        self.assertEqual(switched.status_code, 200)
        self.assertEqual(switched.json()["selected_source"], "api")
        self.assertEqual(health.json()["auth"]["selected_source"], "api")
        self.assertTrue(health.json()["auth_available"])
        for response in (invalid_auto, invalid_pool, invalid_bad):
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["detail"], "source must be codex or api")
        self.assertEqual(persisted["source"], "api")

    def test_account_routes_are_removed(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), auto_start_queue=False)
            client = TestClient(app)

            list_response = client.get("/api/accounts")
            refresh_response = client.post("/api/accounts/refresh")
            patch_response = client.patch("/api/accounts/codex:local", json={"manual_disabled": True})

        self.assertEqual(list_response.status_code, 404)
        self.assertEqual(refresh_response.status_code, 404)
        self.assertEqual(patch_response.status_code, 404)

    def test_legacy_auth_setting_falls_back_to_startup_detection(self) -> None:
        from codex_image.auth import AuthState
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings_path = root / "auth-settings.json"
            settings_path.write_text(json.dumps({"source": "cock" + "pit"}), encoding="utf-8")
            auth_state = AuthState(
                path=root / "auth.json",
                access_token="codex-access",
                refresh_token=None,
                id_token=None,
                account_id="acct-local",
                last_refresh=None,
                raw={},
            )
            with patch("codex_image.webui.startup_auth.load_auth_state", return_value=auth_state), patch(
                "codex_image.webui.auth_routing.load_auth_state", return_value=auth_state
            ):
                app = create_app(output_root=root / "tasks", auth_settings_path=settings_path, auto_start_queue=False)
                response = TestClient(app).get("/api/auth")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["selected_source"], "codex")
    def test_api_settings_routes_persist_secret_without_echoing_it(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth_settings_path = root / "auth-settings.json"
            api_settings_path = root / "api-settings.json"
            app = create_app(
                output_root=root / "tasks",
                auth_settings_path=auth_settings_path,
                api_settings_path=api_settings_path,
                auto_start_queue=False,
            )
            client = TestClient(app)

            initial = client.get("/api/api-settings")
            saved = client.patch(
                "/api/api-settings",
                json={
                    "base_url": "https://api.example.com/v1",
                    "api_key": "test-api-key-test-secret",
                    "image_model": "gpt-image-2",
                    "api_mode": "responses",
                },
            )
            switched = client.patch("/api/auth", json={"source": "api"})
            health = client.get("/api/health")
            reported = client.get("/api/api-settings")
            persisted = json.loads(api_settings_path.read_text(encoding="utf-8"))

        response_text = json.dumps({"saved": saved.json(), "reported": reported.json()}, ensure_ascii=False)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(switched.status_code, 200)
        self.assertEqual(switched.json()["selected_source"], "api")
        self.assertEqual(switched.json()["effective_source"], "api")
        self.assertTrue(health.json()["auth_available"])
        self.assertEqual(health.json()["auth"]["selected_source"], "api")
        self.assertEqual(initial.json()["settings"]["codex_mode"], "images")
        self.assertEqual(initial.json()["settings"]["api_mode"], "images")
        self.assertEqual(reported.json()["settings"]["base_url"], "https://api.example.com/v1")
        self.assertEqual(reported.json()["settings"]["image_model"], "gpt-image-2")
        self.assertEqual(reported.json()["settings"]["codex_mode"], "images")
        self.assertEqual(reported.json()["settings"]["api_mode"], "responses")
        self.assertTrue(reported.json()["settings"]["api_key_set"])
        self.assertEqual(persisted["codex_mode"], "images")
        self.assertEqual(persisted["api_key"], "test-api-key-test-secret")
        self.assertEqual(persisted["api_mode"], "responses")
        self.assertNotIn("test-api-key-test-secret", response_text)
    def test_api_settings_persist_codex_channel_mode(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            api_settings_path = root / "api-settings.json"
            app = create_app(
                output_root=root / "tasks",
                auth_settings_path=root / "auth-settings.json",
                api_settings_path=api_settings_path,
                auto_start_queue=False,
            )
            client = TestClient(app)

            initial = client.get("/api/api-settings")
            saved = client.patch("/api/api-settings", json={"codex_mode": "responses"})
            reported = client.get("/api/api-settings")
            invalid = client.patch("/api/api-settings", json={"codex_mode": "invalid"})
            persisted = json.loads(api_settings_path.read_text(encoding="utf-8"))

        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()["settings"]["codex_mode"], "images")
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["settings"]["codex_mode"], "responses")
        self.assertEqual(reported.json()["settings"]["codex_mode"], "responses")
        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(invalid.json()["settings"]["codex_mode"], "images")
        self.assertEqual(persisted["codex_mode"], "images")
    def test_api_settings_support_multiple_providers_and_legacy_shape(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            api_settings_path = root / "api-settings.json"
            api_settings_path.write_text(
                json.dumps(
                    {
                        "base_url": "https://legacy.example.com/v1",
                        "api_key": "test-api-key-legacy-secret",
                        "image_model": "legacy-image",
                        "api_mode": "responses",
                    }
                ),
                encoding="utf-8",
            )
            app = create_app(
                output_root=root / "tasks",
                auth_settings_path=root / "auth-settings.json",
                api_settings_path=api_settings_path,
                auto_start_queue=False,
            )
            client = TestClient(app)

            initial = client.get("/api/api-settings").json()["settings"]
            saved = client.patch(
                "/api/api-settings",
                json={
                    "active_provider_id": "vendor-b",
                    "providers": [
                        {
                            "id": "legacy",
                            "name": "Legacy",
                            "base_url": "https://legacy.example.com/v1",
                            "image_model": "legacy-image",
                            "api_mode": "responses",
                        },
                        {
                            "id": "vendor-b",
                            "name": "Vendor B",
                            "base_url": "https://vendor-b.example.com/v1",
                            "api_key": "test-api-key-vendor-b-secret",
                            "image_model": "vendor-image",
                            "api_mode": "images",
                            "images_concurrency": 2,
                        },
                    ],
                },
            )
            reported = client.get("/api/api-settings").json()["settings"]
            persisted = json.loads(api_settings_path.read_text(encoding="utf-8"))

        response_text = json.dumps({"saved": saved.json(), "reported": reported}, ensure_ascii=False)
        self.assertEqual(initial["active_provider_id"], "default")
        self.assertEqual(initial["providers"][0]["base_url"], "https://legacy.example.com/v1")
        self.assertEqual(initial["providers"][0]["images_concurrency"], 4)
        self.assertTrue(initial["providers"][0]["api_key_set"])
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(reported["active_provider_id"], "vendor-b")
        self.assertEqual(reported["base_url"], "https://vendor-b.example.com/v1")
        self.assertEqual(reported["image_model"], "vendor-image")
        self.assertEqual(reported["images_concurrency"], 2)
        self.assertEqual([provider["id"] for provider in reported["providers"]], ["legacy", "vendor-b"])
        self.assertTrue(reported["providers"][0]["api_key_set"])
        self.assertTrue(reported["providers"][1]["api_key_set"])
        self.assertEqual(reported["providers"][0]["images_concurrency"], 4)
        self.assertEqual(reported["providers"][1]["images_concurrency"], 2)
        self.assertEqual(persisted["active_provider_id"], "vendor-b")
        self.assertEqual(persisted["providers"][0]["api_key"], "test-api-key-legacy-secret")
        self.assertEqual(persisted["providers"][1]["api_key"], "test-api-key-vendor-b-secret")
        self.assertEqual(persisted["providers"][0]["images_concurrency"], 4)
        self.assertEqual(persisted["providers"][1]["images_concurrency"], 2)
        self.assertNotIn("test-api-key-legacy-secret", response_text)
        self.assertNotIn("test-api-key-vendor-b-secret", response_text)
    def test_api_settings_allows_provider_concurrency_above_single_task_output_limit(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            api_settings_path = root / "api-settings.json"
            app = create_app(
                output_root=root / "tasks",
                auth_settings_path=root / "auth-settings.json",
                api_settings_path=api_settings_path,
                auto_start_queue=False,
            )
            client = TestClient(app)

            saved = client.patch(
                "/api/api-settings",
                json={
                    "base_url": "https://api.example.com/v1",
                    "api_key": "test-api-key-provider-concurrency-secret",
                    "image_model": "gpt-image-2",
                    "api_mode": "images",
                    "images_concurrency": 10,
                },
            )
            reported = client.get("/api/api-settings").json()["settings"]
            persisted = json.loads(api_settings_path.read_text(encoding="utf-8"))

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["settings"]["images_concurrency"], 10)
        self.assertEqual(saved.json()["settings"]["providers"][0]["images_concurrency"], 10)
        self.assertEqual(reported["images_concurrency"], 10)
        self.assertEqual(reported["providers"][0]["images_concurrency"], 10)
        self.assertEqual(persisted["images_concurrency"], 10)
        self.assertEqual(persisted["providers"][0]["images_concurrency"], 10)
    def test_api_source_generate_task_does_not_expose_api_key(self) -> None:
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
                    "base_url": "https://api.example.com/v1",
                    "api_key": "test-api-key-no-leak",
                    "image_model": "gpt-image-2",
                },
            )
            client.patch("/api/auth", json={"source": "api"})

            response = client.post(
                "/api/generate",
                data={"prompt": "api queued", "main_model": "gpt-5.5", "size": "1024x1024", "quality": "low"},
            )
            body = response.json()
            task_id = body["task"]["task_id"]
            request_text = request_path(root / "tasks", task_id).read_text(encoding="utf-8")
            metadata_text = metadata_path(root / "tasks", task_id).read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["task"]["status"], "queued")
        self.assertNotIn("test-api-key-no-leak", json.dumps(body, ensure_ascii=False))
        self.assertNotIn("test-api-key-no-leak", request_text)
        self.assertNotIn("test-api-key-no-leak", metadata_text)
    def test_api_images_mode_uses_prompt_prefix_for_prompt_fidelity(self) -> None:
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
                    "base_url": "https://api.example.com/v1",
                    "api_key": "test-api-key-no-leak",
                    "image_model": "gpt-image-2",
                    "api_mode": "images",
                },
            )
            client.patch("/api/auth", json={"source": "api"})

            response = client.post(
                "/api/generate",
                data={"prompt": "文案标题设计偏儿童Q版卡通化", "main_model": "gpt-5.5", "size": "1024x1024", "quality": "low"},
            )
            body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("instructions", body["request"])
        self.assertIn("提示词保真规则", body["request"]["prompt"])
        self.assertIn("用户原始提示词：\n文案标题设计偏儿童Q版卡通化", body["request"]["prompt"])
    def test_api_images_original_prompt_fidelity_sends_exact_prompt(self) -> None:
        from codex_image.webui.app import create_app

        prompt = "文案标题设计偏儿童Q版卡通化"
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
                    "base_url": "https://api.example.com/v1",
                    "api_key": "test-api-key-no-leak",
                    "image_model": "gpt-image-2",
                    "api_mode": "images",
                },
            )
            client.patch("/api/auth", json={"source": "api"})

            response = client.post(
                "/api/generate",
                data={
                    "prompt": prompt,
                    "prompt_for_model": f"{prompt}\n\n参考图 1 为「小美」（人像），提示词中的 @小美 指这张图。",
                    "main_model": "gpt-5.5",
                    "size": "1024x1024",
                    "quality": "low",
                    "prompt_fidelity": "original",
                },
            )
            body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["task"]["params"]["prompt_fidelity"], "original")
        self.assertNotIn("instructions", body["request"])
        self.assertEqual(body["request"]["prompt"], prompt)
    def test_codex_generate_defaults_to_images_channel_request_preview(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth_settings_path = root / "auth-settings.json"
            auth_settings_path.write_text(json.dumps({"source": "codex"}), encoding="utf-8")
            app = create_app(
                output_root=root / "tasks",
                auth_settings_path=auth_settings_path,
                api_settings_path=root / "api-settings.json",
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            client = TestClient(app)

            response = client.post(
                "/api/generate",
                data={
                    "prompt": "codex images default",
                    "main_model": "gpt-5.5",
                    "size": "1024x1024",
                    "quality": "low",
                    "web_search": "true",
                },
            )
            body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["task"]["requested_backend"], "codex_images")
        self.assertEqual(body["task"]["params"]["codex_mode"], "images")
        self.assertNotIn("web_search", body["task"]["params"])
        self.assertEqual(body["request"]["webui_requested_backend"], "codex_images")
        self.assertEqual(body["request"]["endpoint"], "/images/generations")
        self.assertIn("提示词保真规则", body["request"]["prompt"])
        self.assertIn("用户原始提示词：\ncodex images default", body["request"]["prompt"])
        self.assertNotIn("tools", body["request"])
        self.assertNotIn("instructions", body["request"])

    def test_codex_generate_uses_responses_channel_when_selected(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth_settings_path = root / "auth-settings.json"
            auth_settings_path.write_text(json.dumps({"source": "codex"}), encoding="utf-8")
            app = create_app(
                output_root=root / "tasks",
                auth_settings_path=auth_settings_path,
                api_settings_path=root / "api-settings.json",
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            client = TestClient(app)
            saved = client.patch("/api/api-settings", json={"codex_mode": "responses"})
            response = client.post(
                "/api/generate",
                data={
                    "prompt": "codex responses selected",
                    "main_model": "gpt-5.5",
                    "size": "1024x1024",
                    "quality": "low",
                    "web_search": "true",
                },
            )
            body = response.json()

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["settings"]["codex_mode"], "responses")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["task"]["requested_backend"], "codex_responses")
        self.assertEqual(body["task"]["params"]["codex_mode"], "responses")
        self.assertTrue(body["task"]["params"]["web_search"])
        self.assertEqual(body["request"]["webui_requested_backend"], "codex_responses")
        self.assertEqual(body["request"]["tools"][0]["type"], "web_search")
        self.assertEqual(body["request"]["tools"][1]["type"], "image_generation")

    def test_codex_edit_defaults_to_images_edits_request_preview(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth_settings_path = root / "auth-settings.json"
            auth_settings_path.write_text(json.dumps({"source": "codex"}), encoding="utf-8")
            app = create_app(
                output_root=root / "tasks",
                auth_settings_path=auth_settings_path,
                api_settings_path=root / "api-settings.json",
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            client = TestClient(app)

            response = client.post(
                "/api/edit",
                data={
                    "prompt": "codex edit default",
                    "size": "1152x2048",
                    "quality": "high",
                    "output_format": "png",
                    "prompt_fidelity": "original",
                },
                files={"images": ("input.png", b"input-image", "image/png")},
            )
            body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["task"]["requested_backend"], "codex_images")
        self.assertEqual(body["task"]["params"]["codex_mode"], "images")
        self.assertEqual(body["request"]["webui_requested_backend"], "codex_images")
        self.assertEqual(body["request"]["endpoint"], "/images/edits")
        self.assertEqual(body["request"]["size"], "1152x2048")
        self.assertEqual(body["request"]["quality"], "high")
        self.assertEqual(body["request"]["images"][0]["image_url"], "<redacted image data url, 38 chars>")
        self.assertNotIn("tools", body["request"])

    def test_codex_queue_worker_uses_images_client_by_default(self) -> None:
        from codex_image.auth import AuthState
        from codex_image.webui.app import create_app

        class CapturingCodexImagesClient(FakeImageClient):
            instances: list["CapturingCodexImagesClient"] = []

            def __init__(self, auth_state: AuthState, **_: object) -> None:
                super().__init__()
                self.auth_state = auth_state
                self.instances.append(self)

        class FailingCodexResponsesClient(FakeImageClient):
            def __init__(self, *_: object, **__: object) -> None:
                raise AssertionError("default Codex queue channel should use codex images client")

        auth_state = AuthState(
            path=Path("/tmp/auth.json"),
            access_token="codex-access",
            refresh_token=None,
            id_token=None,
            account_id="acct-local",
            last_refresh=None,
            raw={},
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth_settings_path = root / "auth-settings.json"
            auth_settings_path.write_text(json.dumps({"source": "codex"}), encoding="utf-8")
            with patch("codex_image.webui.queue_runtime.load_auth_state", return_value=auth_state), patch(
                "codex_image.webui.queue_runtime.CodexImageClient", FailingCodexResponsesClient, create=True
            ), patch(
                "codex_image.webui.queue_runtime.CodexImagesImageClient", CapturingCodexImagesClient, create=True
            ):
                app = create_app(
                    output_root=root / "tasks",
                    auth_settings_path=auth_settings_path,
                    api_settings_path=root / "api-settings.json",
                    auth_checker=lambda: True,
                    batch_delay_seconds=0,
                    auto_start_queue=False,
                )
                client = TestClient(app)
                created = client.post(
                    "/api/generate",
                    data={"prompt": "codex worker", "size": "1024x1024", "quality": "low"},
                )
                task_id = created.json()["task"]["task_id"]

                asyncio.run(app.state.queue_manager.run_available_once())
                task = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["assigned_auth_source"], "codex")
        self.assertEqual(task["requested_backend"], "codex_images")
        self.assertEqual(task["backend"], "codex_images")
        self.assertEqual(task["params"]["codex_mode"], "images")
        self.assertEqual(len(CapturingCodexImagesClient.instances), 1)
        self.assertEqual(CapturingCodexImagesClient.instances[0].auth_state.account_id, "acct-local")
    def test_api_queue_worker_uses_saved_images_client_settings(self) -> None:
        from codex_image.webui.app import create_app

        CapturingApiImageClient.instances = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("codex_image.webui.auth_routing.OpenAIImagesImageClient", CapturingApiImageClient, create=True):
                app = create_app(
                    output_root=root / "tasks",
                    auth_settings_path=root / "auth-settings.json",
                    api_settings_path=root / "api-settings.json",
                    batch_delay_seconds=0,
                    auto_start_queue=False,
                )
                client = TestClient(app)
                client.patch(
                    "/api/api-settings",
                    json={
                        "base_url": "https://api.example.com/v1",
                        "api_key": "test-api-key-worker-secret",
                        "image_model": "gpt-image-2",
                    },
                )
                client.patch("/api/auth", json={"source": "api"})
                created = client.post(
                    "/api/generate",
                    data={"prompt": "api worker", "main_model": "gpt-5.5", "size": "1024x1024", "quality": "low"},
                )
                task_id = created.json()["task"]["task_id"]

                asyncio.run(app.state.queue_manager.run_available_once())
                task = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["assigned_auth_source"], "api")
        self.assertEqual(task["requested_backend"], "openai_images")
        self.assertEqual(task["backend"], "openai_images")
        self.assertEqual(len(CapturingApiImageClient.instances), 1)
        api_client = CapturingApiImageClient.instances[0]
        self.assertEqual(api_client.api_key, "test-api-key-worker-secret")
        self.assertEqual(api_client.base_url, "https://api.example.com/v1")
        self.assertEqual(api_client.image_model, "gpt-image-2")
    def test_api_queue_worker_uses_provider_saved_on_task(self) -> None:
        from codex_image.webui.app import create_app

        CapturingApiImageClient.instances = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("codex_image.webui.auth_routing.OpenAIImagesImageClient", CapturingApiImageClient, create=True):
                app = create_app(
                    output_root=root / "tasks",
                    auth_settings_path=root / "auth-settings.json",
                    api_settings_path=root / "api-settings.json",
                    batch_delay_seconds=0,
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
                created = client.post(
                    "/api/generate",
                    data={
                        "prompt": "api provider",
                        "size": "1024x1024",
                        "quality": "low",
                        "api_provider_id": "vendor-b",
                    },
                )
                task_id = created.json()["task"]["task_id"]
                client.patch("/api/api-settings", json={"active_provider_id": "vendor-a"})

                asyncio.run(app.state.queue_manager.run_available_once())
                task = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["params"]["api_provider_id"], "vendor-b")
        self.assertEqual(task["api_provider_id"], "vendor-b")
        self.assertEqual(len(CapturingApiImageClient.instances), 1)
        api_client = CapturingApiImageClient.instances[0]
        self.assertEqual(api_client.api_key, "test-api-key-vendor-b-secret")
        self.assertEqual(api_client.base_url, "https://vendor-b.example.com/v1")
        self.assertEqual(api_client.image_model, "vendor-b-image")
    def test_retry_failed_api_images_uses_current_provider(self) -> None:
        from codex_image.webui.app import create_app

        ProviderSwitchRetryApiImageClient.reset()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("codex_image.webui.auth_routing.OpenAIImagesImageClient", ProviderSwitchRetryApiImageClient, create=True):
                app = create_app(
                    output_root=root / "tasks",
                    auth_settings_path=root / "auth-settings.json",
                    api_settings_path=root / "api-settings.json",
                    batch_delay_seconds=0,
                    auto_start_queue=False,
                )
                client = TestClient(app)
                client.patch(
                    "/api/api-settings",
                    json={
                        "active_provider_id": "vendor-b",
                        "providers": [
                            {
                                "id": "vendor-a",
                                "name": "Vendor A",
                                "base_url": "https://vendor-a.example.com/v1",
                                "api_key": "test-api-key-vendor-a-secret",
                                "image_model": "vendor-a-image",
                                "api_mode": "images",
                                "images_concurrency": 1,
                            },
                            {
                                "id": "vendor-b",
                                "name": "Vendor B",
                                "base_url": "https://vendor-b.example.com/v1",
                                "api_key": "test-api-key-vendor-b-secret",
                                "image_model": "vendor-b-image",
                                "api_mode": "images",
                                "images_concurrency": 1,
                            },
                        ],
                    },
                )
                client.patch("/api/auth", json={"source": "api"})
                created = client.post(
                    "/api/generate",
                    data={
                        "prompt": "retry with current provider",
                        "size": "1024x1024",
                        "quality": "low",
                        "n": "2",
                        "api_provider_id": "vendor-b",
                    },
                )
                task_id = created.json()["task"]["task_id"]

                asyncio.run(app.state.queue_manager.run_available_once())
                partial = client.get(f"/api/tasks/{task_id}").json()["task"]

                client.patch("/api/api-settings", json={"active_provider_id": "vendor-a"})
                retry_response = client.post(
                    f"/api/tasks/{task_id}/retry-failed",
                    json={"api_provider_id": "vendor-a"},
                )
                queued = retry_response.json()["task"]
                asyncio.run(app.state.queue_manager.run_available_once())
                retried = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertEqual(partial["status"], "partial_failed")
        self.assertEqual(partial["api_provider_id"], "vendor-b")
        self.assertEqual(retry_response.status_code, 200)
        self.assertEqual(queued["params"]["api_provider_id"], "vendor-a")
        self.assertEqual(queued["api_provider_id"], "vendor-a")
        self.assertEqual(queued["api_provider_name"], "Vendor A")
        self.assertEqual(retried["status"], "completed")
        self.assertEqual(retried["api_provider_id"], "vendor-a")
        self.assertEqual(retried["api_provider_name"], "Vendor A")
        self.assertIn("https://vendor-a.example.com/v1", [instance.base_url for instance in ProviderSwitchRetryApiImageClient.instances])
        self.assertEqual(ProviderSwitchRetryApiImageClient.calls_by_base_url["https://vendor-b.example.com/v1"], 2)
        self.assertEqual(ProviderSwitchRetryApiImageClient.calls_by_base_url["https://vendor-a.example.com/v1"], 1)
    def test_api_images_queue_worker_generates_multiple_outputs_concurrently(self) -> None:
        from codex_image.webui.app import create_app

        ConcurrentApiImageClient.reset(release_after_active_requests=4)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("codex_image.webui.auth_routing.OpenAIImagesImageClient", ConcurrentApiImageClient, create=True):
                app = create_app(
                    output_root=root / "tasks",
                    auth_settings_path=root / "auth-settings.json",
                    api_settings_path=root / "api-settings.json",
                    batch_delay_seconds=0,
                    auto_start_queue=False,
                )
                client = TestClient(app)
                client.patch(
                    "/api/api-settings",
                    json={
                        "base_url": "https://api.example.com/v1",
                        "api_key": "test-api-key-worker-secret",
                        "image_model": "gpt-image-2",
                        "api_mode": "images",
                    },
                )
                client.patch("/api/auth", json={"source": "api"})
                created = client.post(
                    "/api/generate",
                    data={"prompt": "api batch", "size": "1024x1024", "quality": "low", "n": "4"},
                )
                task_id = created.json()["task"]["task_id"]

                asyncio.run(app.state.queue_manager.run_available_once())
                task = client.get(f"/api/tasks/{task_id}").json()["task"]
                output_files_exist = [(root / "tasks" / output_name(task_id, index)).exists() for index in (1, 2, 3, 4)]

        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["requested_backend"], "openai_images")
        self.assertEqual(task["backend"], "openai_images")
        self.assertEqual(len(ConcurrentApiImageClient.instances), 1)
        api_client = ConcurrentApiImageClient.instances[0]
        self.assertEqual(api_client.generate_images_calls, [])
        self.assertEqual(len(api_client.generate_calls), 4)
        self.assertTrue(all("n" not in call for call in api_client.generate_calls))
        self.assertEqual(api_client.max_active_requests, 4)
        self.assertEqual(task["params"]["api_images_concurrency"], 4)
        self.assertEqual(task["api_images_concurrency"], 4)
        self.assertEqual(task["generated_count"], 4)
        self.assertEqual(task["total_count"], 4)
        self.assertEqual(task["output_urls"], [output_url(task_id, index) for index in (1, 2, 3, 4)])
        self.assertEqual(output_files_exist, [True, True, True, True])
    def test_api_images_queue_worker_publishes_concurrent_outputs_while_running(self) -> None:
        from codex_image.webui.app import create_app

        BlockingConcurrentApiImageClient.instances = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("codex_image.webui.auth_routing.OpenAIImagesImageClient", BlockingConcurrentApiImageClient, create=True):
                app = create_app(
                    output_root=root / "tasks",
                    auth_settings_path=root / "auth-settings.json",
                    api_settings_path=root / "api-settings.json",
                    batch_delay_seconds=0,
                    auto_start_queue=False,
                )
                client = TestClient(app)
                client.patch(
                    "/api/api-settings",
                    json={
                        "base_url": "https://api.example.com/v1",
                        "api_key": "test-api-key-worker-secret",
                        "image_model": "gpt-image-2",
                        "api_mode": "images",
                        "images_concurrency": 2,
                    },
                )
                client.patch("/api/auth", json={"source": "api"})
                created = client.post(
                    "/api/generate",
                    data={"prompt": "api progressive batch", "size": "1024x1024", "quality": "low", "n": "2"},
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
                api_client = None
                try:
                    deadline = time.time() + 5
                    while time.time() < deadline and not BlockingConcurrentApiImageClient.instances:
                        time.sleep(0.01)
                    self.assertTrue(BlockingConcurrentApiImageClient.instances)
                    api_client = BlockingConcurrentApiImageClient.instances[0]
                    self.assertTrue(api_client.slow_call_started.wait(timeout=5))

                    running: dict[str, Any] = {}
                    deadline = time.time() + 2
                    while time.time() < deadline:
                        running = json.loads(metadata_path(root / "tasks", task_id).read_text(encoding="utf-8"))
                        if running.get("generated_count") == 1:
                            break
                        time.sleep(0.02)

                    self.assertEqual(running["status"], "running")
                    self.assertEqual(running["generated_count"], 1)
                    self.assertEqual(running["total_count"], 2)
                    self.assertEqual(len(running["output_files"]), 1)
                    self.assertTrue((root / "tasks" / running["output_files"][0]).exists())
                finally:
                    if api_client is not None:
                        api_client.release_slow_call.set()
                    worker.join(timeout=5)

                task = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertFalse(worker_error)
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["generated_count"], 2)
    def test_api_images_queue_worker_publishes_active_running_slots(self) -> None:
        from codex_image.webui.app import create_app

        BlockingActiveConcurrentApiImageClient.instances = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("codex_image.webui.auth_routing.OpenAIImagesImageClient", BlockingActiveConcurrentApiImageClient, create=True):
                app = create_app(
                    output_root=root / "tasks",
                    auth_settings_path=root / "auth-settings.json",
                    api_settings_path=root / "api-settings.json",
                    batch_delay_seconds=0,
                    auto_start_queue=False,
                )
                client = TestClient(app)
                client.patch(
                    "/api/api-settings",
                    json={
                        "base_url": "https://api.example.com/v1",
                        "api_key": "test-api-key-worker-secret",
                        "image_model": "gpt-image-2",
                        "api_mode": "images",
                        "images_concurrency": 2,
                    },
                )
                client.patch("/api/auth", json={"source": "api"})
                created = client.post(
                    "/api/generate",
                    data={"prompt": "api active batch", "size": "1024x1024", "quality": "low", "n": "4"},
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
                api_client = None
                try:
                    deadline = time.time() + 5
                    while time.time() < deadline and not BlockingActiveConcurrentApiImageClient.instances:
                        time.sleep(0.01)
                    self.assertTrue(BlockingActiveConcurrentApiImageClient.instances)
                    api_client = BlockingActiveConcurrentApiImageClient.instances[0]
                    self.assertTrue(api_client.two_requests_active.wait(timeout=5))

                    running: dict[str, Any] = {}
                    deadline = time.time() + 2
                    while time.time() < deadline:
                        running = json.loads(metadata_path(root / "tasks", task_id).read_text(encoding="utf-8"))
                        running_outputs = [item for item in running.get("outputs", []) if item.get("status") == "running"]
                        if len(running_outputs) == 2:
                            break
                        time.sleep(0.02)

                    self.assertEqual(running["status"], "running")
                    self.assertEqual(running["generated_count"], 0)
                    self.assertEqual(running["total_count"], 4)
                    self.assertEqual(
                        [(item["index"], item["status"]) for item in running["outputs"]],
                        [(1, "running"), (2, "running")],
                    )
                finally:
                    if api_client is not None:
                        api_client.release_requests.set()
                    worker.join(timeout=5)

                task = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertFalse(worker_error)
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["generated_count"], 4)
    def test_api_images_queue_worker_uses_provider_concurrency_limit(self) -> None:
        from codex_image.webui.app import create_app

        ConcurrentApiImageClient.reset(release_after_active_requests=2)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("codex_image.webui.auth_routing.OpenAIImagesImageClient", ConcurrentApiImageClient, create=True):
                app = create_app(
                    output_root=root / "tasks",
                    auth_settings_path=root / "auth-settings.json",
                    api_settings_path=root / "api-settings.json",
                    batch_delay_seconds=0,
                    auto_start_queue=False,
                )
                client = TestClient(app)
                client.patch(
                    "/api/api-settings",
                    json={
                        "base_url": "https://api.example.com/v1",
                        "api_key": "test-api-key-worker-secret",
                        "image_model": "gpt-image-2",
                        "api_mode": "images",
                        "images_concurrency": 2,
                    },
                )
                client.patch("/api/auth", json={"source": "api"})
                created = client.post(
                    "/api/generate",
                    data={"prompt": "api limited batch", "size": "1024x1024", "quality": "low", "n": "4"},
                )
                task_id = created.json()["task"]["task_id"]

                asyncio.run(app.state.queue_manager.run_available_once())
                task = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertEqual(task["status"], "completed")
        self.assertEqual(len(ConcurrentApiImageClient.instances), 1)
        api_client = ConcurrentApiImageClient.instances[0]
        self.assertEqual(len(api_client.generate_calls), 4)
        self.assertEqual(api_client.max_active_requests, 2)
        self.assertEqual(task["params"]["api_images_concurrency"], 2)
        self.assertEqual(task["api_images_concurrency"], 2)
    def test_api_images_provider_concurrency_is_shared_across_parallel_tasks(self) -> None:
        from codex_image.webui.app import create_app

        SharedConcurrentApiImageClient.reset()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("codex_image.webui.auth_routing.OpenAIImagesImageClient", SharedConcurrentApiImageClient, create=True):
                app = create_app(
                    output_root=root / "tasks",
                    auth_settings_path=root / "auth-settings.json",
                    api_settings_path=root / "api-settings.json",
                    batch_delay_seconds=0,
                    auto_start_queue=False,
                )
                client = TestClient(app)
                client.patch(
                    "/api/api-settings",
                    json={
                        "base_url": "https://api.example.com/v1",
                        "api_key": "test-api-key-worker-secret",
                        "image_model": "gpt-image-2",
                        "api_mode": "images",
                        "images_concurrency": 3,
                    },
                )
                client.patch("/api/auth", json={"source": "api"})
                created_a = client.post(
                    "/api/generate",
                    data={"prompt": "api shared batch a", "size": "1024x1024", "quality": "low", "n": "4"},
                )
                created_b = client.post(
                    "/api/generate",
                    data={"prompt": "api shared batch b", "size": "1024x1024", "quality": "low", "n": "4"},
                )
                task_ids = [created_a.json()["task"]["task_id"], created_b.json()["task"]["task_id"]]

                channel_count = len(app.state.queue_manager.channels)
                asyncio.run(app.state.queue_manager.run_available_once())
                tasks = [client.get(f"/api/tasks/{task_id}").json()["task"] for task_id in task_ids]

        self.assertEqual(channel_count, 3)
        self.assertEqual([task["status"] for task in tasks], ["completed", "completed"])
        self.assertEqual(SharedConcurrentApiImageClient.generate_call_count, 8)
        self.assertEqual(SharedConcurrentApiImageClient.max_active_requests, 3)
        self.assertEqual([task["api_images_concurrency"] for task in tasks], [3, 3])
    def test_api_images_queue_worker_keeps_successful_outputs_when_later_requests_fail(self) -> None:
        from codex_image.webui.app import create_app

        PartiallyFailingConcurrentApiImageClient.instances = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                "codex_image.webui.auth_routing.OpenAIImagesImageClient",
                PartiallyFailingConcurrentApiImageClient,
                create=True,
            ):
                app = create_app(
                    output_root=root / "tasks",
                    auth_settings_path=root / "auth-settings.json",
                    api_settings_path=root / "api-settings.json",
                    batch_delay_seconds=0,
                    auto_start_queue=False,
                )
                client = TestClient(app)
                client.patch(
                    "/api/api-settings",
                    json={
                        "base_url": "https://api.example.com/v1",
                        "api_key": "test-api-key-worker-secret",
                        "image_model": "gpt-image-2",
                        "api_mode": "images",
                        "images_concurrency": 2,
                    },
                )
                client.patch("/api/auth", json={"source": "api"})
                created = client.post(
                    "/api/generate",
                    data={"prompt": "api partial batch", "size": "1024x1024", "quality": "low", "n": "4"},
                )
                task_id = created.json()["task"]["task_id"]

                asyncio.run(app.state.queue_manager.run_available_once())
                task = client.get(f"/api/tasks/{task_id}").json()["task"]
                output_files_exist = [(root / "tasks" / output_name(task_id, index)).exists() for index in (1, 2, 3, 4)]

        self.assertEqual(task["status"], "partial_failed")
        self.assertEqual(len(PartiallyFailingConcurrentApiImageClient.instances), 1)
        api_client = PartiallyFailingConcurrentApiImageClient.instances[0]
        self.assertEqual(api_client.generate_images_calls, [])
        self.assertEqual(len(api_client.generate_calls), 4)
        self.assertEqual(api_client.max_active_requests, 2)
        self.assertEqual(task["params"]["api_images_concurrency"], 2)
        self.assertEqual(task["api_images_concurrency"], 2)
        self.assertEqual(task["generated_count"], 2)
        self.assertEqual(task["failed_count"], 2)
        self.assertEqual(task["total_count"], 4)
        completed_indexes = [item["index"] for item in task["outputs"] if item["status"] == "completed"]
        failed_errors = [item["error"] for item in task["outputs"] if item["status"] == "failed"]
        self.assertEqual(len(completed_indexes), 2)
        self.assertEqual(len(failed_errors), 2)
        self.assertEqual(task["output_urls"], [output_url(task_id, index) for index in completed_indexes])
        self.assertTrue(any("insufficient_user_quota" in error for error in failed_errors))
        self.assertEqual(sum(output_files_exist), 2)
        self.assertEqual(
            output_files_exist,
            [index in completed_indexes for index in (1, 2, 3, 4)],
        )
    def test_api_images_usage_limit_fails_without_local_account_cache(self) -> None:
        from codex_image.webui.app import create_app

        QuotaLimitedApiImageClient.instances = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("codex_image.webui.auth_routing.OpenAIImagesImageClient", QuotaLimitedApiImageClient, create=True):
                app = create_app(
                    output_root=root / "tasks",
                    auth_settings_path=root / "auth-settings.json",
                    api_settings_path=root / "api-settings.json",
                    batch_delay_seconds=0,
                    auto_start_queue=False,
                )
                client = TestClient(app)
                client.patch(
                    "/api/api-settings",
                    json={
                        "base_url": "https://api.example.com/v1",
                        "api_key": "test-api-key-worker-secret",
                        "image_model": "gpt-image-2",
                        "api_mode": "images",
                        "images_concurrency": 2,
                    },
                )
                client.patch("/api/auth", json={"source": "api"})
                created = client.post(
                    "/api/generate",
                    data={"prompt": "api quota limited", "size": "1024x1024", "quality": "low"},
                )
                task_id = created.json()["task"]["task_id"]

                with self.assertRaisesRegex(RuntimeError, "insufficient_user_quota"):
                    asyncio.run(app.state.queue_manager.run_available_once())
                task = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertEqual(len(QuotaLimitedApiImageClient.instances), 1)
        self.assertEqual(len(QuotaLimitedApiImageClient.instances[0].generate_calls), 1)
        self.assertEqual(task["status"], "failed")
        self.assertFalse(hasattr(app.state, "account_quota_cache"))
    def test_api_images_queue_worker_uses_task_concurrency_after_provider_switch(self) -> None:
        from codex_image.webui.app import create_app

        ConcurrentApiImageClient.reset(release_after_active_requests=2)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("codex_image.webui.auth_routing.OpenAIImagesImageClient", ConcurrentApiImageClient, create=True):
                app = create_app(
                    output_root=root / "tasks",
                    auth_settings_path=root / "auth-settings.json",
                    api_settings_path=root / "api-settings.json",
                    batch_delay_seconds=0,
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
                                "images_concurrency": 1,
                            },
                            {
                                "id": "vendor-b",
                                "name": "Vendor B",
                                "base_url": "https://vendor-b.example.com/v1",
                                "api_key": "test-api-key-vendor-b-secret",
                                "image_model": "vendor-b-image",
                                "api_mode": "images",
                                "images_concurrency": 2,
                            },
                        ],
                    },
                )
                client.patch("/api/auth", json={"source": "api"})
                created = client.post(
                    "/api/generate",
                    data={
                        "prompt": "api provider concurrency",
                        "size": "1024x1024",
                        "quality": "low",
                        "n": "4",
                        "api_provider_id": "vendor-b",
                    },
                )
                task_id = created.json()["task"]["task_id"]
                client.patch("/api/api-settings", json={"active_provider_id": "vendor-a"})

                asyncio.run(app.state.queue_manager.run_available_once())
                task = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["api_provider_id"], "vendor-b")
        self.assertEqual(task["params"]["api_images_concurrency"], 2)
        self.assertEqual(task["api_images_concurrency"], 2)
        self.assertEqual(len(ConcurrentApiImageClient.instances), 1)
        api_client = ConcurrentApiImageClient.instances[0]
        self.assertEqual(api_client.base_url, "https://vendor-b.example.com/v1")
        self.assertEqual(api_client.max_active_requests, 2)
    def test_api_source_request_preview_uses_direct_images_payload(self) -> None:
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
                    "base_url": "https://api.example.com/v1",
                    "api_key": "test-api-key-preview-secret",
                    "image_model": "gpt-image-2",
                },
            )
            client.patch("/api/auth", json={"source": "api"})

            response = client.post(
                "/api/generate",
                data={
                    "prompt": "api preview",
                    "main_model": "gpt-5.5",
                    "size": "1024x1536",
                    "quality": "auto",
                    "n": "4",
                    "prompt_fidelity": "off",
                },
            )
            body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["request"]["endpoint"], "/images/generations")
        self.assertEqual(body["task"]["requested_backend"], "openai_images")
        self.assertEqual(body["request"]["webui_requested_backend"], "openai_images")
        self.assertEqual(body["request"]["model"], "gpt-image-2")
        self.assertEqual(body["request"]["prompt"], "api preview")
        self.assertEqual(body["request"]["n"], 1)
        self.assertNotIn("tools", body["request"])
        self.assertNotIn("gpt-5.5", json.dumps(body["request"], ensure_ascii=False))
        self.assertNotIn("test-api-key-preview-secret", json.dumps(body, ensure_ascii=False))
    def test_api_source_request_preview_uses_responses_payload_when_selected(self) -> None:
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
                    "base_url": "https://api.example.com/v1",
                    "api_key": "test-api-key-preview-secret",
                    "image_model": "gpt-image-2",
                    "api_mode": "responses",
                },
            )
            client.patch("/api/auth", json={"source": "api"})

            response = client.post(
                "/api/generate",
                data={
                    "prompt": "api responses preview",
                    "main_model": "gpt-5.5",
                    "size": "1024x1536",
                    "quality": "auto",
                    "api_mode": "responses",
                },
            )
            body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["task"]["params"]["api_mode"], "responses")
        self.assertEqual(body["task"]["requested_backend"], "openai_responses")
        self.assertEqual(body["request"]["webui_requested_backend"], "openai_responses")
        self.assertEqual(body["request"]["endpoint"], "/responses")
        self.assertEqual(body["request"]["model"], "gpt-5.5")
        self.assertEqual(body["request"]["tools"][0]["type"], "image_generation")
        self.assertEqual(body["request"]["tools"][0]["model"], "gpt-image-2")
        self.assertEqual(body["request"]["tools"][0]["action"], "generate")
        self.assertNotIn("test-api-key-preview-secret", json.dumps(body, ensure_ascii=False))

    def test_api_responses_preview_can_enable_web_search(self) -> None:
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
                    "base_url": "https://api.example.com/v1",
                    "api_key": "test-api-key-preview-secret",
                    "image_model": "gpt-image-2",
                    "api_mode": "responses",
                },
            )
            client.patch("/api/auth", json={"source": "api"})

            response = client.post(
                "/api/generate",
                data={
                    "prompt": "api responses search preview",
                    "main_model": "gpt-5.5",
                    "size": "1536x864",
                    "quality": "low",
                    "api_mode": "responses",
                    "web_search": "true",
                },
            )
            body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["task"]["params"]["web_search"])
        self.assertEqual([tool["type"] for tool in body["request"]["tools"]], ["web_search", "image_generation"])
        self.assertEqual(body["request"]["tools"][1]["quality"], "low")
        self.assertEqual(body["request"]["tool_choice"], "required")
        self.assertFalse(body["request"]["parallel_tool_calls"])

    def test_api_queue_worker_uses_saved_responses_client_for_responses_tasks(self) -> None:
        from codex_image.webui.app import create_app

        CapturingApiResponsesImageClient.instances = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("codex_image.webui.auth_routing.OpenAIResponsesImageClient", CapturingApiResponsesImageClient, create=True):
                app = create_app(
                    output_root=root / "tasks",
                    auth_settings_path=root / "auth-settings.json",
                    api_settings_path=root / "api-settings.json",
                    batch_delay_seconds=0,
                    auto_start_queue=False,
                )
                client = TestClient(app)
                client.patch(
                    "/api/api-settings",
                    json={
                        "base_url": "https://api.example.com/v1",
                        "api_key": "test-api-key-worker-responses-secret",
                        "image_model": "gpt-image-2",
                        "api_mode": "responses",
                    },
                )
                client.patch("/api/auth", json={"source": "api"})
                created = client.post(
                    "/api/generate",
                    data={
                        "prompt": "api responses worker",
                        "main_model": "gpt-5.5",
                        "size": "1024x1024",
                        "quality": "low",
                        "api_mode": "responses",
                    },
                )
                task_id = created.json()["task"]["task_id"]
                client.patch("/api/api-settings", json={"api_mode": "images"})

                asyncio.run(app.state.queue_manager.run_available_once())
                task = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["assigned_auth_source"], "api")
        self.assertEqual(task["params"]["api_mode"], "responses")
        self.assertEqual(task["requested_backend"], "openai_responses")
        self.assertEqual(task["backend"], "openai_responses")
        self.assertEqual(len(CapturingApiResponsesImageClient.instances), 1)
        api_client = CapturingApiResponsesImageClient.instances[0]
        self.assertEqual(api_client.api_key, "test-api-key-worker-responses-secret")
        self.assertEqual(api_client.base_url, "https://api.example.com/v1")
        self.assertEqual(api_client.image_model, "gpt-image-2")
    def test_settings_routes_report_paths_and_persist_restart_required_changes(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings_path = root / "webui-settings.json"
            app = create_app(output_root=root / "outputs", webui_settings_path=settings_path, auth_checker=lambda: True, auto_start_queue=False)
            client = TestClient(app)

            initial = client.get("/api/settings")
            changed = client.patch(
                "/api/settings",
                json={
                    "input_root": str(root / "new-inputs"),
                    "output_root": str(root / "new-outputs"),
                    "gallery_root": str(root / "new-inputs" / "gallery"),
                    "source_data_root": str(root / "new-outputs" / "source-data"),
                },
            )
            invalid_gallery = client.patch(
                "/api/settings",
                json={
                    "input_root": str(root / "inputs"),
                    "output_root": str(root / "outputs"),
                    "gallery_root": str(root / "outside-gallery"),
                    "source_data_root": str(root / "outputs" / "source-data"),
                },
            )
            persisted = json.loads(settings_path.read_text(encoding="utf-8"))

        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()["settings"]["output_root"], str(root / "outputs"))
        self.assertEqual(changed.status_code, 200)
        self.assertTrue(changed.json()["restart_required"])
        self.assertEqual(persisted["input_root"], str(root / "new-inputs"))
        self.assertEqual(invalid_gallery.status_code, 400)
    def test_color_palette_endpoint_defaults_and_persists_normalized_colors(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            color_settings_path = root / "webui-color-settings.json"
            app = create_app(
                output_root=root / "outputs",
                color_settings_path=color_settings_path,
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            client = TestClient(app)

            initial = client.get("/api/color-palette")
            changed = client.patch(
                "/api/color-palette",
                json={
                    "favorites": [
                        {"name": "brand green", "hex": "#457b66"},
                        {"name": "short blue", "hex": "#0af"},
                        {"name": "duplicate green", "hex": "#457B66"},
                    ],
                    "recent_colors": ["#f60", "#123456"],
                    "recent_limit": 4,
                },
            )
            persisted = json.loads(color_settings_path.read_text(encoding="utf-8"))

        self.assertEqual(initial.status_code, 200)
        self.assertEqual(
            [item["hex"] for item in initial.json()["palette"]["favorites"]],
            ["#FFFFFF", "#111111", "#F6E8D8", "#E6F0EC", "#457B66", "#F4B183", "#B7D7F0", "#F8D7DA"],
        )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(
            changed.json()["palette"]["favorites"],
            [
                {"name": "brand green", "hex": "#457B66", "order": 10},
                {"name": "short blue", "hex": "#00AAFF", "order": 20},
            ],
        )
        self.assertEqual(changed.json()["palette"]["recent_colors"], ["#FF6600", "#123456"])
        self.assertEqual(changed.json()["palette"]["recent_limit"], 4)
        self.assertEqual(persisted["favorites"][1]["hex"], "#00AAFF")
    def test_color_palette_endpoint_rejects_invalid_hex_colors(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                output_root=Path(tmp) / "outputs",
                color_settings_path=Path(tmp) / "webui-color-settings.json",
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            response = TestClient(app).patch(
                "/api/color-palette",
                json={"favorites": [{"name": "bad", "hex": "not-a-color"}]},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid hex color", response.json()["detail"])
    def test_color_palette_css_export_contains_named_swatches(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                output_root=Path(tmp) / "outputs",
                color_settings_path=Path(tmp) / "webui-color-settings.json",
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            client = TestClient(app)
            client.patch(
                "/api/color-palette",
                json={
                    "favorites": [
                        {"name": "Brand Green", "hex": "#457b66"},
                        {"name": "Warm Cream", "hex": "#f6e8d8"},
                    ]
                },
            )
            response = client.get("/api/color-palette/export.css")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"].split(";")[0], "text/css")
        self.assertIn("--brand-green: #457B66;", response.text)
        self.assertIn("--warm-cream: #F6E8D8;", response.text)
        self.assertIn(".swatch-brand-green { color: #457B66; }", response.text)
    def test_color_palette_imports_photoshop_aco_swatches(self) -> None:
        from codex_image.webui.app import create_app

        def color_record(red: int, green: int, blue: int) -> bytes:
            return struct.pack(
                ">HHHHH",
                0,
                round(red * 65535 / 255),
                round(green * 65535 / 255),
                round(blue * 65535 / 255),
                0,
            )

        def unicode_name(name: str) -> bytes:
            encoded = f"{name}\0".encode("utf-16-be")
            return struct.pack(">I", len(name) + 1) + encoded

        records = [color_record(51, 102, 153), color_record(69, 123, 102)]
        aco_payload = struct.pack(">HH", 1, len(records)) + b"".join(records)
        aco_payload += struct.pack(">HH", 2, len(records))
        aco_payload += records[0] + unicode_name("QA Blue")
        aco_payload += records[1] + unicode_name("Duplicate Green")

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                output_root=Path(tmp) / "outputs",
                color_settings_path=Path(tmp) / "webui-color-settings.json",
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            response = TestClient(app).post(
                "/api/color-palette/import",
                files={"file": ("brand.aco", aco_payload, "application/octet-stream")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["imported"], 1)
        self.assertIn({"name": "QA Blue", "hex": "#336699", "order": 90}, response.json()["palette"]["favorites"])
        self.assertEqual(
            [item["hex"] for item in response.json()["palette"]["favorites"]].count("#457B66"),
            1,
        )
    def test_color_palette_imports_css_colors(self) -> None:
        from codex_image.webui.app import create_app

        css_payload = b":root { --brand-orange: #f60; } .accent { color: rgb(12, 34, 56); }"
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                output_root=Path(tmp) / "outputs",
                color_settings_path=Path(tmp) / "webui-color-settings.json",
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            response = TestClient(app).post(
                "/api/color-palette/import",
                files={"file": ("brand.css", css_payload, "text/css")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["imported"], 2)
        self.assertIn({"name": "brand orange", "hex": "#FF6600", "order": 90}, response.json()["palette"]["favorites"])
        self.assertIn({"name": "Imported 2", "hex": "#0C2238", "order": 100}, response.json()["palette"]["favorites"])
    def test_color_palette_import_rejects_files_without_colors(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                output_root=Path(tmp) / "outputs",
                color_settings_path=Path(tmp) / "webui-color-settings.json",
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            response = TestClient(app).post(
                "/api/color-palette/import",
                files={"file": ("empty.css", b".empty { display: block; }", "text/css")},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("No importable colors", response.json()["detail"])
    def test_prompt_snippet_endpoint_defaults_and_persists_normalized_snippets(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snippets_path = root / "webui-prompt-snippets.json"
            app = create_app(
                output_root=root / "outputs",
                prompt_snippets_path=snippets_path,
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            client = TestClient(app)

            initial = client.get("/api/prompt-snippets")
            created = client.post(
                "/api/prompt-snippets",
                json={
                    "tag": "〜电商高级感",
                    "title": "电商高级感",
                    "content": "高级商业摄影，柔和棚拍光，干净背景。",
                    "category": "风格",
                },
            )
            snippet_id = created.json()["snippet"]["id"]
            changed = client.patch(
                f"/api/prompt-snippets/{snippet_id}",
                json={"tag": "∼商业质感", "content": "高级商业摄影，保留产品真实材质。"},
            )
            listed = client.get("/api/prompt-snippets")
            persisted = json.loads(snippets_path.read_text(encoding="utf-8"))

        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()["snippets"], [])
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["snippet"]["tag"], "电商高级感")
        self.assertEqual(created.json()["snippet"]["category"], "风格")
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()["snippet"]["tag"], "商业质感")
        self.assertEqual(changed.json()["snippet"]["title"], "电商高级感")
        self.assertEqual(listed.json()["snippets"][0]["content"], "高级商业摄影，保留产品真实材质。")
        self.assertEqual(persisted["snippets"][0]["tag"], "商业质感")
    def test_prompt_templates_api_persists_local_json_and_defaults_to_gpt_image_2(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            templates_path = root / "webui-prompt-templates.json"
            app = create_app(
                output_root=root / "outputs",
                prompt_templates_path=templates_path,
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            client = TestClient(app)

            initial = client.get("/api/prompt-templates")
            self.assertEqual(initial.status_code, 200)
            self.assertEqual(initial.json()["templates"], [])
            self.assertIn({"id": "常用", "name": "常用", "order": 10}, initial.json()["categories"])

            created = client.post(
                "/api/prompt-templates",
                json={
                    "title": "电商主图",
                    "short_title": "主图",
                    "content": "为 {{产品名}} 生成干净的电商主图，白底，柔和阴影，gpt-image-2。",
                    "category": "产品",
                    "tags": ["产品", "电商"],
                    "mode": "text_to_image",
                    "notes": "适合先跑基准图。",
                    "thumbnail_url": "/outputs/task-001/result-1.png",
                    "favorite": True,
                },
            )
            self.assertEqual(created.status_code, 200)
            template = created.json()["template"]
            self.assertEqual(template["title"], "电商主图")
            self.assertEqual(template["short_title"], "主图")
            self.assertEqual(template["model_hint"], "gpt-image-2")
            self.assertEqual(template["thumbnail_url"], "/outputs/task-001/result-1.png")
            self.assertEqual(template["usage_count"], 0)
            self.assertTrue(template["favorite"])
            self.assertEqual(template["variables"], ["产品名"])

            template_id = template["id"]
            used = client.post(f"/api/prompt-templates/{template_id}/use")
            self.assertEqual(used.status_code, 200)
            self.assertEqual(used.json()["template"]["usage_count"], 1)

            updated = client.patch(
                f"/api/prompt-templates/{template_id}",
                json={"short_title": "商品", "tags": ["产品", "主图", "复用"]},
            )
            self.assertEqual(updated.status_code, 200)
            self.assertEqual(updated.json()["template"]["short_title"], "商品")
            self.assertEqual(updated.json()["template"]["tags"], ["产品", "主图", "复用"])

            listed = client.get("/api/prompt-templates")
            self.assertEqual(listed.status_code, 200)
            self.assertEqual(len(listed.json()["templates"]), 1)
            self.assertTrue(templates_path.exists())
            saved = json.loads(templates_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["version"], 1)
            self.assertEqual(saved["templates"][0]["short_title"], "商品")

            deleted = client.delete(f"/api/prompt-templates/{template_id}")
            self.assertEqual(deleted.status_code, 200)
            self.assertEqual(deleted.json()["templates"], [])

    def test_prompt_templates_support_categories_thumbnails_and_pack_import_export(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            templates_path = root / "webui-prompt-templates.json"
            app = create_app(
                output_root=root / "outputs",
                prompt_templates_path=templates_path,
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            client = TestClient(app)

            created_category = client.post("/api/prompt-template-categories", json={"name": "品牌KV"})
            self.assertEqual(created_category.status_code, 200)
            self.assertEqual(created_category.json()["category"]["id"], "品牌KV")

            renamed_category = client.patch("/api/prompt-template-categories/%E5%93%81%E7%89%8CKV", json={"name": "活动KV"})
            self.assertEqual(renamed_category.status_code, 200)
            self.assertEqual(renamed_category.json()["category"]["id"], "活动KV")

            created_template = client.post(
                "/api/prompt-templates",
                json={
                    "title": "活动主视觉",
                    "content": "生成 {{活动名}} 主视觉，保持真实商品材质。",
                    "category": "活动KV",
                    "thumbnail_url": "/outputs/campaign/001.png",
                },
            )
            self.assertEqual(created_template.status_code, 200)
            self.assertEqual(created_template.json()["template"]["category"], "活动KV")
            self.assertEqual(created_template.json()["template"]["thumbnail_url"], "/outputs/campaign/001.png")

            deleted_category = client.delete("/api/prompt-template-categories/%E6%B4%BB%E5%8A%A8KV")
            self.assertEqual(deleted_category.status_code, 200)
            self.assertEqual(deleted_category.json()["templates"][0]["category"], "常用")

            imported_json = client.post(
                "/api/prompt-templates/import",
                files={
                    "file": (
                        "community-pack.json",
                        json.dumps(
                            {
                                "categories": ["外部包"],
                                "prompts": [
                                    {
                                        "title": "社区产品图",
                                        "prompt": "商业产品图，主体是 {{产品名}}，保留真实材质。",
                                        "category": "外部包",
                                        "tags": "产品,商业",
                                        "model": "external-model",
                                        "thumbnail": "/outputs/community/product.png",
                                    }
                                ],
                            },
                            ensure_ascii=False,
                        ).encode("utf-8"),
                        "application/json",
                    )
                },
            )
            self.assertEqual(imported_json.status_code, 200)
            self.assertEqual(imported_json.json()["imported"], 1)
            imported_template = next(item for item in imported_json.json()["templates"] if item["title"] == "社区产品图")
            self.assertEqual(imported_template["model_hint"], "gpt-image-2")
            self.assertEqual(imported_template["thumbnail_url"], "/outputs/community/product.png")

            imported_markdown = client.post(
                "/api/prompt-templates/import",
                files={
                    "file": (
                        "community-pack.md",
                        (
                            "# 社区提示词包\n\n"
                            "## 胶片人像\n"
                            "Category: 人像\n"
                            "Tags: 胶片, 人像\n"
                            "Thumbnail: /outputs/community/portrait.png\n\n"
                            "```prompt\n"
                            "生成胶片质感人像，主体是 {{人物}}。\n"
                            "```\n"
                        ).encode("utf-8"),
                        "text/markdown",
                    )
                },
            )
            self.assertEqual(imported_markdown.status_code, 200)
            self.assertEqual(imported_markdown.json()["imported"], 1)

            exported = client.get("/api/prompt-templates/export.json")
            self.assertEqual(exported.status_code, 200)
            self.assertIn("categories", exported.json())
            self.assertGreaterEqual(len(exported.json()["templates"]), 3)
    def test_prompt_templates_reject_invalid_payloads_and_model_copy(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "outputs",
                prompt_templates_path=root / "webui-prompt-templates.json",
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            client = TestClient(app)

            missing_title = client.post("/api/prompt-templates", json={"content": "Only content"})
            self.assertEqual(missing_title.status_code, 400)
            self.assertIn("Invalid prompt template title", missing_title.json()["detail"])

            missing_content = client.post("/api/prompt-templates", json={"title": "No content"})
            self.assertEqual(missing_content.status_code, 400)
            self.assertIn("Invalid prompt template content", missing_content.json()["detail"])

            external_model = client.post(
                "/api/prompt-templates",
                json={
                    "title": "外部模型",
                    "content": "生成一张产品图",
                    "model_hint": "external-model",
                },
            )
            self.assertEqual(external_model.status_code, 400)
            self.assertIn("Unsupported prompt template model hint", external_model.json()["detail"])
    def test_settings_store_exports_webui_settings_classes(self) -> None:
        from codex_image.webui.settings_store import (
            ApiSettings,
            AuthSettings,
            ColorPaletteSettings,
            PromptSnippetSettings,
            PromptTemplateSettings,
            WebUISettings,
        )

        self.assertTrue(callable(WebUISettings))
        self.assertTrue(callable(AuthSettings))
        self.assertTrue(callable(ApiSettings))
        self.assertTrue(callable(ColorPaletteSettings))
        self.assertTrue(callable(PromptSnippetSettings))
        self.assertTrue(callable(PromptTemplateSettings))
    def test_prompt_snippet_endpoint_rejects_duplicate_or_invalid_snippets(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                output_root=Path(tmp) / "outputs",
                prompt_snippets_path=Path(tmp) / "webui-prompt-snippets.json",
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            client = TestClient(app)
            created = client.post(
                "/api/prompt-snippets",
                json={"tag": "~商业质感", "content": "高级商业摄影。"},
            )
            duplicate = client.post(
                "/api/prompt-snippets",
                json={"tag": "商业质感", "content": "重复。"},
            )
            invalid = client.post(
                "/api/prompt-snippets",
                json={"tag": "bad tag", "content": "包含空格的 tag 不适合作为 chip。"},
            )

        self.assertEqual(created.status_code, 200)
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("Duplicate prompt snippet tag", duplicate.json()["detail"])
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("Invalid prompt snippet tag", invalid.json()["detail"])
