"""Durable confirmation lifecycle records (SPEC-031 R-1).

Persists every parked kernel confirmation and its resolution so the
owner's transcript cards and the approver inbox survive re-login, pod
restarts, and replica boundaries. The in-memory
``ConfirmationRegistry`` stays the hot path for the single-flight
claim/resume machinery; this store is the source of truth for history
and restart recovery — the two never disagree on a resolved outcome.

Backends mirror the SPEC-017/025 posture: in-memory (code default,
dev/CI) and Postgres (deployed), selected by the same
``AGENT_STATE_STORE_BACKEND`` knob and sharing ``AGENT_STATE_DB_URL``.

Records are bounded (most recent ``PER_SESSION_CAP`` per session,
oldest evicted first) and live and die with their session. Inbox
history is bounded by a ``HISTORY_WINDOW_DAYS`` time window; resolved
rows older than the window are swept opportunistically on writes.

At startup the Postgres backend flips ``pending`` rows that already
exceeded the HITL confirmation TTL to ``expired``: a parked kernel reply
never survives its process (SPEC-020 posture) and a park past its TTL
answers no confirmation on any replica, so closing those rows is safe
across replicas; younger rows stay untouched so a live replica's park is
never expired by a sibling's startup. After a restart the record stays
visible — surfaced as an expired card rather than vanishing — but can
never be resumed. Failures never fail a turn: callers persist
best-effort and degrade to live-only cards.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, runtime_checkable

LOGGER = logging.getLogger(__name__)

PER_SESSION_CAP = 50
HISTORY_WINDOW_DAYS = 30
INBOX_LIMIT = 100

CONFIRMATION_STATUSES = frozenset({"pending", "approved", "denied", "expired"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_record(
    confirm_id: str,
    session_id: str,
    owner_user_id: str,
    pending_calls: list[dict[str, Any]],
    action: str | None,
    turn_index: int | None = None,
) -> dict[str, Any]:
    """Shape the parked record written before the request frame flows."""
    return {
        "confirm_id": confirm_id,
        "session_id": session_id,
        "owner_user_id": owner_user_id,
        "pending_calls": list(pending_calls),
        "action": action,
        # SPEC-033 R-1: the parking turn ordinal (same convention as
        # SPEC-025 evidence turn_index) so seeded cards anchor under the
        # exchange that parked them. None for pre-spec records.
        "turn_index": turn_index,
        "status": "pending",
        "parked_at": _utc_now_iso(),
        "decider_user_id": None,
        "decision": None,
        "decided_at": None,
    }


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ConfirmationRecordStore(Protocol):
    """Public interface for confirmation record backends."""

    @property
    def backend_name(self) -> str: ...

    def save_parked(self, record: dict[str, Any]) -> None: ...

    def mark_resolved(
        self,
        session_id: str,
        confirm_id: str,
        status: str,
        decider_user_id: str | None,
        decision: str | None,
    ) -> None: ...

    def load_for_session(self, session_id: str) -> list[dict[str, Any]]: ...

    def load_record(
        self, session_id: str, confirm_id: str
    ) -> dict[str, Any] | None: ...

    def load_pending_for_session(self, session_id: str) -> dict[str, Any] | None: ...

    def load_inbox(self) -> list[dict[str, Any]]: ...

    def delete_session(self, session_id: str) -> bool: ...

    def is_ready(self) -> bool: ...


# ---------------------------------------------------------------------------
# In-memory backend
# ---------------------------------------------------------------------------


class InMemoryConfirmationRecordStore:
    """In-memory confirmation records.

    Single-replica and non-persistent; suitable for development, CI, and
    as a fallback when Postgres is unreachable.
    """

    backend_name = "memory"

    def __init__(self) -> None:
        self._by_confirm_id: dict[str, dict[str, Any]] = {}

    def save_parked(self, record: dict[str, Any]) -> None:
        self._by_confirm_id[record["confirm_id"]] = dict(record)
        self._evict_over_cap(record["session_id"])

    def mark_resolved(
        self,
        session_id: str,
        confirm_id: str,
        status: str,
        decider_user_id: str | None,
        decision: str | None,
    ) -> None:
        record = self._by_confirm_id.get(confirm_id)
        if record is None or record["session_id"] != session_id:
            return
        # A confirmation resolves exactly once (SPEC-031 R-4): the
        # claim-time write owns the outcome, later writes are no-ops.
        if record["status"] != "pending":
            return
        record["status"] = status
        record["decider_user_id"] = decider_user_id
        record["decision"] = decision
        record["decided_at"] = _utc_now_iso()

    def load_for_session(self, session_id: str) -> list[dict[str, Any]]:
        rows = [
            dict(record)
            for record in self._by_confirm_id.values()
            if record["session_id"] == session_id
        ]
        rows.sort(key=lambda record: record["parked_at"])
        return rows

    def load_record(
        self, session_id: str, confirm_id: str
    ) -> dict[str, Any] | None:
        record = self._by_confirm_id.get(confirm_id)
        if record is None or record["session_id"] != session_id:
            return None
        return dict(record)

    def load_pending_for_session(self, session_id: str) -> dict[str, Any] | None:
        rows = self.load_for_session(session_id)
        for record in reversed(rows):
            if record["status"] == "pending":
                return record
        return None

    def load_inbox(self) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=HISTORY_WINDOW_DAYS)
        rows = []
        for record in self._by_confirm_id.values():
            if record["status"] != "pending":
                decided = record.get("decided_at") or ""
                try:
                    stamp = datetime.fromisoformat(
                        decided.replace("Z", "+00:00")
                    )
                except ValueError:
                    continue
                if stamp < cutoff:
                    continue
            rows.append(dict(record))
        rows.sort(key=lambda record: record["parked_at"], reverse=True)
        return rows[:INBOX_LIMIT]

    def delete_session(self, session_id: str) -> bool:
        doomed = [
            confirm_id
            for confirm_id, record in self._by_confirm_id.items()
            if record["session_id"] == session_id
        ]
        for confirm_id in doomed:
            del self._by_confirm_id[confirm_id]
        return bool(doomed)

    def is_ready(self) -> bool:
        return True

    def _evict_over_cap(self, session_id: str) -> None:
        rows = self.load_for_session(session_id)
        if len(rows) <= PER_SESSION_CAP:
            return
        for record in rows[: len(rows) - PER_SESSION_CAP]:
            self._by_confirm_id.pop(record["confirm_id"], None)


# ---------------------------------------------------------------------------
# Postgres backend
# ---------------------------------------------------------------------------


_CONFIRMATION_RECORDS_DDL = """
CREATE TABLE IF NOT EXISTS confirmation_records (
    confirm_id      TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL,
    owner_user_id   TEXT NOT NULL,
    pending_calls   JSONB NOT NULL,
    action          TEXT,
    status          TEXT NOT NULL,
    parked_at       TIMESTAMPTZ NOT NULL,
    decider_user_id TEXT,
    decision        TEXT,
    decided_at      TIMESTAMPTZ,
    turn_index      INTEGER
);
CREATE INDEX IF NOT EXISTS idx_confirmation_records_session
    ON confirmation_records (session_id, parked_at);
