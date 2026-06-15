from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
