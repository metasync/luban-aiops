"""Incident store strategy (SPEC-015 R-2, SPEC-013/SPEC-014 strategy precedent).

``build_incident_store`` selects the backend from ``INCIDENT_STORE_BACKEND``:
``memory`` for tests/dev, ``postgres`` for deployed environments. Incidents,
their triage reports, and connector dispatch records live in one store so the
incident record is the single read model for the portal, tools, and connectors.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, Protocol

from incident_service.core.config import IncidentSettings
from incident_service.schemas.incident import (
    ConnectorDispatch,
    Incident,
    TriageReport,
)

LOGGER = logging.getLogger(__name__)


class StoreError(Exception):
    """Raised when a store operation cannot be completed."""


class IncidentStore(Protocol):
    """Backend contract shared by the in-memory and PostgreSQL stores."""

    async def initialize(self) -> None: ...

    async def create(self, incident: Incident) -> Incident: ...

    async def save(self, incident: Incident) -> Incident: ...

    async def get(self, incident_id: str) -> Incident | None: ...

    async def get_open_by_fingerprint(self, fingerprint: str) -> Incident | None: ...

    async def list(
        self,
        offset: int,
        limit: int,
        status: str | None = None,
        severity: str | None = None,
        source: str | None = None,
    ) -> tuple[list[Incident], int]: ...

    async def set_report(self, incident_id: str, report: TriageReport) -> None: ...

    async def get_report(self, incident_id: str) -> TriageReport | None: ...

    async def add_dispatch(
        self, incident_id: str, dispatch: ConnectorDispatch
    ) -> None: ...

    async def get_dispatches(self, incident_id: str) -> list[ConnectorDispatch]: ...

    async def count(self, open_only: bool = False) -> int: ...

    async def ready(self) -> bool: ...

    async def close(self) -> None: ...


# --- In-memory store (tests / dev) -------------------------------------------


class InMemoryIncidentStore:
    """Dict-backed store; loses its records on restart (dev/test only)."""

    def __init__(self) -> None:
        self._incidents: dict[str, Incident] = {}
        self._reports: dict[str, TriageReport] = {}
        self._dispatches: dict[str, list[ConnectorDispatch]] = {}

    async def initialize(self) -> None:
        return None

    async def create(self, incident: Incident) -> Incident:
        self._incidents[incident.incident_id] = incident
        return incident

    async def save(self, incident: Incident) -> Incident:
        self._incidents[incident.incident_id] = incident
        return incident

    async def get(self, incident_id: str) -> Incident | None:
        return self._incidents.get(incident_id)

    async def get_open_by_fingerprint(self, fingerprint: str) -> Incident | None:
        candidates = [
            incident
            for incident in self._incidents.values()
            if incident.fingerprint == fingerprint and incident.status.value != "resolved"
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda incident: incident.created_at, reverse=True)
        return candidates[0]

    async def list(
        self,
        offset: int,
        limit: int,
        status: str | None = None,
        severity: str | None = None,
        source: str | None = None,
    ) -> tuple[list[Incident], int]:
        records = [
            incident
            for incident in self._incidents.values()
            if (status is None or incident.status.value == status)
            and (severity is None or incident.severity.value == severity)
            and (source is None or incident.source.value == source)
        ]
        records.sort(
            key=lambda incident: (incident.created_at, incident.incident_id),
            reverse=True,
        )
        return records[offset : offset + limit], len(records)

    async def set_report(self, incident_id: str, report: TriageReport) -> None:
        self._reports[incident_id] = report

    async def get_report(self, incident_id: str) -> TriageReport | None:
        return self._reports.get(incident_id)

    async def add_dispatch(
        self, incident_id: str, dispatch: ConnectorDispatch
    ) -> None:
        self._dispatches.setdefault(incident_id, []).append(dispatch)

    async def get_dispatches(self, incident_id: str) -> list[ConnectorDispatch]:
        return list(self._dispatches.get(incident_id, []))

    async def count(self, open_only: bool = False) -> int:
        if not open_only:
            return len(self._incidents)
        return sum(
            1
            for incident in self._incidents.values()
            if incident.status.value != "resolved"
        )

    async def ready(self) -> bool:
        return True

    async def close(self) -> None:
        return None


# --- PostgreSQL store (deployed environments) --------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    source      TEXT NOT NULL,
    severity    TEXT NOT NULL,
    status      TEXT NOT NULL,
    title       TEXT NOT NULL,
    summary     TEXT NOT NULL,
    labels      JSONB NOT NULL,
    reported_by TEXT,
    session_id  TEXT,
    triage_raw  TEXT,
    created_at  TIMESTAMPTZ NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_incidents_status_created
    ON incidents (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_fingerprint
    ON incidents (fingerprint);
CREATE TABLE IF NOT EXISTS triage_reports (
    incident_id  TEXT PRIMARY KEY REFERENCES incidents (incident_id),
    report       JSONB NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS connector_dispatches (
    id          BIGSERIAL PRIMARY KEY,
    incident_id TEXT NOT NULL REFERENCES incidents (incident_id),
    connector   TEXT NOT NULL,
    status      TEXT NOT NULL,
    reference   TEXT,
    error       TEXT,
    created_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dispatches_incident
    ON connector_dispatches (incident_id, id);
"""

