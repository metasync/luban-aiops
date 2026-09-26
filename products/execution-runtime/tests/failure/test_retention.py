"""Signed admission time bounds, retention sweep, and presentation independence."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import time
from uuid import uuid4

import pytest

from execution_runtime.services.execution_ledger import ExecutionLedger
from execution_runtime.services.execution_migration import connect
from execution_runtime.services.execution_protocol import iso
from execution_runtime.services.execution_signing import sign_envelope
from support.ledger import body, claim_count, register, signed_request
from test_admission import PATH, ledger, outcome
from test_harness_contract import post


class FixedClockConnection:
    def __init__(self, connection, now):
        self.connection, self.now = connection, now

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, query, params=None):
        if query == "SELECT clock_timestamp()":
            return self.connection.execute("SELECT %s::timestamptz", (self.now,))
        return self.connection.execute(query, params)


@dataclass
class FixedClock:
    now: object

    def __call__(self, dsn):
        return FixedClockConnection(connect(dsn), self.now)


@pytest.mark.parametrize("case,offset,expected", [
    pytest.param("before_expiry", -1, "none", marks=pytest.mark.scenario("F-28", "before_expiry")),
    pytest.param("at_expiry", 0, "request_expired", marks=pytest.mark.scenario("F-28", "at_expiry")),
    pytest.param("future", -601_000_000, "request_not_yet_valid", marks=pytest.mark.scenario("F-28", "future")),
])
def test_database_clock_exact_inequality(ledger_database, services, case, offset, expected, evidence):
    db = ledger_database
    with db.connect() as conn:
        now = conn.execute("SELECT clock_timestamp()").fetchone()[0]
    expires = now + timedelta(seconds=600)
    envelope = signed_request(services.token, db.epoch, requested_at=iso(now), expires_at=iso(expires))
    register(db, envelope)
    clock = FixedClock(expires + timedelta(microseconds=offset))
    store = ExecutionLedger(db.dsn, services.token, db.epoch, admission_enabled=True, connection_factory=clock)
    decision = store.claim(envelope, "clock-original")
    assert decision.reason == expected
    assert bool(decision.permit) == (case == "before_expiry")
    assert claim_count(db, envelope["execution_id"]) == int(case == "before_expiry")
    evidence(claim_count=int(case == "before_expiry"), mode=case,
             asserted="requested_at <= DB clock < expires_at; exact equality refuses")


@pytest.mark.scenario("F-28", "at_expiry")
def test_production_clock_expiry_after_b0_never_dispatches(ledger_database, services, evidence):
    db = ledger_database
    gate = services.barrier("B0")
    target = services.http()
    gateway = services.http(upstream=target.url)
    worker = services.worker(gateway=gateway, database=db, hooks=gate)
    with db.connect() as conn:
        now = conn.execute("SELECT clock_timestamp()").fetchone()[0]
    expiry = now + timedelta(seconds=1)
    envelope = signed_request(services.token, db.epoch, requested_at=iso(now), expires_at=iso(expiry))
    register(db, envelope)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(outcome, worker, services.token, envelope)
        gate.wait("B0")
        deadline = time.monotonic() + 5
        with db.connect() as conn:
            while conn.execute("SELECT clock_timestamp() < %s", (expiry,)).fetchone()[0]:
                assert time.monotonic() < deadline
                time.sleep(0.01)
        gate.release("B0")
        reply = pending.result(timeout=10)
    assert reply.status_code == 410 and reply.json()["reason_code"] == "request_expired"
    recovery = reply.json()["recovery"]
    assert recovery["state"] == "not_dispatched" and recovery["run_stopped"]
    assert ledger(db, services.token).claim(envelope, "delayed-original").permit is None
    facts = services.facts(gateway, target)
    assert facts == {"gateway_attempts": 0, "target_accepted": 0, "target_effects": 0}
    evidence(**facts, claim_count=0, barriers=["B0"], asserted="expiry evaluated after barrier using real database time")


@pytest.mark.parametrize("case", [pytest.param(case, marks=pytest.mark.scenario("F-28", case))
                                  for case in ("lifetime", "legacy", "version", "epoch")])
def test_unsupported_lifetime_version_or_epoch_never_sends(ledger_database, services, case, evidence):
    db = ledger_database
    original = signed_request(services.token, db.epoch)
    register(db, original)
    envelope = dict(original)
    if case == "lifetime":
        envelope["expires_at"] = iso(__import__("datetime").datetime.fromisoformat(
            envelope["requested_at"].replace("Z", "+00:00")) + timedelta(seconds=901))
    elif case == "legacy":
        for field in ("protocol_version", "run_id", "admission_epoch", "expires_at"):
            envelope.pop(field)
    elif case == "version":
        envelope["protocol_version"] = 4
    else:
        # Process configuration is independent of the restored/stored epoch.
        pass
    envelope["signature"] = sign_envelope(envelope, services.token)
    target = services.http()
    gateway = services.http(upstream=target.url)
    settings = {"EXECUTION_ADMISSION_EPOCH": str(uuid4())} if case == "epoch" else {}
    worker = services.worker(gateway=gateway, database=db, **settings)
    reply = post(worker.url, services.token, body(envelope, services.token), PATH)
    assert reply.json()["kind"] == "refused"
    assert reply.json()["reason_code"] in {"lifetime_invalid", "protocol_unsupported", "epoch_mismatch"}
    facts = services.facts(gateway, target)
    assert facts == {"gateway_attempts": 0, "target_accepted": 0, "target_effects": 0}
    assert claim_count(db, original["execution_id"]) == 0
    evidence(**facts, claim_count=0, mode=case)


@pytest.mark.parametrize("case", [pytest.param(case, marks=pytest.mark.scenario("F-29", case))
                                  for case in ("session_delete", "presentation_sweep", "cache_eviction")])
def test_presentation_loss_never_releases_dispatch_authority(ledger_database, services, case, evidence):
    """The durable ledger is independent of the presentation/session store.

    A session delete, the presentation store's ``requested_at`` sweep, or an
    in-memory cache eviction must never remove the claim/intent/run, resurrect
    authority, or let a replay dispatch again (SPEC-063 R-7a, no session FK
    cascade). The ledger horizon is driven by signed ``expires_at``, never by
    the presentation ``requested_at`` the sweep keys on.
    """
    from execution_runtime.services.execution_records import (
        InMemoryExecutionRecordStore, RETENTION_WINDOW_DAYS, _EXECUTION_RECORDS_DDL,
        _SWEEP_EXPIRED, _SWEEP_LIMIT, make_execution_record)
    db, key = ledger_database, services.token
    envelope = signed_request(key, db.epoch)
    register(db, envelope)
    store = ledger(db, key)
    assert store.claim(envelope, "harness-original").permit is not None
    assert claim_count(db, envelope["execution_id"]) == 1
    record = make_execution_record(envelope)
    if case == "cache_eviction":
        # An ephemeral presentation cache holds a closed receipt; evicting it
        # cannot matter because the durable ledger is the only authority.
        cache = InMemoryExecutionRecordStore()
        cache.close_execution(record, {"status": "succeeded",
                                       "completed_at": envelope["requested_at"]}, True)
        cache._by_key.clear()
    else:
        with db.connect() as conn:
            conn.execute(_EXECUTION_RECORDS_DDL)
            conn.execute("INSERT INTO execution_records (confirm_id,call_id,session_id,"
                         "execution_id,tool_name,requested_at,status) VALUES (%s,%s,%s,%s,%s,%s,'requested')",
                         tuple(record[name] for name in ("confirm_id", "call_id", "session_id",
                                                         "execution_id", "tool_name", "requested_at")))
            if case == "presentation_sweep":
                conn.execute("UPDATE execution_records SET requested_at = now() - interval '40 days' "
                             "WHERE confirm_id=%s AND call_id=%s", (record["confirm_id"], record["call_id"]))
                conn.execute(_SWEEP_EXPIRED, {"retention_days": RETENTION_WINDOW_DAYS,
                                              "sweep_limit": _SWEEP_LIMIT})
            else:
                conn.execute("DELETE FROM execution_records WHERE session_id=%s", (envelope["session_id"],))
            assert conn.execute("SELECT count(*) FROM execution_records WHERE execution_id=%s",
                                (envelope["execution_id"],)).fetchone()[0] == 0
    # The run and its durable claim survive every presentation-layer loss.
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM execution_runs WHERE run_id=%s",
                            (envelope["run_id"],)).fetchone()[0] == 1
    assert claim_count(db, envelope["execution_id"]) == 1
    replay = store.claim(envelope, "replay")
    assert replay.permit is None and replay.reason == "metadata_replay"
    evidence(claim_count=1, mode=case, original_request_id="harness-original", replay_request_id="replay",
             asserted="presentation delete/sweep/eviction cannot release durable dispatch authority")


@pytest.mark.scenario("F-30", "expired_replay")
def test_expired_replay_rejected_before_and_after_retention_sweep(ledger_database, services, evidence):
    """A signed-expired request is refused, then reclaimed by the bounded sweep.

    Sweeping the elapsed row never resets the execution right: the expired
    replay is refused before the sweep (``request_expired``) and after it
    (``request_missing``), and no claim is ever minted (SPEC-063 R-7a).
    """
    db, key = ledger_database, services.token
    now = datetime.now(timezone.utc)
    envelope = signed_request(key, db.epoch,
                              requested_at=iso(now - timedelta(days=40)),
                              expires_at=iso(now - timedelta(days=40) + timedelta(seconds=600)))
    register(db, envelope)
    store = ledger(db, key)
    before = store.claim(envelope, "expired-original")
    assert before.permit is None and before.reason == "request_expired"
    assert claim_count(db, envelope["execution_id"]) == 0
    swept = store.retention_sweep()
    assert swept["intents"] >= 1
    after = store.claim(envelope, "expired-replay")
    assert after.permit is None and after.reason == "request_missing"
    assert claim_count(db, envelope["execution_id"]) == 0
    evidence(claim_count=0, mode="expired_replay", original_request_id="expired-original",
             replay_request_id="expired-replay",
             asserted="expired replay refused before and after sweep; retention never resets the right")


@pytest.mark.scenario("F-30", "remint")
def test_approved_call_id_remint_refused_within_validity_horizon(ledger_database, services, evidence):
    """A fresh execution id under the same approved-call identity is refused.

    Within the validity horizon the original ``confirm_id``/``call_id`` is
    already bound to its registered intent, so a reminted envelope cannot mint
    a second attempt; the original stays claimable and unchanged (R-7a).
    """
    db, key = ledger_database, services.token
    envelope = signed_request(key, db.epoch)
    register(db, envelope)
    store = ledger(db, key)
    reminted = {**envelope, "execution_id": str(uuid4())}
    reminted["signature"] = sign_envelope(reminted, key)
    refused = store.claim(reminted, "remint")
    assert refused.permit is None and refused.reason == "identity_conflict"
    assert claim_count(db, reminted["execution_id"]) == 0
    assert store.claim(envelope, "harness-original").permit is not None
    assert claim_count(db, envelope["execution_id"]) == 1
    with db.connect() as conn:
        assert conn.execute("SELECT request_envelope FROM execution_intents WHERE execution_id=%s",
                            (envelope["execution_id"],)).fetchone()[0] == envelope
    evidence(claim_count=1, mode="remint", original_request_id="harness-original", replay_request_id="remint",
             asserted="reminted approved-call id cannot obtain a second dispatch window")
