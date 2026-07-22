from __future__ import annotations

import importlib.util
import io
import json
import tempfile
from pathlib import Path
import unittest

from fastapi.testclient import TestClient
from PIL import Image


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "run-webui-provider-fixture.py"


def _fixture_module():
    spec = importlib.util.spec_from_file_location("imagegen_provider_fixture", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load provider fixture script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProviderFixtureTests(unittest.TestCase):
    def test_fixture_png_is_fully_decodable_for_thumbnail_generation(self) -> None:
        module = _fixture_module()
        with Image.open(io.BytesIO(module.PNG_BYTES)) as image:
            image.load()
            self.assertEqual((1, 1), image.size)

    def test_fixture_catalog_has_multi_model_and_protocol_specific_providers(self) -> None:
        module = _fixture_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app, _ = module.build_fixture_app(
                root,
                host="127.0.0.1",
                port=8897,
                auto_start_queue=False,
            )
            with TestClient(app) as client:
                response = client.get("/api/generation-catalog")
                recent = client.get("/api/tasks/recent", params={"limit": 10})

            payload = response.json()
            providers = {provider["id"]: provider for provider in payload["providers"]}
            mega_models = {
                binding["canonical_model_id"]
                for binding in providers["mega-relay"]["bindings"]
            }
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                mega_models,
                {
                    "gpt-image-2",
                    "nano-banana-pro",
                    "nano-banana-2",
                    "nano-banana-2-lite",
                },
            )
            self.assertIn("google-native", providers)
            self.assertIn("gemini-openai", providers)
            self.assertIn("gpt-only", providers)
            def assert_no_api_key(value) -> None:
                if isinstance(value, dict):
                    self.assertNotIn("api_key", value)
                    for nested in value.values():
                        assert_no_api_key(nested)
                elif isinstance(value, list):
                    for nested in value:
                        assert_no_api_key(nested)

            assert_no_api_key(payload)
            self.assertEqual(len(recent.json()["tasks"]), 3)

            index_bytes = (root / "source-data" / "webui-task-index.db").read_bytes()
            self.assertNotIn(module.PNG_B64.encode(), index_bytes)
            self.assertNotIn(b"fixture-mega-key-not-valid", index_bytes)

    def test_fixture_mock_protocols_return_url_base64_thought_and_sanitized_log(self) -> None:
        module = _fixture_module()
        with tempfile.TemporaryDirectory() as temporary:
            app, base_url = module.build_fixture_app(
                Path(temporary),
                host="127.0.0.1",
                port=8897,
                auto_start_queue=False,
            )
            with TestClient(app) as client:
                gemini = client.post(
                    "/mock/gemini/v1beta/models/fixture%2Fnano:generateContent",
                    json={"contents": [], "generationConfig": {"candidateCount": 1}},
                )
                openai_url = client.post(
                    "/mock/openai/v1/images/generations",
                    json={"model": "custom", "prompt": "fixture", "response_format": "url"},
                )
                openai_b64 = client.post(
                    "/mock/openai/v1/images/generations",
                    json={"model": "custom", "prompt": "fixture", "response_format": "b64_json"},
                )
                rejected = client.post(
                    "/mock/openai/v1/images/generations",
                    json={"model": "custom", "prompt": "[fixture:400]"},
                )
                records = client.get("/fixture/requests").json()

        parts = gemini.json()["candidates"][0]["content"]["parts"]
        self.assertEqual(gemini.status_code, 200)
        self.assertTrue(parts[0]["thought"])
        self.assertIn("inlineData", parts[2])
        self.assertEqual(
            openai_url.json()["data"][0]["url"],
            f"{base_url}/mock/assets/fixture.png",
        )
        self.assertEqual(openai_b64.json()["data"][0]["b64_json"], module.PNG_B64)
        self.assertEqual(rejected.status_code, 400)
        record_text = json.dumps(records, ensure_ascii=False)
        self.assertNotIn(module.PNG_B64, record_text)
        self.assertNotIn("Authorization", record_text)
        self.assertNotIn("fixture-mega-key-not-valid", record_text)


if __name__ == "__main__":
    unittest.main()
