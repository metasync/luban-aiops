from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from agent_service.schemas.api import SessionRecord


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionRecord] = {}

    def ensure_session(
        self,
        session_id: str | None,
        user_id: str | None,
    ) -> SessionRecord:
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        record = SessionRecord(
            session_id=session_id or f"ses-{uuid4()}",
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
        )
        self._sessions[record.session_id] = record
        return record

    def get_session(self, session_id: str) -> SessionRecord | None:
        return self._sessions.get(session_id)


SESSION_STORE = SessionStore()
