from __future__ import annotations

import unittest

from codex_image import client
from codex_image.client import (
    CodexImageClient,
    CodexImagesImageClient,
    OpenAIImagesImageClient,
    OpenAIResponsesImageClient,
)


class CodexProviderContractTests(unittest.TestCase):
    def test_codex_images_payload_contract_is_unchanged(self) -> None:
        image_client = object.__new__(CodexImagesImageClient)
        image_client.image_model = "gpt-image-2"
        payload = image_client.build_payload(
            prompt="draw a rabbit",
            action="generate",
            model="gpt-image-2",
            size="1024x1024",
            quality="high",
            output_format="png",
            n=1,
        )

        self.assertEqual(payload["endpoint"], "/images/generations")
        self.assertEqual(payload["model"], "gpt-image-2")
        self.assertEqual(payload["size"], "1024x1024")
        self.assertNotIn("instructions", payload)

    def test_codex_responses_payload_contract_is_unchanged(self) -> None:
        responses_client = object.__new__(CodexImageClient)
        payload = responses_client.build_payload(
            prompt="draw a rabbit",
            action="generate",
            main_model="gpt-5.4-mini",
            model="gpt-image-2",
            output_format="png",
            web_search=True,
        )

        self.assertEqual(payload["model"], "gpt-5.4-mini")
        self.assertEqual(payload["tool_choice"], "required")
        self.assertEqual(payload["tools"][0]["type"], "web_search")
        self.assertEqual(payload["tools"][1]["model"], "gpt-image-2")

    def test_compatibility_imports_expose_codex_clients(self) -> None:
        self.assertIs(client.CodexImageClient, CodexImageClient)
        self.assertIs(client.CodexImagesImageClient, CodexImagesImageClient)
        self.assertIs(client.OpenAIImagesImageClient, OpenAIImagesImageClient)
        self.assertIs(client.OpenAIResponsesImageClient, OpenAIResponsesImageClient)
