from __future__ import annotations

import json
from pathlib import Path

from tests.webui_helpers import WebUIStaticTestCase


class WebUIStaticUserConfigBackupTests(WebUIStaticTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.html = Path("codex_image/webui/static/index.html").read_text(
            encoding="utf-8"
        )

    def test_settings_keeps_four_tabs_and_uses_one_child_view(self) -> None:
        self.assertEqual(self.html.count('data-system-settings-tab="'), 4)
        self.assertIn('id="openUserConfigBackupButton"', self.html)
        self.assertIn('data-i18n="userConfigBackup.entryTitle"', self.html)
        self.assertIn('id="userConfigBackupView"', self.html)
        self.assertRegex(
            self.html,
            r'id="userConfigBackupView"[^>]*hidden[^>]*inert[^>]*aria-hidden="true"',
        )
        self.assertEqual(self.html.count('id="systemSettingsModal"'), 1)

    def test_child_navigation_and_native_file_input_are_accessible(self) -> None:
        self.assertIn('id="systemSettingsTitle"', self.html)
        self.assertIn('id="userConfigBackupBackButton"', self.html)
        self.assertIn(
            'data-i18n-attr="aria-label:userConfigBackup.back;title:userConfigBackup.back"',
            self.html,
        )
        self.assertRegex(
            self.html,
            r'id="userConfigRestoreFile"[^>]*type="file"[^>]*accept="\.zip,application/zip"',
        )
        self.assertIn('data-i18n-attr="aria-label:close.systemSettings', self.html)

    def test_modes_use_segmented_controls_and_replace_needs_checkbox(self) -> None:
        self.assertIn('data-user-config-view-mode="backup"', self.html)
        self.assertIn('data-user-config-view-mode="restore"', self.html)
        self.assertIn('data-user-config-restore-mode="incremental"', self.html)
        self.assertIn('data-user-config-restore-mode="replace"', self.html)
        self.assertRegex(
            self.html,
            r'id="userConfigReplaceAcknowledge"[^>]*type="checkbox"',
        )
        self.assertRegex(
            self.html,
            r'id="confirmUserConfigReplaceButton"[^>]*disabled',
        )

    def test_status_and_progress_semantics_are_explicit(self) -> None:
        for element_id in (
            "userConfigBackupStatus",
            "userConfigRestoreStatus",
            "userConfigRestoreResult",
        ):
            self.assertRegex(
                self.html,
                rf'id="{element_id}"[^>]*aria-live="polite"',
            )
        self.assertRegex(
            self.html,
            r'id="userConfigBackupProgress"[^>]*role="progressbar"',
        )
        self.assertRegex(
            self.html,
            r'id="userConfigRestoreProgress"[^>]*role="progressbar"',
        )

    def test_ready_download_action_has_icon_and_follows_create_action(self) -> None:
        create_index = self.html.index('id="createUserConfigBackupButton"')
        download_index = self.html.index('id="downloadUserConfigBackupButton"')
        self.assertLess(create_index, download_index)
        self.assertRegex(
            self.html,
            r'id="downloadUserConfigBackupButton"[^>]*>\s*<svg[^>]*aria-hidden="true"',
        )

    def test_css_is_manifest_sourced(self) -> None:
        manifest = json.loads(
            Path("codex_image/webui/static/styles/manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("76-user-config-backup.css", manifest)
        source = Path(
            "codex_image/webui/static/styles/76-user-config-backup.css"
        )
        self.assertTrue(source.is_file())
        generated = Path("codex_image/webui/static/styles.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("source: styles/76-user-config-backup.css", generated)

    def test_controller_owns_replace_confirmation_and_chunk_upload(self) -> None:
        source = Path(
            "codex_image/webui/frontend/src/user-config-backup.ts"
        ).read_text(encoding="utf-8")
        settings = Path(
            "codex_image/webui/frontend/src/system-settings.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("buildUserConfigRestoreRequest", source)
        self.assertIn("uploadUserConfigRestore", source)
        self.assertIn("applyUserConfigClientPreferences", source)
        self.assertIn("openUserConfigBackupView", settings)
        self.assertIn("closeUserConfigBackupView", settings)
        self.assertIn("userConfigBackupViewIsOpen", settings)
