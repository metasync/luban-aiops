#!/usr/bin/env python3
"""Documentation hygiene gate for the evergreen docs layer.

Codifies the checks that keep docs/ the single source of truth now that the IDE
Repo Wiki cache is retired (untracked + ignored). Run via `make docs-check`,
which is part of the `make verify` pre-push gate. Pure stdlib; resolves paths
from the repo root so it can be invoked from anywhere.

Four checks, two of them failing:

  1. Broken relative links -- ERROR in the evergreen layer (everything outside
     the frozen docs/specs/SPEC-*/ Tier-2 record); WARN inside frozen specs,
     which are historical and may legitimately point at retired siblings.
  2. Orphaned navigational docs -- ERROR: every top-level guide, workspace note,
     and platform-study doc must be reachable by a markdown link from some doc.
     Dated release notes, spec triads, ADRs, and templates are excluded: they
     are an archive / indexed-by-table, not a navigational tree.
  3. Hard-coded version literals in the Tier-3 guides -- WARN only. Living docs
     state the release by pointing at VERSION/CHANGELOG rather than a literal,
     but past-tense "added in vX.Y.Z" attributions are allowed, so this needs a
     human eye rather than a hard fail.
  4. Unresolvable env-var names in the configuration-reference knob tables --
     WARN only. Every backtick-quoted multi-word env var (``FOO_BAR_BAZ``) in a
     table row should be referenced somewhere in the products/shared/mk source
     or overlays; one that is not has likely been renamed or removed (the drift
     class this gate cannot otherwise see). WARN because a var may be a pure
     operator-set passthrough with no code reader, so it needs a human eye.

Exit status is non-zero if any ERROR is found. See docs/specs/README.md
"Documentation Tiers" for the tier lifecycle these checks enforce.
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Frozen Tier-2 feature-spec record; broken links here are historical, not ERRORs.
FROZEN_SPEC_PREFIX = os.path.join("docs", "specs", "SPEC")

# Top-level (non-recursive) subtrees where every doc must be link-reachable.
# release-notes/ and SPEC-*/ are subdirectories, so they fall outside this scan.
NAV_SUBTREES = (
    os.path.join("docs", "guides"),
    os.path.join("docs", "workspace"),
    os.path.join("docs", "agentic-aiops-platform"),
)

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
SEMVER_RE = re.compile(r"(?<![\w.])\d+\.\d+\.\d+(?![\w.])")
# A literal preceded by an origin marker is a past-tense attribution (allowed).
ATTRIBUTION_RE = re.compile(
    r"(?:in|since|from|added|released|shipped|through|before|after)\s+v?\d+\.\d+\.\d+",
    re.IGNORECASE,
)

# Check 4: env-var drift in the configuration-reference knob tables.
CONFIG_REF = os.path.join("docs", "guides", "configuration-reference.md")
# A multi-word UPPER_SNAKE token (>=2 underscores) -- the shape renames hit, and
# narrow enough to skip make/py constants like IMAGE_TAG or PLATFORM_VERSION.
ENV_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+){2,}\b")
BACKTICK_ENV_RE = re.compile(r"`([A-Z][A-Z0-9]*(?:_[A-Z0-9]+){2,})`")
# Where a documented env var may legitimately be read or set.
CODE_ENV_ROOTS = ("products", "shared", "mk")
CODE_ENV_EXTS = {".py", ".env", ".yaml", ".yml", ".toml", ".sh", ".example", ".mk"}
CODE_ENV_BASENAMES = {"Makefile"}
PRUNE_DIRS = {
    ".venv", "node_modules", "__pycache__", ".git", "dist", "build",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}
MAX_SCAN_BYTES = 2_000_000


def collect_markdown() -> list[str]:
    """Every .md under docs/ plus the root entry docs, as repo-relative paths."""
    files: list[str] = []
    for root, _dirs, names in os.walk(os.path.join(ROOT, "docs")):
        for n in names:
            if n.endswith(".md"):
                files.append(os.path.relpath(os.path.join(root, n), ROOT))
    for n in ("README.md", "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md"):
        if os.path.exists(os.path.join(ROOT, n)):
            files.append(n)
    return sorted(files)


def link_path(raw: str) -> str:
    """Strip an optional "title" and #fragment; return just the path (or '')."""
    return re.split(r'\s+"', raw.strip())[0].split("#")[0].strip()


def is_external(raw: str) -> bool:
    return raw.strip().startswith(("http://", "https://", "mailto:", "<", "//", "#"))


def is_ip_like(text: str) -> bool:
    parts = text.split(".")
    return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


def collect_code_env_tokens() -> set[str]:
    """Every UPPER_SNAKE env-var token referenced in products/shared/mk source.

    Walks the code and overlay trees (pruning .venv/node_modules/caches) and
    harvests tokens from Python, env fragments, YAML, shell, and makefiles, so a
    var read via ``os.getenv`` or set in a runtime-config.env both count as real.
    """
    tokens: set[str] = set()
    roots = [os.path.join(ROOT, top) for top in CODE_ENV_ROOTS]
    roots.append(os.path.join(ROOT, "Makefile"))
    for base in roots:
        if os.path.isfile(base):
            _harvest_env_file(base, tokens)
            continue
        if not os.path.isdir(base):
            continue
        for root, dirs, names in os.walk(base):
            dirs[:] = [d for d in dirs if d not in PRUNE_DIRS]
            for n in names:
                if os.path.splitext(n)[1] in CODE_ENV_EXTS or n in CODE_ENV_BASENAMES:
                    _harvest_env_file(os.path.join(root, n), tokens)
    return tokens


