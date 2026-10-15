from __future__ import annotations

import argparse
from contextlib import chdir
from html.parser import HTMLParser
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from codex_image.cli import build_parser
from codex_image.webui.app import create_app
from tests.helpers import TEST_PNG_BYTES


ROOT = Path(__file__).resolve().parents[1]


class LegacyAccountPoolRemovalTests(unittest.TestCase):
    def test_entrypoint_check_preserves_callers_legacy_data(self) -> None:
        with TemporaryDirectory(prefix="conjure-entrypoint-isolation-") as temporary:
            root = Path(temporary)
            task = Path("output/webui/isolation-task")
            gallery = Path("output/webui-gallery/isolation-gallery")
            expected = {
                task / "metadata.json": json.dumps({
                    "task_id": "isolation-task", "status": "completed",
                    "output_files": ["image.png"], "params": {},
                }).encode(),
                task / "image.png": TEST_PNG_BYTES,
                gallery / "metadata.json": b'{"id":"isolation-gallery"}',
                gallery / "image.png": TEST_PNG_BYTES,
            }
            for relative, content in expected.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)

            result = unittest.TestResult()
            with chdir(root):
                type(self)("test_retired_account_pool_has_no_cli_route_or_ui_entry").run(result)
                self.assertEqual(Path.cwd(), root.resolve())

            for relative, content in expected.items():
                path = root / relative
                self.assertTrue(path.is_file(), f"Entrypoint check removed caller data: {relative}")
                self.assertEqual(path.read_bytes(), content, str(relative))
            self.assertTrue(result.wasSuccessful(), result.errors + result.failures)

    def test_retired_account_pool_has_no_cli_route_or_ui_entry(self) -> None:
        retired = ("cockpit", "account-pool", "account_pool", "accountpool")
        commands = [
            name
            for action in build_parser()._actions
            if isinstance(action, argparse._SubParsersAction)
            for name in action.choices
        ]
        # create_app also migrates legacy data from paths relative to cwd.
        with TemporaryDirectory() as temporary, chdir(temporary):
            root = Path(temporary)
            app = create_app(
                output_root=root / "outputs",
                api_settings_path=root / "api.json",
                auth_settings_path=root / "auth.json",
                webui_settings_path=root / "webui.json",
                auth_checker=lambda: True, auto_start_queue=False,
            )
            routes = [route.path for route in app.routes]

        class UIEntries(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.entries: list[str] = []

            def handle_starttag(self, tag, attrs) -> None:
                self.entries.extend(
                    value for name, value in attrs
                    if name in ("id", "href", "action") and value
                )

        parser = UIEntries()
        for page in ("index.html", "history.html"):
            parser.feed((ROOT / "codex_image/webui/static" / page).read_text(encoding="utf-8"))
        for entry in commands + routes + parser.entries:
            with self.subTest(entry=entry):
                self.assertFalse(any(name in entry.lower() for name in retired))


if __name__ == "__main__":
    unittest.main()
