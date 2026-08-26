"""Durable execution records for signed execution requests (SPEC-037 R-4).

Persists the request/receipt lifecycle of every approved mutating tool
call beside the SPEC-031 confirmation records: the signed request lands
at resume (one row per parked call, keyed by ``confirm_id`` +
``call_id``), the signed receipt closes it after the tool result, and a
rejection at the invocation boundary marks the row without a receipt.

Backends mirror the SPEC-017/025/031 posture: in-memory (code default,
dev/CI) and Postgres (deployed), selected by the same
``AGENT_STATE_STORE_BACKEND`` knob and sharing ``AGENT_STATE_DB_URL``.

Rows are retention-bounded by a ``RETENTION_WINDOW_DAYS`` time window:
expired rows are swept at startup and opportunistically on writes, same
shape as the confirmation records' sweep. Writes are best-effort-durable
— a store failure degrades audit completeness, never the chat stream
(same posture as the SPEC-031 claim-time writes).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import timezone
from typing import Any, Protocol, runtime_checkable

LOGGER = logging.getLogger(__name__)

RETENTION_WINDOW_DAYS = 30

# Lifecycle of one signed execution: ``requested`` at resume, closed by a
# receipt (``succeeded`` / ``failed`` / ``timeout``) or by an invocation
# boundary rejection (``rejected`` — no receipt, the call never ran).
EXECUTION_STATUSES = frozenset(
    {"requested", "succeeded", "failed", "timeout", "rejected"}
)


def make_execution_record(request: dict[str, Any]) -> dict[str, Any]:
    """Shape the row written when a signed request is persisted.

    The signed request envelope itself is not stored — its fields that
    matter for the session surface (execution id, tool, timestamps) ride
    the row; tamper evidence lives in the audit trail and the receipt.
    """
    return {
        "confirm_id": request["confirm_id"],
        "call_id": request["call_id"],
        "session_id": request["session_id"],
        "execution_id": request["execution_id"],
        "tool_name": request["tool_name"],
        "requested_at": request["requested_at"],
        "status": "requested",
        "digest_match": None,
        "reject_reason": None,
        "receipt": None,
        "completed_at": None,
    }


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ExecutionRecordStore(Protocol):
    """Public interface for execution record backends."""

    @property
    def backend_name(self) -> str: ...

    def save_request(self, record: dict[str, Any]) -> None: ...

    def save_receipt(
        self,
        confirm_id: str,
        call_id: str,
        receipt: dict[str, Any],
        digest_match: bool,
    ) -> None: ...

    def mark_rejected(
        self,
        confirm_id: str,
        call_id: str,
        reason: str,
        digest_match: bool | None,
    ) -> None: ...

    def load_for_session(self, session_id: str) -> list[dict[str, Any]]: ...

    def delete_session(self, session_id: str) -> bool: ...

    def is_ready(self) -> bool: ...


# ---------------------------------------------------------------------------
# In-memory backend
# ---------------------------------------------------------------------------


class InMemoryExecutionRecordStore:
    """In-memory execution records.

    Single-replica and non-persistent; suitable for development, CI,
    and as a fallback when Postgres is unreachable.
    """

    backend_name = "memory"

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], dict[str, Any]] = {}

    def save_request(self, record: dict[str, Any]) -> None:
        key = (record["confirm_id"], record["call_id"])
        # A request persists exactly once; a replayed resume never
        # overwrites the original row.
        if key in self._by_key:
            return
        self._by_key[key] = dict(record)

    def save_receipt(
        self,
        confirm_id: str,
        call_id: str,
        receipt: dict[str, Any],
        digest_match: bool,
    ) -> None:
        record = self._by_key.get((confirm_id, call_id))
        if record is None:
            return
        # The first close wins: a receipt lands once, on a row that is
        # still open.
        if record["status"] != "requested":
            return
        record["status"] = receipt["status"]
        record["digest_match"] = digest_match
        record["receipt"] = dict(receipt)
        record["completed_at"] = receipt["completed_at"]

    def mark_rejected(
        self,
        confirm_id: str,
        call_id: str,
        reason: str,
        digest_match: bool | None,
    ) -> None:
        record = self._by_key.get((confirm_id, call_id))
        if record is None or record["status"] != "requested":
            return
        record["status"] = "rejected"
        record["reject_reason"] = reason
        record["digest_match"] = digest_match

    def load_for_session(self, session_id: str) -> list[dict[str, Any]]:
        rows = [
            dict(record)
            for record in self._by_key.values()
            if record["session_id"] == session_id
        ]
        rows.sort(key=lambda record: (record["requested_at"], record["call_id"]))
        return rows

    def delete_session(self, session_id: str) -> bool:
        doomed = [
            key
            for key, record in self._by_key.items()
            if record["session_id"] == session_id
        ]
        for key in doomed:
            del self._by_key[key]
        return bool(doomed)

    def is_ready(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Postgres backend
# ---------------------------------------------------------------------------


_EXECUTION_RECORDS_DDL = """
CREATE TABLE IF NOT EXISTS execution_records (
    confirm_id    TEXT NOT NULL,
    call_id       TEXT NOT NULL,
    session_id    TEXT NOT NULL,
    execution_id  TEXT NOT NULL,
    tool_name     TEXT NOT NULL,
    requested_at  TIMESTAMPTZ NOT NULL,
    status        TEXT NOT NULL,
    digest_match  BOOLEAN,
    reject_reason TEXT,
    receipt       JSONB,
    completed_at  TIMESTAMPTZ,
    PRIMARY KEY (confirm_id, call_id)
);
CREATE INDEX IF NOT EXISTS idx_execution_records_session
    ON execution_records (session_id, requested_at);
