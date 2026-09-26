"""SPEC-063 v3 invocation coordinator unit tests (no DB; fakes + monkeypatch).

These lock the coordinator's control flow and outcome classification. The
attributed-observation durable writes themselves are validated against real
Postgres by the cross-product failure harness (F-13–F-26); here we assert the
boundary logic: register-before-send, permit only on durable original success,
uncertainty vs. blocked classification, latch-before-stop, and that a stopped
run never registers or dispatches.
"""
import asyncio
from types import SimpleNamespace

import pytest

from agent_service.services import execution_invocation
from agent_service.services.execution_invocation import (
    InvocationOutcome,
    agent_observation_kind,
    coordinate_v3_invocation,
    is_uncertain,
)
from agent_service.services.execution_protocol import ProtocolError


class FakeRecovery:
    def __init__(self, register_raises=None):
        self.register_calls = []
        self._register_raises = register_raises

    def register(self, envelope, attempt_request_id):
        self.register_calls.append((envelope, attempt_request_id))
        if self._register_raises is not None:
            raise self._register_raises
        return SimpleNamespace(execution_id=envelope.get("execution_id"))


class FakeGuard:
    def __init__(self, *, stopped=False, permit="PERMIT", release_raises=None,
                 register_raises=None):
        self.recovery = FakeRecovery(register_raises=register_raises)
        self._stopped = stopped
        self._permit = permit
        self._release_raises = release_raises
        self.ensure_calls = 0
        self.release_calls = []
        self.stop_calls = []

    def ensure_not_stopped(self):
        self.ensure_calls += 1
        if self._stopped:
            raise ProtocolError("run_stopped")

    def release_permit(self, envelope, original, current_request_id):
        self.release_calls.append((envelope, original, current_request_id))
        if self._release_raises is not None:
            raise self._release_raises
        return self._permit

    def durable_stop(self, reason, *, envelope=None, fact=None):
        self.stop_calls.append((reason, envelope, fact))
        return True


class FakeOriginal:
    def __init__(self, result):
        self._result = result

    @property
    def result(self):
        return self._result


_SETTINGS = SimpleNamespace(execution_signing_key="signing-key-1")
_ENVELOPE = {
    "execution_id": "exec-1", "run_id": "run-1", "confirm_id": "conf-1",
    "call_id": "call-1", "session_id": "ses-1", "owner_user_id": "alice",
    "tool_name": "k8s.delete_pod", "args_digest": "digest",
}


def _patch_handoff(monkeypatch, *, result=None, raises=None):
    async def fake_handoff(envelope, arguments, token, settings, attempt_id):
        if raises is not None:
            raise raises
        return FakeOriginal(result)

    monkeypatch.setattr(execution_invocation, "handoff_original", fake_handoff)


def _run(coro):
    return asyncio.run(coro)


def _coordinate(guard):
    return coordinate_v3_invocation(
        guard=guard, envelope=_ENVELOPE, arguments={"name": "pod"},
        delegated_token="delegated", settings=_SETTINGS,
        attempt_request_id="req-1", current_request_id="req-1",
    )


def test_success_mints_permit_for_successful_original(monkeypatch):
    _patch_handoff(monkeypatch, result={"status": "success", "data": {"ok": True}})
    guard = FakeGuard()
    outcome = _run(_coordinate(guard))
    assert outcome.status == "original"
    assert outcome.result == {"status": "success", "data": {"ok": True}}
    assert outcome.permit == "PERMIT"
    assert outcome.stopped is False
    assert outcome.original is guard.release_calls[0][1]
    # Registered in-lane before dispatch, and durably accepted afterward.
    assert len(guard.recovery.register_calls) == 1
    assert len(guard.release_calls) == 1
    assert guard.stop_calls == []


def test_success_withholds_permit_for_tool_failure(monkeypatch):
    """A validated tool failure is accepted but releases no secret."""
    _patch_handoff(monkeypatch, result={"status": "error", "error": {"code": "X"}})
    guard = FakeGuard()
    outcome = _run(_coordinate(guard))
    assert outcome.status == "original"
    assert outcome.permit is None
    # Acceptance still ran (response_accepted is persisted for any durable
    # original), so the permit was minted then discarded by the success gate.
    assert len(guard.release_calls) == 1
    assert outcome.stopped is False


def test_pre_dispatch_refusal_blocks_and_stops(monkeypatch):
    _patch_handoff(monkeypatch, raises=ProtocolError("credential_missing"))
    guard = FakeGuard()
    outcome = _run(_coordinate(guard))
    assert outcome.status == "blocked"
    assert outcome.reason == "credential_missing"
    assert outcome.result is None and outcome.permit is None
    assert outcome.stopped is True
    assert len(guard.stop_calls) == 1
    assert guard.stop_calls[0][0] == "credential_missing"


def test_transport_error_after_send_is_uncertain(monkeypatch):
    _patch_handoff(monkeypatch, raises=ProtocolError("transport_error"))
    guard = FakeGuard()
    outcome = _run(_coordinate(guard))
    assert outcome.status == "uncertain"
    assert outcome.reason == "transport_error"
    assert outcome.stopped is True


def test_wait_expired_is_uncertain(monkeypatch):
    _patch_handoff(monkeypatch, raises=ProtocolError("wait_expired"))
    guard = FakeGuard()
    outcome = _run(_coordinate(guard))
    assert outcome.status == "uncertain"
    assert outcome.reason == "wait_expired"
    assert agent_observation_kind("wait_expired") == "wait_expired"


