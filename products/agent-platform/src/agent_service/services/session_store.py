from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from uuid import uuid4

from agent_service.schemas.api import SessionRecord

DEFAULT_SESSION_TTL_SECONDS = 3600.0
DEFAULT_SESSION_MAX_ENTRIES = 1000


class SessionStore:
    """In-memory session store with TTL and max-entry eviction.

    Single-replica and non-persistent by design; see the product README
    for the limitations of the transitional runtime.
    """

    def __init__(
        self,
        ttl_seconds: float = DEFAULT_SESSION_TTL_SECONDS,
        max_entries: int = DEFAULT_SESSION_MAX_ENTRIES,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._sessions: dict[str, SessionRecord] = {}
        self._last_accessed: dict[str, float] = {}

    @classmethod
    def from_env(cls) -> "SessionStore":
        return cls(
            ttl_seconds=float(
                os.getenv("SESSION_TTL_SECONDS", str(DEFAULT_SESSION_TTL_SECONDS))
            ),
            max_entries=int(
                os.getenv("SESSION_MAX_ENTRIES", str(DEFAULT_SESSION_MAX_ENTRIES))
            ),
        )

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

    def __len__(self) -> int:
        return len(self._sessions)


SESSION_STORE = SessionStore.from_env()
