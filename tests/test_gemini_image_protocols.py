from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import unittest

from codex_image.generation.catalog import get_model_manifest
from codex_image.generation.errors import GenerationProviderError
from codex_image.generation.types import GeneratedAsset, GenerationCommand, GenerationResult, ImageInput
from codex_image.providers.contracts import ExecutionPlan, ProviderConnection, ProviderModelBinding

# Protocol baseline rechecked 2026-07-15:
# https://ai.google.dev/gemini-api/docs/generate-content/image-generation
# https://ai.google.dev/gemini-api/docs/openai
# https://ai.google.dev/api/generate-content

FIXTURES = Path(__file__).parent / "fixtures" / "providers"


def _binding(*, profile: str, codec: str) -> ProviderModelBinding:
    return ProviderModelBinding(
        id=f"relay-{codec}",
        provider_id="relay",
        canonical_model_id="nano-banana-2",
        remote_model_id="vendor/custom-nano-pro",
        protocol_profile=profile,
        parameter_codec=codec,
        operations=frozenset({"generate", "edit"}),
    )


def _provider(binding: ProviderModelBinding, *, base_url: str) -> ProviderConnection:
    return ProviderConnection(
        id="relay",
        name="Relay",
        base_url=base_url,
        api_key="gemini-secret-key",
        concurrency=2,
        bindings=(binding,),
    )


def _command(*, operation: str = "generate") -> GenerationCommand:
    return GenerationCommand(
        operation=operation,  # type: ignore[arg-type]
        canonical_model_id="nano-banana-2",
        provider_id="relay",
        prompt="draw a rabbit",
        parameters={
            "canvas.aspect_ratio": "16:9",
            "canvas.resolution": "2K",
            "output.modalities": "IMAGE",
            "gemini.safety_settings": {
                "HARM_CATEGORY_HATE_SPEECH": "BLOCK_ONLY_HIGH",
            },
            "gemini.google_search": True,
            "gemini.google_image_search": True,
            "output.count": 2,
        },
        image_inputs=(
            ImageInput("data:image/png;base64,aW5wdXQtaW1hZ2U="),
        ),
    )


def _plan(*, profile: str, codec: str, base_url: str, operation: str = "generate") -> ExecutionPlan:
    from codex_image.providers.codecs.gemini_image import (
        GeminiGenerateContentImageCodec,
        GeminiGenerateContentImageConfigCodec,
        GeminiOpenAIImagesCodec,
        GeminiOpenRouterImagesCodec,
        GeminiT8ImagesCodec,
    )

    binding = _binding(profile=profile, codec=codec)
    command = _command(operation=operation)
    codecs = {
        "gemini_generate_content_image": GeminiGenerateContentImageCodec(),
        "gemini_generate_content_image_config": GeminiGenerateContentImageConfigCodec(),
        "gemini_openai_images": GeminiOpenAIImagesCodec(),
        "gemini_t8_images": GeminiT8ImagesCodec(),
        "gemini_openrouter_images": GeminiOpenRouterImagesCodec(),
    }
    codec_impl = codecs[codec]
    return ExecutionPlan(
        command=command,
        model=get_model_manifest("nano-banana-2"),
        provider=_provider(binding, base_url=base_url),
        binding=binding,
        protocol_request=codec_impl.encode(
            command,
            get_model_manifest("nano-banana-2"),
            binding,
        ),
    )