CREATE INDEX IF NOT EXISTS idx_confirmation_records_status
    ON confirmation_records (status, parked_at);
"""

# SPEC-033 R-1: clusters whose table predates the turn-anchoring column
# migrate in place at startup; pre-spec rows stay NULL and keep the
# legacy newest-turn anchoring.
_ADD_TURN_INDEX_COLUMN = """
ALTER TABLE confirmation_records
    ADD COLUMN IF NOT EXISTS turn_index INTEGER
"""

_INSERT_PARKED = """
INSERT INTO confirmation_records (
    confirm_id, session_id, owner_user_id, pending_calls, action,
    status, parked_at, turn_index
)
VALUES (
    %(confirm_id)s, %(session_id)s, %(owner_user_id)s, %(pending_calls)s,
    %(action)s, 'pending', now(), %(turn_index)s
)
ON CONFLICT (confirm_id) DO NOTHING
"""

_EVICT_OVER_CAP = """
DELETE FROM confirmation_records
 WHERE ctid IN (
     SELECT ctid FROM confirmation_records
      WHERE session_id = %(session_id)s
      ORDER BY parked_at DESC
      OFFSET %(cap)s
 )
"""

# Resolves exactly once (SPEC-031 R-4): the claim-time write owns the
# outcome; a later write (the resume's safety-net write, a racing expiry)
# finds no pending row and becomes a no-op.
_MARK_RESOLVED = """
UPDATE confirmation_records
   SET status = %(status)s,
       decider_user_id = %(decider_user_id)s,
       decision = %(decision)s,
       decided_at = now()
 WHERE session_id = %(session_id)s
   AND confirm_id = %(confirm_id)s
   AND status = 'pending'
