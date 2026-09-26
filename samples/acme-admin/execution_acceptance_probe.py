"""F-35 deterministic agent seam, executed in the isolated agent image.

Scripted tool calls replace only the model. Signing, registration, worker HTTP,
gateway policy, target mutation, durable acceptance, evidence middleware, and
owner recovery use product code. This is not a conversational/portal UI test.
Only allowlisted facts cross stdout; credentials and original results stay local.
"""
import asyncio
from datetime import timedelta
import json
import logging
import os
from types import SimpleNamespace
from uuid import uuid4

logging.disable(logging.CRITICAL)
os.environ["OTEL_SDK_DISABLED"] = "true"

import httpx
from agentscope.message import ToolCallBlock
from agentscope.tool import ToolResponse
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services.confirmation_records import PostgresConfirmationRecordStore, make_record
from agent_service.services.execution_protocol import ProtocolError, iso
from agent_service.services.execution_recovery import ExecutionRecovery
from agent_service.services.execution_run_guard import CURRENT_RUN_GUARD, bind_run
from agent_service.services.execution_signing import build_requests, sign_envelope
from agent_service.services.execution_worker_client import handoff_original
from agent_service.services.hitl_confirmations import ConfirmationRegistry, redact_pending_calls
from agent_service.services.kernel_middleware import (
    PENDING_RELEASE_DELIVERIES, RELEASE_PERMITS, TOOL_EVIDENCE_SINK, ToolEvidenceMiddleware,
)
from agent_service.tools.gateway_tools import DELEGATED_TOKEN, EXECUTION_AUDIT_CONTEXT, EXECUTION_REQUESTS, _make_tool_fn


def require(condition, code):
    if not condition:
        raise AssertionError(code)


def resources(data):
    settings = RuntimeSettings.from_env()
    require(settings.execution_admission_enabled and settings.execution_admission_epoch == data["epoch"], "admission")
    store = ExecutionRecovery(settings.execution_state_db_url, settings.execution_signing_key,
                              data["epoch"], admission_enabled=True)
    return settings, store, PostgresConfirmationRecordStore(settings.execution_state_db_url)


def wire(path="/status"):
    with httpx.Client(timeout=10, trust_env=False) as client:
        response = client.request("GET" if path == "/status" else "POST", "http://spec063-wire:8080" + path,
                                  headers={"Authorization": "Bearer " + os.environ["AGENT_EXECUTION_HANDOFF_TOKEN"]})
        require(response.status_code == 200, "wire_control")
        return response.json()


def token(username, role):
    with httpx.Client(timeout=15, trust_env=False) as client:
        response = client.post("http://identity-service:8000/api/v1/auth/token", json={
            "username": username, "email": username + "@luban-aiops.local",
            "roles": [role], "groups": ["ops-approvers" if role == "approver" else "ops-operators"]})
        require(response.status_code == 200, "identity_issue")
        response = client.post("http://identity-service:8000/api/v1/auth/exchange",
                               auth=("platform-gateway", os.environ["ACCEPTANCE_DELEGATION_CLIENT_SECRET"]),
                               json={"subject_token": response.json()["access_token"], "audience": "tool-gateway"})
        require(response.status_code == 200, "identity_exchange")
        return response.json()["access_token"]


def parameters(data, password=None):
    action = "password" if password is not None else data["action"]
    require(action in {"lock", "unlock", "password"}, "action")
    return {"url": data["origin"] + "/api/users/" + data["target_user"] + "/" + action,
            "credential_set": "acme-admin", "body": {"password": password} if password is not None else {}}


def prepare(data, args):
    settings, recovery, cards = resources(data)
    session = "spec063-" + str(uuid4())
    run = recovery.create_run(session, data["operator"])
    call = str(uuid4())
    attempt = "spec063-" + str(uuid4())
    registry = ConfirmationRegistry()
    pending = registry.register(session, data["operator"], "scripted-acceptance", [
        ToolCallBlock(id=call, name="http.post", input=json.dumps(args))], 600,
        risk_levels={"http.post": "write"}, approval_kind="action", run_id=run)
    cards.save_parked(make_record(pending.confirm_id, session, data["operator"],
                                  redact_pending_calls(pending, pending.pending_calls_payload()),
                                  "tools:mutate", approval_kind="action"))
    registry.claim(session, pending.confirm_id, 600)
    envelope = build_requests(pending, data["approver"], settings.execution_signing_key,
                              run_id=run, admission_epoch=data["epoch"], lifetime_seconds=600)[0]
    # Use the database clock, not an assumed host/VM clock offset.
    with recovery.connection() as conn:
        now = conn.execute("SELECT clock_timestamp()").fetchone()[0]
    envelope["requested_at"] = iso(now - timedelta(seconds=1))
    envelope["expires_at"] = iso(now + timedelta(seconds=3 if data["path"] == "denied-expired" else 599))
    envelope["signature"] = sign_envelope(envelope, settings.execution_signing_key)
    recovery.register(envelope, attempt)
    cards.mark_resolved(session, pending.confirm_id, "approved", data["approver"], "approve")
    return envelope, attempt


