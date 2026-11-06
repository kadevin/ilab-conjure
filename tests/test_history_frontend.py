"""Compatibility entry; pure frontend suites are discovered centrally."""

from tests.frontend_runner import compatibility_load_tests


load_tests = compatibility_load_tests((
    'history_backup.test.ts',
    'history_import.test.ts',
    'history_position_restore.test.ts',
    'history_scroll_memory.test.ts',
    'history_controllers.test.ts',
))
