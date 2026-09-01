"""Policy engine tests (SPEC-004: deny-by-default evaluation + contract sync)."""

import hashlib
import json
import unittest
from pathlib import Path

import yaml
from jsonschema import validate

from tool_gateway.core.config import GatewaySettings
from tool_gateway.services import policy_engine
from tool_gateway.services.gateway_service import ready_status
from tool_gateway.services.policy_engine import (
    PROTECTED_ACTIONS,
    PolicyDecision,
    PolicyLoadError,
    bundle_sha256,
    evaluate,
    load_bundle,
    reset_policy_state,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = REPO_ROOT / "shared" / "shared-contracts"
SHARED_BUNDLE = CONTRACTS_DIR / "policies" / "policy-default.yaml"
RULE_SCHEMA = CONTRACTS_DIR / "schemas" / "policy-rule.schema.json"
DECISION_SCHEMA = CONTRACTS_DIR / "schemas" / "policy-decision.schema.json"


def _settings(**overrides) -> GatewaySettings:
    reset_policy_state()
    return GatewaySettings(**overrides)


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

    def test_observer_allowed_read_only_tools(self) -> None:
        # Observers may discover and invoke read-only tools, matching the
        # authorization matrix tier-0 read grant.
        settings = _settings()
        for action in ["tools:list", "tools:invoke"]:
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

    def _write_bundle(self, rules: list[dict]) -> GatewaySettings:
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


class BundleProvenanceTests(unittest.TestCase):
    """SPEC-048 R-1: the bundle content hash is computed, not authored."""

    def setUp(self) -> None:
        reset_policy_state()

    def tearDown(self) -> None:
        reset_policy_state()

    def test_packaged_default_hash_matches_canonical_file(self) -> None:
        settings = _settings()
        load_bundle(settings)
        expected = hashlib.sha256(
            SHARED_BUNDLE.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()
        self.assertEqual(bundle_sha256(), expected)

    def test_empty_before_load_and_reset_clears(self) -> None:
        self.assertEqual(bundle_sha256(), "")
        load_bundle(_settings())
        self.assertNotEqual(bundle_sha256(), "")
        reset_policy_state()
        self.assertEqual(bundle_sha256(), "")

    def test_configured_bundle_hash_tracks_file_bytes(self) -> None:
        bundle_path = Path("provenance-bundle.yaml")
        text = yaml.safe_dump({"version": 1, "rules": []})
        bundle_path.write_text(text, encoding="utf-8")
        try:
            load_bundle(_settings(policy_path=str(bundle_path)))
            self.assertEqual(
                bundle_sha256(),
                hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        finally:
            reset_policy_state()
            bundle_path.unlink(missing_ok=True)


class ReadinessProvenanceTests(unittest.IsolatedAsyncioTestCase):
    """SPEC-048 R-1: the readiness surface carries the bundle fingerprint."""

    def setUp(self) -> None:
        reset_policy_state()

    def tearDown(self) -> None:
        reset_policy_state()

    async def test_ready_status_carries_bundle_sha256(self) -> None:
        payload = await ready_status(_settings())
        expected = hashlib.sha256(
            SHARED_BUNDLE.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["policy_bundle_sha256"], expected)


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

    def test_overlay_bundle_matches_shared_contracts(self) -> None:
        # SPEC-048 R-5: the GitOps overlay copy rides `make sync-policy`,
        # so manual overlay drift must fail verify exactly like packaged
        # drift — one canonical bundle, byte-identical everywhere.
        overlay = (
            CONTRACTS_DIR.parent
            / "platform-ops"
            / "gitops"
            / "dev-k8s"
            / "base"
            / "shared"
            / "policy.yaml"
        )
        self.assertEqual(
            overlay.read_text(encoding="utf-8"),
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
        # Health and metrics routes carry no action and are exempt; portal-
        # facing actions (chat, session:*) live in platform-gateway. This set
        # is the complete protected surface of the tool service; tools:mutate
        # gates write/admin risk invocations (SPEC-021 R-1).
        self.assertEqual(
            PROTECTED_ACTIONS,
            frozenset({"tools:list", "tools:invoke", "tools:mutate"}),
        )


class RequireApprovalLoadTests(unittest.TestCase):
    """SPEC-030 R-2: tool-gateway validates then skips require_approval rules.

    The synced default bundle carries the tier_2 tools:mutate rule; this
    gateway has no approval substrate, so the rule must not break the load
    and must not participate in evaluation (SPEC-021 admission unchanged).
    """

    def setUp(self) -> None:
        reset_policy_state()
        self.bundle_path = Path(self.id().split(".")[-1] + "-bundle.yaml")

    def tearDown(self) -> None:
        reset_policy_state()
        self.bundle_path.unlink(missing_ok=True)

    def _load(self, rules: list[dict]) -> list:
        self.bundle_path.write_text(
            yaml.safe_dump({"version": 1, "rules": rules}), encoding="utf-8"
        )
        return load_bundle(_settings(policy_path=str(self.bundle_path)))

    @staticmethod
    def _approval_rule(rule_id: str = "approve-mutate") -> dict:
        return {
            "id": rule_id,
            "domain": "action_authz",
            "description": rule_id,
            "priority": 200,
            "enabled": True,
            "match": {
                "roles_any": ["platform-admin", "approver", "operator", "developer"],
                "actions_any": ["tools:mutate"],
            },
            "decision": {
                "outcome": "require_approval",
                "approval": {
                    "tier": "tier_2",
                    "decided_by_roles": ["approver", "platform-admin"],
                },
            },
        }

    @staticmethod
    def _allow_mutate_rule() -> dict:
        return {
            "id": "allow-mutate",
            "domain": "action_authz",
            "description": "allow",
            "priority": 100,
            "enabled": True,
            "match": {
                "roles_any": ["platform-admin", "operator"],
                "actions_any": ["tools:mutate"],
            },
            "decision": {"outcome": "allow"},
        }

    def test_approval_rule_skipped_at_load(self) -> None:
        rules = self._load([self._allow_mutate_rule(), self._approval_rule()])
        self.assertEqual([rule.id for rule in rules], ["allow-mutate"])

    def test_admission_stays_allow_despite_approval_rule(self) -> None:
        self._load([self._allow_mutate_rule(), self._approval_rule()])
        settings = _settings(policy_path=str(self.bundle_path))
        decision = evaluate(settings, ["operator"], "tools:mutate")
        self.assertEqual(decision.decision, "allow")
        self.assertIsNone(decision.approval)

    def test_packaged_default_bundle_loads_and_admission_unchanged(self) -> None:
        settings = _settings()
        rules = load_bundle(settings)
        self.assertTrue(all(rule.outcome != "require_approval" for rule in rules))
        for role in ["platform-admin", "operator"]:
            decision = evaluate(settings, [role], "tools:mutate")
            self.assertEqual(decision.decision, "allow", role)

    def test_malformed_approval_block_still_rejected(self) -> None:
        bad = self._approval_rule()
        bad["decision"]["approval"]["allow_self_approval"] = True
        with self.assertRaises(PolicyLoadError):
            self._load([bad])

    def test_missing_approval_block_still_rejected(self) -> None:
        bad = self._approval_rule()
        del bad["decision"]["approval"]
        with self.assertRaises(PolicyLoadError):
            self._load([bad])


if __name__ == "__main__":
    unittest.main()
