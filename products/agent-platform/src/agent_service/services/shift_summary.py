"""Shift-summary digest assembly (SPEC-039 R-3).

Builds the ``shift_summary`` digest mechanically from the four durable
stores — the kernel state snapshot (turn counts only), the evidence
store, the confirmation records, and the execution records. Facts are
copied verbatim; every entry carries its source record id so the
document's provenance anchors resolve later without live references.

Coverage is two-tier by session ownership:

- **Owner-covered sessions** contribute the full digest: title, turn
  counts, evidence counts per turn, confirmation decisions, execution
  receipts, and still-pending items.
- **Foreign sessions** (owner != requester) contribute a
  metadata-level digest only, and only when the requester holds
  ``approvals:list``: confirmation decisions, execution receipts, and
  record counts — never titles, transcript excerpts, or evidence
  content (the SPEC-030 Q-1 metadata-only posture, extended).

Unreadable secondary stores degrade per-source — the affected section
reports ``unavailable`` — never a 500.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from agent_service.services.confirmation_records import (
    CONFIRMATION_RECORD_STORE,
)
from agent_service.services.evidence_store import EVIDENCE_STORE
from agent_service.services.execution_records import EXECUTION_RECORD_STORE
from agent_service.services.session_store import SESSION_STORE
from agent_service.services.session_transcript import extract_transcript

LOGGER = logging.getLogger(__name__)

MAX_SESSION_IDS = 20
MAX_LABEL_LENGTH = 120

UNAVAILABLE = "unavailable"


class DigestInputError(Exception):
    """Structurally invalid generation input (bounded input violated)."""


class UnknownSessionError(Exception):
    """One or more supplied session ids do not exist.

    Carries the offending ids; the route answers 400 without revealing
    anything about ownership.
    """

    def __init__(self, session_ids: list[str]) -> None:
        super().__init__(f"unknown session ids: {session_ids}")
        self.session_ids = session_ids


class ForeignSessionDenied(Exception):
    """Foreign coverage requested without ``approvals:list``.

    Rejected before assembly so no foreign fact is ever touched.
    """

    def __init__(self, session_ids: list[str]) -> None:
        super().__init__(f"foreign sessions require approvals:list: {session_ids}")
        self.session_ids = session_ids


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_session_ids(session_ids: list[str]) -> list[str]:
    """Validate and deduplicate the coverage request (bounded input)."""
    if not session_ids:
        raise DigestInputError("at least one session id is required")
    if len(session_ids) > MAX_SESSION_IDS:
        raise DigestInputError(
            f"at most {MAX_SESSION_IDS} session ids are supported"
        )
    seen: dict[str, None] = {}
    for session_id in session_ids:
        if not isinstance(session_id, str) or not session_id.strip():
            raise DigestInputError("session ids must be non-empty strings")
        seen.setdefault(session_id.strip(), None)
    return list(seen)


def _safe_read(read) -> Any:
    """Read a secondary store, degrading to ``None`` on any failure."""
    try:
        return read()
    except Exception as exc:  # noqa: BLE001 — per-source degradation
        LOGGER.warning("shift summary source read failed: %s", exc)
        return None


def _owner_transcript_section(session_id: str) -> Any:
    try:
        available, turns = extract_transcript(session_id)
    except Exception as exc:  # noqa: BLE001 — per-source degradation
        LOGGER.warning("shift summary transcript read failed: %s", exc)
        return UNAVAILABLE
    # Counts only — transcript content never enters the digest.
    return {
        "available": available,
        "turn_count": len(turns),
        "user_turn_count": sum(1 for turn in turns if turn.get("role") == "user"),
    }


def _owner_evidence_section(session_id: str) -> Any:
    turns = _safe_read(lambda: EVIDENCE_STORE.load_turns(session_id))
    if turns is None:
        return UNAVAILABLE
    return {
        "total_frame_count": sum(len(turn.get("frames", [])) for turn in turns),
        "turns": [
            {
                "turn_index": turn.get("turn_index"),
                "frame_count": len(turn.get("frames", [])),
            }
            for turn in turns
        ],
    }


def _confirmation_entry(record: dict[str, Any], *, metadata_only: bool) -> dict[str, Any]:
    entry = {
        "confirm_id": record.get("confirm_id"),
        "action": record.get("action"),
        "status": record.get("status"),
        "decision": record.get("decision"),
        "decider_user_id": record.get("decider_user_id"),
        "parked_at": record.get("parked_at"),
        "decided_at": record.get("decided_at"),
    }
    if not metadata_only:
        # The pending call list names the parked tools for the owner tier;
        # foreign readers get the decisions without the call bodies.
        entry["pending_call_count"] = len(record.get("pending_calls") or [])
        entry["turn_index"] = record.get("turn_index")
    return entry


def _execution_entry(record: dict[str, Any]) -> dict[str, Any]:
    receipt = record.get("receipt") or {}
    return {
        "execution_id": record.get("execution_id"),
        "call_id": record.get("call_id"),
        "tool_name": record.get("tool_name"),
        "status": record.get("status"),
        "digest_match": record.get("digest_match"),
        "receipt_status": receipt.get("status"),
        "completed_at": record.get("completed_at"),
    }


def _open_items(
    confirmations: Any, executions: Any
) -> dict[str, Any]:
    open_confirmations = (
        sum(1 for record in confirmations if record.get("status") == "pending")
        if isinstance(confirmations, list)
        else None
    )
    open_executions = (
        sum(1 for record in executions if record.get("status") == "requested")
        if isinstance(executions, list)
        else None
    )
    return {
        "pending_confirmations": open_confirmations,
        "requested_executions": open_executions,
    }


def _digest_own_session(record, session_id: str) -> tuple[dict[str, Any], list[str]]:
    confirmations = _safe_read(
        lambda: CONFIRMATION_RECORD_STORE.load_for_session(session_id)
    )
    executions = _safe_read(
        lambda: EXECUTION_RECORD_STORE.load_for_session(session_id)
    )
    cited = [
        row.get("confirm_id")
        for row in (confirmations if isinstance(confirmations, list) else [])
        if row.get("confirm_id")
    ] + [
        row.get("execution_id")
        for row in (executions if isinstance(executions, list) else [])
        if row.get("execution_id")
    ]
    entry: dict[str, Any] = {
        "session_id": session_id,
        "coverage": "owner",
        "title": record.title,
        "created_at": record.created_at.isoformat()
        if record.created_at is not None
        else None,
        "transcript": _owner_transcript_section(session_id),
        "evidence": _owner_evidence_section(session_id),
        "confirmations": (
            [_confirmation_entry(row, metadata_only=False) for row in confirmations]
            if confirmations is not None
            else UNAVAILABLE
        ),
        "executions": (
            [_execution_entry(row) for row in executions]
            if executions is not None
            else UNAVAILABLE
        ),
    }
    entry["open_items"] = _open_items(confirmations, executions)
    return entry, cited


def _digest_foreign_session(session_id: str) -> tuple[dict[str, Any], list[str]]:
    confirmations = _safe_read(
        lambda: CONFIRMATION_RECORD_STORE.load_for_session(session_id)
    )
    executions = _safe_read(
        lambda: EXECUTION_RECORD_STORE.load_for_session(session_id)
    )
    cited = [
        row.get("confirm_id")
        for row in (confirmations if isinstance(confirmations, list) else [])
        if row.get("confirm_id")
    ] + [
        row.get("execution_id")
        for row in (executions if isinstance(executions, list) else [])
        if row.get("execution_id")
    ]
    return (
        {
            "session_id": session_id,
            "coverage": "foreign",
            # Metadata-only tier: no title, no transcript, no evidence.
            "confirmation_decisions": (
                [_confirmation_entry(row, metadata_only=True) for row in confirmations]
                if confirmations is not None
                else UNAVAILABLE
            ),
            "execution_receipts": (
                [_execution_entry(row) for row in executions]
                if executions is not None
                else UNAVAILABLE
            ),
            "record_counts": {
                "confirmations": (
                    len(confirmations) if isinstance(confirmations, list) else None
                ),
                "executions": (
                    len(executions) if isinstance(executions, list) else None
                ),
            },
        },
        cited,
    )


def build_digest(
    requester_user_id: str,
    session_ids: list[str],
    can_view_foreign: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Assemble the shift-summary digest and its provenance block.

    Returns ``(digest, provenance)``. Raises ``DigestInputError`` for
    bounded-input violations, ``UnknownSessionError`` for ids that do
    not exist, and ``ForeignSessionDenied`` when foreign coverage is
    requested without ``approvals:list`` — all rejected before any
    foreign fact is read.
    """
    ids = validate_session_ids(session_ids)

    sessions = {}
    unknown: list[str] = []
    for session_id in ids:
        record = SESSION_STORE.get_session(session_id)
        if record is None:
            unknown.append(session_id)
        else:
            sessions[session_id] = record
    if unknown:
        raise UnknownSessionError(unknown)

    foreign = [
        session_id
        for session_id in ids
        if (sessions[session_id].user_id or "") != requester_user_id
    ]
    if foreign and not can_view_foreign:
        raise ForeignSessionDenied(foreign)

    entries: list[dict[str, Any]] = []
    provenance_sessions: list[dict[str, Any]] = []
    for session_id in ids:
        if session_id in foreign:
            entry, cited = _digest_foreign_session(session_id)
        else:
            entry, cited = _digest_own_session(sessions[session_id], session_id)
        entries.append(entry)
        provenance_sessions.append(
            {
                "session_id": session_id,
                "coverage": "foreign" if session_id in foreign else "owner",
                "cited_record_ids": cited,
            }
        )

    digest = {
        "generated_at": _utc_now_iso(),
        "requester_user_id": requester_user_id,
        "session_count": len(entries),
        "sessions": entries,
    }
    return digest, {"sessions": provenance_sessions}
