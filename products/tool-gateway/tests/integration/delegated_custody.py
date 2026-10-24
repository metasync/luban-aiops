"""Disposable R-1/R-6 proof: real Postgres, isolated role, independent processes.

No external database input is accepted. Fake provider responses exercise only the
custody boundary, not production OAuth acquisition or AAP compatibility.
"""
import asyncio
import base64
import json
import multiprocessing
import os
import secrets
import subprocess
import tempfile
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from pydantic import SecretStr

from tool_gateway.services.authorization_transaction_store import (
    CallbackClaim, PostgresAuthorizationTransactionStore)
from tool_gateway.services.authorization_transactions import AuthorizationTransaction
from tool_gateway.services.custody_crypto import CustodyError, Keyring
from tool_gateway.services.delegated_custody import Owner, PostgresCustodyStore, migrate_custody, recover_custody

CALLBACK = "https://portal.test/api/v1/targets/authorizations/callback"
ALICE = Owner("issuer", "alice")
BOB = Owner("issuer", "bob")


def check(value, label):
    if not value:
        raise AssertionError(label)


def docker(*args, **kwargs):
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True, timeout=90, **kwargs).stdout.strip()


def store(args, **kwargs):
    return PostgresCustodyStore(args["db"], Keyring(args["keys"]), args["config"], args.get("set_id", "user"), CALLBACK, **kwargs)


def fixture(root):
    key_path, config_path, linkage = root / "keys.json", root / "sets.json", root / "linkage.json"
    key_path.write_text(json.dumps(dict(active_key_id="k1", recovery_epoch="epoch1",
        fingerprint_key=base64.b64encode(secrets.token_bytes(32)).decode(),
        keys={key: base64.b64encode(secrets.token_bytes(32)).decode() for key in ("k1", "k2")})))
    linkage.write_text(json.dumps([dict(owner_namespace="issuer", owner_sub=user, target_account=account)
                                  for user, account in (("alice", "42"), ("bob", "43"))]))
    entry = dict(scheme="oauth2_authorization_code", target="Automation", authorization_url="https://oauth.test/authorize",
        token_url="https://oauth.test/token", renewal_url="https://oauth.test/token", identity_url="https://oauth.test/whoami",
        client_id="client", client_secret="opaque-client-fixture", client_auth="client_secret_basic", redirect_uri=CALLBACK,
        scope="read", allowed_scopes="read write", oauth_origins="https://oauth.test", resource_origins="https://resource.test",
        pkce_method="S256", store="postgres", config_revision="1", identity_profile="json_immutable_id", identity_claim="id",
        identity_mapping_path=str(linkage))
    config_path.write_text(json.dumps({"user": entry, "other": {**entry, "target": "Other"}}))
    return dict(keys=str(key_path), config=str(config_path)), entry


async def pending(custody, owner=ALICE, *, ttl=600):
    config, linkage, keys, generation, fingerprint = await custody.sync_configuration()
    now = datetime.now(timezone.utc)
    record = AuthorizationTransaction(challenge_id=str(uuid4()), owner_namespace=owner.namespace, owner_sub=owner.subject,
        target=config.value("target"), credential_set_id=custody.set_id, config_generation=generation,
        session_id="session", call_id="call", return_url="/", created_at=now, updated_at=now,
        expires_at=now + timedelta(seconds=ttl))
    tx = PostgresAuthorizationTransactionStore(custody)
    await tx.create(record)
    start = await tx.issue_start(record.challenge_id, owner.namespace, owner.subject, now=now)
    check(start is not None, "start issuance")
    replacement = await tx.issue_start(record.challenge_id, owner.namespace, owner.subject, now=now)
    check(await tx.consume_start(start, now=now) is None, "superseded start burned")
    check(await tx.consume_start(replacement, now=now) is not None, "start consumed")
    check(await tx.consume_start(replacement, now=now) is None, "duplicate start refused")
    state, verifier = await tx.prepare_state(record.challenge_id, owner.namespace, owner.subject, now=now)
    check(await tx.prepare_state(record.challenge_id, owner.namespace, owner.subject, now=now) is None, "duplicate preparation")
    return tx, record, state, verifier


async def enroll(custody, owner=ALICE):
    tx, record, state, verifier = await pending(custody, owner)
    claim = await tx.claim_state(state, now=datetime.now(timezone.utc))
    check(claim is not None, "callback claim")
    check(await tx.claim_state(state, now=datetime.now(timezone.utc)) is None, "callback replay")
    account = "42" if owner == ALICE else "43"
    result = await tx.complete_authorization(claim, target_account=account, scopes="read",
        refresh_secret=SecretStr("opaque-refresh-fixture"), refresh_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        now=datetime.now(timezone.utc))
    check(result is not None, "atomic enrollment")
    check(await tx.complete_authorization(claim, target_account=account, scopes="read",
        refresh_secret=SecretStr("opaque-refresh-fixture"), refresh_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        now=datetime.now(timezone.utc)) is None, "completion replay")
    return result


