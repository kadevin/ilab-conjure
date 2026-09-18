from contextlib import closing
import asyncio
from pathlib import Path
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from codex_image.webui.storage import TaskStorage
from codex_image.webui.task_index import SQLiteTaskIndex


class HistoryPerformanceTests(unittest.TestCase):
    def test_unrepairable_records_are_attempted_once_and_writes_reenable_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = TaskStorage(input_root=root / "in", output_root=root / "out", source_data_root=root / "data")
            ids = []
            for _ in range(3):
                task = storage.create_task("generate")
                ids.append(task.task_id)
                storage.write_metadata(task.task_id, {"task_id": task.task_id, "status": "completed"})
            # Small batches must advance beyond unrepairable rows.
            self.assertEqual(storage.refresh_stale_task_index(limit=2), 2)
            self.assertEqual(storage.refresh_stale_task_index(limit=2), 1)
            with patch.object(storage, "read_metadata", wraps=storage.read_metadata) as read:
                self.assertEqual(storage.refresh_stale_task_index(), 0)
                read.assert_not_called()
            reopened = TaskStorage(input_root=root / "in", output_root=root / "out", source_data_root=root / "data")
            self.assertEqual(reopened.refresh_stale_task_index(), 0)
            reopened.write_metadata(ids[0], {"task_id": ids[0], "status": "completed", "prompt": "updated"})
            self.assertEqual(reopened.refresh_stale_task_index(), 1)
            self.assertEqual(reopened.refresh_stale_task_index(), 0)

    def test_concurrent_history_readers_do_not_repeat_the_same_repair(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = TaskStorage(input_root=root / "in", output_root=root / "out", source_data_root=root / "data")
            for _ in range(5):
                task = storage.create_task("generate")
                storage.write_metadata(task.task_id, {"task_id": task.task_id, "status": "completed"})
            with patch.object(storage, "read_metadata", wraps=storage.read_metadata) as read:
                with ThreadPoolExecutor(max_workers=4) as executor:
                    counts = list(executor.map(lambda _: storage.refresh_stale_task_index(), range(4)))
                self.assertEqual(sum(counts), 5)
                self.assertEqual(read.call_count, 5)

    def test_old_fts_migrates_to_stable_rowids_and_skips_unchanged_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.db"
            index = SQLiteTaskIndex(path)
            if not index.fts_enabled:
                self.skipTest("SQLite FTS5 unavailable")
            records = [{"task_id": str(i), "prompt": f"portrait 猫咪 {i}", "created_at": "2026-09-17T00:00:00Z"} for i in range(3)]
            for row in records:
                index.upsert(row)
            with closing(sqlite3.connect(path)) as conn, conn:
                conn.execute("drop table task_index_fts_keys")
                conn.execute("update task_index_fts set task_id = 'stale'")
            index = SQLiteTaskIndex(path)
            with closing(index._connect()) as conn:
                self.assertEqual(conn.execute("select count(*) from task_index_fts").fetchone()[0], 3)
                ids = dict(conn.execute("select task_id, id from task_index_fts_keys"))
                conn.execute("vacuum")
            queries = []
            connect = index._connect
            def traced():
                conn = connect()
                conn.set_trace_callback(queries.append)
                return conn
            with patch.object(index, "_connect", side_effect=traced):
                index.upsert({**records[1], "status": "running"})
            self.assertFalse(any(q.lower().startswith(("delete from task_index_fts", "insert into task_index_fts(")) for q in queries))
            index.upsert({**records[1], "prompt": "landscape 山水"})
            with closing(index._connect()) as conn:
                self.assertEqual(dict(conn.execute("select task_id, id from task_index_fts_keys")), ids)
                self.assertEqual(conn.execute("select task_id from task_index_fts where task_index_fts match 'landscape'").fetchone()[0], "1")
                plan = conn.execute("explain query plan select * from task_index_fts where rowid = ?", (ids["1"],)).fetchone()[3]
                self.assertIn("=", plan)
            self.assertEqual(len(index.query_history(q="山水")["tasks"]), 1)
            index.delete("1")
            with closing(index._connect()) as conn:
                self.assertEqual(conn.execute("select count(*) from task_index_fts where rowid = ?", (ids["1"],)).fetchone()[0], 0)


class QueuePerformanceTests(unittest.TestCase):
    def test_cache_shares_unchanged_reads_and_invalidates_on_metadata_and_queue_writes(self):
        from codex_image.webui.queue_snapshot_cache import QueueSnapshotCache
        from codex_image.webui.queue_storage import SQLiteQueueStorage
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = TaskStorage(input_root=root / "in", output_root=root / "out", source_data_root=root / "data")
            queue = SQLiteQueueStorage(root / "queue.db")
            ctx = SimpleNamespace(storage=storage, queue_storage=queue, queue_manager=None, active_task_ids=set(), route_helpers={})
            cache = QueueSnapshotCache(ctx)
            task = storage.create_task("generate")
            with patch("codex_image.webui.queue_snapshot_cache.queue_snapshot", return_value={"waiting": [], "running": []}) as build:
                first = cache.get()
                self.assertIs(cache.get(), first)
                self.assertEqual(build.call_count, 1)
                storage.write_metadata(task.task_id, {"task_id": task.task_id, "status": "queued"})
                cache.get()
                queue.enqueue(task.task_id)
                cache.get()
                ctx.active_task_ids.add(task.task_id)
                cache.get()
                self.assertEqual(build.call_count, 4)

    def test_queue_endpoint_does_not_block_the_event_loop(self):
        from fastapi import FastAPI
        from codex_image.webui.routes.queue import register_queue_routes
        from codex_image.webui.state_sync import StateSyncClock
        app = FastAPI()
        app.state.state_sync_clock = StateSyncClock()
        ctx = SimpleNamespace(route_helpers={"ensure_queue_worker_running": lambda: None})
        register_queue_routes(app, ctx)
        entered, release = threading.Event(), threading.Event()
        def slow_read():
            entered.set()
            if not release.wait(2):
                raise AssertionError("event loop could not release the reader")
            return {}, "empty", set()
        async def exercise():
            endpoint = next(route.endpoint for route in app.routes if route.path == "/api/queue")
            pending = asyncio.create_task(endpoint())
            while not entered.is_set():
                await asyncio.sleep(0.001)
            release.set()
            result = await pending
            self.assertGreater(result["sync"]["revision"], 0)
        with patch("codex_image.webui.routes.queue.QueueSnapshotCache.get", side_effect=slow_read):
            asyncio.run(exercise())
