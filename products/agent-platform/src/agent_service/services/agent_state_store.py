"""Agent state store with pluggable backends (SPEC-017 R-3).

Persists the kernel-serializable ``AgentState`` snapshot per platform
session so conversations survive agent-platform restarts. Two backends:
in-memory (code default, dev/CI) and Postgres (deployed). Backend
selection is driven by ``AGENT_STATE_STORE_BACKEND``.

Snapshots are written after every completed turn and restored when an
agent is constructed for a session (cache miss). Failures never fail a
turn: snapshot/restore errors log and count, then degrade gracefully.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Protocol, runtime_checkable

from agent_service.core.metrics import (
    record_agent_state_backend,
    record_agent_state_error,
    record_agent_state_fallback,
)

LOGGER = logging.getLogger(__name__)

DEFAULT_STATE_TTL_SECONDS = 3600.0


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class AgentStateStore(Protocol):
    """Public interface for agent state storage backends."""

    @property
    def backend_name(self) -> str: ...

    def save_state(self, session_id: str, state_json: str) -> None: ...

    def load_state(self, session_id: str) -> str | None: ...

    def delete_state(self, session_id: str) -> bool: ...

    def is_ready(self) -> bool: ...

    def server_version(self) -> str | None:
        """Backend server/product version for the platform inventory (v0.23.4).

        Informational only — ``None`` when unknown or unreachable.
        """
        ...


# ---------------------------------------------------------------------------
# In-memory backend
# ---------------------------------------------------------------------------


class InMemoryAgentStateStore:
    """In-memory agent state store.

    Single-replica and non-persistent; suitable for development, CI, and
    as a fallback when Postgres is unreachable.
    """

    backend_name = "memory"

    def __init__(self) -> None:
        self._states: dict[str, str] = {}

    def save_state(self, session_id: str, state_json: str) -> None:
        self._states[session_id] = state_json

    def load_state(self, session_id: str) -> str | None:
        return self._states.get(session_id)

    def delete_state(self, session_id: str) -> bool:
        return self._states.pop(session_id, None) is not None

    def is_ready(self) -> bool:
        return True

    def server_version(self) -> str | None:
        # No server behind an in-memory store.
        return None

    def __len__(self) -> int:
        return len(self._states)


# ---------------------------------------------------------------------------
# Postgres backend
# ---------------------------------------------------------------------------


_AGENT_STATES_DDL = """
CREATE TABLE IF NOT EXISTS agent_states (
    session_id TEXT PRIMARY KEY,
    state      JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_states_updated
    ON agent_states (updated_at);
"""

_UPSERT_STATE = """
INSERT INTO agent_states (session_id, state, updated_at)
VALUES (%(session_id)s, %(state)s, now())
ON CONFLICT (session_id)
DO UPDATE SET state = EXCLUDED.state, updated_at = now()
"""

# Restore folds a TTL refresh into the read (mirrors the SPEC-016 session
# pattern) so a state row is never swept while its session is still being
# used — reads keep the durable snapshot alive, not just turn writes.
_LOAD_STATE = """
UPDATE agent_states
   SET updated_at = now()
 WHERE session_id = %(session_id)s
RETURNING state
"""

_DELETE_STATE = """
DELETE FROM agent_states
 WHERE session_id = %(session_id)s
RETURNING session_id
"""

# Bounded opportunistic sweep (same pattern as SPEC-016 R-1): reclaim rows
# older than the session TTL without a long-running sweeper; piggybacks on
# writes.
_SWEEP_EXPIRED = """
DELETE FROM agent_states
 WHERE ctid IN (
     SELECT ctid FROM agent_states
      WHERE updated_at <= now() - make_interval(secs => %(ttl_seconds)s)
      LIMIT %(sweep_limit)s
 )
"""

_SWEEP_LIMIT = 100

SyncConnectFactory = Callable[[], Iterator[Any]]


class PostgresAgentStateStore:
    """Postgres-backed agent state store (SPEC-017 R-3).

    Shares the SPEC-016 ``sessions`` database — one database for
    platform-owned agent session state. The ``state`` column carries
    ``AgentState.model_dump_json()`` as JSONB; connections are opened per
    operation and the ``connect`` factory is injectable so tests can
    substitute a fake driver.
    """

    backend_name = "postgres"

    def __init__(
        self,
        db_url: str,
        ttl_seconds: float = DEFAULT_STATE_TTL_SECONDS,
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
                cur.execute(_AGENT_STATES_DDL)
            conn.commit()

    def save_state(self, session_id: str, state_json: str) -> None:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        _UPSERT_STATE,
                        {"session_id": session_id, "state": state_json},
                    )
                    cur.execute(
                        _SWEEP_EXPIRED,
                        {
                            "ttl_seconds": self.ttl_seconds,
                            "sweep_limit": _SWEEP_LIMIT,
                        },
                    )
                conn.commit()
        except Exception:
            record_agent_state_error("save")
            raise

    def load_state(self, session_id: str) -> str | None:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(_LOAD_STATE, {"session_id": session_id})
                    row = cur.fetchone()
                conn.commit()
        except Exception:
            record_agent_state_error("load")
            raise
        if row is None:
            return None
        # JSONB returns a decoded dict; the caller expects the JSON string.
        state = row[0]
        if isinstance(state, str):
            return state
        import json

        return json.dumps(state)

    def delete_state(self, session_id: str) -> bool:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(_DELETE_STATE, {"session_id": session_id})
                    row = cur.fetchone()
                conn.commit()
        except Exception:
            record_agent_state_error("delete")
            raise
        return row is not None

    def is_ready(self) -> bool:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return cur.fetchone() is not None
        except Exception:
            return False

    def server_version(self) -> str | None:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT current_setting('server_version')")
                    row = cur.fetchone()
            value = row[0] if row else None
            return str(value) if value else None
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def build_agent_state_store() -> AgentStateStore:
    """Create the agent state store based on environment configuration.

    Reads:
        AGENT_STATE_STORE_BACKEND: ``memory`` | ``postgres`` (default
            ``memory``; unknown values fail startup, SPEC-017 R-3)
        AGENT_STATE_DB_URL: Postgres DSN (required for ``postgres``)
        AGENT_STATE_TTL_SECONDS: sweep TTL for stale rows (default 3600)

    Backend failures fail open: the service stays usable on an in-memory
    store and records ``agent_state_fallbacks_total``.
    """
    backend = _env_str("AGENT_STATE_STORE_BACKEND", "memory")
    ttl = _env_float("AGENT_STATE_TTL_SECONDS", DEFAULT_STATE_TTL_SECONDS)

    if backend == "memory":
        record_agent_state_backend("memory")
        return InMemoryAgentStateStore()

    if backend == "postgres":
        db_url = os.getenv("AGENT_STATE_DB_URL", "").strip()
        if not db_url:
            raise ValueError(
                "AGENT_STATE_STORE_BACKEND=postgres requires AGENT_STATE_DB_URL to be set"
            )
        try:
            store = PostgresAgentStateStore(db_url=db_url, ttl_seconds=ttl)
            store.initialize()
            record_agent_state_backend("postgres")
            LOGGER.info("agent state store: Postgres backend initialized")
            return store
        except Exception as exc:
            LOGGER.warning(
                "agent state store: Postgres unavailable (%s), falling back to in-memory",
                exc,
            )
            record_agent_state_fallback()
            record_agent_state_backend("memory")
            return InMemoryAgentStateStore()

    raise ValueError(
        f"Unknown AGENT_STATE_STORE_BACKEND: {backend!r} "
        "(expected 'memory' or 'postgres')"
    )


# Module-level singleton — imported by runtime_kernel.py / session_service.py.
AGENT_STATE_STORE = build_agent_state_store()
