"""Authenticated v3 admission; only an acknowledged durable claim can send."""
from __future__ import annotations

import asyncio
import hmac
import logging

import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from execution_runtime.core.config import get_settings
from execution_runtime.core.metrics import (
    record_audit_emit, record_completion, record_conflict, record_duplicate,
    record_handoff, record_rejection, record_store_write_failure,
)
from execution_runtime.services.audit_emitter import build_audit_event, emit_audit_event
from execution_runtime.services.execution_io import database_budget, owned_thread, remaining
from execution_runtime.services.execution_protocol import (
    ProtocolError, observation, validate, validate_request,
)
from execution_runtime.services.execution_signing import build_receipt, canonical_digest
from execution_runtime.services.executor import GatewayUncertain, execute_tool, map_result_status

router = APIRouter()
_STORE_ERRORS = (psycopg.Error, ProtocolError)


def response(kind, request_id, recovery=None, *, status=200, durability="not_applicable", **fields):
    body = {"protocol_version": 3, "kind": kind, "request_id": request_id,
            "recovery": recovery, "durability": durability, **fields}
    validate("execution-handoff-response", body)
    return JSONResponse(status_code=status, content=body, headers={"x-request-id": request_id})


def refused(request_id, reason, recovery=None):
    record_rejection(reason)
    status = (401 if reason == "unauthorized" else 410 if reason == "request_expired" else
              409 if reason in {"identity_conflict", "run_stopped", "predecessor_unresolved"} else 400)
    return response("refused", request_id, recovery, status=status, reason_code=reason)


async def barrier(request, name):
    # Dependency injection only. No environment switch or production control route.
    hook = request.app.state.lifecycle_hook
    if hook is not None:
        await asyncio.to_thread(hook.hit, name)


def audit_execution(settings, envelope, event_type, outcome, state, fact, **details):
    """Mirror bounded ledger facts; audit delivery is never execution authority."""
    if fact is None:
        return
    try:
        emit_audit_event(settings, build_audit_event(
            event_type, fact["request_id"], outcome,
            details={"execution_id": envelope["execution_id"], "confirm_id": envelope["confirm_id"],
                     "call_id": envelope["call_id"], "tool_name": envelope["tool_name"],
                     "attempt_request_id": fact["attempt_request_id"], "state": state,
                     "reason_code": fact["reason_code"], "observation_id": fact["observation_id"],
                     **details},
            subject=envelope["decider_user_id"], username=envelope["decider_user_id"],
            session_id=envelope["session_id"]))
    except Exception:  # An audit thread failing to start cannot erase a durable result.
        record_audit_emit("error")
        logging.getLogger(__name__).warning("execution audit emission unavailable")


async def current_status(ledger, execution_id, request_id, *, durability="confirmed", audit=None):
    recovery = await asyncio.to_thread(ledger.lookup, execution_id)
    if audit is not None:
        settings, envelope, fact = audit
        audit_execution(settings, envelope, "execution_rejected", "deny", recovery["state"], fact)
    if recovery["availability"] == "unavailable":
        return response("unavailable", request_id, recovery, status=503, durability="unconfirmed")
    return response("status_only", request_id, recovery,
                    status=200 if recovery["state"] == "result_recorded" else 202, durability=durability)


async def stop(ledger, envelope, request_id, attempt_id, key, reason, *, refused_before_claim=False, conn=None, kind=None):
    fact = observation(envelope, source="worker",
                       kind=kind or ("pre_dispatch_refused" if refused_before_claim else "transport_uncertain"),
                       attempt_request_id=attempt_id, current_request_id=request_id, key=key, reason=reason)
    if conn is not None and not conn.closed:
        try:
            await owned_thread(ledger.finish, conn, envelope, fact, stop_reason=reason)
            return True
        except _STORE_ERRORS:
            conn.close()
    try:
        await owned_thread(ledger.stop, envelope, fact, reason=reason)
        return True
    except _STORE_ERRORS:
        return False


async def refuse_registered(ledger, envelope, request_id, key, reason):
    """Only an exact registered submission can establish durable no-dispatch."""
    recovery = await asyncio.to_thread(ledger.lookup, envelope["execution_id"])
    if recovery["availability"] == "unavailable":
        return response("unavailable", request_id, recovery, status=503, durability="unconfirmed")
    if recovery["request_digest"] != canonical_digest(envelope) or not recovery["attempt_request_id"]:
        return refused(request_id, reason)
    stopped = await stop(ledger, envelope, request_id, recovery["attempt_request_id"], key, reason,
                         refused_before_claim=True)
    if not stopped:
        return await current_status(ledger, envelope["execution_id"], request_id, durability="unconfirmed")
    recovery = await asyncio.to_thread(ledger.lookup, envelope["execution_id"])
    if recovery["availability"] == "unavailable":
        return response("unavailable", request_id, recovery, status=503, durability="unconfirmed")
    return refused(request_id, reason, recovery)


def persist(ledger, conn, envelope, fact):
    """Retry identical metadata within one wire-inclusive budget; never dispatch."""
    original, durable = conn, False
    with database_budget(5):
        try:
            for attempt in range(3):
                if remaining() <= 0:
                    return False
                try:
                    if conn.closed:
                        conn = ledger._connect(ledger._dsn)
                        ledger._mutex(conn, envelope["run_id"])
                    durable = ledger.finish(conn, envelope, fact) in {"inserted", "identical"}
                    return durable
                except _STORE_ERRORS:
                    # An ambiguous COMMIT can have succeeded. Reading a receipt
                    # never recreates dispatch authority or changes its signed bytes.
                    recovery = ledger.lookup(envelope["execution_id"], replay=False)
                    if (recovery["state"] == "result_recorded" and recovery["receipt"] == fact["receipt"]):
                        durable = True
                        return True
            return False
        finally:
            # The uncertainty fact and stop are written once by the caller's
            # stop() while this connection still holds the run mutex; here we
            # only release a replacement connection opened during retry.
            if conn is not original:
                conn.close()


