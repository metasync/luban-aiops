"""Run-guard unit proofs: synchronous monotonic latch, fail-closed durable stop,
and the typed single-use secret-release permit (SPEC-063 R-4, F-21 foundation).

These are process-local contract proofs and need no Postgres: the guard's own
safety must hold even when the durable store is absent or failing, which is
exactly the seam the failure harness exercises end-to-end elsewhere.
"""
from __future__ import annotations

import copy
import pickle
import uuid

import pytest

from agent_service.services.execution_protocol import (
    ProtocolError,
    VerifiedOriginal,
    _ORIGINAL_AUTHORITY,
)
from agent_service.services.execution_run_guard import (
    RunGuard,
    RunIdentity,
    RunStopLatch,
    SecretReleasePermit,
    bind_run,
)


class FakeRecovery:
    """Stands in for ExecutionRecovery: records calls, raises on demand."""

    def __init__(self, *, stop_raises=False, accept_raises=False):
        self.stop_calls: list[dict] = []
        self.accept_calls: list[tuple] = []
        self._stop_raises = stop_raises
        self._accept_raises = accept_raises
        self.created: list[tuple] = []
        self._run_id = str(uuid.uuid4())

    def create_run(self, session_id, owner_user_id):
        self.created.append((session_id, owner_user_id))
        return self._run_id

    def stop_run(self, run_id, session_id, owner_user_id, *, reason, envelope=None, fact=None):
        self.stop_calls.append({"run_id": run_id, "reason": reason})
        if self._stop_raises:
            raise ProtocolError("store_unavailable")
        return "stopped"

    def accept(self, envelope, original, current_request_id):
        self.accept_calls.append((envelope, original, current_request_id))
        if self._accept_raises:
            raise ProtocolError("response_invalid")
        return {"kind": "response_accepted"}


def _identity():
    return RunIdentity(str(uuid.uuid4()), "session-1", "owner-1")


def _verified_original(receipt_digest="r" * 64):
    # Constructed through the sanctioned internal authority; the guard only reads
    # observation["receipt_digest"] and hands the object to recovery.accept.
    return VerifiedOriginal(
        _ORIGINAL_AUTHORITY,
        {"observation": {"receipt_digest": receipt_digest}},
        "attempt-1",
        "current-1",
    )


def _envelope(execution_id=None):
    return {"execution_id": execution_id or str(uuid.uuid4()), "run_id": "run-1"}


# --- latch -----------------------------------------------------------------


def test_latch_is_monotonic_and_never_resets():
    latch = RunStopLatch()
    assert not latch.is_stopped("run-a")
    latch.mark("run-a", "wait_expired")
    assert latch.is_stopped("run-a") and latch.reason("run-a") == "wait_expired"
    # A second, different reason must not overwrite the first (monotonic).
    latch.mark("run-a", "run_stopped")
    assert latch.reason("run-a") == "wait_expired"
    # Distinct runs are independent.
    assert not latch.is_stopped("run-b")


def test_ensure_not_stopped_raises_after_mark():
    latch = RunStopLatch()
    guard = RunGuard(_identity(), latch=latch)
    guard.ensure_not_stopped()  # clean run passes
    guard.mark_stopped("transport_uncertain")
    with pytest.raises(ProtocolError) as exc:
        guard.ensure_not_stopped()
    assert exc.value.args[0] == "run_stopped"


# --- durable stop ----------------------------------------------------------


def test_durable_stop_success_sets_latch_and_returns_true():
    latch, recovery = RunStopLatch(), FakeRecovery()
    guard = RunGuard(_identity(), recovery=recovery, latch=latch)
    assert guard.durable_stop("wait_expired") is True
    assert recovery.stop_calls and recovery.stop_calls[0]["reason"] == "wait_expired"
    with pytest.raises(ProtocolError):
        guard.ensure_not_stopped()


def test_durable_stop_failure_keeps_latch_set_and_returns_false():
    """A failed durable write must still fail closed in-process (R-4 step 2)."""
    latch = RunStopLatch()
    recovery = FakeRecovery(stop_raises=True)
    guard = RunGuard(_identity(), recovery=recovery, latch=latch)
    assert guard.durable_stop("receipt_unconfirmed") is False
    assert recovery.stop_calls  # the write was attempted
    with pytest.raises(ProtocolError):
        guard.ensure_not_stopped()  # latch set before the write, stays set


