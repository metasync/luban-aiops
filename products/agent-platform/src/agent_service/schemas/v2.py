"""Pydantic models for the platform-owned agent-service contract (v2).

These models are the single source of truth for the /api/v2/ surface.
They are validated against the JSON Schema files in shared/shared-contracts/schemas/agent-*.schema.json.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

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
    """SSE frame payload conforming to agent-stream-event.schema.json (v3).

    v3 adds tool_call/tool_result frames for evidence panel rendering
    (SPEC-011 R-1).
    """

    type: Literal[
        "message_start",
        "message_delta",
        "message_end",
        "error",
        "tool_call",
        "tool_result",
    ]
    session_id: str
    request_id: str
    delta: str | None = None
    message: str | None = None
    tool_name: str | None = None
    call_id: str | None = None
    parameters: dict[str, Any] | None = None
    status: Literal["success", "error", "denied"] | None = None
    evidence: dict[str, Any] | None = None
    data_summary: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


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
    session_store: str | None = None
    session_store_ready: bool | None = None
