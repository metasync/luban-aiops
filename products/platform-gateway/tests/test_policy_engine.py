"""Policy engine tests (SPEC-004: deny-by-default evaluation + contract sync)."""

import hashlib
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
    bundle_metadata,
    evaluate,
    load_bundle,
    reset_policy_state,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = REPO_ROOT / "shared" / "shared-contracts"
SHARED_BUNDLE = CONTRACTS_DIR / "policies" / "policy-default.yaml"
RULE_SCHEMA = CONTRACTS_DIR / "schemas" / "policy-rule.schema.json"
DECISION_SCHEMA = CONTRACTS_DIR / "schemas" / "policy-decision.schema.json"
# SPEC-074: the synthetic agent-role demonstration bundle (the canonical bundle
# stays byte-unchanged, OQ-4), shared with the scenario harness.
FIXTURE_BUNDLE = CONTRACTS_DIR / "policies" / "fixtures" / "agent-role-demo.yaml"


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


class BundleProvenanceTests(unittest.TestCase):
    """SPEC-048 R-1: the bundle content hash is computed, not authored."""

    def setUp(self) -> None:
        reset_policy_state()

    def tearDown(self) -> None:
        reset_policy_state()

    def test_packaged_default_hash_matches_canonical_file(self) -> None:
        settings = _settings()
        metadata = bundle_metadata(settings)
        expected = hashlib.sha256(
            SHARED_BUNDLE.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()
        self.assertEqual(metadata["sha256"], expected)
        self.assertEqual(metadata["source"], "packaged-default")

    def test_hash_is_stable_across_cached_loads(self) -> None:
        settings = _settings()
        first = bundle_metadata(settings)["sha256"]
        second = bundle_metadata(settings)["sha256"]
        self.assertEqual(first, second)

    def test_configured_bundle_hash_tracks_file_bytes(self) -> None:
        bundle_path = Path("provenance-bundle.yaml")
        text = yaml.safe_dump({"version": 1, "rules": []})
        bundle_path.write_text(text, encoding="utf-8")
        try:
            settings = _settings(policy_path=str(bundle_path))
            metadata = bundle_metadata(settings)
            self.assertEqual(metadata["source"], "configured")
            self.assertEqual(
                metadata["sha256"],
                hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        finally:
            reset_policy_state()
            bundle_path.unlink(missing_ok=True)

    def test_one_byte_edit_changes_the_hash(self) -> None:
        bundle_path = Path("provenance-flip-bundle.yaml")
        text = yaml.safe_dump({"version": 1, "rules": []})
        bundle_path.write_text(text, encoding="utf-8")
        try:
            settings = _settings(policy_path=str(bundle_path))
            before = bundle_metadata(settings)["sha256"]
            reset_policy_state()
            bundle_path.write_text(text + "\n", encoding="utf-8")
            settings = _settings(policy_path=str(bundle_path))
            after = bundle_metadata(settings)["sha256"]
            self.assertNotEqual(before, after)
        finally:
            reset_policy_state()
            bundle_path.unlink(missing_ok=True)

    def test_hash_empty_before_load_and_reset_clears_it(self) -> None:
        self.assertEqual(policy_engine._bundle_hash, "")
        settings = _settings()
        bundle_metadata(settings)
        self.assertNotEqual(policy_engine._bundle_hash, "")
        reset_policy_state()
        self.assertEqual(policy_engine._bundle_hash, "")


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
        # Exempt routes (health, runtime, auth, identity) carry no action; this
        # set is the complete protected surface. tools:mutate is enforced by
        # the tool-gateway but listed here so the permission matrix always
        # carries it (SPEC-021). session:list/session:delete complete the
        # session workspace lifecycle (SPEC-022 R-1). models:list guards
        # model catalog discovery (SPEC-024 R-2). approvals:list guards the
        # approver confirmation inbox (SPEC-031 R-3). documents:create/
        # documents:read guard the operations document repository and
        # session:update guards the owner rename (SPEC-039 R-2/R-7).
        # session:skill_draft and incident:skill_draft guard the two
        # skill-draft entry points (SPEC-044 R-3 / SPEC-045 R-3).
        # session:skill_graduate guards skill graduation and the target
        # declaration that scopes it — one capability, one action
        # (SPEC-055 R-4/OQ-3). runtime:flags guards the authenticated
        # feature-flag inventory read (SPEC-072 R-5). remediate:stage guards the
        # operator-initiated diagnose→act staging trigger (SPEC-077 R-3), enforced
        # on this gateway's POST /api/v1/remediate proxy and registered in both
        # engines' vocabularies for policy-matrix parity.
        self.assertEqual(
            PROTECTED_ACTIONS,
            frozenset({
                "chat", "chat:confirm", "session:create", "session:read",
                "session:list", "session:delete", "session:update",
                "session:skill_draft",
                "incident:skill_draft",
                "session:skill_graduate",
                "audit:read",
                "incident:read", "incident:create", "incident:triage",
                "policy:read", "tools:list", "tools:mutate", "secrets:deliver", "skills:read",
                "models:list", "approvals:list",
                "documents:create", "documents:read",
                "runtime:flags",
                "remediate:stage",
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


class AgentRoleAxisSemanticsTests(unittest.TestCase):
    """SPEC-074 R-2: the optional agent-role axis on the platform-gateway engine."""

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
    def _scoped_allow(
        rule_id: str,
        agent_roles: list[str],
        *,
        roles: list[str] | None = None,
        action: str = "tools:invoke",
        priority: int = 100,
    ) -> dict:
        return {
            "id": rule_id,
            "domain": "action_authz",
            "description": rule_id,
            "priority": priority,
            "enabled": True,
            "match": {
                "roles_any": roles or ["operator"],
                "actions_any": [action],
                "agent_roles_any": agent_roles,
            },
            "decision": {"outcome": "allow"},
        }

    def test_canonical_bundle_agent_role_axis_is_live_only_where_scoped(self) -> None:
        # SPEC-076 R-5/OQ-4: phase 5 lands the minimal canonical agent_roles_any
        # rules. This proves the ENGINE semantics — when a role IS threaded, the
        # axis fires (fail-closed, subtractive-only): an unscoped call (agent_role
        # None) and a role the rules do not name (orchestrator) evaluate
        # byte-identically to the pre-axis baseline, while a diagnostician is
        # denied a mutating grant. It stays INERT IN DEPLOYMENT because no deployed
        # caller threads a role (R-3 keeps it off the wire) — see
        # AgentRoleReachabilityGuardTests below.
        settings = _settings()
        human_roles = [
            "platform-admin", "approver", "operator", "developer",
            "read-only-observer", "auditor",
        ]
        for role in human_roles:
            for action in sorted(PROTECTED_ACTIONS):
                baseline = evaluate(settings, [role], action)
                for agent_role in (None, "orchestrator"):
                    scoped = evaluate(settings, [role], action, agent_role)
                    self.assertEqual(
                        scoped.decision, baseline.decision, f"{role}/{action}/{agent_role}"
                    )
                    self.assertEqual(
                        scoped.matched_rule_ids, baseline.matched_rule_ids,
                        f"{role}/{action}/{agent_role}",
                    )
        # The one live divergence: a diagnostician can never reach a mutating
        # grant (the policy mirror of SPEC-073 toolkit narrowing). On this
        # gateway the executor's staged mutation still parks behind tier_2.
        operational = [
            "platform-admin", "approver", "operator", "developer",
            "read-only-observer",
        ]
        for role in operational:
            decision = evaluate(settings, [role], "tools:mutate", "diagnostician")
            self.assertEqual(decision.decision, "deny", role)
            self.assertIn("deny-diagnostician-tools-mutate", decision.matched_rule_ids)
            # The diagnostician read posture is preserved: read invocation stays
            # allowed for every operational role.
            self.assertEqual(
                evaluate(settings, [role], "tools:invoke", "diagnostician").decision,
                "allow",
                role,
            )
        # The executor->require_approval encoding parks on the confirm path for
        # the mutating-capable human roles (developer holds no mutate grant, so
        # it stays deny-by-default whichever axis applies).
        for role in ["platform-admin", "approver", "operator"]:
            self.assertEqual(
                evaluate(settings, [role], "tools:mutate", "executor").decision,
                "require_approval",
                role,
            )

    def test_scoped_rule_matches_only_its_agent_role(self) -> None:
        settings = self._write_bundle([self._scoped_allow("diag-read", ["diagnostician"])])
        self.assertEqual(
            evaluate(settings, ["operator"], "tools:invoke", "diagnostician").decision, "allow"
        )
        self.assertEqual(
            evaluate(settings, ["operator"], "tools:invoke", "executor").decision, "deny"
        )
        self.assertEqual(
            evaluate(settings, ["operator"], "tools:invoke", "orchestrator").decision, "deny"
        )

    def test_scoped_rule_never_matches_an_unscoped_call(self) -> None:
        # Fail-closed: an agent-role-scoped grant cannot be satisfied by a turn
        # carrying no role (mirrors SPEC-073 R-5).
        settings = self._write_bundle([self._scoped_allow("diag-read", ["diagnostician"])])
        decision = evaluate(settings, ["operator"], "tools:invoke")
        self.assertEqual(decision.decision, "deny")
        self.assertEqual(decision.matched_rule_ids, [])

    def test_agent_role_composes_conjunctively_with_the_human_axis(self) -> None:
        settings = self._write_bundle([self._scoped_allow("exec-read", ["executor"])])
        # Both axes must hold: the human role AND the agent-role.
        self.assertEqual(
            evaluate(settings, ["operator"], "tools:invoke", "executor").decision, "allow"
        )
        self.assertEqual(
            evaluate(settings, ["auditor"], "tools:invoke", "executor").decision, "deny"
        )
        self.assertEqual(
            evaluate(settings, ["operator", "auditor"], "tools:invoke", "executor").decision,
            "allow",
        )

    def test_scoped_allow_never_overrides_a_human_deny(self) -> None:
        # R-5 subtractive-only: the axis can only remove authority the token
        # already grants; a scoped allow cannot override an explicit human deny.
        deny = {
            "id": "deny-mutate",
            "domain": "action_authz",
            "description": "deny",
            "priority": 1000,
            "enabled": True,
            "match": {"roles_any": ["operator"], "actions_any": ["tools:mutate"]},
            "decision": {"outcome": "deny"},
        }
        scoped_allow = self._scoped_allow(
            "exec-mutate", ["executor"], action="tools:mutate", priority=100
        )
        settings = self._write_bundle([deny, scoped_allow])
        decision = evaluate(settings, ["operator"], "tools:mutate", "executor")
        self.assertEqual(decision.decision, "deny")
        self.assertEqual(decision.matched_rule_ids, ["deny-mutate"])

    def test_scoped_grant_cannot_widen_an_ungranted_human_role(self) -> None:
        # A human role the token does not hold is never satisfied by the axis.
        settings = self._write_bundle(
            [self._scoped_allow("exec-mutate", ["executor"], action="tools:mutate")]
        )
        self.assertEqual(
            evaluate(settings, ["developer"], "tools:mutate", "executor").decision, "deny"
        )


class AgentRoleLoadValidationTests(unittest.TestCase):
    """SPEC-074 R-2: fail-closed load validation of the agent-role axis."""

    def setUp(self) -> None:
        reset_policy_state()
        self.bundle_path = Path(self.id().split(".")[-1] + "-bundle.yaml")

    def tearDown(self) -> None:
        reset_policy_state()
        self.bundle_path.unlink(missing_ok=True)

    def _load(self, agent_roles_any):
        rule = {
            "id": "scoped",
            "domain": "action_authz",
            "description": "scoped",
            "priority": 100,
            "enabled": True,
            "match": {
                "roles_any": ["operator"],
                "actions_any": ["tools:invoke"],
                "agent_roles_any": agent_roles_any,
            },
            "decision": {"outcome": "allow"},
        }
        self.bundle_path.write_text(
            yaml.safe_dump({"version": 1, "rules": [rule]}), encoding="utf-8"
        )
        settings = _settings(policy_path=str(self.bundle_path))
        load_bundle(settings)
        return settings

    def test_out_of_vocabulary_agent_role_rejected(self) -> None:
        for bad in (["summarizer"], ["EXECUTOR"], ["planner"], ["approver"], ["operator"]):
            reset_policy_state()
            with self.assertRaises(PolicyLoadError, msg=str(bad)):
                self._load(bad)

    def test_non_list_agent_roles_rejected(self) -> None:
        with self.assertRaises(PolicyLoadError):
            self._load("executor")

    def test_empty_list_is_unconstrained_and_loads(self) -> None:
        # An explicit empty list behaves like absent (matches any call).
        settings = self._load([])
        decision = evaluate(settings, ["operator"], "tools:invoke")
        self.assertEqual(decision.decision, "allow")

    def test_valid_vocabulary_loads(self) -> None:
        settings = self._load(["diagnostician", "orchestrator", "executor"])
        rules = load_bundle(settings)
        self.assertEqual(
            rules[0].agent_roles_any, ("diagnostician", "orchestrator", "executor")
        )


class AgentRoleSchemaContractTests(unittest.TestCase):
    """SPEC-074 R-1/R-6: the v2->v3 schema revision is additive and closed."""

    def setUp(self) -> None:
        reset_policy_state()
        self.schema = json.loads(RULE_SCHEMA.read_text(encoding="utf-8"))

    def test_title_is_v3(self) -> None:
        self.assertEqual(self.schema["title"], "Policy Rule (v3)")

    def test_agent_roles_any_is_optional_not_required(self) -> None:
        match = self.schema["properties"]["match"]
        # Additive: the new key is a property but NOT in match.required, so a
        # v2 rule (no agent_roles_any) still validates and evaluates unchanged.
        self.assertIn("agent_roles_any", match["properties"])
        self.assertEqual(match["required"], ["roles_any", "actions_any"])
        self.assertFalse(match["additionalProperties"])

    def test_agent_roles_any_enum_is_the_closed_vocabulary(self) -> None:
        items = self.schema["properties"]["match"]["properties"]["agent_roles_any"]["items"]
        self.assertEqual(set(items["enum"]), {"diagnostician", "orchestrator", "executor"})

    def test_engine_vocabulary_matches_schema_enum(self) -> None:
        # The engine's local AGENT_ROLES is kept in lockstep with the schema.
        items = self.schema["properties"]["match"]["properties"]["agent_roles_any"]["items"]
        self.assertEqual(set(policy_engine.AGENT_ROLES), set(items["enum"]))

    def test_canonical_rules_validate_and_carry_only_the_spec076_axis(self) -> None:
        # SPEC-076 R-5/OQ-4: every canonical rule validates against the v3
        # schema; exactly the two phase-5 rules carry agent_roles_any, and only
        # over the closed vocabulary. Every other rule stays axis-free.
        data = yaml.safe_load(SHARED_BUNDLE.read_text(encoding="utf-8"))
        axis_rules: dict[str, tuple[str, ...]] = {}
        for rule in data["rules"]:
            validate(instance=rule, schema=self.schema)
            axis = rule["match"].get("agent_roles_any")
            if axis is not None:
                self.assertTrue(
                    set(axis) <= {"diagnostician", "orchestrator", "executor"},
                    rule["id"],
                )
                axis_rules[rule["id"]] = tuple(axis)
        self.assertEqual(
            axis_rules,
            {
                "deny-diagnostician-tools-mutate": ("diagnostician",),
                "require-approval-executor-tools-mutate": ("executor",),
            },
        )

    def test_out_of_vocabulary_axis_fails_schema_validation(self) -> None:
        from jsonschema import ValidationError

        bad_rule = {
            "id": "x", "domain": "action_authz", "description": "x",
            "priority": 100, "enabled": True,
            "match": {
                "roles_any": ["operator"], "actions_any": ["tools:invoke"],
                "agent_roles_any": ["summarizer"],
            },
            "decision": {"outcome": "allow"},
        }
        with self.assertRaises(ValidationError):
            validate(instance=bad_rule, schema=self.schema)

    def test_demo_fixture_rules_validate_against_v3(self) -> None:
        # The synthetic demonstration bundle (R-3/R-6) is v3-conformant and
        # actually exercises the axis.
        data = yaml.safe_load(FIXTURE_BUNDLE.read_text(encoding="utf-8"))
        scoped = sum(1 for rule in data["rules"] if "agent_roles_any" in rule["match"])
        for rule in data["rules"]:
            validate(instance=rule, schema=self.schema)
        self.assertGreaterEqual(scoped, 1)


class AgentRoleDisjointnessGuardTests(unittest.TestCase):
    """SPEC-074 R-3: an agent-role is never a human role nor an approver decider."""

    def test_agent_role_vocabulary_disjoint_from_human_roles_and_deciders(self) -> None:
        data = yaml.safe_load(SHARED_BUNDLE.read_text(encoding="utf-8"))
        agent_roles = {"diagnostician", "orchestrator", "executor"}
        human_roles: set[str] = set()
        deciders: set[str] = set()
        for rule in data["rules"]:
            human_roles.update(rule["match"].get("roles_any", []))
            approval = rule.get("decision", {}).get("approval")
            if approval:
                deciders.update(approval.get("decided_by_roles", []))
        # No agent-role is ever a human platform role ...
        self.assertEqual(agent_roles & human_roles, set())
        # ... and no agent-role is ever an approver decider (an agent never
        # approves — the executor->human-approver invariant, now a test).
        self.assertEqual(agent_roles & deciders, set())
        self.assertIn("approver", deciders)  # the human decider vocabulary is real


class AgentRoleReachabilityGuardTests(unittest.TestCase):
    """SPEC-074 R-5: the gateway agent-role axis has no deployed producer.

    SPEC-076 (phase 5) binds the role in-process for toolkit narrowing + audit
    attribution, but SPEC-073 R-3 keeps it off every wire field, so no deployed
    gateway caller threads a non-None ``agent_role`` into ``evaluate()`` — the axis
    stays ready-but-inert and this guard still passes. The canonical rules fire only
    once a role IS threaded (the phase-6 wire contract, or the FU-076-c in-process
    evaluation point), which this guard pins until then.
    """

    def test_no_deployed_caller_threads_a_non_none_agent_role(self) -> None:
        # Policy-side mirror of the SPEC-073 R-5 reachability guard: scan the
        # deployed gateway package. Outside policy_engine.py (which *defines*
        # the vocabulary and the axis), no source may thread a concrete
        # agent-role literal or pass agent_role= by keyword — proving every
        # deployed evaluation forwards the inert default None.
        product_src = Path(policy_engine.__file__).resolve().parents[1]
        literals = {
            '"diagnostician"', "'diagnostician'",
            '"orchestrator"', "'orchestrator'",
            '"executor"', "'executor'",
        }
        offenders: list[str] = []
        for path in product_src.rglob("*.py"):
            if path.name == "policy_engine.py":
                continue
            text = path.read_text(encoding="utf-8")
            rel = str(path.relative_to(product_src))
            for literal in literals:
                if literal in text:
                    offenders.append(f"{rel}: agent-role literal {literal}")
            if "agent_role=" in text:
                offenders.append(f"{rel}: agent_role= keyword pass")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