"""

_INSERT_REQUEST = """
INSERT INTO execution_records (
    confirm_id, call_id, session_id, execution_id, tool_name,
    requested_at, status
)
VALUES (
    %(confirm_id)s, %(call_id)s, %(session_id)s, %(execution_id)s,
    %(tool_name)s, %(requested_at)s, 'requested'
)
ON CONFLICT (confirm_id, call_id) DO NOTHING
"""

# Closes exactly once: only an open row accepts a receipt; a replayed
# result or a racing close is a no-op.
_SAVE_RECEIPT = """
UPDATE execution_records
   SET status = %(status)s,
       digest_match = %(digest_match)s,
       receipt = %(receipt)s,
       completed_at = %(completed_at)s
 WHERE confirm_id = %(confirm_id)s
   AND call_id = %(call_id)s
   AND status = 'requested'
"""

_MARK_REJECTED = """
UPDATE execution_records
   SET status = 'rejected',
       reject_reason = %(reject_reason)s,
       digest_match = %(digest_match)s
 WHERE confirm_id = %(confirm_id)s
   AND call_id = %(call_id)s
   AND status = 'requested'
"""

_LOAD_FOR_SESSION = """
SELECT confirm_id, call_id, session_id, execution_id, tool_name,
       requested_at, status, digest_match, reject_reason, receipt,
       completed_at
  FROM execution_records
 WHERE session_id = %(session_id)s
 ORDER BY requested_at ASC, call_id ASC
"""

_DELETE_SESSION = """
DELETE FROM execution_records
 WHERE session_id = %(session_id)s
RETURNING confirm_id
"""

# Retention sweep (same shape as the confirmation records): reclaim rows
# older than the window, bounded per run; runs at startup and rides writes.
_SWEEP_EXPIRED = """
DELETE FROM execution_records
 WHERE ctid IN (
     SELECT ctid FROM execution_records
      WHERE requested_at <= now() - make_interval(days => %(retention_days)s)
      LIMIT %(sweep_limit)s
 )
