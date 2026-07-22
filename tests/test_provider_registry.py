from __future__ import annotations

import unittest
from dataclasses import replace
from typing import Any, Mapping

from codex_image.generation.catalog import get_model_manifest, list_model_manifests
from codex_image.generation.resolver import BindingResolver
from codex_image.generation.types import (
    GenerationCommand,
    GenerationOperation,
    GenerationResult,
    InputConstraints,
    ModelManifest,
    ParameterDefinition,
)
from codex_image.providers.contracts import (
    ExecutionPlan,
    ProtocolRequest,
    ProviderConnection,
    ProviderModelBinding,
)
from codex_image.providers.registry import ProviderRegistry


class RecordingCodec:
    def __init__(self, mapped_parameter_ids: frozenset[str]) -> None:
        self._mapped_parameter_ids = mapped_parameter_ids
        self.commands: list[GenerationCommand] = []

    def mapped_parameter_ids(
        self,
        model: ModelManifest,
        operation: GenerationOperation,
    ) -> frozenset[str]:
        return self._mapped_parameter_ids

    def encode(
        self,
        command: GenerationCommand,
        model: ModelManifest,
        binding: ProviderModelBinding,
    ) -> ProtocolRequest:
        self.commands.append(command)
        return ProtocolRequest(
            method="POST",
            path="/images",
            content_type="application/json",
            json_body={"model": binding.remote_model_id, **command.parameters},
        )


class NoopProtocol:
    def execute(self, plan: ExecutionPlan) -> GenerationResult:
        return GenerationResult(assets=())


def binding_fixture(
    canonical_model_id: str = "nano-banana-pro",
    remote_model_id: str = "relay-nano",
    *,
    binding_id: str | None = None,
    provider_id: str = "relay",
    operations: frozenset[GenerationOperation] = frozenset({"generate", "edit"}),
    protocol_profile: str = "openai-images",
    parameter_codec: str = "official",
) -> ProviderModelBinding:
    return ProviderModelBinding(
        id=binding_id or f"{provider_id}-{canonical_model_id}",
        provider_id=provider_id,
        canonical_model_id=canonical_model_id,
        remote_model_id=remote_model_id,
        protocol_profile=protocol_profile,
        parameter_codec=parameter_codec,
        operations=operations,
    )


def provider_fixture(
    *,
    provider_id: str = "relay",
    bindings: tuple[ProviderModelBinding, ...] | None = None,
) -> ProviderConnection:
    return ProviderConnection(
        id=provider_id,
        name="Relay",
        base_url="https://relay.example/v1",
        api_key="test-key",
        concurrency=2,
        bindings=bindings or (binding_fixture(provider_id=provider_id),),
    )


def command_fixture(
    *,
    canonical_model_id: str = "nano-banana-pro",
    provider_id: str = "relay",
    operation: GenerationOperation = "generate",
    parameters: Mapping[str, Any] | None = None,
) -> GenerationCommand:
    return GenerationCommand(
        operation=operation,
        canonical_model_id=canonical_model_id,
        provider_id=provider_id,
        prompt="draw a rabbit",
        parameters=parameters or {"canvas.resolution": "2K"},
    )


def resolver_fixture(
    *,
    canonical_model_id: str = "nano-banana-pro",
    remote_model_id: str = "relay-nano",
    mapped_parameter_ids: frozenset[str] = frozenset({"canvas.resolution"}),
    provider_id: str = "relay",
    operations: frozenset[GenerationOperation] = frozenset({"generate", "edit"}),
    protocol_profile: str = "openai-images",
    parameter_codec: str = "official",
    models: Mapping[str, ModelManifest] | None = None,
    protocols: Mapping[str, NoopProtocol] | None = None,
    codecs: Mapping[str, RecordingCodec] | None = None,
) -> BindingResolver:
    binding = binding_fixture(
        canonical_model_id,
        remote_model_id,
        provider_id=provider_id,
        operations=operations,
        protocol_profile=protocol_profile,
        parameter_codec=parameter_codec,
    )
    provider = provider_fixture(provider_id=provider_id, bindings=(binding,))
    registry = ProviderRegistry(
        protocols=protocols if protocols is not None else {"openai-images": NoopProtocol()},
        codecs=codecs if codecs is not None else {"official": RecordingCodec(mapped_parameter_ids)},
    )
    return BindingResolver(
        models=models if models is not None else {model.id: model for model in list_model_manifests()},
        providers={provider_id: provider},
        registry=registry,
    )


