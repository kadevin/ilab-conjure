#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote


PLATFORM_PATTERNS = {
    "darwin-aarch64": "ilab-gpt-conjure_macos_portable_arm64_",
    "darwin-x86_64": "ilab-gpt-conjure_macos_portable_x64_",
    "windows-x86_64": "ilab-gpt-conjure_windows_portable_x64_",
}

STANDARD_PLATFORM_PATTERNS = {
    "darwin-aarch64": ("iLab-GPT-CONJURE-macos-arm64-", ".dmg", "standard-dmg"),
    "darwin-x86_64": ("iLab-GPT-CONJURE-macos-x64-", ".dmg", "standard-dmg"),
    "windows-x86_64": ("iLab-GPT-CONJURE-windows-x64_", ".zip", "standard-zip"),
}


def read_sha256(asset_path: Path) -> str:
    sidecar = asset_path.with_name(f"{asset_path.name}.sha256.txt")
    if not sidecar.exists():
        raise SystemExit(f"missing SHA256 sidecar for {asset_path.name}")
    sidecar_hash = sidecar.read_text(encoding="utf-8").split()[0].lower()
    actual_hash = hashlib.sha256(asset_path.read_bytes()).hexdigest()
    if sidecar_hash != actual_hash:
        raise SystemExit(
            f"SHA256 mismatch for {asset_path.name}: sidecar {sidecar_hash}, actual {actual_hash}"
        )
    return actual_hash


def read_optional_signature(asset_path: Path) -> str | None:
    signature_path = asset_path.with_name(f"{asset_path.name}.sig")
    if not signature_path.exists():
        return None
    signature = signature_path.read_text(encoding="utf-8").strip()
    return signature or None


def release_download_url(repo: str, tag: str, asset_name: str) -> str:
    return (
        f"https://github.com/{repo}/releases/download/"
        f"{quote(tag)}/{quote(asset_name)}"
    )


def build_manifest(
    *,
    assets_dir: Path,
    version: str,
    tag: str,
    repo: str,
    notes: str,
) -> dict[str, object]:
    zip_assets = sorted(path for path in assets_dir.rglob("*.zip") if path.is_file())
    dmg_assets = sorted(path for path in assets_dir.rglob("*.dmg") if path.is_file())
    platforms: dict[str, dict[str, str]] = {}
    standard_platforms: dict[str, dict[str, str]] = {}

    for platform, prefix in PLATFORM_PATTERNS.items():
        matches = [path for path in zip_assets if path.name.startswith(prefix)]
        if len(matches) != 1:
            raise SystemExit(
                f"expected exactly one {platform} asset with prefix {prefix}, found {len(matches)}"
            )
        asset_path = matches[0]
        entry = {
            "asset": asset_path.name,
            "url": release_download_url(repo, tag, asset_path.name),
            "sha256": read_sha256(asset_path),
            "package": "portable-zip",
        }
        signature = read_optional_signature(asset_path)
        if signature:
            entry["signature"] = signature
        platforms[platform] = entry

    for platform, (prefix, suffix, package) in STANDARD_PLATFORM_PATTERNS.items():
        asset_pool = dmg_assets if suffix == ".dmg" else zip_assets
        matches = [
            path
            for path in asset_pool
            if path.name.startswith(prefix) and path.name.endswith(suffix)
        ]
        if len(matches) != 1:
            raise SystemExit(
                f"expected exactly one standard {platform} asset with prefix {prefix}, found {len(matches)}"
            )
        asset_path = matches[0]
        standard_platforms[platform] = {
            "asset": asset_path.name,
            "url": release_download_url(repo, tag, asset_path.name),
            "sha256": read_sha256(asset_path),
            "package": package,
        }

    return {
        "schema_version": 1,
        "version": version,
        "release_url": f"https://github.com/{repo}/releases/tag/{quote(tag)}",
        "notes": notes,
        "platforms": platforms,
        "standard_platforms": standard_platforms,
    }


def manifest_signing_payload(manifest: dict[str, object]) -> bytes:
    lines = ["ilab-gpt-conjure-update-manifest-v1"]

    def field(name: str, value: object) -> None:
        text = str(value)
        lines.append(f"{name}:{len(text.encode('utf-8'))}:{text}")

    field("schema_version", manifest["schema_version"])
    field("version", manifest["version"])
    field("release_url", manifest["release_url"])
    platforms = manifest["platforms"]
    if not isinstance(platforms, dict):
        raise SystemExit("manifest platforms must be an object")
    for platform_key, entry in sorted(platforms.items()):
        if not isinstance(entry, dict):
            raise SystemExit(f"manifest platform {platform_key} must be an object")
        field("platform", platform_key)
        for field_name in ("asset", "url", "sha256", "package"):
            field(field_name, entry[field_name])
    return ("\n".join(lines) + "\n").encode("utf-8")


def standard_manifest_signing_payload(manifest: dict[str, object]) -> bytes:
    lines = ["ilab-gpt-conjure-standard-update-manifest-v1"]

    def field(name: str, value: object) -> None:
        text = str(value)
        lines.append(f"{name}:{len(text.encode('utf-8'))}:{text}")

    field("schema_version", manifest["schema_version"])
    field("version", manifest["version"])
    field("release_url", manifest["release_url"])
    platforms = manifest.get("standard_platforms")
    if not isinstance(platforms, dict):
        raise SystemExit("manifest standard_platforms must be an object")
    for platform_key, entry in sorted(platforms.items()):
        if not isinstance(entry, dict):
            raise SystemExit(f"manifest standard platform {platform_key} must be an object")
        field("standard_platform", platform_key)
        for field_name in ("asset", "url", "sha256", "package"):
            field(field_name, entry[field_name])
    return ("\n".join(lines) + "\n").encode("utf-8")


def sign_manifest(manifest: dict[str, object], private_key_b64: str) -> dict[str, str]:
    private_key_pem = base64.b64decode(private_key_b64)
    payload = manifest_signing_payload(manifest)
    return sign_payload(payload, private_key_pem)


def sign_standard_manifest(manifest: dict[str, object], private_key_b64: str) -> dict[str, str]:
    private_key_pem = base64.b64decode(private_key_b64)
    payload = standard_manifest_signing_payload(manifest)
    return sign_payload(payload, private_key_pem)


def sign_payload(payload: bytes, private_key_pem: bytes) -> dict[str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        key_path = root / "private.pem"
        payload_path = root / "payload.txt"
        signature_path = root / "signature.bin"
        key_path.write_bytes(private_key_pem)
        payload_path.write_bytes(payload)
        subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-rawin",
                "-inkey",
                str(key_path),
                "-in",
                str(payload_path),
                "-out",
                str(signature_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        return {
            "algorithm": "ed25519",
            "value": base64.b64encode(signature_path.read_bytes()).decode("ascii"),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build iLab CONJURE signed update manifest."
    )
    parser.add_argument("--assets-dir", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--notes-file", type=Path)
    parser.add_argument("--signing-private-key-b64")
    parser.add_argument("--require-signature", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    notes = ""
    if args.notes_file:
        notes = args.notes_file.read_text(encoding="utf-8").strip()
    manifest = build_manifest(
        assets_dir=args.assets_dir,
        version=args.version,
        tag=args.tag,
        repo=args.repo,
        notes=notes,
    )
    if args.signing_private_key_b64:
        manifest["signature"] = sign_manifest(manifest, args.signing_private_key_b64)
        manifest["standard_signature"] = sign_standard_manifest(manifest, args.signing_private_key_b64)
    elif args.require_signature:
        raise SystemExit("signing private key is required when --require-signature is set")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
