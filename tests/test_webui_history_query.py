from __future__ import annotations

from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from tests.helpers import history_storage



class HistoryQueryTests(unittest.TestCase):

    def test_refresh_mounted_summaries_is_bounded_and_preserves_history_shape(self) -> None:
        from contextlib import chdir
        from fastapi.testclient import TestClient
        from codex_image.webui.app import create_app

        with TemporaryDirectory() as tmp, chdir(tmp):
            root = Path(tmp)
            app = create_app(
                output_root=root / "outputs", api_settings_path=root / "api.json",
                auth_settings_path=root / "auth.json", webui_settings_path=root / "webui.json",
                auth_checker=lambda: True, auto_start_queue=False,
            )
            storage = app.state.storage
            for number in range(3):
                self._write_task(storage, f"task-{number}", f"2026-10-13T10:0{number}:00Z")
            storage.mutate_metadata("task-0", lambda task: task.update(status="failed", failed_count=1))
            client = TestClient(app)
            page = client.get("/api/task-history/tasks").json()["tasks"]
            refreshed = client.post("/api/task-history/tasks/refresh", json={
                "task_ids": ["task-0", "missing", "task-2", "task-0"],
            })
            self.assertEqual(refreshed.status_code, 200)
            tasks = refreshed.json()["tasks"]
            self.assertEqual([task["task_id"] for task in tasks], ["task-0", "task-2"])
            by_id = {task["task_id"]: task for task in page}
            self.assertEqual(tasks, [by_id["task-0"], by_id["task-2"]])
            self.assertEqual(tasks[0]["status"], "failed")
            for ids in ([], ["../invalid"], [f"task-{n}" for n in range(301)]):
                self.assertEqual(client.post("/api/task-history/tasks/refresh", json={"task_ids": ids}).status_code, 422)
            self.assertEqual(client.post("/api/task-history/tasks/refresh", json={"task_ids": [f"task-{n}" for n in range(300)]}).status_code, 200)

    def _write_task(
        self,
        storage,
        task_id: str,
        created_at: str,
        *,
        prompt: str = "",
        archived: bool = False,
    ) -> None:
        metadata = {
            "task_id": task_id,
            "created_at": created_at,
            "updated_at": created_at,
            "status": "completed",
            "mode": "generate",
            "prompt": prompt or task_id,
            "params": {
                "size": "1024x1024",
                "quality": "high",
                "ratio": "1:1",
                "orientation": "square",
                "prompt_fidelity": "strict",
            },
            "generated_count": 1,
            "failed_count": 0,
            "total_count": 1,
        }
        if archived:
            metadata["archived_at"] = "2026-07-27T00:00:00+00:00"
        storage.write_metadata(task_id, metadata)

    def _organized_storage(self, root: Path):
        storage = history_storage(root)
        self._write_task(
            storage,
            "task-a",
            "2026-07-26T10:00:00+00:00",
            prompt="red landscape",
        )
        self._write_task(
            storage,
            "task-b",
            "2026-07-26T09:00:00+00:00",
            prompt="blue portrait",
        )
        self._write_task(
            storage,
            "task-c",
            "2026-07-25T08:00:00+00:00",
            prompt="green product",
            archived=True,
        )
        warm = storage.history_organizer.create_tag("暖色")
        selected = storage.history_organizer.create_tag("成片")
        storage.organize_history_tasks(
            ["task-a"],
            favorite=True,
            add_tag_ids=[warm.tag_id, selected.tag_id],
            remove_tag_ids=[],
        )
        storage.organize_history_tasks(
            ["task-b"],
            favorite=False,
            add_tag_ids=[warm.tag_id],
            remove_tag_ids=[],
        )
        storage.organize_history_tasks(
            ["task-c"],
            favorite=True,
            add_tag_ids=[],
            remove_tag_ids=[],
        )
        storage.history_organizer.organize(
            ["orphan-task"],
            favorite=True,
            add_tag_ids=[selected.tag_id],
        )
        return storage, warm, selected

    def test_history_query_filters_favorite_tags_and_untagged(self) -> None:
        with TemporaryDirectory() as tmp:
            storage, warm, selected = self._organized_storage(Path(tmp))

            favorites = storage.query_task_history(
                limit=10,
                favorite=True,
            )
            warm_tasks = storage.query_task_history(
                limit=10,
                tag_ids=[warm.tag_id],
            )
            both = storage.query_task_history(
                limit=10,
                tag_ids=[warm.tag_id, selected.tag_id],
            )
            untagged = storage.query_task_history(
                limit=10,
                untagged=True,
            )

        self.assertEqual(
            [task["task_id"] for task in favorites["tasks"]],
            ["task-a", "task-c"],
        )
        self.assertEqual(
            [task["task_id"] for task in warm_tasks["tasks"]],
            ["task-a", "task-b"],
        )
        self.assertEqual(
            [task["task_id"] for task in both["tasks"]],
            ["task-a"],
        )
        self.assertEqual(
            [task["task_id"] for task in untagged["tasks"]],
            ["task-c"],
        )

    def test_history_query_rejects_untagged_with_specific_tags(self) -> None:
        with TemporaryDirectory() as tmp:
            storage, warm, _selected = self._organized_storage(Path(tmp))

            with self.assertRaisesRegex(
                ValueError,
                "untagged cannot be combined",
            ):
                storage.query_task_history(
                    limit=10,
                    tag_ids=[warm.tag_id],
                    untagged=True,
                )

    def test_history_query_combines_organization_with_existing_filters(self) -> None:
        with TemporaryDirectory() as tmp:
            storage, warm, _selected = self._organized_storage(Path(tmp))

            result = storage.query_task_history(
                limit=10,
                q="red",
                month="2026-07",
                archived=False,
                favorite=True,
                tag_ids=[warm.tag_id],
            )

        self.assertEqual(
            [task["task_id"] for task in result["tasks"]],
            ["task-a"],
        )

    def test_history_page_rows_include_favorite_and_all_sorted_tags(self) -> None:
        with TemporaryDirectory() as tmp:
            storage, _warm, _selected = self._organized_storage(Path(tmp))

            result = storage.query_task_history(limit=1)
            task = result["tasks"][0]

        self.assertEqual(task["task_id"], "task-a")
        self.assertTrue(task["favorite"])
        self.assertEqual(
            [tag["name"] for tag in task["tags"]],
            ["成片", "暖色"],
        )

    def test_history_summary_counts_only_indexed_tasks(self) -> None:
        with TemporaryDirectory() as tmp:
            storage, warm, selected = self._organized_storage(Path(tmp))

            summary = storage.task_history_summary()
            counts = {
                item["tag_id"]: item["count"]
                for item in summary["tags"]
            }

        self.assertEqual(summary["favorite_total"], 2)
        self.assertEqual(summary["untagged_total"], 1)
        self.assertEqual(counts[warm.tag_id], 2)
        self.assertEqual(counts[selected.tag_id], 1)

    def test_history_tag_filter_keeps_forward_and_reverse_cursors_stable(self) -> None:
        from codex_image.webui.task_index import _encode_cursor

        with TemporaryDirectory() as tmp:
            storage, warm, _selected = self._organized_storage(Path(tmp))

            first = storage.query_task_history(
                limit=1,
                tag_ids=[warm.tag_id],
            )
            second = storage.query_task_history(
                limit=1,
                cursor=first["next_cursor"],
                tag_ids=[warm.tag_id],
            )
            previous = storage.query_task_history(
                limit=1,
                cursor=_encode_cursor(
                    "2026-07-26T09:00:00+00:00",
                    "task-b",
                ),
                direction="previous",
                tag_ids=[warm.tag_id],
            )

        self.assertEqual(
            [task["task_id"] for task in first["tasks"]],
            ["task-a"],
        )
        self.assertEqual(
            [task["task_id"] for task in second["tasks"]],
            ["task-b"],
        )
        self.assertEqual(
            [task["task_id"] for task in previous["tasks"]],
            ["task-a"],
        )

    def test_history_page_batches_organization_queries(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = history_storage(root)
            task_ids = []
            for index in range(100):
                task_id = f"task-{index:03d}"
                task_ids.append(task_id)
                self._write_task(
                    storage,
                    task_id,
                    f"2026-07-26T10:{index:02d}:00+00:00",
                )
            tag = storage.history_organizer.create_tag("批量")
            storage.organize_history_tasks(
                task_ids[:50],
                favorite=True,
                add_tag_ids=[tag.tag_id],
                remove_tag_ids=[],
            )
            statements: list[str] = []
            original_connect = storage.history_query._connect

            def traced_connect():
                connection = original_connect()
                connection.set_trace_callback(statements.append)
                return connection

            storage.history_query._connect = traced_connect
            result = storage.query_task_history(limit=100)

        selects = [
            statement
            for statement in statements
            if statement.lstrip().lower().startswith("select")
        ]
        self.assertEqual(len(result["tasks"]), 100)
        self.assertEqual(len(selects), 3)
        self.assertEqual(
            sum(
                "from history_org.task_favorites"
                in statement.lower()
                for statement in selects
            ),
            1,
        )
        self.assertEqual(
            sum(
                "from history_org.task_tags"
                in statement.lower()
                for statement in selects
            ),
            1,
        )

    def test_history_query_plan_uses_cursor_and_organization_indexes_at_100k(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = history_storage(root)
            with closing(
                storage.task_index._connect()
            ) as connection:
                with connection:
                    connection.executemany(
                        """
                        insert into task_index(
                            task_id, created_at, updated_at, status,
                            prompt, summary_json, schema_version
                        )
                        values(?, ?, ?, 'completed', '', '{}', 9)
                        """,
                        (
                            (
                                f"task-{index:06d}",
                                f"{index:020d}",
                                f"{index:020d}",
                            )
                            for index in range(100_000)
                        ),
                    )
            tag = storage.history_organizer.create_tag("大库")
            storage.history_organizer.organize(
                ["task-099999"],
                favorite=True,
                add_tag_ids=[tag.tag_id],
            )
            with closing(
                storage.history_query._connect()
            ) as connection:
                rows = connection.execute(
                    """
                    explain query plan
                    select task_id
                    from task_index
                    where exists (
                        select 1
                        from history_org.task_favorites f
                        where f.task_id = task_index.task_id
                    )
                    and exists (
                        select 1
                        from history_org.task_tags tt
                        where tt.task_id = task_index.task_id
                          and tt.tag_id = ?
                    )
                    order by created_at desc, task_id desc
                    limit 101
                    """,
                    (tag.tag_id,),
                ).fetchall()
                summary_rows = connection.execute(
                    """
                    explain query plan
                    select t.tag_id, count(i.task_id)
                    from history_org.tags t
                    left join history_org.task_tags tt
                        on tt.tag_id = t.tag_id
                    left join task_index i
                        on i.task_id = tt.task_id
                    group by t.tag_id
                    """
                ).fetchall()

        details = "\n".join(str(row["detail"]) for row in rows)
        summary_details = "\n".join(
            str(row["detail"]) for row in summary_rows
        )
        self.assertIn("idx_task_index_history_cursor", details)
        self.assertIn("sqlite_autoindex_task_favorites_1", details)
        self.assertIn("sqlite_autoindex_task_tags_1", details)
        self.assertIn("task_tags_by_tag", summary_details)


if __name__ == "__main__":
    unittest.main()
