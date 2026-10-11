from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import httpx
from PIL import Image
from starlette.datastructures import UploadFile

from tests import test_webui_reference_image_order as ordering
from codex_image.webui.reference_assets import ReferenceAssetInUseError, ReferenceAssetStorage
from codex_image.webui.recovery import _recover_queue_state
from codex_image.webui.storage import TaskStorage


class ReferenceAssetSubmissionRetentionTests(unittest.TestCase):
    @contextmanager
    def fixture(self, *, protected="AB", limit=2):
        case = ordering.ReferenceImageOrderTests()
        try:
            case.setUp()
            assets = case.app.state.reference_asset_storage
            storage = case.app.state.storage
            task = storage.create_task("generate")
            storage.write_metadata(task.task_id, {
                "task_id": task.task_id, "status": "completed",
                "created_at": "2026-10-08T00:00:00+00:00",
                "reference_assets": [{"id": case.assets[name]} for name in protected],
            })
            assets.max_items = limit
            yield case
        finally:
            case.doCleanups()

    def assert_submits_and_executes(self, case, mode, names, *, canonical=True):
        response = case.submit(mode, names, canonical=canonical)
        self.assertEqual(response.status_code, 200, response.text)
        task = response.json()["task"]
        self.assertEqual([bool(source.get("missing")) for source in task["input_sources"]], [False] * len(names))
        asyncio.run(case.app.state.queue_manager.run_available_once())
        call = (case.fake.edit_calls if mode == "edit" else case.fake.generate_calls)[-1]
        self.assertEqual(case.data_names(call["images" if mode == "edit" else "reference_images"]), list(names))
        stored = case.app.state.storage.read_metadata(task["task_id"])
        self.assertEqual(stored["status"], "completed", stored.get("last_error"))
        for record in stored["reference_assets"]:
            self.assertTrue(case.app.state.reference_asset_storage.image_path(record["id"]).is_file())

    def test_multiple_uploads_survive_a_full_protected_cache(self):
        for mode in ("generate", "edit"):
            for canonical in (True, False):
                with self.subTest(mode=mode, canonical=canonical), self.fixture() as case:
                    self.assert_submits_and_executes(case, mode, "CF", canonical=canonical)

    def test_structured_mentions_keep_deduplicated_inputs_under_cache_pressure(self):
        parts = ["Place ", {"text": "@second", "source": {"kind": "upload", "index": 2}},
                 " beside ", {"text": "@first", "source": {"kind": "upload", "index": 0}}]
        context = {"version": 1, "template": "reference image {number}", "parts": parts, "model_parts": parts}
        for mode in ("generate", "edit"):
            with self.subTest(mode=mode), self.fixture() as case:
                response = case.submit(mode, "DCCF", prompt_fields={
                    "prompt": "Place @second beside @first", "prompt_image_mentions": json.dumps(context),
                })
                self.assertEqual(response.status_code, 200, response.text)
                task_id = response.json()["task"]["task_id"]
                asyncio.run(case.app.state.queue_manager.run_available_once())
                calls = case.fake.edit_calls if mode == "edit" else case.fake.generate_calls
                self.assertEqual(case.data_names(calls[-1]["images" if mode == "edit" else "reference_images"]), list("DCF"))
                self.assertEqual(calls[-1]["prompt"], "Place reference image 3 beside reference image 2")
                stored = case.app.state.storage.read_metadata(task_id)
                self.assertEqual(stored["status"], "completed", stored.get("last_error"))
                source = stored["prompt_image_mentions"]["parts"][1]["source"]
                self.assertEqual(source, {"kind": "asset", "id": hashlib.sha256(case.images["F"]).hexdigest()})

    def test_new_upload_does_not_evict_a_selected_recent_image_before_touch(self):
        for mode in ("generate", "edit"):
            with self.subTest(mode=mode), self.fixture(protected="B") as case:
                self.assert_submits_and_executes(case, mode, "CA")

    def test_default_fifty_image_limit_preserves_new_task_and_historical_inputs(self):
        with self.fixture(limit=50) as case:
            assets = case.app.state.reference_asset_storage
            storage = case.app.state.storage
            historical_ids = list(case.assets.values())
            for index in range(48):
                buffer = BytesIO()
                Image.new("RGB", (2, 2), (index, 10, 20)).save(buffer, format="PNG")
                historical_ids.append(assets.create_or_touch(f"historic-{index}.png", buffer.getvalue(), "image/png")["id"])
            task = storage.create_task("generate")
            storage.write_metadata(task.task_id, {
                "task_id": task.task_id, "status": "completed",
                "reference_assets": [{"id": asset_id} for asset_id in historical_ids],
            })
            self.assertEqual(len(assets.list_recent(limit=100)), 50)
            self.assert_submits_and_executes(case, "edit", "CF")
            self.assertEqual(len(assets.list_recent(limit=100)), 52)
            for asset_id in historical_ids:
                self.assertTrue(assets.image_path(asset_id).is_file())

    def test_retry_keeps_references_after_further_cache_pressure(self):
        from codex_image.webui.queue import RetryableTaskError

        for mode in ("generate", "edit"):
            for snapshot in (True, False):
                with self.subTest(mode=mode, snapshot=snapshot), self.fixture() as case:
                    task = case.submit(mode, "CF").json()["task"]
                    task_id = task["task_id"]
                    if not snapshot:
                        metadata = case.app.state.storage.read_metadata(task_id)
                        metadata.pop("generation_snapshot", None)
                        case.app.state.storage.write_metadata(task_id, metadata)
                    with patch.object(case.fake, f"{mode}_image", side_effect=RuntimeError("synthetic provider failure")):
                        with self.assertRaises(RetryableTaskError):
                            asyncio.run(case.app.state.queue_manager.run_available_once())
                    case.app.state.reference_asset_storage.create_or_touch("later.png", case.images["G"], "image/png")
                    response = case.client.post(f"/api/tasks/{task_id}/retry-failed")
                    self.assertEqual(response.status_code, 200, response.text)
                    asyncio.run(case.app.state.queue_manager.run_available_once())
                    call = (case.fake.edit_calls if mode == "edit" else case.fake.generate_calls)[-1]
                    self.assertEqual(case.data_names(call["images" if mode == "edit" else "reference_images"]), list("CF"))

    def test_failed_submission_releases_temporary_protection(self):
        from codex_image.webui.routes import generation

        for mode in ("generate", "edit"):
            with self.subTest(mode=mode), self.fixture(protected="") as case:
                with patch.object(generation, "_persist_generation_submission", side_effect=RuntimeError("synthetic disk failure")):
                    with self.assertRaisesRegex(RuntimeError, "synthetic disk failure"):
                        case.submit(mode, "CF")
                assets = case.app.state.reference_asset_storage
                for name in "AB":
                    assets.create_or_touch(f"{name}.png", case.images[name], "image/png")
                self.assertEqual({item["id"] for item in assets.list_recent(limit=100)}, set(case.assets.values()))

    def test_index_failure_preserves_durable_inputs_through_recovery(self):
        for mode in ("generate", "edit"):
            with self.subTest(mode=mode), self.fixture() as case:
                storage = case.app.state.storage
                assets = case.app.state.reference_asset_storage
                with patch.object(storage.task_index, "upsert", side_effect=sqlite3.OperationalError("index unavailable")):
                    with self.assertRaises(sqlite3.OperationalError):
                        case.submit(mode, "CF")
                pending = next(task for task in storage.read_tasks_from_metadata() if task["status"] == "queued")
                self.assertNotIn(pending["task_id"], storage.task_index.all_task_ids())
                later = case.submit(mode, "G")
                self.assertEqual(later.status_code, 200, later.text)
                for record in pending["reference_assets"]:
                    self.assertTrue(assets.image_path(record["id"]).is_file())
                    self.assertEqual(case.client.delete(f"/api/reference-assets/{record['id']}").status_code, 409)

                # Startup must restore protection without relying on in-memory reservations.
                reopened = TaskStorage(storage.output_root, input_root=storage.input_root, source_data_root=storage.source_data_root)
                _recover_queue_state(reopened, case.app.state.queue_storage)
                reopened_assets = ReferenceAssetStorage(assets.root, max_items=2, reference_counts_provider=reopened.reference_asset_reference_counts)
                reopened_assets.create_or_touch("later.png", case.images["G"], "image/png")
                for _ in range(2):
                    asyncio.run(case.app.state.queue_manager.run_available_once())
                for task_id in (pending["task_id"], later.json()["task"]["task_id"]):
                    self.assertEqual(storage.read_metadata(task_id)["status"], "completed")
                calls = case.fake.edit_calls if mode == "edit" else case.fake.generate_calls
                field = "images" if mode == "edit" else "reference_images"
                self.assertCountEqual([case.data_names(call[field]) for call in calls], [list("CF"), list("G")])

    def test_unreadable_unindexed_metadata_stops_pruning_and_deletion(self):
        with self.fixture() as case:
            storage = case.app.state.storage
            assets = case.app.state.reference_asset_storage
            with patch.object(storage.task_index, "upsert", side_effect=sqlite3.OperationalError("index unavailable")):
                with self.assertRaises(sqlite3.OperationalError):
                    case.submit("generate", "CF")
            pending = next(task for task in storage.read_tasks_from_metadata() if task["status"] == "queued")
            storage.metadata_path(pending["task_id"]).write_text("{", encoding="utf-8")
            assets.create_or_touch("later.png", case.images["G"], "image/png")
            for record in pending["reference_assets"]:
                self.assertTrue(assets.image_path(record["id"]).is_file())
                response = case.client.delete(f"/api/reference-assets/{record['id']}")
                self.assertEqual(response.status_code, 503, response.text)

    def test_metadata_write_error_respects_whether_the_file_was_committed(self):
        from codex_image.webui import storage as storage_module

        for committed in (False, True):
            with self.subTest(committed=committed), self.fixture() as case:
                storage = case.app.state.storage
                assets = case.app.state.reference_asset_storage
                original_write = storage_module.atomic_write_text

                def fail_metadata(path, *args, **kwargs):
                    if not path.name.endswith(".metadata.json"):
                        return original_write(path, *args, **kwargs)
                    if committed:
                        original_write(path, *args, **kwargs)
                    raise OSError("metadata write failed")

                with patch.object(storage_module, "atomic_write_text", side_effect=fail_metadata):
                    with self.assertRaises(OSError):
                        case.submit("generate", "CF")
                assets.create_or_touch("later.png", case.images["G"], "image/png")
                for name in "CF":
                    asset_id = hashlib.sha256(case.images[name]).hexdigest()
                    if committed:
                        self.assertTrue(assets.image_path(asset_id).is_file())
                    else:
                        with self.assertRaises(FileNotFoundError):
                            assets.image_path(asset_id)

    def test_selected_image_survives_other_requests_during_upload_reads(self):
        async def check(case, mode, stage):
            entered, release = asyncio.Event(), asyncio.Event()
            original_read = UploadFile.read
            paused = False
            filename = "C.png" if stage == "image" else "brief.txt"

            async def controlled_read(upload, size=-1):
                nonlocal paused
                if upload.filename == filename and not paused:
                    paused = True
                    entered.set()
                    await release.wait()
                return await original_read(upload, size)

            data = {
                "prompt": "synthetic reference retention", "prompt_fidelity": "original",
                "canonical_model_id": "gpt-image-2", "provider_id": "codex",
                "binding_id": "codex-gpt-image-2-responses",
                "parameters_json": json.dumps({"canvas.size": "1024x1024", "output.count": 1}),
                "reference_asset_ids": case.assets["A"],
            }
            files = ([("images" if mode == "edit" else "reference_images", (filename, case.images["C"], "image/png"))]
                     if stage == "image" else [("reference_files", (filename, b"Synthetic notes", "text/plain"))])
            transport = httpx.ASGITransport(app=case.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
                with patch.object(UploadFile, "read", controlled_read):
                    request = asyncio.create_task(client.post(f"/api/{mode}", data=data, files=files))
                    try:
                        await asyncio.wait_for(entered.wait(), 5)
                        with patch.object(case, "client", client):
                            later = await asyncio.wait_for(case.submit(mode, "G"), 5)
                        self.assertEqual(later.status_code, 200, later.text)
                        deletion = await asyncio.wait_for(client.delete(f"/api/reference-assets/{case.assets['A']}"), 5)
                    finally:
                        release.set()
                        response = await request
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(deletion.status_code, 409, deletion.text)
            for _ in range(2):
                await case.app.state.queue_manager.run_available_once()
            stored = case.app.state.storage.read_metadata(response.json()["task"]["task_id"])
            self.assertEqual(stored["status"], "completed", stored.get("last_error"))
            calls = case.fake.edit_calls if mode == "edit" else case.fake.generate_calls
            field = "images" if mode == "edit" else "reference_images"
            self.assertCountEqual([case.data_names(call[field]) for call in calls],
                                  [list("G"), list("CA" if stage == "image" else "A")])

        for mode in ("generate", "edit"):
            for stage in ("image", "reference_file"):
                with self.subTest(mode=mode, stage=stage), self.fixture(protected="B") as case:
                    asyncio.run(check(case, mode, stage))

    def test_preflight_rejection_releases_selected_images(self):
        for mode in ("generate", "edit"):
            with self.subTest(mode=mode), self.fixture(protected="B") as case:
                response = case.submit(mode, "A", raw_order="not-json")
                self.assertEqual(response.status_code, 400)
                deletion = case.client.delete(f"/api/reference-assets/{case.assets['A']}")
                self.assertEqual(deletion.status_code, 200, deletion.text)

    def test_selected_id_normalization_and_invalid_id_cleanup(self):
        for mode in ("generate", "edit"):
            for invalid in (False, True):
                with self.subTest(mode=mode, invalid=invalid), self.fixture(protected="B") as case:
                    asset_id = case.assets["A"]
                    ids = [asset_id, "invalid"] if invalid else ["", f" {asset_id} ", asset_id]
                    response = case.submit(mode, "", send_order=False, prompt_fields={"reference_asset_ids": ids})
                    self.assertEqual(response.status_code, 400 if invalid else 200, response.text)
                    if invalid:
                        deletion = case.client.delete(f"/api/reference-assets/{asset_id}")
                        self.assertEqual(deletion.status_code, 200, deletion.text)
                    else:
                        self.assertEqual([record["id"] for record in response.json()["task"]["reference_assets"]], [asset_id])
                        asyncio.run(case.app.state.queue_manager.run_available_once())
                        calls = case.fake.edit_calls if mode == "edit" else case.fake.generate_calls
                        field = "images" if mode == "edit" else "reference_images"
                        self.assertEqual(case.data_names(calls[-1][field]), ["A"])


class ReferenceAssetSubmissionGuardTests(unittest.TestCase):
    def test_overlapping_reservations_survive_cancellation_and_release_independently(self):
        async def check(storage, asset_id):
            first_entered, second_entered = asyncio.Event(), asyncio.Event()
            finish = asyncio.Event()

            async def reserve(entered):
                with storage.retain_for_submission([asset_id, asset_id]):
                    entered.set()
                    await finish.wait()

            first = asyncio.create_task(reserve(first_entered))
            second = asyncio.create_task(reserve(second_entered))
            try:
                await asyncio.wait_for(first_entered.wait(), 2)
                await asyncio.wait_for(second_entered.wait(), 2)
                first.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await first
                storage.create_or_touch("other.png", b"other")
                self.assertTrue(storage.image_path(asset_id).is_file())
                with self.assertRaises(ReferenceAssetInUseError):
                    storage.delete_item(asset_id)
            finally:
                first.cancel()
                second.cancel()
                await asyncio.gather(first, second, return_exceptions=True)
            storage.delete_item(asset_id)

        with tempfile.TemporaryDirectory() as tmp:
            storage = ReferenceAssetStorage(Path(tmp), max_items=1)
            asset = storage.create_or_touch("original.png", b"original")
            asyncio.run(check(storage, asset["id"]))

    def test_nested_failure_preserves_outer_batch_and_releases_inner_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = ReferenceAssetStorage(Path(tmp), max_items=1)
            ids = {name: hashlib.sha256(name.encode()).hexdigest() for name in "abcd"}
            with storage.protect_submission([ids["a"]]):
                storage.create_or_touch("a.png", b"a")
                with self.assertRaisesRegex(RuntimeError, "failed"):
                    with storage.protect_submission([ids["b"]]):
                        storage.create_or_touch("b.png", b"b")
                        raise RuntimeError("failed")
                storage.create_or_touch("c.png", b"c")
                self.assertTrue(storage.image_path(ids["a"]).is_file())
                with self.assertRaises(FileNotFoundError):
                    storage.read_item(ids["b"])
            storage.create_or_touch("d.png", b"d")
            self.assertEqual([item["id"] for item in storage.list_recent()], [ids["d"]])

    def test_concurrent_deletion_and_pruning_wait_for_durable_task_references(self):
        with tempfile.TemporaryDirectory() as tmp, ThreadPoolExecutor(max_workers=2) as pool:
            counts = {}
            storage = ReferenceAssetStorage(Path(tmp), max_items=1, reference_counts_provider=lambda: counts)
            original = storage.create_or_touch("original.png", b"original")
            delete_started, prune_started = threading.Event(), threading.Event()

            def delete():
                delete_started.set()
                storage.delete_item(original["id"])

            def prune():
                prune_started.set()
                return storage.create_or_touch("other.png", b"other")

            with storage.protect_submission([original["id"]]):
                deletion = pool.submit(delete)
                pruning = pool.submit(prune)
                self.assertTrue(delete_started.wait(2))
                self.assertTrue(prune_started.wait(2))
                self.assertFalse(deletion.done())
                self.assertFalse(pruning.done())
                counts[original["id"]] = 1
            with self.assertRaises(ReferenceAssetInUseError):
                deletion.result(timeout=2)
            pruning.result(timeout=2)
            self.assertTrue(storage.image_path(original["id"]).is_file())
