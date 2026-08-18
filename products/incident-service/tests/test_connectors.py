"""Connector framework tests (SPEC-015 R-5)."""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import httpx

from incident_service.core.config import IncidentSettings
from incident_service.schemas.incident import (
    Incident,
    IncidentSource,
    IncidentStatus,
    TriageReport,
)
from incident_service.services import audit_emitter
from incident_service.services.audit_emitter import AuditConnector
from incident_service.services.connectors import (
    ConnectorConfigError,
    ConnectorOutcome,
    build_connectors,
    dispatch_report,
)
from incident_service.services.incident_store import InMemoryIncidentStore

NOW = datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc)


def _run(coro):
    return asyncio.run(coro)


def _incident() -> Incident:
    return Incident(
        incident_id="inc-aaa111",
        fingerprint="fp-1",
        source=IncidentSource.ALERTMANAGER,
        severity="warning",
        status=IncidentStatus.TRIAGED,
        title="Pod stuck",
        summary="summary",
        labels={"alertname": "KubePodNotReady"},
        created_at=NOW,
        updated_at=NOW,
    )


def _report() -> TriageReport:
    return TriageReport(
        incident_id="inc-aaa111",
        summary="assessment",
        severity_assessment="critical",
        evidence=[],
        hypotheses=["crash loop"],
        next_steps=[
            {"title": "check logs", "rationale": "evidence", "priority": "high"}
        ],
        skills_cited=["sre-alerting/kubepodcrashlooping"],
        session_id="incident-inc-aaa111",
        generated_at=NOW,
        generated_by="alice",
    )


class RegistryTests(unittest.TestCase):
    def test_default_selection_builds_audit_connector(self) -> None:
        connectors = build_connectors(IncidentSettings())
        self.assertEqual([c.name for c in connectors], ["audit"])

    def test_unknown_connector_fails_startup(self) -> None:
        with self.assertRaises(ConnectorConfigError):
            build_connectors(IncidentSettings(connectors=("slack",)))


def _mock_async_client(handler) -> object:
    """Patch target: route the emitter through an httpx MockTransport."""
    real_client = httpx.AsyncClient

    def factory(**kwargs):
        return real_client(
            transport=httpx.MockTransport(handler), timeout=1.0
        )

    return factory


class AuditConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = IncidentSettings(
            audit_service_url="http://audit-service:8000/",
            audit_client_id="incident-service",
            audit_client_secret="audit-secret",
        )

    def test_dispatch_delivers_structured_event(self) -> None:
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("authorization", "")
            seen["body"] = request.read()
            return httpx.Response(202, json={"accepted": 1, "inserted": 1})

        connector = AuditConnector(self.settings)
        with patch.object(
            audit_emitter.httpx, "AsyncClient", _mock_async_client(handler)
        ):
            outcome = _run(connector.dispatch(_incident(), _report()))
        self.assertEqual(outcome.status, "delivered")
        self.assertIsNotNone(outcome.reference)
        self.assertTrue(
            seen["url"].endswith("/api/v1/audit/events")
        )
        import json

        event = json.loads(seen["body"])["events"][0]
        self.assertEqual(event["event_type"], "incident_triaged")
        self.assertEqual(event["service"], "incident-service")
        self.assertEqual(event["outcome"], "success")
        self.assertEqual(event["session_id"], "incident-inc-aaa111")
        self.assertEqual(event["username"], "alice")
        self.assertEqual(
            event["details"]["incident"]["incident_id"], "inc-aaa111"
        )
        self.assertEqual(event["details"]["next_steps"], ["check logs"])
        self.assertEqual(
            event["details"]["skills_cited"],
            ["sre-alerting/kubepodcrashlooping"],
        )
        # Basic credential from INCIDENT_AUDIT_* is presented.
        import base64

        decoded = base64.b64decode(seen["auth"].split()[1]).decode()
        self.assertEqual(decoded, "incident-service:audit-secret")

    def test_dispatch_fails_when_audit_url_missing(self) -> None:
        connector = AuditConnector(IncidentSettings(audit_service_url=""))
        outcome = _run(connector.dispatch(_incident(), _report()))
        self.assertEqual(outcome.status, "failed")
        self.assertIn("not configured", outcome.error)

    def test_dispatch_maps_rejection_to_failed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": "bad credential"})

        connector = AuditConnector(self.settings)
        with patch.object(
            audit_emitter.httpx, "AsyncClient", _mock_async_client(handler)
        ):
            outcome = _run(connector.dispatch(_incident(), _report()))
        self.assertEqual(outcome.status, "failed")
        self.assertIn("401", outcome.error)

    def test_dispatch_maps_unreachable_to_failed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        connector = AuditConnector(self.settings)
        with patch.object(
            audit_emitter.httpx, "AsyncClient", _mock_async_client(handler)
        ):
            outcome = _run(connector.dispatch(_incident(), _report()))
        self.assertEqual(outcome.status, "failed")
        self.assertIn("unreachable", outcome.error)


class _StubConnector:
    def __init__(self, name: str, outcome=None, raises: bool = False) -> None:
        self.name = name
        self._outcome = outcome or ConnectorOutcome(status="delivered")
        self._raises = raises

    async def dispatch(self, incident, report) -> ConnectorOutcome:
        if self._raises:
            raise RuntimeError("connector exploded")
        return self._outcome


class DispatchTests(unittest.TestCase):
    def test_dispatches_recorded_per_incident(self) -> None:
        store = InMemoryIncidentStore()
        _run(store.create(_incident()))
        connectors = (_StubConnector("audit"), _StubConnector("jira"))
        dispatches = _run(
            dispatch_report(store, connectors, _incident(), _report())
        )
        self.assertEqual([d.status for d in dispatches], ["delivered", "delivered"])
        stored = _run(store.get_dispatches("inc-aaa111"))
        self.assertEqual([d.connector for d in stored], ["audit", "jira"])

    def test_connector_failure_is_isolated(self) -> None:
        store = InMemoryIncidentStore()
        _run(store.create(_incident()))
        connectors = (
            _StubConnector("broken", raises=True),
            _StubConnector("audit"),
        )
        dispatches = _run(
            dispatch_report(store, connectors, _incident(), _report())
        )
        self.assertEqual(dispatches[0].status, "failed")
        self.assertIn("connector exploded", dispatches[0].error)
        # The second connector still ran.
        self.assertEqual(dispatches[1].status, "delivered")

    def test_failed_outcome_carries_error(self) -> None:
        store = InMemoryIncidentStore()
        _run(store.create(_incident()))
        connectors = (
            _StubConnector(
                "audit", ConnectorOutcome(status="failed", error="rejected")
            ),
        )
        dispatches = _run(
            dispatch_report(store, connectors, _incident(), _report())
        )
        self.assertEqual(dispatches[0].status, "failed")
        self.assertEqual(dispatches[0].error, "rejected")


if __name__ == "__main__":
    unittest.main()
