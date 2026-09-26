"""Append-only facts, reserved capacity, and independent recovery parity."""
from copy import deepcopy
from uuid import uuid4

import pytest

from execution_runtime.services.execution_protocol import observation, validate
from execution_runtime.services.execution_signing import build_receipt, canonical_digest, sign_envelope
from support.ledger import claim_count, register, signed_request
from test_admission import ledger, outcome
from test_agent_storage import agent


def views_agree(db, key, envelope):
    worker = ledger(db, key).lookup(envelope["execution_id"])
    reader = agent(db, key, "lookup", execution_id=envelope["execution_id"])
    other = reader["recovery"]
    for view in (worker, other):
        validate("execution-recovery", view)
        view.pop("as_of")
    assert worker == other
    return worker, reader["pid"]


@pytest.mark.parametrize("case", [pytest.param(case, marks=pytest.mark.scenario("F-17", case))
                                  for case in ("identical", "same_id_conflict", "different_final")])
def test_identical_and_conflicting_final_observations(ledger_database, services, case, evidence):
    db, key = ledger_database, services.token
    envelope = signed_request(key, db.epoch)
    register(db, envelope)
    target = services.http()
    gateway = services.http(upstream=target.url)
    worker = services.worker(gateway=gateway, database=db)
    original = outcome(worker, key, envelope).json()
    assert original["kind"] == "original_result"
    fact = deepcopy(original["observation"])
    store = ledger(db, key)
    if case == "identical":
        assert store.append(envelope["execution_id"], fact) == "identical"
    else:
        changed_receipt = build_receipt(envelope, "failed", {"different": True}, "harness-original", key)
        fact.update(receipt=changed_receipt, receipt_digest=canonical_digest(changed_receipt), tool_status="error")
        if case == "different_final":
            fact["observation_id"] = str(uuid4())
        fact["signature"] = sign_envelope(fact, key)
        assert store.append(envelope["execution_id"], fact) == ("conflict" if case == "same_id_conflict" else "inserted")
    view, reader_pid = views_agree(db, key, envelope)
    conflicting = case != "identical"
    assert view["integrity_conflict"] == conflicting
    assert view["state"] == ("outcome_unknown" if conflicting else "result_recorded")
    assert (view["receipt"] is None) == conflicting
    results = [f for f in view["observations"] if f["kind"] == "worker_result"]
    assert len(results) == (2 if case == "different_final" else 1)
    assert results[0] == original["observation"]
    if conflicting:
        accepted = agent(db, key, "accept", envelope=envelope, payload=original, attempt_id="harness-original")
        assert not accepted["ok"]
    assert claim_count(db, envelope["execution_id"]) == 1
    replay = outcome(worker, key, envelope, "replay").json()
    assert replay["kind"] == "status_only" and "result" not in replay
    facts = services.facts(gateway, target)
    assert facts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
    evidence(**facts, claim_count=1, mode=case, observer_pid=reader_pid,
             asserted="identical bytes remain idempotent; conflicting signed facts never overwrite originals")


@pytest.mark.scenario("F-17", "overflow")
def test_duplicate_storm_cannot_exhaust_reserved_facts(ledger_database, services, evidence):
    db, key = ledger_database, services.token
    envelope = signed_request(key, db.epoch)
    register(db, envelope)
    store = ledger(db, key)
    for index in range(66):
        fact = observation(envelope, source="worker", kind="duplicate_seen", key=key,
                           attempt_request_id="harness-original", current_request_id=f"duplicate-{index}", reason="metadata_replay")
        assert store.append(envelope["execution_id"], fact) == ("inserted" if index < 64 else "overflow")
    target = services.http()
    gateway = services.http(upstream=target.url)
    worker = services.worker(gateway=gateway, database=db)
    original = outcome(worker, key, envelope).json()
    assert original["kind"] == "original_result"
    accepted = agent(db, key, "accept", envelope=envelope, payload=original, attempt_id="harness-original")
    assert accepted["ok"]
    for kind in ("wait_expired", "run_stopped"):
        fact = observation(envelope, source="agent", kind=kind, key=key,
                           attempt_request_id="harness-original", current_request_id="agent-stop", reason="wait_expired")
        assert store.stop(envelope, fact, reason="wait_expired") == "inserted"
    changed = deepcopy(original["observation"])
    receipt = build_receipt(envelope, "failed", {"conflict": True}, "harness-original", key)
    changed.update(observation_id=str(uuid4()), receipt=receipt, receipt_digest=canonical_digest(receipt), tool_status="error")
    changed["signature"] = sign_envelope(changed, key)
    assert store.append(envelope["execution_id"], changed) == "inserted"
    with db.connect() as conn:
        state = conn.execute("SELECT ordinary_count,overflow_count,overflow,integrity_conflict FROM execution_observation_state WHERE execution_id=%s", (envelope["execution_id"],)).fetchone()
        slots = conn.execute("SELECT reserved_slot FROM execution_observations WHERE execution_id=%s AND reserved_slot IS NOT NULL", (envelope["execution_id"],)).fetchall()
        count = conn.execute("SELECT count(*) FROM execution_observations WHERE execution_id=%s", (envelope["execution_id"],)).fetchone()[0]
    assert state == (64, 2, True, True)
    assert {row[0] for row in slots} == {"claim", "result", "acceptance", "timeout", "stop", "conflict"}
    assert count == 70
    view, reader_pid = views_agree(db, key, envelope)
    assert view["state"] == "outcome_unknown" and view["integrity_conflict"] and view["run_stopped"]
    assert view["observations_truncated"] and len(view["observations"]) == 20
    assert view["receipt"] is None
    facts = services.facts(gateway, target)
    assert facts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
    evidence(**facts, claim_count=1, observer_pid=reader_pid,
             asserted="64 ordinary slots cannot crowd out any of six reserved facts; both readers retain conflict")
