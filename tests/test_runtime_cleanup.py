from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


def load_cleanup_module():
    spec = importlib.util.spec_from_file_location("cleanup_runtime", "packaging/cleanup-runtime.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipIf(sys.platform == "win32", "macOS framework fixtures require Unix symlinks")
class MacOSRuntimeCleanupTests(unittest.TestCase):
    def test_pruned_headers_links_are_removed_without_damaging_runtime_links(self) -> None:
        cleanup = load_cleanup_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            framework = root / "Python.framework"
            versions = framework / "Versions"
            for version in ("3.11", "3.12"):
                current = versions / version
                headers = current / "include" / f"python{version}"
                headers.mkdir(parents=True)
                (headers / "Python.h").write_text("header fixture")
                (current / "Headers").symlink_to(f"include/python{version}", target_is_directory=True)
                (current / "Python").write_bytes(b"runtime fixture")
                (current / "Resources").mkdir()
                (current / "lib").mkdir()
            (versions / "Current").symlink_to("3.12", target_is_directory=True)
            for name in ("Headers", "Python", "Resources", "lib"):
                (framework / name).symlink_to(f"Versions/Current/{name}")

            # The second pass also covers already-pruned portable runtimes.
            for _ in range(2):
                cleanup.cleanup_macos_runtime(root)
                for headers in (framework / "Headers", versions / "3.11/Headers", versions / "3.12/Headers"):
                    self.assertFalse(headers.is_symlink(), f"dangling link retained: {headers}")
                    self.assertFalse(headers.exists())
                for link in (versions / "Current", framework / "Python", framework / "Resources", framework / "lib"):
                    self.assertTrue(link.is_symlink())
                    self.assertTrue(link.exists())
                self.assertEqual((framework / "Python").read_bytes(), b"runtime fixture")

    def test_valid_headers_directory_or_link_is_preserved(self) -> None:
        cleanup = load_cleanup_module()
        for linked in (False, True):
            with self.subTest(linked=linked), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                framework = root / "Python.framework"
                current = framework / "Versions/3.11"
                current.mkdir(parents=True)
                target = current / ("SDKHeaders" if linked else "Headers")
                target.mkdir()
                (target / "Python.h").write_text("retained header")
                if linked:
                    (current / "Headers").symlink_to("SDKHeaders", target_is_directory=True)
                (framework / "Headers").symlink_to("Versions/3.11/Headers", target_is_directory=True)
                cleanup.cleanup_macos_runtime(root)
                self.assertEqual((framework / "Headers/Python.h").read_text(), "retained header")

    def test_cleanup_refuses_headers_link_target_outside_runtime(self) -> None:
        cleanup = load_cleanup_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / "runtime"
            framework = runtime / "Python.framework"
            current = framework / "Versions/3.11"
            current.mkdir(parents=True)
            outside = root / "outside"
            outside.mkdir()
            sentinel = outside / "keep.txt"
            sentinel.write_text("preserve")
            (current / "Headers").symlink_to(outside / "missing-headers", target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "outside cleanup root"):
                cleanup.cleanup_macos_runtime(runtime)
            self.assertEqual(sentinel.read_text(), "preserve")
            self.assertTrue((current / "Headers").is_symlink())


if __name__ == "__main__":
    unittest.main()
