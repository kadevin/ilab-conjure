from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any, Iterable

from .context import WebUIContext
from .storage_utils import utc_now
from .task_metadata import _gallery_item_response, _with_file_urls


GENERATION_PAGE_TASK_LIMIT = 50


def _running_queue_order(entry: tuple[str, Any]) -> tuple[float, str, str]:
    channel_id, item = entry
    task_id = str(item.get("task_id") or "") if isinstance(item, dict) else ""
    raw_started_at = str(item.get("started_at") or "") if isinstance(item, dict) else ""
    try:
        started_at = datetime.fromisoformat(raw_started_at.replace("Z", "+00:00"))
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        started_timestamp = started_at.timestamp()
    except (OverflowError, ValueError):
        started_timestamp = float("inf")
    return started_timestamp, task_id, str(channel_id)


def _prune_inactive_running_channels(ctx: WebUIContext) -> None:
    if ctx.queue_manager is None:
        return
    state = ctx.queue_storage.read_state()
    running = state["running"]
    if not running:
        return
    active_channel_ids = {channel.channel_id for channel in ctx.queue_manager.channels}
    active_auth_sources = {channel.auth_source for channel in ctx.queue_manager.channels}
    stale_channel_ids: list[str] = []
    for channel_id, item in running.items():
        if channel_id in active_channel_ids:
            continue
        if not str(channel_id).rsplit(":", 1)[-1].isdigit():
            continue
        if isinstance(item, dict):
            if str(item.get("auth_source") or "") not in active_auth_sources:
                continue
            task_id = str(item.get("task_id") or "")
            if task_id and task_id in ctx.active_task_ids:
                continue
            if task_id and ctx.storage.metadata_path(task_id).exists():
                metadata = ctx.storage.read_metadata(task_id)
                if metadata.get("status") == "running":
                    message = "Service restarted before this task completed."
                    metadata["status"] = "failed"
                    metadata["updated_at"] = utc_now()
                    metadata["error"] = message
                    metadata["last_error"] = message
                    metadata.pop("request", None)
                    ctx.storage.write_metadata(task_id, metadata)
        stale_channel_ids.append(str(channel_id))
    for channel_id in stale_channel_ids:
        ctx.queue_storage.clear_running(channel_id)


def queue_snapshot(ctx: WebUIContext) -> dict[str, Any]:
    _prune_inactive_running_channels(ctx)
    state = ctx.queue_storage.read_state()
    active_ids = ctx.route_helpers["visible_running_task_ids"]()
    waiting = [
        _with_file_urls(
            task,
            active_ids,
            ctx.gallery_storage,
            ctx.reference_asset_storage,
            ctx.reference_file_storage,
            include_request=False,
        )
        for task in (ctx.storage.read_metadata(task_id) for task_id in state["waiting"] if ctx.storage.metadata_path(task_id).exists())
    ]
    running = []
    for channel_id, item in sorted(
        state["running"].items(),
        key=_running_queue_order,
    ):
        metadata_path = ctx.storage.metadata_path(str(item.get("task_id") or "")) if isinstance(item, dict) else None
        if metadata_path is None or not metadata_path.exists():
            continue
        task = _with_file_urls(
            ctx.storage.read_metadata(str(item["task_id"])),
            active_ids,
            ctx.gallery_storage,
            ctx.reference_asset_storage,
            ctx.reference_file_storage,
            include_request=False,
        )
        task["channel_id"] = channel_id
        task["account_id"] = item.get("account_id")
        running.append(task)
    channels = ctx.queue_manager.channels if ctx.queue_manager is not None else []
    queue_channel_available = ctx.route_helpers["queue_channel_available"]
    return {
        "waiting": waiting,
        "running": running,
        "summary": {
            "waiting_count": len(waiting),
            "running_count": len(running),
            "channel_count": len(channels),
            "usable_channel_count": sum(1 for channel in channels if queue_channel_available(channel)),
        },
    }


def generation_page_payload(
    ctx: WebUIContext,
    queue: dict[str, Any] | None = None,
    *,
    limit_per_group: int = GENERATION_PAGE_TASK_LIMIT,
) -> dict[str, Any]:
    current_queue = queue or queue_snapshot(ctx)
    task_groups = ctx.storage.generation_sidebar_groups(limit_per_group=limit_per_group)["groups"]
    tasks = [task for group in task_groups for task in group.get("tasks", [])]
    task_ids = {str(task.get("task_id") or "") for task in tasks}
    for active_task in list(current_queue.get("waiting") or []) + list(current_queue.get("running") or []):
        task_id = str(active_task.get("task_id") or "") if isinstance(active_task, dict) else ""
        if not task_id or task_id in task_ids:
            continue
        try:
            task = ctx.storage.task_sidebar_card(task_id)
        except (FileNotFoundError, ValueError):
            continue
        tasks.append(task)
        task_ids.add(task_id)
    return {"tasks": tasks, "task_groups": task_groups}


def event_snapshot(ctx: WebUIContext) -> dict[str, Any]:
    with ctx.app.state.state_sync_clock.capture() as sync:
        queue = queue_snapshot(ctx)
        page = generation_page_payload(ctx, queue)
    return {
        "type": "snapshot",
        "sync": sync,
        **page,
        "queue": queue,
        "gallery": [_gallery_item_response(item) for item in ctx.gallery_storage.list_items()],
        "auth": ctx.route_helpers["auth_event_payload"](),
    }


def sse_message(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def event_key(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def queued_or_running_task_ids(queue: dict[str, Any]) -> set[str]:
    return {
        str(task.get("task_id"))
        for task in list(queue.get("waiting") or []) + list(queue.get("running") or [])
        if isinstance(task, dict) and task.get("task_id")
    }


def task_event(ctx: WebUIContext, task_id: str) -> dict[str, Any] | None:
    if not ctx.storage.metadata_path(task_id).exists():
        return None
    return {
        "type": "task",
        "task": _with_file_urls(
            ctx.storage.read_metadata(task_id),
            ctx.route_helpers["visible_running_task_ids"](),
            ctx.gallery_storage,
            ctx.reference_asset_storage,
            ctx.reference_file_storage,
            include_request=False,
        ),
    }


def task_events(ctx: WebUIContext, task_ids: Iterable[str]) -> list[dict[str, Any]]:
    events = []
    for task_id in sorted({str(task_id) for task_id in task_ids if str(task_id or "")}):
        payload = task_event(ctx, task_id)
        if payload is not None:
            events.append(payload)
    return events


def queue_event(queue: dict[str, Any], finished_task_events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": "queue", "queue": queue}
    finished_tasks = [
        event.get("task")
        for event in (finished_task_events or [])
        if isinstance(event, dict) and isinstance(event.get("task"), dict)
    ]
    if finished_tasks:
        payload["tasks"] = finished_tasks
    return payload
