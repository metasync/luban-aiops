"""Skill envelope bound to skill.schema.json (SPEC-014 R-1).

skills-hub builds one envelope per validated Markdown document during source
sync and stores/serves it verbatim. ``body`` travels in store records and
full-record responses; list responses omit it and search responses excerpt it.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SkillStep(BaseModel):
    """One ordered replay step of an ``executable_flow`` skill (SPEC-055 R-3).

    ``args`` carries the step's tool arguments; credential values are
    credential-set references, never literals (replay resolves them via
    ``web.fill_credential``). ``expect`` is an optional post-condition and a
    display/replay aid only, never a security input.
    """

    model_config = ConfigDict(extra="forbid")

    tool: str = Field(min_length=1, max_length=128)
    args: dict = Field(default_factory=dict)
    expect: str | None = Field(default=None, max_length=500)


class Skill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str
    source_id: str
    source_path: str
    source_ref: str
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=500)
    tags: list[str] | None = None
    version: str | None = Field(default=None, max_length=64)
    source_url: str | None = Field(default=None, max_length=2048)
    # SPEC-049 R-3: optional web-check flow declaration. ``risk_class``
    # defaults to ``read`` for consumers when ``web_target`` is present
    # without it; the envelope stores the declaration verbatim.
    web_target: str | None = Field(default=None, max_length=2048)
    risk_class: str | None = Field(default=None, pattern="^(read|write)$")
    # SPEC-053 R-1: optional author-written intent for the flow's gated
    # mutating step, carried card-level on the flow_summary path and shown as
    # the confirmation card's lead decision line. Requires ``web_target``;
    # display-only (never a security input).
    flow_intent: str | None = Field(default=None, max_length=200)
    # SPEC-055 R-3: optional executable-flow class. ``kind`` discriminates a
    # knowledge skill (absent/``knowledge``) from an ``executable_flow`` that
    # carries a machine-readable replay step list; ``steps`` is that ordered
    # list, present only for executable flows. Additive — a knowledge skill
    # omits both and validates exactly as before.
    kind: str | None = Field(default=None, pattern="^(knowledge|executable_flow)$")
    steps: list[SkillStep] | None = None
    updated_at: datetime
    body: str = Field(max_length=65536)

    def summary(self) -> dict:
        """Envelope minus body — the list/search hit representation."""
        return self.model_dump(mode="json", exclude={"body"}, exclude_none=True)
