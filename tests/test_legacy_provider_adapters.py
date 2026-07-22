from __future__ import annotations

import base64
import unittest
from dataclasses import replace
from types import MappingProxyType
from typing import Any
from unittest.mock import patch

from codex_image.generation.catalog import get_model_manifest
from codex_image.generation.resolver import BindingResolver
from codex_image.generation.service import (
    GenerationService,
    merge_generation_results,
    redacted_protocol_request,
)
from codex_image.generation.types import (
    GeneratedAsset,
    GenerationCommand,
    GenerationResult,
)
from codex_image.providers.codex import CodexImagesAdapter, CodexResponsesAdapter
from codex_image.providers.codecs.gpt_image import (
    GptCodexImagesCodec,
    GptCodexResponsesCodec,
    GptOpenAIImagesCodec,
    GptOpenAIResponsesCodec,
)
from codex_image.providers.contracts import (
    ExecutionPlan,
    ProtocolRequest,
    ProviderConnection,
    ProviderModelBinding,
)
from codex_image.providers.openai import OpenAIImagesAdapter, OpenAIResponsesAdapter
from codex_image.providers.registry import ProviderRegistry, default_registry


def _binding(
    *,
    profile: str,
    codec: str,
    remote_model_id: str = "relay/custom-gpt-image",
    provider_id: str = "relay",
) -> ProviderModelBinding:
    return ProviderModelBinding(
        id=f"{provider_id}-{codec}",
        provider_id=provider_id,
        canonical_model_id="gpt-image-2",
        remote_model_id=remote_model_id,
        protocol_profile=profile,
        parameter_codec=codec,
        operations=frozenset({"generate", "edit"}),
    )


def _provider(binding: ProviderModelBinding) -> ProviderConnection:
    return ProviderConnection(
        id=binding.provider_id,
        name="Relay",
        base_url="https://relay.example/v1",
        api_key="test-secret-key",
        concurrency=2,
        bindings=(binding,),
    )


def _command(
    *,
    operation: str = "generate",
    count: int = 1,
    image_inputs: tuple[Any, ...] = (),
) -> GenerationCommand:
    return GenerationCommand(
        operation=operation,  # type: ignore[arg-type]
        canonical_model_id="gpt-image-2",
        provider_id="relay",
        prompt="draw a rabbit",
        parameters={
            "canvas.size": "1024x1024",
            "gpt.quality": "low",
            "gpt.background": "opaque",
            "output.format": "png",
            "gpt.moderation": "auto",
            "output.count": count,
        },
        image_inputs=image_inputs,
        main_model="gpt-5.4-mini",
        instructions="preserve the prompt",
    )


def _plan(
    request: ProtocolRequest,
    *,
    profile: str = "openai_images",
    codec: str = "gpt_openai_images",
) -> ExecutionPlan:
    binding = _binding(profile=profile, codec=codec)
    return ExecutionPlan(
        command=_command(),
        model=get_model_manifest("gpt-image-2"),
        provider=_provider(binding),
        binding=binding,
        protocol_request=request,
    )


class _RecordingProtocol:
    def __init__(self) -> None:
        self.plans: list[ExecutionPlan] = []

    def execute(self, plan: ExecutionPlan) -> GenerationResult:
        self.plans.append(plan)
        index = len(self.plans)
        return GenerationResult(
            assets=(GeneratedAsset(image_bytes=f"image-{index}".encode(), mime_type="image/png"),),
            usage={"request": index},
            provider_metadata={"request": index},
        )


