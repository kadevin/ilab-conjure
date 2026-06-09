from __future__ import annotations

import asyncio
import re
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any


class FakeImageClient:
    def __init__(self) -> None:
        self.generate_calls: list[dict[str, Any]] = []
        self.edit_calls: list[dict[str, Any]] = []

    def build_payload(self, **kwargs: Any) -> dict[str, Any]:
        return {"tools": [{"type": "image_generation", **{key: value for key, value in kwargs.items() if value is not None}}]}

    def generate_image(self, **kwargs: Any):
        from codex_image.client import ImageResult

        self.generate_calls.append(kwargs)
        return ImageResult(b"generated", "revised", "png", kwargs["size"], "auto", kwargs["quality"], {})

    def edit_image(self, **kwargs: Any):
        from codex_image.client import ImageResult

        self.edit_calls.append(kwargs)
        return ImageResult(b"edited", "revised edit", "png", kwargs["size"], "auto", kwargs["quality"], {})


class CapturingApiImageClient(FakeImageClient):
    instances: list["CapturingApiImageClient"] = []

    def __init__(self, *, api_key: str, base_url: str, image_model: str, **_: Any) -> None:
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url
        self.image_model = image_model
        self.instances.append(self)


class ConcurrentApiImageClient(CapturingApiImageClient):
    instances: list["ConcurrentApiImageClient"] = []

    def __init__(self, *, api_key: str, base_url: str, image_model: str, **kwargs: Any) -> None:
        self.generate_images_calls: list[dict[str, Any]] = []
        self.edit_images_calls: list[dict[str, Any]] = []
        self.max_active_requests = 0
        self._active_requests = 0
        self._request_lock = threading.Lock()
        super().__init__(api_key=api_key, base_url=base_url, image_model=image_model, **kwargs)

    def _begin_request(self) -> int:
        with self._request_lock:
            self._active_requests += 1
            self.max_active_requests = max(self.max_active_requests, self._active_requests)
            return self._active_requests

    def _end_request(self) -> None:
        with self._request_lock:
            self._active_requests -= 1

    def generate_image(self, **kwargs: Any):
        from codex_image.client import ImageResult

        with self._request_lock:
            self.generate_calls.append(kwargs)
            call_number = len(self.generate_calls)
        self._begin_request()
        try:
            time.sleep(0.05)
            return ImageResult(
                f"api-concurrent-{call_number}".encode("utf-8"),
                f"api revised {call_number}",
                "png",
                kwargs["size"],
                "auto",
                kwargs["quality"],
                {"call_number": call_number},
            )
        finally:
            self._end_request()

    def edit_image(self, **kwargs: Any):
        from codex_image.client import ImageResult

        with self._request_lock:
            self.edit_calls.append(kwargs)
            call_number = len(self.edit_calls)
        self._begin_request()
        try:
            time.sleep(0.05)
            return ImageResult(
                f"api-edit-concurrent-{call_number}".encode("utf-8"),
                f"api edit revised {call_number}",
                "png",
                kwargs["size"],
                "auto",
                kwargs["quality"],
                {"call_number": call_number},
            )
        finally:
            self._end_request()

    def generate_images(self, **kwargs: Any):
        self.generate_images_calls.append(kwargs)
        raise AssertionError("direct Images API should issue separate single-image requests")

    def edit_images(self, **kwargs: Any):
        self.edit_images_calls.append(kwargs)
        raise AssertionError("direct Images API should issue separate single-image requests")


class BlockingConcurrentApiImageClient(CapturingApiImageClient):
    instances: list["BlockingConcurrentApiImageClient"] = []

    def __init__(self, *, api_key: str, base_url: str, image_model: str, **kwargs: Any) -> None:
        self.generate_images_calls: list[dict[str, Any]] = []
        self.slow_call_started = threading.Event()
        self.release_slow_call = threading.Event()
        self._request_lock = threading.Lock()
        super().__init__(api_key=api_key, base_url=base_url, image_model=image_model, **kwargs)

    def generate_image(self, **kwargs: Any):
        from codex_image.client import ImageResult

        with self._request_lock:
            self.generate_calls.append(kwargs)
            call_number = len(self.generate_calls)
        if call_number == 2:
            self.slow_call_started.set()
            self.release_slow_call.wait(timeout=5)
        else:
            time.sleep(0.05)
        return ImageResult(
            f"api-progress-{call_number}".encode("utf-8"),
            f"api progress revised {call_number}",
            "png",
            kwargs["size"],
            "auto",
            kwargs["quality"],
            {"call_number": call_number},
        )

    def generate_images(self, **kwargs: Any):
        self.generate_images_calls.append(kwargs)
        raise AssertionError("direct Images API should issue separate single-image requests")


