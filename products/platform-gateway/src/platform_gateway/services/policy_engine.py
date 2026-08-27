"""Deny-by-default policy evaluation (SPEC-004, SPEC-030).

A small, dependency-free evaluation module implementing the action_authz slice
of the Tier-1 policy specification. The rule/decision contract lives in
shared/shared-contracts; this module is the consumer. When policy-center becomes
a service, evaluate() moves behind a POST /policy/evaluate endpoint returning the
same decision object — callers swap a function call for a network call.

SPEC-030 adds the third outcome: require_approval with explicit tiers.
Precedence is deny > require_approval > allow; between require_approval
matches the highest priority wins and its approval block rides the decision.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import yaml

from platform_gateway.core.config import PlatformGatewaySettings

LOGGER = logging.getLogger(__name__)

DEFAULT_BUNDLE_RESOURCE = "policy-default.yaml"

# Action vocabulary for the current gateway surface (R-3). Routes not listed
# here (health, runtime metadata, auth, identity normalize) are platform
# plumbing and are deliberately exempt from policy enforcement.
ACTION_CHAT = "chat"
ACTION_SESSION_CREATE = "session:create"
ACTION_SESSION_READ = "session:read"
# Session workspace lifecycle (SPEC-022 R-1): list and delete are scoped
# server-side to the caller's own sessions, mirroring session:create grants.
ACTION_SESSION_LIST = "session:list"
ACTION_SESSION_DELETE = "session:delete"
ACTION_AUDIT_READ = "audit:read"
ACTION_INCIDENT_READ = "incident:read"
ACTION_INCIDENT_CREATE = "incident:create"
ACTION_INCIDENT_TRIAGE = "incident:triage"
# Transparency and workspace inventory actions (SPEC-019).
ACTION_POLICY_READ = "policy:read"
ACTION_TOOLS_LIST = "tools:list"
ACTION_SKILLS_READ = "skills:read"
# HITL confirmation bridging (SPEC-020): mutating chat capability with its
# own action name; observer is denied by default per the bundle convention.
ACTION_CHAT_CONFIRM = "chat:confirm"
# Mutating tool execution (SPEC-021): enforced by the tool-gateway, listed
# here so the live permission matrix always carries the action even if the
# deployed bundle predates the grant.
ACTION_TOOLS_MUTATE = "tools:mutate"
# Model catalog discovery (SPEC-024 R-2): read-only pass-through behind its
# own action; grants mirror the chat scope (operators + observers).
ACTION_MODELS_LIST = "models:list"
# Approvals inbox (SPEC-031 R-3): cross-session confirmation discovery for
# designated approvers; the bundle grants it to the tier_2 decider roles
# only, mirroring decided_by_roles by authoring.
ACTION_APPROVALS_LIST = "approvals:list"
# Operations document repository (SPEC-039 R-2): documents:create gates
# create/publish/delete of one's own documents; documents:read gates
# list/get. The agent layer enforces the visibility matrix server-side.
ACTION_DOCUMENTS_CREATE = "documents:create"
ACTION_DOCUMENTS_READ = "documents:read"
# Owner session rename (SPEC-039 R-7): scoped server-side to the caller's
# own sessions, mirroring session:list/session:delete grants.
ACTION_SESSION_UPDATE = "session:update"
PROTECTED_ACTIONS = frozenset(
    {
        ACTION_CHAT,
        ACTION_CHAT_CONFIRM,
        ACTION_SESSION_CREATE,
        ACTION_SESSION_READ,
        ACTION_SESSION_LIST,
        ACTION_SESSION_DELETE,
        ACTION_AUDIT_READ,
        ACTION_INCIDENT_READ,
        ACTION_INCIDENT_CREATE,
        ACTION_INCIDENT_TRIAGE,
        ACTION_POLICY_READ,
        ACTION_TOOLS_LIST,
        ACTION_SKILLS_READ,
        ACTION_TOOLS_MUTATE,
        ACTION_MODELS_LIST,
        ACTION_APPROVALS_LIST,
        ACTION_DOCUMENTS_CREATE,
        ACTION_DOCUMENTS_READ,
        ACTION_SESSION_UPDATE,
    }
)

# Approval semantics (SPEC-030 R-2): require_approval rules are only valid
# on actions with a bridged enforcement path. This gateway bridges the
# SPEC-020 confirm flow, so tools:mutate is the bridged set for this slice.
APPROVAL_TIERS = frozenset({"tier_1", "tier_2"})
APPROVAL_BRIDGED_ACTIONS = frozenset({ACTION_TOOLS_MUTATE})
OUTCOME_ALLOW = "allow"
OUTCOME_DENY = "deny"
OUTCOME_REQUIRE_APPROVAL = "require_approval"
VALID_OUTCOMES = frozenset({OUTCOME_ALLOW, OUTCOME_DENY, OUTCOME_REQUIRE_APPROVAL})

# Module-level bundle singleton, keyed on the configured path.
_bundle: list[PolicyRule] | None = None
_bundle_version: int = 0
_configured_path: str | None = None


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
    global _bundle, _bundle_version, _configured_path
    _bundle = None
    _bundle_version = 0
    _configured_path = None


def _packaged_bundle_text() -> str:
    return (
        resources.files("platform_gateway.policies")
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


def _parse_rules(text: str, source: str) -> tuple[int, list[PolicyRule]]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PolicyLoadError(f"invalid YAML in policy bundle '{source}': {exc}") from exc

    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        raise PolicyLoadError(
            f"policy bundle '{source}' must be a mapping with a 'rules' list"
        )

    try:
        version = int(data.get("version", 0))
    except (TypeError, ValueError) as exc:
        raise PolicyLoadError(
            f"policy bundle '{source}' version must be an integer"
        ) from exc

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
                approval = _parse_approval(decision, rule_id, source)
                actions_any = tuple(match["actions_any"])
                unbridged = set(actions_any) - APPROVAL_BRIDGED_ACTIONS
                if unbridged:
                    raise PolicyLoadError(
                        f"rule {rule_id!r} in '{source}': require_approval is only valid "
                        f"on bridged actions {sorted(APPROVAL_BRIDGED_ACTIONS)}; "
                        f"unbridged: {sorted(unbridged)}"
                    )
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
    return version, rules


def load_bundle(settings: PlatformGatewaySettings) -> list[PolicyRule]:
    """Load and cache the policy bundle.

    - PLATFORM_GATEWAY_POLICY_PATH set + valid -> load it
    - path set + missing/invalid -> raise PolicyLoadError (no silent fallback)
    - path unset -> load the packaged default bundle

    Note: tool-gateway uses GATEWAY_POLICY_PATH for its own bundle; the
    PLATFORM_GATEWAY_* knobs apply to this edge service only.
    """
    global _bundle, _bundle_version, _configured_path

    path = settings.policy_path
    if _bundle is not None and _configured_path == path:
        return _bundle

    if path:
        bundle_path = Path(path)
        if not bundle_path.is_file():
            raise PolicyLoadError(f"policy bundle not found at '{path}'")
        version, rules = _parse_rules(bundle_path.read_text(encoding="utf-8"), path)
    else:
        version, rules = _parse_rules(_packaged_bundle_text(), "<packaged default>")

    _bundle = rules
    _bundle_version = version
    _configured_path = path
    LOGGER.info(
        "policy bundle loaded",
        extra={"policy_path": path or "<packaged default>", "rule_count": len(rules)},
    )
    return rules


def bundle_metadata(settings: PlatformGatewaySettings) -> dict[str, object]:
    """Version and provenance of the loaded bundle (SPEC-019 R-2).

    Lets transparency surfaces tell a configured bundle from the packaged
    default, so policy drift and degraded loads are visible instead of silent.
    """
    load_bundle(settings)
    return {
        "version": _bundle_version,
        "source": "configured" if settings.policy_path else "packaged-default",
    }


def evaluate(settings: PlatformGatewaySettings, roles: list[str], action: str) -> PolicyDecision:
    """Evaluate an action against the loaded bundle.

    Semantics: deny by default; explicit deny overrides require_approval and
    allow; require_approval overrides allow (safe default); higher priority
    wins within an outcome class; disabled rules are ignored (SPEC-030 R-2).
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
