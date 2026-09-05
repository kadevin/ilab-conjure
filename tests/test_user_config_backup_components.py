from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image


class UserConfigBackupComponentTests(unittest.TestCase):
    def _png_bytes(self) -> bytes:
        image = Image.new("RGB", (10, 7), (48, 96, 144))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def _planner(self, root: Path):
        from codex_image.webui.color_settings import ColorPaletteSettings
        from codex_image.webui.gallery_storage import GalleryStorage
        from codex_image.webui.network_egress import NetworkEgressSettings
        from codex_image.webui.prompt_snippets import PromptSnippetSettings
        from codex_image.webui.prompt_template_assets import (
            PromptTemplateAssetStorage,
            PromptTemplateThumbnailResolver,
        )
        from codex_image.webui.prompt_templates import PromptTemplateSettings
        from codex_image.webui.provider_settings import ProviderSettings
        from codex_image.webui.settings_store import AuthSettings, WebUISettings
        from codex_image.webui.storage import TaskStorage
        from codex_image.webui.user_config_backup_components import (
            UserConfigBackupPlanner,
        )

        settings_root = root / "settings"
        task_storage = TaskStorage(
            root / "outputs",
            input_root=root / "inputs",
            source_data_root=root / "outputs" / "source-data",
        )
        asset_storage = PromptTemplateAssetStorage(
            root / "inputs" / "prompt-template-assets"
        )
        stores = {
            "color_settings": ColorPaletteSettings(settings_root / "colors.json"),
            "prompt_snippet_settings": PromptSnippetSettings(
                settings_root / "snippets.json"
            ),
            "gallery_storage": GalleryStorage(root / "inputs" / "gallery"),
            "prompt_template_settings": PromptTemplateSettings(
                settings_root / "templates.json"
            ),
            "prompt_template_asset_storage": asset_storage,
            "prompt_template_thumbnail_resolver": PromptTemplateThumbnailResolver(
                task_storage,
                asset_storage,
            ),
            "webui_settings": WebUISettings(settings_root / "webui.json"),
            "auth_settings": AuthSettings(settings_root / "auth.json"),
            "provider_settings": ProviderSettings(settings_root / "providers.json"),
            "network_egress_settings": NetworkEgressSettings(
                settings_root / "network.json"
            ),
        }
        return UserConfigBackupPlanner(**stores), stores

    def _populate(self, root: Path, stores: dict[str, object]) -> str:
        image_bytes = self._png_bytes()
        stores["color_settings"].write(  # type: ignore[attr-defined]
            {
                "favorites": [{"name": "Brand", "hex": "#457B66"}],
                "recent_colors": ["#FFFFFF", "#111111"],
                "recent_limit": 6,
            }
        )
        stores["prompt_snippet_settings"].create(  # type: ignore[attr-defined]
            {
                "tag": "portrait",
                "title": "Portrait",
                "content": "portrait lighting",
                "category": "常用",
            }
        )
        stores["gallery_storage"].create_item(  # type: ignore[attr-defined]
            "Reference",
            "portrait",
            "reference.png",
            image_bytes,
            "image/png",
        )
        asset = stores["prompt_template_asset_storage"].store(  # type: ignore[attr-defined]
            image_bytes,
            filename="template.png",
        )
        templates = stores["prompt_template_settings"]  # type: ignore[assignment]
        common = {
            "content": "Generate a composed image",
            "category": "常用",
            "tags": [],
            "mode": "any",
            "model_hint": "any",
        }
        templates.create(  # type: ignore[attr-defined]
            {
                **common,
                "title": "External",
                "thumbnail_url": "https://example.com/thumb.png",
            }
        )
        local_url = f"/api/prompt-template-assets/{asset.asset_id}/image"
        templates.create(  # type: ignore[attr-defined]
            {**common, "title": "Local 1", "thumbnail_url": local_url}
        )
        templates.create(  # type: ignore[attr-defined]
            {**common, "title": "Local 2", "thumbnail_url": local_url}
        )
        templates.create(  # type: ignore[attr-defined]
            {
                **common,
                "title": "Missing",
                "thumbnail_url": "/outputs/unowned.png",
            }
        )
        stores["webui_settings"].write_locale("zh-CN")  # type: ignore[attr-defined]
        stores["auth_settings"].write_source("api")  # type: ignore[attr-defined]
        stores["provider_settings"].write(  # type: ignore[attr-defined]
            {"api_key": "sk-secret-sentinel"}
        )
        stores["network_egress_settings"].write(  # type: ignore[attr-defined]
            {"mode": "direct", "image_request_retry_count": 1}
        )
        (root / "oauth-token.json").write_text(
            '{"token": "oauth-never-copy-sentinel", "cookie": "cookie-never-copy"}',
            encoding="utf-8",
        )
        return asset.asset_id

    def test_summary_and_plan_cover_all_sections_without_leaking_secrets(self) -> None:
        from codex_image.webui.user_config_backup_components import ClientPreferences

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            planner, stores = self._planner(root)
            asset_id = self._populate(root, stores)

            summaries = {item.section: item for item in planner.summary()}
            plan = planner.plan(
                ("chips", "gallery", "templates", "settings"),
                include_api_keys=False,
                client_preferences=ClientPreferences(
                    theme="dark",
                    notifications_in_app=True,
                    notifications_system=False,
                ),
            )

            self.assertEqual(summaries["chips"].item_count, 4)
            self.assertEqual(summaries["gallery"].item_count, 1)
            self.assertEqual(summaries["gallery"].size_bytes, len(self._png_bytes()))
            self.assertEqual(summaries["templates"].item_count, 5)
            self.assertEqual(summaries["settings"].item_count, 5)
            self.assertIn("api_keys_available", summaries["settings"].warnings)

            paths = {member.entry.path for member in plan.members}
            self.assertIn("chips/colors.json", paths)
            self.assertIn("gallery/categories.json", paths)
            self.assertIn("templates/prompt-templates.json", paths)
            self.assertIn(f"templates/thumbnails/{asset_id}.png", paths)
            self.assertIn("settings/client-preferences.json", paths)
            self.assertEqual(plan.manifest.sections, ("chips", "gallery", "templates", "settings"))
            self.assertFalse(plan.manifest.contains_secrets)

            packed_text = b"\n".join(
                member.data or b""
                for member in plan.members
                if member.data is not None
            ).decode("utf-8", errors="ignore")
            warning_text = repr(plan.warnings) + repr(summaries)
            self.assertNotIn("sk-secret-sentinel", packed_text)
            self.assertNotIn("oauth-never-copy-sentinel", packed_text + warning_text)
            self.assertNotIn("cookie-never-copy", packed_text + warning_text)

            template_member = next(
                member
                for member in plan.members
                if member.entry.path == "templates/prompt-templates.json"
            )
            template_payload = json.loads(template_member.data)
            by_title = {
                item["title"]: item for item in template_payload["templates"]
            }
            self.assertEqual(
                by_title["External"]["thumbnail_url"],
                "https://example.com/thumb.png",
            )
            self.assertEqual(
                by_title["Local 1"]["thumbnail_member"],
                f"templates/thumbnails/{asset_id}.png",
            )
            self.assertNotIn("thumbnail_url", by_title["Local 1"])
            self.assertNotIn("thumbnail_url", by_title["Missing"])
            self.assertTrue(
                any(warning.code == "template_thumbnail_missing" for warning in plan.warnings)
            )

            file_members = [member for member in plan.members if member.source_path]
            self.assertTrue(file_members)
            self.assertTrue(all(member.source_identity for member in file_members))

    def test_sensitive_plan_contains_keys_only_after_explicit_opt_in(self) -> None:
        from codex_image.webui.user_config_backup_components import ClientPreferences

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            planner, stores = self._planner(root)
            self._populate(root, stores)
            preferences = ClientPreferences("system", True, True)

            plan = planner.plan(
                ("settings",),
                include_api_keys=True,
                client_preferences=preferences,
            )
            provider_member = next(
                member
                for member in plan.members
                if member.entry.path == "settings/providers.json"
            )

            self.assertTrue(plan.manifest.contains_secrets)
            self.assertIn("sk-secret-sentinel", provider_member.data.decode("utf-8"))

    def test_settings_preferences_and_secret_selection_are_strict(self) -> None:
        from codex_image.webui.user_config_backup_components import ClientPreferences

        with tempfile.TemporaryDirectory() as tmp:
            planner, _ = self._planner(Path(tmp))
            with self.assertRaisesRegex(ValueError, "client_preferences"):
                planner.plan(
                    ("settings",),
                    include_api_keys=False,
                    client_preferences=None,
                )
            with self.assertRaisesRegex(ValueError, "include_api_keys"):
                planner.plan(
                    ("chips",),
                    include_api_keys=True,
                    client_preferences=None,
                )
            with self.assertRaises(ValueError):
                ClientPreferences("blue", True, False)  # type: ignore[arg-type]
            with self.assertRaises(ValueError):
                ClientPreferences("dark", 1, False)  # type: ignore[arg-type]

    def test_gallery_identity_failure_uses_a_safe_actionable_backup_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            planner, stores = self._planner(root)
            gallery = stores["gallery_storage"]
            item = gallery.create_item(  # type: ignore[attr-defined]
                "Reference",
                "portrait",
                "reference.png",
                self._png_bytes(),
                "image/png",
            )
            changed = Image.new("RGB", (10, 7), (160, 80, 40))
            buffer = BytesIO()
            changed.save(buffer, format="PNG")
            gallery.image_path(item["id"]).write_bytes(buffer.getvalue())  # type: ignore[attr-defined]

            with self.assertRaisesRegex(
                ValueError,
                "^user_config_backup_gallery_invalid$",
            ):
                planner.plan(
                    ("gallery",),
                    include_api_keys=False,
                    client_preferences=None,
                )

    def test_gallery_plan_canonicalizes_legacy_extensionless_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            planner, stores = self._planner(root)
            gallery = stores["gallery_storage"]
            item = gallery.create_item(  # type: ignore[attr-defined]
                "Legacy filename",
                "portrait",
                "png",
                self._png_bytes(),
                "image/png",
            )

            plan = planner.plan(
                ("gallery",),
                include_api_keys=False,
                client_preferences=None,
            )

            image_path = f"gallery/items/{item['id']}/image.png"
            metadata_path = f"gallery/items/{item['id']}/metadata.json"
            self.assertIn(image_path, {member.entry.path for member in plan.members})
            metadata_member = next(
                member for member in plan.members if member.entry.path == metadata_path
            )
            self.assertEqual(json.loads(metadata_member.data)["filename"], "image.png")
            self.assertEqual(gallery.image_path(item["id"]).name, "png")  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()
