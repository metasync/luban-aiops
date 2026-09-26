"""F-27: real dispatch, closed recovery, and canary-safe proof surfaces."""
from copy import deepcopy
import json
import logging
import secrets
import subprocess
import time
import traceback
from uuid import uuid4

import httpx
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest

from execution_runtime.services.execution_migration import TABLES
from execution_runtime.services.execution_protocol import ProtocolError, validate, validate_observation
from execution_runtime.services.execution_signing import canonical_digest, canonical_json, sign_envelope, verify_envelope
from support.agent_seam import decode_probe, invoke_agent, run_probe
from support.http_services import counts
from support.ledger import claim_count, register
from support.processes import CanaryLogProbe
from test_admission import PATH, ledger
from test_agent_storage import agent, prepared


def ensure_clean(surface, material, canaries):
    # A rewritten `assert canary not in payload` would print the secret on failure.
    encoded = material if isinstance(material, bytes) else json.dumps(material, default=str).encode()
    if any(value.encode() in encoded for value in canaries):
        raise AssertionError(f"canary detected on {surface}; raw material withheld")


def reject_unsafe_metadata(db, key, worker, canary):
    """Both API and direct SQL reject closed/oversized signed metadata before writes."""
    rejected = 0
    for changes in ({"owner_user_id": canary * 300}, {"tool_name": canary * 300},
                    {"parameters": {"password": canary}}, {"url": "https://invalid.test/?token=" + canary}):
        envelope = {**prepared(db, key), **changes}
        envelope["signature"] = sign_envelope(envelope, key)
        assert agent(db, key, "register", envelope=envelope)["ok"] is False
        with httpx.Client(trust_env=False, timeout=10) as client:
            response = client.post(worker.url + PATH, json={"request": envelope, "arguments": {}, "delegated_token": key},
                                   headers={"Authorization": f"Bearer {key}", "x-request-id": "unsafe-metadata"})
        assert response.status_code == 400
        ensure_clean("metadata refusal", response.json(), (canary, key))
        # Database constraints independently close the bypass path.
        try:
            register(db, envelope)
        except psycopg.Error:
            rejected += 1
        else:
            raise AssertionError("direct SQL accepted unsafe execution metadata")
        assert claim_count(db, envelope["execution_id"]) == 0
    assert rejected == 4


@pytest.mark.parametrize("case", [pytest.param(case, marks=pytest.mark.scenario("F-27", case))
                                  for case in ("args", "result", "malformed", "exception", "url", "oversize")])