@router.post("/api/v1/executions/handoff")
async def handoff(request: Request):
    settings = get_settings()
    request_id = request.state.request_id
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if (scheme.lower() != "bearer" or not settings.handoff_token or not token.strip()
            or not hmac.compare_digest(token.strip().encode(), settings.handoff_token.encode())):
        return refused(request_id, "unauthorized")
    try:
        body = await request.json()
        if (not isinstance(body, dict) or set(body) != {"request", "arguments", "delegated_token"}
                or not isinstance(body["arguments"], dict)):
            raise ProtocolError("bad_request")
        envelope, arguments, delegated = body["request"], body["arguments"], body["delegated_token"]
        validate_request(envelope, settings.execution_signing_key)
        if canonical_digest(arguments) != envelope["args_digest"]:
            raise ProtocolError("args_digest_mismatch")
        if not isinstance(delegated, str) or not delegated.strip():
            raise ProtocolError("credential_missing")
        if not settings.tool_gateway_url:
            raise ProtocolError("gateway_not_configured")
    except (ValueError, TypeError, RecursionError) as exc:
        return refused(request_id, exc.reason if isinstance(exc, ProtocolError) else "bad_request")
    ledger = request.app.state.ledger
    if request.app.state.draining:
        return await refuse_registered(ledger, envelope, request_id, settings.execution_signing_key, "shutdown")
    record_handoff()
    await barrier(request, "B0")
    decision = await owned_thread(ledger.claim, envelope, request_id)
    if decision.reason == "metadata_replay":
        record_duplicate()
        return await current_status(ledger, envelope["execution_id"], request_id,
                                    audit=(settings, envelope, decision.observation))
    if decision.permit is None:
        if decision.reason in {"store_unavailable", "schema_invalid", "claim_commit_unconfirmed"}:
            if decision.reason in {"store_unavailable", "claim_commit_unconfirmed"}:
                record_store_write_failure()
            return response("unavailable", request_id, status=503, durability="unconfirmed")
        if decision.reason == "identity_conflict":
            record_conflict("identity")
        if decision.reason in {"request_expired", "request_not_yet_valid", "admission_disabled",
                               "epoch_mismatch", "run_stopped", "predecessor_unresolved"}:
            return await refuse_registered(ledger, envelope, request_id, settings.execution_signing_key, decision.reason)
        return refused(request_id, decision.reason)
    audit_execution(settings, envelope, "execution_requested", "success",
                    "dispatch_claimed", decision.observation)
    await barrier(request, "B1")
    projection = await asyncio.to_thread(ledger.lookup, envelope["execution_id"], replay=False)
    attempt_id = projection["attempt_request_id"]
    if not attempt_id:
        return response("unavailable", request_id, status=503, durability="unconfirmed")
    conn = None
    try:
        conn = await owned_thread(ledger.open_send, decision.permit, envelope,
                                  dispose=lambda connection: connection.close())
        result = await execute_tool(settings, envelope["tool_name"], arguments, delegated, attempt_id,
                                    session_id=envelope["session_id"], approval_kind=envelope["approval_kind"],
                                    execution_id=envelope["execution_id"])
        receipt = build_receipt(envelope, map_result_status(result), result, attempt_id, settings.execution_signing_key)
        fact = observation(envelope, source="worker", kind="worker_result", attempt_request_id=attempt_id,
                           current_request_id=request_id, key=settings.execution_signing_key,
                           claim_owner_id=decision.permit.owner_id, receipt=receipt,
                           receipt_digest=canonical_digest(receipt), tool_status=result["status"])
        await barrier(request, "B4")
        durable = await owned_thread(persist, ledger, conn, envelope, fact)
        if not durable:
            record_store_write_failure()
            await stop(ledger, envelope, request_id, attempt_id, settings.execution_signing_key,
                       "receipt_unconfirmed", conn=conn, kind="result_persistence_unconfirmed")
            return await current_status(ledger, envelope["execution_id"], request_id, durability="unconfirmed")
        recovery = await asyncio.to_thread(ledger.lookup, envelope["execution_id"], replay=False)
        if recovery["integrity_conflict"]:
            record_conflict("integrity")
        if recovery["state"] != "result_recorded" or recovery["integrity_conflict"] or recovery["run_stopped"]:
            return await current_status(ledger, envelope["execution_id"], request_id, durability="unconfirmed")
        record_completion(receipt["status"])
        audit_execution(settings, envelope, "execution_completed",
                        "success" if receipt["status"] == "succeeded" else "error",
                        recovery["state"], fact, status=receipt["status"], request_id=attempt_id)
        await barrier(request, "B5")
        return response("original_result", request_id, recovery, durability="confirmed", result=result, observation=fact)
    except (GatewayUncertain, psycopg.Error, ProtocolError) as exc:
        reason = exc.reason if isinstance(exc, ProtocolError) else "store_unavailable"
        if isinstance(exc, psycopg.Error) or reason in {"store_unavailable", "claim_commit_unconfirmed"}:
            record_store_write_failure()
        await stop(ledger, envelope, request_id, attempt_id, settings.execution_signing_key, reason, conn=conn)
        return await current_status(ledger, envelope["execution_id"], request_id, durability="unconfirmed")
    finally:
        if conn is not None:
            conn.close()
