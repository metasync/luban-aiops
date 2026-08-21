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
    "AgentChatConfirmRequest",
    "AgentChatResponse",
    "AgentStreamEvent",
    "AgentSession",
    "AgentSessionCreateRequest",
    "AgentRuntimeMetadata",
    "AgentHealth",
]


# --- Chat ---


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None
    response_schema: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional JSON-schema dict for kernel-validated structured "
            "output (SPEC-017 R-2); passed through unchanged."
        ),
    )


class AgentChatResponse(BaseModel):
    session_id: str
    request_id: str
    content: str
    status: Literal["ok", "partial", "error"] = "ok"
    structured_output: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Validated structured output when response_schema was supplied "
            "(SPEC-017 R-2); null when the turn produced none."
        ),
    )


class AgentChatConfirmRequest(BaseModel):
    """Body for ``POST /api/v2/chat/confirm`` (SPEC-020 R-1).

    Answers a parked kernel confirmation; the decision applies to every
    parked tool call (all-or-nothing). Identity stays in headers.
    """

    session_id: str = Field(min_length=1)
    confirm_id: str = Field(min_length=1)
    decision: Literal["approve", "deny"]


# --- Streaming ---


class AgentStreamEvent(BaseModel):
    """SSE frame payload conforming to agent-stream-event.schema.json (v5).

    v3 added tool_call/tool_result frames for evidence panel rendering
    (SPEC-011 R-1). v4 adds confirmation_request/confirmation_result frames
    for HITL confirmation bridging (SPEC-020 R-1). v5 adds the optional
    ``data`` field on tool_result frames: the full tool payload within the
    stream size cap, so the portal can show the complete output of a run.
    """

    type: Literal[
        "message_start",
        "message_delta",
        "message_end",
        "error",
        "tool_call",
        "tool_result",
        "confirmation_request",
        "confirmation_result",
    ]
    session_id: str
    request_id: str
    delta: str | None = None
    message: str | None = None
    confirm_id: str | None = None
    pending_calls: list[dict[str, Any]] | None = None
    tool_name: str | None = None
    call_id: str | None = None
    parameters: dict[str, Any] | None = None
    status: (
        Literal["success", "error", "denied", "approved", "expired", "interrupted"]
        | None
    ) = None
    evidence: dict[str, Any] | None = None
    data_summary: dict[str, Any] | None = None
    data: Any = None
    error: dict[str, Any] | None = None


# --- Sessions ---


class AgentSession(BaseModel):
    session_id: str
    user_id: str
    created_at: datetime
    status: Literal["active", "expired"] = "active"


class AgentSessionCreateRequest(BaseModel):
    """Optional body for ``POST /api/v2/sessions``.

    Omitting ``session_id`` keeps the historical server-generated id;
    supplying one creates a named dedicated session (SPEC-015 R-3 triage
    sessions). Identity stays in headers, never in bodies.
    """

    session_id: str | None = Field(default=None, min_length=1, max_length=128)


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
    agent_state: str | None = None
    agent_state_ready: bool | None = None
