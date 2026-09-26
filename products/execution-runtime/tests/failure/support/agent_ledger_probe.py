"""Test-only agent environment entry point. Credentials arrive over stdin only."""
from dataclasses import asdict
import asyncio
import json
import logging
import os
from pathlib import Path
import sys
from types import SimpleNamespace

from agent_service.services.execution_catalog import connect, fingerprint, verify_schema
from agent_service.services.execution_protocol import ProtocolError, observation, validate_original, validate_request
from agent_service.services.execution_recovery import ExecutionRecovery
from agent_service.services.execution_signing import canonical_digest, sign_envelope
from agent_service.services.execution_worker_client import handoff_original


def derived_facts(data):
    """Actual digest/authoring consumers, with PG evidence and isolated presentation."""
    from uuid import uuid4
    from agent_service.services import incident_report, runtime_dependencies, shift_summary
    from agent_service.services.authoring_trace import PostgresAuthoringTraceStore
    from agent_service.services.confirmation_records import InMemoryConfirmationRecordStore
    from agent_service.services.evidence_store import InMemoryEvidenceStore
    from agent_service.services.execution_records import InMemoryExecutionRecordStore
    from agent_service.services.execution_recovery import EXECUTION_EVIDENCE_GUIDANCE, read_owner_recovery_page
    from agent_service.services.operation_documents import PostgresOperationDocumentStore, make_document
    from agent_service.services.session_store import InMemorySessionStore
    from agent_service.services.skill_draft import build_skeleton, build_skill_draft_prompt, postprocess
    from agent_service.services.skill_graduation import revalidate_blast_radius

    envelope = data["envelope"]
    session_id, owner = envelope["session_id"], envelope["owner_user_id"]
    sessions, executions = InMemorySessionStore(), InMemoryExecutionRecordStore()
    sessions.create_session(owner, session_id=session_id)
    sessions.set_session_title(session_id, "private-title-canary")
    # Explicit historical presentation fixture: current recovery must never inherit it.
    executions.save_request({**envelope, "status": "requested"})
    executions.save_receipt(envelope["confirm_id"], envelope["call_id"], {
        "status": "succeeded", "completed_at": envelope["requested_at"]}, True)
    shift_summary.SESSION_STORE = incident_report.SESSION_STORE = sessions
    shift_summary.EXECUTION_RECORD_STORE = executions
    shift_summary.CONFIRMATION_RECORD_STORE = InMemoryConfirmationRecordStore()
    shift_summary.EVIDENCE_STORE = InMemoryEvidenceStore()
    shift_summary.extract_transcript = lambda _: (True, [])
    recovery = ExecutionRecovery(data.get("recovery_dsn", data["dsn"]), data["key"],
                                 data["epoch"], admission_enabled=True)
    reads = []
    def kernel():
        reads.append(True)
        return SimpleNamespace(_execution_recovery=lambda: recovery if not data.get("legacy") else None)
    runtime_dependencies.get_runtime_kernel = kernel
    foreign = data.get("foreign", False)
    caller = "foreign-reader" if foreign else owner
    digest, provenance = shift_summary.build_digest(caller, [session_id], foreign)
    incident, incident_provenance = incident_report.build_digest(caller, {
        "incident": {"incident_id": "fixture-incident", "session_id": session_id}}, foreign)
    row = digest["sessions"][0]
    if foreign:
        assert not reads
        assert "private-title-canary" not in json.dumps([digest, incident])
        assert set(row) == {"session_id", "coverage", "confirmation_decisions",
                            "execution_receipts", "record_counts"}
        assert "execution_evidence_counts" not in digest["handover"]
        assert "execution_recovery" not in incident["session"]
        denied = False
        try:
            shift_summary.build_digest(caller, [session_id], False)
        except shift_summary.ForeignSessionDenied:
            denied = True
        assert denied
        return {"foreign_limited": True, "owner_recovery_reads": len(reads)}

    results = {}
    if not data.get("legacy"):
        [execution] = row["executions"]
        facts = execution["recovery"]
        assert execution["historical_receipt_status"] == "succeeded"
        assert digest["handover"]["executions"][0]["recovery"] == facts
        assert incident["session"]["executions"][0]["recovery"] == facts
        bundle = {"session": {"title": "Recovery fixture"}, **digest}
        frontmatter, body = build_skeleton(bundle)
        _, rendered = postprocess(frontmatter, body)
        assert execution["evidence_label"] in rendered
        assert EXECUTION_EVIDENCE_GUIDANCE in build_skill_draft_prompt(bundle)
        if data.get("canaries"):
            material = json.dumps([digest, incident, frontmatter, rendered, build_skill_draft_prompt(bundle)])
            results["artifacts_canary_free"] = not any(value in material for value in data["canaries"])
            results["skill_body_bounded"] = len(rendered.encode()) <= 65536
        results.update(facts=facts, counts=row["execution_evidence_counts"],
                       shift_summary=shift_summary.document_summary(digest),
                       incident_summary=incident_report.document_summary(incident),
                       skill_evidence_retained=True)

    if data.get("authoring"):
        trace = PostgresAuthoringTraceStore(data["dsn"])
        steps = trace.load_for_session(session_id)
        before = canonical_digest(steps)
        assert len(steps) == 1
        radius = revalidate_blast_radius(steps, target="https://admin.test",
            recovery_page=read_owner_recovery_page(session_id, owner))
        assert canonical_digest(trace.load_for_session(session_id)) == before
        assert "origin-query-canary" not in json.dumps(steps)
        results.update(graduable=radius.graduable,
                       origin_recorded=steps[0]["flow_origin"] == "https://admin.test")

    if data.get("publish") or data.get("snapshots"):
        documents = PostgresOperationDocumentStore(data["dsn"])
        documents.initialize()
        snapshots = []
        if data.get("publish"):
            for kind, content, sources, summary in (
                ("shift_summary", digest, provenance, shift_summary.document_summary(digest)),
                ("incident_report", incident, incident_provenance, incident_report.document_summary(incident)),
            ):
                document_id = str(uuid4())
                documents.create(make_document(document_id, kind, owner, "Recovery fixture",
                    sources, content, "Historical narrative", "included", summary=summary))
                assert documents.publish(owner, document_id)
                if data.get("canaries"):
                    material = json.dumps(documents.load(document_id))
                    results["published_canary_free"] = results.get("published_canary_free", True) and not any(
                        value in material for value in data["canaries"])
                snapshots.append({"document_id": document_id,
                                  "digest": canonical_digest(documents.load(document_id))})
        for snapshot in data.get("snapshots", []):
            loaded = documents.load(snapshot["document_id"])
            assert loaded["state"] == "published"
            assert canonical_digest(loaded) == snapshot["digest"]
        results.update(snapshots=snapshots, snapshots_unchanged=len(data.get("snapshots", [])))
    return results


