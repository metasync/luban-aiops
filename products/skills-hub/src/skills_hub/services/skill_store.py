"""Skill store strategy (SPEC-014 R-2/R-3, SPEC-013 strategy-pattern precedent).

``build_skill_store`` selects the backend from ``SKILLS_STORE_BACKEND``:
``memory`` for tests/dev, ``postgres`` for deployed environments. Records
carry ``source_id`` so per-source replacement is exact, and both backends
delegate ranking to the shared scorer so ordering is byte-identical.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, Protocol, Sequence

from skills_hub.core.config import SkillsSettings
from skills_hub.schemas.skill import Skill
from skills_hub.services.scoring import SearchHit, rank, tokenize

LOGGER = logging.getLogger(__name__)


class StoreError(Exception):
    """Raised when a store operation cannot be completed."""


def _tag_matches(skill: Skill, tag: str) -> bool:
    return any(t.lower() == tag.lower() for t in skill.tags or [])


class SkillStore(Protocol):
    """Backend contract shared by the in-memory and PostgreSQL stores."""

    async def initialize(self) -> None: ...

    async def replace_source(
        self, source_id: str, records: Sequence[Skill]
    ) -> int: ...

    async def prune_sources(self, source_ids: Sequence[str]) -> int:
        """Drop records whose source is no longer configured; return the
        number of removed records."""
        ...

    async def get(self, skill_id: str) -> Skill | None: ...

    async def list(
        self,
        offset: int,
        limit: int,
        source: str | None = None,
        tag: str | None = None,
    ) -> tuple[list[Skill], int]: ...

    async def search(
        self,
        query: str,
        limit: int,
        source: str | None = None,
        tag: str | None = None,
    ) -> list[SearchHit]: ...

    async def count(self) -> int: ...

    async def ready(self) -> bool: ...

    async def close(self) -> None: ...


# --- In-memory store (tests / dev) -------------------------------------------


class InMemorySkillStore:
    """Per-source snapshot map; loses its index on restart (dev/test only).

    ``replace_source`` builds the new snapshot map first and swaps the
    reference in one assignment — readers always see a complete slice.
    """

    def __init__(self) -> None:
        self._by_source: dict[str, list[Skill]] = {}

    async def initialize(self) -> None:
        return None

    async def replace_source(
        self, source_id: str, records: Sequence[Skill]
    ) -> int:
        snapshot = {**self._by_source, source_id: list(records)}
        self._by_source = snapshot
        return len(records)

    async def prune_sources(self, source_ids: Sequence[str]) -> int:
        keep = set(source_ids)
        removed = sum(
            len(records)
            for source_id, records in self._by_source.items()
            if source_id not in keep
        )
        self._by_source = {
            source_id: records
            for source_id, records in self._by_source.items()
            if source_id in keep
        }
        return removed

    def _all_records(
        self, source: str | None = None, tag: str | None = None
    ) -> list[Skill]:
        records: list[Skill] = []
        for source_id in sorted(self._by_source):
            if source and source_id != source:
                continue
            for skill in self._by_source[source_id]:
                if tag and not _tag_matches(skill, tag):
                    continue
                records.append(skill)
        return records

    async def get(self, skill_id: str) -> Skill | None:
        source_id, _, _ = skill_id.partition("/")
        for skill in self._by_source.get(source_id, []):
            if skill.skill_id == skill_id:
                return skill
        return None

    async def list(
        self,
        offset: int,
        limit: int,
        source: str | None = None,
        tag: str | None = None,
    ) -> tuple[list[Skill], int]:
        records = self._all_records(source, tag)
        records.sort(key=lambda skill: skill.skill_id)
        return records[offset : offset + limit], len(records)

    async def search(
        self,
        query: str,
        limit: int,
        source: str | None = None,
        tag: str | None = None,
    ) -> list[SearchHit]:
        return rank(query, self._all_records(source, tag), limit)

    async def count(self) -> int:
        return sum(len(records) for records in self._by_source.values())

    async def ready(self) -> bool:
        return True

    async def close(self) -> None:
        return None


# --- PostgreSQL store (deployed environments) --------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS skills (
    skill_id    TEXT PRIMARY KEY,
    source_id   TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_ref  TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT NOT NULL,
    tags        TEXT[],
    version     TEXT,
    source_url  TEXT,
    updated_at  TIMESTAMPTZ NOT NULL,
    body        TEXT NOT NULL,
    web_target  TEXT,
    risk_class  TEXT,
    flow_intent TEXT
);
-- SPEC-049 R-3: web-check declaration columns; the idempotent ALTERs
-- migrate tables created before 0.31.0 (CREATE TABLE IF NOT EXISTS never
-- adds columns to an existing table).
ALTER TABLE skills ADD COLUMN IF NOT EXISTS web_target TEXT;
ALTER TABLE skills ADD COLUMN IF NOT EXISTS risk_class TEXT;
-- SPEC-053 R-1: optional card-level flow intent; idempotent ALTER migrates
-- tables created before it existed (existing rows get NULL -> omitted).
ALTER TABLE skills ADD COLUMN IF NOT EXISTS flow_intent TEXT;
CREATE INDEX IF NOT EXISTS idx_skills_source_id
    ON skills (source_id);
-- The GIN expression must only use IMMUTABLE functions; array_to_string /
-- array_out are STABLE in PostgreSQL, so tags stay out of the index and are
-- pre-filtered at query time instead (negligible at skill-catalog scale).
CREATE INDEX IF NOT EXISTS idx_skills_search
    ON skills USING GIN (
        to_tsvector('simple', title || ' ' || body)
    );
"""

