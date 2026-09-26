"""Cross-product failure proofs: real agent seam -> worker -> gateway -> target.

Every test here launches the *actual* product seams with deterministic decisions
(no LLM, and no mocking of policy/HITL/secret-release): the agent invocation
probe drives ``gateway_tools.tool_fn -> _invoke_v3 -> coordinate_v3_invocation ->
handoff_original`` through the real ``ToolEvidenceMiddleware`` against a live
execution-runtime worker, its tool-gateway proxy, and the disposable counter
target, all on real Postgres. Only bounded, allowlisted facts cross the process
boundary and are asserted; raw tool output, secret material, and exception text
never leave the probe subprocess.

This file owns the S2 cross-product families:

* F-16 tool report is not business success: an HTTP error, a valid tool failure
  after a partial effect, and a tool success carrying an upstream 500 stay
  distinct; a failure never proves the target did not act.
* F-18 status store outage is not empty history: an unreachable store reads
  ``unavailable`` (never ``not_found``/empty/fallback success) while read-only
  routing stays available.
* F-15 untrusted response stops continuation (transport variants).
* F-13 lost handoff response recovers on reload (agent death after B5).
* F-14 agent wait then late worker result (timeout and receipt both retained).

This file also owns the S3 secret-delivery proof:

* F-23 secret release requires an original durable success: a held portal_copy
  delivery is revealed only when a verified original durable success on a
  non-stopped run mints the single-use permit; unknown, receipt-failure, replay,
  late-success, and a stop-before-emission race all burn the hold.

This file also owns the S3 permission-gate proofs:

* F-19 denial/expiry/stale flow authority: a denied or expired action approval
  and a revoked/expired/rebound browser-flow authority all fail safe at the real
  ``on_check_permission`` gate and flow signer — no ALLOW, no signed envelope, no
  execution record or audit, and zero gateway attempts or target mutations.
* F-20 flow duplicate and unknown-stop next write: a flow-auto-signed step
  dispatches once and a duplicate consumes no second browser step; once a write
  resolves unknown (durably stopping the run) or a run is otherwise stopped, a
  later automatic write or a freshly-minted card/ID under it is refused at
  registration and never dispatches.
* F-21 restart cannot resume a stopped run: a durable stop blocks a stale
  ALLOWED browser write and a live-authority flow auto-sign at the gate, and a
  fresh agent process cannot register a continuation under the stopped run; a
  stop whose durable write fails still fails closed via the process-local latch;
  a lost run identity fails closed at registration rather than reminting a run.
* F-22 outstanding operations reported and next send blocked: an accepted-but-
  active operation and a response-lost operation are reported as independent
  records and the accepted one is never canceled by the other's failure; a second
  recovery claim lands no second dispatch; and a stop landing between claim and
  send blocks the final send before the gateway is reached.

This file also owns the S4 recovery-read proofs:

* F-24 recovery owner scope and paging: the owner recovery read is scoped to the
  run owner and cursor-paged — a foreign user, the decision-only approver inbox,
  or a forged/unknown id all read ``not_found`` with no distinguishing detail
  even against a recorded success; observations page in bounded windows of 20
  while ``state``/``receipt`` stay computed over the full validated set, and
  repeated or past-the-end reads are isolated idempotent snapshots that never
  degrade the outcome. A recovery read is never an original response.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import re
import time
from uuid import uuid4

import pytest

from support.agent_seam import AgentProcess, decide_permission, invoke_agent
from support.ledger import claim_count, register, signed_request
from support.postgres_faults import FaultFactory
from test_admission import ledger, outcome
from test_agent_storage import agent, prepared


def _unreachable_dsn(db):
    """The same store pointed at a refused port: down, not absent.

    F-18 must distinguish an unreachable status store (availability
    ``unavailable``) from a reachable store with no such execution
    (``not_found``). Loopback port 1 is refused immediately, so the recovery
    read fails fast into ``unavailable`` instead of an empty/fallback history.
    """
    return re.sub(r"port=\d+", "port=1", db.dsn)


@pytest.mark.parametrize("case", [pytest.param(case, marks=pytest.mark.scenario("F-16", case))
                                  for case in ("http_error", "partial_effect", "upstream_500")])
def test_tool_report_is_not_business_success(services, ledger_database, case, evidence):
    db, key = ledger_database, services.token
    if case == "http_error":
        # The gateway returns an HTTP error with no trustworthy body AFTER it
        # forwarded to the target, so the effect happened but cannot be confirmed.
        target = services.http()
        gateway = services.http(upstream=target.url, fault="http_error")
    elif case == "partial_effect":
        # A schema-valid tool failure report after the counter already incremented.
        target = services.http(report={
            "status": "error",
            "error": {"code": "PARTIAL_EFFECT", "message": "counter incremented then the step failed"}})
        gateway = services.http(upstream=target.url)
    else:  # upstream_500
        # A tool success whose own payload documents an upstream 500.
        target = services.http(report={"data": {"incremented": True, "upstream_status": 500}})
        gateway = services.http(upstream=target.url)
    worker = services.worker(gateway=gateway, database=db)

    facts = invoke_agent(db, key, worker_url=worker.url, timeout=20, tool_name="test.increment")
    assert facts["ok"], facts.get("reason")

    # The three legs classify distinctly: an HTTP error with no report is
    # uncertainty; a valid tool failure is a definitive failed receipt; a tool
    # success carrying an upstream 500 is recorded succeeded. None is a verified
    # business success and none claims the target did not act.
    if case == "http_error":
        assert facts["frame_status"] == "error"
        assert facts["error_code"] == "OUTCOME_UNKNOWN"
        assert facts["recovery_state"] == "outcome_unknown"
        assert facts["receipt_status"] is None
        assert facts["recovery_run_stopped"] and facts["guard_stopped"]
        assert "transport_uncertain" in facts["observation_kinds"]
    elif case == "partial_effect":
        assert facts["frame_status"] == "error"
        assert facts["error_code"] == "PARTIAL_EFFECT"
        assert facts["recovery_state"] == "result_recorded"
        assert facts["receipt_status"] == "failed"
        assert not facts["guard_stopped"]
        assert {"claim_committed", "worker_result", "response_accepted"} <= set(facts["observation_kinds"])
    else:  # upstream_500
        assert facts["frame_status"] == "success"
        assert facts["error_code"] is None
        assert facts["recovery_state"] == "result_recorded"
        assert facts["receipt_status"] == "succeeded"
        assert not facts["guard_stopped"]

    # A dispatched call always keeps target verification required, and the effect
    # is counted independently of the report: a tool report is never proof of a
    # business outcome, and an HTTP/tool failure never proves the target idle.
    assert facts["target_verification_required"] is True
    counts = services.facts(gateway, target)
    assert counts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
    assert claim_count(db, facts["execution_id"]) == 1
    evidence(**counts, claim_count=1, worker_pids=[worker.pid], mode=case,
             release_count=facts["release_count"],
             asserted="HTTP error, partial-effect failure, and upstream-500 success stay distinct; none proves no effect")


@pytest.mark.parametrize("case", [pytest.param(case, marks=pytest.mark.scenario("F-18", case))
                                  for case in ("store_outage", "read_tool_available")])
def test_status_store_outage_is_not_empty_history(services, ledger_database, case, evidence):
    db, key = ledger_database, services.token
    target = services.http()
    gateway = services.http(upstream=target.url)
    if case == "store_outage":
        worker = services.worker(gateway=gateway, database=db)
        # A real execution is durably recorded through the normal seam.
        recorded = invoke_agent(db, key, worker_url=worker.url, timeout=20, tool_name="test.increment")
        assert recorded["ok"], recorded.get("reason")
        execution_id = recorded["execution_id"]
        assert recorded["recovery_availability"] == "available"
        assert recorded["recovery_state"] == "result_recorded"
        # On owner reload with the status store unreachable, the owner sees
        # "unavailable" - never an empty history, a not_found, or a fallback
        # memory success. A reachable store with an unknown id is "not_found",
        # which is what makes "unavailable" a distinct, honest signal.
        down = invoke_agent(db, key, operation="recover", execution_id=execution_id,
                            recovery_dsn=_unreachable_dsn(db))
        assert down["recovery_availability"] == "unavailable"
        assert down["recovery_state"] is None
        assert down["receipt_status"] is None
        assert down["target_verification_required"] is True
        absent = invoke_agent(db, key, operation="recover", execution_id=str(uuid4()))
        assert absent["recovery_availability"] == "not_found"
        counts = services.facts(gateway, target)
        assert counts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
        assert claim_count(db, execution_id) == 1
        evidence(**counts, claim_count=1, worker_pids=[worker.pid], mode=case,
                 asserted="an unreachable status store reads unavailable, never empty/not_found/fallback success")
    else:  # read_tool_available
        # A read-tier tool keeps its existing direct gateway path and never
        # touches the recovery store, so a store outage cannot block reads.
        facts = invoke_agent(db, key, read_only=True, gateway_url=gateway.url,
                             recovery_dsn=_unreachable_dsn(db), tool_name="test.read")
        assert facts["ok"], facts.get("reason")
        assert facts["frame_status"] == "success"
        assert facts["execution_id"] is None
        counts = services.facts(gateway, target)
        assert counts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
        evidence(**counts, claim_count=0, worker_pids=[], mode=case,
                 asserted="read-only routing is unchanged and available during a status-store outage")


@pytest.mark.parametrize("case", [pytest.param(case, marks=pytest.mark.scenario("F-15", case))
                                  for case in ("timeout", "disconnect_read", "disconnect_write",
                                               "malformed", "truncated")])
def test_untrusted_worker_reply_blocks_continuation(services, ledger_database, case, evidence):
    db, key = ledger_database, services.token
    target = services.http()
    gateway = services.http(upstream=target.url)
    worker = services.worker(gateway=gateway, database=db)
    # The fault rides the agent<->worker leg only: a non-retrying proxy in front
    # of the *real* worker withholds or corrupts the handoff reply. The worker,
    # gateway, and target behind it are unchanged, so the independent counters
    # still record whether the send actually reached and acted on the target.
    # "timeout" is a delayed reply (the worker finishes, the proxy stalls at B5
    # past the agent's bounded wait); the other four are the wire faults.
    gate = services.barrier("B5") if case == "timeout" else None
    fault = "delayed_headers" if case == "timeout" else case
    proxy = services.http(upstream=worker.url, fault=fault, barrier=gate)
    try:
        facts = invoke_agent(db, key, worker_url=proxy.url, timeout=5, tool_name="test.increment")
    finally:
        if gate is not None:
            gate.release("B5")
    assert facts["ok"], facts.get("reason")

    # Every transport fault on the reply is a potential-send uncertainty: the tool
    # frame reports OUTCOME_UNKNOWN and the run latch stops continuation. None is
    # reported as a pre-dispatch refusal or a verified success, and no secret is
    # released - even though the worker behind the proxy may have fully acted.
    assert facts["frame_status"] == "error"
    assert facts["error_code"] == "OUTCOME_UNKNOWN"
    assert facts["guard_stopped"] and facts["recovery_run_stopped"]
    assert facts["release_count"] == 0
    assert facts["target_verification_required"] is True
    assert "pre_dispatch_refused" not in facts["observation_kinds"]
    counts = services.facts(gateway, target)
    if case == "disconnect_write":
        # The proxy drops the request before it reaches the worker, so nothing
        # dispatched - yet the agent still may not claim a pre-send refusal: it
        # wrote bytes onto a socket that then died, which is uncertainty.
        assert counts == {"gateway_attempts": 0, "target_accepted": 0, "target_effects": 0}
        assert claim_count(db, facts["execution_id"]) == 0
        assert facts["recovery_state"] == "outcome_unknown"
        assert facts["receipt_status"] is None
        assert "transport_uncertain" in facts["observation_kinds"]
        claimed = 0
    else:
        # The worker completed and durably recorded before the reply was lost or
        # corrupted, so the record carries the receipt while the agent - never
        # holding a VerifiedOriginal - honestly stayed uncertain and stopped.
        assert counts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
        assert claim_count(db, facts["execution_id"]) == 1
        assert facts["recovery_state"] == "result_recorded"
        assert facts["receipt_status"] == "succeeded"
        expected = "wait_expired" if case == "timeout" else "transport_uncertain"
        assert expected in facts["observation_kinds"]
        claimed = 1
    evidence(**counts, claim_count=claimed, worker_pids=[worker.pid], mode=case,
             release_count=facts["release_count"], barriers=(["B5"] if gate else []),
             asserted="a transport fault on the worker reply is uncertainty that blocks continuation, never a pre-send refusal or a verified success")


@pytest.mark.scenario("F-13", "agent_death")
def test_agent_death_after_durable_result_recovers_on_reload(services, ledger_database, evidence):
    db, key = ledger_database, services.token
    session_id, owner = str(uuid4()), "test-owner"
    # Pre-create the run in the parent lane so the durable intent can be found by
    # run_id after the agent process is killed mid-handoff and never returns facts.
    root = agent(db, key, "create", session_id=session_id, owner_user_id=owner)
    assert root["ok"]
    run_id = root["run_id"]
    target = services.http()
    gateway = services.http(upstream=target.url)
    gate = services.barrier("B5")
    worker = services.worker(gateway=gateway, database=db, hooks=gate)
    # The agent registers, dispatches through the real worker, and the worker
    # durably records the signed receipt, then parks at B5: the result is
    # committed but the original_result reply has not reached the agent. Kill the
    # agent OS process mid-wait - it can neither accept, nor stop, nor re-execute.
    proc = AgentProcess(db, key, run_id=run_id, session_id=session_id, owner_user_id=owner,
                        worker_url=worker.url, timeout=30, tool_name="test.increment")
    try:
        ack = gate.wait("B5", timeout=30)
        assert ack["pid"] == worker.pid
        assert services.facts(gateway, target) == {
            "gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
        proc.kill()
        # Recover the durable intent by run_id: a fresh read in the parent lane.
        with db.connect() as conn:
            row = conn.execute("SELECT execution_id, request_envelope FROM execution_intents "
                               "WHERE run_id=%s", (run_id,)).fetchone()
        execution_id, envelope = str(row[0]), row[1]
        assert claim_count(db, execution_id) == 1
        # The lost reply: release B5 so the worker answers a dead agent. The
        # committed receipt is unaffected by the undeliverable response.
        gate.release("B5")
        # A fresh process reloads the session and recovers the one durable result;
        # the agent's death neither lost it nor left the run stopped.
        recovered = invoke_agent(db, key, operation="recover", execution_id=execution_id)
        assert recovered["recovery_availability"] == "available"
        assert recovered["recovery_state"] == "result_recorded"
        assert recovered["receipt_status"] == "succeeded"
        assert recovered["target_verification_required"] is True
        assert not recovered["recovery_run_stopped"]
        # No tool re-execution: a fresh worker replays the identical signed intent
        # as metadata only, and the independent counters never pass one effect.
        replacement = services.worker(gateway=gateway, database=db)
        replay = outcome(replacement, key, envelope, "replay")
        assert replay.json()["kind"] == "status_only" and "result" not in replay.json()
        # A later caller wait expiry cannot overwrite the recorded result: it adds
        # a wait_expired observation and stops the run, but the receipt remains.
        assert agent(db, key, "stop", envelope=envelope)["ok"]
        after_stop = invoke_agent(db, key, operation="recover", execution_id=execution_id)
        assert after_stop["recovery_state"] == "result_recorded"
        assert after_stop["receipt_status"] == "succeeded"
        assert after_stop["recovery_run_stopped"]
        assert "wait_expired" in after_stop["observation_kinds"]
        final = services.facts(gateway, target)
        assert final == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
        assert claim_count(db, execution_id) == 1
        evidence(**final, claim_count=1, worker_pids=[worker.pid, replacement.pid],
                 barriers=["B5"], mode="agent_death",
                 asserted="agent death after a durable result recovers on reload; replay is metadata-only and a late wait expiry cannot overwrite it")
    finally:
        if proc.alive:
            proc.kill()
        gate.release("B5")


@pytest.mark.scenario("F-14", "late_worker_result")
@pytest.mark.parametrize("seed", range(20))
def test_agent_wait_then_late_worker_result(services, ledger_database, seed, evidence):
    db, key = ledger_database, services.token
    session_id, owner = str(uuid4()), "test-owner"
    # Pre-create the run in the parent lane so the durable intent stays discoverable
    # by run_id after the agent's own bounded wait has expired and its process ends.
    root = agent(db, key, "create", session_id=session_id, owner_user_id=owner)
    assert root["ok"]
    run_id = root["run_id"]
    target = services.http()
    gateway = services.http(upstream=target.url)
    gate = services.barrier("B4")
    worker = services.worker(gateway=gateway, database=db, hooks=gate)
    # The agent dispatches through the real seam. The worker claims, opens the send
    # gate (taking the run mutex), acts on the target, builds the signed receipt and
    # parks at B4 - still holding the mutex, result NOT yet persisted. The agent's
    # bounded wait expires first: it latches stopped in-process and attempts a durable
    # stop, which cannot take the mutex a live worker still holds, so no stop lands.
    proc = AgentProcess(db, key, run_id=run_id, session_id=session_id, owner_user_id=owner,
                        worker_url=worker.url, timeout=5, tool_name="test.increment")
    try:
        ack = gate.wait("B4", timeout=30)
        assert ack["pid"] == worker.pid
        # The business effect already happened, before the agent gave up waiting.
        assert services.facts(gateway, target) == {
            "gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
        # Recover the durable intent by run_id while the worker still holds the gate.
        with db.connect() as conn:
            row = conn.execute("SELECT execution_id, request_envelope FROM execution_intents "
                               "WHERE run_id=%s", (run_id,)).fetchone()
        execution_id, envelope = str(row[0]), row[1]
        assert claim_count(db, execution_id) == 1
        # Mid-handoff: the claim is durable, the result is not yet recorded, and the
        # run is NOT stopped - the agent's expired wait could not take the held mutex.
        mid = ledger(db, key).lookup(execution_id)
        assert mid["state"] == "dispatch_claimed"
        assert mid["receipt"] is None
        assert not mid["run_stopped"]
        assert {f["kind"] for f in mid["observations"]} == {"claim_committed"}
        # Let the agent finish giving up. Its durable stop fails on the held mutex but
        # the in-process latch stays set (fail closed) and the frame reports uncertainty.
        facts = proc.collect(watchdog=40)
        assert facts["ok"], facts.get("reason")
        assert facts["execution_id"] == execution_id
        assert facts["frame_status"] == "error"
        assert facts["error_code"] == "OUTCOME_UNKNOWN"
        assert facts["guard_stopped"]              # latched in-process ...
        assert not facts["recovery_run_stopped"]   # ... but the durable stop never landed
        assert facts["recovery_state"] == "dispatch_claimed"
        assert facts["receipt_status"] is None
        assert facts["release_count"] == 0
        assert facts["target_verification_required"] is True
        # Now the worker records its result: release B4 so it persists the signed
        # receipt and frees the mutex. The receipt becomes durable before any later
        # stop can re-take the gate, so the late timeout can never displace it.
        gate.release("B4")
        recorded, deadline = None, time.monotonic() + 20
        while time.monotonic() < deadline:
            recorded = ledger(db, key).lookup(execution_id)
            if recorded["state"] == "result_recorded":
                break
            time.sleep(0.05)
        assert recorded["state"] == "result_recorded"
        assert recorded["receipt"]["status"] == "succeeded"
        # The late worker result ALONE made the state result-recorded, and the run is
        # still not stopped: the agent's earlier give-up left no durable trace.
        assert not recorded["run_stopped"]
        assert {f["kind"] for f in recorded["observations"]} == {"claim_committed", "worker_result"}
        # The owner lane then records the timeout the guard could not land mid-handoff
        # (the agent process is gone). It is written AFTER the receipt, so the reducer
        # keeps result-recorded while both observations remain durable.
        assert agent(db, key, "stop", envelope=envelope)["ok"]
        final = ledger(db, key).lookup(execution_id)
        assert final["state"] == "result_recorded"
        assert final["run_stopped"]
        assert final["receipt"]["status"] == "succeeded"
        assert {f["kind"] for f in final["observations"]} == {
            "claim_committed", "worker_result", "wait_expired"}
        # Original turn/card anchoring survives: the attempt id is unchanged.
        assert final["attempt_request_id"] == "agent-original"
        # At most one dispatch and exactly one effect: no re-execution, no takeover.
        assert claim_count(db, execution_id) == 1
        assert services.facts(gateway, target) == {
            "gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
        evidence(gateway_attempts=1, target_accepted=1, target_effects=1, claim_count=1,
                 worker_pids=[worker.pid], observer_pid=proc.pid, barriers=["B4"],
                 mode="late_worker_result", release_count=facts["release_count"],
                 asserted="an expired agent wait and a later worker receipt both stay durable; state is result-recorded and the original attempt anchoring survives")
    finally:
        if proc.alive:
            proc.kill()
        gate.release("B4")


@pytest.mark.parametrize("case", [pytest.param(case, marks=pytest.mark.scenario("F-23", case))
                                  for case in ("original_success", "unknown", "receipt_failure",
                                               "replay", "late", "release_race")])
def test_secret_release_requires_original_durable_success(services, ledger_database, case, evidence):
    db, key = ledger_database, services.token
    target = services.http()
    # Every case holds a generated-secret portal_copy delivery across the outcome.
    # Only a verified original durable success on a non-stopped run may reveal it;
    # the permit gate re-checks the run latch immediately before emission.
    barriers = []
    if case == "unknown":
        # The gateway returns an HTTP error after forwarding to the target, so the
        # effect may have happened and the outcome is unknown - never a permit.
        gateway = services.http(upstream=target.url, fault="http_error")
        worker = services.worker(gateway=gateway, database=db)
        facts = invoke_agent(db, key, held=True, worker_url=worker.url, timeout=20,
                             tool_name="test.increment")
    elif case == "receipt_failure":
        # The worker acts, then its receipt write rolls back: durable completion is
        # unconfirmed, so there is no original success to authorize a reveal.
        gateway = services.http(upstream=target.url)
        worker = services.worker(gateway=gateway, database=db,
                                 connection_factory=FaultFactory("receipt", "rollback"))
        facts = invoke_agent(db, key, held=True, worker_url=worker.url, timeout=20,
                             tool_name="test.increment")
    elif case == "late":
        # The agent's bounded wait expires while the worker parks at B4 holding the
        # run mutex; the success is recorded only after the agent gave up. A late
        # success is display-only and releases nothing.
        gateway = services.http(upstream=target.url)
        gate = services.barrier("B4")
        worker = services.worker(gateway=gateway, database=db, hooks=gate)
        barriers = ["B4"]
        proc = AgentProcess(db, key, held=True, worker_url=worker.url, timeout=5,
                            tool_name="test.increment")
        try:
            gate.wait("B4", timeout=30)
            facts = proc.collect(watchdog=40)
        finally:
            if proc.alive:
                proc.kill()
            gate.release("B4")
    else:  # original_success, replay, release_race
        gateway = services.http(upstream=target.url)
        worker = services.worker(gateway=gateway, database=db)
        extra = {"replay": True} if case == "replay" else \
                {"stop_before_release": True} if case == "release_race" else {}
        facts = invoke_agent(db, key, held=True, worker_url=worker.url, timeout=20,
                             tool_name="test.increment", **extra)
    assert facts["ok"], facts.get("reason")

    counts = services.facts(gateway, target)
    if case == "original_success":
        # The one path that reveals: a verified original durable success on a
        # non-stopped run mints the single-use permit and the middleware consumes
        # it exactly once to release the held delivery.
        assert facts["frame_status"] == "success"
        assert facts["release_count"] == 1
        assert facts["permit_remaining"] == 0
        assert not facts["guard_stopped"]
        assert facts["recovery_state"] == "result_recorded"
        assert facts["receipt_status"] == "succeeded"
        assert counts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
    elif case == "release_race":
        # A real durable success minted a permit, but a stop landed before the
        # middleware emitted: the gate re-checks the latch and burns the permit
        # unconsumed. The success stays recorded; the secret is never revealed.
        assert facts["frame_status"] == "success"
        assert facts["release_count"] == 0
        assert facts["permit_remaining"] == 1
        assert facts["guard_stopped"]
        assert facts["recovery_state"] == "result_recorded"
        assert counts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
    else:
        # unknown / receipt_failure / replay / late: the agent never holds a
        # verified original durable success, so no permit is minted and the held
        # delivery is never revealed - even though the target may have acted.
        assert facts["frame_status"] == "error"
        assert facts["error_code"] == "OUTCOME_UNKNOWN"
        assert facts["release_count"] == 0
        assert facts["guard_stopped"]
        assert facts["target_verification_required"] is True
        assert counts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
        if case == "replay":
            # The priming dispatch recorded the receipt; the replay is metadata-only
            # and cannot mint a permit, so the state stays result-recorded while the
            # held delivery burns.
            assert facts["recovery_state"] == "result_recorded"
            assert facts["recovery_run_stopped"]
        elif case == "late":
            # The worker still holds the mutex, so the agent's durable stop never
            # landed: only the local latch is set and the claim is still mid-handoff.
            assert not facts["recovery_run_stopped"]
            assert facts["recovery_state"] == "dispatch_claimed"
            assert facts["receipt_status"] is None
        else:  # unknown, receipt_failure
            assert facts["recovery_state"] == "outcome_unknown"
            assert facts["receipt_status"] is None
    assert claim_count(db, facts["execution_id"]) == 1
    evidence(**counts, claim_count=1, worker_pids=[worker.pid], mode=case,
             release_count=facts["release_count"], barriers=barriers,
             asserted="only a verified original durable success on a non-stopped run releases a held secret; unknown/receipt-failure/replay/late/stop-before-emission paths never reveal it")


@pytest.mark.parametrize("case", [pytest.param(case, marks=pytest.mark.scenario("F-19", case))
                                  for case in ("action_denied", "action_expired",
                                               "flow_denied", "flow_expired", "flow_stale")])
def test_denial_expiry_and_stale_flow_authority(services, ledger_database, case, evidence):
    """R-4a: a refused authority never reaches the worker.

    Each case drives the *real* ``on_check_permission`` gate (with the kernel's
    real ``flow_signer``) against a live worker/gateway/target. A denied or
    expired action approval and a revoked/expired/rebound browser-flow authority
    all fail safe — the gate parks the call (ASK) or denies it, the signer
    returns ``None``, nothing is signed or persisted, and the gateway/target the
    worker fronts are never reached (zero attempts, zero mutations).
    """
    db, key = ledger_database, services.token
    target = services.http()
    gateway = services.http(upstream=target.url)
    # A real dispatch path exists (worker fronted by the gateway) yet is never
    # used, so "zero gateway attempts" is an observed fact, not an absent dep.
    worker = services.worker(gateway=gateway, database=db)
    if case.startswith("action"):
        # A non-browser mutating action the operator denied, or whose parked card
        # expired: driven through the real ConfirmationRegistry, so the call is
        # never resumed to ALLOWED and the gate must park it.
        confirmation = "denied" if case == "action_denied" else "expired"
        facts = decide_permission(db, key, gateway_tool_name="test.increment",
                                  call_name="test_increment", confirmation=confirmation)
        assert facts["ok"], facts.get("reason")
        assert facts["confirmation_outcome"] == confirmation
    else:
        # A browser write whose flow authority was revoked (denied), lapsed
        # (expired), or rebound to a different origin since approval (stale): the
        # real flow_signer fails safe to None, so the gate parks the write.
        authority = {"flow_denied": "denied", "flow_expired": "expired",
                     "flow_stale": "stale"}[case]
        facts = decide_permission(db, key, flow_authority=authority)
        assert facts["ok"], facts.get("reason")
    # The gate refused: no ALLOW, no built-in resolution, no signed envelope, no
    # durable execution record, and no execution_requested audit. With nothing
    # signed the tool closure cannot hand off, so the worker never dispatched.
    assert facts["behavior"] in {"ASK", "DENY"}
    assert not facts["builtin_called"]
    assert facts["signed"] is False
    assert facts["execution_id"] is None
    assert facts["record_count"] == 0
    assert facts["audit_requested"] == 0
    counts = services.facts(gateway, target)
    assert counts == {"gateway_attempts": 0, "target_accepted": 0, "target_effects": 0}
    evidence(**counts, claim_count=0, worker_pids=[worker.pid], mode=case,
             asserted="denied/expired action approval and revoked/expired/stale browser-flow authority all fail safe at the real permission gate and flow signer: no ALLOW, no signed envelope, no execution record or audit, zero gateway attempts and zero target mutations")


@pytest.mark.parametrize("case", [pytest.param(case, marks=pytest.mark.scenario("F-21", case))
                                  for case in ("stale_allowed", "stale_flow",
                                               "failed_stop", "missing_run")])
def test_restart_cannot_resume_stopped_run(services, ledger_database, case, evidence):
    """R-4b/R-5d: durable uncertainty survives process loss and blocks automatic
    mutation continuation; a stopped run is never laundered back into a clean one
    and no run is reminted to keep mutating. (The fifth F-21 case,
    ``unclaimed_intent``, lives in ``test_agent_storage.py`` at the recovery seam.)

    ``stale_allowed``/``stale_flow`` drive the real ``on_check_permission`` gate:
    a durably stopped run DENYs a stale ALLOWED browser write *before* the
    ALLOWED shortcut, and DENYs a live-authority flow write *before* the signer
    can auto-sign. A fresh agent process then cannot register a continuation
    under the stopped run. ``failed_stop`` proves a stop whose durable write
    cannot land still fails closed via the latch set before the write.
    ``missing_run`` proves a lost run identity fails closed at registration.
    """
    db, key = ledger_database, services.token
    target = services.http()
    gateway = services.http(upstream=target.url)
    worker = services.worker(gateway=gateway, database=db)
    counts = {"gateway_attempts": 0, "target_accepted": 0, "target_effects": 0}

    if case == "missing_run":
        # A resume whose durable run identity was lost: the envelope is signed
        # under a run_id that was never created, so registration fails closed
        # with request_missing rather than reminting a fresh run to continue.
        orphan = signed_request(key, db.epoch)
        refused = agent(db, key, "register", envelope=orphan)
        assert not refused["ok"] and refused["reason"] == "request_missing"
        assert services.facts(gateway, target) == counts
        evidence(**counts, claim_count=0, worker_pids=[worker.pid], mode=case,
                 asserted="a lost run identity fails closed at registration (request_missing); no run is reminted to continue mutating")
        return

    if case == "failed_stop":
        # The durable stop write cannot land (the guard's store is unreachable),
        # yet the process-local latch was set first, so the gate still fails
        # closed on the stale ALLOWED write — a failed persist is never a pass.
        facts = decide_permission(db, key, gateway_tool_name="web.click", call_name="web_click",
                                  flow_authority="live", tool_call_state="allowed",
                                  stop_mode="failed_durable", stop_reason="wait_expired",
                                  guard_dsn=_unreachable_dsn(db))
        assert facts["ok"], facts.get("reason")
        assert facts["behavior"] == "DENY" and not facts["builtin_called"]
        assert facts["signed"] is False and facts["guard_stopped"] is True
        assert services.facts(gateway, target) == counts
        evidence(**counts, claim_count=0, worker_pids=[worker.pid], mode=case,
                 asserted="a stop whose durable write fails still fails closed via the process-local latch set before the write; no dispatch")
        return

    # stale_allowed / stale_flow: a durable stop lands, then the real gate refuses
    # the resume — before the ALLOWED shortcut, and before the flow signer can
    # auto-sign a live authority. Neither signs nor dispatches anything.
    facts = decide_permission(db, key, gateway_tool_name="web.click", call_name="web_click",
                              flow_authority="live",
                              tool_call_state="allowed" if case == "stale_allowed" else "pending",
                              stop_mode="durable", stop_reason="wait_expired")
    assert facts["ok"], facts.get("reason")
    assert facts["behavior"] == "DENY" and not facts["builtin_called"]
    assert facts["signed"] is False and facts["execution_id"] is None
    assert facts["record_count"] == 0 and facts["audit_requested"] == 0
    assert facts["guard_stopped"] is True
    # The durable stop survived the probe process: a fresh agent process cannot
    # register a continuation under the stopped run (no remint, no dispatch).
    next_call = signed_request(key, db.epoch, run_id=facts["run_id"], session_id=facts["session_id"])
    refused = agent(db, key, "register", envelope=next_call)
    assert not refused["ok"] and refused["reason"] == "run_stopped"
    assert services.facts(gateway, target) == counts
    evidence(**counts, claim_count=0, worker_pids=[worker.pid], mode=case,
             asserted="a durably stopped run blocks a stale ALLOWED/flow resume at the real gate and a fresh-process continuation at registration; nothing is signed or dispatched")


@pytest.mark.parametrize("case", [pytest.param(case, marks=pytest.mark.scenario("F-20", case))
                                  for case in ("duplicate_flow", "unknown_next_write", "new_card_bypass")])
@pytest.mark.parametrize("seed", range(20))
def test_flow_duplicate_and_unknown_stop_next_write(services, ledger_database, case, seed, evidence):
    """R-4b: a flow-auto-signed step dispatches once, and once a write resolves
    unknown (or a run is otherwise stopped) no later automatic write, batch
    continuation, or freshly-minted card/ID can dispatch under it.

    ``duplicate_flow`` replays a flow-auto-signed call: the single-use claim
    answers the duplicate metadata-only, so it consumes no second browser step
    (target effects stay at one). ``unknown_next_write`` drives a write to an
    unknown outcome — the gateway forwards (the effect happens) but returns an
    untrustworthy body — which durably stops the run; a later write signed under
    the same run is then refused at registration. ``new_card_bypass`` stops a run
    and proves a brand-new card (fresh confirm_id/call_id/execution_id) under the
    same stopped run is still refused: no additional card or ID evades the stop.
    F-20 is a repeated scenario, so each case runs 20 seeds.
    """
    db, key = ledger_database, services.token
    target = services.http()
    if case == "unknown_next_write":
        # The gateway forwards to the target (so the effect happens) but returns
        # an HTTP error with no trustworthy body: the write resolves unknown.
        gateway = services.http(upstream=target.url, fault="http_error")
    else:
        gateway = services.http(upstream=target.url)
    worker = services.worker(gateway=gateway, database=db)

    if case == "duplicate_flow":
        # A flow-auto-signed step (approval_kind="flow") dispatched exactly once;
        # a duplicate under a fresh request_id is answered from the single-use
        # claim and re-dispatches nothing, so it consumes no second browser step.
        envelope = signed_request(key, db.epoch, approval_kind="flow")
        register(db, envelope)
        original = outcome(worker, key, envelope, f"flow-original-{seed}")
        assert original.status_code == 200
        assert original.json()["kind"] == "original_result"
        duplicate = outcome(worker, key, envelope, f"flow-dup-{seed}")
        assert duplicate.json()["kind"] == "status_only"
        assert "result" not in duplicate.json()
        assert claim_count(db, envelope["execution_id"]) == 1
        counts = services.facts(gateway, target)
        assert counts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
        evidence(**counts, claim_count=1, worker_pids=[worker.pid], mode=case,
                 original_request_id=f"flow-original-{seed}", replay_request_id=f"flow-dup-{seed}",
                 asserted="a duplicate flow-auto-signed call is answered metadata-only from the single-use claim and consumes no second browser step; the target effect stays at one")
        return

    if case == "unknown_next_write":
        # The first write resolves unknown and durably stops the run; a later
        # automatic write signed under the same run/session/owner is refused at
        # registration (run_stopped) and never reaches the gateway or target.
        first = invoke_agent(db, key, worker_url=worker.url, timeout=20,
                             tool_name="test.increment", attempt_request_id=f"agent-original-{seed}")
        assert first["ok"], first.get("reason")
        assert first["frame_status"] == "error"
        assert first["error_code"] == "OUTCOME_UNKNOWN"
        assert first["recovery_run_stopped"] and first["guard_stopped"]
        next_write = signed_request(key, db.epoch, approval_kind="flow",
                                    run_id=first["run_id"], session_id=first["session_id"])
        refused = agent(db, key, "register", envelope=next_write, attempt_id=f"agent-next-{seed}")
        assert not refused["ok"] and refused["reason"] == "run_stopped"
        assert claim_count(db, next_write["execution_id"]) == 0
        counts = services.facts(gateway, target)
        assert counts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
        evidence(**counts, claim_count=0, worker_pids=[worker.pid], mode=case,
                 asserted="an unknown write durably stops the run, so a later automatic write under the same run is refused at registration (run_stopped) and never dispatched; only the first write reached the target")
        return

    # new_card_bypass: a run is stopped through the real agent recovery seam,
    # then a brand-new card under it (fresh confirm_id/call_id/execution_id) is
    # still refused — no additional card or ID evades the stop, and nothing
    # dispatches. The stop's wait_expired observation must bind to the same
    # attempt_request_id the card was registered under, so both share one id.
    session_id = str(uuid4())
    root = agent(db, key, "create", session_id=session_id, owner_user_id="test-owner")
    assert root["ok"], root.get("reason")
    attempt = f"agent-card-{seed}"
    card_a = signed_request(key, db.epoch, approval_kind="flow",
                            run_id=root["run_id"], session_id=session_id)
    registered = agent(db, key, "register", envelope=card_a, attempt_id=attempt)
    assert registered["ok"], registered.get("reason")
    stopped = agent(db, key, "stop", envelope=card_a, attempt_id=attempt)
    assert stopped["ok"], stopped.get("reason")
    card_b = signed_request(key, db.epoch, approval_kind="flow",
                            run_id=root["run_id"], session_id=session_id)
    assert card_b["execution_id"] != card_a["execution_id"]
    assert card_b["confirm_id"] != card_a["confirm_id"]
    assert card_b["call_id"] != card_a["call_id"]
    refused = agent(db, key, "register", envelope=card_b, attempt_id=f"agent-next-{seed}")
    assert not refused["ok"] and refused["reason"] == "run_stopped"
    assert claim_count(db, card_b["execution_id"]) == 0
    counts = services.facts(gateway, target)
    assert counts == {"gateway_attempts": 0, "target_accepted": 0, "target_effects": 0}
    evidence(**counts, claim_count=0, worker_pids=[worker.pid], mode=case,
             asserted="a freshly-minted card (new confirm_id/call_id/execution_id) under a run stopped through the real recovery seam is still refused at registration (run_stopped); no additional card or ID evades the stop and nothing dispatches")


@pytest.mark.parametrize("case", [pytest.param(case, marks=pytest.mark.scenario("F-22", case))
                                  for case in ("remote_operations", "multiple_claims", "send_stop_race")])
@pytest.mark.parametrize("seed", range(20))
def test_outstanding_operations_reported_and_next_send_blocked(services, ledger_database, case, seed, evidence):
    """R-4b: two outstanding target operations are reported independently, a call
    not yet dispatched is blocked before send, and a stop never cancels an
    operation the target already accepted.

    The plan serializes same-run worker HTTP exchanges, so the two outstanding
    target operations are modeled sequentially and are never inferred to be
    remotely serialized or canceled:

    * ``remote_operations`` — A is accepted by the target and held mid-flight
      (still active: claimed, effect done, receipt not yet durable), then commits
      and is accepted; B loses its receipt write (response lost) and stops the
      run; C is refused at registration before any send. A and B are independent
      records and A's success is NOT canceled by B's failure.
    * ``multiple_claims`` — a second worker attempts a recovery claim of an
      already-dispatched execution; the single-use claim answers metadata-only,
      so both attempts are reported independently yet exactly one dispatch lands.
    * ``send_stop_race`` — a durable stop lands while the worker is parked after
      its claim but before the final send; ``open_send`` re-checks the stop and
      refuses, so the gateway/target are never reached (blocked before send).
    F-22 is a repeated scenario, so each case runs 20 seeds.
    """
    db, key = ledger_database, services.token
    target = services.http()
    gateway = services.http(upstream=target.url)

    if case == "multiple_claims":
        # An execution dispatched once, then a second worker (a different claim
        # owner) attempts a recovery claim: the single-use claim suppresses the
        # second dispatch and answers metadata-only, referencing the first attempt.
        envelope = signed_request(key, db.epoch, approval_kind="flow")
        register(db, envelope)
        worker = services.worker(gateway=gateway, database=db)
        first = outcome(worker, key, envelope, f"claim-a-{seed}")
        assert first.json()["kind"] == "original_result"
        recover = services.worker(gateway=gateway, database=db)
        second = outcome(recover, key, envelope, f"claim-b-{seed}")
        body = second.json()
        assert body["kind"] == "status_only" and "result" not in body
        # Both attempts are reported independently: the recovery references the
        # first attempt's durable anchoring, yet only one dispatch ever landed.
        assert body["recovery"]["attempt_request_id"] == "harness-original"
        assert body["request_id"] == f"claim-b-{seed}"
        assert claim_count(db, envelope["execution_id"]) == 1
        counts = services.facts(gateway, target)
        assert counts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
        evidence(**counts, claim_count=1, worker_pids=[worker.pid, recover.pid], mode=case,
                 original_request_id=f"claim-a-{seed}", replay_request_id=f"claim-b-{seed}",
                 asserted="two claim attempts on one execution are reported independently yet the single-use claim lands exactly one dispatch; the recovery is metadata-only")
        return

    if case == "send_stop_race":
        # The worker parks after its claim but before the final send (B1). A
        # durable stop lands while the run mutex is free, then the worker is
        # released: open_send re-checks stopped_at and refuses BEFORE sending, so
        # the gateway and target are never reached.
        attempt = f"agent-send-{seed}"
        envelope = signed_request(key, db.epoch, approval_kind="flow")
        register(db, envelope, request_id=attempt)
        gate = services.barrier("B1")
        worker = services.worker(gateway=gateway, database=db, hooks=gate)
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(outcome, worker, key, envelope, f"send-{seed}")
                gate.wait("B1", timeout=30)
                # The claim is durable but nothing has been sent yet.
                assert claim_count(db, envelope["execution_id"]) == 1
                stopped = agent(db, key, "stop", envelope=envelope, attempt_id=attempt)
                assert stopped["ok"], stopped.get("reason")
                gate.release("B1")
                result = pending.result(timeout=15)
        finally:
            gate.release("B1")
        # The stop won the race: no original result, the run is stopped, and the
        # receipt never landed because the send was blocked before it happened.
        assert "result" not in result.json()
        view = ledger(db, key).lookup(envelope["execution_id"])
        assert view["run_stopped"] and view["receipt"] is None
        assert claim_count(db, envelope["execution_id"]) == 1
        counts = services.facts(gateway, target)
        assert counts == {"gateway_attempts": 0, "target_accepted": 0, "target_effects": 0}
        evidence(**counts, claim_count=1, worker_pids=[worker.pid], barriers=["B1"], mode=case,
                 asserted="a durable stop landing between claim and send makes open_send refuse before the final send; the gateway/target are never reached and the claim stays single-use")
        return

    # remote_operations: A accepted-but-still-active, B loses its response, C blocked.
    attempt_a = f"agent-a-{seed}"
    envelope_a = signed_request(key, db.epoch, approval_kind="flow")
    run_id, session_id = envelope_a["run_id"], envelope_a["session_id"]
    register(db, envelope_a, request_id=attempt_a)
    gate = services.barrier("B4")
    worker_a = services.worker(gateway=gateway, database=db, hooks=gate)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(outcome, worker_a, key, envelope_a, attempt_a)
            gate.wait("B4", timeout=30)
            # A is accepted but still active: the target acted, the claim is
            # durable, and the receipt is not yet committed.
            assert services.facts(gateway, target)["target_effects"] == 1
            mid = ledger(db, key).lookup(envelope_a["execution_id"])
            assert mid["state"] == "dispatch_claimed" and mid["receipt"] is None
            gate.release("B4")
            resp_a = pending.result(timeout=15)
    finally:
        gate.release("B4")
    assert resp_a.json()["kind"] == "original_result"
    accepted = agent(db, key, "accept", envelope=envelope_a, payload=resp_a.json(), attempt_id=attempt_a)
    assert accepted["ok"], accepted.get("reason")
    # B loses its response: the target acts but the receipt write rolls back, so
    # B is outcome_unknown and the worker stops the run.
    envelope_b = signed_request(key, db.epoch, approval_kind="flow", run_id=run_id, session_id=session_id)
    register(db, envelope_b, request_id=f"b-{seed}")
    worker_b = services.worker(gateway=gateway, database=db,
                               connection_factory=FaultFactory("receipt", "rollback"))
    resp_b = outcome(worker_b, key, envelope_b, f"b-{seed}")
    assert "result" not in resp_b.json()
    view_b = ledger(db, key).lookup(envelope_b["execution_id"])
    assert view_b["state"] == "outcome_unknown" and view_b["receipt"] is None and view_b["run_stopped"]
    # C is not yet dispatched: with the run stopped it is refused before send.
    envelope_c = signed_request(key, db.epoch, approval_kind="flow", run_id=run_id, session_id=session_id)
    refused = agent(db, key, "register", envelope=envelope_c, attempt_id=f"c-{seed}")
    assert not refused["ok"] and refused["reason"] == "run_stopped"
    assert claim_count(db, envelope_c["execution_id"]) == 0
    # A and B are reported independently, and A's accepted success is NOT canceled
    # by B's lost response or the run stop: its durable receipt still stands.
    view_a = ledger(db, key).lookup(envelope_a["execution_id"])
    assert view_a["state"] == "result_recorded" and view_a["receipt"]["status"] == "succeeded"
    assert claim_count(db, envelope_a["execution_id"]) == 1
    assert claim_count(db, envelope_b["execution_id"]) == 1
    counts = services.facts(gateway, target)
    assert counts == {"gateway_attempts": 2, "target_accepted": 2, "target_effects": 2}
    evidence(**counts, claim_count=2, worker_pids=[worker_a.pid, worker_b.pid], barriers=["B4"], mode=case,
             asserted="an accepted-but-active A and a response-lost B are reported as independent records and A's success is not canceled by B; a not-yet-dispatched C is refused before send")


@pytest.mark.parametrize("case", [pytest.param(case, marks=pytest.mark.scenario("F-24", case))
                                  for case in ("owner", "foreign", "inbox", "forged_id", "paging", "stale_poll")])
def test_recovery_owner_scope_and_paging(services, ledger_database, case, evidence):
    """F-24: the owner recovery read is owner-scoped, anti-enumeration, and paged.

    Possession of an execution id never authorizes access. Only the run owner
    reading their own session sees the projection; a foreign user, the decider
    (the approver inbox is decision-only), or a forged/unknown id all read
    ``not_found`` with no distinguishing detail, even against a recorded
    success. Observations arrive in a bounded cursor-paged window (20 per page)
    while ``state``/``receipt`` are always computed over the full validated set,
    so paging never changes the reported outcome. Unsigned or wrong-scope
    cursors are rejected without changing any durable facts. A recovery read is
    never an original response and confers no dispatch or continuation permit.
    """
    db, key = ledger_database, services.token
    envelope = prepared(db, key)
    session_id, owner, execution_id = (
        envelope["session_id"], envelope["owner_user_id"], envelope["execution_id"])

    if case == "paging":
        # Register without dispatching, then seed 25 ordinary uncertain agent
        # observations so the 20-row window is exercised past the first page.
        # transport_uncertain is in _UNCERTAIN, so the projection reads
        # outcome_unknown (never a preparation_state) on an otherwise idle run.
        assert agent(db, key, "register", envelope=envelope)["ok"]
        seeded = agent(db, key, "seed_observations", envelope=envelope, count=25)
        assert seeded["ok"] and seeded["written"].count("inserted") == 25
        first = agent(db, key, "owner_recovery", execution_id=execution_id,
                      session_id=session_id, owner_user_id=owner)
        assert first["ok"]
        page_one = first["recovery"]
        assert page_one["availability"] == "available" and page_one["state"] == "outcome_unknown"
        assert "preparation_state" not in page_one
        assert len(page_one["observations"]) == 20 and page_one["observations_truncated"]
        cursor = page_one["next_observation_cursor"]
        assert cursor is not None
        second = agent(db, key, "owner_recovery", execution_id=execution_id,
                       session_id=session_id, owner_user_id=owner, cursor=cursor)
        assert second["ok"]
        page_two = second["recovery"]
        assert len(page_two["observations"]) == 5 and page_two["next_observation_cursor"] is None
        assert page_two["state"] == "outcome_unknown"
        ids_one = {o["observation_id"] for o in page_one["observations"]}
        ids_two = {o["observation_id"] for o in page_two["observations"]}
        assert not (ids_one & ids_two) and len(ids_one | ids_two) == 25
        # Observation cursors are MAC-bound to owner, session, execution, and
        # read kind. A cursor can never widen a query or become a list cursor.
        for overrides in ({"owner_user_id": "foreign"}, {"session_id": str(uuid4())},
                          {"execution_id": str(uuid4())}, {"cursor": "42"},
                          {"cursor": ("A" if cursor[0] != "A" else "B") + cursor[1:]}):
            read = agent(db, key, "owner_recovery", **{
                "execution_id": execution_id, "session_id": session_id,
                "owner_user_id": owner, "cursor": cursor, **overrides})
            assert not read["ok"] and read["reason"] == "bad_request"
        wrong_kind = agent(db, key, "session_recovery", session_id=session_id, owner_user_id=owner, cursor=cursor)
        assert not wrong_kind["ok"] and wrong_kind["reason"] == "bad_request"
        # Enumerate ledger-only intents across three runs. None has a legacy
        # execution or confirmation row, including the two newly registered ids.
        expected = {execution_id}
        for _ in range(2):
            root = agent(db, key, "create", session_id=session_id, owner_user_id=owner)
            request = signed_request(key, db.epoch, run_id=root["run_id"], session_id=session_id)
            assert agent(db, key, "register", envelope=request)["ok"]
            expected.add(request["execution_id"])
        collected, next_cursor = set(), None
        for index in range(3):
            query = {"execution_cursor": next_cursor} if next_cursor else {}
            page = agent(db, key, "session_http", session_id=session_id, owner_user_id=owner,
                         page_size=1, **query)
            assert page["ok"] and page["status_code"] == 200
            detail = page["detail"]
            assert detail["execution_recovery_availability"] == "available"
            rows = [row for card in detail["confirmations"] for row in card["executions"]]
            assert len(rows) == 1 and rows[0]["execution_id"] not in collected
            collected.add(rows[0]["execution_id"])
            next_cursor = detail["next_execution_cursor"]
            assert detail["executions_truncated"] == (index < 2)
            assert bool(next_cursor) == (index < 2)
            if index == 0:
                for changes in ({"session_id": str(uuid4())}, {"owner_user_id": "foreign"},
                                {"execution": execution_id}):
                    refused = agent(db, key, "session_recovery", **{
                        "session_id": session_id, "owner_user_id": owner, "cursor": next_cursor, **changes})
                    assert not refused["ok"] and refused["reason"] == "bad_request"
        assert collected == expected
        assert claim_count(db, execution_id) == 0
        evidence(gateway_attempts=0, target_accepted=0, target_effects=0, claim_count=0,
                 observer_pid=first["pid"], mode=case,
                 asserted="owner recovery pages observations 20+5 and three ledger-only executions through the HTTP session route; scoped cursors reject cross-owner/session/execution/kind reuse; zero dispatch")
        return

    # Every remaining case reads a fully successful durable result, so a
    # non-owner read returning not_found proves scoping even against success.
    target = services.http()
    gateway = services.http(upstream=target.url)
    worker = services.worker(gateway=gateway, database=db)
    exchanged = agent(db, key, "exchange", envelope=envelope, worker_url=worker.url)
    assert exchanged["ok"], exchanged.get("reason")
    assert exchanged["recovery"]["state"] == "result_recorded"

    if case == "owner":
        read = agent(db, key, "owner_recovery", execution_id=execution_id,
                     session_id=session_id, owner_user_id=owner)
        assert read["ok"]
        view = read["recovery"]
        assert view["availability"] == "available" and view["state"] == "result_recorded"
        assert view["execution_id"] == execution_id and not view["run_stopped"]
        assert view["receipt"]["status"] == "succeeded" and view["target_verification_required"]
        assert {o["kind"] for o in view["observations"]} == {
            "claim_committed", "worker_result", "response_accepted"}
        assert view["next_observation_cursor"] is None and not view["observations_truncated"]
        for presentation in ("empty", "unreadable"):
            recovered = agent(db, key, "session_http", session_id=session_id,
                              owner_user_id=owner, presentation=presentation)
            assert recovered["ok"] and recovered["status_code"] == 200
            detail = recovered["detail"]
            assert detail["execution_recovery_availability"] == "available"
            card = detail["confirmations"][0]
            assert card["confirm_id"] == envelope["confirm_id"] and card["recovery_only"] is True
            assert card["turn_index"] is None and card["pending_calls"] == []
            assert card["executions"][0]["recovery"]["receipt"] == view["receipt"]
        outage = agent(db, key, "session_http", session_id=session_id, owner_user_id=owner, dsn=_unreachable_dsn(db))
        assert outage["status_code"] == 200
        assert outage["detail"]["execution_recovery_availability"] == "unavailable"
        for options in ({"caller": "foreign"}, {"deleted": True}):
            blocked = agent(db, key, "session_http", session_id=session_id, owner_user_id=owner, **options)
            assert blocked["status_code"] == 404
        asserted = ("HTTP owner recovery survives missing/unreadable presentation, distinguishes ledger outage, and refuses deleted/foreign sessions; available, result_recorded, a succeeded "
                    "receipt, target verification required, and the full claim/result/acceptance set")
    elif case in ("foreign", "inbox"):
        # A foreign user, or the decider/approver (the inbox is decision-only),
        # never reads the owner's recovery projection.
        intruder = "intruder" if case == "foreign" else envelope["decider_user_id"]
        read = agent(db, key, "owner_recovery", execution_id=execution_id,
                     session_id=session_id, owner_user_id=intruder)
        assert read["ok"]
        view = read["recovery"]
        assert view["availability"] == "not_found" and view["state"] is None
        assert view["receipt"] is None and view["observations"] == []
        assert view["execution_id"] == execution_id
        asserted = ("a non-owner caller (a foreign user, or the decision-only approver inbox) reads "
                    "not_found with no receipt or observations even against a recorded success")
    elif case == "forged_id":
        forged = str(uuid4())
        read = agent(db, key, "owner_recovery", execution_id=forged,
                     session_id=session_id, owner_user_id=owner)
        assert read["ok"]
        view = read["recovery"]
        assert view["availability"] == "not_found" and view["state"] is None
        assert view["receipt"] is None and view["observations"] == []
        assert view["execution_id"] == forged
        asserted = ("a forged/unknown execution id reads not_found echoing only the forged id, with "
                    "no receipt or observations (anti-enumeration, no distinguishing detail)")
    else:  # stale_poll
        # Repeated reads are isolated idempotent snapshots; a caller cannot
        # forge an unsigned keyset position to page beyond the signed cursor.
        first = agent(db, key, "owner_recovery", execution_id=execution_id,
                      session_id=session_id, owner_user_id=owner)
        again = agent(db, key, "owner_recovery", execution_id=execution_id,
                      session_id=session_id, owner_user_id=owner)
        view, repeat = first["recovery"], again["recovery"]
        assert view["state"] == repeat["state"] == "result_recorded"
        assert ([o["observation_id"] for o in view["observations"]]
                == [o["observation_id"] for o in repeat["observations"]])
        assert not view["replay"] and not repeat["replay"]
        stale = agent(db, key, "owner_recovery", execution_id=execution_id,
                      session_id=session_id, owner_user_id=owner, cursor="999999999")
        assert not stale["ok"] and stale["reason"] == "bad_request"
        read = again
        asserted = ("repeated reads are isolated idempotent snapshots; an unsigned numeric position is rejected "
                    "without changing the recorded tool report")

    counts = services.facts(gateway, target)
    assert counts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
    assert claim_count(db, execution_id) == 1
    evidence(**counts, claim_count=1, worker_pids=[worker.pid], observer_pid=read["pid"],
             mode=case, asserted=asserted)


@pytest.mark.parametrize("case", [pytest.param(case, marks=pytest.mark.scenario("F-25", case))
                                  for case in ("correlation", "audit_outage")])
def test_correlation_survives_duplicate_and_audit_outage(services, ledger_database, case, evidence):
    from support.http_services import correlation_facts, counts as sink_counts

    db, key = ledger_database, services.token
    sink = services.http(audit_status=503 if case == "audit_outage" else 202)
    target = services.http()
    gateway = services.http(upstream=target.url)
    worker = services.worker(gateway=gateway, database=db,
        EXECUTION_AUDIT_SERVICE_URL=sink.url, EXECUTION_AUDIT_CLIENT_ID="failure-harness",
        EXECUTION_AUDIT_CLIENT_SECRET=key)
    original_id, duplicate_id = "correlation-original", "correlation-duplicate"
    invoked = invoke_agent(db, key, worker_url=worker.url, timeout=20,
                           attempt_request_id=original_id)
    assert invoked["ok"] and invoked["frame_status"] == "success"
    execution_id = invoked["execution_id"]
    with db.connect() as conn:
        envelope = conn.execute("SELECT request_envelope FROM execution_intents WHERE execution_id=%s",
                                (execution_id,)).fetchone()[0]
    before = ledger(db, key).lookup(execution_id)
    duplicate = outcome(worker, key, envelope, duplicate_id)
    assert duplicate.headers["x-request-id"] == duplicate_id
    payload = duplicate.json()
    assert payload["kind"] == "status_only" and "result" not in payload
    assert payload["request_id"] == duplicate_id
    # Real socket headers are read from outside both the worker and the agent.
    assert correlation_facts(gateway.counter_path)["headers"] == [(original_id, execution_id)]
    assert correlation_facts(target.counter_path)["headers"] == [(original_id, execution_id)]

    read = agent(db, key, "owner_recovery", execution_id=execution_id,
                 session_id=envelope["session_id"], owner_user_id=envelope["owner_user_id"])
    assert read["ok"] and read["pid"] != invoked["pid"]
    view = read["recovery"]
    assert view["availability"] == "available" and view["state"] == "result_recorded"
    assert view["receipt"] == before["receipt"] and view["attempt_request_id"] == original_id
    assert view["receipt"]["request_id"] == original_id and view["target_verification_required"]
    facts = {fact["kind"]: fact for fact in view["observations"]}
    assert {"claim_committed", "worker_result", "response_accepted", "duplicate_seen"} <= facts.keys()
    assert facts["duplicate_seen"]["request_id"] == duplicate_id
    assert all(fact["attempt_request_id"] == original_id for fact in facts.values())
    assert facts["claim_committed"]["request_id"] == facts["worker_result"]["request_id"] == original_id

    # Wait for asynchronous sink delivery, never infer an outage from missing rows.
    deadline = time.monotonic() + 5
    count_key = "audit_attempt" if case == "audit_outage" else "audit_stored"
    while sink_counts(sink.counter_path).get(count_key, 0) < 3 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert sink_counts(sink.counter_path).get(count_key, 0) == 3
    audits = correlation_facts(sink.counter_path)["audits"]
    if case == "audit_outage":
        assert audits == [] and sink_counts(sink.counter_path).get("audit_stored", 0) == 0
    else:
        by_type = {row["event_type"]: row for row in audits}
        assert set(by_type) == {"execution_requested", "execution_completed", "execution_rejected"}
        for event_type, kind in (("execution_requested", "claim_committed"),
                                 ("execution_completed", "worker_result"),
                                 ("execution_rejected", "duplicate_seen")):
            event, fact = by_type[event_type], facts[kind]
            assert event["observation_id"] == fact["observation_id"]
            assert event["request_id"] == fact["request_id"]
            assert event["attempt_request_id"] == original_id
            assert event["execution_id"] == execution_id
            assert event["reason_code"] == fact["reason_code"]
        assert by_type["execution_requested"]["state"] == "dispatch_claimed"
        assert by_type["execution_completed"]["state"] == "result_recorded"
    counts = services.facts(gateway, target)
    assert counts == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
    assert claim_count(db, execution_id) == 1
    evidence(**counts, claim_count=1, observer_pid=read["pid"], worker_pids=[worker.pid], mode=case,
             original_request_id=original_id, replay_request_id=duplicate_id,
             asserted="external headers preserve original; duplicate fact retains its own ID; fresh owner recovery survives confirmed audit sink rejection without a second dispatch")


def _append_derived_conflict(db, key, envelope):
    from copy import deepcopy
    from execution_runtime.services.execution_signing import build_receipt, canonical_digest, sign_envelope

    store = ledger(db, key)
    original = next(f for f in store.lookup(envelope["execution_id"])["observations"]
                    if f["kind"] == "worker_result")
    fact = deepcopy(original)
    receipt = build_receipt(envelope, "failed", {"conflicting": True}, "agent-original", key)
    fact.update(observation_id=str(uuid4()), receipt=receipt,
                receipt_digest=canonical_digest(receipt), tool_status="error")
    fact["signature"] = sign_envelope(fact, key)
    assert store.append(envelope["execution_id"], fact) == "inserted"


@pytest.mark.parametrize("case", [pytest.param(case, marks=pytest.mark.scenario("F-26", case))
                                  for case in ("summary", "incident", "authoring", "foreign", "published_snapshot")])
def test_derived_facts_preserve_uncertainty(services, ledger_database, case, evidence):
    from test_crashes import ProjectionClock

    db, key = ledger_database, services.token
    variants = ("unknown", "late", "conflict", "unavailable")
    if case == "authoring":
        variants += ("original", "replay")
    if case == "published_snapshot":
        variants = ("conflict",)
    worker_pids = []
    total = 0
    for variant in variants:
        target = services.http(report={"data": {"url": "https://admin.test/path?origin-query-canary"}})
        gateway = services.http(upstream=target.url, fault="http_error" if variant == "unknown" else "none")
        # Test-only DB-time substitution at the worker: a claim is 180s earlier,
        # with its real 120s bound intact. The signed result is later than that
        # bound without changing a clock, updating immutable rows, or waiting.
        # Dispatch/signature checks and all PG constraints remain active.
        gate = services.barrier("B4") if variant == "late" else None
        worker = services.worker(gateway=gateway, database=db, hooks=gate,
            connection_factory=ProjectionClock(-180) if variant == "late" else None)
        worker_pids.append(worker.pid)
        options = dict(worker_url=worker.url, tool_name="web.click",
            parameters={"selector": "#submit"}, authoring=case == "authoring",
            replay=variant == "replay", backdate_seconds=300 if variant == "late" else 30)
        if gate is not None:
            # A deadline alone is not a local wait expiry. Hold the original
            # response until the real agent times out and latches its stop.
            proc = AgentProcess(db, key, timeout=5, **options)
            try:
                assert gate.wait("B4", timeout=30)["pid"] == worker.pid
                invoked = proc.collect(watchdog=40)
            finally:
                if proc.alive:
                    proc.kill()
                gate.release("B4")
        else:
            invoked = invoke_agent(db, key, timeout=20, **options)
        assert invoked["ok"], invoked.get("reason")
        execution_id = invoked["execution_id"]
        with db.connect() as conn:
            envelope = conn.execute("SELECT request_envelope FROM execution_intents WHERE execution_id=%s",
                                    (execution_id,)).fetchone()[0]
        if variant == "late":
            assert invoked["guard_stopped"]
            assert invoked["recovery_state"] == "outcome_unknown"
            assert invoked["receipt_status"] is None
            assert invoked["release_count"] == 0
            deadline = time.monotonic() + 20
            while True:
                recorded = ledger(db, key).lookup(execution_id)
                if recorded["state"] == "result_recorded" or time.monotonic() >= deadline:
                    break
                time.sleep(0.05)
            assert recorded["state"] == "result_recorded"
            assert recorded["receipt"]["status"] == "succeeded"
            assert "response_accepted" not in {f["kind"] for f in recorded["observations"]}
            # The worker held the mutex during wait expiry. Record the same
            # attributed stop after it releases the mutex, without tool replay.
            assert agent(db, key, "stop", envelope=envelope)["ok"]
        snapshots = []
        if case == "published_snapshot":
            for legacy in (True, False):
                saved = agent(db, key, "derived_facts", envelope=envelope, publish=True, legacy=legacy)
                assert saved["ok"]
                snapshots.extend(saved["snapshots"])
            assert len(snapshots) == 4
        if variant == "conflict":
            _append_derived_conflict(db, key, envelope)
        if case == "authoring":
            assert invoked["origin_recorded"] == (variant in {"original", "conflict", "unavailable"})
            assert invoked["graduable"] == invoked["origin_recorded"]
        derived = agent(db, key, "derived_facts", envelope=envelope,
            foreign=case == "foreign", authoring=case == "authoring", snapshots=snapshots,
            recovery_dsn=_unreachable_dsn(db) if variant == "unavailable" else db.dsn)
        assert derived["ok"] and derived["pid"] != invoked["pid"]
        if case == "foreign":
            assert derived["foreign_limited"] and derived["owner_recovery_reads"] == 0
        else:
            facts = derived["facts"]
            assert facts["target_verification_required"]
            assert facts["availability"] == ("unavailable" if variant == "unavailable" else "available")
            assert facts["integrity_conflict"] == (variant == "conflict")
            assert facts["late_report"] == (variant == "late")
            if variant in {"late", "original", "replay"}:
                assert facts["state"] == "result_recorded" and facts["tool_report_status"] == "succeeded"
            else:
                assert facts["state"] == (None if variant == "unavailable" else "outcome_unknown")
                assert facts["tool_report_status"] is None
            if variant in {"unknown", "late", "conflict", "unavailable"}:
                expected = {"unknown": "unknown outcome", "late": "late tool report",
                            "conflict": "conflicting report", "unavailable": "missing or unavailable"}[variant]
                assert expected in derived["shift_summary"]
                assert expected in derived["incident_summary"]
            assert derived["skill_evidence_retained"]
            if case == "authoring":
                assert derived["origin_recorded"] == invoked["origin_recorded"]
                assert derived["graduable"] == (variant == "original")
            if snapshots:
                assert derived["snapshots_unchanged"] == 4
        assert claim_count(db, execution_id) == 1
        assert services.facts(gateway, target) == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
        total += 1
    evidence(gateway_attempts=total, target_accepted=total, target_effects=total,
        claim_count=total, worker_pids=worker_pids, observer_pid=derived["pid"], mode=case,
        barriers=["B4"] if "late" in variants else [],
        asserted="actual consumers preserve unknown/late/conflict/outage; original-only origins survive PG reload but do not override current uncertainty; foreign scope and published snapshot bytes unchanged")
