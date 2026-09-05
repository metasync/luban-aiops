"""Pydantic models for the platform-owned agent-service contract (v2).

These models are the single source of truth for the /api/v2/ surface.
They are validated against the JSON Schema files in shared/shared-contracts/schemas/agent-*.schema.json.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

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
    "DocumentCreateRequest",
    "SessionTitleUpdateRequest",
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
    """SSE frame payload conforming to agent-stream-event.schema.json (v9).

    v3 added tool_call/tool_result frames for evidence panel rendering
    (SPEC-011 R-1). v4 adds confirmation_request/confirmation_result frames
    for HITL confirmation bridging (SPEC-020 R-1). v5 adds the optional
    ``data`` field on tool_result frames: the full tool payload within the
    stream size cap, so the portal can show the complete output of a run.
    v6 adds the optional ``risk_level`` on confirmation ``pending_calls``
    entries so the portal can flag mutating batches (SPEC-021 R-3).
    v8 adds the optional ``action`` on ``pending_calls`` entries so the
    confirm bridge can evaluate the parked batch against the policy
    bundle (SPEC-030 R-3). v9 adds the optional ``flow_summary`` on
    confirmation_request frames carrying the bound browser-flow headline
    (SPEC-051 R-6) so the live operator card renders the same workflow
    framing the durable record gives the approver inbox.
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
    # SPEC-051 R-6: card-level browser-flow headline (skill intent, origin,
    # risk_class) on confirmation_request frames. Mirrors the durable
    # record's flow_summary so the live operator card renders the same
    # workflow framing as the approver inbox; absent for non-browser cards.
    flow_summary: dict[str, Any] | None = None
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


class ExecutionRecordModel(BaseModel):
    """Signed execution lifecycle row for one approved parked call (SPEC-037 R-4).

    Rides the session-detail surface under its confirmation card:
    request/receipt status plus the digest-match result, so decided
    cards can render a read-only receipt badge. ``receipt`` is the
    signed receipt envelope (execution-receipt.schema.json) once the
    execution closed; rejected executions carry no receipt.
    """

    execution_id: str
    call_id: str
    confirm_id: str
    session_id: str
    tool_name: str
    status: Literal["requested", "succeeded", "failed", "timeout", "rejected"] = (
        "requested"
    )
    requested_at: str | None = None
    completed_at: str | None = None
    digest_match: bool | None = None
    reject_reason: str | None = None
    receipt: dict[str, Any] | None = None


class ConfirmationRecordModel(BaseModel):
    """Durable confirmation lifecycle record (SPEC-031 R-1/R-2).

    Rides the session-detail surface (owner transcript cards) and the
    inbox surface (approver view). ``pending_calls`` follows the parked
    payload shape of the confirmation_request frame; decided records
    carry the decider and outcome so cards render read-only with
    attribution after any re-login.
    """

    confirm_id: str
    session_id: str
    owner_user_id: str
    session_title: str | None = None
    pending_calls: list[dict[str, Any]] = Field(default_factory=list)
    action: str | None = None
    # SPEC-033 R-2: additive parking-turn ordinal; null for records that
    # predate the column.
    turn_index: int | None = Field(default=None, ge=0)
    # SPEC-051 R-6: additive card-level browser-flow headline (skill intent,
    # origin, risk_class) captured at park time; null for non-browser cards
    # and for records that predate the column.
    flow_summary: dict[str, Any] | None = None
    status: Literal["pending", "approved", "denied", "expired"] = "pending"
    parked_at: str | None = None
    decider_user_id: str | None = None
    decision: str | None = None
    decided_at: str | None = None
    # SPEC-037 R-4: additive execution rows for this confirmation (one
    # per approved parked call); empty for pending/denied/expired records
    # and for decided rows that predate signed execution requests.
    executions: list[ExecutionRecordModel] = Field(default_factory=list)


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
    # SPEC-031 R-2: durable confirmation cards in park order, each in its
    # current state; decided cards stay visible and read-only. Null when
    # the record store is unreadable (degrades like evidence_turns).
    confirmations: list[ConfirmationRecordModel] | None = None


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
    # v0.23.4: tech-stack inventory for the portal's Settings table —
    # the frameworks and servers underneath the component, not the
    # component's own version (which follows the platform version).
    python_version: str | None = None
    fastapi_version: str | None = None
    agentscope_version: str | None = None
    session_store_version: str | None = None
    agent_state_version: str | None = None


# --- Operations document repository (SPEC-039) ---


class DocumentCreateRequest(BaseModel):
    """Creation request for a typed operations document (SPEC-039 R-1/R-3).

    The discriminator rides the request so each document type extends
    the enum, not the route. ``shift_summary`` ships in Phase 1;
    ``incident_report`` (SPEC-043) replaces the caller-supplied session
    list with exactly one caller-supplied incident id — the covered
    session is server-derived from the incident.
    """

    document_type: Literal["shift_summary", "incident_report"] = Field(
        description="Typed-document discriminator."
    )
    session_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "Covered sessions (bounded input) for shift_summary only. Own "
            "sessions contribute the full digest; foreign sessions "
            "(owner != requester) contribute metadata only, and only when "
            "the requester holds approvals:list. Must be empty for "
            "incident_report documents."
        ),
    )
    incident_id: str | None = Field(
        default=None,
        pattern=r"^inc-[a-z0-9-]+$",
        description=(
            "The covered incident for incident_report documents "
            "(SPEC-043 R-2): exactly one incident id, resolved against "
            "incident-service at creation. Must be absent for "
            "shift_summary documents."
        ),
    )
    label: str = Field(
        min_length=1,
        max_length=120,
        description="Owner-supplied human label for the document.",
    )
    include_prose: bool = Field(
        default=True,
        description=(
            "Request the generated handover narrative (SPEC-039 R-4, "
            "default since SPEC-040 R-2; pass false to opt out). The "
            "prompt sees the digest JSON only and must stay anchored "
            "to it; a generation failure yields a digest-only document "
            "(prose_status=failed)."
        ),
    )

    @model_validator(mode="after")
    def _check_type_fields(self) -> "DocumentCreateRequest":
        """Cross-type field mixing is a structural 400 (SPEC-043 R-2)."""
        if self.document_type == "shift_summary":
            if self.incident_id is not None:
                raise ValueError(
                    "incident_id is only valid for incident_report documents"
                )
            if not self.session_ids:
                raise ValueError(
                    "shift_summary documents require at least one session id"
                )
        else:
            if self.incident_id is None:
                raise ValueError(
                    "incident_report documents require exactly one incident id"
                )
            if self.session_ids:
                raise ValueError(
                    "incident_report coverage is the incident's own linked "
                    "session; session_ids must be empty"
                )
        return self


class SessionTitleUpdateRequest(BaseModel):
    """Owner session rename (SPEC-039 R-7): 1–80 chars after trimming."""

    title: str = Field(min_length=1, max_length=80)
