"""Permission-matrix endpoint tests (SPEC-019 R-2).

Validates the live transparency surface: server-side row scoping (full for
platform-admin, own rows otherwise), deny-by-default gating at the route,
bundle provenance reporting, and the full policy semantics (priority,
explicit-deny-wins, disabled rules) inherited through evaluate().
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema
from fastapi.testclient import TestClient

from platform_gateway.app import create_app
from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.schemas.api import IdentityContext, PolicyMatrixResponse
from platform_gateway.services.policy_engine import reset_policy_state

SCHEMAS_DIR = (
    Path(__file__).resolve().parents[3] / "shared" / "shared-contracts" / "schemas"
)

ALL_ROLES = [
    "platform-admin",
    "approver",
    "operator",
    "developer",
    "read-only-observer",
]


def _identity(roles: list[str]) -> IdentityContext:
    return IdentityContext(
        subject=f"user-{roles[0]}",
        username=f"{roles[0]}.user",
        roles=roles,
    )


def _settings(**overrides) -> PlatformGatewaySettings:
    defaults = dict(require_auth=True)
    defaults.update(overrides)
    return PlatformGatewaySettings(**defaults)


class PolicyMatrixBase(unittest.TestCase):
    def setUp(self) -> None:
        reset_policy_state()
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: self._make_settings()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_policy_state()

    def _make_settings(self) -> PlatformGatewaySettings:
        return _settings()

    def _patch_identity(self, roles: list[str]):
        identity = _identity(roles)

        async def fake_identity(settings, request, request_id):
            return identity

        return patch(
            "platform_gateway.api.routes.policy.resolve_request_identity",
            fake_identity,
        )


class PolicyMatrixScopingTests(PolicyMatrixBase):
    def test_admin_receives_full_matrix(self) -> None:
        with self._patch_identity(["platform-admin"]):
            response = self.client.get("/api/v1/policy/matrix")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["scope"], "full")
        # Every role referenced by the bundle gets a row.
        for role in ALL_ROLES + ["auditor"]:
            self.assertIn(role, payload["roles"])
            self.assertIn(role, payload["matrix"])

    def test_operator_receives_only_own_rows(self) -> None:
        with self._patch_identity(["operator"]):
            response = self.client.get("/api/v1/policy/matrix")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["scope"], "own")
        self.assertEqual(payload["roles"], ["operator"])
        self.assertEqual(list(payload["matrix"].keys()), ["operator"])
        # The action catalog is shared across scopes.
        self.assertIn("chat", payload["actions"])
        self.assertIn("policy:read", payload["actions"])

    def test_matrix_cells_match_policy_semantics(self) -> None:
        with self._patch_identity(["platform-admin"]):
            payload = self.client.get("/api/v1/policy/matrix").json()
        matrix = payload["matrix"]
        # Grants from the packaged bundle.
        self.assertTrue(matrix["operator"]["chat"])
        self.assertTrue(matrix["operator"]["incident:triage"])
        self.assertTrue(matrix["read-only-observer"]["tools:list"])
        self.assertTrue(matrix["read-only-observer"]["policy:read"])
        # SPEC-020: chat:confirm is a mutating chat capability — granted to
        # operational roles, observer excluded per the bundle convention.
        self.assertTrue(matrix["operator"]["chat:confirm"])
        self.assertTrue(matrix["approver"]["chat:confirm"])
        self.assertFalse(matrix["read-only-observer"]["chat:confirm"])
        # SPEC-022 R-1: session:list/session:delete mirror session:create —
        # the API scopes both to the caller's own sessions server-side, so
        # every chat-capable role keeps the full lifecycle; auditor holds none.
        for role in ALL_ROLES:
            self.assertTrue(matrix[role]["session:list"], role)
            self.assertTrue(matrix[role]["session:delete"], role)
        self.assertFalse(matrix["auditor"]["session:list"])
        self.assertFalse(matrix["auditor"]["session:delete"])
        # SPEC-021/SPEC-030: tools:mutate answers require_approval for the
        # rule's roles (not immediately allowed: false in the boolean
        # matrix, listed in approval_requirements); observer holds no
        # matching rule and stays a plain deny. developer likewise matches
        # the requirement but is excluded from deciding by authoring.
        self.assertIn("tools:mutate", payload["actions"])
        for role in ["platform-admin", "approver", "operator", "developer"]:
            self.assertFalse(matrix[role]["tools:mutate"], role)
        self.assertFalse(matrix["read-only-observer"]["tools:mutate"])
        requirements = payload["approval_requirements"]
        for role in ["platform-admin", "approver", "operator", "developer"]:
            self.assertEqual(
                requirements[role]["tools:mutate"],
                {
                    "tier": "tier_2",
                    "decided_by_roles": ["approver", "platform-admin"],
                    "rule_id": "require-approval-tools-mutate",
                },
                role,
            )
        self.assertNotIn("read-only-observer", requirements)
        # Deny-by-default and role scoping.
        self.assertFalse(matrix["read-only-observer"]["audit:read"])
        self.assertFalse(matrix["read-only-observer"]["incident:create"])
        self.assertFalse(matrix["operator"]["audit:read"])
        # SPEC-031 R-3: the cross-session inbox exposes other users' parked
        # requests, so approvals:list is granted to the tier_2 decider
        # roles only.
        self.assertIn("approvals:list", payload["actions"])
        self.assertTrue(matrix["approver"]["approvals:list"])
        self.assertTrue(matrix["platform-admin"]["approvals:list"])
        self.assertFalse(matrix["operator"]["approvals:list"])
        self.assertFalse(matrix["developer"]["approvals:list"])
        self.assertFalse(matrix["read-only-observer"]["approvals:list"])
        self.assertFalse(matrix["auditor"]["approvals:list"])
        # SPEC-039 R-2: documents actions are granted to the operational
        # authoring roles only — developer and observer stay read-only on
        # sessions, so they hold neither documents action.
        for action in ("documents:create", "documents:read"):
            self.assertIn(action, payload["actions"])
            for role in ("platform-admin", "approver", "operator"):
                self.assertTrue(matrix[role][action], (role, action))
            self.assertFalse(matrix["developer"][action])
            self.assertFalse(matrix["read-only-observer"][action])
            self.assertFalse(matrix["auditor"][action])
        # SPEC-039 R-7: session rename mirrors session:list grants — every
        # workspace role may rename its own sessions; auditor holds none.
        self.assertIn("session:update", payload["actions"])
        for role in ALL_ROLES:
            self.assertTrue(matrix[role]["session:update"], role)
        self.assertFalse(matrix["auditor"]["session:update"])
        # SPEC-044 R-3: session:skill_draft follows the documents-create
        # grant pattern — the operational authoring roles only; developer,
        # observer, and auditor are denied by default.
        self.assertIn("session:skill_draft", payload["actions"])
        for role in ("platform-admin", "approver", "operator"):
            self.assertTrue(matrix[role]["session:skill_draft"], role)
        self.assertFalse(matrix["developer"]["session:skill_draft"])
        self.assertFalse(matrix["read-only-observer"]["session:skill_draft"])
        self.assertFalse(matrix["auditor"]["session:skill_draft"])
        # SPEC-045 R-3: incident:skill_draft mirrors the session sibling;
        # the route dual-gates with incident:read, so observer/developer
        # incident visibility alone never admits them here.
        self.assertIn("incident:skill_draft", payload["actions"])
        for role in ("platform-admin", "approver", "operator"):
            self.assertTrue(matrix[role]["incident:skill_draft"], role)
        self.assertFalse(matrix["developer"]["incident:skill_draft"])
        self.assertFalse(matrix["read-only-observer"]["incident:skill_draft"])
        self.assertFalse(matrix["auditor"]["incident:skill_draft"])
        # auditor exists in the bundle (audit:read) but holds nothing else.
        self.assertTrue(matrix["auditor"]["audit:read"])
        self.assertFalse(matrix["auditor"]["chat"])

    def test_ungranted_role_denied_by_policy(self) -> None:
        # auditor is not granted policy:read; deny-by-default applies.
        with self._patch_identity(["auditor"]):
            response = self.client.get("/api/v1/policy/matrix")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["action"], "policy:read")

    def test_payload_validates_against_contract(self) -> None:
        with self._patch_identity(["platform-admin"]):
            payload = self.client.get("/api/v1/policy/matrix").json()
        schema = json.loads(
            (SCHEMAS_DIR / "policy-matrix.schema.json").read_text()
        )
        jsonschema.validate(payload, schema)
        PolicyMatrixResponse.model_validate(payload)

    def test_packaged_source_reported(self) -> None:
        with self._patch_identity(["operator"]):
            payload = self.client.get("/api/v1/policy/matrix").json()
        self.assertEqual(payload["source"], "packaged-default")
        self.assertEqual(payload["version"], 1)


CUSTOM_BUNDLE = """
version: 3
rules:
  - id: allow-alpha-chat
    domain: action_authz
    priority: 100
    enabled: true
    match:
      roles_any: ["role-alpha"]
      actions_any: ["chat"]
    decision:
      outcome: allow
  - id: disabled-alpha-audit
    domain: action_authz
    priority: 100
    enabled: false
    match:
      roles_any: ["role-alpha"]
      actions_any: ["audit:read"]
    decision:
      outcome: allow
  - id: allow-alpha-policy-read
    domain: action_authz
    priority: 100
    enabled: true
    match:
      roles_any: ["role-alpha", "platform-admin"]
      actions_any: ["policy:read"]
    decision:
      outcome: allow
  - id: deny-alpha-tools
    domain: action_authz
    priority: 50
    enabled: true
    match:
      roles_any: ["role-alpha"]
      actions_any: ["tools:list"]
    decision:
      outcome: deny
  - id: allow-alpha-tools-low
    domain: action_authz
    priority: 200
    enabled: true
    match:
      roles_any: ["role-alpha"]
      actions_any: ["tools:list"]
    decision:
      outcome: allow
  - id: approve-alpha-tools-mutate
    domain: action_authz
    priority: 100
    enabled: true
    match:
      roles_any: ["role-alpha"]
      actions_any: ["tools:mutate"]
    decision:
      outcome: require_approval
      approval:
        tier: tier_1
        decided_by_roles: ["role-alpha"]
