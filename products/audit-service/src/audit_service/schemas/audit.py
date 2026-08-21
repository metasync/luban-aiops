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
    "chat_started",
    "chat_completed",
    "confirmation_decided",
    "incident_triaged",
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
    """Filter set for the query API (R-4); empty fields mean no constraint."""

    username: str | None = None
    session_id: str | None = None
    request_id: str | None = None
    event_type: str | None = None
    service: str | None = None
    since: datetime | None = None
    until: datetime | None = None
