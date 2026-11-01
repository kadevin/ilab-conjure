from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .runtime_security import python_security_error


RUNTIME_IMPORTS = ("fastapi", "uvicorn", "multipart", "httpx", "PIL")
PIN_PATTERN = re.compile(
    r"^(?P<name>[A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_.-]+\])?==(?P<version>[^\s;\\]+)"
)


def _canonical_package_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def pinned_versions(requirements_path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in requirements_path.read_text(encoding="utf-8").splitlines():
        match = PIN_PATTERN.match(line.strip())
        if match is None:
            continue
        pins[_canonical_package_name(match.group("name"))] = match.group("version")
    return pins


def dependency_mismatches(
    requirements_path: Path,
    *,
    distribution_version: Callable[[str], str] = version,
    package_names: Iterable[str] | None = None,
) -> list[str]:
    pins = pinned_versions(requirements_path)
    mismatches: list[str] = []
    checked_names = pins if package_names is None else package_names
    for raw_name in checked_names:
        name = _canonical_package_name(raw_name)
        required = pins.get(name)
        if required is None:
            mismatches.append(f"{name}: missing exact pin")
            continue
        try:
            installed = distribution_version(name)
        except PackageNotFoundError:
            mismatches.append(f"{name}: not installed, required {required}")
            continue
        if installed != required:
            mismatches.append(f"{name}: installed {installed}, required {required}")
    return mismatches


def verify_runtime_dependencies(requirements_path: Path) -> list[str]:
    if problem := python_security_error():
        return [problem]
    mismatches = dependency_mismatches(requirements_path)
    if mismatches:
        return mismatches
    for module_name in RUNTIME_IMPORTS:
        try:
            import_module(module_name)
        except Exception as exc:
            return [f"{module_name}: import failed ({type(exc).__name__})"]
    return []


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify pinned WebUI runtime dependencies.")
    parser.add_argument("--requirements", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        mismatches = verify_runtime_dependencies(args.requirements)
    except OSError as exc:
        print(f"Unable to read dependency lock: {exc}", file=sys.stderr)
        return 1
    if mismatches:
        print("\n".join(mismatches), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