def _harvest_env_file(path: str, tokens: set[str]) -> None:
    try:
        if os.path.getsize(path) > MAX_SCAN_BYTES:
            return
        with open(path, encoding="utf-8", errors="ignore") as fh:
            tokens.update(ENV_TOKEN_RE.findall(fh.read()))
    except OSError:
        return


def documented_env_vars() -> list[tuple[int, str]]:
    """(line, var) for each distinct backtick-quoted env var in the config-ref tables."""
    path = os.path.join(ROOT, CONFIG_REF)
    if not os.path.exists(path):
        return []
    hits: list[tuple[int, str]] = []
    seen: set[str] = set()
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh.read().splitlines(), 1):
            if not line.lstrip().startswith("|"):
                continue
            for var in BACKTICK_ENV_RE.findall(line):
                if var not in seen:
                    seen.add(var)
                    hits.append((lineno, var))
    return hits


def main() -> int:
    os.chdir(ROOT)
    md = collect_markdown()
    text = {f: open(f, encoding="utf-8").read() for f in md}

    broken_evergreen: list[tuple[str, str]] = []
    broken_frozen: list[tuple[str, str]] = []
    linked: set[str] = set()

    for f in md:
        base = os.path.dirname(f)
        for raw in LINK_RE.findall(text[f]):
            if is_external(raw):
                continue
            target = link_path(raw)
            if not target:
                continue
            resolved = os.path.normpath(os.path.join(base, target))
            if not os.path.exists(resolved):
                (broken_frozen if f.startswith(FROZEN_SPEC_PREFIX) else broken_evergreen).append((f, raw))
            elif target.endswith(".md"):
                linked.add(resolved)

    orphans: list[str] = []
    for sub in NAV_SUBTREES:
        if not os.path.isdir(sub):
            continue
        for name in sorted(os.listdir(sub)):
            p = os.path.join(sub, name)
            if os.path.isfile(p) and name.endswith(".md") and p not in linked:
                orphans.append(p)

    version_warns: list[tuple[str, int, str]] = []
    guides = os.path.join("docs", "guides")
    for name in sorted(os.listdir(guides)) if os.path.isdir(guides) else []:
        if not name.endswith(".md"):
            continue
        p = os.path.join(guides, name)
        for lineno, line in enumerate(text.get(p, "").splitlines(), 1):
            for m in SEMVER_RE.finditer(line):
                literal = m.group(0)
                if is_ip_like(literal):
                    continue
                window = line[max(0, m.start() - 14):m.end()]
                if ATTRIBUTION_RE.search(window):
                    continue
                version_warns.append((p, lineno, literal))

    broken_evergreen.sort()
    broken_frozen.sort()

    code_env = collect_code_env_tokens()
    env_var_warns = [(ln, var) for ln, var in documented_env_vars() if var not in code_env]

    def header(label: str) -> None:
        print(f"\n== {label} ==")

    print(f"docs-check: scanned {len(md)} markdown files (docs/ + root entry docs)")

    header(f"1a. Broken links, evergreen layer (ERROR): {len(broken_evergreen)}")
    for f, raw in broken_evergreen:
        print(f"    {f} -> {raw}")

    header(f"1b. Broken links, frozen SPEC record (WARN, historical): {len(broken_frozen)}")
    for f, raw in broken_frozen[:10]:
        print(f"    {f} -> {raw}")
    if len(broken_frozen) > 10:
        print(f"    ... and {len(broken_frozen) - 10} more (frozen Tier-2 specs; left as-is)")

    header(f"2. Orphaned navigational docs (ERROR): {len(orphans)}")
    for p in orphans:
        print(f"    {p}  (not linked from any index)")

    header(f"3. Hard-coded version literals in docs/guides (WARN): {len(version_warns)}")
    for p, lineno, literal in version_warns:
        print(f"    {p}:{lineno}  '{literal}'  (point at VERSION/CHANGELOG instead)")

    header(f"4. Config-reference env vars not found in code/overlays (WARN): {len(env_var_warns)}")
    for lineno, var in env_var_warns:
        print(f"    {CONFIG_REF}:{lineno}  '{var}'  (no code/overlay reference; renamed or removed?)")

    errors = len(broken_evergreen) + len(orphans)
    print("")
    if errors:
        print(f"FAIL: {errors} error(s) -- {len(broken_evergreen)} broken evergreen link(s), "
              f"{len(orphans)} orphan(s)")
        return 1
    print(f"PASS: evergreen docs layer is link-clean and fully indexed "
          f"({len(broken_frozen)} frozen-spec link(s), {len(version_warns)} version literal(s), "
          f"{len(env_var_warns)} unresolved env var(s) noted as warnings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
