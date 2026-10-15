from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from codex_image.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_LICENSE = "AGPL-3.0-only"
PINNED_ACTIONS = {
    "actions/checkout": ("3d3c42e5aac5ba805825da76410c181273ba90b1", "v7.0.1"),
    "actions/setup-python": ("ece7cb06caefa5fff74198d8649806c4678c61a1", "v6.3.0"),
    "actions/setup-node": ("249970729cb0ef3589644e2896645e5dc5ba9c38", "v6.5.0"),
    "actions/upload-artifact": ("b7c566a772e6b6bfb58ed0dc250532a479d7789f", "v6.0.0"),
    "actions/download-artifact": ("3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c", "v8.0.1"),
}


class ReleaseContractTests(unittest.TestCase):
    def test_public_repository_tracks_design_and_rejects_local_agent_rules(self) -> None:
        manifest = json.loads(
            (ROOT / ".public-export-manifest.json").read_text(encoding="utf-8")
        )
        self.assertIn("DESIGN.md", manifest["allowlist"])
        self.assertNotIn("DESIGN.md", manifest["excluded_private_paths"])
        self.assertIn("AGENT.md", manifest["excluded_private_paths"])
        self.assertIn("AGENTS.md", manifest["excluded_private_paths"])

        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("test ! -e AGENT.md", workflow)
        self.assertIn("test ! -e AGENTS.md", workflow)
        self.assertIn("test -f DESIGN.md", workflow)

    def test_runtime_version_is_the_single_release_version_source(self) -> None:
        version_source = (ROOT / "codex_image" / "version.py").read_text(encoding="utf-8")
        self.assertEqual(
            re.findall(r'^APP_VERSION = "([^"]+)"$', version_source, re.MULTILINE),
            [APP_VERSION],
        )

        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        project = pyproject["project"]
        self.assertNotIn("version", project)
        self.assertIn("version", project["dynamic"])
        self.assertEqual(
            pyproject["tool"]["setuptools"]["dynamic"]["version"]["attr"],
            "codex_image.version.APP_VERSION",
        )

        cargo = tomllib.loads((ROOT / "launcher" / "Cargo.toml").read_text(encoding="utf-8"))
        self.assertEqual(cargo["package"]["version"], APP_VERSION)

    def test_python_package_discovery_excludes_workspace_and_includes_webui_assets(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        setuptools = pyproject["tool"]["setuptools"]

        self.assertRegex(pyproject["build-system"]["requires"][0], r"^setuptools==[^=]+$")
        self.assertEqual(setuptools["packages"]["find"]["include"], ["codex_image*"])
        self.assertFalse(setuptools["packages"]["find"]["namespaces"])
        webui_data = setuptools["package-data"]["codex_image.webui"]
        self.assertIn("static/*", webui_data)
        self.assertIn("static/**/*", webui_data)

    def test_python_and_rust_publish_the_same_license_identifier(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        cargo = tomllib.loads((ROOT / "launcher" / "Cargo.toml").read_text(encoding="utf-8"))

        self.assertEqual(pyproject["project"]["license"], EXPECTED_LICENSE)
        self.assertEqual(cargo["package"]["license"], EXPECTED_LICENSE)

    def test_release_contract_checker_accepts_repository_and_rejects_wrong_tag(self) -> None:
        checker = ROOT / "scripts" / "check-release-contracts.py"
        valid = subprocess.run(
            [sys.executable, str(checker), "--release-tag", f"v{APP_VERSION}"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(valid.returncode, 0, valid.stderr)

        invalid = subprocess.run(
            [sys.executable, str(checker), "--release-tag", "v9.9.9"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("does not match application version", invalid.stderr)

    def test_runtime_dependencies_are_exactly_pinned_and_hash_checked(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        dependencies = pyproject["project"]["dependencies"]
        self.assertEqual(len(dependencies), 5)
        for dependency in dependencies:
            self.assertRegex(dependency, r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_.-]+\])?==[^=]+$")

        requirements = (ROOT / "requirements-webui.txt").read_text(encoding="utf-8")
        self.assertIn("--require-hashes", requirements)
        self.assertNotIn(">=", requirements)
        self.assertNotIn("~=", requirements)
        package_lines = [
            line.strip()
            for line in requirements.splitlines()
            if line
            and not line.startswith((" ", "#", "--"))
        ]
        self.assertGreaterEqual(len(package_lines), 15)
        for line in package_lines:
            self.assertRegex(line, r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_.-]+\])?==")

        self.assertRegex(
            requirements,
            r"(?m)^colorama==[^=]+ \\$",
            "Windows-only runtime dependencies must be present in the cross-platform lock",
        )

        for relative in (
            "Start WebUI.command",
            "Start WebUI Debug.command",
            "Start WebUI.bat",
            "packaging/macos/build-app.sh",
            "packaging/macos/build-portable.sh",
            "packaging/windows/build-app.ps1",
            "packaging/windows/build-portable.ps1",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("--require-hashes", text, relative)

    def test_launcher_rechecks_pinned_versions_before_reusing_environment(self) -> None:
        launcher = (ROOT / "launcher" / "src" / "lib.rs").read_text(encoding="utf-8")
        self.assertIn("codex_image.dependency_check", launcher)
        self.assertIn("--requirements", launcher)
        self.assertIn("WebUI dependency verification failed after installation", launcher)

    def test_dependency_check_detects_outdated_direct_runtime_package(self) -> None:
        from codex_image.dependency_check import dependency_mismatches

        with tempfile.TemporaryDirectory() as directory:
            requirements_path = Path(directory) / "requirements.txt"
            requirements_path.write_text(
                "--require-hashes\n"
                "fastapi==1.2.3 \\\n"
                "    --hash=sha256:" + ("0" * 64) + "\n"
                "httpx==4.5.6 \\\n"
                "    --hash=sha256:" + ("1" * 64) + "\n",
                encoding="utf-8",
            )

            installed = {"fastapi": "1.2.2", "httpx": "4.5.6"}
            mismatches = dependency_mismatches(
                requirements_path,
                distribution_version=installed.__getitem__,
                package_names=("fastapi", "httpx"),
            )

        self.assertEqual(mismatches, ["fastapi: installed 1.2.2, required 1.2.3"])

    def test_dependency_check_detects_outdated_transitive_runtime_package(self) -> None:
        from codex_image.dependency_check import dependency_mismatches

        with tempfile.TemporaryDirectory() as directory:
            requirements_path = Path(directory) / "requirements.txt"
            requirements_path.write_text(
                "fastapi==1.2.3\n"
                "uvicorn==2.3.4\n"
                "python-multipart==3.4.5\n"
                "httpx==4.5.6\n"
                "pillow==5.6.7\n"
                "idna==8.9.0\n",
                encoding="utf-8",
            )
            installed = {
                "fastapi": "1.2.3",
                "uvicorn": "2.3.4",
                "python-multipart": "3.4.5",
                "httpx": "4.5.6",
                "pillow": "5.6.7",
                "idna": "8.8.0",
            }
            mismatches = dependency_mismatches(
                requirements_path,
                distribution_version=installed.__getitem__,
            )

        self.assertEqual(mismatches, ["idna: installed 8.8.0, required 8.9.0"])

    def test_ci_has_python_quality_security_and_cross_platform_rust_gates(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        for expected in (
            "ruff check",
            "bandit",
            "pip-audit",
            "coverage report --fail-under=",
            "cargo fmt --all -- --check",
            "cargo clippy --all-targets --locked -- -D warnings",
            "cargo test --all-targets --locked",
            "macos-latest",
            "windows-latest",
            "python scripts/check-release-contracts.py",
        ):
            self.assertIn(expected, workflow)

    def test_ci_installs_locked_python_runtime_on_windows(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        job = re.search(
            r"(?ms)^  windows-python-lock:\n(?P<body>.*?)(?=^  [a-z0-9-]+:\n|\Z)",
            workflow,
        )
        self.assertIsNotNone(job, "CI must verify the runtime dependency lock on Windows")
        body = job.group("body") if job else ""
        self.assertIn("runs-on: windows-latest", body)
        self.assertIn('python-version: "3.11"', body)
        self.assertIn(
            "python -m pip install --require-hashes -r requirements-webui.txt",
            body,
        )

    def test_workflows_pin_every_action_to_a_full_commit_sha(self) -> None:
        workflows = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        )
        uses = re.findall(r"^\s*uses:\s*([^@\s]+)@([^\s#]+)(?:\s+#\s*(\S+))?", workflows, re.MULTILINE)
        self.assertTrue(set(PINNED_ACTIONS).issubset({action for action, _, _ in uses}))

        for action, revision, comment in uses:
            self.assertRegex(revision, r"^[0-9a-f]{40}$", action)
            if action in PINNED_ACTIONS:
                expected_revision, expected_comment = PINNED_ACTIONS[action]
                self.assertEqual(revision, expected_revision)
                self.assertEqual(comment, expected_comment)

    def test_manual_release_verifies_ci_for_the_exact_resolved_commit(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release-portable.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("Verify CI for release commit", workflow)
        self.assertIn("actions/workflows/ci.yml/runs", workflow)
        self.assertIn('head_sha="$CHECKOUT_REF"', workflow)
        self.assertIn("No successful CI run exists for release commit", workflow)
        self.assertIn("needs: [resolve-release, verify-ci]", workflow)
        self.assertIn("environment: release", workflow)
        self.assertIn(
            'python scripts/check-release-contracts.py --release-tag "$RELEASE_TAG"',
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
