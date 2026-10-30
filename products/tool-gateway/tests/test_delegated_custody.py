"""R-6 foundation unit gates; real concurrency lives in the disposable proof."""
import asyncio
import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import SecretStr

from tool_gateway.services.authorization_transactions import AuthorizationTransaction


def key_file(path, *, active="k1", epoch="recovery-1"):
    path.write_text(json.dumps(dict(active_key_id=active, recovery_epoch=epoch,
        fingerprint_key=base64.b64encode(b"f" * 32).decode(),
        keys={"k1": base64.b64encode(b"1" * 32).decode(), "k2": base64.b64encode(b"2" * 32).decode()})))
    return str(path)


def test_ciphertext_binding_and_key_lifecycle(tmp_path):
    from tool_gateway.services.custody_crypto import Keyring, CustodyError
    path = tmp_path / "keys.json"
    key_file(path)
    keyring = Keyring(str(path))
    binding = dict(owner_namespace="issuer", owner_sub="alice", target="Automation", set_id="user",
                   config_generation="g1", credential_epoch=1, scopes="read", target_account="42")
    blob = keyring.encrypt(SecretStr("opaque-refresh"), "refresh", binding)
    assert b"opaque-refresh" not in blob
    assert keyring.decrypt(blob, "refresh", binding).get_secret_value() == "opaque-refresh"
    assert keyring.encrypt(SecretStr("opaque-refresh"), "refresh", binding) != blob
    for key in binding:
        with pytest.raises(CustodyError):
            keyring.decrypt(blob, "refresh", {**binding, key: "substitution"})
    with pytest.raises(CustodyError):
        keyring.decrypt(blob, "verifier", binding)
    with pytest.raises(CustodyError):
        keyring.decrypt(blob[:-1] + bytes([blob[-1] ^ 1]), "refresh", binding)
    key_file(path, active="k2")
    assert keyring.decrypt(blob, "refresh", binding).get_secret_value() == "opaque-refresh"
    assert keyring.encrypt(SecretStr("opaque-refresh"), "refresh", binding) != blob
    key_file(path, epoch="recovery-2")
    with pytest.raises(CustodyError):
        keyring.decrypt(blob, "refresh", binding)
    path.write_text('{"keys":{},"keys":{}}')
    with pytest.raises(CustodyError):
        keyring.decrypt(blob, "refresh", binding)
    path.unlink()
    with pytest.raises(CustodyError):
        keyring.decrypt(blob, "refresh", binding)


def test_unknown_key_and_secret_safe_failure(tmp_path):
    from tool_gateway.services.custody_crypto import Keyring, CustodyError
    path = tmp_path / "keys.json"
    key_file(path)
    ring = Keyring(str(path))
    blob = ring.encrypt(SecretStr("opaque-refresh"), "refresh", {})
    data = json.loads(path.read_text())
    data["keys"]["k1"] = base64.b64encode(b"x" * 32).decode()
    path.write_text(json.dumps(data))
    with pytest.raises(CustodyError) as failure:
        ring.decrypt(blob, "refresh", {})
    assert "opaque-refresh" not in str(failure.value)
    data["keys"].pop("k1")
    path.write_text(json.dumps(data))
    with pytest.raises(CustodyError):
        ring.snapshot()


