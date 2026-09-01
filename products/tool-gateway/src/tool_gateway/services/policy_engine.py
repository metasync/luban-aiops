"""Deny-by-default policy evaluation (SPEC-004, SPEC-030).

A small, dependency-free evaluation module implementing the action_authz slice
of the Tier-1 policy specification. The rule/decision contract lives in
shared/shared-contracts; this module is the consumer. When policy-center becomes
a service, evaluate() moves behind a POST /policy/evaluate endpoint returning the
same decision object — callers swap a function call for a network call.

SPEC-030 note: this gateway's invocation path has no pre-approval substrate,
so require_approval rules are skipped at bundle load (logged, never silently
enforced as allow) and never participate in evaluation — admission stays the
SPEC-021 allow/deny gate, and tiered approval enforcement lives exclusively
on the platform-gateway confirm path.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import yaml

from tool_gateway.core.config import GatewaySettings

LOGGER = logging.getLogger(__name__)

DEFAULT_BUNDLE_RESOURCE = "policy-default.yaml"

# Action vocabulary for the tool API surface (SPEC-010). Health and metrics
# routes are platform plumbing and are deliberately exempt from policy
# enforcement; portal-facing actions (chat, session:*) live in platform-gateway.
ACTION_TOOLS_LIST = "tools:list"
ACTION_TOOLS_INVOKE = "tools:invoke"
# Mutating tool execution (SPEC-021 R-1): write/admin risk tools additionally
# require this action; deny-by-default like every other platform action.
ACTION_TOOLS_MUTATE = "tools:mutate"
PROTECTED_ACTIONS = frozenset(
    {ACTION_TOOLS_LIST, ACTION_TOOLS_INVOKE, ACTION_TOOLS_MUTATE}
)

# Approval semantics (SPEC-030 R-2): this gateway bridges no approval
# enforcement path, so the bridged action set is empty and every
# require_approval rule is skipped at load (see module docstring).
APPROVAL_TIERS = frozenset({"tier_1", "tier_2"})
APPROVAL_BRIDGED_ACTIONS: frozenset[str] = frozenset()
OUTCOME_ALLOW = "allow"
OUTCOME_DENY = "deny"
OUTCOME_REQUIRE_APPROVAL = "require_approval"
VALID_OUTCOMES = frozenset({OUTCOME_ALLOW, OUTCOME_DENY, OUTCOME_REQUIRE_APPROVAL})

# Module-level bundle singleton, keyed on the configured path.
_bundle: list[PolicyRule] | None = None
_configured_path: str | None = None
# SPEC-048 R-1: content fingerprint of the exact loaded bundle text,
# computed at load time — never authored in the bundle.
_bundle_hash: str = ""


class PolicyLoadError(Exception):
    """Raised when a policy bundle cannot be loaded or is invalid."""


@dataclass(frozen=True)
class ApprovalSpec:
    """Approval requirement carried by a require_approval rule (SPEC-030 R-1).

    ``allow_self_approval=None`` means the tier default applies: tier_1
    allows the session operator to confirm their own parked call,
    tier_2 forbids it.
    """

    tier: str
    decided_by_roles: tuple[str, ...]
    allow_self_approval: bool | None = None

    def effective_self_approval(self) -> bool:
        if self.allow_self_approval is not None:
            return self.allow_self_approval
        return self.tier == "tier_1"

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "tier": self.tier,
            "decided_by_roles": list(self.decided_by_roles),
        }
        if self.allow_self_approval is not None:
            payload["allow_self_approval"] = self.allow_self_approval
        return payload


@dataclass(frozen=True)
class PolicyRule:
    id: str
    priority: int
    enabled: bool
    roles_any: tuple[str, ...]
    actions_any: tuple[str, ...]
    outcome: str
    approval: ApprovalSpec | None = None


@dataclass(frozen=True)
class PolicyDecision:
    decision: str
    matched_rule_ids: list[str] = field(default_factory=list)
    reason: str = ""
    action: str | None = None
    subject: str | None = None
    # SPEC-030 R-1: set when decision is require_approval.
    approval: ApprovalSpec | None = None

    @property
    def approval_tier(self) -> str | None:
        return self.approval.tier if self.approval is not None else None

    def to_dict(self) -> dict[str, object]:
        """Serialize to the policy-decision.schema.json shape."""
        payload: dict[str, object] = {
            "decision": self.decision,
            "matched_rule_ids": list(self.matched_rule_ids),
            "reason": self.reason,
        }
        if self.action is not None:
            payload["action"] = self.action
        if self.subject is not None:
            payload["subject"] = self.subject
        if self.approval is not None:
            payload["approval_tier"] = self.approval.tier
            payload["approval"] = self.approval.to_dict()
        return payload


def reset_policy_state() -> None:
    """Reset module state (for tests)."""
    global _bundle, _configured_path, _bundle_hash
    _bundle = None
    _configured_path = None
    _bundle_hash = ""


def _packaged_bundle_text() -> str:
    return (
        resources.files("tool_gateway.policies")
        .joinpath(DEFAULT_BUNDLE_RESOURCE)
        .read_text(encoding="utf-8")
    )


def _parse_approval(raw_decision: dict, rule_id: str, source: str) -> ApprovalSpec:
    """Validate and build the approval block of a require_approval rule."""
    approval = raw_decision.get("approval")
    if not isinstance(approval, dict):
        raise PolicyLoadError(
            f"rule {rule_id!r} in '{source}': require_approval requires an approval block"
        )
    tier = approval.get("tier")
    if tier not in APPROVAL_TIERS:
        raise PolicyLoadError(
            f"rule {rule_id!r} in '{source}': approval.tier must be one of "
            f"{sorted(APPROVAL_TIERS)}, got {tier!r}"
        )
    deciders = approval.get("decided_by_roles")
    if (
        not isinstance(deciders, list)
        or not deciders
        or not all(isinstance(role, str) and role for role in deciders)
    ):
        raise PolicyLoadError(
            f"rule {rule_id!r} in '{source}': approval.decided_by_roles must be a "
            "non-empty list of role names"
        )
    allow_self = approval.get("allow_self_approval")
    if allow_self is not None and not isinstance(allow_self, bool):
        raise PolicyLoadError(
            f"rule {rule_id!r} in '{source}': approval.allow_self_approval must be a boolean"
        )
    if tier == "tier_2" and allow_self is True:
        raise PolicyLoadError(
            f"rule {rule_id!r} in '{source}': tier_2 approval cannot allow self-approval "
            "(self-approval is reserved for tier_1)"
        )
    return ApprovalSpec(
        tier=str(tier),
        decided_by_roles=tuple(deciders),
        allow_self_approval=allow_self,
    )


def _parse_rules(text: str, source: str) -> list[PolicyRule]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PolicyLoadError(f"invalid YAML in policy bundle '{source}': {exc}") from exc

    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        raise PolicyLoadError(
            f"policy bundle '{source}' must be a mapping with a 'rules' list"
        )

    rules: list[PolicyRule] = []
    for index, raw in enumerate(data["rules"]):
        if not isinstance(raw, dict):
            raise PolicyLoadError(f"rule #{index} in '{source}' is not a mapping")
        try:
            match = raw["match"]
            decision = raw["decision"]
            rule_id = str(raw["id"])
            outcome = str(decision["outcome"])
            if outcome not in VALID_OUTCOMES:
                raise PolicyLoadError(
                    f"rule {rule_id!r} in '{source}': unknown outcome {outcome!r}"
                )
            approval: ApprovalSpec | None = None
            if outcome == OUTCOME_REQUIRE_APPROVAL:
                # Validate the block loudly so a malformed synced bundle
                # never loads, then skip the rule: this gateway has no
                # approval enforcement substrate (SPEC-030 R-2).
                _parse_approval(decision, rule_id, source)
                unbridged = set(match["actions_any"]) - APPROVAL_BRIDGED_ACTIONS
                if unbridged:
                    LOGGER.warning(
                        "skipping require_approval rule %s: unenforceable actions %s "
                        "on the tool-gateway invocation path (SPEC-030 R-2)",
                        rule_id,
                        sorted(unbridged),
                    )
                continue
            elif "approval" in decision:
                raise PolicyLoadError(
                    f"rule {rule_id!r} in '{source}': approval block is only valid on "
                    "require_approval outcomes"
                )
            rules.append(
                PolicyRule(
                    id=rule_id,
                    priority=int(raw["priority"]),
                    enabled=bool(raw["enabled"]),
                    roles_any=tuple(match["roles_any"]),
                    actions_any=tuple(match["actions_any"]),
                    outcome=outcome,
                    approval=approval,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PolicyLoadError(
                f"rule #{index} in '{source}' is malformed: {exc}"
            ) from exc
    return rules


def load_bundle(settings: GatewaySettings) -> list[PolicyRule]:
    """Load and cache the policy bundle.

    - GATEWAY_POLICY_PATH set + valid -> load it
    - path set + missing/invalid -> raise PolicyLoadError (no silent fallback)
    - path unset -> load the packaged default bundle
    """
    global _bundle, _configured_path, _bundle_hash

    path = settings.policy_path
    if _bundle is not None and _configured_path == path:
        return _bundle

    if path:
        bundle_path = Path(path)
        if not bundle_path.is_file():
            raise PolicyLoadError(f"policy bundle not found at '{path}'")
        text = bundle_path.read_text(encoding="utf-8")
    else:
        text = _packaged_bundle_text()
    rules = _parse_rules(text, path or "<packaged default>")

    _bundle = rules
    _configured_path = path
    _bundle_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    LOGGER.info(
        "policy bundle loaded",
        extra={
            "policy_path": path or "<packaged default>",
            "rule_count": len(rules),
            "bundle_sha256": _bundle_hash,
        },
    )
    return rules


def bundle_sha256() -> str:
    """Content fingerprint of the loaded bundle (SPEC-048 R-1).

    Valid after ``load_bundle``; empty before. Lets the readiness surface
    confirm the enforced bundle matches the intended commit.
    """
    return _bundle_hash


def evaluate(settings: GatewaySettings, roles: list[str], action: str) -> PolicyDecision:
    """Evaluate an action against the loaded bundle.

    Semantics: deny by default; explicit deny overrides require_approval and
    allow; require_approval overrides allow (safe default); higher priority
    wins within an outcome class; disabled rules are ignored (SPEC-030 R-2).
    require_approval rules never load on this gateway, so admission stays the
    SPEC-021 allow/deny gate.
    """
    rules = load_bundle(settings)
    role_set = set(roles)

    matched = [
        rule
        for rule in rules
        if rule.enabled
        and action in rule.actions_any
        and (role_set & set(rule.roles_any))
    ]

    if any(rule.outcome == OUTCOME_DENY for rule in matched):
        deny_ids = [rule.id for rule in matched if rule.outcome == OUTCOME_DENY]
        return PolicyDecision(
            decision="deny",
            matched_rule_ids=deny_ids,
            reason="explicit deny rule matched",
            action=action,
        )

    approvals = [rule for rule in matched if rule.outcome == OUTCOME_REQUIRE_APPROVAL]
    if approvals:
        best = max(approvals, key=lambda rule: rule.priority)
        return PolicyDecision(
            decision="require_approval",
            matched_rule_ids=[best.id],
            reason="approval required by policy rule",
            action=action,
            approval=best.approval,
        )

    allows = [rule for rule in matched if rule.outcome == OUTCOME_ALLOW]
    if allows:
        best = max(allows, key=lambda rule: rule.priority)
        return PolicyDecision(
            decision="allow",
            matched_rule_ids=[best.id],
            reason="allowed by policy rule",
            action=action,
        )

    return PolicyDecision(
        decision="deny",
        matched_rule_ids=[],
        reason="no matching policy rule",
        action=action,
    )
