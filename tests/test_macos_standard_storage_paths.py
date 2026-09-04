from __future__ import annotations

import json
import os
import runpy
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
