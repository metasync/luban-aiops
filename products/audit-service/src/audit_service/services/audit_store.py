"""Audit store strategy (SPEC-013 R-2, SPEC-006 strategy-pattern precedent).

``build_audit_store`` selects the backend from ``AUDIT_STORE_BACKEND``:
``memory`` for tests/dev, ``postgres`` for deployed environments. Events are
stored and returned verbatim — no field rewriting between ingest and query.
"""

from __future__ import annotations

import base64
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Protocol, Sequence

from audit_service.core.config import AuditSettings
from audit_service.schemas.audit import AuditEvent, AuditQuery

LOGGER = logging.getLogger(__name__)


class StoreError(Exception):
    """Raised when a store operation cannot be completed."""


@dataclass(frozen=True)
class AuditPage:
    events: list[AuditEvent]
    next_cursor: str | None


class AuditStore(Protocol):
    """Backend contract shared by the in-memory and PostgreSQL stores."""

    async def initialize(self) -> None: ...

    async def add(self, events: Sequence[AuditEvent]) -> int: ...

    async def query(
        self, filters: AuditQuery, cursor: str | None, limit: int
    ) -> AuditPage: ...

    async def count(self) -> int: ...

    async def evict(
        self, cutoff: datetime, max_events: int, batch_size: int
    ) -> int: ...

    async def ready(self) -> bool: ...

    async def close(self) -> None: ...


# --- Cursor encoding ---------------------------------------------------------


def encode_cursor(occurred_at: datetime, event_id: str) -> str:
    raw = f"{occurred_at.astimezone(timezone.utc).isoformat()}|{event_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        occurred_raw, _, event_id = raw.partition("|")
        occurred_at = datetime.fromisoformat(occurred_raw)
        # Naive timestamps would blow up comparing against aware store rows;
        # the codec only ever emits timezone-aware values.
        if occurred_at.tzinfo is None:
            raise ValueError("cursor timestamp must be timezone-aware")
        if not event_id:
            raise ValueError("cursor missing event_id")
        return occurred_at, event_id
    except Exception as exc:
        raise StoreError("invalid cursor") from exc


# --- In-memory store (tests / dev) -------------------------------------------


class InMemoryAuditStore:
    """Bounded in-memory store; loses its trail on restart (dev/test only)."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._ids: set[str] = set()

    async def initialize(self) -> None:
        return None

    async def add(self, events: Sequence[AuditEvent]) -> int:
        inserted = 0
        for event in events:
            if event.event_id in self._ids:
                continue
            self._ids.add(event.event_id)
            self._events.append(event)
            inserted += 1
        return inserted

    async def query(
        self, filters: AuditQuery, cursor: str | None, limit: int
    ) -> AuditPage:
        rows = [e for e in self._events if _matches(e, filters)]
        rows.sort(key=lambda e: (e.occurred_at, e.event_id), reverse=True)
        if cursor is not None:
            cursor_ts, cursor_id = decode_cursor(cursor)
            rows = [
                e
                for e in rows
                if (e.occurred_at, e.event_id) < (cursor_ts, cursor_id)
            ]
        page, rows = rows[:limit], rows[limit:]
        next_cursor = (
            encode_cursor(page[-1].occurred_at, page[-1].event_id)
            if page and rows
            else None
        )
        return AuditPage(events=page, next_cursor=next_cursor)

    async def count(self) -> int:
        return len(self._events)

    async def evict(
        self, cutoff: datetime, max_events: int, batch_size: int
    ) -> int:
        before = len(self._events)
        kept = [e for e in self._events if e.occurred_at >= cutoff]
        kept.sort(key=lambda e: (e.occurred_at, e.event_id))
        if len(kept) > max_events:
            kept = kept[-max_events:]
        self._events = kept
        self._ids = {e.event_id for e in kept}
        return before - len(self._events)

    async def ready(self) -> bool:
        return True

    async def close(self) -> None:
        return None


def _matches(event: AuditEvent, filters: AuditQuery) -> bool:
    if filters.username and event.username != filters.username:
        return False
    if filters.session_id and event.session_id != filters.session_id:
        return False
    if filters.request_id and event.request_id != filters.request_id:
        return False
    if filters.event_type and event.event_type != filters.event_type:
        return False
    if filters.service and event.service != filters.service:
        return False
    if filters.since and event.occurred_at < filters.since:
        return False
    if filters.until and event.occurred_at > filters.until:
        return False
    return True


# --- PostgreSQL store (deployed environments) --------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS audit_events (
    event_id    TEXT PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL,
    event_type  TEXT NOT NULL,
    service     TEXT NOT NULL,
    request_id  TEXT NOT NULL,
    subject     TEXT,
    username    TEXT,
    actor       TEXT,
    roles       TEXT[],
    session_id  TEXT,
    outcome     TEXT NOT NULL,
    details     JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_audit_occurred_at
    ON audit_events (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_username
    ON audit_events (username);
CREATE INDEX IF NOT EXISTS idx_audit_session_id
    ON audit_events (session_id);
CREATE INDEX IF NOT EXISTS idx_audit_request_id
    ON audit_events (request_id);
CREATE INDEX IF NOT EXISTS idx_audit_event_type
    ON audit_events (event_type);
"""

_INSERT = """
INSERT INTO audit_events (
    event_id, occurred_at, event_type, service, request_id,
    subject, username, actor, roles, session_id, outcome, details
) VALUES (
    %(event_id)s, %(occurred_at)s, %(event_type)s, %(service)s, %(request_id)s,
    %(subject)s, %(username)s, %(actor)s, %(roles)s, %(session_id)s,
    %(outcome)s, %(details)s
)
ON CONFLICT (event_id) DO NOTHING
"""

