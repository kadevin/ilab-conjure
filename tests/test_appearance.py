import unittest
from pathlib import Path

from pydantic import ValidationError

from codex_image.webui.appearance import validate_appearance
from codex_image.webui.routes.user_config_backup import ClientPreferencesPayload
from codex_image.webui.user_config_backup_components import ClientPreferences


class AppearanceTests(unittest.TestCase):
    def test_both_entry_pages_restore_appearance_before_styles(self):
        for name in ("index.html", "history.html"):
            source = (Path("codex_image/webui/static") / name).read_text()
            self.assertLess(source.index('/static/appearance-bootstrap.js?v=2'), source.index('<link rel="stylesheet"'))

    def test_old_and_valid_preferences(self):
        self.assertIsNone(ClientPreferences("dark", True, False).appearance)
        skin = {"version": 1, "preset": "custom", "primary": "#abcdef", "background": "warm"}
        self.assertEqual(validate_appearance(skin), {**skin, "primary": "#ABCDEF"})

    def test_invalid_and_css_payloads_are_rejected_at_api_boundary(self):
        base = {"version": 1, "preset": "custom", "primary": "#8057B0", "background": "neutral"}
        for invalid in [[], "red", {**base, "version": True}, {**base, "version": 2},
                        {**base, "primary": "red;display:none"}, {**base, "background": []},
                        {**base, "url": "https://example.com"}]:
            with self.subTest(value=invalid), self.assertRaises(ValidationError):
                ClientPreferencesPayload.model_validate({"theme": "light", "notifications": {
                    "in_app": True, "system": False}, "appearance": invalid})
