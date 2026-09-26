"""Drive the real agent permission seam (on_check_permission + flow_signer).

This probe launches the *actual* product gate a mutating browser/action write
hits before any byte can reach a worker, with durable admission enabled:

* ``GatewayPermissionMiddleware.on_check_permission`` including the SPEC-063 R-4
  stop-before-ALLOWED gate (a stopped run's mutating call is DENY outright).
* the kernel's real ``flow_signer`` (``AgentKernel._sign_flow_execution``) with
  live ``FLOW_APPROVALS``/``FLOW_CONTEXTS`` state, so a denied/expired/stale
  authority fails safe (``None``) exactly as it does in production, and the
  SPEC-063 R-4 (T-21) flow-signing stop gate is exercised on the real seam.

Nothing about the gate or the signer is mocked away; the only substitution is the
model, replaced by one deterministic scripted tool call, and the built-in
permission resolution behind ``next_handler`` (which agentscope would otherwise
run for an already-ALLOWED/read-only call). Only bounded, safe facts leave this
process (closed decision enum, whether an envelope was signed, durable record and
audit counts, ids) — never raw tool output, secret material, or exception text —
so the parent test can assert on them and write an allowlisted evidence record.

It is the cross-product sibling of ``agent_invocation_probe.py`` (the dispatch
seam downstream of this gate) and ``agent_ledger_probe.py`` (pure ledger ops).
"""
import asyncio
import json
import logging
import os
import time
from types import SimpleNamespace
from uuid import uuid4

os.environ["OTEL_SDK_DISABLED"] = "true"
logging.disable(logging.CRITICAL)

from agentscope.message import ToolCallBlock, ToolCallState
from agentscope.permission import PermissionBehavior, PermissionDecision

from agent_service.runtime_kernel import AgentKernel
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services.execution_protocol import ProtocolError
from agent_service.services.execution_records import EXECUTION_RECORD_STORE
from agent_service.services.execution_recovery import ExecutionRecovery
from agent_service.services.execution_run_guard import CURRENT_RUN_GUARD, bind_run
from agent_service.services.flow_approvals import FLOW_APPROVALS, FLOW_CONTEXTS
from agent_service.services.hitl_confirmations import (
    ConfirmationExpired, ConfirmationRegistry,
)
from agent_service.services.kernel_middleware import GatewayPermissionMiddleware
from agent_service.tools.gateway_tools import (
    CHAT_SESSION_ID, EXECUTION_AUDIT_CONTEXT, EXECUTION_REQUESTS,
)

# Browser writes the flow signer is scoped to; mirrored from the product so a
# probe never silently drifts from BROWSER_WRITE_TOOLS.
_FLOW_SKILL = "samples/password-reset"
_FLOW_ORIGIN = "http://admin.local"


def _kernel(data, dsn):
    """A kernel with durable admission armed exactly as a deployed agent runs."""
    return AgentKernel(settings=RuntimeSettings(
        api_key="test-key",
        execution_signing_key=data["key"],
        execution_state_db_url=dsn,
        execution_admission_enabled=True,
        execution_admission_epoch=data["epoch"],
        browser_flow_approval_ttl=data.get("flow_ttl", 900),
    ))


def _record_flow_authority(data, session_id, run_id):
    """Arm FLOW_APPROVALS/FLOW_CONTEXTS for the requested authority shape.

    ``live`` signs; ``denied`` (revoked/absent approval), ``expired`` (TTL
    lapse), and ``stale`` (identity rebind since approval) each fail safe to
    ``None`` on the real signer, so the write parks and nothing is dispatched.
    """
    mode = data.get("flow_authority", "live")
    skill_id = data.get("flow_skill_id", _FLOW_SKILL)
    origin = data.get("flow_origin", _FLOW_ORIGIN)
    if mode in {"denied", "none"}:
        # A bound flow the operator never approved (or an approval revoked by a
        # flow-killing error): context present, no live authority.
        FLOW_CONTEXTS.record(session_id, {"skill_id": skill_id, "origin": origin,
                                          "title": "Reset User Password",
                                          "description": "reset", "risk_class": "write"})
        return
    ttl = 0 if mode == "expired" else float(data.get("flow_ttl", 900))
    FLOW_APPROVALS.record(session_id=session_id, confirm_id=data.get("confirm_id", "conf-approving"),
                          owner_user_id=data.get("owner_user_id", "test-owner"),
                          decider_user_id=data.get("decider_user_id", "test-decider"),
                          skill_id=skill_id, origin=origin, ttl=ttl, run_id=run_id)
    context_origin = data.get("stale_origin", "http://other.local") if mode == "stale" else origin
    FLOW_CONTEXTS.record(session_id, {"skill_id": skill_id, "origin": context_origin,
                                      "title": "Reset User Password",
                                      "description": "reset", "risk_class": "write"})


