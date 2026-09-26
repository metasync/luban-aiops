"""Disabled cutover, downgrade, restore, and epoch-mismatch proofs (SPEC-063 F-33 / R-7b).

F-33 exercises exactly the two interlocks the ledger can actually observe, and
never claims universal out-of-band rollback detection:

* the supported wrapper/CLI refusal of a mutation-enabled downgrade (pure guard
  decision plus the versioned ``plan-cutover`` entrypoint the GitOps wrapper
  calls), and
* a restored catalog whose stored epoch differs from the new external epoch --
  it fails closed with ``epoch_mismatch`` until an explicit rotation records the
  new epoch with admission STILL disabled.

The downgrade case is deterministic guard logic; the restore and epoch_mismatch
cases run against the disposable real Postgres so the rotation, the fail-closed
claim, and the disabled-after-rotation refusal are proven on the live driver.
"""
from __future__ import annotations

import os
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import httpx
import pytest

from execution_runtime.services import execution_cutover
from execution_runtime.services.execution_cutover import (
    CLOCK_DISAGREEMENT_MARGIN_SECONDS,
    old_validity_wait_seconds,
    plan_cutover,
    restore_interlock,
    rotate_epoch,
)
from execution_runtime.services.execution_ledger import ExecutionLedger
from execution_runtime.services.execution_migration import connect, migrate, verify_schema
from execution_runtime.services.execution_protocol import MAX_LIFETIME_SECONDS, ProtocolError
from support.ledger import claim_count, register, signed_request
from test_admission import outcome


def _enable(db):
    """Flip the catalog to admission-enabled (the live pre-restore posture)."""
    with db.connect() as conn:
        conn.execute("UPDATE execution_protocol_state SET admission_enabled=true")


def _disable(db):
    """Clear admission (the disabled-recovery precondition before rotating)."""
    with db.connect() as conn:
        conn.execute("UPDATE execution_protocol_state SET admission_enabled=false")


def _cli_plan_exit(current, target, mode, *, enabled):
    """Exit code of the versioned ``plan-cutover`` entrypoint the wrapper calls."""
    argv = ["execution_cutover", "plan-cutover", "--current-version", current,
            "--target-version", target, "--mode", mode]
    if enabled:
        argv.append("--admission-enabled")
    saved = sys.argv
    sys.argv = argv
    try:
        execution_cutover.main()
    except SystemExit as exc:
        return int(exc.code)
    finally:
        sys.argv = saved
    return 0


@pytest.mark.scenario("F-33", "downgrade")
def test_mutation_enabled_downgrade_is_refused_without_disabled_recovery(evidence):
    # A mutation-enabled downgrade in normal mode is refused outright and never
    # reports admission as surviving the change.
    refused = plan_cutover(current_version="0.42.0", target_version="0.41.0",
                           admission_enabled=True, mode="normal")
    assert not refused.allowed and refused.change == "downgrade"
    assert refused.reason == "downgrade_requires_disabled_recovery"
    assert not refused.admission_after

    # The same downgrade is permitted only under explicit disabled-recovery, and
    # then it forces mutations off + the worker stopped and never re-enables.
    recovery = plan_cutover(current_version="0.42.0", target_version="0.41.0",
                            admission_enabled=True, mode="disabled-recovery")
    assert recovery.allowed and recovery.change == "downgrade"
    assert recovery.must_disable_mutations and recovery.must_stop_worker
    assert not recovery.admission_after and not recovery.requires_epoch_rotation

    # An undeterminable relative version is treated as a downgrade and, because
    # the binary's age cannot be established, additionally requires an external
    # epoch rotation. In normal mode it is refused like any downgrade.
    unknown = plan_cutover(current_version="0.42.0", target_version="not-a-version",
                           admission_enabled=True, mode="disabled-recovery")
    assert unknown.allowed and unknown.change == "unknown" and unknown.requires_epoch_rotation
    assert plan_cutover(current_version="0.42.0", target_version="not-a-version",
                        admission_enabled=True, mode="normal").reason == "downgrade_requires_disabled_recovery"

    # A forward upgrade carries no interlock and never flips admission on.
    upgrade = plan_cutover(current_version="0.41.0", target_version="0.42.0",
                           admission_enabled=False, mode="normal")
    assert upgrade.allowed and upgrade.change == "upgrade" and not upgrade.admission_after
    assert not upgrade.must_stop_worker and not upgrade.must_disable_mutations

    # The supported CLI wrapper exits non-zero on the refused mutation-enabled
    # downgrade and zero on the allowed forward upgrade.
    assert _cli_plan_exit("0.42.0", "0.41.0", "normal", enabled=True) == 1
    assert _cli_plan_exit("0.41.0", "0.42.0", "normal", enabled=False) == 0

    evidence(mode="downgrade", negative_detected=True,
             asserted="mutation-enabled downgrade refused unless disabled-recovery; upgrade never auto-enables")