def worker(args, action, barrier, release, output):
    async def run():
        custody = store(args)
        barrier.wait(timeout=30)
        if action == "callback":
            tx = PostgresAuthorizationTransactionStore(custody)
            claim = await tx.claim_state(SecretStr(args["state"]), now=datetime.now(timezone.utc))
        else:
            claim = await custody.begin_refresh(ALICE)
        output.put(("claimed", claim is not None))
        if claim:
            if not release.poll(30):
                raise AssertionError("parent release timeout")
            release.recv()
            if action == "callback":
                result = await tx.complete_authorization(claim, target_account="42", scopes="read",
                    refresh_secret=SecretStr("opaque-refresh-worker"), refresh_expires_at=datetime.now(timezone.utc)+timedelta(hours=1),
                    now=datetime.now(timezone.utc))
            else:
                result = await custody.complete_refresh(claim, SecretStr("opaque-rotated-worker"),
                    refresh_expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
            output.put(("completed", result is not None))
    try:
        asyncio.run(run())
    except BaseException:
        output.put(("error", False))
        raise SystemExit(1) from None


async def race(args, action, *, revoke=False, terminate=False, count=4):
    context = multiprocessing.get_context("spawn")
    barrier, output = context.Barrier(count), context.Queue()
    receiver, release = context.Pipe(duplex=False)
    children = [context.Process(target=worker, args=(args, action, barrier, receiver, output)) for _ in range(count)]
    try:
        for child in children:
            child.start()
        claims = [await asyncio.to_thread(output.get, True, 40) for _ in children]
        check(all(kind == "claimed" for kind, won in claims), "worker claims completed")
        check(sum(won for kind, won in claims) == 1, "exactly one cross-process winner")
        if revoke:
            await store(args).revoke(ALICE)
        if terminate:
            for child in children:
                if child.is_alive():
                    child.terminate()
        else:
            release.send(True)
            kind, result = await asyncio.to_thread(output.get, True, 40)
            check(kind == "completed" and result is not revoke, "late completion fence")
        for child in children:
            await asyncio.to_thread(child.join, 10)
            check(not child.is_alive(), "worker stopped")
            if not terminate:
                check(child.exitcode == 0, "worker exit")
    finally:
        release.close()
        receiver.close()
        for child in children:
            if child.is_alive():
                child.terminate()
            child.join(5)
        output.close()


def completion_boundary_worker(args, action, release, output):
    """Stop after the database commits, before completion is acknowledged upstream."""
    async def stop_after_commit(phase, when):
        if phase == f"{action}_{args['boundary']}" and when == "after":
            output.send("committed")
            if not release.poll(30):
                raise CustodyError("test_release_timeout")
            release.recv()
            raise CustodyError("injected_commit_uncertainty")

    async def run():
        custody = store(args, commit_hook=stop_after_commit)
        if action == "refresh":
            claim = await custody.begin_refresh(ALICE)
            await custody.complete_refresh(claim, SecretStr("opaque-unacknowledged-refresh"),
                refresh_expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        else:
            tx, record, state, verifier = await pending(custody)
            claim = await tx.claim_state(state, now=datetime.now(timezone.utc))
            await tx.complete_authorization(claim, target_account="42", scopes="read",
                refresh_secret=SecretStr("opaque-unacknowledged-authorization"),
                refresh_expires_at=datetime.now(timezone.utc) + timedelta(hours=1), now=datetime.now(timezone.utc))
    try:
        asyncio.run(run())
    except BaseException:
        raise SystemExit(1) from None


async def completion_visibility(args, action):
    context = multiprocessing.get_context("spawn")
    release_reader, release_writer = context.Pipe(duplex=False)
    output_reader, output_writer = context.Pipe(duplex=False)
    child = context.Process(target=completion_boundary_worker,
                            args=(args, action, release_reader, output_writer))
    try:
        child.start()
        check(await asyncio.to_thread(output_reader.poll, 30), "completion boundary reached")
        check(output_reader.recv() == "committed", "completion boundary signal")
        candidate = await store(args).metadata(ALICE)
        child.terminate()
        await asyncio.to_thread(child.join, 10)
        check(not child.is_alive(), "unacknowledged completion process terminated")
        recovered = await store(args).metadata(ALICE)
        if args["boundary"] == "stage":
            check(await store(args).begin_refresh(ALICE) is None, "staged credential cannot renew")
            return candidate is None and recovered is None
        check(candidate is not None and recovered == candidate, "published grant survives final response loss")
        await store(args).revoke(ALICE)
        check(not await store(args).cache_valid(ALICE, candidate), "revocation dominates published grant")
        return True
    finally:
        if child.is_alive():
            child.terminate()
        child.join(5)
        for endpoint in (release_reader, release_writer, output_reader, output_writer):
            endpoint.close()


class LostCommitAck:
    """Loopback PostgreSQL wire proxy: drop COMMIT's response before the client sees it."""
    def __init__(self, upstream_port):
        self.upstream_port = upstream_port
        self.armed = False
        self.dropped = False
        self.tasks = set()

    async def handle(self, client_reader, client_writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        server_writer = None
        relay = None
        try:
            server_reader, server_writer = await asyncio.open_connection("127.0.0.1", self.upstream_port)
            async def upstream():
                while data := await client_reader.read(65536):
                    server_writer.write(data)
                    await server_writer.drain()
                server_writer.close()
            relay = asyncio.create_task(upstream())
            while True:
                tag = await server_reader.readexactly(1)
                length_bytes = await server_reader.readexactly(4)
                length = int.from_bytes(length_bytes, "big")
                check(4 <= length <= 16 * 1024 * 1024, "bounded Postgres wire message")
                payload = await server_reader.readexactly(length - 4)
                if self.armed and tag == b"C" and payload == b"COMMIT\x00":
                    self.armed = False
                    self.dropped = True
                    break
                client_writer.write(tag + length_bytes + payload)
                await client_writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            client_writer.close()
            if server_writer:
                server_writer.close()
            if relay:
                relay.cancel()
                await asyncio.gather(relay, return_exceptions=True)
            self.tasks.discard(task)

    async def close(self):
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*list(self.tasks), return_exceptions=True)


async def lost_commit_ack(args, action, operation):
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(args["db"])
    proxy = LostCommitAck(parts.port)
    server = await asyncio.start_server(proxy.handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    proxied = urlunsplit((parts.scheme, parts.netloc.rsplit(":", 1)[0] + f":{port}",
                         parts.path, "sslmode=disable", ""))
    async def arm(phase, when):
        if phase == f"{action}_{operation}" and when == "before":
            proxy.armed = True
    faulted = store({**args, "db": proxied}, commit_hook=arm)
    try:
        if action == "refresh":
            claim = await faulted.begin_refresh(ALICE)
            result = faulted.complete_refresh(claim, SecretStr("opaque-wire-loss"),
                refresh_expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        else:
            tx, record, state, verifier = await pending(faulted)
            claim = await tx.claim_state(state, now=datetime.now(timezone.utc))
            result = tx.complete_authorization(claim, target_account="42", scopes="read",
                refresh_secret=SecretStr("opaque-wire-loss"),
                refresh_expires_at=datetime.now(timezone.utc) + timedelta(hours=1), now=datetime.now(timezone.utc))
        await expect_failure(result, "wire-lost acknowledgment must fail its caller")
        check(proxy.dropped, "real commit acknowledgment was dropped")
        published = operation == "complete"
        check((await store(args).metadata(ALICE) is not None) == published, "wire loss preserves only published state")
        if action == "authorization":
            status = await PostgresAuthorizationTransactionStore(store(args)).get(record.challenge_id,
                ALICE.namespace, ALICE.subject, now=datetime.now(timezone.utc))
            check(status.status == ("authorized" if published else "failed"), "atomic publication status after wire loss")
    finally:
        server.close()
        await server.wait_closed()
        await proxy.close()


async def publication_fences(args, admin_db):
    for action in ("refresh", "authorization"):
        for mutation in ("revoke", "replacement", "expiry", "cancel"):
            if action == "refresh" and mutation == "cancel":
                continue
            await enroll(store(args))
            replacement = None
            async def intervene(phase, when):
                nonlocal replacement
                if phase != f"{action}_stage" or when != "after":
                    return
                check(await store(args).metadata(ALICE) is None, "staging fences cache")
                if mutation == "revoke":
                    await store(args).revoke(ALICE)
                elif mutation == "replacement":
                    replacement = await enroll(store(args))
                elif mutation == "cancel":
                    await PostgresAuthorizationTransactionStore(store(args)).cancel(record.challenge_id,
                        ALICE.namespace, ALICE.subject, now=datetime.now(timezone.utc))
                else:
                    async with await psycopg.AsyncConnection.connect(admin_db) as conn:
                        await conn.execute("UPDATE gateway_custody.credentials SET operation_deadline=clock_timestamp()"
                                           " WHERE set_id='user' AND owner_sub='alice'")
            faulted = store(args, commit_hook=intervene)
            if action == "refresh":
                claim = await faulted.begin_refresh(ALICE)
                completion = faulted.complete_refresh(claim, SecretStr("opaque-fenced-candidate"),
                    refresh_expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
            else:
                tx, record, state, verifier = await pending(faulted)
                claim = await tx.claim_state(state, now=datetime.now(timezone.utc))
                completion = tx.complete_authorization(claim, target_account="42", scopes="read",
                    refresh_secret=SecretStr("opaque-fenced-candidate"),
                    refresh_expires_at=datetime.now(timezone.utc) + timedelta(hours=1), now=datetime.now(timezone.utc))
            await expect_failure(completion, "intervening fence prevents publication")
            check(await store(args).metadata(ALICE) == replacement, "late cleanup preserves newer authorization")


async def expect_failure(awaitable, label):
    try:
        await awaitable
    except CustodyError:
        return
    raise AssertionError(label)


# The exact version-1 prototype schema, used only to prove the explicit v1->v2
# upgrade path fences legacy unpublished operations and preserves published rows.
V1_DDL = """
SELECT pg_advisory_xact_lock(700016);
CREATE SCHEMA IF NOT EXISTS gateway_custody;
CREATE TABLE IF NOT EXISTS gateway_custody.schema_version (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton), version INTEGER NOT NULL
);
INSERT INTO gateway_custody.schema_version VALUES (TRUE, 1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS gateway_custody.key_policy (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    recovery_epoch TEXT NOT NULL, active_key_id TEXT NOT NULL,
    retired_key_ids TEXT[] NOT NULL DEFAULT '{}', fingerprint_key_hash TEXT NOT NULL,
    retired_recovery_epochs TEXT[] NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS gateway_custody.configurations (
    set_id TEXT PRIMARY KEY, target TEXT NOT NULL, revision BIGINT NOT NULL CHECK (revision > 0),
    fingerprint TEXT NOT NULL, generation TEXT NOT NULL, active BOOLEAN NOT NULL
);
CREATE TABLE IF NOT EXISTS gateway_custody.credentials (
    set_id TEXT NOT NULL REFERENCES gateway_custody.configurations(set_id), target TEXT NOT NULL,
    owner_namespace TEXT NOT NULL, owner_sub TEXT NOT NULL, config_generation TEXT NOT NULL,
    epoch BIGINT NOT NULL CHECK (epoch >= 0),
    status TEXT NOT NULL CHECK (status IN ('absent','active','in_flight','staged','revoked')),
    target_account TEXT NOT NULL DEFAULT '', scopes TEXT NOT NULL DEFAULT '',
    recovery_epoch TEXT NOT NULL, refresh_cipher BYTEA, key_id TEXT, refresh_expires_at TIMESTAMPTZ,
    operation_hash TEXT, operation_deadline TIMESTAMPTZ,
    PRIMARY KEY (set_id, target, owner_namespace, owner_sub),
    CHECK (status IN ('active','staged') OR refresh_cipher IS NULL),
    CHECK (status NOT IN ('in_flight','staged') OR (operation_hash IS NOT NULL AND operation_deadline IS NOT NULL)),
    CHECK (status <> 'active' OR (operation_hash IS NULL AND operation_deadline IS NULL))
);
CREATE TABLE IF NOT EXISTS gateway_custody.transactions (
    challenge_id TEXT PRIMARY KEY, set_id TEXT NOT NULL, target TEXT NOT NULL,
    owner_namespace TEXT NOT NULL, owner_sub TEXT NOT NULL,
    config_generation TEXT NOT NULL, credential_epoch BIGINT NOT NULL,
    session_id TEXT NOT NULL, call_id TEXT NOT NULL, return_url TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','authorized','canceled','expired','failed')),
    consumed BOOLEAN NOT NULL DEFAULT FALSE, created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL, expires_at TIMESTAMPTZ NOT NULL,
    CHECK (expires_at > created_at),
    FOREIGN KEY (set_id, target, owner_namespace, owner_sub)
        REFERENCES gateway_custody.credentials(set_id, target, owner_namespace, owner_sub)
);
CREATE TABLE IF NOT EXISTS gateway_custody.transaction_secrets (
    challenge_id TEXT PRIMARY KEY REFERENCES gateway_custody.transactions(challenge_id) ON DELETE CASCADE,
    start_hash TEXT UNIQUE, start_expires_at TIMESTAMPTZ, start_consumed BOOLEAN NOT NULL DEFAULT FALSE,
    state_hash TEXT UNIQUE, verifier_cipher BYTEA, key_id TEXT,
    callback_hash TEXT UNIQUE
);
"""


def probe_config(root, entry, set_id, *, revision="1"):
    """Write an isolated single-set config so a regression never disturbs set 'user'."""
    path = root / f"probe-{set_id}.json"
    path.write_text(json.dumps({set_id: {**entry, "config_revision": revision}}))
    return str(path)


def probe_store(args, root, entry, set_id, *, revision="1", **kwargs):
    return store({**args, "set_id": set_id, "config": probe_config(root, entry, set_id, revision=revision)}, **kwargs)


async def refresh_successor_survives_stale_cleanup(args, root, entry):
    """A rolled-back refresh claim's late cleanup must not revoke a successor
    that reused the same next epoch: cleanup is fenced by immutable attempt id."""
    sid = "refresh-race"
    custody = probe_store(args, root, entry, sid)
    await custody.initialize()
    await enroll(custody)
    meta = await custody.metadata(ALICE)
    generation, base_epoch = meta.generation, meta.epoch
    async with await psycopg.AsyncConnection.connect(args["admin_db"], row_factory=dict_row) as conn:
        saved = await (await conn.execute("SELECT refresh_cipher,key_id,refresh_expires_at,target_account,scopes"
            " FROM gateway_custody.credentials WHERE set_id=%s AND owner_sub='alice'", (sid,))).fetchone()
    # Attempt A claims the next epoch (committed), then its transaction is rolled back.
    claim_a = await custody.begin_refresh(ALICE)
    check(claim_a is not None and claim_a.epoch == base_epoch + 1 and claim_a.attempt_id,
          "refresh claim carries an immutable attempt identity")
    async with await psycopg.AsyncConnection.connect(args["admin_db"]) as conn:
        await conn.execute("UPDATE gateway_custody.credentials SET status='active',epoch=%s,attempt_id=NULL,"
            "operation_hash=NULL,operation_deadline=NULL,refresh_cipher=%s,key_id=%s,refresh_expires_at=%s,"
            "target_account=%s,scopes=%s WHERE set_id=%s AND owner_sub='alice'",
            (base_epoch, saved["refresh_cipher"], saved["key_id"], saved["refresh_expires_at"],
             saved["target_account"], saved["scopes"], sid))
    # Successor B independently claims the reused epoch with a different attempt identity.
    successor = probe_store(args, root, entry, sid)
    claim_b = await successor.begin_refresh(ALICE)
    check(claim_b is not None and claim_b.epoch == base_epoch + 1 and claim_b.attempt_id != claim_a.attempt_id,
          "successor reuses the epoch under a distinct attempt")
    # A's delayed uncertainty cleanup resumes with A's attempt identity.
    await custody._uncertain(ALICE, generation, claim_a.epoch, claim_a.attempt_id)
    result = await successor.complete_refresh(claim_b, SecretStr("opaque-successor-refresh"),
        refresh_expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    check(result is not None and result.epoch == claim_b.epoch,
          "stale attempt cleanup cannot revoke the successor refresh")


async def authorization_successor_survives_stale_cleanup(args, root, entry):
    """A rolled-back authorization completion must fail only its own challenge and
    must not revoke or fail a different challenge staged at the reused epoch."""
    sid = "auth-race"
    custody = probe_store(args, root, entry, sid)
    await custody.initialize()
    await enroll(custody)
    meta = await custody.metadata(ALICE)
    base_epoch = meta.epoch
    tx_a, rec_a, state_a, _ = await pending(custody)
    tx_b, rec_b, state_b, _ = await pending(custody)
    now = datetime.now(timezone.utc)
    claim_a = await tx_a.claim_state(state_a, now=now)
    claim_b = await tx_b.claim_state(state_b, now=now)
    check(claim_a is not None and claim_b is not None, "both challenges claimed at the same epoch")

    async def rollback_stage(phase, when):
        if phase == "authorization_stage" and when == "before":
            raise CustodyError("injected_rollback")

    faulted = PostgresAuthorizationTransactionStore(probe_store(args, root, entry, sid, commit_hook=rollback_stage))
    await expect_failure(faulted.complete_authorization(claim_a, target_account="42", scopes="read",
        refresh_secret=SecretStr("opaque-rolledback-auth"),
        refresh_expires_at=datetime.now(timezone.utc) + timedelta(hours=1), now=now),
        "authorization stage rolls back")
    status_a = await tx_a.get(rec_a.challenge_id, ALICE.namespace, ALICE.subject, now=now)
    status_b = await tx_b.get(rec_b.challenge_id, ALICE.namespace, ALICE.subject, now=now)
    check(status_a.status == "failed", "rolled-back completion fails only its own challenge")
    check(status_b.status == "pending" and status_b.consumed, "stale cleanup does not fail an unrelated challenge")
    result_b = await tx_b.complete_authorization(claim_b, target_account="42", scopes="read",
        refresh_secret=SecretStr("opaque-successor-auth"),
        refresh_expires_at=datetime.now(timezone.utc) + timedelta(hours=1), now=now)
    check(result_b is not None and result_b.epoch == base_epoch + 1,
          "successor authorization survives the stale cleanup and publishes")


async def callback_claim_cleanup_is_attempt_scoped(args, root, entry):
    """An unacknowledged old callback claim must not cancel a successor claim of
    the same challenge; cleanup is a compare-and-set on the callback operation."""
    sid = "callback-race"
    custody = probe_store(args, root, entry, sid)
    await custody.initialize()
    tx, record, state, verifier = await pending(custody)
    now = datetime.now(timezone.utc)
    claim = await tx.claim_state(state, now=now)
    check(claim is not None, "callback claim committed")
    stale = CallbackClaim(claim.transaction, SecretStr("stale-callback-operation"), claim.verifier)
    await tx._cancel_uncertain_claim(stale, now=now)
    row = await tx.get(record.challenge_id, ALICE.namespace, ALICE.subject, now=now)
    check(row is not None and row.status == "pending" and row.consumed,
          "a stale callback operation cannot cancel the live claim")
    await tx._cancel_uncertain_claim(claim, now=now)
    row = await tx.get(record.challenge_id, ALICE.namespace, ALICE.subject, now=now)
    check(row is not None and row.status == "canceled",
          "the matching unacknowledged claim cancels only its own challenge")


async def observed_generation_snapshot_is_immutable(args, root, entry):
    """A delayed invalidation of G1 must not invalidate a G2 that another
    coroutine activated on the same store while G1 awaited its connection."""
    sid = "observed-race"
    custody = probe_store(args, root, entry, sid, revision="1")
    await custody.initialize()
    await enroll(custody)
    g1 = custody._observed
    check(g1 is not None, "store observed G1")
    # Activate G2 on the same store before the delayed G1 invalidation acquires a connection.
    probe_config(root, entry, sid, revision="2")
    activated = False
    real_connection = custody.connection

    @asynccontextmanager
    async def delayed_connection():
        nonlocal activated
        if not activated:
            activated = True
            await custody.sync_configuration()
        async with real_connection() as conn:
            yield conn

    custody.connection = delayed_connection
    try:
        await custody.invalidate_observed()
    finally:
        custody.connection = real_connection
    check(custody._observed != g1, "G2 activated while the G1 invalidation was delayed")
    check(await custody.ready(), "a delayed G1 invalidation leaves G2 active")


async def migration_upgrades_v1_and_fences_legacy(args):
    """The explicit v1->v2 upgrade fences legacy unpublished rows, preserves
    published active rows, and is safe to run repeatedly."""
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(args["admin_db"])
    probe_db = "custody_migrate_probe"
    async with await psycopg.AsyncConnection.connect(args["admin_db"], autocommit=True) as conn:
        await conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(probe_db)))
        await conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(probe_db)))
    probe_url = urlunsplit((parts.scheme, parts.netloc, f"/{probe_db}", parts.query, ""))
    keyring = Keyring(args["keys"])
    try:
        async with await psycopg.AsyncConnection.connect(probe_url) as conn:
            await conn.execute(V1_DDL)
            await conn.execute("INSERT INTO gateway_custody.configurations(set_id,target,revision,fingerprint,generation,active)"
                " VALUES('user','Automation',1,'fp','g1',TRUE)")
            await conn.execute("INSERT INTO gateway_custody.credentials(set_id,target,owner_namespace,owner_sub,"
                "config_generation,epoch,status,target_account,scopes,recovery_epoch,key_id)"
                " VALUES('user','Automation','issuer','alice','g1',5,'active','42','read','epoch1','k1')")
            await conn.execute("INSERT INTO gateway_custody.credentials(set_id,target,owner_namespace,owner_sub,"
                "config_generation,epoch,status,recovery_epoch,operation_hash,operation_deadline)"
                " VALUES('user','Automation','issuer','bob','g1',3,'in_flight','epoch1','legacy-hash',"
                "clock_timestamp()+interval '60 seconds')")
        await migrate_custody(probe_url, keyring)
        async with await psycopg.AsyncConnection.connect(probe_url, row_factory=dict_row) as conn:
            version = (await (await conn.execute(
                "SELECT version FROM gateway_custody.schema_version WHERE singleton")).fetchone())["version"]
            check(version == 2, "migration records schema version 2")
            alice = await (await conn.execute(
                "SELECT status,epoch,attempt_id FROM gateway_custody.credentials WHERE owner_sub='alice'")).fetchone()
            bob = await (await conn.execute(
                "SELECT status,epoch,attempt_id FROM gateway_custody.credentials WHERE owner_sub='bob'")).fetchone()
            check(alice["status"] == "active" and alice["epoch"] == 5 and alice["attempt_id"] is None,
                  "published active row is preserved by the upgrade")
            check(bob["status"] == "revoked" and bob["epoch"] == 4 and bob["attempt_id"] is None,
                  "legacy unpublished row is fenced by the upgrade")
        await migrate_custody(probe_url, keyring)
        async with await psycopg.AsyncConnection.connect(probe_url, row_factory=dict_row) as conn:
            alice = await (await conn.execute(
                "SELECT status,epoch FROM gateway_custody.credentials WHERE owner_sub='alice'")).fetchone()
            check(alice["status"] == "active" and alice["epoch"] == 5, "repeat migration is idempotent")
    finally:
        async with await psycopg.AsyncConnection.connect(args["admin_db"], autocommit=True) as conn:
            await conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(probe_db)))


