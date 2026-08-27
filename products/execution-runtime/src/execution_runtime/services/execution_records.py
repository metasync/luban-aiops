"""Worker-side execution record closing (SPEC-038 R-3).

The worker closes the ``execution_records`` rows that agent-platform
opened at resume: it writes the signed receipt once the gateway answers
(first write wins) and never opens rows itself. A close attempt on an
already-closed row is the late-arrival case — the existing receipt is
returned instead of being overwritten, so the resumed stream's timeout
close always survives a worker completion that lands afterwards.

Backends mirror the SPEC-017/025/031/037 posture: in-memory (code
default, dev/CI) and Postgres (deployed), selected by
``EXECUTION_STATE_STORE_BACKEND`` and sharing the sessions database via
``EXECUTION_STATE_DB_URL``. The Postgres backend reuses the same table
and in-place creation as the agent-platform copy; writes are
best-effort-durable — a store failure degrades audit completeness,
never the handoff response.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import timezone
from typing import Any, Protocol, runtime_checkable

from execution_runtime.core.config import ExecutionSettings

LOGGER = logging.getLogger(__name__)

RETENTION_WINDOW_DAYS = 30


def make_execution_record(request: dict[str, Any]) -> dict[str, Any]:
    """Shape the row for one signed request (parity with agent-platform)."""
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
    """Public interface for the worker's record-closing backends."""

    @property
    def backend_name(self) -> str: ...

    def close_execution(
        self,
        record: dict[str, Any],
        receipt: dict[str, Any],
        digest_match: bool,
    ) -> dict[str, Any] | None: ...

    def is_ready(self) -> bool: ...


# ---------------------------------------------------------------------------
# In-memory backend
# ---------------------------------------------------------------------------


class InMemoryExecutionRecordStore:
    """In-memory execution records.

    Single-replica and non-persistent; suitable for development, CI,
    and as a fallback when Postgres is unreachable. Rows the worker
    closes without a prior request write are opened on the spot so the
    close still lands (the durable deployment shares Postgres instead).
    """

    backend_name = "memory"

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], dict[str, Any]] = {}

    def close_execution(
        self,
        record: dict[str, Any],
        receipt: dict[str, Any],
        digest_match: bool,
    ) -> dict[str, Any] | None:
        key = (record["confirm_id"], record["call_id"])
        existing = self._by_key.get(key)
        if existing is None:
            row = dict(record)
            row["status"] = receipt["status"]
            row["digest_match"] = digest_match
            row["receipt"] = dict(receipt)
            row["completed_at"] = receipt["completed_at"]
            self._by_key[key] = row
            return None
        # The first close wins: a row that is no longer open keeps its
        # receipt and hands the existing one back (late arrival).
        if existing["status"] != "requested":
            return existing.get("receipt")
        existing["status"] = receipt["status"]
        existing["digest_match"] = digest_match
        existing["receipt"] = dict(receipt)
        existing["completed_at"] = receipt["completed_at"]
        return None

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

# The request row is normally opened by agent-platform at resume; the
# insert keeps the worker self-contained when it is not (crash window).
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
# result or a racing close leaves the existing receipt untouched.
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

_LOAD_RECEIPT = """
SELECT receipt
  FROM execution_records
 WHERE confirm_id = %(confirm_id)s
   AND call_id = %(call_id)s
"""

# Retention sweep (same shape as the agent-platform copy): reclaim rows
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


class PostgresExecutionRecordStore:
    """Postgres-backed execution record closing (SPEC-038 R-3).

    Shares the SPEC-016 ``sessions`` database — and the
    ``execution_records`` table — with agent-platform. Connections are
    opened per operation and the ``connect`` factory is injectable so
    tests can substitute a fake driver.
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

    def close_execution(
        self,
        record: dict[str, Any],
        receipt: dict[str, Any],
        digest_match: bool,
    ) -> dict[str, Any] | None:
        from psycopg.types.json import Jsonb

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
                    _SAVE_RECEIPT,
                    {
                        "confirm_id": record["confirm_id"],
                        "call_id": record["call_id"],
                        "status": receipt["status"],
                        "digest_match": digest_match,
                        "receipt": Jsonb(receipt),
                        "completed_at": receipt["completed_at"],
                    },
                )
                if cur.rowcount == 0:
                    # Late arrival: the row was already closed (timeout
                    # close from the resumed stream, or a replayed
                    # handoff). Hand the surviving receipt back.
                    cur.execute(
                        _LOAD_RECEIPT,
                        {
                            "confirm_id": record["confirm_id"],
                            "call_id": record["call_id"],
                        },
                    )
                    row = cur.fetchone()
                    conn.commit()
                    return row[0] if row else None
                cur.execute(
                    _SWEEP_EXPIRED,
                    {
                        "retention_days": RETENTION_WINDOW_DAYS,
                        "sweep_limit": _SWEEP_LIMIT,
                    },
                )
            conn.commit()
        return None

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


def build_execution_record_store(
    settings: ExecutionSettings,
) -> ExecutionRecordStore:
    """Create the execution record store from worker settings.

    Backend failures fail open: the service stays usable on an
    in-memory store (same posture as the agent-platform copy).
    """
    if settings.state_store_backend == "memory":
        return InMemoryExecutionRecordStore()

    try:
        store = PostgresExecutionRecordStore(db_url=settings.state_db_url)
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


def iso_utc(value: Any) -> str | None:
    """Normalize a timestamptz column to the envelope's ISO-Z shape."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    stamp = value.astimezone(timezone.utc) if value.tzinfo else value.replace(
        tzinfo=timezone.utc
    )
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")