class GeminiImageCodecTests(unittest.TestCase):
    def test_native_codec_encodes_both_four_category_safety_presets(self) -> None:
        from codex_image.providers.codecs.gemini_image import GeminiGenerateContentImageCodec

        categories = (
            "HARM_CATEGORY_HARASSMENT",
            "HARM_CATEGORY_HATE_SPEECH",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT",
            "HARM_CATEGORY_DANGEROUS_CONTENT",
        )
        binding = _binding(
            profile="gemini_generate_content",
            codec="gemini_generate_content_image",
        )
        model = get_model_manifest("nano-banana-2")
        for threshold in ("OFF", "BLOCK_LOW_AND_ABOVE"):
            with self.subTest(threshold=threshold):
                command = _command()
                command = replace(command, parameters={
                    **command.parameters,
                    "gemini.safety_settings": {
                        category: threshold for category in categories
                    },
                })
                request = GeminiGenerateContentImageCodec().encode(command, model, binding)
                self.assertEqual(
                    {
                        item["category"]: item["threshold"]
                        for item in request.json_body["safetySettings"]
                    },
                    {category: threshold for category in categories},
                )

    def test_generate_content_codec_preserves_custom_model_and_native_shape(self) -> None:
        plan = _plan(
            profile="gemini_generate_content",
            codec="gemini_generate_content_image",
            base_url="https://relay.example/v1beta",
        )
        request = plan.protocol_request
        body = dict(request.json_body or {})

        self.assertEqual(request.path, "/models/vendor%2Fcustom-nano-pro:generateContent")
        self.assertNotIn("interactions", request.path)
        self.assertEqual(
            body["contents"][0]["parts"],
            [
                {"text": "draw a rabbit"},
                {
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": "aW5wdXQtaW1hZ2U=",
                    }
                },
            ],
        )
        self.assertEqual(
            body["tools"],
            [
                {
                    "google_search": {
                        "searchTypes": {"webSearch": {}, "imageSearch": {}}
                    }
                }
            ],
        )
        self.assertEqual(
            body["generationConfig"],
            {
                "responseModalities": ["IMAGE"],
                "responseFormat": {
                    "image": {"aspectRatio": "16:9", "imageSize": "2K"}
                },
                "candidateCount": 2,
            },
        )
        self.assertEqual(
            body["safetySettings"],
            [
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_ONLY_HIGH",
                }
            ],
        )

    def test_openai_codec_keeps_gemini_extensions_at_http_top_level(self) -> None:
        plan = _plan(
            profile="openai_images",
            codec="gemini_openai_images",
            base_url="https://relay.example/v1",
        )
        body = dict(plan.protocol_request.json_body or {})

        self.assertEqual(plan.protocol_request.path, "/images/generations")
        self.assertEqual(body["model"], "vendor/custom-nano-pro")
        self.assertEqual(body["n"], 2)
        self.assertEqual(body["response_format"], "b64_json")
        self.assertEqual(body["aspect_ratio"], "16:9")
        self.assertEqual(
            body["generation_config"],
            {
                "responseModalities": ["IMAGE"],
                "responseFormat": {"image": {"aspectRatio": "16:9", "imageSize": "2K"}},
            },
        )
        self.assertEqual(
            body["safety_settings"],
            [
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_ONLY_HIGH",
                }
            ],
        )
        self.assertEqual(
            body["tools"],
            [{"google_search": {"searchTypes": {"webSearch": {}, "imageSearch": {}}}}],
        )
        self.assertNotIn("extra_body", body)

    def test_openai_edit_uses_explicit_multipart_fields_and_files(self) -> None:
        plan = _plan(
            profile="openai_images",
            codec="gemini_openai_images",
            base_url="https://relay.example/v1",
            operation="edit",
        )
        request = plan.protocol_request

        self.assertEqual(request.path, "/images/edits")
        self.assertIsNone(request.json_body)
        self.assertEqual(request.form_fields["model"], "vendor/custom-nano-pro")
        self.assertEqual(json.loads(request.form_fields["generation_config"])["responseModalities"], ["IMAGE"])
        self.assertEqual(request.files[0][0:3], ("image", "input-1.png", "image/png"))
        self.assertEqual(request.files[0][3], b"input-image")

    def test_image_config_compatibility_uses_change2_bafang_shape(self) -> None:
        plan = _plan(
            profile="gemini_generate_content",
            codec="gemini_generate_content_image_config",
            base_url="https://relay.example/v1beta",
        )
        body = dict(plan.protocol_request.json_body or {})

        self.assertEqual(
            body["generationConfig"]["imageConfig"],
            {"aspectRatio": "16:9", "imageSize": "2K"},
        )
        self.assertNotIn("responseFormat", body["generationConfig"])
        self.assertEqual(
            body["contents"][0]["parts"][1],
            {
                "inlineData": {
                    "mimeType": "image/png",
                    "data": "aW5wdXQtaW1hZ2U=",
                }
            },
        )

    def test_t8_newapi_compatibility_keeps_only_supported_top_level_fields(self) -> None:
        generate = _plan(
            profile="t8_images",
            codec="gemini_t8_images",
            base_url="https://ai.t8star.org/v1",
        ).protocol_request
        self.assertEqual(generate.path, "/images/generations?async=true")
        self.assertEqual(
            generate.json_body,
            {
                "model": "vendor/custom-nano-pro",
                "prompt": "draw a rabbit",
                "aspect_ratio": "16:9",
                "image_size": "2K",
                "response_format": "b64_json",
            },
        )

        edit = _plan(
            profile="t8_images",
            codec="gemini_t8_images",
            base_url="https://ai.t8star.org/v1",
            operation="edit",
        ).protocol_request
        self.assertEqual(edit.path, "/images/edits?async=true")
        self.assertEqual(edit.form_fields["aspect_ratio"], "16:9")
        self.assertEqual(edit.form_fields["image_size"], "2K")
        self.assertEqual(edit.files[0][0:3], ("image", "input-1.png", "image/png"))

    def test_openrouter_compatibility_uses_current_images_endpoint_shape(self) -> None:
        request = _plan(
            profile="openrouter_images",
            codec="gemini_openrouter_images",
            base_url="https://openrouter.ai/api/v1",
        ).protocol_request
        self.assertEqual(request.path, "/images")
        self.assertEqual(
            request.json_body,
            {
                "model": "vendor/custom-nano-pro",
                "prompt": "draw a rabbit",
                "n": 2,
                "aspect_ratio": "16:9",
                "resolution": "2K",
                "input_references": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,aW5wdXQtaW1hZ2U="
                        },
                    }
                ],
            },
        )


