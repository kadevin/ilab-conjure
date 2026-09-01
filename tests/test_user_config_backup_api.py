from __future__ import annotations

from pathlib import Path
import hashlib
import json
import tempfile
import time
import unittest
import zipfile

from fastapi.testclient import TestClient


class UserConfigBackupAPITests(unittest.TestCase):
    def _archive_bytes(self, root: Path) -> bytes:
        from codex_image.webui.user_config_backup_format import (
            USER_CONFIG_BACKUP_FORMAT,
        )

        colors = b'{"version":1,"favorites":[],"recent_colors":[],"recent_limit":6}'
        snippets = b'{"version":1,"snippets":[]}'
        members = {
            "chips/colors.json": colors,
            "chips/prompt-snippets.json": snippets,
        }
        manifest = {
            "format": USER_CONFIG_BACKUP_FORMAT,
            "format_version": 1,
            "app_version": "test",
            "created_at": "2026-08-21T12:00:00Z",
            "sections": ["chips"],
            "contains_secrets": False,
            "members": [
                {
                    "section": "chips",
                    "path": name,
                    "size_bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
                for name, data in members.items()
            ],
        }
        path = root / "restore.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in members.items():
                archive.writestr(name, data)
            archive.writestr("manifest.json", json.dumps(manifest).encode())
        return path.read_bytes()

    def _create_app(self, root: Path):
        from codex_image.webui.app import create_app

        settings_root = root / "settings"
        return create_app(
            output_root=root / "outputs",
            input_root=root / "inputs",
            source_data_root=root / "outputs" / "source-data",
            gallery_root=root / "inputs" / "gallery",
            reference_asset_root=root / "inputs" / "reference-assets",
            reference_file_root=root / "inputs" / "reference-files",
            user_config_backup_temp_root=root / "user-config-backup",
            auth_checker=lambda: True,
            auth_settings_path=settings_root / "auth.json",
            api_settings_path=settings_root / "api.json",
            network_egress_settings_path=settings_root / "network-egress.json",
            color_settings_path=settings_root / "colors.json",
            prompt_snippets_path=settings_root / "prompt-snippets.json",
            prompt_templates_path=settings_root / "prompt-templates.json",
            webui_settings_path=settings_root / "webui.json",
            auto_start_queue=False,
        )

    def _wait_terminal(self, client: TestClient, job_id: str) -> dict:
        for _ in range(100):
            response = client.get(f"/api/user-config-backups/{job_id}")
            self.assertEqual(response.status_code, 200)
            payload = response.json()["job"]
            if payload["status"] not in {"queued", "planning", "packing"}:
                return payload
            time.sleep(0.01)
        self.fail("backup job did not finish")

    def test_summary_create_poll_repeat_download_and_discard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._create_app(Path(tmp))
            with TestClient(app) as client:
                summary = client.get("/api/user-config-backups/summary")
                created = client.post(
                    "/api/user-config-backups",
                    json={
                        "sections": ["chips", "settings"],
                        "include_api_keys": False,
                        "client_preferences": {
                            "theme": "system",
                            "notifications": {"in_app": True, "system": False},
                        },
                    },
                )
                self.assertEqual(created.status_code, 200)
                job_id = created.json()["job"]["job_id"]
                job = self._wait_terminal(client, job_id)
                download = client.get(job["download_url"])
                second_download = client.get(
                    f"/api/user-config-backups/{job_id}/download"
                )

                discarded_job = client.post(
                    "/api/user-config-backups",
                    json={
                        "sections": ["chips"],
                        "include_api_keys": False,
                    },
                ).json()["job"]
                discarded_id = discarded_job["job_id"]
                self._wait_terminal(client, discarded_id)
                discarded = client.delete(
                    f"/api/user-config-backups/{discarded_id}"
                )

            self.assertEqual(summary.status_code, 200)
            self.assertEqual(
                [item["section"] for item in summary.json()["sections"]],
                ["chips", "gallery", "templates", "settings"],
            )
            self.assertEqual(job["status"], "ready")
            self.assertEqual(download.status_code, 200)
            self.assertEqual(download.headers["content-type"], "application/zip")
            self.assertEqual(download.headers.get("cache-control"), "no-store")
            self.assertIn(
                "ilab-conjure-user-config-",
                download.headers["content-disposition"],
            )
            self.assertEqual(second_download.status_code, 200)
            self.assertEqual(second_download.content, download.content)
            self.assertEqual(
                second_download.headers["content-type"],
                "application/zip",
            )
            self.assertEqual(discarded.status_code, 200)
            self.assertEqual(discarded.json()["job"]["status"], "expired")

    def test_summary_exposes_safe_gallery_failure_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._create_app(Path(tmp))

            def fail_summary():
                raise ValueError("user_config_backup_gallery_invalid")

            app.state.user_config_backup_planner.summary = fail_summary
            with TestClient(app) as client:
                response = client.get("/api/user-config-backups/summary")

            self.assertEqual(response.status_code, 409)
            self.assertEqual(
                response.json(),
                {"detail": {"code": "user_config_backup_gallery_invalid"}},
            )

    def test_create_request_is_strict_bounded_and_never_echoes_invalid_body(self) -> None:
        invalid_payloads = (
            {"sections": [], "include_api_keys": False},
            {"sections": ["chips", "chips"], "include_api_keys": False},
            {"sections": ["unknown"], "include_api_keys": False},
            {"sections": ["chips"], "include_api_keys": False, "extra": True},
            {"sections": ["chips"], "include_api_keys": 1},
            {
                "sections": ["chips"],
                "include_api_keys": False,
                "client_preferences": {
                    "theme": "dark",
                    "notifications": {"in_app": True, "system": False},
                },
            },
            {"sections": ["settings"], "include_api_keys": False},
            {"sections": ["chips"], "include_api_keys": True},
        )
        with tempfile.TemporaryDirectory() as tmp:
            app = self._create_app(Path(tmp))
            with TestClient(app) as client:
                responses = [
                    client.post("/api/user-config-backups", json=payload)
                    for payload in invalid_payloads
                ]
                oversized = client.post(
                    "/api/user-config-backups",
                    content=b'{"secret":"never-echo-sentinel","padding":"'
                    + b"x" * (1024 * 1024)
                    + b'"}',
                    headers={"content-type": "application/json"},
                )

        self.assertTrue(all(response.status_code == 422 for response in responses))
        self.assertTrue(
            all("never-echo-sentinel" not in response.text for response in responses)
        )
        self.assertEqual(oversized.status_code, 413)
        self.assertNotIn("never-echo-sentinel", oversized.text)

    def test_restore_upload_validate_get_and_cancel_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self._archive_bytes(root)
            app = self._create_app(root)
            with TestClient(app) as client:
                created = client.post(
                    "/api/user-config-restores",
                    json={"filename": "restore.zip", "size_bytes": len(payload)},
                )
                self.assertEqual(created.status_code, 200)
                session_id = created.json()["session"]["session_id"]
                uploaded = client.put(
                    f"/api/user-config-restores/{session_id}/chunks",
                    content=payload,
                    headers={
                        "content-type": "application/octet-stream",
                        "x-upload-offset": "0",
                        "x-chunk-sha256": hashlib.sha256(payload).hexdigest(),
                    },
                )
                validated = client.post(
                    f"/api/user-config-restores/{session_id}/validate"
                )
                snapshot = client.get(
                    f"/api/user-config-restores/{session_id}"
                )

                second = client.post(
                    "/api/user-config-restores",
                    json={"filename": "second.zip", "size_bytes": 10},
                )
                self.assertEqual(second.status_code, 409)
                cancelled = client.delete(
                    f"/api/user-config-restores/{session_id}"
                )

            self.assertEqual(uploaded.status_code, 200)
            self.assertEqual(uploaded.json()["session"]["status"], "uploaded")
            self.assertEqual(validated.status_code, 200)
            self.assertTrue(validated.json()["preview"]["restorable"])
            self.assertEqual(snapshot.status_code, 200)
            self.assertEqual(snapshot.json()["session"]["status"], "validated")
            self.assertEqual(cancelled.status_code, 200)
            self.assertTrue(cancelled.json()["cancelled"])

    def test_restore_control_and_chunk_requests_are_strict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._create_app(Path(tmp))
            with TestClient(app) as client:
                invalid = (
                    client.post(
                        "/api/user-config-restores",
                        json={"filename": "../escape.zip", "size_bytes": 10},
                    ),
                    client.post(
                        "/api/user-config-restores",
                        json={"filename": "backup.zip", "size_bytes": True},
                    ),
                    client.post(
                        "/api/user-config-restores",
                        json={"filename": "backup.zip", "size_bytes": 10, "extra": 1},
                    ),
                )
                created = client.post(
                    "/api/user-config-restores",
                    json={"filename": "backup.zip", "size_bytes": 10},
                )
                session_id = created.json()["session"]["session_id"]
                bad_chunk = client.put(
                    f"/api/user-config-restores/{session_id}/chunks",
                    content=b"data",
                    headers={
                        "x-upload-offset": "wrong",
                        "x-chunk-sha256": "0" * 64,
                    },
                )

            self.assertTrue(all(response.status_code == 422 for response in invalid))
            self.assertEqual(bad_chunk.status_code, 422)

    def test_restore_apply_supports_incremental_and_requires_replace_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self._archive_bytes(root)
            app = self._create_app(root)
            with TestClient(app) as client:
                created = client.post(
                    "/api/user-config-restores",
                    json={"filename": "restore.zip", "size_bytes": len(payload)},
                ).json()["session"]
                session_id = created["session_id"]
                client.put(
                    f"/api/user-config-restores/{session_id}/chunks",
                    content=payload,
                    headers={
                        "x-upload-offset": "0",
                        "x-chunk-sha256": hashlib.sha256(payload).hexdigest(),
                    },
                )
                preview = client.post(
                    f"/api/user-config-restores/{session_id}/validate"
                ).json()["preview"]
                replace_denied = client.post(
                    f"/api/user-config-restores/{session_id}/restore",
                    json={
                        "sections": ["chips"],
                        "mode": "replace",
                        "archive_sha256": preview["archive_sha256"],
                        "preview_revision": preview["preview_revision"],
                        "confirm_replace": False,
                    },
                )
                replace_blocked = client.post(
                    f"/api/user-config-restores/{session_id}/restore",
                    json={
                        "sections": ["chips"],
                        "mode": "replace",
                        "archive_sha256": preview["archive_sha256"],
                        "preview_revision": preview["preview_revision"],
                        "confirm_replace": True,
                    },
                )
                restored = client.post(
                    f"/api/user-config-restores/{session_id}/restore",
                    json={
                        "sections": ["chips"],
                        "mode": "incremental",
                        "archive_sha256": preview["archive_sha256"],
                        "preview_revision": preview["preview_revision"],
                        "confirm_replace": False,
                    },
                )

            self.assertEqual(replace_denied.status_code, 409)
            self.assertEqual(
                replace_denied.json()["detail"]["code"],
                "user_config_restore_confirm_replace_required",
            )
            self.assertEqual(replace_blocked.status_code, 409)
            self.assertEqual(
                replace_blocked.json()["detail"]["code"],
                "user_config_restore_empty_replace_blocked",
            )
            self.assertEqual(restored.status_code, 200)
            self.assertEqual(restored.json()["result"]["status"], "restored")


if __name__ == "__main__":
    unittest.main()
