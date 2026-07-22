from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_WEBUI_INPUT_ROOT = Path("output") / "webui-inputs"
DEFAULT_WEBUI_OUTPUT_ROOT = Path("output") / "webui-outputs"
DEFAULT_WEBUI_GALLERY_SUBDIR = "gallery"
DEFAULT_WEBUI_REFERENCE_ASSET_SUBDIR = "reference-assets"
DEFAULT_WEBUI_REFERENCE_FILE_SUBDIR = "reference-files"
DEFAULT_WEBUI_SOURCE_DATA_SUBDIR = "source-data"
DEFAULT_WEBUI_GALLERY_ROOT = DEFAULT_WEBUI_INPUT_ROOT / DEFAULT_WEBUI_GALLERY_SUBDIR
DEFAULT_WEBUI_SOURCE_DATA_ROOT = DEFAULT_WEBUI_OUTPUT_ROOT / DEFAULT_WEBUI_SOURCE_DATA_SUBDIR
DEFAULT_WEBUI_SETTINGS_PATH = Path("output") / "webui-settings.json"
DEFAULT_WEBUI_AUTH_SETTINGS_PATH = Path("output") / "webui-auth-settings.json"
DEFAULT_WEBUI_API_SETTINGS_PATH = Path("output") / "webui-api-settings.json"
DEFAULT_WEBUI_NETWORK_EGRESS_SETTINGS_PATH = Path("output") / "webui-network-egress-settings.json"
DEFAULT_WEBUI_COLOR_SETTINGS_PATH = Path("output") / "webui-color-settings.json"
DEFAULT_WEBUI_PROMPT_SNIPPETS_PATH = Path("output") / "webui-prompt-snippets.json"
DEFAULT_WEBUI_PROMPT_TEMPLATES_PATH = Path("output") / "webui-prompt-templates.json"


@dataclass(frozen=True)
class CreatedTask:
    task_id: str
    path: Path
    mode: str
