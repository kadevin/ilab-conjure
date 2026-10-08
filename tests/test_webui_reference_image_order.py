from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from tests.webui_helpers import FakeImageClient


class ReferenceImageOrderTests(unittest.TestCase):
    def setUp(self) -> None:
        from codex_image.webui.app import create_app

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.fake = FakeImageClient()
        settings = {
            name: root / f"{name}.json"
            for name in (
                "auth_settings_path", "api_settings_path", "webui_settings_path",
                "network_egress_settings_path", "color_settings_path",
                "prompt_snippets_path", "prompt_templates_path",
            )
        }
        previous = Path.cwd()
        try:
            os.chdir(root)
            self.app = create_app(
                output_root=root / "outputs", client_factory=lambda: self.fake,
                auth_checker=lambda: True, auto_start_queue=False,
                batch_delay_seconds=0, **settings,
            )
        finally:
            os.chdir(previous)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.images = {}
        for index, name in enumerate("ABCDEFG"):
            buffer = BytesIO()
            Image.new("RGB", (2, 2), (index * 30, 100, 150)).save(buffer, format="PNG")
            self.images[name] = buffer.getvalue()
        self.assets = {
            name: self.app.state.reference_asset_storage.create_or_touch(
                f"{name}.png", self.images[name], "image/png"
            )["id"]
            for name in "AB"
        }
        self.galleries = {
            name: self.client.post(
                "/api/gallery", data={"name": name, "category": "portrait"},
                files={"image": (f"{name}.png", self.images[name], "image/png")},
            ).json()["item"]["id"]
            for name in "DE"
        }

    def submit(self, mode, names, *, canonical=True, send_order=True, raw_order=None, binding_id=None, prompt_fields=None):
        uploads, order, asset_ids, gallery_ids = [], [], [], []
        for name in names:
            if name in self.assets:
                asset_ids.append(self.assets[name])
                order.append({"kind": "asset", "id": self.assets[name]})
            elif name in self.galleries:
                gallery_ids.append(self.galleries[name])
                order.append({"kind": "gallery", "id": self.galleries[name]})
            else:
                order.append({"kind": "upload", "index": len(uploads)})
                uploads.append(("images" if mode == "edit" else "reference_images",
                                (f"{name}.png", self.images[name], "image/png")))
        data = {"prompt": "synthetic reference ordering", "prompt_fidelity": "original"}
        data.update(prompt_fields or {})
        if canonical:
            data.update(canonical_model_id="gpt-image-2", provider_id="codex",
                        parameters_json=json.dumps({"canvas.size": "1024x1024", "output.count": 1}))
        else:
            data["size"] = "1024x1024"
        if binding_id is not None:
            data["binding_id"] = binding_id
        if asset_ids:
            data["reference_asset_ids"] = asset_ids
        if gallery_ids:
            data["gallery_image_ids"] = gallery_ids
        if send_order:
            data["reference_image_order"] = raw_order if raw_order is not None else json.dumps(order)
        return self.client.post(f"/api/{mode}", data=data, files=uploads)

    def source_names(self, sources):
        names = {value: name for name, value in self.assets.items()}
        names.update({value: name for name, value in self.galleries.items()})
        names.update({hashlib.sha256(data).hexdigest(): name for name, data in self.images.items()})
        return [names[source["id"]] for source in sources]

    def data_names(self, values):
        names = {data: name for name, data in self.images.items()}
        return [names[base64.b64decode(value.split(",", 1)[1])] for value in values]

    def test_order_survives_submission_storage_execution_and_history(self):
        from codex_image.webui.routes import generation

        for mode in ("generate", "edit"):
            for canonical in (True, False):
                for names in ("ABC", "DEC", "DACBEF", "CF", "AB"):
                    with self.subTest(mode=mode, canonical=canonical, names=names):
                        with patch.object(generation, "_preview_form_generation", wraps=generation._preview_form_generation) as preview:
                            response = self.submit(mode, names, canonical=canonical)
                        self.assertEqual(response.status_code, 200, response.text)
                        self.assertEqual(self.data_names(preview.call_args.kwargs["image_data_urls"]), list(names))
                        task = response.json()["task"]
                        task_id = task["task_id"]
                        self.assertEqual(self.source_names(task["input_sources"]), list(names))
                        stored = self.app.state.storage.read_metadata(task_id)
                        self.assertEqual(self.source_names(stored["input_sources"]), list(names))
                        asyncio.run(self.app.state.queue_manager.run_available_once())
                        calls = self.fake.edit_calls if mode == "edit" else self.fake.generate_calls
                        field = "images" if mode == "edit" else "reference_images"
                        self.assertEqual(self.data_names(calls[-1][field]), list(names))
                        stored = self.app.state.storage.read_metadata(task_id)
                        self.assertEqual(stored["status"], "completed", stored.get("last_error"))
                        self.assertEqual(self.source_names(stored["input_sources"]), list(names))
                        request = json.loads(self.app.state.storage.request_path(task_id).read_text())
                        self.assertEqual(request["webui_image_refs"]["reference_image_order"], stored["reference_image_order"])
                        restored = self.client.get(f"/api/tasks/{task_id}").json()["task"]
                        self.assertEqual(self.source_names(restored["input_sources"]), list(names))

    def test_legacy_request_without_order_keeps_existing_dedup_and_grouping(self):
        response = self.submit("edit", "ADCCABE", send_order=False)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.source_names(response.json()["task"]["input_sources"]), list("CABDE"))

    def test_explicit_order_deduplicates_at_first_occurrence(self):
        for mode in ("generate", "edit"):
            response = self.submit(mode, "DAECCABED")
            self.assertEqual(response.status_code, 200, response.text)
            task = response.json()["task"]
            self.assertEqual(self.source_names(task["input_sources"]), list("DAECB"))
            asyncio.run(self.app.state.queue_manager.run_available_once())
            calls = self.fake.edit_calls if mode == "edit" else self.fake.generate_calls
            self.assertEqual(self.data_names(calls[-1]["images" if mode == "edit" else "reference_images"]), list("DAECB"))

    def gallery_prompt_fields(self, *, fidelity="off"):
        return {
            "prompt": "@D and @E; keep literal {number}",
            "prompt_for_model": "expanded @D and @E; keep literal {number}",
            "prompt_fidelity": fidelity,
            "gallery_prompt": json.dumps({
                "header": "Reference instructions:",
                "template": "Image {number}: {name}; {role}.{note}",
                "references": [
                    {"id": self.galleries[name], "name": name, "role": "role {number}", "note": " literal {name}"}
                    for name in "DE"
                ],
            }),
        }

    def test_gallery_numbers_use_final_deduplicated_order_in_execution_and_history(self):
        self.images["G"] = self.images["A"]
        for mode in ("generate", "edit"):
            for fidelity in ("off", "strict", "original"):
                for snapshot in (True, False):
                    for names, expected in (("CCDAE", "CDAE"), ("GDACE", "ADCE"), ("AGDCE", "ADCE")):
                        with self.subTest(mode=mode, fidelity=fidelity, snapshot=snapshot, names=names):
                            response = self.submit(mode, names, prompt_fields=self.gallery_prompt_fields(fidelity=fidelity))
                            self.assertEqual(response.status_code, 200, response.text)
                            task = response.json()["task"]
                            task_id = task["task_id"]
                            if not snapshot:
                                metadata = self.app.state.storage.read_metadata(task_id)
                                metadata.pop("generation_snapshot", None)
                                self.app.state.storage.write_metadata(task_id, metadata)
                            asyncio.run(self.app.state.queue_manager.run_available_once())
                            call = (self.fake.edit_calls if mode == "edit" else self.fake.generate_calls)[-1]
                            values = call["images" if mode == "edit" else "reference_images"]
                            self.assertEqual([base64.b64decode(value.split(",", 1)[1]) for value in values],
                                             [self.images[name] for name in expected])
                            restored = self.client.get(f"/api/tasks/{task_id}").json()["task"]
                            self.assertEqual(restored["status"], "completed", restored.get("last_error"))
                            for model_prompt in (task["prompt_for_model"], call["prompt"], restored["prompt_for_model"]):
                                self.assertIn("keep literal {number}", model_prompt)
                                if fidelity == "original":
                                    self.assertNotIn("Reference instructions:", model_prompt)
                                else:
                                    self.assertIn("Image 2: D; role {number}. literal {name}", model_prompt)
                                    self.assertIn("Image 4: E; role {number}. literal {name}", model_prompt)
                                    self.assertEqual(model_prompt.count("Reference instructions:"), 1)

    def test_duplicate_upload_preserves_first_filename(self):
        for mode, first, second in (("generate", "C", "F"), ("edit", "G", "H")):
            self.images[second] = self.images[first]
            with self.subTest(mode=mode):
                response = self.submit(mode, first + second)
                self.assertEqual(response.status_code, 200, response.text)
                task = response.json()["task"]
                self.assertEqual([source["filename"] for source in task["input_sources"]], [f"{first}.png"])
                asyncio.run(self.app.state.queue_manager.run_available_once())
                restored = self.client.get(f"/api/tasks/{task['task_id']}").json()["task"]
                self.assertEqual([source["filename"] for source in restored["input_sources"]], [f"{first}.png"])

    def test_invalid_gallery_prompt_is_rejected_before_persisting_uploads(self):
        context = json.loads(self.gallery_prompt_fields()["gallery_prompt"])
        invalid = ["{", "null", "[]", json.dumps({**context, "references": []}),
                   json.dumps({**context, "template": "missing ordinal"}),
                   json.dumps({**context, "references": context["references"] * 2}),
                   json.dumps({**context, "references": [{**context["references"][0], "id": "unknown"}]})]
        for mode in ("generate", "edit"):
            for raw in invalid:
                with self.subTest(mode=mode, raw=raw[:50]):
                    response = self.submit(mode, "CCDAE", prompt_fields={**self.gallery_prompt_fields(), "gallery_prompt": raw})
                    self.assertEqual(response.status_code, 400, response.text)
                    self.assertEqual(response.json()["detail"]["code"], "gallery_prompt_invalid")
        self.assertEqual(self.app.state.storage.list_tasks(), [])
        with self.assertRaises(FileNotFoundError):
            self.app.state.reference_asset_storage.read_item(hashlib.sha256(self.images["C"]).hexdigest())

    def test_legacy_preformatted_gallery_prompt_is_unchanged(self):
        for mode in ("generate", "edit"):
            for send_order in (True, False):
                response = self.submit(mode, "DAE", send_order=send_order, prompt_fields={
                    "prompt_fidelity": "off", "prompt_for_model": "custom gallery instructions: @D #1, @E #3",
                })
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.json()["task"]["prompt_for_model"].startswith("custom gallery instructions: @D #1, @E #3"))

    def test_gallery_identity_stays_distinct_from_identical_uploaded_content(self):
        self.images["G"] = self.images["D"]
        response = self.submit("edit", "GDCAE", prompt_fields=self.gallery_prompt_fields())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["task"]["input_sources"]), 5)
        asyncio.run(self.app.state.queue_manager.run_available_once())
        call = self.fake.edit_calls[-1]
        self.assertEqual(len(call["images"]), 5)
        self.assertEqual(call["images"][0], call["images"][1])
        self.assertIn("Image 2: D", call["prompt"])
        self.assertIn("Image 5: E", call["prompt"])

    def test_retry_reuses_resolved_gallery_numbers_without_appending_guidance_twice(self):
        from codex_image.webui.queue import RetryableTaskError

        for mode in ("generate", "edit"):
            for snapshot in (True, False):
                with self.subTest(mode=mode, snapshot=snapshot):
                    task = self.submit(mode, "CCDAE", prompt_fields=self.gallery_prompt_fields()).json()["task"]
                    task_id = task["task_id"]
                    if not snapshot:
                        metadata = self.app.state.storage.read_metadata(task_id)
                        metadata.pop("generation_snapshot", None)
                        self.app.state.storage.write_metadata(task_id, metadata)
                    with patch.object(self.fake, f"{mode}_image", side_effect=RuntimeError("synthetic transient failure")):
                        with self.assertRaises(RetryableTaskError):
                            asyncio.run(self.app.state.queue_manager.run_available_once())
                    response = self.client.post(f"/api/tasks/{task_id}/retry-failed")
                    self.assertEqual(response.status_code, 200, response.text)
                    asyncio.run(self.app.state.queue_manager.run_available_once())
                    call = (self.fake.edit_calls if mode == "edit" else self.fake.generate_calls)[-1]
                    self.assertEqual(self.data_names(call["images" if mode == "edit" else "reference_images"]), list("CDAE"))
                    self.assertIn("Image 2: D", call["prompt"])
                    self.assertIn("Image 4: E", call["prompt"])
                    self.assertEqual(call["prompt"].count("Reference instructions:"), 1)

    def test_task_list_preserves_order_through_index_projection(self):
        task = self.submit("generate", "DACBE").json()["task"]
        listed = next(item for item in self.client.get("/api/tasks").json()["tasks"] if item["task_id"] == task["task_id"])
        self.assertEqual(self.source_names(listed["input_sources"]), list("DACBE"))

    def test_execution_without_snapshot_preserves_order(self):
        for mode in ("generate", "edit"):
            task = self.submit(mode, "DACBE").json()["task"]
            metadata = self.app.state.storage.read_metadata(task["task_id"])
            metadata.pop("generation_snapshot", None)
            self.app.state.storage.write_metadata(task["task_id"], metadata)
            asyncio.run(self.app.state.queue_manager.run_available_once())
            calls = self.fake.edit_calls if mode == "edit" else self.fake.generate_calls
            self.assertEqual(self.data_names(calls[-1]["images" if mode == "edit" else "reference_images"]), list("DACBE"))
            restored = self.client.get(f"/api/tasks/{task['task_id']}").json()["task"]
            self.assertEqual(restored["status"], "completed", restored.get("last_error"))
            self.assertEqual(self.source_names(restored["input_sources"]), list("DACBE"))

    def test_upload_matching_recent_asset_keeps_first_occurrence(self):
        self.images["G"] = self.images["A"]
        expected_ids = [self.assets["A"], self.galleries["D"], hashlib.sha256(self.images["C"]).hexdigest(),
                        self.galleries["E"], self.assets["B"]]
        for mode in ("generate", "edit"):
            task = self.submit(mode, "GDACGEB").json()["task"]
            self.assertEqual([source["id"] for source in task["input_sources"]], expected_ids)
            asyncio.run(self.app.state.queue_manager.run_available_once())
            calls = self.fake.edit_calls if mode == "edit" else self.fake.generate_calls
            values = calls[-1]["images" if mode == "edit" else "reference_images"]
            self.assertEqual([base64.b64decode(value.split(",", 1)[1]) for value in values],
                             [self.images[name] for name in "ADCEB"])

    def test_real_client_serialization_keeps_order_with_mock_upstream(self):
        from email import policy
        from email.parser import BytesParser

        from codex_image.openai_images_client import OpenAIImagesImageClient
        from codex_image.openai_responses_client import OpenAIResponsesImageClient
        from tests.helpers import FakeResponse, FakeTransport, make_sse_completed_event

        encoded = base64.b64encode(self.images["F"]).decode("ascii")
        for protocol in ("images", "responses"):
            for mode in ("generate", "edit"):
                with self.subTest(protocol=protocol, mode=mode):
                    body = (json.dumps({"data": [{"b64_json": encoded}]}).encode()
                            if protocol == "images" else make_sse_completed_event(image_b64=encoded))
                    transport = FakeTransport([FakeResponse(status=200, body=body)])
                    client_type = OpenAIImagesImageClient if protocol == "images" else OpenAIResponsesImageClient
                    self.fake = client_type(api_key="synthetic", base_url="https://upstream.invalid", transport=transport)
                    response = self.submit(mode, "CCDAE", binding_id=f"codex-gpt-image-2-{protocol}",
                                           prompt_fields=self.gallery_prompt_fields())
                    self.assertEqual(response.status_code, 200, response.text)
                    asyncio.run(self.app.state.queue_manager.run_available_once())
                    self.assertEqual(len(transport.requests), 1)
                    request = transport.requests[0]
                    if protocol == "images":
                        mime = BytesParser(policy=policy.default).parsebytes(
                            f"Content-Type: {request['headers']['Content-Type']}\r\n\r\n".encode() + request["body"])
                        image_bytes = [part.get_payload(decode=True) for part in mime.iter_parts() if part.get_content_type().startswith("image/")]
                        model_prompt = next(part.get_payload(decode=True).decode() for part in mime.iter_parts()
                                            if part.get_param("name", header="Content-Disposition") == "prompt")
                    else:
                        content = json.loads(request["body"])["input"][0]["content"]
                        image_bytes = [base64.b64decode(part["image_url"].split(",", 1)[1]) for part in content if part["type"] == "input_image"]
                        model_prompt = next(part["text"] for part in content if part["type"] == "input_text")
                    self.assertEqual(image_bytes, [self.images[name] for name in "CDAE"])
                    self.assertIn("Image 2: D", model_prompt)
                    self.assertIn("Image 4: E", model_prompt)

    def test_missing_reference_keeps_its_history_slot_and_blocks_execution(self):
        from codex_image.webui.queue import RetryableTaskError

        self.app.state.queue_manager.auto_retry = False
        task = self.submit("edit", "DACBE").json()["task"]
        self.app.state.gallery_storage.delete_item(self.galleries["D"])
        with self.assertRaises(RetryableTaskError):
            asyncio.run(self.app.state.queue_manager.run_available_once())
        restored = self.client.get(f"/api/tasks/{task['task_id']}").json()["task"]
        self.assertEqual(restored["status"], "failed")
        self.assertEqual(self.fake.edit_calls, [])
        self.assertEqual(self.source_names(restored["input_sources"]), list("DACBE"))
        self.assertTrue(restored["input_sources"][0]["missing"])
        response = self.submit("edit", "DACBE")
        self.assertEqual(response.status_code, 404, response.text)

    def test_explicit_empty_order_does_not_infer_unselected_gallery_images(self):
        from codex_image.webui.task_enrichment import _with_file_urls

        metadata = {"task_id": "synthetic", "prompt": "@D", "reference_image_order": []}
        enriched = _with_file_urls(metadata, gallery_storage=self.app.state.gallery_storage)
        self.assertFalse(enriched.get("gallery_refs"))
        metadata.pop("reference_image_order")
        enriched = _with_file_urls(metadata, gallery_storage=self.app.state.gallery_storage)
        self.assertEqual(enriched["gallery_refs"][0]["id"], self.galleries["D"])

    def test_invalid_order_is_rejected_before_creating_task_or_upload_asset(self):
        for raw in ("{", "{}", "[]", '[{"kind":"upload","index":9}]',
                    '[{"kind":"upload","index":true}]',
                    '[{"kind":"asset","id":"unknown"}]'):
            with self.subTest(raw=raw):
                response = self.submit("edit", "AC", raw_order=raw)
                self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(response.json()["detail"]["code"], "reference_image_order_invalid")
        self.assertEqual(self.app.state.storage.list_tasks(), [])
        with self.assertRaises(FileNotFoundError):
            self.app.state.reference_asset_storage.read_item(hashlib.sha256(self.images["C"]).hexdigest())
