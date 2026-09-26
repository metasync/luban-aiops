"""Real independent agent environment: registration, verified acceptance, recovery.

These are storage/client portions of the matrix, not complete kernel/UI proofs.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from execution_runtime.services.execution_protocol import validate_observation
from execution_runtime.services.execution_signing import canonical_digest, sign_envelope
from support.agent_seam import run_probe
from support.ledger import claim_count, signed_request
from support.postgres_faults import CommitAckProxy
from test_admission import ledger, outcome


def agent(db, key, operation, **data):
    env = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "TMPDIR"}}
    env.update(OTEL_SDK_DISABLED="true", OTEL_TRACES_EXPORTER="none", OTEL_METRICS_EXPORTER="none")
    return run_probe(Path(__file__).parent / "support/agent_ledger_probe.py",
        json.dumps({"dsn": db.dsn, "key": key, "epoch": db.epoch, "operation": operation, **data}),
        env=env, watchdog=20)


def prepared(db, key):
    session_id = str(uuid4())
    root = agent(db, key, "create", session_id=session_id, owner_user_id="test-owner")
    assert root["ok"]
    return signed_request(key, db.epoch, run_id=root["run_id"], session_id=session_id)


@pytest.mark.scenario("F-01", "action")
def test_agent_registers_and_accepts_before_dependent_dispatch(services, ledger_database, evidence):
    db, key = ledger_database, services.token
    envelope = prepared(db, key)
    target = services.http()
    gateway = services.http(upstream=target.url)
    worker = services.worker(gateway=gateway, database=db)
    first = agent(db, key, "exchange", envelope=envelope, worker_url=worker.url)
    assert first["ok"], first.get("reason")
    validate_observation(first["accepted"], envelope, key)
    assert first["accepted"]["receipt_digest"] == canonical_digest(first["recovery"]["receipt"])
    independent = ledger(db, key).lookup(envelope["execution_id"])
    assert independent["receipt"] == first["recovery"]["receipt"]
    assert {fact["kind"] for fact in independent["observations"]} == {
        "claim_committed", "worker_result", "response_accepted"
    }
    next_call = signed_request(key, db.epoch, run_id=envelope["run_id"], session_id=envelope["session_id"])
    second = agent(db, key, "exchange", envelope=next_call, worker_url=worker.url, attempt_id="next-original")
    assert second["ok"] and first["pid"] != second["pid"] != worker.pid
    facts = services.facts(gateway, target)
    assert facts == {"gateway_attempts": 2, "target_accepted": 2, "target_effects": 2}
    assert claim_count(db, envelope["execution_id"]) == claim_count(db, next_call["execution_id"]) == 1
    evidence(**facts, claim_count=2, worker_pids=[worker.pid], observer_pid=second["pid"],
             asserted="dependent dispatch requires exact receipt-bound original acceptance")


@pytest.mark.scenario("F-04", "reminted_id")
def test_registration_preserves_original_attempt_and_both_identities(services, ledger_database, evidence):
    db, key = ledger_database, services.token
    envelope = prepared(db, key)
    first = agent(db, key, "register", envelope=envelope)
    repeat = agent(db, key, "register", envelope=envelope, attempt_id="replay")
    assert first["ok"] and repeat["ok"]
    assert first["attempt_request_id"] == repeat["attempt_request_id"] == "agent-original"
    for changed in ({**envelope, "execution_id": str(uuid4())}, {**envelope, "args_digest": "0" * 64}):
        changed["signature"] = sign_envelope(changed, key)
        rejected = agent(db, key, "register", envelope=changed)
        assert not rejected["ok"] and rejected["reason"] == "identity_conflict"
    worker_view = ledger(db, key).lookup(envelope["execution_id"])
    reader = agent(db, key, "lookup", execution_id=envelope["execution_id"])
    agent_view = reader["recovery"]
    for view in (worker_view, agent_view):
        view.pop("as_of")
    assert agent_view == worker_view
    evidence(claim_count=0, observer_pid=reader["pid"], asserted="immutable idempotent registration and reader parity")


@pytest.mark.parametrize("mode", [pytest.param(mode, marks=pytest.mark.scenario("F-07", mode))
                                  for mode in ("commit_wrapper", "commit_wire", "rollback")])
@pytest.mark.parametrize("seed", range(20))
def test_registration_commit_failure_sends_nothing(services, ledger_database, mode, seed, evidence):
    db, key = ledger_database, services.token
    envelope = prepared(db, key)
    target = services.http()
    gateway = services.http(upstream=target.url)
    worker = services.worker(gateway=gateway, database=db)
    proxy = CommitAckProxy(db.dsn) if mode == "commit_wire" else None
    try:
        if proxy:
            proxy.armed.set()
        options = {"dsn": proxy.dsn} if proxy else {"fault": "rollback" if mode == "rollback" else "ack_lost"}
        attempted = agent(db, key, "exchange", envelope=envelope, worker_url=worker.url, **options)
        assert not attempted["ok"] and attempted["reason"] == "store_unavailable"
        if proxy:
            assert proxy.dropped.wait(5)
    finally:
        if proxy:
            proxy.close()
    reader = agent(db, key, "lookup", execution_id=envelope["execution_id"])
    view = reader["recovery"]
    assert view["availability"] == ("not_found" if mode == "rollback" else "available")
    if mode != "rollback":
        assert view["preparation_state"] == "registered" and view["state"] is None
        assert not agent(db, key, "check", envelope=envelope)["ok"]
    facts = services.facts(gateway, target)
    assert facts == {"gateway_attempts": 0, "target_accepted": 0, "target_effects": 0}
    assert claim_count(db, envelope["execution_id"]) == 0
    evidence(**facts, claim_count=0, observer_pid=reader["pid"], mode=mode)


@pytest.mark.scenario("F-21", "unclaimed_intent")
def test_unaccepted_original_blocks_next_registration_across_agent_restart(services, ledger_database, evidence):
    db, key = ledger_database, services.token
    envelope = prepared(db, key)
    assert agent(db, key, "register", envelope=envelope)["ok"]
    target = services.http()
    gateway = services.http(upstream=target.url)
    worker = services.worker(gateway=gateway, database=db)
    original = outcome(worker, key, envelope, "agent-original").json()
    assert original["kind"] == "original_result"
    next_call = signed_request(key, db.epoch, run_id=envelope["run_id"], session_id=envelope["session_id"])
    refused = agent(db, key, "register", envelope=next_call)
    assert not refused["ok"] and refused["reason"] == "predecessor_unresolved"
    stopped = agent(db, key, "stop", envelope=envelope)
    assert stopped["ok"]
    late_acceptance = agent(db, key, "accept", envelope=envelope, payload=original)
    assert not late_acceptance["ok"] and late_acceptance["reason"] == "run_stopped"
    fresh = agent(db, key, "lookup", execution_id=envelope["execution_id"])["recovery"]
    assert fresh["run_stopped"] and fresh["state"] == "result_recorded"
    assert {f["kind"] for f in fresh["observations"]} == {"claim_committed", "worker_result", "wait_expired"}
    facts = services.facts(gateway, target)
    assert facts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
    evidence(**facts, claim_count=1, asserted="recorded result alone cannot continue; stop survives late acceptance")


@pytest.mark.parametrize("field", [pytest.param(field, marks=pytest.mark.scenario("F-15", field)) for field in (
    "receipt_signature", "observation_signature", "execution_id", "run_id", "epoch", "request_digest",
    "request_id", "tool", "status", "outcome_digest", "shape",
)])
def test_agent_rejects_corrupt_original_before_acceptance(services, ledger_database, field, evidence):
    db, key = ledger_database, services.token
    envelope = prepared(db, key)
    assert agent(db, key, "register", envelope=envelope)["ok"]
    target = services.http()
    gateway = services.http(upstream=target.url)
    worker = services.worker(gateway=gateway, database=db)
    original = outcome(worker, key, envelope, "agent-original").json()
    assert original["kind"] == "original_result"
    changed = deepcopy(original)
    if field == "receipt_signature":
        changed["observation"]["receipt"]["signature"] = "0" * 64
    elif field == "observation_signature":
        changed["observation"]["signature"] = "0" * 64
    elif field in {"execution_id", "run_id", "epoch"}:
        changed["recovery"]["admission_epoch" if field == "epoch" else field] = str(uuid4())
    elif field == "request_digest":
        changed["recovery"][field] = "0" * 64
    elif field == "request_id":
        changed[field] = "not-original"
    elif field == "tool":
        changed["result"]["tool_name"] = "test.other"
    elif field == "status":
        changed["observation"]["receipt"]["status"] = "failed"
    elif field == "outcome_digest":
        changed["result"]["data"] = {"changed": True}
    else:
        changed["unexpected"] = "forbidden"
    rejected = agent(db, key, "accept", envelope=envelope, payload=changed)
    assert not rejected["ok"] and rejected["reason"] == "response_invalid"
    view = ledger(db, key).lookup(envelope["execution_id"])
    assert "response_accepted" not in {fact["kind"] for fact in view["observations"]}
    assert not agent(db, key, "check", envelope=envelope)["ok"]
    facts = services.facts(gateway, target)
    assert facts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
    evidence(**facts, claim_count=1, mode=field, asserted="corrupt original never creates acceptance")
