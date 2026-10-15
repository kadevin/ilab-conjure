import unittest

from tests.frontend_runner import run_frontend


class RuntimeFeedbackFrontendTests(unittest.TestCase):
    def test_runtime_feedback(self) -> None:
        run_frontend(self, "runtime_feedback.test.ts")
