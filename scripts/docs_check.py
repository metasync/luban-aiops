#!/usr/bin/env python3
"""Documentation hygiene gate for the evergreen docs layer.

Codifies the checks that keep docs/ the single source of truth now that the IDE
Repo Wiki cache is retired (untracked + ignored). Run via `make docs-check`,
which is part of the `make verify` pre-push gate. Pure stdlib; resolves paths
from the repo root so it can be invoked from anywhere.

Three checks, two of them failing:

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

    errors = len(broken_evergreen) + len(orphans)
    print("")
    if errors:
        print(f"FAIL: {errors} error(s) -- {len(broken_evergreen)} broken evergreen link(s), "
              f"{len(orphans)} orphan(s)")
        return 1
    print(f"PASS: evergreen docs layer is link-clean and fully indexed "
          f"({len(broken_frozen)} frozen-spec link(s), {len(version_warns)} version literal(s) noted as warnings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
