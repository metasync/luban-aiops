#!/usr/bin/env python3
"""Validate the secret-parameter redaction vocabulary is in lockstep.

SPEC-054 R-3 masks secret-bearing values in the change-request projection
using a name-substring vocabulary carried kernel-side in agent-platform
(``secret_params.SECRET_PARAM_SUBSTRINGS``). That vocabulary is a deliberate
**second copy** of the tool-gateway's evidence-redaction list
(``browser_connector._SECRET_QUERY_PARAMS``, SPEC-049 R-5): the projection is
assembled in the agent-platform kernel, where the gateway's known-secret value
set is unavailable, so it masks by the same names. A copy (rather than a shared
mounted file) is intentional — a vocabulary in a data file would fail *open*
(nothing masked) if the file were missing, whereas a constant has no such
failure mode.

The two copies live in different products, which never import each other, so
this script compares them **textually**: it extracts each tuple literal from
source and diffs the two as sets. It fails the build on any divergence so the
copies cannot drift silently (the ``validate-secret-vocabulary`` leg of
``make verify``).

Usage:
    python validate_secret_vocabulary.py [repo-root]

Defaults to the repository containing this script. Exits 0 when the two
vocabularies agree, 1 on any divergence or extraction failure.
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


def main() -> int:
    root = repo_root()
    errors: list[str] = []

    agent = extract_vocabulary(
        errors, root, AGENT_PLATFORM_REL, AGENT_PLATFORM_VAR, "agent-platform"
    )
    gateway = extract_vocabulary(
        errors, root, TOOL_GATEWAY_REL, TOOL_GATEWAY_VAR, "tool-gateway"
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

    if errors:
        print(
            "FAIL: secret-parameter vocabulary drift between agent-platform "
            "and tool-gateway:"
        )
        for e in errors:
            print(f"  - {e}")
        return 1

    count = len(agent) if agent is not None else 0
    print(
        "OK: agent-platform and tool-gateway secret-parameter vocabularies "
        f"agree ({count} substrings)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
