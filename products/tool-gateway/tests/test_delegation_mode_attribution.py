"""SPEC-070 R-4a/R-4c — top-level ``delegation_mode`` attribution.

Failure-first. The emitted ``tool_invoked`` audit event must carry a TOP-LEVEL
``delegation_mode`` derived from the *verified acquisition outcome* at the shared
``resolve_outbound_auth`` seam — never the static ``target_identity_mode`` config
label (which stays in ``details``), and never a fabricated success standing in for
a failed acquisition:

* ``user_delegated`` only after a verified user-delegated grant is acquired;
* ``acting_service`` for an actual machine credential (basic / bearer /
  client-credentials);
* ``none`` when an acquisition was attempted but failed (authorization failure is
  not delegated success);
* omitted entirely for a tool that never touches the seam, so unrelated legacy
  events stay byte-identical.

The mode is captured before payload redaction, so a REDACTION_OVERFLOW result
replacement preserves it. Derivation is a per-task ``ContextVar`` at the single
acquisition seam, never an attribute on a reusable connector singleton, so
concurrent invocations cannot cross-contaminate.
"""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import jsonschema
from pydantic import SecretStr

from tool_gateway.core.config import GatewaySettings
from tool_gateway.schemas.api import IdentityContext
from tool_gateway.services.delegated_custody import CredentialMetadata
from tool_gateway.services.gateway_service import _dispatch_invocation
from tool_gateway.services.policy_engine import reset_policy_state
from tool_gateway.tools.auth_resolution import DELEGATION_MODE, resolve_outbound_auth
from tool_gateway.tools.base import (
    BaseTool,
    ToolDefinition,
    ToolResult,
    build_evidence,
)
from tool_gateway.tools.http_connector import HttpConnector
from tool_gateway.tools.registry import ToolRegistry
from tool_gateway.tools.user_delegated_client import (
    DelegatedAccessToken,
    DelegatedAcquisitionError,
)

# The same secret-shaped JWT test_redaction uses to drive a redaction overflow.
_JWT = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJzZXJ2aWNlLWFjY291bnQifQ.sig-value-12345678"
RESOURCE = "https://resource.test"
_IDENTITY = IdentityContext(
    subject="user-carol", username="carol.ops", roles=["operator"], actor="agent-platform",
)

# SPEC-070 plan line 156 end-to-end link: the shared audit-event contract is the
# single boundary the audit-service ingestion model is bound to, so validating the
# REAL gateway-emitted envelope against it proves what the gateway emits is exactly
# what audit ingests, persists, and queries — including an overflow/signed-path
# attribution event whose top-level mode must survive a REDACTION_OVERFLOW result.
SCHEMAS_DIR = Path(__file__).resolve().parents[3] / "shared" / "shared-contracts" / "schemas"


def _assert_ingestible(event: dict) -> None:
    jsonschema.validate(event, json.loads((SCHEMAS_DIR / "audit-event.schema.json").read_text()))


def _run(coro):
    return asyncio.run(coro)


class _CountingMachineClient:
    """A machine-grant client that returns a token (and counts) — never fails."""

    def __init__(self) -> None:
        self.acquire_calls = 0

    async def acquire(self, name, entry):
        self.acquire_calls += 1
        return "machine-grant-token", None


class _StubDelegatedClient:
    """Stands in for :class:`UserDelegatedClient` at the acquisition seam."""

    def __init__(self, token="delegated-at", exc=None) -> None:
        self._token = token
        self._exc = exc

    async def access_token_for_send(self, ctx):
        if self._exc is not None:
            raise self._exc
        return DelegatedAccessToken(
            token=SecretStr(self._token),
            expires_at=9_999_999_999.0,
            metadata=CredentialMetadata("gen1", 1, "42", "read"),
        )

    async def invalidate_grant(self, ctx):  # pragma: no cover - unused here
        pass


class _Router:
    def __init__(self, routes: dict) -> None:
        self.routes = routes
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        entry = self.routes.get((request.method, request.url.path))
        if entry is None:
            return httpx.Response(404, json={"error": "no route"})
        return entry