class GeminiGenerateContentAdapterTests(unittest.TestCase):
    def _execute(self, *, status: int = 200, body: bytes | None = None):
        from codex_image.providers.gemini import GeminiGenerateContentAdapter
        from tests.helpers import FakeResponse, FakeTransport

        response_body = body or (FIXTURES / "gemini_generate_content_response.json").read_bytes()
        transport = FakeTransport([FakeResponse(status=status, body=response_body)])
        plan = _plan(
            profile="gemini_generate_content",
            codec="gemini_generate_content_image",
            base_url="https://relay.example/v1beta",
        )
        result = GeminiGenerateContentAdapter(transport=transport).execute(plan)
        return result, transport

    def test_native_adapter_uses_only_x_goog_key_and_parses_final_assets(self) -> None:
        result, transport = self._execute()

        self.assertEqual(len(transport.requests), 1)
        request = transport.requests[0]
        self.assertEqual(
            request["url"],
            "https://relay.example/v1beta/models/vendor%2Fcustom-nano-pro:generateContent",
        )
        self.assertEqual(request["headers"]["x-goog-api-key"], "gemini-secret-key")
        self.assertNotIn("Authorization", request["headers"])
        self.assertEqual([asset.image_bytes for asset in result.assets], [b"final-image"])
        self.assertEqual(result.text_parts, ("Here is the finished image.",))
        self.assertEqual(result.usage["totalTokenCount"], 46)
        self.assertEqual(
            result.provider_metadata["grounding"][0]["sources"][0]["page_uri"],
            "https://example.com/rabbits",
        )

    def test_change2pro_adapter_routes_shared_v1_base_to_gemini_v1beta(self) -> None:
        from codex_image.providers.gemini import Change2ProGeminiAdapter
        from tests.helpers import FakeResponse, FakeTransport

        transport = FakeTransport([
            FakeResponse(
                status=200,
                body=(FIXTURES / "gemini_generate_content_response.json").read_bytes(),
            )
        ])
        plan = _plan(
            profile="gemini_change2pro_generate_content",
            codec="gemini_generate_content_image_config",
            base_url="https://api.change2pro.com/v1",
        )

        result = Change2ProGeminiAdapter(transport=transport).execute(plan)

        self.assertEqual(result.assets[0].image_bytes, b"final-image")
        self.assertEqual(
            transport.requests[0]["url"],
            "https://api.change2pro.com/v1beta/models/vendor%2Fcustom-nano-pro:generateContent",
        )
        self.assertEqual(
            transport.requests[0]["headers"]["x-goog-api-key"],
            "gemini-secret-key",
        )

    def test_native_adapter_rejects_thought_only_response(self) -> None:
        body = json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "thought": True,
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": "dGhvdWdodA==",
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ).encode()
        with self.assertRaises(GenerationProviderError) as raised:
            self._execute(body=body)
        self.assertEqual(raised.exception.detail.code, "upstream_error")

    def test_image_config_relay_can_return_an_unauthenticated_file_url(self) -> None:
        from codex_image.providers.gemini import GeminiGenerateContentAdapter
        from tests.helpers import FakeResponse, FakeTransport

        body = json.dumps({
            "candidates": [{
                "content": {
                    "parts": [{
                        "fileData": {
                            "mimeType": "image/png",
                            "fileUri": "https://assets.example/final.png",
                        }
                    }]
                }
            }]
        }).encode()
        png = b"\x89PNG\r\n\x1a\n" + b"test-image"
        transport = FakeTransport([
            FakeResponse(status=200, body=body),
            FakeResponse(status=200, body=png, headers={"Content-Type": "image/png"}),
        ])
        plan = _plan(
            profile="gemini_generate_content",
            codec="gemini_generate_content_image_config",
            base_url="https://relay.example/v1beta",
        )

        result = GeminiGenerateContentAdapter(transport=transport).execute(plan)

        self.assertEqual(result.assets[0].image_bytes, png)
        self.assertEqual(transport.requests[1]["url"], "https://assets.example/final.png")
        self.assertNotIn("x-goog-api-key", transport.requests[1]["headers"])

    def test_native_adapter_maps_http_errors_without_retrying_or_leaking(self) -> None:
        from codex_image.providers.gemini import GeminiGenerateContentAdapter
        from tests.helpers import FakeResponse, FakeTransport

        transport = FakeTransport(
            [FakeResponse(status=400, body=b'{"error":{"message":"gemini-secret-key draw a rabbit"}}')]
        )
        plan = _plan(
            profile="gemini_generate_content",
            codec="gemini_generate_content_image",
            base_url="https://relay.example/v1beta",
        )
        with self.assertRaises(GenerationProviderError) as raised:
            GeminiGenerateContentAdapter(transport=transport).execute(plan)

        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(raised.exception.detail.code, "invalid_parameters")
        self.assertFalse(raised.exception.detail.retryable)
        self.assertNotIn("gemini-secret-key", str(raised.exception))
        self.assertNotIn("draw a rabbit", str(raised.exception))

    def test_http_error_taxonomy(self) -> None:
        cases = (
            (401, "authentication_failed", False),
            (403, "authentication_failed", False),
            (422, "invalid_parameters", False),
            (429, "rate_limited", True),
            (500, "upstream_error", True),
        )
        for status, code, retryable in cases:
            with self.subTest(status=status):
                with self.assertRaises(GenerationProviderError) as raised:
                    self._execute(status=status, body=b'{"error":{"message":"failed"}}')
                self.assertEqual(raised.exception.detail.code, code)
                self.assertEqual(raised.exception.detail.retryable, retryable)


