"""SPEC-063 derived recovery facts: no authority or business-success inference."""
from copy import deepcopy
from importlib.resources import files
import json
from types import SimpleNamespace

import pytest

from agent_service.services.execution_recovery import (
    RECOVERY_AVAILABILITY,
    RECOVERY_STATES,
    TOOL_REPORT_STATUSES,
    execution_evidence_label,
    read_owner_recovery_page,
    summarize_execution_recovery,
)
from agent_service.services import runtime_dependencies


@pytest.mark.parametrize("state", [None, "not_dispatched", "dispatch_claimed", "outcome_unknown"])
def test_nonfinal_state_never_inherits_a_success_receipt(state):
    facts = summarize_execution_recovery({
        "availability": "available", "state": state,
        "receipt": {"status": "succeeded"},
    })
    assert facts["state"] == state
    assert facts["tool_report_status"] is None
    assert facts["target_verification_required"] is True
    assert facts["preparation_state"] == ("registered" if state is None else None)


@pytest.mark.parametrize("status", ["succeeded", "failed", "timeout"])
def test_late_tool_reports_survive_without_implying_business_outcome(status):
    projection = {
        "availability": "available", "state": "result_recorded", "run_stopped": True,
        "observe_by": "2026-09-24T10:00:00Z",
        "receipt": {"status": status, "completed_at": "2026-09-24T10:00:01Z"},
        "observations": [], "next_cursor": "opaque",
    }
    facts = summarize_execution_recovery(projection)
    assert facts["tool_report_status"] == status
    assert facts["late_report"] is True
    assert facts["run_stopped"] is True
    assert facts["target_verification_required"] is True
    assert status in execution_evidence_label(facts)
    assert "late report" in execution_evidence_label(facts)
    assert summarize_execution_recovery({**projection, "observations": [{"kind": "wait_expired"}]}) == facts
    assert set(facts) == {"availability", "state", "preparation_state", "tool_report_status",
                          "late_report", "integrity_conflict", "run_stopped", "target_verification_required"}


@pytest.mark.parametrize("availability", ["unavailable", "not_found", "bad", []])
def test_missing_or_unreadable_never_falls_back_to_success(availability):
    facts = summarize_execution_recovery({"availability": availability,
        "state": "result_recorded", "receipt": {"status": "succeeded"}})
    assert facts["state"] is None
    assert facts["tool_report_status"] is None
    assert facts["preparation_state"] is None


@pytest.mark.parametrize("receipt", [None, [], "bad", {}, {"status": []}])
def test_malformed_recorded_receipt_is_unknown(receipt):
    facts = summarize_execution_recovery({"availability": "available",
        "state": "result_recorded", "receipt": receipt})
    assert facts["state"] == "outcome_unknown"
    assert facts["tool_report_status"] is None


def test_conflict_overrides_recorded_success():
    facts = summarize_execution_recovery({"availability": "available",
        "state": "result_recorded", "integrity_conflict": True, "receipt": {"status": "succeeded"}})
    assert facts["state"] == "outcome_unknown"
    assert facts["tool_report_status"] is None
    assert execution_evidence_label(facts) == "Outcome unknown — conflicting reports"


def test_compact_facts_vocabulary_matches_packaged_contracts():
    def schema(name):
        return json.loads(files("agent_service").joinpath("contracts", name + ".schema.json").read_text())
    recovery = schema("execution-recovery")
    receipt = schema("execution-receipt")
    assert list(RECOVERY_AVAILABILITY) == recovery["properties"]["availability"]["enum"]
    assert list(RECOVERY_STATES) == recovery["properties"]["state"]["enum"]
    assert list(TOOL_REPORT_STATUSES) == receipt["properties"]["status"]["enum"]
    for state in RECOVERY_STATES:
        for status in TOOL_REPORT_STATUSES:
            facts = summarize_execution_recovery({"availability": "available", "state": state,
                                                  "receipt": {"status": status}})
            assert (facts["tool_report_status"] == status) == (state == "result_recorded")
            assert (status in execution_evidence_label(facts)) == (state == "result_recorded")


@pytest.mark.parametrize("state,status", [([], "succeeded"), ({}, "succeeded"),
    ("unrecognized", "succeeded"), ("result_recorded", None), ("result_recorded", "secret-canary"),
    ("outcome_unknown", "succeeded")])
def test_malformed_compact_facts_never_render_success(state, status):
    assert execution_evidence_label({"availability": "available", "state": state,
                                    "tool_report_status": status}) == "Outcome unknown"


def test_compact_facts_drop_oversize_unrecognized_material_without_mutation():
    canary = "Bearer private-projection-canary"
    projection = {"availability": "available", "state": "result_recorded",
        "receipt": {"status": "succeeded", "completed_at": canary}, "observe_by": canary,
        "parameters": {"password": canary}, "snapshot": canary * 10000,
        "observations": [{"kind": canary, "reason_code": canary}] * 100,
        "url": "https://invalid.test/?password=" + canary, "signature": canary}
    before = deepcopy(projection)
    facts = summarize_execution_recovery(projection)
    assert len(json.dumps(facts).encode()) < 1024
    assert (canary in json.dumps(facts)) is False
    assert facts["tool_report_status"] == "succeeded" and facts["late_report"] is False
    assert projection == before