def _delegated_entry(resource_origins=RESOURCE):
    return {
        "scheme": "oauth2_authorization_code",
        "target": "https://issuer.test",
        "authorization_url": "https://idp.test/authorize",
        "token_url": "https://idp.test/token",
        "renewal_url": "https://idp.test/token",
        "client_id": "client-1",
        "client_secret": "secret-1",
        "client_auth": "client_secret_basic",
        "redirect_uri": "https://gateway.test/api/v1/targets/authorizations/callback",
        "scope": "read",
        "allowed_scopes": "read write",
        "oauth_origins": "https://idp.test",
        "resource_origins": resource_origins,
        "pkce_method": "S256",
        "store": "postgres",
        "config_revision": "1",
        "identity_profile": "json_immutable_id",
        "identity_claim": "sub",
        "identity_mapping_path": "/etc/tool-gateway/identity.json",
        "identity_url": "https://idp.test/whoami",
        "access_cache_ttl_seconds": "300",
        "refresh_max_lifetime_seconds": "2592000",
    }


def _http_connector(router, sets, *, delegated_client=None):
    tmp = Path(tempfile.mkdtemp()) / "sets.json"
    tmp.write_text(json.dumps(sets), encoding="utf-8")
    return HttpConnector(
        allow_origins=(RESOURCE,),
        transport=httpx.MockTransport(router),
        credential_sets_path=tmp,
        delegated_client=delegated_client or _StubDelegatedClient(),
        token_client=_CountingMachineClient(),
    )


def _dispatch_captured(registry, tool_name, parameters, *,
                       delegated_requester=None, settings=None):
    """Drive the real audit choke point and capture the emitted event."""
    reset_policy_state()
    with patch("tool_gateway.services.gateway_service.emit_audit_event") as emit:
        response = _run(_dispatch_invocation(
            settings or GatewaySettings(), registry, _IDENTITY, tool_name, parameters,
            None, None, {}, "req-1", delegated_requester=delegated_requester,
        ))
    event = emit.call_args.args[1] if emit.call_args else None
    return response, event


async def _resolve_and_read(**kwargs):
    """Call the seam and read the derived mode within the SAME task context.

    ``asyncio.run`` copies the current context, so a ``ContextVar`` set inside a
    bare ``resolve_outbound_auth`` call would not be visible to the caller. The
    gateway reads it inside the same request task; this helper reproduces that
    co-location so the derivation is asserted exactly where it is consumed.
    """
    token = DELEGATION_MODE.set(None)
    try:
        resolved, err = await resolve_outbound_auth(**kwargs)
        return resolved, err, DELEGATION_MODE.get()
    finally:
        DELEGATION_MODE.reset(token)


