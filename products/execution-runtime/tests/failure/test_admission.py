"""Actual worker admission and independent effects against disposable Postgres."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest

from execution_runtime.services.execution_ledger import ExecutionLedger
from execution_runtime.services.execution_protocol import iso, validate, validate_observation
from execution_runtime.services.execution_signing import canonical_digest, sign_envelope
from support.ledger import body, claim_count, register, signed_request
from test_harness_contract import post

PATH = "/api/v1/executions/handoff"


def ledger(database, key):
    return ExecutionLedger(database.dsn, key, database.epoch, admission_enabled=True)


def outcome(worker, token, envelope, request_id="harness-original"):
    return post(worker.url, token, body(envelope, token), PATH, request_id=request_id)


@pytest.mark.scenario("F-01", "action")
def test_original_action_dispatches_once(services, ledger_database, evidence):
    db = ledger_database
    envelope = signed_request(services.token, db.epoch)
    register(db, envelope)
    target = services.http()
    gateway = services.http(upstream=target.url)
    worker = services.worker(gateway=gateway, database=db)
    result = outcome(worker, services.token, envelope)
    assert result.status_code == 200
    value = result.json()
    validate("execution-handoff-response", value)
    assert value["kind"] == "original_result"
    validate_observation(value["observation"], envelope, services.token)
    assert canonical_digest(value["result"]) == value["observation"]["receipt"]["outcome_digest"]
    assert ledger(db, services.token).lookup(envelope["execution_id"])["receipt"] == value["observation"]["receipt"]
    assert claim_count(db, envelope["execution_id"]) == 1
    replay = outcome(worker, services.token, envelope, "harness-replay").json()
    assert replay["kind"] == "status_only" and "result" not in replay
    assert replay["recovery"]["attempt_request_id"] == "harness-original"
    assert replay["request_id"] == "harness-replay"
    assert services.facts(gateway, target) == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
    evidence(**services.facts(gateway, target), claim_count=1, worker_pids=[worker.pid],
             original_request_id="harness-original", replay_request_id="harness-replay")


@pytest.mark.parametrize("mode", [
    pytest.param("same_process", marks=pytest.mark.scenario("F-03", "same_process")),
    pytest.param("two_processes", marks=pytest.mark.scenario("F-03", "two_processes")),
])
@pytest.mark.parametrize("seed", range(20))
def test_duplicate_race_across_processes(services, ledger_database, mode, seed, evidence):
    db = ledger_database
    envelope = signed_request(services.token, db.epoch)
    register(db, envelope)
    gate = services.barrier("B1")
    target = services.http()
    gateway = services.http(upstream=target.url)
    original = services.worker(gateway=gateway, database=db, hooks=gate)
    duplicate = original if mode == "same_process" else services.worker(gateway=gateway, database=db)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(outcome, original, services.token, envelope)
        gate.wait("B1")
        replay = outcome(duplicate, services.token, envelope, f"replay-{seed}")
        assert replay.status_code == 202 and replay.json()["kind"] == "status_only"
        assert "result" not in replay.json()
        assert claim_count(db, envelope["execution_id"]) == 1
        assert services.facts(gateway, target)["gateway_attempts"] == 0
        gate.release("B1")
        assert future.result(timeout=15).json()["kind"] == "original_result"
    facts = services.facts(gateway, target)
    assert facts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
    evidence(**facts, claim_count=1, worker_pids=[original.pid, duplicate.pid], barriers=["B1"], mode=mode)


@pytest.mark.parametrize("mode", [pytest.param(mode, marks=pytest.mark.scenario("F-03", mode))
                                  for mode in ("same_process", "two_processes")])
@pytest.mark.parametrize("seed", range(20))
def test_simultaneous_preclaim_unique_key_race(services, ledger_database, mode, seed, evidence):
    db = ledger_database
    envelope = signed_request(services.token, db.epoch)
    register(db, envelope)
    gate = services.barrier("B0")
    target = services.http()
    gateway = services.http(upstream=target.url)
    first = services.worker(gateway=gateway, database=db, hooks=gate)
    second = first if mode == "same_process" else services.worker(gateway=gateway, database=db, hooks=gate)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [pool.submit(outcome, item, services.token, envelope, f"race-{seed}-{index}")
                   for index, item in enumerate((first, second))]
        acknowledgments = [gate.wait("B0"), gate.wait("B0")]
        assert {item["pid"] for item in acknowledgments} == {first.pid, second.pid}
        assert claim_count(db, envelope["execution_id"]) == 0
        gate.release("B0")
        replies = [future.result(timeout=15).json() for future in pending]
    assert sorted(reply["kind"] for reply in replies) == ["original_result", "status_only"]
    assert "result" not in next(reply for reply in replies if reply["kind"] == "status_only")
    assert claim_count(db, envelope["execution_id"]) == 1
    facts = services.facts(gateway, target)
    assert facts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
    evidence(**facts, claim_count=1, worker_pids=[first.pid, second.pid], mode=mode, barriers=["B0"])


@pytest.mark.parametrize("case", [pytest.param(case, marks=pytest.mark.scenario("F-02", case)) for case in
    ("auth_missing", "auth_invalid", "signing_missing", "schema", "signature", "args_digest",
     "gateway_missing", "credential_missing", "provenance")])
def test_invalid_handoff_never_dispatches(services, ledger_database, case, evidence):
    db = ledger_database
    envelope = signed_request(services.token, db.epoch)
    register(db, envelope)
    target = services.http()
    gateway = services.http(upstream=target.url)
    config = {"EXECUTION_SIGNING_KEY": ""} if case == "signing_missing" else {}
    if case == "gateway_missing":
        config["TOOL_GATEWAY_URL"] = ""
    worker = services.worker(gateway=gateway, database=db, **config)
    payload = body(envelope.copy(), services.token)
    token = services.token
    if case.startswith("auth_"):
        token = "" if case == "auth_missing" else "wrong"
    elif case == "schema":
        payload["request"]["unexpected"] = "not allowed"
    elif case == "signature":
        payload["request"]["signature"] = "0" * 64
    elif case == "args_digest":
        payload["arguments"] = {"changed": True}
    elif case == "credential_missing":
        payload["delegated_token"] = None
    elif case == "provenance":
        del payload["request"]["approval_kind"]
        payload["request"]["signature"] = sign_envelope(payload["request"], services.token)
    result = post(worker.url, token, payload, PATH)
    assert result.status_code in {400, 401}
    validate("execution-handoff-response", result.json())
    assert result.json()["kind"] == "refused"
    assert claim_count(db, envelope["execution_id"]) == 0
    facts = services.facts(gateway, target)
    assert facts == {"gateway_attempts": 0, "target_accepted": 0, "target_effects": 0}
    evidence(**facts, claim_count=0, mode=case)


@pytest.mark.parametrize("case,field,value", [
    pytest.param(case, field, value, marks=pytest.mark.scenario("F-04", case)) for case, field, value in (
        ("tool", "tool_name", "test.other"), ("args", "args_digest", "1" * 64),
        ("owner", "owner_user_id", "different-owner"), ("decider", "decider_user_id", "different-decider"),
        ("provenance", "approval_kind", "flow"),
        ("expiry", "expires_at", iso(datetime.now(timezone.utc) + timedelta(seconds=700))),
        ("reminted_id", "execution_id", str(uuid4())),
    )])
def test_identity_collision_preserves_original(ledger_database, services, case, field, value, evidence):
    db = ledger_database
    envelope = signed_request(services.token, db.epoch)
    register(db, envelope)
    store = ledger(db, services.token)
    assert store.claim(envelope, "harness-original").permit is not None
    changed = {**envelope, field: value}
    changed["signature"] = sign_envelope(changed, services.token)
    assert store.claim(changed, "different-request").reason == "identity_conflict"
    with db.connect() as conn:
        row = conn.execute("SELECT request_envelope FROM execution_intents WHERE execution_id=%s",
                           (envelope["execution_id"],)).fetchone()[0]
    assert row == envelope and claim_count(db, envelope["execution_id"]) == 1
    evidence(claim_count=1, mode=case, asserted="changed identity cannot mutate the original or mint a permit")


@pytest.mark.parametrize("mode", [pytest.param(mode, marks=pytest.mark.scenario("F-06", mode))
                                  for mode in ("startup", "backend")])
def test_admission_without_postgres_never_ready(services, ledger_database, mode, evidence):
    target = services.http()
    gateway = services.http(upstream=target.url)
    config = {"EXECUTION_STATE_DB_URL": ""} if mode == "startup" else {"EXECUTION_STATE_STORE_BACKEND": "memory"}
    worker = services.worker(gateway=gateway, database=ledger_database, **config)
    with httpx.Client(trust_env=False) as client:
        assert client.get(worker.url + "/health/live").status_code == 200
        ready = client.get(worker.url + "/health/ready")
        assert ready.status_code == 503 and not ready.json()["protocol_ready"]
        assert ready.json()["actual_backend"] == "unavailable"
    envelope = signed_request(services.token, ledger_database.epoch)
    register(ledger_database, envelope)
    assert outcome(worker, services.token, envelope).json()["kind"] == "unavailable"
    assert claim_count(ledger_database, envelope["execution_id"]) == 0
    evidence(**services.facts(gateway, target), claim_count=0, mode=mode)
