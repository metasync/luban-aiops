"""Policy engine tests (SPEC-004: deny-by-default evaluation + contract sync)."""

import json
import unittest
from pathlib import Path

import yaml
from jsonschema import validate

from platform_gateway.core.config import PlatformGatewaySettings
from platform_gateway.services import policy_engine
from platform_gateway.services.policy_engine import (
    PROTECTED_ACTIONS,
    PolicyDecision,
    PolicyLoadError,
    evaluate,
    load_bundle,
    reset_policy_state,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = REPO_ROOT / "shared" / "shared-contracts"
SHARED_BUNDLE = CONTRACTS_DIR / "policies" / "policy-default.yaml"
RULE_SCHEMA = CONTRACTS_DIR / "schemas" / "policy-rule.schema.json"
DECISION_SCHEMA = CONTRACTS_DIR / "schemas" / "policy-decision.schema.json"


def _settings(**overrides) -> PlatformGatewaySettings:
    reset_policy_state()
    return PlatformGatewaySettings(**overrides)


class EvaluationSemanticsTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_policy_state()

    def tearDown(self) -> None:
        reset_policy_state()

    def test_allows_granted_role(self) -> None:
        settings = _settings()
        for role in ["platform-admin", "approver", "operator", "developer"]:
            for action in ["chat", "session:create", "session:read"]:
                decision = evaluate(settings, [role], action)
                self.assertEqual(decision.decision, "allow", f"{role}/{action}")

    def test_observer_allowed_chat_and_sessions(self) -> None:
        settings = _settings()
        for action in ["chat", "session:create", "session:read"]:
            decision = evaluate(settings, ["read-only-observer"], action)
            self.assertEqual(decision.decision, "allow", action)

    def test_deny_by_default_for_unknown_action(self) -> None:
        settings = _settings()
        decision = evaluate(settings, ["operator"], "restart-service")
        self.assertEqual(decision.decision, "deny")
        self.assertEqual(decision.matched_rule_ids, [])
        self.assertIn("no matching policy rule", decision.reason)

    def test_deny_by_default_for_ungranted_role(self) -> None:
        settings = _settings()
        decision = evaluate(settings, ["auditor"], "chat")
        self.assertEqual(decision.decision, "deny")
        self.assertEqual(decision.matched_rule_ids, [])

    def test_deny_by_default_for_empty_roles(self) -> None:
        settings = _settings()
        decision = evaluate(settings, [], "chat")
        self.assertEqual(decision.decision, "deny")


class PrecedenceTests(unittest.TestCase):
    """Precedence semantics via a custom bundle (deny wins, priority, disabled)."""

    def setUp(self) -> None:
        reset_policy_state()
        self.bundle_path = Path(self.id() + "-bundle.yaml")

    def tearDown(self) -> None:
        reset_policy_state()
        self.bundle_path.unlink(missing_ok=True)

    def _write_bundle(self, rules: list[dict]) -> PlatformGatewaySettings:
        self.bundle_path.write_text(
            yaml.safe_dump({"version": 1, "rules": rules}), encoding="utf-8"
        )
        return _settings(policy_path=str(self.bundle_path))

    def test_explicit_deny_overrides_allow(self) -> None:
        settings = self._write_bundle(
            [
                {
                    "id": "allow-chat",
                    "domain": "action_authz",
                    "description": "allow",
                    "priority": 100,
                    "enabled": True,
                    "match": {"roles_any": ["operator"], "actions_any": ["chat"]},
                    "decision": {"outcome": "allow"},
                },
                {
                    "id": "deny-chat",
                    "domain": "action_authz",
                    "description": "deny",
                    "priority": 1,
                    "enabled": True,
                    "match": {"roles_any": ["operator"], "actions_any": ["chat"]},
                    "decision": {"outcome": "deny"},
                },
            ]
        )
        decision = evaluate(settings, ["operator"], "chat")
        self.assertEqual(decision.decision, "deny")
        self.assertEqual(decision.matched_rule_ids, ["deny-chat"])

    def test_higher_priority_allow_wins(self) -> None:
        settings = self._write_bundle(
            [
                {
                    "id": "low",
                    "domain": "action_authz",
                    "description": "low",
                    "priority": 10,
                    "enabled": True,
                    "match": {"roles_any": ["operator"], "actions_any": ["chat"]},
                    "decision": {"outcome": "allow"},
                },
                {
                    "id": "high",
                    "domain": "action_authz",
                    "description": "high",
                    "priority": 500,
                    "enabled": True,
                    "match": {"roles_any": ["operator"], "actions_any": ["chat"]},
                    "decision": {"outcome": "allow"},
                },
            ]
        )
        decision = evaluate(settings, ["operator"], "chat")
        self.assertEqual(decision.decision, "allow")
        self.assertEqual(decision.matched_rule_ids, ["high"])

    def test_disabled_rule_is_ignored(self) -> None:
        settings = self._write_bundle(
            [
                {
                    "id": "disabled-allow",
                    "domain": "action_authz",
                    "description": "disabled",
                    "priority": 100,
                    "enabled": False,
                    "match": {"roles_any": ["operator"], "actions_any": ["chat"]},
                    "decision": {"outcome": "allow"},
                },
            ]
        )
        decision = evaluate(settings, ["operator"], "chat")
        self.assertEqual(decision.decision, "deny")


class BundleLoadingTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_policy_state()

    def tearDown(self) -> None:
        reset_policy_state()

    def test_missing_configured_path_raises(self) -> None:
        settings = _settings(policy_path="/nonexistent/policy.yaml")
        with self.assertRaises(PolicyLoadError):
            load_bundle(settings)

    def test_invalid_yaml_at_configured_path_raises(self) -> None:
        bad = Path("invalid-bundle.yaml")
        bad.write_text("rules: [not: valid: yaml", encoding="utf-8")
        try:
            settings = _settings(policy_path=str(bad))
            with self.assertRaises(PolicyLoadError):
                load_bundle(settings)
        finally:
            bad.unlink(missing_ok=True)

    def test_malformed_rule_at_configured_path_raises(self) -> None:
        malformed = Path("malformed-bundle.yaml")
        malformed.write_text(
            yaml.safe_dump({"version": 1, "rules": [{"id": "x"}]}), encoding="utf-8"
        )
        try:
            settings = _settings(policy_path=str(malformed))
            with self.assertRaises(PolicyLoadError):
                load_bundle(settings)
        finally:
            malformed.unlink(missing_ok=True)

    def test_unset_path_loads_packaged_default(self) -> None:
        settings = _settings()
        rules = load_bundle(settings)
        self.assertTrue(rules)
        self.assertTrue(all(rule.enabled for rule in rules))


class ContractAlignmentTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_policy_state()

    def tearDown(self) -> None:
        reset_policy_state()

    def test_packaged_bundle_matches_shared_contracts(self) -> None:
        packaged = Path(
            policy_engine.__file__
        ).parent.parent / "policies" / "policy-default.yaml"
        self.assertEqual(
            packaged.read_text(encoding="utf-8"),
            SHARED_BUNDLE.read_text(encoding="utf-8"),
        )

    def test_default_bundle_rules_validate_against_schema(self) -> None:
        schema = json.loads(RULE_SCHEMA.read_text(encoding="utf-8"))
        data = yaml.safe_load(SHARED_BUNDLE.read_text(encoding="utf-8"))
        for rule in data["rules"]:
            validate(instance=rule, schema=schema)

    def test_decision_serialization_validates_against_schema(self) -> None:
        schema = json.loads(DECISION_SCHEMA.read_text(encoding="utf-8"))
        decision = PolicyDecision(
            decision="deny",
            matched_rule_ids=[],
            reason="no matching policy rule",
            action="chat",
            subject="user-1",
        )
        validate(instance=decision.to_dict(), schema=schema)

    def test_protected_actions_boundary(self) -> None:
        # Exempt routes (health, runtime, auth, identity) carry no action; this
        # set is the complete protected surface. tools:mutate is enforced by
        # the tool-gateway but listed here so the permission matrix always
        # carries it (SPEC-021). session:list/session:delete complete the
        # session workspace lifecycle (SPEC-022 R-1). models:list guards
        # model catalog discovery (SPEC-024 R-2). approvals:list guards the
        # approver confirmation inbox (SPEC-031 R-3). documents:create/
        # documents:read guard the operations document repository and
        # session:update guards the owner rename (SPEC-039 R-2/R-7).
        self.assertEqual(
            PROTECTED_ACTIONS,
            frozenset({
                "chat", "chat:confirm", "session:create", "session:read",
                "session:list", "session:delete", "session:update",
                "audit:read",
                "incident:read", "incident:create", "incident:triage",
                "policy:read", "tools:list", "tools:mutate", "skills:read",
                "models:list", "approvals:list",
                "documents:create", "documents:read",
            }),
        )


class RequireApprovalSemanticsTests(unittest.TestCase):
    """SPEC-030 R-2: deny > require_approval > allow, priority, disabled."""

    def setUp(self) -> None:
        reset_policy_state()
        self.bundle_path = Path(self.id().split(".")[-1] + "-bundle.yaml")

    def tearDown(self) -> None:
        reset_policy_state()
        self.bundle_path.unlink(missing_ok=True)

    def _write_bundle(self, rules: list[dict]) -> PlatformGatewaySettings:
        self.bundle_path.write_text(
            yaml.safe_dump({"version": 1, "rules": rules}), encoding="utf-8"
        )
        return _settings(policy_path=str(self.bundle_path))

    @staticmethod
    def _approval_rule(
        rule_id: str,
        *,
        priority: int = 100,
        enabled: bool = True,
        tier: str = "tier_2",
        deciders: list[str] | None = None,
        allow_self_approval: bool | None = None,
        roles: list[str] | None = None,
    ) -> dict:
        approval: dict = {
            "tier": tier,
            "decided_by_roles": deciders or ["approver", "platform-admin"],
        }
        if allow_self_approval is not None:
            approval["allow_self_approval"] = allow_self_approval
        return {
            "id": rule_id,
            "domain": "action_authz",
            "description": rule_id,
            "priority": priority,
            "enabled": enabled,
            "match": {
                "roles_any": roles or ["operator"],
                "actions_any": ["tools:mutate"],
            },
            "decision": {"outcome": "require_approval", "approval": approval},
        }

    @staticmethod
    def _allow_rule(rule_id: str, action: str = "tools:mutate") -> dict:
        return {
            "id": rule_id,
            "domain": "action_authz",
            "description": rule_id,
            "priority": 100,
            "enabled": True,
            "match": {"roles_any": ["operator"], "actions_any": [action]},
            "decision": {"outcome": "allow"},
        }

    def test_require_approval_overrides_allow(self) -> None:
        settings = self._write_bundle(
            [self._allow_rule("allow-mutate"), self._approval_rule("approve-mutate")]
        )
        decision = evaluate(settings, ["operator"], "tools:mutate")
        self.assertEqual(decision.decision, "require_approval")
        self.assertEqual(decision.matched_rule_ids, ["approve-mutate"])
        self.assertEqual(decision.approval_tier, "tier_2")
        self.assertIsNotNone(decision.approval)
        self.assertEqual(
            decision.approval.decided_by_roles, ("approver", "platform-admin")
        )
        self.assertFalse(decision.approval.effective_self_approval())

    def test_explicit_deny_overrides_require_approval(self) -> None:
        approval = self._approval_rule("approve-mutate")
        deny = {
            "id": "deny-mutate",
            "domain": "action_authz",
            "description": "deny",
            "priority": 1,
            "enabled": True,
            "match": {"roles_any": ["operator"], "actions_any": ["tools:mutate"]},
            "decision": {"outcome": "deny"},
        }
        settings = self._write_bundle([approval, deny, self._allow_rule("allow-mutate")])
        decision = evaluate(settings, ["operator"], "tools:mutate")
        self.assertEqual(decision.decision, "deny")
        self.assertEqual(decision.matched_rule_ids, ["deny-mutate"])
        self.assertIsNone(decision.approval)

    def test_highest_priority_approval_wins(self) -> None:
        settings = self._write_bundle(
            [
                self._approval_rule("low", priority=10, tier="tier_1", deciders=["operator"]),
                self._approval_rule("high", priority=500),
            ]
        )
        decision = evaluate(settings, ["operator"], "tools:mutate")
        self.assertEqual(decision.decision, "require_approval")
        self.assertEqual(decision.matched_rule_ids, ["high"])
        self.assertEqual(decision.approval_tier, "tier_2")

    def test_disabled_approval_rule_is_ignored(self) -> None:
        settings = self._write_bundle(
            [
                self._allow_rule("allow-mutate"),
                self._approval_rule("approve-mutate", enabled=False),
            ]
        )
        decision = evaluate(settings, ["operator"], "tools:mutate")
        self.assertEqual(decision.decision, "allow")

    def test_tier_1_self_approval_default(self) -> None:
        settings = self._write_bundle(
            [self._approval_rule("approve", tier="tier_1", deciders=["operator"])]
        )
        decision = evaluate(settings, ["operator"], "tools:mutate")
        self.assertEqual(decision.decision, "require_approval")
        self.assertTrue(decision.approval.effective_self_approval())

    def test_require_approval_serialization_validates_schema(self) -> None:
        schema = json.loads(DECISION_SCHEMA.read_text(encoding="utf-8"))
        settings = self._write_bundle([self._approval_rule("approve-mutate")])
        decision = evaluate(settings, ["operator"], "tools:mutate")
        validate(instance=decision.to_dict(), schema=schema)
        payload = decision.to_dict()
        self.assertEqual(payload["approval_tier"], "tier_2")
        self.assertEqual(payload["approval"]["tier"], "tier_2")


class RequireApprovalLoadValidationTests(unittest.TestCase):
    """SPEC-030 R-2: loud load failures for malformed approval rules."""

    def setUp(self) -> None:
        reset_policy_state()
        self.bundle_path = Path(self.id().split(".")[-1] + "-bundle.yaml")

    def tearDown(self) -> None:
        reset_policy_state()
        self.bundle_path.unlink(missing_ok=True)

    def _load(self, rules: list[dict]) -> None:
        self.bundle_path.write_text(
            yaml.safe_dump({"version": 1, "rules": rules}), encoding="utf-8"
        )
        load_bundle(_settings(policy_path=str(self.bundle_path)))

    @staticmethod
    def _base_rule(decision: dict) -> dict:
        return {
            "id": "rule",
            "domain": "action_authz",
            "description": "rule",
            "priority": 100,
            "enabled": True,
            "match": {"roles_any": ["operator"], "actions_any": ["tools:mutate"]},
            "decision": decision,
        }

    def test_tier_2_with_self_approval_true_rejected(self) -> None:
        with self.assertRaises(PolicyLoadError):
            self._load(
                [
                    self._base_rule(
                        {
                            "outcome": "require_approval",
                            "approval": {
                                "tier": "tier_2",
                                "decided_by_roles": ["approver"],
                                "allow_self_approval": True,
                            },
                        }
                    )
                ]
            )

    def test_unbridged_action_rejected(self) -> None:
        rule = self._base_rule(
            {
                "outcome": "require_approval",
                "approval": {"tier": "tier_1", "decided_by_roles": ["operator"]},
            }
        )
        rule["match"]["actions_any"] = ["chat"]
        with self.assertRaises(PolicyLoadError):
            self._load([rule])

    def test_require_approval_without_approval_block_rejected(self) -> None:
        with self.assertRaises(PolicyLoadError):
            self._load([self._base_rule({"outcome": "require_approval"})])

    def test_unknown_tier_rejected(self) -> None:
        with self.assertRaises(PolicyLoadError):
            self._load(
                [
                    self._base_rule(
                        {
                            "outcome": "require_approval",
                            "approval": {"tier": "tier_9", "decided_by_roles": ["approver"]},
                        }
                    )
                ]
            )

    def test_empty_deciders_rejected(self) -> None:
        with self.assertRaises(PolicyLoadError):
            self._load(
                [
                    self._base_rule(
                        {
                            "outcome": "require_approval",
                            "approval": {"tier": "tier_1", "decided_by_roles": []},
                        }
                    )
                ]
            )

    def test_approval_block_on_allow_rejected(self) -> None:
        with self.assertRaises(PolicyLoadError):
            self._load(
                [
                    self._base_rule(
                        {
                            "outcome": "allow",
                            "approval": {"tier": "tier_1", "decided_by_roles": ["operator"]},
                        }
                    )
                ]
            )

    def test_unknown_outcome_rejected(self) -> None:
        with self.assertRaises(PolicyLoadError):
            self._load([self._base_rule({"outcome": "allow_with_conditions"})])

    def test_default_bundle_ships_tier_2_tools_mutate_rule(self) -> None:
        # R-4 posture: the packaged default carries the tier_2 rule and it
        # answers require_approval for a mutating requester.
        settings = _settings()
        decision = evaluate(settings, ["operator"], "tools:mutate")
        self.assertEqual(decision.decision, "require_approval")
        self.assertEqual(decision.approval_tier, "tier_2")
        self.assertIn("approver", decision.approval.decided_by_roles)
        self.assertIn("platform-admin", decision.approval.decided_by_roles)


if __name__ == "__main__":
    unittest.main()
