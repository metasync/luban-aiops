"""Incident and triage-report models bound to the shared contracts (SPEC-015 R-1).

incident-service builds one incident envelope per normalized alert group or
manual report and stores/serves it verbatim. The triage report is validated
against this model before storage — a report that does not conform to
``triage-report.schema.json`` is never persisted.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class IncidentSource(str, Enum):
    ALERTMANAGER = "alertmanager"
    MANUAL = "manual"


class IncidentSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class IncidentStatus(str, Enum):
    NEW = "new"
    TRIAGING = "triaging"
    TRIAGED = "triaged"
    TRIAGE_FAILED = "triage_failed"
    RESOLVED = "resolved"


class Incident(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str = Field(pattern=r"^inc-[a-z0-9-]+$")
    fingerprint: str = Field(min_length=1, max_length=256)
    source: IncidentSource
    severity: IncidentSeverity
    status: IncidentStatus
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=2000)
    labels: dict[str, str] = Field(default_factory=dict)
    reported_by: str | None = Field(default=None, max_length=200)
    session_id: str | None = Field(default=None, max_length=200)
    triage_raw: str | None = Field(default=None, max_length=65536)
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None

    def envelope(self) -> dict:
        """The contract envelope served to callers (incident.schema.json)."""
        return self.model_dump(mode="json", exclude_none=True)

    def list_entry(self) -> dict:
        """Envelope minus summary — the list representation."""
        return self.model_dump(
            mode="json", exclude={"summary"}, exclude_none=True
        )


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=400)


class NextStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=400)
    priority: str = Field(pattern=r"^(high|medium|low)$")


class TriageReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str = Field(pattern=r"^inc-[a-z0-9-]+$")
    summary: str = Field(min_length=1, max_length=2000)
    severity_assessment: IncidentSeverity
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=20)
    # Item bounds mirror triage-report.schema.json exactly so the model
    # never accepts what the canonical contract rejects.
    hypotheses: list[Annotated[str, Field(min_length=1, max_length=400)]] = (
        Field(default_factory=list, max_length=5)
    )
    next_steps: list[NextStep] = Field(default_factory=list, max_length=10)
    skills_cited: list[Annotated[str, Field(min_length=1, max_length=256)]] = (
        Field(default_factory=list, max_length=10)
    )
    session_id: str = Field(max_length=200)
    generated_at: datetime
    generated_by: str = Field(min_length=1, max_length=200)

    def envelope(self) -> dict:
        """The contract envelope served to callers (triage-report.schema.json)."""
        return self.model_dump(mode="json", exclude_none=True)


class ConnectorDispatch(BaseModel):
    """Outcome of pushing a triage report through one connector (R-5)."""

    model_config = ConfigDict(extra="forbid")

    connector: str
    status: str = Field(pattern=r"^(delivered|failed)$")
    reference: str | None = None
    error: str | None = None
    created_at: datetime
