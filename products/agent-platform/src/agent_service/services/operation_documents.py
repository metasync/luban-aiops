"""Typed operations document repository (SPEC-039 R-1).

Persists immutable typed documents — shift summaries in Phase 1 — so
operators can produce durable recaps from the platform's own records
and colleagues can read published documents by role, never by
per-document grants. Documents are snapshots: the assembly copies
facts verbatim from the durable stores, record ids are provenance
anchors (not live references), and a document never depends on its
source records' lifetimes.

Lifecycle is one-way: ``draft`` -> ``published`` (owner action);
drafts are visible only to their owner — every list/get filters them
out for non-owners, including admins — while published documents are
visible to every ``documents:read`` holder. Publishing and deletion
are owner-only; published documents can be deleted but never edited.

Backends mirror the SPEC-017/025/031 posture: in-memory (code
default, dev/CI) and Postgres (deployed), selected by the same
``AGENT_STATE_STORE_BACKEND`` knob and sharing ``AGENT_STATE_DB_URL``.
Documents are bounded (most recent ``PER_OWNER_CAP`` per owner,
oldest evicted first) and age out after ``RETENTION_DAYS`` (aligned
with the inbox history window); expired rows are swept
opportunistically on writes and at startup. Failures never fail the
request path: callers degrade to the in-memory backend.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, runtime_checkable

LOGGER = logging.getLogger(__name__)

PER_OWNER_CAP = 20
RETENTION_DAYS = 30

DOCUMENT_STATES = frozenset({"draft", "published"})
PROSE_STATUSES = frozenset({"included", "failed", "not_requested"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_document(
    document_id: str,
    document_type: str,
    owner_user_id: str,
    label: str,
    provenance: dict[str, Any],
    digest: dict[str, Any],
    prose: str | None,
    prose_status: str,
    summary: str | None = None,
) -> dict[str, Any]:
    """Shape the immutable document row written at creation time.

    ``summary`` (SPEC-041 R-4) is the deterministic counts-only
    one-liner derived from the digest's handover section at creation;
    it flows through the envelope-only listing because it discloses
    counts, never content.
    """
    return {
        "document_id": document_id,
        "document_type": document_type,
        "state": "draft",
        "owner_user_id": owner_user_id,
        "label": label,
        "created_at": _utc_now_iso(),
        "published_at": None,
        "provenance": provenance,
        "digest": digest,
        "prose": prose,
        "prose_status": prose_status,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class OperationDocumentStore(Protocol):
    """Public interface for operation document backends.

    The visibility matrix (SPEC-039 R-2) is enforced here at the query
    boundary: ``list_for_owner`` is the only surface returning drafts,
    ``list_published`` returns published rows only.
    """

    @property
    def backend_name(self) -> str: ...

    def create(self, document: dict[str, Any]) -> None: ...

    def publish(self, owner_user_id: str, document_id: str) -> bool: ...

    def load(self, document_id: str) -> dict[str, Any] | None: ...

    def list_for_owner(self, owner_user_id: str) -> list[dict[str, Any]]: ...

    def list_published(self) -> list[dict[str, Any]]: ...

    def delete(self, owner_user_id: str, document_id: str) -> bool: ...

    def is_ready(self) -> bool: ...


# ---------------------------------------------------------------------------
# In-memory backend
# ---------------------------------------------------------------------------


class InMemoryOperationDocumentStore:
    """In-memory operation documents.

    Single-replica and non-persistent; suitable for development, CI,
    and as a fallback when Postgres is unreachable.
    """

    backend_name = "memory"

    def __init__(self) -> None:
        self._by_document_id: dict[str, dict[str, Any]] = {}

    def create(self, document: dict[str, Any]) -> None:
        self._by_document_id[document["document_id"]] = dict(document)
        self._evict_over_cap(document["owner_user_id"])
        self._sweep_expired()

    def publish(self, owner_user_id: str, document_id: str) -> bool:
        record = self._by_document_id.get(document_id)
        if record is None or record["owner_user_id"] != owner_user_id:
            return False
        # Publishing is a one-way owner action (SPEC-039 R-1): the
        # first publish owns the transition, later calls are no-ops.
        if record["state"] != "draft":
            return False
        record["state"] = "published"
        record["published_at"] = _utc_now_iso()
        return True

    def load(self, document_id: str) -> dict[str, Any] | None:
        record = self._by_document_id.get(document_id)
        return dict(record) if record is not None else None

    def list_for_owner(self, owner_user_id: str) -> list[dict[str, Any]]:
        rows = [
            dict(record)
            for record in self._by_document_id.values()
            if record["owner_user_id"] == owner_user_id
        ]
        rows.sort(key=lambda record: record["created_at"], reverse=True)
        return rows

    def list_published(self) -> list[dict[str, Any]]:
        rows = [
            dict(record)
            for record in self._by_document_id.values()
            if record["state"] == "published"
        ]
        rows.sort(key=lambda record: record["created_at"], reverse=True)
        return rows

    def delete(self, owner_user_id: str, document_id: str) -> bool:
        record = self._by_document_id.get(document_id)
        if record is None or record["owner_user_id"] != owner_user_id:
            return False
        del self._by_document_id[document_id]
        return True

    def is_ready(self) -> bool:
        return True

    def _evict_over_cap(self, owner_user_id: str) -> None:
        rows = self.list_for_owner(owner_user_id)
        if len(rows) <= PER_OWNER_CAP:
            return
        # ``rows`` is newest-first: evict the oldest rows beyond the cap.
        for record in rows[PER_OWNER_CAP:]:
            self._by_document_id.pop(record["document_id"], None)

    def _sweep_expired(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
        doomed = []
        for document_id, record in self._by_document_id.items():
            try:
                stamp = datetime.fromisoformat(
                    record["created_at"].replace("Z", "+00:00")
                )
            except ValueError:
                continue
            if stamp < cutoff:
                doomed.append(document_id)
        for document_id in doomed:
            del self._by_document_id[document_id]


# ---------------------------------------------------------------------------
# Postgres backend
# ---------------------------------------------------------------------------


_OPERATION_DOCUMENTS_DDL = """
CREATE TABLE IF NOT EXISTS operation_documents (
    document_id     TEXT PRIMARY KEY,
    document_type   TEXT NOT NULL,
    state           TEXT NOT NULL,
    owner_user_id   TEXT NOT NULL,
    label           TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL,
    published_at    TIMESTAMPTZ,
    provenance      JSONB NOT NULL,
    digest          JSONB NOT NULL,
    prose           TEXT,
    prose_status    TEXT NOT NULL,
    summary         TEXT
);
CREATE INDEX IF NOT EXISTS idx_operation_documents_owner
    ON operation_documents (owner_user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_operation_documents_state
    ON operation_documents (state, created_at);
"""

# Additive migration (SPEC-041 R-4): rows created before the summary
# field keep NULL and degrade to label-only listings.
_ADD_SUMMARY_COLUMN = """
ALTER TABLE operation_documents
    ADD COLUMN IF NOT EXISTS summary TEXT
"""

_INSERT_DOCUMENT = """
INSERT INTO operation_documents (
    document_id, document_type, state, owner_user_id, label,
    created_at, provenance, digest, prose, prose_status, summary
)
VALUES (
    %(document_id)s, %(document_type)s, 'draft', %(owner_user_id)s,
    %(label)s, now(), %(provenance)s, %(digest)s, %(prose)s,
    %(prose_status)s, %(summary)s
)
ON CONFLICT (document_id) DO NOTHING
"""

_EVICT_OVER_CAP = """
DELETE FROM operation_documents
 WHERE ctid IN (
     SELECT ctid FROM operation_documents
      WHERE owner_user_id = %(owner_user_id)s
      ORDER BY created_at DESC
      OFFSET %(cap)s
 )
"""

# Publishing resolves exactly once (SPEC-039 R-1): the first update
# owns the transition; a racing or repeated publish finds no draft row
# and becomes a no-op.
_PUBLISH = """
UPDATE operation_documents
   SET state = 'published', published_at = now()
 WHERE document_id = %(document_id)s
   AND owner_user_id = %(owner_user_id)s
   AND state = 'draft'
"""

_LOAD_DOCUMENT = """
SELECT document_id, document_type, state, owner_user_id, label,
       created_at, published_at, provenance, digest, prose, prose_status,
       summary
  FROM operation_documents
 WHERE document_id = %(document_id)s
"""

_LIST_FOR_OWNER = """
SELECT document_id, document_type, state, owner_user_id, label,
       created_at, published_at, provenance, digest, prose, prose_status,
       summary
  FROM operation_documents
 WHERE owner_user_id = %(owner_user_id)s
 ORDER BY created_at DESC, document_id DESC
"""

_LIST_PUBLISHED = """
SELECT document_id, document_type, state, owner_user_id, label,
       created_at, published_at, provenance, digest, prose, prose_status,
       summary
  FROM operation_documents
 WHERE state = 'published'
 ORDER BY created_at DESC, document_id DESC
"""

_DELETE_DOCUMENT = """
DELETE FROM operation_documents
 WHERE document_id = %(document_id)s
   AND owner_user_id = %(owner_user_id)s
RETURNING document_id
"""

# Bounded opportunistic sweep (SPEC-017 state-store pattern): reclaim
# rows past the retention window; piggybacks on writes.
_SWEEP_EXPIRED = """
DELETE FROM operation_documents
 WHERE ctid IN (
     SELECT ctid FROM operation_documents
      WHERE created_at <= now() - make_interval(days => %(retention_days)s)
      LIMIT %(sweep_limit)s
 )
"""

_SWEEP_LIMIT = 100

SyncConnectFactory = Callable[[], Iterator[Any]]


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    stamp = value.astimezone(timezone.utc) if value.tzinfo else value.replace(
        tzinfo=timezone.utc
    )
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_document(row: Any) -> dict[str, Any]:
    (
        document_id,
        document_type,
        state,
        owner_user_id,
        label,
        created_at,
        published_at,
        provenance,
        digest,
        prose,
        prose_status,
        summary,
    ) = row
    return {
        "document_id": document_id,
        "document_type": document_type,
        "state": state,
        "owner_user_id": owner_user_id,
        "label": label,
        "created_at": _iso(created_at),
        "published_at": _iso(published_at),
        "provenance": provenance or {},
        "digest": digest or {},
        "prose": prose,
        "prose_status": prose_status,
        "summary": summary,
    }


class PostgresOperationDocumentStore:
    """Postgres-backed operation documents (SPEC-039 R-1).

    Shares the SPEC-016 ``sessions`` database — one database for
    platform-owned agent session state. Connections are opened per
    operation and the ``connect`` factory is injectable so tests can
    substitute a fake driver.
    """

    backend_name = "postgres"

    def __init__(
        self,
        db_url: str,
        connect: SyncConnectFactory | None = None,
    ) -> None:
        self._db_url = db_url
        self._connect = connect or self._default_connect

    @contextmanager
    def _default_connect(self) -> Iterator[Any]:
        import psycopg

        conn = psycopg.connect(self._db_url, autocommit=False)
        try:
            yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        """Create the table and sweep rows past the retention window."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_OPERATION_DOCUMENTS_DDL)
                cur.execute(_ADD_SUMMARY_COLUMN)
                cur.execute(
                    _SWEEP_EXPIRED,
                    {
                        "retention_days": RETENTION_DAYS,
                        "sweep_limit": _SWEEP_LIMIT,
                    },
                )
            conn.commit()

    def create(self, document: dict[str, Any]) -> None:
        from psycopg.types.json import Jsonb

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _INSERT_DOCUMENT,
                    {
                        "document_id": document["document_id"],
                        "document_type": document["document_type"],
                        "owner_user_id": document["owner_user_id"],
                        "label": document["label"],
                        "provenance": Jsonb(document["provenance"]),
                        "digest": Jsonb(document["digest"]),
                        "prose": document["prose"],
                        "prose_status": document["prose_status"],
                        "summary": document.get("summary"),
                    },
                )
                cur.execute(
                    _EVICT_OVER_CAP,
                    {
                        "owner_user_id": document["owner_user_id"],
                        "cap": PER_OWNER_CAP,
                    },
                )
                cur.execute(
                    _SWEEP_EXPIRED,
                    {
                        "retention_days": RETENTION_DAYS,
                        "sweep_limit": _SWEEP_LIMIT,
                    },
                )
            conn.commit()

    def publish(self, owner_user_id: str, document_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _PUBLISH,
                    {
                        "document_id": document_id,
                        "owner_user_id": owner_user_id,
                    },
                )
                published = cur.rowcount > 0
            conn.commit()
        return published

    def load(self, document_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_LOAD_DOCUMENT, {"document_id": document_id})
                row = cur.fetchone()
            conn.commit()
        return _row_to_document(row) if row is not None else None

    def list_for_owner(self, owner_user_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _LIST_FOR_OWNER, {"owner_user_id": owner_user_id}
                )
                rows = cur.fetchall()
            conn.commit()
        return [_row_to_document(row) for row in rows]

    def list_published(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_LIST_PUBLISHED)
                rows = cur.fetchall()
            conn.commit()
        return [_row_to_document(row) for row in rows]

    def delete(self, owner_user_id: str, document_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _DELETE_DOCUMENT,
                    {
                        "document_id": document_id,
                        "owner_user_id": owner_user_id,
                    },
                )
                rows = cur.fetchall()
            conn.commit()
        return bool(rows)

    def is_ready(self) -> bool:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return cur.fetchone() is not None
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_operation_document_store() -> OperationDocumentStore:
    """Create the operation document store from environment configuration.

    Reuses the SPEC-017/025 knobs (``AGENT_STATE_STORE_BACKEND`` /
    ``AGENT_STATE_DB_URL``) so documents share the state store's
    lifecycle and durability guarantees. Backend failures fail open:
    the service stays usable on an in-memory store.
    """
    backend = os.getenv("AGENT_STATE_STORE_BACKEND", "memory")

    if backend == "memory":
        return InMemoryOperationDocumentStore()

    if backend == "postgres":
        db_url = os.getenv("AGENT_STATE_DB_URL", "").strip()
        if not db_url:
            raise ValueError(
                "AGENT_STATE_STORE_BACKEND=postgres requires "
                "AGENT_STATE_DB_URL to be set"
            )
        try:
            store = PostgresOperationDocumentStore(db_url=db_url)
            store.initialize()
            LOGGER.info(
                "operation document store: Postgres backend initialized"
            )
            return store
        except Exception as exc:
            LOGGER.warning(
                "operation document store: Postgres unavailable (%s), "
                "falling back to in-memory",
                exc,
            )
            return InMemoryOperationDocumentStore()

    raise ValueError(
        f"Unknown AGENT_STATE_STORE_BACKEND: {backend!r} "
        "(expected 'memory' or 'postgres')"
    )


# Module-level singleton — imported by the v2 routes.
OPERATION_DOCUMENT_STORE = build_operation_document_store()
