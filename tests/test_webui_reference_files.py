from __future__ import annotations

import asyncio
import base64
import importlib
import io
import json
import tempfile
import threading
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest import mock

from fastapi.testclient import TestClient

from codex_image.client import CodexImageClient, DEFAULT_MAIN_MODEL, DEFAULT_RESPONSES_URL, ResponsesRequestError
from codex_image.webui.app import create_app
from codex_image.webui import app as webui_app
from codex_image.webui import reference_files
from codex_image.webui.reference_files import (
    ReferenceFileStorage,
    dedupe_reference_file_records,
    read_reference_file_uploads,
    reference_file_task_record,
    validate_reference_file,
    validate_reference_file_total,
)
from codex_image.webui.storage_utils import _safe_filename
from codex_image.webui.storage import TaskStorage
from codex_image.webui.task_metadata import (
    _fail_task,
    _write_progress_metadata,
    _write_queued_metadata,
    _write_running_metadata,
)
from tests.webui_helpers import CapturingResponsesClient, FakeImageClient, RejectingResponsesClient


def openxml_bytes(member: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(member, "content")
    return buffer.getvalue()


def zip_with_member(member: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(member, "content")
    return buffer.getvalue()


def odt_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        archive.writestr("content.xml", "<office:document-content/>")
    return buffer.getvalue()


COMPOUND_FILE_BYTES = bytes.fromhex("d0cf11e0a1b11ae1") + b"content"

OFFICIAL_EXTENSIONS = {
    ".pdf",
    ".xla", ".xlb", ".xlc", ".xlm", ".xls", ".xlsx", ".xlt", ".xlw",
    ".csv", ".tsv", ".iif",
    ".doc", ".docx", ".dot", ".odt", ".rtf",
    ".pot", ".ppa", ".pps", ".ppt", ".pptx", ".pwz", ".wiz",
    ".asm", ".bat", ".c", ".cc", ".conf", ".cpp", ".css", ".cxx", ".def", ".dic",
    ".eml", ".h", ".hh", ".htm", ".html", ".ics", ".ifb", ".in", ".js", ".json",
    ".ksh", ".list", ".log", ".markdown", ".md", ".mht", ".mhtml", ".mime", ".mjs",
    ".nws", ".pl", ".py", ".rst", ".s", ".sql", ".srt", ".text", ".txt", ".vcf",
    ".vtt", ".xml",
}

OFFICIAL_CATEGORY_MIME_ALIASES = {
    "pdf": {"application/pdf"},
    "excel": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    },
    "delimited": {
        "text/csv", "application/csv", "text/tsv", "text/x-iif", "application/x-iif",
        "application/vnd.google-apps.spreadsheet",
    },
    "document": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword", "application/rtf", "text/rtf",
        "application/vnd.oasis.opendocument.text", "application/vnd.apple.pages",
        "application/vnd.google-apps.document", "application/vnd.apple.iwork",
    },
    "presentation": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.ms-powerpoint", "application/vnd.apple.keynote",
        "application/vnd.google-apps.presentation", "application/vnd.apple.iwork",
    },
    "text": {
        "application/javascript", "application/typescript", "text/xml", "text/x-shellscript",
        "text/x-rst", "text/x-makefile", "text/x-lisp", "text/x-asm", "text/vbscript", "text/css",
        "message/rfc822", "application/x-sql", "application/x-scala", "application/x-rust",
        "application/x-powershell", "text/x-diff", "text/x-patch", "application/x-patch",
        "text/plain", "text/markdown", "text/x-java", "text/x-script.python", "text/x-python",
        "text/x-c", "text/x-c++", "text/x-golang", "text/html", "text/x-php", "application/x-php",
        "application/x-httpd-php", "application/x-httpd-php-source", "text/x-ruby", "text/x-sh",
        "text/x-bash", "application/x-bash", "text/x-zsh", "text/x-tex", "text/x-csharp",
        "application/json", "text/x-typescript", "text/javascript", "text/x-go", "text/x-rust",
        "text/x-scala", "text/x-kotlin", "text/x-swift", "text/x-lua", "text/x-r", "text/x-julia",
        "text/x-perl", "text/x-objectivec", "text/x-objectivec++", "text/x-erlang", "text/x-elixir",
        "text/x-haskell", "text/x-clojure", "text/x-groovy", "text/x-dart", "text/x-awk",
        "application/x-awk", "text/jsx", "text/tsx", "text/x-handlebars", "text/x-mustache",
        "text/x-ejs", "text/x-jinja2", "text/x-liquid", "text/x-erb", "text/x-twig", "text/x-pug",
        "text/x-jade", "text/x-tmpl", "text/x-cmake", "text/x-dockerfile", "text/x-gradle",
        "text/x-ini", "text/x-properties", "text/x-protobuf", "application/x-protobuf", "text/x-sql",
        "text/x-sass", "text/x-scss", "text/x-less", "text/x-hcl", "text/x-terraform",
        "application/x-terraform", "text/x-toml", "application/x-toml", "application/graphql",
        "application/x-graphql", "text/x-graphql", "application/x-ndjson", "application/json5",
        "application/x-json5", "text/x-yaml", "application/toml", "application/x-yaml",
        "application/yaml", "text/x-astro", "text/srt", "application/x-subrip", "text/x-subrip",
        "text/vtt", "text/x-vcard", "text/calendar",
    },
}