class BlockingActiveConcurrentApiImageClient(CapturingApiImageClient):
    instances: list["BlockingActiveConcurrentApiImageClient"] = []

    def __init__(self, *, api_key: str, base_url: str, image_model: str, **kwargs: Any) -> None:
        self.generate_images_calls: list[dict[str, Any]] = []
        self.two_requests_active = threading.Event()
        self.release_requests = threading.Event()
        self._request_lock = threading.Lock()
        self._active_requests = 0
        super().__init__(api_key=api_key, base_url=base_url, image_model=image_model, **kwargs)

    def generate_image(self, **kwargs: Any):
        from codex_image.client import ImageResult

        with self._request_lock:
            self.generate_calls.append(kwargs)
            call_number = len(self.generate_calls)
            self._active_requests += 1
            if self._active_requests == 2:
                self.two_requests_active.set()
        try:
            self.release_requests.wait(timeout=5)
            return ImageResult(
                f"api-active-{call_number}".encode("utf-8"),
                f"api active revised {call_number}",
                "png",
                kwargs["size"],
                "auto",
                kwargs["quality"],
                {"call_number": call_number},
            )
        finally:
            with self._request_lock:
                self._active_requests -= 1

    def generate_images(self, **kwargs: Any):
        self.generate_images_calls.append(kwargs)
        raise AssertionError("direct Images API should issue separate single-image requests")


class ProviderSwitchRetryApiImageClient(CapturingApiImageClient):
    instances: list["ProviderSwitchRetryApiImageClient"] = []
    calls_by_base_url: dict[str, int] = {}

    @classmethod
    def reset(cls) -> None:
        cls.instances = []
        cls.calls_by_base_url = {}

    def generate_image(self, **kwargs: Any):
        from codex_image.client import ImageResult

        self.generate_calls.append(kwargs)
        type(self).calls_by_base_url[self.base_url] = type(self).calls_by_base_url.get(self.base_url, 0) + 1
        call_number = type(self).calls_by_base_url[self.base_url]
        if "vendor-b" in self.base_url and call_number >= 2:
            raise RuntimeError("OpenAI-compatible images request failed: HTTP 502: vendor-b temporary failure")
        return ImageResult(
            f"provider-switch-{self.base_url}-{call_number}".encode("utf-8"),
            f"provider switch revised {call_number}",
            "png",
            kwargs["size"],
            "auto",
            kwargs["quality"],
            {"call_number": call_number},
        )


class SharedConcurrentApiImageClient(CapturingApiImageClient):
    instances: list["SharedConcurrentApiImageClient"] = []
    generate_call_count = 0
    active_requests = 0
    max_active_requests = 0
    request_lock = threading.Lock()

    def __init__(self, *, api_key: str, base_url: str, image_model: str, **kwargs: Any) -> None:
        self.generate_images_calls: list[dict[str, Any]] = []
        super().__init__(api_key=api_key, base_url=base_url, image_model=image_model, **kwargs)

    @classmethod
    def reset(cls) -> None:
        cls.instances = []
        cls.generate_call_count = 0
        cls.active_requests = 0
        cls.max_active_requests = 0

    def generate_image(self, **kwargs: Any):
        from codex_image.client import ImageResult

        with self.request_lock:
            self.generate_calls.append(kwargs)
            type(self).generate_call_count += 1
            call_number = type(self).generate_call_count
            type(self).active_requests += 1
            type(self).max_active_requests = max(type(self).max_active_requests, type(self).active_requests)
        try:
            time.sleep(0.05)
            return ImageResult(
                f"api-shared-{call_number}".encode("utf-8"),
                f"api shared revised {call_number}",
                "png",
                kwargs["size"],
                "auto",
                kwargs["quality"],
                {"call_number": call_number},
            )
        finally:
            with self.request_lock:
                type(self).active_requests -= 1

    def generate_images(self, **kwargs: Any):
        self.generate_images_calls.append(kwargs)
        raise AssertionError("direct Images API should issue separate single-image requests")


