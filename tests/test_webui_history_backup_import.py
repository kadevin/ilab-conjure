from __future__ import annotations

from dataclasses import asdict
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import time
import unittest
from unittest import mock
import zipfile

from PIL import Image

from codex_image.webui.history_backup_format import (
    BACKUP_FORMAT,
    BACKUP_FORMAT_VERSION,
    BackupFileEntry,
    canonical_task_fingerprint,
)
from codex_image.webui.history_backup_import import HistoryBackupImportService
from codex_image.webui.gallery_storage import GalleryStorage
from codex_image.webui.history_backup_plan import TaskBackupPlanner
from codex_image.webui.reference_assets import ReferenceAssetStorage
from codex_image.webui.reference_files import ReferenceFileStorage, validate_reference_file
from codex_image.webui.storage import TaskStorage


class _Planner:
    def __init__(self, fingerprints: dict[str, str | None] | None = None) -> None:
        self.fingerprints = fingerprints or {}

    def current_task_fingerprint(self, task_id: str) -> str | None:
        return self.fingerprints.get(task_id)


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _task_files(task_id: str, *, extra: tuple[str, str, bytes] | None = None):
    metadata = {"task_id": task_id, "created_at": "2026-08-01T00:00:00Z", "status": "completed"}
    request = {"prompt": "safe"}
    organization = {"favorite": False, "tags": []}
    payloads = {
        f"tasks/{task_id}/source/metadata.json": _json_bytes(metadata),
        f"tasks/{task_id}/source/request.json": _json_bytes(request),
        f"tasks/{task_id}/source/organization.json": _json_bytes(organization),
    }
    roles = {
        f"tasks/{task_id}/source/metadata.json": ("metadata", None),
        f"tasks/{task_id}/source/request.json": ("request", None),
        f"tasks/{task_id}/source/organization.json": ("organization", None),
    }
    if extra is not None:
        path, role, data = extra
        payloads[path] = data
        roles[path] = (role, 1)
    entries = tuple(
        BackupFileEntry(
            path=path,
            role=roles[path][0],
            required=True,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            source_index=roles[path][1],
        )
        for path, data in payloads.items()
    )
    fingerprint = canonical_task_fingerprint(metadata, request, entries, organization)
    task = {
        "task_id": task_id,
        "created_at": metadata["created_at"],
        "fingerprint": fingerprint,
        "files": [asdict(entry) for entry in entries],
    }
    return task, payloads, fingerprint


def _archive_bytes(
    *,
    tasks: list[dict[str, object]] | None = None,
    payloads: dict[str, bytes] | None = None,
    version: int = BACKUP_FORMAT_VERSION,
    extra_members: list[tuple[zipfile.ZipInfo | str, bytes]] | None = None,
    compression: int = zipfile.ZIP_DEFLATED,
) -> bytes:
    if tasks is None or payloads is None:
        task, payloads, _ = _task_files("task-1")
        tasks = [task]
    file_entries = [entry for task in tasks for entry in task["files"]]
    manifest = {
        "format": BACKUP_FORMAT,
        "version": version,
        "created_at": "2026-08-01T00:00:00Z",
        "app_version": "test",
        "scope": {"kind": "selected"},
        "task_count": len(tasks),
        "file_count": len(file_entries),
        "uncompressed_bytes": sum(entry["size_bytes"] for entry in file_entries),
        "tasks": tasks,
    }
    destination = io.BytesIO()
    with zipfile.ZipFile(destination, "w", compression=compression, allowZip64=True) as archive:
        for path, data in payloads.items():
            archive.writestr(path, data)
        for name, data in extra_members or []:
            archive.writestr(name, data)
        archive.writestr("manifest.json", _json_bytes(manifest))
    return destination.getvalue()


def _replace_manifest(archive_bytes: bytes, mutate) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(archive_bytes))
    manifest = json.loads(source.read("manifest.json"))
    mutate(manifest)
    members = [(info, source.read(info)) for info in source.infolist() if info.filename != "manifest.json"]
    source.close()
    destination = io.BytesIO()
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for info, data in members:
            archive.writestr(info, data)
        archive.writestr("manifest.json", _json_bytes(manifest))
    return destination.getvalue()


def _set_encrypted_flag(payload: bytes) -> bytes:
    changed = bytearray(payload)
    cursor = 0
    while True:
        cursor = changed.find(b"PK\x03\x04", cursor)
        if cursor < 0:
            break
        flags = int.from_bytes(changed[cursor + 6 : cursor + 8], "little") | 1
        changed[cursor + 6 : cursor + 8] = flags.to_bytes(2, "little")
        cursor += 4
    cursor = 0
    while True:
        cursor = changed.find(b"PK\x01\x02", cursor)
        if cursor < 0:
            break
        flags = int.from_bytes(changed[cursor + 8 : cursor + 10], "little") | 1
        changed[cursor + 8 : cursor + 10] = flags.to_bytes(2, "little")
        cursor += 4
    return bytes(changed)


def _png_bytes(color: tuple[int, int, int]) -> bytes:
    target = io.BytesIO()
    Image.new("RGB", (3, 2), color).save(target, format="PNG")
    return target.getvalue()


def _full_restore_archive(task_id: str = "restore-all") -> tuple[bytes, dict[str, bytes]]:
    binaries = {
        "output": _png_bytes((255, 0, 0)),
        "input": _png_bytes((0, 255, 0)),
        "mask": _png_bytes((0, 0, 0)),
        "reference_asset": _png_bytes((0, 0, 255)),
        "gallery_reference": _png_bytes((255, 255, 0)),
        "reference_file": b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n",
    }
    metadata = {
        "task_id": task_id,
        "created_at": "2026-08-01T00:00:00Z",
        "status": "completed",
        "archived_at": "2026-08-01T01:00:00Z",
        "output_files": ["/archive/output.png"],
        "outputs": [{"index": 1, "status": "completed", "file": "/archive/output.png"}],
        "input_files": ["/archive/input.png"],
        "mask_file": "/archive/mask.png",
        "reference_assets": [{"id": "a" * 64, "filename": "portrait.png"}],
        "gallery_refs": [{"id": "old-gallery", "name": "Pose", "category": "portrait", "filename": "pose.png"}],
        "reference_files": [{
            "id": "b" * 64,
            "filename": "notes.pdf",
            "mime_type": "application/pdf",
            "family": "pdf",
            "size_bytes": 1,
            "detail": "auto",
        }],
        "nested": {
            "arbitrary": "/Users/archive/private.png",
            "windows": "C:\\archive\\private.png",
            "local_url": "http://127.0.0.1:8787/outputs/private.png",
            "safe": "keep",
        },
    }
    request = {
        "prompt": "safe",
        "input_files": ["/archive/request-input.png"],
        "mask_file": "/archive/request-mask.png",
        "webui_image_refs": {
            "reference_assets": [{"id": "old-asset", "url": "/inputs/old.png"}],
            "gallery_refs": [{"id": "old-gallery", "url": "http://localhost/gallery/old"}],
        },
        "nested": {"unknown": "file:///archive/secret.png", "safe": "keep"},
    }
    organization = {"favorite": True, "tags": [{"tag_id": "archive-local-id", "name": "  Travel  "}]}
    payloads = {
        f"tasks/{task_id}/source/metadata.json": _json_bytes(metadata),
        f"tasks/{task_id}/source/request.json": _json_bytes(request),
        f"tasks/{task_id}/source/organization.json": _json_bytes(organization),
    }
    role_paths = {
        "output": f"tasks/{task_id}/outputs/output-0001.png",
        "input": f"tasks/{task_id}/inputs/images/input-0001.png",
        "mask": f"tasks/{task_id}/inputs/masks/mask-0001.png",
        "reference_asset": f"tasks/{task_id}/inputs/images/reference_asset-0001.png",
        "gallery_reference": f"tasks/{task_id}/inputs/images/gallery_reference-0001.png",
        "reference_file": f"tasks/{task_id}/inputs/references/reference_file-0001.pdf",
    }
    for role, path in role_paths.items():
        payloads[path] = binaries[role]
    entries = tuple(
        BackupFileEntry(
            path=path,
            role=("metadata" if path.endswith("metadata.json") else "request" if path.endswith("request.json") else "organization" if path.endswith("organization.json") else next(role for role, role_path in role_paths.items() if role_path == path)),
            required=True,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            source_index=None if path.endswith(".json") else 1,
        )
        for path, data in payloads.items()
    )
    fingerprint = canonical_task_fingerprint(metadata, request, entries, organization)
    task = {"task_id": task_id, "created_at": metadata["created_at"], "fingerprint": fingerprint, "files": [asdict(entry) for entry in entries]}
    return _archive_bytes(tasks=[task], payloads=payloads), binaries


class HistoryBackupImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "private-imports"
        self.service = HistoryBackupImportService(
            _Planner(),
            self.root,
            max_upload_bytes=1024 * 1024,
            max_chunk_bytes=64,
            max_entries=32,
            max_member_bytes=64 * 1024,
            max_expanded_bytes=128 * 1024,
            max_compression_ratio=100,
            max_manifest_bytes=32 * 1024,
            min_free_bytes=0,
            free_ratio=0,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _upload(self, payload: bytes, *, service=None):
        service = service or self.service
        session = service.create("backup.zip", len(payload))
        for offset in range(0, len(payload), 64):
            chunk = payload[offset : offset + 64]
            service.append_chunk(session.session_id, offset, chunk, hashlib.sha256(chunk).hexdigest())
        return session.session_id

    def assertCode(self, expected: str, callback) -> None:
        with self.assertRaises(ValueError) as caught:
            callback()
        self.assertEqual(str(caught.exception), expected)

    def _restore_service(self, payload: bytes, *, failure_injector=None):
        work = Path(self.temporary.name)
        storage = TaskStorage(
            work / "outputs",
            input_root=work / "inputs",
            source_data_root=work / "outputs" / "source-data",
        )
        gallery = GalleryStorage(work / "gallery")
        assets = ReferenceAssetStorage(work / "reference-assets", max_items=50)
        reference_files = ReferenceFileStorage(work / "reference-files")
        planner = TaskBackupPlanner(storage, gallery, assets, reference_files)
        service = HistoryBackupImportService(
            planner,
            self.root,
            max_upload_bytes=len(payload) + 1,
            max_chunk_bytes=64,
            max_entries=32,
            max_member_bytes=64 * 1024,
            max_expanded_bytes=128 * 1024,
            max_compression_ratio=100,
            max_manifest_bytes=32 * 1024,
            min_free_bytes=0,
            free_ratio=0,
            failure_injector=failure_injector,
        )
        return service, planner

    def _recovering_service(self, planner):
        return HistoryBackupImportService(
            planner,
            self.root,
            max_upload_bytes=1024 * 1024,
            max_chunk_bytes=64,
            max_entries=32,
            max_member_bytes=64 * 1024,
            max_expanded_bytes=128 * 1024,
            max_compression_ratio=100,
            max_manifest_bytes=32 * 1024,
            min_free_bytes=0,
            free_ratio=0,
            recover_on_init=False,
        )

    def test_restore_all_roles_and_organization_without_archive_paths(self) -> None:
        payload, binaries = _full_restore_archive()
        service, planner = self._restore_service(payload)
        session_id = self._upload(payload, service=service)
        service.validate(session_id)

        result = service.restore(session_id)

        self.assertEqual([item.task_id for item in result.restored], ["restore-all"])
        self.assertEqual((result.duplicates, result.conflicts, result.invalid, result.failed), ((), (), (), ()))
        metadata = planner.task_storage.read_metadata("restore-all")
        request = json.loads(planner.task_storage.request_path("restore-all").read_text(encoding="utf-8"))
        self.assertNotIn("/archive/", json.dumps({"metadata": metadata, "request": request}))
        serialized = json.dumps({"metadata": metadata, "request": request})
        self.assertNotIn("C:\\\\archive", serialized)
        self.assertNotIn("127.0.0.1", serialized)
        self.assertNotIn("file://", serialized)
        self.assertEqual(metadata["nested"], {"safe": "keep"})
        self.assertEqual(planner.task_storage.output_path(metadata["output_files"][0]).read_bytes(), binaries["output"])
        self.assertEqual(planner.task_storage.input_path(metadata["input_files"][0]).read_bytes(), binaries["input"])
        self.assertEqual(planner.task_storage.input_path(metadata["mask_file"]).read_bytes(), binaries["mask"])
        self.assertEqual(planner.reference_asset_storage.image_path(metadata["reference_assets"][0]["id"]).read_bytes(), binaries["reference_asset"])
        self.assertEqual(planner.gallery_storage.image_path(metadata["gallery_refs"][0]["id"]).read_bytes(), binaries["gallery_reference"])
        reference_record = metadata["reference_files"][0]
        self.assertEqual(reference_record["id"], hashlib.sha256(binaries["reference_file"]).hexdigest())
        self.assertEqual(reference_record["size_bytes"], len(binaries["reference_file"]))
        self.assertEqual(planner.reference_file_storage.file_path(reference_record["id"]).read_bytes(), binaries["reference_file"])
        organization = planner.task_storage.history_organizations(["restore-all"])["restore-all"]
        self.assertTrue(organization.favorite)
        self.assertEqual([tag.name for tag in organization.tags], ["Travel"])
        self.assertNotEqual(organization.tags[0].tag_id, "archive-local-id")
        self.assertIn("restore-all", planner.task_storage.task_index.existing_task_ids(["restore-all"]))
        self.assertEqual(metadata["archived_at"], "2026-08-01T01:00:00Z")
        self.assertTrue(planner.task_storage.output_thumbnail_path("restore-all", 1).is_file())
        refs = request["webui_image_refs"]
        self.assertEqual(refs["reference_assets"], metadata["reference_assets"])
        self.assertEqual(refs["gallery_refs"], metadata["gallery_refs"])
        self.assertEqual(request["webui_file_refs"]["reference_files"], metadata["reference_files"])
        self.assertNotIn("old-asset", json.dumps(request))
        second_session = self._upload(payload, service=service)
        second_preview = service.validate(second_session)
        self.assertEqual([item.task_id for item in second_preview.duplicate], ["restore-all"])

    def test_partial_task_roundtrip_preserves_output_slots_and_selection(self) -> None:
        from codex_image.webui.task_outputs import (
            _retryable_failed_output_indexes,
            _visible_completed_output_records,
        )

        source_root = Path(self.temporary.name) / "source"
        source = TaskStorage(source_root / "outputs", input_root=source_root / "inputs")
        planner = TaskBackupPlanner(
            source, GalleryStorage(source_root / "gallery"),
            ReferenceAssetStorage(source_root / "assets"),
            ReferenceFileStorage(source_root / "files"),
        )
        task_id = source.create_task("generate").task_id
        outputs = [{"index": 1, "status": "failed", "error": "temporary failure"}]
        image_bytes = {2: _png_bytes((255, 0, 0)), 3: _png_bytes((0, 0, 255))}
        for index, data in image_bytes.items():
            path = source.write_output(task_id, data, "png", index=index)
            outputs.append({
                "index": index, "status": "completed", "file": source.output_file(path),
                "revised_prompt": f"image {index}",
            })
        source.write_metadata(task_id, {
            "task_id": task_id, "created_at": "2026-10-07T00:00:00Z",
            "status": "partial_failed", "mode": "generate", "params": {"n": 3},
            "total_count": 3, "generated_count": 2, "failed_count": 1,
            "outputs": outputs, "selected_output_indexes": [3],
        })
        source.write_request(task_id, {"prompt": "roundtrip"})
        planned = planner.plan_task(task_id)
        payload = _archive_bytes(tasks=[asdict(planned.entry)], payloads={
            item.entry.path: item.inline_bytes if item.inline_bytes is not None else item.source_path.read_bytes()
            for item in planned.files
        })
        service, restored_planner = self._restore_service(payload)
        self.addCleanup(service.close)
        session_id = self._upload(payload, service=service)
        service.validate(session_id)
        result = service.restore(session_id)
        self.assertEqual(len(result.restored), 1)
        self.assertFalse(result.failed)
        restored = restored_planner.task_storage.read_metadata(task_id)
        self.assertEqual([(record["index"], record["status"]) for record in restored["outputs"]],
                         [(1, "failed"), (2, "completed"), (3, "completed")])
        self.assertEqual(restored["selected_output_indexes"], [3])
        self.assertEqual(_retryable_failed_output_indexes(restored), [1])
        visible = _visible_completed_output_records(restored)
        self.assertEqual([record["index"] for record in visible], [2, 3])
        for record in visible:
            self.assertEqual(record["revised_prompt"], f"image {record['index']}")
            self.assertEqual(restored_planner.task_storage.output_path(record["file"]).read_bytes(),
                             image_bytes[record["index"]])

    def test_restore_keeps_prompt_and_output_when_all_referenced_inputs_are_absent(self) -> None:
        task_id = "restore-without-inputs"
        output = _png_bytes((32, 96, 160))
        metadata = {
            "task_id": task_id,
            "created_at": "2026-08-01T00:00:00Z",
            "status": "completed",
            "output_files": ["/archive/output.png"],
            "outputs": [{"index": 1, "status": "completed", "file": "/archive/output.png"}],
            "input_files": ["/archive/missing-input.png"],
            "mask_file": "/archive/missing-mask.png",
            "reference_assets": [{"id": "a" * 64, "filename": "missing-asset.png"}],
            "gallery_refs": [{"id": "missing-gallery", "filename": "missing-gallery.png"}],
            "reference_files": [{"id": "b" * 64, "filename": "missing.pdf"}],
        }
        request = {
            "prompt": "prompt must survive",
            "input_files": ["/archive/missing-request-input.png"],
            "mask_file": "/archive/missing-request-mask.png",
            "webui_image_refs": {
                "reference_assets": [{"id": "missing-asset"}],
                "gallery_refs": [{"id": "missing-gallery"}],
            },
            "webui_file_refs": {"reference_files": [{"id": "missing-reference"}]},
        }
        organization = {"favorite": False, "tags": []}
        payloads = {
            f"tasks/{task_id}/source/metadata.json": _json_bytes(metadata),
            f"tasks/{task_id}/source/request.json": _json_bytes(request),
            f"tasks/{task_id}/source/organization.json": _json_bytes(organization),
            f"tasks/{task_id}/outputs/output-0001.png": output,
        }
        roles = ("metadata", "request", "organization", "output")
        entries = tuple(
            BackupFileEntry(
                path=path,
                role=role,
                required=True,
                size_bytes=len(payloads[path]),
                sha256=hashlib.sha256(payloads[path]).hexdigest(),
                source_index=1 if role == "output" else None,
            )
            for path, role in zip(payloads, roles, strict=True)
        )
        task = {
            "task_id": task_id,
            "created_at": metadata["created_at"],
            "fingerprint": canonical_task_fingerprint(metadata, request, entries, organization),
            "files": [asdict(entry) for entry in entries],
        }
        payload = _archive_bytes(tasks=[task], payloads=payloads)
        service, planner = self._restore_service(payload)
        session_id = self._upload(payload, service=service)

        preview = service.validate(session_id)
        result = service.restore(session_id)

        self.assertEqual([item.task_id for item in preview.restorable], [task_id])
        self.assertEqual([item.task_id for item in result.restored], [task_id])
        restored_metadata = planner.task_storage.read_metadata(task_id)
        restored_request = json.loads(
            planner.task_storage.request_path(task_id).read_text(encoding="utf-8")
        )
        self.assertEqual(restored_request["prompt"], "prompt must survive")
        self.assertEqual(restored_metadata["input_files"], [])
        self.assertNotIn("mask_file", restored_metadata)
        self.assertEqual(restored_metadata["reference_assets"], [])
        self.assertEqual(restored_metadata["gallery_refs"], [])
        self.assertEqual(restored_metadata["reference_files"], [])
        self.assertEqual(restored_request["webui_image_refs"]["input_files"], [])
        self.assertEqual(restored_request["webui_image_refs"]["reference_assets"], [])
        self.assertEqual(restored_request["webui_image_refs"]["gallery_refs"], [])
        self.assertEqual(restored_request["webui_file_refs"]["reference_files"], [])
        self.assertEqual(
            planner.task_storage.output_path(restored_metadata["output_files"][0]).read_bytes(),
            output,
        )

    def test_recover_startup_marks_active_interrupted_and_restores_terminal_result(self) -> None:
        payload, _ = _full_restore_archive("recover.result")
        service, planner = self._restore_service(payload)
        active_id = service.create("backup.zip", len(payload)).session_id
        active_status_before = service._status_path(active_id).read_bytes()

        dormant = HistoryBackupImportService(
            planner,
            self.root,
            max_upload_bytes=len(payload) + 1,
            max_chunk_bytes=64,
            min_free_bytes=0,
            free_ratio=0,
            recover_on_init=False,
        )
        self.assertEqual(service._status_path(active_id).read_bytes(), active_status_before)
        self.assertIsNone(dormant.get(active_id))
        with self.assertRaisesRegex(ValueError, "backup_import_lifecycle_conflict"):
            dormant.create("backup.zip", len(payload))
        dormant.recover_startup()
        self.assertEqual(dormant.get(active_id).status, "interrupted")
        self.assertTrue(dormant.cancel(active_id))

        restored_id = self._upload(payload, service=service)
        service.validate(restored_id)
        expected = service.restore(restored_id)
        recovered = HistoryBackupImportService(
            planner,
            self.root,
            max_upload_bytes=len(payload) + 1,
            max_chunk_bytes=64,
            min_free_bytes=0,
            free_ratio=0,
            recover_on_init=False,
        )
        recovered.recover_startup()
        self.assertEqual(recovered.get(restored_id).status, "restored")
        snapshot = recovered.get_snapshot(restored_id)
        self.assertEqual(snapshot.session.status, "restored")
        self.assertEqual(snapshot.result, expected)
        self.assertEqual(recovered.restore(restored_id), expected)
        self.assertEqual([item.task_id for item in expected.restored], ["recover.result"])

    def test_validate_restore_are_single_worker_and_close_rejects_waiter(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        service = self.service

        def slow_validate(_session_id):
            entered.set()
            release.wait(2)
            return "validated"

        service._validate = slow_validate
        service._restore = lambda _session_id: "restored"
        validate_result = []
        restore_errors = []
        first = threading.Thread(target=lambda: validate_result.append(service.validate("a" * 32)))
        first.start()
        self.assertTrue(entered.wait(1))
        def restore_waiter():
            try:
                service.restore("b" * 32)
            except ValueError as exc:
                restore_errors.append(str(exc))

        second = threading.Thread(target=restore_waiter)
        second.start()
        closer = threading.Thread(target=service.close)
        closer.start()
        for _ in range(100):
            if not service._accepting:
                break
            time.sleep(0.001)
        release.set()
        first.join(2)
        second.join(2)
        closer.join(2)
        self.assertEqual(validate_result, ["validated"])
        self.assertEqual(restore_errors, ["backup_import_lifecycle_conflict"])

    def test_close_waits_for_inflight_create_before_returning(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        original = self.service._preflight_capacity

        def blocking(required_bytes):
            entered.set()
            release.wait(2)
            return original(required_bytes)

        self.service._preflight_capacity = blocking
        creator = threading.Thread(target=lambda: self.service.create("backup.zip", 3))
        creator.start()
        self.assertTrue(entered.wait(1))
        closer = threading.Thread(target=self.service.close)
        closer.start()
        for _ in range(100):
            if not self.service._accepting:
                break
            time.sleep(0.001)
        self.assertTrue(closer.is_alive())
        with self.assertRaisesRegex(ValueError, "backup_import_lifecycle_conflict"):
            self.service.create("backup.zip", 3)
        release.set()
        creator.join(2)
        closer.join(2)
        self.assertFalse(closer.is_alive())

    def test_close_waits_for_inflight_append_before_returning(self) -> None:
        session = self.service.create("backup.zip", 3)
        entered = threading.Event()
        release = threading.Event()
        original = self.service._preflight_capacity

        def blocking(required_bytes):
            entered.set()
            release.wait(2)
            return original(required_bytes)

        self.service._preflight_capacity = blocking
        chunk = b"abc"
        appender = threading.Thread(
            target=lambda: self.service.append_chunk(
                session.session_id, 0, chunk, hashlib.sha256(chunk).hexdigest()
            )
        )
        appender.start()
        self.assertTrue(entered.wait(1))
        closer = threading.Thread(target=self.service.close)
        closer.start()
        for _ in range(100):
            if not self.service._accepting:
                break
            time.sleep(0.001)
        self.assertTrue(closer.is_alive())
        release.set()
        appender.join(2)
        closer.join(2)
        self.assertFalse(closer.is_alive())

    def test_failed_terminal_result_is_recovered_and_restore_is_idempotent(self) -> None:
        payload, _ = _full_restore_archive("failed-result")
        service, planner = self._restore_service(
            payload,
            failure_injector=lambda phase: (_ for _ in ()).throw(OSError("metadata"))
            if phase == "after_metadata_write"
            else None,
        )
        session_id = self._upload(payload, service=service)
        service.validate(session_id)
        with mock.patch.object(
            planner.reference_asset_storage,
            "rollback_restore",
            return_value=False,
        ):
            expected = service.restore(session_id)
        self.assertEqual(service.get(session_id).status, "failed")

        recovered = HistoryBackupImportService(
            planner,
            self.root,
            max_upload_bytes=len(payload) + 1,
            max_chunk_bytes=64,
            min_free_bytes=0,
            free_ratio=0,
            recover_on_init=False,
        )
        recovered.recover_startup()

        self.assertEqual(recovered.get(session_id).status, "failed")
        self.assertEqual(recovered.restore(session_id), expected)

    def test_recovery_removes_only_unreferenced_canonical_orphan_staging(self) -> None:
        session_id = "d" * 32
        nonce = "a" * 32
        plain = self.root / f".history-backup-import-task-plain.{nonce}.staging"
        dotted = self.root / f".history-backup-import-task.with.dot.{nonce}.staging"
        referenced = self.root / f".history-backup-import-task-kept.{nonce}.staging"
        unknown = self.root / ".history-backup-import-bad name.staging"
        outside = Path(self.temporary.name) / "outside-staging"
        symlink = self.root / f".history-backup-import-task-link.{nonce}.staging"
        for path in (plain, dotted, referenced, unknown, outside):
            path.mkdir()
            (path / "member.staged").write_bytes(b"x")
        symlink.symlink_to(outside, target_is_directory=True)
        journal = self.root / f"history-backup-import-{session_id}.cleanup.json"
        journal.write_text(json.dumps({
            "session_id": session_id,
            "code": "backup_import_staging_cleanup_incomplete",
            "tasks": [{
                "task_id": "task-kept",
                "pending_staging_paths": [str(referenced / "member.staged")],
            }],
        }), encoding="utf-8")

        dormant = HistoryBackupImportService(
            self.service.planner,
            self.root,
            max_upload_bytes=1024,
            max_chunk_bytes=64,
            min_free_bytes=0,
            free_ratio=0,
            recover_on_init=False,
        )
        dormant.recover_startup()

        self.assertFalse(plain.exists())
        self.assertFalse(dotted.exists())
        self.assertTrue(referenced.exists())
        self.assertTrue(unknown.exists())
        self.assertTrue(symlink.is_symlink())
        self.assertTrue((outside / "member.staged").exists())

    def test_restore_rolls_back_only_new_task_at_each_commit_failure_boundary(self) -> None:
        for phase in ("after_binary_staging", "after_metadata_write", "after_organizer_write"):
            with self.subTest(phase=phase):
                payload, _ = _full_restore_archive(f"rollback-{phase}")
                service, planner = self._restore_service(
                    payload,
                    failure_injector=lambda current, expected=phase: (_ for _ in ()).throw(OSError("injected")) if current == expected else None,
                )
                sentinel = planner.task_storage.input_root / "sentinel.bin"
                sentinel.parent.mkdir(parents=True, exist_ok=True)
                sentinel.write_bytes(b"keep")
                existing_name = f"Existing {phase}"
                tag = planner.task_storage.history_organizer.create_tag(existing_name)
                sentinel_task = f"sentinel-{phase}"
                planner.task_storage.history_organizer.organize([sentinel_task], favorite=True, add_tag_ids=[tag.tag_id])
                session_id = self._upload(payload, service=service)
                service.validate(session_id)

                result = service.restore(session_id)

                task_id = f"rollback-{phase}"
                self.assertEqual([item.task_id for item in result.failed], [task_id])
                self.assertFalse(planner.task_storage.metadata_path(task_id).exists())
                self.assertNotIn(task_id, planner.task_storage.task_index.existing_task_ids([task_id]))
                self.assertEqual(planner.task_storage.history_organizations([task_id])[task_id].tags, ())
                self.assertEqual(planner.reference_asset_storage.list_recent(limit=100), [])
                self.assertEqual(planner.gallery_storage.list_items(), [])
                self.assertEqual(planner.reference_file_storage.list_recent(limit=100), [])
                self.assertEqual(sentinel.read_bytes(), b"keep")
                sentinel_state = planner.task_storage.history_organizations([sentinel_task])[sentinel_task]
                self.assertTrue(sentinel_state.favorite)
                self.assertEqual([item.name for item in sentinel_state.tags], [existing_name])

    def test_restore_thumbnail_failure_is_warning_and_cancel_conflicts_after_commit_starts(self) -> None:
        payload, binaries = _full_restore_archive("warning-task")
        lifecycle_codes: list[str] = []
        service = None
        session_id = ""

        def inject(phase: str) -> None:
            if phase == "after_binary_staging":
                try:
                    assert service is not None
                    service.cancel(session_id)
                except ValueError as exc:
                    lifecycle_codes.append(str(exc))

        service, planner = self._restore_service(payload, failure_injector=inject)
        session_id = self._upload(payload, service=service)
        service.validate(session_id)
        with mock.patch(
            "codex_image.webui.history_backup_import.create_image_thumbnail",
            side_effect=OSError("thumbnail unavailable"),
        ):
            result = service.restore(session_id)

        self.assertEqual(lifecycle_codes, ["backup_import_lifecycle_conflict"])
        self.assertEqual([item.task_id for item in result.restored], ["warning-task"])
        self.assertEqual([item.reason for item in result.thumbnail_warnings], ["backup_import_thumbnail_failed"])
        metadata = planner.task_storage.read_metadata("warning-task")
        self.assertEqual(planner.task_storage.output_path(metadata["output_files"][0]).read_bytes(), binaries["output"])
        self.assertNotIn("/", json.dumps(asdict(result)))

    def test_restore_conflicts_with_preexisting_orphan_organization_without_changing_it(self) -> None:
        payload, _ = _full_restore_archive("orphan-state")
        service, planner = self._restore_service(payload)
        tag = planner.task_storage.history_organizer.create_tag("Keep orphan")
        planner.task_storage.history_organizer.organize(["orphan-state"], favorite=True, add_tag_ids=[tag.tag_id])
        before = planner.task_storage.history_organizations(["orphan-state"])["orphan-state"]
        session_id = self._upload(payload, service=service)
        service.validate(session_id)

        result = service.restore(session_id)

        self.assertEqual([item.reason for item in result.conflicts], ["backup_import_task_organization_conflict"])
        self.assertEqual(planner.task_storage.history_organizations(["orphan-state"])["orphan-state"], before)
        self.assertFalse(planner.task_storage.metadata_path("orphan-state").exists())

    def test_restore_streams_zip_members_without_archive_read(self) -> None:
        payload, _ = _full_restore_archive("streamed-task")
        service, planner = self._restore_service(payload)
        session_id = self._upload(payload, service=service)
        service.validate(session_id)
        with mock.patch.object(zipfile.ZipFile, "read", side_effect=AssertionError("archive.read forbidden")):
            result = service.restore(session_id)
        self.assertEqual([item.task_id for item in result.restored], ["streamed-task"])
        self.assertTrue(planner.task_storage.metadata_path("streamed-task").exists())

    def test_tampered_upload_restore_failure_is_stable_and_not_stuck_restoring(self) -> None:
        payload, _ = _full_restore_archive("tampered-task")
        service, _ = self._restore_service(payload)
        session_id = self._upload(payload, service=service)
        service.validate(session_id)
        upload_path = next(self.root.glob(f"*{session_id}.upload.partial"))
        with upload_path.open("r+b") as target:
            target.seek(0)
            target.write(b"X")
        for _ in range(2):
            self.assertCode("backup_import_upload_state_invalid", lambda: service.restore(session_id))
            state = service.get(session_id)
            self.assertEqual((state.status, state.error_code), ("failed", "backup_import_upload_state_invalid"))

    def test_index_rollback_failure_keeps_cleaning_resources_and_reports_incomplete(self) -> None:
        payload, _ = _full_restore_archive("rollback-incomplete")
        service, planner = self._restore_service(
            payload,
            failure_injector=lambda phase: (_ for _ in ()).throw(OSError("after metadata")) if phase == "after_metadata_write" else None,
        )
        session_id = self._upload(payload, service=service)
        service.validate(session_id)
        with mock.patch.object(planner.task_storage.task_index, "delete", side_effect=OSError("index delete unavailable")):
            result = service.restore(session_id)
        self.assertEqual([item.reason for item in result.failed], ["backup_import_restore_rollback_incomplete"])
        self.assertEqual(planner.reference_asset_storage.list_recent(limit=100), [])
        self.assertEqual(planner.gallery_storage.list_items(), [])
        self.assertEqual(planner.reference_file_storage.list_recent(limit=100), [])
        journal_path = next(self.root.glob(f"*{session_id}.rollback.json"))
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        self.assertEqual(journal["tasks"][0]["pending_paths"], [])
        self.assertTrue(journal["tasks"][0]["index_pending"])
        self.assertEqual(
            (service.get(session_id).status, service.get(session_id).error_code),
            ("failed", "backup_import_restore_rollback_incomplete"),
        )

    def test_failure_does_not_delete_unrelated_tag_created_during_restore(self) -> None:
        payload, _ = _full_restore_archive("concurrent-tag-task")
        created_tag_ids: list[str] = []
        planner = None

        def inject(phase: str) -> None:
            if phase == "after_metadata_write":
                assert planner is not None
                created_tag_ids.append(
                    planner.task_storage.history_organizer.create_tag("Concurrent orphan").tag_id
                )
                raise OSError("injected")

        service, planner = self._restore_service(payload, failure_injector=inject)
        session_id = self._upload(payload, service=service)
        service.validate(session_id)
        result = service.restore(session_id)
        self.assertEqual([item.task_id for item in result.failed], ["concurrent-tag-task"])
        tags = {tag.tag_id: tag.name for tag in planner.task_storage.history_organizer.list_tags()}
        self.assertEqual({tag_id: tags[tag_id] for tag_id in created_tag_ids}, {created_tag_ids[0]: "Concurrent orphan"})

    def test_after_binary_staging_gallery_update_survives_restore_rollback(self) -> None:
        payload, _ = _full_restore_archive("gallery-concurrent-update")
        planner = None

        def inject(phase: str) -> None:
            if phase != "after_binary_staging":
                return
            assert planner is not None
            item = planner.gallery_storage.list_items()[0]
            planner.gallery_storage.update_item(
                str(item["id"]), prompt_note="concurrent prompt"
            )
            raise OSError("injected after concurrent update")

        service, planner = self._restore_service(payload, failure_injector=inject)
        session_id = self._upload(payload, service=service)
        service.validate(session_id)

        result = service.restore(session_id)

        self.assertEqual([item.task_id for item in result.failed], ["gallery-concurrent-update"])
        remaining = planner.gallery_storage.list_items()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["prompt_note"], "concurrent prompt")

    def test_resource_rollback_failure_is_recorded_as_exact_pending_handle(self) -> None:
        payload, _ = _full_restore_archive("resource-pending")
        service, planner = self._restore_service(
            payload,
            failure_injector=lambda phase: (_ for _ in ()).throw(OSError("metadata"))
            if phase == "after_metadata_write"
            else None,
        )
        session_id = self._upload(payload, service=service)
        service.validate(session_id)

        with mock.patch.object(
            planner.reference_asset_storage,
            "rollback_restore",
            side_effect=OSError("asset rollback unavailable"),
        ):
            result = service.restore(session_id)

        self.assertEqual(
            [item.reason for item in result.failed],
            ["backup_import_restore_rollback_incomplete"],
        )
        journal_path = next(self.root.glob(f"*{session_id}.rollback.json"))
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        pending = journal["tasks"][0]["pending_resources"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["kind"], "reference_asset")
        self.assertTrue(pending[0]["created"])
        self.assertIsInstance(pending[0]["version"], int)
        self.assertEqual(pending[0]["id"], hashlib.sha256(_png_bytes((0, 0, 255))).hexdigest())

    def test_resource_deleted_before_rollback_error_is_not_recorded_pending(self) -> None:
        payload, _ = _full_restore_archive("resource-cleared")
        service, planner = self._restore_service(
            payload,
            failure_injector=lambda phase: (_ for _ in ()).throw(OSError("metadata"))
            if phase == "after_metadata_write"
            else None,
        )
        session_id = self._upload(payload, service=service)
        service.validate(session_id)
        original_rollback = planner.reference_asset_storage.rollback_restore

        def delete_then_raise(handle):
            original_rollback(handle)
            raise OSError("reported after delete")

        with mock.patch.object(
            planner.reference_asset_storage,
            "rollback_restore",
            side_effect=delete_then_raise,
        ):
            result = service.restore(session_id)

        self.assertEqual([item.reason for item in result.failed], ["backup_import_restore_failed"])
        self.assertFalse(any(self.root.glob(f"*{session_id}.rollback.json")))

    def test_resource_rollback_false_with_unchanged_identity_is_pending(self) -> None:
        payload, _ = _full_restore_archive("resource-false-pending")
        service, planner = self._restore_service(
            payload,
            failure_injector=lambda phase: (_ for _ in ()).throw(OSError("metadata"))
            if phase == "after_metadata_write"
            else None,
        )
        session_id = self._upload(payload, service=service)
        service.validate(session_id)

        with mock.patch.object(
            planner.reference_asset_storage,
            "rollback_restore",
            return_value=False,
        ):
            result = service.restore(session_id)

        self.assertEqual(
            [item.reason for item in result.failed],
            ["backup_import_restore_rollback_incomplete"],
        )
        journal_path = next(self.root.glob(f"*{session_id}.rollback.json"))
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [item["kind"] for item in journal["tasks"][0]["pending_resources"]],
            ["reference_asset"],
        )

    def test_gallery_false_rollback_after_category_rename_is_reported_pending(self) -> None:
        payload, _ = _full_restore_archive("gallery-derived-pending")
        planner = None

        def inject(phase: str) -> None:
            if phase != "after_binary_staging":
                return
            assert planner is not None
            planner.gallery_storage.update_category(
                "portrait",
                name="Renamed category",
                prompt_role="Changed derived role",
            )
            raise OSError("task failure")

        service, planner = self._restore_service(payload, failure_injector=inject)
        session_id = self._upload(payload, service=service)
        service.validate(session_id)

        with mock.patch.object(
            planner.gallery_storage,
            "rollback_restore",
            return_value=False,
        ):
            result = service.restore(session_id)

        self.assertEqual(
            [item.reason for item in result.failed],
            ["backup_import_restore_rollback_incomplete"],
        )
        journal_path = next(self.root.glob(f"*{session_id}.rollback.json"))
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [item["kind"] for item in journal["tasks"][0]["pending_resources"]],
            ["gallery"],
        )

    def test_rollback_journal_write_failure_has_stable_failed_lifecycle(self) -> None:
        payload, _ = _full_restore_archive("journal-write-failure")
        service, planner = self._restore_service(
            payload,
            failure_injector=lambda phase: (_ for _ in ()).throw(OSError("metadata"))
            if phase == "after_metadata_write"
            else None,
        )
        session_id = self._upload(payload, service=service)
        service.validate(session_id)

        with mock.patch.object(
            planner.task_storage.task_index,
            "delete",
            side_effect=OSError("index pending"),
        ), mock.patch.object(
            service,
            "_write_rollback_journal",
            side_effect=OSError("journal unavailable"),
        ):
            self.assertCode(
                "backup_import_restore_rollback_incomplete",
                lambda: service.restore(session_id),
            )

        self.assertEqual(
            (service.get(session_id).status, service.get(session_id).error_code),
            ("failed", "backup_import_restore_rollback_incomplete"),
        )
        self.assertCode(
            "backup_import_restore_rollback_incomplete",
            lambda: service.restore(session_id),
        )
        self.assertCode("backup_import_lifecycle_conflict", lambda: service.cancel(session_id))

    def test_committed_task_stays_restored_when_staging_cleanup_is_incomplete(self) -> None:
        payload, _ = _full_restore_archive("cleanup-warning")
        service, planner = self._restore_service(payload)
        session_id = self._upload(payload, service=service)
        service.validate(session_id)
        original_unlink = Path.unlink

        def fail_staged(path: Path, *args, **kwargs):
            if path.name == "member-0000.staged":
                raise OSError("staging cleanup unavailable")
            return original_unlink(path, *args, **kwargs)

        with mock.patch.object(Path, "unlink", autospec=True, side_effect=fail_staged):
            result = service.restore(session_id)

        self.assertEqual([item.task_id for item in result.restored], ["cleanup-warning"])
        self.assertEqual(
            [item.reason for item in result.cleanup_warnings],
            ["backup_import_staging_cleanup_incomplete"],
        )
        self.assertEqual(service.get(session_id).status, "restored")
        self.assertTrue(planner.task_storage.metadata_path("cleanup-warning").exists())
        self.assertIn(
            "cleanup-warning",
            planner.task_storage.task_index.existing_task_ids(["cleanup-warning"]),
        )
        organization = planner.task_storage.history_organizations(["cleanup-warning"])["cleanup-warning"]
        self.assertTrue(organization.favorite)
        cleanup_path = next(self.root.glob(f"*{session_id}.cleanup.json"))
        cleanup = json.loads(cleanup_path.read_text(encoding="utf-8"))
        self.assertEqual(len(cleanup["tasks"][0]["pending_staging_paths"]), 1)
        self.assertTrue(cleanup["tasks"][0]["pending_staging_paths"][0].endswith("member-0000.staged"))

    def test_startup_replays_cleanup_journal_and_removes_it_only_after_success(self) -> None:
        payload, _ = _full_restore_archive("replay-cleanup")
        _, planner = self._restore_service(payload)
        session_id = "1" * 32
        staging = self.root / f".history-backup-import-task-a.{'2' * 32}.staging"
        staging.mkdir()
        pending = staging / "member-0000.staged"
        pending.write_bytes(b"pending")
        journal = self.root / f"history-backup-import-{session_id}.cleanup.json"
        journal.write_text(json.dumps({
            "session_id": session_id,
            "tasks": [{"task_id": "task-a", "pending_staging_paths": [str(pending)]}],
            "code": "backup_import_staging_cleanup_incomplete",
        }), encoding="utf-8")

        self._recovering_service(planner).recover_startup()

        self.assertFalse(pending.exists())
        self.assertFalse(staging.exists())
        self.assertFalse(journal.exists())

    def test_startup_rollback_replay_persists_partial_failure_for_retry(self) -> None:
        payload, _ = _full_restore_archive("replay-rollback")
        _, planner = self._restore_service(payload)
        session_id = "3" * 32
        restore_token = "a" * 32
        planner.task_storage._write_restore_ownership("task-a", restore_token)
        journal = self.root / f"history-backup-import-{session_id}.rollback.json"
        journal.write_text(json.dumps({
            "session_id": session_id,
            "tasks": [{
                "task_id": "task-a", "restore_token": restore_token,
                "pending_paths": [], "index_pending": True,
                "pending_resources": [], "pending_staging_paths": [],
                "organization_pending": False, "ownership_pending": True,
            }],
            "code": "backup_import_restore_rollback_incomplete",
        }), encoding="utf-8")
        with mock.patch.object(planner.task_storage.task_index, "delete", side_effect=OSError("busy")):
            self._recovering_service(planner).recover_startup()
        self.assertTrue(journal.exists())
        remaining = json.loads(journal.read_text(encoding="utf-8"))
        self.assertTrue(remaining["tasks"][0]["index_pending"])

        self._recovering_service(planner).recover_startup()
        self.assertFalse(journal.exists())

    def test_startup_replay_fails_closed_for_out_of_root_path(self) -> None:
        payload_bytes, _ = _full_restore_archive("replay-hostile")
        _, planner = self._restore_service(payload_bytes)
        session_id = "4" * 32
        restore_token = "b" * 32
        planner.task_storage._write_restore_ownership("task-a", restore_token)
        outside = Path(self.temporary.name) / "must-survive.txt"
        outside.write_text("keep", encoding="utf-8")
        journal = self.root / f"history-backup-import-{session_id}.rollback.json"
        payload = {
            "session_id": session_id,
            "tasks": [{
                "task_id": "task-a", "restore_token": restore_token,
                "pending_paths": [str(outside)], "index_pending": False,
                "pending_resources": [], "pending_staging_paths": [],
                "organization_pending": False, "ownership_pending": True,
            }],
            "code": "backup_import_restore_rollback_incomplete",
        }
        journal.write_text(json.dumps(payload), encoding="utf-8")

        self._recovering_service(planner).recover_startup()

        self.assertEqual(outside.read_text(encoding="utf-8"), "keep")
        self.assertEqual(json.loads(journal.read_text(encoding="utf-8")), payload)

    def test_startup_replay_rejects_symlink_parent_and_preserves_external_file(self) -> None:
        payload_bytes, _ = _full_restore_archive("replay-symlink-parent")
        _, planner = self._restore_service(payload_bytes)
        session_id = "7" * 32
        restore_token = "e" * 32
        planner.task_storage._write_restore_ownership("task-a", restore_token)
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        external = outside / "task-a-image-1.png"
        external.write_bytes(b"keep")
        link = planner.task_storage.output_root / "linked-parent"
        link.symlink_to(outside, target_is_directory=True)
        journal = self.root / f"history-backup-import-{session_id}.rollback.json"
        journal.write_text(json.dumps({
            "session_id": session_id,
            "tasks": [{
                "task_id": "task-a", "restore_token": restore_token,
                "pending_paths": [str(link / external.name)], "index_pending": False,
                "pending_resources": [], "pending_staging_paths": [],
                "organization_pending": False, "ownership_pending": True,
            }],
            "code": "backup_import_restore_rollback_incomplete",
        }), encoding="utf-8")

        self._recovering_service(planner).recover_startup()

        self.assertEqual(external.read_bytes(), b"keep")
        self.assertTrue(journal.exists())

    def test_old_index_rollback_journal_cannot_delete_new_same_id_restore(self) -> None:
        payload_bytes, _ = _full_restore_archive("replay-index-cas")
        _, planner = self._restore_service(payload_bytes)
        session_id = "8" * 32
        old_token = "f" * 32
        planner.task_storage._write_restore_ownership("task-a", old_token)
        journal = self.root / f"history-backup-import-{session_id}.rollback.json"
        journal.write_text(json.dumps({
            "session_id": session_id,
            "tasks": [{
                "task_id": "task-a", "restore_token": old_token,
                "pending_paths": [], "index_pending": True,
                "pending_resources": [], "pending_staging_paths": [],
                "organization_pending": False, "ownership_pending": True,
            }],
            "code": "backup_import_restore_rollback_incomplete",
        }), encoding="utf-8")
        planner.task_storage.task_index.upsert({
            "task_id": "task-a", "created_at": "2026-08-01T00:00:00Z", "status": "completed",
        })
        planner.task_storage._write_restore_ownership("task-a", "0" * 32)

        self._recovering_service(planner).recover_startup()

        self.assertEqual(planner.task_storage.task_index.existing_task_ids(["task-a"]), {"task-a"})
        self.assertTrue(journal.exists())

    def test_old_organization_rollback_journal_cannot_delete_new_same_id_update(self) -> None:
        payload_bytes, _ = _full_restore_archive("replay-organization-cas")
        _, planner = self._restore_service(payload_bytes)
        session_id = "9" * 32
        old_token = "1" * 32
        planner.task_storage._write_restore_ownership("task-a", old_token)
        journal = self.root / f"history-backup-import-{session_id}.rollback.json"
        journal.write_text(json.dumps({
            "session_id": session_id,
            "tasks": [{
                "task_id": "task-a", "restore_token": old_token,
                "pending_paths": [], "index_pending": False,
                "pending_resources": [], "pending_staging_paths": [],
                "organization_pending": True, "ownership_pending": True,
            }],
            "code": "backup_import_restore_rollback_incomplete",
        }), encoding="utf-8")
        planner.task_storage.history_organizer.restore_task_organization(
            "task-a", True, ["New state"]
        )
        planner.task_storage._write_restore_ownership("task-a", "2" * 32)

        self._recovering_service(planner).recover_startup()

        organization = planner.task_storage.history_organizations(["task-a"])["task-a"]
        self.assertTrue(organization.favorite)
        self.assertEqual([tag.name for tag in organization.tags], ["New state"])
        self.assertTrue(journal.exists())

    def test_startup_resource_replay_requires_exact_restore_identity(self) -> None:
        payload_bytes, _ = _full_restore_archive("replay-resource")
        _, planner = self._restore_service(payload_bytes)
        session_id = "5" * 32
        data = _png_bytes((20, 40, 60))
        handle = planner.reference_asset_storage.restore_content("asset.png", data, "image/png")
        task_token = "c" * 32
        planner.task_storage._write_restore_ownership("task-a", task_token)
        resource = {
            "kind": "reference_asset", "id": handle.record["id"],
            "created": True, "version": handle.version, "record": handle.record,
            "restore_token": handle.restore_token,
        }

        def write_journal() -> Path:
            journal_path = self.root / f"history-backup-import-{session_id}.rollback.json"
            journal_path.write_text(json.dumps({
                "session_id": session_id,
                "tasks": [{
                    "task_id": "task-a", "restore_token": task_token,
                    "pending_paths": [], "index_pending": False,
                    "pending_resources": [resource], "pending_staging_paths": [],
                    "organization_pending": False, "ownership_pending": True,
                }],
                "code": "backup_import_restore_rollback_incomplete",
            }), encoding="utf-8")
            return journal_path

        journal = write_journal()
        planner.reference_asset_storage.delete_item(handle.record["id"])
        recreated = planner.reference_asset_storage.restore_content("asset.png", data, "image/png")
        self.assertEqual(recreated.record["id"], handle.record["id"])
        self.assertNotEqual(recreated.restore_token, handle.restore_token)
        cold_planner = TaskBackupPlanner(
            TaskStorage(
                planner.task_storage.output_root,
                input_root=planner.task_storage.input_root,
                source_data_root=planner.task_storage.source_data_root,
            ),
            GalleryStorage(planner.gallery_storage.root),
            ReferenceAssetStorage(planner.reference_asset_storage.root, max_items=50),
            ReferenceFileStorage(planner.reference_file_storage.root),
        )
        self._recovering_service(cold_planner).recover_startup()
        self.assertTrue(cold_planner.reference_asset_storage.read_item(handle.record["id"]))
        self.assertFalse(journal.exists())

    def test_existing_resource_restore_handles_do_not_claim_persistent_ownership(self) -> None:
        payload_bytes, _ = _full_restore_archive("existing-resource-ownership")
        _, planner = self._restore_service(payload_bytes)
        image = _png_bytes((31, 62, 93))
        first_asset = planner.reference_asset_storage.restore_content("asset.png", image, "image/png")
        reused_asset = planner.reference_asset_storage.restore_content("asset.png", image, "image/png")
        first_gallery = planner.gallery_storage.restore_content(
            "Pose", "portrait", "pose.png", image, "image/png"
        )
        reused_gallery = planner.gallery_storage.restore_content(
            "Pose", "portrait", "pose.png", image, "image/png"
        )
        reference = validate_reference_file("notes.txt", b"existing", "text/plain")
        first_file = planner.reference_file_storage.restore_validated(reference)
        reused_file = planner.reference_file_storage.restore_validated(reference)

        self.assertTrue(first_asset.created and first_gallery.created and first_file.created)
        for handle in (reused_asset, reused_gallery, reused_file):
            self.assertFalse(handle.created)
            self.assertIsNone(handle.restore_token)
        self.assertFalse(
            planner.reference_asset_storage._restore_token_path(first_asset.record["id"]).exists()
        )
        self.assertFalse(
            planner.gallery_storage._restore_token_path(first_gallery.record["id"]).exists()
        )
        self.assertFalse(
            planner.reference_file_storage._restore_token_path(first_file.record["id"]).exists()
        )

    def test_successful_restore_releases_all_task_and_resource_owners(self) -> None:
        payload, _ = _full_restore_archive("committed-owner-release")
        service, planner = self._restore_service(payload)
        session_id = self._upload(payload, service=service)
        service.validate(session_id)

        result = service.restore(session_id)

        self.assertEqual([item.task_id for item in result.restored], ["committed-owner-release"])
        metadata = planner.task_storage.read_metadata("committed-owner-release")
        self.assertFalse(planner.task_storage.restore_ownership_path("committed-owner-release").exists())
        self.assertFalse(
            planner.reference_asset_storage._restore_token_path(metadata["reference_assets"][0]["id"]).exists()
        )
        self.assertFalse(
            planner.gallery_storage._restore_token_path(metadata["gallery_refs"][0]["id"]).exists()
        )
        self.assertFalse(
            planner.reference_file_storage._restore_token_path(metadata["reference_files"][0]["id"]).exists()
        )

    def test_committed_owner_cleanup_failure_retries_without_rollback_and_normal_reuse_is_safe(self) -> None:
        payload, binaries = _full_restore_archive("committed-cleanup-retry")
        service, planner = self._restore_service(payload)
        session_id = self._upload(payload, service=service)
        service.validate(session_id)

        with mock.patch.object(
            planner.reference_asset_storage,
            "release_restore_ownership",
            return_value=False,
        ), mock.patch.object(
            planner.gallery_storage,
            "release_restore_ownership",
            return_value=False,
        ):
            result = service.restore(session_id)

        self.assertEqual([item.task_id for item in result.restored], ["committed-cleanup-retry"])
        metadata = planner.task_storage.read_metadata("committed-cleanup-retry")
        journal = self.root / f"history-backup-import-{session_id}.ownership.json"
        self.assertTrue(journal.exists())
        self.assertTrue(planner.task_storage.metadata_path("committed-cleanup-retry").exists())
        asset_id = metadata["reference_assets"][0]["id"]
        gallery_id = metadata["gallery_refs"][0]["id"]
        planner.reference_asset_storage.create_or_touch(
            "portrait.png", binaries["reference_asset"], "image/png"
        )
        cold_planner = TaskBackupPlanner(
            TaskStorage(
                planner.task_storage.output_root,
                input_root=planner.task_storage.input_root,
                source_data_root=planner.task_storage.source_data_root,
            ),
            GalleryStorage(planner.gallery_storage.root),
            ReferenceAssetStorage(planner.reference_asset_storage.root, max_items=50),
            ReferenceFileStorage(planner.reference_file_storage.root),
        )

        self._recovering_service(cold_planner).recover_startup()
        self.assertTrue(cold_planner.task_storage.metadata_path("committed-cleanup-retry").exists())
        self.assertEqual(cold_planner.reference_asset_storage.read_item(asset_id)["id"], asset_id)
        self.assertEqual(cold_planner.gallery_storage.read_item(gallery_id)["id"], gallery_id)
        self.assertFalse(journal.exists())
        self.assertFalse(cold_planner.reference_asset_storage._restore_token_path(asset_id).exists())
        self.assertFalse(cold_planner.gallery_storage._restore_token_path(gallery_id).exists())

    def test_owner_cleanup_journal_write_failure_returns_stable_warning_without_rollback(self) -> None:
        payload, _ = _full_restore_archive("committed-cleanup-warning")
        service, planner = self._restore_service(payload)
        session_id = self._upload(payload, service=service)
        service.validate(session_id)

        with mock.patch.object(
            planner.reference_asset_storage,
            "release_restore_ownership",
            return_value=False,
        ), mock.patch.object(
            service,
            "_write_ownership_cleanup_journal",
            side_effect=OSError("private detail must not escape"),
        ):
            result = service.restore(session_id)

        self.assertEqual([item.task_id for item in result.restored], ["committed-cleanup-warning"])
        self.assertEqual(
            [item.reason for item in result.cleanup_warnings],
            ["backup_import_restore_owner_cleanup_incomplete"],
        )
        self.assertTrue(planner.task_storage.metadata_path("committed-cleanup-warning").exists())
        self.assertFalse(any(self.root.glob(f"*{session_id}.rollback.json")))

    def test_normal_asset_and_reference_file_reuse_invalidates_old_rollback_after_cold_restart(self) -> None:
        payload_bytes, _ = _full_restore_archive("normal-resource-reuse")
        _, planner = self._restore_service(payload_bytes)
        image = _png_bytes((71, 72, 73))
        asset_handle = planner.reference_asset_storage.restore_content("asset.png", image, "image/png")
        reference = validate_reference_file("notes.txt", b"normal reuse", "text/plain")
        file_handle = planner.reference_file_storage.restore_validated(reference)
        task_token = "7" * 32
        planner.task_storage._write_restore_ownership("failed-restore", task_token)
        session_id = "e" * 32
        journal = self.root / f"history-backup-import-{session_id}.rollback.json"
        resources = [
            {
                "kind": "reference_asset", "id": asset_handle.record["id"],
                "created": True, "version": asset_handle.version,
                "record": asset_handle.record, "restore_token": asset_handle.restore_token,
            },
            {
                "kind": "reference_file", "id": file_handle.record["id"],
                "created": True, "version": file_handle.version,
                "record": file_handle.record, "restore_token": file_handle.restore_token,
            },
        ]
        journal.write_text(json.dumps({
            "session_id": session_id,
            "tasks": [{
                "task_id": "failed-restore", "restore_token": task_token,
                "pending_paths": [], "index_pending": False,
                "pending_resources": resources, "pending_staging_paths": [],
                "organization_pending": False, "ownership_pending": True,
            }],
            "code": "backup_import_restore_rollback_incomplete",
        }), encoding="utf-8")
        planner.reference_asset_storage.create_or_touch("asset.png", image, "image/png")
        planner.reference_file_storage.create_or_touch(reference)
        cold_planner = TaskBackupPlanner(
            TaskStorage(
                planner.task_storage.output_root,
                input_root=planner.task_storage.input_root,
                source_data_root=planner.task_storage.source_data_root,
            ),
            GalleryStorage(planner.gallery_storage.root),
            ReferenceAssetStorage(planner.reference_asset_storage.root, max_items=50),
            ReferenceFileStorage(planner.reference_file_storage.root),
        )

        with mock.patch.object(
            cold_planner.task_storage,
            "resource_reference_snapshot",
            wraps=cold_planner.task_storage.resource_reference_snapshot,
        ) as scan:
            self._recovering_service(cold_planner).recover_startup()

        self.assertEqual(scan.call_count, 1)
        self.assertEqual(cold_planner.reference_asset_storage.read_item(asset_handle.record["id"])["id"], asset_handle.record["id"])
        self.assertEqual(cold_planner.reference_file_storage.read_item(file_handle.record["id"])["id"], file_handle.record["id"])
        self.assertFalse(journal.exists())

    def test_rollback_replay_preserves_all_resource_types_referenced_by_new_task(self) -> None:
        payload_bytes, _ = _full_restore_archive("gallery-reference-guard")
        _, planner = self._restore_service(payload_bytes)
        data = _png_bytes((44, 55, 66))
        gallery_handle = planner.gallery_storage.restore_content(
            "Guarded pose", "portrait", "pose.png", data, "image/png"
        )
        asset_handle = planner.reference_asset_storage.restore_content(
            "guarded.png", data, "image/png"
        )
        reference = validate_reference_file("guarded.txt", b"guarded", "text/plain")
        file_handle = planner.reference_file_storage.restore_validated(reference)
        task_token = "6" * 32
        planner.task_storage._write_restore_ownership("failed-restore", task_token)
        planner.task_storage.write_metadata("new-task", {
            "task_id": "new-task", "created_at": "2026-08-01T00:00:00Z",
            "status": "completed",
            "gallery_refs": [{"id": gallery_handle.record["id"]}],
            "reference_assets": [{"id": asset_handle.record["id"]}],
            "reference_files": [{"id": file_handle.record["id"]}],
        })
        session_id = "d" * 32
        journal = self.root / f"history-backup-import-{session_id}.rollback.json"
        journal.write_text(json.dumps({
            "session_id": session_id,
            "tasks": [{
                "task_id": "failed-restore", "restore_token": task_token,
                "pending_paths": [], "index_pending": False,
                "pending_resources": [
                    {
                        "kind": "gallery", "id": gallery_handle.record["id"],
                        "created": True, "version": gallery_handle.version,
                        "record": gallery_handle.record,
                        "restore_token": gallery_handle.restore_token,
                    },
                    {
                        "kind": "reference_asset", "id": asset_handle.record["id"],
                        "created": True, "version": asset_handle.version,
                        "record": asset_handle.record,
                        "restore_token": asset_handle.restore_token,
                    },
                    {
                        "kind": "reference_file", "id": file_handle.record["id"],
                        "created": True, "version": file_handle.version,
                        "record": file_handle.record,
                        "restore_token": file_handle.restore_token,
                    },
                ],
                "pending_staging_paths": [], "organization_pending": False,
                "ownership_pending": True,
            }],
            "code": "backup_import_restore_rollback_incomplete",
        }), encoding="utf-8")
        cold_planner = TaskBackupPlanner(
            TaskStorage(
                planner.task_storage.output_root,
                input_root=planner.task_storage.input_root,
                source_data_root=planner.task_storage.source_data_root,
            ),
            GalleryStorage(planner.gallery_storage.root),
            ReferenceAssetStorage(planner.reference_asset_storage.root, max_items=50),
            ReferenceFileStorage(planner.reference_file_storage.root),
        )

        self._recovering_service(cold_planner).recover_startup()

        self.assertEqual(
            cold_planner.gallery_storage.read_item(gallery_handle.record["id"])["id"],
            gallery_handle.record["id"],
        )
        self.assertEqual(
            cold_planner.reference_asset_storage.read_item(asset_handle.record["id"])["id"],
            asset_handle.record["id"],
        )
        self.assertEqual(
            cold_planner.reference_file_storage.read_item(file_handle.record["id"])["id"],
            file_handle.record["id"],
        )
        self.assertFalse(
            cold_planner.gallery_storage._restore_token_path(gallery_handle.record["id"]).exists()
        )
        self.assertFalse(
            cold_planner.reference_asset_storage._restore_token_path(asset_handle.record["id"]).exists()
        )
        self.assertFalse(
            cold_planner.reference_file_storage._restore_token_path(file_handle.record["id"]).exists()
        )
        self.assertFalse(journal.exists())

    def test_referenced_resource_owner_release_failure_retains_rollback_for_retry(self) -> None:
        payload_bytes, _ = _full_restore_archive("reference-release-retry")
        _, planner = self._restore_service(payload_bytes)
        data = _png_bytes((91, 92, 93))
        handle = planner.reference_asset_storage.restore_content("guarded.png", data, "image/png")
        planner.task_storage.write_metadata("new-task", {
            "task_id": "new-task", "created_at": "2026-08-01T00:00:00Z",
            "status": "completed", "reference_assets": [{"id": handle.record["id"]}],
        })
        task_token = "8" * 32
        planner.task_storage._write_restore_ownership("failed-restore", task_token)
        session_id = "f" * 32
        journal = self.root / f"history-backup-import-{session_id}.rollback.json"
        journal.write_text(json.dumps({
            "session_id": session_id,
            "tasks": [{
                "task_id": "failed-restore", "restore_token": task_token,
                "pending_paths": [], "index_pending": False,
                "pending_resources": [{
                    "kind": "reference_asset", "id": handle.record["id"],
                    "created": True, "version": handle.version,
                    "record": handle.record, "restore_token": handle.restore_token,
                }],
                "pending_staging_paths": [], "organization_pending": False,
                "ownership_pending": True,
            }],
            "code": "backup_import_restore_rollback_incomplete",
        }), encoding="utf-8")
        recovering = self._recovering_service(planner)
        with mock.patch.object(
            planner.reference_asset_storage,
            "release_restore_ownership",
            return_value=False,
        ):
            recovering.recover_startup()
        self.assertTrue(journal.exists())
        self.assertEqual(planner.reference_asset_storage.read_item(handle.record["id"])["id"], handle.record["id"])

        self._recovering_service(planner).recover_startup()
        self.assertFalse(journal.exists())
        self.assertFalse(planner.reference_asset_storage._restore_token_path(handle.record["id"]).exists())
        self.assertEqual(planner.reference_asset_storage.read_item(handle.record["id"])["id"], handle.record["id"])

    def test_resource_reference_scan_rejects_date_shard_symlink_and_preserves_rollback(self) -> None:
        payload_bytes, _ = _full_restore_archive("reference-symlink-guard")
        _, planner = self._restore_service(payload_bytes)
        data = _png_bytes((101, 102, 103))
        handle = planner.reference_asset_storage.restore_content("guarded.png", data, "image/png")
        external = Path(self.temporary.name) / "external-metadata"
        external.mkdir()
        (external / "outside.metadata.json").write_text(json.dumps({
            "task_id": "outside", "reference_assets": [],
        }), encoding="utf-8")
        tasks_root = planner.task_storage.source_data_root / "tasks"
        tasks_root.mkdir(parents=True, exist_ok=True)
        (tasks_root / "2026-08-01").symlink_to(external, target_is_directory=True)
        task_token = "9" * 32
        planner.task_storage._write_restore_ownership("failed-restore", task_token)
        session_id = "0" * 32
        journal = self.root / f"history-backup-import-{session_id}.rollback.json"
        journal.write_text(json.dumps({
            "session_id": session_id,
            "tasks": [{
                "task_id": "failed-restore", "restore_token": task_token,
                "pending_paths": [], "index_pending": False,
                "pending_resources": [{
                    "kind": "reference_asset", "id": handle.record["id"],
                    "created": True, "version": handle.version,
                    "record": handle.record, "restore_token": handle.restore_token,
                }],
                "pending_staging_paths": [], "organization_pending": False,
                "ownership_pending": True,
            }],
            "code": "backup_import_restore_rollback_incomplete",
        }), encoding="utf-8")

        self._recovering_service(planner).recover_startup()

        self.assertEqual(planner.reference_asset_storage.read_item(handle.record["id"])["id"], handle.record["id"])
        self.assertTrue(journal.exists())

    def test_source_data_binding_swap_during_descriptor_scan_fails_closed(self) -> None:
        for variant, session_char in (("parent", "1"), ("root", "2")):
            with self.subTest(variant=variant):
                base = Path(self.temporary.name) / f"binding-{variant}"
                real_parent = base / "real-parent"
                alternate_parent = base / "alternate-parent"
                real_source = real_parent / "source-data"
                alternate_source = alternate_parent / "source-data"
                real_source.mkdir(parents=True)
                alternate_source.mkdir(parents=True)
                if variant == "parent":
                    configured_link = base / "configured-parent"
                    configured_link.symlink_to(real_parent, target_is_directory=True)
                    configured_source = configured_link / "source-data"
                    swap_target = alternate_parent
                else:
                    configured_link = base / "configured-source-data"
                    configured_link.symlink_to(real_source, target_is_directory=True)
                    configured_source = configured_link
                    swap_target = alternate_source
                storage = TaskStorage(
                    base / "outputs",
                    input_root=base / "inputs",
                    source_data_root=configured_source,
                )
                gallery = GalleryStorage(base / "gallery")
                assets = ReferenceAssetStorage(base / "assets", max_items=50)
                files = ReferenceFileStorage(base / "reference-files")
                planner = TaskBackupPlanner(storage, gallery, assets, files)
                data = _png_bytes((111, 112, 113))
                handle = assets.restore_content("guarded.png", data, "image/png")
                task_token = session_char * 32
                storage._write_restore_ownership("failed-restore", task_token)
                session_id = session_char * 32
                journal = self.root / f"history-backup-import-{session_id}.rollback.json"
                journal.write_text(json.dumps({
                    "session_id": session_id,
                    "tasks": [{
                        "task_id": "failed-restore", "restore_token": task_token,
                        "pending_paths": [], "index_pending": False,
                        "pending_resources": [{
                            "kind": "reference_asset", "id": handle.record["id"],
                            "created": True, "version": handle.version,
                            "record": handle.record, "restore_token": handle.restore_token,
                        }],
                        "pending_staging_paths": [], "organization_pending": False,
                        "ownership_pending": True,
                    }],
                    "code": "backup_import_restore_rollback_incomplete",
                }), encoding="utf-8")
                original_scandir = os.scandir
                swapped = False

                def swap_binding_then_scan(path):
                    nonlocal swapped
                    if not swapped:
                        swapped = True
                        configured_link.unlink()
                        configured_link.symlink_to(swap_target, target_is_directory=True)
                    return original_scandir(path)

                with mock.patch(
                    "codex_image.webui.storage.os.scandir",
                    side_effect=swap_binding_then_scan,
                ):
                    self._recovering_service(planner).recover_startup()

                self.assertEqual(assets.read_item(handle.record["id"])["id"], handle.record["id"])
                self.assertTrue(journal.exists())

    def test_missing_nofollow_capability_keeps_normal_reads_but_rollback_fails_closed(self) -> None:
        payload_bytes, _ = _full_restore_archive("missing-nofollow")
        _, planner = self._restore_service(payload_bytes)
        planner.task_storage.write_metadata("normal-task", {
            "task_id": "normal-task", "created_at": "2026-08-01T00:00:00Z",
            "status": "completed", "reference_assets": [],
        })
        data = _png_bytes((121, 122, 123))
        handle = planner.reference_asset_storage.restore_content("guarded.png", data, "image/png")
        task_token = "3" * 32
        planner.task_storage._write_restore_ownership("failed-restore", task_token)
        session_id = "3" * 32
        journal = self.root / f"history-backup-import-{session_id}.rollback.json"
        journal.write_text(json.dumps({
            "session_id": session_id,
            "tasks": [{
                "task_id": "failed-restore", "restore_token": task_token,
                "pending_paths": [], "index_pending": False,
                "pending_resources": [{
                    "kind": "reference_asset", "id": handle.record["id"],
                    "created": True, "version": handle.version,
                    "record": handle.record, "restore_token": handle.restore_token,
                }],
                "pending_staging_paths": [], "organization_pending": False,
                "ownership_pending": True,
            }],
            "code": "backup_import_restore_rollback_incomplete",
        }), encoding="utf-8")

        with mock.patch.object(os, "O_NOFOLLOW", None, create=True):
            self.assertTrue(planner.task_storage.iter_metadata_paths())
            self.assertEqual(
                planner.task_storage.read_tasks_from_metadata()[0]["task_id"],
                "normal-task",
            )
            with self.assertRaisesRegex(OSError, "backup_restore_reference_scan_unavailable"):
                planner.task_storage.resource_reference_snapshot()
            self._recovering_service(planner).recover_startup()

        self.assertEqual(planner.reference_asset_storage.read_item(handle.record["id"])["id"], handle.record["id"])
        self.assertTrue(journal.exists())

    def test_absent_gallery_restore_is_complete_and_same_content_recreation_survives(self) -> None:
        payload_bytes, _ = _full_restore_archive("replay-gallery-recreate")
        _, planner = self._restore_service(payload_bytes)
        data = _png_bytes((25, 50, 75))
        old_handle = planner.gallery_storage.restore_content(
            "Old pose", "portrait", "pose.png", data, "image/png"
        )
        planner.gallery_storage.delete_item(old_handle.record["id"])
        recreated = planner.gallery_storage.restore_content(
            "New pose", "portrait", "pose.png", data, "image/png"
        )
        self.assertNotEqual(recreated.record["id"], old_handle.record["id"])
        task_token = "5" * 32
        planner.task_storage._write_restore_ownership("task-a", task_token)
        session_id = "c" * 32
        journal = self.root / f"history-backup-import-{session_id}.rollback.json"
        journal.write_text(json.dumps({
            "session_id": session_id,
            "tasks": [{
                "task_id": "task-a", "restore_token": task_token,
                "pending_paths": [], "index_pending": False,
                "pending_resources": [{
                    "kind": "gallery", "id": old_handle.record["id"],
                    "created": True, "version": old_handle.version,
                    "record": old_handle.record, "restore_token": old_handle.restore_token,
                }],
                "pending_staging_paths": [], "organization_pending": False,
                "ownership_pending": True,
            }],
            "code": "backup_import_restore_rollback_incomplete",
        }), encoding="utf-8")
        cold_planner = TaskBackupPlanner(
            TaskStorage(
                planner.task_storage.output_root,
                input_root=planner.task_storage.input_root,
                source_data_root=planner.task_storage.source_data_root,
            ),
            GalleryStorage(planner.gallery_storage.root),
            ReferenceAssetStorage(planner.reference_asset_storage.root, max_items=50),
            ReferenceFileStorage(planner.reference_file_storage.root),
        )

        self._recovering_service(cold_planner).recover_startup()

        self.assertEqual(cold_planner.gallery_storage.read_item(recreated.record["id"])["id"], recreated.record["id"])
        self.assertFalse(journal.exists())

    def test_startup_resource_replay_verifies_persisted_record_after_cold_restart(self) -> None:
        payload_bytes, _ = _full_restore_archive("replay-cold-resource")
        _, planner = self._restore_service(payload_bytes)
        data = _png_bytes((70, 80, 90))
        handle = planner.reference_asset_storage.restore_content("asset.png", data, "image/png")
        task_token = "d" * 32
        planner.task_storage._write_restore_ownership("task-a", task_token)
        session_id = "6" * 32
        journal = self.root / f"history-backup-import-{session_id}.rollback.json"
        journal.write_text(json.dumps({
            "session_id": session_id,
            "tasks": [{
                "task_id": "task-a", "restore_token": task_token,
                "pending_paths": [], "index_pending": False,
                "pending_resources": [{
                    "kind": "reference_asset", "id": handle.record["id"],
                    "created": True, "version": handle.version, "record": handle.record,
                    "restore_token": handle.restore_token,
                }],
                "pending_staging_paths": [], "organization_pending": False,
                "ownership_pending": True,
            }],
            "code": "backup_import_restore_rollback_incomplete",
        }), encoding="utf-8")
        cold_planner = TaskBackupPlanner(
            TaskStorage(
                planner.task_storage.output_root,
                input_root=planner.task_storage.input_root,
                source_data_root=planner.task_storage.source_data_root,
            ),
            GalleryStorage(planner.gallery_storage.root),
            ReferenceAssetStorage(planner.reference_asset_storage.root, max_items=50),
            ReferenceFileStorage(planner.reference_file_storage.root),
        )

        self._recovering_service(cold_planner).recover_startup()

        with self.assertRaises(FileNotFoundError):
            cold_planner.reference_asset_storage.read_item(handle.record["id"])
        self.assertFalse(journal.exists())

    def test_old_reference_file_journal_preserves_same_content_recreated_before_cold_restart(self) -> None:
        payload_bytes, _ = _full_restore_archive("replay-reference-file-cas")
        _, planner = self._restore_service(payload_bytes)
        reference = validate_reference_file("notes.txt", b"same content", "text/plain")
        old_handle = planner.reference_file_storage.restore_validated(reference)
        planner.reference_file_storage.delete_created(reference.asset_id)
        new_handle = planner.reference_file_storage.restore_validated(reference)
        self.assertNotEqual(old_handle.restore_token, new_handle.restore_token)
        task_token = "3" * 32
        planner.task_storage._write_restore_ownership("task-a", task_token)
        session_id = "a" * 32
        journal = self.root / f"history-backup-import-{session_id}.rollback.json"
        journal.write_text(json.dumps({
            "session_id": session_id,
            "tasks": [{
                "task_id": "task-a", "restore_token": task_token,
                "pending_paths": [], "index_pending": False,
                "pending_resources": [{
                    "kind": "reference_file", "id": old_handle.record["id"],
                    "created": True, "version": old_handle.version,
                    "record": old_handle.record, "restore_token": old_handle.restore_token,
                }],
                "pending_staging_paths": [], "organization_pending": False,
                "ownership_pending": True,
            }],
            "code": "backup_import_restore_rollback_incomplete",
        }), encoding="utf-8")
        cold_planner = TaskBackupPlanner(
            TaskStorage(
                planner.task_storage.output_root,
                input_root=planner.task_storage.input_root,
                source_data_root=planner.task_storage.source_data_root,
            ),
            GalleryStorage(planner.gallery_storage.root),
            ReferenceAssetStorage(planner.reference_asset_storage.root, max_items=50),
            ReferenceFileStorage(planner.reference_file_storage.root),
        )

        self._recovering_service(cold_planner).recover_startup()

        self.assertEqual(
            cold_planner.reference_file_storage.read_item(reference.asset_id)["id"],
            reference.asset_id,
        )
        self.assertFalse(journal.exists())

    def test_rollback_journal_rewrite_fsync_failure_retains_retry_and_replay_converges(self) -> None:
        payload_bytes, _ = _full_restore_archive("replay-journal-fsync")
        _, planner = self._restore_service(payload_bytes)
        session_id = "b" * 32
        restore_token = "4" * 32
        planner.task_storage._write_restore_ownership("task-a", restore_token)
        journal = self.root / f"history-backup-import-{session_id}.rollback.json"
        journal.write_text(json.dumps({
            "session_id": session_id,
            "tasks": [{
                "task_id": "task-a", "restore_token": restore_token,
                "pending_paths": [], "index_pending": True,
                "pending_resources": [], "pending_staging_paths": [],
                "organization_pending": False, "ownership_pending": True,
            }],
            "code": "backup_import_restore_rollback_incomplete",
        }), encoding="utf-8")
        recovering = self._recovering_service(planner)
        with mock.patch.object(
            planner.task_storage.task_index, "delete", side_effect=OSError("busy")
        ), mock.patch(
            "codex_image.webui.history_backup_import._fsync_directory",
            side_effect=OSError("fsync unavailable"),
        ):
            recovering.recover_startup()
        self.assertTrue(journal.exists())

        self._recovering_service(planner).recover_startup()
        self.assertFalse(journal.exists())
        self._recovering_service(planner).recover_startup()
        self.assertFalse(journal.exists())

    def test_changed_or_symlinked_staged_binary_rolls_back_entire_task(self) -> None:
        for attack in ("changed", "symlink"):
            with self.subTest(attack=attack):
                task_id = f"staged-{attack}"
                payload, _ = _full_restore_archive(task_id)
                service, planner = self._restore_service(payload)
                session_id = self._upload(payload, service=service)
                service.validate(session_id)
                original_restore = planner.task_storage.restore_task_files

                def tamper(plan):
                    staged_path = plan.binaries[0].staged_path
                    assert staged_path is not None
                    if attack == "changed":
                        staged_path.write_bytes(b"X" * plan.binaries[0].expected_size)
                    else:
                        outside = Path(self.temporary.name) / f"outside-{task_id}.bin"
                        outside.write_bytes(b"outside")
                        staged_path.unlink()
                        staged_path.symlink_to(outside)
                    return original_restore(plan)

                with mock.patch.object(planner.task_storage, "restore_task_files", side_effect=tamper):
                    result = service.restore(session_id)

                self.assertEqual([item.task_id for item in result.failed], [task_id])
                self.assertFalse(planner.task_storage.metadata_path(task_id).exists())
                self.assertNotIn(task_id, planner.task_storage.task_index.existing_task_ids([task_id]))
                self.assertFalse(planner.task_storage.history_organizer.has_task_state(task_id))
                self.assertEqual(planner.reference_asset_storage.list_recent(limit=100), [])
                self.assertEqual(planner.gallery_storage.list_items(), [])
                self.assertEqual(planner.reference_file_storage.list_recent(limit=100), [])

    def test_restore_plan_task_mismatch_is_stable_failed_not_restoring(self) -> None:
        payload, _ = _full_restore_archive("plan-mismatch")
        service, _ = self._restore_service(payload)
        session_id = self._upload(payload, service=service)
        service.validate(session_id)
        plan_path = next(self.root.glob(f"*{session_id}.plan.json"))
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["manifest"].update(
            {"tasks": [], "task_count": 0, "file_count": 0, "uncompressed_bytes": 0}
        )
        plan_path.write_text(json.dumps(plan), encoding="utf-8")

        for _ in range(2):
            self.assertCode("backup_import_restore_interrupted", lambda: service.restore(session_id))
            state = service.get(session_id)
            self.assertEqual(
                (state.status, state.error_code),
                ("failed", "backup_import_restore_interrupted"),
            )

    def test_restore_status_write_failures_do_not_leave_ambiguous_memory_state(self) -> None:
        payload, _ = _full_restore_archive("status-write")
        service, _ = self._restore_service(payload)
        session_id = self._upload(payload, service=service)
        service.validate(session_id)
        original_write = service._write_status

        with mock.patch.object(service, "_write_status", side_effect=OSError("initial status")):
            with self.assertRaisesRegex(OSError, "initial status"):
                service.restore(session_id)
        self.assertEqual(service.get(session_id).status, "validated")

        failed_once = False

        def fail_final(session):
            nonlocal failed_once
            if session.status == "restored" and not failed_once:
                failed_once = True
                raise OSError("final status")
            return original_write(session)

        with mock.patch.object(service, "_write_status", side_effect=fail_final):
            self.assertCode("backup_import_restore_interrupted", lambda: service.restore(session_id))
        self.assertEqual(
            (service.get(session_id).status, service.get(session_id).error_code),
            ("failed", "backup_import_restore_interrupted"),
        )
        self.assertCode("backup_import_restore_interrupted", lambda: service.restore(session_id))

    def test_chunk_protocol_is_sequential_hashed_bounded_and_private(self) -> None:
        session = self.service.create("backup.zip", 6)
        artifacts = list(self.root.iterdir())
        self.assertEqual(len(artifacts), 2)
        self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in artifacts))

        first = b"abc"
        state = self.service.append_chunk(session.session_id, 0, first, hashlib.sha256(first).hexdigest())
        self.assertEqual(state.uploaded_bytes, 3)
        for code, call in (
            ("backup_import_offset_invalid", lambda: self.service.append_chunk(session.session_id, 1, b"x", hashlib.sha256(b"x").hexdigest())),
            ("backup_import_chunk_hash_mismatch", lambda: self.service.append_chunk(session.session_id, 3, b"x", "0" * 64)),
            ("backup_import_chunk_too_large", lambda: self.service.append_chunk(session.session_id, 3, b"x" * 65, hashlib.sha256(b"x" * 65).hexdigest())),
            ("backup_import_upload_overflow", lambda: self.service.append_chunk(session.session_id, 3, b"xxxx", hashlib.sha256(b"xxxx").hexdigest())),
        ):
            self.assertCode(code, call)
            self.assertEqual(self.service.get(session.session_id).uploaded_bytes, 3)

        final = b"def"
        completed = self.service.append_chunk(session.session_id, 3, final, hashlib.sha256(final).hexdigest())
        self.assertEqual(completed.status, "uploaded")
        retry = self.service.append_chunk(session.session_id, 3, final, hashlib.sha256(final).hexdigest())
        self.assertEqual(retry.uploaded_bytes, 6)
        self.assertCode(
            "backup_import_offset_invalid",
            lambda: self.service.append_chunk(session.session_id, 0, first, hashlib.sha256(first).hexdigest()),
        )
        self.assertCode(
            "backup_import_chunk_retry_mismatch",
            lambda: self.service.append_chunk(session.session_id, 3, b"deg", hashlib.sha256(b"deg").hexdigest()),
        )

    def test_incomplete_upload_cannot_validate_and_error_does_not_advance(self) -> None:
        session = self.service.create("backup.zip", 10)
        chunk = b"short"
        self.service.append_chunk(session.session_id, 0, chunk, hashlib.sha256(chunk).hexdigest())
        self.assertCode("backup_import_upload_incomplete", lambda: self.service.validate(session.session_id))
        state = self.service.get(session.session_id)
        self.assertEqual((state.status, state.uploaded_bytes), ("uploading", 5))

    def test_each_chunk_rechecks_current_disk_capacity_without_advancing_on_failure(self) -> None:
        payload = _archive_bytes()
        capacity = {"free": len(payload) + 100}

        class _Usage:
            total = 100

            @property
            def free(self):
                return capacity["free"]

        service = HistoryBackupImportService(
            _Planner(),
            self.root,
            max_upload_bytes=len(payload) + 1,
            max_chunk_bytes=64,
            max_entries=32,
            max_member_bytes=64 * 1024,
            max_expanded_bytes=128 * 1024,
            max_compression_ratio=100,
            max_manifest_bytes=32 * 1024,
            min_free_bytes=10,
            free_ratio=0.10,
            disk_usage=lambda _path: _Usage(),
        )
        session = service.create("backup.zip", len(payload))
        upload_path = next(self.root.glob("*.upload.partial"))
        status_path = next(self.root.glob("*.status.json"))
        status_before = status_path.read_bytes()
        first = payload[:64]
        capacity["free"] = 10 + len(first) - 1
        self.assertCode(
            "backup_import_insufficient_space",
            lambda: service.append_chunk(
                session.session_id,
                0,
                first,
                hashlib.sha256(first).hexdigest(),
            ),
        )
        self.assertEqual(upload_path.stat().st_size, 0)
        self.assertEqual(status_path.read_bytes(), status_before)
        self.assertEqual(service.get(session.session_id), session)

        capacity["free"] = len(payload) + 100
        for offset in range(0, len(payload), 64):
            chunk = payload[offset : offset + 64]
            service.append_chunk(session.session_id, offset, chunk, hashlib.sha256(chunk).hexdigest())
        self.assertEqual(service.validate(session.session_id).restorable[0].task_id, "task-1")

    def test_valid_preview_uses_server_digest_and_server_side_classification(self) -> None:
        first, first_payloads, first_fingerprint = _task_files("restorable")
        second, second_payloads, second_fingerprint = _task_files("duplicate")
        third, third_payloads, _ = _task_files("conflict")
        payload = _archive_bytes(
            tasks=[first, second, third],
            payloads={**first_payloads, **second_payloads, **third_payloads},
        )
        service = HistoryBackupImportService(
            _Planner({"duplicate": second_fingerprint, "conflict": "sha256:" + "f" * 64}),
            self.root,
            max_upload_bytes=len(payload) + 1,
            max_chunk_bytes=64,
            max_entries=32,
            max_member_bytes=64 * 1024,
            max_expanded_bytes=128 * 1024,
            max_compression_ratio=100,
            max_manifest_bytes=32 * 1024,
            min_free_bytes=0,
            free_ratio=0,
        )
        session_id = self._upload(payload, service=service)
        preview = service.validate(session_id)
        self.assertEqual(preview.whole_file_sha256, hashlib.sha256(payload).hexdigest())
        self.assertEqual([item.task_id for item in preview.restorable], ["restorable"])
        self.assertEqual([item.task_id for item in preview.duplicate], ["duplicate"])
        self.assertEqual([item.task_id for item in preview.conflict], ["conflict"])
        self.assertEqual(preview.invalid, ())
        self.assertEqual(service.validate(session_id), preview)
        plan_path = next(self.root.glob("*.plan.json"))
        self.assertEqual(stat.S_IMODE(plan_path.stat().st_mode), 0o600)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        self.assertEqual(plan["classifications"]["conflict"][0]["task_id"], "conflict")
        self.assertNotIn("classification", plan["manifest"]["tasks"][0])

    def test_cancel_removes_only_session_artifacts(self) -> None:
        sentinel = self.root / "sentinel.txt"
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("keep", encoding="utf-8")
        session = self.service.create("backup.zip", 4)
        self.assertTrue(self.service.cancel(session.session_id))
        self.assertIsNone(self.service.get(session.session_id))
        self.assertTrue(sentinel.is_file())
        self.assertFalse(any(session.session_id in path.name for path in self.root.iterdir()))

    def test_cancel_keeps_retryable_ownership_when_same_name_directory_cannot_unlink(self) -> None:
        session = self.service.create("backup.zip", 4)
        plan_path = self.root / f"history-backup-import-{session.session_id}.plan.json"
        plan_path.mkdir()
        self.assertFalse(self.service.cancel(session.session_id))
        self.assertEqual(self.service.get(session.session_id), session)
        self.assertTrue(plan_path.is_dir())
        self.assertTrue(next(self.root.glob("*.upload.partial")).is_file())
        self.assertTrue(next(self.root.glob("*.status.json")).is_file())

        plan_path.rmdir()
        self.assertTrue(self.service.cancel(session.session_id))
        self.assertIsNone(self.service.get(session.session_id))

    def test_cancel_keeps_record_when_directory_fsync_fails_and_can_retry(self) -> None:
        session = self.service.create("backup.zip", 4)
        with mock.patch(
            "codex_image.webui.history_backup_import._fsync_directory",
            side_effect=OSError("synthetic fsync failure"),
        ):
            self.assertFalse(self.service.cancel(session.session_id))
        self.assertEqual(self.service.get(session.session_id), session)
        self.assertFalse(any(session.session_id in path.name for path in self.root.iterdir()))
        self.assertTrue(self.service.cancel(session.session_id))
        self.assertIsNone(self.service.get(session.session_id))

    def test_hostile_member_paths_are_rejected_without_extraction(self) -> None:
        for name in ("../escape", "/absolute", "C:/absolute", "tasks\\evil\\file"):
            with self.subTest(name=name):
                payload = _archive_bytes(extra_members=[(name, b"bad")])
                session_id = self._upload(payload)
                self.assertCode("backup_import_member_path_invalid", lambda: self.service.validate(session_id))
        self.assertFalse((self.root.parent / "escape").exists())

    def test_symlink_encrypted_and_duplicate_members_are_rejected(self) -> None:
        link = zipfile.ZipInfo("tasks/task-1/outputs/output-0001.png")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        cases = (
            ("backup_import_symlink_forbidden", _archive_bytes(extra_members=[(link, b"target")])),
            ("backup_import_encrypted_forbidden", _set_encrypted_flag(_archive_bytes())),
            ("backup_import_duplicate_member_path", _archive_bytes(extra_members=[("tasks/task-1/source/metadata.json", b"again")])),
            ("backup_import_duplicate_member_path", _archive_bytes(extra_members=[("future/Payload.bin", b"a"), ("future/payload.bin", b"b")])),
        )
        for code, payload in cases:
            with self.subTest(code=code):
                session_id = self._upload(payload)
                self.assertCode(code, lambda: self.service.validate(session_id))

    def test_special_files_and_unsupported_compression_are_rejected(self) -> None:
        special = zipfile.ZipInfo("tasks/task-1/outputs/output-0001.png")
        special.create_system = 3
        special.external_attr = (stat.S_IFCHR | 0o600) << 16
        cases = (
            ("backup_import_special_file_forbidden", _archive_bytes(extra_members=[(special, b"device")])),
            ("backup_import_compression_unsupported", _archive_bytes(compression=zipfile.ZIP_BZIP2)),
        )
        for code, payload in cases:
            with self.subTest(code=code):
                session_id = self._upload(payload)
                self.assertCode(code, lambda: self.service.validate(session_id))

    def test_import_root_is_forced_private(self) -> None:
        permissive_root = Path(self.temporary.name) / "permissive-imports"
        permissive_root.mkdir(mode=0o777)
        os.chmod(permissive_root, 0o777)
        HistoryBackupImportService(
            _Planner(),
            permissive_root,
            min_free_bytes=0,
            free_ratio=0,
        )
        self.assertEqual(stat.S_IMODE(permissive_root.stat().st_mode), 0o700)

    def test_manifest_members_must_match_archive_and_supported_version(self) -> None:
        valid = _archive_bytes()
        undeclared = _archive_bytes(extra_members=[("tasks/task-1/outputs/output-0001.png", b"x")])
        missing = _replace_manifest(valid, lambda manifest: manifest["tasks"][0]["files"].append({
            "path": "tasks/task-1/outputs/output-0001.png", "role": "output", "required": True,
            "size_bytes": 1, "sha256": hashlib.sha256(b"x").hexdigest(), "source_index": 1,
        }))
        # Keep aggregate fields coherent so the missing-member check is reached.
        missing = _replace_manifest(missing, lambda manifest: manifest.update(
            file_count=len(manifest["tasks"][0]["files"]),
            uncompressed_bytes=sum(item["size_bytes"] for item in manifest["tasks"][0]["files"]),
        ))
        for code, payload in (
            ("backup_import_member_undeclared", undeclared),
            ("backup_import_member_missing", missing),
            ("backup_manifest_version_unsupported", _archive_bytes(version=2)),
        ):
            with self.subTest(code=code):
                session_id = self._upload(payload)
                self.assertCode(code, lambda: self.service.validate(session_id))

    def test_actual_member_size_and_hash_are_verified(self) -> None:
        valid = _archive_bytes()
        wrong_size = _replace_manifest(valid, lambda manifest: manifest["tasks"][0]["files"][0].update(size_bytes=999))
        wrong_size = _replace_manifest(wrong_size, lambda manifest: manifest.update(
            uncompressed_bytes=sum(item["size_bytes"] for item in manifest["tasks"][0]["files"])
        ))
        wrong_hash = _replace_manifest(valid, lambda manifest: manifest["tasks"][0]["files"][0].update(sha256="0" * 64))
        for code, payload in (
            ("backup_import_member_size_mismatch", wrong_size),
            ("backup_import_member_hash_mismatch", wrong_hash),
        ):
            with self.subTest(code=code):
                session_id = self._upload(payload)
                self.assertCode(code, lambda: self.service.validate(session_id))

    def test_entry_member_expanded_manifest_and_ratio_budgets_are_injected(self) -> None:
        payload = _archive_bytes()
        configurations = (
            ("backup_import_too_many_entries", {"max_entries": 1}),
            ("backup_import_member_too_large", {"max_member_bytes": 8}),
            ("backup_import_expanded_too_large", {"max_expanded_bytes": 8}),
            ("backup_import_manifest_too_large", {"max_manifest_bytes": 8}),
        )
        for code, overrides in configurations:
            with self.subTest(code=code):
                limits = {
                    "max_upload_bytes": len(payload) + 1,
                    "max_chunk_bytes": 64,
                    "max_entries": 32,
                    "max_member_bytes": 64 * 1024,
                    "max_expanded_bytes": 128 * 1024,
                    "max_compression_ratio": 100,
                    "max_manifest_bytes": 32 * 1024,
                    "min_free_bytes": 0,
                    "free_ratio": 0,
                }
                limits.update(overrides)
                service = HistoryBackupImportService(_Planner(), self.root, **limits)
                session_id = self._upload(payload, service=service)
                self.assertCode(code, lambda: service.validate(session_id))

        bomb = _archive_bytes(extra_members=[("bomb.bin", b"0" * 8192)])
        ratio_service = HistoryBackupImportService(
            _Planner(), self.root,
            max_upload_bytes=len(bomb) + 1, max_chunk_bytes=64,
            max_entries=32, max_member_bytes=64 * 1024,
            max_expanded_bytes=128 * 1024, max_compression_ratio=2,
            max_manifest_bytes=32 * 1024, min_free_bytes=0, free_ratio=0,
        )
        session_id = self._upload(bomb, service=ratio_service)
        self.assertCode("backup_import_compression_ratio_too_high", lambda: ratio_service.validate(session_id))

    def test_invalid_raster_and_reference_file_are_classified_invalid(self) -> None:
        cases = (
            ("output", "tasks/bad-image/outputs/output-0001.png", b"not-a-png"),
            ("reference_file", "tasks/bad-reference/inputs/references/reference_file-0001.pdf", b"not-a-pdf"),
        )
        for role, path, data in cases:
            with self.subTest(role=role):
                task_id = path.split("/")[1]
                task, payloads, _ = _task_files(task_id, extra=(path, role, data))
                if role == "reference_file":
                    metadata_path = f"tasks/{task_id}/source/metadata.json"
                    metadata = json.loads(payloads[metadata_path])
                    metadata["reference_files"] = [{"id": "0" * 64, "filename": "file.pdf", "mime_type": "application/pdf", "size_bytes": len(data)}]
                    payloads[metadata_path] = _json_bytes(metadata)
                    entry = next(item for item in task["files"] if item["role"] == "metadata")
                    entry.update(size_bytes=len(payloads[metadata_path]), sha256=hashlib.sha256(payloads[metadata_path]).hexdigest())
                    task["fingerprint"] = canonical_task_fingerprint(
                        metadata, {"prompt": "safe"},
                        tuple(BackupFileEntry(**item) for item in task["files"]), {"favorite": False, "tags": []},
                    )
                payload = _archive_bytes(tasks=[task], payloads=payloads)
                session_id = self._upload(payload)
                preview = self.service.validate(session_id)
                self.assertEqual([item.task_id for item in preview.invalid], [task_id])

    def test_unknown_optional_role_is_integrity_checked_but_does_not_break_v1_preview(self) -> None:
        task, payloads, _ = _task_files("task-optional")
        optional_payload = b"future"
        optional_path = "tasks/task-optional/future/payload.bin"
        task["files"].append({
            "path": optional_path,
            "role": "future_optional_role",
            "required": False,
            "size_bytes": len(optional_payload),
            "sha256": hashlib.sha256(optional_payload).hexdigest(),
            "source_index": None,
        })
        payloads[optional_path] = optional_payload
        session_id = self._upload(_archive_bytes(tasks=[task], payloads=payloads))
        preview = self.service.validate(session_id)
        self.assertEqual([item.task_id for item in preview.restorable], ["task-optional"])

    def test_sensitive_request_is_classified_invalid_even_with_matching_fingerprint(self) -> None:
        task, payloads, _ = _task_files("task-secret")
        request_path = "tasks/task-secret/source/request.json"
        request = {"prompt": "safe", "api_key": "must-not-restore"}
        payloads[request_path] = _json_bytes(request)
        request_entry = next(item for item in task["files"] if item["role"] == "request")
        request_entry.update(
            size_bytes=len(payloads[request_path]),
            sha256=hashlib.sha256(payloads[request_path]).hexdigest(),
        )
        metadata = json.loads(payloads["tasks/task-secret/source/metadata.json"])
        organization = json.loads(payloads["tasks/task-secret/source/organization.json"])
        task["fingerprint"] = canonical_task_fingerprint(
            metadata,
            request,
            tuple(BackupFileEntry(**item) for item in task["files"]),
            organization,
        )
        session_id = self._upload(_archive_bytes(tasks=[task], payloads=payloads))
        preview = self.service.validate(session_id)
        self.assertEqual(preview.invalid[0].reason, "backup_import_request_contains_sensitive_fields")

    def test_sensitive_metadata_is_classified_invalid(self) -> None:
        task, payloads, _ = _task_files("task-metadata-secret")
        metadata_path = "tasks/task-metadata-secret/source/metadata.json"
        metadata = json.loads(payloads[metadata_path])
        metadata["authorization"] = "must-not-restore"
        payloads[metadata_path] = _json_bytes(metadata)
        entry = next(item for item in task["files"] if item["role"] == "metadata")
        entry.update(size_bytes=len(payloads[metadata_path]), sha256=hashlib.sha256(payloads[metadata_path]).hexdigest())
        request = json.loads(payloads["tasks/task-metadata-secret/source/request.json"])
        organization = json.loads(payloads["tasks/task-metadata-secret/source/organization.json"])
        task["fingerprint"] = canonical_task_fingerprint(
            metadata, request, tuple(BackupFileEntry(**item) for item in task["files"]), organization,
        )
        session_id = self._upload(_archive_bytes(tasks=[task], payloads=payloads))
        preview = self.service.validate(session_id)
        self.assertEqual(preview.invalid[0].reason, "backup_import_metadata_contains_sensitive_fields")


if __name__ == "__main__":
    unittest.main()
