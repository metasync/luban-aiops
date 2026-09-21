"""Audit event envelope bound to audit-event.schema.json (SPEC-013 R-1).

Emitters mint ``event_id`` and ``occurred_at``; the audit service stores and
returns envelopes verbatim (no field rewriting between ingest and query).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EventType = Literal[
    "tool_invoked",
    "policy_decision",
    "token_exchange",
    "session_created",
    "session_deleted",
    "chat_started",
    "chat_completed",
    "confirmation_decided",
    "incident_triaged",
    "skill_searched",
    "skill_retrieved",
    "skills_synced",
    "execution_requested",
    "execution_completed",
    "execution_rejected",
    "document_created",
    "document_published",
    "document_read",
    "skill_draft_generated",
    "incident_skill_draft_generated",
    # SPEC-055 R-4: deterministic graduation of a session's captured authoring
    # trace into an executable-flow skill draft (blast-radius re-validated,
    # never auto-published).
    "skill_graduated",
    # SPEC-062 R-3/R-4: a generated secret reached a human (portal-copy
    # redemption or SMTP accept). Carries delivery_id/channel/recipient, never
    # the value.
    "secret_delivered",
]

Outcome = Literal["allow", "deny", "success", "error"]


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    occurred_at: datetime
    event_type: EventType
    service: str
    request_id: str
    subject: str | None = None
    username: str | None = None
    actor: str | None = None
    roles: list[str] | None = None
    session_id: str | None = None
    outcome: Outcome
    details: dict = Field(default_factory=dict)


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[AuditEvent] = Field(min_length=1)


class AuditQuery(BaseModel):
    """Filter set for the query API (R-4); empty fields mean no constraint.

    ``outcome`` (SPEC-047 R-1) is additive: it filters on the envelope
    ``outcome`` column verbatim against the shared schema enum, so the
    Summary/Export drill-down can narrow to a terminal result.
    """

    username: str | None = None
    session_id: str | None = None
    request_id: str | None = None
    event_type: str | None = None
    service: str | None = None
    outcome: Outcome | None = None
    since: datetime | None = None
    until: datetime | None = None
