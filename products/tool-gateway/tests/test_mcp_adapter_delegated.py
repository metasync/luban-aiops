"""SPEC-070 acquisition — MCP adapter enforcement for delegated sets.

The MCP ingestion adapter already resolves a credential set into a bearer
through the SPEC-068 seam and opens a single-shot session. These tests drive the
*delegated* branch through the real connector (only the session opener is faked)
and prove the plan's §"HTTP and MCP enforcement" MCP clauses:

* delegated MCP uses only the bearer-capable streamable-HTTP transport; a stdio
  transport is refused **before** any subprocess/session is created;
* the verified requester context is threaded into invocation and diagnostics, and
  the acquired user-delegated bearer — never a machine grant — rides the session;
* a diagnostic with no verified user reports configuration but opens **no**
  authenticated target connection;
* every delegated failure opens no session and calls zero machine-grant fallbacks.
"""

import asyncio
import json
import tempfile
import types
import unittest
from contextlib import asynccontextmanager
from pathlib import Path

from pydantic import SecretStr

from tool_gateway.ingestion.mcp_adapter import (
    AdmittedTool,
    McpIngestionConnector,
    McpTransport,
)
from tool_gateway.services.delegated_custody import CredentialMetadata
from tool_gateway.tools.registry import ToolRegistry
from tool_gateway.tools.user_delegated_client import (
    DelegatedAccessToken,
    DelegatedAcquisitionError,
)

IDENTITY = {
    "subject": "carol",
    "actor": "carol",
    "delegated_requester_namespace": "issuer",
    "delegated_requester_sub": "alice",
}

ADMITTED = (
    AdmittedTool(
        server_name="list_inventories",
        name="ansible.list_inventories",
        description="List inventories.",
        risk_level="read",
        category="ansible",
        parameters_schema={"type": "object", "properties": {}},
    ),
)


def _run(coro):
    return asyncio.run(coro)


def _delegated_entry():
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
        "resource_origins": "https://resource.test",
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


class _StubDelegatedClient:
    def __init__(self, token="delegated-at", exc=None):
        self._token = token
        self._exc = exc
        self.acquire_calls = []
        self.invalidate_calls = []

    async def access_token_for_send(self, ctx):
        self.acquire_calls.append(ctx)
        if self._exc is not None:
            raise self._exc
        return DelegatedAccessToken(
            token=SecretStr(self._token),
            expires_at=9_999_999_999.0,
            metadata=CredentialMetadata("gen1", 1, "42", "read"),
        )

    async def invalidate_grant(self, ctx):
        self.invalidate_calls.append(ctx)


class _FailingTokenClient:
    async def acquire(self, name, entry):
        raise AssertionError(
            "machine-grant token client must never be used for a delegated set"
        )


class _FakeSession:
    def __init__(self, server):
        self._server = server

    async def call_tool(self, name, arguments):
        self._server.calls.append((name, arguments))
        return types.SimpleNamespace(
            is_error=False, content=[], structured_content={"ok": True, "tool": name}
        )

    async def list_tools(self):
        self._server.discoveries += 1
        return types.SimpleNamespace(
            tools=[types.SimpleNamespace(name=n) for n in self._server.tools]
        )


class _FakeServer:
    def __init__(self, tools=("list_inventories",)):
        self.tools = list(tools)
        self.calls = []
        self.bearers = []
        self.discoveries = 0

    def opener(self):
        server = self

        @asynccontextmanager
        async def _open(transport, bearer):
            server.bearers.append(bearer)
            yield _FakeSession(server)

        return _open


@asynccontextmanager
async def _must_not_open(transport, bearer):
    raise AssertionError("a refused delegated path must never open a session")
    yield  # pragma: no cover


def _connector(server, *, delegated_client=None, transport=None, opener=None):
    tmp = Path(tempfile.mkdtemp()) / "sets.json"
    tmp.write_text(json.dumps({"delegated": _delegated_entry()}), encoding="utf-8")
    return McpIngestionConnector(
        transport=transport or McpTransport(kind="streamable_http", url="http://awx-mcp.local/mcp"),
        admitted=ADMITTED,
        source_system="ansible",
        credential_set="delegated",
        credential_sets_path=str(tmp),
        delegated_client=delegated_client if delegated_client is not None else _StubDelegatedClient(),
        token_client=_FailingTokenClient(),
        session_opener=opener or server.opener(),
    )


def _invoke(connector, identity=None):
    registry = ToolRegistry()
    connector.register_tools(registry)
    return _run(
        registry.invoke(
            "ansible.list_inventories", {},
            identity if identity is not None else dict(IDENTITY),
        )
    )


