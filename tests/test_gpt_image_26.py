from __future__ import annotations

import base64
import json
import unittest
from email.parser import BytesParser
from email.policy import default
from io import BytesIO

import httpx
from PIL import Image
from codex_image.client_types import DEFAULT_MAIN_MODEL
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
from codex_image.webui.routes.generation import _generation_request_error


class GptImage26Tests(unittest.TestCase):
    def plan(self, parameters, *, operation="generate", model_id="gpt-image-2.6-flare", **kwargs):
        model = get_model_manifest(model_id)
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

    def test_reference_gif_preserves_animation_controls_for_both_models(self):
        image = ImageInput("data:image/png;base64," + TEST_PNG_BASE64)
        for model in ("gpt-image-2.6-flare", "gpt-image-2.6-sunburst"):
            for operation in ("generate", "edit"):
                with self.subTest(model=model, operation=operation):
                    plan = self.plan({"output.format": "gif", "gpt.frame_count": 12,
                                      "gpt.frame_duration_ms": 100}, model_id=model,
                                     operation=operation, image_inputs=(image,))
                    self.assertEqual(plan.protocol_request.path, "/images/edits")
                    self.assertEqual(plan.protocol_request.content_type, "multipart/form-data")
                    payload = plan.protocol_request.json_body
                    self.assertEqual(payload["output_format"], "gif")
                    self.assertEqual(payload["images"], [{"image_url": image.data_url}])
                    self.assertEqual(payload["frame_count"], 12)
                    self.assertEqual(payload["frame_duration_ms"], 100)
                    for field in ("stream", "partial_images", "output_compression", "mask"):
                        self.assertNotIn(field, payload)

    def test_reference_svg_uses_edit_and_preserves_batch_count_for_both_models(self):
        image = ImageInput("data:image/png;base64," + TEST_PNG_BASE64)
        for model in ("gpt-image-2.6-flare", "gpt-image-2.6-sunburst"):
            for operation in ("generate", "edit"):
                with self.subTest(model=model, operation=operation):
                    plan = self.plan({"output.format": "svg", "output.count": 3},
                                     model_id=model, operation=operation, image_inputs=(image,))
                    self.assertEqual(plan.protocol_request.path, "/images/edits")
                    self.assertEqual(plan.protocol_request.content_type, "multipart/form-data")
                    self.assertEqual(plan.protocol_request.repeat_count, 3)
                    payload = plan.protocol_request.json_body
                    self.assertEqual(payload["output_format"], "svg")
                    self.assertEqual(payload["images"], [{"image_url": image.data_url}])
                    self.assertEqual(payload["n"], 1)
                    for field in ("stream", "partial_images", "output_compression", "frame_count", "frame_duration_ms"):
                        self.assertNotIn(field, payload)

    def test_reference_gif_rejects_mask_and_incompatible_parameters(self):
        image = ImageInput("data:image/png;base64," + TEST_PNG_BASE64)
        for kwargs in (
            {"mask_image": image.data_url},
            {"legacy_compat_parameters": {"gpt.output_compression": 80}},
            {"legacy_compat_parameters": {"gpt.partial_images": 1}},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, "gif_output_does_not_support"):
                self.plan({"output.format": "gif"}, operation="edit", image_inputs=(image,), **kwargs)
        for parameters in ({"gpt.output_compression": 80}, {"gpt.partial_images": 1}, {"stream": True}):
            with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                self.plan({"output.format": "gif", **parameters}, operation="edit", image_inputs=(image,))
        with self.assertRaisesRegex(ValueError, "gif_frame_pixel_limit_exceeded"):
            self.plan({"canvas.size": "3840x3840", "output.format": "gif", "gpt.frame_count": 64},
                      operation="edit", image_inputs=(image,))

    def test_svg_keeps_batch_count_by_repeating_single_output_requests(self):
        plan = self.plan({"output.format": "svg", "output.count": 3})
        self.assertEqual(plan.protocol_request.json_body["n"], 1)
        self.assertEqual(plan.protocol_request.repeat_count, 3)

    def test_gif_errors_keep_actionable_public_details(self):
        for suffix, keyword in (("mask", "mask"), ("compression", "compression"), ("partial_images", "previews")):
            code = "gif_output_does_not_support_" + suffix
            with self.subTest(code=code):
                error = _generation_request_error(ValueError(code))
                self.assertEqual(error.status_code, 400)
                self.assertEqual(error.detail["code"], code)
                self.assertIn(keyword, error.detail["message"])
                self.assertIn(" or choose ", error.detail["message"])

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

    def test_svg_author_model_is_added_only_when_openai_requires_it(self):
        missing_model = {"error": {"code": "missing_required_parameter", "param": "svg.model"}}
        invalid_size = {"error": {"code": "invalid_value", "param": "size"}}
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M0 0h8v8z"/></svg>'
        image = ("images", ("reference.png", TEST_PNG_BYTES, "image/png"))
        for base_url, error, should_retry in (
            ("https://api.openai.com/v1", missing_model, True),
            ("https://api.openai.com:443/v1", missing_model, True),
            ("https://api.openai.com/v1", invalid_size, False),
            ("https://api.openai.com:8443/v1", missing_model, False),
            ("https://relay.example/v1", missing_model, False),
        ):
            for operation in ("generate", "edit"):
                calls = []

                def handler(request):
                    calls.append(request)
                    if len(calls) == 1:
                        return httpx.Response(400, json=error)
                    return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(svg).decode()}]})

                with self.subTest(base_url=base_url, error=error, operation=operation), self.task(
                    handler, canonical_model="gpt-image-2.6-flare", base_url=base_url,
                    requested_parameters={"output.format": "svg"}, edit_files=[image] if operation == "edit" else None,
                ) as (app, _client, task_id):
                    task = self.run_queue(app, task_id)
                    self.assertEqual(len(calls), 2 if should_retry else 1)
                    if should_retry:
                        self.assertEqual(task["status"], "completed", task.get("error"))
                    else:
                        self.assertNotEqual(task["status"], "completed")
                    if operation == "generate":
                        self.assertNotIn("svg", json.loads(calls[0].content))
                        if should_retry:
                            self.assertEqual(json.loads(calls[1].content)["svg"], {"model": DEFAULT_MAIN_MODEL})
                    else:
                        self.assertNotIn(b'name="svg[model]"', calls[0].content)
                        if should_retry:
                            self.assertIn(f'name="svg[model]"\r\n\r\n{DEFAULT_MAIN_MODEL}'.encode(), calls[1].content)
                            self.assertIn(TEST_PNG_BYTES, calls[1].content)

    def test_svg_author_model_is_reused_within_an_official_openai_batch(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M0 0h8v8z"/></svg>'
        image = ("images", ("reference.png", TEST_PNG_BYTES, "image/png"))
        for operation in ("generate", "edit"):
            for author_required in (True, False):
                author_sent = []

                def handler(request):
                    if operation == "edit":
                        self.assertIn(TEST_PNG_BYTES, request.content)
                        present = f'name="svg[model]"\r\n\r\n{DEFAULT_MAIN_MODEL}'.encode() in request.content
                    else:
                        present = json.loads(request.content).get("svg") == {"model": DEFAULT_MAIN_MODEL}
                    author_sent.append(present)
                    if author_required and not present:
                        return httpx.Response(400, json={
                            "error": {"code": "missing_required_parameter", "param": "svg.model"},
                        })
                    return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(svg).decode()}]})

                with self.subTest(operation=operation, author_required=author_required), self.task(
                    handler, canonical_model="gpt-image-2.6-flare", count=3,
                    base_url="https://api.openai.com/v1", requested_parameters={"output.format": "svg"},
                    edit_files=[image] if operation == "edit" else None,
                ) as (app, _client, task_id):
                    task = self.run_queue(app, task_id)
                    self.assertEqual(task["status"], "completed", task.get("error"))
                    self.assertEqual(len(task["output_files"]), 3)
                    self.assertEqual(author_sent, [False, True, True, True] if author_required else [False] * 3)

    def test_svg_author_permission_failure_can_be_retried_with_updated_connection(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M0 0h8v8z"/></svg>'
        image = ("images", ("reference.png", TEST_PNG_BYTES, "image/png"))
        allowed_author = "gpt-6.2-sol"
        for operation, status, rejection in (
            ("generate", 403, {"code": "insufficient_permissions", "param": "svg.model"}),
            ("edit", 404, {"code": "model_not_found", "message": f"No access to `{DEFAULT_MAIN_MODEL}`."}),
        ):
            calls = []

            def handler(request):
                if operation == "edit":
                    self.assertIn(TEST_PNG_BYTES, request.content)
                    message = BytesParser(policy=default).parsebytes(
                        f'Content-Type: {request.headers["content-type"]}\r\n\r\n'.encode() + request.content
                    )
                    author = next((
                        part.get_payload(decode=True).decode() for part in message.iter_parts()
                        if part.get_param("name", header="content-disposition") == "svg[model]"
                    ), None)
                else:
                    author = json.loads(request.content).get("svg", {}).get("model")
                calls.append(author)
                if author is None:
                    return httpx.Response(400, json={
                        "error": {"code": "missing_required_parameter", "param": "svg.model"},
                    })
                if author != allowed_author:
                    return httpx.Response(status, json={"error": rejection})
                return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(svg).decode()}]})

            with self.subTest(operation=operation), self.task(
                handler, canonical_model="gpt-image-2.6-flare",
                base_url="https://api.openai.com:443/v1", requested_parameters={"output.format": "svg"},
                edit_files=[image] if operation == "edit" else None,
            ) as (app, client, task_id):
                failed = self.run_queue(app, task_id)
                self.assertEqual(failed["status"], "failed")
                self.assertEqual(failed["generation_error"]["code"], "svg_author_model_rejected")
                self.assertFalse(failed["generation_error"]["retryable"])
                self.run_queue(app, task_id)
                self.assertEqual(calls, [None, DEFAULT_MAIN_MODEL])

                settings = client.get("/api/api-settings").json()["settings"]
                settings["providers"][0]["svg_author_model"] = allowed_author
                saved = client.patch("/api/api-settings", json=settings)
                self.assertEqual(saved.status_code, 200, saved.text)
                self.assertEqual(saved.json()["settings"]["providers"][0]["svg_author_model"], allowed_author)
                retry = client.post(f"/api/tasks/{task_id}/retry-failed")
                self.assertEqual(retry.status_code, 200, retry.text)
                completed = self.run_queue(app, task_id)
                self.assertEqual(completed["status"], "completed", completed.get("error"))
                self.assertEqual(calls, [None, DEFAULT_MAIN_MODEL, None, allowed_author])

    def test_gif_edit_frame_limit_is_specific_to_official_openai(self):
        def handler(_request):
            self.fail("Validation must not call a provider")

        image = ("images", ("reference.png", TEST_PNG_BYTES, "image/png"))
        for base_url, limit in (("https://api.openai.com/v1", 16), ("https://relay.example/v1", None)):
            with self.subTest(base_url=base_url), self.task(
                handler, canonical_model="gpt-image-2.6-flare", edit_files=[image],
                base_url=base_url, requested_parameters={"output.format": "gif", "gpt.frame_count": 16},
            ) as (_app, client, _task_id):
                catalog = client.get("/api/generation-catalog").json()
                provider = next(provider for provider in catalog["providers"] if provider["id"] == "relay")
                self.assertEqual(provider.get("gif_edit_max_frames"), limit)
                response = client.post("/api/edit", files=[image], data={
                    "prompt": "Synthetic reference GIF", "canonical_model_id": "gpt-image-2.6-flare",
                    "provider_id": "relay", "parameters_json": json.dumps({
                        "canvas.size": "512x512", "output.format": "gif", "gpt.frame_count": 17,
                    }),
                })
                self.assertEqual(response.status_code, 400 if limit else 200, response.text)
                if limit:
                    self.assertEqual(response.json()["detail"]["code"], "openai_gif_edit_frame_limit_exceeded")

    def test_gif_mask_and_compression_errors_reach_api_without_provider_calls(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"data": [{"b64_json": TEST_PNG_BASE64}]})
        image = ("images", ("reference.png", TEST_PNG_BYTES, "image/png"))
        with self.task(handler, canonical_model="gpt-image-2.6-flare", requested_parameters={"output.format": "gif"},
                       edit_files=[image]) as (_app, client, _task_id):
            for parameters, files, code in (
                ({"output.format": "gif"}, [image, ("mask", ("mask.png", TEST_PNG_BYTES, "image/png"))], "gif_output_does_not_support_mask"),
                ({"output.format": "gif", "gpt.output_compression": 80}, [image], "output_compression_requires_jpeg_or_webp"),
            ):
                with self.subTest(code=code):
                    response = client.post("/api/edit", files=files, data={
                        "prompt": "Synthetic incompatible GIF", "canonical_model_id": "gpt-image-2.6-flare",
                        "provider_id": "relay", "parameters_json": json.dumps(parameters),
                    })
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.json()["detail"]["code"], code)
                    self.assertNotEqual(response.json()["detail"]["message"], "The generation request is invalid.")
            self.assertEqual(calls, [])

    def test_svg_batch_persists_previews_and_reopens_without_rasterizing(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512"><path d="M0 0h20v20H0z"/></svg>'
        for operation in ("generate", "edit"):
            calls = []
            def handler(request):
                calls.append(request)
                return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(svg).decode()}]})
            edit_files = [("images", ("reference.png", TEST_PNG_BYTES, "image/png"))] if operation == "edit" else None
            with self.subTest(operation=operation), self.task(
                handler, canonical_model="gpt-image-2.6-flare", count=3,
                requested_parameters={"output.format": "svg"}, edit_files=edit_files,
            ) as (app, client, task_id):
                reopen = app.state.reopen_for_test
                app = reopen()
                metadata = self.run_queue(app, task_id)
                self.assertEqual(metadata["status"], "completed", metadata.get("last_error"))
                self.assertEqual(len(calls), 3)
                for request in calls:
                    if operation == "edit":
                        self.assertEqual(request.url.path, "/v1/images/edits")
                        self.assertTrue(request.headers["content-type"].startswith("multipart/form-data;"))
                        message = BytesParser(policy=default).parsebytes(
                            f'Content-Type: {request.headers["content-type"]}\r\n\r\n'.encode() + request.content)
                        parts = {part.get_param("name", header="content-disposition"): part
                                 for part in message.iter_parts()}
                        self.assertEqual(parts.pop("image").get_payload(decode=True), TEST_PNG_BYTES)
                        fields = {key: part.get_payload(decode=True).decode() for key, part in parts.items()}
                    else:
                        self.assertEqual(request.url.path, "/v1/images/generations")
                        fields = json.loads(request.content)
                    self.assertEqual(int(fields["n"]), 1)
                    self.assertEqual(fields["output_format"], "svg")
                    for field in ("stream", "partial_images", "output_compression", "frame_count", "frame_duration_ms"):
                        self.assertNotIn(field, fields)
                self.assertEqual(len(metadata["output_files"]), 3)
                for path in metadata["output_files"]:
                    self.assertTrue(path.endswith(".svg"))
                    response = client.get("/outputs/" + path)
                    self.assertEqual(response.content, svg)
                    self.assertEqual(response.headers["content-type"], "image/svg+xml")
                    self.assertIn("sandbox", response.headers["content-security-policy"])
                preview = client.get(f"/api/tasks/{task_id}/outputs/1/thumbnail")
                self.assertEqual(preview.content, svg)
                reopened = reopen()
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

    def test_reference_gif_survives_queue_restore_and_multipart_transport(self):
        encoded = BytesIO()
        Image.new("RGB", (2, 2), "red").save(encoded, "GIF", save_all=True,
            append_images=[Image.new("RGB", (2, 2), "blue")], duration=100, loop=0)
        gif = encoded.getvalue()
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(gif).decode()}]})

        parameters = {"output.format": "gif", "gpt.complexity": "low", "gpt.quality": "max",
                      "gpt.frame_count": 2, "gpt.frame_duration_ms": 100}
        with self.task(handler, canonical_model="gpt-image-2.6-sunburst", requested_parameters=parameters,
                       edit_files=[("images", ("reference.png", TEST_PNG_BYTES, "image/png"))]) as (app, client, task_id):
            app = app.state.reopen_for_test()
            metadata = self.run_queue(app, task_id)
            self.assertEqual(metadata["status"], "completed", metadata.get("last_error"))
            self.assertEqual(len(calls), 1)
            request = calls[0]
            self.assertEqual(request.url.path, "/v1/images/edits")
            self.assertEqual(request.method, "POST")
            self.assertTrue(request.headers["content-type"].startswith("multipart/form-data;"))
            message = BytesParser(policy=default).parsebytes(
                f'Content-Type: {request.headers["content-type"]}\r\n\r\n'.encode() + request.content)
            parts = {part.get_param("name", header="content-disposition"): part
                     for part in message.iter_parts()}
            self.assertEqual(parts["image"].get_payload(decode=True), TEST_PNG_BYTES)
            for field, value in {"output_format": b"gif", "frame_count": b"2",
                                 "frame_duration_ms": b"100", "complexity": b"low", "quality": b"max"}.items():
                self.assertEqual(parts[field].get_payload(decode=True), value)
            for field in ("output_compression", "mask", "stream", "partial_images"):
                self.assertNotIn(field, parts)
            requested = metadata["generation_snapshot"]["requested_parameters"]
            for key, value in parameters.items():
                self.assertEqual(requested[key], value)
            self.assertTrue(metadata["output_files"][0].endswith(".gif"))
            preview = client.get(f"/api/tasks/{task_id}/outputs/1/thumbnail")
            self.assertEqual(preview.content, gif)
            self.assertEqual(preview.headers["content-type"], "image/gif")

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
