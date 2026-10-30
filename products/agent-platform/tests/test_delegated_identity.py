"""SPEC-070 trusted identities are cryptographic facts, never header projections."""
import dataclasses
import json
import pickle
import time
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from agent_service.services.delegated_identity import (
    DelegatedIdentityError, DelegatedIdentityVerifier, VerifiedHuman, signed_identity_fields,
)
from agent_service.services.execution_signing import build_requests, verify_envelope
from test_execution_signing import _parked, KEY


@pytest.fixture
def identities():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwks = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key()))
    verifier = DelegatedIdentityVerifier("trusted-issuer", "tool-gateway", ("platform-gateway",), jwks)

    def mint(**changes):
        claims = {"iss": "trusted-issuer", "aud": ["tool-gateway"], "sub": "alice-immutable",
                  "username": "alice", "iat": int(time.time()) - 1, "exp": int(time.time()) + 300,
                  "authentication_source": "oidc", "act": {"sub": "platform-gateway"}}
        claims.update(changes)
        return jwt.encode(claims, key, algorithm="RS256")

    return verifier, mint


def test_verified_context_has_no_bearer_and_cannot_be_mutated_or_serialized(identities):
    verifier, mint = identities
    token = mint()
    identity = verifier.verify(token, user_id="alice")
    assert identity.namespace == "trusted-issuer" and identity.subject == "alice-immutable"
    assert identity.user_id == "alice" and identity.actor == "platform-gateway"
    assert token not in repr(identity)
    with pytest.raises(dataclasses.FrozenInstanceError):
        identity.subject = "bob"
    with pytest.raises(TypeError):
        pickle.dumps(identity)
    with pytest.raises(TypeError):
        json.dumps(identity)
    with pytest.raises(TypeError):
        VerifiedHuman("untrusted", "s", "u", "a", 123)


@pytest.mark.parametrize("changes", [
    {"iss": "foreign"}, {"aud": ["platform-gateway"]}, {"exp": 1}, {"exp": None},
    {"exp": "9999999999"}, {"sub": ""}, {"sub": None}, {"sub": " "}, {"sub": "x" * 257},
    {"authentication_source": "development"}, {"authentication_source": None},
    {"act": None}, {"act": {"sub": "other-service"}}, {"act": {"sub": "platform-gateway", "act": {"sub": "other"}}},
])
def test_verification_rejects_non_human_wrong_binding_and_bad_types(identities, changes):
    verifier, mint = identities
    with pytest.raises(DelegatedIdentityError, match="delegated_identity_invalid"):
        verifier.verify(mint(**changes), user_id="alice")


def test_forged_signature_and_unsigned_user_override_fail_closed(identities):
    verifier, mint = identities
    with pytest.raises(DelegatedIdentityError):
        verifier.verify(mint(), user_id="bob")
    claims = jwt.decode(mint(), options={"verify_signature": False})
    forged = jwt.encode(claims, rsa.generate_private_key(public_exponent=65537, key_size=2048), algorithm="RS256")
    with pytest.raises(DelegatedIdentityError):
        verifier.verify(forged)
    for token in (None, "", "opaque", "x" * 16385):
        with pytest.raises(DelegatedIdentityError):
            verifier.verify(token)


def test_builder_signs_requester_and_decider_separately(identities):
    verifier, mint = identities
    alice = verifier.verify(mint(), user_id="alice")
    bob = verifier.verify(mint(sub="bob-immutable", username="bob"), user_id="bob")
    pending = _parked()
    envelope = build_requests(pending, "bob", KEY, run_id=str(uuid4()), admission_epoch=str(uuid4()),
                              requester=alice, decider=bob)[0]
    assert envelope["requester_sub"] == "alice-immutable"
    assert envelope["decider_sub"] == "bob-immutable"
    assert envelope["owner_user_id"] == "alice"
    assert verify_envelope(envelope, envelope["signature"], KEY)
    with pytest.raises(DelegatedIdentityError):
        signed_identity_fields(alice, None, "alice", "bob")
    with pytest.raises(DelegatedIdentityError):
        signed_identity_fields(bob, alice, "alice", "bob")
    with pytest.raises(DelegatedIdentityError):
        signed_identity_fields({"namespace": "trusted-issuer", "subject": "alice-immutable"}, bob, "alice", "bob")
    with pytest.raises(DelegatedIdentityError):
        build_requests(pending, "bob", KEY, requester=alice, decider=bob)


