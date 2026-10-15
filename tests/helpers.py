from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest import TestCase


TEST_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAIAAAB7QOjd"
    "AAAAD0lEQVR4nGPkUbJgYGAAAAHgAGimn4WSAAAAAElFTkSuQmCC"
)
TEST_PNG_BYTES = base64.b64decode(TEST_PNG_BASE64)
TEST_JPEG_BASE64 = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8U"
    "HRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgN"
    "DRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
    "MjIyMjL/wAARCAABAAIDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQF"
    "BgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEI"
    "I0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNk"
    "ZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLD"
    "xMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEB"
    "AQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJB"
    "UQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZH"
    "SElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaan"
    "qKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oA"
    "DAMBAAIRAxEAPwDx2iiiu04z/9k="
)
TEST_JPEG_BYTES = base64.b64decode(TEST_JPEG_BASE64)
TEST_WEBP_BASE64 = (
    "UklGRjAAAABXRUJQVlA4ICQAAABQAQCdASoCAAEAAUAmJQBOgC6gAP77LkvF3YjjJ4dVU9ffoAA="
)
TEST_WEBP_BYTES = base64.b64decode(TEST_WEBP_BASE64)


def history_storage(root: Path):
    from codex_image.webui.storage import TaskStorage

    return TaskStorage(
        root / "outputs", input_root=root / "inputs",
        source_data_root=root / "source-data",
    )


def assert_no_api_key(case: TestCase, value: object) -> None:
    if isinstance(value, dict):
        case.assertNotIn("api_key", value)
        for nested in value.values():
            assert_no_api_key(case, nested)
    elif isinstance(value, list):
        for nested in value:
            assert_no_api_key(case, nested)


@dataclass
class FakeResponse:
    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)


class FakeTransport:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
    ) -> FakeResponse:
        self.requests.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "body": body,
            }
        )
        if not self._responses:
            raise AssertionError("FakeTransport has no more queued responses")
        return self._responses.pop(0)


def write_auth_file(path: Path, *, access_token: str = "access-token", refresh_token: str = "refresh-token", id_token: str = "header.payload.sig", account_id: str = "acct-123") -> None:
    payload = {
        "OPENAI_API_KEY": None,
        "last_refresh": "2026-04-24T00:00:00Z",
        "tokens": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "id_token": id_token,
            "account_id": account_id,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def make_sse_completed_event(
    *,
    image_b64: str,
    revised_prompt: str = "revised prompt",
    size: str = "3840x2160",
    output_format: str = "png",
    quality: str = "high",
    background: str = "opaque",
    tool_usage: dict[str, Any] | None = None,
) -> bytes:
    if tool_usage is None:
        tool_usage = {
            "image_gen": {
                "input_tokens": 1,
                "output_tokens": 2,
                "total_tokens": 3,
            }
        }
    event = {
        "type": "response.completed",
        "response": {
            "created_at": 1710000000,
            "output": [
                {
                    "type": "image_generation_call",
                    "result": image_b64,
                    "revised_prompt": revised_prompt,
                    "size": size,
                    "output_format": output_format,
                    "quality": quality,
                    "background": background,
                }
            ],
            "tool_usage": tool_usage,
        },
    }
    return f"data: {json.dumps(event)}\n\n".encode("utf-8")
