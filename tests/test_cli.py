from __future__ import annotations

import base64
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import FakeResponse, FakeTransport, make_sse_completed_event, write_auth_file


class CLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.base = Path(self.tmpdir.name)
        self.auth_path = self.base / "auth.json"
        self.out_path = self.base / "image.png"

    def test_cli_generate_writes_output_file(self) -> None:
        write_auth_file(self.auth_path, access_token="cli-token", account_id="acct-cli")
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=make_sse_completed_event(image_b64=base64.b64encode(b"cli-image").decode("ascii")),
                    headers={"Content-Type": "text/event-stream"},
                )
            ]
        )

        from codex_image.cli import main

        exit_code = main(
            [
                "generate",
                "--prompt",
                "draw a black mug",
                "--size",
                "2048x1152",
                "--out",
                str(self.out_path),
                "--auth-file",
                str(self.auth_path),
            ],
            transport=transport,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(self.out_path.read_bytes(), b"cli-image")

    def test_generate_help_lists_moderation(self) -> None:
        from codex_image.cli import build_parser

        parser = build_parser()
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit):
                parser.parse_args(["generate", "--help"])

        self.assertIn("--moderation", stdout.getvalue())

    def test_cli_defaults_remain_codex_gpt_image_without_provider_family_flags(self) -> None:
        from codex_image.cli import build_parser

        parser = build_parser()
        generate = parser.parse_args(
            ["generate", "--prompt", "fixture", "--out", str(self.out_path)]
        )
        edit = parser.parse_args(
            [
                "edit",
                "--prompt",
                "fixture",
                "--image",
                str(self.base / "input.png"),
                "--out",
                str(self.out_path),
            ]
        )

        self.assertEqual(generate.model, "gpt-image-2")
        self.assertEqual(edit.model, "gpt-image-2")
        self.assertEqual(generate.output_format, "png")
        self.assertEqual(edit.output_format, "png")
        self.assertFalse(hasattr(generate, "provider_id"))
        self.assertFalse(hasattr(generate, "canonical_model_id"))

    def test_run_generate_passes_moderation_to_request(self) -> None:
        write_auth_file(self.auth_path, access_token="cli-token", account_id="acct-cli")
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=make_sse_completed_event(image_b64=base64.b64encode(b"cli-image").decode("ascii")),
                    headers={"Content-Type": "text/event-stream"},
                )
            ]
        )

        from codex_image.cli import _run_generate

        exit_code = _run_generate(
            SimpleNamespace(
                prompt="draw a black mug",
                prompt_file=None,
                size="2048x1152",
                quality="low",
                background=None,
                output_format="png",
                moderation="low",
                model="gpt-image-2",
                image=[],
                out=str(self.out_path),
                auth_file=str(self.auth_path),
                dry_run=False,
            ),
            transport=transport,
        )

        self.assertEqual(exit_code, 0)
        payload = json.loads(transport.requests[0]["body"].decode("utf-8"))
        self.assertEqual(payload["tools"][0]["moderation"], "low")

    def test_cli_edit_uses_local_image_paths(self) -> None:
        write_auth_file(self.auth_path, access_token="cli-token", account_id="acct-cli")
        input_image = self.base / "input.png"
        input_image.write_bytes(b"png-bytes")
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=make_sse_completed_event(image_b64=base64.b64encode(b"edited-cli-image").decode("ascii")),
                    headers={"Content-Type": "text/event-stream"},
                )
            ]
        )

        from codex_image.cli import main

        exit_code = main(
            [
                "edit",
                "--prompt",
                "change background",
                "--image",
                str(input_image),
                "--out",
                str(self.out_path),
                "--auth-file",
                str(self.auth_path),
            ],
            transport=transport,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(self.out_path.read_bytes(), b"edited-cli-image")

    def test_run_edit_passes_moderation_to_request(self) -> None:
        write_auth_file(self.auth_path, access_token="cli-token", account_id="acct-cli")
        input_image = self.base / "input.png"
        input_image.write_bytes(b"png-bytes")
        transport = FakeTransport(
            [
                FakeResponse(
                    status=200,
                    body=make_sse_completed_event(image_b64=base64.b64encode(b"edited-cli-image").decode("ascii")),
                    headers={"Content-Type": "text/event-stream"},
                )
            ]
        )

        from codex_image.cli import _run_edit

        exit_code = _run_edit(
            SimpleNamespace(
                prompt="change background",
                prompt_file=None,
                image=[str(input_image)],
                mask=None,
                size="1536x1024",
                quality="low",
                background=None,
                output_format="png",
                input_fidelity=None,
                moderation="auto",
                model="gpt-image-2",
                out=str(self.out_path),
                auth_file=str(self.auth_path),
                dry_run=False,
            ),
            transport=transport,
        )

        self.assertEqual(exit_code, 0)
        payload = json.loads(transport.requests[0]["body"].decode("utf-8"))
        self.assertEqual(payload["tools"][0]["moderation"], "auto")


if __name__ == "__main__":
    unittest.main()
