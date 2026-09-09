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

A trace also carries the **target** the session acted on, in two forms
(SPEC-055 R-4). ``authoring_trace_target`` holds the target an operator
declared when opening a skill-development session — up front, before any
mutation, so it is an authorization *scope* rather than a post-hoc claim
about the past — and ``skill_target_scope`` reduces it to the origin and
path a replay is actually bound by. ``flow_origin`` on each step holds the
origin the tool-gateway reported the interaction landed on (``data["url"]``
on a successful browser write), recorded after the fact from the receipt
seam. Graduation reads both: the declaration names the draft's
``web_target`` — the security parameter a replayed flow binds to — and
the per-step observations prove every captured mutation landed on it, so
"every target/origin allowlisted" is a check the platform can substantiate
rather than assert. Neither is derivable from the steps alone: R-2's tier
gate captures write-tier calls, whose arguments are selectors and values,
and the ``web.navigate`` that carries a URL is read-tier and never enters
a trace.

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
from urllib.parse import urlparse, urlunparse

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


def origin_of_url(url: Any) -> str | None:
    """Normalize a URL to its ``scheme://host[:port]`` origin, or ``None``.

    A deliberate twin of the tool-gateway's ``origin_of``
    (``tools/browser_connector.py``) — products never import each other, so
    the normalization is copied. Unlike the secret vocabularies this is not
    a security *list* but a pure derivation from ``urlparse``, and the two
    must agree because graduation compares a declared target normalized
    here against origins the gateway normalized there: a divergence would
    make a coherent trace look like a drift. ``test_origin_of_url`` pins the
    shapes both sides rely on.

    ``None`` means "not an absolute http(s) URL", which callers read as
    "no origin recorded" rather than as an error — capture is best-effort.
    """
    try:
        parsed = urlparse(str(url or ""))
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}".lower()


def skill_target_scope(url: str) -> str:
    """Reduce a declared target to the part a replayed flow is actually bound by.

    ``bind_flow`` (``tools/browser_connector.py``) holds an interaction to a
    skill's ``web_target`` on two axes — origin equality *and*
    ``_path_under(url_path, target_path)`` — and never reads the query. So
    origin and path are the scope an operator is declaring, and everything
    else is dropped here rather than stored.

    The **query and fragment** go because they are inert at replay, so
    persisting one would advertise a narrowing that does not exist — and a
    target pasted from a browser address bar routinely carries a session token
    or an API key in its query, which would otherwise be written verbatim into
    a store that outlives every execution receipt (ADR-0009) and into the
    ``skill_graduated`` audit payload. A declaration arrives here from the
    operator's own input rather than through the gateway's result redaction, so
    nothing upstream has masked it.

    ``user:password@`` **userinfo** goes for the same reason, plus a second one
    that makes it unusable rather than merely risky: ``origin_of_url`` keeps the
    netloc verbatim, so a declared ``https://u:p@host`` normalizes to an origin
    the gateway can never report — a browser strips credentials from the URL it
    lands on — and graduation would refuse a trace that ran perfectly. Stripping
    it here rather than inside ``origin_of_url`` is deliberate: that function
    must stay byte-identical to the gateway's ``origin_of`` twin, because a
    divergence is what would make a coherent trace look like a drift.

    The **path is kept**: collapsing a declared path to a bare origin would
    silently widen the graduated skill to every path on the host. Callers
    shape-check with ``origin_of_url`` first — this assumes an absolute http(s)
    URL, and returns it unchanged when there is nothing to strip.
    """
    parsed = urlparse(url)
    # ``rpartition`` rather than a split: an ``@`` can only appear in the
    # netloc as the userinfo separator, and with none present this is a no-op
    # that leaves an IPv6 literal or a bare host untouched.
    netloc = parsed.netloc.rpartition("@")[2]
    if netloc == parsed.netloc and not parsed.query and not parsed.fragment:
        return url
    return urlunparse(parsed._replace(netloc=netloc, query="", fragment=""))


