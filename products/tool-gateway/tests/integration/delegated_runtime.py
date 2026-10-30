"""SPEC-070 p5b — the real delegated runtime, single process.

Drives the *actual* tool-gateway application — ``create_app()`` composed purely
from environment variables, with **no** dependency overrides, **no** injected
fake stores/clients, and **no** JWKS patching — against the p5a fixture stack:
real generated-TLS OAuth authorization/token/identity/revocation servers, a real
fixture target resource server, a real JWKS endpoint, and disposable Docker
Postgres custody. Every JWT is a genuine RS256 token verified over the network
against the fixture JWKS; every provider/resource call is a real TLS request.

It proves the whole SPEC-070 story on the real stack:

    read-path invoke (delegated set, no grant yet)
      -> the shared acquisition seam fails closed (DELEGATED_REAUTHORIZATION_REQUIRED)
      -> the producer upgrades it to a durable challenge (TARGET_AUTHORIZATION_REQUIRED)
      -> the six OQ-7 authorization routes enroll the owner via a real
         browser-simulated authorization-code grant over TLS
      -> the delegated send path (invoke-delegated -> http.get) refreshes the
         grant and calls the real resource server -> 200

plus the route-level fail-closed matrix (dedicated workload audiences, no-oracle
404s, single-use handles, callback replay, cancel/browser-reset lifecycle), the
cross-user approval matrix (requester A / approver B reaching the target as A's
account, never B's, with every tampered/stale/foreign/override handoff failing
closed at zero dispatch), and network call-count / recipient assertions for every
no-fallback / no-dispatch case (the fixture provider counts
authorize/token/whoami/resource/revoke calls).

Run::

    uv run --frozen --project products/tool-gateway \
        python products/tool-gateway/tests/integration/delegated_runtime.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from contextlib import contextmanager
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

import delegated_fixtures as fx
from delegated_fixtures import (
    CALLBACK,
    IDENTITY_AUDIENCE,
    IDENTITY_ISSUER,
    USERS,
    FixtureStack,
    check,
    mint_auth_workload,
    mint_exec_workload,
    mint_human,
)

EXEC_AUDIENCE = "luban-target-execution-handoff"
AUTH_AUDIENCE = "luban-target-authorization-handoff"
TARGET = "Automation"
SET_ID = "user"
REAUTH_CODE = "DELEGATED_REAUTHORIZATION_REQUIRED"
CHALLENGE_CODE = "TARGET_AUTHORIZATION_REQUIRED"


def _log(msg: str) -> None:
    print(f"[s70-runtime] {msg}", flush=True)


# --- the real app, composed from env (no overrides, no fakes) ---------------

def runtime_env(stack: FixtureStack) -> dict[str, str]:
    """Environment that composes the *real* delegated runtime over the fixtures.

    Three independent gates on, the shared Postgres custody runtime, the
    delegated-human trust set, both dedicated workload trust sets (execution +
    authorization handoff audiences), the portal identity path (local JWT verify
    against the same fixture JWKS), and the real HTTP connector pinned to the
    fixture resource origin. Every JWKS URL points at the fixture JWKS server, so
    all four verifiers resolve the one generated signing key over the network.
    """
    files, pg = stack.files, stack.postgres
    return {
        # --- delegated gates (all three on) ---
        "GATEWAY_DELEGATED_INVOKE_ENABLED": "true",
        "GATEWAY_DELEGATED_ACQUISITION_ENABLED": "true",
        "GATEWAY_DELEGATED_AUTHORIZATION_ENABLED": "true",
        # --- shared Postgres custody runtime ---
        "GATEWAY_DELEGATED_CUSTODY_DB_URL": pg["admin_dsn"],
        "GATEWAY_DELEGATED_CUSTODY_KEYRING_PATH": files["keyring_path"],
        "GATEWAY_DELEGATED_CUSTODY_CONFIG_PATH": files["config_path"],
        "GATEWAY_DELEGATED_CUSTODY_SET_ID": files["set_id"],
        "GATEWAY_DELEGATED_CUSTODY_TRUSTED_CALLBACK": CALLBACK,
        # --- delegated-human trust (owner edges + read-path requester) ---
        "GATEWAY_DELEGATED_IDENTITY_ISSUER": IDENTITY_ISSUER,
        "GATEWAY_DELEGATED_IDENTITY_JWKS_URL": stack.jwks_url,
        "GATEWAY_DELEGATED_IDENTITY_AUDIENCE": IDENTITY_AUDIENCE,
        "GATEWAY_DELEGATED_IDENTITY_ACTORS": "platform-gateway",
        # --- execution-workload trust (invoke-delegated send path) ---
        "GATEWAY_EXECUTION_WORKLOAD_ISSUER": fx.WORKLOAD_ISSUER,
        "GATEWAY_EXECUTION_WORKLOAD_JWKS_URL": stack.jwks_url,
        "GATEWAY_EXECUTION_WORKLOAD_AUDIENCE": EXEC_AUDIENCE,
        "GATEWAY_EXECUTION_WORKLOAD_SUBJECTS": fx.EXEC_WORKLOAD_SUBJECT,
        # --- authorization-workload trust (provider-url / callback handoffs) ---
        "GATEWAY_AUTHORIZATION_WORKLOAD_ISSUER": fx.WORKLOAD_ISSUER,
        "GATEWAY_AUTHORIZATION_WORKLOAD_JWKS_URL": stack.jwks_url,
        "GATEWAY_AUTHORIZATION_WORKLOAD_AUDIENCE": AUTH_AUDIENCE,
        "GATEWAY_AUTHORIZATION_WORKLOAD_SUBJECTS": fx.AUTH_WORKLOAD_SUBJECT,
        # --- portal identity path (local JWT verify; same fixture JWKS) ---
        "IDENTITY_JWKS_URL": stack.jwks_url,
        "IDENTITY_TOKEN_ISSUER": IDENTITY_ISSUER,
        "GATEWAY_TOKEN_AUDIENCE": IDENTITY_AUDIENCE,
        "GATEWAY_REQUIRE_AUTH": "true",
        # --- the real HTTP connector (send-path adapter) ---
        "GATEWAY_HTTP_ENABLED": "true",
        "GATEWAY_HTTP_ALLOW_ORIGINS": stack.resource_base,
        "GATEWAY_HTTP_CREDENTIAL_SETS": files["credential_sets_path"],
        # --- the real MCP-ingestion adapter (SPEC-069 binding, SPEC-070 seam) ---
        # Bound to the *same* delegated credential set over the bearer-capable
        # streamable-HTTP transport, aimed at the fixture MCP contact recorder.
        # The adapter's delegated seam shares ``resolve_outbound_auth`` with the
        # HTTP connector and fails closed *before* opening a session, so an
        # unenrolled owner leaves the recorder at zero hits (R-4).
        "GATEWAY_ANSIBLE_MCP_ENABLED": "true",
        "GATEWAY_ANSIBLE_MCP_TRANSPORT": "streamable_http",
        "GATEWAY_ANSIBLE_MCP_URL": stack.mcp_base,
        "GATEWAY_ANSIBLE_MCP_CREDENTIAL_SET": files["set_id"],
        "GATEWAY_ANSIBLE_MCP_CREDENTIAL_SETS": files["credential_sets_path"],
        # --- quiet, inert plumbing ---
        "OTEL_ENABLED": "false",
    }


def _reset_caches() -> None:
    from tool_gateway.core.config import get_settings
    from tool_gateway.services.delegated_invoke import reset_delegated_state
    from tool_gateway.services.policy_engine import reset_policy_state
    from tool_gateway.services.token_verifier import reset_verifier_state

    get_settings.cache_clear()
    reset_delegated_state()
    reset_verifier_state()
    reset_policy_state()


@contextmanager
def real_app(stack: FixtureStack):
    """Build the real app from env and yield a TestClient with lifespan running."""
    from tool_gateway.app import create_app

    env = runtime_env(stack)
    saved = {k: os.environ.get(k) for k in env}
    try:
        os.environ.update(env)
        _reset_caches()
        app = create_app()
        check(getattr(app.state, "authorization_service", None) is not None,
              "create_app composed the real AuthorizationService from env")
        with TestClient(app) as client:
            yield client
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        _reset_caches()


# --- auth header helpers (genuine RS256 tokens over the fixture JWKS) -------

def human(stack, user):
    return {"Authorization": f"Bearer {mint_human(stack.signing_key, user)}"}


def auth_workload(stack, *, aud=AUTH_AUDIENCE, sub=None):
    kwargs = {"aud": aud} if aud != AUTH_AUDIENCE else {}
    if sub is not None:
        kwargs["sub"] = sub
    return {"Authorization": f"Bearer {mint_auth_workload(stack.signing_key, **kwargs)}"}


def exec_workload(stack, *, aud=EXEC_AUDIENCE, sub=None):
    kwargs = {"aud": aud} if aud != EXEC_AUDIENCE else {}
    if sub is not None:
        kwargs["sub"] = sub
    return {"Authorization": f"Bearer {mint_exec_workload(stack.signing_key, **kwargs)}"}


def resource_url(stack, path="/api/data"):
    return stack.resource_base + path


# --- phase 1: the producer (read-path invoke -> durable challenge) ----------

def phase_producer(client, stack, user, session_id, call_id):
    """A delegated read with no enrolled grant fails closed and mints a challenge.

    This is the real SPEC-070 producer seam: the shared acquisition resolver
    denies with the transitional code, ``_produce_authorization_challenge``
    promotes it to a durable challenge bound to the verified owner + the exact
    call, and the response carries only safe opaque metadata. No token is
    acquired, no resource is called, and nothing falls back to another auth path.
    """
    stack.state.reset_stats()
    r = client.post("/api/v2/tools/invoke", json={
        "tool_name": "http.get",
        "parameters": {"url": resource_url(stack), "credential_set": SET_ID},
        "session_id": session_id, "call_id": call_id,
    }, headers=human(stack, user))
    check(r.status_code == 400, f"producer: unenrolled delegated read is an error ({r.status_code})")
    body = r.json()
    check(body.get("status") == "error", f"producer: promoted to error, got {body.get('status')}")
    check(body.get("error", {}).get("code") == CHALLENGE_CODE,
          f"producer: reserved challenge code, got {body.get('error')}")
    ar = body.get("authorization_required")
    check(isinstance(ar, dict) and ar.get("challenge_id"), f"producer: challenge metadata, got {ar}")
    check(ar.get("target") == TARGET, f"producer: challenge target, got {ar.get('target')}")
    s = stack.state.stats
    check(s["resource"] == 0 and s["token"] == 0 and s["token_code"] == 0 and s["token_refresh"] == 0,
          f"producer: no acquisition, no dispatch, no fallback {s}")
    _log(f"producer({user}): challenge {ar['challenge_id']} minted; no provider/resource call")
    return ar["challenge_id"]


# --- phase 2: enrollment through the six real authorization routes ----------

def phase_enroll(client, stack, challenge_id, user):
    """Drive start -> provider-url -> browser-sim grant -> callback -> status."""
    browser_secret = f"cookie-{challenge_id}"
    jar = {challenge_id: browser_secret}

    # 2a. start (verified human owner) mints a single-use handle; no-store.
    r = client.post(f"/api/v2/targets/authorizations/{challenge_id}/start",
                    json={"browser_secret": browser_secret}, headers=human(stack, user))
    check(r.status_code == 200, f"start: {r.status_code} {r.text}")
    check(r.headers.get("cache-control") == "no-store", "start: response is no-store")
    start_token = r.json()["start_token"]
    check(bool(start_token), "start: handle issued")

    # 2b. provider-url (authorization-handoff workload) consumes the handle with
    #     the browser proof and returns the secret provider URL.
    r = client.post("/api/v2/targets/authorizations/provider-url",
                    json={"start_token": start_token, "browser_bindings": jar},
                    headers=auth_workload(stack))
    check(r.status_code == 200, f"provider-url: {r.status_code} {r.text}")
    provider_url = r.json()["provider_url"]
    check(provider_url.startswith(stack.oauth_base + "/authorize?"),
          "provider-url: targets the fixture authorization endpoint")

    # 2c. a repeated navigation cannot obtain a second URL (handle is single-use).
    r2 = client.post("/api/v2/targets/authorizations/provider-url",
                     json={"start_token": start_token, "browser_bindings": jar},
                     headers=auth_workload(stack))
    check(r2.status_code != 200, f"provider-url: start handle is single-use ({r2.status_code})")

    # 2d. the initiating browser navigates to the provider and is redirected to
    #     the exact callback with a single-use code + the opaque state.
    with stack.client() as http:
        nav = http.get(provider_url + f"&fixture_user={user}")
    check(nav.status_code == 302, f"browser-sim: provider redirects ({nav.status_code})")
    qs = parse_qs(urlsplit(nav.headers["location"]).query)
    code, state = qs["code"][0], qs["state"][0]

    # 2e. callback (authorization-handoff workload) resolves the grant.
    r = client.post("/api/v2/targets/authorizations/callback",
                    json={"state": state, "browser_bindings": jar, "code": code},
                    headers=auth_workload(stack))
    check(r.status_code == 200, f"callback: {r.status_code} {r.text}")
    check(r.json().get("status") == "authorized", f"callback: authorized, got {r.json()}")
    check(r.json().get("return_url") == f"/authorizations/return/{challenge_id}",
          f"callback: server-chosen return path, got {r.json().get('return_url')}")
    # No secret material crosses the response boundary.
    for secret in (code, state, start_token, browser_secret):
        check(secret not in r.text, "callback: response leaks no code/state/handle/cookie")

    # 2f. the consumed state cannot be replayed: the no-oracle callback always
    #     returns a bounded 200, but a spent state is a safe ``failed`` outcome
    #     routed to ``/`` — it never re-authorizes and never reveals the challenge.
    r3 = client.post("/api/v2/targets/authorizations/callback",
                     json={"state": state, "browser_bindings": jar, "code": code},
                     headers=auth_workload(stack))
    check(r3.status_code == 200 and r3.json().get("status") == "failed"
          and r3.json().get("return_url") == "/",
          f"callback: replayed state is a safe non-authorized no-oracle outcome ({r3.text})")

    # 2g. status (verified human owner) projects authorized.
    r = client.get(f"/api/v2/targets/authorizations/{challenge_id}", headers=human(stack, user))
    check(r.status_code == 200 and r.json().get("status") == "authorized",
          f"status: authorized, got {r.status_code} {r.text}")

    s = stack.state.stats
    check(s["authorize"] == 1 and s["token_code"] == 1 and s["resource"] == 0,
          f"enroll: exactly one authorize + one code exchange, no resource call {s}")
    _log(f"enroll({user}): challenge {challenge_id} authorized via real TLS grant")


# --- phase 3: the delegated send path (invoke-delegated -> http.get) --------

def phase_send(client, stack, user):
    """The execution handoff refreshes the enrolled grant and calls the target."""
    from tool_gateway.services.delegated_invoke import canonical_digest

    stack.state.reset_stats()
    profile = USERS[user]
    parameters = {"url": resource_url(stack), "credential_set": SET_ID}
    projection = {
        "tool_name": "http.get", "session_id": "ses-send", "approval_kind": "action",
        "execution_id": "exec-send-1", "args_digest": canonical_digest(parameters),
        "requester_namespace": IDENTITY_ISSUER, "requester_sub": profile["sub"],
        "decider_namespace": IDENTITY_ISSUER, "decider_sub": profile["sub"],
        "owner_user_id": profile["username"], "decider_user_id": profile["username"],
    }
    body = {
        "projection": projection, "parameters": parameters,
        "requester_token": mint_human(stack.signing_key, user),
        "decider_token": mint_human(stack.signing_key, user),
    }
    r = client.post("/api/v2/tools/invoke-delegated", json=body, headers=exec_workload(stack))
    check(r.status_code == 200, f"send: invoke-delegated succeeded ({r.status_code}) {r.text}")
    res = r.json()
    check(res.get("status") == "success", f"send: tool success, got {res.get('status')} {res}")
    check(profile["account"] in r.text, f"send: resource returned {user}'s account {profile['account']}")
    s = stack.state.stats
    check(s["token_refresh"] >= 1 and s["resource"] == 1,
          f"send: real refresh + exactly one resource call {s}")
    _log(f"send({user}): http.get via delegated grant -> 200 (account {profile['account']})")


# --- phase 3b: the MCP-ingestion adapter fails closed with no target session --

def phase_mcp_failclosed(client, stack, user):
    """An unenrolled owner's MCP read opens *no* target session (SPEC-070 R-4).

    The MCP-ingestion adapter (the SPEC-069 Ansible binding) is wired to the same
    delegated credential set over the bearer-capable streamable-HTTP transport and
    shares ``resolve_outbound_auth`` with the HTTP connector. Its delegated seam
    resolves the bearer *before* the session opener dials, so a missing grant
    fails closed with the transitional denial — promoted here to the durable
    challenge — and the fixture MCP contact recorder is never reached. This proves
    the R-4 invariant on the MCP surface (no target connection without a verified
    grant) without a real MCP server; the user-delegated MCP *success* path is the
    AAP-compatibility leg (DI-070/R-6e), out of scope for this harness.
    """
    stack.state.reset_stats()
    r = client.post("/api/v2/tools/invoke", json={
        "tool_name": "ansible.get_environment_health",
        "parameters": {},
        "session_id": "ses-mcp", "call_id": "call-mcp-1",
    }, headers=human(stack, user))
    check(r.status_code == 400, f"mcp: unenrolled delegated MCP read is an error ({r.status_code})")
    body = r.json()
    check(body.get("status") == "error", f"mcp: promoted to error, got {body.get('status')}")
    check(body.get("error", {}).get("code") == CHALLENGE_CODE,
          f"mcp: reserved challenge code, got {body.get('error')}")
    ar = body.get("authorization_required")
    check(isinstance(ar, dict) and ar.get("challenge_id"), f"mcp: challenge metadata, got {ar}")
    check(ar.get("target") == TARGET, f"mcp: challenge target, got {ar.get('target')}")
    s = stack.state.stats
    check(s["mcp"] == 0, f"mcp: no target session opened — recorder never contacted {s}")
    check(s["token"] == 0 and s["token_code"] == 0 and s["token_refresh"] == 0,
          f"mcp: no acquisition, no fallback {s}")
    _log(f"mcp({user}): {ar['challenge_id']} minted; MCP recorder at 0 hits — no session opened")


# --- phase 3c: cross-user approval matrix (requester A / approver B) ---------

def _crossuser_body(stack, *, requester, decider, requester_token=None,
                    decider_token=None, requester_sub=None, session_id="ses-crossuser"):
    """A real invoke-delegated handoff: the requester owns the grant, the decider approves.

    ``requester_sub`` overrides the signed projection's requester identity, used to
    prove an altered projection fails closed against the genuine bearer.
    """
    from tool_gateway.services.delegated_invoke import canonical_digest

    req, dec = USERS[requester], USERS[decider]
    parameters = {"url": resource_url(stack), "credential_set": SET_ID}
    projection = {
        "tool_name": "http.get", "session_id": session_id, "approval_kind": "action",
        "execution_id": f"exec-crossuser-{requester}-{decider}",
        "args_digest": canonical_digest(parameters),
        "requester_namespace": IDENTITY_ISSUER, "requester_sub": requester_sub or req["sub"],
        "decider_namespace": IDENTITY_ISSUER, "decider_sub": dec["sub"],
        "owner_user_id": req["username"], "decider_user_id": dec["username"],
    }
    return {
        "projection": projection, "parameters": parameters,
        "requester_token": requester_token or mint_human(stack.signing_key, requester),
        "decider_token": decider_token or mint_human(stack.signing_key, decider),
    }


def phase_crossuser(client, stack):
    """SPEC-070 cross-user approval matrix on the real stack (plan L50/L66/L181).

    Requester A = alice (enrolled -> target account 42); approver B = bob. Policy
    rides the DECIDER while target acquisition rides the REQUESTER, so a
    cross-user approval must reach the target as alice's account 42 and NEVER
    switch to bob's 43 (L50). Every tampered / stale / foreign / override handoff
    below fails closed with ZERO real resource or token dispatch — the fixture
    provider counts every call, so "no fallback / no dispatch" is a measured fact,
    not a mocked return (L180).

    Scope note (consumed durable claim): the gateway's OWN single-use durable
    claims — the authorization start handle and the callback state — are proven
    non-replayable in ``phase_enroll``; the single-use *execution dispatch* claim
    that gates a delegated send is the execution-runtime worker ledger's boundary
    (``execution_dispatch_claims`` uniqueness + ``metadata_replay``), which the
    gateway trusts by design (plan L65) and deliberately does not re-implement.
    """
    alice, bob = USERS["alice"], USERS["bob"]

    # POSITIVE: requester alice (enrolled), approver bob -> the target identity is A.
    stack.state.reset_stats()
    r = client.post("/api/v2/tools/invoke-delegated",
                    json=_crossuser_body(stack, requester="alice", decider="bob"),
                    headers=exec_workload(stack))
    check(r.status_code == 200,
          f"crossuser(+): alice-requester approved by bob succeeded ({r.status_code}) {r.text}")
    res = r.json()
    check(res.get("status") == "success", f"crossuser(+): tool success, got {res.get('status')}")
    account = ((res.get("data") or {}).get("body") or {}).get("account")
    check(account == alice["account"],
          f"crossuser(+): target identity is the REQUESTER's account {alice['account']}, got {account}")
    check(account != bob["account"],
          f"crossuser(+): never the approver's account {bob['account']} (L50), got {account}")
    check(stack.state.stats["resource"] == 1,
          f"crossuser(+): exactly one real resource call {stack.state.stats}")
    _log(f"crossuser(+): alice-requester / bob-approver -> account {account} (requester's, not approver's)")

    def _denied(label, body, headers, expect_code):
        stack.state.reset_stats()
        rr = client.post("/api/v2/tools/invoke-delegated", json=body, headers=headers)
        check(rr.status_code == expect_code,
              f"crossuser[{label}]: {expect_code}, got {rr.status_code} {rr.text}")
        s = stack.state.stats
        check(s["resource"] == 0 and s["token_refresh"] == 0 and s["token_code"] == 0,
              f"crossuser[{label}]: no dispatch, no acquisition, no fallback {s}")
        return rr

    # 1. Wrong requester bearer: bob's genuine token presented for alice's identity.
    _denied("wrong-requester-bearer",
            _crossuser_body(stack, requester="alice", decider="bob",
                            requester_token=mint_human(stack.signing_key, "bob")),
            exec_workload(stack), 403)

    # 2. Altered signed identity: projection.requester_sub tampered to bob's sub while
    #    the genuine alice bearer is presented — the equality re-proof fails closed.
    _denied("altered-signed-identity",
            _crossuser_body(stack, requester="alice", decider="bob", requester_sub=bob["sub"]),
            exec_workload(stack), 403)

    # 3. Expired owner (requester) token: a fresh requester turn is required, never an
    #    impersonation fallback (plan L56).
    _denied("expired-owner-token",
            _crossuser_body(stack, requester="alice", decider="bob",
                            requester_token=mint_human(stack.signing_key, "alice", exp=200, iat=100)),
            exec_workload(stack), 403)

    # 4. Foreign session: requester bob is UNENROLLED while approver alice IS enrolled.
    #    Acquisition rides the requester, so alice's grant can never be borrowed and the
    #    send fails closed at the seam (denied, not promoted — the exec route has no producer).
    rr = _denied("foreign-session",
                 _crossuser_body(stack, requester="bob", decider="alice", session_id="ses-foreign"),
                 exec_workload(stack), 403)
    check(rr.json().get("error", {}).get("code") == REAUTH_CODE,
          f"crossuser[foreign-session]: re-authorization denial, got {rr.json().get('error')}")

    # 5. Stale envelope: an expired execution-workload transport token is refused before
    #    the handoff is parsed (durable single-use replay is the worker ledger's gate).
    _denied("stale-envelope",
            _crossuser_body(stack, requester="alice", decider="bob"),
            {"Authorization": f"Bearer {mint_exec_workload(stack.signing_key, exp=200)}"}, 401)

    # 6. Wrong workload audience: a valid cross-user body, but the authorization-handoff
    #    workload token is presented on the execution route (dedicated audiences, L64).
    _denied("wrong-workload-audience",
            _crossuser_body(stack, requester="alice", decider="bob"),
            auth_workload(stack), 401)

    # 7. Wrong workload subject: a valid body + audience, but an unallowlisted SA subject.
    _denied("wrong-workload-subject",
            _crossuser_body(stack, requester="alice", decider="bob"),
            exec_workload(stack, sub="system:serviceaccount:bogus:bogus"), 401)

    # 8. Direct requester override on the ordinary READ path is ignored (L66): bob
    #    (unenrolled) injects alice's identity into the body, hoping to ride her grant.
    #    The read derives its requester ONLY from the directly verified bearer, so it
    #    fails closed and binds the challenge to bob — never to the asserted alice.
    stack.state.reset_stats()
    r = client.post("/api/v2/tools/invoke", json={
        "tool_name": "http.get",
        "parameters": {"url": resource_url(stack), "credential_set": SET_ID},
        "session_id": "ses-override", "call_id": "call-override-1",
        # Caller-supplied requester overrides the route must NEVER honor:
        "delegated_requester_sub": alice["sub"], "delegated_requester_namespace": IDENTITY_ISSUER,
        "requester_sub": alice["sub"], "requester_namespace": IDENTITY_ISSUER, "owner_sub": alice["sub"],
    }, headers=human(stack, "bob"))
    check(r.status_code == 400,
          f"crossuser[override]: unenrolled bob read is an error ({r.status_code}) {r.text}")
    ob = r.json()
    check(ob.get("error", {}).get("code") == CHALLENGE_CODE,
          f"crossuser[override]: promoted challenge, got {ob.get('error')}")
    cid = (ob.get("authorization_required") or {}).get("challenge_id")
    check(cid, "crossuser[override]: challenge minted")
    s = stack.state.stats
    check(s["resource"] == 0 and s["token_refresh"] == 0,
          f"crossuser[override]: no dispatch — alice's grant never ridden {s}")
    # The challenge bound to the DIRECTLY verified requester (bob), not the asserted alice.
    r = client.get(f"/api/v2/targets/authorizations/{cid}", headers=human(stack, "bob"))
    check(r.status_code == 200, f"crossuser[override]: challenge is bob's ({r.status_code})")
    r = client.get(f"/api/v2/targets/authorizations/{cid}", headers=human(stack, "alice"))
    check(r.status_code == 404, f"crossuser[override]: not alice's — override ignored ({r.status_code})")
    _log("crossuser(-): wrong bearer / altered identity / expired owner / foreign session / "
         "stale envelope / wrong workload aud+sub / read override all fail closed, zero dispatch")


# --- phase 4: route-level fail-closed matrix --------------------------------

def phase_failclosed(client, stack, alice_cid, bob_cid):
    """Auth boundaries, no-oracle ownership, and the cancel/reset lifecycle."""
    # A human bearer is not authority on the bearerless workload handoffs.
    r = client.post("/api/v2/targets/authorizations/provider-url",
                    json={"start_token": "x", "browser_bindings": {bob_cid: "y"}},
                    headers=human(stack, "bob"))
    check(r.status_code in (401, 403), f"fail-closed: human on workload route ({r.status_code})")

    # The wrong workload audience is refused (dedicated handoff audiences).
    r = client.post("/api/v2/targets/authorizations/callback",
                    json={"state": "x", "browser_bindings": {bob_cid: "y"}, "denial": "access_denied"},
                    headers=auth_workload(stack, aud=EXEC_AUDIENCE))
    check(r.status_code in (401, 403), f"fail-closed: wrong workload audience ({r.status_code})")

    # The send path refuses a non-execution workload token.
    r = client.post("/api/v2/tools/invoke-delegated", json={}, headers=auth_workload(stack))
    check(r.status_code == 401, f"fail-closed: auth workload on exec route ({r.status_code})")

    # No-oracle: alice cannot start or read bob's challenge (and vice versa).
    r = client.post(f"/api/v2/targets/authorizations/{bob_cid}/start",
                    json={"browser_secret": "s"}, headers=human(stack, "alice"))
    check(r.status_code == 404, f"fail-closed: cross-owner start no-oracle ({r.status_code})")
    r = client.get(f"/api/v2/targets/authorizations/{bob_cid}", headers=human(stack, "alice"))
    check(r.status_code == 404, f"fail-closed: cross-owner status no-oracle ({r.status_code})")
    r = client.get("/api/v2/targets/authorizations/00000000-0000-4000-8000-000000000000",
                   headers=human(stack, "alice"))
    check(r.status_code == 404, f"fail-closed: unknown challenge no-oracle ({r.status_code})")

    # The send path fails closed when the parameter digest does not match.
    from tool_gateway.services.delegated_invoke import canonical_digest
    alice = USERS["alice"]
    params = {"url": resource_url(stack), "credential_set": SET_ID}
    projection = {
        "tool_name": "http.get", "session_id": "s", "approval_kind": "action",
        "execution_id": "e", "args_digest": canonical_digest({"tampered": True}),
        "requester_namespace": IDENTITY_ISSUER, "requester_sub": alice["sub"],
        "decider_namespace": IDENTITY_ISSUER, "decider_sub": alice["sub"],
        "owner_user_id": alice["username"], "decider_user_id": alice["username"],
    }
    stack.state.reset_stats()
    r = client.post("/api/v2/tools/invoke-delegated", json={
        "projection": projection, "parameters": params,
        "requester_token": mint_human(stack.signing_key, "alice"),
        "decider_token": mint_human(stack.signing_key, "alice"),
    }, headers=exec_workload(stack))
    check(r.status_code == 400, f"fail-closed: digest mismatch ({r.status_code})")
    check(stack.state.stats["resource"] == 0, "fail-closed: digest mismatch dispatches nothing")

    # A requester token that does not equal the signed projection is refused.
    projection["args_digest"] = canonical_digest(params)
    r = client.post("/api/v2/tools/invoke-delegated", json={
        "projection": projection, "parameters": params,
        "requester_token": mint_human(stack.signing_key, "bob"),  # != requester_sub
        "decider_token": mint_human(stack.signing_key, "alice"),
    }, headers=exec_workload(stack))
    check(r.status_code == 403, f"fail-closed: requester token != projection ({r.status_code})")
    check(stack.state.stats["resource"] == 0, "fail-closed: identity mismatch dispatches nothing")

    # Lifecycle: bob cancels his own pending challenge -> 204, then canceled.
    r = client.post(f"/api/v2/targets/authorizations/{bob_cid}/cancel", headers=human(stack, "bob"))
    check(r.status_code == 204, f"cancel: {r.status_code}")
    r = client.get(f"/api/v2/targets/authorizations/{bob_cid}", headers=human(stack, "bob"))
    check(r.status_code == 200 and r.json().get("status") == "canceled",
          f"cancel: status canceled, got {r.status_code} {r.text}")
    _log("fail-closed matrix: workload/audience boundaries, no-oracle ownership, "
         "digest + identity binding, and cancel lifecycle all held")


# --- phase 5: browser-reset cancels an owner's pending browser work ---------

def phase_browser_reset(client, stack):
    cid = phase_producer(client, stack, "bob", "ses-reset", "call-reset-1")
    browser_secret = f"cookie-{cid}"
    jar = {cid: browser_secret}
    r = client.post(f"/api/v2/targets/authorizations/{cid}/start",
                    json={"browser_secret": browser_secret}, headers=human(stack, "bob"))
    check(r.status_code == 200, f"browser-reset: start {r.status_code} {r.text}")
    r = client.post("/api/v2/targets/authorizations/browser-reset",
                    json={"browser_bindings": jar}, headers=human(stack, "bob"))
    check(r.status_code == 200, f"browser-reset: {r.status_code} {r.text}")
    check(r.json().get("canceled", 0) >= 1, f"browser-reset: canceled pending work, got {r.json()}")
    r = client.get(f"/api/v2/targets/authorizations/{cid}", headers=human(stack, "bob"))
    check(r.status_code == 200 and r.json().get("status") in ("canceled", "expired"),
          f"browser-reset: pending work no longer active, got {r.text}")
    _log(f"browser-reset(bob): challenge {cid} canceled via cookie-jar logout cleanup")


# --- provisioning + orchestration -------------------------------------------

async def _provision(stack: FixtureStack) -> None:
    from tool_gateway.services.custody_crypto import Keyring
    from tool_gateway.services.delegated_custody import PostgresCustodyStore, migrate_custody

    keyring = Keyring(stack.files["keyring_path"])
    await migrate_custody(stack.admin_dsn, keyring)
    custody = PostgresCustodyStore(stack.admin_dsn, keyring, stack.files["config_path"],
                                   stack.files["set_id"], CALLBACK)
    await custody.initialize()


def _run(stack: FixtureStack) -> None:
    asyncio.run(_provision(stack))
    with real_app(stack) as client:
        _log("phase 1-3: alice — producer -> enrollment -> delegated send")
        alice_cid = phase_producer(client, stack, "alice", "ses-alice", "call-alice-1")
        phase_enroll(client, stack, alice_cid, "alice")
        phase_send(client, stack, "alice")
        _log("phase 3b: bob — MCP-ingestion adapter fails closed (no target session)")
        phase_mcp_failclosed(client, stack, "bob")
        _log("phase 3c: cross-user approval matrix — requester alice / approver bob (L50/L66/L181)")
        phase_crossuser(client, stack)
        _log("phase 4: bob — a second unenrolled owner for the fail-closed matrix")
        bob_cid = phase_producer(client, stack, "bob", "ses-bob", "call-bob-1")
        phase_failclosed(client, stack, alice_cid, bob_cid)
        _log("phase 5: browser-reset logout cleanup")
        phase_browser_reset(client, stack)


def main() -> int:
    if not __debug__:
        raise SystemExit("delegated-runtime proof requires assertions enabled")
    fx.quiet_logs()
    try:
        fx._docker("ps")  # bounded liveness probe; fails fast on a wedged daemon
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None
    stack = FixtureStack()
    try:
        stack.start()
        _run(stack)
    except AssertionError as exc:
        print(f"DELEGATED-RUNTIME FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        stack.stop()
    print("delegated-runtime p5b: real app routes + HTTP adapter + MCP adapter "
          "fail-closed + producer + enrollment + delegated send + cross-user "
          "approval matrix + fail-closed matrix all passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