@pytest.mark.scenario("F-33", "restore")
def test_restored_snapshot_fails_closed_until_external_epoch_rotated_disabled(empty_database, services, evidence):
    db = empty_database
    old_epoch = db.epoch                      # epoch baked into the restored snapshot
    migrate(db.dsn, old_epoch)
    _enable(db)                               # the live catalog had admission enabled
    envelope = signed_request(services.token, old_epoch)
    register(db, envelope)

    new_epoch = str(uuid4())                  # operator's new external epoch post-restore

    # Before rotation a ledger carrying the new external epoch fails closed with
    # epoch_mismatch and mints no dispatch authority.
    mismatched = ExecutionLedger(db.dsn, services.token, new_epoch, admission_enabled=True)
    assert mismatched.health()["reason_code"] == "epoch_mismatch"
    assert mismatched.claim(envelope, "post-restore").reason == "epoch_mismatch"
    assert claim_count(db, envelope["execution_id"]) == 0

    # The restore interlock reports every blocker until each clears, never
    # enables admission, and bounds the wait below by one full request lifetime.
    blocked = restore_interlock(stored_epoch=old_epoch, external_epoch=new_epoch,
                                evidence_retained_outside=False, old_senders_stopped=False,
                                wait_complete=False)
    assert not blocked.allowed and not blocked.admission_after and not blocked.epochs_reconciled
    assert set(blocked.blockers) == {"evidence_not_retained_outside_snapshot", "old_senders_not_stopped",
                                     "external_epoch_not_rotated", "old_validity_window_open"}
    assert blocked.required_wait_seconds == MAX_LIFETIME_SECONDS + CLOCK_DISAGREEMENT_MARGIN_SECONDS
    assert old_validity_wait_seconds(clock_disagreement_seconds=45, issuer_shutdown_skew_seconds=15) == \
        MAX_LIFETIME_SECONDS + CLOCK_DISAGREEMENT_MARGIN_SECONDS + 60

    # Rotation REFUSES while the restored catalog is still admission-enabled:
    # the disabled-recovery posture (disable mutations, stop the worker) must
    # clear admission first. This proves the guard's enabled-catalog refusal.
    with pytest.raises(ProtocolError, match="epoch_rotation_refused_enabled"):
        rotate_epoch(db.dsn, new_epoch)

    # Disabled-recovery precondition met: admission disabled, then the explicit
    # external rotation records the new epoch with admission STILL disabled.
    _disable(db)
    assert rotate_epoch(db.dsn, new_epoch) == \
        {"rotated": True, "admission_epoch": new_epoch, "admission_enabled": False}
    with connect(db.dsn) as conn:
        state = verify_schema(conn)
    assert state["admission_epoch"] == new_epoch and not state["admission_enabled"]
    # Rotation is idempotent for the epoch already recorded and never enables.
    assert rotate_epoch(db.dsn, new_epoch)["rotated"] is False

    # After rotation the epoch matches, but admission is disabled, so a claim is
    # still refused -- rotation alone confers no dispatch authority; enabling is
    # a separate, explicitly authorized step.
    rotated = ExecutionLedger(db.dsn, services.token, new_epoch, admission_enabled=True)
    assert rotated.health()["reason_code"] == "admission_disabled"
    assert rotated.claim(envelope, "post-rotation").reason == "admission_disabled"
    assert claim_count(db, envelope["execution_id"]) == 0

    evidence(mode="restore", claim_count=0, negative_detected=True,
             asserted="restored epoch fails closed; external rotation records epoch with admission still disabled")


@pytest.mark.scenario("F-33", "epoch_mismatch")
def test_external_epoch_mismatch_mints_no_dispatch_authority(empty_database, services, evidence):
    db = empty_database
    stored_epoch = db.epoch
    migrate(db.dsn, stored_epoch)
    _enable(db)
    envelope = signed_request(services.token, stored_epoch)
    register(db, envelope)

    # A ledger whose external epoch differs from the stored/envelope epoch mints
    # no permit and writes no claim row.
    mismatched = ExecutionLedger(db.dsn, services.token, str(uuid4()), admission_enabled=True)
    decision = mismatched.claim(envelope, "mismatched")
    assert decision.permit is None and decision.reason == "epoch_mismatch"
    assert claim_count(db, envelope["execution_id"]) == 0

    # Control: the correctly-epoched ledger DOES mint a permit, proving the
    # refusal above is the epoch mismatch and not a blanket disable.
    matched = ExecutionLedger(db.dsn, services.token, stored_epoch, admission_enabled=True)
    assert matched.claim(envelope, "matched").permit is not None
    assert claim_count(db, envelope["execution_id"]) == 1

    evidence(mode="epoch_mismatch", claim_count=1, negative_detected=True,
             asserted="mismatched external epoch mints no permit; matched epoch does (control)")


@pytest.mark.parametrize("case", [pytest.param(case, marks=pytest.mark.scenario("F-32", case))
                                  for case in ("disabled_cutover", "overlap", "drain", "abrupt")])