def make_trace_step(
    *,
    session_id: str,
    tool_name: str,
    args: dict[str, Any],
    captured_at: str,
    execution_id: str | None = None,
    confirm_id: str | None = None,
    flow_origin: str | None = None,
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

    ``flow_origin`` is left ``None`` at capture: the step is appended at
    the *signing* seam, before the call runs, so the origin the gateway
    reports it landed on does not exist yet. ``record_step_origin``
    completes it from the receipt seam.
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
        "flow_origin": flow_origin,
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

    def record_step_origin(
        self, session_id: str, execution_id: str, origin: str
    ) -> bool: ...

    def declare_target(self, session_id: str, target: str) -> str: ...

    def trace_target(self, session_id: str) -> str | None: ...

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
        # session_id -> (declared target, declared_at). Independent of the
        # step rows: an operator declares the target when opening a
        # skill-development session, before any mutation is captured.
        self._targets: dict[str, tuple[str, str]] = {}

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
        # Always present as a key, so a caller shaping a draft sees the same
        # field set this backend returns as the Postgres row-map does.
        stored["flow_origin"] = step.get("flow_origin")
        rows.append(stored)
        return True

    def record_step_origin(
        self, session_id: str, execution_id: str, origin: str
    ) -> bool:
        rows = self._by_session.get(session_id) or []
        for row in rows:
            if row.get("execution_id") != execution_id:
                continue
            if row.get("flow_origin") is not None:
                # First observation wins, matching the SQL ``IS NULL``
                # guard: a step's recorded origin is what the gateway
                # reported the first time it closed, and a later result
                # frame for the same execution never rewrites it.
                return False
            row["flow_origin"] = origin
            return True
        return False

    def declare_target(self, session_id: str, target: str) -> str:
        existing = self._targets.get(session_id)
        if existing is not None:
            return existing[0]
        self._targets[session_id] = (
            target,
            _canonical_timestamp(datetime.now(timezone.utc)),
        )
        return target

    def trace_target(self, session_id: str) -> str | None:
        entry = self._targets.get(session_id)
        return entry[0] if entry is not None else None

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
        self._sweep_idle_targets(cutoff)
        if reclaimed:
            LOGGER.info(
                "authoring trace: reclaimed %d idle draft step(s)", reclaimed
            )
        return reclaimed

    def _sweep_idle_targets(self, cutoff: datetime) -> int:
        """Drop declarations whose session produced no step and has idled.

        Mirrors the Postgres orphan sweep. The ``session_id not in rows``
        predicate is what makes this safe for the up-front declaration: a
        target declared minutes ago for a session that has not mutated yet
        is exactly the case this store exists to keep, so idleness is
        judged on the declaration's own stamp, never on the absence of
        steps alone. Returns the count dropped; the caller's return value
        stays a *step* count so both backends report the same unit.
        """
        stale = [
            session_id
            for session_id, (_, declared_at) in self._targets.items()
            if session_id not in self._by_session
            and _declared_before(declared_at, cutoff)
        ]
        for session_id in stale:
            self._targets.pop(session_id, None)
        return len(stale)

    def delete_session(self, session_id: str) -> bool:
        rows = self._by_session.pop(session_id, None)
        # The declaration lives and dies with the session even when the
        # session never captured a step, so its removal cannot be keyed on
        # ``rows`` being non-empty.
        declared = self._targets.pop(session_id, None)
        return bool(rows) or declared is not None

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
    flow_origin  TEXT,
    PRIMARY KEY (session_id, position)
);
CREATE INDEX IF NOT EXISTS idx_authoring_trace_status_session
    ON authoring_trace (status, session_id, captured_at);