def main(data):
    logging.disable(logging.CRITICAL)
    factory = connect
    if data.get("fault"):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from support.postgres_faults import CommitFaultConnection
        factory = lambda dsn: CommitFaultConnection(connect(dsn), data["fault"])
    store = ExecutionRecovery(data["dsn"], data["key"], data["epoch"],
                              admission_enabled=data.get("enabled", True), connection_factory=factory)
    envelope = data.get("envelope")
    operation = data["operation"]
    attempt = data.get("attempt_id", "agent-original")
    if operation == "derived_facts":
        return derived_facts(data)
    if operation == "catalog":
        with connect(data["dsn"]) as conn:
            state = verify_schema(conn)
            return {"fingerprint": fingerprint(conn), "state": state}
    if operation == "sign":
        from agentscope.message import ToolCallBlock
        from agent_service.services.execution_signing import build_requests, build_flow_request
        from agent_service.services.flow_approvals import FlowApproval
        from agent_service.services.hitl_confirmations import ConfirmationRegistry

        window = dict(run_id=data["run_id"], admission_epoch=data["epoch"],
                      lifetime_seconds=data.get("lifetime", 900))
        if data["kind"] == "action":
            pending = ConfirmationRegistry().register(
                "test-session", "test-owner", "test-reply",
                [ToolCallBlock(id="test-call", name="test.increment", input=json.dumps(data["parameters"]))], 600)
            signed = build_requests(pending, "test-decider", data["key"], **window)[0]
        else:
            authority = FlowApproval(session_id="test-session", confirm_id=data["confirm_id"],
                                     owner_user_id="test-owner", decider_user_id="test-decider",
                                     skill_id="test/flow", origin="http://test.invalid", ttl=900)
            signed = build_flow_request("test-call", "test.increment", data["parameters"], authority,
                                        data["key"], **window)
        validate_request(signed, data["key"])
        return {"envelope": signed, "digest": canonical_digest(signed)}
    if operation == "create":
        return {"run_id": store.create_run(data["session_id"], data["owner_user_id"])}
    if operation == "register":
        return asdict(store.register(envelope, attempt))
    if operation == "lookup":
        return {"recovery": store.lookup(data["execution_id"])}
    if operation == "owner_recovery":
        return {"recovery": store.owner_recovery(data["execution_id"], data["session_id"],
                                                 data["owner_user_id"], cursor=data.get("cursor"))}
    if operation == "session_recovery":
        return {"page": store.owner_session_recovery(data["session_id"], data["owner_user_id"],
            execution=data.get("execution"), cursor=data.get("cursor"), page_size=data.get("page_size", 50))}
    if operation == "session_http":
        # Actual owner-check and response serialization; only presentation
        # dependencies are disposable fixture stores. Recovery uses real PG.
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from agent_service.api.v2 import routes
        from agent_service.services import session_service, session_transcript
        from agent_service.services.session_store import InMemorySessionStore
        from agent_service.services.agent_state_store import InMemoryAgentStateStore
        sessions = InMemorySessionStore()
        if not data.get("deleted"):
            sessions.create_session(data["owner_user_id"], session_id=data["session_id"])
        session_service.SESSION_STORE = sessions
        session_transcript.AGENT_STATE_STORE = InMemoryAgentStateStore()
        def presentation(_session_id):
            if data.get("presentation") == "unreadable":
                raise RuntimeError("fixture-presentation-unavailable")
            return []
        routes.CONFIRMATION_RECORD_STORE = SimpleNamespace(load_for_session=presentation)
        routes.EXECUTION_RECORD_STORE = SimpleNamespace(load_for_session=presentation)
        routes.get_runtime_kernel = lambda: SimpleNamespace(_execution_recovery=lambda: store)
        app = FastAPI()
        app.include_router(routes.router)
        params = {name: data[name] for name in ("execution", "execution_cursor", "page_size") if name in data}
        with TestClient(app) as client:
            response = client.get(f"/api/v2/sessions/{data['session_id']}", params=params,
                                  headers={"X-User-ID": data.get("caller", data["owner_user_id"])})
        detail = response.json()
        if data.get("canaries") and any(value in json.dumps(detail) for value in data["canaries"]):
            return {"status_code": response.status_code, "session_canary_free": False}
        return {"status_code": response.status_code, "detail": detail, "session_canary_free": True}
    if operation == "seed_observations":
        # Test-only: append N ordinary signed agent observations so owner
        # recovery paging (window size 20) can be exercised past the first page.
        with store.connection() as conn:
            verify_schema(conn)
            intent = store._intent(conn, envelope)
            written = [store._append(conn, intent, observation(
                envelope, source="agent", kind=data.get("kind", "transport_uncertain"),
                key=data["key"], attempt_request_id=attempt, current_request_id=f"seed-{i}",
                reason=data.get("reason", "transport_error"))) for i in range(data["count"])]
            conn.commit()
        return {"written": written}
    if operation == "check":
        store.check_run(envelope["run_id"], envelope["session_id"], envelope["owner_user_id"])
        return {"checked": True}
    if operation == "stop":
        fact = observation(envelope, source="agent", kind="wait_expired", key=data["key"],
                           attempt_request_id=attempt, current_request_id="agent-wait", reason="wait_expired")
        return {"written": store.stop_run(envelope["run_id"], envelope["session_id"], envelope["owner_user_id"],
                                         reason="wait_expired", envelope=envelope, fact=fact)}
    if operation == "validate":
        validate_request(envelope, data["key"])
        return {"digest": canonical_digest(envelope), "signature": sign_envelope(envelope, data["key"])}
    if operation == "accept":
        original = validate_original(data["payload"], envelope, data["key"], attempt, attempt)
        return {"accepted": store.accept(envelope, original, attempt)}
    if operation == "exchange":
        registration = store.register(envelope, attempt)
        store.check_run(envelope["run_id"], envelope["session_id"], envelope["owner_user_id"], envelope=envelope)
        settings = SimpleNamespace(execution_signing_key=data["key"], execution_handoff_token=data["key"],
                                   execution_worker_url=data["worker_url"], execution_worker_timeout_seconds=10)
        original = asyncio.run(handoff_original(envelope, {}, data["key"], settings, registration.attempt_request_id))
        accepted = store.accept(envelope, original, registration.attempt_request_id)
        return {"accepted": accepted, "recovery": store.lookup(envelope["execution_id"])}
    raise AssertionError("unsupported test operation")


if __name__ == "__main__":
    try:
        result = {"ok": True, **main(json.load(sys.stdin))}
    except ProtocolError as exc:
        result = {"ok": False, "reason": exc.reason}
    result["pid"] = os.getpid()
    print(json.dumps(result))
