from __future__ import annotations

import json
import os
from pathlib import Path

from codex_image.webui.app import create_app
from codex_image.webui.settings_store import _settings_path, _validate_webui_paths


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(
    os.environ.get("ILAB_CONJURE_DATA_DIR")
    or Path.home() / "Library" / "Application Support" / "iLab GPT CONJURE"
).resolve()

# 已保存路径优先；首次启动保留标准安装包的数据目录约定。
SETTINGS_PATH = DATA_DIR / "webui-settings.json"
try:
    saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
except FileNotFoundError:
    saved = {}
if not isinstance(saved, dict):
    raise ValueError("WebUI settings must be a JSON object")
INPUT_ROOT = _settings_path(saved.get("input_root"), DATA_DIR / "webui-inputs")
OUTPUT_ROOT = _settings_path(saved.get("output_root"), DATA_DIR / "webui-outputs")
GALLERY_ROOT = _settings_path(saved.get("gallery_root"), INPUT_ROOT / "gallery")
SOURCE_DATA_ROOT = _settings_path(saved.get("source_data_root"), OUTPUT_ROOT / "source-data")
_validate_webui_paths({
    "input_root": INPUT_ROOT,
    "output_root": OUTPUT_ROOT,
    "gallery_root": GALLERY_ROOT,
    "source_data_root": SOURCE_DATA_ROOT,
})

DATA_DIR.mkdir(parents=True, exist_ok=True)

app = create_app(
    input_root=INPUT_ROOT,
    output_root=OUTPUT_ROOT,
    gallery_root=GALLERY_ROOT,
    reference_asset_root=INPUT_ROOT / "reference-assets",
    source_data_root=SOURCE_DATA_ROOT,
    webui_settings_path=DATA_DIR / "webui-settings.json",
    auth_settings_path=DATA_DIR / "webui-auth-settings.json",
    api_settings_path=DATA_DIR / "webui-api-settings.json",
    network_egress_settings_path=DATA_DIR / "webui-network-egress-settings.json",
    color_settings_path=DATA_DIR / "webui-color-settings.json",
    prompt_snippets_path=DATA_DIR / "webui-prompt-snippets.json",
    prompt_templates_path=DATA_DIR / "webui-prompt-templates.json",
    enforce_single_instance=True,
)