CREATE TABLE IF NOT EXISTS authoring_trace_target (
    session_id  TEXT PRIMARY KEY,
    target      TEXT NOT NULL,
    declared_at TIMESTAMPTZ NOT NULL
);
"""

# SPEC-055 R-4: clusters whose ``authoring_trace`` predates the observed-origin
# column migrate in place at startup; pre-spec steps stay NULL, i.e. "no origin
# recorded", which graduation reads as unverifiable rather than as a drift.
# ``CREATE TABLE IF NOT EXISTS`` never adds a column to an existing table, so
# the ALTER is what makes a 0.35.0 cluster usable at 0.36.0.
_ADD_FLOW_ORIGIN_COLUMN = """
ALTER TABLE authoring_trace
    ADD COLUMN IF NOT EXISTS flow_origin TEXT
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
    status, captured_at, flow_origin
)
SELECT %(session_id)s,
       COALESCE(MAX(position), 0) + 1,
       %(tool_name)s,
       %(args)s,
       %(execution_id)s,
       %(confirm_id)s,
       'draft',
       %(captured_at)s,
       %(flow_origin)s
  FROM authoring_trace
 WHERE session_id = %(session_id)s
HAVING COUNT(*) < %(max_steps)s
   AND COUNT(*) FILTER (WHERE status <> 'draft') = 0
ON CONFLICT (session_id, position) DO NOTHING
"""

_LOAD_FOR_SESSION = """
SELECT session_id, position, tool_name, args, execution_id, confirm_id,
       status, captured_at, flow_origin
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

# Records the origin the gateway reported a captured step actually landed on
# (SPEC-055 R-4), from the receipt seam — after execution, since the signing
# seam that appends the step runs before the call. ``IS NULL`` makes the first
# observation win, matching the in-memory guard: a later frame for the same
# execution never rewrites what the step was seen to do. ``execution_id`` is
# minted once per signed envelope, so it selects exactly the step it belongs
# to; a zero rowcount is "no such step or already observed", which the caller
# reads as a no-op rather than an error.
_RECORD_STEP_ORIGIN = """
UPDATE authoring_trace
   SET flow_origin = %(origin)s
 WHERE session_id = %(session_id)s
   AND execution_id = %(execution_id)s
   AND flow_origin IS NULL
"""

# First declaration wins: the target an operator named when opening a
# skill-development session is the authorization scope the session acted under,
# so a later declaration must not retroactively widen or move it. DO NOTHING
# plus the read-back returns whichever target is actually in force.
_DECLARE_TARGET = """
INSERT INTO authoring_trace_target (session_id, target, declared_at)
VALUES (%(session_id)s, %(target)s, now())
ON CONFLICT (session_id) DO NOTHING
"""

_TRACE_TARGET = """
SELECT target
  FROM authoring_trace_target
 WHERE session_id = %(session_id)s
"""

# Reclaims declarations that never produced a step and have idled past the
# window. ``NOT IN`` is safe here because ``authoring_trace.session_id`` is
# NOT NULL — a NULL in the subquery would otherwise make the whole predicate
# unknown and silently retain everything. A declaration whose session *has*
# steps is kept for as long as those steps are: the trace's own lifecycle, not
# the declaration's age, governs it.
_SWEEP_IDLE_TARGETS = """
DELETE FROM authoring_trace_target
 WHERE declared_at <= now() - make_interval(days => %(idle_days)s)
   AND session_id NOT IN (SELECT session_id FROM authoring_trace)
"""

