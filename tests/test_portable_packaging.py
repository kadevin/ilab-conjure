from __future__ import annotations

from pathlib import Path
import unittest


class PortablePackagingTests(unittest.TestCase):
    def test_ci_workflow_avoids_github_unsupported_job_hashfiles_if(self) -> None:
        workflow = Path(".github/workflows/ci.yml")
        self.assertTrue(workflow.exists(), f"{workflow} should exist")

        text = workflow.read_text(encoding="utf-8")
        self.assertIn("name: CI", text)
        self.assertIn("Public export guard", text)
        self.assertNotIn("hashFiles('.public-export-manifest.json')", text)

    def test_windows_portable_packaging_files_define_self_contained_bundle(self) -> None:
        build_script = Path("packaging/windows/build-portable.ps1")
        launcher = Path("packaging/windows/Start WebUI Portable.bat")
        readme = Path("packaging/windows/README-portable.md")
        notices = Path("packaging/windows/THIRD_PARTY_NOTICES.md")

        for path in (build_script, launcher, readme, notices):
            self.assertTrue(path.exists(), f"{path} should exist")

        build_text = build_script.read_text(encoding="utf-8")
        self.assertIn('$PythonVersion = "3.11.9"', build_text)
        self.assertIn("python-${PythonVersion}-embed-amd64.zip", build_text)
        self.assertIn("get-pip.py", build_text)
        self.assertIn("requirements-webui.txt", build_text)
        self.assertIn("Start WebUI Portable.bat", build_text)
        self.assertIn("THIRD_PARTY_NOTICES.md", build_text)
        self.assertIn("Invoke-WebRequest", build_text)
        self.assertIn("Compress-Archive", build_text)
        self.assertIn("codex_image", build_text)

        launcher_text = launcher.read_text(encoding="utf-8")
        self.assertIn(r"python\python.exe", launcher_text)
        self.assertIn("portable_webui_app:app", launcher_text)
        self.assertIn("api/health", launcher_text)
        self.assertIn("data", launcher_text)

        readme_text = readme.read_text(encoding="utf-8")
        self.assertIn("Do not put API keys", readme_text)
        self.assertIn("OpenAI-compatible API", readme_text)

    def test_macos_portable_packaging_files_define_arch_specific_bundles(self) -> None:
        build_script = Path("packaging/macos/build-portable.sh")
        launcher = Path("packaging/macos/Start WebUI Portable.command")
        app_module = Path("packaging/macos/portable_webui_app.py")
        readme = Path("packaging/macos/README-portable.md")
        notices = Path("packaging/macos/THIRD_PARTY_NOTICES.md")

        for path in (build_script, launcher, app_module, readme, notices):
            self.assertTrue(path.exists(), f"{path} should exist")

        build_text = build_script.read_text(encoding="utf-8")
        self.assertIn('PYTHON_VERSION="3.11.9"', build_text)
        self.assertIn("python-${PYTHON_VERSION}-macos11.pkg", build_text)
        self.assertIn('PACKAGE_ARCH="arm64"', build_text)
        self.assertIn('PACKAGE_ARCH="x64"', build_text)
        self.assertIn('x86_64)', build_text)
        self.assertIn('macos_portable_${PACKAGE_ARCH}', build_text)
        self.assertIn("pkgutil --expand-full", build_text)
        self.assertIn("install_name_tool", build_text)
        self.assertIn('name "*.dylib"', build_text)
        self.assertIn("codesign --force --sign -", build_text)
        self.assertIn("requirements-webui.txt", build_text)
        self.assertIn("Start WebUI Portable.command", build_text)
        self.assertIn("THIRD_PARTY_NOTICES.md", build_text)
        self.assertIn("ditto -c -k", build_text)
        self.assertIn("portable_webui_app", build_text)

        launcher_text = launcher.read_text(encoding="utf-8")
        self.assertIn("Python.framework/Versions/3.11/bin/python3", launcher_text)
        self.assertIn("portable_webui_app:app", launcher_text)
        self.assertIn("api/health", launcher_text)
        self.assertIn("data", launcher_text)

        app_module_text = app_module.read_text(encoding="utf-8")
        self.assertIn("ILAB_CONJURE_DATA_DIR", app_module_text)
        self.assertIn("create_app", app_module_text)

        readme_text = readme.read_text(encoding="utf-8")
        self.assertIn("Double-click", readme_text)
        self.assertIn("Apple Silicon", readme_text)
        self.assertIn("Intel", readme_text)
        self.assertIn("unsigned portable zip", readme_text)
        self.assertIn("xattr -dr com.apple.quarantine", readme_text)
        self.assertIn("OpenAI-compatible API", readme_text)

    def test_portable_release_workflow_runs_after_ci_success(self) -> None:
        workflow = Path(".github/workflows/release-portable.yml")
        self.assertTrue(workflow.exists(), f"{workflow} should exist")

        text = workflow.read_text(encoding="utf-8")
        self.assertIn("workflow_run:", text)
        self.assertIn('workflows: ["CI"]', text)
        self.assertIn("types: [completed]", text)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", text)
        self.assertIn("github.event.workflow_run.event == 'push'", text)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", text)
        self.assertIn("packaging/windows/build-portable.ps1", text)
        self.assertIn("packaging/macos/build-portable.sh", text)
        self.assertIn("macos-15", text)
        self.assertIn("macos-15-intel", text)
        self.assertIn("macos-portable", text)
        self.assertIn("macos-portable-arm64", text)
        self.assertIn("macos-portable-x64", text)
        self.assertIn("actions/upload-artifact", text)
        self.assertIn("actions/download-artifact", text)
        self.assertIn("GH_REPO: ${{ github.repository }}", text)
        self.assertIn("## 发布说明", text)
        self.assertIn("此版本包含 iLab GPT Conjure 对应 tag 的源码和免安装一键包。", text)
        self.assertIn("## 免安装一键包", text)
        self.assertIn('release_version="${RELEASE_TAG#v}"', text)
        self.assertIn("ilab-gpt-conjure_windows_portable_x64_${release_version}.zip", text)
        self.assertNotIn("<version>", text)
        self.assertNotIn("Portable packages for iLab GPT Conjure.", text)
        self.assertIn("gh release upload", text)


if __name__ == "__main__":
    unittest.main()
