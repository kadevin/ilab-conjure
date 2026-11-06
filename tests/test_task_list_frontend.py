"""Compatibility entry; pure frontend suites are discovered centrally."""

from tests.frontend_runner import compatibility_load_tests


load_tests = compatibility_load_tests((
    'task_list_modules.test.ts',
))
