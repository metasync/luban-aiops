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
# SPEC-074: the synthetic agent-role demonstration bundle (the canonical bundle
# stays byte-unchanged, OQ-4), shared with the scenario harness.
FIXTURE_BUNDLE = CONTRACTS_DIR / "policies" / "fixtures" / "agent-role-demo.yaml"


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

    def test_targets_authorize_mirrors_invoke_holders(self) -> None:
        # SPEC-070 OQ-7: targets:authorize is granted to exactly the
        # tools:invoke holders — a requester may only drive enrollment for a
        # target they may already invoke on behalf of — so no new role is
        # synthesized. auditor (governance-only) and unknown roles stay denied
        # by default; the administered-mapping and entitlement rechecks are
        # route-level, never a bundle grant.
        settings = _settings()
        for role in [
            "platform-admin", "approver", "operator", "developer", "read-only-observer",
        ]:
            decision = evaluate(settings, [role], "targets:authorize")
            self.assertEqual(decision.decision, "allow", role)
        for role in ["auditor", "ghost-role"]:
            decision = evaluate(settings, [role], "targets:authorize")
            self.assertEqual(decision.decision, "deny", role)

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
        # gates write/admin risk invocations (SPEC-021 R-1), secrets:deliver
        # gates external-channel secret delivery (SPEC-062 R-4), and
        # targets:authorize gates the human-initiated outbound user-delegated
        # authorization workflow (SPEC-070 OQ-7). remediate:stage (SPEC-077 R-3)
        # is enforced on the platform-gateway proxy but registered here too so
        # the action surfaces in both engines' matrices and scenario coverage
        # (R-3 ratified "both engines"); no tool-gateway route evaluates it.
        self.assertEqual(
            PROTECTED_ACTIONS,
            frozenset(
                {
                    "tools:list",
                    "tools:invoke",
                    "tools:mutate",
                    "secrets:deliver",
                    "targets:authorize",
                    "remediate:stage",
                }
            ),
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


class AgentRoleAxisSemanticsTests(unittest.TestCase):
    """SPEC-074 R-2: the optional agent-role axis on the tool-gateway engine."""

    def setUp(self) -> None:
        reset_policy_state()
        self.bundle_path = Path(self.id().split(".")[-1] + "-bundle.yaml")

    def tearDown(self) -> None:
        reset_policy_state()
        self.bundle_path.unlink(missing_ok=True)

    def _write_bundle(self, rules: list[dict]) -> GatewaySettings:
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
        # grant (the policy mirror of SPEC-073 toolkit narrowing).
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
