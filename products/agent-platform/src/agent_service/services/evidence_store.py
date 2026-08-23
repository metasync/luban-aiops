"""Per-session tool-evidence store (SPEC-025 R-1).

Persists the ``tool_call`` / ``tool_result`` evidence frames of each
streamed turn so reopened sessions replay the same evidence card the live
stream rendered. Two backends mirror the SPEC-017 agent state store:
in-memory (code default, dev/CI) and Postgres (deployed), selected by the
same ``AGENT_STATE_STORE_BACKEND`` knob and sharing ``AGENT_STATE_DB_URL``.

Size is bounded at two levels (defaults measured on dev-k8s, SPEC-025
plan §Q3): a per-entry cap replaces oversized ``tool_result`` data with a
truncated preview plus a visible marker, and a per-session budget evicts
the oldest result payloads (metadata preserved) when the session's stored
evidence exceeds it. Failures never fail a turn: the kernel persists
best-effort and degrades to live-only evidence.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from agent_service.core.metrics import (
    record_evidence_frame_truncated,
    record_evidence_frames_persisted,
)

LOGGER = logging.getLogger(__name__)

# Frame types worth persisting; everything else on the sink (e.g. future
# diagnostic frames) stays live-stream-scoped.
EVIDENCE_FRAME_TYPES = frozenset({"tool_call", "tool_result"})

_TTL_SWEEP_LIMIT = 100


# ---------------------------------------------------------------------------
# Shared size-cap enforcement (identical across backends by construction)
# ---------------------------------------------------------------------------


def prepare_frames(
    frames: list[dict[str, Any]], entry_max_chars: int
) -> list[dict[str, Any]]:
    """Apply the per-entry cap to ``tool_result`` data payloads.

    An oversized payload cannot be truncated shape-preserving, so ``data``
    is replaced with the truncated serialized preview (a string) and the
    frame carries a ``truncated`` marker (R-1: visible marker, never a
    silently dropped frame). Redaction already ran at the tool-gateway
    choke point (SPEC-009), so stored payloads inherit it.
    """
    prepared: list[dict[str, Any]] = []
    for frame in frames:
        frame = dict(frame)
        if frame.get("type") == "tool_result" and frame.get("data") is not None:
            serialized = json.dumps(frame["data"], default=str)
            if len(serialized) > entry_max_chars:
                frame["data"] = serialized[:entry_max_chars]
                frame["truncated"] = {
                    "reason": "entry_cap",
                    "original_chars": len(serialized),
                }
                record_evidence_frame_truncated("entry_cap")
        prepared.append(frame)
    return prepared


def _frame_bytes(frame: dict[str, Any]) -> int:
    return len(json.dumps(frame, default=str))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class EvidenceStore(Protocol):
    """Public interface for evidence storage backends."""

    @property
    def backend_name(self) -> str: ...

    def save_turn(
        self,
        session_id: str,
        request_id: str,
        turn_index: int,
        frames: list[dict[str, Any]],
        session_max_bytes: int,
    ) -> None: ...

    def load_turns(self, session_id: str) -> list[dict[str, Any]]: ...

    def delete_session(self, session_id: str) -> bool: ...

    def is_ready(self) -> bool: ...


class _BaseEvidenceStore:
    """Cap enforcement and grouping shared by both backends.

    Subclasses provide the row-level primitives (``_session_bytes``,
    ``_evict_oldest_result_payload``, ``_insert_rows``, ``_next_frame_index``,
    ``_load_rows``, ``_delete_rows``); everything size-related lives here so
    the two backends cannot drift.
    """

    def save_turn(
        self,
        session_id: str,
        request_id: str,
        turn_index: int,
        frames: list[dict[str, Any]],
        session_max_bytes: int,
    ) -> None:
        if not frames:
            return
        start_index = self._next_frame_index(session_id, turn_index)
        created_at = _utc_now_iso()
        rows = []
        for offset, frame in enumerate(frames):
            payload = json.dumps(frame, default=str)
            rows.append(
                {
                    "session_id": session_id,
                    "request_id": request_id,
                    "turn_index": turn_index,
                    "frame_index": start_index + offset,
                    "frame": frame,
                    "payload_bytes": len(payload),
                    "created_at": created_at,
                }
            )
        self._insert_rows(rows)
        # Rows are already stored, so _session_bytes() includes this turn;
        # no incoming-byte addendum (that double count over-evicted).
        self._enforce_budget(session_id, session_max_bytes)
        record_evidence_frames_persisted(len(rows))

    def _enforce_budget(self, session_id: str, session_max_bytes: int) -> None:
        """Evict oldest result payloads until the session fits its budget.

        Eviction preserves metadata (counts, durations, request ids stay
        exact on the card) and only nulls the ``data`` payload of the
        oldest ``tool_result`` frames, oldest turn first.
        """
        total = self._session_bytes(session_id)
        while total > session_max_bytes:
            freed = self._evict_oldest_result_payload(session_id)
            if freed <= 0:
                break
            total -= freed
            record_evidence_frame_truncated("session_budget")

    def load_turns(self, session_id: str) -> list[dict[str, Any]]:
        groups: dict[int, dict[str, Any]] = {}
        for row in self._load_rows(session_id):
            group = groups.setdefault(
                row["turn_index"],
                {
                    "turn_index": row["turn_index"],
                    "request_id": row["request_id"],
                    "created_at": row["created_at"],
                    "frames": [],
                },
            )
            group["frames"].append(row["frame"])
        return [
            groups[index] for index in sorted(groups)
        ]

    # --- row-level primitives (backend-specific) ---

    def _next_frame_index(self, session_id: str, turn_index: int) -> int:
        raise NotImplementedError

    def _insert_rows(self, rows: list[dict[str, Any]]) -> None:
        raise NotImplementedError

    def _session_bytes(self, session_id: str) -> int:
        raise NotImplementedError

    def _evict_oldest_result_payload(self, session_id: str) -> int:
        raise NotImplementedError

    def _load_rows(self, session_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def _delete_rows(self, session_id: str) -> bool:
        raise NotImplementedError

    def delete_session(self, session_id: str) -> bool:
        return self._delete_rows(session_id)


# ---------------------------------------------------------------------------
# In-memory backend
# ---------------------------------------------------------------------------


class InMemoryEvidenceStore(_BaseEvidenceStore):
    """In-memory evidence store (dev/CI and fail-open fallback)."""

    backend_name = "memory"

    def __init__(self) -> None:
        # session_id -> rows in insertion order.
        self._rows: dict[str, list[dict[str, Any]]] = {}

    def _next_frame_index(self, session_id: str, turn_index: int) -> int:
        rows = self._rows.get(session_id, [])
        existing = [r for r in rows if r["turn_index"] == turn_index]
        return max((r["frame_index"] for r in existing), default=-1) + 1

    def _insert_rows(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self._rows.setdefault(row["session_id"], []).append(dict(row))

    def _session_bytes(self, session_id: str) -> int:
        return sum(r["payload_bytes"] for r in self._rows.get(session_id, ()))

    def _evict_oldest_result_payload(self, session_id: str) -> int:
        for row in self._rows.get(session_id, ()):
            frame = row["frame"]
            if (
                frame.get("type") == "tool_result"
                and "truncated" not in frame
                and frame.get("data") is not None
            ):
                evicted = dict(frame)
                evicted["data"] = None
                evicted["truncated"] = {"reason": "session_budget"}
                new_bytes = _frame_bytes(evicted)
                freed = row["payload_bytes"] - new_bytes
                row["frame"] = evicted
                row["payload_bytes"] = new_bytes
                return max(freed, 0)
        return 0

    def _load_rows(self, session_id: str) -> list[dict[str, Any]]:
        rows = self._rows.get(session_id, [])
        return [
            {
                "turn_index": r["turn_index"],
                "frame_index": r["frame_index"],
                "request_id": r["request_id"],
                "frame": r["frame"],
                "created_at": r.get("created_at", ""),
            }
            for r in sorted(
                rows, key=lambda r: (r["turn_index"], r["frame_index"])
            )
        ]

    def _delete_rows(self, session_id: str) -> bool:
        return self._rows.pop(session_id, None) is not None

    def is_ready(self) -> bool:
        return True

    def __len__(self) -> int:
        return sum(len(rows) for rows in self._rows.values())


# ---------------------------------------------------------------------------
# Postgres backend
# ---------------------------------------------------------------------------


_SESSION_EVIDENCE_DDL = """
CREATE TABLE IF NOT EXISTS session_evidence (
    session_id    TEXT NOT NULL,
    turn_index    INTEGER NOT NULL,
    frame_index   INTEGER NOT NULL,
    request_id    TEXT NOT NULL,
    frame         JSONB NOT NULL,
    payload_bytes INTEGER NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, turn_index, frame_index)
);
CREATE INDEX IF NOT EXISTS idx_session_evidence_updated
    ON session_evidence (updated_at);
