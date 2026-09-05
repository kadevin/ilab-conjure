from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile


class DirectExecutor:
    def submit(self, function, *args, **kwargs):
        function(*args, **kwargs)
        return None


class DeferredExecutor:
    def __init__(self) -> None:
        self.pending = []

    def submit(self, function, *args, **kwargs):
        self.pending.append((function, args, kwargs))
        return None

    def run(self) -> None:
        function, args, kwargs = self.pending.pop(0)
        function(*args, **kwargs)


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


@dataclass(frozen=True)
class DiskUsage:
    total: int
    used: int
    free: int


class FakePlanner:
    def __init__(self, root: Path, *, mutate_after_plan: bool = False) -> None:
        self.source = root / "source.png"
        self.source.write_bytes(b"source-file")
        self.mutate_after_plan = mutate_after_plan

    def plan(self, sections, *, include_api_keys, client_preferences):
        from codex_image.webui.user_config_backup_components import (
            FileIdentity,
            PlannedUserConfigMember,
            UserConfigBackupPlan,
        )
        from codex_image.webui.user_config_backup_format import (
            USER_CONFIG_BACKUP_FORMAT,
            USER_CONFIG_BACKUP_FORMAT_VERSION,
            UserConfigBackupManifest,
            UserConfigBackupMember,
        )

        inline = b'{"version": 1}\n'
        source_data = self.source.read_bytes()
        source_stat = self.source.stat()
        source_digest = hashlib.sha256(source_data).hexdigest()
        entries = (
            UserConfigBackupMember(
                "chips",
                "chips/colors.json",
                len(inline),
                hashlib.sha256(inline).hexdigest(),
            ),
            UserConfigBackupMember(
                "gallery",
                "gallery/items/item-1/image.png",
                len(source_data),
                source_digest,
            ),
        )
        plan = UserConfigBackupPlan(
            manifest=UserConfigBackupManifest(
                USER_CONFIG_BACKUP_FORMAT,
                USER_CONFIG_BACKUP_FORMAT_VERSION,
                "test",
                "2026-08-21T12:00:00Z",
                ("chips", "gallery"),
                False,
                entries,
            ),
            members=(
                PlannedUserConfigMember(entries[0], inline, None, None),
                PlannedUserConfigMember(
                    entries[1],
                    None,
                    self.source,
                    FileIdentity(
                        len(source_data),
                        source_stat.st_mtime_ns,
                        source_stat.st_dev,
                        source_stat.st_ino,
                        source_digest,
                    ),
                ),
            ),
            warnings=(),
        )
        if self.mutate_after_plan:
            self.source.write_bytes(b"changed-source-file")
        return plan

    def summary(self):
        return ()


