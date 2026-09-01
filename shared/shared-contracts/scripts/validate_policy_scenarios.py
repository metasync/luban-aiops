#!/usr/bin/env python3
"""Scenario-expectation guard for the canonical policy bundle (SPEC-048 R-2).

Evaluates `policy-scenarios.yaml` against a bundle with the exact engine
semantics — the engines are the contract, so this script imports them rather
than re-implementing evaluation — and fails on any mismatch. It also
mechanically enforces the table's completeness invariant: every granted
(role, action) pair of the bundle must be covered by at least one scenario,
so a new grant with no recorded expectation fails the gate.

Usage:
    python validate_policy_scenarios.py --engine api [--bundle PATH] [--scenarios PATH]
    python validate_policy_scenarios.py --engine tools [--bundle PATH] [--scenarios PATH]

Run inside the owning product's uv env (the root Makefile does this):
`--engine api` under products/platform-gateway, `--engine tools` under
products/tool-gateway. Exits 0 on success, 1 on any mismatch or coverage gap.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

CONTRACTS_DIR = Path(__file__).resolve().parent.parent
DEFAULT_BUNDLE = CONTRACTS_DIR / "policies" / "policy-default.yaml"
DEFAULT_SCENARIOS = CONTRACTS_DIR / "policies" / "policy-scenarios.yaml"
VALID_EXPECTATIONS = frozenset({"allow", "deny", "require_approval"})


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


def _expand_entries(section: list[dict]) -> dict[tuple[str, str], tuple[str, str | None]]:
    """Expand role/roles x action/actions entries into per-pair expectations."""
    expectations: dict[tuple[str, str], tuple[str, str | None]] = {}
    for index, entry in enumerate(section):
        if not isinstance(entry, dict):
            sys.exit(f"error: scenario #{index} is not a mapping")
        expect = entry.get("expect")
        if expect not in VALID_EXPECTATIONS:
            sys.exit(f"error: scenario #{index}: expect must be one of "
                     f"{sorted(VALID_EXPECTATIONS)}, got {expect!r}")
        tier = entry.get("approval_tier")
        if tier is not None and expect != "require_approval":
            sys.exit(f"error: scenario #{index}: approval_tier is only valid on "
                     f"require_approval expectations")
        roles = entry.get("roles") or ([entry["role"]] if entry.get("role") else [])
        actions = entry.get("actions") or ([entry["action"]] if entry.get("action") else [])
        if not roles or not actions:
            sys.exit(f"error: scenario #{index}: needs role/roles and action/actions")
        for role in roles:
            for action in actions:
                pair = (str(role), str(action))
                if pair in expectations and expectations[pair] != (expect, tier):
                    sys.exit(f"error: conflicting expectations for {pair}: "
                             f"{expectations[pair]} vs {(expect, tier)}")
                expectations[pair] = (expect, tier)
    return expectations


def _granted_pairs(policy_engine) -> set[tuple[str, str]]:
    """Every (role, action) pair the engine actually enforces.

    Disabled rules are excluded (they grant nothing), and pairs are
    restricted to the engine's PROTECTED_ACTIONS vocabulary — the shared
    bundle carries both vocabularies, but each engine only enforces its
    own (the tools engine loads API-vocabulary allow rules it never
    evaluates). Engines that skip rule classes at load (tool-gateway
    skips require_approval, SPEC-030 R-2) exclude them automatically
    because they never load.
    """
    pairs: set[tuple[str, str]] = set()
    for rule in policy_engine._bundle or []:
        if not rule.enabled:
            continue
        for role in rule.roles_any:
            for action in rule.actions_any:
                if action in policy_engine.PROTECTED_ACTIONS:
                    pairs.add((role, action))
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, choices=["api", "tools"])
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    args = parser.parse_args()

    if not args.bundle.is_file():
        print(f"error: bundle not found: {args.bundle}", file=sys.stderr)
        return 1
    if not args.scenarios.is_file():
        print(f"error: scenarios not found: {args.scenarios}", file=sys.stderr)
        return 1

    with open(args.scenarios) as f:
        table = yaml.safe_load(f)
    if not isinstance(table, dict) or not isinstance(table.get(args.engine), list):
        print(f"error: scenarios table has no {args.engine!r} section", file=sys.stderr)
        return 1
    expectations = _expand_entries(table[args.engine])

    settings_cls, policy_engine = _load_engine(args.engine)
    settings = settings_cls(policy_path=str(args.bundle))
    try:
        policy_engine.load_bundle(settings)
    except policy_engine.PolicyLoadError as exc:
        print(f"error: bundle failed to load: {exc}", file=sys.stderr)
        return 1

    failures: list[str] = []

    # Expectation evaluation — the exact enforce_policy path.
    for (role, action), (expect, tier) in sorted(expectations.items()):
        decision = policy_engine.evaluate(settings, [role], action)
        if decision.decision != expect:
            failures.append(
                f"{role} x {action}: expected {expect}, got {decision.decision} "
                f"(rules: {decision.matched_rule_ids or 'none'})"
            )
        elif expect == "require_approval" and tier is not None:
            got_tier = decision.approval_tier
            if got_tier != tier:
                failures.append(
                    f"{role} x {action}: expected approval_tier {tier}, got {got_tier}"
                )

    # Coverage invariant — no grant may escape the table.
    uncovered = sorted(_granted_pairs(policy_engine) - set(expectations))
    for role, action in uncovered:
        failures.append(f"{role} x {action}: granted by the bundle but has no scenario")

    if failures:
        print(f"FAIL: {len(failures)} scenario failure(s) for engine {args.engine} "
              f"against {args.bundle}:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(f"OK: {len(expectations)} scenario(s) passed for engine {args.engine}; "
          f"all granted pairs covered ({len(_granted_pairs(policy_engine))})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
