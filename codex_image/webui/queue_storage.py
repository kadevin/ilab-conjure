from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import time
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, TypeVar

from .storage_utils import utc_now
from .store_locks import StoreLockMixin

_T = TypeVar("_T")


class QueueStorage(StoreLockMixin):
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    def read_state(self) -> dict[str, Any]:
        with self._lock:
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return self._empty_state()
            except json.JSONDecodeError:
                corrupt_path = self.path.with_name(
                    f"{self.path.stem}.corrupt.{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.{uuid.uuid4().hex}{self.path.suffix}"
                )
                try:
                    self.path.replace(corrupt_path)
                except FileNotFoundError:
                    return self._empty_state()
                return self._empty_state()

            if not isinstance(payload, dict):
                return self._empty_state()

            waiting = payload.get("waiting")
            running = payload.get("running")
            return {
                "version": 1,
                "waiting": [str(item) for item in waiting] if isinstance(waiting, list) else [],
                "running": running if isinstance(running, dict) else {},
                "updated_at": str(payload.get("updated_at") or utc_now()),
            }

    def write_state(self, state: dict[str, Any]) -> None:
        with self._lock:
            clean = {
                "version": 1,
                "waiting": [str(item) for item in state.get("waiting", [])],
                "running": state.get("running", {}) if isinstance(state.get("running"), dict) else {},
                "updated_at": utc_now(),
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path: str | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    delete=False,
                    dir=self.path.parent,
                    prefix=f".{self.path.name}.",
                    suffix=".tmp",
                ) as tmp:
                    tmp_path = tmp.name
                    tmp.write(json.dumps(clean, indent=2, ensure_ascii=False))
                    tmp.flush()
                    os.fsync(tmp.fileno())
                os.replace(tmp_path, self.path)
                tmp_path = None
            finally:
                if tmp_path is not None:
                    try:
                        Path(tmp_path).unlink()
                    except FileNotFoundError:
                        pass

    def enqueue(self, task_id: str) -> None:
        with self._lock:
            state = self.read_state()
            waiting = [item for item in state["waiting"] if item != task_id]
            waiting.append(task_id)
            state["waiting"] = waiting
            self.write_state(state)

    def remove_waiting(self, task_id: str) -> None:
        with self._lock:
            state = self.read_state()
            state["waiting"] = [item for item in state["waiting"] if item != task_id]
            self.write_state(state)

    def promote(self, task_id: str) -> None:
        with self._lock:
            state = self.read_state()
            if task_id not in state["waiting"]:
                raise ValueError("Task is not waiting")
            state["waiting"] = [task_id] + [item for item in state["waiting"] if item != task_id]
            self.write_state(state)

    def reorder(self, task_ids: list[str]) -> None:
        with self._lock:
            state = self.read_state()
            current = state["waiting"]
            requested = set(task_ids)
            existing = set(current)
            if (
                len(task_ids) != len(requested)
                or len(current) != len(existing)
                or len(task_ids) != len(current)
                or requested != existing
            ):
                raise ValueError("Reorder list must match waiting queue")
            state["waiting"] = list(task_ids)
            self.write_state(state)

    def pop_next(self) -> str | None:
        with self._lock:
            state = self.read_state()
            if not state["waiting"]:
                return None
            task_id = state["waiting"].pop(0)
            self.write_state(state)
            return task_id

    def set_running(
        self,
        channel_id: str,
        task_id: str,
        *,
        auth_source: str,
        account_id: str | None = None,
    ) -> None:
        with self._lock:
            state = self.read_state()
            running = dict(state["running"])
            running[channel_id] = {
                "task_id": task_id,
                "started_at": utc_now(),
                "auth_source": auth_source,
                "account_id": account_id,
            }
            state["running"] = running
            self.write_state(state)

    def clear_running(self, channel_id: str) -> None:
        with self._lock:
            state = self.read_state()
            running = dict(state["running"])
            running.pop(channel_id, None)
            state["running"] = running
            self.write_state(state)

    def claim_waiting(
        self,
        task_id: str,
        channel_id: str,
        *,
        auth_source: str,
        account_id: str | None = None,
    ) -> bool:
        with self._lock:
            state = self.read_state()
            if channel_id in state["running"]:
                return False
            if any(
                isinstance(record, dict) and record.get("task_id") == task_id
                for record in state["running"].values()
            ):
                return False
            if task_id not in state["waiting"]:
                return False
            state["waiting"] = [item for item in state["waiting"] if item != task_id]
            state["running"][channel_id] = {
                "task_id": task_id,
                "started_at": utc_now(),
                "auth_source": auth_source,
                "account_id": account_id,
            }
            self.write_state(state)
            return True

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {"version": 1, "waiting": [], "running": {}, "updated_at": utc_now()}


