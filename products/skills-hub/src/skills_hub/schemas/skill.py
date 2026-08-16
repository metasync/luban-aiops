"""Skill envelope bound to skill.schema.json (SPEC-014 R-1).

skills-hub builds one envelope per validated Markdown document during source
sync and stores/serves it verbatim. ``body`` travels in store records and
full-record responses; list responses omit it and search responses excerpt it.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
    updated_at: datetime
    body: str = Field(max_length=65536)

    def summary(self) -> dict:
        """Envelope minus body — the list/search hit representation."""
        return self.model_dump(mode="json", exclude={"body"}, exclude_none=True)
