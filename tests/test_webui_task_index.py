from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from codex_image.webui.task_index import RATIO_OTHER_VALUE, SQLiteTaskIndex, _encode_cursor


class WebUITaskIndexTests(unittest.TestCase):
    def test_index_upserts_and_lists_newest_first(self) -> None:
        with TemporaryDirectory() as tmp:
            index = SQLiteTaskIndex(Path(tmp) / "tasks.db")
            index.upsert(
                {
                    "task_id": "old",
                    "created_at": "2026-05-09T10:00:00+00:00",
                    "updated_at": "2026-05-09T10:01:00+00:00",
                    "status": "completed",
                    "prompt": "old prompt",
                    "params": {"size": "1152x2048"},
                    "generated_count": 1,
                    "failed_count": 0,
                    "total_count": 1,
                    "request": {"input": [{"content": "large payload should not be indexed"}]},
                    "outputs": [{"index": 1, "status": "completed", "thumbnail_url": "/thumb-old.jpg"}],
                }
            )
            index.upsert(
                {
                    "task_id": "new",
                    "created_at": "2026-05-09T11:00:00+00:00",
                    "updated_at": "2026-05-09T11:01:00+00:00",
                    "status": "failed",
                    "prompt": "new prompt",
                    "params": {"size": "2160x3840"},
                    "generated_count": 0,
                    "failed_count": 1,
                    "total_count": 1,
                    "outputs": [],
                }
            )

            tasks = index.list_summaries()

        self.assertEqual([task["task_id"] for task in tasks], ["new", "old"])
        self.assertEqual(tasks[0]["params"]["size"], "2160x3840")
        self.assertNotIn("request", tasks[1])

    def test_index_deletes_task(self) -> None:
        with TemporaryDirectory() as tmp:
            index = SQLiteTaskIndex(Path(tmp) / "tasks.db")
            index.upsert({"task_id": "task-1", "created_at": "2026-05-09T10:00:00+00:00"})

            index.delete("task-1")

            self.assertEqual(index.list_summaries(), [])

    def test_history_query_paginates_filters_and_searches_lightweight_rows(self) -> None:
        with TemporaryDirectory() as tmp:
            index = SQLiteTaskIndex(Path(tmp) / "tasks.db")
            shared_time = "2026-05-10T10:00:00+00:00"
            index.upsert(
                {
                    "task_id": "task-b",
                    "created_at": shared_time,
                    "updated_at": shared_time,
                    "status": "completed",
                    "mode": "generate",
                    "prompt": "green portrait session with soft light",
                    "prompt_for_model": "expanded searchable portrait prompt",
                    "params": {
                        "size": "1152x2048",
                        "quality": "high",
                        "ratio": "9:16",
                        "orientation": "portrait",
                        "prompt_fidelity": "strict",
                    },
                    "output_urls": ["/outputs/task-b-image-1.png"],
                    "outputs": [{"index": 1, "status": "completed", "thumbnail_url": "/thumb-b.jpg"}],
                    "generated_count": 1,
                    "failed_count": 0,
                    "total_count": 1,
                    "api_provider_name": "qian",
                    "backend": "openai_images",
                }
            )
            index.upsert(
                {
                    "task_id": "task-a",
                    "created_at": shared_time,
                    "updated_at": shared_time,
                    "status": "failed",
                    "mode": "generate",
                    "prompt": "product packshot",
                    "params": {
                        "size": "1024x1024",
                        "quality": "low",
                        "ratio": "1:1",
                        "orientation": "square",
                        "prompt_fidelity": "original",
                    },
                    "failed_count": 1,
                    "total_count": 1,
                    "archived_at": "2026-05-11T00:00:00+00:00",
                }
            )
            index.upsert(
                {
                    "task_id": "task-old",
                    "created_at": "2026-04-09T10:00:00+00:00",
                    "updated_at": "2026-04-09T10:01:00+00:00",
                    "status": "completed",
                    "prompt": "older landscape",
                    "params": {
                        "size": "1536x864",
                        "quality": "auto",
                        "ratio": "16:9",
                        "orientation": "landscape",
                        "prompt_fidelity": "off",
                    },
                }
            )

            first_page = index.query_history(limit=1, month="2026-05")
            second_page = index.query_history(limit=2, month="2026-05", cursor=first_page["next_cursor"])
            visible = index.query_history(limit=10, month="2026-05", archived=False)
            searched = index.query_history(limit=10, q="searchable")
            searched_by_task_id = index.query_history(limit=10, q="task-b")
            archived = index.query_history(limit=10, archived=True)
            backend = index.query_history(limit=10, backend="openai_images")
            provider = index.query_history(limit=10, provider="qian")
            prompt_mode = index.query_history(limit=10, prompt_mode="strict")
            size = index.query_history(limit=10, size="1152x2048")
            quality = index.query_history(limit=10, quality="high")
            oldest = index.query_history(limit=2, sort="oldest")
            previous_newest = index.query_history(
                limit=1,
                month="2026-05",
                cursor=_encode_cursor(shared_time, "task-a"),
                direction="previous",
            )
            previous_oldest = index.query_history(
                limit=1,
                month="2026-05",
                sort="oldest",
                cursor=_encode_cursor(shared_time, "task-b"),
                direction="previous",
            )

        self.assertEqual([task["task_id"] for task in first_page["tasks"]], ["task-b"])
        self.assertEqual(first_page["tasks"][0]["thumbnail_url"], "/api/tasks/task-b/outputs/1/thumbnail")
        self.assertNotIn("outputs", first_page["tasks"][0])
        self.assertNotIn("prompt_for_model", first_page["tasks"][0])
        self.assertEqual([task["task_id"] for task in second_page["tasks"]], ["task-a"])
        self.assertIsNone(second_page["next_cursor"])
        self.assertEqual([task["task_id"] for task in visible["tasks"]], ["task-b"])
        self.assertEqual([task["task_id"] for task in searched["tasks"]], ["task-b"])
        self.assertEqual([task["task_id"] for task in searched_by_task_id["tasks"]], ["task-b"])
        self.assertEqual([task["task_id"] for task in archived["tasks"]], ["task-a"])
        self.assertEqual([task["task_id"] for task in backend["tasks"]], ["task-b"])
        self.assertEqual([task["task_id"] for task in provider["tasks"]], ["task-b"])
        self.assertEqual([task["task_id"] for task in prompt_mode["tasks"]], ["task-b"])
        self.assertEqual([task["task_id"] for task in size["tasks"]], ["task-b"])
        self.assertEqual([task["task_id"] for task in quality["tasks"]], ["task-b"])
        self.assertEqual(first_page["tasks"][0]["prompt_mode"], "strict")
        self.assertEqual(first_page["tasks"][0]["quality"], "high")
        self.assertEqual([task["task_id"] for task in oldest["tasks"]], ["task-old", "task-a"])
        self.assertEqual([task["task_id"] for task in previous_newest["tasks"]], ["task-b"])
        self.assertIn("previous_cursor", previous_newest)
        self.assertEqual([task["task_id"] for task in previous_oldest["tasks"]], ["task-a"])

    def test_history_summary_groups_counts_for_filters(self) -> None:
        with TemporaryDirectory() as tmp:
            index = SQLiteTaskIndex(Path(tmp) / "tasks.db")
            index.upsert(
                {
                    "task_id": "portrait",
                    "created_at": "2026-05-09T10:00:00+00:00",
                    "status": "completed",
                    "prompt": "portrait",
                    "params": {
                        "size": "1152x2048",
                        "quality": "high",
                        "ratio": "9:16",
                        "orientation": "portrait",
                        "prompt_fidelity": "strict",
                    },
                    "backend": "openai_images",
                    "api_provider_name": "openai",
                }
            )
            index.upsert(
                {
                    "task_id": "square",
                    "created_at": "2026-05-08T10:00:00+00:00",
                    "status": "failed",
                    "prompt": "square",
                    "params": {
                        "size": "1024x1024",
                        "quality": "low",
                        "ratio": "1:1",
                        "orientation": "square",
                        "prompt_fidelity": "original",
                    },
                    "backend": "codex_responses",
                    "api_provider_name": "codex",
                    "archived_at": "2026-05-10T00:00:00+00:00",
                }
            )
            index.upsert(
                {
                    "task_id": "landscape",
                    "created_at": "2026-04-07T10:00:00+00:00",
                    "status": "completed",
                    "prompt": "landscape",
                    "params": {
                        "size": "1536x864",
                        "quality": "high",
                        "ratio": "16:9",
                        "orientation": "landscape",
                        "prompt_fidelity": "strict",
                    },
                    "backend": "openai_images",
                    "api_provider_name": "openai",
                }
            )

            summary = index.history_summary()

        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["archived_total"], 1)
        self.assertEqual(summary["months"][0], {"month": "2026-05", "count": 2})
        self.assertIn({"value": "completed", "count": 2}, summary["statuses"])
        self.assertIn({"value": "9:16", "count": 1}, summary["ratios"])
        self.assertIn({"value": "portrait", "count": 1}, summary["orientations"])
        self.assertIn({"value": "openai_images", "count": 2}, summary["backends"])
        self.assertIn({"value": "openai", "count": 2}, summary["providers"])
        self.assertIn({"value": "strict", "count": 2}, summary["prompt_modes"])
        self.assertIn({"value": "1152x2048", "count": 1}, summary["sizes"])
        self.assertIn({"value": "high", "count": 2}, summary["qualities"])

    def test_history_ratio_filter_derives_known_size_and_groups_unknown_as_other(self) -> None:
        with TemporaryDirectory() as tmp:
            index = SQLiteTaskIndex(Path(tmp) / "tasks.db")
            index.upsert(
                {
                    "task_id": "has-ratio",
                    "created_at": "2026-05-09T10:00:00+00:00",
                    "status": "completed",
                    "prompt": "portrait",
                    "params": {"ratio": "9:16", "size": "1152x2048"},
                }
            )
            index.upsert(
                {
                    "task_id": "known-size",
                    "created_at": "2026-05-08T10:00:00+00:00",
                    "status": "completed",
                    "prompt": "legacy size only",
                    "params": {"size": "1344x2016"},
                }
            )
            index.upsert(
                {
                    "task_id": "unknown-size",
                    "created_at": "2026-05-07T10:00:00+00:00",
                    "status": "completed",
                    "prompt": "custom size only",
                    "params": {"size": "1232x1568"},
                }
            )

            summary = index.history_summary()
            portrait = index.query_history(limit=10, ratio="2:3")
            other = index.query_history(limit=10, ratio=RATIO_OTHER_VALUE)

        self.assertIn({"value": "9:16", "count": 1}, summary["ratios"])
        self.assertIn({"value": "2:3", "count": 1}, summary["ratios"])
        self.assertIn({"value": RATIO_OTHER_VALUE, "count": 1}, summary["ratios"])
        self.assertIn({"value": "portrait", "count": 3}, summary["orientations"])
        self.assertEqual([task["task_id"] for task in portrait["tasks"]], ["known-size"])
        self.assertEqual([task["task_id"] for task in other["tasks"]], ["unknown-size"])
