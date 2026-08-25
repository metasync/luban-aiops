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
    "EvidenceTurn",
    "AgentSessionSummary",
    "AgentSessionList",
    "AgentSessionCreateRequest",
    "AgentModelInfo",
    "AgentModelCatalog",
    "AgentRuntimeMetadata",
    "AgentHealth",
]


# --- Chat ---


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None
    input_modality: Literal["text", "voice"] = Field(
        default="text",
        description=(
            "Voice-readiness contract (SPEC-022 R-2): modality is metadata "
            "only — it never changes policy, auto-allow, or HITL outcomes, "
            "and it can never approve or deny a parked confirmation."
        ),
    )
    response_schema: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional JSON-schema dict for kernel-validated structured "
            "output (SPEC-017 R-2); passed through unchanged."
        ),
    )
    model: str | None = Field(
        default=None,
        description=(
            "Optional model selection (SPEC-024 R-3): a model id from "
            "GET /api/v2/models. Resolution order is request model > "
            "session-pinned model > deploy-time default; an unknown id is "
            "refused with 4xx (fail-closed). Metadata only — it never "
            "changes policy or HITL outcomes."
        ),
    )
    read_only: bool = Field(
        default=False,
        description=(
            "Restrict this turn's toolkit to read-level tools. Intended "
            "for automated diagnostic turns (incident triage) that must "
            "never invoke — or park on — a mutating tool. Tool-surface "
            "selection only: it never changes policy or HITL outcomes."
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
    model: str | None = Field(
        default=None,
        description=(
            "Model id that resolved for this turn (SPEC-024 R-3/R-4); "
            "null when no model is configured."
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
    """SSE frame payload conforming to agent-stream-event.schema.json (v8).

    v3 added tool_call/tool_result frames for evidence panel rendering
    (SPEC-011 R-1). v4 adds confirmation_request/confirmation_result frames
    for HITL confirmation bridging (SPEC-020 R-1). v5 adds the optional
    ``data`` field on tool_result frames: the full tool payload within the
    stream size cap, so the portal can show the complete output of a run.
    v6 adds the optional ``risk_level`` on confirmation ``pending_calls``
    entries so the portal can flag mutating batches (SPEC-021 R-3).
    v8 adds the optional ``action`` on ``pending_calls`` entries so the
    confirm bridge can evaluate the parked batch against the policy
    bundle (SPEC-030 R-3).
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
    # SPEC-024 R-3/R-4: model id that resolved for the turn; present on
    # message_end frames (stream schema v7) so downstream tees can attribute
    # the turn.
    model: str | None = None


# --- Sessions ---


class EvidenceTurn(BaseModel):
    """Persisted tool-evidence group for one assistant turn (SPEC-025 R-2).

    Frames follow the tool_call/tool_result shapes of
    agent-stream-event.schema.json; the evidence store may add a
    ``truncated`` marker where a size cap replaced a payload (SPEC-025
    R-1), never silently drop a frame.
    """

    turn_index: int = Field(ge=0)
    request_id: str
    created_at: str | None = None
    frames: list[dict[str, Any]] = Field(default_factory=list)


class AgentSession(BaseModel):
    session_id: str
    user_id: str
    created_at: datetime
    status: Literal["active", "expired"] = "active"
    # SPEC-022 R-1 workspace fields: server-minted title (null for
    # pre-existing sessions), last activity marker, parked-confirmation
    # badge, and the best-effort transcript reconstructed from the kernel
    # state snapshot (transcript_available=false when unrecoverable).
    title: str | None = None
    last_active_at: datetime | None = None
    pending_confirmation: bool = False
    transcript_available: bool = False
    transcript: list[dict[str, str]] = Field(default_factory=list)
    # SPEC-024 R-3: model id pinned on the session by the most recent turn;
    # null when the session never selected a model.
    model: str | None = None
    # SPEC-025 R-2: persisted tool evidence grouped by assistant turn.
    # Empty list when the session stored none; null when the evidence
    # store is unreadable (degrades like transcript_available=false).
    evidence_turns: list[EvidenceTurn] | None = None


class AgentSessionSummary(BaseModel):
    """Compact list-view row for ``GET /api/v2/sessions`` (SPEC-022 R-1)."""

    session_id: str
    title: str | None = None
    created_at: datetime
    last_active_at: datetime | None = None
    pending_confirmation: bool = False


class AgentSessionList(BaseModel):
    """Envelope for ``GET /api/v2/sessions`` (capped, most-recent first)."""

    sessions: list[AgentSessionSummary]


class AgentSessionCreateRequest(BaseModel):
    """Optional body for ``POST /api/v2/sessions``.

    Omitting ``session_id`` keeps the historical server-generated id;
    supplying one creates a named dedicated session (SPEC-015 R-3 triage
    sessions). Identity stays in headers, never in bodies.
    """

    session_id: str | None = Field(default=None, min_length=1, max_length=128)


# --- Model discovery (SPEC-024 R-2) ---


class AgentModelInfo(BaseModel):
    """Discovery-safe model entry: no credentials, no base URLs."""

    id: str
    label: str
    provider: Literal["dashscope", "deepseek", "openai", "luban"]
    default: bool


class AgentModelCatalog(BaseModel):
    """Envelope for ``GET /api/v2/models`` (credential-gated catalog)."""

    models: list[AgentModelInfo]
    default: str | None = None


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