class ReferenceFilePolicyTests(unittest.TestCase):
    def test_upload_reader_uses_bounded_reads_and_stops_after_total_limit(self) -> None:
        class InstrumentedUpload:
            def __init__(self, filename: str, data: bytes) -> None:
                self.filename = filename
                self.content_type = "text/plain"
                self._data = data
                self._offset = 0
                self.read_sizes: list[int] = []
                self.closed = False

            async def read(self, size: int = -1) -> bytes:
                self.read_sizes.append(size)
                if size < 0:
                    raise AssertionError("upload reader performed an unbounded read")
                chunk = self._data[self._offset : self._offset + size]
                self._offset += len(chunk)
                return chunk

            async def close(self) -> None:
                self.closed = True

        first = InstrumentedUpload("first.txt", b"123456")
        later = InstrumentedUpload("later.txt", b"never-read")

        with self.assertRaisesRegex(ValueError, "^reference_files_total_too_large$"):
            asyncio.run(
                read_reference_file_uploads(
                    [first, later],  # type: ignore[list-item]
                    max_file_bytes=20,
                    max_total_bytes=5,
                    chunk_size=3,
                )
            )

        self.assertTrue(first.read_sizes)
        self.assertTrue(all(0 < size <= 3 for size in first.read_sizes))
        self.assertEqual(later.read_sizes, [])
        self.assertTrue(first.closed)
        self.assertTrue(later.closed)

    def test_upload_reader_reads_only_size_plus_one_before_per_file_rejection(self) -> None:
        class InstrumentedUpload:
            filename = "large.txt"
            content_type = "text/plain"

            def __init__(self) -> None:
                self.remaining = b"123456789"
                self.total_requested = 0

            async def read(self, size: int = -1) -> bytes:
                if size < 0:
                    raise AssertionError("upload reader performed an unbounded read")
                self.total_requested += size
                chunk, self.remaining = self.remaining[:size], self.remaining[size:]
                return chunk

            async def close(self) -> None:
                pass

        upload = InstrumentedUpload()
        with self.assertRaisesRegex(ValueError, "^reference_file_too_large$"):
            asyncio.run(
                read_reference_file_uploads(
                    [upload],  # type: ignore[list-item]
                    max_file_bytes=5,
                    max_total_bytes=20,
                    chunk_size=3,
                )
            )
        self.assertLessEqual(upload.total_requested, 6)

    def test_upload_reader_deduplicates_large_files_before_aggregate_limit(self) -> None:
        from starlette.datastructures import UploadFile

        thirty_mib = 30 * 1024 * 1024
        duplicate_bytes = b"a" * thirty_mib
        uploads = [
            UploadFile(io.BytesIO(duplicate_bytes), filename="first.txt"),
            UploadFile(io.BytesIO(duplicate_bytes), filename="duplicate.txt"),
        ]

        result = asyncio.run(read_reference_file_uploads(uploads))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].filename, "first.txt")
        self.assertEqual(result[0].size_bytes, thirty_mib)

    def test_distinct_large_files_exceed_aggregate_and_stop_later_parts(self) -> None:
        class InstrumentedUpload:
            content_type = "text/plain"

            def __init__(self, filename: str, data: bytes) -> None:
                self.filename = filename
                self._data = io.BytesIO(data)
                self.read_calls = 0
                self.closed = False

            async def read(self, size: int = -1) -> bytes:
                if size < 0:
                    raise AssertionError("unbounded read")
                self.read_calls += 1
                return self._data.read(size)

            async def close(self) -> None:
                self.closed = True

        thirty_mib = 30 * 1024 * 1024
        first = InstrumentedUpload("first.txt", b"a" * thirty_mib)
        second = InstrumentedUpload("second.txt", b"b" * thirty_mib)
        later = InstrumentedUpload("later.txt", b"not-read")

        with self.assertRaisesRegex(ValueError, "^reference_files_total_too_large$"):
            asyncio.run(read_reference_file_uploads([first, second, later]))  # type: ignore[list-item]

        self.assertGreater(first.read_calls, 0)
        self.assertGreater(second.read_calls, 0)
        self.assertEqual(later.read_calls, 0)
        self.assertTrue(all(upload.closed for upload in (first, second, later)))

    def test_official_policy_is_complete_data_driven_and_uses_only_official_mimes(self) -> None:
        policy = getattr(reference_files, "REFERENCE_FILE_TYPES", {})
        self.assertEqual(set(policy), OFFICIAL_EXTENSIONS)
        official_mimes = set().union(*OFFICIAL_CATEGORY_MIME_ALIASES.values())
        for suffix, file_type in policy.items():
            with self.subTest(suffix=suffix):
                self.assertIn(file_type.mime_type, official_mimes)
                self.assertEqual(
                    set(file_type.accepted_mime_types),
                    OFFICIAL_CATEGORY_MIME_ALIASES[file_type.category],
                )
                data = self._valid_data_for_policy(file_type.validation)
                result = validate_reference_file(f"sample{suffix}", data, file_type.mime_type)
                self.assertEqual(result.mime_type, file_type.mime_type)
                self.assertEqual(result.family, file_type.family)

    def test_every_official_mime_alias_is_accepted_for_its_category(self) -> None:
        policy = getattr(reference_files, "REFERENCE_FILE_TYPES", {})
        representatives = {
            "pdf": ".pdf",
            "excel": ".xlsx",
            "delimited": ".csv",
            "document": ".docx",
            "presentation": ".pptx",
            "text": ".txt",
        }
        for category, aliases in OFFICIAL_CATEGORY_MIME_ALIASES.items():
            suffix = representatives[category]
            file_type = policy[suffix]
            data = self._valid_data_for_policy(file_type.validation)
            for mime_type in aliases:
                with self.subTest(category=category, mime_type=mime_type):
                    result = validate_reference_file(f"sample{suffix}", data, mime_type)
                    self.assertEqual(result.mime_type, file_type.mime_type)

    def test_official_delimited_and_xml_mimes_are_normalized(self) -> None:
        cases = [
            ("table.csv", "application/csv", "text/csv"),
            ("table.tsv", "text/tsv", "text/tsv"),
            ("ledger.iif", "application/x-iif", "text/x-iif"),
            ("data.xml", "text/xml", "text/xml"),
        ]
        for filename, supplied, expected in cases:
            with self.subTest(filename=filename, supplied=supplied):
                self.assertEqual(validate_reference_file(filename, b"content\n", supplied).mime_type, expected)

    def test_odt_rejects_oversized_compressed_mimetype_without_unbounded_read(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "mimetype",
                b"application/vnd.oasis.opendocument.text" + b"A" * (1024 * 1024),
            )
        with mock.patch.object(zipfile.ZipFile, "read", side_effect=AssertionError("unbounded ZipFile.read")):
            with self.assertRaisesRegex(ValueError, "^reference_file_invalid$"):
                validate_reference_file(
                    "bomb.odt",
                    buffer.getvalue(),
                    "application/vnd.oasis.opendocument.text",
                )

    @staticmethod
    def _valid_data_for_policy(validation: str) -> bytes:
        if validation == "pdf":
            return b"%PDF-1.7\n"
        if validation == "ooxml-word":
            return zip_with_member("word/document.xml")
        if validation == "ooxml-ppt":
            return zip_with_member("ppt/presentation.xml")
        if validation == "ooxml-sheet":
            return zip_with_member("xl/workbook.xml")
        if validation == "odt":
            return odt_bytes()
        if validation == "compound":
            return COMPOUND_FILE_BYTES
        if validation == "rtf":
            return b"{\\rtf1 content}"
        return b"content\n"

    def test_supported_families_and_pdf_detail(self) -> None:
        pdf = validate_reference_file("brief.pdf", b"%PDF-1.7\nbody", "application/pdf")
        markdown = validate_reference_file("notes.md", b"# Notes\n", "text/markdown")
        sheet = validate_reference_file(
            "budget.xlsx",
            openxml_bytes("xl/workbook.xml"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertEqual((pdf.family, pdf.detail), ("pdf", "auto"))
        self.assertEqual((markdown.family, markdown.detail), ("text", None))
        self.assertEqual((sheet.family, sheet.detail), ("spreadsheet", None))

    def test_ods_and_disguised_zip_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "reference_file_type_unsupported"):
            validate_reference_file(
                "sheet.ods",
                openxml_bytes("content.xml"),
                "application/vnd.oasis.opendocument.spreadsheet",
            )
        with self.assertRaisesRegex(ValueError, "reference_file_invalid"):
            validate_reference_file("fake.docx", openxml_bytes("misc/file.txt"), "application/octet-stream")

    def test_openxml_accepts_a_valid_zip_with_the_required_family_member(self) -> None:
        result = validate_reference_file(
            "brief.docx",
            zip_with_member("word/document.xml"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertEqual(result.family, "document")

    def test_file_and_combined_limits_are_exact(self) -> None:
        first = validate_reference_file("a.md", b"123456", "text/markdown", max_bytes=7)
        second = validate_reference_file("b.txt", b"1234", "text/plain", max_bytes=7)
        validate_reference_file_total([first, second], max_total_bytes=10)
        with self.assertRaisesRegex(ValueError, "reference_files_total_too_large"):
            validate_reference_file_total([first, second], max_total_bytes=9)
        with self.assertRaisesRegex(ValueError, "reference_file_too_large"):
            validate_reference_file("c.txt", b"1234567", "text/plain", max_bytes=7)

    def test_representative_official_types_are_accepted(self) -> None:
        cases = [
            ("brief.pdf", b"%PDF-1.7\n", "application/pdf", "pdf", "application/pdf"),
            ("notes.md", b"# Notes\n", "text/markdown", "text", "text/markdown"),
            ("notes.txt", b"Notes\n", "text/plain", "text", "text/plain"),
            (
                "brief.docx",
                openxml_bytes("word/document.xml"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "document",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            (
                "slides.pptx",
                openxml_bytes("ppt/presentation.xml"),
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "document",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ),
            (
                "budget.xlsx",
                openxml_bytes("xl/workbook.xml"),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "spreadsheet",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            ("table.csv", b"a,b\n1,2\n", "text/csv", "spreadsheet", "text/csv"),
            ("table.tsv", b"a\tb\n", "text/tsv", "spreadsheet", "text/tsv"),
            ("ledger.iif", b"!TRNS\tTRNSTYPE\n", "text/x-iif", "spreadsheet", "text/x-iif"),
            (
                "draft.odt",
                odt_bytes(),
                "application/vnd.oasis.opendocument.text",
                "document",
                "application/vnd.oasis.opendocument.text",
            ),
            ("draft.rtf", b"{\\rtf1 draft}", "application/rtf", "document", "application/rtf"),
            ("data.json", b'{"ok": true}\n', "application/json", "text", "application/json"),
            ("page.html", b"<p>Hello</p>\n", "text/html", "text", "text/html"),
            ("data.xml", b"<root/>\n", "text/xml", "text", "text/xml"),
            ("tool.py", b"print('ok')\n", "text/x-python", "text", "text/x-python"),
        ]
        for filename, data, content_type, family, normalized_mime in cases:
            with self.subTest(filename=filename):
                result = validate_reference_file(filename, data, content_type)
                self.assertEqual(result.family, family)
                self.assertEqual(result.mime_type, normalized_mime)

    def test_invalid_empty_mismatched_and_disallowed_types_are_rejected(self) -> None:
        cases = [
            ("empty.txt", b"", "text/plain", "reference_file_empty"),
            ("slides.odp", openxml_bytes("content.xml"), "application/vnd.oasis.opendocument.presentation", "reference_file_type_unsupported"),
            ("program.exe", b"MZpayload", "application/x-msdownload", "reference_file_type_unsupported"),
            ("archive.zip", openxml_bytes("file.txt"), "application/zip", "reference_file_type_unsupported"),
            ("photo.png", b"\x89PNG\r\n\x1a\n", "image/png", "reference_file_type_unsupported"),
            ("broken.pdf", b"not a pdf", "application/pdf", "reference_file_invalid"),
            ("broken.docx", b"not a zip", "application/octet-stream", "reference_file_invalid"),
            ("broken.doc", b"not compound", "application/msword", "reference_file_invalid"),
            ("renamed.txt", b"MZpayload", "text/plain", "reference_file_invalid"),
            ("notes.txt", b"notes", "application/pdf", "reference_file_type_mismatch"),
        ]
        for filename, data, content_type, error_code in cases:
            with self.subTest(filename=filename, error_code=error_code):
                with self.assertRaisesRegex(ValueError, f"^{error_code}$"):
                    validate_reference_file(filename, data, content_type)

    def test_display_filename_preserves_unicode_while_transport_fallback_is_safe(self) -> None:
        long_name = "文" * 300 + ".md"
        result = validate_reference_file(
            "folder\\ignored/  报\x00告😀.md  ",
            "# 内容\n".encode(),
            "text/markdown",
        )
        truncated = validate_reference_file(long_name, b"long\n", "text/markdown")
        self.assertEqual(result.filename, "报告😀.md")
        self.assertEqual(len(truncated.filename), 255)
        self.assertTrue(truncated.filename.endswith(".md"))
        fallback = _safe_filename(result.filename)
        self.assertTrue(fallback.isascii())
        self.assertNotIn("/", fallback)
        self.assertNotIn("\\", fallback)

        with tempfile.TemporaryDirectory() as tmp:
            item = ReferenceFileStorage(tmp).create_or_touch(result)
            self.assertEqual(item["first_filename"], "报告😀.md")
            self.assertEqual(item["last_filename"], "报告😀.md")

        with self.assertRaisesRegex(ValueError, "^reference_file_invalid$"):
            validate_reference_file("folder/\x00\x01\x1f", b"text", "text/plain")

    def test_total_size_deduplicates_same_asset_id(self) -> None:
        first = validate_reference_file("first.txt", b"123456", "text/plain")
        duplicate = reference_file_task_record(first)
        other = validate_reference_file("other.md", b"1234", "text/markdown")
        validate_reference_file_total([first, duplicate, other], max_total_bytes=10)
        with self.assertRaisesRegex(ValueError, "^reference_files_total_too_large$"):
            validate_reference_file_total([first, duplicate, other], max_total_bytes=9)
        self.assertEqual(len(dedupe_reference_file_records([duplicate, duplicate])), 1)


class ReferenceFileStorageTests(unittest.TestCase):
    @staticmethod
    def _file_snapshot(root: Path) -> dict[str, bytes]:
        return {
            str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

    def test_create_rejects_forged_asset_id_and_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = ReferenceFileStorage(tmp)
            valid = validate_reference_file("valid.txt", b"valid", "text/plain")
            forged = [
                replace(valid, asset_id="0" * 64),
                replace(valid, size_bytes=valid.size_bytes + 1),
            ]
            for item in forged:
                with self.subTest(asset_id=item.asset_id, size_bytes=item.size_bytes):
                    with self.assertRaisesRegex(ValueError, "^reference_file_invalid$"):
                        storage.create_or_touch(item)
            self.assertFalse(list(Path(tmp).glob("*/*.bin")))

    def test_create_rejects_an_existing_corrupt_blob(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = ReferenceFileStorage(tmp)
            valid = validate_reference_file("valid.txt", b"valid", "text/plain")
            item = storage.create_or_touch(valid)
            storage.file_path(item["id"]).write_bytes(b"fraud")
            with self.assertRaisesRegex(ValueError, "^reference_file_invalid$"):
                storage.create_or_touch(valid)

    def test_new_blob_write_failure_never_exposes_a_partial_final_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = ReferenceFileStorage(tmp)
            valid = validate_reference_file("valid.txt", b"valid", "text/plain")
            original_write_bytes = Path.write_bytes

            def partial_write_then_fail(path: Path, data: bytes) -> int:
                original_write_bytes(path, data[:1])
                raise OSError("simulated interrupted write")

            with mock.patch.object(Path, "write_bytes", new=partial_write_then_fail):
                with self.assertRaisesRegex(OSError, "simulated interrupted write"):
                    storage.create_or_touch(valid)
            self.assertFalse(list(Path(tmp).glob("*/*.bin")))
            self.assertFalse(list(Path(tmp).glob("*/*.tmp")))

    def test_identical_bytes_share_storage_but_keep_task_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = ReferenceFileStorage(Path(tmp))
            first = validate_reference_file("first.md", b"same", "text/markdown")
            second = validate_reference_file("second.txt", b"same", "text/plain")
            first_item = storage.create_or_touch(first)
            second_item = storage.create_or_touch(second)
            self.assertEqual(first_item["id"], second_item["id"])
            self.assertEqual(len(list(Path(tmp).glob("*/*.bin"))), 1)
            self.assertEqual(second_item["last_filename"], "second.txt")
            self.assertEqual(storage.file_path(first_item["id"]).read_bytes(), b"same")

    def test_same_name_different_bytes_get_different_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = ReferenceFileStorage(tmp)
            first = storage.create_or_touch(validate_reference_file("same.txt", b"first", "text/plain"))
            second = storage.create_or_touch(validate_reference_file("same.txt", b"second", "text/plain"))
            self.assertNotEqual(first["id"], second["id"])
            self.assertEqual(len(list(Path(tmp).glob("*/*.bin"))), 2)

    def test_reuse_updates_recent_metadata_without_changing_first_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = ReferenceFileStorage(tmp)
            first = storage.create_or_touch(validate_reference_file("first.md", b"same", "text/markdown"))
            reused = storage.create_or_touch(validate_reference_file("second.txt", b"same", "text/plain"))
            self.assertEqual(reused["first_filename"], "first.md")
            self.assertEqual(reused["last_filename"], "second.txt")
            self.assertEqual(reused["last_mime_type"], "text/plain")
            self.assertEqual(reused["last_family"], "text")
            self.assertNotEqual(reused["last_used_at"], first["last_used_at"])
            self.assertEqual(reused["used_count"], 2)

    def test_recent_sort_skips_corrupt_metadata_and_invalid_ids_fail_containment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = ReferenceFileStorage(tmp)
            older = storage.create_or_touch(validate_reference_file("older.txt", b"older", "text/plain"))
            newer = storage.create_or_touch(validate_reference_file("newer.txt", b"newer", "text/plain"))
            older_path = Path(tmp) / older["id"][:2] / f"{older['id']}.json"
            older_metadata = storage.read_item(older["id"])
            older_metadata["last_used_at"] = "2000-01-01T00:00:00+00:00"
            older_path.write_text(__import__("json").dumps(older_metadata), encoding="utf-8")
            corrupt_dir = Path(tmp) / "ff"
            corrupt_dir.mkdir()
            (corrupt_dir / ("f" * 64 + ".json")).write_text("{", encoding="utf-8")

            self.assertEqual([item["id"] for item in storage.list_recent()], [newer["id"], older["id"]])
            for invalid_id in ("../escape", "f" * 63, "F" * 64, "g" * 64):
                with self.subTest(invalid_id=invalid_id):
                    with self.assertRaises(ValueError):
                        storage.file_path(invalid_id)
            with self.assertRaises(FileNotFoundError):
                storage.file_path("0" * 64)
            with self.assertRaises(FileNotFoundError):
                storage.read_item("0" * 64)

    def test_batch_commit_revalidates_missing_and_corrupt_selected_before_upload_publish(self) -> None:
        for corruption in ("missing", "corrupt", "metadata_size_type"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                storage = ReferenceFileStorage(root)
                selected = storage.create_or_touch(validate_reference_file("selected.md", b"selected", "text/markdown"))
                selected_metadata = storage.read_item(selected["id"])
                selected_path = storage.file_path(selected["id"])
                if corruption == "missing":
                    selected_path.unlink()
                elif corruption == "corrupt":
                    selected_path.write_bytes(b"corrupt!")
                else:
                    metadata_path = root / selected["id"][:2] / f"{selected['id']}.json"
                    damaged_metadata = dict(selected_metadata)
                    damaged_metadata["size_bytes"] = str(damaged_metadata["size_bytes"])
                    metadata_path.write_text(json.dumps(damaged_metadata), encoding="utf-8")
                upload = validate_reference_file("new.md", b"new upload", "text/markdown")
                commit = getattr(storage, "commit_batch", None)
                self.assertIsNotNone(commit)

                with self.assertRaisesRegex(ValueError, "^reference_file_missing$"):
                    commit([upload], [selected["id"]])

                self.assertFalse((root / upload.asset_id[:2] / f"{upload.asset_id}.bin").exists())
                self.assertFalse((root / upload.asset_id[:2] / f"{upload.asset_id}.json").exists())
                self.assertEqual(storage._read_metadata(selected["id"], require_data=False)["used_count"], selected_metadata["used_count"])

    def test_batch_commit_rolls_back_new_files_and_existing_metadata_after_publish_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = ReferenceFileStorage(root)
            selected = storage.create_or_touch(validate_reference_file("selected.md", b"selected", "text/markdown"))
            upload = validate_reference_file("new.md", b"new upload", "text/markdown")
            commit = getattr(storage, "commit_batch", None)
            publish = getattr(storage, "_publish_staged", None)
            self.assertIsNotNone(commit)
            self.assertIsNotNone(publish)
            before = self._file_snapshot(root)
            selected_metadata_path = storage.root / selected["id"][:2] / f"{selected['id']}.json"

            def fail_after_selected_metadata_publish(staged_path: Path, final_path: Path) -> None:
                publish(staged_path, final_path)
                if final_path == selected_metadata_path:
                    raise OSError("simulated private metadata replace failure")

            with mock.patch.object(storage, "_publish_staged", side_effect=fail_after_selected_metadata_publish):
                with self.assertRaisesRegex(ValueError, "^reference_file_invalid$"):
                    commit([upload], [selected["id"]])

            self.assertEqual(self._file_snapshot(root), before)
            self.assertFalse(list(root.rglob("*.tmp")))

    def test_batch_commit_rolls_back_blob_publish_for_all_regular_exceptions(self) -> None:
        for exception_type in (OSError, RuntimeError):
            with self.subTest(exception_type=exception_type.__name__), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                storage = ReferenceFileStorage(root)
                upload = validate_reference_file("new.md", b"new upload", "text/markdown")
                publish = storage._publish_staged
                caught: Exception | None = None

                def publish_blob_then_fail(staged_path: Path, final_path: Path) -> None:
                    publish(staged_path, final_path)
                    if final_path.suffix == ".bin":
                        raise exception_type("simulated blob replace failure")

                with mock.patch.object(storage, "_publish_staged", side_effect=publish_blob_then_fail):
                    try:
                        storage.commit_batch([upload], [])
                    except Exception as exc:
                        caught = exc

                self.assertIsInstance(caught, ValueError)
                self.assertEqual(str(caught), "reference_file_invalid")
                self.assertEqual(self._file_snapshot(root), {})
                self.assertFalse(list(root.rglob("*.tmp")))

    def test_batch_commit_touch_staging_failure_preserves_usage_and_upload_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = ReferenceFileStorage(root)
            selected = storage.create_or_touch(validate_reference_file("selected.md", b"selected", "text/markdown"))
            upload = validate_reference_file("new.md", b"new upload", "text/markdown")
            before = self._file_snapshot(root)
            selected_metadata_path = storage.root / selected["id"][:2] / f"{selected['id']}.json"
            stage_metadata = storage._stage_metadata

            def fail_selected_touch(final_path: Path, metadata: dict[str, Any]) -> Path:
                if final_path == selected_metadata_path:
                    raise OSError("simulated touch staging failure")
                return stage_metadata(final_path, metadata)

            with mock.patch.object(storage, "_stage_metadata", side_effect=fail_selected_touch):
                with self.assertRaisesRegex(ValueError, "^reference_file_invalid$"):
                    storage.commit_batch([upload], [selected["id"]])

            self.assertEqual(self._file_snapshot(root), before)
            self.assertFalse(list(root.rglob("*.tmp")))

    def test_batch_commit_normal_and_duplicate_paths_increment_usage_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = ReferenceFileStorage(root)
            first = validate_reference_file("first.md", b"same bytes", "text/markdown")
            duplicate_upload = validate_reference_file("second.txt", b"same bytes", "text/plain")

            created_records = storage.commit_batch([first, duplicate_upload], [])
            reused_records = storage.commit_batch([duplicate_upload], [first.asset_id, first.asset_id])

            self.assertEqual(len(created_records), 1)
            self.assertEqual(len(reused_records), 1)
            self.assertEqual(reused_records[0]["filename"], "second.txt")
            self.assertEqual(storage.read_item(first.asset_id)["used_count"], 2)
            self.assertEqual(len(list(root.glob("*/*.bin"))), 1)
            self.assertEqual(len(list(root.glob("*/*.json"))), 1)

    def test_batch_commit_serializes_same_storage_concurrent_selected_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = ReferenceFileStorage(root)
            selected = storage.create_or_touch(validate_reference_file("selected.md", b"selected", "text/markdown"))
            selected_metadata = storage.read_item(selected["id"])
            upload = validate_reference_file("new.md", b"new upload", "text/markdown")
            commit = getattr(storage, "commit_batch", None)
            self.assertIsNotNone(commit)
            started = threading.Event()
            errors: list[Exception] = []

            def submit() -> None:
                started.set()
                try:
                    commit([upload], [selected["id"]])
                except Exception as exc:
                    errors.append(exc)

            with storage._lock:
                worker = threading.Thread(target=submit)
                worker.start()
                self.assertTrue(started.wait(timeout=2))
                storage.file_path(selected["id"]).unlink()
            worker.join(timeout=2)

            self.assertFalse(worker.is_alive())
            self.assertEqual([str(error) for error in errors], ["reference_file_missing"])
            self.assertFalse((root / upload.asset_id[:2] / f"{upload.asset_id}.bin").exists())
            self.assertEqual(storage._read_metadata(selected["id"], require_data=False)["used_count"], selected_metadata["used_count"])


class ReferenceFileRouteTests(unittest.TestCase):
    @staticmethod
    def _download_fixture(root: Path, data: bytes = b"trusted bytes") -> tuple[Any, dict[str, Any], Any]:
        app = create_app(
            output_root=root / "outputs",
            input_root=root / "inputs",
            client_factory=lambda: FakeImageClient(),
            auth_checker=lambda: True,
            auto_start_queue=False,
        )
        stored = app.state.ctx.reference_file_storage.create_or_touch(
            validate_reference_file("审查.txt", data, "text/plain")
        )
        task = app.state.ctx.storage.create_task("generate")
        app.state.ctx.storage.write_metadata(
            task.task_id,
            {
                "task_id": task.task_id,
                "status": "completed",
                "reference_files": [
                    reference_file_task_record(
                        {
                            **stored,
                            "filename": "任务审查.txt",
                            "mime_type": "text/plain",
                            "family": "text",
                        }
                    )
                ],
            },
        )
        return app, stored, task

    def _assert_corrupt_download_is_missing(self, app: Any, task_id: str) -> None:
        client = TestClient(app)
        download = client.get(f"/api/tasks/{task_id}/reference-files/1/download")
        detail = client.get(f"/api/tasks/{task_id}")

        self.assertEqual(download.status_code, 404)
        self.assertEqual(download.json(), {"detail": "Reference file not found"})
        serialized = json.dumps(download.json())
        self.assertNotIn(str(app.state.ctx.reference_file_root), serialized)
        self.assertNotIn("reference_file_invalid", serialized)
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.json()["task"]["reference_files"][0]["missing"])

    def test_recent_and_task_download_use_stored_bytes_and_task_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            validated = validate_reference_file("brief.md", b"# Brief\n", "text/markdown")
            self.assertIs(app.state.reference_file_storage, app.state.ctx.reference_file_storage)
            self.assertEqual(app.state.reference_file_root, root / "inputs" / "reference-files")
            self.assertIs(app.state.responses_file_unsupported_keys, app.state.ctx.responses_file_unsupported_keys)
            stored = app.state.ctx.reference_file_storage.create_or_touch(validated)
            task = app.state.ctx.storage.create_task("generate")
            app.state.ctx.storage.write_metadata(
                task.task_id,
                {
                    "task_id": task.task_id,
                    "created_at": "2026-07-10T00:00:00+00:00",
                    "mode": "generate",
                    "status": "completed",
                    "reference_files": [
                        reference_file_task_record(
                            {
                                **stored,
                                "filename": "历史简报.md",
                                "mime_type": "text/markdown",
                                "family": "text",
                            }
                        )
                    ],
                },
            )

            client = TestClient(app)
            recent = client.get("/api/reference-files/recent?limit=20")
            download = client.get(f"/api/tasks/{task.task_id}/reference-files/1/download")

            self.assertEqual(recent.status_code, 200)
            self.assertEqual(recent.json()["items"][0]["id"], stored["id"])
            self.assertEqual(download.status_code, 200)
            self.assertEqual(download.content, b"# Brief\n")
            disposition = download.headers["content-disposition"]
            self.assertIn('filename="', disposition)
            self.assertIn("filename*=UTF-8''", disposition)
            self.assertIn("%E5%8E%86%E5%8F%B2%E7%AE%80%E6%8A%A5.md", disposition)

    def test_task_detail_enriches_missing_file_without_input_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            task = app.state.ctx.storage.create_task("generate")
            app.state.ctx.storage.write_metadata(
                task.task_id,
                {
                    "task_id": task.task_id,
                    "created_at": "2026-07-10T00:00:00+00:00",
                    "mode": "generate",
                    "status": "failed",
                    "reference_files": [
                        {
                            "id": "a" * 64,
                            "filename": "missing.pdf",
                            "mime_type": "application/pdf",
                            "size_bytes": 10,
                            "family": "pdf",
                        }
                    ],
                },
            )

            response = TestClient(app).get(f"/api/tasks/{task.task_id}")

            self.assertEqual(response.status_code, 200)
            returned = response.json()["task"]
            self.assertTrue(returned["reference_files"][0]["missing"])
            self.assertEqual(
                returned["reference_files"][0]["download_url"],
                f"/api/tasks/{task.task_id}/reference-files/1/download",
            )
            self.assertNotIn("input_sources", returned)

    def test_deleting_one_task_keeps_shared_reference_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            stored = app.state.ctx.reference_file_storage.create_or_touch(
                validate_reference_file("shared.txt", b"shared bytes", "text/plain")
            )
            tasks = [app.state.ctx.storage.create_task("generate") for _ in range(2)]
            for index, task in enumerate(tasks, start=1):
                app.state.ctx.storage.write_metadata(
                    task.task_id,
                    {
                        "task_id": task.task_id,
                        "created_at": f"2026-07-10T00:00:0{index}+00:00",
                        "mode": "generate",
                        "status": "completed",
                        "reference_files": [
                            reference_file_task_record(
                                {
                                    **stored,
                                    "filename": f"shared-{index}.txt",
                                    "mime_type": "text/plain",
                                    "family": "text",
                                }
                            )
                        ],
                    },
                )

            client = TestClient(app)
            deleted = client.delete(f"/api/tasks/{tasks[0].task_id}")
            remaining = client.get(f"/api/tasks/{tasks[1].task_id}/reference-files/1/download")

            self.assertEqual(deleted.status_code, 200)
            self.assertEqual(remaining.status_code, 200)
            self.assertEqual(remaining.content, b"shared bytes")

    def test_recent_never_exposes_paths_or_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            stored = app.state.ctx.reference_file_storage.create_or_touch(
                validate_reference_file("private.md", b"super-secret-body", "text/markdown")
            )

            response = TestClient(app).get("/api/reference-files/recent")

            self.assertEqual(response.status_code, 200)
            item = response.json()["items"][0]
            self.assertEqual(item["id"], stored["id"])
            self.assertEqual(item["filename"], "private.md")
            self.assertEqual(item["mime_type"], "text/markdown")
            self.assertEqual(item["family"], "text")
            self.assertIs(item["missing"], False)
            self.assertLessEqual(
                set(item),
                {
                    "id",
                    "filename",
                    "mime_type",
                    "family",
                    "size_bytes",
                    "detail",
                    "created_at",
                    "last_used_at",
                    "used_count",
                    "missing",
                },
            )
            serialized = __import__("json").dumps(response.json())
            self.assertNotIn(str(app.state.ctx.reference_file_root), serialized)
            self.assertNotIn("super-secret-body", serialized)
            self.assertNotIn("file_data", serialized)
            self.assertNotIn("base64", serialized.lower())
            self.assertNotIn('"body"', serialized)

    def test_download_rejects_invalid_indexes_ids_and_missing_blobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            task = app.state.ctx.storage.create_task("generate")
            app.state.ctx.storage.write_metadata(
                task.task_id,
                {
                    "task_id": task.task_id,
                    "status": "completed",
                    "reference_files": [
                        {
                            "id": "../escape",
                            "filename": "bad.txt",
                            "mime_type": "text/plain",
                            "family": "text",
                            "size_bytes": 1,
                        }
                    ],
                },
            )
            client = TestClient(app)

            for url in (
                f"/api/tasks/{task.task_id}/reference-files/0/download",
                f"/api/tasks/{task.task_id}/reference-files/1/download",
                f"/api/tasks/{task.task_id}/reference-files/2/download",
                "/api/tasks/missing/reference-files/1/download",
            ):
                with self.subTest(url=url):
                    self.assertEqual(client.get(url).status_code, 404)

    def test_download_rejects_corrupt_asset_metadata_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app, stored, task = self._download_fixture(Path(tmp))
            storage = app.state.ctx.reference_file_storage
            metadata_path = storage.root / stored["id"][:2] / f"{stored['id']}.json"
            metadata_path.write_text("{", encoding="utf-8")

            self._assert_corrupt_download_is_missing(app, task.task_id)

    def test_download_rejects_asset_or_task_size_mismatch(self) -> None:
        for corrupt_source in ("asset_metadata", "task_record"):
            with self.subTest(corrupt_source=corrupt_source), tempfile.TemporaryDirectory() as tmp:
                app, stored, task = self._download_fixture(Path(tmp))
                storage = app.state.ctx.reference_file_storage
                if corrupt_source == "asset_metadata":
                    metadata_path = storage.root / stored["id"][:2] / f"{stored['id']}.json"
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                    metadata["size_bytes"] = int(metadata["size_bytes"]) + 1
                    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
                else:
                    task_metadata = app.state.ctx.storage.read_metadata(task.task_id)
                    task_metadata["reference_files"][0]["size_bytes"] += 1
                    app.state.ctx.storage.write_metadata(task.task_id, task_metadata)

                self._assert_corrupt_download_is_missing(app, task.task_id)

    def test_download_rejects_same_size_sha_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app, stored, task = self._download_fixture(Path(tmp), data=b"trusted bytes")
            storage = app.state.ctx.reference_file_storage
            storage.file_path(stored["id"]).write_bytes(b"tampered byte")

            self._assert_corrupt_download_is_missing(app, task.task_id)

    def test_image_task_omits_empty_reference_files_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            task = app.state.ctx.storage.create_task("generate")
            app.state.ctx.storage.write_metadata(
                task.task_id,
                {
                    "task_id": task.task_id,
                    "status": "completed",
                    "reference_files": [],
                    "reference_file_count": 0,
                },
            )

            returned = TestClient(app).get(f"/api/tasks/{task.task_id}").json()["task"]

            self.assertNotIn("reference_files", returned)
            self.assertNotIn("reference_file_count", returned)


class ReferenceFileSubmissionTests(unittest.TestCase):
    @staticmethod
    def _app(root: Path) -> Any:
        return create_app(
            output_root=root / "outputs",
            input_root=root / "inputs",
            client_factory=lambda: FakeImageClient(),
            auth_checker=lambda: True,
            auto_start_queue=False,
        )

    def test_generate_responses_stores_file_reference_without_payload_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(Path(tmp))

            response = TestClient(app).post(
                "/api/generate",
                data={"prompt": "Use the brief", "codex_mode": "responses"},
                files={"reference_files": ("brief.md", b"UNIQUE-PLAINTEXT", "text/markdown")},
            )

            self.assertEqual(response.status_code, 200)
            task = response.json()["task"]
            self.assertEqual(task["reference_file_count"], 1)
            self.assertEqual(task["reference_files"][0]["filename"], "brief.md")
            request_text = app.state.ctx.storage.request_path(task["task_id"]).read_text(encoding="utf-8")
            self.assertIn("webui_file_refs", request_text)
            self.assertNotIn("UNIQUE-PLAINTEXT", request_text)
            self.assertNotIn("data:text/markdown;base64", request_text)

    def test_images_backend_rejects_before_storing_upload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(Path(tmp))

            response = TestClient(app).post(
                "/api/generate",
                data={"prompt": "Use the brief", "codex_mode": "images"},
                files={"reference_files": ("brief.md", b"brief", "text/markdown")},
            )

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["detail"]["code"], "reference_files_require_responses")
            self.assertEqual(list(app.state.ctx.reference_file_root.glob("*/*.bin")), [])

    def test_edit_file_does_not_satisfy_image_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(Path(tmp))

            response = TestClient(app).post(
                "/api/edit",
                data={"prompt": "Edit", "codex_mode": "responses"},
                files={"reference_files": ("brief.md", b"brief", "text/markdown")},
            )

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["detail"], "At least one image is required")
            self.assertEqual(list(app.state.ctx.reference_file_root.glob("*/*.bin")), [])

    def test_edit_empty_image_part_does_not_persist_reference_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(Path(tmp))
            storage = app.state.ctx.reference_file_storage
            selected = storage.create_or_touch(
                validate_reference_file("selected.md", b"selected", "text/markdown")
            )
            before = ReferenceFileStorageTests._file_snapshot(storage.root)

            response = TestClient(app).post(
                "/api/edit",
                data={
                    "prompt": "Edit",
                    "codex_mode": "responses",
                    "reference_file_ids": selected["id"],
                },
                files=[
                    ("images", ("empty.png", b"", "image/png")),
                    ("reference_files", ("brief.md", b"brief", "text/markdown")),
                ],
            )

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["detail"], "At least one image is required")
            self.assertEqual(ReferenceFileStorageTests._file_snapshot(storage.root), before)
            self.assertEqual(app.state.ctx.storage.list_tasks(), [])

    def test_edit_backend_gate_precedes_empty_image_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(Path(tmp))

            response = TestClient(app).post(
                "/api/edit",
                data={"prompt": "Edit", "codex_mode": "images"},
                files=[
                    ("images", ("empty.png", b"", "image/png")),
                    ("reference_files", ("brief.md", b"brief", "text/markdown")),
                ],
            )

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["detail"]["code"], "reference_files_require_responses")
            self.assertEqual(list(app.state.ctx.reference_file_root.glob("*/*")), [])
            self.assertEqual(app.state.ctx.storage.list_tasks(), [])

    def test_uploaded_and_selected_duplicates_are_one_task_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(Path(tmp))
            client = TestClient(app)
            first = client.post(
                "/api/generate",
                data={"prompt": "First", "codex_mode": "responses"},
                files={"reference_files": ("first.md", b"same bytes", "text/markdown")},
            )
            self.assertEqual(first.status_code, 200)
            asset_id = first.json()["task"]["reference_files"][0]["id"]

            second = client.post(
                "/api/generate",
                data={
                    "prompt": "Reuse",
                    "codex_mode": "responses",
                    "reference_file_ids": asset_id,
                },
                files={"reference_files": ("second.md", b"same bytes", "text/markdown")},
            )

            self.assertEqual(second.status_code, 200)
            self.assertEqual(second.json()["task"]["reference_file_count"], 1)
            self.assertEqual(len(second.json()["task"]["reference_files"]), 1)
            self.assertEqual(len(list(app.state.ctx.reference_file_root.glob("*/*.bin"))), 1)

    def test_invalid_batch_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(Path(tmp))

            response = TestClient(app).post(
                "/api/generate",
                data={"prompt": "Batch", "codex_mode": "responses"},
                files=[
                    ("reference_files", ("valid.md", b"valid", "text/markdown")),
                    ("reference_files", ("invalid.ods", b"invalid", "application/vnd.oasis.opendocument.spreadsheet")),
                ],
            )

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["detail"]["code"], "reference_file_type_unsupported")
            self.assertEqual(list(app.state.ctx.reference_file_root.glob("*/*.bin")), [])

    def test_selected_missing_or_invalid_id_is_stable_404(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(Path(tmp))
            for asset_id in ("0" * 64, "not-an-id"):
                with self.subTest(asset_id=asset_id):
                    response = TestClient(app).post(
                        "/api/generate",
                        data={
                            "prompt": "Missing",
                            "codex_mode": "responses",
                            "reference_file_ids": asset_id,
                        },
                    )
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(response.json()["detail"]["code"], "reference_file_missing")

    def test_selected_deleted_between_prevalidation_and_commit_does_not_persist_upload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = self._app(root)
            storage = app.state.ctx.reference_file_storage
            selected = storage.create_or_touch(validate_reference_file("selected.md", b"selected", "text/markdown"))
            used_count = storage.read_item(selected["id"])["used_count"]
            original_commit = getattr(storage, "commit_batch", None)
            self.assertIsNotNone(original_commit)

            def delete_selected_then_commit(uploads: Any, asset_ids: Any) -> Any:
                storage.file_path(selected["id"]).unlink()
                return original_commit(uploads, asset_ids)

            with mock.patch.object(storage, "commit_batch", side_effect=delete_selected_then_commit):
                response = TestClient(app).post(
                    "/api/generate",
                    data={
                        "prompt": "Race",
                        "codex_mode": "responses",
                        "reference_file_ids": selected["id"],
                    },
                    files={"reference_files": ("new.md", b"new upload", "text/markdown")},
                )

            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["detail"]["code"], "reference_file_missing")
            self.assertNotIn(str(storage.root), response.text)
            self.assertEqual(storage._read_metadata(selected["id"], require_data=False)["used_count"], used_count)
            upload_id = validate_reference_file("new.md", b"new upload", "text/markdown").asset_id
            self.assertFalse((storage.root / upload_id[:2] / f"{upload_id}.bin").exists())

    def test_metadata_publish_failure_returns_sanitized_400_and_restores_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = self._app(root)
            storage = app.state.ctx.reference_file_storage
            selected = storage.create_or_touch(validate_reference_file("selected.md", b"selected", "text/markdown"))
            before = ReferenceFileStorageTests._file_snapshot(storage.root)
            publish = getattr(storage, "_publish_staged", None)
            self.assertIsNotNone(publish)
            selected_metadata_path = storage.root / selected["id"][:2] / f"{selected['id']}.json"

            def fail_after_selected_metadata_publish(staged_path: Path, final_path: Path) -> None:
                publish(staged_path, final_path)
                if final_path == selected_metadata_path:
                    raise OSError("/private/reference-file-metadata.json")

            with mock.patch.object(storage, "_publish_staged", side_effect=fail_after_selected_metadata_publish):
                response = TestClient(app).post(
                    "/api/generate",
                    data={
                        "prompt": "Failure",
                        "codex_mode": "responses",
                        "reference_file_ids": selected["id"],
                    },
                    files={"reference_files": ("new.md", b"new upload", "text/markdown")},
                )

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["detail"]["code"], "reference_file_invalid")
            self.assertNotIn("private", response.text)
            self.assertNotIn(str(storage.root), response.text)
            self.assertEqual(ReferenceFileStorageTests._file_snapshot(storage.root), before)

    def test_request_redaction_covers_file_data_and_generic_data_urls(self) -> None:
        redact = getattr(webui_app, "_redact_request_data", None)
        self.assertIsNotNone(redact)
        result = redact(
            {
                "file_data": "plaintext-secret",
                "nested": ["data:application/pdf;base64,SECRET", "safe"],
            }
        )
        self.assertNotIn("plaintext-secret", json.dumps(result))
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertEqual(result["nested"][1], "safe")

    def test_reference_files_survive_task_metadata_transitions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = TaskStorage(Path(tmp) / "outputs")
            task = storage.create_task("generate")
            refs = [reference_file_task_record(validate_reference_file("brief.md", b"brief", "text/markdown"))]
            common = {
                "created_at": "2026-07-11T00:00:00+00:00",
                "mode": "generate",
                "prompt": "Use brief",
                "prompt_for_model": "Use brief",
                "params": {"n": 1},
                "gallery_refs": [],
                "reference_assets": [],
                "reference_files": refs,
            }
            transition_common = {key: value for key, value in common.items() if key != "reference_files"}

            _write_queued_metadata(
                storage,
                task.task_id,
                input_files=[],
                mask_file=None,
                **common,
            )
            self._assert_task_reference_state(storage.read_metadata(task.task_id), refs)
            _write_running_metadata(storage, task.task_id, input_files=[], **transition_common)
            self._assert_task_reference_state(storage.read_metadata(task.task_id), refs)
            _write_progress_metadata(
                storage,
                task.task_id,
                total_count=1,
                results=[],
                output_paths=[],
                input_files=[],
                request_payload={},
                output_records=[],
                **transition_common,
            )
            self._assert_task_reference_state(storage.read_metadata(task.task_id), refs)
            _fail_task(
                storage,
                task.task_id,
                input_files=[],
                request_payload={},
                exc=RuntimeError("failed"),
                **transition_common,
            )
            self._assert_task_reference_state(storage.read_metadata(task.task_id), refs)

    def _assert_task_reference_state(self, metadata: dict[str, Any], refs: list[dict[str, Any]]) -> None:
        self.assertEqual(metadata["reference_files"], refs)
        self.assertEqual(metadata["reference_file_count"], 1)
        self.assertEqual(metadata["input_files"], [])
        self.assertEqual(metadata["input_sources"], [])


class ReferenceFileExecutionTests(unittest.TestCase):
    def test_codex_file_task_is_not_silently_claimed_by_api(self) -> None:
        from codex_image.webui.queue import QueueChannel
        from codex_image.webui.settings_store import ApiSettings, AuthSettings

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth_settings_path = root / "auth.json"
            api_settings_path = root / "api.json"
            AuthSettings(auth_settings_path).write_source("codex")
            ApiSettings(api_settings_path).write(
                {
                    "active_provider_id": "provider-a",
                    "providers": [
                        {
                            "id": "provider-a",
                            "name": "Provider A",
                            "base_url": "https://provider-a.example.com/v1",
                            "api_key": "test-key",
                            "image_model": "gpt-image-2",
                            "api_mode": "responses",
                            "images_concurrency": 3,
                        }
                    ],
                }
            )
            fake = CapturingResponsesClient()
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                auth_settings_path=auth_settings_path,
                api_settings_path=api_settings_path,
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            created = TestClient(app).post(
                "/api/generate",
                data={"prompt": "Use the PDF", "codex_mode": "responses"},
                files={"reference_files": ("brief.pdf", b"%PDF-1.4\nbrief", "application/pdf")},
            ).json()["task"]
            app.state.queue_manager.channels = [QueueChannel("api:default:1", "api")]

            asyncio.run(app.state.queue_manager.run_available_once())

            metadata = app.state.ctx.storage.read_metadata(created["task_id"])
            self.assertEqual(metadata["requested_backend"], "codex_responses")
            self.assertNotIn("backend", metadata)
            self.assertEqual(app.state.queue_storage.read_state()["waiting"], [created["task_id"]])
            self.assertEqual(fake.reference_file_snapshots, [])
            stored_request = json.loads(app.state.ctx.storage.request_path(created["task_id"]).read_text(encoding="utf-8"))
            self.assertEqual(stored_request["webui_requested_backend"], "codex_responses")
            self.assertNotIn("api_key", json.dumps(stored_request))
            self.assertNotIn("file_data", json.dumps(stored_request))

    def test_completed_without_image_echo_never_reaches_queue_metadata(self) -> None:
        private_text = "QUEUE COMPLETED PRIVATE TEXT"

        class CompletedEchoClient(CapturingResponsesClient):
            def generate_image(self, **kwargs: Any):
                files = kwargs.get("reference_files") or []
                sensitive_values: set[str] = set()
                for file in files:
                    sensitive_values.update({file.file_data, file.file_data.rsplit(",", 1)[-1], private_text})
                event = {
                    "type": "response.completed",
                    "response": {
                        "output": [{"type": "message", "content": [{"type": "output_text", "text": private_text}]}],
                    },
                }
                return CodexImageClient.parse_sse_response(
                    object.__new__(CodexImageClient),
                    f"data: {json.dumps(event)}\n\n".encode(),
                    sensitive_values=sensitive_values,
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=CompletedEchoClient,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
                auto_retry=False,
            )
            created = TestClient(app).post(
                "/api/generate",
                data={"prompt": "Use it", "codex_mode": "responses"},
                files={"reference_files": ("brief.md", private_text.encode(), "text/markdown")},
            ).json()["task"]

            with self.assertRaises(Exception):
                asyncio.run(app.state.queue_manager.run_available_once())

            metadata = app.state.ctx.storage.read_metadata(created["task_id"])
            self.assertNotIn(private_text, json.dumps(metadata))

    def test_message_only_provider_echo_never_reaches_queue_metadata_or_status(self) -> None:
        private_text = "QUEUE-PRIVATE-DOCUMENT-TEXT"

        class MessageEchoClient(CapturingResponsesClient):
            def generate_image(self, **kwargs: Any):
                files = kwargs.get("reference_files") or []
                sensitive_values = [file.file_data for file in files]
                raise ResponsesRequestError(
                    f"provider rejected {private_text}",
                    status=400,
                    body=json.dumps({"error": {"message": f"provider rejected {private_text}"}}),
                    sensitive_values=sensitive_values,
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=MessageEchoClient,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
                auto_retry=False,
            )
            created = TestClient(app).post(
                "/api/generate",
                data={"prompt": "Use it", "codex_mode": "responses"},
                files={"reference_files": ("brief.md", private_text.encode("utf-8"), "text/markdown")},
            ).json()["task"]

            with self.assertRaises(Exception):
                asyncio.run(app.state.queue_manager.run_available_once())

            metadata = app.state.ctx.storage.read_metadata(created["task_id"])
            serialized = json.dumps(metadata)
            self.assertNotIn(private_text, serialized)
            self.assertNotIn(base64.b64encode(private_text.encode()).decode(), serialized)
            self.assertNotIn(private_text, str(metadata.get("error") or ""))
            self.assertNotIn(private_text, str(metadata.get("last_error") or ""))

    def test_queue_resolves_inline_file_only_at_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = CapturingResponsesClient()
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            created = TestClient(app).post(
                "/api/generate",
                data={"prompt": "Use it", "codex_mode": "responses"},
                files={"reference_files": ("brief.md", b"# Brief", "text/markdown")},
            ).json()["task"]

            asyncio.run(app.state.queue_manager.run_available_once())

            self.assertEqual(len(fake.reference_file_snapshots), 1)
            call_file = fake.reference_file_snapshots[0][0]
            self.assertEqual(call_file.filename, "brief.md")
            self.assertEqual(call_file.mime_type, "text/markdown")
            self.assertTrue(call_file.file_data.startswith("data:text/markdown;base64,"))
            self.assertEqual(fake.reference_file_lists, [[]])
            persisted = app.state.ctx.storage.request_path(created["task_id"]).read_text(encoding="utf-8")
            self.assertNotIn("data:text/markdown;base64,", persisted)
            self.assertNotIn("# Brief", persisted)

    def test_each_output_resolves_a_fresh_ephemeral_file_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = CapturingResponsesClient()
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            response = TestClient(app).post(
                "/api/generate",
                data={"prompt": "Use it", "codex_mode": "responses", "n": "2"},
                files={"reference_files": ("brief.md", b"# Brief", "text/markdown")},
            )
            self.assertEqual(response.status_code, 200)

            asyncio.run(app.state.queue_manager.run_available_once())

            self.assertEqual(len(fake.reference_file_snapshots), 2)
            self.assertIsNot(fake.reference_file_lists[0], fake.reference_file_lists[1])
            self.assertEqual(fake.reference_file_lists, [[], []])

    def test_corrupt_file_is_stable_non_retryable_reference_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = CapturingResponsesClient()
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
                auto_retry=True,
            )
            created = TestClient(app).post(
                "/api/generate",
                data={"prompt": "Use it", "codex_mode": "responses"},
                files={"reference_files": ("brief.md", b"# Brief", "text/markdown")},
            ).json()["task"]
            asset_id = created["reference_files"][0]["id"]
            app.state.ctx.reference_file_storage.file_path(asset_id).write_bytes(b"# Wrong")

            with self.assertRaises(Exception):
                asyncio.run(app.state.queue_manager.run_available_once())

            metadata = app.state.ctx.storage.read_metadata(created["task_id"])
            self.assertEqual(metadata["status"], "failed")
            self.assertEqual(metadata["error"], "reference_file_missing")
            self.assertEqual(fake.generate_calls, [])
            self.assertEqual(app.state.ctx.queue_storage.read_state()["waiting"], [])

    def test_non_list_reference_file_metadata_is_stable_missing(self) -> None:
        for corrupt_value in ({"id": "not-a-list"}, "not-a-list"):
            with self.subTest(value_type=type(corrupt_value).__name__), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                fake = CapturingResponsesClient()
                app = create_app(
                    output_root=root / "outputs",
                    input_root=root / "inputs",
                    client_factory=lambda: fake,
                    auth_checker=lambda: True,
                    batch_delay_seconds=0,
                    auto_start_queue=False,
                    auto_retry=True,
                )
                created = TestClient(app).post(
                    "/api/generate",
                    data={"prompt": "Use it", "codex_mode": "responses"},
                    files={"reference_files": ("brief.md", b"# Brief", "text/markdown")},
                ).json()["task"]
                metadata = app.state.ctx.storage.read_metadata(created["task_id"])
                metadata["reference_files"] = corrupt_value
                app.state.ctx.storage.write_metadata(created["task_id"], metadata)

                with self.assertRaises(Exception):
                    asyncio.run(app.state.queue_manager.run_available_once())

                failed = app.state.ctx.storage.read_metadata(created["task_id"])
                self.assertEqual(failed["status"], "failed")
                self.assertEqual(failed["error"], "reference_file_missing")
                self.assertEqual(fake.generate_calls, [])
                self.assertEqual(app.state.ctx.queue_storage.read_state()["waiting"], [])

    def test_edit_responses_passes_reference_files_without_changing_image_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = CapturingResponsesClient()
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            png = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAIAAAADCAIAAAA2iEnWAAAAFElEQVR4nGNkZGJmYGBgYgADKAUAAMQADPiqQJgAAAAASUVORK5CYII="
            )
            response = TestClient(app).post(
                "/api/edit",
                data={"prompt": "Edit it", "codex_mode": "responses"},
                files=[
                    ("images", ("input.png", png, "image/png")),
                    ("reference_files", ("brief.md", b"# Brief", "text/markdown")),
                ],
            )
            self.assertEqual(response.status_code, 200)

            asyncio.run(app.state.queue_manager.run_available_once())

            self.assertEqual(len(fake.edit_calls), 1)
            self.assertEqual(fake.generate_calls, [])
            self.assertEqual(fake.reference_file_snapshots[0][0].filename, "brief.md")

    def test_direct_images_branch_does_not_read_or_pass_reference_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = CapturingResponsesClient()
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            created = TestClient(app).post(
                "/api/generate",
                data={"prompt": "Use it", "codex_mode": "responses", "n": "2"},
                files={"reference_files": ("brief.md", b"# Brief", "text/markdown")},
            ).json()["task"]
            metadata = app.state.ctx.storage.read_metadata(created["task_id"])
            metadata["requested_backend"] = "codex_images"
            metadata["params"]["codex_mode"] = "images"
            metadata.pop("generation_snapshot", None)
            app.state.ctx.storage.write_metadata(created["task_id"], metadata)
            asset_id = created["reference_files"][0]["id"]
            app.state.ctx.reference_file_storage.file_path(asset_id).unlink()

            with mock.patch("codex_image.webui.executor.CodexImagesImageClient", CapturingResponsesClient):
                asyncio.run(app.state.queue_manager.run_available_once())

            self.assertEqual(len(fake.generate_calls), 2)
            self.assertTrue(all("reference_files" not in call for call in fake.generate_calls))
            self.assertEqual(fake.reference_file_snapshots, [])


