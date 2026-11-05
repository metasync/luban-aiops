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


def _expand_entries(
    section: list[dict],
) -> dict[tuple[str, str, str | None], tuple[str, str | None]]:
    """Expand role/roles x action/actions entries into per-tuple expectations.

    Each expectation is keyed on ``(role, action, agent_role)``. ``agent_role``
    is ``None`` unless the entry names one — SPEC-074's optional agent-role
    axis. Canonical entries omit it, so the human-axis coverage invariant is
    computed over the ``agent_role is None`` slice exactly as before.
    """
    expectations: dict[tuple[str, str, str | None], tuple[str, str | None]] = {}
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
        agent_role = entry.get("agent_role")
        if agent_role is not None and not isinstance(agent_role, str):
            sys.exit(f"error: scenario #{index}: agent_role must be a string when present")
        roles = entry.get("roles") or ([entry["role"]] if entry.get("role") else [])
        actions = entry.get("actions") or ([entry["action"]] if entry.get("action") else [])
        if not roles or not actions:
            sys.exit(f"error: scenario #{index}: needs role/roles and action/actions")
        for role in roles:
            for action in actions:
                key = (str(role), str(action), agent_role)
                if key in expectations and expectations[key] != (expect, tier):
                    sys.exit(f"error: conflicting expectations for {key}: "
                             f"{expectations[key]} vs {(expect, tier)}")
                expectations[key] = (expect, tier)
    return expectations


def _sorted_keys(expectations: dict) -> list:
    """Deterministic order over ``(role, action, agent_role)`` keys.

    ``agent_role`` may be ``None``; comparing ``None`` against a string raises
    ``TypeError``, so the sort key coerces it to ``""`` (the axis is optional).
    """
    return sorted(
        expectations.items(),
        key=lambda item: (item[0][0], item[0][1], item[0][2] or ""),
    )


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

    # Expectation evaluation — the exact enforce_policy path. The agent_role
    # axis (SPEC-074) is None for every canonical entry, so this is byte-
    # identical to the pre-v3 evaluation.
    for (role, action, agent_role), (expect, tier) in _sorted_keys(expectations):
        decision = policy_engine.evaluate(settings, [role], action, agent_role)
        label = f"{role} x {action}" + (f" (agent_role={agent_role})" if agent_role else "")
        if decision.decision != expect:
            failures.append(
                f"{label}: expected {expect}, got {decision.decision} "
                f"(rules: {decision.matched_rule_ids or 'none'})"
            )
        elif expect == "require_approval" and tier is not None:
            got_tier = decision.approval_tier
            if got_tier != tier:
                failures.append(f"{label}: expected approval_tier {tier}, got {got_tier}")

    # Coverage invariant — no human-axis grant may escape the table. Scoped
    # (agent_role) entries are excluded: the canonical bundle carries no
    # agent_roles_any rule (SPEC-074 OQ-4), so its granted (role, action) pairs
    # are covered entirely by the agent_role-is-None slice.
    canonical_expected = {(role, action) for (role, action, ar) in expectations if ar is None}
    canonical_granted = _granted_pairs(policy_engine)
    uncovered = sorted(canonical_granted - canonical_expected)
    for role, action in uncovered:
        failures.append(f"{role} x {action}: granted by the bundle but has no scenario")

    # SPEC-074 agent-role demonstration — an optional section validated against
    # a synthetic bundle (the canonical bundle is byte-unchanged, OQ-4), so it
    # pins the axis's matching semantics without touching any deployed grant.
    # No coverage invariant here: the demo is a targeted pin, not a complete
    # grant surface.
    demo_count = 0
    demo = table.get("agent_role")
    if isinstance(demo, dict) and isinstance(demo.get(args.engine), list):
        demo_rel = demo.get("bundle")
        demo_bundle = (CONTRACTS_DIR / "policies" / demo_rel) if demo_rel else None
        if demo_bundle is None or not demo_bundle.is_file():
            failures.append(f"agent_role demo bundle not found: {demo_bundle}")
        else:
            demo_expectations = _expand_entries(demo[args.engine])
            policy_engine.reset_policy_state()
            demo_settings = settings_cls(policy_path=str(demo_bundle))
            try:
                policy_engine.load_bundle(demo_settings)
            except policy_engine.PolicyLoadError as exc:
                failures.append(f"agent_role demo bundle failed to load: {exc}")
            else:
                for (role, action, agent_role), (expect, tier) in _sorted_keys(demo_expectations):
                    demo_count += 1
                    decision = policy_engine.evaluate(demo_settings, [role], action, agent_role)
                    label = f"[agent-role demo] {role} x {action} (agent_role={agent_role})"
                    if decision.decision != expect:
                        failures.append(
                            f"{label}: expected {expect}, got {decision.decision} "
                            f"(rules: {decision.matched_rule_ids or 'none'})"
                        )
                    elif expect == "require_approval" and tier is not None:
                        got_tier = decision.approval_tier
                        if got_tier != tier:
                            failures.append(
                                f"{label}: expected approval_tier {tier}, got {got_tier}"
                            )

    if failures:
        print(f"FAIL: {len(failures)} scenario failure(s) for engine {args.engine} "
              f"against {args.bundle}:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    demo_note = f"; {demo_count} agent-role demo scenario(s) passed" if demo_count else ""
    print(f"OK: {len(expectations)} scenario(s) passed for engine {args.engine}; "
          f"all granted pairs covered ({len(canonical_granted)}){demo_note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
