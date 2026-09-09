#!/usr/bin/env python3
"""Validate the cross-product secret literals are in lockstep.

Three couplings are pinned here, each a deliberate **second copy** of a
constant in a product that never imports the other.

1. The secret-parameter redaction vocabulary. SPEC-054 R-3 masks
   secret-bearing values in the change-request projection using a
   name-substring vocabulary carried kernel-side in agent-platform
   (``secret_params.SECRET_PARAM_SUBSTRINGS``), a copy of the tool-gateway's
   evidence-redaction list (``browser_connector._SECRET_QUERY_PARAMS``,
   SPEC-049 R-5): the projection is assembled in the agent-platform kernel,
   where the gateway's known-secret value set is unavailable, so it masks by
   the same names. A copy (rather than a shared mounted file) is intentional —
   a vocabulary in a data file would fail *open* (nothing masked) if the file
   were missing, whereas a constant has no such failure mode.

2. The credential-hole marker. SPEC-055 R-2 replaces a literal credential with
   ``secret_params.TRACE_CREDENTIAL_PLACEHOLDER`` when it captures an
   authoring-trace step, and SPEC-055 R-3 rejects an executable-flow document
   whose args still carry one, matching
   ``skills_hub.ingestion.CREDENTIAL_HOLE``. Divergence here fails *open* in
   the ingestion check — a renamed marker would no longer be recognized, so an
   unresolved hole would ingest instead of being rejected.

3. The secret-*shape* vocabulary. The tool-gateway redacts tool output by
   shape (``tools/redaction._VALUE_PATTERNS``), agent-platform's model-written
   skill-draft body redacts by the same shapes
   (``services/skill_draft.REDACTION_VALUE_PATTERNS``), and SPEC-055 R-4
   graduation **refuses** a captured step whose argument matches one. Divergence
   fails *open* in the graduation guard: a shape the gateway added and
   agent-platform did not mirror would still be redacted out of tool output and
   out of the draft's readable body, while the value itself rode unrefused into
   the frontmatter a human merges — the one copy that is never scrubbed,
   because a redacted argument would replay the wrong value.

All three pairs live in different products, so this script compares them
**textually**: it extracts each literal from source and diffs them (the
substring vocabulary as sets, the marker by equality, the shape patterns as
ordered lists because both copies document their order as meaningful). It fails
the build on any divergence so the copies cannot drift silently (the
``validate-secret-vocabulary`` leg of ``make verify``).

Usage:
    python validate_secret_vocabulary.py [repo-root]

Defaults to the repository containing this script. Exits 0 when all three
couplings agree, 1 on any divergence or extraction failure.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# The two source copies of the vocabulary, as repo-root-relative paths, and the
# module-level tuple each declares.
AGENT_PLATFORM_REL = "products/agent-platform/src/agent_service/services/secret_params.py"
AGENT_PLATFORM_VAR = "SECRET_PARAM_SUBSTRINGS"
TOOL_GATEWAY_REL = "products/tool-gateway/src/tool_gateway/tools/browser_connector.py"
TOOL_GATEWAY_VAR = "_SECRET_QUERY_PARAMS"

# The credential-hole marker (SPEC-055 R-2 writes it, R-3 refuses it).
SKILLS_HUB_REL = "products/skills-hub/src/skills_hub/services/ingestion.py"
SKILLS_HUB_VAR = "CREDENTIAL_HOLE"
AGENT_PLATFORM_HOLE_VAR = "TRACE_CREDENTIAL_PLACEHOLDER"

# The secret-shape vocabulary (the gateway redacts tool output with it,
# agent-platform redacts a draft body with it, SPEC-055 R-4 graduation refuses a
# step argument matching it).
AGENT_DRAFT_REL = "products/agent-platform/src/agent_service/services/skill_draft.py"
AGENT_DRAFT_PATTERNS_VAR = "REDACTION_VALUE_PATTERNS"
REDACTION_REL = "products/tool-gateway/src/tool_gateway/tools/redaction.py"
REDACTION_PATTERNS_VAR = "_VALUE_PATTERNS"


def repo_root() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    # shared/shared-contracts/scripts/validate_secret_vocabulary.py -> repo root
    return Path(__file__).resolve().parents[3]


def _tuple_pattern(var_name: str) -> re.Pattern[str]:
    """Match a module-level ``VAR[: annotation] = ( ... )`` tuple literal.

    The vocabulary tuples hold only string literals (no nested parens), so the
    body is captured up to the first ``)``.
    """
    return re.compile(
        rf"^{re.escape(var_name)}\s*(?::[^=]+)?=\s*\(([^)]*)\)",
        re.MULTILINE,
    )


def extract_vocabulary(
    errors: list[str], root: Path, rel: str, var_name: str, label: str
) -> set[str] | None:
    """Extract one product's vocabulary tuple as a set, recording failures."""
    path = root / rel
    if not path.is_file():
        errors.append(f"{label}: missing file: {path}")
        return None
    match = _tuple_pattern(var_name).search(path.read_text(encoding="utf-8"))
    if not match:
        errors.append(f"{label}: {var_name} tuple not found in {path}")
        return None
    return set(re.findall(r'"([^"]*)"', match.group(1)))


