from __future__ import annotations

import json
import io
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


class WebUIProviderRoutingTests(unittest.TestCase):
    @staticmethod
    def _png_bytes() -> bytes:
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (2, 2), "white").save(buffer, format="PNG")
        return buffer.getvalue()

    def assert_no_secret_field(self, value) -> None:
        if isinstance(value, dict):
            self.assertNotIn("api_key", value)
            for item in value.values():
                self.assert_no_secret_field(item)
        elif isinstance(value, list):
            for item in value:
                self.assert_no_secret_field(item)

    def _app(self, root: Path, *, api_settings: dict | None = None):
        from codex_image.webui.app import create_app

        api_path = root / "api-settings.json"
        if api_settings is not None:
            api_path.write_text(json.dumps(api_settings), encoding="utf-8")
        return create_app(
            output_root=root / "outputs",
            api_settings_path=api_path,
            auth_settings_path=root / "auth-settings.json",
            webui_settings_path=root / "webui-settings.json",
            client_factory=lambda: object(),
            auth_checker=lambda: True,
            auto_start_queue=False,
        )

    def test_catalog_contains_builtin_codex_without_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = TestClient(self._app(Path(tmp))).get("/api/generation-catalog").json()

        codex = next(provider for provider in payload["providers"] if provider["id"] == "codex")
        self.assertEqual(payload["schema_version"], 1)
        self.assertTrue(codex["builtin"])
        self.assert_no_secret_field(payload)
        self.assertEqual(
            [
                (binding["id"], binding["protocol_profile"], binding["parameter_codec"])
                for binding in codex["bindings"]
            ],
            [
                ("codex-gpt-image-2-images", "codex_images", "gpt_codex_images"),
                ("codex-gpt-image-2-responses", "codex_responses", "gpt_codex_responses"),
            ],
        )

    def test_explicit_codex_responses_binding_is_snapshotted_without_global_mode_change(self) -> None:
        parameters = {"canvas.size": "1024x1024", "output.count": 1}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = TestClient(self._app(root))
            response = client.post(
                "/api/generate",
                data={
                    "prompt": "binding selection",
                    "canonical_model_id": "gpt-image-2",
                    "provider_id": "codex",
                    "binding_id": "codex-gpt-image-2-responses",
                    "parameters_json": json.dumps(parameters),
                },
            )
            task_id = response.json()["task"]["task_id"]
            metadata = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertEqual(response.status_code, 200)
        snapshot = metadata["generation_snapshot"]
        self.assertEqual(snapshot["binding_id"], "codex-gpt-image-2-responses")
        self.assertEqual(snapshot["protocol_profile"], "codex_responses")
        self.assertEqual(metadata["requested_backend"], "codex_responses")

    def test_canonical_codex_gpt_bindings_restore_ratio_prompt_from_canvas_size(self) -> None:
        for binding_id, protocol_profile in (
            ("codex-gpt-image-2-images", "codex_images"),
            ("codex-gpt-image-2-responses", "codex_responses"),
        ):
            for size, ratio, orientation in (
                ("1024x1024", "1:1", "square"),
                ("864x1536", "9:16", "portrait"),
            ):
                with self.subTest(binding_id=binding_id, size=size), tempfile.TemporaryDirectory() as tmp:
                    client = TestClient(self._app(Path(tmp)))
                    response = client.post(
                        "/api/generate",
                        data={
                            "prompt": "codex composition",
                            "canonical_model_id": "gpt-image-2",
                            "provider_id": "codex",
                            "binding_id": binding_id,
                            "parameters_json": json.dumps({"canvas.size": size, "output.count": 1}),
                        },
                    )
                    body = response.json()
                    task = body["task"]

                self.assertEqual(response.status_code, 200)
                self.assertEqual(task["requested_backend"], protocol_profile)
                expected_prompt = f"codex composition\n\n将宽高比设为 {ratio}"
                request_prompt = (
                    body["request"]["prompt"]
                    if protocol_profile == "codex_images"
                    else body["request"]["input"][0]["content"][0]["text"]
                )
                self.assertEqual(task["prompt_for_model"], expected_prompt)
                self.assertTrue(request_prompt.endswith(expected_prompt))
                self.assertEqual(task["params"]["size"], size)
                self.assertEqual(task["params"]["ratio"], ratio)
                self.assertEqual(task["params"]["orientation"], orientation)

    def test_canonical_api_gpt_bindings_do_not_add_codex_ratio_fallback(self) -> None:
        parameters = {"canvas.size": "864x1536", "output.count": 1}
        for binding_id, protocol_profile, parameter_codec in (
            ("relay-images", "openai_images", "gpt_openai_images"),
            ("relay-responses", "openai_responses", "gpt_openai_responses"),
        ):
            with self.subTest(binding_id=binding_id), tempfile.TemporaryDirectory() as tmp:
                settings = {
                    "schema_version": 2,
                    "active_provider_id": "relay",
                    "default_provider_by_model": {"gpt-image-2": "relay"},
                    "providers": [{
                        "id": "relay", "name": "Relay", "base_url": "https://relay.example/v1",
                        "api_key": "unit-test-secret", "auth_scheme": "bearer", "concurrency": 2,
                        "bindings": [{
                            "id": binding_id, "canonical_model_id": "gpt-image-2",
                            "remote_model_id": "relay/gpt-image-2", "protocol_profile": protocol_profile,
                            "parameter_codec": parameter_codec, "operations": ["generate", "edit"],
                        }],
                    }],
                }
                client = TestClient(self._app(Path(tmp), api_settings=settings))
                response = client.post(
                    "/api/generate",
                    data={
                        "prompt": "api portrait",
                        "canonical_model_id": "gpt-image-2",
                        "provider_id": "relay",
                        "binding_id": binding_id,
                        "parameters_json": json.dumps(parameters),
                    },
                )
                body = response.json()
                task = body["task"]

            self.assertEqual(response.status_code, 200)
            self.assertEqual(task["requested_backend"], protocol_profile)
            self.assertEqual(task["prompt_for_model"], "api portrait")
            request_prompt = (
                body["request"]["prompt"]
                if protocol_profile == "openai_images"
                else body["request"]["input"][0]["content"][0]["text"]
            )
            self.assertTrue(request_prompt.endswith("api portrait"))
            self.assertNotIn("将宽高比设为", request_prompt)
            self.assertNotIn("ratio", task["params"])
            self.assertNotIn("orientation", task["params"])

    def test_canonical_api_gpt_bindings_add_localized_ratio_prompt_when_enabled(self) -> None:
        parameters = {"canvas.size": "864x1536", "output.count": 1}
        for binding_id, protocol_profile, parameter_codec in (
            ("relay-images", "openai_images", "gpt_openai_images"),
            ("relay-responses", "openai_responses", "gpt_openai_responses"),
        ):
            for locale, instruction in (
                ("en", "Set the aspect ratio to 9:16."),
                ("zh-TW", "將寬高比設為 9:16"),
            ):
                with self.subTest(binding_id=binding_id, locale=locale), tempfile.TemporaryDirectory() as tmp:
                    settings = {
                        "schema_version": 2,
                        "active_provider_id": "relay",
                        "default_provider_by_model": {"gpt-image-2": "relay"},
                        "providers": [{
                            "id": "relay", "name": "Relay", "base_url": "https://relay.example/v1",
                            "api_key": "unit-test-secret", "auth_scheme": "bearer", "concurrency": 2,
                            "bindings": [{
                                "id": binding_id, "canonical_model_id": "gpt-image-2",
                                "remote_model_id": "relay/gpt-image-2", "protocol_profile": protocol_profile,
                                "parameter_codec": parameter_codec, "operations": ["generate", "edit"],
                                "append_aspect_ratio_prompt": True,
                            }],
                        }],
                    }
                    client = TestClient(self._app(Path(tmp), api_settings=settings))
                    response = client.post(
                        "/api/generate",
                        data={
                            "prompt": "api portrait",
                            "canonical_model_id": "gpt-image-2",
                            "provider_id": "relay",
                            "binding_id": binding_id,
                            "parameters_json": json.dumps(parameters),
                            "ui_language": locale,
                        },
                    )
                    body = response.json()
                    task = body["task"]

                self.assertEqual(response.status_code, 200)
                expected_prompt = f"api portrait\n\n{instruction}"
                request_prompt = (
                    body["request"]["prompt"]
                    if protocol_profile == "openai_images"
                    else body["request"]["input"][0]["content"][0]["text"]
                )
                self.assertEqual(task["prompt_for_model"], expected_prompt)
                self.assertTrue(request_prompt.endswith(expected_prompt))
                self.assertNotIn("ratio", task["params"])

    def test_catalog_codex_availability_uses_real_codex_checker(self) -> None:
        from unittest.mock import patch
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp, patch(
            "codex_image.webui.app._codex_auth_available", return_value=False
        ):
            root = Path(tmp)
            (root / "auth.json").write_text(json.dumps({"source": "api"}), encoding="utf-8")
            (root / "api.json").write_text(json.dumps({
                "api_key": "api-source-key", "base_url": "https://relay.example/v1",
                "image_model": "gpt-image-2",
            }), encoding="utf-8")
            app = create_app(
                output_root=root / "outputs", auth_settings_path=root / "auth.json",
                api_settings_path=root / "api.json", webui_settings_path=root / "webui.json",
                auto_start_queue=False,
            )
            payload = TestClient(app).get("/api/generation-catalog").json()
        codex = next(item for item in payload["providers"] if item["id"] == "codex")
        self.assertFalse(codex["available"])
        self.assertFalse(payload["codex"]["available"])

    def test_catalog_drops_legacy_connection_auth_scheme(self) -> None:
        settings = {
            "schema_version": 2,
            "codex_mode": "images",
            "active_provider_id": "relay",
            "default_provider_by_model": {"gpt-image-2": "relay"},
            "providers": [{
                "id": "relay",
                "name": "Relay",
                "base_url": "https://relay.example/v1",
                "api_key": "relay-key",
                "auth_scheme": "basic",
                "concurrency": 1,
                "bindings": [{
                    "id": "relay-gpt",
                    "canonical_model_id": "gpt-image-2",
                    "remote_model_id": "custom-gpt",
                    "protocol_profile": "openai_images",
                    "parameter_codec": "gpt_openai_images",
                    "operations": ["generate"],
                }],
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            payload = TestClient(self._app(Path(tmp), api_settings=settings)).get(
                "/api/generation-catalog"
            ).json()

        relay = next(provider for provider in payload["providers"] if provider["id"] == "relay")
        self.assertNotIn("auth_scheme", relay)

    def test_canonical_external_provider_is_not_blocked_by_current_source_auth(self) -> None:
        settings = {
            "schema_version": 2, "codex_mode": "images", "active_provider_id": "relay",
            "default_provider_by_model": {"gpt-image-2": "relay"},
            "providers": [{
                "id": "relay", "name": "Relay", "base_url": "https://relay.example/v1",
                "api_key": "relay-key", "auth_scheme": "bearer", "concurrency": 1,
                "bindings": [{
                    "id": "relay-gpt", "canonical_model_id": "gpt-image-2",
                    "remote_model_id": "custom-gpt", "protocol_profile": "openai_images",
                    "parameter_codec": "gpt_openai_images", "operations": ["generate"],
                }],
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            from codex_image.webui.app import create_app
            api_path = root / "api-settings.json"
            api_path.write_text(json.dumps(settings), encoding="utf-8")
            app = create_app(
                output_root=root / "outputs", api_settings_path=api_path,
                auth_settings_path=root / "auth.json", webui_settings_path=root / "webui.json",
                client_factory=lambda: object(), auth_checker=lambda: False,
                auto_start_queue=False,
            )
            response = TestClient(app).post("/api/generate", data={
                "prompt": "external", "canonical_model_id": "gpt-image-2",
                "provider_id": "relay",
                "parameters_json": json.dumps({"canvas.size": "1024x1024", "output.count": 1}),
            })
        self.assertEqual(response.status_code, 200)

    def test_legacy_form_is_translated_to_gpt_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = TestClient(self._app(root))
            response = client.post(
                "/api/generate",
                data={"prompt": "legacy", "model": "gpt-image-2", "size": "1024x1024", "quality": "high"},
            )
            task_id = response.json()["task"]["task_id"]
            metadata = client.get(f"/api/tasks/{task_id}").json()["task"]

        self.assertEqual(response.status_code, 200)
        snapshot = metadata["generation_snapshot"]
        self.assertEqual(snapshot["canonical_model_id"], "gpt-image-2")
        self.assertEqual(snapshot["requested_parameters"]["canvas.size"], "1024x1024")
        self.assertNotIn("legacy", json.dumps(snapshot))

    def test_snapshot_metadata_excludes_prompt_key_and_inline_image_marker(self) -> None:
        marker = b"RAW-INLINE-IMAGE-MARKER"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = self._app(root)
            response = TestClient(app).post(
                "/api/generate",
                data={"prompt": "PRIVATE-PROMPT-MARKER", "size": "1024x1024", "quality": "low"},
                files={"reference_images": ("marker.png", marker, "image/png")},
            )
            task_id = response.json()["task"]["task_id"]
            metadata = app.state.storage.read_metadata(task_id)

        encoded = json.dumps(metadata["generation_snapshot"])
        self.assertNotIn("PRIVATE-PROMPT-MARKER", encoded)
        self.assertNotIn("RAW-INLINE-IMAGE-MARKER", encoded)
        self.assertNotIn("data:image/png;base64", encoded)

    def test_new_form_rejects_provider_not_bound_to_model(self) -> None:
        settings = {
            "schema_version": 2,
            "codex_mode": "images",
            "active_provider_id": "gpt-only-relay",
            "default_provider_by_model": {"gpt-image-2": "gpt-only-relay"},
            "providers": [{
                "id": "gpt-only-relay", "name": "GPT Relay", "base_url": "https://relay.example/v1",
                "api_key": "unit-test-secret", "auth_scheme": "bearer", "concurrency": 2,
                "bindings": [{
                    "id": "gpt-binding", "canonical_model_id": "gpt-image-2",
                    "remote_model_id": "custom/gpt", "protocol_profile": "openai_images",
                    "parameter_codec": "gpt_openai_images", "operations": ["generate", "edit"],
                }],
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            response = TestClient(self._app(Path(tmp), api_settings=settings)).post(
                "/api/generate",
                data={
                    "prompt": "future", "canonical_model_id": "nano-banana-pro",
                    "provider_id": "gpt-only-relay",
                    "parameters_json": json.dumps({"canvas.aspect_ratio": "1:1", "canvas.resolution": "2K", "output.count": 1}),
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["code"], "provider_model_binding_missing")

    def test_new_fields_are_all_or_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            response = TestClient(self._app(Path(tmp))).post(
                "/api/generate",
                data={"prompt": "partial", "canonical_model_id": "gpt-image-2"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["code"], "generation_request_invalid")

    def test_canonical_form_rejects_explicit_legacy_routing_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            response = TestClient(self._app(Path(tmp))).post(
                "/api/generate",
                data={
                    "prompt": "mixed",
                    "canonical_model_id": "gpt-image-2",
                    "provider_id": "codex",
                    "parameters_json": json.dumps({"canvas.size": "1024x1024", "output.count": 1}),
                    "quality": "high",
                },
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["code"], "generation_request_invalid")

    def test_canonical_generate_runtime_keeps_snapshot_parameters(self) -> None:
        import asyncio
        from tests.webui_helpers import FakeImageClient

        parameters = {
            "canvas.size": "1024x1024",
            "gpt.quality": "high",
            "gpt.background": "opaque",
            "output.format": "jpeg",
            "gpt.moderation": "auto",
            "output.count": 1,
        }
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(Path(tmp))
            fake = FakeImageClient()
            app.state.ctx.client_factory = lambda: fake
            app.state.client_factory = app.state.ctx.client_factory
            response = TestClient(app).post(
                "/api/generate",
                data={
                    "prompt": "canonical",
                    "canonical_model_id": "gpt-image-2",
                    "provider_id": "codex",
                    "parameters_json": json.dumps(parameters),
                },
            )
            asyncio.run(app.state.queue_manager.run_available_once())
            metadata = app.state.storage.read_metadata(response.json()["task"]["task_id"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(metadata["generation_snapshot"]["requested_parameters"], parameters)
        self.assertEqual(fake.generate_calls[0]["quality"], "high")
        self.assertEqual(fake.generate_calls[0]["output_format"], "jpeg")
        self.assertEqual(fake.generate_calls[0]["background"], "opaque")

    def test_canonical_output_uses_provider_asset_format_and_metadata(self) -> None:
        import asyncio
        from codex_image.client import ImageResult

        class AssetFormatClient:
            def __init__(self, output_format: str) -> None:
                self.output_format = output_format

            def generate_image(self, **kwargs):
                return ImageResult(
                    b"provider-asset", "provider revised", self.output_format,
                    "2048x1024", "transparent", "high", {"provider": "usage"},
                )

        for output_format in ("jpeg", "webp"):
            with self.subTest(output_format=output_format), tempfile.TemporaryDirectory() as tmp:
                app = self._app(Path(tmp))
                fake = AssetFormatClient(output_format)
                app.state.ctx.client_factory = lambda: fake
                app.state.client_factory = app.state.ctx.client_factory
                response = TestClient(app).post("/api/generate", data={
                    "prompt": "asset format",
                    "canonical_model_id": "gpt-image-2",
                    "provider_id": "codex",
                    "parameters_json": json.dumps({
                        "canvas.size": "1024x1024", "gpt.quality": "low",
                        "gpt.background": "auto", "output.format": output_format,
                        "gpt.moderation": "auto", "output.count": 1,
                    }),
                })
                asyncio.run(app.state.queue_manager.run_available_once())
                metadata = app.state.storage.read_metadata(response.json()["task"]["task_id"])

            output = metadata["outputs"][0]
            expected_extension = "jpg" if output_format == "jpeg" else output_format
            self.assertTrue(output["file"].endswith(f".{expected_extension}"))
            self.assertEqual(output["format"], output_format)
            self.assertEqual(output["size"], "2048x1024")
            self.assertEqual(output["background"], "transparent")
            self.assertEqual(output["quality"], "high")

    def test_canonical_responses_allows_main_model_separate_from_image_model(self) -> None:
        settings = {
            "schema_version": 2,
            "codex_mode": "responses",
            "active_provider_id": "relay",
            "default_provider_by_model": {"gpt-image-2": "relay"},
            "providers": [{
                "id": "relay", "name": "Relay", "base_url": "https://relay.example/v1",
                "api_key": "key", "auth_scheme": "bearer", "concurrency": 1,
                "bindings": [{
                    "id": "relay-gpt", "canonical_model_id": "gpt-image-2",
                    "remote_model_id": "remote-gpt", "protocol_profile": "openai_images",
                    "parameter_codec": "gpt_openai_images", "operations": ["generate", "edit"],
                }],
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            response = TestClient(self._app(Path(tmp), api_settings=settings)).post(
                "/api/generate",
                data={
                    "prompt": "main model",
                    "main_model": "gpt-main-custom",
                    "canonical_model_id": "gpt-image-2",
                    "provider_id": "codex",
                    "parameters_json": json.dumps({"canvas.size": "1024x1024", "output.count": 1}),
                },
            )

        self.assertEqual(response.status_code, 200)
        mapped = response.json()["task"]["generation_snapshot"]["mapped_request"]["json_body"]
        self.assertEqual(mapped["model"], "gpt-main-custom")
        image_tool = next(tool for tool in mapped["tools"] if tool["type"] == "image_generation")
        self.assertEqual(image_tool["model"], "gpt-image-2")

    def test_canonical_non_gpt_ignores_gpt_main_model_and_prompt_processing(self) -> None:
        settings = {
            "schema_version": 2,
            "codex_mode": "images",
            "active_provider_id": "gemini-relay",
            "default_provider_by_model": {"nano-banana-pro": "gemini-relay"},
            "providers": [{
                "id": "gemini-relay",
                "name": "Gemini Relay",
                "base_url": "https://generativelanguage.googleapis.com/v1beta",
                "api_key": "key",
                "concurrency": 1,
                "bindings": [{
                    "id": "gemini-pro",
                    "canonical_model_id": "nano-banana-pro",
                    "remote_model_id": "gemini-3-pro-image",
                    "protocol_profile": "gemini_generate_content",
                    "parameter_codec": "gemini_generate_content_image",
                    "operations": ["generate"],
                }],
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            response = TestClient(self._app(Path(tmp), api_settings=settings)).post(
                "/api/generate",
                data={
                    "prompt": "必须保留蓝色文字",
                    "prompt_for_model": "expanded gallery prompt",
                    "main_model": "gpt-must-not-participate",
                    "prompt_fidelity": "strict",
                    "canonical_model_id": "nano-banana-pro",
                    "provider_id": "gemini-relay",
                    "parameters_json": json.dumps({
                        "canvas.aspect_ratio": "1:1",
                        "canvas.resolution": "1K",
                        "gemini.safety_settings": {},
                        "output.count": 1,
                    }),
                },
            )

        self.assertEqual(response.status_code, 200)
        task = response.json()["task"]
        self.assertEqual(task["prompt_for_model"], "expanded gallery prompt")
        self.assertNotIn("prompt_constraints", task)
        self.assertNotIn("main_model", task["params"])
        self.assertNotIn("prompt_fidelity", task["params"])

    def test_canonical_form_rejects_legacy_canvas_and_prompt_fields(self) -> None:
        for field, value in (("resolution", "2K"), ("ratio", "16:9"), ("orientation", "landscape")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                response = TestClient(self._app(Path(tmp))).post(
                    "/api/generate",
                    data={
                        "prompt": "mixed canvas",
                        "canonical_model_id": "gpt-image-2",
                        "provider_id": "codex",
                        "parameters_json": json.dumps({"canvas.size": "1024x1024", "output.count": 1}),
                        field: value,
                    },
                )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["detail"]["code"], "generation_request_invalid")

    def test_canonical_edit_runtime_keeps_inputs_mask_and_fidelity(self) -> None:
        import asyncio
        from tests.webui_helpers import FakeImageClient

        parameters = {
            "canvas.size": "1024x1024",
            "gpt.quality": "high",
            "gpt.background": "auto",
            "output.format": "png",
            "gpt.moderation": "auto",
            "output.count": 1,
        }
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(Path(tmp))
            fake = FakeImageClient()
            app.state.ctx.client_factory = lambda: fake
            app.state.client_factory = app.state.ctx.client_factory
            response = TestClient(app).post(
                "/api/edit",
                data={
                    "prompt": "canonical edit",
                    "canonical_model_id": "gpt-image-2",
                    "provider_id": "codex",
                    "parameters_json": json.dumps(parameters),
                },
                files={
                    "images": ("input.png", self._png_bytes(), "image/png"),
                    "mask": ("mask.png", self._png_bytes(), "image/png"),
                },
            )
            asyncio.run(app.state.queue_manager.run_available_once())
            metadata = app.state.storage.read_metadata(response.json()["task"]["task_id"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(metadata["generation_snapshot"]["requested_parameters"], parameters)
        self.assertIsNone(fake.edit_calls[0]["input_fidelity"])
        self.assertTrue(fake.edit_calls[0]["images"])
        self.assertTrue(fake.edit_calls[0]["mask_image"].startswith("data:image/png;base64,"))

    def test_legacy_compat_options_are_frozen_in_snapshot_for_worker(self) -> None:
        import asyncio
        from tests.webui_helpers import FakeImageClient

        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(Path(tmp))
            fake = FakeImageClient()
            app.state.ctx.client_factory = lambda: fake
            app.state.client_factory = app.state.ctx.client_factory
            response = TestClient(app).post(
                "/api/generate",
                data={
                    "prompt": "legacy compat",
                    "codex_mode": "responses",
                    "output_format": "jpeg",
                    "output_compression": "61",
                    "web_search": "true",
                },
            )
            task_id = response.json()["task"]["task_id"]
            metadata = app.state.storage.read_metadata(task_id)
            self.assertEqual(metadata["generation_snapshot"]["legacy_compat_parameters"], {
                "gpt.output_compression": 61,
                "gpt.web_search": True,
            })
            metadata["params"]["output_compression"] = 5
            metadata["params"]["web_search"] = False
            app.state.storage.write_metadata(task_id, metadata)
            asyncio.run(app.state.queue_manager.run_available_once())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake.generate_calls[0]["output_compression"], 61)
        self.assertIs(fake.generate_calls[0]["web_search"], True)

    def test_queued_snapshot_keeps_remote_model_after_settings_change(self) -> None:
        settings = {
            "schema_version": 2, "codex_mode": "images", "active_provider_id": "relay",
            "default_provider_by_model": {"gpt-image-2": "relay"},
            "providers": [{
                "id": "relay", "name": "Relay", "base_url": "https://relay.example/v1",
                "api_key": "unit-test-secret", "auth_scheme": "bearer", "concurrency": 2,
                "bindings": [{
                    "id": "relay-gpt", "canonical_model_id": "gpt-image-2",
                    "remote_model_id": "relay/model-before", "protocol_profile": "openai_images",
                    "parameter_codec": "gpt_openai_images", "operations": ["generate", "edit"],
                }],
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = self._app(root, api_settings=settings)
            client = TestClient(app)
            response = client.post(
                "/api/generate",
                data={
                    "prompt": "snapshot", "canonical_model_id": "gpt-image-2", "provider_id": "relay",
                    "parameters_json": json.dumps({"canvas.size": "1024x1024", "gpt.quality": "low", "gpt.background": "auto", "output.format": "png", "gpt.moderation": "auto", "output.count": 1}),
                },
            )
            task_id = response.json()["task"]["task_id"]
            changed = json.loads(json.dumps(settings))
            changed["providers"][0]["bindings"][0]["remote_model_id"] = "relay/model-after"
            app.state.api_settings.write(changed)
            metadata = app.state.storage.read_metadata(task_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(metadata["generation_snapshot"]["remote_model_id"], "relay/model-before")
        self.assertNotIn("unit-test-secret", json.dumps(metadata))

    def test_structured_error_sanitizes_prompt_and_credentials(self) -> None:
        from codex_image.generation.errors import provider_error, provider_error_from_exception

        error = provider_error_from_exception(
            RuntimeError("Authorization: Bearer unit-test-secret\nraw prompt: private-rabbit"),
            provider_id="relay", canonical_model_id="gpt-image-2", protocol_profile="openai_images",
        )
        encoded = json.dumps(error.detail.to_dict())
        self.assertNotIn("unit-test-secret", encoded)
        self.assertNotIn("private-rabbit", encoded)
        self.assertNotIn("\n", error.detail.message)
        self.assertEqual(error.detail.code, "upstream_error")
        stable_codes = {
            "authentication_failed", "rate_limited", "invalid_parameters",
            "operation_unsupported", "upstream_error", "asset_download_failed",
            "request_timeout",
        }
        for code in stable_codes:
            with self.subTest(code=code):
                mapped = provider_error(
                    code,
                    provider_id="relay",
                    canonical_model_id="gpt-image-2",
                    protocol_profile="openai_images",
                )
                self.assertEqual(mapped.detail.code, code)
                self.assertNotIn("unit-test-secret", mapped.detail.message)
        self.assertEqual(
            provider_error_from_exception(
                RuntimeError("HTTP 401"), provider_id="p", canonical_model_id="m", protocol_profile="x"
            ).detail.code,
            "authentication_failed",
        )
        self.assertEqual(
            provider_error_from_exception(
                RuntimeError("HTTP 429"), provider_id="p", canonical_model_id="m", protocol_profile="x"
            ).detail.code,
            "rate_limited",
        )
        self.assertEqual(
            provider_error_from_exception(
                TimeoutError(), provider_id="p", canonical_model_id="m", protocol_profile="x"
            ).detail.code,
            "request_timeout",
        )

    def test_persisted_worker_error_removes_controls_auth_tokens_and_prompt(self) -> None:
        import asyncio

        prompt = "PRIVATE-PROMPT-ORIGINAL"
        secret = "url-token-secret"

        class FailingClient:
            def generate_image(self, **kwargs):
                raise RuntimeError(
                    f"\x1b[31mAuthorization: Bearer bearer-secret\x1b[0m\x00 "
                    f"api_key=api-key-secret https://relay.example/v1?token={secret} {prompt}"
                )

        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(Path(tmp))
            app.state.ctx.client_factory = FailingClient
            app.state.client_factory = FailingClient
            response = TestClient(app).post("/api/generate", data={"prompt": prompt})
            task_id = response.json()["task"]["task_id"]
            with self.assertRaises(Exception):
                asyncio.run(app.state.queue_manager.run_available_once())
            metadata = app.state.storage.read_metadata(task_id)

        persisted = f"{metadata.get('error', '')} {metadata.get('last_error', '')}"
        for marker in (prompt, "bearer-secret", "api-key-secret", secret, "\x1b", "\x00"):
            self.assertNotIn(marker, persisted)

    def test_snapshot_redacts_gemini_contents_part_text(self) -> None:
        from codex_image.generation.catalog import get_model_manifest
        from codex_image.generation.snapshot import generation_snapshot
        from codex_image.generation.types import GenerationCommand
        from codex_image.providers.contracts import ExecutionPlan, ProtocolRequest, ProviderConnection, ProviderModelBinding

        marker = "PRIVATE-GEMINI-TEXT-MARKER"
        binding = ProviderModelBinding(
            "b", "relay", "gpt-image-2", "remote", "openai_images",
            "gpt_openai_images", frozenset({"generate"}),
        )
        command = GenerationCommand(
            "generate", "gpt-image-2", "relay", marker,
            {"canvas.size": "1024x1024", "output.count": 1},
        )
        plan = ExecutionPlan(
            command, get_model_manifest("gpt-image-2"),
            ProviderConnection("relay", "Relay", "https://relay.example", "", 1, (binding,)),
            binding,
            ProtocolRequest("POST", "/models/x:generate", "application/json", json_body={
                "contents": [{"parts": [{"text": marker}]}],
            }),
        )
        self.assertNotIn(marker, json.dumps(generation_snapshot(plan)))

    def test_snapshot_worker_executes_through_generation_service_once(self) -> None:
        import asyncio
        from unittest.mock import patch
        from codex_image.generation.service import GenerationService
        from tests.webui_helpers import FakeImageClient

        observed = []
        original = GenerationService.execute_plan_once

        def recording_execute(service, plan):
            observed.append(plan)
            return original(service, plan)

        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(Path(tmp))
            fake = FakeImageClient()
            app.state.ctx.client_factory = lambda: fake
            app.state.client_factory = app.state.ctx.client_factory
            client = TestClient(app)
            created = client.post("/api/generate", data={"prompt": "service path", "size": "1024x1024", "quality": "low"})
            with patch.object(GenerationService, "execute_plan_once", recording_execute):
                asyncio.run(app.state.queue_manager.run_available_once())

        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0].command.canonical_model_id, "gpt-image-2")
        self.assertEqual(len(fake.generate_calls), 1)


class GenerationRequestTests(unittest.TestCase):
    def test_provider_scoped_retry_does_not_deadlock_behind_other_provider(self) -> None:
        import asyncio
        from codex_image.webui.queue import QueueChannel, QueueManager
        from codex_image.webui.storage import QueueStorage

        with tempfile.TemporaryDirectory() as tmp:
            storage = QueueStorage(Path(tmp) / "queue.json")
            storage.enqueue("task-a")
            calls: list[str] = []

            async def execute(task_id, channel, is_final):
                calls.append(channel.channel_id)
                if len(calls) == 1:
                    raise RuntimeError("retry")

            matches = lambda task_id, channel: channel.provider_id == "provider-a"
            manager = QueueManager(
                storage,
                [
                    QueueChannel("provider:provider-a:0", "api", provider_id="provider-a"),
                    QueueChannel("provider:provider-b:0", "api", provider_id="provider-b"),
                ],
                execute,
                max_attempts=2,
                claim_task=matches,
                task_channel_matches=matches,
            )
            with self.assertRaises(RuntimeError):
                asyncio.run(manager.run_channel_once(manager.channels[0]))
            asyncio.run(manager.run_available_once())
            state = storage.read_state()

        self.assertEqual(calls, ["provider:provider-a:0", "provider:provider-a:0"])
        self.assertNotIn("task-a", state["waiting"])
    def test_binding_resolver_enforces_manifest_input_constraints_before_protocol(self) -> None:
        from codex_image.client_types import ResponsesInputFile
        from codex_image.generation.catalog import list_model_manifests
        from codex_image.generation.resolver import BindingResolver
        from codex_image.generation.types import GenerationCommand, ImageInput
        from codex_image.providers.contracts import ProviderConnection, ProviderModelBinding
        from codex_image.providers.registry import default_registry
        from codex_image.webui.generation_request import codex_provider_connection

        registry = default_registry()
        nano_binding = ProviderModelBinding(
            "nano", "relay", "nano-banana-pro", "nano", "future_profile",
            "future_codec", frozenset({"generate", "edit"}),
        )
        nano_provider = ProviderConnection(
            "relay", "Relay", "https://relay.example", "key", 1,
            (nano_binding,),
        )
        resolver = BindingResolver(
            models={model.id: model for model in list_model_manifests()},
            providers={"codex": codex_provider_connection("images"), "relay": nano_provider},
            registry=registry,
        )
        too_many = GenerationCommand(
            "generate", "gpt-image-2", "codex", "p",
            {"canvas.size": "1024x1024", "output.count": 1},
            image_inputs=tuple(ImageInput("data:image/png;base64,eA==") for _ in range(17)),
        )
        with self.assertRaisesRegex(ValueError, "image_input_limit_exceeded"):
            resolver.resolve(too_many)
        with self.assertRaisesRegex(ValueError, "mask_input_unsupported"):
            resolver.resolve(GenerationCommand(
                "edit", "nano-banana-pro", "relay", "p",
                {"canvas.aspect_ratio": "1:1", "canvas.resolution": "1K", "output.count": 1},
                image_inputs=(ImageInput("data:image/png;base64,eA=="),),
                mask_image="data:image/png;base64,eA==",
            ))
        with self.assertRaisesRegex(ValueError, "reference_files_unsupported"):
            resolver.resolve(GenerationCommand(
                "generate", "nano-banana-pro", "relay", "p",
                {"canvas.aspect_ratio": "1:1", "canvas.resolution": "1K", "output.count": 1},
                reference_files=(ResponsesInputFile("a.txt", "text/plain", "data:text/plain;base64,eA=="),),
            ))

    def test_snapshot_restore_revalidates_manifest_input_constraints(self) -> None:
        from dataclasses import replace
        from codex_image.generation.catalog import get_model_manifest
        from codex_image.generation.resolver import BindingResolver
        from codex_image.generation.service import GenerationService
        from codex_image.generation.snapshot import execution_plan_from_snapshot, generation_snapshot
        from codex_image.generation.types import GenerationCommand, ImageInput
        from codex_image.providers.registry import default_registry
        from codex_image.webui.generation_request import codex_provider_connection

        registry = default_registry()
        provider = codex_provider_connection("images")
        command = GenerationCommand(
            "generate", "gpt-image-2", "codex", "p",
            {"canvas.size": "1024x1024", "output.count": 1},
        )
        plan = GenerationService(BindingResolver(
            models={"gpt-image-2": get_model_manifest("gpt-image-2")},
            providers={"codex": provider}, registry=registry,
        ), registry).preview(command)
        snapshot = generation_snapshot(plan)
        invalid = replace(command, image_inputs=tuple(
            ImageInput("data:image/png;base64,eA==") for _ in range(17)
        ))
        with self.assertRaises(Exception) as raised:
            execution_plan_from_snapshot(
                snapshot=snapshot, command=invalid, api_key="", registry=registry
            )
        self.assertEqual(raised.exception.detail.code, "snapshot_manifest_incompatible")

    def test_gpt_codecs_do_not_construct_uninitialized_clients(self) -> None:
        import inspect
        import codex_image.providers.codecs.gpt_image as codec_module

        self.assertNotIn("object.__new__", inspect.getsource(codec_module))

    def test_legacy_mapping_preserves_compression_fidelity_and_web_search(self) -> None:
        from codex_image.webui.generation_request import legacy_gpt_compat_parameters

        parameters = legacy_gpt_compat_parameters({
            "output_compression": 61,
            "input_fidelity": "high",
            "web_search": True,
        })
        self.assertEqual(parameters["gpt.output_compression"], 61)
        self.assertEqual(parameters["gpt.input_fidelity"], "high")
        self.assertIs(parameters["gpt.web_search"], True)

    def test_provider_models_share_provider_concurrency_slots(self) -> None:
        import tempfile
        from codex_image.webui.auth_routing import _queue_channels_for_source
        from codex_image.webui.provider_settings import ProviderSettings

        payload = {
            "schema_version": 2, "codex_mode": "images", "active_provider_id": "relay-a",
            "default_provider_by_model": {"gpt-image-2": "relay-a", "nano-banana-pro": "relay-a"},
            "providers": [{
                "id": "relay-a", "name": "Relay A", "base_url": "https://relay.example/v1", "api_key": "key",
                "auth_scheme": "bearer", "concurrency": 2,
                "bindings": [
                    {"id": "gpt", "canonical_model_id": "gpt-image-2", "remote_model_id": "gpt", "protocol_profile": "openai_images", "parameter_codec": "gpt_openai_images", "operations": ["generate"]},
                    {"id": "gemini", "canonical_model_id": "nano-banana-pro", "remote_model_id": "gemini", "protocol_profile": "openai_images", "parameter_codec": "gemini_openai_images", "operations": ["generate"]},
                ],
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            settings = ProviderSettings(Path(tmp) / "providers.json")
            settings.write(payload)
            channels = _queue_channels_for_source("api", api_settings=settings)
        self.assertEqual([channel.channel_id for channel in channels], ["provider:relay-a:0", "provider:relay-a:1"])
        self.assertEqual({channel.provider_id for channel in channels}, {"relay-a"})

    def test_parameter_json_must_be_object(self) -> None:
        from codex_image.webui.generation_request import parse_parameters_json

        with self.assertRaisesRegex(ValueError, "JSON object"):
            parse_parameters_json("[]")

    def test_snapshot_restore_uses_current_key_but_frozen_route(self) -> None:
        from codex_image.generation.catalog import get_model_manifest
        from codex_image.generation.snapshot import execution_plan_from_snapshot, generation_snapshot
        from codex_image.generation.types import GenerationCommand
        from codex_image.providers.contracts import ProviderConnection, ProviderModelBinding
        from codex_image.providers.registry import default_registry
        from codex_image.generation.resolver import BindingResolver
        from codex_image.generation.service import GenerationService

        binding = ProviderModelBinding("b", "relay", "gpt-image-2", "before", "openai_images", "gpt_openai_images", frozenset({"generate"}))
        provider = ProviderConnection("relay", "Relay", "https://before.example/v1", "old-key", 2, (binding,))
        command = GenerationCommand("generate", "gpt-image-2", "relay", "private", {"canvas.size": "1024x1024", "output.count": 1})
        registry = default_registry()
        plan = GenerationService(BindingResolver(models={"gpt-image-2": get_model_manifest("gpt-image-2")}, providers={"relay": provider}, registry=registry), registry).preview(command)
        snapshot = generation_snapshot(plan)
        restored = execution_plan_from_snapshot(snapshot=snapshot, command=command, api_key="new-key", registry=registry)

        self.assertNotIn("provider_auth_scheme", snapshot)
        self.assertEqual(restored.provider.base_url, "https://before.example/v1")
        self.assertEqual(restored.provider.api_key, "new-key")
        self.assertEqual(restored.binding.remote_model_id, "before")
        self.assertEqual(restored.binding.protocol_profile, "openai_images")
        self.assertNotIn("private", json.dumps(snapshot))
