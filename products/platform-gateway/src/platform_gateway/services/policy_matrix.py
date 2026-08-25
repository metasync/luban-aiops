"""Live permission-matrix derivation (SPEC-019 R-2).

Renders the effective role x action matrix from the policy bundle the
gateway actually enforces. Every cell goes through the standard
``evaluate()`` path — priority, explicit-deny-wins, and disabled-rule
semantics are inherited, never re-implemented — so a matrix cell always
equals what ``enforce_policy`` would decide for that role. The surface is
read-only transparency; authority stays with the policy engine.

SPEC-030 R-5: cells evaluating to ``require_approval`` read ``false`` in
the boolean matrix (they are not immediately allowed) and additionally
appear in the additive ``approval_requirements`` structure with the
tier and decider roles, so consumers that only read booleans keep the
fail-safe view while the portal renders the third state.
"""

from __future__ import annotations

from platform_gateway.core.config import PlatformGatewaySettings
from platform_gateway.schemas.api import IdentityContext
from platform_gateway.services.policy_engine import (
    PROTECTED_ACTIONS,
    bundle_metadata,
    evaluate,
    load_bundle,
)

ADMIN_ROLE = "platform-admin"


def build_policy_matrix(
    settings: PlatformGatewaySettings,
    identity: IdentityContext,
) -> dict[str, object]:
    """Build the caller-scoped permission matrix from the loaded bundle.

    Roles come from the bundle's rules; actions are the bundle's vocabulary
    unioned with the gateway's protected route actions. ``platform-admin``
    sees every row (scope ``full``); every other identity sees only its own
    granted roles (scope ``own``) — filtering happens here, server-side.
    """
    rules = load_bundle(settings)
    metadata = bundle_metadata(settings)

    bundle_roles = {role for rule in rules for role in rule.roles_any}
    bundle_actions = {action for rule in rules for action in rule.actions_any}
    actions = sorted(bundle_actions | PROTECTED_ACTIONS)

    is_admin = ADMIN_ROLE in identity.roles
    visible_roles = sorted(bundle_roles) if is_admin else sorted(identity.roles)

    matrix: dict[str, dict[str, bool]] = {}
    approval_requirements: dict[str, dict[str, dict[str, object]]] = {}
    for role in visible_roles:
        row: dict[str, bool] = {}
        approval_row: dict[str, dict[str, object]] = {}
        for action in actions:
            decision = evaluate(settings, [role], action)
            row[action] = decision.decision == "allow"
            # SPEC-030 R-5: the third cell state rides an additive
            # structure so boolean-only consumers stay unbroken.
            if decision.decision == "require_approval" and decision.approval:
                approval_row[action] = {
                    "tier": decision.approval.tier,
                    "decided_by_roles": list(decision.approval.decided_by_roles),
                    "rule_id": (
                        decision.matched_rule_ids[0]
                        if decision.matched_rule_ids
                        else None
                    ),
                }
        matrix[role] = row
        if approval_row:
            approval_requirements[role] = approval_row

    return {
        "version": metadata["version"],
        "source": metadata["source"],
        "scope": "full" if is_admin else "own",
        "roles": visible_roles,
        "actions": actions,
        "matrix": matrix,
        "approval_requirements": approval_requirements,
    }
