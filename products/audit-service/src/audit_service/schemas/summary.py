"""Audit summary contract (SPEC-046 R-1).

Deterministic envelope-column aggregates over the stored trail. The store
returns the ``AuditSummary`` dataclass (both backends produce it); the route
renders it through the pydantic response model, which binds to
``audit-summary.schema.json`` (SPEC-046 R-4). Aggregation touches envelope
columns only — never the ``details`` payload (Q-3).
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from audit_service.schemas.audit import AuditQuery

# SPEC-037 decision-to-execution chain, in the order governance reads it:
# a confirmation decision, the execution it authorized, and the terminal
# outcome. Counts are zero when the event type is absent from the window.
DECISION_CHAIN_TYPES = (
    "confirmation_decided",
    "execution_requested",
    "execution_completed",
    "execution_rejected",
)

# ``top_actors`` reports the busiest registered usernames, capped so the
# section stays a glanceable table regardless of trail volume.
TOP_ACTORS_LIMIT = 10


@dataclass(frozen=True)
class SummaryBucket:
    """One name/count pair; sections sort count desc, then name asc."""

    name: str
    count: int


@dataclass(frozen=True)
class DecisionChain:
    confirmation_decided: int = 0
    execution_requested: int = 0
    execution_completed: int = 0
    execution_rejected: int = 0


@dataclass(frozen=True)
class AuditSummary:
    total_events: int
    window: dict[str, str]
    by_event_type: tuple[SummaryBucket, ...]
    by_outcome: tuple[SummaryBucket, ...]
    by_service: tuple[SummaryBucket, ...]
    top_actors: tuple[SummaryBucket, ...]
    decision_chain: DecisionChain


def window_echo(filters: AuditQuery) -> dict[str, str]:
    """Echo of the applied filters; unset (None) fields are omitted."""
    echo: dict[str, str] = {}
    if filters.username:
        echo["username"] = filters.username
    if filters.session_id:
        echo["session_id"] = filters.session_id
    if filters.request_id:
        echo["request_id"] = filters.request_id
    if filters.event_type:
        echo["event_type"] = filters.event_type
    if filters.service:
        echo["service"] = filters.service
    if filters.outcome:
        echo["outcome"] = filters.outcome
    if filters.since:
        echo["since"] = filters.since.isoformat()
    if filters.until:
        echo["until"] = filters.until.isoformat()
    return echo


class SummaryBucketModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    count: int


class DecisionChainModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_decided: int
    execution_requested: int
    execution_completed: int
    execution_rejected: int


class AuditSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_events: int
    window: dict[str, str]
    by_event_type: list[SummaryBucketModel]
    by_outcome: list[SummaryBucketModel]
    by_service: list[SummaryBucketModel]
    top_actors: list[SummaryBucketModel]
    decision_chain: DecisionChainModel


def to_response(summary: AuditSummary) -> AuditSummaryResponse:
    """Render the store dataclass through the contract-bound model."""
    return AuditSummaryResponse(
        total_events=summary.total_events,
        window=summary.window,
        by_event_type=[
            SummaryBucketModel(name=b.name, count=b.count)
            for b in summary.by_event_type
        ],
        by_outcome=[
            SummaryBucketModel(name=b.name, count=b.count)
            for b in summary.by_outcome
        ],
        by_service=[
            SummaryBucketModel(name=b.name, count=b.count)
            for b in summary.by_service
        ],
        top_actors=[
            SummaryBucketModel(name=b.name, count=b.count)
            for b in summary.top_actors
        ],
        decision_chain=DecisionChainModel(
            confirmation_decided=summary.decision_chain.confirmation_decided,
            execution_requested=summary.decision_chain.execution_requested,
            execution_completed=summary.decision_chain.execution_completed,
            execution_rejected=summary.decision_chain.execution_rejected,
        ),
    )