class GeminiOpenAIAdapterTests(unittest.TestCase):
    def test_openai_compatible_uses_only_bearer_and_keeps_extension_fields(self) -> None:
        from codex_image.providers.openai import OpenAIImagesAdapter
        from tests.helpers import FakeResponse, FakeTransport

        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=(FIXTURES / "gemini_openai_images_response.json").read_bytes(),
                )
            ]
        )
        result = OpenAIImagesAdapter(transport=transport).execute(
            _plan(
                profile="openai_images",
                codec="gemini_openai_images",
                base_url="https://relay.example/v1",
            )
        )

        self.assertEqual(result.assets[0].image_bytes, b"final-image")
        self.assertEqual(len(transport.requests), 1)
        request = transport.requests[0]
        self.assertEqual(request["headers"]["Authorization"], "Bearer gemini-secret-key")
        self.assertNotIn("x-goog-api-key", request["headers"])
        body = json.loads(request["body"])
        self.assertEqual(body["model"], "vendor/custom-nano-pro")
        self.assertEqual(body["aspect_ratio"], "16:9")
        self.assertIn("generation_config", body)
        self.assertIn("safety_settings", body)
        self.assertIn("tools", body)
        self.assertNotIn("extra_body", body)

    def test_openai_compatible_invalid_parameters_are_not_retried(self) -> None:
        from codex_image.providers.openai import OpenAIImagesAdapter
        from tests.helpers import FakeResponse, FakeTransport

        transport = FakeTransport(
            [FakeResponse(status=400, body=b'{"error":{"message":"unsupported parameter"}}')]
        )
        with self.assertRaises(GenerationProviderError) as raised:
            OpenAIImagesAdapter(transport=transport).execute(
                _plan(
                    profile="openai_images",
                    codec="gemini_openai_images",
                    base_url="https://relay.example/v1",
                )
            )

        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(raised.exception.detail.code, "invalid_parameters")
        self.assertFalse(raised.exception.detail.retryable)

    def test_openrouter_media_type_is_preserved_for_base64_results(self) -> None:
        from codex_image.providers.openai import OpenAIImagesAdapter
        from tests.helpers import FakeResponse, FakeTransport

        transport = FakeTransport([
            FakeResponse(
                status=200,
                body=b'{"data":[{"b64_json":"ZmluYWwtaW1hZ2U=","media_type":"image/webp"}]}',
            )
        ])
        result = OpenAIImagesAdapter(transport=transport).execute(
            _plan(
                profile="openrouter_images",
                codec="gemini_openrouter_images",
                base_url="https://openrouter.ai/api/v1",
            )
        )

        self.assertEqual(result.assets[0].image_bytes, b"final-image")
        self.assertEqual(result.assets[0].mime_type, "image/webp")