def test_durable_stop_without_recovery_is_local_only():
    latch = RunStopLatch()
    guard = RunGuard(_identity(), recovery=None, latch=latch)
    assert guard.durable_stop("run_stopped") is False
    with pytest.raises(ProtocolError):
        guard.ensure_not_stopped()


# --- secret-release permit -------------------------------------------------


def test_permit_requires_a_durable_recovery_store():
    guard = RunGuard(_identity(), recovery=None, latch=RunStopLatch())
    with pytest.raises(ProtocolError) as exc:
        guard.release_permit(_envelope(), _verified_original(), "current-1")
    assert exc.value.args[0] == "receipt_unconfirmed"


def test_permit_rejects_non_verified_original_before_acceptance():
    """A dict / recovery page / status frame can never mint a permit."""
    recovery = FakeRecovery()
    guard = RunGuard(_identity(), recovery=recovery, latch=RunStopLatch())
    for bad in ({"kind": "original_result"}, "success", None, 42):
        with pytest.raises(ProtocolError) as exc:
            guard.release_permit(_envelope(), bad, "current-1")
        assert exc.value.args[0] == "response_invalid"
    assert recovery.accept_calls == []  # type gate fires before any durable write


def test_permit_refused_on_stopped_run():
    latch = RunStopLatch()
    recovery = FakeRecovery()
    guard = RunGuard(_identity(), recovery=recovery, latch=latch)
    guard.mark_stopped("wait_expired")
    with pytest.raises(ProtocolError) as exc:
        guard.release_permit(_envelope(), _verified_original(), "current-1")
    assert exc.value.args[0] == "run_stopped"
    assert recovery.accept_calls == []


def test_permit_refused_when_durable_acceptance_fails():
    recovery = FakeRecovery(accept_raises=True)
    guard = RunGuard(_identity(), recovery=recovery, latch=RunStopLatch())
    with pytest.raises(ProtocolError):
        guard.release_permit(_envelope(), _verified_original(), "current-1")
    assert len(recovery.accept_calls) == 1  # acceptance was attempted and failed


def test_permit_minted_from_durable_original_success_is_single_use():
    recovery = FakeRecovery()
    guard = RunGuard(_identity(), recovery=recovery, latch=RunStopLatch())
    envelope = _envelope()
    permit = guard.release_permit(envelope, _verified_original("a" * 64), "current-1")
    assert isinstance(permit, SecretReleasePermit)
    assert permit.run_id == guard.run_id
    assert permit.execution_id == envelope["execution_id"]
    assert permit.receipt_digest == "a" * 64
    assert len(recovery.accept_calls) == 1
    assert permit.consumed is False
    permit.consume()
    assert permit.consumed is True
    with pytest.raises(TypeError):
        permit.consume()  # single-use


def test_permit_cannot_be_serialized_or_copied():
    recovery = FakeRecovery()
    guard = RunGuard(_identity(), recovery=recovery, latch=RunStopLatch())
    permit = guard.release_permit(_envelope(), _verified_original(), "current-1")
    with pytest.raises(TypeError):
        pickle.dumps(permit)
    with pytest.raises(TypeError):
        copy.copy(permit)
    with pytest.raises(TypeError):
        copy.deepcopy(permit)


def test_permit_cannot_be_forged_without_authority():
    with pytest.raises(TypeError):
        SecretReleasePermit(object(), "run-1", "exec-1", "digest")


# --- persistent identity ---------------------------------------------------


def test_bind_run_mints_only_for_a_new_root():
    recovery = FakeRecovery()
    guard = bind_run(recovery, "session-1", "owner-1")
    assert guard.run_id == recovery._run_id
    assert recovery.created == [("session-1", "owner-1")]
    # A restore rebinds the existing UUID and must not mint a new run.
    recovery2 = FakeRecovery()
    existing = str(uuid.uuid4())
    restored = bind_run(recovery2, "session-1", "owner-1", run_id=existing)
    assert restored.run_id == existing
    assert recovery2.created == []
