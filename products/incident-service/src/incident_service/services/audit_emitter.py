"""Built-in audit connector (SPEC-015 R-5).

The ``audit`` connector emits a structured ``incident_triaged`` event to the
audit-service ingest endpoint, using the same ingest-credential vocabulary as
the other emitters (gateway-held-style Basic credential from
``INCIDENT_AUDIT_*``). The event carries the incident envelope, the report
summary, the ranked next-step titles, and the cited skills so the full
intake → triage → dispatch chain is queryable from the audit trail.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import httpx

from incident_service.core.config import IncidentSettings
from incident_service.schemas.incident import Incident, TriageReport
from incident_service.services.connectors import ConnectorOutcome

LOGGER = logging.getLogger(__name__)

INGEST_PATH = "/api/v1/audit/events"
EMITTER_SERVICE = "incident-service"
REQUEST_TIMEOUT_SECONDS = 10.0


class AuditConnector:
    """Delivers the triage outcome to audit-service as one ingest batch."""

    name = "audit"

    def __init__(self, settings: IncidentSettings) -> None:
        self._service_url = settings.audit_service_url.rstrip("/")
        self._client_id = settings.audit_client_id
        self._client_secret = settings.audit_client_secret

    def _build_event(
        self, incident: Incident, report: TriageReport
    ) -> dict[str, object]:
        event_id = str(uuid.uuid4())
        return {
            "event_id": event_id,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "event_type": "incident_triaged",
            "service": EMITTER_SERVICE,
            "request_id": event_id,
            "username": report.generated_by,
            "session_id": report.session_id,
            "outcome": "success",
            "details": {
                "incident": incident.envelope(),
                "severity_assessment": report.severity_assessment.value,
                "report_summary": report.summary,
                "next_steps": [step.title for step in report.next_steps],
                "skills_cited": list(report.skills_cited),
            },
        }

    async def dispatch(
        self, incident: Incident, report: TriageReport
    ) -> ConnectorOutcome:
        if not self._service_url:
            return ConnectorOutcome(
                status="failed",
                error="audit-service not configured "
                "(INCIDENT_AUDIT_SERVICE_URL is empty)",
            )
        event = self._build_event(incident, report)
        try:
            async with httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT_SECONDS
            ) as client:
                response = await client.post(
                    f"{self._service_url}{INGEST_PATH}",
                    json={"events": [event]},
                    auth=(self._client_id, self._client_secret),
                )
        except httpx.HTTPError as exc:
            return ConnectorOutcome(
                status="failed",
                error=f"audit-service unreachable: {exc.__class__.__name__}",
            )
        if response.status_code < 300:
            return ConnectorOutcome(
                status="delivered", reference=str(event["event_id"])
            )
        return ConnectorOutcome(
            status="failed",
            error=f"audit-service rejected the event with "
            f"{response.status_code}",
        )