class PartiallyFailingConcurrentApiImageClient(CapturingApiImageClient):
    instances: list["PartiallyFailingConcurrentApiImageClient"] = []

    def __init__(self, *, api_key: str, base_url: str, image_model: str, **kwargs: Any) -> None:
        self.generate_images_calls: list[dict[str, Any]] = []
        self.max_active_requests = 0
        self._active_requests = 0
        self._request_lock = threading.Lock()
        super().__init__(api_key=api_key, base_url=base_url, image_model=image_model, **kwargs)

    def _begin_request(self) -> None:
        with self._request_lock:
            self._active_requests += 1
            self.max_active_requests = max(self.max_active_requests, self._active_requests)

    def _end_request(self) -> None:
        with self._request_lock:
            self._active_requests -= 1

    def generate_image(self, **kwargs: Any):
        from codex_image.client import ImageResult

        with self._request_lock:
            self.generate_calls.append(kwargs)
            call_number = len(self.generate_calls)
        self._begin_request()
        try:
            time.sleep(0.05)
            if call_number <= 2:
                return ImageResult(
                    f"api-partial-{call_number}".encode("utf-8"),
                    f"api partial revised {call_number}",
                    "png",
                    kwargs["size"],
                    "auto",
                    kwargs["quality"],
                    {"call_number": call_number},
                )
            if call_number == 3:
                raise RuntimeError(
                    'OpenAI-compatible images request failed: HTTP 403: {"error":'
                    '{"code":"insufficient_user_quota","message":"预扣费额度失败, 余额不足"}}'
                )
            raise RuntimeError("OpenAI-compatible images request failed: HTTP 502: ")
        finally:
            self._end_request()

    def generate_images(self, **kwargs: Any):
        self.generate_images_calls.append(kwargs)
        raise AssertionError("direct Images API should issue separate single-image requests")


class QuotaLimitedApiImageClient(CapturingApiImageClient):
    instances: list["QuotaLimitedApiImageClient"] = []

    def __init__(self, *, api_key: str, base_url: str, image_model: str, **kwargs: Any) -> None:
        self.generate_images_calls: list[dict[str, Any]] = []
        super().__init__(api_key=api_key, base_url=base_url, image_model=image_model, **kwargs)

    def generate_image(self, **kwargs: Any):
        self.generate_calls.append(kwargs)
        raise RuntimeError(
            'OpenAI-compatible images request failed: HTTP 403: {"error":'
            '{"code":"insufficient_user_quota","message":"预扣费额度失败, 余额不足"}}'
        )

    def generate_images(self, **kwargs: Any):
        self.generate_images_calls.append(kwargs)
        raise AssertionError("direct Images API should issue separate single-image requests")


class CapturingApiResponsesImageClient(FakeImageClient):
    instances: list["CapturingApiResponsesImageClient"] = []

    def __init__(self, *, api_key: str, base_url: str, image_model: str, **_: Any) -> None:
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url
        self.image_model = image_model
        self.instances.append(self)


class SlowImageClient(FakeImageClient):
    def __init__(self, delay_seconds: float = 0.2) -> None:
        super().__init__()
        self.delay_seconds = delay_seconds

    def generate_image(self, **kwargs: Any):
        time.sleep(self.delay_seconds)
        return super().generate_image(**kwargs)


