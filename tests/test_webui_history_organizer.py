from __future__ import annotations

from contextlib import closing
import importlib.util
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
from tests.helpers import history_storage



class HistoryOrganizerTests(unittest.TestCase):
    def _module(self):
        module_name = "codex_image.webui.history_organizer"
        self.assertIsNotNone(
            importlib.util.find_spec(module_name),
            "history organizer module must exist",
        )
        from codex_image.webui import history_organizer

        return history_organizer

    def _organizer(self, root: Path):
        module = self._module()
        return module.HistoryOrganizer(root / "webui-history-organizer.db")

    def test_schema_is_initialized_with_version_and_relationship_indexes(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "webui-history-organizer.db"
            self._organizer(Path(tmp))

            with closing(sqlite3.connect(path)) as connection:
                version = connection.execute(
                    "select value from history_meta where key = 'schema_version'"
                ).fetchone()
                tables = {
                    row[0]
                    for row in connection.execute(
                        "select name from sqlite_master where type = 'table'"
                    )
                }
                indexes = {
                    row[0]
                    for row in connection.execute(
                        "select name from sqlite_master where type = 'index'"
                    )
                }

        self.assertEqual(version, ("1",))
        self.assertTrue(
            {"history_meta", "tags", "task_tags", "task_favorites"}.issubset(
                tables
            )
        )
        self.assertIn("task_tags_by_tag", indexes)
        self.assertIn("task_favorites_by_time", indexes)

    def test_tag_names_are_trimmed_normalized_unique_and_length_limited(self) -> None:
        module = self._module()
        with TemporaryDirectory() as tmp:
            organizer = self._organizer(Path(tmp))
            created = organizer.create_tag("  Ａ  ")

            with self.assertRaises(module.TagNameConflictError):
                organizer.create_tag("a")
            with self.assertRaises(module.InvalidTagNameError):
                organizer.create_tag(" ")
            with self.assertRaises(module.InvalidTagNameError):
                organizer.create_tag("x" * 41)

        self.assertEqual(created.name, "Ａ")
        self.assertEqual(len(created.tag_id), 32)

    def test_rename_keeps_id_and_rejects_normalized_conflict(self) -> None:
        module = self._module()
        with TemporaryDirectory() as tmp:
            organizer = self._organizer(Path(tmp))
            first = organizer.create_tag("风景")
            organizer.create_tag("人物")

            renamed = organizer.rename_tag(first.tag_id, "  自然  ")
            with self.assertRaises(module.TagNameConflictError):
                organizer.rename_tag(first.tag_id, "人物")
            with self.assertRaises(module.TagNotFoundError):
                organizer.rename_tag("missing", "不存在")

        self.assertEqual(renamed.tag_id, first.tag_id)
        self.assertEqual(renamed.name, "自然")

    def test_organize_is_idempotent_and_preserves_unmentioned_tags(self) -> None:
        with TemporaryDirectory() as tmp:
            organizer = self._organizer(Path(tmp))
            landscape = organizer.create_tag("风景")
            favorite = organizer.create_tag("成片")

            organizer.organize(
                ["task-b", "task-a", "task-a"],
                favorite=True,
                add_tag_ids=[landscape.tag_id, favorite.tag_id],
            )
            result = organizer.organize(
                ["task-a"],
                favorite=True,
                add_tag_ids=[landscape.tag_id],
                remove_tag_ids=[favorite.tag_id],
            )
            repeated = organizer.organize(
                ["task-a"],
                favorite=True,
                add_tag_ids=[landscape.tag_id],
                remove_tag_ids=[favorite.tag_id],
            )

        self.assertTrue(result["task-a"].favorite)
        self.assertEqual(
            [tag.tag_id for tag in result["task-a"].tags],
            [landscape.tag_id],
        )
        self.assertEqual(result, repeated)

    def test_invalid_batch_rolls_back_favorite_and_tag_changes(self) -> None:
        module = self._module()
        with TemporaryDirectory() as tmp:
            organizer = self._organizer(Path(tmp))
            existing = organizer.create_tag("保留")

            with self.assertRaises(module.TagNotFoundError):
                organizer.organize(
                    ["task-a", "task-b"],
                    favorite=True,
                    add_tag_ids=[existing.tag_id, "missing"],
                )
            snapshots = organizer.organizations_for_tasks(["task-a", "task-b"])

            with self.assertRaises(ValueError):
                organizer.organize(
                    ["task-a"],
                    add_tag_ids=[existing.tag_id],
                    remove_tag_ids=[existing.tag_id],
                )
            after_overlap = organizer.organizations_for_tasks(["task-a"])

        self.assertFalse(snapshots["task-a"].favorite)
        self.assertFalse(snapshots["task-b"].favorite)
        self.assertEqual(snapshots["task-a"].tags, ())
        self.assertEqual(snapshots["task-b"].tags, ())
        self.assertEqual(after_overlap["task-a"].tags, ())

    def test_cancel_favorite_and_remove_tag_are_idempotent(self) -> None:
        with TemporaryDirectory() as tmp:
            organizer = self._organizer(Path(tmp))
            tag = organizer.create_tag("待选")
            organizer.organize(
                ["task-a"],
                favorite=True,
                add_tag_ids=[tag.tag_id],
            )

            first = organizer.organize(
                ["task-a"],
                favorite=False,
                remove_tag_ids=[tag.tag_id],
            )
            second = organizer.organize(
                ["task-a"],
                favorite=False,
                remove_tag_ids=[tag.tag_id],
            )

        self.assertEqual(first, second)
        self.assertFalse(first["task-a"].favorite)
        self.assertEqual(first["task-a"].tags, ())

    def test_delete_tag_cascades_relationships_without_touching_other_tags(self) -> None:
        module = self._module()
        with TemporaryDirectory() as tmp:
            organizer = self._organizer(Path(tmp))
            removed = organizer.create_tag("删除")
            kept = organizer.create_tag("保留")
            organizer.organize(
                ["task-a", "task-b"],
                add_tag_ids=[removed.tag_id, kept.tag_id],
            )

            affected = organizer.delete_tag(removed.tag_id)
            snapshots = organizer.organizations_for_tasks(["task-a", "task-b"])
            with self.assertRaises(module.TagNotFoundError):
                organizer.delete_tag(removed.tag_id)

        self.assertEqual(affected, 2)
        for organization in snapshots.values():
            self.assertEqual(
                [tag.tag_id for tag in organization.tags],
                [kept.tag_id],
            )

    def test_delete_task_state_removes_only_that_tasks_relationships(self) -> None:
        with TemporaryDirectory() as tmp:
            organizer = self._organizer(Path(tmp))
            tag = organizer.create_tag("共用")
            organizer.organize(
                ["task-a", "task-b"],
                favorite=True,
                add_tag_ids=[tag.tag_id],
            )

            organizer.delete_task_state("task-a")
            snapshots = organizer.organizations_for_tasks(["task-a", "task-b"])

        self.assertFalse(snapshots["task-a"].favorite)
        self.assertEqual(snapshots["task-a"].tags, ())
        self.assertTrue(snapshots["task-b"].favorite)
        self.assertEqual(
            [item.tag_id for item in snapshots["task-b"].tags],
            [tag.tag_id],
        )

    def test_tags_and_task_snapshots_have_stable_normalized_name_order(self) -> None:
        with TemporaryDirectory() as tmp:
            organizer = self._organizer(Path(tmp))
            zebra = organizer.create_tag("zebra")
            alpha = organizer.create_tag("Alpha")
            organizer.organize(
                ["task-a"],
                add_tag_ids=[zebra.tag_id, alpha.tag_id],
            )

            tags = organizer.list_tags()
            snapshot = organizer.organizations_for_tasks(["task-a"])["task-a"]

        self.assertEqual([tag.name for tag in tags], ["Alpha", "zebra"])
        self.assertEqual([tag.name for tag in snapshot.tags], ["Alpha", "zebra"])


class HistoryOrganizerTaskStorageTests(unittest.TestCase):

    def _write_task(self, storage, task_id: str) -> None:
        storage.write_metadata(
            task_id,
            {
                "task_id": task_id,
                "created_at": "2026-07-26T08:00:00+00:00",
                "updated_at": "2026-07-26T08:00:00+00:00",
                "status": "completed",
                "mode": "generate",
                "prompt": task_id,
            },
        )

    def test_task_index_checks_existing_task_ids_in_one_batch(self) -> None:
        with TemporaryDirectory() as tmp:
            storage = history_storage(Path(tmp))
            self._write_task(storage, "task-a")
            self._write_task(storage, "task-b")

            existing = storage.task_index.existing_task_ids(
                ["task-b", "missing", "task-a", "task-a"]
            )

        self.assertEqual(existing, {"task-a", "task-b"})

    def test_storage_rejects_missing_task_before_any_organization_write(self) -> None:
        from codex_image.webui.storage import HistoryTaskNotFoundError

        with TemporaryDirectory() as tmp:
            storage = history_storage(Path(tmp))
            self._write_task(storage, "task-a")
            tag = storage.history_organizer.create_tag("有效")

            with self.assertRaises(HistoryTaskNotFoundError) as raised:
                storage.organize_history_tasks(
                    ["task-a", "missing"],
                    favorite=True,
                    add_tag_ids=[tag.tag_id],
                    remove_tag_ids=[],
                )
            snapshot = storage.history_organizations(["task-a"])["task-a"]

        self.assertEqual(raised.exception.task_ids, ("missing",))
        self.assertFalse(snapshot.favorite)
        self.assertEqual(snapshot.tags, ())

    def test_storage_limits_history_organization_to_three_hundred_tasks(self) -> None:
        with TemporaryDirectory() as tmp:
            storage = history_storage(Path(tmp))

            with self.assertRaisesRegex(
                ValueError,
                "At most 300 tasks can be organized at once",
            ):
                storage.organize_history_tasks(
                    [f"task-{index:03d}" for index in range(301)],
                    favorite=True,
                    add_tag_ids=[],
                    remove_tag_ids=[],
                )

    def test_delete_task_removes_history_organization(self) -> None:
        with TemporaryDirectory() as tmp:
            storage = history_storage(Path(tmp))
            self._write_task(storage, "task-a")
            tag = storage.history_organizer.create_tag("待清理")
            storage.organize_history_tasks(
                ["task-a"],
                favorite=True,
                add_tag_ids=[tag.tag_id],
                remove_tag_ids=[],
            )

            storage.delete_task("task-a")
            snapshot = storage.history_organizations(["task-a"])["task-a"]

        self.assertFalse(snapshot.favorite)
        self.assertEqual(snapshot.tags, ())

    def test_rebuilding_task_index_preserves_history_organization(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = history_storage(root)
            self._write_task(storage, "task-a")
            tag = storage.history_organizer.create_tag("长期")
            storage.organize_history_tasks(
                ["task-a"],
                favorite=True,
                add_tag_ids=[tag.tag_id],
                remove_tag_ids=[],
            )
            index_path = storage.task_index.path
            index_path.unlink()

            restarted = history_storage(root)
            restarted.rebuild_task_index()
            snapshot = restarted.history_organizations(["task-a"])["task-a"]

        self.assertTrue(snapshot.favorite)
        self.assertEqual([item.tag_id for item in snapshot.tags], [tag.tag_id])

    def test_organize_validation_and_delete_share_one_lock(self) -> None:
        with TemporaryDirectory() as tmp:
            storage = history_storage(Path(tmp))
            self._write_task(storage, "task-a")
            tag = storage.history_organizer.create_tag("互斥")
            validation_started = threading.Event()
            allow_validation = threading.Event()
            organize_finished = threading.Event()
            delete_finished = threading.Event()
            failures: list[BaseException] = []
            original_existing = storage.task_index.existing_task_ids

            def blocking_existing(task_ids):
                validation_started.set()
                allow_validation.wait(timeout=2)
                return original_existing(task_ids)

            def organize() -> None:
                try:
                    storage.organize_history_tasks(
                        ["task-a"],
                        favorite=True,
                        add_tag_ids=[tag.tag_id],
                        remove_tag_ids=[],
                    )
                except BaseException as exc:
                    failures.append(exc)
                finally:
                    organize_finished.set()

            def delete() -> None:
                try:
                    storage.delete_task("task-a")
                except BaseException as exc:
                    failures.append(exc)
                finally:
                    delete_finished.set()

            with patch.object(
                storage.task_index,
                "existing_task_ids",
                side_effect=blocking_existing,
            ):
                organize_thread = threading.Thread(target=organize)
                delete_thread = threading.Thread(target=delete)
                organize_thread.start()
                self.assertTrue(validation_started.wait(timeout=1))
                delete_thread.start()
                self.assertFalse(delete_finished.wait(timeout=0.05))
                allow_validation.set()
                organize_thread.join(timeout=2)
                delete_thread.join(timeout=2)

            snapshot = storage.history_organizations(["task-a"])["task-a"]

        self.assertEqual(failures, [])
        self.assertTrue(organize_finished.is_set())
        self.assertTrue(delete_finished.is_set())
        self.assertFalse(snapshot.favorite)
        self.assertEqual(snapshot.tags, ())


if __name__ == "__main__":
    unittest.main()
