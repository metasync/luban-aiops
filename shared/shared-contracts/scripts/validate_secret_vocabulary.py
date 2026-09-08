#!/usr/bin/env python3
"""Validate the cross-product secret literals are in lockstep.

Two couplings are pinned here, both of them a deliberate **second copy** of a
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

Both pairs live in different products, so this script compares them
**textually**: it extracts each literal from source and diffs them (the tuple
pair as sets, the marker by equality). It fails the build on any divergence so
the copies cannot drift silently (the ``validate-secret-vocabulary`` leg of
``make verify``).

Usage:
    python validate_secret_vocabulary.py [repo-root]

Defaults to the repository containing this script. Exits 0 when both couplings
agree, 1 on any divergence or extraction failure.
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
