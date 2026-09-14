from __future__ import annotations

from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from codex_image.webui.context import WebUIContext
from codex_image.webui.events import event_key, event_snapshot, queue_event, queue_snapshot, queued_or_running_task_ids, sse_message, task_events

EVENT_STREAM_CHECK_INTERVAL_SECONDS = 1.0


def register_queue_routes(app: FastAPI, ctx: WebUIContext) -> None:
    h = ctx.route_helpers

    @app.get("/api/queue")
    async def get_queue() -> dict[str, Any]:
        h["ensure_queue_worker_running"]()
        with app.state.state_sync_clock.capture() as sync:
            return {**queue_snapshot(ctx), "sync": sync}

    @app.get("/api/events", response_model=None)
    async def events(request: Request, stream: bool = False) -> StreamingResponse:
        h["ensure_queue_worker_running"]()
        should_stream = stream

        async def stream_events():
            h["ensure_queue_worker_running"]()
            snapshot = event_snapshot(ctx)
            yield sse_message(snapshot)
            if not should_stream:
                return

            previous_queue = snapshot["queue"]
            previous_queue_key = event_key(previous_queue)
            previous_task_ids = queued_or_running_task_ids(previous_queue)
            while True:
                shutdown_coordinator = (
                    request.app.state.webui_shutdown_coordinator
                )
                if await shutdown_coordinator.wait(
                    EVENT_STREAM_CHECK_INTERVAL_SECONDS
                ):
                    return
                if await request.is_disconnected():
                    return
                h["ensure_queue_worker_running"]()
                with app.state.state_sync_clock.capture() as sync:
                    queue = queue_snapshot(ctx)
                    queue_key = event_key(queue)
                    if queue_key == previous_queue_key:
                        continue

                    current_task_ids = queued_or_running_task_ids(queue)
                    finished_events = task_events(ctx, previous_task_ids - current_task_ids)
                yield sse_message({**queue_event(queue, finished_events), "sync": sync})
                for task_payload in finished_events:
                    yield sse_message({**task_payload, "sync": sync})
                previous_queue_key = queue_key
                previous_task_ids = current_task_ids

        return StreamingResponse(
            stream_events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.patch("/api/queue/reorder")
    def reorder_queue(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        task_ids = [str(item) for item in payload.get("task_ids", [])]
        try:
            ctx.queue_storage.reorder(task_ids)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return queue_snapshot(ctx)

    @app.post("/api/queue/{task_id}/promote")
    def promote_queue_task(task_id: str) -> dict[str, Any]:
        try:
            ctx.queue_storage.promote(task_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return queue_snapshot(ctx)

    @app.post("/api/queue/cancel-batch")
    async def cancel_queue_tasks(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        task_ids = list(dict.fromkeys(str(item).strip() for item in payload.get("task_ids", []) if str(item).strip()))
        if not task_ids:
            raise HTTPException(status_code=400, detail="At least one task id is required")

        state = ctx.queue_storage.read_state()
        waiting_ids = set(state["waiting"])
        running_channels = {
            str(item.get("task_id") or ""): str(channel_id)
            for channel_id, item in state["running"].items()
            if isinstance(item, dict) and item.get("task_id")
        }
        results: list[dict[str, Any]] = []

        for task_id in task_ids:
            previous_state = "waiting" if task_id in waiting_ids else "running" if task_id in running_channels else None
            if previous_state is None:
                results.append({"task_id": task_id, "result": "skipped", "reason": "not_active"})
                continue
            try:
                h["request_task_cancellation"](task_id)
                if previous_state == "waiting":
                    h["finalize_task_cancellation"](task_id)
                    ctx.queue_storage.remove_waiting(task_id)
            except FileNotFoundError:
                results.append({"task_id": task_id, "result": "skipped", "reason": "not_found"})
                continue
            except OSError:
                results.append({"task_id": task_id, "result": "failed", "reason": "storage_error"})
                continue
            cancellation_pending = previous_state == "running"
            results.append(
                {
                    "task_id": task_id,
                    "result": (
                        "cancellation_requested"
                        if cancellation_pending
                        else "cancelled"
                    ),
                    "previous_state": previous_state,
                    "cancellation_pending": cancellation_pending,
                }
            )

        return {
            "ok": not any(item["result"] == "failed" for item in results),
            "summary": {
                "cancelled": sum(item["result"] == "cancelled" for item in results),
                "cancellation_requested": sum(
                    item["result"] == "cancellation_requested"
                    for item in results
                ),
                "skipped": sum(item["result"] == "skipped" for item in results),
                "failed": sum(item["result"] == "failed" for item in results),
            },
            "results": results,
        }

    @app.delete("/api/queue/{task_id}")
    async def delete_queue_task(task_id: str) -> dict[str, Any]:
        state = ctx.queue_storage.read_state()
        if task_id in state["waiting"]:
            ctx.storage.delete_task(task_id)
            ctx.queue_storage.remove_waiting(task_id)
            return {"ok": True, "task_id": task_id, "cancelled": False}
        running_channel_id = h["running_channel_for_task"](task_id)
        if running_channel_id is None:
            raise HTTPException(status_code=409, detail="Only waiting or running tasks can be cancelled from queue")
        try:
            h["request_task_cancellation"](task_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        return {
            "ok": True,
            "task_id": task_id,
            "cancelled": False,
            "cancellation_pending": True,
        }
