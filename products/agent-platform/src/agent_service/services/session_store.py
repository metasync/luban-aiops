"""Session store with pluggable backends (SPEC-006, SPEC-016).

Provides a Protocol-based interface so the service layer can work with an
in-memory store (dev/CI), a Redis-backed store (legacy deployments), or a
Postgres-backed store (deployed, SPEC-016). Backend selection is driven by
the ``SESSION_STORE_BACKEND`` env var.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from agent_service.core.metrics import (
    record_session_store_backend,
    record_session_store_error,
    record_session_store_fallback,
)
from agent_service.schemas.api import SessionRecord

LOGGER = logging.getLogger(__name__)

DEFAULT_SESSION_TTL_SECONDS = 3600.0
DEFAULT_SESSION_MAX_ENTRIES = 1000
DEFAULT_SESSION_REDIS_HOST = "127.0.0.1"
DEFAULT_SESSION_REDIS_PORT = 6379
DEFAULT_SESSION_REDIS_DB = 1
REDIS_PING_TIMEOUT_SECONDS = 3.0

_SESSION_KEY_PREFIX = "session:"
_USER_SESSIONS_KEY_PREFIX = "user_sessions:"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class SessionStore(Protocol):
    """Public interface for session storage backends."""

    @property
    def backend_name(self) -> str: ...

    def create_session(
        self, user_id: str | None, session_id: str | None = None
    ) -> SessionRecord: ...

    def get_session(self, session_id: str) -> SessionRecord | None: ...

    def list_sessions_by_user(self, user_id: str) -> list[SessionRecord]: ...

    def delete_session(self, session_id: str) -> bool: ...

    def touch_session(self, session_id: str) -> None:
        """Mark the session active now (SPEC-022 R-1 workspace ordering)."""
        ...

    def set_session_title(self, session_id: str, title: str) -> None:
        """Record the session title once; an existing title is never rewritten."""
        ...

    def set_session_model(self, session_id: str, model: str) -> None:
        """Pin the model that resolved for the turn (SPEC-024 R-3, Q-4).

        Overwrites on every resolved turn so the newest selection wins;
        best-effort bookkeeping — a store failure never fails the turn.
        """
        ...

    def is_ready(self) -> bool: ...

    def __len__(self) -> int: ...


# ---------------------------------------------------------------------------
# In-memory backend
# ---------------------------------------------------------------------------


class InMemorySessionStore:
    """In-memory session store with TTL and max-entry eviction.

    Single-replica and non-persistent; suitable for development, CI, and
    as a fallback when Redis is unreachable.
    """

    backend_name = "memory"

    def __init__(
        self,
        ttl_seconds: float = DEFAULT_SESSION_TTL_SECONDS,
        max_entries: int = DEFAULT_SESSION_MAX_ENTRIES,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._sessions: dict[str, SessionRecord] = {}
        self._last_accessed: dict[str, float] = {}

    def _purge_expired(self, now: float) -> None:
        expired = [
            session_id
            for session_id, accessed_at in self._last_accessed.items()
            if now - accessed_at > self.ttl_seconds
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)
            self._last_accessed.pop(session_id, None)

    def _evict_oldest(self) -> None:
        while len(self._sessions) > self.max_entries:
            oldest_id = min(self._last_accessed, key=self._last_accessed.get)
            self._sessions.pop(oldest_id, None)
            self._last_accessed.pop(oldest_id, None)

    def create_session(
        self, user_id: str | None, session_id: str | None = None
    ) -> SessionRecord:
        now = time.monotonic()
        self._purge_expired(now)
        record = SessionRecord(
            session_id=session_id or f"ses-{uuid4()}",
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
            last_active_at=datetime.now(timezone.utc),
        )
        self._sessions[record.session_id] = record
        self._last_accessed[record.session_id] = now
        self._evict_oldest()
        return record

    def get_session(self, session_id: str) -> SessionRecord | None:
        now = time.monotonic()
        self._purge_expired(now)
        record = self._sessions.get(session_id)
        if record is not None:
            self._last_accessed[session_id] = now
        return record

    def list_sessions_by_user(self, user_id: str) -> list[SessionRecord]:
        now = time.monotonic()
        self._purge_expired(now)
        return [
            record
            for record in self._sessions.values()
            if record.user_id == user_id
        ]

    def delete_session(self, session_id: str) -> bool:
        record = self._sessions.pop(session_id, None)
        self._last_accessed.pop(session_id, None)
        return record is not None

    def touch_session(self, session_id: str) -> None:
        record = self._sessions.get(session_id)
        if record is not None:
            record.last_active_at = datetime.now(timezone.utc)

    def set_session_title(self, session_id: str, title: str) -> None:
        record = self._sessions.get(session_id)
        if record is not None and record.title is None:
            record.title = title

    def set_session_model(self, session_id: str, model: str) -> None:
        record = self._sessions.get(session_id)
        if record is not None:
            record.model = model

    def is_ready(self) -> bool:
        return True

    def __len__(self) -> int:
        return len(self._sessions)


# ---------------------------------------------------------------------------
# Redis backend
# ---------------------------------------------------------------------------


class RedisSessionStore:
    """Redis-backed session store.

    Sessions are stored as JSON blobs keyed by ``session:{session_id}``
    with Redis-native ``EXPIRE`` for TTL.  User-scoped listing uses a
    sorted set ``user_sessions:{user_id}`` scored by ``created_at`` epoch.

    Titles live in a dedicated ``session:title:{session_id}`` key minted
    with ``SET ... NX`` (SPEC-022 R-1 set-once contract): the blob
    read-modify-write path in ``touch_session`` can never clobber a
    minted title, and two concurrent first turns cannot both win.
    """

    backend_name = "redis"

    def __init__(
        self,
        client: "redis.Redis",  # type: ignore[name-defined]  # noqa: F821
        ttl_seconds: float = DEFAULT_SESSION_TTL_SECONDS,
    ) -> None:
        self._client = client
        self.ttl_seconds = int(ttl_seconds)

    def _session_key(self, session_id: str) -> str:
        return f"{_SESSION_KEY_PREFIX}{session_id}"

    def _title_key(self, session_id: str) -> str:
        return f"{_SESSION_KEY_PREFIX}title:{session_id}"

    def _user_key(self, user_id: str) -> str:
        return f"{_USER_SESSIONS_KEY_PREFIX}{user_id}"

    def _serialize(self, record: SessionRecord) -> str:
        return record.model_dump_json()

    def _deserialize(self, raw: bytes | str) -> SessionRecord | None:
        try:
            return SessionRecord.model_validate_json(raw)
        except Exception:
            return None

    def create_session(
        self, user_id: str | None, session_id: str | None = None
    ) -> SessionRecord:
        record = SessionRecord(
            session_id=session_id or f"ses-{uuid4()}",
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
            last_active_at=datetime.now(timezone.utc),
        )
        key = self._session_key(record.session_id)
        try:
            self._client.setex(key, self.ttl_seconds, self._serialize(record))
            if user_id:
                self._client.zadd(
                    self._user_key(user_id),
                    {record.session_id: record.created_at.timestamp()},
                )
        except Exception:
            record_session_store_error("create")
            raise
        return record

    def get_session(self, session_id: str) -> SessionRecord | None:
        key = self._session_key(session_id)
        try:
            raw = self._client.get(key)
            if raw is None:
                return None
            record = self._deserialize(raw)
            if record is not None:
                # Refresh TTL on access.
                self._client.expire(key, self.ttl_seconds)
                self._overlay_title(record)
            return record
        except Exception:
            record_session_store_error("get")
            raise

    def _overlay_title(self, record: SessionRecord) -> None:
        """Merge the atomically-minted title key into the record.

        The blob itself never carries the title, so ``touch_session``'s
        rewrite cannot erase it.
        """
        title_key = self._title_key(record.session_id)
        raw_title = self._client.get(title_key)
        if raw_title is None:
            return
        record.title = (
            raw_title.decode() if isinstance(raw_title, bytes) else raw_title
        )
        self._client.expire(title_key, self.ttl_seconds)

    def list_sessions_by_user(self, user_id: str) -> list[SessionRecord]:
        try:
            session_ids = self._client.zrangebyscore(
                self._user_key(user_id), "-inf", "+inf"
            )
            results: list[SessionRecord] = []
            for sid_bytes in session_ids:
                sid = sid_bytes if isinstance(sid_bytes, str) else sid_bytes.decode()
                record = self.get_session(sid)
                if record is not None:
                    results.append(record)
            return results
        except Exception:
            record_session_store_error("list")
            raise

    def delete_session(self, session_id: str) -> bool:
        key = self._session_key(session_id)
        try:
            raw = self._client.get(key)
            if raw is None:
                return False
            record = self._deserialize(raw)
            deleted = self._client.delete(key)
            self._client.delete(self._title_key(session_id))
            if record and record.user_id:
                self._client.zrem(self._user_key(record.user_id), session_id)
            return bool(deleted)
        except Exception:
            record_session_store_error("delete")
            raise

    def touch_session(self, session_id: str) -> None:
        # The blob never carries the title (it lives in the NX-minted
        # title key), so this read-modify-write can only race on
        # last_active_at, where a lost update is harmless.
        key = self._session_key(session_id)
        try:
            raw = self._client.get(key)
            if raw is None:
                return
            record = self._deserialize(raw)
            if record is None:
                return
            record.last_active_at = datetime.now(timezone.utc)
            self._client.setex(key, self.ttl_seconds, self._serialize(record))
        except Exception:
            record_session_store_error("touch")
            raise

    def set_session_title(self, session_id: str, title: str) -> None:
        try:
            if self._client.get(self._session_key(session_id)) is None:
                return
            # Atomic set-once: NX never overwrites a minted title, and
            # concurrent first turns cannot both win.
            self._client.set(
                self._title_key(session_id),
                title,
                nx=True,
                ex=self.ttl_seconds,
            )
        except Exception:
            record_session_store_error("set_title")
            raise

    def set_session_model(self, session_id: str, model: str) -> None:
        # The pinned model rides the serialized blob (pydantic default
        # keeps legacy blobs readable); newest resolved selection wins.
        key = self._session_key(session_id)
        try:
            raw = self._client.get(key)
            if raw is None:
                return
            record = self._deserialize(raw)
            if record is None:
                return
            record.model = model
            self._client.setex(key, self.ttl_seconds, self._serialize(record))
        except Exception:
            record_session_store_error("set_model")
            raise

    def is_ready(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception:
            return False

    def __len__(self) -> int:
        # Count session keys only (exclude user sorted sets and the
        # session:title:* keys that carry minted titles).
        try:
            keys = self._client.keys(f"{_SESSION_KEY_PREFIX}*")
            return len(
                [
                    key
                    for key in keys
                    if not (
                        key if isinstance(key, str) else key.decode()
                    ).startswith(f"{_SESSION_KEY_PREFIX}title:")
                ]
            )
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# Postgres backend (SPEC-016)
# ---------------------------------------------------------------------------


_SESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id       TEXT PRIMARY KEY,
    user_id          TEXT,
    created_at       TIMESTAMPTZ NOT NULL,
    last_accessed_at TIMESTAMPTZ NOT NULL,
    title            TEXT,
    last_active_at   TIMESTAMPTZ,
    model            TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_user
    ON sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_accessed
    ON sessions (last_accessed_at);
-- SPEC-022 R-1: deployments bootstrapped before the workspace columns
-- existed gain them idempotently (fail-open semantics unchanged).
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMPTZ;
-- SPEC-024 R-3: pinned model id per session (Q-4 affinity home).
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS model TEXT;
"""

