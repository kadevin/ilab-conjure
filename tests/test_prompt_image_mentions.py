import json
import unittest

from fastapi import HTTPException

from codex_image.webui.prompt_image_mentions import resolve_prompt_image_mentions, remap_prompt_image_mentions


class PromptImageMentionTests(unittest.TestCase):
    def context(self):
        parts = ["Use ", {"text": "@same.png", "source": {"kind": "upload", "index": 1}},
                 " beside ", {"text": "@same.png", "source": {"kind": "gallery", "id": "g"}},
                 ". Literal @same.png stays text."]
        return {"version": 1, "template": "reference image {number}", "parts": parts, "model_parts": parts}

    def resolve(self, context):
        text = "Use @same.png beside @same.png. Literal @same.png stays text."
        return resolve_prompt_image_mentions(json.dumps(context), text, text,
                                             [{"id": "a"}, {"id": "a"}],
                                             [{"kind": "gallery", "id": "g"}, {"kind": "asset", "id": "a"}])

    def test_dedup_and_same_name_use_identity_and_only_explicit_mentions(self):
        original, model, stored = self.resolve(self.context())
        self.assertEqual(original, "Use reference image 2 beside reference image 1. Literal @same.png stays text.")
        self.assertEqual(model, original)
        self.assertEqual(stored["parts"][1]["source"], {"kind": "asset", "id": "a"})

    def test_invalid_or_stale_parts_never_guess_an_image(self):
        for source in ({"kind": "upload", "index": -1}, {"kind": "upload", "index": True},
                       {"kind": "asset", "id": "unknown"}, {"kind": "local", "id": "a"},
                       {"kind": "asset", "id": ["a"]}, {"kind": "asset", "id": "a", "missing": True}):
            with self.subTest(source=source):
                context = self.context()
                context["parts"][1]["source"] = source
                with self.assertRaises(HTTPException) as result:
                    self.resolve(context)
                self.assertEqual(result.exception.detail["code"], "prompt_image_mentions_invalid")
        context = self.context()
        context["parts"][0] = "changed "
        with self.assertRaises(HTTPException):
            self.resolve(context)

    def test_model_parts_cannot_switch_references(self):
        context = self.context()
        context["model_parts"] = json.loads(json.dumps(context["parts"]))
        context["model_parts"][1]["source"] = {"kind": "gallery", "id": "g"}
        with self.assertRaises(HTTPException):
            self.resolve(context)

    def test_legacy_prompt_and_backup_remapping(self):
        self.assertEqual(resolve_prompt_image_mentions(None, "raw", "expanded", [], None), ("raw", "expanded", None))
        _, _, stored = self.resolve(self.context())
        restored = remap_prompt_image_mentions(stored, {("asset", "a"): "restored"})
        self.assertEqual(restored["parts"][1]["source"]["id"], "restored")
        self.assertTrue(restored["parts"][3]["source"]["missing"])
        remapped_again = remap_prompt_image_mentions(restored, {("gallery", "g"): "unrelated"})
        self.assertTrue(remapped_again["parts"][3]["source"]["missing"])
        self.assertEqual(remapped_again["parts"][3]["source"]["id"], "g")
