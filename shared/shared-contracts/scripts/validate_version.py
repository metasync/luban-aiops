#!/usr/bin/env python3
"""Validate platform version consistency across the workspace.

The root VERSION file is the single source of truth for the platform
semver. All products ship in lockstep with it, so this script fails on
any drift between VERSION and:

  - products/*/pyproject.toml          ([project] version)
  - products/*/src/*/metadata.py       (SERVICE_VERSION)
  - products/*/src/*/__init__.py       (__version__, where present)
  - products/operator-portal/web-ui/app/vite.config.ts (SPEC-023: the
    build-time PLATFORM_VERSION injection must keep reading the root
    VERSION file)

Usage:
    python validate_version.py [repo-root]

Defaults to the repository containing this script. Exits 0 on success,
1 on any drift or malformed version.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
SERVICE_VERSION_RE = re.compile(r'^SERVICE_VERSION = "([^"]+)"', re.MULTILINE)
DUNDER_VERSION_RE = re.compile(r'^__version__ = "([^"]+)"', re.MULTILINE)
# SPEC-023 R-1: the rebuild injects PLATFORM_VERSION at build time from the
# root VERSION file; assert the injection wiring instead of a literal.
VITE_VERSION_READ_RE = re.compile(
    r'new URL\("\.\./\.\./\.\./\.\./VERSION", import\.meta\.url\)'
)
VITE_VERSION_DEFINE_RE = re.compile(
    r"__PLATFORM_VERSION__:\s*JSON\.stringify\(platformVersion\)"
)


def repo_root() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    # shared/shared-contracts/scripts/validate_version.py -> repo root
    return Path(__file__).resolve().parents[3]


def check_file(
    errors: list[str], path: Path, pattern: re.Pattern, label: str, expected: str
) -> None:
    if not path.is_file():
        errors.append(f"{label}: missing file: {path}")
        return
    match = pattern.search(path.read_text(encoding="utf-8"))
    if not match:
        errors.append(f"{label}: version not found in {path}")
        return
    found = match.group(1)
    if found != expected:
        errors.append(f"{label}: {path} has {found!r}, expected {expected!r}")


def check_wiring(errors: list[str], path: Path, pattern: re.Pattern, label: str) -> None:
    """Assert a pattern exists in a file (no version capture involved)."""
    if not path.is_file():
        errors.append(f"{label}: missing file: {path}")
        return
    if not pattern.search(path.read_text(encoding="utf-8")):
        errors.append(f"{label}: expected wiring not found in {path}")


def main() -> int:
    root = repo_root()
    version_file = root / "VERSION"
    if not version_file.is_file():
        print(f"error: VERSION file not found at {version_file}", file=sys.stderr)
        return 1

    expected = version_file.read_text(encoding="utf-8").strip()
    if not SEMVER_RE.match(expected):
        print(
            f"error: VERSION is not a valid semver (MAJOR.MINOR.PATCH): {expected!r}",
            file=sys.stderr,
        )
        return 1

    errors: list[str] = []
    products_dir = root / "products"

    for pyproject in sorted(products_dir.glob("*/pyproject.toml")):
        product = pyproject.parent.name
        try:
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            errors.append(f"{product}: unparseable pyproject.toml: {exc}")
            continue
        found = data.get("project", {}).get("version")
        if found != expected:
            errors.append(
                f"{product}: pyproject.toml version is {found!r}, expected {expected!r}"
            )

        # SERVICE_VERSION in the product's metadata module.
        for metadata in sorted(pyproject.parent.glob("src/*/metadata.py")):
            check_file(
                errors, metadata, SERVICE_VERSION_RE, product, expected
            )

        # __version__ in package roots that declare one.
        for init in sorted(pyproject.parent.glob("src/*/__init__.py")):
            text = init.read_text(encoding="utf-8")
            if "__version__" not in text:
                continue
            check_file(errors, init, DUNDER_VERSION_RE, product, expected)

    # Portal version constant. The Vite rebuild (SPEC-023) derives
    # PLATFORM_VERSION from the root VERSION file at build time, so we
    # assert the injection wiring in vite.config.ts.
    vite_config = (
        products_dir / "operator-portal" / "web-ui" / "app" / "vite.config.ts"
    )
    check_wiring(
        errors,
        vite_config,
        VITE_VERSION_READ_RE,
        "operator-portal (vite VERSION read)",
    )
    check_wiring(
        errors,
        vite_config,
        VITE_VERSION_DEFINE_RE,
        "operator-portal (vite PLATFORM_VERSION define)",
    )

    if errors:
        print(f"FAIL: {len(errors)} version drift(s) against VERSION={expected}:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"OK: all product and portal versions match VERSION={expected}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