_NOT_EXPIRED = (
    "last_accessed_at > now() - make_interval(secs => %(ttl_seconds)s)"
)

# Conflict-safe insert: reclaim a row whose idle TTL has lapsed but has not
# been swept yet, and no-op against a live conflicting row. The no-op case
# keeps create_named_session's post-create re-read authoritative (foreign
# owner surfaces as 404 instead of a UniqueViolation 500).
_INSERT_SESSION = """
INSERT INTO sessions (session_id, user_id, created_at, last_accessed_at)
VALUES (%(session_id)s, %(user_id)s, %(created_at)s, %(created_at)s)
ON CONFLICT (session_id) DO UPDATE
   SET user_id = EXCLUDED.user_id,
       created_at = EXCLUDED.created_at,
       last_accessed_at = EXCLUDED.last_accessed_at
 WHERE sessions.last_accessed_at <= now() - make_interval(secs => %(ttl_seconds)s)
"""

# Idle-TTL refresh folded into the read (one statement, one round trip).
_GET_SESSION = f"""
UPDATE sessions
   SET last_accessed_at = now()
 WHERE session_id = %(session_id)s AND {_NOT_EXPIRED}
RETURNING session_id, user_id, created_at, title, last_active_at, model
"""

_LIST_USER_SESSIONS = f"""
SELECT session_id, user_id, created_at, title, last_active_at, model
  FROM sessions
 WHERE user_id = %(user_id)s AND {_NOT_EXPIRED}
 ORDER BY COALESCE(last_active_at, created_at) DESC
 LIMIT %(limit)s
"""

