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
    """SSE frame payload conforming to agent-stream-event.schema.json (v11).

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
    framing the durable record gives the approver inbox. v10 adds the
    optional ``flow_intent`` inside ``flow_summary`` (SPEC-053 R-2): the
    skill-authored sentence describing what the flow's gated mutating step
    achieves, rendered as the card's lead decision line. Additive and
    display-only — ``flow_summary`` stays ``dict[str, Any]`` and the frame
    shape is unchanged for skills that omit it. v11 adds the optional
    ``approval_kind`` on confirmation_request frames declaring whether the
    parked batch is a bound browser ``flow`` or an individually-approved
    ``action`` (SPEC-054 R-1), so a card's kind is stated rather than inferred
    from ambient session state, plus an optional display-only ``change_request``
    projection riding each ``pending_calls`` entry (SPEC-054 R-3) so an action
    card reads as a secret-masked change request. Both are additive and
    display-only; a client that ignores them renders today's card.
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
    # SPEC-054 R-1: the parked batch's declared kind on confirmation_request
    # frames — ``"flow"`` (a bound browser web-check flow, one gate per
    # SPEC-051) or ``"action"`` (an individually-approved mutating call).
    # Derived at park time from the batch, never from ambient session state;
    # ``flow_summary`` is present iff this is ``"flow"``. Display-driving only
    # (the signed envelope carries its own provenance, ADR-0010). Absent for
    # clients predating v11, which fall back to today's tool-level rendering.
    approval_kind: Literal["flow", "action"] | None = None
    # SPEC-051 R-6: card-level browser-flow headline (skill intent, origin,
    # risk_class) on confirmation_request frames; SPEC-053 R-2 adds the
    # author-written ``flow_intent`` decision line inside it. Mirrors the
    # durable record's flow_summary so the live operator card renders the same
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
    # SPEC-054 R-1: additive declared kind of the parked batch (``flow`` or
    # ``action``), captured at park time so a replayed card declares its own
    # kind rather than inferring it; null for records that predate the column.
    approval_kind: Literal["flow", "action"] | None = None
    # SPEC-054 R-4: additive top-line card message, persisted so every surface
    # rendering from this record (approver inbox, re-loaded owner transcript)
    # shows the same message the live card did; null for records that predate
    # the column, which degrade to no message line (never an empty artifact).
    message: str | None = None
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

    ``skill_target`` (SPEC-055 R-4) opens the session as a
    develop-as-you-go session: naming the web target it will work against
    *at birth* is what makes that target an authorization scope rather
    than a claim fitted to the trace afterwards, because no mutation can
    have been captured yet. Shaped exactly like the standalone
    declaration's — origin and path kept, any query or embedded
    credentials dropped — since both paths go through one validator.
    Bounded by the skill contract's own ``web_target`` maxLength, so
    anything accepted here can always be emitted into a graduated draft.
    """

    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    skill_target: str | None = Field(default=None, min_length=1, max_length=2048)


# --- Skill graduation (SPEC-055 R-4) ---


class SkillTargetDeclareRequest(BaseModel):
    """Body for ``POST /api/v2/sessions/{session_id}/skill-target``.

    The web target an operator names when opening a skill-development
    session — declared *before* the first mutation, so it is the
    authorization scope the session's captured steps are corroborated
    against, not a post-hoc claim about the past. Stored as origin and
    path (the operator's path narrowing is part of the scope and must
    survive into the draft's ``web_target``) with any query, fragment and
    ``user:password@`` dropped, and capped at the skill contract's own
    ``web_target`` bound, so a declared target can always be emitted.
    """

    target: str = Field(min_length=1, max_length=2048)


class SkillTargetDeclaration(BaseModel):
    """The target actually in force for one session's graduation.

    ``target`` is the *effective* value, not an echo of the request: the
    first declaration wins, so a second call reports the scope already set.
    A UI that showed the request back would let an operator believe they had
    moved a scope they cannot move.

    ``already_declared`` means precisely that a target *other than the one
    requested* is in force — not that a declaration pre-existed, which the
    field cannot tell the caller and does not try to. Re-declaring the same
    scope is a no-op that reads as success, so an operator confirming a
    target they already set is not told they were too late.
    """

    session_id: str
    target: str
    already_declared: bool


class SkillGraduationResponse(BaseModel):
    """One session's graduated executable-flow draft (SPEC-055 R-4).

    Field-compatible with the SPEC-044 draft response (``markdown``, ``mode``,
    ``validation``, ``suggested_filename``) so the portal's shared preview
    modal serves both, with three additions that only a graduation can report:

    ``mode`` is ``graduated`` rather than ``generated`` or ``skeleton`` — no
    model was involved, which is the property a reviewer of an *executable*
    artifact most needs to see, and there is no skeleton to fall back to
    because a trace either re-validates or it does not.

    ``step_count`` is the number of replay steps in the draft, i.e. the number
    of approved mutations the session captured. ``web_target`` is the declared
    scope the draft binds a replay to, and is ``None`` for a flow with no
    browser step, which needs none and gets none rather than a target it would
    never use.

    ``declaration`` reports where the declaration sits relative to the first
    captured step — ``preceded`` (an authorization scope the session acted
    under), ``postdated`` (a scope fitted to a trace that had already begun)
    or ``indeterminate`` (both stamps are second-precision, so a same-second
    declaration cannot be ordered). It is a report, never a gate: corroboration
    of every observed origin against the declared one is the control, and a
    hard ordering gate would add friction without adding safety.
    """

    markdown: str
    mode: str
    validation: str
    suggested_filename: str
    step_count: int
    web_target: str | None
    declaration: str


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
