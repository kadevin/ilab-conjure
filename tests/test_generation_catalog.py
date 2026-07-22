from __future__ import annotations

import unittest

from codex_image.generation.catalog import (
    MODEL_MANIFEST_VERSION,
    get_model_manifest,
    list_model_families,
    list_model_manifests,
    manifests_for_family,
)


class GenerationCatalogTests(unittest.TestCase):
    def test_manifest_version_is_stable_and_consistent(self) -> None:
        self.assertEqual(MODEL_MANIFEST_VERSION, 1)
        self.assertEqual({model.version for model in list_model_manifests()}, {1})

    def test_builtin_model_ids_are_stable(self) -> None:
        self.assertEqual(
            {model.id for model in list_model_manifests()},
            {
                "gpt-image-2",
                "nano-banana-pro",
                "nano-banana-2",
                "nano-banana-2-lite",
            },
        )

    def test_nano_banana_models_have_model_specific_resolutions(self) -> None:
        pro = get_model_manifest("nano-banana-pro")
        flash = get_model_manifest("nano-banana-2")
        lite = get_model_manifest("nano-banana-2-lite")
        self.assertEqual(pro.parameter("canvas.resolution").allowed_values, ("1K", "2K", "4K"))
        self.assertEqual(flash.parameter("canvas.resolution").allowed_values, ("512", "1K", "2K", "4K"))
        self.assertEqual(lite.parameter("canvas.resolution").allowed_values, ("1K",))

    def test_new_model_manifests_use_image2_style_compact_controls(self) -> None:
        for model_id in ("nano-banana-pro", "nano-banana-2", "nano-banana-2-lite"):
            with self.subTest(model=model_id):
                model = get_model_manifest(model_id)
                aspect_ratio = model.parameter("canvas.aspect_ratio")
                self.assertEqual(aspect_ratio.control, "aspect_ratio_grid")
                self.assertTrue(aspect_ratio.full_width)
                self.assertEqual(model.parameter("canvas.resolution").control, "segmented")
                with self.assertRaises(KeyError):
                    model.parameter("output.modalities")
                count = model.parameter("output.count")
                self.assertEqual(count.control, "segmented")
                self.assertEqual(count.allowed_values, (1, 2, 3, 4))

    def test_remote_model_name_is_not_part_of_model_manifest(self) -> None:
        model = get_model_manifest("nano-banana-pro")
        self.assertEqual(model.official_model_id, "gemini-3-pro-image")
        self.assertFalse(hasattr(model, "remote_model_id"))

    def test_model_families_are_explicit_and_all_manifests_reference_them(self) -> None:
        families = list_model_families()
        self.assertEqual(
            [(family.id, family.display_name, family.short_name) for family in families],
            [
                ("gpt-image", "GPT Image", "GPT"),
                ("gemini-image", "Gemini", "Gemini"),
            ],
        )
        family_ids = {family.id for family in families}
        self.assertTrue(all(family.label_key for family in families))
        self.assertTrue(all(model.family_id in family_ids for model in list_model_manifests()))
        self.assertEqual(
            {model.id for model in manifests_for_family("gemini-image")},
            {"nano-banana-pro", "nano-banana-2", "nano-banana-2-lite"},
        )

    def test_unknown_model_does_not_fall_back_to_gpt(self) -> None:
        with self.assertRaisesRegex(KeyError, "Unknown image model: unknown"):
            get_model_manifest("unknown")

    def test_nano_banana_models_have_approved_aspect_ratios_and_search_options(self) -> None:
        common_ratios = ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")
        pro = get_model_manifest("nano-banana-pro")
        flash = get_model_manifest("nano-banana-2")
        lite = get_model_manifest("nano-banana-2-lite")

        self.assertEqual(pro.parameter("canvas.aspect_ratio").allowed_values, common_ratios)
        self.assertEqual(
            flash.parameter("canvas.aspect_ratio").allowed_values,
            common_ratios + ("1:4", "1:8", "4:1", "8:1"),
        )
        self.assertEqual(lite.parameter("canvas.aspect_ratio").allowed_values, common_ratios)
        self.assertEqual(pro.input_constraints.max_images, 14)
        self.assertEqual(flash.input_constraints.max_images, 14)
        self.assertEqual(lite.input_constraints.max_images, 14)
        self.assertIsNotNone(pro.parameter("gemini.google_search"))
        self.assertIsNotNone(flash.parameter("gemini.google_search"))
        with self.assertRaises(KeyError):
            pro.parameter("gemini.google_image_search")
        with self.assertRaises(KeyError):
            flash.parameter("gemini.google_image_search")
        with self.assertRaises(KeyError):
            lite.parameter("gemini.google_search")
        with self.assertRaises(KeyError):
            lite.parameter("gemini.google_image_search")

    def test_nano_banana_models_place_count_then_safety_without_output_modalities(self) -> None:
        expected_categories = (
            "HARM_CATEGORY_HARASSMENT",
            "HARM_CATEGORY_HATE_SPEECH",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT",
            "HARM_CATEGORY_DANGEROUS_CONTENT",
        )
        expected_thresholds = (
            "HARM_BLOCK_THRESHOLD_UNSPECIFIED",
            "OFF",
            "BLOCK_NONE",
            "BLOCK_ONLY_HIGH",
            "BLOCK_MEDIUM_AND_ABOVE",
            "BLOCK_LOW_AND_ABOVE",
        )
        for model_id in ("nano-banana-pro", "nano-banana-2", "nano-banana-2-lite"):
            with self.subTest(model=model_id):
                model = get_model_manifest(model_id)
                self.assertTrue(model.expand_advanced_parameters)
                with self.assertRaises(KeyError):
                    model.parameter("output.modalities")
                safety = model.parameter("gemini.safety_settings")
                self.assertEqual(safety.control, "object_presets")
                self.assertEqual(safety.value_type, "object")
                self.assertEqual(safety.group, "generation")
                self.assertEqual(
                    tuple(preset.id for preset in safety.object_presets),
                    ("off", "block_all"),
                )
                self.assertTrue(safety.object_presets[0].matches_empty)
                self.assertFalse(safety.object_presets[1].matches_empty)
                self.assertEqual(set(safety.default), set(expected_categories))
                self.assertEqual(set(safety.default.values()), {"OFF"})
                self.assertEqual(safety.object_presets[0].value, safety.default)
                self.assertEqual(
                    set(safety.object_presets[1].value.values()),
                    {"BLOCK_LOW_AND_ABOVE"},
                )
                self.assertFalse(safety.full_width)
                self.assertEqual(tuple(row.key for row in safety.object_choices), expected_categories)
                for row in safety.object_choices:
                    self.assertEqual(row.default, "HARM_BLOCK_THRESHOLD_UNSPECIFIED")
                    self.assertEqual(row.allowed_values, expected_thresholds)
                    self.assertEqual(len(row.label_keys), len(expected_thresholds))

                parameter_ids = tuple(parameter.id for parameter in model.parameters)
                self.assertEqual(
                    parameter_ids[:4],
                    (
                        "canvas.aspect_ratio",
                        "canvas.resolution",
                        "output.count",
                        "gemini.safety_settings",
                    ),
                )
                if model_id != "nano-banana-2-lite":
                    self.assertEqual(parameter_ids[4:], ("gemini.google_search",))
                    google_search = model.parameter("gemini.google_search")
                    self.assertEqual(google_search.group, "generation")
                    self.assertEqual(google_search.control, "boolean_segmented")
                    self.assertEqual(google_search.value_type, "boolean")
                    self.assertFalse(google_search.default)
                    self.assertFalse(google_search.full_width)
                else:
                    self.assertEqual(len(parameter_ids), 4)

        self.assertFalse(get_model_manifest("gpt-image-2").expand_advanced_parameters)

    def test_output_count_is_application_scoped_for_every_model(self) -> None:
        for model in list_model_manifests():
            with self.subTest(model=model.id):
                count = model.parameter("output.count")
                self.assertEqual(count.default, 1)
                self.assertEqual(count.scope, "application")
                self.assertEqual(count.minimum, 1)
                self.assertEqual(count.maximum, 4)

    def test_gpt_image_2_preserves_current_parameter_contract(self) -> None:
        gpt = get_model_manifest("gpt-image-2")
        size = gpt.parameter("canvas.size")
        self.assertEqual(size.value_type, "string")
        self.assertEqual(size.default, "1024x1024")
        self.assertEqual(size.allowed_values, ())
        self.assertEqual(gpt.parameter("gpt.quality").allowed_values, ("auto", "low", "medium", "high"))
        self.assertEqual(gpt.parameter("gpt.background").allowed_values, ("auto", "transparent", "opaque"))
        self.assertEqual(gpt.parameter("output.format").allowed_values, ("png", "jpeg", "webp"))
        self.assertEqual(gpt.parameter("gpt.moderation").allowed_values, ("auto", "low"))
        web_search = gpt.parameter("gpt.web_search")
        self.assertEqual(web_search.value_type, "boolean")
        self.assertFalse(web_search.default)
        compression = gpt.parameter("gpt.output_compression")
        self.assertEqual(compression.value_type, "integer")
        self.assertEqual(compression.default, 80)
        self.assertEqual((compression.minimum, compression.maximum, compression.step), (0, 100, 1))
        self.assertEqual(len(compression.visible_when), 1)
        self.assertEqual(compression.visible_when[0].parameter_id, "output.format")
        self.assertEqual(compression.visible_when[0].operator, "in")
        self.assertEqual(compression.visible_when[0].value, ("jpeg", "webp"))
        with self.assertRaises(KeyError):
            gpt.parameter("gpt.input_fidelity")