_ROW_COLUMNS = (
    "event_id, occurred_at, event_type, service, request_id, subject, "
    "username, actor, roles, session_id, outcome, details"
)

ConnectFactory = Callable[[], AsyncIterator[Any]]


def _row_to_event(row: dict[str, Any]) -> AuditEvent:
    return AuditEvent(
        event_id=row["event_id"],
        occurred_at=row["occurred_at"],
        event_type=row["event_type"],
        service=row["service"],
        request_id=row["request_id"],
        subject=row["subject"],
        username=row["username"],
        actor=row["actor"],
        roles=list(row["roles"]) if row["roles"] is not None else None,
        session_id=row["session_id"],
        outcome=row["outcome"],
        details=row["details"] or {},
    )


class PostgresAuditStore:
    """WAL-durable store over a single ``audit_events`` table.

    Connections are opened per operation (audit traffic is low-volume); the
    ``connect`` factory is injectable so tests can substitute a fake driver.
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

    async def add(self, events: Sequence[AuditEvent]) -> int:
        from psycopg.types.json import Jsonb

        inserted = 0
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                for event in events:
                    payload = event.model_dump(mode="json")
                    await cur.execute(
                        _INSERT,
                        {
                            "event_id": payload["event_id"],
                            "occurred_at": event.occurred_at,
                            "event_type": payload["event_type"],
                            "service": payload["service"],
                            "request_id": payload["request_id"],
                            "subject": payload.get("subject"),
                            "username": payload.get("username"),
                            "actor": payload.get("actor"),
                            "roles": payload.get("roles"),
                            "session_id": payload.get("session_id"),
                            "outcome": payload["outcome"],
                            "details": Jsonb(payload.get("details", {})),
                        },
                    )
                    inserted += cur.rowcount if cur.rowcount > 0 else 0
            await conn.commit()
        return inserted

    async def query(
        self, filters: AuditQuery, cursor: str | None, limit: int
    ) -> AuditPage:
        where: list[str] = []
        params: dict[str, Any] = {}
        if filters.username:
            where.append("username = %(username)s")
            params["username"] = filters.username
        if filters.session_id:
            where.append("session_id = %(session_id)s")
            params["session_id"] = filters.session_id
        if filters.request_id:
            where.append("request_id = %(request_id)s")
            params["request_id"] = filters.request_id
        if filters.event_type:
            where.append("event_type = %(event_type)s")
            params["event_type"] = filters.event_type
        if filters.service:
            where.append("service = %(service)s")
            params["service"] = filters.service
        if filters.since:
            where.append("occurred_at >= %(since)s")
            params["since"] = filters.since
        if filters.until:
            where.append("occurred_at <= %(until)s")
            params["until"] = filters.until
        if cursor is not None:
            cursor_ts, cursor_id = decode_cursor(cursor)
            where.append(
                "(occurred_at, event_id) < (%(cursor_ts)s, %(cursor_id)s)"
            )
            params["cursor_ts"] = cursor_ts
            params["cursor_id"] = cursor_id
        params["limit"] = limit + 1

        clause = f"WHERE {' AND '.join(where)}" if where else ""
        sql = (
            f"SELECT {_ROW_COLUMNS} FROM audit_events {clause} "
            "ORDER BY occurred_at DESC, event_id DESC LIMIT %(limit)s"
        )
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                rows = [dict(zip(_row_names(), row)) for row in await cur.fetchall()]
        events = [_row_to_event(row) for row in rows]
        page, rest = events[:limit], events[limit:]
        next_cursor = (
            encode_cursor(page[-1].occurred_at, page[-1].event_id)
            if page and rest
            else None
        )
        return AuditPage(events=page, next_cursor=next_cursor)

    async def count(self) -> int:
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT count(*) FROM audit_events")
                row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def evict(
        self, cutoff: datetime, max_events: int, batch_size: int
    ) -> int:
        evicted = 0
        batch = max(batch_size, 1)
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                # Window eviction, batched so a large backlog never becomes
                # one unbounded DELETE.
                while True:
                    await cur.execute(
                        "DELETE FROM audit_events WHERE event_id IN ("
                        "SELECT event_id FROM audit_events "
                        "WHERE occurred_at < %(cutoff)s LIMIT %(batch)s)",
                        {"cutoff": cutoff, "batch": batch},
                    )
                    deleted = max(cur.rowcount, 0)
                    evicted += deleted
                    if deleted < batch:
                        break
                # Enforce the hard cap by dropping the oldest excess,
                # likewise batched.
                while True:
                    await cur.execute(
                        "DELETE FROM audit_events WHERE event_id IN ("
                        "SELECT event_id FROM audit_events "
                        "ORDER BY occurred_at DESC, event_id DESC "
                        "OFFSET %(keep)s LIMIT %(batch)s)",
                        {"keep": max_events, "batch": batch},
                    )
                    deleted = max(cur.rowcount, 0)
                    evicted += deleted
                    if deleted < batch:
                        break
            await conn.commit()
        return evicted

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


def _row_names() -> tuple[str, ...]:
    return tuple(name.strip() for name in _ROW_COLUMNS.split(","))


# --- Factory ------------------------------------------------------------------


def build_audit_store(settings: AuditSettings) -> AuditStore:
    """Select the store backend from settings (default: in-memory)."""
    if settings.store_backend == "postgres":
        if not settings.db_url:
            raise StoreError(
                "AUDIT_DB_URL is required when AUDIT_STORE_BACKEND=postgres"
            )
        return PostgresAuditStore(settings.db_url)
    return InMemoryAuditStore()