_INSERT = """
INSERT INTO skills (
    skill_id, source_id, source_path, source_ref, title, description,
    tags, version, source_url, updated_at, body, web_target, risk_class,
    flow_intent
) VALUES (
    %(skill_id)s, %(source_id)s, %(source_path)s, %(source_ref)s,
    %(title)s, %(description)s, %(tags)s, %(version)s, %(source_url)s,
    %(updated_at)s, %(body)s, %(web_target)s, %(risk_class)s,
    %(flow_intent)s
)
ON CONFLICT (skill_id) DO UPDATE SET
    source_path = EXCLUDED.source_path,
    source_ref = EXCLUDED.source_ref,
    title = EXCLUDED.title,
    description = EXCLUDED.description,
    tags = EXCLUDED.tags,
    version = EXCLUDED.version,
    source_url = EXCLUDED.source_url,
    updated_at = EXCLUDED.updated_at,
    body = EXCLUDED.body,
    web_target = EXCLUDED.web_target,
    risk_class = EXCLUDED.risk_class,
    flow_intent = EXCLUDED.flow_intent
"""

_ROW_COLUMNS = (
    "skill_id, source_id, source_path, source_ref, title, description, "
    "tags, version, source_url, updated_at, body, web_target, risk_class, "
    "flow_intent"
)

# The tsvector half mirrors idx_skills_search exactly so the GIN index can
# apply; the tags branch keeps tag-only matches in the candidate set (tags
# cannot join the index expression: array_to_string/array_out are STABLE,
# not IMMUTABLE, in PostgreSQL — fine in a filter, not in an index).
# The caller OR-joins the query lexemes: the prefilter must keep every
# record the shared scorer could rank above zero (per-token OR scoring).
# plainto_tsquery would AND the words instead and silently drop partial
# matches ("kubernetes incident" finding nothing lacking both words).
_SEARCH_VECTOR = (
    "(to_tsvector('simple', title || ' ' || body) "
    "@@ to_tsquery('simple', %(query)s) "
    "OR to_tsvector('simple', coalesce(array_to_string(tags, ' '), '')) "
    "@@ to_tsquery('simple', %(query)s))"
)

ConnectFactory = Callable[[], AsyncIterator[Any]]


def _row_to_skill(row: dict[str, Any]) -> Skill:
    return Skill(
        skill_id=row["skill_id"],
        source_id=row["source_id"],
        source_path=row["source_path"],
        source_ref=row["source_ref"],
        title=row["title"],
        description=row["description"],
        tags=list(row["tags"]) if row["tags"] is not None else None,
        version=row["version"],
        source_url=row["source_url"],
        updated_at=row["updated_at"],
        body=row["body"],
        web_target=row["web_target"],
        risk_class=row["risk_class"],
        flow_intent=row["flow_intent"],
    )


def _row_names() -> tuple[str, ...]:
    return tuple(name.strip() for name in _ROW_COLUMNS.split(","))