"""

_LOAD_FOR_SESSION = """
SELECT confirm_id, session_id, owner_user_id, pending_calls, action,
       status, parked_at, decider_user_id, decision, decided_at,
       turn_index
  FROM confirmation_records
 WHERE session_id = %(session_id)s
 ORDER BY parked_at ASC
"""

_LOAD_RECORD = """
SELECT confirm_id, session_id, owner_user_id, pending_calls, action,
       status, parked_at, decider_user_id, decision, decided_at,
       turn_index
  FROM confirmation_records
 WHERE session_id = %(session_id)s
   AND confirm_id = %(confirm_id)s
"""

_LOAD_PENDING_FOR_SESSION = """
SELECT confirm_id, session_id, owner_user_id, pending_calls, action,
       status, parked_at, decider_user_id, decision, decided_at,
       turn_index
  FROM confirmation_records
 WHERE session_id = %(session_id)s
   AND status = 'pending'
 ORDER BY parked_at DESC
 LIMIT 1
"""

_LOAD_INBOX = """
SELECT confirm_id, session_id, owner_user_id, pending_calls, action,
       status, parked_at, decider_user_id, decision, decided_at,
       turn_index
  FROM confirmation_records
 WHERE status = 'pending'
    OR decided_at >= now() - make_interval(days => %(history_days)s)
 ORDER BY parked_at DESC
 LIMIT %(limit)s
"""

_DELETE_SESSION = """
DELETE FROM confirmation_records
 WHERE session_id = %(session_id)s
RETURNING confirm_id
"""

# Bounded opportunistic sweep (SPEC-017 state-store pattern): reclaim
# resolved rows beyond the inbox history window; piggybacks on writes.
_SWEEP_OLD_RESOLVED = """
DELETE FROM confirmation_records
 WHERE ctid IN (
     SELECT ctid FROM confirmation_records
      WHERE status <> 'pending'
        AND decided_at <= now() - make_interval(days => %(history_days)s)
      LIMIT %(sweep_limit)s
 )
"""

# Startup sweep (SPEC-031): close pending rows that already exceeded the
# HITL confirmation TTL — such a park answers no confirmation on any
# replica (claim raises ConfirmationExpired), so expiring it here is safe
# across replicas. Younger rows stay pending: on a live replica they are
# still answerable, and a single replica's own orphaned parks age past
# the TTL before a later sweep closes them.
_CLOSE_STALE_PENDING = """
UPDATE confirmation_records
   SET status = 'expired', decided_at = now()
 WHERE status = 'pending'
   AND parked_at <= now() - make_interval(secs => %(stale_after_seconds)s)