_DELETE_SESSION = """
DELETE FROM sessions
 WHERE session_id = %(session_id)s
RETURNING session_id
"""

# SPEC-022 R-1: workspace bookkeeping. The title is minted once server-side
# (first user turn) and never rewritten, hence the ``title IS NULL`` guard.
_TOUCH_SESSION = f"""
UPDATE sessions
   SET last_active_at = now()
 WHERE session_id = %(session_id)s AND {_NOT_EXPIRED}
"""

_SET_SESSION_TITLE = f"""
UPDATE sessions
   SET title = %(title)s
 WHERE session_id = %(session_id)s AND {_NOT_EXPIRED} AND title IS NULL
"""

# SPEC-024 R-3: the pinned model follows the newest resolved selection
# (unlike the set-once title), so no IS NULL guard.
_SET_SESSION_MODEL = f"""
UPDATE sessions
   SET model = %(model)s
 WHERE session_id = %(session_id)s AND {_NOT_EXPIRED}
"""

_COUNT_SESSIONS = f"""
SELECT COUNT(*) FROM sessions WHERE {_NOT_EXPIRED}
"""

# Bounded opportunistic sweep (SPEC-016 R-1): reclaim expired rows without a
# long-running sweeper; runs piggyback on writes.
_SWEEP_EXPIRED = """
DELETE FROM sessions
 WHERE ctid IN (
     SELECT ctid FROM sessions
      WHERE last_accessed_at <= now() - make_interval(secs => %(ttl_seconds)s)
      LIMIT %(sweep_limit)s
 )
"""

