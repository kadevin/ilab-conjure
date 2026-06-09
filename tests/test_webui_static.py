"""Compatibility entry for WebUI static contract tests.

Domain-specific tests live in ``tests/test_webui_static_build.py``,
``tests/test_webui_static_prompt.py``, ``tests/test_webui_static_tasks.py``,
and ``tests/test_webui_static_layout.py``.
"""

from __future__ import annotations

import unittest


_DOMAIN_MODULES = (
    "tests.test_webui_static_build",
    "tests.test_webui_static_prompt",
    "tests.test_webui_static_tasks",
    "tests.test_webui_static_layout",
    "tests.test_webui_static_i18n",
)


def load_tests(loader: unittest.TestLoader, standard_tests: unittest.TestSuite, pattern: str | None) -> unittest.TestSuite:
    if pattern is not None:
        return unittest.TestSuite()
    suite = unittest.TestSuite()
    for module_name in _DOMAIN_MODULES:
        suite.addTests(loader.loadTestsFromName(module_name))
    return suite
