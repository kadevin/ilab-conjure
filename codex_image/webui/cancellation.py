from __future__ import annotations

from typing import Any

from .storage import TaskStorage, utc_now

USER_CANCELLATION_ERROR = "Task cancelled by user."


def _attempt_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def request_task_cancellation(
    storage: TaskStorage,
    task_id: str,
) -> dict[str, Any]:
    with storage._task_write_lock(task_id):
        metadata = storage.read_metadata(task_id)
        if metadata.get("cancelled_at"):
            return metadata
        requested_at = str(metadata.get("cancel_requested_at") or utc_now())
        metadata.update(
            {
                "status": "cancelling",
                "updated_at": requested_at,
                "cancel_requested": True,
                "cancel_requested_at": requested_at,
            }
        )
        metadata.pop("terminal_at", None)
        metadata.pop("request", None)
        storage.write_metadata(task_id, metadata)
        return metadata


def finalize_task_cancellation(
    storage: TaskStorage,
    task_id: str,
) -> dict[str, Any]:
    with storage._task_write_lock(task_id):
        metadata = storage.read_metadata(task_id)
        cancelled_at = str(metadata.get("cancelled_at") or utc_now())
        metadata.update(
            {
                "status": "failed",
                "updated_at": cancelled_at,
                "cancelled_at": cancelled_at,
                "cancel_requested": True,
                "cancel_requested_at": str(
                    metadata.get("cancel_requested_at") or cancelled_at
                ),
                "error": USER_CANCELLATION_ERROR,
                "last_error": USER_CANCELLATION_ERROR,
            }
        )
        output_records = metadata.get("outputs")
        if isinstance(output_records, list):
            normalized: list[Any] = []
            for item in output_records:
                if not isinstance(item, dict):
                    normalized.append(item)
                    continue
                record = dict(item)
                if str(record.get("status") or "") in {"", "waiting", "queued", "running"}:
                    record["status"] = "failed"
                    record.setdefault("error", USER_CANCELLATION_ERROR)
                    record.setdefault("failed_at", cancelled_at)
                    record["updated_at"] = cancelled_at
                normalized.append(record)
            metadata["outputs"] = normalized
        metadata.pop("request", None)
        storage.write_metadata(task_id, metadata)
        return metadata


def requeue_task_after_shutdown(
    storage: TaskStorage,
    task_id: str,
) -> dict[str, Any]:
    with storage._task_write_lock(task_id):
        metadata = storage.read_metadata(task_id)
        if metadata.get("cancel_requested"):
            return finalize_task_cancellation(storage, task_id)
        requeued_at = utc_now()
        metadata.update(
            {
                "status": "queued",
                "updated_at": requeued_at,
                "queued_at": requeued_at,
                "attempts": max(0, _attempt_count(metadata.get("attempts")) - 1),
            }
        )
        output_records = metadata.get("outputs")
        if isinstance(output_records, list):
            metadata["outputs"] = [
                {
                    **record,
                    "status": (
                        "queued"
                        if isinstance(record, dict)
                        and str(record.get("status") or "") == "running"
                        else record.get("status")
                    ),
                }
                if isinstance(record, dict)
                else record
                for record in output_records
            ]
        metadata.pop("attempt_started_at", None)
        metadata.pop("assigned_auth_source", None)
        metadata.pop("assigned_account_id", None)
        metadata.pop("request", None)
        storage.write_metadata(task_id, metadata)
        return metadata
