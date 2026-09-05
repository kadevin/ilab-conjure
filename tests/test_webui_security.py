from __future__ import annotations

from io import BytesIO
from pathlib import Path
import asyncio
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from PIL import Image


class WebUISecurityTests(unittest.TestCase):
    def _png_bytes(self) -> bytes:
        image = Image.new("RGB", (12, 8), (48, 96, 144))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def _gif_bytes(self, *, frames: int = 2) -> bytes:
        images = [
            Image.new("RGB", (3, 2), (index * 40, 80, 120))
            for index in range(frames)
        ]
        buffer = BytesIO()
        images[0].save(
            buffer,
            format="GIF",
            save_all=True,
            append_images=images[1:],
            duration=10,
            loop=0,
        )
        return buffer.getvalue()

    def _create_app(self, root: Path):
        from codex_image.webui.app import create_app

        settings_root = root / "settings"
        return create_app(
            output_root=root / "outputs",
            input_root=root / "inputs",
            source_data_root=root / "outputs" / "source-data",
            gallery_root=root / "inputs" / "gallery",
            reference_asset_root=root / "inputs" / "reference-assets",
            reference_file_root=root / "inputs" / "reference-files",
            auth_checker=lambda: True,
            auth_settings_path=settings_root / "auth.json",
            api_settings_path=settings_root / "api.json",
            network_egress_settings_path=settings_root / "network-egress.json",
            color_settings_path=settings_root / "colors.json",
            prompt_snippets_path=settings_root / "prompt-snippets.json",
            prompt_templates_path=settings_root / "prompt-templates.json",
            webui_settings_path=settings_root / "webui.json",
            auto_start_queue=False,
        )

    def test_task_media_routes_preserve_known_files_and_hide_unowned_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = self._create_app(root)
            storage = app.state.storage
            task = storage.create_task("edit")
            image_bytes = self._png_bytes()
            template_asset = app.state.prompt_template_asset_storage.store(
                image_bytes,
                filename="template.png",
            )
            input_path = storage.write_input(task.task_id, "source.png", image_bytes)
            output_path = storage.write_output(task.task_id, image_bytes, "png", index=1)
            output_file = storage.output_file(output_path)
            storage.write_metadata(
                task.task_id,
                {
                    "task_id": task.task_id,
                    "status": "completed",
                    "input_files": [input_path.name],
                    "generated_count": 1,
                    "total_count": 1,
                    "output_file": output_file,
                    "output_files": [output_file],
                    "output_url": f"/outputs/{output_file}",
                    "output_urls": [f"/outputs/{output_file}"],
                    "outputs": [
                        {
                            "index": 1,
                            "status": "completed",
                            "file": output_file,
                            "url": f"/outputs/{output_file}",
                        }
                    ],
                },
            )

            unowned_input = storage.input_root / "unowned.png"
            unowned_input.write_bytes(image_bytes)
            unowned_output = storage.output_root / "unowned.png"
            unowned_output.write_bytes(image_bytes)
            private_source = storage.source_data_root / "private.json"
            private_source.parent.mkdir(parents=True, exist_ok=True)
            private_source.write_text('{"secret": true}', encoding="utf-8")
            unowned_template_asset = (
                app.state.prompt_template_asset_root / ("f" * 64 + ".png")
            )
            unowned_template_asset.write_bytes(image_bytes)

            client = TestClient(app)
            task_response = client.get(f"/api/tasks/{task.task_id}")
            input_image = client.get(f"/api/tasks/{task.task_id}/inputs/1/image")
            output_image = client.get(f"/api/tasks/{task.task_id}/outputs/1/image")
            task_payload = task_response.json()["task"]
            legacy_input = client.get(task_payload["input_urls"][0])
            legacy_output = client.get(task_payload["output_urls"][0])
            hidden_input = client.get("/inputs/unowned.png")
            hidden_output = client.get("/outputs/unowned.png")
            hidden_source = client.get("/outputs/source-data/private.json")
            template_image = client.get(
                f"/api/prompt-template-assets/{template_asset.asset_id}/image"
            )
            hidden_template = client.get(
                "/api/prompt-template-assets/" + "f" * 64 + "/image"
            )
            escaped_template = client.get(
                "/api/prompt-template-assets/%2e%2e/image"
            )

        self.assertEqual(task_response.status_code, 200)
        self.assertEqual(input_image.status_code, 200)
        self.assertEqual(input_image.content, image_bytes)
        self.assertEqual(output_image.status_code, 200)
        self.assertEqual(output_image.content, image_bytes)
        self.assertEqual(legacy_input.status_code, 200)
        self.assertEqual(legacy_input.content, image_bytes)
        self.assertEqual(legacy_output.status_code, 200)
        self.assertEqual(legacy_output.content, image_bytes)
        self.assertEqual(hidden_input.status_code, 404)
        self.assertEqual(hidden_output.status_code, 404)
        self.assertEqual(hidden_source.status_code, 404)
        self.assertEqual(template_image.status_code, 200)
        self.assertEqual(template_image.content, image_bytes)
        self.assertEqual(hidden_template.status_code, 404)
        self.assertEqual(escaped_template.status_code, 404)

    def test_legacy_output_route_accepts_owned_file_after_output_reindex(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = self._create_app(root)
            storage = app.state.storage
            task = storage.create_task("generate")
            image_bytes = self._png_bytes()
            retained_path = storage.write_output(
                task.task_id,
                image_bytes,
                "png",
                index=2,
            )
            unowned_path = storage.write_output(
                task.task_id,
                image_bytes,
                "png",
                index=3,
            )
            retained_file = storage.output_file(retained_path)
            unowned_file = storage.output_file(unowned_path)
            storage.write_metadata(
                task.task_id,
                {
                    "task_id": task.task_id,
                    "status": "completed",
                    "generated_count": 1,
                    "total_count": 1,
                    "output_file": retained_file,
                    "output_files": [retained_file],
                    "output_url": f"/outputs/{retained_file}",
                    "output_urls": [f"/outputs/{retained_file}"],
                    "outputs": [
                        {
                            "index": 1,
                            "status": "completed",
                            "file": retained_file,
                            "url": f"/outputs/{retained_file}",
                        }
                    ],
                },
            )

            client = TestClient(app)
            legacy_retained = client.get(f"/outputs/{retained_file}")
            canonical_retained = client.get(
                f"/api/tasks/{task.task_id}/outputs/1/image"
            )
            stale_physical_slot = client.get(
                f"/api/tasks/{task.task_id}/outputs/2/image"
            )
            legacy_unowned = client.get(f"/outputs/{unowned_file}")

        self.assertEqual(legacy_retained.status_code, 200)
        self.assertEqual(legacy_retained.content, image_bytes)
        self.assertEqual(canonical_retained.status_code, 200)
        self.assertEqual(canonical_retained.content, image_bytes)
        self.assertEqual(stale_physical_slot.status_code, 404)
        self.assertEqual(legacy_unowned.status_code, 404)

    def test_webui_rejects_non_loopback_hosts_clients_and_cross_origin_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = self._create_app(root)
            client = TestClient(app)

            invalid_host = client.get(
                "/api/health",
                headers={"Host": "127.0.0.1.attacker.example"},
            )
            remote_client = TestClient(
                app,
                base_url="http://127.0.0.1",
                client=("192.0.2.10", 4242),
            ).get("/api/health")
            cross_origin = client.patch(
                "/api/settings",
                headers={"Origin": "https://attacker.example"},
                json={},
            )
            cross_site = client.patch(
                "/api/settings",
                headers={"Sec-Fetch-Site": "cross-site"},
                json={},
            )
            same_origin = client.patch(
                "/api/settings",
                headers={"Origin": "http://testserver"},
                json={},
            )
            local_script = client.patch("/api/settings", json={})
            localhost = client.get(
                "/api/health",
                headers={"Host": "localhost:8787"},
            )

        self.assertEqual(invalid_host.status_code, 400)
        self.assertEqual(remote_client.status_code, 403)
        self.assertEqual(cross_origin.status_code, 403)
        self.assertEqual(cross_site.status_code, 403)
        self.assertEqual(same_origin.status_code, 200)
        self.assertEqual(local_script.status_code, 200)
        self.assertEqual(localhost.status_code, 200)

    def test_webui_adds_browser_security_headers_and_disables_api_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._create_app(Path(tmp))
            client = TestClient(app)

            response = client.get("/api/health")
            openapi = client.get("/openapi.json")
            docs = client.get("/docs")
            redoc = client.get("/redoc")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(response.headers["referrer-policy"], "no-referrer")
        self.assertEqual(response.headers["cross-origin-resource-policy"], "same-origin")
        self.assertEqual(response.headers["cross-origin-opener-policy"], "same-origin")
        self.assertIn("default-src 'self'", response.headers["content-security-policy"])
        self.assertEqual(openapi.status_code, 404)
        self.assertEqual(docs.status_code, 404)
        self.assertEqual(redoc.status_code, 404)

    def test_webui_rejects_declared_and_streamed_request_bodies_over_the_limit(self) -> None:
        from codex_image.webui.security import LocalWebUISecurityMiddleware

        def limited_app() -> FastAPI:
            app = FastAPI()
            app.add_middleware(
                LocalWebUISecurityMiddleware,
                max_request_bytes=10,
            )

            @app.post("/body")
            async def read_body(request: Request) -> dict[str, int]:
                return {"size": len(await request.body())}

            return app

        client = TestClient(limited_app())
        declared = client.post(
            "/body",
            content=b"x",
            headers={"Content-Length": "11"},
        )
        streamed = client.post(
            "/body",
            content=(part for part in (b"123456", b"78901")),
            headers={"Transfer-Encoding": "chunked"},
        )
        accepted = client.post("/body", content=b"1234567890")

        self.assertEqual(declared.status_code, 413)
        self.assertEqual(declared.json()["detail"]["code"], "request_body_too_large")
        self.assertEqual(streamed.status_code, 413)
        self.assertEqual(streamed.json()["detail"]["code"], "request_body_too_large")
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json(), {"size": 10})

    def test_task_image_budget_deduplicates_content_addressed_assets(self) -> None:
        from codex_image.webui.resource_limits import (
            TaskImageResource,
            validate_task_image_total,
        )

        resources = [
            TaskImageResource(key="reference:abc", size_bytes=7),
            TaskImageResource(key="reference:abc", size_bytes=7),
            TaskImageResource(key="gallery:item-1", size_bytes=4),
            TaskImageResource(key="mask:def", size_bytes=3),
        ]

        self.assertEqual(
            validate_task_image_total(resources, max_total_bytes=14),
            14,
        )
        with self.assertRaisesRegex(ValueError, "task_images_total_too_large"):
            validate_task_image_total(resources, max_total_bytes=13)

    def test_edit_rejects_combined_image_budget_before_writing_new_assets_or_tasks(self) -> None:
        def png_bytes(color: tuple[int, int, int]) -> bytes:
            buffer = BytesIO()
            Image.new("RGB", (4, 3), color).save(buffer, format="PNG")
            return buffer.getvalue()

        existing_bytes = png_bytes((10, 20, 30))
        gallery_bytes = png_bytes((40, 50, 60))
        uploaded_bytes = png_bytes((70, 80, 90))
        mask_bytes = png_bytes((100, 110, 120))
        total_bytes = sum(
            map(len, (existing_bytes, gallery_bytes, uploaded_bytes, mask_bytes))
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = self._create_app(root)
            existing = app.state.reference_asset_storage.create_or_touch(
                "existing.png",
                existing_bytes,
                "image/png",
            )
            gallery = app.state.gallery_storage.create_item(
                "gallery",
                "portrait",
                "gallery.png",
                gallery_bytes,
                "image/png",
            )
            before_existing = app.state.reference_asset_storage.read_item(existing["id"])
            client = TestClient(app)

            with patch(
                "codex_image.webui.routes.generation.MAX_TASK_IMAGE_BYTES",
                total_bytes - 1,
            ):
                response = client.post(
                    "/api/edit",
                    data={
                        "prompt": "budget",
                        "reference_asset_ids": existing["id"],
                        "gallery_image_ids": gallery["id"],
                    },
                    files=[
                        ("images", ("uploaded.png", uploaded_bytes, "image/png")),
                        ("mask", ("mask.png", mask_bytes, "image/png")),
                    ],
                )

            after_existing = app.state.reference_asset_storage.read_item(existing["id"])
            recent_asset_ids = {
                item["id"]
                for item in app.state.reference_asset_storage.list_recent(limit=100)
            }
            task_files = list(
                (root / "outputs" / "source-data" / "tasks").rglob("*")
            ) if (root / "outputs" / "source-data" / "tasks").exists() else []

        self.assertEqual(response.status_code, 413)
        self.assertEqual(
            response.json()["detail"]["code"],
            "task_images_total_too_large",
        )
        self.assertEqual(after_existing, before_existing)
        self.assertEqual(recent_asset_ids, {existing["id"]})
        self.assertEqual(task_files, [])

    def test_gallery_accepts_decoded_raster_content_and_rejects_svg_or_fake_images(self) -> None:
        svg_bytes = (
            b'<svg xmlns="http://www.w3.org/2000/svg">'
            b'<script>alert(1)</script><rect width="10" height="10"/></svg>'
        )
        with tempfile.TemporaryDirectory() as tmp:
            app = self._create_app(Path(tmp))
            client = TestClient(app)

            valid = client.post(
                "/api/gallery",
                data={"name": "valid", "category": "portrait"},
                files={
                    "image": (
                        "misleading.svg",
                        self._png_bytes(),
                        "application/octet-stream",
                    )
                },
            )
            valid_item = valid.json()["item"]
            valid_image = client.get(valid_item["image_url"])
            svg = client.post(
                "/api/gallery",
                data={"name": "svg", "category": "portrait"},
                files={"image": ("active.svg", svg_bytes, "image/svg+xml")},
            )
            fake = client.post(
                "/api/gallery",
                data={"name": "fake", "category": "portrait"},
                files={"image": ("fake.png", b"not-a-real-image", "image/png")},
            )
            listed = client.get("/api/gallery").json()["items"]

        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid_item["filename"], "misleading.png")
        self.assertEqual(valid_item["mime_type"], "image/png")
        self.assertEqual(valid_image.headers["content-type"], "image/png")
        self.assertEqual(svg.status_code, 400)
        self.assertEqual(fake.status_code, 400)
        self.assertEqual([item["name"] for item in listed], ["valid"])

    def test_generation_and_mask_uploads_reject_non_raster_content(self) -> None:
        svg_bytes = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>'
        with tempfile.TemporaryDirectory() as tmp:
            app = self._create_app(Path(tmp))
            client = TestClient(app)

            svg_reference = client.post(
                "/api/generate",
                data={"prompt": "svg reference"},
                files={
                    "reference_images": (
                        "active.svg",
                        svg_bytes,
                        "image/svg+xml",
                    )
                },
            )
            fake_reference = client.post(
                "/api/generate",
                data={"prompt": "fake reference"},
                files={
                    "reference_images": (
                        "fake.png",
                        b"not-a-real-image",
                        "image/png",
                    )
                },
            )
            svg_mask = client.post(
                "/api/edit",
                data={"prompt": "svg mask"},
                files={
                    "images": ("source.png", self._png_bytes(), "image/png"),
                    "mask": ("mask.svg", svg_bytes, "image/svg+xml"),
                },
            )

        self.assertEqual(svg_reference.status_code, 400)
        self.assertEqual(fake_reference.status_code, 400)
        self.assertEqual(svg_mask.status_code, 400)

    def test_raster_validation_enforces_byte_dimension_pixel_and_frame_budgets(self) -> None:
        from codex_image.webui.image_uploads import validate_raster_image

        png = self._png_bytes()
        gif = self._gif_bytes(frames=2)
        invalid_cases = (
            (png, {"max_bytes": len(png) - 1}, "byte limit"),
            (png, {"max_width": 11}, "dimensions"),
            (png, {"max_height": 7}, "dimensions"),
            (png, {"max_pixels": 95}, "pixel limit"),
            (gif, {"max_frames": 1}, "frame limit"),
            (gif, {"max_total_frame_pixels": 11}, "frame pixel limit"),
        )

        for data, limits, expected in invalid_cases:
            with self.subTest(expected=expected), self.assertRaisesRegex(
                ValueError,
                expected,
            ):
                validate_raster_image(data, filename="image.bin", **limits)

    def test_raster_upload_reader_uses_a_bounded_read_and_closes_the_upload(self) -> None:
        from codex_image.webui.image_uploads import read_validated_raster_upload

        class TrackingUpload:
            filename = "large.png"

            def __init__(self) -> None:
                self.read_sizes: list[int] = []
                self.closed = False

            async def read(self, size: int = -1) -> bytes:
                self.read_sizes.append(size)
                return b"x" * size

            async def close(self) -> None:
                self.closed = True

        upload = TrackingUpload()

        with self.assertRaisesRegex(ValueError, "byte limit"):
            asyncio.run(read_validated_raster_upload(upload, max_bytes=10))

        self.assertEqual(upload.read_sizes, [11])
        self.assertTrue(upload.closed)

    def test_raster_validation_keeps_supported_formats_within_budget(self) -> None:
        from codex_image.webui.image_uploads import validate_raster_image

        fixtures: list[tuple[str, str, bytes]] = []
        for image_format, expected_mime, suffix in (
            ("PNG", "image/png", ".png"),
            ("JPEG", "image/jpeg", ".jpg"),
            ("WEBP", "image/webp", ".webp"),
        ):
            buffer = BytesIO()
            Image.new("RGB", (4, 3), "white").save(buffer, format=image_format)
            fixtures.append((suffix, expected_mime, buffer.getvalue()))
        fixtures.append((".gif", "image/gif", self._gif_bytes(frames=2)))

        for suffix, expected_mime, data in fixtures:
            with self.subTest(expected_mime=expected_mime):
                validated = validate_raster_image(data, filename=f"image{suffix}")
                self.assertEqual(validated.mime_type, expected_mime)
                self.assertEqual(validated.width, 4 if suffix != ".gif" else 3)
                self.assertEqual(validated.height, 3 if suffix != ".gif" else 2)
                self.assertEqual(validated.frames, 2 if suffix == ".gif" else 1)

    def test_legacy_active_media_stays_on_disk_but_is_not_served_inline(self) -> None:
        svg_bytes = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        with tempfile.TemporaryDirectory() as tmp:
            app = self._create_app(Path(tmp))
            storage = app.state.storage
            task = storage.create_task("edit")
            input_path = storage.write_input(task.task_id, "legacy.svg", svg_bytes)
            output_path = storage.write_output(task.task_id, svg_bytes, "png", index=1)
            output_path.unlink()
            output_path = output_path.with_suffix(".svg")
            output_path.write_bytes(svg_bytes)
            output_file = storage.output_file(output_path)
            storage.write_metadata(
                task.task_id,
                {
                    "task_id": task.task_id,
                    "status": "completed",
                    "input_files": [input_path.name],
                    "output_files": [output_file],
                    "output_urls": [f"/outputs/{output_file}"],
                },
            )
            gallery_item = app.state.gallery_storage.create_item(
                name="legacy svg",
                category="portrait",
                filename="legacy.svg",
                data=svg_bytes,
                content_type="image/svg+xml",
            )
            reference_item = app.state.reference_asset_storage.create_or_touch(
                "legacy.svg",
                svg_bytes,
                "image/svg+xml",
            )

            client = TestClient(app)
            task_input = client.get(f"/api/tasks/{task.task_id}/inputs/1/image")
            task_output = client.get(f"/api/tasks/{task.task_id}/outputs/1/image")
            gallery_image = client.get(f"/api/gallery/{gallery_item['id']}/image")
            reference_image = client.get(
                f"/api/reference-assets/{reference_item['id']}/image"
            )
            files_still_exist = [
                input_path.is_file(),
                output_path.is_file(),
                app.state.gallery_storage.image_path(gallery_item["id"]).is_file(),
                app.state.reference_asset_storage.image_path(reference_item["id"]).is_file(),
            ]

        self.assertEqual(task_input.status_code, 415)
        self.assertEqual(task_output.status_code, 415)
        self.assertEqual(gallery_image.status_code, 415)
        self.assertEqual(reference_image.status_code, 415)
        self.assertEqual(files_still_exist, [True, True, True, True])


if __name__ == "__main__":
    unittest.main()