@pytest.mark.parametrize("backend", ["memory", "redis"])
def test_session_requester_is_birth_only_and_survives_bookkeeping(identities, monkeypatch, backend):
    import fakeredis
    from fastapi import HTTPException
    from agent_service.services import session_service
    from agent_service.services.session_store import InMemorySessionStore, RedisSessionStore

    verifier, mint = identities
    alice = verifier.verify(mint())
    renamed_subject = verifier.verify(mint(sub="other-immutable"))
    store = InMemorySessionStore() if backend == "memory" else RedisSessionStore(fakeredis.FakeRedis())
    monkeypatch.setattr(session_service, "SESSION_STORE", store)
    record = session_service.create_named_session("bound", "alice", requester=alice)
    assert (record.requester_namespace, record.requester_sub) == (alice.namespace, alice.subject)
    for requester in (None, renamed_subject):
        # Even a direct legacy store caller cannot overwrite an existing binding.
        store.create_session("alice", session_id="bound", requester=requester)
    session_service.mark_session_turn("bound", "safe title")
    session_service.pin_session_model("bound", "test-model")
    stored = session_service.ensure_session("bound", "alice", requester=alice)
    assert stored.requester_sub == alice.subject
    assert store.list_sessions_by_user("alice")[0].requester_sub == alice.subject
    assert "Bearer" not in stored.model_dump_json()
    with pytest.raises(HTTPException) as exc:
        session_service.ensure_session("bound", "alice", requester=renamed_subject)
    assert exc.value.status_code == 404
    with pytest.raises(Exception):
        stored.requester_sub = "other"


@pytest.mark.parametrize("backend", ["memory", "redis"])
def test_legacy_session_cannot_be_promoted_by_username(identities, monkeypatch, backend):
    import fakeredis
    from agent_service.services import session_service
    from agent_service.services.session_store import InMemorySessionStore, RedisSessionStore
    from agent_service.services.delegated_identity import session_requester

    verifier, mint = identities
    alice = verifier.verify(mint())
    store = InMemorySessionStore() if backend == "memory" else RedisSessionStore(fakeredis.FakeRedis())
    monkeypatch.setattr(session_service, "SESSION_STORE", store)
    legacy = session_service.create_named_session("legacy", "alice")
    again = session_service.create_named_session("legacy", "alice", requester=alice)
    assert legacy.requester_sub is None and again.requester_sub is None
    assert session_requester(again, alice) is None
    fresh = session_service.ensure_session(None, "alice", requester=alice)
    assert session_requester(fresh, alice) is alice
    with pytest.raises(DelegatedIdentityError):
        store.create_session("bob", requester=alice)
    with pytest.raises(DelegatedIdentityError):
        store.create_session("alice", requester={"subject": "alice-immutable"})


@pytest.mark.parametrize("fields", [
    {"requester_namespace": "issuer"}, {"requester_sub": "sub"},
    {"requester_namespace": "", "requester_sub": "sub"},
    {"requester_namespace": "issuer", "requester_sub": "x" * 257},
])
def test_session_identity_metadata_rejects_partial_or_unbounded_fields(fields):
    from datetime import datetime, timezone
    from pydantic import ValidationError
    from agent_service.schemas.api import SessionRecord
    with pytest.raises(ValidationError):
        SessionRecord(session_id="session", user_id="alice", created_at=datetime.now(timezone.utc), **fields)


def test_delegated_runtime_requires_explicit_trust_configuration(monkeypatch):
    from agent_service.runtime_settings import RuntimeSettings
    assert not RuntimeSettings().target_authorization_enabled
    with pytest.raises(ValueError, match="delegated identity"):
        RuntimeSettings(target_authorization_enabled=True)
    monkeypatch.setenv("AGENT_TARGET_AUTHORIZATION_ENABLED", "true")
    monkeypatch.setenv("AGENT_DELEGATED_IDENTITY_ISSUER", "https://identity.test")
    monkeypatch.setenv("AGENT_DELEGATED_IDENTITY_JWKS_URL", "https://identity.test/jwks")
    monkeypatch.setenv("AGENT_DELEGATED_IDENTITY_AUDIENCE", "tool-gateway")
    monkeypatch.setenv("AGENT_DELEGATED_IDENTITY_ACTORS", "platform-gateway")
    settings = RuntimeSettings.from_env()
    assert settings.target_authorization_enabled
    assert settings.delegated_identity_actors == ("platform-gateway",)