class ProviderRegistryTests(unittest.TestCase):
    def test_provider_can_bind_multiple_model_families(self) -> None:
        provider = provider_fixture(
            bindings=(
                binding_fixture("gpt-image-2", "relay-gpt"),
                binding_fixture("nano-banana-pro", "relay-nano"),
            )
        )
        self.assertEqual(
            {binding.canonical_model_id for binding in provider.bindings},
            {"gpt-image-2", "nano-banana-pro"},
        )

    def test_resolver_preserves_custom_remote_model_id(self) -> None:
        plan = resolver_fixture(remote_model_id="vendor/custom-nano-pro").resolve(command_fixture())
        self.assertEqual(plan.binding.remote_model_id, "vendor/custom-nano-pro")
        self.assertEqual(plan.command.canonical_model_id, "nano-banana-pro")
        self.assertEqual(plan.model.id, "nano-banana-pro")

    def test_resolver_rejects_provider_without_current_model(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not support model"):
            resolver_fixture(canonical_model_id="gpt-image-2").resolve(
                command_fixture(canonical_model_id="nano-banana-pro")
            )

    def test_resolver_rejects_codec_that_would_drop_official_parameter(self) -> None:
        resolver = resolver_fixture(mapped_parameter_ids=frozenset({"canvas.aspect_ratio"}))
        with self.assertRaisesRegex(ValueError, "codec_parameter_mapping_missing"):
            resolver.resolve(command_fixture(parameters={"canvas.resolution": "2K"}))

    def test_application_scope_parameter_must_be_mapped_and_is_passed_to_codec(self) -> None:
        codec = RecordingCodec(frozenset({"output.count"}))
        resolver = resolver_fixture(codecs={"official": codec})
        command = command_fixture(parameters={"output.count": 2})
        plan = resolver.resolve(command)
        self.assertEqual(codec.commands, [command])
        self.assertEqual(plan.protocol_request.json_body["output.count"], 2)

        missing_mapping = resolver_fixture(mapped_parameter_ids=frozenset())
        with self.assertRaisesRegex(ValueError, "codec_parameter_mapping_missing: output.count"):
            missing_mapping.resolve(command)

    def test_gpt_compression_is_valid_only_for_jpeg_or_webp(self) -> None:
        resolver = resolver_fixture(
            canonical_model_id="gpt-image-2",
            mapped_parameter_ids=frozenset({"output.format", "gpt.output_compression"}),
        )
        with self.assertRaisesRegex(ValueError, "Parameter is not applicable: gpt.output_compression"):
            resolver.resolve(command_fixture(
                canonical_model_id="gpt-image-2",
                parameters={"output.format": "png", "gpt.output_compression": 80},
            ))
        plan = resolver.resolve(command_fixture(
            canonical_model_id="gpt-image-2",
            parameters={"output.format": "webp", "gpt.output_compression": 63},
        ))
        self.assertEqual(plan.command.parameters["gpt.output_compression"], 63)

    def test_provider_rejects_duplicate_or_overlapping_bindings(self) -> None:
        first = binding_fixture(operations=frozenset({"generate"}), binding_id="first")
        duplicate = replace(first, id="duplicate")
        with self.assertRaisesRegex(ValueError, "ambiguous provider binding"):
            provider_fixture(bindings=(first, duplicate))

        overlapping = binding_fixture(operations=frozenset({"generate", "edit"}), binding_id="overlap")
        with self.assertRaisesRegex(ValueError, "ambiguous provider binding"):
            provider_fixture(bindings=(first, overlapping))

    def test_provider_allows_same_model_with_disjoint_operations(self) -> None:
        generate = binding_fixture(operations=frozenset({"generate"}), binding_id="generate")
        edit = binding_fixture(operations=frozenset({"edit"}), binding_id="edit")
        provider = provider_fixture(bindings=(generate, edit))
        self.assertEqual(provider.bindings, (generate, edit))

    def test_resolver_rejects_unsupported_model_or_binding_operation(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not support operation: edit"):
            resolver_fixture(operations=frozenset({"generate"})).resolve(
                command_fixture(operation="edit")
            )

    def test_registry_and_resolver_reject_unknown_names(self) -> None:
        registry = ProviderRegistry(protocols={}, codecs={})
        with self.assertRaisesRegex(ValueError, "Unknown protocol profile: missing"):
            registry.protocol("missing")
        with self.assertRaisesRegex(ValueError, "Unknown parameter codec: missing"):
            registry.codec("missing")

        with self.assertRaisesRegex(ValueError, "Unknown provider: missing"):
            resolver_fixture().resolve(command_fixture(provider_id="missing"))
        with self.assertRaisesRegex(ValueError, "Unknown image model: missing"):
            resolver_fixture().resolve(command_fixture(canonical_model_id="missing"))
        with self.assertRaisesRegex(ValueError, "Unknown parameter codec: missing"):
            resolver_fixture(parameter_codec="missing").resolve(command_fixture())
        with self.assertRaisesRegex(ValueError, "Unknown protocol profile: missing"):
            resolver_fixture(protocol_profile="missing").resolve(command_fixture())

    def test_resolver_rejects_unknown_parameter(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown parameter: made.up"):
            resolver_fixture(mapped_parameter_ids=frozenset({"made.up"})).resolve(
                command_fixture(parameters={"made.up": "value"})
            )

    def test_resolver_validates_parameter_types_without_treating_bool_as_integer(self) -> None:
        cases = (
            ("canvas.resolution", 2, "expected string"),
            ("output.count", True, "expected integer"),
            ("gemini.google_search", "yes", "expected boolean"),
        )
        for parameter_id, value, message in cases:
            with self.subTest(parameter_id=parameter_id):
                with self.assertRaisesRegex(ValueError, message):
                    resolver_fixture(mapped_parameter_ids=frozenset({parameter_id})).resolve(
                        command_fixture(parameters={parameter_id: value})
                    )

    def test_resolver_requires_object_values_to_be_non_array_mappings(self) -> None:
        definition = ParameterDefinition(
            id="advanced.payload",
            label_key="advanced.payload",
            group="advanced",
            control="text",
            value_type="object",
            default={},
        )
        model = ModelManifest(
            id="object-model",
            family_id="test",
            display_name="Object Model",
            official_model_id="object-model",
            version=1,
            operations=frozenset({"generate"}),
            parameters=(definition,),
            input_constraints=InputConstraints(0, False, False),
        )
        resolver = resolver_fixture(
            canonical_model_id="object-model",
            models={"object-model": model},
            mapped_parameter_ids=frozenset({"advanced.payload"}),
        )
        resolver.resolve(command_fixture(canonical_model_id="object-model", parameters={"advanced.payload": {"x": 1}}))
        with self.assertRaisesRegex(ValueError, "expected object"):
            resolver.resolve(command_fixture(canonical_model_id="object-model", parameters={"advanced.payload": [1]}))

    def test_resolver_validates_allowed_values_ranges_and_step(self) -> None:
        invalid_cases = (
            ("canvas.resolution", "8K", "invalid value"),
            ("output.count", 0, "below minimum"),
            ("output.count", 5, "above maximum"),
        )
        for parameter_id, value, message in invalid_cases:
            with self.subTest(parameter_id=parameter_id, value=value):
                with self.assertRaisesRegex(ValueError, message):
                    resolver_fixture(mapped_parameter_ids=frozenset({parameter_id})).resolve(
                        command_fixture(parameters={parameter_id: value})
                    )

        stepped = replace(get_model_manifest("nano-banana-pro").parameter("output.count"), maximum=5, step=2)
        model = replace(
            get_model_manifest("nano-banana-pro"),
            parameters=(stepped,),
        )
        resolver = resolver_fixture(
            models={model.id: model},
            mapped_parameter_ids=frozenset({"output.count"}),
        )
        resolver.resolve(command_fixture(parameters={"output.count": 3}))
        with self.assertRaisesRegex(ValueError, "invalid step"):
            resolver.resolve(command_fixture(parameters={"output.count": 2}))

    def test_empty_allowed_values_only_enforces_declared_type(self) -> None:
        resolver = resolver_fixture(
            canonical_model_id="gpt-image-2",
            mapped_parameter_ids=frozenset({"canvas.size"}),
        )
        plan = resolver.resolve(
            command_fixture(canonical_model_id="gpt-image-2", parameters={"canvas.size": "1536x1024"})
        )
        self.assertEqual(plan.command.parameters["canvas.size"], "1536x1024")

    def test_parameter_must_support_current_operation(self) -> None:
        definition = replace(
            get_model_manifest("nano-banana-pro").parameter("canvas.resolution"),
            operations=frozenset({"generate"}),
        )
        model = replace(get_model_manifest("nano-banana-pro"), parameters=(definition,))
        resolver = resolver_fixture(
            models={model.id: model},
            mapped_parameter_ids=frozenset({"canvas.resolution"}),
        )
        with self.assertRaisesRegex(ValueError, "Parameter does not support operation"):
            resolver.resolve(command_fixture(operation="edit"))


if __name__ == "__main__":
    unittest.main()
