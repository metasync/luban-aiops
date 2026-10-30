"""SPEC-070 private delegated execution route tests.

``POST /api/v2/tools/invoke-delegated`` is callable only by the exact
execution-runtime workload identity. Tool-gateway independently re-verifies the
requester and approver human bearers against the signed projection, then applies
the existing invocation/mutation policy using the *approver's* roles — without
ever receiving the execution HMAC signing secret. Human and workload bearers are
never persisted, echoed, or logged.
"""

from __future__ import annotations

import hashlib
import json
import time
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from tool_gateway.app import create_app
from tool_gateway.core.config import GatewaySettings, get_settings
from tool_gateway.schemas.authorization import AuthorizationRequired
from tool_gateway.services import delegated_invoke, token_verifier
from tool_gateway.services.policy_engine import reset_policy_state
from tool_gateway.tools.base import BaseTool, ToolDefinition, ToolResult, build_evidence
from tool_gateway.tools.registry import ToolRegistry

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

ISSUER = "trusted-issuer"
AUDIENCE = "tool-gateway"
WORKLOAD_ISSUER = "https://cluster.issuer"
WORKLOAD_AUDIENCE = "luban-target-execution-handoff"
WORKLOAD_SUBJECT = "system:serviceaccount:execution:execution-runtime"


def _digest(obj) -> str:
    """Independent canonical digest (mirrors the signed projection's args_digest)."""
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class _DelegatedEchoTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="test.echo",
            description="Echoes the delegated identity binding.",
            risk_level="read",
            category="test",
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        return ToolResult(
            tool_name="test.echo",
            status="success",
            data={
                "caller": identity.get("username"),
                "roles": identity.get("roles"),
                "delegated_requester_namespace": identity.get(
                    "delegated_requester_namespace"
                ),
                "delegated_requester_sub": identity.get("delegated_requester_sub"),
                "chat_session_id": identity.get("chat_session_id"),
                "approval_kind": identity.get("approval_kind"),
            },
            evidence=build_evidence("read", "test", 5),
        )


class _DelegatedWriteTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="test.mutate",
            description="Mutating delegated target.",
            risk_level="write",
            category="test",
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        return ToolResult(
            tool_name="test.mutate",
            status="success",
            data={"mutated_by": identity.get("username")},
            evidence=build_evidence("write", "test", 5),
        )


def _registry(*, mutating: bool = False) -> ToolRegistry:
    registry = ToolRegistry(allow_mutating=mutating)
    registry.register(_DelegatedEchoTool())
    if mutating:
        registry.register(_DelegatedWriteTool())
    return registry


def _settings(**overrides) -> GatewaySettings:
    kwargs = dict(
        require_auth=True,
        delegated_invoke_enabled=True,
        delegated_identity_issuer=ISSUER,
        delegated_identity_jwks_url="https://identity.test/jwks",
        delegated_identity_audience=AUDIENCE,
        delegated_identity_actors=("platform-gateway",),
        execution_workload_issuer=WORKLOAD_ISSUER,
        execution_workload_jwks_url="https://cluster.issuer/jwks",
        execution_workload_audience=WORKLOAD_AUDIENCE,
        execution_workload_subjects=(WORKLOAD_SUBJECT,),
    )
    kwargs.update(overrides)
    return GatewaySettings(**kwargs)


def _mint_human(
    sub: str,
    username: str,
    roles: list[str],
    *,
    iss: str = ISSUER,
    aud: str = AUDIENCE,
    authentication_source: str = "oidc",
    act=None,
    exp=None,
    iat=None,
) -> str:
    now = int(time.time())
    claims = {
        "iss": iss,
        "aud": [aud],
        "sub": sub,
        "username": username,
        "roles": roles,
        "groups": [],
        "iat": iat if iat is not None else now - 1,
        "exp": exp if exp is not None else now + 300,
        "authentication_source": authentication_source,
        "act": {"sub": "platform-gateway"} if act is None else act,
    }
    return pyjwt.encode(claims, _KEY, algorithm="RS256")