@pytest.mark.parametrize("field", ["last_active_at", "model"])
def test_redis_delayed_bookkeeping_cannot_restore_old_requester(identities, monkeypatch, field):
    import fakeredis
    from datetime import datetime, timezone
    from agent_service.services.session_store import RedisSessionStore
    verifier, mint = identities
    first = verifier.verify(mint())
    successor = verifier.verify(mint(sub="replacement"))
    client = fakeredis.FakeRedis()
    store = RedisSessionStore(client)
    store.create_session("alice", "race", requester=first)
    pipeline = client.pipeline

    def racing_pipeline(*args, **kwargs):
        pipe = pipeline(*args, **kwargs)
        execute = pipe.execute
        def after_read(*args, **kwargs):
            store.delete_session("race")
            store.create_session("alice", "race", requester=successor)
            return execute(*args, **kwargs)
        pipe.execute = after_read
        return pipe

    monkeypatch.setattr(client, "pipeline", racing_pipeline)
    store._update_blob("race", field, datetime.now(timezone.utc) if field == "last_active_at" else "new")
    assert store.get_session("race").requester_sub == "replacement"


@pytest.fixture
def delegated_kernel(identities, monkeypatch):
    from agent_service.api.v2 import routes
    from agent_service.runtime_kernel import AgentKernel
    from agent_service.runtime_settings import RuntimeSettings
    from agent_service.services import delegated_identity, session_service
    from agent_service.services.hitl_confirmations import CONFIRMATION_REGISTRY
    from agent_service.services.session_store import InMemorySessionStore

    verifier, mint = identities
    monkeypatch.setattr(delegated_identity, "_verifier", lambda *args: verifier)
    store = InMemorySessionStore()
    monkeypatch.setattr(session_service, "SESSION_STORE", store)
    monkeypatch.setattr(routes, "SESSION_STORE", store)
    monkeypatch.setattr(CONFIRMATION_REGISTRY, "_by_session", {})
    kernel = AgentKernel(settings=RuntimeSettings(
        api_key="test-key", target_authorization_enabled=True,
        delegated_identity_issuer="trusted-issuer", delegated_identity_audience="tool-gateway",
        delegated_identity_actors=("platform-gateway",), delegated_identity_jwks_url="https://identity.test/jwks",
        execution_signing_key=KEY, execution_admission_epoch=str(uuid4()),
    ))
    monkeypatch.setattr(routes, "get_runtime_kernel", lambda: kernel)
    token = mint()
    session = store.create_session("alice", requester=verifier.verify(token))
    return SimpleNamespace(kernel=kernel, store=store, session=session, token=token, mint=mint, verifier=verifier)


def _assert_no_identity_context():
    from agent_service.services.delegated_identity import REQUESTER_IDENTITY, DECIDER_IDENTITY
    from agent_service.tools.gateway_tools import DELEGATED_TOKEN, GENERATION_OWNER_TOKEN
    assert REQUESTER_IDENTITY.get() is None
    assert DECIDER_IDENTITY.get() is None
    assert DELEGATED_TOKEN.get() is None
    assert GENERATION_OWNER_TOKEN.get() is None