class GeminiT8AdapterTests(unittest.TestCase):
    def test_async_task_is_polled_and_nested_openai_image_result_is_parsed(self) -> None:
        from codex_image.providers.t8 import T8ImagesAdapter
        from tests.helpers import FakeResponse, FakeTransport

        transport = FakeTransport([
            FakeResponse(status=200, body=b'{"task_id":"task-123"}'),
            FakeResponse(
                status=200,
                body=b'{"data":{"status":"SUCCESS","data":{"data":[{"b64_json":"ZmluYWwtaW1hZ2U="}]}}}',
            ),
        ])
        plan = _plan(
            profile="t8_images",
            codec="gemini_t8_images",
            base_url="https://ai.t8star.org/v1",
        )
        sleeps: list[float] = []
        result = T8ImagesAdapter(
            transport=transport,
            sleep=sleeps.append,
            poll_attempts=2,
        ).execute(plan)

        self.assertEqual(result.assets[0].image_bytes, b"final-image")
        self.assertEqual(transport.requests[0]["url"], "https://ai.t8star.org/v1/images/generations?async=true")
        self.assertEqual(transport.requests[1]["method"], "GET")
        self.assertEqual(transport.requests[1]["url"], "https://ai.t8star.org/v1/images/tasks/task-123")
        self.assertEqual(transport.requests[1]["headers"]["Authorization"], "Bearer gemini-secret-key")
        self.assertEqual(sleeps, [10.0])

    def test_async_task_accepts_t8_data_url_in_b64_json(self) -> None:
        from codex_image.providers.t8 import T8ImagesAdapter
        from tests.helpers import FakeResponse, FakeTransport

        transport = FakeTransport([
            FakeResponse(status=200, body=b'{"task_id":"task-data-url"}'),
            FakeResponse(
                status=200,
                body=(
                    b'{"code":"success","data":{"status":"SUCCESS","data":{"data":['
                    b'{"url":"https://assets.example/final.png",'
                    b'"b64_json":"data:image/png;base64,ZmluYWwtaW1hZ2U="}'
                    b']}}}'
                ),
            ),
        ])
        result = T8ImagesAdapter(
            transport=transport,
            sleep=lambda _seconds: None,
            poll_attempts=1,
        ).execute(
            _plan(
                profile="t8_images",
                codec="gemini_t8_images",
                base_url="https://ai.t8star.org/v1",
            )
        )

        self.assertEqual(result.assets[0].image_bytes, b"final-image")
        self.assertEqual(result.assets[0].mime_type, "image/png")
        self.assertEqual(len(transport.requests), 2)


