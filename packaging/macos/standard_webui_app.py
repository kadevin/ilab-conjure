from __future__ import annotations

import os
from pathlib import Path

from codex_image.webui.app import create_app
from codex_image.webui.standard_storage import load_standard_storage_paths


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(
    os.environ.get("ILAB_CONJURE_DATA_DIR")
    or Path.home() / "Library" / "Application Support" / "iLab GPT CONJURE"
).resolve()

paths = load_standard_storage_paths(DATA_DIR)

DATA_DIR.mkdir(parents=True, exist_ok=True)

app = create_app(
    **paths,
    reference_asset_root=paths["input_root"] / "reference-assets",
    webui_settings_path=DATA_DIR / "webui-settings.json",
    auth_settings_path=DATA_DIR / "webui-auth-settings.json",
    api_settings_path=DATA_DIR / "webui-api-settings.json",
    network_egress_settings_path=DATA_DIR / "webui-network-egress-settings.json",
    color_settings_path=DATA_DIR / "webui-color-settings.json",
    prompt_snippets_path=DATA_DIR / "webui-prompt-snippets.json",
    prompt_templates_path=DATA_DIR / "webui-prompt-templates.json",
    enforce_single_instance=True,
)