class ReferenceFileCapabilityTests(unittest.TestCase):
    def _module(self) -> Any:
        try:
            return importlib.import_module("codex_image.webui.reference_file_capabilities")
        except ModuleNotFoundError:
            self.fail("reference_file_capabilities module is missing")

    def test_capability_key_preserves_exact_contract_identity(self) -> None:
        module = self._module()
        key = module.reference_file_capability_key(
            requested_backend="openai_responses",
            provider_id="provider-a",
            endpoint="https://api.example.com/v1/responses/",
            main_model="gpt-5.4-mini",
        )
        self.assertEqual(
            key,
            ("openai_responses", "provider-a", "https://api.example.com/v1/responses", "gpt-5.4-mini"),
        )

    def test_explicit_input_file_schema_rejection_is_classified(self) -> None:
        module = self._module()
        for status, message in (
            (400, "Unknown content type input_file"),
            (422, "file_data is not allowed"),
            (200, "Unrecognized file content part"),
        ):
            with self.subTest(status=status, message=message):
                error = ResponsesRequestError(
                    "bad input",
                    status=status,
                    body=json.dumps({"error": {"message": message}}),
                )
                self.assertTrue(module.is_explicit_file_input_rejection(error))

    def test_non_schema_file_and_transient_errors_are_not_classified(self) -> None:
        module = self._module()
        cases = (
            (400, "Unsupported spreadsheet MIME"),
            (400, "Unsupported PDF document type"),
            (400, "Unsupported format for input_file"),
            (401, "Unknown input_file"),
            (429, "Unknown input_file rate limit"),
            (500, "Unknown input_file"),
        )
        for status, message in cases:
            with self.subTest(status=status, message=message):
                error = ResponsesRequestError(
                    "request failed",
                    status=status,
                    body=json.dumps({"error": {"message": message}}),
                )
                self.assertFalse(module.is_explicit_file_input_rejection(error))
        self.assertFalse(module.is_explicit_file_input_rejection(TimeoutError("input_file timed out")))

    def test_request_echo_cannot_supply_schema_tokens_to_unrelated_error(self) -> None:
        module = self._module()
        body = json.dumps(
            {
                "error": {"code": "unsupported_model", "message": "The selected model is unsupported"},
                "request": {
                    "input": [
                        {
                            "type": "input_file",
                            "file_data": "data:text/plain;base64,U0VDUkVU",
                        }
                    ]
                },
            }
        )
        error = ResponsesRequestError("request failed", status=400, body=body)

        self.assertFalse(module.is_explicit_file_input_rejection(error))

    def test_non_json_classifier_requires_schema_and_rejection_tokens_near_each_other(self) -> None:
        module = self._module()
        far_apart = ResponsesRequestError(
            "request failed",
            status=400,
            body="unsupported model " + ("x" * 600) + " echoed input_file",
        )
        adjacent_request_echo = ResponsesRequestError(
            "request failed",
            status=400,
            body='unsupported_model: selected model is unsupported; request={"type":"input_file","file_data":"echo"}',
        )
        explicit_rejections = (
            "unknown content type input_file",
            "input_file is not allowed",
            "unsupported input_file",
            "unrecognized input_file",
            "file_data is not allowed",
            "unknown field input_file",
            "unknown parameter file_data",
        )

        self.assertFalse(module.is_explicit_file_input_rejection(far_apart))
        self.assertFalse(module.is_explicit_file_input_rejection(adjacent_request_echo))
        for phrase in explicit_rejections:
            adjacent = ResponsesRequestError("request failed", status=400, body=phrase)
            with self.subTest(phrase=phrase):
                self.assertTrue(module.is_explicit_file_input_rejection(adjacent))

    def test_explicit_schema_rejection_is_non_retryable_and_caches_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = RejectingResponsesClient(
                ResponsesRequestError(
                    "bad input",
                    status=400,
                    body='{"error":{"message":"Unknown content type input_file"}}',
                )
            )
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
                auto_retry=True,
            )
            created = TestClient(app).post(
                "/api/generate",
                data={"prompt": "Use it", "codex_mode": "responses"},
                files={"reference_files": ("brief.md", b"# Brief", "text/markdown")},
            ).json()["task"]

            with self.assertRaises(Exception):
                asyncio.run(app.state.queue_manager.run_available_once())

            metadata = app.state.ctx.storage.read_metadata(created["task_id"])
            self.assertEqual(len(fake.generate_calls), 1)
            self.assertEqual(metadata["status"], "failed")
            self.assertEqual(metadata["error"], "provider_reference_files_unsupported")
            self.assertNotIn("Unknown content type input_file", json.dumps(metadata))
            self.assertEqual(
                app.state.ctx.responses_file_unsupported_keys,
                {("codex_responses", "codex", DEFAULT_RESPONSES_URL, DEFAULT_MAIN_MODEL)},
            )
            self.assertEqual(app.state.ctx.queue_storage.read_state()["waiting"], [])

    def test_cached_key_rejects_before_reading_or_storing_upload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            app.state.ctx.responses_file_unsupported_keys.add(
                ("codex_responses", "codex", DEFAULT_RESPONSES_URL, DEFAULT_MAIN_MODEL)
            )

            response = TestClient(app).post(
                "/api/generate",
                data={"prompt": "Use it", "codex_mode": "responses"},
                files={"reference_files": ("brief.md", b"# Brief", "text/markdown")},
            )

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["detail"]["code"], "provider_reference_files_unsupported")
            self.assertEqual(list(app.state.ctx.reference_file_root.glob("*/*.bin")), [])
            self.assertEqual(app.state.ctx.storage.list_tasks(), [])

    def test_empty_main_model_hits_default_key_before_upload_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            app.state.ctx.responses_file_unsupported_keys.add(
                ("codex_responses", "codex", DEFAULT_RESPONSES_URL, DEFAULT_MAIN_MODEL)
            )

            response = TestClient(app).post(
                "/api/generate",
                data={"prompt": "Use it", "codex_mode": "responses", "main_model": "   "},
                files={"reference_files": ("brief.md", b"# Brief", "text/markdown")},
            )

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["detail"]["code"], "provider_reference_files_unsupported")
            self.assertEqual(list(app.state.ctx.reference_file_root.glob("*/*.bin")), [])
            self.assertEqual(app.state.ctx.storage.list_tasks(), [])

    def test_blank_main_model_persists_and_executes_default_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = CapturingResponsesClient()
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )
            created = TestClient(app).post(
                "/api/generate",
                data={"prompt": "Use it", "codex_mode": "responses", "main_model": "   "},
                files={"reference_files": ("brief.md", b"# Brief", "text/markdown")},
            ).json()["task"]

            self.assertEqual(created["params"]["main_model"], DEFAULT_MAIN_MODEL)
            asyncio.run(app.state.queue_manager.run_available_once())
            self.assertEqual(fake.generate_calls[0]["main_model"], DEFAULT_MAIN_MODEL)

    def test_main_model_change_uses_a_new_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            app.state.ctx.responses_file_unsupported_keys.add(
                ("codex_responses", "codex", DEFAULT_RESPONSES_URL, DEFAULT_MAIN_MODEL)
            )

            response = TestClient(app).post(
                "/api/generate",
                data={"prompt": "Use it", "codex_mode": "responses", "main_model": "gpt-new"},
                files={"reference_files": ("brief.md", b"# Brief", "text/markdown")},
            )

            self.assertEqual(response.status_code, 200)

    def test_format_auth_rate_limit_timeout_and_server_errors_do_not_cache(self) -> None:
        errors: tuple[Exception, ...] = (
            ResponsesRequestError(
                "bad spreadsheet",
                status=400,
                body='{"error":{"message":"Unsupported spreadsheet MIME for input_file"}}',
            ),
            ResponsesRequestError("unauthorized", status=401, body='{"error":{"message":"Unauthorized"}}'),
            ResponsesRequestError("limited", status=429, body='{"error":{"message":"Rate limit"}}'),
            TimeoutError("request timed out"),
            ResponsesRequestError("server failed", status=500, body='{"error":{"message":"Server error"}}'),
        )
        for index, error in enumerate(errors):
            with self.subTest(error=type(error).__name__, index=index), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                fake = RejectingResponsesClient(error)
                app = create_app(
                    output_root=root / "outputs",
                    input_root=root / "inputs",
                    client_factory=lambda: fake,
                    auth_checker=lambda: True,
                    batch_delay_seconds=0,
                    auto_start_queue=False,
                    auto_retry=True,
                )
                created = TestClient(app).post(
                    "/api/generate",
                    data={"prompt": "Use it", "codex_mode": "responses"},
                    files={"reference_files": ("brief.md", b"# Brief", "text/markdown")},
                ).json()["task"]

                with self.assertRaises(Exception):
                    asyncio.run(app.state.queue_manager.run_available_once())

                metadata = app.state.ctx.storage.read_metadata(created["task_id"])
                self.assertEqual(metadata["status"], "queued")
                self.assertEqual(app.state.ctx.responses_file_unsupported_keys, set())
                self.assertEqual(app.state.ctx.queue_storage.read_state()["waiting"], [created["task_id"]])

    def test_restart_reuses_task_file_but_clears_capability_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=lambda: FakeImageClient(),
                auth_checker=lambda: True,
                auto_start_queue=False,
            )
            created = TestClient(first_app).post(
                "/api/generate",
                data={"prompt": "Use it", "codex_mode": "responses"},
                files={"reference_files": ("brief.md", b"# Brief", "text/markdown")},
            ).json()["task"]
            first_app.state.ctx.responses_file_unsupported_keys.add(
                ("codex_responses", "codex", DEFAULT_RESPONSES_URL, DEFAULT_MAIN_MODEL)
            )

            fake = CapturingResponsesClient()
            restarted = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
            )

            self.assertEqual(restarted.state.ctx.responses_file_unsupported_keys, set())
            asyncio.run(restarted.state.queue_manager.run_available_once())
            self.assertEqual(restarted.state.ctx.storage.read_metadata(created["task_id"])["status"], "completed")
            self.assertEqual(fake.reference_file_snapshots[0][0].filename, "brief.md")

    def test_api_provider_endpoint_or_main_model_change_uses_a_new_key(self) -> None:
        from codex_image.webui.settings_store import ApiSettings, AuthSettings

        actual = ("openai_responses", "provider-b", "https://b.example.com/v1/responses", DEFAULT_MAIN_MODEL)
        cached_variants = (
            ("openai_responses", "provider-a", actual[2], actual[3]),
            ("openai_responses", actual[1], "https://old.example.com/v1/responses", actual[3]),
            ("openai_responses", actual[1], actual[2], "gpt-old"),
        )
        for index, cached_key in enumerate(cached_variants):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                auth_settings_path = root / "auth.json"
                api_settings_path = root / "api.json"
                AuthSettings(auth_settings_path).write_source("api")
                ApiSettings(api_settings_path).write(
                    {
                        "active_provider_id": "provider-b",
                        "providers": [
                            {
                                "id": "provider-b",
                                "name": "Provider B",
                                "base_url": "https://b.example.com/v1/responses/",
                                "api_key": "test-key",
                                "image_model": "gpt-image-2",
                                "api_mode": "responses",
                            }
                        ],
                    }
                )
                app = create_app(
                    output_root=root / "outputs",
                    input_root=root / "inputs",
                    auth_settings_path=auth_settings_path,
                    api_settings_path=api_settings_path,
                    auth_checker=lambda: True,
                    auto_start_queue=False,
                )
                app.state.ctx.responses_file_unsupported_keys.add(cached_key)

                response = TestClient(app).post(
                    "/api/generate",
                    data={
                        "prompt": "Use it",
                        "api_mode": "responses",
                        "api_provider_id": "provider-b",
                        "main_model": DEFAULT_MAIN_MODEL,
                    },
                    files={"reference_files": ("brief.md", b"# Brief", "text/markdown")},
                )

                self.assertEqual(response.status_code, 200)

    def test_inflight_api_rejection_uses_immutable_provider_contract_snapshot(self) -> None:
        from codex_image.webui.settings_store import ApiSettings, AuthSettings

        scenarios = (
            (
                "endpoint_changed",
                {
                    "active_provider_id": "provider-a",
                    "providers": [
                        {
                            "id": "provider-a",
                            "name": "Provider A",
                            "base_url": "https://new-a.example.com/v1",
                            "api_key": "new-key-a",
                            "image_model": "gpt-image-2",
                            "api_mode": "responses",
                            "images_concurrency": 1,
                        },
                        {
                            "id": "provider-b",
                            "name": "Provider B",
                            "base_url": "https://b.example.com/v1",
                            "api_key": "key-b",
                            "image_model": "gpt-image-2",
                            "api_mode": "responses",
                            "images_concurrency": 1,
                        },
                    ],
                },
                "provider-a",
            ),
            (
                "pinned_provider_deleted",
                {
                    "active_provider_id": "provider-b",
                    "providers": [
                        {
                            "id": "provider-b",
                            "name": "Provider B",
                            "base_url": "https://b.example.com/v1",
                            "api_key": "key-b",
                            "image_model": "gpt-image-2",
                            "api_mode": "responses",
                            "images_concurrency": 1,
                        }
                    ],
                },
                "provider-b",
            ),
        )

        for scenario, changed_settings, next_provider_id in scenarios:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                class BlockingRejectingApiClient(CapturingResponsesClient):
                    entered = threading.Event()
                    release = threading.Event()

                    def __init__(self, *, api_key: str, base_url: str, image_model: str, **_: Any) -> None:
                        super().__init__()
                        self.api_key = api_key
                        self.base_url = base_url
                        self.image_model = image_model

                    def generate_image(self, **kwargs: Any):
                        self._capture_reference_files(kwargs)
                        self.generate_calls.append(kwargs)
                        type(self).entered.set()
                        if not type(self).release.wait(timeout=5):
                            raise TimeoutError("test did not release blocked request")
                        raise ResponsesRequestError(
                            "bad input",
                            status=400,
                            body='{"error":{"message":"Unknown content type input_file"}}',
                        )

                root = Path(tmp)
                auth_settings_path = root / "auth.json"
                api_settings_path = root / "api.json"
                AuthSettings(auth_settings_path).write_source("api")
                api_settings = ApiSettings(api_settings_path)
                api_settings.write(
                    {
                        "active_provider_id": "provider-a",
                        "providers": [
                            {
                                "id": "provider-a",
                                "name": "Provider A",
                                "base_url": "https://old-a.example.com/v1",
                                "api_key": "old-key-a",
                                "image_model": "gpt-image-2",
                                "api_mode": "responses",
                                "images_concurrency": 1,
                            },
                            {
                                "id": "provider-b",
                                "name": "Provider B",
                                "base_url": "https://b.example.com/v1",
                                "api_key": "key-b",
                                "image_model": "gpt-image-2",
                                "api_mode": "responses",
                                "images_concurrency": 1,
                            },
                        ],
                    }
                )
                with mock.patch(
                    "codex_image.webui.auth_routing.OpenAIResponsesImageClient",
                    BlockingRejectingApiClient,
                ):
                    app = create_app(
                        output_root=root / "outputs",
                        input_root=root / "inputs",
                        auth_settings_path=auth_settings_path,
                        api_settings_path=api_settings_path,
                        auth_checker=lambda: True,
                        batch_delay_seconds=0,
                        auto_start_queue=False,
                        auto_retry=True,
                    )
                    created = TestClient(app).post(
                        "/api/generate",
                        data={
                            "prompt": "Use it",
                            "api_mode": "responses",
                            "api_provider_id": "provider-a",
                        },
                        files={"reference_files": ("brief.md", b"# Brief", "text/markdown")},
                    ).json()["task"]
                    failures: list[BaseException] = []

                    def run_queue() -> None:
                        try:
                            asyncio.run(app.state.queue_manager.run_available_once())
                        except BaseException as exc:
                            failures.append(exc)

                    worker = threading.Thread(target=run_queue)
                    worker.start()
                    try:
                        self.assertTrue(BlockingRejectingApiClient.entered.wait(timeout=5))
                        api_settings.write(changed_settings)
                    finally:
                        BlockingRejectingApiClient.release.set()
                    worker.join(timeout=5)

                    self.assertFalse(worker.is_alive())
                    self.assertEqual(len(failures), 1)
                    self.assertEqual(
                        app.state.ctx.responses_file_unsupported_keys,
                        {
                            (
                                "openai_responses",
                                "provider-a",
                                "https://old-a.example.com/v1/responses",
                                DEFAULT_MAIN_MODEL,
                            )
                        },
                    )
                    next_response = TestClient(app).post(
                        "/api/generate",
                        data={
                            "prompt": "Use changed contract",
                            "api_mode": "responses",
                            "api_provider_id": next_provider_id,
                        },
                        files={"reference_files": ("next.md", b"next", "text/markdown")},
                    )

                self.assertEqual(
                    app.state.ctx.storage.read_metadata(created["task_id"])["error"],
                    "provider_reference_files_unsupported",
                )
                self.assertEqual(next_response.status_code, 200)

    def test_deleted_pinned_provider_does_not_fallback_or_cache_capability(self) -> None:
        from codex_image.webui.settings_store import ApiSettings, AuthSettings

        class RejectingApiClient(RejectingResponsesClient):
            def __init__(self, *, api_key: str, base_url: str, image_model: str, **_: Any) -> None:
                super().__init__(
                    ResponsesRequestError(
                        "bad input",
                        status=400,
                        body='{"error":{"message":"Unknown content type input_file"}}',
                    )
                )
                self.api_key = api_key
                self.base_url = base_url
                self.image_model = image_model

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth_settings_path = root / "auth.json"
            api_settings_path = root / "api.json"
            AuthSettings(auth_settings_path).write_source("api")
            api_settings = ApiSettings(api_settings_path)
            api_settings.write(
                {
                    "active_provider_id": "provider-a",
                    "providers": [
                        {
                            "id": "provider-a",
                            "name": "Provider A",
                            "base_url": "https://a.example.com/v1",
                            "api_key": "key-a",
                            "image_model": "gpt-image-2",
                            "api_mode": "responses",
                            "images_concurrency": 1,
                        },
                        {
                            "id": "provider-b",
                            "name": "Provider B",
                            "base_url": "https://b.example.com/v1",
                            "api_key": "key-b",
                            "image_model": "gpt-image-2",
                            "api_mode": "responses",
                            "images_concurrency": 1,
                        },
                    ],
                }
            )
            with mock.patch("codex_image.webui.auth_routing.OpenAIResponsesImageClient", RejectingApiClient):
                app = create_app(
                    output_root=root / "outputs",
                    input_root=root / "inputs",
                    auth_settings_path=auth_settings_path,
                    api_settings_path=api_settings_path,
                    auth_checker=lambda: True,
                    batch_delay_seconds=0,
                    auto_start_queue=False,
                    auto_retry=True,
                )
                first = TestClient(app).post(
                    "/api/generate",
                    data={
                        "prompt": "Use it",
                        "api_mode": "responses",
                        "api_provider_id": "provider-a",
                    },
                    files={"reference_files": ("brief.md", b"# Brief", "text/markdown")},
                ).json()["task"]
                api_settings.write(
                    {
                        "active_provider_id": "provider-b",
                        "providers": [
                            {
                                "id": "provider-b",
                                "name": "Provider B",
                                "base_url": "https://b.example.com/v1",
                                "api_key": "key-b",
                                "image_model": "gpt-image-2",
                                "api_mode": "responses",
                                "images_concurrency": 1,
                            }
                        ],
                    }
                )

                with self.assertRaises(Exception):
                    asyncio.run(app.state.queue_manager.run_available_once())

                self.assertEqual(app.state.ctx.responses_file_unsupported_keys, set())
                before = list(app.state.ctx.reference_file_root.glob("*/*.bin"))
                second = TestClient(app).post(
                    "/api/generate",
                    data={
                        "prompt": "Use another",
                        "api_mode": "responses",
                        "api_provider_id": "provider-b",
                    },
                    files={"reference_files": ("another.md", b"another", "text/markdown")},
                )

            first_metadata = app.state.ctx.storage.read_metadata(first["task_id"])
            self.assertEqual(first_metadata["generation_error"]["code"], "provider_credentials_missing")
            self.assertEqual(second.status_code, 200)

    def test_sse_status_200_schema_rejection_is_cached_and_non_retryable(self) -> None:
        from codex_image.codex_responses_client import CodexImageClient

        class SSERejectingClient(CapturingResponsesClient):
            def generate_image(self, **kwargs: Any):
                self._capture_reference_files(kwargs)
                self.generate_calls.append(kwargs)
                event = {
                    "type": "response.failed",
                    "response": {
                        "status": "failed",
                        "error": {"code": "unknown_input_file", "message": "input_file is not allowed"},
                    },
                }
                return CodexImageClient.parse_sse_response(
                    object.__new__(CodexImageClient),
                    f"data: {json.dumps(event)}\n\n".encode("utf-8"),
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = SSERejectingClient()
            app = create_app(
                output_root=root / "outputs",
                input_root=root / "inputs",
                client_factory=lambda: fake,
                auth_checker=lambda: True,
                batch_delay_seconds=0,
                auto_start_queue=False,
                auto_retry=True,
            )
            created = TestClient(app).post(
                "/api/generate",
                data={"prompt": "Use it", "codex_mode": "responses"},
                files={"reference_files": ("brief.md", b"# Brief", "text/markdown")},
            ).json()["task"]

            with self.assertRaises(Exception):
                asyncio.run(app.state.queue_manager.run_available_once())

            metadata = app.state.ctx.storage.read_metadata(created["task_id"])
            self.assertEqual(metadata["status"], "failed")
            self.assertEqual(metadata["error"], "provider_reference_files_unsupported")
            self.assertEqual(len(fake.generate_calls), 1)
            self.assertEqual(
                app.state.ctx.responses_file_unsupported_keys,
                {("codex_responses", "codex", DEFAULT_RESPONSES_URL, DEFAULT_MAIN_MODEL)},
            )

    def test_api_concurrent_partial_success_does_not_swallow_schema_rejection(self) -> None:
        from codex_image.client import ImageResult
        from codex_image.webui.settings_store import ApiSettings, AuthSettings

        class PartialSchemaRejectingApiClient(CapturingResponsesClient):
            instances: list[Any] = []

            def __init__(self, *, api_key: str, base_url: str, image_model: str, **_: Any) -> None:
                super().__init__()
                self.api_key = api_key
                self.base_url = base_url
                self.image_model = image_model
                self._lock = threading.Lock()
                self._barrier = threading.Barrier(2)
                self.active_requests = 0
                self.max_active_requests = 0
                type(self).instances.append(self)

            def generate_image(self, **kwargs: Any) -> ImageResult:
                self._capture_reference_files(kwargs)
                with self._lock:
                    self.generate_calls.append(kwargs)
                    call_number = len(self.generate_calls)
                    self.active_requests += 1
                    self.max_active_requests = max(self.max_active_requests, self.active_requests)
                try:
                    self._barrier.wait(timeout=5)
                    if call_number == 2:
                        raise ResponsesRequestError(
                            "bad input",
                            status=422,
                            body='{"error":{"message":"file_data is not allowed"}}',
                        )
                    return ImageResult(b"generated", "revised", "png", kwargs["size"], "auto", kwargs["quality"], {})
                finally:
                    with self._lock:
                        self.active_requests -= 1

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth_settings_path = root / "auth.json"
            api_settings_path = root / "api.json"
            AuthSettings(auth_settings_path).write_source("api")
            ApiSettings(api_settings_path).write(
                {
                    "base_url": "https://api.example.com/v1",
                    "api_key": "test-key",
                    "image_model": "gpt-image-2",
                    "api_mode": "responses",
                    "images_concurrency": 2,
                }
            )
            with mock.patch(
                "codex_image.webui.auth_routing.OpenAIResponsesImageClient",
                PartialSchemaRejectingApiClient,
            ):
                app = create_app(
                    output_root=root / "outputs",
                    input_root=root / "inputs",
                    auth_settings_path=auth_settings_path,
                    api_settings_path=api_settings_path,
                    auth_checker=lambda: True,
                    batch_delay_seconds=0,
                    auto_start_queue=False,
                    auto_retry=True,
                )
                created = TestClient(app).post(
                    "/api/generate",
                    data={"prompt": "Use it", "api_mode": "responses", "n": "2"},
                    files={"reference_files": ("brief.md", b"# Brief", "text/markdown")},
                ).json()["task"]

                with self.assertRaises(Exception):
                    asyncio.run(app.state.queue_manager.run_available_once())

            metadata = app.state.ctx.storage.read_metadata(created["task_id"])
            self.assertEqual(metadata["status"], "failed")
            self.assertEqual(metadata["error"], "provider_reference_files_unsupported")
            self.assertEqual(
                app.state.ctx.responses_file_unsupported_keys,
                {("openai_responses", "default", "https://api.example.com/v1/responses", DEFAULT_MAIN_MODEL)},
            )
            self.assertEqual(PartialSchemaRejectingApiClient.instances[0].max_active_requests, 2)


if __name__ == "__main__":
    unittest.main()