def _mint_workload(
    *,
    iss: str = WORKLOAD_ISSUER,
    aud: str = WORKLOAD_AUDIENCE,
    sub: str = WORKLOAD_SUBJECT,
    exp=None,
) -> str:
    now = int(time.time())
    claims = {
        "iss": iss,
        "aud": [aud],
        "sub": sub,
        "iat": now - 1,
        "exp": exp if exp is not None else now + 300,
    }
    return pyjwt.encode(claims, _KEY, algorithm="RS256")


def _projection(
    parameters: dict,
    *,
    tool_name: str = "test.echo",
    session_id: str = "sess-1",
    approval_kind: str = "action",
    execution_id: str | None = None,
    requester_sub: str = "alice-immutable",
    requester_namespace: str = ISSUER,
    owner_user_id: str = "alice",
    decider_sub: str = "bob-immutable",
    decider_namespace: str = ISSUER,
    decider_user_id: str = "bob",
) -> dict:
    return {
        "tool_name": tool_name,
        "session_id": session_id,
        "approval_kind": approval_kind,
        "execution_id": execution_id or str(uuid4()),
        "args_digest": _digest(parameters),
        "requester_namespace": requester_namespace,
        "requester_sub": requester_sub,
        "decider_namespace": decider_namespace,
        "decider_sub": decider_sub,
        "owner_user_id": owner_user_id,
        "decider_user_id": decider_user_id,
    }


@contextmanager
def _patch_jwks():
    """Point both human and workload JWKS resolvers at the controlled test key."""
    public_key = _KEY.public_key()
    fake = type(
        "FakeClient",
        (),
        {
            "get_signing_key_from_jwt": lambda _self, _t: type(
                "K", (), {"key": public_key}
            )()
        },
    )()
    with patch.object(delegated_invoke, "_human_jwks_client", return_value=fake), \
            patch.object(delegated_invoke, "_workload_jwks_client", return_value=fake):
        yield


class DelegatedInvokeEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_policy_state()
        delegated_invoke.reset_delegated_state()
        self.parameters = {"msg": "hi"}
        self.requester_token = _mint_human("alice-immutable", "alice", ["operator"])
        self.decider_token = _mint_human("bob-immutable", "bob", ["operator"])
        self.workload_token = _mint_workload()

    def tearDown(self) -> None:
        reset_policy_state()
        delegated_invoke.reset_delegated_state()

    def _client(self, settings: GatewaySettings, *, mutating: bool = False) -> TestClient:
        app = create_app()
        app.state.tool_registry = _registry(mutating=mutating)
        app.dependency_overrides[get_settings] = lambda: settings
        return TestClient(app)

    def _body(self, projection: dict, parameters: dict | None = None) -> dict:
        return {
            "projection": projection,
            "parameters": self.parameters if parameters is None else parameters,
            "requester_token": self.requester_token,
            "decider_token": self.decider_token,
            "request_id": "attempt-1",
        }

    def _post(self, client: TestClient, body: dict, *, bearer: str | None = None):
        headers = {"x-request-id": "attempt-1"}
        if bearer is not None:
            headers["Authorization"] = f"Bearer {bearer}"
        return client.post("/api/v2/tools/invoke-delegated", json=body, headers=headers)

    def test_success_binds_requester_and_uses_decider_identity(self) -> None:
        client = self._client(_settings())
        projection = _projection(self.parameters)
        with _patch_jwks():
            response = self._post(client, self._body(projection), bearer=self.workload_token)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["caller"], "bob")  # the approver drives policy + attribution
        self.assertEqual(data["delegated_requester_namespace"], ISSUER)
        self.assertEqual(data["delegated_requester_sub"], "alice-immutable")
        self.assertEqual(data["chat_session_id"], "sess-1")
        self.assertEqual(data["approval_kind"], "action")
        # No bearer survives into the response.
        for token in (self.requester_token, self.decider_token, self.workload_token):
            self.assertNotIn(token, response.text)

    def test_disabled_route_fails_closed(self) -> None:
        client = self._client(_settings(delegated_invoke_enabled=False))
        projection = _projection(self.parameters)
        with _patch_jwks():
            response = self._post(client, self._body(projection), bearer=self.workload_token)
        self.assertEqual(response.status_code, 403)

    def test_missing_workload_bearer_rejected(self) -> None:
        client = self._client(_settings())
        projection = _projection(self.parameters)
        with _patch_jwks():
            response = self._post(client, self._body(projection), bearer=None)
        self.assertEqual(response.status_code, 401)

    def test_wrong_workload_audience_rejected(self) -> None:
        client = self._client(_settings())
        projection = _projection(self.parameters)
        bad = _mint_workload(aud="tool-gateway")
        with _patch_jwks():
            response = self._post(client, self._body(projection), bearer=bad)
        self.assertEqual(response.status_code, 401)

    def test_unregistered_workload_subject_rejected(self) -> None:
        client = self._client(_settings())
        projection = _projection(self.parameters)
        bad = _mint_workload(sub="system:serviceaccount:other:service")
        with _patch_jwks():
            response = self._post(client, self._body(projection), bearer=bad)
        self.assertEqual(response.status_code, 401)

    def test_requester_bearer_must_match_projection(self) -> None:
        client = self._client(_settings())
        projection = _projection(self.parameters)
        body = self._body(projection)
        body["requester_token"] = _mint_human("mallory-immutable", "alice", ["operator"])
        with _patch_jwks():
            response = self._post(client, body, bearer=self.workload_token)
        self.assertEqual(response.status_code, 403)

    def test_decider_development_provenance_rejected(self) -> None:
        client = self._client(_settings())
        projection = _projection(self.parameters)
        body = self._body(projection)
        body["decider_token"] = _mint_human(
            "bob-immutable", "bob", ["operator"], authentication_source="development"
        )
        with _patch_jwks():
            response = self._post(client, body, bearer=self.workload_token)
        self.assertEqual(response.status_code, 403)

    def test_expired_human_token_rejected(self) -> None:
        client = self._client(_settings())
        projection = _projection(self.parameters)
        body = self._body(projection)
        body["decider_token"] = _mint_human(
            "bob-immutable", "bob", ["operator"], iat=100, exp=200
        )
        with _patch_jwks():
            response = self._post(client, body, bearer=self.workload_token)
        self.assertEqual(response.status_code, 403)

    def test_args_digest_mismatch_rejected(self) -> None:
        client = self._client(_settings())
        projection = _projection(self.parameters)
        # The signed digest covers {"msg": "hi"}; send tampered parameters.
        body = self._body(projection, parameters={"msg": "hi", "extra": "injected"})
        with _patch_jwks():
            response = self._post(client, body, bearer=self.workload_token)
        self.assertEqual(response.status_code, 400)

    def test_missing_projection_identity_fields_rejected(self) -> None:
        client = self._client(_settings())
        projection = _projection(self.parameters)
        del projection["requester_sub"]
        with _patch_jwks():
            response = self._post(client, self._body(projection), bearer=self.workload_token)
        self.assertEqual(response.status_code, 400)

    def test_policy_uses_decider_roles_and_denies_mutation(self) -> None:
        client = self._client(_settings(), mutating=True)
        body = self._body(_projection(self.parameters, tool_name="test.mutate"))
        # The approver is a read-only observer: mutation must be denied by policy.
        body["decider_token"] = _mint_human(
            "bob-immutable", "bob", ["read-only-observer"]
        )
        with _patch_jwks():
            response = self._post(client, body, bearer=self.workload_token)
        self.assertEqual(response.status_code, 403)

    def test_bearers_never_logged_or_audited(self) -> None:
        client = self._client(_settings())
        projection = _projection(self.parameters)
        with _patch_jwks(), \
                patch("tool_gateway.services.gateway_service.emit_audit_event") as emit, \
                patch("tool_gateway.services.gateway_service.LOGGER") as logger:
            response = self._post(client, self._body(projection), bearer=self.workload_token)
        self.assertEqual(response.status_code, 200)
        sink = str(emit.call_args_list) + str(logger.info.call_args_list) + \
            str(logger.warning.call_args_list)
        for token in (self.requester_token, self.decider_token, self.workload_token):
            self.assertNotIn(token, sink)


