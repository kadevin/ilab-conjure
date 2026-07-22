from __future__ import annotations

from typing import Literal


AuthScheme = Literal["bearer", "x-goog-api-key", "codex_login"]


_AUTH_BY_PROTOCOL: dict[str, AuthScheme] = {
    "codex_images": "codex_login",
    "codex_responses": "codex_login",
    "openai_images": "bearer",
    "openai_responses": "bearer",
    "gemini_generate_content": "x-goog-api-key",
    "gemini_change2pro_generate_content": "x-goog-api-key",
    "t8_images": "bearer",
    "openrouter_images": "bearer",
}


def auth_scheme_for_protocol(protocol_profile: str) -> AuthScheme:
    try:
        return _AUTH_BY_PROTOCOL[protocol_profile]
    except KeyError as exc:
        raise ValueError("unknown_protocol_auth_scheme") from exc


__all__ = ("AuthScheme", "auth_scheme_for_protocol")