def test_canaries_absent_from_all_recovery_surfaces(services, ledger_database, tmp_path, request, case, evidence):
    db, key = ledger_database, services.token
    secret, handle = secrets.token_hex(24), str(uuid4())
    canaries = (secret, handle, key)
    parameters = {"nested": {"z": [None, True, 1.25], "a": "é雪"}}
    report = {"data": {"incremented": True}}
    if case == "args":
        parameters.update(password=secret, delivery_token=handle)
    if case in {"result", "oversize"}:
        report = {"data": {"snapshot": "Bearer " + secret,
                           "nested": ["Basic " + handle], "padding": "é" * (12000 if case == "oversize" else 1)}}
    if case == "url":
        url = "https://admin.test/path?password=" + secret + "&delivery_token=" + handle
        parameters["url"] = url
        report = {"data": {"url": url}}
    sink = services.http(audit_status=202, canaries=canaries)
    target = services.http(report=report, canaries=canaries,
        fault="malformed" if case == "malformed" else "none",
        malformed_body=b'{"snapshot":"Bearer ' + secret.encode() + b'"')
    gateway = services.http(upstream=target.url)
    log_path = tmp_path / "worker-log-facts.sqlite"
    worker = services.worker(gateway=gateway, database=db,
        minimization={"canaries": canaries, "log_path": str(log_path),
                      "exception": "transport https://invalid.test/?token=" + secret if case == "exception" else None},
        EXECUTION_AUDIT_SERVICE_URL=sink.url, EXECUTION_AUDIT_CLIENT_ID="failure-harness",
        EXECUTION_AUDIT_CLIENT_SECRET=key)
    invoked = invoke_agent(db, key, worker_url=worker.url, timeout=20, parameters=parameters,
                           canaries=canaries, delivery_id=handle, held=case in {"malformed", "exception"})
    assert invoked["ok"]
    assert invoked["frames_canary_free"] and invoked["logs_canary_free"]
    assert invoked["logs_scanned"] > 1
    assert invoked["signing_input_unchanged"] and invoked["args_digest_matches"]
    assert invoked["original_digest_matches"] and invoked["release_count"] == 0
    uncertain = case in {"malformed", "exception"}
    assert invoked["recovery_state"] == ("outcome_unknown" if uncertain else "result_recorded")
    execution_id = invoked["execution_id"]
    with db.connect() as conn:
        envelope = conn.execute("SELECT request_envelope FROM execution_intents WHERE execution_id=%s",
                                (execution_id,)).fetchone()[0]
    assert envelope["args_digest"] == canonical_digest(parameters)
    assert verify_envelope(envelope, envelope["signature"], key)
    external = counts(target.counter_path)
    assert ("args_digest", envelope["args_digest"]) in external["operations"]
    view = ledger(db, key).lookup(execution_id)
    validate("execution-recovery", view)
    ensure_clean("worker recovery", view, canaries)
    for fact in view["observations"]:
        validate_observation(fact, envelope, key)
        assert len(canonical_json(fact).encode()) <= 8192
    if not uncertain:
        assert ("result_digest", view["receipt"]["outcome_digest"]) in external["operations"]
        assert verify_envelope(view["receipt"], view["receipt"]["signature"], key)
    before = deepcopy(view["receipt"])
    with httpx.Client(trust_env=False, timeout=10) as client:
        duplicate = client.post(worker.url + PATH,
            json={"request": envelope, "arguments": parameters, "delegated_token": key},
            headers={"Authorization": f"Bearer {key}", "x-request-id": "minimization-replay"}).json()
    assert duplicate["kind"] == "status_only" and "result" not in duplicate
    ensure_clean("duplicate response", duplicate, canaries)
    assert duplicate["recovery"]["receipt"] == before

    owner = dict(session_id=envelope["session_id"], owner_user_id=envelope["owner_user_id"])
    page = agent(db, key, "session_http", canaries=canaries, **owner)
    assert page["ok"] and page["status_code"] == 200 and page["session_canary_free"]
    [card] = page["detail"]["confirmations"]
    assert card["executions"][0]["recovery"]["receipt"] == before
    ensure_clean("owner session card", page, canaries)
    derived = agent(db, key, "derived_facts", envelope=envelope, canaries=canaries, publish=True)
    assert derived["ok"] and derived["artifacts_canary_free"] and derived["published_canary_free"]
    assert derived["skill_body_bounded"] and derived["skill_evidence_retained"]
    ensure_clean("derived consumer facts", derived, canaries)

    if case == "oversize":
        reject_unsafe_metadata(db, key, worker, secret)
        source = view["observations"][0]
        for change in ({"reason_code": secret}, {"request_id": secret * 300},
                       {"snapshot": secret}, {"url": "https://invalid.test/" + secret}):
            fact = {**source, **change, "observation_id": str(uuid4())}
            fact["signature"] = sign_envelope(fact, key)
            with pytest.raises(ProtocolError, match="bad_request"):
                ledger(db, key).append(execution_id, fact)
            try:
                with db.connect() as conn:
                    conn.execute("INSERT INTO execution_observations "
                        "(observation_id,execution_id,source,kind,payload,content_digest) VALUES (%s,%s,%s,%s,%s,%s)",
                        (fact["observation_id"], execution_id, fact["source"], fact["kind"], Jsonb(fact), canonical_digest(fact)))
            except psycopg.Error:
                pass
            else:
                raise AssertionError("SQL accepted an unsafe observation")

    # Fresh database observer scans all ledger columns, including JSONB, not a filtered view.
    with db.connect() as conn:
        for table in TABLES:
            rows = conn.execute(sql.SQL("SELECT row_to_json(r)::text FROM {} r").format(sql.Identifier(table))).fetchall()
            ensure_clean("ledger table", rows, canaries)
    expected_audits = 2 if uncertain else 3
    deadline = time.monotonic() + 5
    while counts(sink.counter_path).get("audit_scanned", 0) < expected_audits and time.monotonic() < deadline:
        time.sleep(0.02)
    audit = counts(sink.counter_path)
    assert audit.get("audit_scanned", 0) == expected_audits
    assert audit.get("audit_canary", 0) == 0
    logs = counts(log_path)
    assert logs.get("log_scanned", 0) > 1 and logs.get("log_canary", 0) == 0
    assert logs.get("exception_injected", 0) == int(case == "exception")
    assert claim_count(db, execution_id) == 1
    counters = services.facts(gateway, target)
    assert counters == {"gateway_attempts": 1, "target_accepted": 1, "target_effects": 1}
    evidence(**counters, claim_count=1, mode=case, worker_pids=[worker.pid], observer_pid=page["pid"],
        asserted="canaries absent from raw ledger rows, enabled logs, pre-filter audit wire, owner card, middleware frames, derived/published artifacts; signed original digests unchanged; duplicate never dispatches")
    ensure_clean("proof manifest", request.config.proof_records, canaries)
    # Counter stores and their WALs contain only counts/digests/metadata, never fixtures.
    for path in tmp_path.rglob("*"):
        if path.is_file():
            ensure_clean("harness artifact", path.read_bytes(), canaries)


