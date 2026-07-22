from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from codex_image.webui.app import create_app
from codex_image.webui.storage import QueueStorage, SQLiteQueueStorage, TaskStorage


class WebUIRefactorContractTests(unittest.TestCase):
    def test_create_app_remains_callable(self) -> None:
        self.assertTrue(callable(create_app))

    def test_auth_routing_backend_contract(self) -> None:
        from codex_image.webui import auth_routing

        self.assertEqual(
            auth_routing.BACKEND_OPENAI_RESPONSES,
            auth_routing._backend_for_submit("api", "responses"),
        )
        self.assertEqual(
            auth_routing.BACKEND_OPENAI_IMAGES,
            auth_routing._backend_for_submit("api", "images"),
        )
        self.assertEqual(
            auth_routing.BACKEND_CODEX_IMAGES,
            auth_routing._backend_for_submit("codex", None),
        )
        self.assertEqual(
            auth_routing.BACKEND_CODEX_RESPONSES,
            auth_routing._backend_for_submit("codex", None, "responses"),
        )

    def test_task_output_and_enrichment_modules_are_importable(self) -> None:
        from codex_image.webui import task_enrichment, task_outputs

        for name in (
            "_accept_partial_task_successes",
            "_downloadable_output_paths",
            "_finalize_generated_task",
            "_write_queued_metadata",
        ):
            self.assertTrue(callable(getattr(task_outputs, name)))
        for name in (
            "_gallery_item_response",
            "_reference_asset_response",
            "_with_file_urls",
                "_params",
        ):
            self.assertTrue(callable(getattr(task_enrichment, name)))

    def test_storage_utils_module_contract_and_legacy_imports(self) -> None:
        from codex_image.webui import storage_utils
        from codex_image.webui.storage import _guess_mime_type, utc_now

        for name in (
            "utc_now",
            "_safe_filename",
            "_safe_extension",
            "_task_date_directory",
            "_safe_output_relative_path",
            "_guess_mime_type",
        ):
            self.assertTrue(callable(getattr(storage_utils, name)))
        self.assertTrue(callable(utc_now))
        self.assertTrue(callable(_guess_mime_type))

    def test_color_settings_module_contract_and_legacy_imports(self) -> None:
        from codex_image.webui import color_settings
        from codex_image.webui.settings_store import (
            ColorPaletteSettings as LegacyColorPaletteSettings,
            DEFAULT_COLOR_FAVORITES as LegacyDefaultColorFavorites,
            MAX_COLOR_IMPORT_BYTES as LegacyMaxColorImportBytes,
            _color_palette_css as legacy_color_palette_css,
            _normalize_hex_color as legacy_normalize_hex_color,
            _parse_color_palette_import as legacy_parse_color_palette_import,
        )

        self.assertIs(color_settings.ColorPaletteSettings, LegacyColorPaletteSettings)
        self.assertIs(color_settings.DEFAULT_COLOR_FAVORITES, LegacyDefaultColorFavorites)
        self.assertEqual(color_settings.MAX_COLOR_IMPORT_BYTES, LegacyMaxColorImportBytes)
        self.assertIs(color_settings._color_palette_css, legacy_color_palette_css)
        self.assertIs(color_settings._normalize_hex_color, legacy_normalize_hex_color)
        self.assertIs(color_settings._parse_color_palette_import, legacy_parse_color_palette_import)
        self.assertEqual("#AABBCC", color_settings._normalize_hex_color("abc"))
        self.assertEqual("brand green", color_settings._color_name_from_slug("brand-green"))
        self.assertGreater(len(color_settings.ColorPaletteSettings.default_settings()["favorites"]), 0)

    def test_prompt_snippets_module_contract_and_legacy_imports(self) -> None:
        from codex_image.webui import prompt_snippets
        from codex_image.webui.settings_store import (
            MAX_PROMPT_SNIPPETS as LegacyMaxPromptSnippets,
            PromptSnippetSettings as LegacyPromptSnippetSettings,
            _clean_prompt_snippet_tag as legacy_clean_prompt_snippet_tag,
            _normalize_prompt_snippet_payload as legacy_normalize_prompt_snippet_payload,
            _normalize_prompt_snippets_payload as legacy_normalize_prompt_snippets_payload,
        )

        self.assertIs(prompt_snippets.PromptSnippetSettings, LegacyPromptSnippetSettings)
        self.assertEqual(prompt_snippets.MAX_PROMPT_SNIPPETS, LegacyMaxPromptSnippets)
        self.assertIs(prompt_snippets._clean_prompt_snippet_tag, legacy_clean_prompt_snippet_tag)
        self.assertIs(prompt_snippets._normalize_prompt_snippet_payload, legacy_normalize_prompt_snippet_payload)
        self.assertIs(prompt_snippets._normalize_prompt_snippets_payload, legacy_normalize_prompt_snippets_payload)
        self.assertEqual("style", prompt_snippets._clean_prompt_snippet_tag("~style"))
        self.assertEqual({"version": 1, "snippets": []}, prompt_snippets.PromptSnippetSettings.default_settings())

    def test_prompt_templates_module_contract_and_legacy_imports(self) -> None:
        from codex_image.webui import prompt_templates
        from codex_image.webui.settings_store import (
            MAX_PROMPT_TEMPLATES as LegacyMaxPromptTemplates,
            PromptTemplateSettings as LegacyPromptTemplateSettings,
            _extract_prompt_template_variables as legacy_extract_prompt_template_variables,
            _normalize_prompt_template_payload as legacy_normalize_prompt_template_payload,
            _normalize_prompt_templates_payload as legacy_normalize_prompt_templates_payload,
        )

        self.assertIs(prompt_templates.PromptTemplateSettings, LegacyPromptTemplateSettings)
        self.assertEqual(prompt_templates.MAX_PROMPT_TEMPLATES, LegacyMaxPromptTemplates)
        self.assertIs(prompt_templates._extract_prompt_template_variables, legacy_extract_prompt_template_variables)
        self.assertIs(prompt_templates._normalize_prompt_template_payload, legacy_normalize_prompt_template_payload)
        self.assertIs(prompt_templates._normalize_prompt_templates_payload, legacy_normalize_prompt_templates_payload)
        self.assertEqual(["产品名"], prompt_templates._extract_prompt_template_variables("生成 {{产品名}} 主图"))
        defaults = prompt_templates.PromptTemplateSettings.default_settings()
        self.assertEqual(defaults["version"], 1)
        self.assertEqual(defaults["templates"], [])
        self.assertIn({"id": "常用", "name": "常用", "order": 10}, defaults["categories"])

    def test_reference_assets_module_contract_and_legacy_imports(self) -> None:
        from codex_image.webui import reference_assets
        from codex_image.webui.storage import (
            REFERENCE_ASSET_SUFFIXES as LegacyReferenceAssetSuffixes,
            ReferenceAssetStorage as LegacyReferenceAssetStorage,
            _reference_asset_suffix as legacy_reference_asset_suffix,
        )

        self.assertTrue(callable(reference_assets.ReferenceAssetStorage))
        self.assertTrue(callable(reference_assets._reference_asset_suffix))
        self.assertIs(reference_assets.ReferenceAssetStorage, LegacyReferenceAssetStorage)
        self.assertIs(reference_assets.REFERENCE_ASSET_SUFFIXES, LegacyReferenceAssetSuffixes)
        self.assertIs(reference_assets._reference_asset_suffix, legacy_reference_asset_suffix)
        self.assertTrue(reference_assets.REFERENCE_ASSET_SUFFIXES)
        self.assertGreater(reference_assets.MAX_REFERENCE_ASSETS, 0)
        self.assertEqual(".jpg", reference_assets._reference_asset_suffix("photo.jpeg"))
        self.assertEqual(".png", reference_assets._reference_asset_suffix("photo.jpe"))
        self.assertEqual(".jpg", reference_assets._reference_asset_suffix("photo.bin", "image/jpeg"))

    def test_gallery_storage_module_contract_and_legacy_imports(self) -> None:
        from codex_image.webui import gallery_storage
        from codex_image.webui.storage import (
            DEFAULT_GALLERY_CATEGORIES as LegacyDefaultGalleryCategories,
            GALLERY_CATEGORIES as LegacyGalleryCategories,
            GalleryStorage as LegacyGalleryStorage,
            _clean_gallery_category as legacy_clean_gallery_category,
            _clean_gallery_category_id as legacy_clean_gallery_category_id,
            _clean_gallery_category_name as legacy_clean_gallery_category_name,
            _clean_gallery_name as legacy_clean_gallery_name,
            _clean_gallery_prompt_note as legacy_clean_gallery_prompt_note,
            _clean_gallery_prompt_role as legacy_clean_gallery_prompt_role,
            _gallery_name_key as legacy_gallery_name_key,
            _normalize_gallery_category as legacy_normalize_gallery_category,
        )

        self.assertIs(gallery_storage.GalleryStorage, LegacyGalleryStorage)
        self.assertIs(gallery_storage.DEFAULT_GALLERY_CATEGORIES, LegacyDefaultGalleryCategories)
        self.assertIs(gallery_storage.GALLERY_CATEGORIES, LegacyGalleryCategories)
        for name in (
            "_clean_gallery_name",
            "_gallery_name_key",
            "_clean_gallery_category",
            "_clean_gallery_category_id",
            "_clean_gallery_category_name",
            "_clean_gallery_prompt_role",
            "_clean_gallery_prompt_note",
            "_normalize_gallery_category",
        ):
            self.assertTrue(callable(getattr(gallery_storage, name)))
        self.assertIs(gallery_storage._clean_gallery_name, legacy_clean_gallery_name)
        self.assertIs(gallery_storage._gallery_name_key, legacy_gallery_name_key)
        self.assertIs(gallery_storage._clean_gallery_category, legacy_clean_gallery_category)
        self.assertIs(gallery_storage._clean_gallery_category_id, legacy_clean_gallery_category_id)
        self.assertIs(gallery_storage._clean_gallery_category_name, legacy_clean_gallery_category_name)
        self.assertIs(gallery_storage._clean_gallery_prompt_role, legacy_clean_gallery_prompt_role)
        self.assertIs(gallery_storage._clean_gallery_prompt_note, legacy_clean_gallery_prompt_note)
        self.assertIs(gallery_storage._normalize_gallery_category, legacy_normalize_gallery_category)
        self.assertTrue(gallery_storage.DEFAULT_GALLERY_CATEGORIES)
        self.assertIn("portrait", gallery_storage.GALLERY_CATEGORIES)

    def test_queue_storage_module_contract_and_legacy_imports(self) -> None:
        from codex_image.webui import queue_storage
        from codex_image.webui.storage import (
            QueueStorage as LegacyQueueStorage,
            SQLiteQueueStorage as LegacySQLiteQueueStorage,
        )

        self.assertTrue(callable(queue_storage.QueueStorage))
        self.assertTrue(callable(queue_storage.SQLiteQueueStorage))
        self.assertIs(queue_storage.QueueStorage, LegacyQueueStorage)
        self.assertIs(queue_storage.SQLiteQueueStorage, LegacySQLiteQueueStorage)

    def test_recovery_module_is_importable_without_queue_runtime(self) -> None:
        from codex_image.webui import recovery

        for name in (
            "_migrate_legacy_task_directories",
            "_migrate_legacy_inputs",
            "_migrate_legacy_mask",
            "_migrate_legacy_outputs",
            "_migrate_legacy_gallery_directory",
            "_prune_missing_queue_tasks",
            "_prune_duplicate_request_payloads",
            "_materialize_orphaned_running_failure",
            "_recover_queue_state",
            "_is_legacy_auto_retry_queue_task",
            "_recover_completed_outputs_from_disk",
            "_recoverable_total_count",
            "_disk_output_paths",
            "_output_index_from_path",
        ):
            self.assertTrue(callable(getattr(recovery, name)))

    def test_queue_runtime_module_contract(self) -> None:
        from codex_image.webui import queue_runtime

        for name in (
            "QueueRuntimeResult",
            "install_queue_runtime",
            "_queue_channel_worker_loop",
            "_queue_worker_loop",
            "_ensure_queue_worker_running",
            "_queue_channel_available",
            "_client_for_queue_channel",
            "execute_task",
        ):
            self.assertTrue(callable(getattr(queue_runtime, name)))
        self.assertFalse(hasattr(queue_runtime, "_record_local_quota_usage"))
        self.assertFalse(hasattr(queue_runtime, "_has_local_quota_retry_alternative"))

        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "import codex_image.webui.queue_runtime; "
                    "print('codex_image.webui.app' in sys.modules)"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual("", probe.stderr)
        self.assertEqual("False", probe.stdout.strip())

    def test_client_modules_keep_legacy_import_contract(self) -> None:
        from codex_image import client
        from codex_image.client_types import ImageResult, image_model_supports_input_fidelity
        from codex_image.codex_responses_client import CodexImageClient
        from codex_image.openai_images_client import OpenAIImagesImageClient
        from codex_image.openai_responses_client import OpenAIResponsesImageClient

        self.assertIs(client.ImageResult, ImageResult)
        self.assertIs(client.CodexImageClient, CodexImageClient)
        self.assertIs(client.OpenAIImagesImageClient, OpenAIImagesImageClient)
        self.assertIs(client.OpenAIResponsesImageClient, OpenAIResponsesImageClient)
        self.assertIs(client.image_model_supports_input_fidelity, image_model_supports_input_fidelity)
        self.assertEqual("gpt-5.4-mini", client.DEFAULT_MAIN_MODEL)
        self.assertEqual("gpt-image-2", client.DEFAULT_IMAGE_MODEL)

    def test_executor_helper_modules_keep_legacy_import_contract(self) -> None:
        from codex_image.webui import executor, executor_inputs, executor_progress, executor_transport

        for name in (
            "_normalize_api_mode",
            "_normalize_api_images_concurrency",
            "_image_request_timeout_seconds",
            "_normalize_prompt_fidelity",
            "_prompt_for_transport",
            "_instructions_for_transport",
            "_noop_request_context",
            "_call_image_client",
            "_direct_images_concurrent_enabled",
            "_debug_sse_path",
            "_is_usage_limit_error",
            "_parse_optional_int",
            "_normalize_compression",
        ):
            self.assertIs(getattr(executor, name), getattr(executor_transport, name))
        for name in (
            "_file_to_data_url",
            "_image_mime_type",
            "_sniff_image_mime_type",
            "_resolve_reference_assets",
            "_resolve_gallery_refs",
            "_task_cancel_requested",
            "_raise_if_task_cancelled",
        ):
            self.assertIs(getattr(executor, name), getattr(executor_inputs, name))
        self.assertIs(
            executor._restore_completed_output_progress,
            executor_progress._restore_completed_output_progress,
        )

    def test_create_app_keeps_public_route_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), auth_checker=lambda: True, auto_start_queue=False)

            route_surface = {
                (getattr(route, "path", ""), method)
                for route in app.routes
                if hasattr(route, "methods")
                if getattr(route, "path", "") == "/" or getattr(route, "path", "").startswith("/api/")
                for method in set(getattr(route, "methods", None) or []) - {"HEAD", "OPTIONS"}
            }
            expected_surface = {
                ("/", "GET"),
                ("/api/health", "GET"),
                ("/api/app-version", "GET"),
                ("/api/app-version/open-updater", "POST"),
                ("/api/app-version/dismiss-onboarding", "POST"),
                ("/api/settings", "GET"),
                ("/api/settings", "PATCH"),
                ("/api/color-palette", "GET"),
                ("/api/color-palette", "PATCH"),
                ("/api/color-palette/export.css", "GET"),
                ("/api/color-palette/import", "POST"),
                ("/api/prompt-snippets", "GET"),
                ("/api/prompt-snippets", "POST"),
                ("/api/prompt-snippets/{snippet_id}", "PATCH"),
                ("/api/prompt-snippets/{snippet_id}", "DELETE"),
                ("/api/prompt-templates", "GET"),
                ("/api/prompt-templates", "POST"),
                ("/api/prompt-templates/export.json", "GET"),
                ("/api/prompt-templates/import", "POST"),
                ("/api/prompt-templates/{template_id}", "PATCH"),
                ("/api/prompt-templates/{template_id}", "DELETE"),
                ("/api/prompt-templates/{template_id}/use", "POST"),
                ("/api/prompt-template-categories", "POST"),
                ("/api/prompt-template-categories/{category_id}", "PATCH"),
                ("/api/prompt-template-categories/{category_id}", "DELETE"),
                ("/api/auth", "GET"),
                ("/api/auth", "PATCH"),
                ("/api/api-settings", "GET"),
                ("/api/api-settings", "PATCH"),
                ("/api/network-egress", "GET"),
                ("/api/network-egress", "PATCH"),
                ("/api/network-egress/test", "POST"),
                ("/api/tasks", "GET"),
                ("/api/tasks/recent", "GET"),
                ("/api/task-history/summary", "GET"),
                ("/api/task-history/tasks", "GET"),
                ("/api/tasks/{task_id}", "GET"),
                ("/api/tasks/{task_id}", "DELETE"),
                ("/api/tasks/{task_id}/viewed", "PATCH"),
                ("/api/tasks/{task_id}/outputs.zip", "GET"),
                ("/api/tasks/{task_id}/reveal-output", "POST"),
                ("/api/tasks/{task_id}/inputs/{input_index}/thumbnail", "GET"),
                ("/api/tasks/{task_id}/reference-files/{file_index}/download", "GET"),
                ("/api/tasks/{task_id}/outputs/{output_index}/thumbnail", "GET"),
                ("/api/tasks/{task_id}/outputs/{output_index}/selected", "PATCH"),
                ("/api/tasks/{task_id}/outputs/delete-unselected", "POST"),
                ("/api/tasks/{task_id}/archive", "PATCH"),
                ("/api/tasks/{task_id}/retry-failed", "POST"),
                ("/api/tasks/{task_id}/accept-successes", "POST"),
                ("/api/queue", "GET"),
                ("/api/queue/reorder", "PATCH"),
                ("/api/queue/{task_id}/promote", "POST"),
                ("/api/queue/{task_id}", "DELETE"),
                ("/api/events", "GET"),
                ("/api/gallery", "GET"),
                ("/api/gallery", "POST"),
                ("/api/gallery/categories", "GET"),
                ("/api/gallery/categories", "POST"),
                ("/api/gallery/categories/reorder", "PATCH"),
                ("/api/gallery/categories/{category_id}", "PATCH"),
                ("/api/gallery/categories/{category_id}", "DELETE"),
                ("/api/gallery/reorder", "PATCH"),
                ("/api/gallery/{item_id}", "PATCH"),
                ("/api/gallery/{item_id}", "DELETE"),
                ("/api/gallery/{item_id}/image", "GET"),
                ("/api/gallery/{item_id}/image", "PUT"),
                ("/api/reference-assets/recent", "GET"),
                ("/api/reference-assets/{asset_id}", "DELETE"),
                ("/api/reference-assets/{asset_id}/image", "GET"),
                ("/api/reference-files/recent", "GET"),
                ("/api/generate", "POST"),
                ("/api/edit", "POST"),
            }
            self.assertEqual(expected_surface, route_surface)

    def test_create_app_keeps_core_state_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), auth_checker=lambda: True, auto_start_queue=False)

            self.assertIsInstance(app.state.storage, TaskStorage)
            self.assertIsInstance(app.state.queue_storage, SQLiteQueueStorage)
            self.assertTrue(hasattr(app.state, "queue_manager"))
            self.assertTrue(hasattr(app.state, "api_settings"))
            self.assertTrue(hasattr(app.state, "auth_settings"))
            self.assertTrue(hasattr(app.state, "network_egress_settings"))
            self.assertTrue(hasattr(app.state, "network_egress_manager"))
            self.assertFalse(hasattr(app.state, "account_quota_cache"))
            self.assertTrue(hasattr(app.state, "active_task_ids"))
            self.assertTrue(hasattr(app.state, "running_worker_tasks"))
            self.assertIs(app.state.ctx.storage, app.state.storage)
            self.assertIs(app.state.ctx.queue_storage, app.state.queue_storage)
            self.assertIs(app.state.ctx.queue_manager, app.state.queue_manager)

    def test_health_route_still_reports_auth_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), auth_checker=lambda: True, auto_start_queue=False)
            response = TestClient(app).get("/api/health")

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["auth_available"])
