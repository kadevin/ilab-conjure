from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .auth import AuthState

DEFAULT_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
DEFAULT_CODEX_IMAGES_BASE_URL = "https://chatgpt.com/backend-api/codex"
DEFAULT_OPENAI_API_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MAIN_MODEL = "gpt-5.4-mini"
DEFAULT_IMAGE_MODEL = "gpt-image-2"


def image_model_supports_input_fidelity(model: str | None) -> bool:
    return (model or "").lower() != "gpt-image-2"


@dataclass
class ImageResult:
    image_bytes: bytes
    revised_prompt: str
    output_format: str
    size: str
    background: str
    quality: str
    usage: dict[str, Any]
    tool_usage: dict[str, Any] = field(default_factory=dict)


class AuthProvider(Protocol):
    def next_auth_state(self) -> AuthState:
        ...

    def next_auth_state_after_unauthorized(self, current_state: AuthState) -> AuthState | None:
        ...

    def available_count(self) -> int:
        ...
