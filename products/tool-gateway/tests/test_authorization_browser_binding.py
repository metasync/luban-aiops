"""SPEC-070 initiating-browser binding proof for the authorization store.

Each challenge is bound at authenticated initiation to a 256-bit opaque browser
secret; the store keeps only its hash. The browser proof is required before
consuming start/state and again at the callback claim, is bounded to eight
outstanding cookies, and fails closed: a missing, mismatched, expired,
ambiguous, malformed, or oversized binding never advances the transaction.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import SecretStr

from tool_gateway.services.authorization_transactions import AuthorizationTransaction

CHALLENGE = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


def _record(challenge_id=CHALLENGE, *, seconds=600):
    now = datetime.now(timezone.utc)
    return AuthorizationTransaction(challenge_id=challenge_id, owner_namespace="issuer", owner_sub="alice",
        target="Automation", credential_set_id="user", config_generation="g1", session_id="ses", call_id="call",
        return_url="/", created_at=now, updated_at=now, expires_at=now + timedelta(seconds=seconds))


def _store():
    from tool_gateway.services.authorization_transaction_store import build_transaction_store
    return build_transaction_store(backend="memory", replicas=1)


def _bindings(challenge_id, secret):
    return {challenge_id: secret.get_secret_value()}


def test_select_browser_secret_bounds_and_validates_the_cookie_jar():
    from tool_gateway.services.authorization_transaction_store import (
        MAX_BROWSER_BINDINGS, select_browser_secret)
    secret = "opaque-browser-secret"
    assert select_browser_secret(CHALLENGE, {CHALLENGE: secret}) == secret
    # A browser may hold several outstanding challenge cookies; only the matching
    # one is returned and the others are ignored.
    assert select_browser_secret(CHALLENGE, {OTHER: "x", CHALLENGE: secret}) == secret
    # Oversized jar, missing challenge, empty/malformed secret, and malformed
    # cookie names all fail closed rather than guessing.
    assert select_browser_secret(CHALLENGE, {}) is None
    assert select_browser_secret(CHALLENGE, {OTHER: secret}) is None
    assert select_browser_secret(CHALLENGE, {CHALLENGE: ""}) is None
    assert select_browser_secret(CHALLENGE, {CHALLENGE: None}) is None
    assert select_browser_secret(CHALLENGE, {"not-a-uuid": secret}) is None
    assert select_browser_secret(CHALLENGE, "not-a-mapping") is None
    oversized = {f"{i:08d}-1111-4111-8111-111111111111": "x" for i in range(MAX_BROWSER_BINDINGS)}
    assert select_browser_secret(CHALLENGE, oversized) is None
    assert select_browser_secret(CHALLENGE, {**oversized, CHALLENGE: secret}) is None


def test_issue_start_stores_only_the_browser_secret_hash():
    async def prove():
        store = _store()
        now = datetime.now(timezone.utc)
        await store.create(_record())
        browser_secret = SecretStr("opaque-browser-secret-value")
        token = await store.issue_start(CHALLENGE, "issuer", "alice", browser_secret=browser_secret, now=now)
        assert token is not None
        state = store._secrets[CHALLENGE]
        # Only a hash is retained; the plaintext secret never lives in the store.
        assert state["browser_secret_hash"] is not None
        assert "opaque-browser-secret-value" not in repr(state)
        assert browser_secret.get_secret_value() not in str(state)
        assert state["browser_expires_at"] is not None
    asyncio.run(prove())


def test_consume_start_requires_a_matching_unexpired_browser_proof():
    async def prove():
        store = _store()
        now = datetime.now(timezone.utc)
        await store.create(_record())
        browser_secret = SecretStr("opaque-browser-secret-value")
        token = await store.issue_start(CHALLENGE, "issuer", "alice", browser_secret=browser_secret, now=now)
        good = _bindings(CHALLENGE, browser_secret)
        # A missing, empty, or mismatched proof never consumes the start handle.
        assert await store.consume_start(token, browser_bindings={}, now=now) is None
        assert await store.consume_start(token, browser_bindings=_bindings(CHALLENGE, SecretStr("wrong")), now=now) is None
        # The correct proof consumes it exactly once.
        assert await store.consume_start(token, browser_bindings=good, now=now) is not None
        assert await store.consume_start(token, browser_bindings=good, now=now) is None
    asyncio.run(prove())


def test_atomic_start_has_one_winner_and_no_separate_preparation_surface():
    async def prove():
        store = _store()
        now = datetime.now(timezone.utc)
        await store.create(_record())
        browser_secret = SecretStr("opaque-browser-secret-value")
        token = await store.issue_start(CHALLENGE, "issuer", "alice", browser_secret=browser_secret, now=now)
        good = _bindings(CHALLENGE, browser_secret)
        results = await asyncio.gather(*(store.consume_start(token, browser_bindings=good, now=now)
                                         for _ in range(8)))
        winners = [result for result in results if result is not None]
        assert len(winners) == 1
        prepared = winners[0]
        assert prepared.transaction.challenge_id == CHALLENGE
        assert not prepared.transaction.consumed  # Callback is still unclaimed.
        for secret in (token, browser_secret, prepared.state, prepared.verifier):
            assert secret.get_secret_value() not in repr(prepared)
        assert store._secrets[CHALLENGE]["start_hash"] is None
        assert not hasattr(store, "prepare_state")
        assert await store.issue_start(CHALLENGE, "issuer", "alice", browser_secret=browser_secret, now=now) is None
        claim = await store.claim_state(prepared.state, browser_bindings=good, now=now)
        assert claim.verifier == prepared.verifier
    asyncio.run(prove())


def test_browser_proof_expires_with_the_cookie_lifetime():
    async def prove():
        store = _store()
        now = datetime.now(timezone.utc)
        await store.create(_record(seconds=600))
        browser_secret = SecretStr("opaque-browser-secret-value")
        token = await store.issue_start(CHALLENGE, "issuer", "alice", browser_secret=browser_secret, now=now)
        good = _bindings(CHALLENGE, browser_secret)
        prepared = await store.consume_start(token, browser_bindings=good, now=now)
        assert prepared is not None
        state = prepared.state
        # Past the transaction/cookie lifetime the callback claim proof fails closed.
        later = now + timedelta(seconds=601)
        assert await store.claim_state(state, browser_bindings=good, now=later) is None
    asyncio.run(prove())


def test_claim_state_requires_a_matching_browser_proof():
    async def prove():
        store = _store()
        now = datetime.now(timezone.utc)
        await store.create(_record())
        browser_secret = SecretStr("opaque-browser-secret-value")
        token = await store.issue_start(CHALLENGE, "issuer", "alice", browser_secret=browser_secret, now=now)
        good = _bindings(CHALLENGE, browser_secret)
        prepared = await store.consume_start(token, browser_bindings=good, now=now)
        assert prepared is not None
        state, verifier = prepared.state, prepared.verifier
        # A wrong or absent browser proof cannot claim the callback state.
        assert await store.claim_state(state, browser_bindings={}, now=now) is None
        assert await store.claim_state(state, browser_bindings=_bindings(CHALLENGE, SecretStr("wrong")), now=now) is None
        claim = await store.claim_state(state, browser_bindings=good, now=now)
        assert claim is not None and claim.verifier.get_secret_value() == verifier.get_secret_value()
        assert await store.claim_state(state, browser_bindings=good, now=now) is None
    asyncio.run(prove())


def test_issue_start_without_a_browser_secret_is_rejected():
    async def prove():
        store = _store()
        now = datetime.now(timezone.utc)
        await store.create(_record())
        with pytest.raises(TypeError):
            await store.issue_start(CHALLENGE, "issuer", "alice", now=now)
    asyncio.run(prove())


def test_browser_reset_cancels_only_matching_owned_pending_transactions():
    async def prove():
        store = _store()
        now = datetime.now(timezone.utc)
        await store.create(_record(CHALLENGE))
        await store.create(_record(OTHER))
        secret = SecretStr("opaque-browser-secret-value")
        other_secret = SecretStr("other-browser-secret-value")
        await store.issue_start(CHALLENGE, "issuer", "alice", browser_secret=secret, now=now)
        await store.issue_start(OTHER, "issuer", "alice", browser_secret=other_secret, now=now)
        # A jar presenting only CHALLENGE's proof cancels just that challenge and
        # burns its secret state; it never revokes a credential or touches OTHER.
        canceled = await store.browser_reset(
            "issuer", "alice", browser_bindings=_bindings(CHALLENGE, secret), now=now)
        assert canceled == 1
        assert (await store.get(CHALLENGE, "issuer", "alice", now=now)).status == "canceled"
        assert (await store.get(OTHER, "issuer", "alice", now=now)).status == "pending"
        # A wrong proof, a foreign owner, a malformed jar, and an empty jar all
        # fail closed and cancel nothing.
        assert await store.browser_reset(
            "issuer", "alice", browser_bindings=_bindings(OTHER, SecretStr("wrong")), now=now) == 0
        assert await store.browser_reset(
            "issuer", "mallory", browser_bindings=_bindings(OTHER, other_secret), now=now) == 0
        assert await store.browser_reset(
            "issuer", "alice", browser_bindings={"not-a-uuid": "x"}, now=now) == 0
        assert await store.browser_reset("issuer", "alice", browser_bindings={}, now=now) == 0
        # The surviving challenge is still resettable with its own correct proof.
        assert await store.browser_reset(
            "issuer", "alice", browser_bindings=_bindings(OTHER, other_secret), now=now) == 1
        assert (await store.get(OTHER, "issuer", "alice", now=now)).status == "canceled"
    asyncio.run(prove())