@pytest.mark.scenario("F-27", "exception")
def test_minimization_observers_detect_leaks_without_printing_them(monkeypatch, evidence):
    canary = secrets.token_hex(24)
    probe = CanaryLogProbe((canary,))
    probe.scan(logging.LogRecord("fixture", logging.WARNING, __file__, 1, "token=%s", (canary,), None))
    structured = logging.LogRecord("fixture", logging.INFO, __file__, 1, "safe", (), None)
    structured.private_field = canary
    probe.scan(structured)
    assert probe.seen == probe.leaked == 2
    for code, output in ((1, canary), (0, "{" + canary), (0, "x" * 1048577)):
        try:
            decode_probe(code, output)
        except AssertionError as exc:
            ensure_clean("probe failure traceback", "".join(traceback.format_exception(exc)), (canary,))
        else:
            raise AssertionError("unsafe probe output was accepted")
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("fixture", 1, output=canary, stderr=canary)
    monkeypatch.setattr(subprocess, "run", timeout)
    try:
        run_probe("fixture", "{}")
    except AssertionError as exc:
        ensure_clean("timeout traceback", "".join(traceback.format_exception(exc)), (canary,))
    else:
        raise AssertionError("watchdog failure was suppressed")
    evidence(negative_detected=True, asserted="enabled log scanner detects message and structured-field canaries; probe exit/parse/oversize/watchdog errors never print captured diagnostics")


@pytest.mark.scenario("F-27", "result")
def test_audit_canary_scanner_observes_before_fixture_filtering(services, evidence):
    canary = secrets.token_hex(24)
    sink = services.http(audit_status=202, canaries=(canary,))
    with httpx.Client(trust_env=False, timeout=5) as client:
        reply = client.post(sink.url, auth=("failure-harness", services.token), json={"events": [{
            "event_type": "execution_completed", "request_id": "safe-control",
            "details": {"unexpected_result": canary}}]})
    assert reply.status_code == 202
    facts = counts(sink.counter_path)
    assert facts["audit_scanned"] == facts["audit_canary"] == facts["audit_stored"] == 1
    ensure_clean("negative audit control artifact", sink.counter_path.read_bytes(), (canary,))
    evidence(negative_detected=True, asserted="wire scanner detects an unexpected raw audit result before fixture allowlisting; only detection counts persist")
