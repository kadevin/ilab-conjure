from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from .storage import QueueStorage


@dataclass(frozen=True)
class QueueChannel:
    channel_id: str
    auth_source: str
    account_id: str | None = None
    provider_id: str | None = None
    slot_index: int = 0


TaskExecutor = Callable[[str, QueueChannel, bool], Awaitable[None]]
ChannelAvailability = Callable[[QueueChannel], bool]
TaskClaim = Callable[[str, QueueChannel], bool]
TaskClaimRelease = Callable[[str, QueueChannel], None]
CancelledTaskRequeue = Callable[[str], bool]


class QueueTaskError(RuntimeError):
    """A task execution failure that must not be treated as a worker fault."""

    def __init__(
        self,
        message: str,
        *,
        task_id: str = "",
        error_code: str = "task_execution_failed",
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.task_id = str(task_id or "")
        self.error_code = str(error_code or "task_execution_failed")
        self.retryable = bool(retryable)


class NonRetryableTaskError(QueueTaskError):
    """Raised when retrying the task on another channel cannot change the result."""

    def __init__(
        self,
        message: str,
        *,
        task_id: str = "",
        error_code: str = "task_execution_failed",
    ) -> None:
        super().__init__(
            message,
            task_id=task_id,
            error_code=error_code,
            retryable=False,
        )


class RetryableTaskError(QueueTaskError):
    """Raised when a task failed but may succeed on a later attempt."""

    def __init__(
        self,
        message: str,
        *,
        task_id: str = "",
        error_code: str = "task_execution_failed",
    ) -> None:
        super().__init__(
            message,
            task_id=task_id,
            error_code=error_code,
            retryable=True,
        )


@dataclass
class QueueManager:
    queue_storage: QueueStorage
    channels: list[QueueChannel]
    execute_task: TaskExecutor
    max_attempts: int = 2
    channel_available: ChannelAvailability | None = None
    claim_task: TaskClaim | None = None
    release_task_claim: TaskClaimRelease | None = None
    task_channel_matches: TaskClaim | None = None
    should_requeue_cancelled: CancelledTaskRequeue | None = None
    auto_retry: bool = True
    attempts: dict[str, int] = field(default_factory=dict)
    failed_channels: dict[str, set[str]] = field(default_factory=dict)

    async def run_available_once(self) -> None:
        jobs: list[Awaitable[None]] = []
        for channel in self.channels:
            task_id = self._next_task_for_channel(channel)
            if task_id is None:
                continue
            jobs.append(self._run_task(task_id, channel))
        if jobs:
            results = await asyncio.gather(*jobs, return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException):
                    raise result

    async def run_channel_once(self, channel: QueueChannel) -> bool:
        task_id = self._next_task_for_channel(channel)
        if task_id is None:
            return False
        await self._run_task(task_id, channel)
        return True

    def _next_task_for_channel(self, channel: QueueChannel) -> str | None:
        if not self._channel_can_take_work(channel):
            return None
        state = self.queue_storage.read_state()
        for task_id in state["waiting"]:
            blocked = self.failed_channels.get(task_id, set())
            if channel.channel_id not in blocked:
                if self._claim_waiting_task(task_id, channel):
                    return task_id
                continue
            matching_ids = self._matching_available_channel_ids(task_id)
            if matching_ids and matching_ids.issubset(blocked):
                self.failed_channels[task_id] = set()
                if self._claim_waiting_task(task_id, channel):
                    return task_id
        return None

    def _channel_can_take_work(self, channel: QueueChannel) -> bool:
        if self.channel_available is None:
            return True
        return bool(self.channel_available(channel))

    def _claim_task(self, task_id: str, channel: QueueChannel) -> bool:
        if self.claim_task is None:
            return True
        return bool(self.claim_task(task_id, channel))

    def _claim_waiting_task(self, task_id: str, channel: QueueChannel) -> bool:
        if not self._claim_task(task_id, channel):
            return False
        try:
            claimed = self.queue_storage.claim_waiting(
                task_id,
                channel.channel_id,
                auth_source=channel.auth_source,
                account_id=channel.account_id,
            )
        except BaseException:
            self._release_task_claim(task_id, channel)
            raise
        if not claimed:
            self._release_task_claim(task_id, channel)
        return claimed

    def _release_task_claim(self, task_id: str, channel: QueueChannel) -> None:
        if self.release_task_claim is not None:
            self.release_task_claim(task_id, channel)

    def _available_channel_count(self) -> int:
        return max(1, sum(1 for channel in self.channels if self._channel_can_take_work(channel)))

    def _matching_available_channel_ids(self, task_id: str) -> set[str]:
        return {
            channel.channel_id
            for channel in self.channels
            if self._channel_can_take_work(channel)
            and (
                self.task_channel_matches is None
                or self.task_channel_matches(task_id, channel)
            )
        }

    async def _run_task(self, task_id: str, channel: QueueChannel) -> None:
        self.attempts[task_id] = self.attempts.get(task_id, 0) + 1
        is_final_attempt = not self.auto_retry or self.attempts[task_id] >= self.max_attempts
        try:
            await self.execute_task(task_id, channel, is_final_attempt)
            self.failed_channels.pop(task_id, None)
            self.attempts.pop(task_id, None)
        except asyncio.CancelledError:
            if (
                self.should_requeue_cancelled is not None
                and self.should_requeue_cancelled(task_id)
            ):
                self.queue_storage.enqueue(task_id)
            attempt_count = self.attempts.get(task_id, 0) - 1
            if attempt_count > 0:
                self.attempts[task_id] = attempt_count
            else:
                self.attempts.pop(task_id, None)
            raise
        except NonRetryableTaskError as exc:
            self.failed_channels.pop(task_id, None)
            self.attempts.pop(task_id, None)
            if not exc.task_id:
                exc.task_id = task_id
            raise
        except Exception as exc:
            self.failed_channels.setdefault(task_id, set()).add(channel.channel_id)
            if self.auto_retry and not is_final_attempt:
                self.queue_storage.enqueue(task_id)
            if isinstance(exc, QueueTaskError):
                if not exc.task_id:
                    exc.task_id = task_id
                raise
            raise RetryableTaskError(
                str(exc),
                task_id=task_id,
            ) from exc
        finally:
            self.queue_storage.clear_running(channel.channel_id)
