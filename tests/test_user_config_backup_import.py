from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


class UserConfigBackupImportTests(unittest.TestCase):
    def _archive(
        self,
        path: Path,
        *,
        members: dict[str, bytes] | None = None,
        contains_secrets: bool = False,
        format_version: int = 1,
        compression: int = zipfile.ZIP_DEFLATED,
        extra_entries: list[tuple[zipfile.ZipInfo | str, bytes]] = [],
    ) -> bytes:
        from codex_image.webui.user_config_backup_format import (
            USER_CONFIG_BACKUP_FORMAT,
        )

        payloads = members or {
            "chips/colors.json": json.dumps(
                {
                    "version": 1,
                    "favorites": [],
                    "recent_colors": [],
                    "recent_limit": 6,
                }
            ).encode(),
            "chips/prompt-snippets.json": b'{"version":1,"snippets":[]}',
        }
        sections = [
            section
            for section in ("chips", "gallery", "templates", "settings")
            if any(name.startswith(section + "/") for name in payloads)
        ]
        manifest = {
            "format": USER_CONFIG_BACKUP_FORMAT,
            "format_version": format_version,
            "app_version": "test",
            "created_at": "2026-08-21T12:00:00Z",
            "sections": sections,
            "contains_secrets": contains_secrets,
            "members": [
                {
                    "section": name.split("/", 1)[0],
                    "path": name,
                    "size_bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
                for name, data in payloads.items()
            ],
        }
        with zipfile.ZipFile(path, "w", compression=compression) as archive:
            for name, data in payloads.items():
                archive.writestr(name, data)
            for info, data in extra_entries:
                archive.writestr(info, data)
            archive.writestr("manifest.json", json.dumps(manifest).encode())
        return path.read_bytes()

    def _service(self, root: Path, **overrides):
        from codex_image.webui.user_config_backup_import import (
            UserConfigBackupImportService,
        )

        options = {
            "max_chunk_bytes": 8,
            "max_upload_bytes": 1024 * 1024,
            "max_expanded_bytes": 1024 * 1024,
            "max_member_bytes": 512 * 1024,
            "max_manifest_bytes": 64 * 1024,
            "max_entries": 100,
            "max_compression_ratio": 200,
            "min_free_bytes": 0,
            "free_ratio": 0,
            "ttl_seconds": 24 * 60 * 60,
        }
        options.update(overrides)
        return UserConfigBackupImportService(None, root / "imports", **options)

    def _upload(self, service, payload: bytes):
        session = service.create("backup.zip", len(payload))
        for offset in range(0, len(payload), 8):
            chunk = payload[offset : offset + 8]
            session = service.append_chunk(
                session.session_id,
                offset,
                chunk,
                hashlib.sha256(chunk).hexdigest(),
            )
        return session

    def test_chunk_upload_is_private_exact_and_last_retry_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._archive(root / "valid.zip")
            service = self._service(root)
            session = service.create("backup.zip", len(archive))
            first = archive[:8]
            updated = service.append_chunk(
                session.session_id,
                0,
                first,
                hashlib.sha256(first).hexdigest(),
            )
            retried = service.append_chunk(
                session.session_id,
                0,
                first,
                hashlib.sha256(first).hexdigest(),
            )

            self.assertEqual(updated, retried)
            self.assertEqual(
                (service.root / f"{session.session_id}.upload").stat().st_mode
                & 0o777,
                0o600,
            )
            with self.assertRaisesRegex(ValueError, "retry_mismatch"):
                different = b"differen"
                service.append_chunk(
                    session.session_id,
                    0,
                    different,
                    hashlib.sha256(different).hexdigest(),
                )
            with self.assertRaisesRegex(ValueError, "offset"):
                service.append_chunk(
                    session.session_id,
                    9,
                    b"x",
                    hashlib.sha256(b"x").hexdigest(),
                )

    def test_valid_archive_extracts_declared_members_and_returns_no_write_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self._archive(root / "valid.zip")
            service = self._service(root)
            session = self._upload(service, payload)
            preview = service.validate(session.session_id)

            self.assertTrue(preview.restorable)
            self.assertEqual(preview.archive_sha256, hashlib.sha256(payload).hexdigest())
            self.assertEqual([item.section for item in preview.sections], ["chips"])
            self.assertTrue(preview.preview_revision)
            staging = service.root / f"{session.session_id}.staging"
            self.assertEqual(
                (staging / "chips" / "colors.json").stat().st_mode & 0o777,
                0o600,
            )
            self.assertFalse(any(root.glob("settings/*.json")))

    def test_hostile_zip_shapes_are_rejected_before_restore(self) -> None:
        cases: list[tuple[str, bytes, str]] = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            duplicate_path = root / "duplicate.zip"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                cases.append(
                    (
                        "duplicate",
                        self._archive(
                            duplicate_path,
                            extra_entries=[("chips/colors.json", b"duplicate")],
                        ),
                        "duplicate_entry",
                    )
                )
            cases.append(
                (
                    "traversal",
                    self._archive(
                        root / "traversal.zip",
                        extra_entries=[("../escape.json", b"escape")],
                    ),
                    "member_path",
                )
            )
            symlink = zipfile.ZipInfo("link")
            symlink.create_system = 3
            symlink.external_attr = (0o120777 << 16)
            cases.append(
                (
                    "symlink",
                    self._archive(
                        root / "symlink.zip",
                        extra_entries=[(symlink, b"target")],
                    ),
                    "non_regular",
                )
            )
            cases.append(
                (
                    "undeclared",
                    self._archive(
                        root / "undeclared.zip",
                        extra_entries=[("extra.json", b"extra")],
                    ),
                    "undeclared_member",
                )
            )
            cases.append(
                (
                    "unsupported-compression",
                    self._archive(
                        root / "bzip.zip",
                        compression=zipfile.ZIP_BZIP2,
                    ),
                    "compression_unsupported",
                )
            )

            for name, payload, code in cases:
                with self.subTest(name=name):
                    service = self._service(root / name)
                    session = self._upload(service, payload)
                    with self.assertRaisesRegex(ValueError, code):
                        service.validate(session.session_id)

    def test_semantic_validation_rejects_secrets_template_ambiguity_and_fake_raster(self) -> None:
        semantic_cases = (
            (
                "secret",
                {
                    "settings/webui.json": b'{"values":{},"present_fields":[]}',
                    "settings/auth-source.json": b'{"source":"api","present":true}',
                    "settings/providers.json": b'{"schema_version":2,"api_key":"secret"}',
                    "settings/network.json": b'{"values":{},"present_fields":[]}',
                    "settings/client-preferences.json": b'{"theme":"system","notifications_in_app":true,"notifications_system":false}',
                },
                "secret_declaration",
            ),
            (
                "template-both",
                {
                    "templates/prompt-templates.json": json.dumps(
                        {
                            "version": 1,
                            "categories": [],
                            "templates": [
                                {
                                    "id": "t1",
                                    "thumbnail_url": "https://example.com/a.png",
                                    "thumbnail_member": "templates/thumbnails/"
                                    + "a" * 64
                                    + ".png",
                                }
                            ],
                        }
                    ).encode(),
                    "templates/thumbnails/" + "a" * 64 + ".png": b"not-png",
                },
                "template_thumbnail_ambiguous",
            ),
            (
                "fake-raster",
                {
                    "gallery/categories.json": b'[{"id":"portrait","name":"Portrait"}]',
                    "gallery/items/item1/metadata.json": json.dumps(
                        {
                            "id": "item1",
                            "name": "Item",
                            "category": "portrait",
                            "filename": "image.png",
                            "mime_type": "image/png",
                            "size_bytes": 8,
                            "sha256": hashlib.sha256(b"notimage").hexdigest(),
                        }
                    ).encode(),
                    "gallery/items/item1/image.png": b"notimage",
                },
                "raster_invalid",
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, members, code in semantic_cases:
                with self.subTest(name=name):
                    payload = self._archive(root / f"{name}.zip", members=members)
                    service = self._service(root / name)
                    session = self._upload(service, payload)
                    with self.assertRaisesRegex(ValueError, code):
                        service.validate(session.session_id)

    def test_higher_format_version_is_previewed_but_never_restorable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self._archive(root / "future.zip", format_version=2)
            service = self._service(root)
            session = self._upload(service, payload)
            preview = service.validate(session.session_id)

            self.assertFalse(preview.restorable)
            self.assertEqual(preview.format_version, 2)
            self.assertEqual(preview.warnings, ("user_config_restore_version_unsupported",))

    def test_cancel_expiry_and_interrupted_startup_remove_only_owned_files(self) -> None:
        clock = MutableClock()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self._service(root, clock=clock, ttl_seconds=10)
            session = service.create("backup.zip", 100)
            unrelated = service.root / "keep.txt"
            unrelated.write_text("keep", encoding="utf-8")
            self.assertTrue(service.cancel(session.session_id))
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep")

            expiring = service.create("backup.zip", 100)
            clock.advance(11)
            self.assertEqual(service.cleanup_expired(), 1)
            self.assertIsNone(service.get_snapshot(expiring.session_id))

            interrupted_id = "a" * 32
            (service.root / f"{interrupted_id}.json").write_text(
                json.dumps(
                    {
                        "session_id": interrupted_id,
                        "filename": "backup.zip",
                        "size_bytes": 100,
                        "uploaded_bytes": 10,
                        "status": "uploading",
                        "created_at": "2026-08-21T12:00:00Z",
                        "updated_at": "2026-08-21T12:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            recovered = self._service(
                root,
                clock=clock,
                ttl_seconds=10,
                recover_on_init=False,
            )
            recovered.recover_startup()
            snapshot = recovered.get_snapshot(interrupted_id)
            self.assertIsNotNone(snapshot)
            self.assertEqual(snapshot.session.status, "interrupted")

    def test_incremental_chip_restore_deduplicates_colors_and_creates_snippet_copy(self) -> None:
        from tests.test_user_config_backup_components import (
            UserConfigBackupComponentTests,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            planner, stores = UserConfigBackupComponentTests()._planner(root)
            stores["color_settings"].write(  # type: ignore[attr-defined]
                {
                    "favorites": [{"name": "Current", "hex": "#457B66"}],
                    "recent_colors": ["#111111"],
                    "recent_limit": 6,
                }
            )
            stores["prompt_snippet_settings"].create(  # type: ignore[attr-defined]
                {
                    "tag": "portrait",
                    "title": "Current",
                    "content": "current content",
                    "category": "常用",
                }
            )
            members = {
                "chips/colors.json": json.dumps(
                    {
                        "version": 1,
                        "favorites": [
                            {"name": "Imported", "hex": "#457B66"},
                            {"name": "New", "hex": "#ABCDEF"},
                        ],
                        "recent_colors": ["#222222"],
                        "recent_limit": 6,
                    }
                ).encode(),
                "chips/prompt-snippets.json": json.dumps(
                    {
                        "version": 1,
                        "snippets": [
                            {
                                "id": "imported",
                                "tag": "portrait",
                                "title": "Imported",
                                "content": "different content",
                                "category": "常用",
                                "order": 10,
                                "created_at": "2026-08-21T00:00:00Z",
                                "updated_at": "2026-08-21T00:00:00Z",
                            }
                        ],
                    }
                ).encode(),
            }
            payload = self._archive(root / "chips.zip", members=members)
            from codex_image.webui.user_config_backup_import import (
                UserConfigBackupImportService,
            )

            service = UserConfigBackupImportService(
                planner,
                root / "imports",
                min_free_bytes=0,
                free_ratio=0,
            )
            session = self._upload(service, payload)
            preview = service.validate(session.session_id)
            result = service.restore(
                session.session_id,
                sections=("chips",),
                mode="incremental",
                archive_sha256=preview.archive_sha256,
                preview_revision=preview.preview_revision,
                confirm_replace=False,
            )

            colors = stores["color_settings"].read()  # type: ignore[attr-defined]
            snippets = stores["prompt_snippet_settings"].read()["snippets"]  # type: ignore[attr-defined]
            self.assertEqual(colors["favorites"][0]["name"], "Current")
            self.assertIn("#ABCDEF", [item["hex"] for item in colors["favorites"]])
            self.assertEqual(len(snippets), 2)
            self.assertNotEqual(snippets[0]["tag"], snippets[1]["tag"])
            self.assertEqual(result.section_stats["chips"].recovery_copies, 1)

    def test_preview_reports_current_groups_and_blocks_empty_replacement(self) -> None:
        from tests.test_user_config_backup_components import (
            UserConfigBackupComponentTests,
        )
        from codex_image.webui.user_config_backup_import import (
            UserConfigBackupImportService,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            components = UserConfigBackupComponentTests()
            planner, stores = components._planner(root)
            components._populate(root, stores)
            members = {
                "chips/colors.json": json.dumps(
                    {
                        "version": 1,
                        "favorites": [{"name": "Archive", "hex": "#FFFFFF"}],
                        "recent_colors": [],
                        "recent_limit": 6,
                    }
                ).encode(),
                "chips/prompt-snippets.json": b'{"version":1,"snippets":[]}',
                "gallery/categories.json": b"[]",
                "templates/prompt-templates.json": (
                    b'{"version":1,"categories":[],"templates":[]}'
                ),
            }
            payload = self._archive(root / "empty-groups.zip", members=members)
            service = UserConfigBackupImportService(
                planner,
                root / "imports",
                min_free_bytes=0,
                free_ratio=0,
            )
            session = self._upload(service, payload)
            preview = service.validate(session.session_id)
            by_section = {item.section: item for item in preview.sections}

            self.assertEqual(by_section["chips"].replace_existing_count, 4)
            self.assertEqual(
                [
                    (group.group, group.archive_count, group.current_count)
                    for group in by_section["chips"].groups
                ],
                [("colors", 1, 3), ("prompt_snippets", 0, 1)],
            )
            self.assertEqual(by_section["gallery"].replace_existing_count, 1)
            self.assertEqual(
                [
                    (group.group, group.archive_count, group.current_count)
                    for group in by_section["gallery"].groups
                ],
                [("gallery_items", 0, 1)],
            )
            self.assertEqual(by_section["templates"].replace_existing_count, 5)
            self.assertEqual(
                [
                    (group.group, group.archive_count, group.current_count)
                    for group in by_section["templates"].groups
                ],
                [("prompt_templates", 0, 4)],
            )

            original_colors = stores["color_settings"].path.read_bytes()  # type: ignore[attr-defined]
            original_snippets = stores["prompt_snippet_settings"].path.read_bytes()  # type: ignore[attr-defined]
            original_templates = stores["prompt_template_settings"].path.read_bytes()  # type: ignore[attr-defined]
            gallery_item = stores["gallery_storage"].snapshot().items[0]  # type: ignore[attr-defined]

            with self.assertRaisesRegex(
                ValueError,
                "^user_config_restore_empty_replace_blocked$",
            ):
                service.restore(
                    session.session_id,
                    sections=("chips", "gallery", "templates"),
                    mode="replace",
                    archive_sha256=preview.archive_sha256,
                    preview_revision=preview.preview_revision,
                    confirm_replace=True,
                )

            self.assertEqual(
                stores["color_settings"].path.read_bytes(),  # type: ignore[attr-defined]
                original_colors,
            )
            self.assertEqual(
                stores["prompt_snippet_settings"].path.read_bytes(),  # type: ignore[attr-defined]
                original_snippets,
            )
            self.assertEqual(
                stores["prompt_template_settings"].path.read_bytes(),  # type: ignore[attr-defined]
                original_templates,
            )
            self.assertTrue(gallery_item.image_path.is_file())

    def test_replace_requires_confirmation_and_failed_apply_rolls_back(self) -> None:
        from unittest.mock import patch

        from tests.test_user_config_backup_components import (
            UserConfigBackupComponentTests,
        )
        from codex_image.webui.user_config_backup_import import (
            UserConfigBackupImportService,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            planner, stores = UserConfigBackupComponentTests()._planner(root)
            stores["color_settings"].write(  # type: ignore[attr-defined]
                {
                    "favorites": [{"name": "Current", "hex": "#111111"}],
                    "recent_colors": [],
                    "recent_limit": 6,
                }
            )
            original = stores["color_settings"].path.read_bytes()  # type: ignore[attr-defined]
            members = {
                "chips/colors.json": b'{"version":1,"favorites":[{"name":"Imported","hex":"#FFFFFF"}],"recent_colors":[],"recent_limit":6}',
                "chips/prompt-snippets.json": b'{"version":1,"snippets":[]}',
            }
            payload = self._archive(root / "replace.zip", members=members)
            service = UserConfigBackupImportService(
                planner,
                root / "imports",
                min_free_bytes=0,
                free_ratio=0,
            )
            session = self._upload(service, payload)
            preview = service.validate(session.session_id)

            with self.assertRaisesRegex(ValueError, "confirm_replace"):
                service.restore(
                    session.session_id,
                    sections=("chips",),
                    mode="replace",
                    archive_sha256=preview.archive_sha256,
                    preview_revision=preview.preview_revision,
                    confirm_replace=False,
                )

            with patch.object(
                stores["prompt_snippet_settings"],
                "write",
                side_effect=OSError("simulated private path"),
            ):
                with self.assertRaisesRegex(ValueError, "apply_failed"):
                    service.restore(
                        session.session_id,
                        sections=("chips",),
                        mode="replace",
                        archive_sha256=preview.archive_sha256,
                        preview_revision=preview.preview_revision,
                        confirm_replace=True,
                    )

            self.assertEqual(
                stores["color_settings"].path.read_bytes(),  # type: ignore[attr-defined]
                original,
            )

    def test_startup_journal_rolls_back_interrupted_restore(self) -> None:
        from tests.test_user_config_backup_components import (
            UserConfigBackupComponentTests,
        )
        from codex_image.webui.user_config_backup_import import (
            UserConfigBackupImportService,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            planner, stores = UserConfigBackupComponentTests()._planner(root)
            colors = stores["color_settings"]
            colors.write(  # type: ignore[attr-defined]
                {
                    "favorites": [{"name": "Before", "hex": "#111111"}],
                    "recent_colors": [],
                    "recent_limit": 6,
                }
            )
            original = colors.path.read_bytes()  # type: ignore[attr-defined]
            service = UserConfigBackupImportService(
                planner,
                root / "imports",
                min_free_bytes=0,
                free_ratio=0,
            )
            session_id = "d" * 32
            backups = service._capture_selected_json_backups(("chips",))
            service._write_rollback_journal(session_id, backups, {})
            colors.write(  # type: ignore[attr-defined]
                {
                    "favorites": [{"name": "Half-written", "hex": "#FFFFFF"}],
                    "recent_colors": [],
                    "recent_limit": 6,
                }
            )

            recovered = UserConfigBackupImportService(
                planner,
                root / "imports",
                min_free_bytes=0,
                free_ratio=0,
            )

            self.assertEqual(colors.path.read_bytes(), original)  # type: ignore[attr-defined]
            self.assertFalse((recovered.root / f"{session_id}.rollback").exists())

    def test_all_sections_round_trip_from_export_plan_into_empty_stores(self) -> None:
        from tests.test_user_config_backup_components import (
            UserConfigBackupComponentTests,
        )
        from tests.test_user_config_backup_export import DirectExecutor
        from codex_image.webui.user_config_backup_components import ClientPreferences
        from codex_image.webui.user_config_backup_export import (
            UserConfigBackupExportService,
        )
        from codex_image.webui.user_config_backup_import import (
            UserConfigBackupImportService,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            helper = UserConfigBackupComponentTests()
            source_planner, source_stores = helper._planner(root / "source")
            helper._populate(root / "source", source_stores)
            export = UserConfigBackupExportService(
                source_planner,
                root / "exports",
                executor=DirectExecutor(),
                min_free_bytes=0,
                free_ratio=0,
            )
            export_job = export.create(
                ("chips", "gallery", "templates", "settings"),
                False,
                ClientPreferences("dark", True, False),
            )
            archive_path = export.download_path(export_job.job_id)
            archive = archive_path.read_bytes()

            target_planner, target_stores = helper._planner(root / "target")
            restore = UserConfigBackupImportService(
                target_planner,
                root / "imports",
                min_free_bytes=0,
                free_ratio=0,
            )
            session = self._upload(restore, archive)
            preview = restore.validate(session.session_id)
            result = restore.restore(
                session.session_id,
                sections=("chips", "gallery", "templates", "settings"),
                mode="incremental",
                archive_sha256=preview.archive_sha256,
                preview_revision=preview.preview_revision,
                confirm_replace=False,
            )

            self.assertEqual(result.status, "restored")
            self.assertTrue(target_stores["gallery_storage"].list_items())  # type: ignore[attr-defined]
            templates = target_stores["prompt_template_settings"].read()["templates"]  # type: ignore[attr-defined]
            self.assertEqual(len(templates), 4)
            self.assertTrue(
                any(
                    str(item.get("thumbnail_url", "")).startswith(
                        "/api/prompt-template-assets/"
                    )
                    for item in templates
                )
            )
            self.assertEqual(result.client_preferences.theme, "dark")


if __name__ == "__main__":
    unittest.main()
