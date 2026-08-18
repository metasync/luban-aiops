"""Frozen incident-service settings loaded from environment variables (SPEC-015 R-2).

Mirrors the skills-hub settings vocabulary (SPEC-014 precedent) with the
incident-specific intake, triage, and connector knobs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


class SettingsError(Exception):
    """Raised when an INCIDENT_* setting is malformed (fail startup fast)."""


@dataclass(frozen=True)
class QueryClient:
    """Registered static platform-caller credential (SPEC-014 R-3 vocabulary)."""

    client_id: str
    secret: str


@dataclass(frozen=True)
class WorkloadClient:
    """Projected-token subject to registered client mapping (SPEC-009 R-3)."""

    workload_subject: str
    client_id: str


def parse_query_clients(raw: str) -> tuple[QueryClient, ...]:
    """Parse ``INCIDENT_QUERY_CLIENTS`` (``client_id=secret,client_id=secret``)."""
    clients: list[QueryClient] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        client_id, _, secret = entry.partition("=")
        if client_id and secret:
            clients.append(QueryClient(client_id=client_id, secret=secret))
    return tuple(clients)


def parse_workload_clients(raw: str) -> tuple[WorkloadClient, ...]:
    """Parse ``INCIDENT_WORKLOAD_CLIENTS`` (``subject=client_id,...``)."""
    mappings: list[WorkloadClient] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        subject, _, client_id = entry.partition("=")
        if subject and client_id:
            mappings.append(
                WorkloadClient(workload_subject=subject, client_id=client_id)
            )
    return tuple(mappings)


def parse_connectors(raw: str) -> tuple[str, ...]:
    """Parse ``INCIDENT_CONNECTORS`` (comma list of registered connector names).

    Empty input selects the built-in audit sink; unknown names fail at
    connector construction (startup), not here.
    """
    names = [entry.strip() for entry in raw.split(",") if entry.strip()]
    return tuple(names) if names else ("audit",)


@dataclass(frozen=True)
class IncidentSettings:
    """Frozen settings loaded from environment variables (SPEC-015 R-2/R-3/R-5)."""

    webhook_token: str = ""
    query_clients: tuple[QueryClient, ...] = field(default_factory=tuple)
    workload_issuer_url: str = ""
    workload_audience: str = "incident-service"
    workload_clients: tuple[WorkloadClient, ...] = field(default_factory=tuple)
    store_backend: str = "memory"
    db_url: str = ""
    connectors: tuple[str, ...] = ("audit",)
    agent_service_url: str = "http://agent-service:8000"
    triage_timeout_seconds: float = 120.0
    audit_service_url: str = ""
    audit_client_id: str = "incident-service"
    audit_client_secret: str = ""

    @classmethod
    def from_env(cls) -> "IncidentSettings":
        return cls(
            webhook_token=os.getenv("INCIDENT_WEBHOOK_TOKEN", ""),
            query_clients=parse_query_clients(
                os.getenv("INCIDENT_QUERY_CLIENTS", "")
            ),
            workload_issuer_url=os.getenv("INCIDENT_WORKLOAD_ISSUER_URL", ""),
            workload_audience=os.getenv(
                "INCIDENT_WORKLOAD_AUDIENCE", "incident-service"
            ),
            workload_clients=parse_workload_clients(
                os.getenv("INCIDENT_WORKLOAD_CLIENTS", "")
            ),
            store_backend=os.getenv("INCIDENT_STORE_BACKEND", "memory")
            .strip()
            .lower(),
            db_url=os.getenv("INCIDENT_DB_URL", ""),
            connectors=parse_connectors(os.getenv("INCIDENT_CONNECTORS", "")),
            agent_service_url=os.getenv(
                "INCIDENT_AGENT_SERVICE_URL", "http://agent-service:8000"
            ),
            triage_timeout_seconds=float(
                os.getenv("INCIDENT_TRIAGE_TIMEOUT_SECONDS", "120")
            ),
            audit_service_url=os.getenv("INCIDENT_AUDIT_SERVICE_URL", ""),
            audit_client_id=os.getenv(
                "INCIDENT_AUDIT_CLIENT_ID", "incident-service"
            ),
            audit_client_secret=os.getenv("INCIDENT_AUDIT_CLIENT_SECRET", ""),
        )


@lru_cache(maxsize=1)
def get_settings() -> IncidentSettings:
    return IncidentSettings.from_env()