async def prove(admin_db, args, root, entry):
    for attempt in range(60):
        try:
            async with await psycopg.AsyncConnection.connect(admin_db, connect_timeout=2):
                break
        except psycopg.OperationalError:
            if attempt == 59:
                raise AssertionError("disposable Postgres readiness") from None
            await asyncio.sleep(.25)
    args["admin_db"] = admin_db
    await migrate_custody(admin_db, Keyring(args["keys"]))
    await migrate_custody(admin_db, Keyring(args["keys"]))
    password = secrets.token_urlsafe(32)
    async with await psycopg.AsyncConnection.connect(admin_db) as conn:
        await conn.execute(sql.SQL("CREATE ROLE custody_runtime LOGIN PASSWORD {}").format(sql.Literal(password)))
        await conn.execute("GRANT USAGE ON SCHEMA gateway_custody TO custody_runtime")
        await conn.execute("GRANT SELECT ON gateway_custody.schema_version,gateway_custody.key_policy TO custody_runtime")
        # Row-lock permission without authority to alter key policy values.
        await conn.execute("GRANT UPDATE(singleton) ON gateway_custody.key_policy TO custody_runtime")
        await conn.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON gateway_custody.configurations,gateway_custody.credentials,"
                           "gateway_custody.transactions,gateway_custody.transaction_secrets TO custody_runtime")
    args["db"] = admin_db.replace("postgres:", "custody_runtime:").replace(args.pop("admin_password"), password)
    custody = store(args)
    await custody.initialize()
    # The runtime role cannot create arbitrary tables or access an unrelated application's data.
    async with await psycopg.AsyncConnection.connect(admin_db) as conn:
        await conn.execute("CREATE TABLE public.unrelated_private(value TEXT)")
    for statement in ("CREATE TABLE gateway_custody.forbidden(id INT)", "SELECT * FROM public.unrelated_private",
                      "UPDATE gateway_custody.key_policy SET active_key_id='unauthorized'",
                      "DELETE FROM gateway_custody.key_policy", "UPDATE gateway_custody.schema_version SET version=99"):
        try:
            async with await psycopg.AsyncConnection.connect(args["db"]) as conn:
                await conn.execute(statement)
        except psycopg.errors.InsufficientPrivilege:
            pass
        else:
            raise AssertionError("dedicated role boundary")
    print("custody proof: isolated role and migration passed")
    metadata = await enroll(custody)
    check(await store(args).cache_valid(ALICE, metadata), "fresh process-equivalent committed read")
    check(await custody.metadata(BOB) is None, "owner isolation")
    check(await custody.metadata(Owner("other-issuer", "alice")) is None, "namespace isolation")
    other = store({**args, "set_id": "other"})
    await other.initialize()
    check(await other.metadata(ALICE) is None, "target isolation")
    await enroll(other)
    await enroll(custody, BOB)
    # Ciphertext substitution must fail, including authenticated clear metadata.
    async with await psycopg.AsyncConnection.connect(admin_db) as conn:
        rows = await (await conn.execute("SELECT owner_sub,refresh_cipher FROM gateway_custody.credentials WHERE set_id='user'"
                                       " AND owner_namespace='issuer' AND status='active' ORDER BY owner_sub")).fetchall()
        await conn.execute("UPDATE gateway_custody.credentials SET refresh_cipher=%s WHERE set_id='user' AND owner_sub='bob'", (rows[0][1],))
    await expect_failure(store(args).metadata(BOB), "ciphertext owner substitution")
    await enroll(store(args), BOB)
    async with await psycopg.AsyncConnection.connect(admin_db) as conn:
        saved_cipher = (await (await conn.execute("SELECT refresh_cipher FROM gateway_custody.credentials"
                                                " WHERE set_id='user' AND owner_sub='alice'")).fetchone())[0]
    await custody.revoke(ALICE)
    async with await psycopg.AsyncConnection.connect(admin_db) as conn:
        await conn.execute("UPDATE gateway_custody.credentials SET status='active',refresh_cipher=%s"
                           " WHERE set_id='user' AND owner_sub='alice'", (saved_cipher,))
    await expect_failure(store(args).metadata(ALICE), "old ciphertext cannot revive a revoked credential epoch")
    metadata = await enroll(custody)
    # Cancellation is not revocation and terminalization cannot manufacture success.
    tx, record, state, verifier = await pending(custody)
    now = datetime.now(timezone.utc)
    check(await tx.get(record.challenge_id, "issuer", "bob", now=now) is None, "wrong owner no oracle")
    check(not await tx.finish(record.challenge_id, "issuer", "alice", record.config_generation, "authorized", now=now), "no naked success")
    await tx.cancel(record.challenge_id, "issuer", "alice", now=now)
    check(await tx.claim_state(state, now=now) is None, "canceled state")
    check(await custody.cache_valid(ALICE, metadata), "cancel preserves grant")
    # Repeated cross-process success and revocation races.
    for iteration in range(3):
        tx, record, state, verifier = await pending(store(args))
        await race({**args, "state": state.get_secret_value()}, "callback", revoke=bool(iteration % 2))
        await enroll(store(args))
        await race(args, "refresh", revoke=bool(iteration % 2))
        await enroll(store(args))
    print("custody proof: independent callback/refresh/revocation races passed")
    await publication_fences(args, admin_db)
    await enroll(store(args))
    stale_tx, stale_record, stale_state, stale_verifier = await pending(store(args))
    await enroll(store(args))
    check(await stale_tx.claim_state(stale_state, now=datetime.now(timezone.utc)) is None,
          "superseded credential fence rejects callback before provider use")
    await race(args, "refresh", terminate=True)
    check(await store(args).begin_refresh(ALICE) is None, "crashed claimant never retried")
    check(await store(args).metadata(ALICE) is None, "crash fences cached access")
    await enroll(store(args))
    claim = await store(args).begin_refresh(ALICE)
    await store(args).abandon_refresh(claim)
    check(await store(args).begin_refresh(ALICE) is None, "lost provider response needs reauthorization")
    # The uncertain caller fails; only committed publication may survive its lost response.
    for operation in ("stage", "complete"):
        for boundary in ("before", "after"):
            await enroll(store(args))
            async def failure(phase, when):
                if phase == f"refresh_{operation}" and when == boundary:
                    raise CustodyError("injected_commit_uncertainty")
            faulted = store(args, commit_hook=failure)
            claim = await faulted.begin_refresh(ALICE)
            await expect_failure(faulted.complete_refresh(claim, SecretStr("opaque-lost-rotation"),
                refresh_expires_at=datetime.now(timezone.utc)+timedelta(hours=1)), "uncertain completion")
            published = operation == "complete" and boundary == "after"
            check((await store(args).metadata(ALICE) is not None) == published, "only publication is authoritative")
            check(await faulted.complete_refresh(claim, SecretStr("opaque-replayed-candidate"),
                refresh_expires_at=datetime.now(timezone.utc)+timedelta(hours=1)) is None, "completion cannot replay")
            if not published:
                check(await store(args).begin_refresh(ALICE) is None, "uncertain old token cannot be retried")
    # Expiry is checked at consumption even without sweeping.
    tx, record, state, verifier = await pending(store(args), ttl=1)
    await asyncio.sleep(1.05)
    check(await tx.claim_state(state, now=now) is None, "expired state rejected before sweep")
    check((await tx.get(record.challenge_id, "issuer", "alice", now=now)).status == "expired", "database time is authoritative")
    # Configuration changes/removal, stale replica, and anti-rollback tombstones.
    await enroll(store(args))
    stale_path = root / "stale.json"
    stale_path.write_text(Path(args["config"]).read_text())
    stale = store({**args, "config": str(stale_path)})
    await stale.initialize()
    live = store(args)
    await live.initialize()
    data = json.loads(Path(args["config"]).read_text())
    data["user"]["config_revision"] = "2"
    Path(args["config"]).write_text(json.dumps(data))
    await live.initialize()
    await expect_failure(stale.metadata(ALICE), "stale replica revision refused")
    stale_path.write_text("{")
    await expect_failure(stale.metadata(ALICE), "stale unreadable config refused")
    check(await live.ready(), "old observer cannot invalidate newer generation")
    await enroll(live)
    Path(args["config"]).write_text("{")
    await expect_failure(live.metadata(ALICE), "unreadable delegated config")
    Path(args["config"]).write_text(json.dumps(data))
    await expect_failure(store(args).initialize(), "same revision cannot resurrect invalidated grants")
    data["user"]["config_revision"] = "3"
    Path(args["config"]).write_text(json.dumps(data))
    await enroll(store(args))
    print("custody proof: crash/uncertain commit/configuration fencing passed")
    # Key rotation uses an authoritative write key and retains decryption compatibility.
    keys = json.loads(Path(args["keys"]).read_text())
    old_keys = root / "old-keys.json"
    old_keys.write_text(json.dumps(keys))
    rotation_tx, rotation_record, rotation_state, rotation_verifier = await pending(store(args))
    keys["active_key_id"] = "k2"
    Path(args["keys"]).write_text(json.dumps(keys))
    await expect_failure(store(args).initialize(), "unratified key mount cannot write")
    await expect_failure(store(args).rotate_key("k1"), "runtime cannot change key policy")
    await store({**args, "db": admin_db}).rotate_key("k1")
    check(await store(args).reencrypt(limit=1) == 1, "bounded key rotation")
    while await store(args).reencrypt(limit=1):
        pass
    async with await psycopg.AsyncConnection.connect(admin_db) as conn:
        key_id = (await (await conn.execute("SELECT key_id FROM gateway_custody.transaction_secrets WHERE challenge_id=%s",
                                           (rotation_record.challenge_id,))).fetchone())[0]
        check(key_id == "k2", "pending verifier reencrypted with current key")
    rotated_claim = await rotation_tx.claim_state(rotation_state, now=datetime.now(timezone.utc))
    check(rotated_claim.verifier == rotation_verifier, "rotated verifier remains bound and decryptable")
    await rotation_tx.cancel(rotation_record.challenge_id, ALICE.namespace, ALICE.subject, now=datetime.now(timezone.utc))
    await expect_failure(store({**args, "keys": str(old_keys)}).initialize(), "stale key writer")
    check(await store(args).metadata(ALICE) is not None, "rotated key decrypt")
    # Missing keys and store faults cannot serve a cached credential; revoke still works.
    valid = await store(args).metadata(ALICE)
    Path(args["keys"]).write_text("{}")
    await expect_failure(store(args).cache_valid(ALICE, valid), "missing keys deny cache")
    check(await store(args).revoke(ALICE) == "local_revoked_remote_unconfirmed", "keyless local revoke")
    Path(args["keys"]).write_text(json.dumps(keys))
    check(await store(args).metadata(ALICE) is None, "revocation survives key restoration")
    await enroll(store(args))
    keys["recovery_epoch"] = "epoch2"
    Path(args["keys"]).write_text(json.dumps(keys))
    await expect_failure(store(args).metadata(ALICE), "backup recovery epoch mismatch")
    await recover_custody(admin_db, Keyring(args["keys"]), expected_epoch="epoch1")
    await expect_failure(store(args).initialize(), "recovery requires new config revision")
    data["user"]["config_revision"] = "4"
    Path(args["config"]).write_text(json.dumps(data))
    await store(args).initialize()
    check(await store(args).metadata(ALICE) is None, "recovery cannot resurrect old grants")
    await expect_failure(store({**args, "keys": str(old_keys)}).initialize(), "restored old key mount refused")
    await enroll(store(args))
    Path(args["keys"]).write_text(json.dumps({**keys, "recovery_epoch": "epoch1"}))
    await expect_failure(recover_custody(admin_db, Keyring(args["keys"]), expected_epoch="epoch2"),
                         "previous recovery epoch cannot be reused")
    Path(args["keys"]).write_text(json.dumps(keys))
    bad_db = {**args, "db": args["db"].replace("127.0.0.1", "127.0.0.2")}
    await expect_failure(store(bad_db).cache_valid(ALICE, valid), "unavailable store denies cache")
    # Absent capabilities remain explicit at the custody boundary, without any provider call.
    data = json.loads(Path(args["config"]).read_text())
    data["no-renew"] = {k: v for k, v in data["user"].items() if k != "renewal_url"}
    data["no-identity"] = {k: v for k, v in data["user"].items() if k != "identity_url"}
    Path(args["config"]).write_text(json.dumps(data))
    no_renew = store({**args, "set_id": "no-renew"})
    await enroll(no_renew)
    await expect_failure(no_renew.begin_refresh(ALICE), "missing renewal explicitly unsupported")
    check(await no_renew.revoke(ALICE) == "local_revoked_remote_unconfirmed", "absent remote revocation stays unconfirmed")
    no_identity = store({**args, "set_id": "no-identity"})
    tx, record, state, verifier = await pending(no_identity)
    claim = await tx.claim_state(state, now=datetime.now(timezone.utc))
    await expect_failure(tx.complete_authorization(claim, target_account="42", scopes="read",
        refresh_secret=SecretStr("opaque-unverified-account"),
        refresh_expires_at=datetime.now(timezone.utc) + timedelta(hours=1), now=datetime.now(timezone.utc)),
        "missing identity evidence blocks installation")
    check(await no_identity.metadata(ALICE) is None, "mapping alone does not authorize")
    # Keep live PKCE material in the dump so its encryption assertion is nonvacuous.
    tx, record, state, verifier = await pending(store(args))
    # No opaque secret appears in a database dump, including state/verifiers and client config.
    dump_env = {**os.environ, "PGPASSWORD": password}
    dump = subprocess.run(["docker", "exec", "-e", "PGPASSWORD", args["container"], "pg_dump", "-U", "custody_runtime",
                           "-h", "127.0.0.1", "-d", "postgres", "-n", "gateway_custody", "--data-only"],
                          env=dump_env, capture_output=True, timeout=30, check=True).stdout
    for marker in (b"opaque-refresh", b"opaque-client", b"opaque-rotated", b"opaque-lost", state.get_secret_value().encode(),
                   verifier.get_secret_value().encode()):
        check(marker not in dump, "database is ciphertext/hash only")
    print("custody proof: keys, cache denial, and ciphertext-only persistence passed")
    # Immutable attempt fencing and observed-generation snapshot regressions.
    await refresh_successor_survives_stale_cleanup(args, root, entry)
    await authorization_successor_survives_stale_cleanup(args, root, entry)
    await callback_claim_cleanup_is_attempt_scoped(args, root, entry)
    await observed_generation_snapshot_is_immutable(args, root, entry)
    await migration_upgrades_v1_and_fences_legacy(args)
    print("custody proof: attempt fencing, callback CAS, observed snapshot, and v1->v2 migration passed")
    for action in ("refresh", "authorization"):
        for boundary in ("stage", "complete"):
            await enroll(store(args))
            check(await completion_visibility({**args, "boundary": boundary}, action),
                  "staged candidate became usable across replicas/restart")
        for operation in ("stage", "complete"):
            await enroll(store(args))
            await lost_commit_ack(args, action, operation)
        print(f"custody proof: {action} staging/publication crash and wire-ack boundaries passed")