def _original_browser_response():
    from uuid import uuid4
    from agentscope.message import ToolCallBlock
    from agent_service.services.hitl_confirmations import ConfirmationRegistry
    from agent_service.services.execution_protocol import observation, validate_original
    from agent_service.services.execution_recovery import ExecutionRecovery
    from agent_service.services.execution_signing import build_requests, build_receipt, canonical_digest
    key, request_id = "test-signing-key", "test-original"
    pending = ConfirmationRegistry().register("ses-original", "owner", "reply",
        [ToolCallBlock(id="call-original", name="web.click", input='{"selector":"#submit"}')], 600)
    envelope = build_requests(pending, "decider", key, run_id=str(uuid4()), admission_epoch=str(uuid4()))[0]
    result = {
        "tool_name": "web.click", "status": "success",
        "data": {"url": "https://admin.test/path?private-canary"},
        "evidence": {"executed_at": envelope["requested_at"], "duration_ms": 1,
                     "risk_level": "write", "source_system": "browser"},
    }
    receipt = build_receipt(envelope, "succeeded", result, request_id, key)
    fact = observation(envelope, source="worker", kind="worker_result", key=key,
        attempt_request_id=request_id, current_request_id=request_id,
        receipt=receipt, receipt_digest=canonical_digest(receipt), tool_status="success",
        claim_owner_id=str(uuid4()))
    recovery = ExecutionRecovery.empty("available", envelope["execution_id"], replay=False)
    for name in ("execution_id", "run_id", "admission_epoch", "session_id", "confirm_id",
                 "call_id", "tool_name", "requested_at", "expires_at"):
        recovery[name] = envelope[name]
    recovery.update(state="result_recorded", receipt=receipt, claimed_at=envelope["requested_at"],
        observe_by=envelope["expires_at"], as_of=receipt["completed_at"],
        attempt_request_id=request_id, request_digest=canonical_digest(envelope), observations=[fact])
    payload = {"protocol_version": 3, "durability": "confirmed",
               "kind": "original_result", "request_id": request_id, "result": result,
               "observation": fact, "recovery": recovery}
    return envelope, validate_original(payload, envelope, key, request_id, request_id), key, request_id


@pytest.mark.parametrize("mode", ["original", "plain_frame", "recovery", "wrong_key", "wrong_request", "wrong_execution"])
def test_authoring_origin_requires_matching_verified_original(monkeypatch, mode):
    from agent_service import runtime_kernel
    from agent_service.services.authoring_trace import InMemoryAuthoringTraceStore, make_trace_step
    envelope, original, key, request_id = _original_browser_response()
    trace = InMemoryAuthoringTraceStore()
    trace.append_step(make_trace_step(session_id=envelope["session_id"], tool_name="web.click",
        args={"selector": "#submit"}, captured_at=envelope["requested_at"],
        execution_id=envelope["execution_id"], confirm_id=envelope["confirm_id"]))
    monkeypatch.setattr(runtime_kernel, "AUTHORING_TRACE_STORE", trace)
    evidence = original if mode not in {"plain_frame", "recovery"} else (original.recovery if mode == "recovery" else None)
    request = {**envelope, "call_id": "other"} if mode == "wrong_execution" else envelope
    runtime_kernel.AgentKernel._observe_step_origin(request, original.result, "succeeded",
        original=evidence, signing_key="wrong" if mode == "wrong_key" else key,
        current_request_id="other" if mode == "wrong_request" else request_id)
    [step] = trace.load_for_session(envelope["session_id"])
    assert step["flow_origin"] == ("https://admin.test" if mode == "original" else None)
    assert "private-canary" not in str(step)


def test_owner_helper_is_disabled_by_default():
    assert runtime_dependencies.get_runtime_kernel().settings.execution_admission_enabled is False
    assert read_owner_recovery_page("session", "owner") is None


def test_owner_helper_bounds_and_scopes_read(monkeypatch):
    calls = []
    def read(*args, **kwargs):
        calls.append((args, kwargs))
        return {"availability": "available", "executions": []}
    recovery = SimpleNamespace(owner_session_recovery=read)
    monkeypatch.setattr(runtime_dependencies, "get_runtime_kernel",
                        lambda: SimpleNamespace(_execution_recovery=lambda: recovery))
    assert read_owner_recovery_page("session", "owner")["availability"] == "available"
    assert calls == [(("session", "owner"), {"page_size": 100})]


def test_owner_helper_outage_is_explicit_and_does_not_log_exception(monkeypatch, caplog):
    def failed():
        raise RuntimeError("private-exception-canary")
    monkeypatch.setattr(runtime_dependencies, "get_runtime_kernel", failed)
    assert read_owner_recovery_page("session", "owner") == {
        "availability": "unavailable", "executions": [], "executions_truncated": False}
    assert "private-exception-canary" not in caplog.text
