from __future__ import annotations

import argparse
import base64
import mimetypes
import json
import sys
from pathlib import Path
from typing import Sequence

from .auth import DEFAULT_AUTH_PATH, load_auth_state
from .client import CodexImageClient
from .http import Transport
from .runtime_security import dependency_security_error, python_security_error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate images by calling Codex directly with the local OAuth session.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Generate an image from a prompt")
    generate.add_argument("--prompt")
    generate.add_argument("--prompt-file")
    generate.add_argument("--size")
    generate.add_argument("--quality")
    generate.add_argument("--background")
    generate.add_argument("--moderation", choices=("auto", "low"))
    generate.add_argument("--output-format", default="png")
    generate.add_argument("--model", default="gpt-image-2")
    generate.add_argument("--image", action="append", default=[])
    generate.add_argument("--out", required=True)
    generate.add_argument("--auth-file", default=str(DEFAULT_AUTH_PATH))
    generate.add_argument("--dry-run", action="store_true")

    edit = subparsers.add_parser("edit", help="Edit one or more images")
    edit.add_argument("--prompt")
    edit.add_argument("--prompt-file")
    edit.add_argument("--image", action="append", required=True)
    edit.add_argument("--mask")
    edit.add_argument("--size")
    edit.add_argument("--quality")
    edit.add_argument("--background")
    edit.add_argument("--moderation", choices=("auto", "low"))
    edit.add_argument("--output-format", default="png")
    edit.add_argument("--input-fidelity")
    edit.add_argument("--model", default="gpt-image-2")
    edit.add_argument("--out", required=True)
    edit.add_argument("--auth-file", default=str(DEFAULT_AUTH_PATH))
    edit.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None, *, transport: Transport | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if problem := python_security_error() or dependency_security_error():
        print(problem, file=sys.stderr)
        return 2
    try:
        if args.command == "generate":
            return _run_generate(args, transport=transport)
        if args.command == "edit":
            return _run_edit(args, transport=transport)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def main_entry() -> None:
    raise SystemExit(main())


def _run_generate(args: argparse.Namespace, *, transport: Transport | None = None) -> int:
    prompt = _read_prompt(args)
    auth_state = load_auth_state(args.auth_file)
    client = CodexImageClient(auth_state, transport=transport)
    reference_images = [_path_to_data_url(Path(image_path)) for image_path in args.image]
    payload = client.build_payload(
        prompt=prompt,
        model=args.model,
        input_images=reference_images,
        size=args.size,
        quality=args.quality,
        background=args.background,
        moderation=args.moderation,
        output_format=args.output_format,
    )
    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return 0

    result = client.generate_image(
        prompt=prompt,
        model=args.model,
        reference_images=reference_images,
        size=args.size,
        quality=args.quality,
        background=args.background,
        moderation=args.moderation,
        output_format=args.output_format,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(result.image_bytes)
    print(f"Wrote {out_path}")
    if result.size:
        print(f"Size: {result.size}")
    if result.revised_prompt:
        print(f"Revised prompt: {result.revised_prompt}")
    return 0


def _run_edit(args: argparse.Namespace, *, transport: Transport | None = None) -> int:
    prompt = _read_prompt(args)
    auth_state = load_auth_state(args.auth_file)
    client = CodexImageClient(auth_state, transport=transport)
    images = [_path_to_data_url(Path(image_path)) for image_path in args.image]
    mask_image = _path_to_data_url(Path(args.mask)) if args.mask else None
    payload = client.build_payload(
        prompt=prompt,
        action="edit",
        model=args.model,
        input_images=images,
        mask_image=mask_image,
        size=args.size,
        quality=args.quality,
        background=args.background,
        moderation=args.moderation,
        output_format=args.output_format,
        input_fidelity=args.input_fidelity,
    )
    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return 0

    result = client.edit_image(
        prompt=prompt,
        images=images,
        mask_image=mask_image,
        model=args.model,
        size=args.size,
        quality=args.quality,
        background=args.background,
        moderation=args.moderation,
        output_format=args.output_format,
        input_fidelity=args.input_fidelity,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(result.image_bytes)
    print(f"Wrote {out_path}")
    if result.size:
        print(f"Size: {result.size}")
    if result.revised_prompt:
        print(f"Revised prompt: {result.revised_prompt}")
    return 0


def _read_prompt(args: argparse.Namespace) -> str:
    if bool(args.prompt) == bool(args.prompt_file):
        raise RuntimeError("Use exactly one of --prompt or --prompt-file")
    if args.prompt:
        return str(args.prompt).strip()
    return Path(args.prompt_file).read_text(encoding="utf-8").strip()


def _path_to_data_url(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(path.name)
    if not mime_type:
        mime_type = "application/octet-stream"
    return f"data:{mime_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
