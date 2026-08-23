from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    """Mirror of `shared-contracts/schemas/chat-request.schema.json`."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)
    session_id: str | None = None
    user_id: str | None = None
    request_id: str | None = None
    # SPEC-022 R-2 voice-readiness: metadata only — never a privilege.
    input_modality: Literal["text", "voice"] = "text"


class ChatConfirmRequest(BaseModel):
    """Mirror of `shared-contracts/schemas/chat-confirm.schema.json` (SPEC-020)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    confirm_id: str = Field(min_length=1)
    decision: Literal["approve", "deny"]


class ChatResponse(BaseModel):
    """Mirror of `shared-contracts/schemas/agent-chat-response.schema.json` (v2)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    request_id: str
    content: str
    status: Literal["ok", "partial", "error"] = "ok"
    # Kernel-validated structured output (SPEC-017 R-2); null when the turn
    # requested no response schema. Relayed verbatim from agent-service.
    structured_output: dict[str, Any] | None = None


class CreateSessionRequest(BaseModel):
    """Session creation body accepted by the gateway and forwarded to agent-service."""

    model_config = ConfigDict(extra="forbid")

    user_id: str | None = None


class ReportIncidentRequest(BaseModel):
    """Manual incident report (SPEC-015); mirrored to incident-service."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=2000)
    severity: Literal["critical", "warning", "info"] = "warning"
    labels: dict[str, str] = Field(default_factory=dict)


class SessionRecord(BaseModel):
    """Mirror of `shared-contracts/schemas/agent-session.schema.json` (v2)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    user_id: str
    created_at: datetime
    status: Literal["active", "expired"] = "active"
    # SPEC-022 R-1 workspace fields; null/empty for pre-SPEC-022 sessions.
    title: str | None = None
    last_active_at: datetime | None = None
    pending_confirmation: bool = False
    transcript_available: bool = False
    transcript: list[dict[str, str]] = Field(default_factory=list)
    # SPEC-025 R-2: persisted tool evidence grouped by assistant turn;
    # relayed verbatim (empty list = none stored, null = store unreadable).
    evidence_turns: list[dict[str, Any]] | None = None


class IdentityContext(BaseModel):
    """Mirror of `shared-contracts/schemas/identity-context.schema.json`."""

    model_config = ConfigDict(extra="forbid")

    subject: str
    username: str
    email: str | None = None
    groups: list[str] = Field(default_factory=list)
    roles: list[str]
    actor: str | None = None


class PolicyMatrixResponse(BaseModel):
    """Mirror of `shared-contracts/schemas/policy-matrix.schema.json` (SPEC-019 R-2)."""

    model_config = ConfigDict(extra="forbid")

    version: int
    source: Literal["configured", "packaged-default"]
    scope: Literal["full", "own"]
    roles: list[str]
    actions: list[str]
    matrix: dict[str, dict[str, bool]]
