"""Dependency-free startup checks; also executable before packages are installed."""
from __future__ import annotations

import argparse
import re
import sys
from importlib.metadata import PackageNotFoundError, version
from collections.abc import Sequence


# Python's October 2026 security releases, including the emSign trust-store fix.
MINIMUM_PYTHON_PATCHES = {(3, 11): 18, (3, 12): 16, (3, 13): 18, (3, 14): 10, (3, 15): 2}
MINIMUM_PIP = (26, 2, 2)
# Security floors, separate from the exact versions in the installation lock.
MINIMUM_RUNTIME_DEPENDENCIES = {"Pillow": (13, 0, 0), "certifi": (2026, 10, 19)}


def python_security_error(version_info: Sequence[int] | None = None) -> str | None:
    current = tuple((sys.version_info if version_info is None else version_info)[:3])
    label = ".".join(map(str, current))
    if current[:2] < (3, 11):
        return f"Python {label} is unsupported. Use a security-patched Python 3.11 or newer."
    minimum = MINIMUM_PYTHON_PATCHES.get(current[:2])
    if minimum is not None and current[2] < minimum:
        required = ".".join(map(str, (*current[:2], minimum)))
        return (
            f"Python {label} is below the security baseline {required}. "
            "Choose a patched interpreter and recreate this project's virtual environment; "
            "updating Python packages alone does not update the interpreter."
        )
    return None


def _version_label(installed: str | None) -> str:
    if isinstance(installed, str) and installed.strip():
        return installed.strip()
    return "unknown (missing or invalid version metadata)"


def pip_security_error(installed: str | None = None) -> str | None:
    if installed is None:
        try:
            installed = version("pip")
        except PackageNotFoundError:
            installed = "not installed"
        except (FileNotFoundError, KeyError):
            # Python 3.15 raises for missing METADATA or a missing Version field.
            installed = None
    installed = _version_label(installed)
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", installed)
    if match and tuple(int(part or 0) for part in match.groups()) >= MINIMUM_PIP:
        return None
    return (
        f"pip {installed} cannot be used to install dependencies. "
        "Install pip 26.2.2 or newer in this project's virtual environment using "
        "a verified wheel before retrying. Do not disable TLS verification."
    )


def dependency_security_error() -> str | None:
    """Check package metadata without importing image parsers or requiring pip."""
    for name, minimum in MINIMUM_RUNTIME_DEPENDENCIES.items():
        try:
            installed = version(name)
        except PackageNotFoundError:
            installed = "not installed"
        except (FileNotFoundError, KeyError):
            installed = None
        installed = _version_label(installed)
        match = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?(?:\.post\d+)?", installed)
        if match and tuple(int(part or 0) for part in match.groups()) >= minimum:
            continue
        required = ".".join(map(str, minimum))
        return (
            f"{name} {installed} does not meet the security baseline {required}. "
            "Update this project's environment from requirements-webui.txt, "
            "or replace the complete native application package. Keep existing user data."
        )
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the Python security baseline.")
    parser.add_argument("--installer", action="store_true", help="Also check pip before installing packages.")
    parser.add_argument("--runtime", action="store_true", help="Also check installed runtime dependencies; pip is not required.")
    args = parser.parse_args(argv)
    problem = python_security_error()
    if problem is None and args.installer:
        problem = pip_security_error()
    if problem is None and args.runtime:
        problem = dependency_security_error()
    if problem:
        print(problem, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
