"""SPEC-070 acquisition — HTTP connector enforcement for delegated sets.

The HTTP connector already pins destinations against the connector-wide
``GATEWAY_HTTP_ALLOW_ORIGINS`` policy and resolves outbound auth through
``resolve_outbound_auth``. These tests drive the *delegated* branch end to end
through the real connector (only the socket is faked) and prove:

* the acquired user-delegated bearer — not a machine grant — is attached;
* the selected set's exact ``resource_origins`` allowlist is enforced on the
  initial request and every GET redirect hop, alongside the connector policy;
* a delegated set without the authenticated worker requester context fails
  closed (no caller-supplied override is honoured);
* a target 401 invalidates the grant while a 403 stays a permission denial;
* every failure path calls zero Basic/static-bearer/machine-grant fallbacks and
  reaches the transport zero times.
"""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import httpx
from pydantic import SecretStr

from tool_gateway.services.delegated_custody import CredentialMetadata
from tool_gateway.tools.http_connector import HttpConnector
from tool_gateway.tools.registry import ToolRegistry
from tool_gateway.tools.user_delegated_client import (
    DelegatedAccessToken,
    DelegatedAcquisitionError,
)

RESOURCE = "https://resource.test"
ELSEWHERE = "https://elsewhere.test"
IDENTITY = {
    "subject": "carol",
    "actor": "carol",
    "roles": "operator",
    "delegated_requester_namespace": "issuer",
    "delegated_requester_sub": "alice",
}


def _run(coro):
    return asyncio.run(coro)


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


class _StubDelegatedClient:
    """Stands in for :class:`UserDelegatedClient` at the connector seam."""

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
    """A machine-grant client that fails the test if ever used."""

    async def acquire(self, name, entry):
        raise AssertionError(
            "machine-grant token client must never be used for a delegated set"
        )


class _Router:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, request):
        self.calls.append(request)
        entry = self.routes.get((request.method, request.url.path))
        if entry is None:
            entry = self.routes.get(request.url.path)
        if entry is None:
            return httpx.Response(404, json={"error": "no route"})
        if isinstance(entry, Exception):
            raise entry
        if callable(entry):
            return entry(request)
        return entry


def _connector(router, entry, *, delegated_client=None, allow=(RESOURCE,), **kwargs):
    tmp = Path(tempfile.mkdtemp()) / "sets.json"
    tmp.write_text(json.dumps({"delegated": entry}), encoding="utf-8")
    return HttpConnector(
        allow_origins=allow,
        transport=httpx.MockTransport(router),
        credential_sets_path=tmp,
        delegated_client=delegated_client if delegated_client is not None else _StubDelegatedClient(),
        token_client=_FailingTokenClient(),
        **kwargs,
    )


def _call(connector, tool, params, *, allow_mutating=True, identity=None):
    registry = ToolRegistry(allow_mutating=allow_mutating)
    connector.register_tools(registry)
    return _run(registry.invoke(tool, params, identity if identity is not None else dict(IDENTITY)))


class DelegatedHttpGetTests(unittest.TestCase):
    def test_acquired_bearer_is_attached_and_machine_grant_untouched(self):
        router = _Router({("GET", "/api"): httpx.Response(200, json={"ok": True})})
        stub = _StubDelegatedClient(token="delegated-at")
        connector = _connector(router, _delegated_entry(), delegated_client=stub)
        result = _call(connector, "http.get", {"url": f"{RESOURCE}/api", "credential_set": "delegated"})
        self.assertEqual(result.status, "success")
        self.assertEqual(router.calls[0].headers["Authorization"], "Bearer delegated-at")
        # The acquisition context carries the verified requester as the owner.
        ctx = stub.acquire_calls[0]
        self.assertEqual((ctx.owner_namespace, ctx.owner_sub), ("issuer", "alice"))
        self.assertEqual(ctx.set_name, "delegated")
        self.assertEqual(ctx.target, "https://issuer.test")

    def test_missing_requester_context_fails_closed_without_transport(self):
        router = _Router({("GET", "/api"): httpx.Response(200, json={"ok": True})})
        stub = _StubDelegatedClient()
        connector = _connector(router, _delegated_entry(), delegated_client=stub)
        result = _call(connector, "http.get", {"url": f"{RESOURCE}/api", "credential_set": "delegated"}, identity={"subject": "carol", "actor": "carol"})
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error["code"], "DELEGATED_CONTEXT_REQUIRED")
        self.assertEqual(stub.acquire_calls, [])
        self.assertEqual(router.calls, [])


class DelegatedResourceOriginTests(unittest.TestCase):
    def test_origin_outside_resource_allowlist_is_denied(self):
        router = _Router({("GET", "/api"): httpx.Response(200, json={"ok": True})})
        stub = _StubDelegatedClient()
        connector = _connector(router, _delegated_entry(resource_origins=ELSEWHERE), delegated_client=stub)
        result = _call(connector, "http.get", {"url": f"{RESOURCE}/api", "credential_set": "delegated"})
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error["code"], "HTTP_RESOURCE_ORIGIN_NOT_ALLOWED")
        self.assertEqual(stub.acquire_calls, [])
        self.assertEqual(router.calls, [])

    def test_redirect_hop_leaving_resource_allowlist_is_denied(self):
        router = _Router({
            ("GET", "/api"): httpx.Response(302, headers={"Location": f"{ELSEWHERE}/x"}),
            ("GET", "/x"): httpx.Response(200, json={"ok": True}),
        })
        stub = _StubDelegatedClient()
        connector = _connector(router, _delegated_entry(), delegated_client=stub, allow=(RESOURCE, ELSEWHERE))
        result = _call(connector, "http.get", {"url": f"{RESOURCE}/api", "credential_set": "delegated"})
        self.assertEqual(result.status, "denied")
        # A hop is re-coded as a redirect refusal but carries the resource-origin
        # reason in its message; the first hop still reached the transport.
        self.assertEqual(result.error["code"], "HTTP_REDIRECT_NOT_ALLOWED")
        self.assertIn("resource-origin", result.error["message"])
        self.assertEqual(len(router.calls), 1)  # only the first hop reached the transport