class LegacyProviderAdapterTests(unittest.TestCase):
    def test_codex_images_codec_matches_existing_payload(self) -> None:
        from codex_image.codex_images_client import CodexImagesImageClient

        command = _command(count=2)
        binding = _binding(
            provider_id="codex",
            profile="codex_images",
            codec="gpt_codex_images",
            remote_model_id="gpt-image-2",
        )
        legacy_client = object.__new__(CodexImagesImageClient)
        legacy_client.image_model = "gpt-image-2"
        legacy = legacy_client.build_payload(
            prompt=command.prompt,
            action="generate",
            model=binding.remote_model_id,
            input_images=[],
            size="1024x1024",
            quality="low",
            background="opaque",
            output_format="png",
            moderation="auto",
            n=2,
        )

        encoded = GptCodexImagesCodec().encode(
            command, get_model_manifest("gpt-image-2"), binding
        )

        self.assertEqual(dict(encoded.json_body or {}), legacy)
        self.assertEqual(encoded.path, "/images/generations")
        self.assertEqual(encoded.repeat_count, 1)

    def test_codex_responses_codec_matches_existing_payload(self) -> None:
        from codex_image.codex_responses_client import CodexImageClient

        command = _command()
        binding = _binding(
            provider_id="codex",
            profile="codex_responses",
            codec="gpt_codex_responses",
            remote_model_id="gpt-image-2",
        )
        legacy_client = object.__new__(CodexImageClient)
        legacy = legacy_client.build_payload(
            prompt=command.prompt,
            instructions=command.instructions,
            action="generate",
            main_model=command.main_model or "",
            model=binding.remote_model_id,
            input_images=[],
            size="1024x1024",
            quality="low",
            background="opaque",
            output_format="png",
            moderation="auto",
        )

        encoded = GptCodexResponsesCodec().encode(
            command, get_model_manifest("gpt-image-2"), binding
        )

        self.assertEqual(dict(encoded.json_body or {}), legacy)
        self.assertEqual(encoded.path, "/responses")

    def test_openai_images_codec_preserves_custom_remote_model_id(self) -> None:
        binding = _binding(profile="openai_images", codec="gpt_openai_images")
        body = dict(
            GptOpenAIImagesCodec()
            .encode(_command(count=3), get_model_manifest("gpt-image-2"), binding)
            .json_body
            or {}
        )
        self.assertEqual(body["model"], "relay/custom-gpt-image")
        self.assertEqual(body["n"], 3)

    def test_openai_responses_codec_keeps_main_and_image_models_separate(self) -> None:
        binding = _binding(profile="openai_responses", codec="gpt_openai_responses")
        body = dict(
            GptOpenAIResponsesCodec()
            .encode(_command(), get_model_manifest("gpt-image-2"), binding)
            .json_body
            or {}
        )
        self.assertEqual(body["model"], "gpt-5.4-mini")
        image_tool = next(tool for tool in body["tools"] if tool["type"] == "image_generation")
        self.assertEqual(image_tool["model"], binding.remote_model_id)

    def test_all_gpt_codecs_declare_explicit_capabilities(self) -> None:
        manifest = get_model_manifest("gpt-image-2")
        required = {
            parameter.id
            for parameter in manifest.parameters
            if parameter.scope == "model"
        }
        for codec in (
            GptCodexImagesCodec(),
            GptCodexResponsesCodec(),
            GptOpenAIImagesCodec(),
            GptOpenAIResponsesCodec(),
        ):
            self.assertTrue(required <= codec.mapped_parameter_ids(manifest, "generate"))

    def test_openai_multipart_accepts_arbitrary_scalar_fields_and_explicit_files(self) -> None:
        from codex_image.openai_images_client import build_multipart_body

        body, content_type = build_multipart_body(
            {"model": "custom", "vendor_extension": "kept", "candidateCount": 2},
            (("image", "input.png", "image/png", b"input-bytes"),),
        )
        text = body.decode("utf-8", errors="replace")
        self.assertIn("multipart/form-data; boundary=", content_type)
        self.assertIn('name="vendor_extension"', text)
        self.assertIn("kept", text)
        self.assertIn('name="candidateCount"', text)
        self.assertIn('name="image"; filename="input.png"', text)
        self.assertIn(b"input-bytes", body)

    def test_codex_adapters_delegate_to_public_clients(self) -> None:
        result = _image_result()
        plan = _plan(
            ProtocolRequest("POST", "/images/generations", "application/json", json_body={}),
            profile="codex_images",
            codec="gpt_codex_images",
        )
        plan = replace(plan, command=_command(count=2))
        with patch("codex_image.providers.codex.CodexImagesImageClient") as client_type:
            client_type.return_value.generate_images.return_value = [result]
            converted = CodexImagesAdapter(auth_provider=object()).execute(plan)
        client_type.return_value.generate_images.assert_called_once()
        self.assertEqual(client_type.return_value.generate_images.call_args.kwargs["n"], 2)
        self.assertEqual(converted.assets[0].image_bytes, b"image")

        responses_plan = replace(
            plan,
            binding=replace(
                plan.binding,
                protocol_profile="codex_responses",
                parameter_codec="gpt_codex_responses",
            ),
            protocol_request=replace(plan.protocol_request, path="/responses"),
        )
        with patch("codex_image.providers.codex.CodexImageClient") as client_type:
            client_type.return_value.generate_image.return_value = result
            converted = CodexResponsesAdapter(auth_provider=object()).execute(responses_plan)
        client_type.return_value.generate_image.assert_called_once()
        self.assertEqual(converted.assets[0].image_bytes, b"image")

    def test_openai_adapters_execute_encoded_requests(self) -> None:
        from tests.helpers import FakeResponse, FakeTransport, make_sse_completed_event

        image_body = base64.b64encode(b"direct").decode("ascii")
        images_transport = FakeTransport(
            [FakeResponse(status=200, body=(f'{{"data":[{{"b64_json":"{image_body}"}}]}}').encode())]
        )
        images_request = ProtocolRequest(
            method="POST",
            path="/images/generations",
            content_type="application/json",
            json_body={"model": "custom", "prompt": "draw", "n": 1, "output_format": "png"},
        )
        images_result = OpenAIImagesAdapter(transport=images_transport).execute(_plan(images_request))
        self.assertEqual(images_result.assets[0].image_bytes, b"direct")

        responses_transport = FakeTransport(
            [FakeResponse(status=200, body=make_sse_completed_event(image_b64=image_body))]
        )
        responses_request = ProtocolRequest(
            method="POST",
            path="/responses",
            content_type="application/json",
            json_body={"model": "main", "input": [], "tools": []},
        )
        responses_result = OpenAIResponsesAdapter(transport=responses_transport).execute(
            _plan(responses_request, profile="openai_responses", codec="gpt_openai_responses")
        )
        self.assertEqual(responses_result.assets[0].image_bytes, b"direct")

    def test_openai_images_client_and_adapter_share_identical_http_error_handling(self) -> None:
        from codex_image.openai_images_client import (
            OpenAIImagesImageClient,
            raise_for_openai_images_response,
        )
        from tests.helpers import FakeResponse, FakeTransport

        response = FakeResponse(status=429, body=b'{"error":{"message":"rate limited"}}')
        client = OpenAIImagesImageClient(
            api_key="test-secret-key",
            base_url="https://relay.example/v1",
            transport=FakeTransport([response]),
        )
        with self.assertRaises(RuntimeError) as legacy_error:
            client.generate_image(prompt="draw")

        request = ProtocolRequest(
            method="POST",
            path="/images/generations",
            content_type="application/json",
            json_body={"model": "custom", "prompt": "draw", "n": 1, "output_format": "png"},
        )
        with self.assertRaises(RuntimeError) as adapter_error:
            OpenAIImagesAdapter(transport=FakeTransport([response])).execute(_plan(request))

        self.assertTrue(callable(raise_for_openai_images_response))
        self.assertIs(type(adapter_error.exception), type(legacy_error.exception))
        self.assertEqual(str(adapter_error.exception), str(legacy_error.exception))

    def test_generation_service_executes_repeat_count_as_single_requests_and_merges(self) -> None:
        protocol = _RecordingProtocol()
        registry = ProviderRegistry(protocols={"recording": protocol}, codecs={})
        plan = _plan(ProtocolRequest("POST", "/generate", "application/json", repeat_count=3))
        plan = replace(plan, binding=replace(plan.binding, protocol_profile="recording"))

        class Resolver:
            def resolve(self, command: GenerationCommand) -> ExecutionPlan:
                return plan

        service = GenerationService(Resolver(), registry)  # type: ignore[arg-type]
        self.assertIs(service.preview(plan.command), plan)
        result = service.execute(plan.command)

        self.assertEqual(len(protocol.plans), 3)
        self.assertEqual([item.protocol_request.repeat_count for item in protocol.plans], [1, 1, 1])
        self.assertEqual([asset.image_bytes for asset in result.assets], [b"image-1", b"image-2", b"image-3"])
        self.assertEqual(result.usage, {"requests": [{"request": 1}, {"request": 2}, {"request": 3}]})

    def test_merge_generation_results_requires_input_and_preserves_single_metadata(self) -> None:
        with self.assertRaisesRegex(ValueError, "At least one generation result"):
            merge_generation_results([])
        single = GenerationResult(assets=(), usage={"tokens": 1}, provider_metadata={"id": "x"})
        self.assertEqual(merge_generation_results([single]), single)

    def test_redacted_protocol_request_removes_secrets_and_binary_data(self) -> None:
        plan = _plan(
            ProtocolRequest(
                method="POST",
                path="https://relay.example/generate?key=url-secret&safe=yes",
                content_type="application/json",
                json_body={
                    "api_key": "json-secret",
                    "image": {"image_url": "data:image/png;base64,aW1hZ2U="},
                    "input": [{"file_data": "data:application/pdf;base64,cGRm"}],
                    "prompt": "safe",
                },
                form_fields={"token": "form-secret", "prompt": "safe"},
                files=(("image", "secret.png", "image/png", b"secret-bytes"),),
            )
        )
        redacted = redacted_protocol_request(plan)
        dump = repr(redacted)
        for secret in ("url-secret", "json-secret", "aW1hZ2U", "cGRm", "form-secret", "secret-bytes"):
            self.assertNotIn(secret, dump)
        self.assertIn("safe", dump)

    def test_redacted_protocol_request_covers_url_auth_fragments_and_header_variants(self) -> None:
        plan = _plan(
            ProtocolRequest(
                method="POST",
                path=(
                    "https://url-user:url-password@relay.example/generate?view=full"
                    "#access_token=fragment-secret&panel=preview"
                ),
                content_type="application/json",
                json_body=MappingProxyType(
                    {
                        "X-Goog-Api-Key": "google-secret",
                        "X_Api_Key": "api-secret",
                        "Proxy-Authorization": "proxy-secret",
                        "data": "ordinary prompt data",
                    }
                ),
                form_fields=MappingProxyType(
                    {
                        "authorization": "bearer-secret",
                        "prompt": "keep this prompt",
                    }
                ),
            )
        )

        redacted = redacted_protocol_request(plan)
        dump = repr(redacted)
        for secret in (
            "url-user",
            "url-password",
            "fragment-secret",
            "google-secret",
            "api-secret",
            "proxy-secret",
            "bearer-secret",
        ):
            self.assertNotIn(secret, dump)
        self.assertIn("view=full", redacted.path)
        self.assertIn("panel=preview", redacted.path)
        self.assertEqual(redacted.json_body["data"], "ordinary prompt data")
        self.assertEqual(redacted.form_fields["prompt"], "keep this prompt")

    def test_redacted_protocol_request_covers_gemini_camel_case_inline_and_file_data(self) -> None:
        plan = _plan(
            ProtocolRequest(
                method="POST",
                path="/generate",
                content_type="application/json",
                json_body={
                    "inlineData": {
                        "mimeType": "image/png",
                        "data": "RAW-IMAGE-BASE64",
                    },
                    "fileData": {
                        "mimeType": "application/pdf",
                        "data": "RAW-FILE-BASE64",
                    },
                    "inline_data": {"data": "RAW-SNAKE-BASE64"},
                    "data": "business-data",
                },
            )
        )

        redacted = redacted_protocol_request(plan)
        dump = repr(redacted)
        for secret in ("RAW-IMAGE-BASE64", "RAW-FILE-BASE64", "RAW-SNAKE-BASE64"):
            self.assertNotIn(secret, dump)
        self.assertEqual(redacted.json_body["data"], "business-data")

    def test_default_registry_registers_all_legacy_profiles_and_codecs(self) -> None:
        registry = default_registry(codex_auth_provider=object())
        for profile in ("codex_images", "codex_responses", "openai_images", "openai_responses"):
            self.assertIsNotNone(registry.protocol(profile))
        for codec in (
            "gpt_codex_images",
            "gpt_codex_responses",
            "gpt_openai_images",
            "gpt_openai_responses",
        ):
            self.assertIsNotNone(registry.codec(codec))


def _image_result():
    from codex_image.client_types import ImageResult

    return ImageResult(
        image_bytes=b"image",
        revised_prompt="revised",
        output_format="png",
        size="1024x1024",
        background="opaque",
        quality="low",
        usage={"tokens": 1},
    )


if __name__ == "__main__":
    unittest.main()