def load(data):
    settings, recovery, cards = resources(data)
    with recovery.connection() as conn:
        row = conn.execute("SELECT i.request_envelope,i.attempt_request_id FROM execution_intents i "
                           "JOIN execution_runs r USING(run_id) WHERE i.execution_id=%s "
                           "AND r.owner_user_id=%s AND r.session_id=%s",
                           (data["execution_id"], data["operator"], data["session_id"])).fetchone()
    require(row is not None, "owner_scope")
    require(row[0]["admission_epoch"] == data["epoch"], "epoch")
    return row


def facts(data, envelope):
    settings, recovery, cards = resources(data)
    view = recovery.lookup(envelope["execution_id"])
    require(view["availability"] == "available" and not view["integrity_conflict"], "recovery")
    card = cards.load_record(envelope["session_id"], envelope["confirm_id"])
    require(card is not None, "durable_card")
    with recovery.connection() as conn:
        claims = conn.execute("SELECT count(*) FROM execution_dispatch_claims WHERE execution_id=%s",
                              (envelope["execution_id"],)).fetchone()[0]
    return {"execution_id": envelope["execution_id"], "session_id": envelope["session_id"],
            "confirm_id": envelope["confirm_id"], "call_id": envelope["call_id"],
            "run_id": envelope["run_id"], "state": view["state"], "claims": claims,
            "run_stopped": view["run_stopped"], "receipt_status": (view["receipt"] or {}).get("status"),
            "observation_kinds": sorted({o["kind"] for o in view["observations"]}),
            "card_status": card["status"], "card_decider": card["decider_user_id"],
            "target_verification_required": view["target_verification_required"]}


async def invoke(data, envelope, attempt, args, held=()):
    settings, recovery, _cards = resources(data)
    guard = bind_run(recovery, envelope["session_id"], data["operator"], run_id=envelope["run_id"])
    delegated = token(data["approver"], "approver")
    if data["path"] == "owner-reload":
        original = await handoff_original(envelope, args, delegated, settings, attempt)
        require(original.result["status"] == "success", "original_result")
        # Deliberately withhold acceptance; stop survives the subprocess exit.
        require(guard.durable_stop("wait_expired"), "withheld_acceptance_stop")
        return {**facts(data, envelope), "release_count": 0}
    if data["path"] == "denied-expired":
        with recovery.connection() as conn:
            delay = conn.execute("SELECT greatest(0, extract(epoch FROM %s::timestamptz - clock_timestamp()))",
                                 (envelope["expires_at"],)).fetchone()[0]
        await asyncio.sleep(float(delay) + 0.2)
    frames = []

    class Sink:
        async def put(self, frame):
            frames.append(frame)

    call = ToolCallBlock(id=envelope["call_id"], name="http.post", input=json.dumps(args))
    agent = SimpleNamespace(toolkit=SimpleNamespace(tool_groups=[SimpleNamespace(tools=[
        SimpleNamespace(name="http.post", gateway_tool_name="http.post")])]))
    tool = _make_tool_fn(settings.execution_worker_url, "http.post", "acceptance mutation", is_read_only=False)
    tokens = [(TOOL_EVIDENCE_SINK, TOOL_EVIDENCE_SINK.set(Sink())),
              (PENDING_RELEASE_DELIVERIES, PENDING_RELEASE_DELIVERIES.set(list(held))),
              (RELEASE_PERMITS, RELEASE_PERMITS.set({})), (DELEGATED_TOKEN, DELEGATED_TOKEN.set(delegated)),
              (CURRENT_RUN_GUARD, CURRENT_RUN_GUARD.set(guard)),
              (EXECUTION_REQUESTS, EXECUTION_REQUESTS.set({call.id: envelope})),
              (EXECUTION_AUDIT_CONTEXT, EXECUTION_AUDIT_CONTEXT.set({"settings": settings, "request_id": attempt,
                  "session_id": envelope["session_id"], "confirm_id": envelope["confirm_id"],
                  "owner_user_id": data["operator"], "decider_user_id": data["approver"]}))]

    async def next_handler(**_kwargs):
        chunk = await tool(**args)
        yield ToolResponse(content=chunk.content, metadata=chunk.metadata)

    try:
        async for _ in ToolEvidenceMiddleware().on_acting(agent, {"tool_call": call}, next_handler):
            pass
        second_release = ToolEvidenceMiddleware._permit_secret_release(call.id)
    finally:
        for variable, old in reversed(tokens):
            variable.reset(old)
    secret = args.get("body", {}).get("password")
    require(not secret or secret not in json.dumps(frames), "frame_secret_redaction")
    return {**facts(data, envelope), "release_count": sum(f.get("type") == "secret_delivery" for f in frames),
            "second_release": second_release}


