from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest


class UpdateManifestTests(unittest.TestCase):
    TEST_PRIVATE_KEY_PEM_B64 = (
        "LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tCk1DNENBUUF3QlFZREsyVndCQ0lFSUFBQkFn"
        "TUVCUVlIQ0FrS0N3d05EZzhRRVJJVEZCVVdGeGdaR2hzY0hSNGYKLS0tLS1FTkQgUFJJVkFU"
        "RSBLRVktLS0tLQo="
    )

    def test_build_update_manifest_maps_portable_assets_to_platforms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets_dir = root / "dist-assets"
            output_path = root / "latest.json"
            assets_dir.mkdir()

            assets = {
                "ilab-gpt-conjure_windows_portable_x64_0.6.0.zip": b"windows",
                "ilab-gpt-conjure_macos_portable_arm64_0.6.0.zip": b"mac arm",
                "ilab-gpt-conjure_macos_portable_x64_0.6.0.zip": b"mac intel",
                "iLab-GPT-CONJURE-windows-x64_0.6.0.zip": b"windows app",
            }
            for name, payload in assets.items():
                path = assets_dir / name
                path.write_bytes(payload)
                digest = hashlib.sha256(payload).hexdigest()
                (assets_dir / f"{name}.sha256.txt").write_text(
                    f"{digest}  {name}\n", encoding="utf-8"
                )
            for name, payload in {
                "iLab-GPT-CONJURE-macos-arm64-0.6.0.dmg": b"mac app arm",
                "iLab-GPT-CONJURE-macos-x64-0.6.0.dmg": b"mac app intel",
            }.items():
                path = assets_dir / name
                path.write_bytes(payload)
                digest = hashlib.sha256(payload).hexdigest()
                (assets_dir / f"{name}.sha256.txt").write_text(
                    f"{digest}  {name}\n", encoding="utf-8"
                )

            subprocess.run(
                [
                    sys.executable,
                    "scripts/build-update-manifest.py",
                    "--assets-dir",
                    str(assets_dir),
                    "--version",
                    "0.6.0",
                    "--tag",
                    "v0.6.0",
                    "--repo",
                    "kadevin/ilab-conjure",
                    "--output",
                    str(output_path),
                ],
                check=True,
            )

            manifest = json.loads(output_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["version"], "0.6.0")
            self.assertEqual(
                manifest["release_url"],
                "https://github.com/kadevin/ilab-conjure/releases/tag/v0.6.0",
            )
            self.assertEqual(
                set(manifest["platforms"]),
                {"darwin-aarch64", "darwin-x86_64", "windows-x86_64"},
            )
            self.assertEqual(
                set(manifest["standard_platforms"]),
                {"darwin-aarch64", "darwin-x86_64", "windows-x86_64"},
            )
            windows = manifest["platforms"]["windows-x86_64"]
            self.assertEqual(
                windows["url"],
                "https://github.com/kadevin/ilab-conjure/releases/download/v0.6.0/ilab-gpt-conjure_windows_portable_x64_0.6.0.zip",
            )
            self.assertEqual(windows["package"], "portable-zip")
            self.assertRegex(windows["sha256"], r"^[0-9a-f]{64}$")
            windows_app = manifest["standard_platforms"]["windows-x86_64"]
            self.assertEqual(windows_app["package"], "standard-zip")
            self.assertEqual(
                windows_app["url"],
                "https://github.com/kadevin/ilab-conjure/releases/download/v0.6.0/iLab-GPT-CONJURE-windows-x64_0.6.0.zip",
            )
            mac_app = manifest["standard_platforms"]["darwin-aarch64"]
            self.assertEqual(mac_app["package"], "standard-dmg")
            self.assertEqual(
                mac_app["url"],
                "https://github.com/kadevin/ilab-conjure/releases/download/v0.6.0/iLab-GPT-CONJURE-macos-arm64-0.6.0.dmg",
            )

    def test_build_update_manifest_can_sign_with_ed25519_private_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets_dir = root / "dist-assets"
            output_path = root / "latest.json"
            payload_path = root / "payload.txt"
            private_key_path = root / "private.pem"
            public_key_path = root / "public.pem"
            signature_path = root / "signature.bin"
            assets_dir.mkdir()

            assets = {
                "ilab-gpt-conjure_windows_portable_x64_0.6.0.zip": b"windows",
                "ilab-gpt-conjure_macos_portable_arm64_0.6.0.zip": b"mac arm",
                "ilab-gpt-conjure_macos_portable_x64_0.6.0.zip": b"mac intel",
                "iLab-GPT-CONJURE-windows-x64_0.6.0.zip": b"windows app",
                "iLab-GPT-CONJURE-macos-arm64-0.6.0.dmg": b"mac app arm",
                "iLab-GPT-CONJURE-macos-x64-0.6.0.dmg": b"mac app intel",
            }
            for name, payload in assets.items():
                path = assets_dir / name
                path.write_bytes(payload)
                digest = hashlib.sha256(payload).hexdigest()
                (assets_dir / f"{name}.sha256.txt").write_text(
                    f"{digest}  {name}\n", encoding="utf-8"
                )

            subprocess.run(
                [
                    sys.executable,
                    "scripts/build-update-manifest.py",
                    "--assets-dir",
                    str(assets_dir),
                    "--version",
                    "0.6.0",
                    "--tag",
                    "v0.6.0",
                    "--repo",
                    "kadevin/ilab-conjure",
                    "--signing-private-key-b64",
                    self.TEST_PRIVATE_KEY_PEM_B64,
                    "--output",
                    str(output_path),
                ],
                check=True,
            )

            manifest = json.loads(output_path.read_text(encoding="utf-8"))
            signature = manifest["signature"]
            self.assertEqual(signature["algorithm"], "ed25519")
            self.assertRegex(signature["value"], r"^[A-Za-z0-9+/=]+$")
            standard_signature = manifest["standard_signature"]
            self.assertEqual(standard_signature["algorithm"], "ed25519")
            self.assertRegex(standard_signature["value"], r"^[A-Za-z0-9+/=]+$")

            private_key_path.write_bytes(
                __import__("base64").b64decode(self.TEST_PRIVATE_KEY_PEM_B64)
            )
            subprocess.run(
                ["openssl", "pkey", "-in", str(private_key_path), "-pubout", "-out", str(public_key_path)],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            payload_path.write_bytes(self._manifest_signing_payload(manifest))
            signature_path.write_bytes(__import__("base64").b64decode(signature["value"]))
            subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-verify",
                    "-rawin",
                    "-pubin",
                    "-inkey",
                    str(public_key_path),
                    "-sigfile",
                    str(signature_path),
                    "-in",
                    str(payload_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            payload_path.write_bytes(self._standard_manifest_signing_payload(manifest))
            signature_path.write_bytes(__import__("base64").b64decode(standard_signature["value"]))
            subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-verify",
                    "-rawin",
                    "-pubin",
                    "-inkey",
                    str(public_key_path),
                    "-sigfile",
                    str(signature_path),
                    "-in",
                    str(payload_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )

    def test_build_update_manifest_requires_signature_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets_dir = root / "dist-assets"
            assets_dir.mkdir()
            for name in (
                "ilab-gpt-conjure_windows_portable_x64_0.6.0.zip",
                "ilab-gpt-conjure_macos_portable_arm64_0.6.0.zip",
                "ilab-gpt-conjure_macos_portable_x64_0.6.0.zip",
                "iLab-GPT-CONJURE-windows-x64_0.6.0.zip",
                "iLab-GPT-CONJURE-macos-arm64-0.6.0.dmg",
                "iLab-GPT-CONJURE-macos-x64-0.6.0.dmg",
            ):
                path = assets_dir / name
                path.write_bytes(b"payload")
                (assets_dir / f"{name}.sha256.txt").write_text(
                    f"{hashlib.sha256(b'payload').hexdigest()}  {name}\n",
                    encoding="utf-8",
                )

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/build-update-manifest.py",
                    "--assets-dir",
                    str(assets_dir),
                    "--version",
                    "0.6.0",
                    "--tag",
                    "v0.6.0",
                    "--repo",
                    "kadevin/ilab-conjure",
                    "--require-signature",
                    "--output",
                    str(root / "latest.json"),
                ],
                stderr=subprocess.PIPE,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("signing private key", result.stderr)

    @staticmethod
    def _manifest_signing_payload(manifest: dict[str, object]) -> bytes:
        lines = ["ilab-gpt-conjure-update-manifest-v1"]

        def field(name: str, value: object) -> None:
            text = str(value)
            lines.append(f"{name}:{len(text.encode('utf-8'))}:{text}")

        field("schema_version", manifest["schema_version"])
        field("version", manifest["version"])
        field("release_url", manifest["release_url"])
        platforms = manifest["platforms"]
        assert isinstance(platforms, dict)
        for key, entry in sorted(platforms.items()):
            assert isinstance(entry, dict)
            field("platform", key)
            for field_name in ("asset", "url", "sha256", "package"):
                field(field_name, entry[field_name])
        return ("\n".join(lines) + "\n").encode("utf-8")

    @staticmethod
    def _standard_manifest_signing_payload(manifest: dict[str, object]) -> bytes:
        lines = ["ilab-gpt-conjure-standard-update-manifest-v1"]

        def field(name: str, value: object) -> None:
            text = str(value)
            lines.append(f"{name}:{len(text.encode('utf-8'))}:{text}")

        field("schema_version", manifest["schema_version"])
        field("version", manifest["version"])
        field("release_url", manifest["release_url"])
        platforms = manifest["standard_platforms"]
        assert isinstance(platforms, dict)
        for key, entry in sorted(platforms.items()):
            assert isinstance(entry, dict)
            field("standard_platform", key)
            for field_name in ("asset", "url", "sha256", "package"):
                field(field_name, entry[field_name])
        return ("\n".join(lines) + "\n").encode("utf-8")


if __name__ == "__main__":
    unittest.main()