"""


class PolicyMatrixConfiguredBundleTests(PolicyMatrixBase):
    """A configured bundle exercises source reporting and full semantics."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.bundle_path = Path(self._tmp.name) / "policy.yaml"
        self.bundle_path.write_text(CUSTOM_BUNDLE, encoding="utf-8")
        super().setUp()

    def tearDown(self) -> None:
        super().tearDown()
        self._tmp.cleanup()

    def _make_settings(self) -> PlatformGatewaySettings:
        return _settings(policy_path=str(self.bundle_path))

    def test_configured_source_and_version_reported(self) -> None:
        with self._patch_identity(["platform-admin"]):
            payload = self.client.get("/api/v1/policy/matrix").json()
        self.assertEqual(payload["source"], "configured")
        self.assertEqual(payload["version"], 3)

    def test_disabled_rule_and_explicit_deny_semantics(self) -> None:
        with self._patch_identity(["platform-admin"]):
            payload = self.client.get("/api/v1/policy/matrix").json()
        row = payload["matrix"]["role-alpha"]
        self.assertTrue(row["chat"])
        # Disabled allow rule must not grant.
        self.assertFalse(row["audit:read"])
        # Explicit deny wins over the higher-priority allow.
        self.assertFalse(row["tools:list"])
        # Actions absent from the bundle stay denied by default.
        self.assertFalse(row["skills:read"])

    def test_missing_bundle_path_returns_503(self) -> None:
        self.bundle_path.unlink()
        reset_policy_state()
        with self._patch_identity(["platform-admin"]):
            response = self.client.get("/api/v1/policy/matrix")
        self.assertEqual(response.status_code, 503)

    def test_custom_tier1_requirement_renders_third_state(self) -> None:
        with self._patch_identity(["platform-admin"]):
            payload = self.client.get("/api/v1/policy/matrix").json()
        row = payload["matrix"]["role-alpha"]
        # require_approval cells are not immediately allowed.
        self.assertFalse(row["tools:mutate"])
        self.assertEqual(
            payload["approval_requirements"]["role-alpha"]["tools:mutate"],
            {
                "tier": "tier_1",
                "decided_by_roles": ["role-alpha"],
                "rule_id": "approve-alpha-tools-mutate",
            },
        )


class PolicyMatrixApprovalScopeTests(PolicyMatrixBase):
    """SPEC-030 R-5: the third state honors caller-scoped rendering."""

    def test_operator_scope_carries_own_approval_requirement(self) -> None:
        with self._patch_identity(["operator"]):
            payload = self.client.get("/api/v1/policy/matrix").json()
        self.assertEqual(payload["scope"], "own")
        self.assertEqual(payload["roles"], ["operator"])
        self.assertFalse(payload["matrix"]["operator"]["tools:mutate"])
        self.assertEqual(
            payload["approval_requirements"]["operator"]["tools:mutate"]["tier"],
            "tier_2",
        )

    def test_observer_scope_reports_no_approval_requirements(self) -> None:
        with self._patch_identity(["read-only-observer"]):
            payload = self.client.get("/api/v1/policy/matrix").json()
        self.assertEqual(payload["approval_requirements"], {})


if __name__ == "__main__":
    unittest.main()
