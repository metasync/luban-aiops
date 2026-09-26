"""Real transaction ambiguity; no exception-only substitute for committed state."""
from concurrent.futures import ThreadPoolExecutor
import os
from types import SimpleNamespace

import pytest

from support.barriers import CONTEXT
from support.ledger import claim_count, register, signed_request
from support.postgres_faults import CommitAckProxy, FaultFactory
from test_admission import ledger, outcome


def observe(dsn, key, epoch, execution_id, pipe):
    from execution_runtime.services.execution_ledger import ExecutionLedger
    state = ExecutionLedger(dsn, key, epoch).lookup(execution_id)
    pipe.send({"state": state["state"], "receipt": state["receipt"], "pid": os.getpid()})
    pipe.close()


def fresh_observer(database, key, execution_id):
    receive, send = CONTEXT.Pipe(duplex=False)
    child = CONTEXT.Process(target=observe, args=(database.dsn, key, database.epoch, execution_id, send))
    child.start()
    send.close()
    try:
        assert receive.poll(10), "fresh recovery observer timed out"
        result = receive.recv()
        child.join(timeout=5)
        assert child.exitcode == 0
        return result
    finally:
        receive.close()
        if child.is_alive():
            child.kill()
            child.join(timeout=5)
        child.close()


@pytest.mark.parametrize("mode", [pytest.param(mode, marks=pytest.mark.scenario("F-07", mode))
                                  for mode in ("commit_wrapper", "commit_wire", "rollback")])
@pytest.mark.parametrize("seed", range(20))
def test_claim_commit_ack_loss_never_sends(services, ledger_database, mode, seed, evidence):
    db = ledger_database
    envelope = signed_request(services.token, db.epoch)
    register(db, envelope)
    target = services.http()
    gateway = services.http(upstream=target.url)
    proxy = CommitAckProxy(db.dsn) if mode == "commit_wire" else None
    try:
        database = SimpleNamespace(dsn=proxy.dsn, epoch=db.epoch) if proxy else db
        factory = None if proxy else FaultFactory("claim", "rollback" if mode == "rollback" else "ack_lost")
        worker = services.worker(gateway=gateway, database=database, connection_factory=factory)
        if proxy:
            proxy.armed.set()
        result = outcome(worker, services.token, envelope)
        assert result.status_code == 503 and result.json()["kind"] == "unavailable"
        if proxy:
            assert proxy.dropped.wait(5)
        expected = 0 if mode == "rollback" else 1
        assert claim_count(db, envelope["execution_id"]) == expected
        observed = fresh_observer(db, services.token, envelope["execution_id"])
        assert observed["pid"] != worker.pid
        if expected:
            assert observed["state"] == "dispatch_claimed"
            replacement = services.worker(gateway=gateway, database=db)
            replay = outcome(replacement, services.token, envelope, f"replay-{seed}")
            assert replay.status_code == 202 and "result" not in replay.json()
        facts = services.facts(gateway, target)
        assert facts == {"gateway_attempts": 0, "target_accepted": 0, "target_effects": 0}
        evidence(**facts, claim_count=expected, worker_pids=[worker.pid], observer_pid=observed["pid"], mode=mode)
    finally:
        if proxy:
            proxy.close()


@pytest.mark.parametrize("mode", [pytest.param(mode, marks=pytest.mark.scenario("F-12", mode))
                                  for mode in ("rollback", "commit_wrapper", "commit_wire")])
@pytest.mark.parametrize("seed", range(20))
def test_receipt_write_failure_or_ack_loss(services, ledger_database, mode, seed, evidence):
    db = ledger_database
    envelope = signed_request(services.token, db.epoch)
    register(db, envelope)
    target = services.http()
    gateway = services.http(upstream=target.url)
    gate = services.barrier("B4")
    proxy = CommitAckProxy(db.dsn) if mode == "commit_wire" else None
    try:
        database = SimpleNamespace(dsn=proxy.dsn, epoch=db.epoch) if proxy else db
        factory = None if proxy else FaultFactory("receipt", "rollback" if mode == "rollback" else "ack_lost")
        worker = services.worker(gateway=gateway, database=database, hooks=gate, connection_factory=factory)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(outcome, worker, services.token, envelope)
            gate.wait("B4")
            assert services.facts(gateway, target)["target_effects"] == 1
            if proxy:
                proxy.armed.set()
            gate.release("B4")
            result = pending.result(timeout=15)
        assert result.status_code in {200, 202}
        if proxy:
            assert proxy.dropped.wait(5)
        value = result.json()
        observed = fresh_observer(db, services.token, envelope["execution_id"])
        if mode == "rollback":
            assert value["kind"] == "status_only" and "result" not in value
            assert value["durability"] == "unconfirmed" and observed["receipt"] is None
            assert observed["state"] == "outcome_unknown"
        else:
            assert value["kind"] == "original_result"
            assert observed["receipt"] == value["observation"]["receipt"]
        replacement = services.worker(gateway=gateway, database=db)
        replay = outcome(replacement, services.token, envelope, f"replay-{seed}")
        assert replay.json()["kind"] == "status_only" and "result" not in replay.json()
        assert claim_count(db, envelope["execution_id"]) == 1
        facts = services.facts(gateway, target)
        assert facts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
        evidence(**facts, claim_count=1, worker_pids=[worker.pid, replacement.pid],
                 observer_pid=observed["pid"], mode=mode, barriers=["B4"])
    finally:
        if proxy:
            proxy.close()
