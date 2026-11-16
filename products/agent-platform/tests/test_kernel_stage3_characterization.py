"""Stage-3 characterization gate: the ExecutionDispatcher seam.

These pins snapshot the *execution-orchestration* seam (SPEC-037/051/063) as it
behaves today, driven entirely through the public ``AgentKernel`` surface, so
the Stage-3 extraction of ``ExecutionDispatcher`` (``_execution_recovery`` /
``_resolve_run_id`` / ``_bind_guard`` / ``_prepare_executions`` /
``_persist_execution_request`` / ``_sign_flow_execution`` /
``_execution_duration_ms`` / ``_emit_execution_event``) into
``services/kernel_executions.py`` is provably byte-identical.

Every pin is written to hold *before and after* the move, and each patches only
a "move-safe" seam:

* ``agent_service.runtime_kernel.emit_audit_event`` — the long-standing audit
  patch surface (mirrors ``test_runtime_kernel._capture_flow_audits``). The
  emitter must keep resolving it through the ``runtime_kernel`` namespace so a
  test that patches it still intercepts execution audits after the move. This
  is the exact hazard class Stage 2 hit with ``AGENT_STATE_STORE``.
* instance-level ``monkeypatch.setattr(kernel, "_emit_execution_event"/...)`` —
  proves the moved methods route their sibling calls back through the kernel,
  so an instance patch on the kernel stays authoritative (the same invariant
  ``test_delegated_identity`` relies on for ``_execution_recovery``).
* read-through state ``kernel._recovery`` / ``kernel._recovery_built`` — owned by
  the collaborator after the move, still readable on the kernel.

The rich business behavior of this seam is already pinned end to end in
``test_runtime_kernel`` / ``test_hitl_confirmations``; this file adds the
wiring-focused net that guards the relocation itself.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from agentscope.message import ToolCallBlock

from agent_service.runtime_kernel import AgentKernel
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services.execution_protocol import ProtocolError
from agent_service.services.execution_recovery import ExecutionRecovery
from agent_service.services.execution_run_guard import RunGuard
from agent_service.services.execution_signing import REASON_SIGNING_UNAVAILABLE
from agent_service.services.hitl_confirmations import CONFIRMATION_REGISTRY

FLOW_SIGNING_KEY = "test-flow-execution-key"


def _kernel(**overrides) -> AgentKernel:
    kwargs = dict(
        api_key="test-key",
        execution_signing_key=FLOW_SIGNING_KEY,
        browser_flow_approval_ttl=900,
    )
    kwargs.update(overrides)
    return AgentKernel(settings=RuntimeSettings(**kwargs))


def _capture_audits(monkeypatch) -> list:
    """Capture audit events through the runtime_kernel patch surface."""
    events: list = []

    def fake_emit(settings, event):
        events.append(event)

    monkeypatch.setattr("agent_service.runtime_kernel.emit_audit_event", fake_emit)
    return events


def _register(session_id, *tool_calls, risk_levels=None):
    return CONFIRMATION_REGISTRY.register(
        session_id,
        "alice",
        "reply-1",
        list(tool_calls),
        600,
        risk_levels=(
            {call.name: "write" for call in tool_calls}
            if risk_levels is None
            else risk_levels
        ),
    )


class _FakeRunRecovery:
    """Stand-in for ExecutionRecovery's run-minting surface (no DB)."""

    def __init__(self, *, run_id="run-minted", raise_on_create=None):
        self._run_id = run_id
        self._raise = raise_on_create
        self.create_calls: list = []

    def create_run(self, session_id, owner_user_id):
        self.create_calls.append((session_id, owner_user_id))
        if self._raise is not None:
            raise self._raise
        return self._run_id


# --- the audit patch-surface hazard (the Stage-2 AGENT_STATE_STORE class) ---


def test_emit_execution_event_uses_runtime_kernel_audit_patch_surface(monkeypatch):
    """``_emit_execution_event`` must be intercepted by patching
    ``agent_service.runtime_kernel.emit_audit_event`` — the emitter resolves the
    symbol through the kernel module namespace, not a captured local binding."""
    audits = _capture_audits(monkeypatch)
    kernel = _kernel()

    kernel._emit_execution_event(
        "execution_requested",
        "success",
        {"confirm_id": "conf-1", "call_id": "call-1"},
        "req-1",
        "ses-1",
        "alice",
    )

    assert len(audits) == 1
    event = audits[0]
    assert event["event_type"] == "execution_requested"
    assert event["outcome"] == "success"
    assert event["request_id"] == "req-1"
    assert event["session_id"] == "ses-1"
    assert event["subject"] == "alice"
    assert event["details"] == {"confirm_id": "conf-1", "call_id": "call-1"}


# --- recovery factory + read-through state ---


def test_execution_recovery_inert_and_state_read_through_when_disabled():
    """SPEC-063 R-2a: disabled admission yields no store; ``_recovery`` /
    ``_recovery_built`` stay readable on the kernel and never flip."""
    kernel = AgentKernel(settings=RuntimeSettings(api_key=None))
    assert kernel.settings.execution_admission_enabled is False
    assert kernel._execution_recovery() is None
    assert kernel._execution_recovery() is None
    assert kernel._recovery_built is False
    assert kernel._recovery is None


