from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from fastapi.testclient import TestClient
from tests.helpers import history_storage



class HistoryExportServiceTests(unittest.TestCase):

    def _write_task(
        self,
        storage,
        task_id: str,
        outputs: list[tuple[int, str, bytes, str]],
        *,
        prompt: str = "",
        prompt_for_model: str = "",
    ) -> list[Path]:
        records = []
        paths = []
        for index, output_format, data, revised_prompt in outputs:
            path = storage.write_output(
                task_id,
                data,
                output_format,
                index=index,
            )
            paths.append(path)
            records.append(
                {
                    "index": index,
                    "status": "completed",
                    "file": storage.output_file(path),
                    "revised_prompt": revised_prompt,
                }
            )
        storage.write_metadata(
            task_id,
            {
                "task_id": task_id,
                "created_at": "2026-07-26T10:00:00+00:00",
                "updated_at": "2026-07-26T10:00:00+00:00",
                "status": "completed",
                "mode": "generate",
                "prompt": prompt,
                "prompt_for_model": prompt_for_model,
                "outputs": records,
                "generated_count": len(records),
                "failed_count": 0,
                "total_count": len(records),
            },
        )
        return paths

    def _service(self, storage, export_root: Path):
        from codex_image.webui.history_export import (
            HistoryExportService,
        )

        return HistoryExportService(
            storage,
            temp_root=export_root,
            now=lambda: datetime(
                2026,
                7,
                26,
                12,
                34,
                56,
                tzinfo=UTC,
            ),
        )

    def test_images_and_prompts_keep_slots_bytes_and_fallback_order(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = history_storage(root)
            task_id = "20260726100000-aaaaaaaa"
            self._write_task(
                storage,
                task_id,
                [
                    (1, "png", b"PNG-ONE", "revised one"),
                    (3, "webp", b"WEBP-THREE", "  "),
                ],
                prompt="original prompt",
                prompt_for_model="private model prompt",
            )
            service = self._service(
                storage,
                root / "exports",
            )
            result = service.create(
                [task_id],
                mode="images_with_prompts",
            )
            pending = service.claim(result.export_id)
            with zipfile.ZipFile(pending.path) as archive:
                names = archive.namelist()
                first_bytes = archive.read(
                    f"{task_id}/image-01.png"
                )
                third_bytes = archive.read(
                    f"{task_id}/image-03.webp"
                )
                first_prompt = archive.read(
                    f"{task_id}/image-01.txt"
                ).decode("utf-8")
                third_prompt = archive.read(
                    f"{task_id}/image-03.txt"
                ).decode("utf-8")
                image_compression = archive.getinfo(
                    f"{task_id}/image-01.png"
                ).compress_type

        self.assertEqual(
            names,
            [
                f"{task_id}/image-01.png",
                f"{task_id}/image-01.txt",
                f"{task_id}/image-03.webp",
                f"{task_id}/image-03.txt",
            ],
        )
        self.assertEqual(first_bytes, b"PNG-ONE")
        self.assertEqual(third_bytes, b"WEBP-THREE")
        self.assertEqual(first_prompt, "revised one")
        self.assertEqual(third_prompt, "original prompt")
        self.assertEqual(image_compression, zipfile.ZIP_STORED)
        self.assertEqual(result.task_count, 1)
        self.assertEqual(result.image_count, 2)
        self.assertRegex(
            result.filename,
            r"^iLab-CONJURE-export-20260726-123456\.zip$",
        )

    def test_empty_prompt_does_not_fall_back_to_prompt_for_model(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = history_storage(root)
            task_id = "20260726100000-bbbbbbbb"
            self._write_task(
                storage,
                task_id,
                [(1, "jpg", b"JPG", "")],
                prompt="",
                prompt_for_model="must not export",
            )
            service = self._service(
                storage,
                root / "exports",
            )
            result = service.create(
                [task_id],
                mode="images_with_prompts",
            )
            pending = service.claim(result.export_id)
            with zipfile.ZipFile(pending.path) as archive:
                prompt = archive.read(
                    f"{task_id}/image-01.txt"
                )

        self.assertEqual(prompt, b"")

    def test_images_only_contains_no_text_or_hidden_metadata(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = history_storage(root)
            task_id = "20260726100000-cccccccc"
            self._write_task(
                storage,
                task_id,
                [(1, "png", b"PNG", "revised")],
                prompt="original",
                prompt_for_model="private",
            )
            service = self._service(
                storage,
                root / "exports",
            )
            result = service.create(
                [task_id],
                mode="images_only",
            )
            pending = service.claim(result.export_id)
            with zipfile.ZipFile(pending.path) as archive:
                names = archive.namelist()

        self.assertEqual(names, [f"{task_id}/image-01.png"])
        self.assertFalse(any(name.endswith(".txt") for name in names))
        self.assertFalse(
            any(
                word in name.lower()
                for name in names
                for word in ("manifest", "metadata", "request")
            )
        )

    def test_multiple_tasks_keep_first_request_order_and_dedupe(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = history_storage(root)
            first = "20260726100000-dddddddd"
            second = "20260726100000-eeeeeeee"
            self._write_task(
                storage,
                first,
                [(1, "png", b"FIRST", "")],
            )
            self._write_task(
                storage,
                second,
                [(2, "png", b"SECOND", "")],
            )
            service = self._service(
                storage,
                root / "exports",
            )
            result = service.create(
                [second, first, second],
                mode="images_only",
            )
            pending = service.claim(result.export_id)
            with zipfile.ZipFile(pending.path) as archive:
                names = archive.namelist()

        self.assertEqual(
            names,
            [
                f"{second}/image-02.png",
                f"{first}/image-01.png",
            ],
        )
        self.assertEqual(result.task_count, 2)

    def test_invalid_batch_leaves_no_partial_or_zip_files(
        self,
    ) -> None:
        from codex_image.webui.history_export import (
            HistoryExportTaskNotFoundError,
            HistoryExportValidationError,
        )

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = history_storage(root)
            valid = "20260726100000-ffffffff"
            missing_file = "20260726100000-11111111"
            empty = "20260726100000-22222222"
            self._write_task(
                storage,
                valid,
                [(1, "png", b"VALID", "")],
            )
            missing_paths = self._write_task(
                storage,
                missing_file,
                [(1, "png", b"MISSING", "")],
            )
            missing_paths[0].unlink()
            self._write_task(storage, empty, [])
            export_root = root / "exports"
            service = self._service(storage, export_root)

            with self.assertRaises(HistoryExportTaskNotFoundError):
                service.create(
                    [valid, "missing-task"],
                    mode="images_only",
                )
            with self.assertRaises(HistoryExportValidationError):
                service.create(
                    [valid, missing_file],
                    mode="images_only",
                )
            with self.assertRaises(HistoryExportValidationError):
                service.create(
                    [empty],
                    mode="images_only",
                )

            leftovers = (
                list(export_root.iterdir())
                if export_root.exists()
                else []
            )

        self.assertEqual(leftovers, [])

    def test_rejects_unsafe_records_invalid_mode_and_over_300_tasks(
        self,
    ) -> None:
        from codex_image.webui.history_export import (
            HistoryExportValidationError,
        )

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = history_storage(root)
            unsafe = "20260726100000-33333333"
            storage.write_metadata(
                unsafe,
                {
                    "task_id": unsafe,
                    "created_at": "2026-07-26T10:00:00+00:00",
                    "updated_at": "2026-07-26T10:00:00+00:00",
                    "status": "completed",
                    "mode": "generate",
                    "outputs": [
                        {
                            "index": 1,
                            "status": "completed",
                            "file": "../outside.png",
                        }
                    ],
                },
            )
            service = self._service(
                storage,
                root / "exports",
            )

            with self.assertRaises(HistoryExportValidationError):
                service.create(
                    [unsafe],
                    mode="images_only",
                )
            with self.assertRaises(HistoryExportValidationError):
                service.create(
                    [unsafe],
                    mode="invalid",
                )
            with self.assertRaises(HistoryExportValidationError):
                service.create(
                    [f"task-{index}" for index in range(301)],
                    mode="images_only",
                )
            leftovers = list((root / "exports").iterdir())

        self.assertEqual(leftovers, [])

    def test_claim_is_one_time_and_expired_files_are_cleaned(
        self,
    ) -> None:
        from codex_image.webui.history_export import (
            HistoryExportNotFoundError,
            HistoryExportService,
        )

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = history_storage(root)
            task_id = "20260726100000-44444444"
            self._write_task(
                storage,
                task_id,
                [(1, "png", b"PNG", "")],
            )
            current = datetime(
                2026,
                7,
                26,
                12,
                0,
                tzinfo=UTC,
            )
            service = HistoryExportService(
                storage,
                temp_root=root / "exports",
                now=lambda: current,
                ttl=timedelta(hours=1),
            )
            result = service.create(
                [task_id],
                mode="images_only",
            )
            pending = service.claim(result.export_id)
            with self.assertRaises(HistoryExportNotFoundError):
                service.claim(result.export_id)
            service.remove_file(pending.path)
            service.remove_file(pending.path)

        self.assertFalse(pending.path.exists())

    def test_cleanup_expired_removes_registry_zip_and_stale_partial(
        self,
    ) -> None:
        from codex_image.webui.history_export import (
            HistoryExportNotFoundError,
            HistoryExportService,
        )

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = history_storage(root)
            task_id = "20260726100000-45454545"
            self._write_task(
                storage,
                task_id,
                [(1, "png", b"PNG", "")],
            )
            current = [
                datetime(
                    2026,
                    7,
                    26,
                    12,
                    0,
                    tzinfo=UTC,
                )
            ]
            export_root = root / "exports"
            service = HistoryExportService(
                storage,
                temp_root=export_root,
                now=lambda: current[0],
                ttl=timedelta(hours=1),
            )
            result = service.create(
                [task_id],
                mode="images_only",
            )
            pending_path = next(export_root.glob("*.zip"))
            stale_partial = (
                export_root
                / "ilab-conjure-history-export-stale.partial"
            )
            stale_partial.write_bytes(b"partial")
            stale_time = (
                current[0] - timedelta(hours=2)
            ).timestamp()
            os.utime(stale_partial, (stale_time, stale_time))
            unrelated = export_root / "keep-me.partial"
            unrelated.write_bytes(b"unrelated")

            current[0] += timedelta(hours=2)
            service.cleanup_expired()
            with self.assertRaises(HistoryExportNotFoundError):
                service.claim(result.export_id)
            unrelated_kept = unrelated.exists()

        self.assertFalse(pending_path.exists())
        self.assertFalse(stale_partial.exists())
        self.assertTrue(unrelated_kept)


class HistoryExportApiTests(unittest.TestCase):
    def _app_client(self, root: Path):
        from codex_image.webui.app import create_app

        export_root = root / "exports"
        app = create_app(
            output_root=root / "outputs",
            auth_checker=lambda: True,
            auto_start_queue=False,
            history_export_temp_root=export_root,
        )
        return app, TestClient(app), export_root

    def _write_task(
        self,
        storage,
        task_id: str,
        *,
        with_output: bool = True,
    ) -> Path | None:
        path = (
            storage.write_output(
                task_id,
                b"EXPORT-IMAGE",
                "png",
                index=1,
            )
            if with_output
            else None
        )
        outputs = (
            [
                {
                    "index": 1,
                    "status": "completed",
                    "file": storage.output_file(path),
                    "revised_prompt": "per image prompt",
                }
            ]
            if path is not None
            else []
        )
        storage.write_metadata(
            task_id,
            {
                "task_id": task_id,
                "created_at": "2026-07-26T10:00:00+00:00",
                "updated_at": "2026-07-26T10:00:00+00:00",
                "status": "completed",
                "mode": "generate",
                "prompt": "original",
                "outputs": outputs,
                "generated_count": len(outputs),
                "failed_count": 0,
                "total_count": len(outputs),
            },
        )
        return path

    def test_create_and_one_time_download_streams_then_cleans_file(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            app, client, export_root = self._app_client(root)
            task_id = "20260726100000-55555555"
            self._write_task(app.state.storage, task_id)

            created = client.post(
                "/api/task-history/exports",
                json={
                    "task_ids": [task_id],
                    "mode": "images_with_prompts",
                },
            )
            payload = created.json()
            pending_before = list(export_root.glob("*.zip"))
            downloaded = client.get(payload["download_url"])
            pending_after = list(export_root.glob("*.zip"))
            second = client.get(payload["download_url"])

        self.assertEqual(created.status_code, 200)
        self.assertEqual(payload["task_count"], 1)
        self.assertEqual(payload["image_count"], 1)
        self.assertNotIn("path", payload)
        self.assertNotIn(str(export_root), str(payload))
        self.assertEqual(len(pending_before), 1)
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(
            downloaded.headers["content-type"],
            "application/zip",
        )
        self.assertIn(
            payload["filename"],
            downloaded.headers["content-disposition"],
        )
        with zipfile.ZipFile(BytesIO(downloaded.content)) as archive:
            self.assertEqual(
                archive.read(f"{task_id}/image-01.png"),
                b"EXPORT-IMAGE",
            )
            self.assertEqual(
                archive.read(
                    f"{task_id}/image-01.txt"
                ).decode("utf-8"),
                "per image prompt",
            )
        self.assertEqual(pending_after, [])
        self.assertEqual(second.status_code, 404)

    def test_export_api_validates_mode_count_and_complete_batch(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            app, client, export_root = self._app_client(root)
            empty_task = "20260726100000-66666666"
            missing_file_task = "20260726100000-77777777"
            self._write_task(
                app.state.storage,
                empty_task,
                with_output=False,
            )
            path = self._write_task(
                app.state.storage,
                missing_file_task,
            )
            assert path is not None
            path.unlink()

            invalid_mode = client.post(
                "/api/task-history/exports",
                json={
                    "task_ids": [empty_task],
                    "mode": "invalid",
                },
            )
            empty_ids = client.post(
                "/api/task-history/exports",
                json={
                    "task_ids": [],
                    "mode": "images_only",
                },
            )
            too_many = client.post(
                "/api/task-history/exports",
                json={
                    "task_ids": [
                        f"task-{index}"
                        for index in range(301)
                    ],
                    "mode": "images_only",
                },
            )
            missing_task = client.post(
                "/api/task-history/exports",
                json={
                    "task_ids": ["missing-task"],
                    "mode": "images_only",
                },
            )
            empty_output = client.post(
                "/api/task-history/exports",
                json={
                    "task_ids": [empty_task],
                    "mode": "images_only",
                },
            )
            missing_file = client.post(
                "/api/task-history/exports",
                json={
                    "task_ids": [missing_file_task],
                    "mode": "images_only",
                },
            )
            leftovers = list(export_root.glob("*"))

        self.assertEqual(invalid_mode.status_code, 422)
        self.assertEqual(empty_ids.status_code, 422)
        self.assertEqual(too_many.status_code, 422)
        self.assertEqual(missing_task.status_code, 404)
        self.assertEqual(empty_output.status_code, 409)
        self.assertEqual(missing_file.status_code, 409)
        self.assertEqual(leftovers, [])

    def test_one_time_response_cleans_file_when_send_fails(
        self,
    ) -> None:
        from codex_image.webui.routes.history import (
            OneTimeHistoryExportResponse,
        )

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "export.zip"
            path.write_bytes(b"zip")
            response = OneTimeHistoryExportResponse(
                path,
                filename="export.zip",
                cleanup=lambda item: Path(item).unlink(
                    missing_ok=True
                ),
            )

            async def receive():
                return {"type": "http.disconnect"}

            async def send(_message):
                raise RuntimeError("send failed")

            with self.assertRaisesRegex(
                RuntimeError,
                "send failed",
            ):
                asyncio.run(
                    response(
                        {
                            "type": "http",
                            "method": "GET",
                            "path": "/download",
                            "headers": [],
                        },
                        receive,
                        send,
                    )
                )
            exists = path.exists()

        self.assertFalse(exists)


if __name__ == "__main__":
    unittest.main()
