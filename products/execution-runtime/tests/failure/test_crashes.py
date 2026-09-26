"""Kill actual worker PIDs; retain target state and consumed claims across restart."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import time

import httpx
import pytest

from execution_runtime.services.execution_ledger import ExecutionLedger
from execution_runtime.services.execution_migration import connect
from execution_runtime.services.execution_protocol import observation
from support.ledger import claim_count, register, signed_request
from test_admission import ledger, outcome
from test_persistence import fresh_observer


class ProjectionClockConnection:
    def __init__(self, connection, seconds):
        self.connection, self.seconds = connection, seconds

    def __getattr__(self, name):
        return getattr(self.connection, name)

    @property
    def autocommit(self):
        return self.connection.autocommit

    @autocommit.setter
    def autocommit(self, value):
        self.connection.autocommit = value

    def execute(self, query, params=None):
        if query == "SELECT clock_timestamp()":
            return self.connection.execute("SELECT clock_timestamp() + %s * interval '1 second'", (self.seconds,))
        return self.connection.execute(query, params)


@dataclass
class ProjectionClock:
    seconds: int

    def __call__(self, dsn):
        return ProjectionClockConnection(connect(dsn), self.seconds)


def after_deadline(db, key, envelope):
    # Only the test reader's DB-time expression advances. No host/server clock or
    # durable row is modified; dispatch still uses the production DB clock.
    store = ExecutionLedger(db.dsn, key, db.epoch, connection_factory=ProjectionClock(121))
    return store.lookup(envelope["execution_id"])


@pytest.mark.scenario("F-08", "kill_B1")
@pytest.mark.parametrize("seed", range(20))
def test_kill_after_claim_before_send(services, ledger_database, seed, evidence):
    db = ledger_database
    envelope = signed_request(services.token, db.epoch)
    register(db, envelope)
    gate = services.barrier("B1")
    target = services.http()
    gateway = services.http(upstream=target.url)
    worker = services.worker(gateway=gateway, database=db, hooks=gate)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(outcome, worker, services.token, envelope)
        gate.wait("B1")
        assert claim_count(db, envelope["execution_id"]) == 1
        worker.kill()
        gate.release("B1")
        with pytest.raises(httpx.HTTPError):
            pending.result(timeout=10)
    replacement = services.worker(gateway=gateway, database=db)
    assert replacement.pid != worker.pid
    replay = outcome(replacement, services.token, envelope, f"replay-{seed}")
    assert replay.status_code == 202 and "result" not in replay.json()
    unknown = after_deadline(db, services.token, envelope)
    assert unknown["state"] == "outcome_unknown" and unknown["receipt"] is None
    facts = services.facts(gateway, target)
    assert facts == {"gateway_attempts": 0, "target_accepted": 0, "target_effects": 0}
    evidence(**facts, claim_count=1, worker_pids=[worker.pid, replacement.pid], barriers=["B1"])


@pytest.mark.parametrize("mode", [pytest.param(mode, marks=pytest.mark.scenario("F-09", mode))
                                  for mode in ("resume_original", "explicit_stop")])
@pytest.mark.parametrize("seed", range(20))
def test_suspended_owner_is_not_canceled_or_replaced(services, ledger_database, mode, seed, evidence):
    db = ledger_database
    envelope = signed_request(services.token, db.epoch)
    register(db, envelope)
    gate = services.barrier("B1")
    target = services.http()
    gateway = services.http(upstream=target.url)
    original = services.worker(gateway=gateway, database=db, hooks=gate)
    other = services.worker(gateway=gateway, database=db)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(outcome, original, services.token, envelope)
        gate.wait("B1")
        assert after_deadline(db, services.token, envelope)["state"] == "outcome_unknown"
        assert outcome(other, services.token, envelope, f"replay-{seed}").json()["kind"] == "status_only"
        if mode == "explicit_stop":
            fact = observation(envelope, source="agent", kind="wait_expired", key=services.token,
                               attempt_request_id="harness-original", current_request_id="agent-wait",
                               reason="wait_expired")
            ledger(db, services.token).stop(envelope, fact, reason="wait_expired")
        gate.release("B1")
        value = pending.result(timeout=15).json()
        assert value["kind"] == ("original_result" if mode == "resume_original" else "status_only")
    next_call = signed_request(services.token, db.epoch, run_id=envelope["run_id"], session_id=envelope["session_id"])
    register(db, next_call, "next-original")
    decision = ledger(db, services.token).claim(next_call, "next-original")
    assert decision.permit is None and decision.reason in {"run_stopped", "predecessor_unresolved"}
    expected = 1 if mode == "resume_original" else 0
    facts = services.facts(gateway, target)
    assert facts == {"gateway_attempts": expected, "target_accepted": expected, "target_effects": expected}
    evidence(**facts, claim_count=1, worker_pids=[original.pid, other.pid], mode=mode, barriers=["B1"])


@pytest.mark.scenario("F-11", "lost_gateway_reply")
def test_target_commit_with_lost_gateway_reply(services, ledger_database, evidence):
    db = ledger_database
    envelope = signed_request(services.token, db.epoch)
    register(db, envelope)
    target = services.http()
    gateway = services.http(upstream=target.url, fault="drop_reply")
    worker = services.worker(gateway=gateway, database=db)
    value = outcome(worker, services.token, envelope).json()
    assert value["kind"] == "status_only" and "result" not in value
    assert value["recovery"]["state"] == "outcome_unknown" and value["recovery"]["run_stopped"]
    assert fresh_observer(db, services.token, envelope["execution_id"])["state"] == "outcome_unknown"
    replacement = services.worker(gateway=gateway, database=db)
    assert outcome(replacement, services.token, envelope, "replay").json()["kind"] == "status_only"
    facts = services.facts(gateway, target)
    assert facts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
    evidence(**facts, claim_count=1, worker_pids=[worker.pid, replacement.pid])


@pytest.mark.parametrize("boundary", [
    pytest.param("B2", marks=pytest.mark.scenario("F-10", "kill_B2")),
    pytest.param("B3", marks=pytest.mark.scenario("F-10", "kill_B3")),
    pytest.param("B4", marks=pytest.mark.scenario("F-12", "kill_B4")),
    pytest.param("B5", marks=pytest.mark.scenario("F-13", "lost_handoff_reply")),
])
@pytest.mark.parametrize("seed", range(20))
def test_kill_after_gateway_acceptance(services, ledger_database, boundary, seed, evidence):
    db, key = ledger_database, services.token
    envelope = signed_request(key, db.epoch)
    register(db, envelope)
    gate = services.barrier(boundary)
    target = services.http(barrier=gate if boundary == "B3" else None)
    gateway = services.http(upstream=target.url, barrier=gate if boundary == "B2" else None)
    worker = services.worker(gateway=gateway, database=db, hooks=gate if boundary in {"B4", "B5"} else None)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(outcome, worker, key, envelope)
        ack = gate.wait(boundary)
        assert ack["pid"] == (gateway.pid if boundary == "B2" else target.pid if boundary == "B3" else worker.pid)
        before = services.facts(gateway, target)
        assert before["gateway_attempts"] == 1
        assert before["target_effects"] == (0 if boundary == "B2" else 1)
        assert claim_count(db, envelope["execution_id"]) == 1
        worker.kill()
        with pytest.raises(httpx.HTTPError):
            pending.result(timeout=10)
        replacement = services.worker(gateway=gateway, database=db)
        assert replacement.pid != worker.pid
        replay = outcome(replacement, key, envelope, f"replay-{seed}").json()
        assert replay["kind"] == "status_only" and "result" not in replay
        assert services.facts(gateway, target) == before
        gate.release(boundary)
    deadline = time.monotonic() + 5
    while services.facts(gateway, target)["target_effects"] != 1:
        assert time.monotonic() < deadline, "target did not finish after barrier release"
        time.sleep(0.01)
    state = after_deadline(db, key, envelope)
    expected = "result_recorded" if boundary == "B5" else "outcome_unknown"
    assert state["state"] == expected
    assert bool(state["receipt"]) == (boundary == "B5")
    observer = fresh_observer(db, key, envelope["execution_id"])
    assert observer["receipt"] == state["receipt"]
    next_call = signed_request(key, db.epoch, run_id=envelope["run_id"], session_id=envelope["session_id"])
    register(db, next_call, "next-original")
    assert ledger(db, key).claim(next_call, "next-original").reason == "predecessor_unresolved"
    final_replay = outcome(replacement, key, envelope, f"after-release-{seed}").json()
    assert final_replay["kind"] == "status_only" and "result" not in final_replay
    facts = services.facts(gateway, target)
    assert facts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
    evidence(**facts, claim_count=1, worker_pids=[worker.pid, replacement.pid], observer_pid=observer["pid"],
             barriers=[boundary], asserted="worker death cannot cancel remote work or reconstruct original output")


@pytest.mark.parametrize("case", [pytest.param(case, marks=pytest.mark.scenario("F-05", case))
                                  for case in ("cache_eviction", "restart")])
def test_restart_replay_metadata_only(services, ledger_database, case, evidence):
    db = ledger_database
    envelope = signed_request(services.token, db.epoch)
    register(db, envelope)
    target = services.http()
    gateway = services.http(upstream=target.url)
    worker = services.worker(gateway=gateway, database=db)
    original = outcome(worker, services.token, envelope).json()
    assert original["kind"] == "original_result"
    if case == "restart":
        # Process death: the replacement starts with no local memory at all.
        worker.kill()
    # The durable worker keeps no process-local result cache: replay is served
    # from the shared ledger. A freshly launched peer therefore holds no local
    # entry for this execution, modelling "evict all local cache entries"
    # (cache_eviction, original left running) and the post-death replacement
    # (restart) alike -- neither may fabricate output or re-dispatch.
    replacement = services.worker(gateway=gateway, database=db)
    replay = outcome(replacement, services.token, envelope, "replay").json()
    assert replay["kind"] == "status_only" and "result" not in replay
    assert replay["recovery"]["receipt"] == original["observation"]["receipt"]
    assert fresh_observer(db, services.token, envelope["execution_id"])["receipt"] == original["observation"]["receipt"]
    facts = services.facts(gateway, target)
    assert facts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
    evidence(**facts, claim_count=1, worker_pids=[worker.pid, replacement.pid], mode=case,
             asserted=("worker restart" if case == "restart" else "local cache eviction")
                      + " still answers durable metadata-only replay; attempt/effect stay one, no fabricated output")
