from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from PIL import Image


class UserConfigStoreSnapshotTests(unittest.TestCase):
    def _png_bytes(self) -> bytes:
        image = Image.new("RGB", (8, 6), (48, 96, 144))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def test_settings_snapshots_preserve_explicit_field_presence(self) -> None:
        from codex_image.webui.network_egress import NetworkEgressSettings
        from codex_image.webui.settings_store import AuthSettings, WebUISettings

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            webui_path = root / "webui.json"
            webui_path.write_text('{"locale": "zh-CN"}', encoding="utf-8")
            webui = WebUISettings(webui_path)
            webui_snapshot = webui.snapshot()

            self.assertEqual(webui_snapshot["present_fields"], ["locale"])
            self.assertEqual(webui_snapshot["values"]["locale"], "zh-CN")
            self.assertEqual(
                set(webui_snapshot["values"]),
                {
                    "input_root",
                    "output_root",
                    "gallery_root",
                    "source_data_root",
                    "locale",
                },
            )
            webui_snapshot["values"]["locale"] = "en"
            self.assertEqual(webui.snapshot()["values"]["locale"], "zh-CN")

            auth = AuthSettings(root / "auth.json")
            self.assertFalse(auth.snapshot()["present"])
            auth.write_source("api")
            self.assertEqual(auth.snapshot(), {"source": "api", "present": True})

            network_path = root / "network.json"
            network_path.write_text('{"mode": "direct"}', encoding="utf-8")
            network = NetworkEgressSettings(network_path)
            network_snapshot = network.snapshot_payload()
            self.assertEqual(network_snapshot["present_fields"], ["mode"])
            self.assertEqual(network_snapshot["values"]["mode"], "direct")
            self.assertEqual(
                network_snapshot["values"]["image_request_retry_count"],
                2,
            )

    def test_json_stores_expose_reentrant_exclusive_contexts(self) -> None:
        from codex_image.webui.color_settings import ColorPaletteSettings
        from codex_image.webui.prompt_snippets import PromptSnippetSettings
        from codex_image.webui.prompt_templates import PromptTemplateSettings

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stores = (
                ColorPaletteSettings(root / "colors.json"),
                PromptSnippetSettings(root / "snippets.json"),
                PromptTemplateSettings(root / "templates.json"),
            )
            for store in stores:
                with self.subTest(store=type(store).__name__):
                    with store.exclusive():
                        with store.exclusive():
                            snapshot = store.read()
                    snapshot.clear()
                    self.assertTrue(store.read())

    def test_provider_backup_snapshot_controls_secrets_and_replace_is_exact(self) -> None:
        from codex_image.webui.provider_settings import ProviderSettings

        with tempfile.TemporaryDirectory() as tmp:
            settings = ProviderSettings(Path(tmp) / "providers.json")
            settings.write({"api_key": "sk-secret"})

            public_snapshot = settings.backup_snapshot(include_api_keys=False)
            secret_snapshot = settings.backup_snapshot(include_api_keys=True)

            self.assertEqual(
                set(public_snapshot),
                {
                    "schema_version",
                    "codex_mode",
                    "active_provider_id",
                    "default_provider_by_model",
                    "providers",
                },
            )
            self.assertNotIn("api_key", json.dumps(public_snapshot))
            self.assertIn("sk-secret", json.dumps(secret_snapshot))

            replacement = json.loads(json.dumps(public_snapshot))
            replacement["providers"][0]["name"] = "Restored"
            restored = settings.replace_snapshot(replacement)

            self.assertEqual(restored["providers"][0]["name"], "Restored")
            self.assertEqual(restored["providers"][0]["api_key"], "")
            self.assertNotIn("sk-secret", settings.path.read_text(encoding="utf-8"))
            self.assertNotIn('"api_key":', json.dumps(settings.public_settings()))
            self.assertEqual(settings.path.stat().st_mode & 0o777, 0o600)

    def test_gallery_snapshot_round_trips_owned_images_and_rejects_tampering(self) -> None:
        from dataclasses import replace

        from codex_image.webui.gallery_storage import GalleryStorage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = GalleryStorage(root / "source")
            item = source.create_item(
                "Reference",
                "portrait",
                "reference.png",
                self._png_bytes(),
                "image/png",
            )

            snapshot = source.snapshot()
            managed = source.managed_paths()
            self.assertEqual(len(snapshot.items), 1)
            self.assertEqual(snapshot.items[0].metadata["id"], item["id"])
            self.assertIn(
                source.root / item["id"] / "metadata.json",
                managed,
            )
            self.assertIn(source.image_path(item["id"]), managed)

            target = GalleryStorage(root / "target")
            target.write_snapshot(snapshot)
            restored = target.read_item(item["id"])
            self.assertEqual(restored["sha256"], item["sha256"])
            self.assertEqual(target.image_path(item["id"]).read_bytes(), self._png_bytes())

            tampered_item = replace(
                snapshot.items[0],
                sha256="0" * 64,
            )
            with self.assertRaisesRegex(ValueError, "digest"):
                GalleryStorage(root / "rejected").write_snapshot(
                    replace(snapshot, items=(tampered_item,))
                )

    def test_gallery_snapshot_derives_identity_for_legacy_metadata(self) -> None:
        from codex_image.webui.gallery_storage import GalleryStorage

        with tempfile.TemporaryDirectory() as tmp:
            gallery = GalleryStorage(Path(tmp) / "gallery")
            item = gallery.create_item(
                "Legacy reference",
                "portrait",
                "legacy.png",
                self._png_bytes(),
                "image/png",
            )
            metadata_path = gallery.root / item["id"] / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata.pop("sha256")
            metadata.pop("size_bytes")
            metadata["mime_type"] = "image/jpeg"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            snapshot = gallery.snapshot()

            self.assertEqual(len(snapshot.items), 1)
            legacy = snapshot.items[0]
            self.assertEqual(legacy.metadata["sha256"], legacy.sha256)
            self.assertEqual(legacy.metadata["size_bytes"], len(self._png_bytes()))
            self.assertEqual(legacy.metadata["mime_type"], "image/png")

    def test_queue_exclusive_blocks_json_and_sqlite_mutations(self) -> None:
        from codex_image.webui.queue_storage import QueueStorage, SQLiteQueueStorage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stores = (
                QueueStorage(root / "queue.json"),
                SQLiteQueueStorage(root / "queue.db"),
            )
            for index, store in enumerate(stores):
                with self.subTest(store=type(store).__name__):
                    task_id = f"task-{index}"
                    started = threading.Event()
                    finished = threading.Event()

                    def enqueue() -> None:
                        started.set()
                        store.enqueue(task_id)
                        finished.set()

                    with store.exclusive():
                        thread = threading.Thread(target=enqueue)
                        thread.start()
                        self.assertTrue(started.wait(timeout=1))
                        time.sleep(0.05)
                        self.assertFalse(finished.is_set())
                        self.assertNotIn(task_id, store.read_state()["waiting"])
                    thread.join(timeout=1)
                    self.assertTrue(finished.is_set())
                    self.assertIn(task_id, store.read_state()["waiting"])


if __name__ == "__main__":
    unittest.main()