class DelegatedInvokeConfigurationTests(unittest.TestCase):
    """Enabling the private route without full trust sets must fail closed."""

    def test_disabled_by_default(self) -> None:
        self.assertFalse(GatewaySettings().delegated_invoke_enabled)
        self.assertEqual(
            GatewaySettings().execution_workload_audience, WORKLOAD_AUDIENCE
        )

    def test_enabled_without_trust_sets_raises(self) -> None:
        with self.assertRaises(ValueError):
            GatewaySettings(delegated_invoke_enabled=True)

    def test_enabled_without_workload_subjects_raises(self) -> None:
        with self.assertRaises(ValueError):
            _settings(execution_workload_subjects=())

    def test_enabled_without_human_actors_raises(self) -> None:
        with self.assertRaises(ValueError):
            _settings(delegated_identity_actors=())

    def test_enabled_with_full_trust_sets_constructs(self) -> None:
        settings = _settings()
        self.assertTrue(settings.delegated_invoke_enabled)
        self.assertEqual(settings.execution_workload_subjects, (WORKLOAD_SUBJECT,))


def _read_settings(**overrides) -> GatewaySettings:
    """Acquisition runtime + delegated-human trust + portal trust pinned together.

    The portal verifier (``verify_token``) and the delegated-human bar
    (``decode_delegated_human_claims``) are pointed at the SAME issuer/audience so
    one genuine human bearer satisfies both: policy rides the portal verification
    while the requester is derived from the independent delegated-human proof.
    """
    kwargs = dict(
        require_auth=True,
        identity_token_issuer=ISSUER,
        token_audience=AUDIENCE,
        delegated_acquisition_enabled=True,
        delegated_custody_db_url="postgresql://gateway@db.internal:5432/gateway",
        delegated_custody_keyring_path="/etc/tool-gateway/delegated-keyring.json",
        delegated_custody_config_path="/etc/tool-gateway/delegated.json",
        delegated_custody_set_id="ansible-prod",
        delegated_custody_trusted_callback=(
            "https://gw.internal/api/v1/targets/authorizations/callback"
        ),
        delegated_identity_issuer=ISSUER,
        delegated_identity_jwks_url="https://identity.test/jwks",
        delegated_identity_audience=AUDIENCE,
        delegated_identity_actors=("platform-gateway",),
    )
    kwargs.update(overrides)
    return GatewaySettings(**kwargs)


@contextmanager
def _patch_read_jwks():
    """Point BOTH the portal verifier and the delegated-human resolver at _KEY."""
    public_key = _KEY.public_key()
    fake = type(
        "FakeClient",
        (),
        {"get_signing_key_from_jwt": lambda _self, _t: type("K", (), {"key": public_key})()},
    )()
    with patch.object(token_verifier, "_get_jwks_client", return_value=fake), \
            patch.object(delegated_invoke, "_human_jwks_client", return_value=fake):
        yield


