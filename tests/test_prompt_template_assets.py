from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from PIL import Image


class PromptTemplateAssetTests(unittest.TestCase):
    def _image_bytes(
        self,
        image_format: str = "PNG",
        color: tuple[int, int, int] = (48, 96, 144),
    ) -> bytes:
        image = Image.new("RGB", (12, 8), color)
        buffer = BytesIO()
        image.save(buffer, format=image_format)
        return buffer.getvalue()

    def _task_storage(self, root: Path):
        from codex_image.webui.storage import TaskStorage

        return TaskStorage(
            root / "outputs",
            input_root=root / "inputs",
            source_data_root=root / "outputs" / "source-data",
        )

    def _owned_task_media(self, storage, image_bytes: bytes) -> tuple[str, Path, Path]:
        task = storage.create_task("edit")
        input_path = storage.write_input(task.task_id, "source.png", image_bytes)
        output_path = storage.write_output(task.task_id, image_bytes, "png", index=1)
        output_file = storage.output_file(output_path)
        storage.write_metadata(
            task.task_id,
            {
                "task_id": task.task_id,
                "status": "completed",
                "input_files": [input_path.name],
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
        return task.task_id, input_path, output_path

    def test_store_is_content_addressed_private_and_deduplicated(self) -> None:
        from codex_image.webui.prompt_template_assets import (
            PromptTemplateAssetStorage,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "inputs" / "prompt-template-assets"
            storage = PromptTemplateAssetStorage(root)
            data = self._image_bytes("PNG")

            first = storage.store(data, filename="thumbnail.bin")
            second = storage.store(data, filename="other.jpeg")

            self.assertEqual(first, second)
            self.assertEqual(first.asset_id, first.sha256)
            self.assertEqual(first.path, root / f"{first.sha256}.png")
            self.assertEqual(first.path.read_bytes(), data)
            self.assertEqual(first.mime_type, "image/png")
            self.assertEqual(first.size_bytes, len(data))
            self.assertEqual(first.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(storage.resolve(first.asset_id), first)
            self.assertEqual(storage.list_managed(), (first,))

    def test_resolve_rejects_invalid_ids_corrupt_files_and_digest_mismatches(self) -> None:
        from codex_image.webui.prompt_template_assets import (
            PromptTemplateAssetStorage,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "assets"
            root.mkdir(parents=True)
            storage = PromptTemplateAssetStorage(root)
            valid = storage.store(self._image_bytes(), filename="valid.png")

            corrupt_id = "a" * 64
            (root / f"{corrupt_id}.png").write_bytes(b"not an image")
            mismatched_id = "b" * 64
            (root / f"{mismatched_id}.png").write_bytes(
                self._image_bytes(color=(1, 2, 3))
            )

            self.assertIsNone(storage.resolve("../" + valid.asset_id))
            self.assertIsNone(storage.resolve(valid.asset_id.upper()))
            self.assertIsNone(storage.resolve(corrupt_id))
            self.assertIsNone(storage.resolve(mismatched_id))
            self.assertEqual(storage.list_managed(), (valid,))

    def test_resolver_accepts_only_owned_local_media_routes(self) -> None:
        from codex_image.webui.prompt_template_assets import (
            PromptTemplateAssetStorage,
            PromptTemplateThumbnailResolver,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_storage = self._task_storage(root)
            assets = PromptTemplateAssetStorage(root / "inputs" / "prompt-template-assets")
            resolver = PromptTemplateThumbnailResolver(task_storage, assets)
            image_bytes = self._image_bytes()
            task_id, input_path, output_path = self._owned_task_media(
                task_storage,
                image_bytes,
            )
            asset = assets.store(image_bytes, filename="template.png")
            output_file = task_storage.output_file(output_path)

            expected = {
                f"/api/tasks/{task_id}/inputs/1/image": input_path,
                f"/api/tasks/{task_id}/outputs/1/image": output_path,
                f"/inputs/{input_path.name}": input_path,
                f"/outputs/{output_file}": output_path,
                f"/api/prompt-template-assets/{asset.asset_id}/image": asset.path,
            }
            for url, path in expected.items():
                with self.subTest(url=url):
                    self.assertEqual(resolver.resolve(url), path)

    def test_resolver_rejects_external_ambiguous_unowned_and_escaped_paths(self) -> None:
        from codex_image.webui.prompt_template_assets import (
            PromptTemplateAssetStorage,
            PromptTemplateThumbnailResolver,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_storage = self._task_storage(root)
            assets = PromptTemplateAssetStorage(root / "inputs" / "prompt-template-assets")
            resolver = PromptTemplateThumbnailResolver(task_storage, assets)
            image_bytes = self._image_bytes()
            task_id, input_path, output_path = self._owned_task_media(
                task_storage,
                image_bytes,
            )
            output_file = task_storage.output_file(output_path)

            unowned_output = task_storage.output_root / "unowned.png"
            unowned_output.write_bytes(image_bytes)
            outside = root / "outside.png"
            outside.write_bytes(image_bytes)
            symlink_name = f"{task_id}-image-2.png"
            symlink_path = task_storage.output_root / symlink_name
            symlink_path.symlink_to(outside)

            denied = (
                "https://example.com/image.png",
                "http://example.com/image.png",
                "file:///etc/passwd",
                "data:image/png;base64,AAAA",
                "/etc/passwd",
                "/outputs/../outside.png",
                "/outputs/%2e%2e/outside.png",
                f"/outputs/{output_file}?download=/etc/passwd",
                f"/api/tasks/{task_id}/inputs/1/image?x=1",
                "/outputs/unowned.png",
                f"/outputs/{symlink_name}",
                "/api/prompt-template-assets/" + "f" * 64 + "/image",
            )
            for url in denied:
                with self.subTest(url=url):
                    self.assertIsNone(resolver.resolve(url))

            input_path.unlink()
            self.assertIsNone(
                resolver.resolve(f"/api/tasks/{task_id}/inputs/1/image")
            )

            metadata = task_storage.read_metadata(task_id)
            metadata["outputs"][0]["status"] = "deleted"
            metadata["outputs"][0]["deleted"] = True
            task_storage.write_metadata(task_id, metadata)
            self.assertIsNone(
                resolver.resolve(f"/api/tasks/{task_id}/outputs/1/image")
            )
            self.assertIsNone(resolver.resolve(f"/outputs/{output_file}"))

            if symlink_path.exists() or symlink_path.is_symlink():
                os.unlink(symlink_path)

    def test_app_exposes_only_valid_managed_assets_on_private_media_route(self) -> None:
        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings_root = root / "settings"
            asset_root = root / "isolated-template-assets"
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                source_data_root=root / "outputs" / "source-data",
                gallery_root=root / "inputs" / "gallery",
                reference_asset_root=root / "inputs" / "reference-assets",
                reference_file_root=root / "inputs" / "reference-files",
                prompt_template_asset_root=asset_root,
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
            asset = app.state.prompt_template_asset_storage.store(
                self._image_bytes(),
                filename="template.png",
            )
            client = TestClient(app)

            response = client.get(
                f"/api/prompt-template-assets/{asset.asset_id}/image"
            )
            missing = client.get(
                "/api/prompt-template-assets/" + "f" * 64 + "/image"
            )
            invalid = client.get("/api/prompt-template-assets/not-a-digest/image")

            self.assertEqual(app.state.prompt_template_asset_root, asset_root)
            self.assertEqual(
                app.state.prompt_template_thumbnail_resolver.resolve(
                    f"/api/prompt-template-assets/{asset.asset_id}/image"
                ),
                asset.path,
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, asset.path.read_bytes())
            self.assertEqual(response.headers["content-type"], "image/png")
            self.assertEqual(response.headers["cache-control"], "private, max-age=3600")
            self.assertEqual(missing.status_code, 404)
            self.assertEqual(invalid.status_code, 404)


if __name__ == "__main__":
    unittest.main()
