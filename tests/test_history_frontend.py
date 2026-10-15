from __future__ import annotations

import unittest

from tests.frontend_runner import run_frontend


class HistoryFrontendTests(unittest.TestCase):
    """Run the history controllers through the same bundler as the WebUI."""

    def run_typescript(self, name: str) -> None:
        run_frontend(self, f"{name}.test.ts")

    def test_backup(self) -> None:
        self.run_typescript("history_backup")

    def test_import(self) -> None:
        self.run_typescript("history_import")

    def test_position_restore(self) -> None:
        self.run_typescript("history_position_restore")

    def test_scroll_memory(self) -> None:
        self.run_typescript("history_scroll_memory")

    def test_controllers(self) -> None:
        self.run_typescript("history_controllers")
