from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SessionRecord(BaseModel):
    session_id: str
    user_id: str | None = None
    created_at: datetime
    status: str = "active"


class CreateSessionRequest(BaseModel):
    user_id: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None
    user_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    request_id: str
    response: str
    status: str = "ok"