_SWEEP_LIMIT = 100

SyncConnectFactory = Callable[[], Iterator[Any]]


class PostgresSessionStore:
    """Postgres-backed session store (SPEC-016 R-1).

    Semantics mirror the Redis backend: idle TTL refreshed on read, expired
    rows invisible to every query. Connections are opened per operation
    (session traffic is low-volume); the ``connect`` factory is injectable
    so tests can substitute a fake driver.
    """

    backend_name = "postgres"

    def __init__(
        self,
        db_url: str,
        ttl_seconds: float = DEFAULT_SESSION_TTL_SECONDS,
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

    def _ttl_params(self) -> dict[str, Any]:
        return {"ttl_seconds": self.ttl_seconds}

    def initialize(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_SESSIONS_DDL)
            conn.commit()

    def create_session(
        self, user_id: str | None, session_id: str | None = None
    ) -> SessionRecord:
        record = SessionRecord(
            session_id=session_id or f"ses-{uuid4()}",
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
        )
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        _INSERT_SESSION,
                        {
                            "session_id": record.session_id,
                            "user_id": record.user_id,
                            "created_at": record.created_at,
                            **self._ttl_params(),
                        },
                    )
                    cur.execute(
                        _SWEEP_EXPIRED,
                        {
                            **self._ttl_params(),
                            "sweep_limit": _SWEEP_LIMIT,
                        },
                    )
                conn.commit()
        except Exception:
            record_session_store_error("create")
            raise
        return record

    def get_session(self, session_id: str) -> SessionRecord | None:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        _GET_SESSION,
                        {
                            "session_id": session_id,
                            **self._ttl_params(),
                        },
                    )
                    row = cur.fetchone()
                conn.commit()
        except Exception:
            record_session_store_error("get")
            raise
        if row is None:
            return None
        return SessionRecord(
            session_id=row[0],
            user_id=row[1],
            created_at=row[2],
            title=row[3],
            last_active_at=row[4],
            model=row[5],
        )

    def list_sessions_by_user(
        self, user_id: str, limit: int = 50
    ) -> list[SessionRecord]:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        _LIST_USER_SESSIONS,
                        {
                            "user_id": user_id,
                            "limit": limit,
                            **self._ttl_params(),
                        },
                    )
                    rows = cur.fetchall()
                conn.commit()
        except Exception:
            record_session_store_error("list")
            raise
        return [
            SessionRecord(
                session_id=row[0],
                user_id=row[1],
                created_at=row[2],
                title=row[3],
                last_active_at=row[4],
                model=row[5],
            )
            for row in rows
        ]

    def delete_session(self, session_id: str) -> bool:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        _DELETE_SESSION, {"session_id": session_id}
                    )
                    row = cur.fetchone()
                conn.commit()
        except Exception:
            record_session_store_error("delete")
            raise
        return row is not None

    def touch_session(self, session_id: str) -> None:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        _TOUCH_SESSION,
                        {"session_id": session_id, **self._ttl_params()},
                    )
                conn.commit()
        except Exception:
            record_session_store_error("touch")
            raise

    def set_session_title(self, session_id: str, title: str) -> None:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        _SET_SESSION_TITLE,
                        {
                            "session_id": session_id,
                            "title": title,
                            **self._ttl_params(),
                        },
                    )
                conn.commit()
        except Exception:
            record_session_store_error("set_title")
            raise

    def set_session_model(self, session_id: str, model: str) -> None:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        _SET_SESSION_MODEL,
                        {
                            "session_id": session_id,
                            "model": model,
                            **self._ttl_params(),
                        },
                    )
                conn.commit()
        except Exception:
            record_session_store_error("set_model")
            raise

    def is_ready(self) -> bool:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return cur.fetchone() is not None
        except Exception:
            return False

    def __len__(self) -> int:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(_COUNT_SESSIONS, self._ttl_params())
                    row = cur.fetchone()
                conn.commit()
        except Exception:
            return 0
        return int(row[0]) if row else 0


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _build_memory_store(ttl: float) -> InMemorySessionStore:
    store = InMemorySessionStore(
        ttl_seconds=ttl,
        max_entries=_env_int("SESSION_MAX_ENTRIES", DEFAULT_SESSION_MAX_ENTRIES),
    )
    record_session_store_backend("memory")
    return store


