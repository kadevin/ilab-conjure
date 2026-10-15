import unittest

from tests.frontend_runner import run_frontend


class WebUIStartupSyncTests(unittest.TestCase):
    def test_http_and_realtime_state_reconciliation(self) -> None:
        run_frontend(self, "startup_sync.test.cjs")