def _string_pattern(var_name: str) -> re.Pattern[str]:
    """Match a module-level ``VAR[: annotation] = "..."`` string literal.

    Anchored at the line start so a prose mention of the name in a comment
    above the assignment cannot be mistaken for the assignment itself.
    """
    return re.compile(
        rf"^{re.escape(var_name)}\s*(?::[^=]+)?=\s*[\"']([^\"']*)[\"']",
        re.MULTILINE,
    )


def extract_string_literal(
    errors: list[str], root: Path, rel: str, var_name: str, label: str
) -> str | None:
    """Extract one product's string constant, recording failures."""
    path = root / rel
    if not path.is_file():
        errors.append(f"{label}: missing file: {path}")
        return None
    match = _string_pattern(var_name).search(path.read_text(encoding="utf-8"))
    # An empty extraction is treated as absent rather than as a value. The
    # pattern stops at the first quote, so a triple-quoted assignment yields
    # ``''`` — and if both sides were converted that way a later divergence
    # would compare equal and pass vacuously. An empty marker is a bug in its
    # own right (``"" in value`` matches every string, so the ingestion check
    # would reject every document), so failing closed here costs nothing.
    if not match or not match.group(1):
        errors.append(f"{label}: {var_name} literal not found in {path}")
        return None
    return match.group(1)


def _patterns_block_pattern(var_name: str) -> re.Pattern[str]:
    """Match a module-level ``VAR[: annotation] = ( ... )`` tuple of compiled
    patterns, closing at the first ``)`` **at column zero**.

    ``_tuple_pattern`` cannot be reused: it stops at the first ``)``, and these
    bodies are regex source texts full of their own groups. Both copies close
    the tuple with a paren on its own line, which is the only unambiguous
    boundary available without importing the modules (and importing is exactly
    what a cross-product check must not do).
    """
    return re.compile(
        rf"^{re.escape(var_name)}\s*(?::[^=]+)?=\s*\((.*?)^\)",
        re.MULTILINE | re.DOTALL,
    )


def extract_patterns(
    errors: list[str], root: Path, rel: str, var_name: str, label: str
) -> list[str] | None:
    """Extract one product's shape vocabulary as an **ordered** list.

    Ordered, not a set like the substring vocabulary: both copies document the
    order as meaningful ("most specific first" so overlapping shapes are not
    double-counted), so a re-ordering is a divergence worth failing on and a set
    comparison would pass it silently.

    Raw-string literals only, with backslash escapes kept exactly as written —
    ``\\b`` and ``\\s`` are load-bearing characters in a regex source text, and
    comparing post-unescape would equate patterns that differ.
    """
    path = root / rel
    if not path.is_file():
        errors.append(f"{label}: missing file: {path}")
        return None
    match = _patterns_block_pattern(var_name).search(path.read_text(encoding="utf-8"))
    if not match:
        errors.append(f"{label}: {var_name} tuple not found in {path}")
        return None
    literals = re.findall(r'r"((?:[^"\\]|\\.)*)"', match.group(1))
    # An empty extraction is absent rather than empty, for the same reason as in
    # ``extract_string_literal``: two empty lists would compare equal and the
    # coupling would pass vacuously after a refactor changed the quoting style.
    if not literals:
        errors.append(f"{label}: no raw-string patterns in {var_name} at {path}")
        return None
    return literals