class BlockingFirstImageClient(FakeImageClient):
    def __init__(self) -> None:
        super().__init__()
        self.first_call_started = threading.Event()
        self.release_first_call = threading.Event()
        self.second_call_started = threading.Event()

    def generate_image(self, **kwargs: Any):
        from codex_image.client import ImageResult

        self.generate_calls.append(kwargs)
        call_number = len(self.generate_calls)
        if call_number == 1:
            self.first_call_started.set()
            self.release_first_call.wait(timeout=5)
        if call_number == 2:
            self.second_call_started.set()
        return ImageResult(
            f"generated-{call_number}".encode("utf-8"),
            f"revised-{call_number}",
            "png",
            kwargs["size"],
            "auto",
            kwargs["quality"],
            {"call": call_number},
        )


class BlockingSecondImageClient(FakeImageClient):
    def __init__(self) -> None:
        super().__init__()
        self.second_call_started = threading.Event()
        self.release_second_call = threading.Event()

    def generate_image(self, **kwargs: Any):
        from codex_image.client import ImageResult

        self.generate_calls.append(kwargs)
        call_number = len(self.generate_calls)
        if call_number == 2:
            self.second_call_started.set()
            self.release_second_call.wait(timeout=5)
        return ImageResult(
            f"generated-{call_number}".encode("utf-8"),
            f"revised-{call_number}",
            "png",
            kwargs["size"],
            "auto",
            kwargs["quality"],
            {"call": call_number},
        )


class SlowFourthImageClient(FakeImageClient):
    def __init__(self, delay_seconds: float = 0.2) -> None:
        super().__init__()
        self.delay_seconds = delay_seconds

    def generate_image(self, **kwargs: Any):
        from codex_image.client import ImageResult

        self.generate_calls.append(kwargs)
        call_number = len(self.generate_calls)
        if call_number == 4:
            time.sleep(self.delay_seconds)
        return ImageResult(
            f"generated-{call_number}".encode("utf-8"),
            f"revised-{call_number}",
            "png",
            kwargs["size"],
            "auto",
            kwargs["quality"],
            {"call": call_number},
        )


class BlockingFourthImageClient(FakeImageClient):
    def __init__(self) -> None:
        super().__init__()
        self.fourth_call_started = threading.Event()
        self.second_task_started = threading.Event()
        self.release_fourth_call = threading.Event()

    def generate_image(self, **kwargs: Any):
        from codex_image.client import ImageResult

        self.generate_calls.append(kwargs)
        call_number = len(self.generate_calls)
        if call_number == 4:
            self.fourth_call_started.set()
            self.release_fourth_call.wait(timeout=1)
        if call_number >= 5:
            self.second_task_started.set()
        return ImageResult(
            f"generated-{call_number}".encode("utf-8"),
            f"revised-{call_number}",
            "png",
            kwargs["size"],
            "auto",
            kwargs["quality"],
            {"call": call_number},
        )


class FailsSecondImageClient(FakeImageClient):
    def generate_image(self, **kwargs: Any):
        from codex_image.client import ImageResult

        self.generate_calls.append(kwargs)
        call_number = len(self.generate_calls)
        if call_number in {2, 3}:
            raise RuntimeError("temporary server failure")
        return ImageResult(
            f"generated-{call_number}".encode("utf-8"),
            f"revised-{call_number}",
            "png",
            kwargs["size"],
            "auto",
            kwargs["quality"],
            {"call": call_number},
        )


class QuotaLimitedImageClient(FakeImageClient):
    def generate_image(self, **kwargs: Any):
        self.generate_calls.append(kwargs)
        raise RuntimeError("Codex usage limit reached: The usage limit has been reached (resets in 9h 3m)")


class QuotaLimitedAfterFirstImageClient(FakeImageClient):
    def generate_image(self, **kwargs: Any):
        from codex_image.client import ImageResult

        self.generate_calls.append(kwargs)
        call_number = len(self.generate_calls)
        if call_number > 1:
            raise RuntimeError("Codex usage limit reached: The usage limit has been reached (resets in 9h 3m)")
        return ImageResult(
            b"generated-1",
            "revised-1",
            "png",
            kwargs["size"],
            "auto",
            kwargs["quality"],
            {"call": call_number},
        )


