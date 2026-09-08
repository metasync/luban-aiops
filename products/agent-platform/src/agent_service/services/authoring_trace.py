"""Durable authoring traces for develop-as-you-go graduation (SPEC-055 R-1).

Captures, per chat session, the ordered sequence of approved mutating
steps as a *replay-oriented* trace: the arguments a graduated executable
flow will replay, plus references to the confirmation card that
authorized each step and the signed execution that ran it. It sits
beside — never inside — the SPEC-037 execution records, which store an
``args_digest`` hash rather than replayable arguments and are swept at
30 days; a session authored now must still be graduable after those
receipts are gone (ADR-0009).

Backends mirror the SPEC-017/025/031/037 posture: in-memory (code
default, dev/CI) and Postgres (deployed), selected by the same
``AGENT_STATE_STORE_BACKEND`` knob and sharing ``AGENT_STATE_DB_URL``
(the SPEC-016 ``sessions`` database). Every schema field exists on both
backends — a field on one only is silently dropped in production.

Retention is lifecycle-bound rather than time-swept with the receipts.
A trace stays ``draft`` while steps are still being captured and is
closed exactly once by graduation (``graduated``) or by an operator
dropping the candidate (``discarded``); both are terminal and are never
reopened or swept. Only ``draft`` traces idle beyond
``AGENT_AUTHORING_TRACE_IDLE_DAYS`` are reclaimed (OQ-1 — a fixed window
tied to the receipt sweep would reintroduce exactly the loss this store
exists to prevent). A per-session step cap
(``AGENT_AUTHORING_TRACE_MAX_STEPS``) bounds one session's trace, so an
unbounded session cannot grow an unbounded table.

Writes are best-effort-durable: a store failure degrades graduation
candidacy, never the chat stream, the signed request or the receipt.
"""

from __future__ import annotations

import copy
import logging
import os
import zlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, runtime_checkable

LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_STEPS = 100
DEFAULT_IDLE_DAYS = 180

# Lifecycle of one session's authoring trace: ``draft`` while steps are
# still being captured, closed exactly once by ``graduated`` or
# ``discarded``. A closed trace is the provenance of a published skill
# draft (or of a deliberately dropped candidate), so a later approval
# never appends to it and the idle-GC never reclaims it.
TRACE_DRAFT = "draft"
TRACE_TERMINAL_STATUSES = frozenset({"graduated", "discarded"})
TRACE_STATUSES = frozenset({TRACE_DRAFT}) | TRACE_TERMINAL_STATUSES

# Idle-GC bound per run, counted in *sessions* rather than rows so a run
# never leaves one session's trace half-reclaimed (a holed trace would
# graduate into an incomplete flow).
_SWEEP_SESSION_LIMIT = 50

# Namespace for the per-session advisory lock below. The two-argument lock
# form keys on ``(class, key)``, so this class keeps the authoring trace
# from ever sharing a lock with an unrelated single-key advisory user.
_ADVISORY_LOCK_CLASS = 5501


def make_trace_step(
    *,
    session_id: str,
    tool_name: str,
    args: dict[str, Any],
    captured_at: str,
    execution_id: str | None = None,
    confirm_id: str | None = None,
) -> dict[str, Any]:
    """Shape one authoring-trace step.

    ``args`` must already be secret-safe — credential values replaced by
    placeholders or credential-set references, never literals — because
    the store persists exactly what it is given and a trace outlives the
    receipts that would otherwise be the only copy. ``execution_id`` and
    ``confirm_id`` are *references*: the signed request, receipt and
    outcome stay in ``execution_records`` / ``confirmation_records``, so
    the trace never duplicates tamper evidence. ``position`` is assigned
    by the store — the per-session ordinal is what makes the trace
    replay-ordered, and only the store sees the whole sequence.
    """
    return {
        "session_id": session_id,
        "position": None,
        "tool_name": tool_name,
        "args": dict(args or {}),
        "execution_id": execution_id,
        "confirm_id": confirm_id,
        "status": TRACE_DRAFT,
        "captured_at": captured_at,
    }


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class AuthoringTraceStore(Protocol):
    """Public interface for authoring-trace backends."""

    @property
    def backend_name(self) -> str: ...

    def append_step(self, step: dict[str, Any]) -> bool: ...

    def load_for_session(self, session_id: str) -> list[dict[str, Any]]: ...

    def trace_status(self, session_id: str) -> str | None: ...

    def close_trace(self, session_id: str, status: str) -> bool: ...

    def sweep_idle(self, *, now: datetime | None = None) -> int: ...

    def delete_session(self, session_id: str) -> bool: ...

    def is_ready(self) -> bool: ...