@pytest.mark.parametrize("decision", ["approve", "deny"])
def test_enabled_root_park_cross_user_resume_and_repark(delegated_kernel, monkeypatch, decision):
    import asyncio
    from agent_service.services.delegated_identity import REQUESTER_IDENTITY, DECIDER_IDENTITY
    from agent_service.services.hitl_confirmations import CONFIRMATION_REGISTRY
    from agent_service.tools.gateway_tools import DELEGATED_TOKEN, EXECUTION_REQUESTS, generation_bearer_token
    from test_hitl_confirmations import FakeAgent, _patch_agent, _park_event

    ctx = delegated_kernel
    observed = []

    class ReparkAgent(FakeAgent):
        async def reply_stream(self, inputs):
            self.inputs.append(inputs)
            observed.append((REQUESTER_IDENTITY.get(), DECIDER_IDENTITY.get(),
                             DELEGATED_TOKEN.get(), generation_bearer_token(), EXECUTION_REQUESTS.get()))
            yield _park_event()

    agent = ReparkAgent()
    _patch_agent(monkeypatch, ctx.kernel, agent)
    bob_token = ctx.mint(sub="bob-immutable", username="bob")

    async def run():
        frames = [f async for f in ctx.kernel.stream_events("check", "req", ctx.session.session_id, "alice", ctx.token)]
        _assert_no_identity_context()
        pending = CONFIRMATION_REGISTRY.claim(ctx.session.session_id, frames[-1]["confirm_id"], 600)
        assert pending.requester_identity.subject == "alice-immutable"
        assert pending.requester_delegated_token == ctx.token
        assert ctx.token not in repr(pending) + json.dumps(frames)
        pending.run_id = str(uuid4())
        # This test exercises the real signing boundary, not durable dispatch.
        monkeypatch.setattr(ctx.kernel, "_execution_recovery", lambda: object())
        monkeypatch.setattr(ctx.kernel, "_bind_guard", lambda *args: None)
        resumed = [f async for f in ctx.kernel.resume_confirmation(
            ctx.session.session_id, pending, decision, "bob", "req-resume", bob_token, owner_user_name="alice"
        )]
        _assert_no_identity_context()
        successor = CONFIRMATION_REGISTRY.peek_parked(ctx.session.session_id)
        assert successor is not pending
        assert successor.requester_identity.subject == "alice-immutable"
        assert successor.requester_delegated_token == ctx.token
        assert pending.requester_identity is None and pending.requester_delegated_token is None
        assert all(token not in json.dumps(resumed) for token in (ctx.token, bob_token))

    asyncio.run(run())
    assert observed[0][0].subject == observed[0][1].subject == "alice-immutable"
    requester, decider, primary, owner, requests = observed[1]
    assert (requester.subject, decider.subject) == ("alice-immutable", "bob-immutable")
    assert (primary, owner) == (bob_token, ctx.token)
    if decision == "approve":
        envelope = requests["call-1"]
        assert envelope["requester_sub"] == "alice-immutable"
        assert envelope["decider_sub"] == "bob-immutable"
        assert verify_envelope(envelope, envelope["signature"], KEY)
    else:
        assert not requests


@pytest.mark.parametrize("failure", ["missing", "expired", "swapped", "untyped", "foreign_session", "decider"])
def test_enabled_resume_invalid_continuity_interrupts_without_confirmation(delegated_kernel, monkeypatch, failure):
    import asyncio
    from agentscope.event import UserInterruptEvent
    from agent_service.services.hitl_confirmations import CONFIRMATION_REGISTRY
    from test_hitl_confirmations import FakeAgent, _patch_agent, _park_event

    ctx = delegated_kernel
    agent = FakeAgent([_park_event()])
    _patch_agent(monkeypatch, ctx.kernel, agent)

    async def run():
        frames = [f async for f in ctx.kernel.stream_events("check", "req", ctx.session.session_id, "alice", ctx.token)]
        pending = CONFIRMATION_REGISTRY.claim(ctx.session.session_id, frames[-1]["confirm_id"], 600)
        agent.inputs.clear()
        agent.events = []
        session_id = ctx.session.session_id
        bob = ctx.mint(sub="bob-immutable", username="bob")
        if failure == "missing":
            pending.requester_delegated_token = None
        elif failure == "expired":
            pending.requester_delegated_token = ctx.mint(exp=1)
        elif failure == "swapped":
            pending.requester_delegated_token = ctx.mint(sub="different-sub")
        elif failure == "untyped":
            pending.requester_identity = {"subject": "alice-immutable"}
        elif failure == "foreign_session":
            session_id = ctx.store.create_session("alice", requester=ctx.verifier.verify(ctx.token)).session_id
        else:
            bob = ctx.mint(sub="bob-immutable", username="bob", authentication_source="development")
        resumed = [f async for f in ctx.kernel.resume_confirmation(session_id, pending, "approve", "bob", "req", bob)]
        _assert_no_identity_context()
        assert len(agent.inputs) == 1 and isinstance(agent.inputs[0], UserInterruptEvent)
        assert sum(f.get("event") == "message_end" for f in resumed) == 1
        assert "fresh requester turn" in json.dumps(resumed)
        assert pending.requester_delegated_token is None and pending.requester_identity is None
        assert not CONFIRMATION_REGISTRY.is_parked(ctx.session.session_id, 600)

    asyncio.run(run())


