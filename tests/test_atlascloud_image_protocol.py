from __future__ import annotations

import json
import unittest
from dataclasses import replace

from codex_image.generation.catalog import get_model_manifest
from codex_image.generation.types import GenerationCommand, ImageInput
from codex_image.providers.atlascloud import AtlasCloudImagesAdapter
from codex_image.providers.auth import auth_scheme_for_protocol
from codex_image.providers.codecs.gpt_image import GptAtlasCloudImagesCodec
from codex_image.providers.contracts import (
    ExecutionPlan,
    ProviderConnection,
    ProviderModelBinding,
)
from codex_image.providers.registry import default_registry
from tests.helpers import FakeResponse, FakeTransport, TEST_PNG_BASE64, TEST_PNG_BYTES


def _binding() -> ProviderModelBinding:
    return ProviderModelBinding(
        id="atlascloud-gpt-image-2",
        provider_id="atlascloud",
        canonical_model_id="gpt-image-2",
        remote_model_id="openai/gpt-image-2",
        protocol_profile="atlascloud_images",
        parameter_codec="gpt_atlascloud_images",
        operations=frozenset({"generate", "edit"}),
    )


def _provider(binding: ProviderModelBinding) -> ProviderConnection:
    return ProviderConnection(
        id="atlascloud",
        name="Atlas Cloud",
        base_url="https://api.atlascloud.ai",
        api_key="atlas-test-key",
        concurrency=2,
        bindings=(binding,),
    )


def _command(*, operation: str = "generate", **parameters) -> GenerationCommand:
    values = {
        "canvas.size": "1024x1024",
        "gpt.quality": "low",
        "gpt.background": "auto",
        "output.format": "png",
        "gpt.moderation": "auto",
        "gpt.output_compression": 80,
        "gpt.web_search": False,
        "output.count": 1,
        **parameters,
    }
    return GenerationCommand(
        operation=operation,  # type: ignore[arg-type]
        canonical_model_id="gpt-image-2",
        provider_id="atlascloud",
        prompt="draw a blue square",
        parameters=values,
        image_inputs=(ImageInput(data_url=f"data:image/png;base64,{TEST_PNG_BASE64}"),)
        if operation == "edit"
        else (),
    )


def _plan(command: GenerationCommand) -> ExecutionPlan:
    binding = _binding()
    request = GptAtlasCloudImagesCodec().encode(
        command, get_model_manifest("gpt-image-2"), binding
    )
    return ExecutionPlan(
        command=command,
        model=get_model_manifest("gpt-image-2"),
        provider=_provider(binding),
        binding=binding,
        protocol_request=request,
    )


class AtlasCloudImageProtocolTests(unittest.TestCase):
    def test_codec_routes_generate_and_edit_models(self) -> None:
        generate = _plan(_command())
        self.assertEqual(generate.protocol_request.path, "/api/v1/model/generateImage")
        self.assertEqual(
            generate.protocol_request.json_body["model"],
            "openai/gpt-image-2/text-to-image",
        )
        self.assertNotIn("images", generate.protocol_request.json_body)

        edit = _plan(_command(operation="edit"))
        self.assertEqual(
            edit.protocol_request.json_body["model"], "openai/gpt-image-2/edit"
        )
        self.assertEqual(
            edit.protocol_request.json_body["images"],
            [f"data:image/png;base64,{TEST_PNG_BASE64}"],
        )

    def test_codec_repeats_output_count_and_rejects_unsupported_controls(self) -> None:
        plan = _plan(_command(**{"output.count": 3}))
        self.assertEqual(plan.protocol_request.repeat_count, 3)
        with self.assertRaisesRegex(ValueError, "transparent"):
            _plan(_command(**{"gpt.background": "transparent"}))
        with self.assertRaisesRegex(ValueError, "PNG or JPEG"):
            _plan(_command(**{"output.format": "webp"}))
        with self.assertRaisesRegex(ValueError, "mask"):
            command = replace(
                _command(operation="edit"), mask_image="data:image/png;base64,x"
            )
            _plan(command)

    def test_adapter_polls_wrapped_prediction_and_decodes_data_url(self) -> None:
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=json.dumps(
                        {
                            "code": 200,
                            "data": {
                                "id": "prediction-123",
                                "status": "created",
                                "urls": {
                                    "get": "https://api.atlascloud.ai/api/v1/model/prediction/prediction-123"
                                },
                            },
                        }
                    ).encode(),
                ),
                FakeResponse(
                    status=200,
                    body=b'{"code":200,"data":{"id":"prediction-123","status":"processing"}}',
                ),
                FakeResponse(
                    status=200,
                    body=json.dumps(
                        {
                            "code": 200,
                            "data": {
                                "id": "prediction-123",
                                "status": "completed",
                                "outputs": [f"data:image/png;base64,{TEST_PNG_BASE64}"],
                            },
                        }
                    ).encode(),
                ),
            ]
        )
        result = AtlasCloudImagesAdapter(
            transport=transport, sleep=lambda _seconds: None, poll_interval=0
        ).execute(_plan(_command()))

        self.assertEqual(result.assets[0].image_bytes, TEST_PNG_BYTES)
        self.assertEqual(result.provider_metadata["prediction_id"], "prediction-123")
        self.assertEqual(
            [request["method"] for request in transport.requests],
            ["POST", "GET", "GET"],
        )
        self.assertEqual(
            json.loads(transport.requests[0]["body"])["model"],
            "openai/gpt-image-2/text-to-image",
        )

    def test_cross_origin_output_download_does_not_receive_api_key(self) -> None:
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=b'{"id":"prediction-456","status":"created"}',
                ),
                FakeResponse(
                    status=200,
                    body=b'{"id":"prediction-456","status":"completed","outputs":["https://cdn.example/image.png"]}',
                ),
                FakeResponse(
                    status=200,
                    body=TEST_PNG_BYTES,
                    headers={"Content-Type": "image/png"},
                ),
            ]
        )
        result = AtlasCloudImagesAdapter(
            transport=transport, sleep=lambda _seconds: None, poll_interval=0
        ).execute(_plan(_command()))

        self.assertEqual(result.assets[0].image_bytes, TEST_PNG_BYTES)
        self.assertEqual(
            transport.requests[1]["url"],
            "https://api.atlascloud.ai/api/v1/model/result/prediction-456",
        )
        self.assertNotIn("Authorization", transport.requests[-1]["headers"])

    def test_registry_and_auth_register_atlas_cloud(self) -> None:
        registry = default_registry()
        self.assertIsInstance(
            registry.protocol("atlascloud_images"), AtlasCloudImagesAdapter
        )
        self.assertIsInstance(
            registry.codec("gpt_atlascloud_images"), GptAtlasCloudImagesCodec
        )
        self.assertEqual(auth_scheme_for_protocol("atlascloud_images"), "bearer")


if __name__ == "__main__":
    unittest.main()