"""

_SWEEP_LIMIT = 100

SyncConnectFactory = Callable[[], Iterator[Any]]


def _row_to_record(row: Any) -> dict[str, Any]:
    (
        confirm_id,
        session_id,
        owner_user_id,
        pending_calls,
        action,
        status,
        parked_at,
        decider_user_id,
        decision,
        decided_at,
        turn_index,
    ) = row
    return {
        "confirm_id": confirm_id,
        "session_id": session_id,
        "owner_user_id": owner_user_id,
        "pending_calls": pending_calls or [],
        "action": action,
        "status": status,
        "parked_at": _iso(parked_at),
        "decider_user_id": decider_user_id,
        "decision": decision,
        "decided_at": _iso(decided_at),
        "turn_index": turn_index,
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


class PostgresConfirmationRecordStore:
    """Postgres-backed confirmation records (SPEC-031 R-1).

    Shares the SPEC-016 ``sessions`` database — one database for
    platform-owned agent session state. Connections are opened per
    operation and the ``connect`` factory is injectable so tests can
    substitute a fake driver.
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

    def initialize(self, stale_after_seconds: float = 0.0) -> None:
        """Create the table and close pending rows that can no longer answer.

        ``stale_after_seconds`` is the HITL confirmation TTL: only rows
        parked longer ago than that are closed (they answer no
        confirmation on any replica, live or restarted). ``0`` closes
        every pending row — correct when bridging is disabled, since no
        live park can exist anywhere.
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_CONFIRMATION_RECORDS_DDL)
                cur.execute(_ADD_TURN_INDEX_COLUMN)
                cur.execute(
                    _CLOSE_STALE_PENDING,
                    {"stale_after_seconds": max(stale_after_seconds, 0)},
                )
            conn.commit()

    def save_parked(self, record: dict[str, Any]) -> None:
        from psycopg.types.json import Jsonb

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _INSERT_PARKED,
                    {
                        "confirm_id": record["confirm_id"],
                        "session_id": record["session_id"],
                        "owner_user_id": record["owner_user_id"],
                        "pending_calls": Jsonb(record["pending_calls"]),
                        "action": record["action"],
                        "turn_index": record.get("turn_index"),
                    },
                )
                cur.execute(
                    _EVICT_OVER_CAP,
                    {"session_id": record["session_id"], "cap": PER_SESSION_CAP},
                )
                cur.execute(
                    _SWEEP_OLD_RESOLVED,
                    {
                        "history_days": HISTORY_WINDOW_DAYS,
                        "sweep_limit": _SWEEP_LIMIT,
                    },
                )
            conn.commit()

    def mark_resolved(
        self,
        session_id: str,
        confirm_id: str,
        status: str,
        decider_user_id: str | None,
        decision: str | None,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _MARK_RESOLVED,
                    {
                        "session_id": session_id,
                        "confirm_id": confirm_id,
                        "status": status,
                        "decider_user_id": decider_user_id,
                        "decision": decision,
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

    def load_record(
        self, session_id: str, confirm_id: str
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _LOAD_RECORD,
                    {"session_id": session_id, "confirm_id": confirm_id},
                )
                row = cur.fetchone()
            conn.commit()
        return _row_to_record(row) if row is not None else None

    def load_pending_for_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _LOAD_PENDING_FOR_SESSION, {"session_id": session_id}
                )
                row = cur.fetchone()
            conn.commit()
        return _row_to_record(row) if row is not None else None

    def load_inbox(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _LOAD_INBOX,
                    {"history_days": HISTORY_WINDOW_DAYS, "limit": INBOX_LIMIT},
                )
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


def build_confirmation_record_store() -> ConfirmationRecordStore:
    """Create the confirmation record store from environment configuration.

    Reuses the SPEC-017/025 knobs (``AGENT_STATE_STORE_BACKEND`` /
    ``AGENT_STATE_DB_URL``) so the records share the state store's
    lifecycle and durability guarantees. Backend failures fail open: the
    service stays usable on an in-memory store.
    """
    backend = os.getenv("AGENT_STATE_STORE_BACKEND", "memory")

    if backend == "memory":
        return InMemoryConfirmationRecordStore()

    if backend == "postgres":
        db_url = os.getenv("AGENT_STATE_DB_URL", "").strip()
        if not db_url:
            raise ValueError(
                "AGENT_STATE_STORE_BACKEND=postgres requires "
                "AGENT_STATE_DB_URL to be set"
            )
        try:
            store = PostgresConfirmationRecordStore(db_url=db_url)
            # Startup sweep scope mirrors the registry TTL: a park past
            # its confirmation timeout answers nothing on any replica.
            try:
                stale_after_seconds = max(
                    int(os.getenv("AGENT_HITL_CONFIRM_TIMEOUT", "600")), 0
                )
            except ValueError:
                stale_after_seconds = 600
            store.initialize(stale_after_seconds=stale_after_seconds)
            LOGGER.info(
                "confirmation record store: Postgres backend initialized"
            )
            return store
        except Exception as exc:
            LOGGER.warning(
                "confirmation record store: Postgres unavailable (%s), "
                "falling back to in-memory",
                exc,
            )
            return InMemoryConfirmationRecordStore()

    raise ValueError(
        f"Unknown AGENT_STATE_STORE_BACKEND: {backend!r} "
        "(expected 'memory' or 'postgres')"
    )


# Module-level singleton — imported by runtime_kernel.py and the v2 routes.
CONFIRMATION_RECORD_STORE = build_confirmation_record_store()