class GeminiRegistrationTests(unittest.TestCase):
    def test_default_registry_registers_native_and_openai_compatible_gemini(self) -> None:
        from codex_image.providers.gemini import Change2ProGeminiAdapter, GeminiGenerateContentAdapter
        from codex_image.providers.codecs.gemini_image import (
            GeminiGenerateContentImageCodec,
            GeminiGenerateContentImageConfigCodec,
            GeminiOpenAIImagesCodec,
            GeminiOpenRouterImagesCodec,
            GeminiT8ImagesCodec,
        )
        from codex_image.providers.openai import OpenAIImagesAdapter
        from codex_image.providers.t8 import T8ImagesAdapter
        from codex_image.providers.registry import default_registry

        registry = default_registry()
        self.assertIsInstance(registry.protocol("gemini_generate_content"), GeminiGenerateContentAdapter)
        self.assertIsInstance(
            registry.protocol("gemini_change2pro_generate_content"),
            Change2ProGeminiAdapter,
        )
        self.assertIsInstance(
            registry.codec("gemini_generate_content_image"), GeminiGenerateContentImageCodec
        )
        self.assertIsInstance(registry.codec("gemini_openai_images"), GeminiOpenAIImagesCodec)
        self.assertIsInstance(
            registry.codec("gemini_generate_content_image_config"),
            GeminiGenerateContentImageConfigCodec,
        )
        self.assertIsInstance(registry.protocol("t8_images"), T8ImagesAdapter)
        self.assertIsInstance(registry.codec("gemini_t8_images"), GeminiT8ImagesCodec)
        self.assertIsInstance(registry.protocol("openrouter_images"), OpenAIImagesAdapter)
        self.assertIsInstance(
            registry.codec("gemini_openrouter_images"), GeminiOpenRouterImagesCodec
        )


class GeminiExecutionPlanClientTests(unittest.TestCase):
    def test_batch_assets_are_distributed_without_duplicate_upstream_request(self) -> None:
        from codex_image.providers.codecs.gemini_image import GeminiGenerateContentImageCodec
        from codex_image.providers.registry import ProviderRegistry
        from codex_image.webui.execution_plan_client import ExecutionPlanImageClient

        class BatchProtocol:
            def __init__(self) -> None:
                self.calls = 0

            def execute(self, plan: ExecutionPlan) -> GenerationResult:
                self.calls += 1
                return GenerationResult(
                    assets=(
                        GeneratedAsset(b"image-one", "image/png"),
                        GeneratedAsset(b"image-two", "image/png"),
                    ),
                    text_parts=("Search-assisted result",),
                    usage={"totalTokenCount": 46},
                    provider_metadata={"grounding": [{"sources": []}]},
                )

        protocol = BatchProtocol()
        registry = ProviderRegistry(
            protocols={"gemini_generate_content": protocol},
            codecs={"gemini_generate_content_image": GeminiGenerateContentImageCodec()},
        )
        client = ExecutionPlanImageClient(
            _plan(
                profile="gemini_generate_content",
                codec="gemini_generate_content_image",
                base_url="https://relay.example/v1beta",
            ),
            object(),
            registry=registry,
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: client.generate_image(), range(2)))

        self.assertEqual(protocol.calls, 1)
        self.assertEqual({item.image_bytes for item in results}, {b"image-one", b"image-two"})
        for result in results:
            self.assertEqual(result.tool_usage["text_parts"], ["Search-assisted result"])
            self.assertIn("grounding", result.tool_usage["provider_metadata"])


if __name__ == "__main__":
    unittest.main()
