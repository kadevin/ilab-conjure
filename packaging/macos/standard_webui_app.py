from __future__ import annotations

import os
from pathlib import Path

from codex_image.webui.app import create_app


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(
    os.environ.get("ILAB_CONJURE_DATA_DIR")
    or Path.home() / "Library" / "Application Support" / "iLab GPT CONJURE"
).resolve()

INPUT_ROOT = DATA_DIR / "webui-inputs"
OUTPUT_ROOT = DATA_DIR / "webui-outputs"

DATA_DIR.mkdir(parents=True, exist_ok=True)

app = create_app(
    input_root=INPUT_ROOT,
    output_root=OUTPUT_ROOT,
    gallery_root=INPUT_ROOT / "gallery",
    reference_asset_root=INPUT_ROOT / "reference-assets",
    source_data_root=OUTPUT_ROOT / "source-data",
    webui_settings_path=DATA_DIR / "webui-settings.json",
    auth_settings_path=DATA_DIR / "webui-auth-settings.json",
    api_settings_path=DATA_DIR / "webui-api-settings.json",
    network_egress_settings_path=DATA_DIR / "webui-network-egress-settings.json",
    color_settings_path=DATA_DIR / "webui-color-settings.json",
    prompt_snippets_path=DATA_DIR / "webui-prompt-snippets.json",
    prompt_templates_path=DATA_DIR / "webui-prompt-templates.json",
)