class DelegatedReadRequesterTests(unittest.TestCase):
    """SPEC-070 R-2a: reads thread a DIRECTLY verified requester (plan line 66).

    A read invocation re-verifies its presentation bearer against the
    delegated-human trust bar and threads the pinned ``(issuer, sub)`` as the
    inert acquisition-seam binding. A caller can never assert a requester; a
    bearer that is not a genuine delegated human threads none, so a delegated
    credential set then fails closed at the connector rather than acquiring under
    an unverified owner.
    """

    def setUp(self) -> None:
        reset_policy_state()
        token_verifier.reset_verifier_state()
        delegated_invoke.reset_delegated_state()

    def tearDown(self) -> None:
        reset_policy_state()
        token_verifier.reset_verifier_state()
        delegated_invoke.reset_delegated_state()

    def _client(self, settings: GatewaySettings) -> TestClient:
        app = create_app()
        app.state.tool_registry = _registry()
        app.dependency_overrides[get_settings] = lambda: settings
        return TestClient(app)

    def _invoke(self, client: TestClient, token: str):
        return client.post(
            "/api/v2/tools/invoke",
            json={"tool_name": "test.echo", "parameters": {"msg": "hi"}, "request_id": "req-read"},
            headers={"Authorization": f"Bearer {token}", "x-request-id": "req-read"},
        )

    def test_read_threads_directly_verified_requester(self) -> None:
        client = self._client(_read_settings())
        token = _mint_human("alice-immutable", "alice", ["operator"])
        with _patch_read_jwks():
            response = self._invoke(client, token)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["delegated_requester_namespace"], ISSUER)
        self.assertEqual(data["delegated_requester_sub"], "alice-immutable")
        # The bearer never survives into the response.
        self.assertNotIn(token, response.text)

    def test_read_without_delegated_provenance_threads_no_requester(self) -> None:
        # A portal-valid token that is NOT a genuine delegated human (development
        # provenance) still passes policy, but threads no requester.
        client = self._client(_read_settings())
        token = _mint_human(
            "alice-immutable", "alice", ["operator"], authentication_source="development"
        )
        with _patch_read_jwks():
            response = self._invoke(client, token)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertIsNone(data["delegated_requester_namespace"])
        self.assertIsNone(data["delegated_requester_sub"])

    def test_read_with_acquisition_disabled_threads_no_requester(self) -> None:
        client = self._client(_read_settings(delegated_acquisition_enabled=False))
        token = _mint_human("alice-immutable", "alice", ["operator"])
        with _patch_read_jwks():
            response = self._invoke(client, token)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["data"]["delegated_requester_namespace"])

    def test_read_without_identity_trust_set_threads_no_requester(self) -> None:
        # Acquisition on but the delegated-human trust set unprovisioned: fail
        # closed rather than verify against an empty issuer.
        client = self._client(_read_settings(delegated_identity_issuer=""))
        token = _mint_human("alice-immutable", "alice", ["operator"])
        with _patch_read_jwks():
            response = self._invoke(client, token)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["data"]["delegated_requester_namespace"])