"""

_NEXT_FRAME_INDEX = """
SELECT COALESCE(MAX(frame_index), -1) + 1
  FROM session_evidence
 WHERE session_id = %(session_id)s AND turn_index = %(turn_index)s
"""

_INSERT_ROW = """
INSERT INTO session_evidence
    (session_id, turn_index, frame_index, request_id, frame, payload_bytes)
VALUES
    (%(session_id)s, %(turn_index)s, %(frame_index)s, %(request_id)s,
     %(frame)s, %(payload_bytes)s)
ON CONFLICT (session_id, turn_index, frame_index) DO NOTHING
"""

_SESSION_BYTES = """
SELECT COALESCE(SUM(payload_bytes), 0)
  FROM session_evidence
 WHERE session_id = %(session_id)s
"""

_OLDEST_EVICTABLE = """
SELECT ctid, frame, payload_bytes
  FROM session_evidence
 WHERE session_id = %(session_id)s
   AND frame ->> 'type' = 'tool_result'
   AND NOT (frame ? 'truncated')
   AND jsonb_typeof(frame -> 'data') <> 'null'
 ORDER BY turn_index, frame_index
 LIMIT 1
"""

_EVICT_ROW = """
UPDATE session_evidence
   SET frame = %(frame)s, payload_bytes = %(payload_bytes)s,
       updated_at = now()
 WHERE ctid = %(ctid)s