@pytest.mark.parametrize("structured", [False, True])
@pytest.mark.parametrize("fail", [False, True])
def test_enabled_blocking_context_is_scoped_with_durable_evidence(delegated_kernel, monkeypatch, structured, fail):
    import asyncio
    from agent_service.services.delegated_identity import REQUESTER_IDENTITY, DECIDER_IDENTITY
    from agent_service.services.kernel_middleware import TOOL_EVIDENCE_SINK
    from test_hitl_confirmations import FakeAgent, FakeUserMsg

    ctx = delegated_kernel
    seen = []

    class BlockingAgent(FakeAgent):
        async def reply(self, message, structured_schema=None):
            seen.append((REQUESTER_IDENTITY.get().subject, DECIDER_IDENTITY.get().subject, TOOL_EVIDENCE_SINK.get()))
            if fail:
                raise RuntimeError("fixture failure")
            return SimpleNamespace(content="safe reply", structured_output={"ok": True} if structured_schema else None)

    async def ensure(*args):
        return BlockingAgent(), FakeUserMsg, "fixture-model"
    monkeypatch.setattr(ctx.kernel, "ensure_agent", ensure)
    monkeypatch.setattr(ctx.kernel, "_snapshot_state", lambda *args: None)

    async def run():
        result = await ctx.kernel.reply_text("check", ctx.session.session_id, "alice", ctx.token,
                                           response_schema={"type": "object"} if structured else None)
        _assert_no_identity_context()
        if not fail:
            assert tuple(result) == ("safe reply", {"ok": True} if structured else None)
            assert result.authorization_required is None
        assert TOOL_EVIDENCE_SINK.get() is None
    asyncio.run(run())
    assert len(seen) == 1
    assert seen[0][:2] == ("alice-immutable", "alice-immutable")
    assert isinstance(seen[0][2], asyncio.Queue)


def test_resume_setup_failure_clears_claim_and_requester(delegated_kernel, monkeypatch):
    import asyncio
    from agent_service.services.hitl_confirmations import CONFIRMATION_REGISTRY
    from test_hitl_confirmations import FakeAgent, _patch_agent, _park_event
    ctx = delegated_kernel
    _patch_agent(monkeypatch, ctx.kernel, FakeAgent([_park_event()]))

    async def run():
        frames = [f async for f in ctx.kernel.stream_events("check", "req", ctx.session.session_id, "alice", ctx.token)]
        pending = CONFIRMATION_REGISTRY.claim(ctx.session.session_id, frames[-1]["confirm_id"], 600)
        async def broken(*args):
            raise RuntimeError("setup failure")
        monkeypatch.setattr(ctx.kernel, "ensure_agent", broken)
        try:
            async for _ in ctx.kernel.resume_confirmation(ctx.session.session_id, pending, "deny", "alice", "req", ctx.token):
                pass
        except RuntimeError:
            pass
        _assert_no_identity_context()
        assert pending.requester_identity is None and pending.requester_delegated_token is None
        assert not CONFIRMATION_REGISTRY.is_parked(ctx.session.session_id, 600)
    asyncio.run(run())


@pytest.mark.parametrize("path", ["/api/v2/sessions", "/api/v2/chat", "/api/v2/chat/stream"])
@pytest.mark.parametrize("source", ["absent", "development", "foreign_subject", "forged"])
def test_enabled_routes_reject_unverified_identity_before_session_birth(delegated_kernel, path, source):
    from fastapi.testclient import TestClient
    from agent_service.app import create_app
    ctx = delegated_kernel
    client = TestClient(create_app())
    tokens = {"absent": "", "development": ctx.mint(authentication_source="development"),
              "foreign_subject": ctx.mint(username="bob"), "forged": "not-a-jwt"}
    headers = {"X-User-ID": "alice", "Authorization": "Bearer " + tokens[source]}
    count = len(ctx.store.list_sessions_by_user("alice"))
    if path.endswith("/stream"):
        response = client.get(path, params={"message": "check"}, headers=headers)
    else:
        response = client.post(path, json={"message": "check"} if path.endswith("/chat") else {}, headers=headers)
    assert response.status_code == 401
    assert len(ctx.store.list_sessions_by_user("alice")) == count
    assert response.json() == {"detail": "verified human identity required"}