# ---------------------------------------------------------------------------
# In-memory backend
# ---------------------------------------------------------------------------


class InMemoryAuthoringTraceStore:
    """In-memory authoring traces.

    Single-replica and non-persistent; suitable for development, CI, and
    as a fallback when Postgres is unreachable. A restart loses an
    in-flight trace, which degrades to "no graduation candidate" — the
    approved executions and their receipts are unaffected.
    """

    backend_name = "memory"

    def __init__(
        self,
        max_steps: int = DEFAULT_MAX_STEPS,
        idle_days: int = DEFAULT_IDLE_DAYS,
    ) -> None:
        self._max_steps = max_steps
        self._idle_days = idle_days
        self._by_session: dict[str, list[dict[str, Any]]] = {}

    def append_step(self, step: dict[str, Any]) -> bool:
        session_id = str(step["session_id"])
        rows = self._by_session.setdefault(session_id, [])
        if rows and rows[0]["status"] in TRACE_TERMINAL_STATUSES:
            LOGGER.debug(
                "authoring trace: session %s is %s, dropping step for %s",
                session_id,
                rows[0]["status"],
                step.get("tool_name"),
            )
            return False
        if len(rows) >= self._max_steps:
            LOGGER.debug(
                "authoring trace: session %s reached the %d-step cap, "
                "dropping step for %s",
                session_id,
                self._max_steps,
                step.get("tool_name"),
            )
            return False
        stored = dict(step)
        # Deep-copy the arguments: the seam that captures a step still holds
        # the parsed tool call, and a later mutation there must not retro-edit
        # the trace a graduation will replay.
        stored["args"] = copy.deepcopy(step.get("args") or {})
        stored["captured_at"] = _canonical_timestamp(step.get("captured_at"))
        stored["position"] = len(rows) + 1
        stored["status"] = TRACE_DRAFT
        rows.append(stored)
        return True

    def load_for_session(self, session_id: str) -> list[dict[str, Any]]:
        # Deep-copy on the way out too: Postgres re-decodes JSONB per load, so
        # a caller shaping a draft must not be able to mutate the stored
        # provenance on one backend only.
        return copy.deepcopy(self._by_session.get(session_id, []))

    def trace_status(self, session_id: str) -> str | None:
        rows = self._by_session.get(session_id) or []
        return str(rows[0]["status"]) if rows else None

    def close_trace(self, session_id: str, status: str) -> bool:
        if status not in TRACE_TERMINAL_STATUSES:
            raise ValueError(
                f"Unknown authoring-trace status: {status!r} "
                f"(expected one of: {', '.join(sorted(TRACE_TERMINAL_STATUSES))})"
            )
        rows = self._by_session.get(session_id) or []
        # The first close wins: a graduated trace is never re-discarded
        # and vice versa.
        if not rows or rows[0]["status"] != TRACE_DRAFT:
            return False
        for row in rows:
            row["status"] = status
        return True

    def sweep_idle(self, *, now: datetime | None = None) -> int:
        if self._idle_days <= 0:
            # 0 disables the idle-GC: a trace is the operator's work
            # product and is never reclaimed behind their back.
            return 0
        moment = now or datetime.now(timezone.utc)
        cutoff = moment - timedelta(days=self._idle_days)
        idle: list[str] = []
        for session_id, rows in self._by_session.items():
            if not rows or rows[0]["status"] != TRACE_DRAFT:
                continue
            # Idleness is a property of the *trace*, not of one step: an
            # old step in a session that was appended to yesterday stays.
            newest = _newest_captured_at(rows)
            if newest is None:
                # A trace with a step this store cannot date is never
                # reclaimed: the sweep must not delete what it cannot prove
                # is idle.
                continue
            if newest <= cutoff:
                idle.append(session_id)
        reclaimed = 0
        for session_id in idle[:_SWEEP_SESSION_LIMIT]:
            reclaimed += len(self._by_session.pop(session_id))
        if reclaimed:
            LOGGER.info(
                "authoring trace: reclaimed %d idle draft step(s)", reclaimed
            )
        return reclaimed

    def delete_session(self, session_id: str) -> bool:
        rows = self._by_session.pop(session_id, None)
        return bool(rows)

    def is_ready(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Postgres backend
# ---------------------------------------------------------------------------


_AUTHORING_TRACE_DDL = """
CREATE TABLE IF NOT EXISTS authoring_trace (
    session_id   TEXT NOT NULL,
    position     INTEGER NOT NULL,
    tool_name    TEXT NOT NULL,
    args         JSONB NOT NULL,
    execution_id TEXT,
    confirm_id   TEXT,
    status       TEXT NOT NULL DEFAULT 'draft',
    captured_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (session_id, position)
);
CREATE INDEX IF NOT EXISTS idx_authoring_trace_status_session
    ON authoring_trace (status, session_id, captured_at);
"""

# Appends one step, assigning the per-session ordinal and enforcing both
# bounds in the same statement:
#   - COUNT(*) < max_steps   — the per-session step cap drops the rest
#   - no non-draft row       — a closed trace is never reopened
# The cap is atomic on this statement alone: two concurrent appends both
# compute MAX+1, the primary key rejects the second, and ON CONFLICT DO
# NOTHING makes it a no-op rather than an error. The reopen guard is *not*
# — it reads the session's statuses in the same statement that writes the
# new row, so under READ COMMITTED a ``close_trace`` committing between
# that read and this insert would leave a trailing draft row behind the
# terminal ones. Callers therefore take ``_ADVISORY_LOCK`` for the session
# first, which serializes append against close.
# A racing append that still lands on a taken position is a no-op rather
# than an error: capture is best-effort and must not raise into the seam.
_INSERT_STEP = """
INSERT INTO authoring_trace (
    session_id, position, tool_name, args, execution_id, confirm_id,
    status, captured_at
)
SELECT %(session_id)s,
       COALESCE(MAX(position), 0) + 1,
       %(tool_name)s,
       %(args)s,
       %(execution_id)s,
       %(confirm_id)s,
       'draft',
       %(captured_at)s
  FROM authoring_trace
 WHERE session_id = %(session_id)s
HAVING COUNT(*) < %(max_steps)s
   AND COUNT(*) FILTER (WHERE status <> 'draft') = 0
ON CONFLICT (session_id, position) DO NOTHING
"""

_LOAD_FOR_SESSION = """
SELECT session_id, position, tool_name, args, execution_id, confirm_id,
       status, captured_at
  FROM authoring_trace
 WHERE session_id = %(session_id)s
 ORDER BY position ASC
"""

_TRACE_STATUS = """
SELECT status
  FROM authoring_trace
 WHERE session_id = %(session_id)s
 ORDER BY position ASC
 LIMIT 1
"""

# Closes exactly once: only a draft trace accepts a terminal status, so a
# replayed graduation or a racing discard is a no-op.
_CLOSE_TRACE = """
UPDATE authoring_trace
   SET status = %(status)s
 WHERE session_id = %(session_id)s
   AND status = 'draft'
"""

# Idle-GC (OQ-1): reclaim whole *draft* traces whose newest step is older
# than the window, bounded per run by session count. Terminal rows are
# excluded by the status predicate on both the outer delete and the
# grouping subquery, so a graduated or discarded trace is never swept.
_SWEEP_IDLE = """
DELETE FROM authoring_trace
 WHERE status = 'draft'
   AND session_id IN (
       SELECT session_id
         FROM authoring_trace
        WHERE status = 'draft'
        GROUP BY session_id
       HAVING MAX(captured_at) <= now() - make_interval(days => %(idle_days)s)
        LIMIT %(sweep_limit)s
   )
"""

_DELETE_SESSION = """
DELETE FROM authoring_trace
 WHERE session_id = %(session_id)s
RETURNING session_id
"""

# Transaction-scoped per-session lock: held until the commit that ends the
# operation, so an append and a close on one session cannot interleave.
# Uncontended it is a no-op round trip inside a transaction already open.
_ADVISORY_LOCK = """
SELECT pg_advisory_xact_lock(%(lock_class)s, %(lock_key)s)
"""

SyncConnectFactory = Callable[[], Iterator[Any]]


def _parse_timestamp(value: Any) -> datetime:
    """Normalize a stored ``captured_at`` to an aware UTC datetime."""
    if isinstance(value, datetime):
        stamp = value
    else:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    stamp = _parse_timestamp(value).astimezone(timezone.utc)
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_timestamp(value: Any) -> str:
    """Canonicalize a ``captured_at`` to second-precision UTC.

    The Postgres backend hands back a ``TIMESTAMPTZ`` that ``_iso`` renders
    as ``%Y-%m-%dT%H:%M:%SZ``, so the in-memory backend stores that same
    form on the way in: a caller must not see sub-second precision on one
    backend and none on the other. An unparsable stamp is kept verbatim
    rather than raising — capture is best-effort.
    """
    try:
        stamp = _parse_timestamp(value).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return str(value)
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def _newest_captured_at(rows: list[dict[str, Any]]) -> datetime | None:
    """Newest ``captured_at`` across a trace, or ``None`` if any is undatable.

    ``None`` means "cannot prove this trace is idle", which the sweep reads
    as "leave it alone" — an undatable row must not cost the session its
    trace, and must not raise out of a best-effort GC either.
    """
    newest: datetime | None = None
    for row in rows:
        try:
            stamp = _parse_timestamp(row.get("captured_at"))
        except (TypeError, ValueError):
            return None
        newest = stamp if newest is None else max(newest, stamp)
    return newest


def _advisory_lock_params(session_id: Any) -> dict[str, int]:
    """Lock parameters serializing one session's append against its close.

    ``crc32`` keeps the key inside the ``int4`` range the two-argument lock
    form takes; a collision only makes two unrelated sessions wait on each
    other, which is harmless for a best-effort trace.
    """
    return {
        "lock_class": _ADVISORY_LOCK_CLASS,
        "lock_key": zlib.crc32(str(session_id).encode("utf-8")) & 0x7FFFFFFF,
    }


def _row_to_step(row: Any) -> dict[str, Any]:
    (
        session_id,
        position,
        tool_name,
        args,
        execution_id,
        confirm_id,
        status,
        captured_at,
    ) = row
    return {
        "session_id": session_id,
        "position": position,
        "tool_name": tool_name,
        "args": args if isinstance(args, dict) else {},
        "execution_id": execution_id,
        "confirm_id": confirm_id,
        "status": status,
        "captured_at": _iso(captured_at),
    }


class PostgresAuthoringTraceStore:
    """Postgres-backed authoring traces (SPEC-055 R-1).

    Shares the SPEC-016 ``sessions`` database with the agent state, the
    confirmation records and the execution records. Connections are
    opened per operation and the ``connect`` factory is injectable so
    tests can substitute a fake driver. The table is created in place on
    first use — same migration posture as the confirmation and execution
    tables, so no separate DDL deploy step exists.
    """

    backend_name = "postgres"

    def __init__(
        self,
        db_url: str,
        connect: SyncConnectFactory | None = None,
        max_steps: int = DEFAULT_MAX_STEPS,
        idle_days: int = DEFAULT_IDLE_DAYS,
    ) -> None:
        self._db_url = db_url
        self._connect = connect or self._default_connect
        self._max_steps = max_steps
        self._idle_days = idle_days

    @contextmanager
    def _default_connect(self) -> Iterator[Any]:
        import psycopg

        conn = psycopg.connect(self._db_url, autocommit=False)
        try:
            yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        """Create the table and reclaim draft traces idle past the window."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_AUTHORING_TRACE_DDL)
                if self._idle_days > 0:
                    cur.execute(
                        _SWEEP_IDLE,
                        {
                            "idle_days": self._idle_days,
                            "sweep_limit": _SWEEP_SESSION_LIMIT,
                        },
                    )
            conn.commit()

    def append_step(self, step: dict[str, Any]) -> bool:
        from psycopg.types.json import Jsonb

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _ADVISORY_LOCK, _advisory_lock_params(step["session_id"])
                )
                cur.execute(
                    _INSERT_STEP,
                    {
                        "session_id": step["session_id"],
                        "tool_name": step["tool_name"],
                        "args": Jsonb(dict(step.get("args") or {})),
                        "execution_id": step.get("execution_id"),
                        "confirm_id": step.get("confirm_id"),
                        "captured_at": step["captured_at"],
                        "max_steps": self._max_steps,
                    },
                )
                inserted = int(getattr(cur, "rowcount", 0) or 0) > 0
                # Opportunistic idle-GC: the startup sweep alone would
                # never run on a long-lived replica.
                if self._idle_days > 0:
                    cur.execute(
                        _SWEEP_IDLE,
                        {
                            "idle_days": self._idle_days,
                            "sweep_limit": _SWEEP_SESSION_LIMIT,
                        },
                    )
            conn.commit()
        return inserted

    def load_for_session(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_LOAD_FOR_SESSION, {"session_id": session_id})
                rows = cur.fetchall()
            conn.commit()
        return [_row_to_step(row) for row in rows]

    def trace_status(self, session_id: str) -> str | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_TRACE_STATUS, {"session_id": session_id})
                row = cur.fetchone()
            conn.commit()
        return str(row[0]) if row is not None else None

    def close_trace(self, session_id: str, status: str) -> bool:
        if status not in TRACE_TERMINAL_STATUSES:
            raise ValueError(
                f"Unknown authoring-trace status: {status!r} "
                f"(expected one of: {', '.join(sorted(TRACE_TERMINAL_STATUSES))})"
            )
        with self._connect() as conn:
            with conn.cursor() as cur:
                # Same lock the append takes: a close must not land between
                # an append's status read and its insert.
                cur.execute(_ADVISORY_LOCK, _advisory_lock_params(session_id))
                cur.execute(
                    _CLOSE_TRACE,
                    {"session_id": session_id, "status": status},
                )
                closed = int(getattr(cur, "rowcount", 0) or 0) > 0
            conn.commit()
        return closed

    def sweep_idle(self, *, now: datetime | None = None) -> int:
        """Reclaim idle draft traces.

        Sweeps against the database clock (``now()``), same as the
        execution-record and confirmation-record sweeps; ``now`` is the
        in-memory backend's test seam and is deliberately unused here so
        the SQL stays idiomatic.
        """
        if self._idle_days <= 0:
            return 0
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _SWEEP_IDLE,
                    {
                        "idle_days": self._idle_days,
                        "sweep_limit": _SWEEP_SESSION_LIMIT,
                    },
                )
                reclaimed = int(getattr(cur, "rowcount", 0) or 0)
            conn.commit()
        return reclaimed

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


def _env_int(name: str, default: int, minimum: int) -> int:
    """Read an integer knob, degrading to the default on a bad value.

    The store is built at import time, so a typo in a deployment env must
    not take the service down — it falls back to the documented default
    with a warning. ``RuntimeSettings`` validates the same two knobs
    strictly for operators who read their configuration at startup.
    """
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        LOGGER.warning(
            "authoring trace store: %s=%r is not an integer, using %d",
            name,
            raw,
            default,
        )
        return default
    if value < minimum:
        LOGGER.warning(
            "authoring trace store: %s=%d is below the %d floor, using %d",
            name,
            value,
            minimum,
            default,
        )
        return default
    return value


def build_authoring_trace_store() -> AuthoringTraceStore:
    """Create the authoring-trace store from environment configuration.

    Reuses the SPEC-017/025 knobs (``AGENT_STATE_STORE_BACKEND`` /
    ``AGENT_STATE_DB_URL``) so the trace shares the state store's
    lifecycle and durability guarantees, and reads its own two bounds
    (``AGENT_AUTHORING_TRACE_MAX_STEPS`` /
    ``AGENT_AUTHORING_TRACE_IDLE_DAYS``) with the defaults
    ``RuntimeSettings`` registers. Backend failures fail open: the
    service stays usable on an in-memory store.
    """
    max_steps = _env_int(
        "AGENT_AUTHORING_TRACE_MAX_STEPS", DEFAULT_MAX_STEPS, 1
    )
    idle_days = _env_int(
        "AGENT_AUTHORING_TRACE_IDLE_DAYS", DEFAULT_IDLE_DAYS, 0
    )
    backend = os.getenv("AGENT_STATE_STORE_BACKEND", "memory")

    if backend == "memory":
        return InMemoryAuthoringTraceStore(
            max_steps=max_steps, idle_days=idle_days
        )

    if backend == "postgres":
        db_url = os.getenv("AGENT_STATE_DB_URL", "").strip()
        if not db_url:
            raise ValueError(
                "AGENT_STATE_STORE_BACKEND=postgres requires "
                "AGENT_STATE_DB_URL to be set"
            )
        try:
            store = PostgresAuthoringTraceStore(
                db_url=db_url, max_steps=max_steps, idle_days=idle_days
            )
            store.initialize()
            LOGGER.info("authoring trace store: Postgres backend initialized")
            return store
        except Exception as exc:
            LOGGER.warning(
                "authoring trace store: Postgres unavailable (%s), "
                "falling back to in-memory",
                exc,
            )
            return InMemoryAuthoringTraceStore(
                max_steps=max_steps, idle_days=idle_days
            )

    raise ValueError(
        f"Unknown AGENT_STATE_STORE_BACKEND: {backend!r} "
        "(expected 'memory' or 'postgres')"
    )


# Module-level singleton — imported by runtime_kernel.py at the capture
# seam (SPEC-055 R-2) and by the graduation endpoint (R-4).
AUTHORING_TRACE_STORE = build_authoring_trace_store()
