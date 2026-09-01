#!/usr/bin/env python3
"""Review-time policy impact report (SPEC-048 R-3).

Compares the canonical policy bundle against a candidate bundle and
enumerates every per-(role, action) outcome transition — allow→deny,
allow→require_approval, approval-tier changes, new grants, removed
grants — with unchanged pairs summarized by count. Reviewers read the
report; nothing is mutated and the canonical bundle is never touched.

Evaluation shares the exact engine path of the scenario harness
(validate_policy_scenarios.py): the engines are the contract (Q-2), so
this script imports them rather than re-implementing semantics. That
also means engine non-parity shows up honestly — the tools engine skips
require_approval rules at load (SPEC-030 R-2), so the same candidate
can report different transitions per engine.

Pair space: roles are the union of every role declared by either
bundle; actions are the union of declared actions plus the engine's
PROTECTED_ACTIONS, so a removed grant surfaces as allow→deny rather
than disappearing from the report.

Usage:
    python policy_diff.py --engine api --candidate PATH [--canonical PATH]
    python policy_diff.py --engine tools --candidate PATH [--canonical PATH]

Run inside the owning product's uv env (the root Makefile's
`policy-diff` target does this). Exits 0 with the report (including the
no-transitions case), 1 on a missing/unparseable candidate — the same
PolicyLoadError posture the gateways apply at startup.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

CONTRACTS_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CANONICAL = CONTRACTS_DIR / "policies" / "policy-default.yaml"


def _load_engine(engine: str):
    """Import the owning engine — one evaluator, never a re-implementation."""
    if engine == "api":
        from platform_gateway.core.config import PlatformGatewaySettings
        from platform_gateway.services import policy_engine
    elif engine == "tools":
        from tool_gateway.core.config import GatewaySettings as PlatformGatewaySettings
        from tool_gateway.services import policy_engine
    else:  # pragma: no cover — argparse restricts the choice
        raise ValueError(f"unknown engine {engine!r}")
    return PlatformGatewaySettings, policy_engine


def _bundle_sha256(policy_engine, settings) -> str:
    """Provenance hash of the currently loaded bundle (SPEC-048 R-1)."""
    if hasattr(policy_engine, "bundle_metadata"):
        return str(policy_engine.bundle_metadata(settings)["sha256"])
    return policy_engine.bundle_sha256()


def _outcome_map(settings_cls, policy_engine, bundle_path: Path,
                 roles: set[str], actions: set[str]) -> tuple[dict[tuple[str, str], tuple[str, str | None]], str]:
    """Evaluate every (role, action) pair with the engine's exact path."""
    policy_engine.reset_policy_state()
    settings = settings_cls(policy_path=str(bundle_path))
    try:
        policy_engine.load_bundle(settings)
    except policy_engine.PolicyLoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    sha256 = _bundle_sha256(policy_engine, settings)
    outcomes: dict[tuple[str, str], tuple[str, str | None]] = {}
    for role in roles:
        for action in actions:
            decision = policy_engine.evaluate(settings, [role], action)
            outcomes[(role, action)] = (decision.decision, decision.approval_tier)
    return outcomes, sha256


def _declared_surface(policy_engine, bundle_path: Path) -> tuple[set[str], set[str]]:
    """Roles and actions declared by a bundle's enabled rules."""
    try:
        data = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        print(f"error: cannot read candidate bundle '{bundle_path}': {exc}",
              file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, dict):
        print(f"error: bundle '{bundle_path}' is not a mapping with a 'rules' list",
              file=sys.stderr)
        sys.exit(1)
    roles: set[str] = set()
    actions: set[str] = set()
    for rule in (data or {}).get("rules") or []:
        if not isinstance(rule, dict) or not rule.get("enabled", False):
            continue
        match = rule.get("match") or {}
        roles.update(str(r) for r in match.get("roles_any") or [])
        actions.update(str(a) for a in match.get("actions_any") or [])
    return roles, actions


def _format_outcome(outcome: tuple[str, str | None]) -> str:
    decision, tier = outcome
    if decision == "require_approval" and tier:
        return f"require_approval ({tier})"
    return decision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, choices=["api", "tools"])
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    args = parser.parse_args()

    # Review-time tooling: the engines log load banners at INFO; the
    # report is the only output that matters here.
    logging.disable(logging.INFO)

    if not args.canonical.is_file():
        print(f"error: canonical bundle not found: {args.canonical}", file=sys.stderr)
        return 1
    if not args.candidate.is_file():
        print(f"error: candidate bundle not found: {args.candidate}", file=sys.stderr)
        return 1

    settings_cls, policy_engine = _load_engine(args.engine)

    # Pair space spans both bundles' declared surface (enabled rules
    # only) plus the engine's enforced vocabulary, so removed grants and
    # deny-by-default posture changes stay visible in the report.
    canon_roles, canon_actions = _declared_surface(policy_engine, args.canonical)
    cand_roles, cand_actions = _declared_surface(policy_engine, args.candidate)
    roles = canon_roles | cand_roles
    actions = canon_actions | cand_actions | set(policy_engine.PROTECTED_ACTIONS)
    if not roles or not actions:
        print("error: no roles/actions to evaluate — both bundles declare no rules",
              file=sys.stderr)
        return 1

    canonical_outcomes, canonical_sha = _outcome_map(
        settings_cls, policy_engine, args.canonical, roles, actions
    )
    candidate_outcomes, candidate_sha = _outcome_map(
        settings_cls, policy_engine, args.candidate, roles, actions
    )

    transitions: list[str] = []
    unchanged = 0
    for pair in sorted(canonical_outcomes):
        canon = canonical_outcomes[pair]
        cand = candidate_outcomes[pair]
        if canon == cand:
            unchanged += 1
        else:
            role, action = pair
            transitions.append(
                f"  {role} x {action}: {_format_outcome(canon)} -> {_format_outcome(cand)}"
            )

    print(f"policy-diff: engine {args.engine}")
    print(f"canonical: {args.canonical}")
    print(f"           sha256 {canonical_sha}")
    print(f"candidate: {args.candidate}")
    print(f"           sha256 {candidate_sha}")
    print(f"pairs evaluated: {len(canonical_outcomes)} "
          f"({len(roles)} roles x {len(actions)} actions)")
    if not transitions:
        print("no outcome transitions")
    else:
        print(f"transitions: {len(transitions)}")
        for line in transitions:
            print(line)
    print(f"unchanged pairs: {unchanged}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