def test_memory_transactions_and_fail_closed_factory():
    from tool_gateway.services.authorization_transaction_store import build_transaction_store
    async def prove():
        ticks = [0.0]
        store = build_transaction_store(backend="memory", replicas=1, clock=lambda: ticks[0])
        now = datetime.now(timezone.utc)
        record = AuthorizationTransaction(challenge_id="11111111-1111-4111-8111-111111111111",
            owner_namespace="issuer", owner_sub="alice", target="Automation", credential_set_id="user",
            config_generation="g1", session_id="ses", call_id="call", return_url="/",
            created_at=now, updated_at=now, expires_at=now + timedelta(seconds=600))
        await store.create(record)
        with pytest.raises(ValueError):
            await store.create(record)
        assert await store.get(record.challenge_id, "issuer", "bob", now=now) is None
        assert await store.claim_callback(record.challenge_id, "issuer", "alice", "bad", now=now) is None
        claims = await asyncio.gather(*(store.claim_callback(record.challenge_id, "issuer", "alice", "g1", now=now)
                                        for _ in range(10)))
        assert sum(claim is not None for claim in claims) == 1
        assert not await store.finish(record.challenge_id, "issuer", "alice", "g1", "authorized", now=now)
        await store.cancel(record.challenge_id, "issuer", "alice", now=now)
        assert not await store.finish(record.challenge_id, "issuer", "alice", "g1", "failed", now=now)
        assert (await store.get(record.challenge_id, "issuer", "alice", now=now)).status == "canceled"
        other = record.model_copy(update={"challenge_id": "22222222-2222-4222-8222-222222222222"})
        await store.create(other)
        browser = SecretStr("opaque-browser-secret")
        jar = {other.challenge_id: browser.get_secret_value()}
        start = await store.issue_start(other.challenge_id, "issuer", "alice", browser_secret=browser, now=now)
        prepared = await store.consume_start(start, browser_bindings=jar, now=now)
        assert prepared is not None
        assert await store.consume_start(start, browser_bindings=jar, now=now) is None
        state, verifier = prepared.state, prepared.verifier
        claim = await store.claim_state(state, browser_bindings=jar, now=now)
        assert claim.verifier.get_secret_value() == verifier.get_secret_value()
        assert await store.claim_state(state, browser_bindings=jar, now=now) is None
        assert state.get_secret_value() not in repr(claim)
        ticks[0] = 600.0
        assert await store.claim_callback(other.challenge_id, "issuer", "alice", "g1", now=now) is None
        assert (await store.get(other.challenge_id, "issuer", "alice", now=now)).status == "expired"
        assert await store.ready()
        await store.close()
    asyncio.run(prove())
    for kwargs in (dict(backend="memory", replicas=2), dict(backend="redis", replicas=1),
                   dict(backend="postgres", replicas=2), dict(backend="memory", replicas=True)):
        with pytest.raises(ValueError):
            build_transaction_store(**kwargs)


@pytest.mark.parametrize("elapsed,usable", [(59.999, True), (60.0, False), (60.001, False)])
def test_memory_start_exact_boundary(elapsed, usable):
    from tool_gateway.services.authorization_transaction_store import build_transaction_store
    async def prove():
        ticks = [0.0]
        store = build_transaction_store(clock=lambda: ticks[0])
        now = datetime.now(timezone.utc)
        record = AuthorizationTransaction(challenge_id="11111111-1111-4111-8111-111111111111",
            owner_namespace="issuer", owner_sub="alice", target="Automation", credential_set_id="user",
            config_generation="g1", session_id="ses", call_id="call", return_url="/",
            created_at=now, updated_at=now, expires_at=now + timedelta(seconds=600))
        await store.create(record)
        browser = SecretStr("opaque-browser-secret")
        jar = {record.challenge_id: browser.get_secret_value()}
        old = await store.issue_start(record.challenge_id, "issuer", "alice", browser_secret=browser, now=now)
        start = await store.issue_start(record.challenge_id, "issuer", "alice", browser_secret=browser, now=now)
        assert await store.consume_start(old, browser_bindings=jar, now=now) is None
        ticks[0] = elapsed
        assert (await store.consume_start(start, browser_bindings=jar, now=now) is not None) == usable
        assert await store.consume_start(start, browser_bindings=jar, now=now) is None
    asyncio.run(prove())


def test_transaction_envelope_binds_every_routing_dimension(tmp_path):
    from tool_gateway.services.authorization_transaction_store import transaction_binding
    from tool_gateway.services.custody_crypto import CustodyError, Keyring
    ring = Keyring(key_file(tmp_path / "keys.json"))
    row = dict(challenge_id="challenge", set_id="set", target="target", owner_namespace="issuer", owner_sub="alice",
               config_generation="g1", credential_epoch=1, session_id="session", call_id="call", return_url="/",
               browser_secret_hash="browser-hash", start_attempt=1,
               expires_at=datetime.now(timezone.utc) + timedelta(seconds=600))
    binding = transaction_binding(row)
    ciphertext = ring.encrypt(SecretStr("opaque-verifier"), "verifier", binding)
    for dimension in binding:
        with pytest.raises(CustodyError):
            ring.decrypt(ciphertext, "verifier", {**binding, dimension: "substituted"})


