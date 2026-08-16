"""Deterministic keyword scoring shared by both store backends (SPEC-014 R-3).

A single pure ``score`` function keeps in-memory and Postgres retrieval
byte-identical: Postgres pre-filters candidates with ``to_tsvector`` and
re-ranks them here. Weighting is fixed and explainable: a query token found
in the title scores 3, in the tags scores 2, and each body occurrence scores
1 (saturating at ``BODY_OCCURRENCE_CAP`` so long documents cannot drown out
title/tag matches). Zero-score records are excluded; equal scores break ties
by ``skill_id`` ascending.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from skills_hub.schemas.skill import Skill

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
TITLE_WEIGHT = 3.0
TAG_WEIGHT = 2.0
BODY_WEIGHT = 1.0
BODY_OCCURRENCE_CAP = 5
EXCERPT_MAX_CHARS = 400


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens — the only matching unit in this slice."""
    return TOKEN_PATTERN.findall(text.lower())


def score(query: str, skill: Skill) -> float:
    """Deterministic relevance score; 0.0 means no match at all."""
    query_tokens = tokenize(query)
    if not query_tokens:
        return 0.0
    title_tokens = set(tokenize(skill.title))
    tag_tokens = {
        token for tag in skill.tags or [] for token in tokenize(tag)
    }
    body_counts = Counter(tokenize(skill.body))
    total = 0.0
    for token in query_tokens:
        if token in title_tokens:
            total += TITLE_WEIGHT
        if token in tag_tokens:
            total += TAG_WEIGHT
        occurrences = body_counts.get(token, 0)
        if occurrences:
            total += BODY_WEIGHT * min(occurrences, BODY_OCCURRENCE_CAP)
    return total


def excerpt(query: str, skill: Skill) -> str:
    """Bounded snippet around the first matched body region (≤ 400 chars).

    Falls back to the description head when the match lives only in
    title/tags — excerpts must never exceed the cap regardless of source.
    """
    query_tokens = tokenize(query)
    body_lower = skill.body.lower()
    first_pos = -1
    for token in query_tokens:
        pos = body_lower.find(token)
        if pos != -1 and (first_pos == -1 or pos < first_pos):
            first_pos = pos
    if first_pos == -1:
        return skill.description[:EXCERPT_MAX_CHARS]
    window = skill.body[first_pos : first_pos + EXCERPT_MAX_CHARS]
    if len(window) == EXCERPT_MAX_CHARS and first_pos + len(window) < len(
        skill.body
    ):
        window = window.rstrip() + "…"
    return window


@dataclass(frozen=True)
class SearchHit:
    skill: Skill
    score: float
    excerpt: str


def rank(query: str, records: list[Skill], limit: int) -> list[SearchHit]:
    """Score, filter zero scores, order by (-score, skill_id), cap at limit."""
    hits = []
    for skill in records:
        value = score(query, skill)
        if value <= 0.0:
            continue
        hits.append(
            SearchHit(skill=skill, score=value, excerpt=excerpt(query, skill))
        )
    hits.sort(key=lambda hit: (-hit.score, hit.skill.skill_id))
    return hits[:limit]