@pytest.mark.parametrize("seed", range(20))
def test_disabled_cutover_overlap_and_bounded_drain(services, ledger_database, case, seed, evidence):
    """R-7c cutover postures keep dispatch single-use across every transition.

    ``disabled_cutover``: a worker deployed with admission off is unready and
    mints no dispatch authority. ``overlap``: two overlapping new-version PIDs
    still dispatch exactly once (the single-use claim, not the Recreate
    strategy, is the authority). ``drain``: SIGTERM refuses new handoffs, lets
    the in-flight call finish inside the bounded drain, and terminates WITHOUT
    releasing the claim. ``abrupt``: a SIGKILL mid-flight retains the claim and
    a replacement mints no second dispatch. F-32 is repeated: 20 seeds per case.
    """
    db, key = ledger_database, services.token
    envelope = signed_request(key, db.epoch)
    register(db, envelope)
    target = services.http()
    gateway = services.http(upstream=target.url)

    if case == "disabled_cutover":
        # A worker brought up during the disabled-cutover window (admission off)
        # is never ready and refuses to mint dispatch authority for a registered
        # intent; the durable refusal records no claim and reaches no target.
        worker = services.worker(gateway=gateway, database=db, EXECUTION_ADMISSION_ENABLED="false")
        with httpx.Client(trust_env=False, timeout=10) as client:
            ready = client.get(worker.url + "/health/ready")
        assert ready.status_code == 503 and not ready.json()["protocol_ready"]
        refused = outcome(worker, key, envelope, f"cutover-{seed}").json()
        assert refused["kind"] == "refused" and refused["reason_code"] == "admission_disabled"
        assert claim_count(db, envelope["execution_id"]) == 0
        facts = services.facts(gateway, target)
        assert facts == {"gateway_attempts": 0, "target_accepted": 0, "target_effects": 0}
        evidence(**facts, claim_count=0, worker_pids=[worker.pid], mode=case, negative_detected=True,
                 asserted="admission-disabled cutover worker is unready and mints no dispatch authority")
        return

    if case == "overlap":
        # Recreate avoids old/new overlap, but overlap safety is still proven: two
        # new-version PIDs race the same approved call at B0 and the single-use
        # claim admits exactly one dispatch.
        gate = services.barrier("B0")
        first = services.worker(gateway=gateway, database=db, hooks=gate)
        second = services.worker(gateway=gateway, database=db, hooks=gate)
        assert first.pid != second.pid
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(outcome, item, key, envelope, f"overlap-{seed}-{index}")
                       for index, item in enumerate((first, second))]
            acknowledgments = [gate.wait("B0"), gate.wait("B0")]
            assert {item["pid"] for item in acknowledgments} == {first.pid, second.pid}
            assert claim_count(db, envelope["execution_id"]) == 0
            gate.release("B0")
            replies = [future.result(timeout=15).json() for future in pending]
        assert sorted(reply["kind"] for reply in replies) == ["original_result", "status_only"]
        assert claim_count(db, envelope["execution_id"]) == 1
        facts = services.facts(gateway, target)
        assert facts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
        evidence(**facts, claim_count=1, worker_pids=[first.pid, second.pid], mode=case, barriers=["B0"],
                 asserted="two overlapping new-version PIDs still dispatch exactly once")
        return

    # drain / abrupt: the claim is minted at B1 (before send), then the worker is
    # terminated either gracefully (SIGTERM) or abruptly (SIGKILL).
    gate = services.barrier("B1")
    worker = services.worker(gateway=gateway, database=db, hooks=gate)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(outcome, worker, key, envelope, f"inflight-{seed}")
        gate.wait("B1")
        assert claim_count(db, envelope["execution_id"]) == 1
        if case == "drain":
            # SIGTERM flips draining (refuse new handoffs, mark unready) and the
            # in-flight call is allowed to finish inside the bounded drain; the
            # claim is consumed by the dispatch, never released.
            os.kill(worker.pid, signal.SIGTERM)
            gate.release("B1")
            assert pending.result(timeout=15).json()["kind"] == "original_result"
        else:
            worker.kill()
            gate.release("B1")
            with pytest.raises(httpx.HTTPError):
                pending.result(timeout=10)
    if case == "drain":
        deadline = time.monotonic() + 15
        while worker.process.is_alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not worker.process.is_alive(), "worker did not terminate after the bounded drain"
    replacement = services.worker(gateway=gateway, database=db)
    assert replacement.pid != worker.pid
    replay = outcome(replacement, key, envelope, f"replay-{seed}")
    assert replay.status_code in {200, 202} and "result" not in replay.json()
    assert claim_count(db, envelope["execution_id"]) == 1
    facts = services.facts(gateway, target)
    expected = 1 if case == "drain" else 0
    assert facts == {"gateway_attempts": expected, "target_accepted": expected, "target_effects": expected}
    evidence(**facts, claim_count=1, worker_pids=[worker.pid, replacement.pid], mode=case, barriers=["B1"],
             asserted=("SIGTERM drained the in-flight call then terminated without releasing the claim"
                       if case == "drain" else
                       "abrupt SIGKILL retained the claim and a replacement minted no second dispatch"))