class QuotaLimitedOnceImageClient(FakeImageClient):
    def generate_image(self, **kwargs: Any):
        from codex_image.client import ImageResult

        self.generate_calls.append(kwargs)
        if len(self.generate_calls) == 1:
            raise RuntimeError("Codex usage limit reached: The usage limit has been reached (resets in 9h 3m)")
        return ImageResult(b"generated", "revised", "png", kwargs["size"], "auto", kwargs["quality"], {})


class InvalidRequestImageClient(FakeImageClient):
    def generate_image(self, **kwargs: Any):
        self.generate_calls.append(kwargs)
        raise RuntimeError(
            'Codex responses request failed: HTTP 400: {"error":'
            '{"type":"invalid_request_error","code":"invalid_value"}}'
        )


class CancelsTaskBeforeReturningImageClient(FakeImageClient):
    def __init__(self) -> None:
        super().__init__()
        self.storage: Any | None = None
        self.task_id = ""

    def generate_image(self, **kwargs: Any):
        from codex_image.client import ImageResult
        from codex_image.webui.storage import utc_now

        self.generate_calls.append(kwargs)
        metadata = self.storage.read_metadata(self.task_id)
        metadata["status"] = "failed"
        metadata["cancel_requested"] = True
        metadata["cancelled_at"] = utc_now()
        metadata["updated_at"] = metadata["cancelled_at"]
        metadata["error"] = "Task cancelled by user."
        metadata["last_error"] = metadata["error"]
        self.storage.write_metadata(self.task_id, metadata)
        return ImageResult(b"generated-after-cancel", "late revised", "png", kwargs["size"], "auto", kwargs["quality"], {})


class QueueTestExecutor:
    def __init__(self) -> None:
        self.started: list[tuple[str, str]] = []
        self.fail_once_for: set[str] = set()

    async def __call__(self, task_id: str, channel: Any, is_final_attempt: bool) -> None:
        self.started.append((task_id, channel.channel_id))
        if task_id in self.fail_once_for:
            self.fail_once_for.remove(task_id)
            raise RuntimeError("temporary auth failure")


class AlwaysFailQueueTestExecutor:
    def __init__(self) -> None:
        self.final_attempts: list[bool] = []

    async def __call__(self, task_id: str, channel: Any, is_final_attempt: bool) -> None:
        self.final_attempts.append(is_final_attempt)
        raise RuntimeError("temporary auth failure")


class FailFastSlowCompleteQueueTestExecutor:
    def __init__(self) -> None:
        self.completed: list[str] = []

    async def __call__(self, task_id: str, channel: Any, is_final_attempt: bool) -> None:
        if task_id == "task-a":
            await asyncio.sleep(0)
            raise RuntimeError("temporary auth failure")
        await asyncio.sleep(0.01)
        self.completed.append(task_id)


class CancelQueueTestExecutor:
    async def __call__(self, task_id: str, channel: Any, is_final_attempt: bool) -> None:
        raise asyncio.CancelledError()


class BlockingFirstQueueTestExecutor:
    def __init__(self) -> None:
        self.started: list[tuple[str, str]] = []
        self.completed: list[str] = []
        self.first_started: asyncio.Event | None = None
        self.release_first: asyncio.Event | None = None

    async def __call__(self, task_id: str, channel: Any, is_final_attempt: bool) -> None:
        del is_final_attempt
        self.started.append((task_id, channel.channel_id))
        if task_id == "task-a":
            assert self.first_started is not None
            assert self.release_first is not None
            self.first_started.set()
            await self.release_first.wait()
        self.completed.append(task_id)


def metadata_path(root: Path, task_id: str) -> Path:
    legacy_path = root / "source-data" / f"{task_id}.metadata.json"
    sharded_path = root / "source-data" / "tasks" / f"{task_id[:4]}-{task_id[4:6]}-{task_id[6:8]}" / f"{task_id}.metadata.json"
    if legacy_path.exists() and not sharded_path.exists():
        return legacy_path
    return sharded_path


def request_path(root: Path, task_id: str) -> Path:
    legacy_path = root / "source-data" / f"{task_id}.request.json"
    sharded_path = root / "source-data" / "tasks" / f"{task_id[:4]}-{task_id[4:6]}-{task_id[6:8]}" / f"{task_id}.request.json"
    if legacy_path.exists() and not sharded_path.exists():
        return legacy_path
    return sharded_path


