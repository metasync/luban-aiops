"""Collaboration connector framework (SPEC-015 R-5).

A connector pushes a validated triage report onto a collaboration surface.
R3 ships the contract plus one built-in sink (the ``audit`` connector);
collaboration adapters (Slack, Jira, ...) implement the same protocol and
register in ``CONNECTOR_REGISTRY``.

Dispatch failures are recorded and counted but never raised into the triage
path — a connector outage must not turn a successful triage into a failure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol

from incident_service.core.config import IncidentSettings
from incident_service.core.metrics import record_dispatch
from incident_service.core.observability import log_event
from incident_service.schemas.incident import (
    ConnectorDispatch,
    Incident,
    TriageReport,
)

LOGGER = logging.getLogger(__name__)


class ConnectorConfigError(Exception):
    """Raised at startup when INCIDENT_CONNECTORS names an unknown connector."""


@dataclass(frozen=True)
class ConnectorOutcome:
    """Structured result of one connector dispatch."""

    status: str  # "delivered" | "failed"
    reference: str | None = None
    error: str | None = None


class Connector(Protocol):
    """Contract every collaboration connector implements."""

    name: str

    async def dispatch(
        self, incident: Incident, report: TriageReport
    ) -> ConnectorOutcome:
        """Push the report onto the collaboration surface."""
        ...


ConnectorFactory = Callable[[IncidentSettings], Connector]


def _build_audit_connector(settings: IncidentSettings) -> Connector:
    # Local import keeps the registry importable without the emitter's deps.
    from incident_service.services.audit_emitter import AuditConnector

    return AuditConnector(settings)


# Registry of connector name -> factory receiving the service settings.
# Extend by adding a factory here; select via INCIDENT_CONNECTORS.
CONNECTOR_REGISTRY: dict[str, ConnectorFactory] = {
    "audit": _build_audit_connector,
}


def build_connectors(settings: IncidentSettings) -> tuple[Connector, ...]:
    """Instantiate the configured connectors; unknown names fail fast."""
    connectors: list[Connector] = []
    for name in settings.connectors:
        factory = CONNECTOR_REGISTRY.get(name)
        if factory is None:
            raise ConnectorConfigError(
                f"unknown connector '{name}' in INCIDENT_CONNECTORS; "
                f"registered: {sorted(CONNECTOR_REGISTRY)}"
            )
        connectors.append(factory(settings))
    return tuple(connectors)


async def dispatch_report(
    store,
    connectors: tuple[Connector, ...],
    incident: Incident,
    report: TriageReport,
) -> list[ConnectorDispatch]:
    """Push a triage report through every connector and record the outcomes.

    Each connector is isolated: an exception becomes a failed dispatch record
    rather than an abort of the remaining connectors or the triage path.
    """
    dispatches: list[ConnectorDispatch] = []
    for connector in connectors:
        try:
            outcome = await connector.dispatch(incident, report)
        except Exception as exc:  # noqa: BLE001 - isolation by design
            outcome = ConnectorOutcome(
                status="failed", error=f"{exc.__class__.__name__}: {exc}"
            )
        result = "delivered" if outcome.status == "delivered" else "failed"
        record_dispatch(connector.name, result)
        dispatch = ConnectorDispatch(
            connector=connector.name,
            status=outcome.status,
            reference=outcome.reference,
            error=outcome.error,
            created_at=datetime.now(timezone.utc),
        )
        await store.add_dispatch(incident.incident_id, dispatch)
        dispatches.append(dispatch)
        log_event(
            LOGGER,
            "connector_dispatched",
            connector=connector.name,
            incident_id=incident.incident_id,
            result=result,
            reference=outcome.reference,
            error=outcome.error,
        )
    return dispatches