def held_secret(data):
    owner = token(data["operator"], "operator")
    headers = {"Authorization": "Bearer " + owner}
    with httpx.Client(timeout=30, trust_env=False) as client:
        def generate():
            generated = client.post("http://tool-gateway:8000/api/v2/tools/invoke", headers=headers,
                                    json={"tool_name": "secrets.generate_password", "parameters": {"handoff": "portal_copy"}})
            require(generated.status_code == 200, "secret_generation_http")
            generated = generated.json()
            require(generated["status"] == "success", "secret_generation")
            return generated["data"]["generated_password"], {
                k: generated["data"][k] for k in ("delivery_id", "channel", "expires_at")}

        base = "http://tool-gateway:8000/api/v2/secrets/delivery/"
        value, handle = generate()
        try:
            args = parameters(data, value)
            envelope, attempt = prepare(data, args)
            result = asyncio.run(invoke(data, envelope, attempt, args, [handle]))
            require(result["release_count"] == 1 and result["second_release"] is False, "single_release")
            url = base + handle["delivery_id"]
            redeemed = client.get(url, headers=headers)
            require(redeemed.status_code == 200, "secret_redemption_http_" + str(redeemed.status_code))
            require(redeemed.json()["value"] == value, "secret_redemption_value")
            require(client.get(url, headers=headers).status_code == 404, "secret_spent")
            # Replaying the exact signed call cannot mint another release permit.
            replay = asyncio.run(invoke({**data, "path": "replay"}, envelope, attempt, args, [handle]))
            require(replay["release_count"] == 0, "secret_replay_release")
            require(value not in json.dumps(result), "fact_secret_redaction")
            # Wrong-owner GET burns a handle by contract. Use a separate
            # generation-only control, never the password used in the reset.
            _control_value, control = generate()
            try:
                control_url = base + control["delivery_id"]
                wrong = client.get(control_url, headers={"Authorization": "Bearer " + token(data["approver"], "approver")})
                require(wrong.status_code == 404, "secret_owner")
                require(client.get(control_url, headers=headers).status_code == 404, "secret_owner_burn")
            finally:
                client.delete(base + control["delivery_id"], headers=headers)
            return {**result, "redeemed_once": True, "wrong_owner_burned": True,
                    "replay_release_count": replay["release_count"]}
        finally:
            client.delete(base + handle["delivery_id"], headers=headers)


def main(data):
    operation = data["operation"]
    try:
        if operation == "wire":
            return {"ok": True, **wire(data.get("control", "/status"))}
        if operation == "ready":
            with httpx.Client(timeout=10, trust_env=False) as client:
                response = client.get("http://execution-runtime:8000/health/ready")
                require(response.status_code == 200, "worker_ready")
            resources(data)
            return {"ok": True}
        if operation == "inventory":
            _settings, recovery, _cards = resources(data)
            with recovery.connection() as conn:
                conn.execute("SET TRANSACTION READ ONLY")
                rows = conn.execute("SELECT i.request_envelope FROM execution_intents i "
                                    "JOIN execution_runs r USING(run_id) WHERE r.owner_user_id=%s "
                                    "AND r.session_id LIKE 'spec063-%%' AND i.request_envelope->>'admission_epoch'=%s "
                                    "ORDER BY i.registration_seq LIMIT 101", (data["operator"], data["epoch"])).fetchall()
            require(len(rows) <= 100, "inventory_limit")
            return {"ok": True, "executions": [facts(data, row[0]) for row in rows]}
        if operation == "held-secret":
            return {"ok": True, **held_secret(data)}
        if operation == "prepare":
            envelope, attempt = prepare(data, parameters(data))
            return {"ok": True, "execution_id": envelope["execution_id"], "session_id": envelope["session_id"],
                    "request_id": attempt, "path": data["path"], "action": data["action"]}
        envelope, attempt = load(data)
        if operation == "invoke":
            return {"ok": True, **asyncio.run(invoke(data, envelope, attempt, parameters(data)))}
        if operation == "recover":
            _settings, recovery, _cards = resources(data)
            page = recovery.owner_session_recovery(envelope["session_id"], data["operator"])
            foreign = recovery.owner_session_recovery(envelope["session_id"], data["approver"])
            require(page["availability"] == "available" and len(page["executions"]) == 1, "owner_page")
            require(foreign["availability"] == "available" and not foreign["executions"], "foreign_page")
            require("result" not in page["executions"][0] and "arguments" not in page["executions"][0], "metadata_only")
            return {"ok": True, **facts(data, envelope), "metadata_only": True}
        raise AssertionError("operation")
    except AssertionError as exc:
        return {"ok": False, "failure": str(exc)}
    except Exception as exc:
        # Exception messages can contain payloads; retain only the type and
        # innermost product function name to make failures diagnosable safely.
        tb = exc.__traceback__
        while tb.tb_next:
            tb = tb.tb_next
        return {"ok": False, "failure": "probe_failed:" + type(exc).__name__ + ":" + tb.tb_frame.f_code.co_name}