class UserConfigBackupExportTests(unittest.TestCase):
    def _service(self, root: Path, planner, **overrides):
        from codex_image.webui.user_config_backup_export import (
            UserConfigBackupExportService,
        )

        options = {
            "executor": DirectExecutor(),
            "clock": MutableClock(),
            "disk_usage": lambda _path: DiskUsage(
                total=10_000_000,
                used=0,
                free=10_000_000,
            ),
            "min_free_bytes": 100,
            "free_ratio": 0.10,
            "ttl_seconds": 24 * 60 * 60,
            "chunk_bytes": 3,
        }
        options.update(overrides)
        return UserConfigBackupExportService(
            planner,
            root / "private-user-config-backups",
            **options,
        )

    def test_export_lifecycle_progress_private_archive_and_manifest_last(self) -> None:
        from codex_image.webui.user_config_backup_components import ClientPreferences
        from codex_image.webui.user_config_backup_format import parse_user_config_manifest

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self._service(root, FakePlanner(root))
            observed = []
            service._progress_observer = observed.append

            job = service.create(
                ("chips", "gallery"),
                False,
                None,
            )

            self.assertEqual(job.status, "ready")
            self.assertEqual(
                [item.status for item in observed],
                ["planning", "packing", "packing", "packing", "ready"],
            )
            progress = [(item.completed_members, item.completed_bytes) for item in observed]
            self.assertEqual(progress, sorted(progress))
            ready_path = service.root / f"{job.job_id}.zip"
            self.assertEqual(ready_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(service.root.stat().st_mode & 0o777, 0o700)
            with zipfile.ZipFile(ready_path) as archive:
                self.assertEqual(archive.namelist()[-1], "manifest.json")
                manifest = parse_user_config_manifest(archive.read("manifest.json"))
            self.assertEqual(manifest.members[0].path, "chips/colors.json")
            self.assertFalse(any(service.root.glob("*.partial")))

    def test_only_one_active_export_and_queued_job_can_cancel(self) -> None:
        executor = DeferredExecutor()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self._service(root, FakePlanner(root), executor=executor)
            first = service.create(("chips", "gallery"), False, None)

            with self.assertRaisesRegex(ValueError, "active"):
                service.create(("chips",), False, None)
            self.assertTrue(service.cancel(first.job_id))
            executor.run()

            cancelled = service.get(first.job_id)
            self.assertIsNotNone(cancelled)
            self.assertEqual(cancelled.status, "cancelled")
            self.assertFalse(any(service.root.glob("*.zip")))

    def test_source_mutation_and_insufficient_space_fail_with_stable_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            changed = self._service(root, FakePlanner(root, mutate_after_plan=True))
            changed_job = changed.create(("chips", "gallery"), False, None)
            self.assertEqual(changed_job.status, "failed")
            self.assertEqual(changed_job.error_code, "user_config_backup_source_changed")
            self.assertNotIn(str(root), json.dumps(changed_job.__dict__))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            full = self._service(
                root,
                FakePlanner(root),
                disk_usage=lambda _path: DiskUsage(total=100, used=99, free=1),
            )
            full_job = full.create(("chips", "gallery"), False, None)
            self.assertEqual(full_job.status, "failed")
            self.assertEqual(
                full_job.error_code,
                "user_config_backup_insufficient_space",
            )

    def test_ready_archive_can_be_downloaded_repeatedly_until_expiry(self) -> None:
        clock = MutableClock()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = self._service(root, FakePlanner(root), clock=clock)
            first = service.create(("chips", "gallery"), False, None)
            first_download = service.download_path(first.job_id)
            second_download = service.download_path(first.job_id)

            self.assertEqual(first_download, second_download)
            self.assertTrue(first_download.is_file())
            self.assertEqual(first_download.suffix, ".zip")
            self.assertEqual(first_download.read_bytes(), second_download.read_bytes())
            self.assertEqual(service.get(first.job_id).status, "ready")

            clock.advance(24 * 60 * 60 + 1)
            self.assertEqual(service.cleanup_expired(), 1)
            self.assertFalse(first_download.exists())
            self.assertIsNone(service.get(first.job_id))

    def test_startup_recovery_marks_active_status_interrupted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            private_root = root / "private-user-config-backups"
            private_root.mkdir()
            os.chmod(private_root, 0o700)
            job_id = "a" * 32
            status_path = private_root / f"{job_id}.json"
            status_path.write_text(
                json.dumps(
                    {
                        "job_id": job_id,
                        "status": "packing",
                        "created_at": "2026-08-21T12:00:00Z",
                        "updated_at": "2026-08-21T12:00:00Z",
                        "sections": ["chips"],
                    }
                ),
                encoding="utf-8",
            )
            service = self._service(
                root,
                FakePlanner(root),
                recover_on_init=False,
            )
            service.recover_startup()

            recovered = service.get(job_id)
            self.assertIsNotNone(recovered)
            self.assertEqual(recovered.status, "interrupted")
            self.assertEqual(
                recovered.error_code,
                "user_config_backup_interrupted",
            )


if __name__ == "__main__":
    unittest.main()
