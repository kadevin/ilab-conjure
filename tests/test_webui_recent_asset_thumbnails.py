from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image


class RecentAssetThumbnailTests(unittest.TestCase):
    def test_recent_upload_uses_bounded_thumbnail_and_keeps_original(self) -> None:
        from codex_image.webui.app import create_app
        from codex_image.webui.thumbnails import create_sidebar_thumbnail

        source = BytesIO()
        Image.effect_noise((800, 600), 100).convert("RGB").save(source, format="PNG")
        original_bytes = source.getvalue()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                input_root=root / "inputs",
                output_root=root / "outputs",
                auth_settings_path=root / "auth.json",
                webui_settings_path=root / "settings.json",
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            storage = app.state.reference_asset_storage
            asset = storage.create_or_touch("large.png", original_bytes, "image/png")
            client = TestClient(app)

            item = client.get("/api/reference-assets/recent").json()["items"][0]
            self.assertEqual(item["image_url"], f"/api/reference-assets/{asset['id']}/image")
            self.assertEqual(item["thumbnail_url"], f"/api/reference-assets/{asset['id']}/thumbnail")
            with patch(
                "codex_image.webui.reference_assets.create_sidebar_thumbnail",
                wraps=create_sidebar_thumbnail,
            ) as create_thumbnail:
                thumbnail = client.get(item["thumbnail_url"])
                again = client.get(item["thumbnail_url"])
            original = client.get(item["image_url"])
            thumbnail_path = storage.thumbnail_path(asset["id"])
            with Image.open(BytesIO(thumbnail.content)) as preview:
                thumbnail_format = preview.format
                thumbnail_size = preview.size

            self.assertEqual(thumbnail.status_code, 200)
            self.assertEqual(thumbnail.headers["content-type"], "image/webp")
            self.assertEqual(thumbnail.headers["cache-control"], "no-store")
            self.assertEqual(thumbnail_format, "WEBP")
            self.assertLessEqual(max(thumbnail_size), 256)
            self.assertLess(len(thumbnail.content), len(original_bytes))
            self.assertEqual(again.content, thumbnail.content)
            self.assertEqual(create_thumbnail.call_count, 1)
            self.assertEqual(original.content, original_bytes)

            deleted = client.delete(f"/api/reference-assets/{asset['id']}")
            self.assertEqual(deleted.status_code, 200)
            self.assertFalse(thumbnail_path.exists())
            self.assertEqual(client.get(item["thumbnail_url"]).status_code, 404)


if __name__ == "__main__":
    unittest.main()