"""

_SWEEP_LIMIT = 100

SyncConnectFactory = Callable[[], Iterator[Any]]


def _row_to_record(row: Any) -> dict[str, Any]:
    (
        confirm_id,
        call_id,
        session_id,
        execution_id,
        tool_name,
        requested_at,
        status,
        digest_match,
        reject_reason,
        receipt,
        completed_at,
    ) = row
    return {
        "confirm_id": confirm_id,
        "call_id": call_id,
        "session_id": session_id,
        "execution_id": execution_id,
        "tool_name": tool_name,
        "requested_at": _iso(requested_at),
        "status": status,
        "digest_match": digest_match,
        "reject_reason": reject_reason,
        "receipt": receipt,
        "completed_at": _iso(completed_at),
    }


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    stamp = value.astimezone(timezone.utc) if value.tzinfo else value.replace(
        tzinfo=timezone.utc
    )
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


class PostgresExecutionRecordStore:
    """Postgres-backed execution records (SPEC-037 R-4).

    Shares the SPEC-016 ``sessions`` database with the agent state and
    confirmation records. Connections are opened per operation and the
    ``connect`` factory is injectable so tests can substitute a fake
    driver. The table is created in place on first use — same migration
    posture as the confirmation table.
    """

    backend_name = "postgres"

    def __init__(
        self,
        db_url: str,
        connect: SyncConnectFactory | None = None,
    ) -> None:
        self._db_url = db_url
        self._connect = connect or self._default_connect

    @contextmanager
    def _default_connect(self) -> Iterator[Any]:
        import psycopg

        conn = psycopg.connect(self._db_url, autocommit=False)
        try:
            yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        """Create the table and sweep rows past the retention window."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_EXECUTION_RECORDS_DDL)
                cur.execute(
                    _SWEEP_EXPIRED,
                    {
                        "retention_days": RETENTION_WINDOW_DAYS,
                        "sweep_limit": _SWEEP_LIMIT,
                    },
                )
            conn.commit()

    def save_request(self, record: dict[str, Any]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _INSERT_REQUEST,
                    {
                        "confirm_id": record["confirm_id"],
                        "call_id": record["call_id"],
                        "session_id": record["session_id"],
                        "execution_id": record["execution_id"],
                        "tool_name": record["tool_name"],
                        "requested_at": record["requested_at"],
                    },
                )
                cur.execute(
                    _SWEEP_EXPIRED,
                    {
                        "retention_days": RETENTION_WINDOW_DAYS,
                        "sweep_limit": _SWEEP_LIMIT,
                    },
                )
            conn.commit()

    def save_receipt(
        self,
        confirm_id: str,
        call_id: str,
        receipt: dict[str, Any],
        digest_match: bool,
    ) -> None:
        from psycopg.types.json import Jsonb

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _SAVE_RECEIPT,
                    {
                        "confirm_id": confirm_id,
                        "call_id": call_id,
                        "status": receipt["status"],
                        "digest_match": digest_match,
                        "receipt": Jsonb(receipt),
                        "completed_at": receipt["completed_at"],
                    },
                )
            conn.commit()

    def mark_rejected(
        self,
        confirm_id: str,
        call_id: str,
        reason: str,
        digest_match: bool | None,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _MARK_REJECTED,
                    {
                        "confirm_id": confirm_id,
                        "call_id": call_id,
                        "reject_reason": reason,
                        "digest_match": digest_match,
                    },
                )
            conn.commit()

    def load_for_session(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_LOAD_FOR_SESSION, {"session_id": session_id})
                rows = cur.fetchall()
            conn.commit()
        return [_row_to_record(row) for row in rows]

    def delete_session(self, session_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_DELETE_SESSION, {"session_id": session_id})
                rows = cur.fetchall()
            conn.commit()
        return bool(rows)

    def is_ready(self) -> bool:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return cur.fetchone() is not None
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_execution_record_store() -> ExecutionRecordStore:
    """Create the execution record store from environment configuration.

    Reuses the SPEC-017/025 knobs (``AGENT_STATE_STORE_BACKEND`` /
    ``AGENT_STATE_DB_URL``) so execution records share the state store's
    lifecycle and durability guarantees. Backend failures fail open: the
    service stays usable on an in-memory store.
    """
    backend = os.getenv("AGENT_STATE_STORE_BACKEND", "memory")

    if backend == "memory":
        return InMemoryExecutionRecordStore()

    if backend == "postgres":
        db_url = os.getenv("AGENT_STATE_DB_URL", "").strip()
        if not db_url:
            raise ValueError(
                "AGENT_STATE_STORE_BACKEND=postgres requires "
                "AGENT_STATE_DB_URL to be set"
            )
        try:
            store = PostgresExecutionRecordStore(db_url=db_url)
            store.initialize()
            LOGGER.info("execution record store: Postgres backend initialized")
            return store
        except Exception as exc:
            LOGGER.warning(
                "execution record store: Postgres unavailable (%s), "
                "falling back to in-memory",
                exc,
            )
            return InMemoryExecutionRecordStore()

    raise ValueError(
        f"Unknown AGENT_STATE_STORE_BACKEND: {backend!r} "
        "(expected 'memory' or 'postgres')"
    )


# Module-level singleton — imported by runtime_kernel.py and the v2 routes.
EXECUTION_RECORD_STORE = build_execution_record_store()
