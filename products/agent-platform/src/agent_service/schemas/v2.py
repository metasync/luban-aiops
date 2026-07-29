"""Pydantic models for the platform-owned agent-service contract (v2).

These models are the single source of truth for the /api/v2/ surface.
They are validated against the JSON Schema files in shared/shared-contracts/schemas/agent-*.schema.json.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "AgentChatRequest",
    "AgentChatResponse",
    "AgentStreamEvent",
    "AgentSession",
    "AgentRuntimeMetadata",
    "AgentHealth",
]


# --- Chat ---


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None


class AgentChatResponse(BaseModel):
    session_id: str
    request_id: str
    content: str
    status: Literal["ok", "partial", "error"] = "ok"


# --- Streaming ---


class AgentStreamEvent(BaseModel):
    type: Literal["message_start", "message_delta", "message_end", "error"]
    session_id: str
    request_id: str
    delta: str | None = None
    message: str | None = None


# --- Sessions ---


class AgentSession(BaseModel):
    session_id: str
    user_id: str
    created_at: datetime
    status: Literal["active", "expired"] = "active"


# --- Runtime metadata ---


class AgentRuntimeMetadata(BaseModel):
    runtime_mode: str
    runtime_state: Literal["ready", "not_configured", "provider_error"]
    provider: str
    model_name: str | None = None
    hint: str | None = None
    last_error: str | None = None


# --- Health ---


class AgentHealth(BaseModel):
    status: Literal["ready", "not_ready"]
    runtime_mode: str
    runtime_state: Literal["ready", "not_configured", "provider_error"] | None = None
    provider: str | None = None
    configured: bool