def test_attempt_scoped_local_blocks_are_independent(tmp_path):
    """Cleaning or completing one uncertain attempt must never clear another
    unresolved attempt's process-local block for the same owner."""
    from tool_gateway.services.custody_crypto import Keyring
    from tool_gateway.services.delegated_custody import Owner, PostgresCustodyStore
    store = PostgresCustodyStore("postgresql://unused", Keyring(key_file(tmp_path / "keys.json")),
                                 "cfg", "user", "https://portal.test/callback")
    alice = Owner("issuer", "alice")
    bob = Owner("issuer", "bob")
    assert not store._is_blocked(alice)
    store._blocked.add((alice, "attempt-1"))
    store._blocked.add((alice, "attempt-2"))
    assert store._is_blocked(alice)
    assert not store._is_blocked(bob)
    store._blocked.discard((alice, "attempt-1"))
    assert store._is_blocked(alice), "a resolved attempt must not clear another attempt's block"
    store._blocked.discard((alice, "attempt-2"))
    assert not store._is_blocked(alice)


def test_custody_schema_is_explicitly_versioned_with_attempt_invariants():
    """Attempt fencing ships as an explicit versioned migration, never runtime DDL."""
    from tool_gateway.services import custody_schema as schema
    assert schema.SCHEMA_VERSION == 3
    assert "attempt_id TEXT" in schema.DDL
    assert "credentials_attempt_fenced" in schema.DDL
    assert "credentials_attempt_cleared" in schema.DDL
    # The v1->v2 upgrade adds the column, fences legacy unpublished rows, and bumps the version.
    assert "ADD COLUMN IF NOT EXISTS attempt_id" in schema.UPGRADE_V1_TO_V2
    assert "status IN ('in_flight','staged')" in schema.UPGRADE_V1_TO_V2
    assert "SET version=2" in schema.UPGRADE_V1_TO_V2


def test_custody_schema_v3_adds_browser_binding_fields():
    """SPEC-070 browser handoff: the v3 migration adds the per-challenge browser
    binding fields and fences incompatible pending prototype transactions rather
    than decrypting a v2-bound verifier under a guessed binding."""
    from tool_gateway.services import custody_schema as schema
    # A fresh database is created at version 3 with the browser-binding columns.
    assert "VALUES (TRUE, 3)" in schema.DDL
    assert "browser_secret_hash TEXT" in schema.DDL
    assert "browser_expires_at TIMESTAMPTZ" in schema.DDL
    assert "start_attempt INTEGER NOT NULL DEFAULT 0" in schema.DDL
    # The explicit v2->v3 upgrade adds the same columns, fences every pending
    # prototype transaction (no browser binding; v2 verifier AAD), and bumps the
    # recorded version. Published credentials are never touched.
    upgrade = schema.UPGRADE_V2_TO_V3
    assert "ADD COLUMN IF NOT EXISTS browser_secret_hash" in upgrade
    assert "ADD COLUMN IF NOT EXISTS browser_expires_at" in upgrade
    assert "ADD COLUMN IF NOT EXISTS start_attempt" in upgrade
    assert "status='failed'" in upgrade and "status='pending'" in upgrade
    assert "SET version=3" in upgrade
    assert "credentials" not in upgrade


def test_refresh_claim_carries_immutable_attempt_identity():
    from tool_gateway.services.delegated_custody import Owner, RefreshClaim
    claim = RefreshClaim(Owner("issuer", "alice"), "g1", 3, "attempt-abc",
                         SecretStr("opaque-operation"), SecretStr("opaque-refresh"))
    assert claim.attempt_id == "attempt-abc"
    with pytest.raises(Exception):
        RefreshClaim(Owner("issuer", "alice"), "g1", 3, SecretStr("op"), SecretStr("rf"))