def main() -> int:
    root = repo_root()
    errors: list[str] = []

    agent = extract_vocabulary(
        errors, root, AGENT_PLATFORM_REL, AGENT_PLATFORM_VAR, "agent-platform"
    )
    gateway = extract_vocabulary(
        errors, root, TOOL_GATEWAY_REL, TOOL_GATEWAY_VAR, "tool-gateway"
    )
    agent_hole = extract_string_literal(
        errors,
        root,
        AGENT_PLATFORM_REL,
        AGENT_PLATFORM_HOLE_VAR,
        "agent-platform",
    )
    hub_hole = extract_string_literal(
        errors, root, SKILLS_HUB_REL, SKILLS_HUB_VAR, "skills-hub"
    )
    agent_patterns = extract_patterns(
        errors, root, AGENT_DRAFT_REL, AGENT_DRAFT_PATTERNS_VAR, "agent-platform"
    )
    gateway_patterns = extract_patterns(
        errors, root, REDACTION_REL, REDACTION_PATTERNS_VAR, "tool-gateway"
    )

    if agent is not None and gateway is not None and agent != gateway:
        only_agent = sorted(agent - gateway)
        only_gateway = sorted(gateway - agent)
        if only_agent:
            errors.append(
                "agent-platform only: "
                + ", ".join(repr(s) for s in only_agent)
            )
        if only_gateway:
            errors.append(
                "tool-gateway only: "
                + ", ".join(repr(s) for s in only_gateway)
            )

    if (
        agent_hole is not None
        and hub_hole is not None
        and agent_hole != hub_hole
    ):
        errors.append(
            f"credential-hole marker differs: agent-platform "
            f"{AGENT_PLATFORM_HOLE_VAR}={agent_hole!r} vs skills-hub "
            f"{SKILLS_HUB_VAR}={hub_hole!r}"
        )

    if (
        agent_patterns is not None
        and gateway_patterns is not None
        and agent_patterns != gateway_patterns
    ):
        only_agent = [p for p in agent_patterns if p not in gateway_patterns]
        only_gateway = [p for p in gateway_patterns if p not in agent_patterns]
        parts = []
        if only_agent:
            parts.append(
                f"agent-platform only: " + ", ".join(repr(p) for p in only_agent)
            )
        if only_gateway:
            parts.append(
                f"tool-gateway only: " + ", ".join(repr(p) for p in only_gateway)
            )
        if not parts:
            # Same set, different order — still a divergence, because both
            # copies apply them in sequence and document the order as
            # meaningful.
            parts.append("the same patterns in a different order")
        errors.append(
            f"secret-shape vocabulary differs ({AGENT_DRAFT_PATTERNS_VAR} vs "
            f"{REDACTION_PATTERNS_VAR}): " + "; ".join(parts)
        )

    if errors:
        print(
            "FAIL: secret-literal drift across products "
            "(agent-platform / tool-gateway / skills-hub):"
        )
        for e in errors:
            print(f"  - {e}")
        return 1

    count = len(agent) if agent is not None else 0
    print(
        "OK: agent-platform and tool-gateway secret-parameter vocabularies "
        f"agree ({count} substrings)"
    )
    print(
        "OK: agent-platform and skills-hub credential-hole markers agree "
        f"({agent_hole!r})"
    )
    shape_count = len(agent_patterns) if agent_patterns is not None else 0
    print(
        "OK: agent-platform and tool-gateway secret-shape vocabularies agree "
        f"({shape_count} patterns, in order)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