class SQLiteQueueStorage(StoreLockMixin):
    def __init__(self, path: Path | str, *, legacy_json_path: Path | str | None = None) -> None:
        self.path = Path(path)
        self.legacy_json_path = Path(legacy_json_path) if legacy_json_path is not None else None
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._import_legacy_json_once()

    def read_state(self) -> dict[str, Any]:
        with self._lock, closing(self._connect()) as connection:
            waiting = [
                row[0]
                for row in connection.execute(
                    "select task_id from queue_waiting order by position asc, task_id asc"
                ).fetchall()
            ]
            running = {
                row["channel_id"]: {
                    "task_id": row["task_id"],
                    "started_at": row["started_at"],
                    "auth_source": row["auth_source"],
                    "account_id": row["account_id"],
                }
                for row in connection.execute(
                    "select channel_id, task_id, started_at, auth_source, account_id from queue_running order by channel_id"
                ).fetchall()
            }
            updated = connection.execute("select value from queue_meta where key = 'updated_at'").fetchone()
        return {
            "version": 1,
            "waiting": waiting,
            "running": running,
            "updated_at": str(updated[0] if updated else utc_now()),
        }

    def write_state(self, state: dict[str, Any]) -> None:
        waiting = [str(item) for item in state.get("waiting", [])]
        running = state.get("running", {}) if isinstance(state.get("running"), dict) else {}
        def replace_state(connection: sqlite3.Connection) -> None:
            connection.execute("delete from queue_waiting")
            connection.execute("delete from queue_running")
            for position, task_id in enumerate(waiting):
                connection.execute(
                    "insert into queue_waiting(task_id, position) values(?, ?)",
                    (task_id, position),
                )
            for channel_id, item in running.items():
                if not isinstance(item, dict):
                    continue
                connection.execute(
                    """
                    insert into queue_running(channel_id, task_id, started_at, auth_source, account_id)
                    values(?, ?, ?, ?, ?)
                    """,
                    (
                        str(channel_id),
                        str(item.get("task_id") or ""),
                        str(item.get("started_at") or utc_now()),
                        str(item.get("auth_source") or ""),
                        item.get("account_id"),
                    ),
                )
            self._touch(connection)

        with self._lock:
            self._run_write_transaction(replace_state)

    def enqueue(self, task_id: str) -> None:
        def append_waiting(connection: sqlite3.Connection) -> None:
            connection.execute("delete from queue_waiting where task_id = ?", (task_id,))
            row = connection.execute(
                "select coalesce(max(position), -1) + 1 from queue_waiting"
            ).fetchone()
            connection.execute(
                "insert into queue_waiting(task_id, position) values(?, ?)",
                (task_id, int(row[0] if row else 0)),
            )
            self._touch(connection)

        with self._lock:
            self._run_write_transaction(append_waiting)

    def remove_waiting(self, task_id: str) -> None:
        def remove(connection: sqlite3.Connection) -> None:
            connection.execute("delete from queue_waiting where task_id = ?", (task_id,))
            self._touch(connection)

        with self._lock:
            self._run_write_transaction(remove)

    def promote(self, task_id: str) -> None:
        def promote_waiting(connection: sqlite3.Connection) -> None:
            existing = connection.execute(
                "select position from queue_waiting where task_id = ?",
                (task_id,),
            ).fetchone()
            if existing is None:
                raise ValueError("Task is not waiting")
            first = connection.execute(
                "select coalesce(min(position), 0) - 1 from queue_waiting"
            ).fetchone()
            connection.execute(
                "update queue_waiting set position = ? where task_id = ?",
                (int(first[0] if first else -1), task_id),
            )
            self._touch(connection)

        with self._lock:
            self._run_write_transaction(promote_waiting)

    def reorder(self, task_ids: list[str]) -> None:
        def reorder_waiting(connection: sqlite3.Connection) -> None:
            current = [
                str(row[0])
                for row in connection.execute(
                    "select task_id from queue_waiting order by position asc, task_id asc"
                ).fetchall()
            ]
            requested = set(task_ids)
            existing = set(current)
            if (
                len(task_ids) != len(requested)
                or len(current) != len(existing)
                or len(task_ids) != len(current)
                or requested != existing
            ):
                raise ValueError("Reorder list must match waiting queue")
            connection.executemany(
                "update queue_waiting set position = ? where task_id = ?",
                [(position, task_id) for position, task_id in enumerate(task_ids)],
            )
            self._touch(connection)

        with self._lock:
            self._run_write_transaction(reorder_waiting)

    def pop_next(self) -> str | None:
        def pop(connection: sqlite3.Connection) -> str | None:
            row = connection.execute(
                "select task_id from queue_waiting order by position asc, task_id asc limit 1"
            ).fetchone()
            if row is None:
                return None
            task_id = str(row[0])
            connection.execute("delete from queue_waiting where task_id = ?", (task_id,))
            self._touch(connection)
            return task_id

        with self._lock:
            return self._run_write_transaction(pop)

    def set_running(
        self,
        channel_id: str,
        task_id: str,
        *,
        auth_source: str,
        account_id: str | None = None,
    ) -> None:
        def mark_running(connection: sqlite3.Connection) -> None:
            connection.execute(
                """
                insert or replace into queue_running(
                    channel_id, task_id, started_at, auth_source, account_id
                ) values(?, ?, ?, ?, ?)
                """,
                (channel_id, task_id, utc_now(), auth_source, account_id),
            )
            self._touch(connection)

        with self._lock:
            self._run_write_transaction(mark_running)

    def clear_running(self, channel_id: str) -> None:
        def clear(connection: sqlite3.Connection) -> None:
            connection.execute(
                "delete from queue_running where channel_id = ?",
                (channel_id,),
            )
            self._touch(connection)

        with self._lock:
            self._run_write_transaction(clear)

    def claim_waiting(
        self,
        task_id: str,
        channel_id: str,
        *,
        auth_source: str,
        account_id: str | None = None,
    ) -> bool:
        def claim(connection: sqlite3.Connection) -> bool:
            channel_busy = connection.execute(
                "select 1 from queue_running where channel_id = ? limit 1",
                (channel_id,),
            ).fetchone()
            task_running = connection.execute(
                "select 1 from queue_running where task_id = ? limit 1",
                (task_id,),
            ).fetchone()
            if channel_busy is not None or task_running is not None:
                return False
            deleted = connection.execute(
                "delete from queue_waiting where task_id = ?",
                (task_id,),
            )
            if deleted.rowcount != 1:
                return False
            connection.execute(
                """
                insert into queue_running(
                    channel_id, task_id, started_at, auth_source, account_id
                ) values(?, ?, ?, ?, ?)
                """,
                (channel_id, task_id, utc_now(), auth_source, account_id),
            )
            self._touch(connection)
            return True

        with self._lock:
            return self._run_write_transaction(claim)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("pragma busy_timeout = 5000")
        return connection

    def _run_write_transaction(
        self,
        operation: Callable[[sqlite3.Connection], _T],
    ) -> _T:
        delay = 0.01
        for attempt in range(4):
            with closing(self._connect()) as connection:
                try:
                    connection.execute("begin immediate")
                    result = operation(connection)
                    connection.commit()
                    return result
                except sqlite3.OperationalError as exc:
                    connection.rollback()
                    locked = "locked" in str(exc).lower() or "busy" in str(exc).lower()
                    if not locked or attempt >= 3:
                        raise
                except BaseException:
                    connection.rollback()
                    raise
            time.sleep(delay)
            delay *= 2
        raise RuntimeError("SQLite queue transaction retry exhausted")

    def _initialize(self) -> None:
        with self._lock, closing(self._connect()) as connection:
            connection.execute("pragma journal_mode = delete")
            connection.execute(
                "create table if not exists queue_meta(key text primary key, value text not null)"
            )
            connection.execute(
                "create table if not exists queue_waiting(task_id text primary key, position integer not null)"
            )
            connection.execute(
                """
                create table if not exists queue_running(
                    channel_id text primary key,
                    task_id text not null,
                    started_at text not null,
                    auth_source text not null,
                    account_id text
                )
                """
            )
            self._touch(connection)
            connection.commit()

    def _import_legacy_json_once(self) -> None:
        if self.legacy_json_path is None or not self.legacy_json_path.exists():
            return
        with self._lock, closing(self._connect()) as connection:
            imported = connection.execute(
                "select value from queue_meta where key = 'legacy_json_imported'"
            ).fetchone()
            waiting_exists = connection.execute("select 1 from queue_waiting limit 1").fetchone()
            running_exists = connection.execute("select 1 from queue_running limit 1").fetchone()
            if imported or waiting_exists or running_exists:
                return
        legacy_state = QueueStorage(self.legacy_json_path).read_state()
        self.write_state(legacy_state)
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                "insert or replace into queue_meta(key, value) values('legacy_json_imported', ?)",
                (utc_now(),),
            )
            connection.commit()

    def _touch(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            "insert or replace into queue_meta(key, value) values('updated_at', ?)",
            (utc_now(),),
        )
