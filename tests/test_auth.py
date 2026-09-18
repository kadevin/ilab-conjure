from __future__ import annotations

import base64
import json
import tempfile
import unittest
import os
import stat
from unittest.mock import patch
from pathlib import Path

from tests.helpers import FakeResponse, FakeTransport, write_auth_file


def _make_id_token(account_id: str) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode("ascii").rstrip("=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"https://api.openai.com/auth": {"chatgpt_account_id": account_id}}).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"{header}.{payload}.sig"


class AuthTests(unittest.TestCase):
    def test_failed_refresh_persistence_keeps_complete_original_json(self) -> None:
        from codex_image.auth import load_auth_state, refresh_auth_state

        for failure in ("create", "write", "sync", "replace", "permissions"):
            with self.subTest(failure=failure):
                write_auth_file(self.auth_path, access_token="old-access", refresh_token="old-refresh", account_id="acct-old")
                before = self.auth_path.read_bytes()
                transport = FakeTransport([FakeResponse(200, b'{"access_token":"new","refresh_token":"rotated"}', {})])
                target = {"create": "tempfile.mkstemp", "write": "os.fdopen", "sync": "os.fsync",
                          "replace": "os.replace", "permissions": "os.chmod"}[failure]
                original_fdopen = os.fdopen

                class PartialWrite:
                    def __init__(self, descriptor, mode):
                        self.handle = original_fdopen(descriptor, mode)
                    def __enter__(self):
                        return self
                    def __exit__(self, *args):
                        self.handle.close()
                    def write(self, data):
                        self.handle.write(data[:8])
                        self.handle.flush()
                        raise OSError(28, "synthetic disk full")

                effect = PartialWrite if failure == "write" else OSError(28, "synthetic failure")
                with patch("codex_image.atomic_files." + target, side_effect=effect):
                    with self.assertRaisesRegex(OSError, "could not be saved"):
                        refresh_auth_state(load_auth_state(self.auth_path), transport=transport)
                self.assertEqual(self.auth_path.read_bytes(), before)
                self.assertEqual(load_auth_state(self.auth_path).refresh_token, "old-refresh")
                self.assertEqual(list(self.auth_path.parent.glob(".auth.json.*.tmp")), [])

    def test_atomic_refresh_preserves_auth_symlink_and_private_permissions(self) -> None:
        from codex_image.auth import load_auth_state, refresh_auth_state
        destination = self.auth_path.with_name("shared.json")
        write_auth_file(destination, access_token="old", refresh_token="old-refresh", account_id="acct")
        self.auth_path.symlink_to(destination)
        transport = FakeTransport([FakeResponse(200, b'{"access_token":"new","refresh_token":"rotated"}', {})])
        refresh_auth_state(load_auth_state(self.auth_path), transport=transport)
        self.assertTrue(self.auth_path.is_symlink())
        self.assertEqual(load_auth_state(destination).refresh_token, "rotated")
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.auth_path = Path(self.tmpdir.name) / "auth.json"

    def test_load_auth_state_reads_codex_desktop_layout(self) -> None:
        write_auth_file(self.auth_path, access_token="abc", refresh_token="def", account_id="acct-xyz")

        from codex_image.auth import load_auth_state

        state = load_auth_state(self.auth_path)

        self.assertEqual(state.access_token, "abc")
        self.assertEqual(state.refresh_token, "def")
        self.assertEqual(state.account_id, "acct-xyz")
        self.assertEqual(state.path, self.auth_path)

    def test_refresh_auth_state_persists_new_tokens(self) -> None:
        write_auth_file(self.auth_path, access_token="old-access", refresh_token="old-refresh", account_id="acct-old")
        token_body = json.dumps(
            {
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "id_token": _make_id_token("acct-new"),
                "expires_in": 3600,
                "token_type": "Bearer",
            }
        ).encode("utf-8")
        transport = FakeTransport([FakeResponse(status=200, body=token_body, headers={"Content-Type": "application/json"})])

        from codex_image.auth import load_auth_state, refresh_auth_state

        refreshed = refresh_auth_state(load_auth_state(self.auth_path), transport=transport)

        self.assertEqual(refreshed.access_token, "new-access")
        self.assertEqual(refreshed.refresh_token, "new-refresh")
        self.assertEqual(refreshed.account_id, "acct-new")

        persisted = json.loads(self.auth_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["tokens"]["access_token"], "new-access")
        self.assertEqual(persisted["tokens"]["refresh_token"], "new-refresh")
        self.assertEqual(persisted["tokens"]["account_id"], "acct-new")
        self.assertEqual(transport.requests[0]["method"], "POST")
        self.assertIn("grant_type=refresh_token", transport.requests[0]["body"].decode("utf-8"))

    def test_refresh_auth_state_reuses_newer_auth_file_instead_of_old_refresh_token(self) -> None:
        write_auth_file(self.auth_path, access_token="old-access", refresh_token="old-refresh", account_id="acct-old")

        from codex_image.auth import load_auth_state, refresh_auth_state

        stale_state = load_auth_state(self.auth_path)
        write_auth_file(self.auth_path, access_token="fresh-access", refresh_token="fresh-refresh", account_id="acct-fresh")
        transport = FakeTransport([])

        refreshed = refresh_auth_state(stale_state, transport=transport)

        self.assertEqual(refreshed.access_token, "fresh-access")
        self.assertEqual(refreshed.refresh_token, "fresh-refresh")
        self.assertEqual(refreshed.account_id, "acct-fresh")
        self.assertEqual(transport.requests, [])

    def test_auth_refresh_lock_degrades_when_fcntl_is_unavailable(self) -> None:
        from codex_image import auth

        original_fcntl = auth.fcntl
        auth.fcntl = None
        self.addCleanup(setattr, auth, "fcntl", original_fcntl)

        with auth._auth_refresh_lock(self.auth_path):
            self.assertTrue(self.auth_path.with_suffix(".json.lock").exists())

    def test_refresh_auth_state_reports_reused_refresh_token_as_login_required(self) -> None:
        write_auth_file(self.auth_path, access_token="expired-access", refresh_token="reused-refresh", account_id="acct-old")
        error_body = json.dumps(
            {
                "error": {
                    "message": "Your refresh token has already been used to generate a new access token. Please try signing in again.",
                    "type": "invalid_request_error",
                    "code": "refresh_token_reused",
                }
            }
        ).encode("utf-8")
        transport = FakeTransport([FakeResponse(status=401, body=error_body, headers={"Content-Type": "application/json"})])

        from codex_image.auth import AuthNeedsLoginError, load_auth_state, refresh_auth_state

        with self.assertRaises(AuthNeedsLoginError) as cm:
            refresh_auth_state(load_auth_state(self.auth_path), transport=transport)

        self.assertIn("Codex login has expired", str(cm.exception))
        self.assertIn("codex logout", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