class DelegatedInvalidationTests(unittest.TestCase):
    def test_target_401_invalidates_the_grant_but_is_reported_as_a_fact(self):
        router = _Router({("GET", "/api"): httpx.Response(401, json={"error": "token rejected"})})
        stub = _StubDelegatedClient()
        connector = _connector(router, _delegated_entry(), delegated_client=stub)
        result = _call(connector, "http.get", {"url": f"{RESOURCE}/api", "credential_set": "delegated"})
        self.assertEqual(result.status, "success")  # a 401 is an observed fact
        self.assertEqual(result.data["status"], 401)
        self.assertEqual(len(stub.invalidate_calls), 1)

    def test_target_403_is_a_permission_denial_not_reenrollment(self):
        router = _Router({("GET", "/api"): httpx.Response(403, json={"error": "forbidden"})})
        stub = _StubDelegatedClient()
        connector = _connector(router, _delegated_entry(), delegated_client=stub)
        result = _call(connector, "http.get", {"url": f"{RESOURCE}/api", "credential_set": "delegated"})
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["status"], 403)
        self.assertEqual(stub.invalidate_calls, [])


class DelegatedAcquisitionFailureTests(unittest.TestCase):
    def test_authorization_required_is_denied_with_no_transport_or_fallback(self):
        router = _Router({("GET", "/api"): httpx.Response(200, json={"ok": True})})
        stub = _StubDelegatedClient(exc=DelegatedAcquisitionError("authorization_required", "no grant"))
        connector = _connector(router, _delegated_entry(), delegated_client=stub)
        result = _call(connector, "http.get", {"url": f"{RESOURCE}/api", "credential_set": "delegated"})
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error["code"], "DELEGATED_REAUTHORIZATION_REQUIRED")
        self.assertEqual(router.calls, [])

    def test_acquisition_in_progress_is_a_safe_error_not_an_enrollment_challenge(self):
        router = _Router({("GET", "/api"): httpx.Response(200, json={"ok": True})})
        stub = _StubDelegatedClient(exc=DelegatedAcquisitionError("acquisition_in_progress", "busy"))
        connector = _connector(router, _delegated_entry(), delegated_client=stub)
        result = _call(connector, "http.get", {"url": f"{RESOURCE}/api", "credential_set": "delegated"})
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "DELEGATED_ACQUISITION_IN_PROGRESS")
        self.assertEqual(router.calls, [])


class DelegatedHttpPostTests(unittest.TestCase):
    def test_write_redirect_is_refused_and_resource_origin_enforced(self):
        router = _Router({("POST", "/api"): httpx.Response(302, headers={"Location": f"{RESOURCE}/x"})})
        stub = _StubDelegatedClient()
        connector = _connector(router, _delegated_entry(), delegated_client=stub)
        result = _call(connector, "http.post", {"url": f"{RESOURCE}/api", "credential_set": "delegated", "body": {"a": 1}})
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "HTTP_REDIRECT_NOT_ALLOWED")
        self.assertEqual(len(stub.acquire_calls), 1)  # token was acquired for the POST


class _CountingMachineClient:
    """A machine-grant client that counts (never fails) so a test can assert it
    was called exactly zero times for a delegated set."""

    def __init__(self):
        self.acquire_calls = 0

    async def acquire(self, name, entry):
        self.acquire_calls += 1
        return "machine-grant-token", None


class ZeroFallbackCounterTests(unittest.TestCase):
    """Plan §"HTTP and MCP enforcement": on every delegated failure, counters
    prove zero calls to Basic, static-bearer, machine-grant, unauthenticated, and
    alternate-transport fallback paths."""

    def test_delegated_failure_fires_no_fallback_path(self):
        seen_auth = []  # every Authorization header the single transport sees

        def router(request):
            seen_auth.append(request.headers.get("Authorization"))
            return httpx.Response(200, json={"ok": True})

        tmp = Path(tempfile.mkdtemp()) / "sets.json"
        # A basic and a static-bearer set sit beside the delegated one; a fallback
        # implementation could only reach them by re-resolving the destination,
        # which the empty transport log proves never happened.
        tmp.write_text(json.dumps({
            "delegated": _delegated_entry(),
            "basic-fallback": {"scheme": "basic", "username": "svc", "password": "pw-SUPERSECRET"},
            "bearer-fallback": {"scheme": "bearer", "token": "static-tok-SUPERSECRET"},
        }), encoding="utf-8")
        machine = _CountingMachineClient()
        stub = _StubDelegatedClient(exc=DelegatedAcquisitionError("authorization_required", "no grant"))
        connector = HttpConnector(
            allow_origins=(RESOURCE,),
            transport=httpx.MockTransport(router),
            credential_sets_path=tmp,
            delegated_client=stub,
            token_client=machine,
        )
        result = _call(connector, "http.get", {"url": f"{RESOURCE}/api", "credential_set": "delegated"})
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error["code"], "DELEGATED_REAUTHORIZATION_REQUIRED")
        # Zero calls across every fallback class:
        self.assertEqual(seen_auth, [])                  # no Basic / static-bearer / unauthenticated send
        self.assertEqual(machine.acquire_calls, 0)       # no machine-grant acquisition
        self.assertEqual(stub.invalidate_calls, [])      # a pre-send failure invalidates nothing
        self.assertNotIn("SUPERSECRET", json.dumps(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