def main():
    if not __debug__:
        raise SystemExit("custody proof requires assertions enabled")
    password = secrets.token_hex(24)
    name = f"luban-custody-proof-{secrets.token_hex(6)}"
    started = time.monotonic()
    try:
        docker("run", "--rm", "-d", "--name", name, "-p", "127.0.0.1::5432", "--tmpfs", "/var/lib/postgresql/data",
               "-e", "POSTGRES_PASSWORD", "postgres:16-alpine", env={**os.environ, "POSTGRES_PASSWORD": password})
        port = int(docker("port", name, "5432/tcp").rsplit(":", 1)[1])
        with tempfile.TemporaryDirectory(prefix="luban-custody-") as directory:
            args, entry = fixture(Path(directory))
            args.update(admin_password=password, container=name)
            asyncio.run(prove(f"postgresql://postgres:{password}@127.0.0.1:{port}/postgres", args, Path(directory), entry))
    except AssertionError as exc:
        raise SystemExit(f"custody proof failed: {exc}") from None
    except Exception as exc:
        raise SystemExit(f"custody proof failed: {type(exc).__name__}") from None
    finally:
        cleanup = subprocess.run(["docker", "stop", "--time", "1", name], capture_output=True, timeout=30)
    if cleanup.returncode:
        raise SystemExit("custody proof cleanup failed")
    print(f"delegated custody Postgres proof passed ({time.monotonic()-started:.1f}s); AAP compatibility unverified")


if __name__ == "__main__":
    main()