class _PlainTool(BaseTool):
    """A read tool that never touches the acquisition seam."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="test.plain", description="No credential.", risk_level="read",
            category="test",
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        return ToolResult(
            tool_name="test.plain", status="success", data={"ok": True},
            evidence=build_evidence("read", "platform", 1),
        )


class _LeakyBasicTool(BaseTool):
    """Resolves a machine credential (acting_service) then overflows redaction.

    Proves the derived mode is captured before the REDACTION_OVERFLOW envelope
    replaces the result — the mode rides a ContextVar, not ``result``.
    """

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="test.leaky_basic", description="Leaks.", risk_level="read",
            category="test",
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        await resolve_outbound_auth(
            set_name="svc",
            entry={"scheme": "basic", "username": "svc", "password": "pw"},
            token_client=_CountingMachineClient(),
        )
        return ToolResult(
            tool_name="test.leaky_basic", status="success",
            data={"logs": [_JWT * 4]},
            evidence=build_evidence("read", "ansible", 1),
        )


class DelegationModeDerivationTests(unittest.TestCase):
    """The seam derives the mode from the verified acquisition outcome."""

    def test_verified_delegated_grant_is_user_delegated(self) -> None:
        _, err, mode = _run(_resolve_and_read(
            set_name="delegated", entry={"scheme": "oauth2_authorization_code"},
            token_client=_CountingMachineClient(),
            delegated_client=_StubDelegatedClient(), acquisition=object(),
        ))
        self.assertIsNone(err)
        self.assertEqual(mode, "user_delegated")

    def test_basic_credential_is_acting_service(self) -> None:
        _, err, mode = _run(_resolve_and_read(
            set_name="svc", entry={"scheme": "basic", "username": "svc", "password": "pw"},
            token_client=_CountingMachineClient(),
        ))
        self.assertIsNone(err)
        self.assertEqual(mode, "acting_service")

    def test_bearer_credential_is_acting_service(self) -> None:
        _, err, mode = _run(_resolve_and_read(
            set_name="svc", entry={"scheme": "bearer", "token": "tok"},
            token_client=_CountingMachineClient(),
        ))
        self.assertIsNone(err)
        self.assertEqual(mode, "acting_service")

    def test_client_credentials_is_acting_service(self) -> None:
        _, err, mode = _run(_resolve_and_read(
            set_name="svc", entry={"scheme": "oauth2_client_credentials"},
            token_client=_CountingMachineClient(),
        ))
        self.assertIsNone(err)
        self.assertEqual(mode, "acting_service")

    def test_delegated_authorization_required_is_none_not_success(self) -> None:
        _, err, mode = _run(_resolve_and_read(
            set_name="delegated", entry={"scheme": "oauth2_authorization_code"},
            token_client=_CountingMachineClient(),
            delegated_client=_StubDelegatedClient(
                exc=DelegatedAcquisitionError("authorization_required", "no grant")
            ),
            acquisition=object(),
        ))
        self.assertIsNotNone(err)
        self.assertEqual(mode, "none")

    def test_delegated_not_enabled_is_none(self) -> None:
        _, err, mode = _run(_resolve_and_read(
            set_name="delegated", entry={"scheme": "oauth2_authorization_code"},
            token_client=_CountingMachineClient(),
        ))
        self.assertIsNotNone(err)
        self.assertEqual(mode, "none")

    def test_basic_missing_password_is_none(self) -> None:
        _, err, mode = _run(_resolve_and_read(
            set_name="svc", entry={"scheme": "basic", "username": "svc"},
            token_client=_CountingMachineClient(),
        ))
        self.assertIsNotNone(err)
        self.assertEqual(mode, "none")


class DelegationModeEmissionTests(unittest.TestCase):
    """The gateway emits the derived mode as a TOP-LEVEL audit field."""

    def test_delegated_invoke_emits_top_level_user_delegated(self) -> None:
        router = _Router({("GET", "/api"): httpx.Response(200, json={"ok": True})})
        connector = _http_connector(router, {"delegated": _delegated_entry()})
        registry = ToolRegistry()
        connector.register_tools(registry)
        response, event = _dispatch_captured(
            registry, "http.get",
            {"url": f"{RESOURCE}/api", "credential_set": "delegated"},
            delegated_requester=("issuer", "alice"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(event["event_type"], "tool_invoked")
        self.assertEqual(event["delegation_mode"], "user_delegated")
        # The top-level mode is a runtime fact, not the static config label.
        self.assertNotIn("delegation_mode", event["details"])
        _assert_ingestible(event)

    def test_machine_credential_emits_top_level_acting_service(self) -> None:
        router = _Router({("GET", "/api"): httpx.Response(200, json={"ok": True})})
        connector = _http_connector(
            router, {"svc": {"scheme": "basic", "username": "svc", "password": "pw"}}
        )
        registry = ToolRegistry()
        connector.register_tools(registry)
        response, event = _dispatch_captured(
            registry, "http.get", {"url": f"{RESOURCE}/api", "credential_set": "svc"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(event["delegation_mode"], "acting_service")
        _assert_ingestible(event)

    def test_failed_delegated_acquisition_emits_none(self) -> None:
        router = _Router({("GET", "/api"): httpx.Response(200, json={"ok": True})})
        connector = _http_connector(
            router, {"delegated": _delegated_entry()},
            delegated_client=_StubDelegatedClient(
                exc=DelegatedAcquisitionError("authorization_required", "no grant")
            ),
        )
        registry = ToolRegistry()
        connector.register_tools(registry)
        response, event = _dispatch_captured(
            registry, "http.get",
            {"url": f"{RESOURCE}/api", "credential_set": "delegated"},
            delegated_requester=("issuer", "alice"),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(event["outcome"], "error")
        self.assertEqual(event["delegation_mode"], "none")
        _assert_ingestible(event)

    def test_no_credential_tool_omits_delegation_mode(self) -> None:
        registry = ToolRegistry()
        registry.register(_PlainTool())
        response, event = _dispatch_captured(registry, "test.plain", {})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("delegation_mode", event)
        _assert_ingestible(event)

    def test_redaction_overflow_preserves_delegation_mode(self) -> None:
        registry = ToolRegistry()
        registry.register(_LeakyBasicTool())
        response, event = _dispatch_captured(registry, "test.leaky_basic", {})
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.body)
        self.assertEqual(body["error"]["code"], "REDACTION_OVERFLOW")
        self.assertEqual(event["delegation_mode"], "acting_service")
        _assert_ingestible(event)


if __name__ == "__main__":
    unittest.main()
