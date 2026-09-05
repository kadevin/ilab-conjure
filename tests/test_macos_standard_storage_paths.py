from __future__ import annotations

import json
import os
import runpy
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_image.webui.settings_store import WebUISettings


ENTRYPOINT = Path(__file__).resolve().parents[1] / "packaging/macos/standard_webui_app.py"


class MacOSStandardStoragePathsTests(unittest.TestCase):
    def launch(self, data_dir: Path) -> dict:
        # 只隔离服务启动副作用，真实执行打包入口及路径解析。
        with (
            patch.dict(os.environ, {"ILAB_CONJURE_DATA_DIR": str(data_dir)}),
            patch("codex_image.webui.app.create_app", side_effect=lambda **kwargs: kwargs),
        ):
            return runpy.run_path(str(ENTRYPOINT))["app"]

    def copy_portable_data(self, root: Path, *, external_input: bool = False) -> tuple[Path, Path]:
        source = root / "portable/data"
        target = root / "standard"
        input_root = root / "external-input" if external_input else source / "webui-inputs"
        saved = WebUISettings(source / "webui-settings.json")
        saved.write_paths({
            "input_root": str(input_root),
            "output_root": str(source / "webui-outputs"),
            "gallery_root": str(input_root / "library"),
            "source_data_root": str(source / "webui-outputs/history"),
        })
        saved.write_locale("en")
        settings_path = source / "webui-settings.json"
        settings = json.loads(settings_path.read_text())
        settings["future_setting"] = {"keep": [1, "value"]}
        settings_path.write_text(json.dumps(settings))
        (source / "webui-outputs/history").mkdir(parents=True)
        (source / "webui-outputs/history/retained.txt").write_text("synthetic history")
        if not external_input:
            (input_root / "library").mkdir(parents=True)
        # Match the launcher's copy plus portable-data-copied-v1.json contract.
        shutil.copytree(source, target)
        marker = target / ".migration/portable-data-copied-v1.json"
        marker.parent.mkdir()
        marker.write_text(json.dumps({"schema_version": 1, "mode": "copy", "source": str(source), "migrated_at_unix": 1}))
        return source, target

    def test_copied_portable_paths_use_the_standard_copy_and_preserve_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, target = self.copy_portable_data(Path(directory).resolve())
            original = (source / "webui-settings.json").read_bytes()
            for _ in range(2):
                result = self.launch(target)
                self.assertEqual(result["input_root"], target / "webui-inputs")
                self.assertEqual(result["output_root"], target / "webui-outputs")
                self.assertEqual(result["gallery_root"], target / "webui-inputs/library")
                self.assertEqual(result["source_data_root"], target / "webui-outputs/history")
                self.assertEqual((result["source_data_root"] / "retained.txt").read_text(), "synthetic history")
            self.assertEqual((source / "webui-settings.json").read_bytes(), original)
            self.assertEqual((source / "webui-outputs/history/retained.txt").read_text(), "synthetic history")
            self.assertEqual(WebUISettings(target / "webui-settings.json").read_locale(), "en")
            self.assertEqual(json.loads((target / "webui-settings.json").read_text())["future_setting"], {"keep": [1, "value"]})
            self.assertEqual(WebUISettings(target / "webui-settings.json").read_paths()["input_root"], target / "webui-inputs")
            self.assertEqual((target / ".migration/webui-settings-before-path-rebase.json").read_bytes(), original)

    def test_failed_settings_rewrite_keeps_original_config_and_allows_retry(self) -> None:
        from codex_image.webui.atomic_files import atomic_write_text

        with tempfile.TemporaryDirectory() as directory:
            source, target = self.copy_portable_data(Path(directory).resolve())
            settings_path = target / "webui-settings.json"
            original = settings_path.read_bytes()

            def fail_settings_write(path: Path, text: str, **kwargs: object) -> None:
                if path == settings_path:
                    raise OSError("synthetic write failure")
                atomic_write_text(path, text, **kwargs)

            with patch("codex_image.webui.standard_storage.atomic_write_text", side_effect=fail_settings_write):
                with self.assertRaisesRegex(OSError, "synthetic write failure"):
                    self.launch(target)
            self.assertEqual(settings_path.read_bytes(), original)
            self.assertEqual((source / "webui-settings.json").read_bytes(), original)
            self.assertNotIn("storage_paths_rebased", json.loads((target / ".migration/portable-data-copied-v1.json").read_text()))
            self.assertEqual(self.launch(target)["input_root"], target / "webui-inputs")

    def test_upgrade_repairs_copied_paths_after_the_portable_folder_was_removed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, target = self.copy_portable_data(Path(directory).resolve())
            shutil.rmtree(source)
            result = self.launch(target)
            self.assertEqual(result["source_data_root"], target / "webui-outputs/history")
            self.assertFalse(source.exists())

    def test_failed_marker_write_retries_without_overwriting_the_original_backup(self) -> None:
        from codex_image.webui.atomic_files import atomic_write_text

        with tempfile.TemporaryDirectory() as directory:
            source, target = self.copy_portable_data(Path(directory).resolve())
            marker = target / ".migration/portable-data-copied-v1.json"
            original = (source / "webui-settings.json").read_bytes()

            def fail_marker_write(path: Path, text: str, **kwargs: object) -> None:
                if path == marker:
                    raise OSError("synthetic marker failure")
                atomic_write_text(path, text, **kwargs)

            with patch("codex_image.webui.standard_storage.atomic_write_text", side_effect=fail_marker_write):
                with self.assertRaisesRegex(OSError, "synthetic marker failure"):
                    self.launch(target)
            self.assertNotIn("storage_paths_rebased", json.loads(marker.read_text()))
            self.assertEqual(self.launch(target)["input_root"], target / "webui-inputs")
            self.assertIs(json.loads(marker.read_text())["storage_paths_rebased"], True)
            self.assertEqual((source / "webui-settings.json").read_bytes(), original)
            self.assertEqual((target / ".migration/webui-settings-before-path-rebase.json").read_bytes(), original)

    def test_migration_preserves_external_custom_roots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _, target = self.copy_portable_data(root, external_input=True)
            result = self.launch(target)
            self.assertEqual(result["input_root"], root / "external-input")
            self.assertEqual(result["gallery_root"], root / "external-input/library")
            self.assertEqual(result["output_root"], target / "webui-outputs")

    def test_copied_history_and_images_survive_real_app_restarts_without_the_source(self) -> None:
        from fastapi.testclient import TestClient
        from codex_image.webui.app import create_app
        from codex_image.webui.storage import TaskStorage
        from tests.test_webui_storage import _png_bytes

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, target = self.copy_portable_data(root)
            storage = TaskStorage(
                input_root=source / "webui-inputs",
                output_root=source / "webui-outputs",
                source_data_root=source / "webui-outputs/history",
            )
            task = storage.create_task("generate")
            image = _png_bytes((4, 4))
            output = storage.output_file(storage.write_output(task.task_id, image, "png"))
            storage.write_metadata(task.task_id, {
                "task_id": task.task_id, "mode": "generate", "status": "completed",
                "created_at": "2026-08-01T00:00:00Z", "prompt": "synthetic copied history",
                "output_file": output, "output_files": [output],
                "generated_count": 1, "total_count": 1,
            })
            storage.write_request(task.task_id, {"prompt": "synthetic copied history"})
            shutil.copytree(source, target, dirs_exist_ok=True)
            shutil.rmtree(source)
            cwd = Path.cwd()
            try:
                os.chdir(root)
                for _ in range(2):
                    with (
                        patch.dict(os.environ, {"ILAB_CONJURE_DATA_DIR": str(target)}),
                        patch("codex_image.webui.app.create_app", side_effect=lambda **kwargs: create_app(
                            **kwargs, auth_checker=lambda: False, auto_start_queue=False,
                        )),
                    ):
                        app = runpy.run_path(str(ENTRYPOINT))["app"]
                    with TestClient(app) as client:
                        history = client.get("/api/task-history/tasks")
                        self.assertEqual(history.status_code, 200)
                        self.assertEqual([item["task_id"] for item in history.json()["tasks"]], [task.task_id])
                        self.assertEqual(client.get(f"/api/tasks/{task.task_id}").json()["task"]["prompt"], "synthetic copied history")
                        downloaded = client.get(f"/outputs/{output}")
                        self.assertEqual(downloaded.status_code, 200)
                        self.assertEqual(downloaded.content, image)
            finally:
                os.chdir(cwd)
            self.assertFalse(source.exists())

    def test_later_explicit_path_changes_are_not_rebased_again(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source, target = self.copy_portable_data(Path(directory).resolve())
            self.launch(target)
            saved = json.loads((source / "webui-settings.json").read_text())
            WebUISettings(target / "webui-settings.json").write_paths(saved)
            result = self.launch(target)
            self.assertEqual(result["input_root"], source / "webui-inputs")
            self.assertEqual(result["source_data_root"], source / "webui-outputs/history")

    def test_paths_are_not_rebased_without_a_valid_copy_record(self) -> None:
        for record in (None, "{broken", '{"schema_version": 1, "mode": "copy", "source": "relative/path"}'):
            with self.subTest(record=record), tempfile.TemporaryDirectory() as directory:
                source, target = self.copy_portable_data(Path(directory).resolve())
                marker = target / ".migration/portable-data-copied-v1.json"
                if record is None:
                    marker.unlink()
                else:
                    marker.write_text(record)
                self.assertEqual(self.launch(target)["input_root"], source / "webui-inputs")

    def test_first_launch_keeps_standard_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            result = self.launch(root)
            self.assertEqual(result["input_root"], root / "webui-inputs")
            self.assertEqual(result["output_root"], root / "webui-outputs")
            self.assertEqual(result["gallery_root"], root / "webui-inputs/gallery")
            self.assertEqual(result["source_data_root"], root / "webui-outputs/source-data")
            self.assertFalse((root / "webui-settings.json").exists())

    def test_saved_paths_survive_repeated_launches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            settings_path = root / "webui-settings.json"
            saved = WebUISettings(settings_path).write_paths({
                "input_root": str(root / "workspace/input"),
                "output_root": str(root / "workspace/output"),
                "gallery_root": str(root / "workspace/input/library"),
                "source_data_root": str(root / "workspace/output/source"),
            })
            original = settings_path.read_bytes()
            for _ in range(2):
                result = self.launch(root)
                for key, value in saved.items():
                    self.assertEqual(result[key], value)
                self.assertEqual(result["reference_asset_root"], saved["input_root"] / "reference-assets")
                self.assertEqual(result["webui_settings_path"], settings_path)
                self.assertEqual(result["api_settings_path"], root / "webui-api-settings.json")
                self.assertEqual(settings_path.read_bytes(), original)

    def test_partial_configuration_derives_child_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "webui-settings.json").write_text(json.dumps({
                "input_root": str(root / "input"),
                "output_root": str(root / "output"),
            }), encoding="utf-8")
            result = self.launch(root)
            self.assertEqual(result["gallery_root"], root / "input/gallery")
            self.assertEqual(result["source_data_root"], root / "output/source-data")

    def test_invalid_child_paths_are_not_silently_ignored(self) -> None:
        for key in ("gallery_root", "source_data_root"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                (root / "webui-settings.json").write_text(
                    json.dumps({key: str(root / "outside")}), encoding="utf-8",
                )
                with self.assertRaises(ValueError):
                    self.launch(root)

    def test_invalid_json_is_not_silently_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "webui-settings.json").write_text("{broken", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                self.launch(root)

    def test_non_object_configuration_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "webui-settings.json").write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON object"):
                self.launch(root)


if __name__ == "__main__":
    unittest.main()
