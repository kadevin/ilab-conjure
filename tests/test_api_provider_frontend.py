"""Compatibility entry; pure frontend suites are discovered centrally."""

from tests.frontend_runner import compatibility_load_tests


load_tests = compatibility_load_tests((
    'provider_model_discovery.test.ts',
    'api_provider_model.test.ts',
))