def test_execution_recovery_builds_caches_and_reads_through_when_enabled():
    kernel = AgentKernel(
        settings=RuntimeSettings(
            api_key=None,
            execution_signing_key="signing-key-1",
            execution_admission_enabled=True,
            execution_state_db_url="postgres://agent@ledger:5432/exec",
            execution_admission_epoch="epoch-7",
        )
    )
    recovery = kernel._execution_recovery()
    assert isinstance(recovery, ExecutionRecovery)
    # Cached: a second call returns the same instance, built once.
    assert kernel._execution_recovery() is recovery
    assert kernel._recovery_built is True
    assert kernel._recovery is recovery


# --- durable run identity + guard ---


def test_resolve_run_id_inherits_mints_and_fails_closed():
    kernel = AgentKernel(settings=RuntimeSettings(api_key=None))

    # A reused flow authority inherits its originating run without minting.
    inheriting = _FakeRunRecovery()
    assert (
        kernel._resolve_run_id(
            inheriting, "ses-1", "alice", flow_approval=SimpleNamespace(run_id="run-origin")
        )
        == "run-origin"
    )
    assert inheriting.create_calls == []

    # A new human root turn mints one via the ledger.
    minting = _FakeRunRecovery(run_id="run-new")
    assert kernel._resolve_run_id(minting, "ses-1", "alice") == "run-new"
    assert minting.create_calls == [("ses-1", "alice")]

    # A failed mint yields no identity: the lane fails closed, never re-mints.
    failing = _FakeRunRecovery(raise_on_create=ProtocolError("store_unavailable"))
    assert kernel._resolve_run_id(failing, "ses-1", "alice") is None


def test_bind_guard_carries_the_resolved_run_identity():
    kernel = AgentKernel(settings=RuntimeSettings(api_key=None))
    guard = kernel._bind_guard(_FakeRunRecovery(), "run-1", "ses-1", "alice")
    assert isinstance(guard, RunGuard)
    assert guard.run_id == "run-1"
    assert guard.identity.session_id == "ses-1"
    assert guard.identity.owner_user_id == "alice"


# --- per-action signing site (_prepare_executions) ---


def test_prepare_executions_denial_constructs_nothing(monkeypatch):
    audits = _capture_audits(monkeypatch)
    kernel = _kernel()
    pending = _register("ses-deny", ToolCallBlock(id="call-1", name="k8s.restart_service", input="{}"))

    requests, rejection = kernel._prepare_executions(
        pending, "bob-approver", False, "req-9", "ses-deny"
    )

    assert requests == {}
    assert rejection is None
    assert audits == []


def test_prepare_executions_missing_key_rejects_batch_and_audits_deny(monkeypatch):
    audits = _capture_audits(monkeypatch)
    kernel = _kernel(execution_signing_key=None)
    pending = _register(
        "ses-nokey", ToolCallBlock(id="call-1", name="k8s.restart_service", input='{"namespace": "ops"}')
    )

    requests, rejection = kernel._prepare_executions(
        pending, "bob-approver", True, "req-9", "ses-nokey"
    )

    assert requests == {}
    assert rejection == REASON_SIGNING_UNAVAILABLE
    assert [a["event_type"] for a in audits] == ["execution_rejected"]
    assert audits[0]["outcome"] == "deny"
    assert audits[0]["details"]["call_id"] == "call-1"
    assert audits[0]["details"]["reason"] == REASON_SIGNING_UNAVAILABLE


def test_prepare_executions_routes_emit_and_persist_back_through_kernel(monkeypatch):
    """The signed batch must call ``_emit_execution_event`` and
    ``_persist_execution_request`` *through the kernel instance*, so an
    instance-level patch stays authoritative after the move (the dispatcher
    routes sibling calls back via ``self._kernel``)."""
    kernel = _kernel()
    emitted: list = []
    persisted: list = []
    monkeypatch.setattr(
        kernel, "_emit_execution_event", lambda *a, **k: emitted.append(a)
    )
    monkeypatch.setattr(
        kernel, "_persist_execution_request", lambda req: persisted.append(req)
    )
    pending = _register(
        "ses-route", ToolCallBlock(id="call-1", name="k8s.restart_service", input='{"namespace": "ops"}')
    )

    requests, rejection = kernel._prepare_executions(
        pending, "bob-approver", True, "req-9", "ses-route"
    )

    assert rejection is None
    assert set(requests) == {"call-1"}
    # One durable write and one execution_requested audit, both via the kernel.
    assert len(persisted) == 1
    assert persisted[0]["call_id"] == "call-1"
    assert [call[0] for call in emitted] == ["execution_requested"]


# --- flow-unlock signing site (_sign_flow_execution) ---


def test_sign_flow_execution_refuses_a_non_browser_write():
    """SPEC-055 R-5: the signer enforces its own "one browser write" scope
    ahead of every side effect, so a non-browser name parks (returns None)."""
    kernel = _kernel()
    tool_call = ToolCallBlock(id="call-infra", name="k8s.restart_service", input="{}")
    assert kernel._sign_flow_execution(tool_call, "k8s.restart_service") is None


# --- receipt timing helper ---


def test_execution_duration_ms_computes_whole_ms_and_zero_on_bad_input():
    kernel = _kernel()
    started = datetime.now(timezone.utc) - timedelta(seconds=2)
    request = {"requested_at": started.strftime("%Y-%m-%dT%H:%M:%SZ")}
    duration = kernel._execution_duration_ms(request)
    assert isinstance(duration, int)
    assert 0 <= duration < 60_000

    # Missing / malformed timestamps degrade to 0, never raise.
    assert kernel._execution_duration_ms({}) == 0
    assert kernel._execution_duration_ms({"requested_at": "not-a-timestamp"}) == 0