_INCIDENT_COLUMNS = (
    "incident_id, fingerprint, source, severity, status, title, summary, "
    "labels, reported_by, session_id, triage_raw, created_at, updated_at, "
    "resolved_at"
)

_UPSERT = """
INSERT INTO incidents (
    incident_id, fingerprint, source, severity, status, title, summary,
    labels, reported_by, session_id, triage_raw, created_at, updated_at,
    resolved_at
) VALUES (
    %(incident_id)s, %(fingerprint)s, %(source)s, %(severity)s, %(status)s,
    %(title)s, %(summary)s, %(labels)s, %(reported_by)s, %(session_id)s,
    %(triage_raw)s, %(created_at)s, %(updated_at)s, %(resolved_at)s
)
ON CONFLICT (incident_id) DO UPDATE SET
    fingerprint = EXCLUDED.fingerprint,
    source = EXCLUDED.source,
    severity = EXCLUDED.severity,
    status = EXCLUDED.status,
    title = EXCLUDED.title,
    summary = EXCLUDED.summary,
    labels = EXCLUDED.labels,
    reported_by = EXCLUDED.reported_by,
    session_id = EXCLUDED.session_id,
    triage_raw = EXCLUDED.triage_raw,
    created_at = EXCLUDED.created_at,
    updated_at = EXCLUDED.updated_at,
    resolved_at = EXCLUDED.resolved_at
"""

ConnectFactory = Callable[[], AsyncIterator[Any]]


def _incident_params(incident: Incident) -> dict[str, Any]:
    payload = incident.model_dump(mode="json")
    return {
        "incident_id": payload["incident_id"],
        "fingerprint": payload["fingerprint"],
        "source": payload["source"],
        "severity": payload["severity"],
        "status": payload["status"],
        "title": payload["title"],
        "summary": payload["summary"],
        # psycopg3 requires a serialized JSON string for JSONB columns —
        # raw dicts break the binary adapter lookup.
        "labels": json.dumps(payload["labels"]),
        "reported_by": payload.get("reported_by"),
        "session_id": payload.get("session_id"),
        "triage_raw": payload.get("triage_raw"),
        "created_at": incident.created_at,
        "updated_at": incident.updated_at,
        "resolved_at": incident.resolved_at,
    }


