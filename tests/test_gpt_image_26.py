from __future__ import annotations

import base64
import json
import unittest
from io import BytesIO

import httpx
from PIL import Image
from codex_image.generation.types import ImageInput
from tests import test_generation_failure_boundaries as boundaries
from tests.helpers import TEST_PNG_BYTES, TEST_PNG_BASE64

from codex_image.generation.catalog import get_model_manifest
from codex_image.generation.resolver import BindingResolver
from codex_image.generation.types import GenerationCommand
from codex_image.openai_images_client import OpenAIImagesImageClient
from codex_image.providers.contracts import ProviderConnection, ProviderModelBinding
from codex_image.providers.registry import default_registry
from codex_image.providers.result_assets import AssetLoadError, load_response_asset


class GptImage26Tests(unittest.TestCase):
    def plan(self, parameters, *, operation="generate", **kwargs):
        model = get_model_manifest("gpt-image-2.6-flare")
        binding = ProviderModelBinding(
            id="image26", provider_id="test", canonical_model_id=model.id,
            remote_model_id="custom-image26", protocol_profile="openai_images",
            parameter_codec="gpt_openai_images", operations=frozenset({"generate", "edit"}),
        )
        provider = ProviderConnection(
            id="test", name="Test", base_url="https://images.example/v1",
            api_key="synthetic", concurrency=1, bindings=(binding,),
        )
        resolver = BindingResolver(models={model.id: model}, providers={provider.id: provider},
                                   registry=default_registry())
        command = GenerationCommand(operation=operation, canonical_model_id=model.id,
                                    provider_id=provider.id, prompt="Synthetic test",
                                    parameters=parameters, **kwargs)
        return resolver.resolve(command)

    def test_model_specific_controls_preserve_older_contracts(self):
        old = get_model_manifest("gpt-image-2")
        self.assertNotIn("max", old.parameter("gpt.quality").allowed_values)
        self.assertNotIn("gif", old.parameter("output.format").allowed_values)
        for version in ("2.5", "2.6"):
            for variant in ("flare", "sunburst"):
                model = get_model_manifest(f"gpt-image-{version}-{variant}")
                self.assertIn("max", model.parameter("gpt.quality").allowed_values)
                if version == "2.6":
                    self.assertEqual(model.parameter("gpt.complexity").default, "high")
                    self.assertIn("svg", model.parameter("output.format").allowed_values)

    def test_gif_request_contains_animation_controls_without_compression(self):
        plan = self.plan({"output.format": "gif", "gpt.quality": "max",
                          "gpt.complexity": "low", "gpt.frame_count": 12,
                          "gpt.frame_duration_ms": 100})
        payload = plan.protocol_request.json_body
        self.assertEqual(payload["model"], "custom-image26")
        self.assertEqual(payload["complexity"], "low")
        self.assertEqual(payload["frame_count"], 12)
        self.assertEqual(payload["frame_duration_ms"], 100)
        self.assertEqual(payload["quality"], "max")
        self.assertNotIn("output_compression", payload)

    def test_animation_controls_are_rejected_outside_gif(self):
        with self.assertRaises(ValueError):
            self.plan({"output.format": "png", "gpt.frame_count": 12})
        for bad in (1, 65, True):
            with self.subTest(frames=bad), self.assertRaises(ValueError):
                self.plan({"output.format": "gif", "gpt.frame_count": bad})

    def test_gif_request_rejects_known_local_decoding_limit_before_generation(self):
        with self.assertRaisesRegex(ValueError, "gif_frame_pixel_limit_exceeded"):
            self.plan({"canvas.size": "3840x3840", "output.format": "gif", "gpt.frame_count": 64})
        self.assertEqual(self.plan({"canvas.size": "512x512", "output.format": "gif", "gpt.frame_count": 64}).protocol_request.json_body["frame_count"], 64)

    def test_generated_formats_are_rejected_on_edit(self):
        for output_format in ("gif", "svg"):
            with self.subTest(format=output_format), self.assertRaises(ValueError):
                self.plan({"output.format": output_format}, operation="edit")

    def test_svg_keeps_batch_count_by_repeating_single_output_requests(self):
        plan = self.plan({"output.format": "svg", "output.count": 3})
        self.assertEqual(plan.protocol_request.json_body["n"], 1)
        self.assertEqual(plan.protocol_request.repeat_count, 3)

    def test_static_svg_is_opt_in_and_preserves_vector_bytes(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 256"><path d="M0 0h512v256H0z" fill="#457b66"/></svg>'
        item = {"b64_json": base64.b64encode(svg).decode()}
        with self.assertRaises(AssetLoadError):
            load_response_asset(item)
        result = OpenAIImagesImageClient.parse_response_json(
            json.dumps({"data": [item]}).encode(), request_payload={"output_format": "svg"},
        )
        self.assertEqual(result.image_bytes, svg)
        self.assertEqual(result.output_format, "svg")
        self.assertEqual(result.size, "512x256")

    def test_active_svg_is_rejected_even_when_requested(self):
        for content in ('<script>alert(1)</script>', '<image href="https://external.example/a.png"/>',
                        '<foreignObject><div>HTML</div></foreignObject>',
                        '<path onload="alert(1)"/>', '<style>@import "https://external.example/x";</style>'):
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512">{content}</svg>'.encode()
            with self.subTest(content=content), self.assertRaises((AssetLoadError, RuntimeError)):
                OpenAIImagesImageClient.parse_response_json(
                    json.dumps({"data": [{"b64_json": base64.b64encode(svg).decode()}]}).encode(),
                    request_payload={"output_format": "svg"},
                )


class GptImage26QueueTests(unittest.TestCase):
    task = boundaries.GenerationFailureBoundaryTests.task
    run_queue = staticmethod(boundaries.GenerationFailureBoundaryTests.run_queue)

    def test_svg_batch_persists_previews_and_reopens_without_rasterizing(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512"><path d="M0 0h20v20H0z"/></svg>'
        calls = []
        def handler(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(svg).decode()}]})
        with self.task(handler, canonical_model="gpt-image-2.6-flare", count=3,
                       requested_parameters={"output.format": "svg"}) as (app, client, task_id):
            metadata = self.run_queue(app, task_id)
            self.assertEqual(metadata["status"], "completed", metadata.get("last_error"))
            self.assertEqual(len(calls), 3)
            self.assertTrue(all(call["n"] == 1 for call in calls))
            for path in metadata["output_files"]:
                self.assertTrue(path.endswith(".svg"))
                response = client.get("/outputs/" + path)
                self.assertEqual(response.content, svg)
                self.assertEqual(response.headers["content-type"], "image/svg+xml")
                self.assertIn("sandbox", response.headers["content-security-policy"])
            preview = client.get(f"/api/tasks/{task_id}/outputs/1/thumbnail")
            self.assertEqual(preview.content, svg)
            reopened = app.state.reopen_for_test()
            self.assertEqual(reopened.state.storage.read_metadata(task_id)["output_files"], metadata["output_files"])

    def test_gif_parameters_reach_transport_and_preview_keeps_animation(self):
        encoded = BytesIO()
        Image.new("RGB", (2, 2), "red").save(encoded, "GIF", save_all=True,
            append_images=[Image.new("RGB", (2, 2), "blue")], duration=100, loop=0)
        gif = encoded.getvalue()
        calls = []
        def handler(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(gif).decode()}]})
        with self.task(handler, canonical_model="gpt-image-2.6-flare", requested_parameters={
            "output.format": "gif", "gpt.complexity": "low", "gpt.quality": "max",
            "gpt.frame_count": 2, "gpt.frame_duration_ms": 100,
        }) as (app, client, task_id):
            metadata = self.run_queue(app, task_id)
            self.assertEqual(metadata["status"], "completed", metadata.get("last_error"))
            self.assertEqual(calls[0]["complexity"], "low")
            self.assertEqual(calls[0]["quality"], "max")
            self.assertEqual(calls[0]["frame_count"], 2)
            self.assertEqual(calls[0]["frame_duration_ms"], 100)
            self.assertNotIn("output_compression", calls[0])
            preview = client.get(f"/api/tasks/{task_id}/outputs/1/thumbnail")
            self.assertEqual(preview.content, gif)
            self.assertEqual(preview.headers["content-type"], "image/gif")

    def test_markup_upload_survives_queue_restore_and_multipart_transport(self):
        overlay = BytesIO()
        Image.new("RGBA", (2, 1), (255, 0, 0, 128)).save(overlay, "PNG")
        markup = overlay.getvalue()
        bodies = []
        def handler(request):
            bodies.append(request.content)
            return httpx.Response(200, json={"data": [{"b64_json": TEST_PNG_BASE64}]})
        with self.task(handler, canonical_model="gpt-image-2.6-flare", edit_files=[
            ("images", ("first.png", TEST_PNG_BYTES, "image/png")),
            ("markup", ("markup.png", markup, "image/png")),
        ]) as (app, client, task_id):
            queued = app.state.storage.read_metadata(task_id)
            self.assertTrue(queued["markup_file"])
            self.assertEqual(client.get(f"/api/tasks/{task_id}/markup").content, markup)
            metadata = self.run_queue(app, task_id)
            self.assertEqual(metadata["status"], "completed", metadata.get("last_error"))
            self.assertEqual(len(bodies), 1)
            self.assertIn(b'name="markup"; filename="markup.png"', bodies[0])
            self.assertIn(markup, bodies[0])
            self.assertIn(TEST_PNG_BYTES, bodies[0])

    def test_markup_rejects_opaque_wrong_size_and_mask_combination(self):
        base = ImageInput("data:image/png;base64," + TEST_PNG_BASE64)
        for size, color in [((2, 2), (255, 0, 0, 128)), ((2, 1), (255, 0, 0, 255))]:
            data = BytesIO(); Image.new("RGBA", size, color).save(data, "PNG")
            url = "data:image/png;base64," + base64.b64encode(data.getvalue()).decode()
            with self.assertRaises(ValueError):
                GptImage26Tests().plan({}, operation="edit", image_inputs=(base,), markup_image=url)
        data = BytesIO(); Image.new("RGBA", (2, 1), (255, 0, 0, 128)).save(data, "PNG")
        url = "data:image/png;base64," + base64.b64encode(data.getvalue()).decode()
        with self.assertRaises(ValueError):
            GptImage26Tests().plan({}, operation="edit", image_inputs=(base,), markup_image=url, mask_image=url)

    def test_markup_accepts_transparent_palette_png(self):
        base = ImageInput("data:image/png;base64," + TEST_PNG_BASE64)
        data = BytesIO()
        overlay = Image.new("P", (2, 1), 0)
        overlay.putpixel((1, 0), 1)
        overlay.save(data, "PNG", transparency=0)
        url = "data:image/png;base64," + base64.b64encode(data.getvalue()).decode()
        plan = GptImage26Tests().plan({}, operation="edit", image_inputs=(base,), markup_image=url)
        self.assertEqual(plan.protocol_request.json_body["markup"], {"image_url": url})