class PostgresSkillStore:
    """Durable store over a single ``skills`` table in the ``skills`` database.

    Connections are opened per operation (retrieval traffic is low-volume);
    the ``connect`` factory is injectable so tests can substitute a fake
    driver. Search pre-filters candidates with full-text matching, then
    re-ranks them with the shared scorer for byte-identical ordering.
    """

    def __init__(
        self,
        db_url: str,
        connect: ConnectFactory | None = None,
    ) -> None:
        self._db_url = db_url
        self._connect = connect or self._default_connect

    @asynccontextmanager
    async def _default_connect(self) -> AsyncIterator[Any]:
        import psycopg

        conn = await psycopg.AsyncConnection.connect(
            self._db_url, autocommit=False
        )
        try:
            yield conn
        finally:
            await conn.close()

    async def initialize(self) -> None:
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(_DDL)
            await conn.commit()

    async def replace_source(
        self, source_id: str, records: Sequence[Skill]
    ) -> int:
        """Atomic per-source swap: delete + insert inside one transaction."""
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM skills WHERE source_id = %(source_id)s",
                    {"source_id": source_id},
                )
                for skill in records:
                    payload = skill.model_dump(mode="json")
                    await cur.execute(
                        _INSERT,
                        {
                            "skill_id": payload["skill_id"],
                            "source_id": payload["source_id"],
                            "source_path": payload["source_path"],
                            "source_ref": payload["source_ref"],
                            "title": payload["title"],
                            "description": payload["description"],
                            "tags": payload.get("tags"),
                            "version": payload.get("version"),
                            "source_url": payload.get("source_url"),
                            "updated_at": skill.updated_at,
                            "body": payload["body"],
                            "web_target": payload.get("web_target"),
                            "risk_class": payload.get("risk_class"),
                            "flow_intent": payload.get("flow_intent"),
                        },
                    )
            await conn.commit()
        return len(records)

    async def prune_sources(self, source_ids: Sequence[str]) -> int:
        # Sources removed from SKILLS_SOURCES never sync again, so their
        # rows would otherwise keep serving stale skills forever; prune at
        # startup keeps the catalog equal to the federation entry.
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM skills WHERE NOT (source_id = ANY(%(keep)s))",
                    {"keep": list(source_ids)},
                )
                removed = cur.rowcount or 0
            await conn.commit()
        return int(removed)

    async def get(self, skill_id: str) -> Skill | None:
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_ROW_COLUMNS} FROM skills "
                    "WHERE skill_id = %(skill_id)s",
                    {"skill_id": skill_id},
                )
                row = await cur.fetchone()
        if row is None:
            return None
        return _row_to_skill(dict(zip(_row_names(), row)))

    async def list(
        self,
        offset: int,
        limit: int,
        source: str | None = None,
        tag: str | None = None,
    ) -> tuple[list[Skill], int]:
        where, params = self._filter_clause(source, tag)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT count(*) FROM skills {clause}", params
                )
                count_row = await cur.fetchone()
                total = int(count_row[0]) if count_row else 0
                await cur.execute(
                    f"SELECT {_ROW_COLUMNS} FROM skills {clause} "
                    "ORDER BY skill_id LIMIT %(limit)s OFFSET %(offset)s",
                    {**params, "limit": limit, "offset": offset},
                )
                rows = [
                    dict(zip(_row_names(), row)) for row in await cur.fetchall()
                ]
        return [_row_to_skill(row) for row in rows], total

    async def search(
        self,
        query: str,
        limit: int,
        source: str | None = None,
        tag: str | None = None,
    ) -> list[SearchHit]:
        # Tokenized lexemes keep to_tsquery safe (no operator characters)
        # and mirror the scorer's matching unit; a tokenless query can
        # never score above zero, so skip the round-trip entirely.
        tokens = tokenize(query)
        if not tokens:
            return []
        where, params = self._filter_clause(source, tag)
        where.append(_SEARCH_VECTOR)
        params["query"] = " | ".join(tokens)
        clause = f"WHERE {' AND '.join(where)}"
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {_ROW_COLUMNS} FROM skills {clause}", params
                )
                rows = [
                    dict(zip(_row_names(), row)) for row in await cur.fetchall()
                ]
        candidates = [_row_to_skill(row) for row in rows]
        return rank(query, candidates, limit)

    @staticmethod
    def _filter_clause(
        source: str | None, tag: str | None
    ) -> tuple[list[str], dict[str, Any]]:
        where: list[str] = []
        params: dict[str, Any] = {}
        if source:
            where.append("source_id = %(source)s")
            params["source"] = source
        if tag:
            # Exact case-insensitive match, mirroring the in-memory store and
            # the scorer; ILIKE would interpret the parameter as a pattern
            # ('%'/'_') and diverge between backends.
            where.append(
                "EXISTS (SELECT 1 FROM unnest(tags) AS t "
                "WHERE lower(t) = lower(%(tag)s))"
            )
            params["tag"] = tag
        return where, params

    async def count(self) -> int:
        async with self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT count(*) FROM skills")
                row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def ready(self) -> bool:
        try:
            async with self._connect() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
                    await cur.fetchone()
            return True
        except Exception:  # noqa: BLE001 - readiness must never raise
            return False

    async def close(self) -> None:
        return None


# --- Factory ------------------------------------------------------------------


def build_skill_store(settings: SkillsSettings) -> SkillStore:
    """Select the store backend from settings (default: in-memory)."""
    if settings.store_backend == "postgres":
        if not settings.db_url:
            raise StoreError(
                "SKILLS_DB_URL is required when SKILLS_STORE_BACKEND=postgres"
            )
        return PostgresSkillStore(settings.db_url)
    return InMemorySkillStore()
