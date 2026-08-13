from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass(frozen=True)
class IngestClient:
    """Registered static ingest credential (SPEC-008 R-3 vocabulary)."""

    client_id: str
    secret: str


@dataclass(frozen=True)
class WorkloadClient:
    """Projected-token subject to registered client mapping (SPEC-009 R-3)."""

    workload_subject: str
    client_id: str


def parse_ingest_clients(raw: str) -> tuple[IngestClient, ...]:
    """Parse ``AUDIT_INGEST_CLIENTS`` (``client_id=secret,client_id=secret``)."""
    clients: list[IngestClient] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        client_id, _, secret = entry.partition("=")
        if client_id and secret:
            clients.append(IngestClient(client_id=client_id, secret=secret))
    return tuple(clients)


def parse_workload_clients(raw: str) -> tuple[WorkloadClient, ...]:
    """Parse ``AUDIT_WORKLOAD_CLIENTS`` (``subject=client_id,subject=client_id``)."""
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


@dataclass(frozen=True)
class AuditSettings:
    """Frozen settings loaded from environment variables (SPEC-013 R-2)."""

    store_backend: str = "memory"
    db_url: str = ""
    ingest_clients: tuple[IngestClient, ...] = field(default_factory=tuple)
    workload_issuer_url: str = ""
    workload_audience: str = "audit-service"
    workload_clients: tuple[WorkloadClient, ...] = field(default_factory=tuple)
    retention_days: int = 30
    max_events: int = 100_000
    eviction_interval_seconds: int = 3600
    eviction_batch_size: int = 1000
    max_batch: int = 50

    @classmethod
    def from_env(cls) -> "AuditSettings":
        return cls(
            store_backend=os.getenv("AUDIT_STORE_BACKEND", "memory").strip().lower(),
            db_url=os.getenv("AUDIT_DB_URL", ""),
            ingest_clients=parse_ingest_clients(
                os.getenv("AUDIT_INGEST_CLIENTS", "")
            ),
            workload_issuer_url=os.getenv("AUDIT_WORKLOAD_ISSUER_URL", ""),
            workload_audience=os.getenv(
                "AUDIT_WORKLOAD_AUDIENCE", "audit-service"
            ),
            workload_clients=parse_workload_clients(
                os.getenv("AUDIT_WORKLOAD_CLIENTS", "")
            ),
            retention_days=int(os.getenv("AUDIT_RETENTION_DAYS", "30")),
            max_events=int(os.getenv("AUDIT_MAX_EVENTS", "100000")),
            eviction_interval_seconds=int(
                os.getenv("AUDIT_EVICTION_INTERVAL_SECONDS", "3600")
            ),
            eviction_batch_size=int(
                os.getenv("AUDIT_EVICTION_BATCH_SIZE", "1000")
            ),
            max_batch=int(os.getenv("AUDIT_MAX_BATCH", "50")),
        )


@lru_cache(maxsize=1)
def get_settings() -> AuditSettings:
    return AuditSettings.from_env()
