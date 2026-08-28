"""SPEC-043 R-2/R-3: incident client and incident-report assembly.

Covers the structured error hierarchy of the incident-service client
(not-configured 503, transport/5xx 502, unknown-id 404, 4xx
passthrough), the credential and request-id forwarding, and the
assembler's four deterministic sections — verbatim copies, the
raw-triage exclusion marker, every linked-session tier (owner,
foreign, foreign_denied, missing, unavailable), the provenance block,
and the counts-only summary.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from agent_service.runtime_settings import RuntimeSettings
from agent_service.services import incident_client, incident_report, shift_summary
from agent_service.services.confirmation_records import (
    InMemoryConfirmationRecordStore,
    make_record,
)
from agent_service.services.evidence_store import InMemoryEvidenceStore
from agent_service.services.execution_records import (
    InMemoryExecutionRecordStore,
)
from agent_service.services.incident_client import (
    DETAIL_PATH_TEMPLATE,
    IncidentClientRejected,
    IncidentDependencyNotConfigured,
    IncidentNotFound,
    IncidentServiceUnavailable,
    fetch_incident_bundle,
    is_configured,
)
from agent_service.services.incident_report import (
    NOT_TRIAGED,
    build_digest,
    document_summary,
)
from agent_service.services.session_store import InMemorySessionStore


# --- Incident client (SPEC-043 R-3) ------------------------------------------


def _settings(**overrides) -> RuntimeSettings:
    base = {
        "incident_service_url": "http://incident-service:8000",
        "incident_client_secret": "query-secret",
    }
    base.update(overrides)
    return RuntimeSettings(**base)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("no body")
        return self._payload


class _FakeAsyncClient:
    def __init__(
        self,
        response: _FakeResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.requests: list[dict] = []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, url, auth=None, headers=None):
        self.requests.append({"url": url, "auth": auth, "headers": headers})
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def _patch_http(monkeypatch, fake: _FakeAsyncClient) -> None:
    def _factory(timeout=None):
        fake.timeout = timeout
        return fake

    monkeypatch.setattr(incident_client.httpx, "AsyncClient", _factory)


class TestIncidentClientConfiguration:
    def test_requires_both_url_and_secret(self) -> None:
        assert is_configured(_settings()) is True
        assert is_configured(_settings(incident_service_url=None)) is False
        assert is_configured(_settings(incident_client_secret=None)) is False

    def test_not_configured_raises_structured(self, monkeypatch) -> None:
        with pytest.raises(IncidentDependencyNotConfigured):
            asyncio.run(
                fetch_incident_bundle(
                    _settings(incident_service_url=None), "req-1", "inc-a"
                )
            )


class TestIncidentClientFetch:
    def test_success_fetches_bundle_with_credential_and_request_id(
        self, monkeypatch
    ) -> None:
        bundle = {"incident": {"incident_id": "inc-a"}, "report": None, "dispatches": []}
        fake = _FakeAsyncClient(response=_FakeResponse(200, bundle))
        _patch_http(monkeypatch, fake)
        result = asyncio.run(
            fetch_incident_bundle(_settings(), "req-42", "inc-a")
        )
        assert result == bundle
        [request] = fake.requests
        assert request["url"] == (
            "http://incident-service:8000"
            + DETAIL_PATH_TEMPLATE.format(incident_id="inc-a")
        )
        # The registered Basic query credential, forwarded request id.
        assert request["auth"] == ("agent-service", "query-secret")
        assert request["headers"] == {"x-request-id": "req-42"}
        assert fake.timeout == _settings().incident_client_timeout_seconds

    def test_404_maps_to_incident_not_found(self, monkeypatch) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(404, {"error": {}}))
        _patch_http(monkeypatch, fake)
        with pytest.raises(IncidentNotFound) as excinfo:
            asyncio.run(fetch_incident_bundle(_settings(), None, "inc-gone"))
        assert excinfo.value.incident_id == "inc-gone"

    def test_401_maps_to_rejected_with_upstream_message(
        self, monkeypatch
    ) -> None:
        fake = _FakeAsyncClient(
            response=_FakeResponse(
                401, {"error": {"code": "unauthorized", "message": "bad credential"}}
            )
        )
        _patch_http(monkeypatch, fake)
        with pytest.raises(IncidentClientRejected) as excinfo:
            asyncio.run(fetch_incident_bundle(_settings(), None, "inc-a"))
        assert excinfo.value.status_code == 401
        assert excinfo.value.message == "bad credential"

    def test_5xx_maps_to_unavailable(self, monkeypatch) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(500))
        _patch_http(monkeypatch, fake)
        with pytest.raises(IncidentServiceUnavailable):
            asyncio.run(fetch_incident_bundle(_settings(), None, "inc-a"))

    def test_transport_failure_maps_to_unavailable(self, monkeypatch) -> None:
        fake = _FakeAsyncClient(error=httpx.ConnectError("boom"))
        _patch_http(monkeypatch, fake)
        with pytest.raises(IncidentServiceUnavailable):
            asyncio.run(fetch_incident_bundle(_settings(), None, "inc-a"))


# --- Assembler (SPEC-043 R-2) -------------------------------------------------

TRIAGE_REPORT = {
    "incident_id": "inc-abc123",
    "severity_assessment": "critical",
    "summary": "Database pool exhaustion on the payment service",
    "evidence": [{"source": "metrics", "description": "pool saturation"}],
    "hypotheses": ["connection pool exhaustion"],
    "next_steps": [
        {"title": "raise pool size", "priority": "immediate", "rationale": "sat"}
    ],
    "skills_cited": ["sre-database"],
    "session_id": "ses-alice",
    "generated_at": "2026-08-28T10:10:00Z",
    "generated_by": "triage-agent",
}


def _bundle(session_id: str | None = "ses-alice", report: dict | None = TRIAGE_REPORT):
    return {
        "incident": {
            "incident_id": "inc-abc123",
            "fingerprint": "fp-1",
            "source": "webhook",
            "severity": "critical",
            "status": "triaged",
            "title": "Payment API latency",
            "summary": "p99 latency spike on the payment API",
            "labels": {"team": "payments"},
            "reported_by": "alertmanager",
            "session_id": session_id,
            "created_at": "2026-08-28T10:00:00Z",
            "updated_at": "2026-08-28T10:05:00Z",
            "resolved_at": None,
            "triage_raw": "RAW ALERT PAYLOAD — never reaches the digest",
        },
        "report": report,
        "dispatches": [
            {
                "connector": "pagerduty",
                "status": "sent",
                "reference": "PD-1",
                "error": None,
                "created_at": "2026-08-28T10:02:00Z",
            }
        ],
    }


@pytest.fixture()
def stores(monkeypatch):
    """Fresh in-memory stores wired into both assemblers' namespaces."""
    sessions = InMemorySessionStore()
    confirmations = InMemoryConfirmationRecordStore()
    executions = InMemoryExecutionRecordStore()
    evidence = InMemoryEvidenceStore()
    monkeypatch.setattr(incident_report, "SESSION_STORE", sessions)
    monkeypatch.setattr(shift_summary, "SESSION_STORE", sessions)
    monkeypatch.setattr(shift_summary, "CONFIRMATION_RECORD_STORE", confirmations)
    monkeypatch.setattr(shift_summary, "EXECUTION_RECORD_STORE", executions)
    monkeypatch.setattr(shift_summary, "EVIDENCE_STORE", evidence)
    return {"sessions": sessions, "confirmations": confirmations}


