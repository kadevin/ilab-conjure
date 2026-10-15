import unittest

from tests.frontend_runner import run_frontend


class ApiProviderFrontendTests(unittest.TestCase):
    def test_provider_model_discovery(self) -> None:
        run_frontend(self, "provider_model_discovery.test.ts")

    def test_api_provider_model(self) -> None:
        run_frontend(self, "api_provider_model.test.ts")
