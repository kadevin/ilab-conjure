"""Compatibility entry; pure frontend suites are discovered centrally."""

from tests.frontend_runner import compatibility_load_tests


load_tests = compatibility_load_tests((
    'startup_sync.test.cjs',
))
