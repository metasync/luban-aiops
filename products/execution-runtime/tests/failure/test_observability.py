"""Operational observability surface proofs (SPEC-063 F-34 / R-7c).

The readiness and metrics endpoints must publish bounded, fixed-cardinality
operational signal -- actual admission availability, duplicate/conflict totals,
the unresolved count and its oldest DATABASE-clock age, write failures, and drain
state -- while never triggering execution work and never labeling on identity,
session, or request values. Each case establishes one fault or state condition,
then proves the surface reflects it and dispatches nothing extra.

These are development/harness proofs against the disposable real Postgres and a
real worker process; the metric text is parsed with a bounded helper that reads
one sample at a time and never echoes raw request data into evidence.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from execution_runtime.services.execution_signing import sign_envelope
from support.ledger import body, claim_count, register, signed_request
from support.postgres_faults import FaultFactory
from test_admission import ledger, outcome
from test_harness_contract import post

PATH = "/api/v1/executions/handoff"


def scrape(worker, path="/metrics"):
    with httpx.Client(trust_env=False, timeout=10) as client:
        return client.get(worker.url + path)


def metric_value(text, name, label=None):
    """Read one sample from a Prometheus text body (bounded, no raw echo)."""
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        sample, _, value = line.rpartition(" ")
        if not value:
            continue
        if label is None and sample == name:
            return float(value)
        if label is not None and sample.startswith(name + "{") and label in sample:
            return float(value)
    return None


@pytest.mark.parametrize("case", [pytest.param(case, marks=pytest.mark.scenario("F-34", case))
                                  for case in ("store_failure", "duplicate_storm", "conflict",
                                               "unknown_age", "receipt_failure")])
def test_health_and_metrics_do_not_trigger_work(services, ledger_database, case, evidence):
    db, key = ledger_database, services.token
    target = services.http()
    gateway = services.http(upstream=target.url)

    if case == "store_failure":
        # A worker with no reachable store still serves /metrics and /health/ready
        # (fail open), publishes admission unavailable plus the write failure, and
        # dispatches nothing. Scraping is not execution work.
        worker = services.worker(gateway=gateway, database=db,
                                 EXECUTION_STATE_STORE_BACKEND="memory", EXECUTION_STATE_DB_URL="")
        before = services.facts(gateway, target)
        ready = scrape(worker, "/health/ready")
        assert ready.status_code == 503 and ready.json()["actual_backend"] == "unavailable"
        assert metric_value(scrape(worker).text, "execution_admission_available") == 0
        envelope = signed_request(key, db.epoch)
        assert outcome(worker, key, envelope).json()["kind"] == "unavailable"
        after = scrape(worker)
        assert metric_value(after.text, "execution_store_write_failures_total") >= 1
        assert claim_count(db, envelope["execution_id"]) == 0
        facts = services.facts(gateway, target)
        assert facts == before == {"gateway_attempts": 0, "target_accepted": 0, "target_effects": 0}
        evidence(**facts, claim_count=0, worker_pids=[worker.pid], mode=case, negative_detected=True,
                 asserted="store outage fails open on health/metrics, marks admission unavailable, dispatches nothing")
        return

    if case == "duplicate_storm":
        worker = services.worker(gateway=gateway, database=db)
        envelope = signed_request(key, db.epoch)
        register(db, envelope)
        assert outcome(worker, key, envelope, "storm-original").json()["kind"] == "original_result"
        before = services.facts(gateway, target)
        for index in range(5):
            replay = outcome(worker, key, envelope, f"storm-dup-{index}")
            assert replay.status_code == 200 and replay.json()["kind"] == "status_only"
            assert "result" not in replay.json()
        text = scrape(worker).text
        assert metric_value(text, "execution_duplicate_claims_total") >= 5
        # Fixed cardinality: no identity/session/confirm value is ever a label.
        for identity in (envelope["execution_id"], envelope["session_id"], envelope["confirm_id"]):
            assert identity not in text
        assert claim_count(db, envelope["execution_id"]) == 1
        facts = services.facts(gateway, target)
        assert facts == before == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
        evidence(**facts, claim_count=1, worker_pids=[worker.pid], mode=case,
                 asserted="a duplicate storm is answered metadata-only; the duplicate counter moves and no identity is labeled")
        return

    if case == "conflict":
        worker = services.worker(gateway=gateway, database=db)
        envelope = signed_request(key, db.epoch)
        register(db, envelope)
        changed = {**envelope, "tool_name": "test.other"}
        changed["signature"] = sign_envelope(changed, key)
        before = services.facts(gateway, target)
        refused = post(worker.url, key, body(changed, key), PATH, request_id="conflict-probe")
        assert refused.status_code == 409 and refused.json()["kind"] == "refused"
        assert refused.json()["reason_code"] == "identity_conflict"
        assert metric_value(scrape(worker).text, "execution_conflicts_total", 'kind="identity"') >= 1
        assert claim_count(db, envelope["execution_id"]) == 0
        facts = services.facts(gateway, target)
        assert facts == before == {"gateway_attempts": 0, "target_accepted": 0, "target_effects": 0}
        evidence(**facts, claim_count=0, worker_pids=[worker.pid], mode=case, negative_detected=True,
                 asserted="an identity conflict is refused and counted without minting dispatch authority")
        return

    if case == "unknown_age":
        # A minted claim with no recorded outcome on a live run is "unresolved".
        # Its age is measured with the DATABASE clock and never reset by being
        # observed; claiming directly dispatches nothing.
        envelope = signed_request(key, db.epoch)
        register(db, envelope)
        store = ledger(db, key)
        assert store.claim(envelope, f"unresolved-{case}").permit is not None
        first = store.metrics_snapshot()
        assert first["admission_available"] is True and first["unresolved_count"] >= 1
        assert first["oldest_unresolved_age_seconds"] >= 0
        time.sleep(1.1)
        second = store.metrics_snapshot()
        assert second["unresolved_count"] >= 1
        # DB-time age grows; observing it does not reset the deadline.
        assert second["oldest_unresolved_age_seconds"] >= first["oldest_unresolved_age_seconds"] + 1.0
        worker = services.worker(gateway=gateway, database=db)
        before = services.facts(gateway, target)
        text = scrape(worker).text
        assert metric_value(text, "execution_unresolved_count") >= 1
        assert metric_value(text, "execution_unresolved_oldest_age_seconds") >= 0
        assert claim_count(db, envelope["execution_id"]) == 1
        facts = services.facts(gateway, target)
        assert facts == before == {"gateway_attempts": 0, "target_accepted": 0, "target_effects": 0}
        evidence(**facts, claim_count=1, worker_pids=[worker.pid], mode=case,
                 asserted="unresolved count and oldest DB-clock age are published; observation never resets the deadline")
        return

    # receipt_failure: a rolled-back receipt write is published as a write failure
    # and never reported as a completion; the target effect already happened once.
    gate = services.barrier("B4")
    worker = services.worker(gateway=gateway, database=db, hooks=gate,
                             connection_factory=FaultFactory("receipt", "rollback"))
    envelope = signed_request(key, db.epoch)
    register(db, envelope)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(outcome, worker, key, envelope, "receipt-original")
        gate.wait("B4")
        assert services.facts(gateway, target)["target_effects"] == 1
        gate.release("B4")
        value = pending.result(timeout=15).json()
    assert value["kind"] == "status_only" and "result" not in value
    assert value["durability"] == "unconfirmed"
    assert metric_value(scrape(worker).text, "execution_store_write_failures_total") >= 1
    assert claim_count(db, envelope["execution_id"]) == 1
    facts = services.facts(gateway, target)
    assert facts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
    evidence(**facts, claim_count=1, worker_pids=[worker.pid], mode=case, barriers=["B4"],
             asserted="a rolled-back receipt write is published as a write failure and never reported as a completion")