def _row_to_incident(row: dict[str, Any]) -> Incident:
    labels = row["labels"]
    if isinstance(labels, str):
        labels = json.loads(labels)
    return Incident(
        incident_id=row["incident_id"],
        fingerprint=row["fingerprint"],
        source=row["source"],
        severity=row["severity"],
        status=row["status"],
        title=row["title"],
        summary=row["summary"],
        labels=labels or {},
        reported_by=row["reported_by"],
        session_id=row["session_id"],
        triage_raw=row["triage_raw"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        resolved_at=row["resolved_at"],
    )


def _incident_row_names() -> tuple[str, ...]:
    return tuple(name.strip() for name in _INCIDENT_COLUMNS.split(","))


class PostgresIncidentStore:
    """Durable store over the ``incidents`` database.

    Connections are opened per operation (incident traffic is low-volume);
    the ``connect`` factory is injectable so tests can substitute a fake
    driver.
    """

    def __init__(
        self,
        db_url: str,
        connect: ConnectFactory | None = None,
    ) -> None:
        self._db_url = db_url
        self._connect = connect or self._default_connect

    @asynccontextmanager
    async def _default_connect(self) -> AsyncIterator[Any]:
        import psycopg

        conn = await psycopg.AsyncConnection.connect(
            self._db_url, autocommit=False
        )
        try:
            yield conn
        finally:
            await conn.close()

    async def initialize(self) -> None:
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(_DDL)
            await conn.commit()

    async def create(self, incident: Incident) -> Incident:
        return await self.save(incident)

    async def save(self, incident: Incident) -> Incident:
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(_UPSERT, _incident_params(incident))
            await conn.commit()
        return incident

    async def get(self, incident_id: str) -> Incident | None:
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_INCIDENT_COLUMNS} FROM incidents "
                    "WHERE incident_id = %(incident_id)s",
                    {"incident_id": incident_id},
                )
                row = await cur.fetchone()
        if row is None:
            return None
        return _row_to_incident(dict(zip(_incident_row_names(), row)))

    async def get_open_by_fingerprint(self, fingerprint: str) -> Incident | None:
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_INCIDENT_COLUMNS} FROM incidents "
                    "WHERE fingerprint = %(fingerprint)s "
                    "AND status <> 'resolved' "
                    "ORDER BY created_at DESC LIMIT 1",
                    {"fingerprint": fingerprint},
                )
                row = await cur.fetchone()
        if row is None:
            return None
        return _row_to_incident(dict(zip(_incident_row_names(), row)))

    async def list(
        self,
        offset: int,
        limit: int,
        status: str | None = None,
        severity: str | None = None,
        source: str | None = None,
    ) -> tuple[list[Incident], int]:
        where, params = self._filter_clause(status, severity, source)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT count(*) FROM incidents {clause}", params
                )
                count_row = await cur.fetchone()
                total = int(count_row[0]) if count_row else 0
                await cur.execute(
                    f"SELECT {_INCIDENT_COLUMNS} FROM incidents {clause} "
                    "ORDER BY created_at DESC, incident_id DESC "
                    "LIMIT %(limit)s OFFSET %(offset)s",
                    {**params, "limit": limit, "offset": offset},
                )
                rows = [
                    dict(zip(_incident_row_names(), row))
                    for row in await cur.fetchall()
                ]
        return [_row_to_incident(row) for row in rows], total

    @staticmethod
    def _filter_clause(
        status: str | None, severity: str | None, source: str | None
    ) -> tuple[list[str], dict[str, Any]]:
        where: list[str] = []
        params: dict[str, Any] = {}
        if status:
            where.append("status = %(status)s")
            params["status"] = status
        if severity:
            where.append("severity = %(severity)s")
            params["severity"] = severity
        if source:
            where.append("source = %(source)s")
            params["source"] = source
        return where, params

    async def set_report(self, incident_id: str, report: TriageReport) -> None:
        payload = report.model_dump(mode="json")
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO triage_reports (incident_id, report, generated_at)
                    VALUES (%(incident_id)s, %(report)s, %(generated_at)s)
                    ON CONFLICT (incident_id) DO UPDATE SET
                        report = EXCLUDED.report,
                        generated_at = EXCLUDED.generated_at
                    """,
                    {
                        "incident_id": incident_id,
                        "report": json.dumps(payload),
                        "generated_at": report.generated_at,
                    },
                )
            await conn.commit()

    async def get_report(self, incident_id: str) -> TriageReport | None:
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT report FROM triage_reports "
                    "WHERE incident_id = %(incident_id)s",
                    {"incident_id": incident_id},
                )
                row = await cur.fetchone()
        if row is None:
            return None
        report = row[0]
        if isinstance(report, str):
            report = json.loads(report)
        return TriageReport.model_validate(report)

    async def add_dispatch(
        self, incident_id: str, dispatch: ConnectorDispatch
    ) -> None:
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO connector_dispatches (
                        incident_id, connector, status, reference, error,
                        created_at
                    ) VALUES (
                        %(incident_id)s, %(connector)s, %(status)s,
                        %(reference)s, %(error)s, %(created_at)s
                    )
                    """,
                    {
                        "incident_id": incident_id,
                        "connector": dispatch.connector,
                        "status": dispatch.status,
                        "reference": dispatch.reference,
                        "error": dispatch.error,
                        "created_at": dispatch.created_at,
                    },
                )
            await conn.commit()

    async def get_dispatches(self, incident_id: str) -> list[ConnectorDispatch]:
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT connector, status, reference, error, created_at "
                    "FROM connector_dispatches "
                    "WHERE incident_id = %(incident_id)s ORDER BY id",
                    {"incident_id": incident_id},
                )
                rows = await cur.fetchall()
        return [
            ConnectorDispatch(
                connector=row[0],
                status=row[1],
                reference=row[2],
                error=row[3],
                created_at=row[4],
            )
            for row in rows
        ]

    async def count(self, open_only: bool = False) -> int:
        query = "SELECT count(*) FROM incidents"
        if open_only:
            query += " WHERE status <> 'resolved'"
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query)
                row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def ready(self) -> bool:
        try:
            async with self._connect() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
                    await cur.fetchone()
            return True
        except Exception:  # noqa: BLE001 - readiness must never raise
            return False

    async def close(self) -> None:
        return None


# --- Factory ------------------------------------------------------------------


def build_incident_store(settings: IncidentSettings) -> IncidentStore:
    """Select the store backend from settings (default: in-memory)."""
    if settings.store_backend == "postgres":
        if not settings.db_url:
            raise StoreError(
                "INCIDENT_DB_URL is required when INCIDENT_STORE_BACKEND=postgres"
            )
        return PostgresIncidentStore(settings.db_url)
    return InMemoryIncidentStore()