def test_stopped_run_blocks_before_register_or_dispatch(monkeypatch):
    called = {"handoff": False}

    async def fake_handoff(*args, **kwargs):  # pragma: no cover - must not run
        called["handoff"] = True
        return FakeOriginal({"status": "success"})

    monkeypatch.setattr(execution_invocation, "handoff_original", fake_handoff)
    guard = FakeGuard(stopped=True)
    outcome = _run(_coordinate(guard))
    assert outcome.status == "blocked"
    assert outcome.reason == "run_stopped"
    assert guard.recovery.register_calls == []  # never registered
    assert called["handoff"] is False           # never dispatched
    # A run_stopped stop is bare (no attributed observation is appended).
    assert len(guard.stop_calls) == 1
    assert guard.stop_calls[0][0] == "run_stopped"
    assert guard.stop_calls[0][1] is None and guard.stop_calls[0][2] is None


def test_accept_failure_after_successful_send_is_uncertain(monkeypatch):
    """A durable worker result the agent cannot accept yields no permit."""
    _patch_handoff(monkeypatch, result={"status": "success", "data": {}})
    guard = FakeGuard(release_raises=ProtocolError("integrity_conflict"))
    outcome = _run(_coordinate(guard))
    assert outcome.status == "uncertain"
    assert outcome.reason == "integrity_conflict"
    assert outcome.permit is None and outcome.result is None
    assert outcome.original is None
    assert outcome.stopped is True


def test_register_failure_blocks_before_dispatch(monkeypatch):
    called = {"handoff": False}

    async def fake_handoff(*args, **kwargs):  # pragma: no cover - must not run
        called["handoff"] = True
        return FakeOriginal({"status": "success"})

    monkeypatch.setattr(execution_invocation, "handoff_original", fake_handoff)
    guard = FakeGuard(register_raises=ProtocolError("predecessor_unresolved"))
    outcome = _run(_coordinate(guard))
    assert outcome.status == "blocked"
    assert outcome.reason == "predecessor_unresolved"
    assert called["handoff"] is False
    assert outcome.stopped is True


def test_attributed_observation_is_passed_to_the_durable_stop(monkeypatch):
    """When an observation can be built, the stop carries envelope + fact."""
    _patch_handoff(monkeypatch, raises=ProtocolError("transport_error"))
    sentinel = {"kind": "transport_uncertain", "observation_id": "obs-1"}
    monkeypatch.setattr(execution_invocation, "observation", lambda *a, **k: sentinel)
    guard = FakeGuard()
    outcome = _run(_coordinate(guard))
    assert outcome.status == "uncertain"
    reason, envelope, fact = guard.stop_calls[0]
    assert reason == "transport_error"
    assert envelope is _ENVELOPE
    assert fact is sentinel


def test_observation_build_failure_falls_back_to_bare_stop(monkeypatch):
    """A non-v3 envelope cannot build a fact; the latch still fails closed."""
    _patch_handoff(monkeypatch, raises=ProtocolError("transport_error"))

    def boom(*args, **kwargs):
        raise ProtocolError("bad_request")

    monkeypatch.setattr(execution_invocation, "observation", boom)
    guard = FakeGuard()
    outcome = _run(_coordinate(guard))
    assert outcome.status == "uncertain"
    assert outcome.stopped is True
    reason, envelope, fact = guard.stop_calls[0]
    assert reason == "transport_error"
    assert envelope is None and fact is None  # bare stop


def test_agent_observation_kind_mapping():
    assert agent_observation_kind("wait_expired") == "wait_expired"
    assert agent_observation_kind("run_stopped") == "run_stopped"
    assert agent_observation_kind("transport_error") == "transport_uncertain"
    assert agent_observation_kind("response_invalid") == "transport_uncertain"
    assert agent_observation_kind("metadata_replay") == "transport_uncertain"
    assert agent_observation_kind("integrity_conflict") == "transport_uncertain"
    assert agent_observation_kind("credential_missing") == "pre_dispatch_refused"
    assert agent_observation_kind("args_digest_mismatch") == "pre_dispatch_refused"
    assert agent_observation_kind("epoch_mismatch") == "pre_dispatch_refused"


def test_is_uncertain_classification():
    assert is_uncertain("wait_expired") is True
    assert is_uncertain("transport_error") is True
    assert is_uncertain("response_invalid") is True
    assert is_uncertain("metadata_replay") is True
    assert is_uncertain("credential_missing") is False
    assert is_uncertain("run_stopped") is False
    assert is_uncertain("args_digest_mismatch") is False


@pytest.mark.parametrize("accept_fails", [False, True])
def test_invocation_passes_original_to_trusted_observer_only_after_acceptance(monkeypatch, accept_fails):
    from agent_service.tools import gateway_tools
    _patch_handoff(monkeypatch, result={"status": "success", "data": {}})
    guard = FakeGuard(release_raises=ProtocolError("integrity_conflict") if accept_fails else None)
    seen = []
    def observe(envelope, original, request_id):
        assert len(guard.release_calls) == 1
        assert original is guard.release_calls[0][1]
        seen.append((envelope, request_id))
    token = gateway_tools.EXECUTION_AUDIT_CONTEXT.set({
        "settings": _SETTINGS, "request_id": "req-1", "observe_original": observe})
    requests = gateway_tools.EXECUTION_REQUESTS.set({"call-1": _ENVELOPE})
    try:
        result = _run(gateway_tools._invoke_v3("k8s.delete_pod", "call-1", {}, "token", guard))
    finally:
        gateway_tools.EXECUTION_REQUESTS.reset(requests)
        gateway_tools.EXECUTION_AUDIT_CONTEXT.reset(token)
    assert len(seen) == (0 if accept_fails else 1)
    assert "original" not in result


def test_outcome_is_immutable():
    outcome = InvocationOutcome("original", {"status": "success"}, "P", None, False)
    with pytest.raises(Exception):
        outcome.status = "blocked"  # type: ignore[misc]
