"""Shared Node runner; ``python -m tests.frontend_runner`` runs pure frontend tests."""

from __future__ import annotations

import argparse
import ast
from functools import wraps
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "tests" / "frontend"
# This suite consumes a real FastAPI response supplied by its Python test.
BACKEND_FIXTURE_SUITES = frozenset({"catalog_payload_parity.test.ts"})
SKIP_FRONTEND_ENV = "ILAB_SKIP_PURE_FRONTEND_TESTS"


def frontend_test(method):
    """Keep an inline Node harness locally, but run it once in frontend CI."""
    @wraps(method)
    def run(case):
        if os.environ.get(SKIP_FRONTEND_ENV) == "1":
            case.skipTest("pure frontend suite runs in the WebUI CI job")
        return method(case)
    return run


def inline_frontend_tests() -> list[str]:
    """Discover explicitly marked harnesses without importing backend fixtures."""
    names = []
    for path in sorted((ROOT / "tests").glob("test_webui_static*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for cls in tree.body:
            if not isinstance(cls, ast.ClassDef):
                continue
            for method in cls.body:
                if isinstance(method, ast.FunctionDef) and any(
                    isinstance(decorator, ast.Name) and decorator.id == "frontend_test"
                    for decorator in method.decorator_list
                ):
                    names.append(f"tests.{path.stem}.{cls.name}.{method.name}")
    return names


def node_suite(filenames: list[str] | tuple[str, ...] | None = None) -> unittest.TestSuite:
    """One named unittest per discovered Node file, shared by both entrypoints."""
    methods = {}
    for filename in pure_frontend_suites() if filenames is None else filenames:
        def run(case, name=filename):
            run_frontend(case, name)
        run.__doc__ = filename
        name = "test_" + filename.split(".test.", 1)[0]
        if name in methods:
            raise ValueError(f"Duplicate frontend test name: {filename}")
        methods[name] = run
    case_type = type("PureFrontendTests", (unittest.TestCase,), methods)
    case_type.__module__ = __name__
    return unittest.defaultTestLoader.loadTestsFromTestCase(case_type)


def compatibility_load_tests(filenames: tuple[str, ...]):
    """Old module commands still work; discovery collects their suites centrally."""
    def load_tests(loader, standard_tests, pattern):
        if pattern is None:
            standard_tests.addTests(node_suite(filenames))
        return standard_tests
    return load_tests


def frontend_tools() -> tuple[str, Path]:
    node = shutil.which("node")
    esbuild = ROOT / "node_modules" / ".bin" / ("esbuild.cmd" if os.name == "nt" else "esbuild")
    if node is None or not esbuild.is_file():
        raise RuntimeError("node and npm ci are required for frontend behavior tests")
    return node, esbuild


def pure_frontend_suites() -> list[str]:
    return sorted(
        path.name
        for pattern in ("*.test.ts", "*.test.cjs")
        for path in FRONTEND.glob(pattern)
        if path.name not in BACKEND_FIXTURE_SUITES
    )


def run_frontend(
    case: unittest.TestCase,
    filename: str,
    *,
    backend_fixture: bool = False,
    node_test: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Bundle and execute a suite, or a helper that returns JSON on stdout.

    Local unittest discovery still includes frontend tests. CI moves only pure
    suites to the WebUI job; callers using real backend fixtures opt out.
    """
    if not backend_fixture and os.environ.get(SKIP_FRONTEND_ENV) == "1":
        case.skipTest("pure frontend suite runs in the WebUI CI job")
    if filename in BACKEND_FIXTURE_SUITES and not backend_fixture:
        raise ValueError(f"{filename} requires a backend fixture")
    try:
        node, esbuild = frontend_tools()
    except RuntimeError as error:
        case.skipTest(str(error))

    source = FRONTEND / filename
    case.assertTrue(source.is_file(), f"Missing frontend suite: {filename}")
    with tempfile.TemporaryDirectory(prefix="ilab-frontend-") as directory:
        output = source
        if source.suffix == ".ts":
            output = Path(directory) / (source.stem + ".mjs")
            build = subprocess.run(
                [str(esbuild), str(source), "--bundle", "--platform=node",
                 "--format=esm", "--target=node20", f"--outfile={output}",
                 "--log-level=warning"],
                cwd=ROOT, check=False, capture_output=True, text=True,
            )
            case.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        result = subprocess.run(
            [node, *(["--test"] if node_test else []), str(output)],
            cwd=ROOT, check=False, capture_output=True, text=True,
            env={**os.environ, **(env or {})},
        )
        case.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suites", nargs="*", help="Node filenames or inline unittest IDs; defaults to all pure suites")
    args = parser.parse_args()
    node_names = pure_frontend_suites()
    inline_names = inline_frontend_tests()
    available = node_names + inline_names
    selected = args.suites or available
    if not selected:
        parser.error(f"no pure frontend suites found in {FRONTEND}")
    unknown = set(selected) - set(available)
    if unknown:
        parser.error(f"not a pure frontend suite: {', '.join(sorted(unknown))}")
    if os.environ.get(SKIP_FRONTEND_ENV) == "1":
        parser.error(f"unset {SKIP_FRONTEND_ENV} to run the frontend job")
    # A dedicated frontend job must fail, not silently succeed with all skipped.
    try:
        frontend_tools()
    except RuntimeError as error:
        parser.error(str(error))
    suite = node_suite([name for name in selected if name in node_names])
    suite.addTests(unittest.defaultTestLoader.loadTestsFromNames(
        [name for name in selected if name in inline_names]
    ))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
