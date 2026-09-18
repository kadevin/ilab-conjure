from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(shutil.which("zsh"), "macOS updater requires zsh")
class MacOSPortableUpdateTests(unittest.TestCase):
    def test_replace_and_rollback_do_not_depend_on_moved_python(self) -> None:
        source = Path("packaging/macos/Update WebUI Portable.command").read_text()
        functions = source[source.index("assert_replace_item_name()"):source.index("trap cleanup EXIT")]
        loops = source[source.index('step "Backing up current app files"'):source.index('chmod +x "${BUNDLE_DIR}/Start WebUI')]
        for failure in ("none", "app", "python", "copy"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                bundle, new = root / "bundle", root / "new"
                for base, marker in ((bundle, "old"), (new, "new")):
                    for name in ("app", "python", "launcher"):
                        (base / name).mkdir(parents=True)
                        (base / name / "marker").write_text(marker)
                interpreter = bundle / "python/bin/python3"
                interpreter.parent.mkdir()
                interpreter.symlink_to(sys.executable)
                (bundle / "data").mkdir()
                (bundle / "data/keep").write_text("user data")
                script = root / "test.zsh"
                script.write_text('''set -e
set -o pipefail
BUNDLE_DIR="$1"
NEW_ROOT="$2"
FAILURE="$3"
BACKUP_DIR="$BUNDLE_DIR/.backup/test"
PYTHON_BIN="$BUNDLE_DIR/python/bin/python3"
REPLACE_ITEMS=(app python launcher)
step() { :; }
cleanup() { :; }
pause_to_close() { :; }
mv() {
  command mv "$@" || return $?
  if [[ "$1" == "$BUNDLE_DIR/$FAILURE" ]]; then FAILURE=done; return 1; fi
  return 0
}
cp() {
  command cp "$@" || return $?
  if [[ "$FAILURE" == copy ]]; then FAILURE=done; return 1; fi
  return 0
}
''' + functions + loops)
                run = subprocess.run(["zsh", str(script), str(bundle), str(new), failure], capture_output=True, text=True, timeout=15)
                self.assertEqual(run.returncode, 0 if failure == "none" else 1, run.stderr)
                expected = "new" if failure == "none" else "old"
                for name in ("app", "python", "launcher"):
                    self.assertEqual((bundle / name / "marker").read_text(), expected, run.stderr)
                self.assertEqual((bundle / "data/keep").read_text(), "user data")

    def test_path_guard_rejects_root_parent_and_symlink_escape(self) -> None:
        source = Path("packaging/macos/Update WebUI Portable.command").read_text()
        guard = source[source.index("assert_in_bundle()"):source.index("restore_backup()")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / "bundle"
            bundle.mkdir()
            (bundle / "escape").symlink_to(root, target_is_directory=True)
            for target in (bundle, root, bundle / "escape/nested"):
                run = subprocess.run(["zsh", "-c", 'BUNDLE_DIR="$1"\n' + guard + '\nassert_in_bundle "$2"', "test", str(bundle), str(target)])
                self.assertNotEqual(run.returncode, 0)
