"""Deny-by-default policy evaluation (SPEC-004).

A small, dependency-free evaluation module implementing the action_authz slice
of the Tier-1 policy specification. The rule/decision contract lives in
shared/shared-contracts; this module is the consumer. When policy-center becomes
a service, evaluate() moves behind a POST /policy/evaluate endpoint returning the
same decision object — callers swap a function call for a network call.
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
PROTECTED_ACTIONS = frozenset(
    {
        ACTION_CHAT,
        ACTION_CHAT_CONFIRM,
        ACTION_SESSION_CREATE,
        ACTION_SESSION_READ,
        ACTION_AUDIT_READ,
        ACTION_INCIDENT_READ,
        ACTION_INCIDENT_CREATE,
        ACTION_INCIDENT_TRIAGE,
        ACTION_POLICY_READ,
        ACTION_TOOLS_LIST,
        ACTION_SKILLS_READ,
        ACTION_TOOLS_MUTATE,
    }
)

# Module-level bundle singleton, keyed on the configured path.
_bundle: list[PolicyRule] | None = None
_bundle_version: int = 0
_configured_path: str | None = None


class PolicyLoadError(Exception):
    """Raised when a policy bundle cannot be loaded or is invalid."""


@dataclass(frozen=True)
class PolicyRule:
    id: str
    priority: int
    enabled: bool
    roles_any: tuple[str, ...]
    actions_any: tuple[str, ...]
    outcome: str


@dataclass(frozen=True)
class PolicyDecision:
    decision: str
    matched_rule_ids: list[str] = field(default_factory=list)
    reason: str = ""
    action: str | None = None
    subject: str | None = None

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
            rules.append(
                PolicyRule(
                    id=str(raw["id"]),
                    priority=int(raw["priority"]),
                    enabled=bool(raw["enabled"]),
                    roles_any=tuple(match["roles_any"]),
                    actions_any=tuple(match["actions_any"]),
                    outcome=str(decision["outcome"]),
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

    Semantics: deny by default; explicit deny overrides allow; higher priority
    wins between allows; disabled rules are ignored.
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

    if any(rule.outcome == "deny" for rule in matched):
        deny_ids = [rule.id for rule in matched if rule.outcome == "deny"]
        return PolicyDecision(
            decision="deny",
            matched_rule_ids=deny_ids,
            reason="explicit deny rule matched",
            action=action,
        )

    allows = [rule for rule in matched if rule.outcome == "allow"]
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
