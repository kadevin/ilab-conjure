from __future__ import annotations

import base64
import contextlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised by Windows portable builds.
    fcntl = None

from .http import Transport, UrllibTransport
from .atomic_files import atomic_write_text

DEFAULT_AUTH_PATH = Path.home() / ".codex" / "auth.json"
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"


class AuthNeedsLoginError(RuntimeError):
    """Raised when local Codex OAuth credentials cannot be refreshed."""


@dataclass
class AuthState:
    path: Path
    access_token: str
    refresh_token: str
    id_token: str
    account_id: str
    last_refresh: str | None
    raw: dict[str, Any]


def load_auth_state(path: str | Path | None = None) -> AuthState:
    auth_path = Path(path) if path is not None else DEFAULT_AUTH_PATH
    payload = json.loads(auth_path.read_text(encoding="utf-8"))
    tokens = payload.get("tokens", payload)
    return AuthState(
        path=auth_path,
        access_token=str(tokens.get("access_token", "")),
        refresh_token=str(tokens.get("refresh_token", "")),
        id_token=str(tokens.get("id_token", "")),
        account_id=str(tokens.get("account_id", "")),
        last_refresh=payload.get("last_refresh"),
        raw=payload,
    )


def refresh_auth_state(
    state: AuthState,
    *,
    transport: Transport | None = None,
    token_url: str = TOKEN_URL,
    client_id: str = CLIENT_ID,
) -> AuthState:
    if not state.refresh_token:
        raise RuntimeError("Codex auth file has no refresh token")

    transport = transport or UrllibTransport()
    with _auth_refresh_lock(state.path):
        latest_state = _load_newer_auth_state_if_refresh_rotated(state)
        if latest_state is not state:
            return latest_state

        return _refresh_auth_state_unlocked(
            latest_state,
            transport=transport,
            token_url=token_url,
            client_id=client_id,
        )


def _refresh_auth_state_unlocked(
    state: AuthState,
    *,
    transport: Transport,
    token_url: str,
    client_id: str,
) -> AuthState:
    body = urlencode(
        {
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": state.refresh_token,
            "scope": "openid profile email",
        }
    ).encode("utf-8")
    response = transport.request(
        method="POST",
        url=token_url,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        body=body,
    )
    if response.status != 200:
        body_text = response.body.decode("utf-8", errors="replace")
        if _is_reused_refresh_token_error(body_text):
            raise AuthNeedsLoginError(
                "Codex login has expired because the stored refresh token was already used. "
                "Run `codex logout` and then `codex login` to create a fresh ~/.codex/auth.json."
            )
        raise RuntimeError(f"Token refresh failed: HTTP {response.status}: {body_text}")

    token_payload = json.loads(response.body.decode("utf-8"))
    return _persist_refreshed_tokens(state, token_payload)


@contextlib.contextmanager
def _auth_refresh_lock(auth_path: Path):
    lock_path = auth_path.with_suffix(auth_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock_file:
        if fcntl is None:
            yield
            return
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _load_newer_auth_state_if_refresh_rotated(state: AuthState) -> AuthState:
    try:
        latest_state = load_auth_state(state.path)
    except Exception:
        return state
    if latest_state.refresh_token and latest_state.refresh_token != state.refresh_token:
        return latest_state
    return state


def _is_reused_refresh_token_error(body_text: str) -> bool:
    try:
        payload = json.loads(body_text)
    except json.JSONDecodeError:
        return "refresh_token_reused" in body_text
    error = payload.get("error")
    if isinstance(error, dict):
        return error.get("code") == "refresh_token_reused" or "refresh token has already been used" in str(error.get("message", ""))
    return False


def decode_jwt_claims(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload + padding)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def _persist_refreshed_tokens(state: AuthState, token_payload: dict[str, Any]) -> AuthState:
    now = datetime.now(UTC).isoformat()
    raw = dict(state.raw)
    tokens = dict(raw.get("tokens", {}))

    access_token = str(token_payload.get("access_token") or state.access_token)
    refresh_token = str(token_payload.get("refresh_token") or state.refresh_token)
    id_token = str(token_payload.get("id_token") or state.id_token)
    claims = decode_jwt_claims(id_token)
    account_id = _extract_account_id(claims) or state.account_id

    tokens.update(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "id_token": id_token,
            "account_id": account_id,
        }
    )
    raw["tokens"] = tokens
    raw["last_refresh"] = now
    try:
        # Preserve a user-managed auth symlink while replacing its destination
        # atomically. A failed write must never truncate the shared login file.
        atomic_write_text(state.path.resolve(), json.dumps(raw, indent=2), mode=0o600)
    except OSError as exc:
        raise OSError(
            "Refreshed Codex credentials could not be saved. The previous auth file "
            "was preserved; fix the storage error and run `codex login` if the "
            "refresh token was already rotated."
        ) from exc

    return AuthState(
        path=state.path,
        access_token=access_token,
        refresh_token=refresh_token,
        id_token=id_token,
        account_id=account_id,
        last_refresh=now,
        raw=raw,
    )


def _extract_account_id(claims: dict[str, Any]) -> str:
    auth_claim = claims.get("https://api.openai.com/auth")
    if isinstance(auth_claim, dict):
        return str(auth_claim.get("chatgpt_account_id") or auth_claim.get("account_id") or "")
    return str(claims.get("account_id") or "")