class _ReauthDenyTool(BaseTool):
    """Returns the transitional delegated re-authorization denial (read tier)."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="test.reauth", description="Denies pending re-authorization.",
            risk_level="read", category="test",
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        return ToolResult(
            tool_name="test.reauth", status="denied",
            evidence=build_evidence("read", "test", 5),
            error={"code": "DELEGATED_REAUTHORIZATION_REQUIRED", "message": "reauth needed"},
        )


class _FakeProducer:
    """Stands in for ``AuthorizationService.produce_challenge``."""

    def __init__(self, *, challenge=None) -> None:
        self._challenge = challenge
        self.calls: list[dict] = []

    async def produce_challenge(self, **kwargs):
        self.calls.append(kwargs)
        return self._challenge


def _challenge(target: str = "Automation") -> AuthorizationRequired:
    return AuthorizationRequired(
        challenge_id=str(uuid4()), target=target,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=600),
    )


class DelegatedReadChallengeProducerTests(unittest.TestCase):
    """SPEC-070 producer wiring: a verified read-path ``authorization_required``
    denial becomes a durable challenge plus the reserved ``TARGET_AUTHORIZATION_REQUIRED``
    result the kernel promotes. The producer fires only when the authorization
    runtime is wired AND the invocation carries the verified owner and the
    session/call correlation; any gap leaves the original denial untouched.
    """

    def setUp(self) -> None:
        reset_policy_state()
        token_verifier.reset_verifier_state()
        delegated_invoke.reset_delegated_state()

    def tearDown(self) -> None:
        reset_policy_state()
        token_verifier.reset_verifier_state()
        delegated_invoke.reset_delegated_state()

    def _client(self, settings: GatewaySettings, producer) -> TestClient:
        app = create_app()
        registry = ToolRegistry()
        registry.register(_ReauthDenyTool())
        app.state.tool_registry = registry
        if producer is not None:
            app.state.authorization_service = producer
        app.dependency_overrides[get_settings] = lambda: settings
        return TestClient(app)

    def _post(self, client: TestClient, token: str, body: dict):
        return client.post(
            "/api/v2/tools/invoke", json=body,
            headers={"Authorization": f"Bearer {token}", "x-request-id": body.get("request_id", "r")},
        )

    def test_authorization_required_produces_challenge_result(self) -> None:
        challenge = _challenge()
        producer = _FakeProducer(challenge=challenge)
        client = self._client(_read_settings(), producer)
        token = _mint_human("alice-immutable", "alice", ["operator"])
        body = {"tool_name": "test.reauth", "parameters": {}, "request_id": "req-chal",
                "session_id": "ses-1", "call_id": "tool_call_01AA"}
        with _patch_read_jwks():
            response = self._post(client, token, body)
        self.assertEqual(response.status_code, 400)
        result = response.json()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "TARGET_AUTHORIZATION_REQUIRED")
        self.assertEqual(result["authorization_required"]["challenge_id"], challenge.challenge_id)
        self.assertEqual(result["authorization_required"]["target"], "Automation")
        # The producer received the verified owner and the exact correlation.
        self.assertEqual(producer.calls, [dict(
            owner_namespace=ISSUER, owner_sub="alice-immutable",
            session_id="ses-1", call_id="tool_call_01AA")])

    def test_no_producer_leaves_denial_untouched(self) -> None:
        client = self._client(_read_settings(), None)
        token = _mint_human("alice-immutable", "alice", ["operator"])
        body = {"tool_name": "test.reauth", "parameters": {}, "request_id": "req-nop",
                "session_id": "ses-1", "call_id": "tool_call_01AA"}
        with _patch_read_jwks():
            response = self._post(client, token, body)
        self.assertEqual(response.status_code, 403)
        result = response.json()
        self.assertEqual(result["status"], "denied")
        self.assertEqual(result["error"]["code"], "DELEGATED_REAUTHORIZATION_REQUIRED")
        self.assertNotIn("authorization_required", result)

    def test_producer_returning_none_leaves_denial_untouched(self) -> None:
        producer = _FakeProducer(challenge=None)
        client = self._client(_read_settings(), producer)
        token = _mint_human("alice-immutable", "alice", ["operator"])
        body = {"tool_name": "test.reauth", "parameters": {}, "request_id": "req-none",
                "session_id": "ses-1", "call_id": "tool_call_01AA"}
        with _patch_read_jwks():
            response = self._post(client, token, body)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "DELEGATED_REAUTHORIZATION_REQUIRED")
        self.assertEqual(len(producer.calls), 1)

    def test_missing_call_id_does_not_produce(self) -> None:
        # No in-flight call id to bind a challenge to: the producer is not called
        # and the denial stands (a challenge must bind to the exact call).
        producer = _FakeProducer(challenge=_challenge())
        client = self._client(_read_settings(), producer)
        token = _mint_human("alice-immutable", "alice", ["operator"])
        body = {"tool_name": "test.reauth", "parameters": {}, "request_id": "req-nocall",
                "session_id": "ses-1"}
        with _patch_read_jwks():
            response = self._post(client, token, body)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "DELEGATED_REAUTHORIZATION_REQUIRED")
        self.assertEqual(producer.calls, [])


if __name__ == "__main__":
    unittest.main()