def input_name(task_id: str, filename: str, *, kind: str = "input", index: int = 1) -> str:
    return f"{task_id}-{kind}-{index:02d}-{filename}"


def output_date_dir(task_id: str) -> str:
    if len(task_id) >= 8 and task_id[:8].isdigit():
        return f"{task_id[:4]}-{task_id[4:6]}-{task_id[6:8]}"
    return "undated"


def output_name(task_id: str, index: int = 1, suffix: str = "png") -> str:
    return f"{output_date_dir(task_id)}/{task_id}-image-{index}.{suffix}"


def output_url(task_id: str, index: int = 1, suffix: str = "png") -> str:
    return f"/outputs/{output_name(task_id, index, suffix)}"



class WebUIStaticTestCase(unittest.TestCase):
    def assertCloseButtonUsesConsistentX(self, html: str, button_id: str, aria_label: str) -> None:
        self.assertRegex(
            html,
            rf'<button id="{re.escape(button_id)}" class="ghost-button drawer-close-button" type="button" aria-label="{re.escape(aria_label)}" title="关闭"[^>]*>\s*'
            rf'<svg class="drawer-close-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">\s*'
            rf'<path d="M7 7L17 17M17 7L7 17" />\s*</svg>\s*</button>',
        )

    def _assert_valid_javascript(self, node: str, script: str, label: str) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8") as temp_file:
            temp_file.write(script)
            temp_file.flush()
            result = subprocess.run(
                [node, "--check", temp_file.name],
                check=False,
                text=True,
                capture_output=True,
            )

        self.assertEqual(result.returncode, 0, f"{label} has invalid JavaScript:\n{result.stderr}")

    def _assert_bootstrap_proxy(self, bootstrap_source: str, function_name: str) -> None:
        self.assertNotRegex(bootstrap_source, rf"\n(?:async\s+)?function {function_name}\(")
        self.assertIn(f'{function_name}: proxy("{function_name}")', bootstrap_source)

    def _frontend_script_source(self) -> str:
        source_path = Path("codex_image/webui/frontend/legacy-app.js")
        src_dir = Path("codex_image/webui/frontend/src")
        if source_path.exists():
            sources = [source_path.read_text(encoding="utf-8")]
            ordered_sources = [
                "state-defaults.ts",
                "elements.ts",
                "webui-utils.ts",
                "runtime-feedback.ts",
                "form-controls.ts",
                "task-derived.ts",
                "task-preview.ts",
                "tasks.ts",
                "task-list-render.ts",
                "task-archive-controls.ts",
                "task-batch-controls.ts",
                "task-actions.ts",
                "task-submit.ts",
                "task-selection.ts",
                "prompt.ts",
                "prompt-serialization.ts",
                "prompt-gallery-chips.ts",
                "prompt-editor-paste.ts",
                "prompt-editor-events.ts",
                "prompt-model.ts",
                "prompt-colors.ts",
                "prompt-snippets.ts",
                "input-sources.ts",
                "image-strip.ts",
                "gallery-categories.ts",
                "recent-assets.ts",
                "quick-gallery.ts",
                "gallery-grid.ts",
                "gallery-item-actions.ts",
                "gallery.ts",
                "api-settings.ts",
                "storage-settings.ts",
                "color-palette.ts",
                "task-list-controls.ts",
                "task-notifications.ts",
                "overlay-popovers.ts",
                "shell-ui.ts",
                "lightbox.ts",
                "image-editor.ts",
                "legacy-bridge.ts",
                "event-bindings.ts",
                "boot.ts",
                "bootstrap.ts",
                "main.ts",
            ]
            seen_paths = set()
            for name in ordered_sources:
                path = src_dir / name
                if path.exists():
                    sources.append(self._javascript_like_typescript_source(path))
                    seen_paths.add(path)
            sources.extend(
                self._javascript_like_typescript_source(path)
                for path in sorted(src_dir.glob("*.ts"))
                if path not in seen_paths
            )
            return "\n".join(sources)
        return Path("codex_image/webui/static/app.js").read_text(encoding="utf-8")

    def _frontend_bundle_source(self) -> str:
        return Path("codex_image/webui/static/app.js").read_text(encoding="utf-8")

    def _queue_source(self) -> str:
        return Path("codex_image/webui/frontend/src/queue.ts").read_text(encoding="utf-8")

    def _task_source(self) -> str:
        return Path("codex_image/webui/frontend/src/tasks.ts").read_text(encoding="utf-8")

    def _task_list_render_source(self) -> str:
        return Path("codex_image/webui/frontend/src/task-list-render.ts").read_text(encoding="utf-8")

    def _task_history_anchors_source(self) -> str:
        return Path("codex_image/webui/frontend/src/task-history-anchors.ts").read_text(encoding="utf-8")

    def _task_actions_source(self) -> str:
        return Path("codex_image/webui/frontend/src/task-actions.ts").read_text(encoding="utf-8")

    def _task_submit_source(self) -> str:
        return Path("codex_image/webui/frontend/src/task-submit.ts").read_text(encoding="utf-8")

    def _task_batch_controls_source(self) -> str:
        return Path("codex_image/webui/frontend/src/task-batch-controls.ts").read_text(encoding="utf-8")

    def _task_archive_controls_source(self) -> str:
        return Path("codex_image/webui/frontend/src/task-archive-controls.ts").read_text(encoding="utf-8")

    def _task_derived_source(self) -> str:
        return Path("codex_image/webui/frontend/src/task-derived.ts").read_text(encoding="utf-8")

    def _task_preview_source(self) -> str:
        return Path("codex_image/webui/frontend/src/task-preview.ts").read_text(encoding="utf-8")

    def _task_selection_source(self) -> str:
        return Path("codex_image/webui/frontend/src/task-selection.ts").read_text(encoding="utf-8")

    def _task_notifications_source(self) -> str:
        return Path("codex_image/webui/frontend/src/task-notifications.ts").read_text(encoding="utf-8")

    def _prompt_source(self) -> str:
        return Path("codex_image/webui/frontend/src/prompt.ts").read_text(encoding="utf-8")

    def _prompt_serialization_source(self) -> str:
        return Path("codex_image/webui/frontend/src/prompt-serialization.ts").read_text(encoding="utf-8")

    def _prompt_gallery_chips_source(self) -> str:
        return Path("codex_image/webui/frontend/src/prompt-gallery-chips.ts").read_text(encoding="utf-8")

    def _prompt_editor_events_source(self) -> str:
        return Path("codex_image/webui/frontend/src/prompt-editor-events.ts").read_text(encoding="utf-8")

    def _prompt_editor_paste_source(self) -> str:
        return Path("codex_image/webui/frontend/src/prompt-editor-paste.ts").read_text(encoding="utf-8")

    def _prompt_model_source(self) -> str:
        return Path("codex_image/webui/frontend/src/prompt-model.ts").read_text(encoding="utf-8")

    def _prompt_colors_source(self) -> str:
        return Path("codex_image/webui/frontend/src/prompt-colors.ts").read_text(encoding="utf-8")

    def _prompt_snippets_source(self) -> str:
        return Path("codex_image/webui/frontend/src/prompt-snippets.ts").read_text(encoding="utf-8")

    def _prompt_templates_source(self) -> str:
        return Path("codex_image/webui/frontend/src/prompt-templates.ts").read_text(encoding="utf-8")

    def _input_sources_source(self) -> str:
        return Path("codex_image/webui/frontend/src/input-sources.ts").read_text(encoding="utf-8")

    def _image_strip_source(self) -> str:
        return Path("codex_image/webui/frontend/src/image-strip.ts").read_text(encoding="utf-8")

    def _gallery_source(self) -> str:
        return Path("codex_image/webui/frontend/src/gallery.ts").read_text(encoding="utf-8")

    def _gallery_categories_source(self) -> str:
        return Path("codex_image/webui/frontend/src/gallery-categories.ts").read_text(encoding="utf-8")

    def _recent_assets_source(self) -> str:
        return Path("codex_image/webui/frontend/src/recent-assets.ts").read_text(encoding="utf-8")

    def _quick_gallery_source(self) -> str:
        return Path("codex_image/webui/frontend/src/quick-gallery.ts").read_text(encoding="utf-8")

    def _gallery_grid_source(self) -> str:
        return Path("codex_image/webui/frontend/src/gallery-grid.ts").read_text(encoding="utf-8")

    def _gallery_item_actions_source(self) -> str:
        return Path("codex_image/webui/frontend/src/gallery-item-actions.ts").read_text(encoding="utf-8")

    def _api_settings_source(self) -> str:
        return Path("codex_image/webui/frontend/src/api-settings.ts").read_text(encoding="utf-8")

    def _storage_settings_source(self) -> str:
        return Path("codex_image/webui/frontend/src/storage-settings.ts").read_text(encoding="utf-8")

    def _color_palette_source(self) -> str:
        return Path("codex_image/webui/frontend/src/color-palette.ts").read_text(encoding="utf-8")

    def _form_controls_source(self) -> str:
        return Path("codex_image/webui/frontend/src/form-controls.ts").read_text(encoding="utf-8")

    def _task_list_controls_source(self) -> str:
        return Path("codex_image/webui/frontend/src/task-list-controls.ts").read_text(encoding="utf-8")

    def _task_list_queue_controls_source(self) -> str:
        return Path("codex_image/webui/frontend/src/task-list-queue-controls.ts").read_text(encoding="utf-8")

    def _overlay_popovers_source(self) -> str:
        return Path("codex_image/webui/frontend/src/overlay-popovers.ts").read_text(encoding="utf-8")

    def _shell_ui_source(self) -> str:
        return Path("codex_image/webui/frontend/src/shell-ui.ts").read_text(encoding="utf-8")

    def _lightbox_source(self) -> str:
        return Path("codex_image/webui/frontend/src/lightbox.ts").read_text(encoding="utf-8")

    def _image_editor_source(self) -> str:
        return Path("codex_image/webui/frontend/src/image-editor.ts").read_text(encoding="utf-8")

    def _javascript_like_typescript_source(self, path: Path) -> str:
        source = path.read_text(encoding="utf-8")
        source = re.sub(r":\s*any\[\](?=\s*[,)=])", "", source)
        source = re.sub(r":\s*(?:any|unknown|string|number|boolean|Event|KeyboardEvent|ClipboardEvent)(?=\s*[,)=])", "", source)
        source = re.sub(r"\)\s*:\s*[^({=>\n]+(?=\s*\{)", ")", source)
        return source

    def _state_source(self) -> str:
        return Path("codex_image/webui/frontend/src/state.ts").read_text(encoding="utf-8")

    def _dom_source(self) -> str:
        return Path("codex_image/webui/frontend/src/dom.ts").read_text(encoding="utf-8")

    def _bootstrap_source(self) -> str:
        return Path("codex_image/webui/frontend/src/bootstrap.ts").read_text(encoding="utf-8")

    def _elements_source(self) -> str:
        return Path("codex_image/webui/frontend/src/elements.ts").read_text(encoding="utf-8")

    def _runtime_feedback_source(self) -> str:
        return Path("codex_image/webui/frontend/src/runtime-feedback.ts").read_text(encoding="utf-8")

    def _state_defaults_source(self) -> str:
        return Path("codex_image/webui/frontend/src/state-defaults.ts").read_text(encoding="utf-8")

    def _extract_javascript_function(self, script: str, function_name: str) -> str:
        marker = f"function {function_name}("
        start = script.index(marker)
        brace_start = script.index("{", start)
        depth = 0
        for index in range(brace_start, len(script)):
            char = script[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return script[start:index + 1]
        raise AssertionError(f"Could not extract JavaScript function {function_name}")

    def _extract_css_block(self, styles: str, selector: str) -> str:
        match = re.search(rf"{re.escape(selector)}\s*\{{[^}}]*\}}", styles)
        if not match:
            raise AssertionError(f"CSS block {selector} not found")
        return match.group(0)
