#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


BUILD_ONLY_APP_PATHS = (
    "codex_image/webui/frontend",
    "codex_image/webui/static/styles",
    "launcher",
    "package.json",
    "package-lock.json",
    "tsconfig.webui.json",
    "scripts/build-webui-css.mjs",
)

BUILD_TOOL_PACKAGES = (
    "pip",
    "setuptools",
    "wheel",
    "packaging",
    "_distutils_hack",
    "pkg_resources",
)


def _remove(path: Path, *, root: Path) -> None:
    root = root.resolve()
    candidate = path.resolve(strict=False)
    if candidate == root or root not in candidate.parents:
        raise ValueError(f"Refusing to remove path outside cleanup root: {path}")
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _remove_matching(directory: Path, patterns: tuple[str, ...], *, root: Path) -> None:
    if not directory.is_dir():
        return
    for pattern in patterns:
        for path in directory.glob(pattern):
            _remove(path, root=root)


def _remove_build_tool_packages(site_packages: Path, *, root: Path) -> None:
    patterns: list[str] = ["distutils-precedence.pth"]
    for package in BUILD_TOOL_PACKAGES:
        patterns.extend(
            (
                package,
                f"{package}-*.dist-info",
                f"{package}-*.egg-info",
            )
        )
    _remove_matching(site_packages, tuple(patterns), root=root)


def _remove_test_trees(root_dir: Path, *, root: Path) -> None:
    if not root_dir.is_dir():
        return
    candidates = [
        path
        for path in root_dir.rglob("*")
        if path.is_dir() and path.name in {"test", "tests"}
    ]
    for path in sorted(candidates, key=lambda item: len(item.parts), reverse=True):
        _remove(path, root=root)


def cleanup_app(app_dir: Path) -> None:
    app_dir = app_dir.resolve()
    for relative in BUILD_ONLY_APP_PATHS:
        _remove(app_dir / relative, root=app_dir)

    static_dir = app_dir / "codex_image" / "webui" / "static"
    if static_dir.is_dir():
        for source_map in static_dir.rglob("*.map"):
            _remove(source_map, root=app_dir)

    dependencies = app_dir / ".deps"
    _remove_test_trees(dependencies, root=app_dir)
    _remove_build_tool_packages(dependencies, root=app_dir)

    scripts_dir = app_dir / "scripts"
    if scripts_dir.is_dir() and not any(scripts_dir.iterdir()):
        _remove(scripts_dir, root=app_dir)


def cleanup_macos_runtime(runtime_dir: Path) -> None:
    runtime_dir = runtime_dir.resolve()
    framework = runtime_dir / "Python.framework" / "Versions"
    if not framework.is_dir():
        return
    headers_links = [framework.parent / "Headers"]
    for version_dir in framework.iterdir():
        if not version_dir.is_dir() or version_dir.name == "Current":
            continue
        headers_links.append(version_dir / "Headers")
        for relative in ("include", "share"):
            _remove(version_dir / relative, root=runtime_dir)
        for stdlib in (version_dir / "lib").glob("python3.*"):
            _remove_test_trees(stdlib, root=runtime_dir)
            for relative in ("test", "tests", "ensurepip", "idlelib", "turtledemo"):
                _remove(stdlib / relative, root=runtime_dir)
            _remove_build_tool_packages(stdlib / "site-packages", root=runtime_dir)
        _remove_matching(
            version_dir / "bin",
            ("pip*", "idle*", "2to3*", "pydoc*"),
            root=runtime_dir,
        )

    # Pruning include/ leaves framework Headers aliases dangling. Remove only
    # broken aliases, from the version outwards; retain valid runtime/SDK links.
    for headers in reversed(headers_links):
        if headers.is_symlink() and not headers.exists():
            _remove(headers, root=runtime_dir)


def cleanup_windows_runtime(runtime_dir: Path) -> None:
    runtime_dir = runtime_dir.resolve()
    _remove_test_trees(runtime_dir / "Lib", root=runtime_dir)
    _remove_build_tool_packages(runtime_dir / "Lib" / "site-packages", root=runtime_dir)
    _remove_matching(
        runtime_dir / "Scripts",
        ("pip*.exe", "pip*.py", "wheel.exe"),
        root=runtime_dir,
    )


def cleanup_runtime(app_dir: Path, runtime_dir: Path, platform: str) -> None:
    cleanup_app(app_dir)
    if platform == "macos":
        cleanup_macos_runtime(runtime_dir)
    elif platform == "windows":
        cleanup_windows_runtime(runtime_dir)
    else:
        raise ValueError(f"Unsupported platform: {platform}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove build-only files from an iLab CONJURE packaged runtime."
    )
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--platform", choices=("macos", "windows"), required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cleanup_runtime(args.app_dir, args.runtime_dir, args.platform)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
