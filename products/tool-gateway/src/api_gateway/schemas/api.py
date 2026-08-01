from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    """Mirror of `shared-contracts/schemas/chat-request.schema.json`."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)
    session_id: str | None = None
    user_id: str | None = None
    request_id: str | None = None


class ChatResponse(BaseModel):
    """Mirror of `shared-contracts/schemas/agent-chat-response.schema.json` (v2)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    request_id: str
    content: str
    status: Literal["ok", "partial", "error"] = "ok"


class CreateSessionRequest(BaseModel):
    """Session creation body accepted by the gateway and forwarded to agent-service."""

    model_config = ConfigDict(extra="forbid")

    user_id: str | None = None


class SessionRecord(BaseModel):
    """Mirror of `shared-contracts/schemas/agent-session.schema.json` (v2)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    user_id: str
    created_at: datetime
    status: Literal["active", "expired"] = "active"


class IdentityContext(BaseModel):
    """Mirror of `shared-contracts/schemas/identity-context.schema.json`."""

    model_config = ConfigDict(extra="forbid")

    subject: str
    username: str
    email: str | None = None
    groups: list[str] = Field(default_factory=list)
    roles: list[str]
    actor: str | None = None