def test_enabled_session_routes_bind_birth_hide_metadata_and_preserve_legacy(delegated_kernel):
    from fastapi.testclient import TestClient
    from agent_service.app import create_app
    ctx = delegated_kernel
    client = TestClient(create_app())
    headers = {"X-User-ID": "alice", "Authorization": "Bearer " + ctx.token}
    result = client.post("/api/v2/sessions", json={"session_id": "bound-http"}, headers=headers)
    assert result.status_code == 201
    stored = ctx.store.get_session("bound-http")
    assert stored.requester_sub == "alice-immutable"
    assert ctx.token not in stored.model_dump_json()
    for response, expected in ((result, 201), (client.get("/api/v2/sessions", headers=headers), 200),
                               (client.get("/api/v2/sessions/bound-http", headers=headers), 200)):
        assert response.status_code == expected
        assert "requester_namespace" not in response.text and "requester_sub" not in response.text
        assert ctx.token not in response.text
    other = {**headers, "Authorization": "Bearer " + ctx.mint(sub="other-sub")}
    assert client.post("/api/v2/sessions", json={"session_id": "bound-http"}, headers=other).status_code == 404
    ctx.store.create_session("alice", "legacy-http")
    assert client.post("/api/v2/sessions", json={"session_id": "legacy-http"}, headers=headers).status_code == 201
    assert ctx.store.get_session("legacy-http").requester_sub is None


def test_enabled_confirm_route_checks_decider_before_claim(delegated_kernel, monkeypatch):
    import asyncio
    from fastapi.testclient import TestClient
    from agent_service.app import create_app
    from agent_service.services.hitl_confirmations import CONFIRMATION_REGISTRY
    from test_hitl_confirmations import FakeAgent, _patch_agent, _park_event
    ctx = delegated_kernel
    agent = FakeAgent([_park_event()])
    _patch_agent(monkeypatch, ctx.kernel, agent)
    async def park():
        return [f async for f in ctx.kernel.stream_events("check", "req", ctx.session.session_id, "alice", ctx.token)]
    frames = asyncio.run(park())
    pending = CONFIRMATION_REGISTRY.peek_parked(ctx.session.session_id)
    agent.events = []
    client = TestClient(create_app())
    body = {"session_id": ctx.session.session_id, "confirm_id": frames[-1]["confirm_id"], "decision": "deny"}
    headers = {"X-User-ID": "bob", "Authorization": "Bearer " + ctx.mint(username="bob", sub="bob-sub", authentication_source="development")}
    assert client.post("/api/v2/chat/confirm", json=body, headers=headers).status_code == 401
    assert not pending.claimed and pending.requester_delegated_token == ctx.token
    headers["Authorization"] = "Bearer " + ctx.mint(username="bob", sub="bob-sub")
    response = client.post("/api/v2/chat/confirm", json=body, headers=headers)
    assert response.status_code == 200 and '"denied"' in response.text
    assert pending.requester_identity is None and pending.requester_delegated_token is None


@pytest.mark.parametrize("close_at", ["first_frame", "active_stream", "setup"])
def test_resume_disconnect_always_releases_identity_context(delegated_kernel, monkeypatch, close_at):
    import asyncio
    from agent_service.services.hitl_confirmations import CONFIRMATION_REGISTRY
    from test_hitl_confirmations import FakeAgent, _patch_agent, _park_event
    ctx = delegated_kernel
    _patch_agent(monkeypatch, ctx.kernel, FakeAgent([_park_event()]))

    async def run():
        frames = [f async for f in ctx.kernel.stream_events("check", "req", ctx.session.session_id, "alice", ctx.token)]
        pending = CONFIRMATION_REGISTRY.claim(ctx.session.session_id, frames[-1]["confirm_id"], 600)
        class CancelAgent(FakeAgent):
            async def reply_stream(self, inputs):
                raise asyncio.CancelledError()
                yield
        _patch_agent(monkeypatch, ctx.kernel, CancelAgent())
        if close_at == "setup":
            async def canceled(*args):
                raise asyncio.CancelledError()
            monkeypatch.setattr(ctx.kernel, "ensure_agent", canceled)
        stream = ctx.kernel.resume_confirmation(ctx.session.session_id, pending, "deny", "alice", "req", ctx.token)
        try:
            await anext(stream)
            if close_at == "active_stream":
                await anext(stream)
        except asyncio.CancelledError:
            pass
        finally:
            await stream.aclose()
        _assert_no_identity_context()
        assert pending.requester_identity is None and pending.requester_delegated_token is None
        assert not CONFIRMATION_REGISTRY.is_parked(ctx.session.session_id, 600)
    asyncio.run(run())


def test_live_check_does_not_refresh_or_reinterpret_expired_identity(identities, monkeypatch):
    verifier, mint = identities
    identity = verifier.verify(mint())
    monkeypatch.setattr("agent_service.services.delegated_identity.time.time", lambda: identity.expires_at + 1)
    with pytest.raises(DelegatedIdentityError):
        identity.require_live()
