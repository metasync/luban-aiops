"""Session store with pluggable backends (SPEC-006).

Provides a Protocol-based interface so the service layer can work with
either an in-memory store (dev/CI) or a Redis-backed store (deployed).
Backend selection is driven by the ``SESSION_STORE_BACKEND`` env var.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable
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

    def create_session(self, user_id: str | None) -> SessionRecord: ...

    def get_session(self, session_id: str) -> SessionRecord | None: ...

    def list_sessions_by_user(self, user_id: str) -> list[SessionRecord]: ...

    def delete_session(self, session_id: str) -> bool: ...

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

    def create_session(self, user_id: str | None) -> SessionRecord:
        now = time.monotonic()
        self._purge_expired(now)
        record = SessionRecord(
            session_id=f"ses-{uuid4()}",
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
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

    def _user_key(self, user_id: str) -> str:
        return f"{_USER_SESSIONS_KEY_PREFIX}{user_id}"

    def _serialize(self, record: SessionRecord) -> str:
        return record.model_dump_json()

    def _deserialize(self, raw: bytes | str) -> SessionRecord | None:
        try:
            return SessionRecord.model_validate_json(raw)
        except Exception:
            return None

    def create_session(self, user_id: str | None) -> SessionRecord:
        record = SessionRecord(
            session_id=f"ses-{uuid4()}",
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
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
            return record
        except Exception:
            record_session_store_error("get")
            raise

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
            if record and record.user_id:
                self._client.zrem(self._user_key(record.user_id), session_id)
            return bool(deleted)
        except Exception:
            record_session_store_error("delete")
            raise

    def is_ready(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception:
            return False

    def __len__(self) -> int:
        # Count session keys only (exclude user sorted sets).
        try:
            keys = self._client.keys(f"{_SESSION_KEY_PREFIX}*")
            return len(keys)
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def build_session_store() -> SessionStore:
    """Create the session store based on environment configuration.

    Reads:
        SESSION_STORE_BACKEND: ``memory`` | ``redis`` (default ``memory``)
        SESSION_TTL_SECONDS: TTL for both backends (default 3600)
        SESSION_MAX_ENTRIES: max entries for in-memory backend (default 1000)
        SESSION_REDIS_HOST: Redis host (default ``127.0.0.1``)
        SESSION_REDIS_PORT: Redis port (default ``6379``)
        SESSION_REDIS_DB: Redis DB number (default ``1``)
    """
    backend = _env_str("SESSION_STORE_BACKEND", "memory")
    ttl = _env_float("SESSION_TTL_SECONDS", DEFAULT_SESSION_TTL_SECONDS)

    if backend == "memory":
        store = InMemorySessionStore(
            ttl_seconds=ttl,
            max_entries=_env_int("SESSION_MAX_ENTRIES", DEFAULT_SESSION_MAX_ENTRIES),
        )
        record_session_store_backend("memory")
        return store

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
        fallback = InMemorySessionStore(
            ttl_seconds=ttl,
            max_entries=_env_int("SESSION_MAX_ENTRIES", DEFAULT_SESSION_MAX_ENTRIES),
        )
        record_session_store_backend("memory")
        return fallback


# Module-level singleton — imported by session_service.py.
SESSION_STORE = build_session_store()