_DELETE_SESSION_TARGET = """
DELETE FROM authoring_trace_target
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


def _declared_before(declared_at: Any, cutoff: datetime) -> bool:
    """Whether a target declaration predates the idle cutoff.

    ``False`` for an undatable stamp, same posture as
    ``_newest_captured_at``: the sweep must not reclaim what it cannot prove
    is idle, and must not raise out of a best-effort GC either.
    """
    try:
        stamp = _parse_timestamp(declared_at)
    except (TypeError, ValueError):
        return False
    return stamp <= cutoff


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
        flow_origin,
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
        # Left as None for a pre-R-4 row and for a step whose execution the
        # receipt seam never observed; graduation treats both as unverified.
        "flow_origin": flow_origin if isinstance(flow_origin, str) else None,
    }


class PostgresAuthoringTraceStore:
    """Postgres-backed authoring traces (SPEC-055 R-1).

    Shares the SPEC-016 ``sessions`` database with the agent state, the
    confirmation records and the execution records. Connections are
    opened per operation and the ``connect`` factory is injectable so
    tests can substitute a fake driver. Both tables are created in place
    on first use — same migration posture as the confirmation and
    execution tables, so no separate DDL deploy step exists — and a
    cluster that predates ``flow_origin`` picks the column up from an
    idempotent ``ALTER`` in ``initialize``.
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
        """Create the tables, migrate in place, and reclaim idle drafts."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_AUTHORING_TRACE_DDL)
                cur.execute(_ADD_FLOW_ORIGIN_COLUMN)
                if self._idle_days > 0:
                    cur.execute(
                        _SWEEP_IDLE,
                        {
                            "idle_days": self._idle_days,
                            "sweep_limit": _SWEEP_SESSION_LIMIT,
                        },
                    )
                    # After the step sweep, so a session whose last draft
                    # steps were just reclaimed is also eligible to lose its
                    # now-orphaned declaration in the same run.
                    cur.execute(
                        _SWEEP_IDLE_TARGETS,
                        {"idle_days": self._idle_days},
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
                        "flow_origin": step.get("flow_origin"),
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

    def record_step_origin(
        self, session_id: str, execution_id: str, origin: str
    ) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _RECORD_STEP_ORIGIN,
                    {
                        "session_id": session_id,
                        "execution_id": execution_id,
                        "origin": origin,
                    },
                )
                recorded = int(getattr(cur, "rowcount", 0) or 0) > 0
            conn.commit()
        return recorded

    def declare_target(self, session_id: str, target: str) -> str:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _DECLARE_TARGET,
                    {"session_id": session_id, "target": target},
                )
                # Read back in the same transaction: the caller must learn
                # which target is actually in force, not assume its own
                # declaration landed.
                cur.execute(_TRACE_TARGET, {"session_id": session_id})
                row = cur.fetchone()
            conn.commit()
        if row is None:
            # Concurrent delete of the session between the insert and the
            # read-back. Report the caller's target — nothing is stored, and
            # graduation will see no declaration and refuse the draft.
            return target
        return str(row[0])

    def trace_target(self, session_id: str) -> str | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_TRACE_TARGET, {"session_id": session_id})
                row = cur.fetchone()
            conn.commit()
        return str(row[0]) if row is not None else None

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
        """Reclaim idle draft traces and orphaned target declarations.

        Sweeps against the database clock (``now()``), same as the
        execution-record and confirmation-record sweeps; ``now`` is the
        in-memory backend's test seam and is deliberately unused here so
        the SQL stays idiomatic. The returned count is *steps* reclaimed on
        both backends — the declaration sweep is reported nowhere so the
        two backends cannot diverge on the unit a caller observes.
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
                # Same transaction, after the step sweep, as in
                # ``initialize``: a session emptied by this run loses its
                # declaration in the same run rather than a window later.
                cur.execute(
                    _SWEEP_IDLE_TARGETS, {"idle_days": self._idle_days}
                )
            conn.commit()
        return reclaimed

    def delete_session(self, session_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_DELETE_SESSION, {"session_id": session_id})
                rows = cur.fetchall()
                # The declaration lives and dies with the session even when
                # the session never captured a step, so its removal cannot
                # be keyed on ``rows`` being non-empty.
                cur.execute(
                    _DELETE_SESSION_TARGET, {"session_id": session_id}
                )
                declared = cur.fetchall()
            conn.commit()
        return bool(rows) or bool(declared)

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
