"""Collect every pure Node suite exactly once in local unittest discovery."""

from tests import frontend_runner


def load_tests(loader, standard_tests, pattern):
    return frontend_runner.node_suite()