"""

# Load folds a TTL refresh into the read (mirrors the SPEC-017 state-store
# pattern): reads keep stored evidence alive exactly like turn writes.
_LOAD_ROWS = """
UPDATE session_evidence
   SET updated_at = now()
 WHERE session_id = %(session_id)s
RETURNING turn_index, frame_index, request_id, frame,
          to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
"""

_DELETE_ROWS = """
DELETE FROM session_evidence
 WHERE session_id = %(session_id)s
"""

_SWEEP_EXPIRED = """
DELETE FROM session_evidence
 WHERE ctid IN (
     SELECT ctid FROM session_evidence
      WHERE updated_at <= now() - make_interval(secs => %(ttl_seconds)s)
      LIMIT %(sweep_limit)s
 )
"""

SyncConnectFactory = Callable[[], Iterator[Any]]


class PostgresEvidenceStore(_BaseEvidenceStore):
    """Postgres-backed evidence store sharing the SPEC-016/017 database.

    Connections open per operation; the ``connect`` factory is injectable
    so tests can substitute a fake driver (same test seam as the SPEC-017
    state store).
    """

    backend_name = "postgres"

    def __init__(
        self,
        db_url: str,
        ttl_seconds: float,
        connect: SyncConnectFactory | None = None,
    ) -> None:
        self._db_url = db_url
        self.ttl_seconds = ttl_seconds
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
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_SESSION_EVIDENCE_DDL)
            conn.commit()

    def _next_frame_index(self, session_id: str, turn_index: int) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _NEXT_FRAME_INDEX,
                    {"session_id": session_id, "turn_index": turn_index},
                )
                row = cur.fetchone()
            conn.commit()
        return int(row[0]) if row is not None else 0

    def _insert_rows(self, rows: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(
                        _INSERT_ROW,
                        {
                            **row,
                            "frame": json.dumps(row["frame"], default=str),
                        },
                    )
                cur.execute(
                    _SWEEP_EXPIRED,
                    {
                        "ttl_seconds": self.ttl_seconds,
                        "sweep_limit": _TTL_SWEEP_LIMIT,
                    },
                )
            conn.commit()

    def _session_bytes(self, session_id: str) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_SESSION_BYTES, {"session_id": session_id})
                row = cur.fetchone()
            conn.commit()
        return int(row[0]) if row is not None else 0

    def _evict_oldest_result_payload(self, session_id: str) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_OLDEST_EVICTABLE, {"session_id": session_id})
                row = cur.fetchone()
                if row is None:
                    conn.commit()
                    return 0
                ctid, frame, old_bytes = row
                evicted = frame if isinstance(frame, dict) else json.loads(frame)
                evicted["data"] = None
                evicted["truncated"] = {"reason": "session_budget"}
                new_bytes = _frame_bytes(evicted)
                cur.execute(
                    _EVICT_ROW,
                    {
                        "frame": json.dumps(evicted, default=str),
                        "payload_bytes": new_bytes,
                        "ctid": ctid,
                    },
                )
            conn.commit()
        return max(int(old_bytes) - new_bytes, 0)

    def _load_rows(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_LOAD_ROWS, {"session_id": session_id})
                rows = cur.fetchall()
            conn.commit()
        loaded = []
        for turn_index, frame_index, request_id, frame, created_at in rows:
            loaded.append(
                {
                    "turn_index": turn_index,
                    "frame_index": frame_index,
                    "request_id": request_id,
                    "frame": frame if isinstance(frame, dict) else json.loads(frame),
                    "created_at": created_at or "",
                }
            )
        loaded.sort(key=lambda r: (r["turn_index"], r["frame_index"]))
        return loaded

    def _delete_rows(self, session_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_DELETE_ROWS, {"session_id": session_id})
                deleted = cur.rowcount or 0
            conn.commit()
        return deleted > 0

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


def build_evidence_store() -> EvidenceStore:
    """Create the evidence store from the state-store environment knobs.

    Reads the same ``AGENT_STATE_STORE_BACKEND`` / ``AGENT_STATE_DB_URL``
    pair as the SPEC-017 state store (one knob, same DSN) plus
    ``AGENT_STATE_TTL_SECONDS`` for the opportunistic sweep. Backend
    failures fail open: evidence degrades to live-only, counted via the
    state-store fallback metric path.
    """
    from agent_service.services.agent_state_store import (
        DEFAULT_STATE_TTL_SECONDS,
        _env_float,
        _env_str,
    )

    backend = _env_str("AGENT_STATE_STORE_BACKEND", "memory")
    ttl = _env_float("AGENT_STATE_TTL_SECONDS", DEFAULT_STATE_TTL_SECONDS)

    if backend == "memory":
        return InMemoryEvidenceStore()

    if backend == "postgres":
        db_url = os.getenv("AGENT_STATE_DB_URL", "").strip()
        if not db_url:
            raise ValueError(
                "AGENT_STATE_STORE_BACKEND=postgres requires AGENT_STATE_DB_URL to be set"
            )
        store = PostgresEvidenceStore(db_url=db_url, ttl_seconds=ttl)
        try:
            store.initialize()
        except Exception as exc:
            LOGGER.warning(
                "evidence store: Postgres unavailable (%s), falling back to in-memory",
                exc,
            )
            return InMemoryEvidenceStore()
        LOGGER.info("evidence store: Postgres backend initialized")
        return store

    raise ValueError(
        f"Unknown AGENT_STATE_STORE_BACKEND: {backend!r} "
        "(expected 'memory' or 'postgres')"
    )


# Module-level singleton — imported by runtime_kernel.py / routes.
EVIDENCE_STORE = build_evidence_store()
