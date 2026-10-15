import unittest

from tests.frontend_runner import run_frontend


class TaskListFrontendTests(unittest.TestCase):
    def test_task_list_modules(self) -> None:
        run_frontend(self, "task_list_modules.test.ts")
