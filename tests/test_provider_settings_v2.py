from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch


class ProviderSettingsV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        from codex_image.webui.provider_settings import ProviderSettings

        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "api-settings.json"
        self.settings = ProviderSettings(self.path)

    def write_json(self, payload: dict[str, Any]) -> Path:
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        return self.path

    @staticmethod
    def provider(**overrides: Any) -> dict[str, Any]:
        provider = {
            "id": "relay",
            "name": "Relay",
            "base_url": "https://relay.example/v1",
            "api_key": "secret",
            "concurrency": 6,
            "bindings": [
                {
                    "id": "relay-gpt",
                    "canonical_model_id": "gpt-image-2",
                    "remote_model_id": " vendor/gpt image:custom ",
                    "protocol_profile": "openai_images",
                    "parameter_codec": "gpt_openai_images",
                    "operations": ["generate", "edit"],
                }
            ],
        }
        provider.update(overrides)
        return provider

    def v2_payload(self, **overrides: Any) -> dict[str, Any]:
        payload = {
            "schema_version": 2,
            "codex_mode": "responses",
            "active_provider_id": "relay",
            "default_provider_by_model": {"gpt-image-2": "relay"},
            "providers": [self.provider()],
        }
        payload.update(overrides)
        return payload

    def test_legacy_provider_is_migrated_in_memory_without_rewriting_file(self) -> None:
        path = self.write_json(
            {
                "active_provider_id": "relay",
                "codex_mode": "responses",
                "providers": [
                    {
                        "id": "relay",
                        "name": "Relay",
                        "base_url": "https://relay.example/v1/images/generations?legacy=1",
                        "api_key": "secret",
                        "image_model": "vendor-gpt-name",
                        "api_mode": "images",
                        "images_concurrency": 6,
                    }
                ],
            }
        )
        before = path.read_text(encoding="utf-8")

        settings = self.settings.read()
        binding = settings["providers"][0]["bindings"][0]

        self.assertEqual(settings["schema_version"], 2)
        self.assertEqual(binding["canonical_model_id"], "gpt-image-2")
        self.assertEqual(binding["remote_model_id"], "vendor-gpt-name")
        self.assertEqual(settings["codex_mode"], "responses")
        self.assertEqual(settings["base_url"], "https://relay.example/v1")
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_public_settings_never_return_api_key_at_any_depth(self) -> None:
        self.settings.write(self.v2_payload())

        public = self.settings.public_settings()

        def assert_no_api_key(value: Any) -> None:
            if isinstance(value, dict):
                self.assertNotIn("api_key", value)
                for nested in value.values():
                    assert_no_api_key(nested)
            elif isinstance(value, list):
                for nested in value:
                    assert_no_api_key(nested)

        assert_no_api_key(public)
        self.assertTrue(public["providers"][0]["api_key_set"])
        self.assertEqual(public["providers"][0]["api_key_masked"], "********")

    def test_write_persists_v2_and_preserves_custom_remote_model_id(self) -> None:
        written = self.settings.write(self.v2_payload())
        persisted = json.loads(self.path.read_text(encoding="utf-8"))

        self.assertEqual(persisted["schema_version"], 2)
        self.assertEqual(written["providers"][0]["bindings"][0]["remote_model_id"], "vendor/gpt image:custom")
        self.assertNotIn("auth_scheme", written["providers"][0])
        self.assertNotIn("auth_scheme", persisted["providers"][0])
        self.assertNotIn("api_key", self.settings.public_settings()["providers"][0])

    def test_write_persists_optional_provider_icon_emoji(self) -> None:
        written = self.settings.write(self.v2_payload(providers=[self.provider(icon_emoji="🪄")]))
        persisted = json.loads(self.path.read_text(encoding="utf-8"))
        public = self.settings.public_settings()

        self.assertEqual(written["providers"][0].get("icon_emoji"), "🪄")
        self.assertEqual(persisted["providers"][0].get("icon_emoji"), "🪄")
        self.assertEqual(public["providers"][0].get("icon_emoji"), "🪄")

    def test_binding_persists_optional_aspect_ratio_prompt_setting(self) -> None:
        binding = {
            **self.provider()["bindings"][0],
            "append_aspect_ratio_prompt": True,
        }

        written = self.settings.write(
            self.v2_payload(providers=[self.provider(bindings=[binding])])
        )
        persisted = json.loads(self.path.read_text(encoding="utf-8"))
        public = self.settings.public_settings()
        connection = self.settings.read_connections()[0]

        self.assertTrue(written["providers"][0]["bindings"][0]["append_aspect_ratio_prompt"])
        self.assertTrue(persisted["providers"][0]["bindings"][0]["append_aspect_ratio_prompt"])
        self.assertTrue(public["providers"][0]["bindings"][0]["append_aspect_ratio_prompt"])
        self.assertTrue(connection.bindings[0].append_aspect_ratio_prompt)

    def test_legacy_auth_scheme_is_accepted_then_dropped_everywhere(self) -> None:
        legacy_provider = self.provider(auth_scheme="basic")
        written = self.settings.write(self.v2_payload(providers=[legacy_provider]))
        persisted = json.loads(self.path.read_text(encoding="utf-8"))
        public = self.settings.public_settings()

        self.assertNotIn("auth_scheme", written["providers"][0])
        self.assertNotIn("auth_scheme", persisted["providers"][0])
        self.assertNotIn("auth_scheme", public["providers"][0])

    def test_one_provider_accepts_mixed_binding_protocols_without_connection_auth(self) -> None:
        gpt_binding = self.provider()["bindings"][0]
        nano_binding = {
            "id": "relay-nano",
            "canonical_model_id": "nano-banana-pro",
            "remote_model_id": "relay/nano-pro:custom",
            "protocol_profile": "gemini_generate_content",
            "parameter_codec": "gemini_generate_content_image",
            "operations": ["generate", "edit"],
        }
        written = self.settings.write(self.v2_payload(
            default_provider_by_model={
                "gpt-image-2": "relay",
                "nano-banana-pro": "relay",
            },
            providers=[self.provider(bindings=[gpt_binding, nano_binding])],
        ))

        self.assertEqual(
            [binding["protocol_profile"] for binding in written["providers"][0]["bindings"]],
            ["openai_images", "gemini_generate_content"],
        )
        self.assertNotIn("auth_scheme", written["providers"][0])

    def test_compatibility_codec_choices_are_persisted_per_binding(self) -> None:
        cases = (
            ("gemini_generate_content", "gemini_generate_content_image_config"),
            ("gemini_change2pro_generate_content", "gemini_generate_content_image_config"),
            ("t8_images", "gemini_t8_images"),
            ("openrouter_images", "gemini_openrouter_images"),
        )
        for protocol, codec in cases:
            with self.subTest(codec=codec):
                binding = {
                    "id": "relay-nano",
                    "canonical_model_id": "nano-banana-2",
                    "remote_model_id": "vendor/custom-nano",
                    "protocol_profile": protocol,
                    "parameter_codec": codec,
                    "operations": ["generate", "edit"],
                }
                written = self.settings.write(self.v2_payload(
                    default_provider_by_model={"nano-banana-2": "relay"},
                    providers=[self.provider(bindings=[binding])],
                ))
                saved = written["providers"][0]["bindings"][0]
                self.assertEqual(saved["protocol_profile"], protocol)
                self.assertEqual(saved["parameter_codec"], codec)

    def test_read_connections_returns_provider_contracts(self) -> None:
        from codex_image.providers import ProviderConnection

        self.settings.write(self.v2_payload())
        connections = self.settings.read_connections()

        self.assertEqual(len(connections), 1)
        self.assertIsInstance(connections[0], ProviderConnection)
        self.assertEqual(connections[0].bindings[0].provider_id, "relay")
        self.assertEqual(connections[0].bindings[0].remote_model_id, "vendor/gpt image:custom")

    def test_v2_rejects_invalid_connection_fields_and_codex_disk_provider(self) -> None:
        invalid_cases = (
            (self.provider(id="codex"), "codex_provider_not_allowed"),
            (self.provider(base_url="ftp://relay.example/v1"), "invalid_base_url"),
            (self.provider(base_url="https://user:pass@relay.example/v1"), "invalid_base_url"),
            (self.provider(base_url="https://relay.example/v1?q=1"), "invalid_base_url"),
            (self.provider(base_url="https://bad host/v1"), "invalid_base_url"),
            (self.provider(base_url="https://bad\nhost/v1"), "invalid_base_url"),
            (self.provider(base_url="https://bad%20host/v1"), "invalid_base_url"),
            (self.provider(concurrency=33), "invalid_concurrency"),
        )
        for provider, error in invalid_cases:
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                self.settings.write(self.v2_payload(providers=[provider]))

    def test_v2_accepts_localhost_ipv4_and_ipv6_base_urls(self) -> None:
        valid_urls = (
            "http://localhost:8787/v1",
            "https://127.0.0.1:9443/api",
            "http://[::1]:8787/v1",
        )
        for base_url in valid_urls:
            with self.subTest(base_url=base_url):
                written = self.settings.write(
                    self.v2_payload(providers=[self.provider(base_url=base_url)])
                )
                self.assertEqual(written["providers"][0]["base_url"], base_url)

    def test_v2_rejects_invalid_binding_fields(self) -> None:
        base_binding = self.provider()["bindings"][0]
        invalid_cases = (
            ({**base_binding, "canonical_model_id": "unknown"}, "unknown_canonical_model"),
            ({**base_binding, "remote_model_id": "   "}, "invalid_remote_model_id"),
            ({**base_binding, "protocol_profile": "codex_images"}, "unknown_protocol_profile"),
            ({**base_binding, "parameter_codec": "unknown"}, "unknown_parameter_codec"),
            ({**base_binding, "operations": []}, "invalid_operations"),
            ({**base_binding, "operations": ["remove"]}, "invalid_operations"),
        )
        for binding, error in invalid_cases:
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                self.settings.write(self.v2_payload(providers=[self.provider(bindings=[binding])]))

    def test_v2_rejects_duplicate_or_overlapping_bindings(self) -> None:
        first = self.provider()["bindings"][0]
        duplicate_id = {**first, "operations": ["generate"]}
        overlap = {**first, "id": "relay-gpt-edit", "operations": ["edit"]}

        with self.assertRaisesRegex(ValueError, "duplicate_binding_id"):
            self.settings.write(self.v2_payload(providers=[self.provider(bindings=[first, duplicate_id])]))
        with self.assertRaisesRegex(ValueError, "overlapping_binding"):
            self.settings.write(self.v2_payload(providers=[self.provider(bindings=[first, overlap])]))

    def test_v2_rejects_missing_defaults_and_incomplete_codec_mapping(self) -> None:
        with self.assertRaisesRegex(ValueError, "default_provider_mapping_missing"):
            self.settings.write(self.v2_payload(default_provider_by_model={}))
        with self.assertRaisesRegex(ValueError, "invalid_default_provider_mapping"):
            self.settings.write(
                self.v2_payload(
                    default_provider_by_model={
                        "gpt-image-2": "relay",
                        "unknown-model": "relay",
                    }
                )
            )
        with self.assertRaisesRegex(ValueError, "invalid_default_provider_mapping"):
            self.settings.write(
                self.v2_payload(default_provider_by_model={"gpt-image-2": "missing"})
            )

        bad_binding = {
            **self.provider()["bindings"][0],
            "parameter_codec": "gemini_openai_images",
        }
        with self.assertRaisesRegex(ValueError, "codec_parameter_mapping_missing"):
            self.settings.write(self.v2_payload(providers=[self.provider(bindings=[bad_binding])]))

        from codex_image.providers import capabilities

        declared = capabilities.CODEC_CAPABILITIES["gpt_openai_images"]
        with patch.dict(
            capabilities.CODEC_CAPABILITIES,
            {
                "gpt_openai_images": replace(
                    declared,
                    mapped_parameter_ids=declared.mapped_parameter_ids - {"canvas.size"},
                )
            },
        ), self.assertRaisesRegex(ValueError, "codec_parameter_mapping_missing: canvas.size"):
            self.settings.write(self.v2_payload())

    def test_legacy_active_patch_preserves_non_gpt_bindings(self) -> None:
        gpt_binding = self.provider()["bindings"][0]
        gemini_binding = {
            "id": "relay-gemini",
            "canonical_model_id": "nano-banana-pro",
            "remote_model_id": "vendor/gemini-pro",
            "protocol_profile": "openai_images",
            "parameter_codec": "gemini_openai_images",
            "operations": ["generate", "edit"],
        }
        payload = self.v2_payload(
            default_provider_by_model={
                "gpt-image-2": "relay",
                "nano-banana-pro": "relay",
            },
            providers=[self.provider(bindings=[gpt_binding, gemini_binding])],
        )
        self.settings.write(payload)

        codex_only = self.settings.write({"codex_mode": "images"})
        self.assertEqual(codex_only["providers"][0]["bindings"][1], gemini_binding)

        updated = self.settings.write(
            {"image_model": "vendor/gpt-v2", "api_mode": "responses"}
        )
        self.assertEqual(updated["providers"][0]["bindings"][1], gemini_binding)
        self.assertEqual(
            updated["providers"][0]["bindings"][0]["remote_model_id"],
            "vendor/gpt-v2",
        )
        self.assertEqual(
            updated["providers"][0]["bindings"][0]["protocol_profile"],
            "openai_responses",
        )

    def test_legacy_provider_list_write_preserves_existing_non_gpt_bindings(self) -> None:
        gpt_binding = self.provider()["bindings"][0]
        gemini_binding = {
            "id": "relay-gemini",
            "canonical_model_id": "nano-banana-pro",
            "remote_model_id": "vendor/gemini-pro",
            "protocol_profile": "openai_images",
            "parameter_codec": "gemini_openai_images",
            "operations": ["generate", "edit"],
        }
        donor = self.provider(
            id="donor",
            name="Donor",
            api_key="donor-secret",
            bindings=[{**gpt_binding, "id": "donor-gpt"}],
        )
        self.settings.write(
            self.v2_payload(
                default_provider_by_model={
                    "gpt-image-2": "relay",
                    "nano-banana-pro": "relay",
                },
                providers=[self.provider(bindings=[gpt_binding, gemini_binding]), donor],
            )
        )

        updated = self.settings.write(
            {
                "active_provider_id": "relay",
                "providers": [
                    {
                        "id": "donor",
                        "name": "Donor",
                        "base_url": "https://donor.example/v1",
                        "image_model": "donor-gpt",
                        "api_mode": "images",
                        "images_concurrency": 4,
                    },
                    {
                        "id": "relay",
                        "name": "Relay Renamed",
                        "base_url": "https://relay.example/v1",
                        "image_model": "vendor/gpt-v3",
                        "api_mode": "responses",
                        "images_concurrency": 7,
                        "api_key_source_provider_id": "donor",
                    },
                ],
            }
        )

        self.assertEqual([provider["id"] for provider in updated["providers"]], ["donor", "relay"])
        relay = updated["providers"][1]
        self.assertEqual(relay["name"], "Relay Renamed")
        self.assertEqual(relay["api_key"], "donor-secret")
        self.assertEqual(relay["bindings"][1], gemini_binding)
        self.assertEqual(relay["bindings"][0]["remote_model_id"], "vendor/gpt-v3")
        self.assertEqual(relay["bindings"][0]["protocol_profile"], "openai_responses")

    def test_legacy_provider_list_delete_repairs_multi_model_defaults_deterministically(self) -> None:
        nano_binding = {
            "id": "nano",
            "canonical_model_id": "nano-banana-pro",
            "remote_model_id": "vendor/nano",
            "protocol_profile": "openai_images",
            "parameter_codec": "gemini_openai_images",
            "operations": ["generate", "edit"],
        }
        flash_binding = {
            "id": "flash",
            "canonical_model_id": "nano-banana-2",
            "remote_model_id": "vendor/flash",
            "protocol_profile": "openai_images",
            "parameter_codec": "gemini_openai_images",
            "operations": ["generate", "edit"],
        }
        removed = self.provider(
            id="removed",
            name="Removed",
            bindings=[
                {**nano_binding, "id": "removed-nano"},
                {**flash_binding, "id": "removed-flash"},
            ],
        )
        active = self.provider(
            id="active",
            name="Active",
            bindings=[{**nano_binding, "id": "active-nano"}],
        )
        first_flash = self.provider(
            id="first-flash",
            name="First Flash",
            bindings=[{**flash_binding, "id": "first-flash-binding"}],
        )
        second_flash = self.provider(
            id="second-flash",
            name="Second Flash",
            bindings=[{**flash_binding, "id": "second-flash-binding"}],
        )
        self.settings.write(
            self.v2_payload(
                active_provider_id="active",
                default_provider_by_model={
                    "nano-banana-pro": "removed",
                    "nano-banana-2": "removed",
                },
                providers=[removed, active, first_flash, second_flash],
            )
        )

        updated = self.settings.write(
            {
                "active_provider_id": "active",
                "providers": [
                    {"id": "first-flash", "name": "First Flash"},
                    {"id": "active", "name": "Active"},
                    {"id": "second-flash", "name": "Second Flash"},
                ],
            }
        )

        self.assertEqual(
            updated["default_provider_by_model"]["nano-banana-pro"],
            "active",
        )
        self.assertEqual(
            updated["default_provider_by_model"]["nano-banana-2"],
            "first-flash",
        )

    def test_corrupt_file_falls_back_without_rewriting_but_invalid_v2_raises(self) -> None:
        self.path.write_text("{broken", encoding="utf-8")
        before = self.path.read_text(encoding="utf-8")
        fallback = self.settings.read()
        self.assertEqual(fallback["schema_version"], 2)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

        self.write_json(self.v2_payload(providers=[self.provider(concurrency=0)]))
        with self.assertRaisesRegex(ValueError, "invalid_concurrency"):
            self.settings.read()

    def test_legacy_migration_rejects_codex_and_duplicate_provider_ids(self) -> None:
        self.write_json(
            {
                "providers": [
                    {
                        "id": "codex",
                        "base_url": "https://relay.example/v1",
                        "image_model": "gpt-image-2",
                    }
                ]
            }
        )
        with self.assertRaisesRegex(ValueError, "codex_provider_not_allowed"):
            self.settings.read()

        self.write_json(
            {
                "providers": [
                    {
                        "id": "Relay A",
                        "base_url": "https://relay-a.example/v1",
                        "image_model": "gpt-image-2",
                    },
                    {
                        "id": "relay-a",
                        "base_url": "https://relay-b.example/v1",
                        "image_model": "gpt-image-2",
                    },
                ]
            }
        )
        with self.assertRaisesRegex(ValueError, "duplicate_provider_id"):
            self.settings.read()


if __name__ == "__main__":
    unittest.main()
