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
        # model catalog discovery (SPEC-024 R-2).
        self.assertEqual(
            PROTECTED_ACTIONS,
            frozenset({
                "chat", "chat:confirm", "session:create", "session:read",
                "session:list", "session:delete",
                "audit:read",
                "incident:read", "incident:create", "incident:triage",
                "policy:read", "tools:list", "tools:mutate", "skills:read",
                "models:list",
            }),
        )


if __name__ == "__main__":
    unittest.main()