class TestBuildDigest:
    def test_owner_session_full_digest(self, stores) -> None:
        record = stores["sessions"].create_session(
            user_id="alice", session_id="ses-alice"
        )
        stores["sessions"].set_session_title(record.session_id, "triage inc-abc123")
        stores["confirmations"].save_parked(
            make_record(
                "cf-1",
                record.session_id,
                "alice",
                [{"call_id": "call-1", "tool_name": "k8s.restart_service"}],
                "tools:mutate",
            )
        )
        digest, provenance = build_digest("alice", _bundle(), can_view_foreign=False)

        # Four deterministic sections, in verbatim-copy posture.
        incident = digest["incident"]
        assert incident["incident_id"] == "inc-abc123"
        assert incident["severity"] == "critical"
        assert incident["title"] == "Payment API latency"
        # Raw triage never reaches the digest; a presence marker does.
        assert "triage_raw" not in incident
        assert incident["has_triage_raw"] is True

        assert digest["triage"] == TRIAGE_REPORT
        assert digest["dispatches"][0]["connector"] == "pagerduty"

        session = digest["session"]
        assert session["status"] == "owner"
        assert session["session_id"] == "ses-alice"
        assert session["title"] == "triage inc-abc123"

        assert provenance["incident_id"] == "inc-abc123"
        assert provenance["sessions"] == [
            {
                "session_id": "ses-alice",
                "coverage": "owner",
                "cited_record_ids": ["cf-1"],
            }
        ]

    def test_no_report_yields_not_triaged_marker(self, stores) -> None:
        digest, _ = build_digest(
            "alice", _bundle(session_id=None, report=None), can_view_foreign=False
        )
        assert digest["triage"] == dict(NOT_TRIAGED)

    def test_foreign_session_with_capability_metadata_only(self, stores) -> None:
        stores["sessions"].create_session(user_id="carol", session_id="ses-alice")
        digest, provenance = build_digest(
            "alice", _bundle(), can_view_foreign=True
        )
        session = digest["session"]
        assert session["status"] == "foreign"
        assert session["coverage"] == "foreign"
        # The metadata tier never carries the owner's title.
        assert "title" not in session
        assert provenance["sessions"][0]["coverage"] == "foreign"

    def test_foreign_session_denied_rides_marker(self, stores) -> None:
        stores["sessions"].create_session(user_id="carol", session_id="ses-alice")
        digest, provenance = build_digest(
            "alice", _bundle(), can_view_foreign=False
        )
        assert digest["session"] == {
            "status": "foreign_denied",
            "session_id": "ses-alice",
        }
        # Denied coverage is never a provenance entry.
        assert provenance["sessions"] == []

    def test_missing_session_marker_when_incident_has_none(self, stores) -> None:
        digest, provenance = build_digest(
            "alice", _bundle(session_id=None), can_view_foreign=True
        )
        assert digest["session"] == {"status": "missing"}
        assert provenance["sessions"] == []

    def test_store_failure_degrades_to_unavailable(self, stores, monkeypatch) -> None:
        def _boom(session_id):
            raise RuntimeError("store offline")

        monkeypatch.setattr(incident_report.SESSION_STORE, "get_session", _boom)
        digest, provenance = build_digest("alice", _bundle(), can_view_foreign=True)
        assert digest["session"] == {
            "status": "unavailable",
            "session_id": "ses-alice",
        }
        assert provenance["sessions"] == []

    def test_vanished_session_degrades_to_unavailable(self, stores) -> None:
        # The incident links a session the store no longer covers.
        digest, _ = build_digest("alice", _bundle(), can_view_foreign=True)
        assert digest["session"]["status"] == "unavailable"

    def test_empty_dispatches_copy_verbatim(self, stores) -> None:
        bundle = _bundle(session_id=None)
        bundle["dispatches"] = []
        digest, _ = build_digest("alice", bundle, can_view_foreign=False)
        assert digest["dispatches"] == []


class TestDocumentSummary:
    def test_triaged_owner_summary_is_counts_only(self, stores) -> None:
        stores["sessions"].create_session(user_id="alice", session_id="ses-alice")
        digest, _ = build_digest("alice", _bundle(), can_view_foreign=False)
        summary = document_summary(digest)
        assert summary == (
            "critical · triaged · triage report present · 1 dispatch · own session"
        )
        # Never the incident title or summary text (envelope-only safety).
        assert "Payment API latency" not in summary

    def test_not_triaged_and_missing_session_phrases(self, stores) -> None:
        bundle = _bundle(session_id=None, report=None)
        bundle["dispatches"] = []
        digest, _ = build_digest("alice", bundle, can_view_foreign=False)
        summary = document_summary(digest)
        assert "not triaged" in summary
        assert "0 dispatches" in summary
        assert "no linked session" in summary

    def test_denied_and_unavailable_phrases(self, stores) -> None:
        stores["sessions"].create_session(user_id="carol", session_id="ses-alice")
        denied, _ = build_digest("alice", _bundle(), can_view_foreign=False)
        assert "foreign session denied" in document_summary(denied)

    def test_missing_incident_section_returns_none(self) -> None:
        assert document_summary({"triage": dict(NOT_TRIAGED)}) is None