class DelegatedMcpInvocationTests(unittest.TestCase):
    def test_acquired_bearer_rides_the_session_and_machine_grant_untouched(self):
        server = _FakeServer()
        stub = _StubDelegatedClient(token="delegated-at")
        result = _invoke(_connector(server, delegated_client=stub))
        self.assertEqual(result.status, "success")
        self.assertEqual(server.bearers, ["delegated-at"])
        ctx = stub.acquire_calls[0]
        self.assertEqual((ctx.owner_namespace, ctx.owner_sub), ("issuer", "alice"))
        self.assertEqual(ctx.set_name, "delegated")

    def test_stdio_transport_refused_before_any_subprocess_or_session(self):
        server = _FakeServer()
        stub = _StubDelegatedClient()
        connector = _connector(
            server, delegated_client=stub,
            transport=McpTransport(kind="stdio", command="must-not-run"),
            opener=_must_not_open,
        )
        result = _invoke(connector)
        self.assertEqual(result.error["code"], "DELEGATED_TRANSPORT_UNSUPPORTED")
        self.assertEqual(stub.acquire_calls, [])  # refused before acquisition
        self.assertEqual(server.bearers, [])

    def test_invocation_without_requester_context_fails_closed(self):
        server = _FakeServer()
        stub = _StubDelegatedClient()
        result = _invoke(_connector(server, delegated_client=stub), identity={"subject": "carol"})
        self.assertEqual(result.error["code"], "DELEGATED_CONTEXT_REQUIRED")
        self.assertEqual(stub.acquire_calls, [])
        self.assertEqual(server.bearers, [])  # no session opened

    def test_acquisition_failure_opens_no_session_and_no_fallback(self):
        server = _FakeServer()
        stub = _StubDelegatedClient(exc=DelegatedAcquisitionError("authorization_required", "no grant"))
        result = _invoke(_connector(server, delegated_client=stub))
        self.assertEqual(result.error["code"], "DELEGATED_REAUTHORIZATION_REQUIRED")
        # SPEC-070: the delegated re-authorization denial keeps its ``denied``
        # posture (never flattened to a terminal ``error``) so the producer seam
        # can promote it to a durable authorization challenge exactly as the HTTP
        # connector does — otherwise an MCP target's delegated read is stranded
        # with no enrollment path.
        self.assertEqual(result.status, "denied")
        self.assertEqual(server.bearers, [])  # no session opened


class DelegatedMcpDiagnosticTests(unittest.TestCase):
    def test_diagnostic_without_user_opens_no_authenticated_connection(self):
        server = _FakeServer()
        stub = _StubDelegatedClient()
        connector = _connector(server, delegated_client=stub)
        names, err = _run(connector.list_server_tools())
        self.assertIsNone(names)
        self.assertEqual(err[0], "DELEGATED_DIAGNOSTIC_NO_USER")
        self.assertEqual(err[2], "denied")
        self.assertEqual(server.discoveries, 0)
        self.assertEqual(server.bearers, [])
        self.assertEqual(stub.acquire_calls, [])

    def test_diagnostic_with_verified_user_may_connect(self):
        server = _FakeServer(tools=("list_inventories", "get_job"))
        stub = _StubDelegatedClient()
        connector = _connector(server, delegated_client=stub)
        names, err = _run(connector.list_server_tools(dict(IDENTITY)))
        self.assertIsNone(err)
        self.assertEqual(names, ["list_inventories", "get_job"])
        self.assertEqual(server.discoveries, 1)
        self.assertEqual(server.bearers, ["delegated-at"])


class _CountingMachineClient:
    def __init__(self):
        self.acquire_calls = 0

    async def acquire(self, name, entry):
        self.acquire_calls += 1
        return "machine-grant-token", None


class ZeroFallbackCounterTests(unittest.TestCase):
    """Plan §"HTTP and MCP enforcement": on a delegated failure, counters prove
    zero calls to Basic, static-bearer, machine-grant, unauthenticated, and
    alternate-transport fallback paths. (The alternate-transport/stdio refusal is
    counted by ``test_stdio_transport_refused_before_any_subprocess_or_session``
    above via ``_must_not_open``.)"""

    def test_delegated_failure_opens_no_session_and_no_fallback(self):
        server = _FakeServer()
        machine = _CountingMachineClient()
        stub = _StubDelegatedClient(exc=DelegatedAcquisitionError("authorization_required", "no grant"))
        tmp = Path(tempfile.mkdtemp()) / "sets.json"
        # A basic and a static-bearer set sit beside the delegated one; the empty
        # session log proves neither was reached as a fallback.
        tmp.write_text(json.dumps({
            "delegated": _delegated_entry(),
            "basic-fallback": {"scheme": "basic", "username": "svc", "password": "pw-SUPERSECRET"},
            "bearer-fallback": {"scheme": "bearer", "token": "static-tok-SUPERSECRET"},
        }), encoding="utf-8")
        connector = McpIngestionConnector(
            transport=McpTransport(kind="streamable_http", url="http://awx-mcp.local/mcp"),
            admitted=ADMITTED,
            source_system="ansible",
            credential_set="delegated",
            credential_sets_path=str(tmp),
            delegated_client=stub,
            token_client=machine,
            session_opener=server.opener(),
        )
        result = _invoke(connector)
        self.assertEqual(result.error["code"], "DELEGATED_REAUTHORIZATION_REQUIRED")
        self.assertEqual(server.bearers, [])        # no session opened (no unauthenticated/basic/bearer session)
        self.assertEqual(server.calls, [])          # no tool dispatched
        self.assertEqual(machine.acquire_calls, 0)  # no machine-grant acquisition


if __name__ == "__main__":
    unittest.main()