def _drive_confirmation(data, session_id, tool_call):
    """Reproduce why a mutating action call reaches the gate WITHOUT an ALLOWED
    state: the operator denied it, or its pending confirmation expired.

    Both are driven through the real ``ConfirmationRegistry`` so the case is
    anchored at the actual HITL seam, not a synthetic flag. Either way the call
    is never resumed to ``ToolCallState.ALLOWED``, so the permission gate must
    park it (ASK) and sign nothing — zero gateway attempts.
    """
    mode = data.get("confirmation")
    if not mode:
        return "none"
    registry = ConfirmationRegistry()
    pending = registry.register(session_id, data.get("owner_user_id", "test-owner"),
                                "probe-reply", [tool_call], 600)
    if mode == "expired":
        # Backdate past the TTL so ``get`` raises the real expiry, exactly as a
        # parked card that lapsed before the operator resumed it would.
        pending.created_at = time.monotonic() - 10_000
        try:
            registry.get(session_id, pending.confirm_id, 1)
            return "not_expired"
        except ConfirmationExpired:
            return "expired"
    # "denied": the operator's deny decision consumes the parked confirmation;
    # it is resolved (no longer parked) and the call never becomes ALLOWED.
    registry.resolve(session_id, pending.confirm_id)
    return "denied"


async def _decide(data):
    dsn = data.get("recovery_dsn", data["dsn"])
    session_id = data.get("session_id") or str(uuid4())
    owner = data.get("owner_user_id", "test-owner")
    call_id = data.get("call_id") or str(uuid4())
    gateway_tool_name = data.get("gateway_tool_name", "web.click")
    call_name = data.get("call_name", "web_click")
    parameters = data.get("parameters", {"ref": 1})
    is_read_only = bool(data.get("read_only"))

    kernel = _kernel(data, dsn)
    recovery = kernel._execution_recovery()
    run_id = data.get("run_id") or recovery.create_run(session_id, owner)
    _record_flow_authority(data, session_id, run_id)

    # Bind the run guard the gate and the flow-signing seam both consult. A
    # separate guard DSN lets F-21 ``failed_stop`` prove a durable stop that
    # cannot persist still fails closed via the process-local latch.
    guard_dsn = data.get("guard_dsn", dsn)
    guard_recovery = (ExecutionRecovery(guard_dsn, data["key"], data["epoch"], admission_enabled=True)
                      if guard_dsn != dsn else recovery)
    guard = bind_run(guard_recovery, session_id, owner, run_id=run_id)
    stop_mode = data.get("stop_mode")
    if data.get("pre_stopped") or stop_mode:
        reason = data.get("stop_reason", "wait_expired")
        if stop_mode == "latch" or (data.get("pre_stopped") and not stop_mode):
            guard.mark_stopped(reason)
        else:  # "durable" / "failed_durable"
            guard.durable_stop(reason)

    state = ToolCallState.ALLOWED if data.get("tool_call_state") == "allowed" else ToolCallState.PENDING
    tool_call = ToolCallBlock(id=call_id, name=call_name, input=json.dumps(parameters), state=state)
    confirmation_outcome = _drive_confirmation(data, session_id, tool_call)
    tool = SimpleNamespace(name=call_name, is_read_only=is_read_only, gateway_tool_name=gateway_tool_name)
    agent = SimpleNamespace(toolkit=SimpleNamespace(tool_groups=[]))

    audits: list = []
    import agent_service.runtime_kernel as rk
    original_emit = rk.emit_audit_event
    rk.emit_audit_event = lambda settings, event: audits.append(event)

    requests: dict = {}
    builtin = {"called": False}

    async def next_handler(**_kwargs):
        # Stand in for agentscope's built-in permission resolution, which the
        # middleware delegates to for an already-ALLOWED or tool-less call.
        builtin["called"] = True
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, message="builtin-resolution")

    middleware = GatewayPermissionMiddleware(flow_signer=kernel._sign_flow_execution)
    tokens = [
        (CHAT_SESSION_ID, CHAT_SESSION_ID.set(session_id)),
        (EXECUTION_REQUESTS, EXECUTION_REQUESTS.set(requests)),
        (EXECUTION_AUDIT_CONTEXT, EXECUTION_AUDIT_CONTEXT.set(
            {"request_id": data.get("request_id", "req-probe"), "session_id": session_id})),
        (CURRENT_RUN_GUARD, CURRENT_RUN_GUARD.set(guard)),
    ]
    try:
        decision = await middleware.on_check_permission(
            agent, {"tool": tool, "tool_call": tool_call}, next_handler)
    finally:
        rk.emit_audit_event = original_emit
        for variable, token in reversed(tokens):
            variable.reset(token)

    signed_envelope = requests.get(call_id)
    return {
        "run_id": run_id,
        "session_id": session_id,
        "call_id": call_id,
        "behavior": decision.behavior.name,
        "builtin_called": builtin["called"],
        "confirmation_outcome": confirmation_outcome,
        "signed": signed_envelope is not None,
        "execution_id": (signed_envelope or {}).get("execution_id"),
        "record_count": len(EXECUTION_RECORD_STORE.load_for_session(session_id)),
        "audit_requested": sum(1 for a in audits if a.get("event_type") == "execution_requested"),
        "guard_stopped": bool(guard.stopped()),
    }


def main(data):
    operation = data.get("operation", "decide")
    if operation == "decide":
        return asyncio.run(_decide(data))
    raise AssertionError("unsupported probe operation")


if __name__ == "__main__":
    import sys
    try:
        result = {"ok": True, **main(json.load(sys.stdin))}
    except ProtocolError as exc:
        result = {"ok": False, "reason": exc.reason}
    result["pid"] = os.getpid()
    print(json.dumps(result))