def _build_postgres_store(db_url: str, ttl: float) -> PostgresSessionStore:
    """Construct and initialize the Postgres backend (SPEC-016 R-2).

    Raises on an unreachable database so the factory can apply the
    fail-open in-memory fallback.
    """
    store = PostgresSessionStore(db_url=db_url, ttl_seconds=ttl)
    store.initialize()
    record_session_store_backend("postgres")
    LOGGER.info("session store: Postgres backend initialized")
    return store


def build_session_store() -> SessionStore:
    """Create the session store based on environment configuration.

    Reads:
        SESSION_STORE_BACKEND: ``memory`` | ``redis`` | ``postgres``
            (default ``memory``; unknown values fail startup, SPEC-016 R-2)
        SESSION_TTL_SECONDS: TTL for all backends (default 3600)
        SESSION_MAX_ENTRIES: max entries for in-memory backend (default 1000)
        SESSION_REDIS_HOST: Redis host (default ``127.0.0.1``)
        SESSION_REDIS_PORT: Redis port (default ``6379``)
        SESSION_REDIS_DB: Redis DB number (default ``1``)
        SESSION_DB_URL: Postgres DSN (required for ``postgres``)

    Backend failures fail open: the service stays usable on an in-memory
    fallback and records ``session_store_fallbacks_total``.
    """
    backend = _env_str("SESSION_STORE_BACKEND", "memory")
    ttl = _env_float("SESSION_TTL_SECONDS", DEFAULT_SESSION_TTL_SECONDS)

    if backend == "memory":
        return _build_memory_store(ttl)

    if backend == "postgres":
        db_url = os.getenv("SESSION_DB_URL", "").strip()
        if not db_url:
            raise ValueError(
                "SESSION_STORE_BACKEND=postgres requires SESSION_DB_URL to be set"
            )
        try:
            return _build_postgres_store(db_url, ttl)
        except Exception as exc:
            LOGGER.warning(
                "session store: Postgres unavailable (%s), falling back to in-memory",
                exc,
            )
            record_session_store_fallback()
            return _build_memory_store(ttl)

    if backend != "redis":
        raise ValueError(
            f"Unknown SESSION_STORE_BACKEND: {backend!r} "
            "(expected 'memory', 'redis', or 'postgres')"
        )

    # Redis backend — attempt connection with timeout.
    try:
        import redis

        client = redis.Redis(
            host=_env_str("SESSION_REDIS_HOST", DEFAULT_SESSION_REDIS_HOST),
            port=_env_int("SESSION_REDIS_PORT", DEFAULT_SESSION_REDIS_PORT),
            db=_env_int("SESSION_REDIS_DB", DEFAULT_SESSION_REDIS_DB),
            socket_timeout=REDIS_PING_TIMEOUT_SECONDS,
            socket_connect_timeout=REDIS_PING_TIMEOUT_SECONDS,
            decode_responses=False,
        )
        client.ping()
        store = RedisSessionStore(client=client, ttl_seconds=ttl)
        record_session_store_backend("redis")
        LOGGER.info(
            "session store: Redis backend connected",
            extra={
                "host": _env_str("SESSION_REDIS_HOST", DEFAULT_SESSION_REDIS_HOST),
                "port": _env_int("SESSION_REDIS_PORT", DEFAULT_SESSION_REDIS_PORT),
                "db": _env_int("SESSION_REDIS_DB", DEFAULT_SESSION_REDIS_DB),
            },
        )
        return store
    except Exception as exc:
        LOGGER.warning(
            "session store: Redis unreachable (%s), falling back to in-memory",
            exc,
        )
        record_session_store_fallback()
        return _build_memory_store(ttl)


# Module-level singleton — imported by session_service.py.
SESSION_STORE = build_session_store()
