import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from codex_image.webui.gallery_storage import GalleryStorage
from codex_image.webui.history_backup_export import HistoryBackupExportService
from codex_image.webui.history_backup_import import HistoryBackupImportService
from codex_image.webui.history_backup_plan import BackupExportScope, TaskBackupPlanner
from codex_image.webui.reference_assets import ReferenceAssetStorage
from codex_image.webui.reference_files import ReferenceFileStorage
from codex_image.webui.storage import TaskStorage
from tests.test_webui_history_backup_import import _png_bytes


def _planner(root: Path) -> TaskBackupPlanner:
    return TaskBackupPlanner(TaskStorage(root / "outputs", input_root=root / "inputs", source_data_root=root / "source"),
                             GalleryStorage(root / "gallery"), ReferenceAssetStorage(root / "assets"),
                             ReferenceFileStorage(root / "files"))


class _DirectExecutor:
    def submit(self, function, *args, **kwargs):
        function(*args, **kwargs)


class BackupPromptRoundtripTests(unittest.TestCase):
    def test_export_import_preserves_free_text_even_when_it_looks_like_a_path(self):
        prompts = ("ordinary text", "/imagine a small red rabbit", "/tmp/example is a label",
                   "C:\\art\\rabbit", "file:///reference is written on the sign",
                   "http://localhost:8787 is the caption", " /兔子\n第二行 🐇\n ")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, target = _planner(root / "source"), _planner(root / "target")
            expected = {}
            png = _png_bytes((255, 0, 0))
            for prompt in prompts:
                storage = source.task_storage
                task_id = storage.create_task("generate").task_id
                filename = storage.output_file(storage.write_output(task_id, png, "png"))
                storage.write_metadata(task_id, {"task_id": task_id, "status": "completed",
                    "created_at": "2026-09-16T00:00:00Z", "prompt": prompt, "prompt_for_model": prompt,
                    "output_file": filename, "output_files": [filename],
                    "outputs": [{"index": 1, "status": "completed", "file": filename, "revised_prompt": prompt}]})
                storage.write_request(task_id, {"prompt": prompt, "input": [{"content": [{"type": "input_text", "text": prompt}]}]})
                expected[task_id] = prompt
            exporter = HistoryBackupExportService(source, root / "exports", executor=_DirectExecutor(), min_free_bytes=0, free_ratio=0)
            job = exporter.create(BackupExportScope("selected", tuple(expected)))
            self.assertEqual(job.status, "ready")
            payload = exporter.claim_download(job.job_id).read_bytes()
            importer = HistoryBackupImportService(target, root / "imports", min_free_bytes=0, free_ratio=0)
            session = importer.create("backup.zip", len(payload))
            importer.append_chunk(session.session_id, 0, payload, hashlib.sha256(payload).hexdigest())
            importer.validate(session.session_id)
            result = importer.restore(session.session_id)
            self.assertEqual(len(result.restored), len(expected))
            self.assertEqual(result.failed, ())
            for task_id, prompt in expected.items():
                metadata = target.task_storage.read_metadata(task_id)
                request = json.loads(target.task_storage.request_path(task_id).read_text())
                self.assertEqual(metadata.get("prompt"), prompt)
                self.assertEqual(metadata.get("prompt_for_model"), prompt)
                self.assertEqual(metadata["outputs"][0].get("revised_prompt"), prompt)
                self.assertEqual(request.get("prompt"), prompt)
                self.assertEqual(request["input"][0]["content"][0].get("text"), prompt)
                self.assertEqual(target.task_storage.output_path(metadata["output_file"]).read_bytes(), png)
