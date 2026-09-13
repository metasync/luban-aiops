from __future__ import annotations

import logging

from fastapi import HTTPException

from agent_service.core.metrics import record_session_created
from agent_service.schemas.api import SessionRecord
from agent_service.services.agent_state_store import AGENT_STATE_STORE
from agent_service.services.authoring_trace import AUTHORING_TRACE_STORE
from agent_service.services.confirmation_records import CONFIRMATION_RECORD_STORE
from agent_service.services.evidence_store import EVIDENCE_STORE
from agent_service.services.execution_records import EXECUTION_RECORD_STORE
from agent_service.services.flow_approvals import FLOW_APPROVALS, FLOW_CONTEXTS
from agent_service.services.prose_redaction import redact_user_text
from agent_service.services.session_store import SESSION_STORE

LOGGER = logging.getLogger(__name__)

# SPEC-022 R-1: workspace list cap and title minting bounds.
SESSION_LIST_CAP = 50
SESSION_TITLE_MAX_LENGTH = 80

# --- Title secret masking (SPEC-049 R-5 posture applied to a UI label) ---
#
# A minted title comes from the *user's own first message*, which is the one
# credential carrier no tool-side redactor ever sees: the operator typed the
# password into the chat, so it is in the prompt text, not in a tool argument.
# The title is then rendered in the workspace sidebar and the session header
# and — because an approver's inbox lists a pending card by its session title —
# in front of a *second identity*. Neither the gateway's result redaction nor
# R-7's confirmation-frame masking can reach it, since both run downstream of
# the model's tool calls.
#
# The masking itself lives in ``prose_redaction``, which applies the same
# user-authored-text projection to the two other carriers of chat prose: the
# durable transcript and the live assistant stream. Sharing one predicate is
# what keeps the three coherent — a sidebar reading ``... to ***`` above a
# transcript panel showing the value in full was the defect that made this a
# module instead of a title-local helper. That module also records the
# boundary this projection must not cross: the heuristic layer is scoped to
# user-authored text, and is never a tool-output or trace redactor.


def _assert_session_owner(session: SessionRecord, user_id: str | None) -> None:
    # 404 instead of 403 so foreign session IDs are indistinguishable from
    # unknown ones.
    if session.user_id and user_id and session.user_id != user_id:
        raise HTTPException(status_code=404, detail="session not found")


def create_session(
    user_id: str | None, session_type: str = "operation"
) -> SessionRecord:
    """Create a session, writing its birth ``session_type`` exactly once.

    SPEC-056 R-1: the type is threaded to the store's create path and never
    reassigned afterwards — this function is the only place a fresh session's
    type is decided, and it defaults to ``operation`` so the historical
    one-click path is unchanged.
    """
    record_session_created()
    return SESSION_STORE.create_session(user_id, session_type=session_type)


def create_named_session(
    session_id: str, user_id: str | None, session_type: str = "operation"
) -> SessionRecord:
    """Get-or-create a caller-supplied dedicated session (SPEC-015 R-3).

    Idempotent for the owning user so re-triage of an incident reuses the
    same session; a foreign owner is indistinguishable from an unknown id.
    The post-create re-read resolves the check-then-create race (Redis
    last-writer-wins) by surfacing a lost race as 404 instead of letting
    two owners share one session.

    SPEC-056 R-1: ``session_type`` is written only on the create branch; an
    already-existing session is returned verbatim, so re-triage never
    re-types a live session (immutability). Incident-triage named sessions
    are operational work and default to ``operation``.
    """
    existing = SESSION_STORE.get_session(session_id)
    if existing is not None:
        _assert_session_owner(existing, user_id)
        return existing
    record_session_created()
    record = SESSION_STORE.create_session(
        user_id, session_id=session_id, session_type=session_type
    )
    stored = SESSION_STORE.get_session(session_id)
    if stored is None:
        return record
    _assert_session_owner(stored, user_id)
    return stored


def ensure_session(
    session_id: str | None, user_id: str | None, session_type: str = "operation"
) -> SessionRecord:
    """Resolve a session for a chat turn, creating one only when id is None.

    SPEC-056 R-1: the create branch writes ``session_type`` once; the
    existing-session branch returns the stored record untouched, so a turn
    against a live session can never re-type it (immutability).
    """
    if session_id is None:
        record_session_created()
        return SESSION_STORE.create_session(user_id, session_type=session_type)
    session = SESSION_STORE.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    _assert_session_owner(session, user_id)
    return session


def get_session(session_id: str, user_id: str | None = None) -> SessionRecord:
    session = SESSION_STORE.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    _assert_session_owner(session, user_id)
    return session


def rename_session_title(
    session_id: str, title: str, user_id: str | None = None
) -> SessionRecord:
    """Owner session rename (SPEC-039 R-7).

    Supersedes the SPEC-022 server-minted set-once title: the rename
    overwrites whatever title the session carries. Ownership is
    asserted through ``get_session`` (foreign or unknown ids 404 per
    the anti-enumeration convention); renames are not audited
    (owner-side cosmetic act on one's own record).
    """
    session = get_session(session_id, user_id)
    SESSION_STORE.update_session_title(session.session_id, title)
    updated = SESSION_STORE.get_session(session.session_id)
    return updated if updated is not None else session


def list_sessions(
    user_id: str, session_type: str | None = None
) -> list[SessionRecord]:
    """The caller's sessions, most-recently-active first (SPEC-022 R-1).

    Backends that cannot order server-side (memory, Redis) are sorted here;
    the Postgres backend already returns the capped, ordered window.

    SPEC-056 R-2/R-4: ``session_type`` is an **optional** scope — omitted
    returns every row exactly as before (legacy behavior), a value narrows to
    that birth type. Ownership scoping is unchanged, so the anti-enumeration
    posture holds; the filter is passed by keyword so all three backends'
    differing signatures (Postgres also takes a server-side ``limit``) accept
    it uniformly.
    """
    records = SESSION_STORE.list_sessions_by_user(user_id, session_type=session_type)
    records.sort(
        key=lambda record: record.last_active_at or record.created_at,
        reverse=True,
    )
    return records[:SESSION_LIST_CAP]


def mark_session_turn(session_id: str, message: str) -> None:
    """Workspace bookkeeping at chat-turn start (SPEC-022 R-1).

    Mints the title from the first user turn (80-char cap, never rewritten)
    and refreshes ``last_active_at``. Both are fail-open: bookkeeping never
    fails a turn.

    Masking runs **before** the cap, not after: truncating first leaves the
    leading characters of a secret straddling the boundary readable, which is
    how a sidebar came to show ``... to Temp``.
    """
    title = " ".join(redact_user_text(message).split())[:SESSION_TITLE_MAX_LENGTH]
    try:
        if title:
            SESSION_STORE.set_session_title(session_id, title)
        SESSION_STORE.touch_session(session_id)
    except Exception as exc:
        LOGGER.warning(
            "session workspace bookkeeping failed for %s: %s", session_id, exc
        )


def pin_session_model(session_id: str, model: str | None) -> None:
    """Pin the model that resolved for a turn (SPEC-024 R-3, Q-4).

    The newest resolved selection wins (unlike the set-once title). Like
    all workspace bookkeeping this is fail-open: a store failure degrades
    affinity, never the turn.
    """
    if not model:
        return
    try:
        SESSION_STORE.set_session_model(session_id, model)
    except Exception as exc:
        LOGGER.warning(
            "session model pinning failed for %s: %s", session_id, exc
        )


def delete_session(session_id: str, user_id: str | None = None) -> bool:
    """Delete a session and its persisted agent state (SPEC-017 R-3).

    State cleanup follows session deletion so a deleted session never
    leaves a durable conversation snapshot behind; a state-store failure
    does not fail the session delete (fail-open). Stored tool evidence
    cascades with the session for the same reason (SPEC-025 R-2).
    """
    session = SESSION_STORE.get_session(session_id)
    if session is None:
        return False
    _assert_session_owner(session, user_id)
    deleted = SESSION_STORE.delete_session(session_id)
    if deleted:
        # SPEC-051 R-1/R-2: the session-scoped browser-flow stores are
        # in-memory and their context entries never expire on their own, so
        # drop both here to bound per-process growth alongside every other
        # per-session store. Plain dict pops — best-effort by construction.
        FLOW_CONTEXTS.clear(session_id)
        FLOW_APPROVALS.clear(session_id)
        try:
            AGENT_STATE_STORE.delete_state(session_id)
        except Exception:
            # Durability cleanup is best-effort; the session is gone.
            pass
        try:
            EVIDENCE_STORE.delete_session(session_id)
        except Exception:
            # Evidence cleanup is best-effort; the session is gone.
            pass
        try:
            CONFIRMATION_RECORD_STORE.delete_session(session_id)
        except Exception:
            # Confirmation records live and die with their session;
            # cleanup is best-effort once the session is gone.
            pass
        try:
            EXECUTION_RECORD_STORE.delete_session(session_id)
        except Exception:
            # Execution records live and die with their session too
            # (SPEC-037 R-4); cleanup is best-effort.
            pass
        # The authoring trace is session-scoped work product, so it follows
        # the session even when it is terminal (SPEC-055 R-1/R-2). Its
        # lifecycle protection is against *time* — the idle-GC never reclaims
        # a graduated trace and a later approval never reopens one — not
        # against the owner deleting the session it was authored in, which
        # would otherwise leave durable argument copies behind for a session
        # that no longer exists, forever: a terminal trace is by definition
        # exempt from the sweep. Deleting a graduated trace does destroy the
        # provenance of whatever draft it produced, because a graduation
        # draft is ephemeral (previewed and downloaded for a human merge,
        # never persisted by the platform), so the operator's window to keep
        # it closes at the delete. That is the trade every sibling store here
        # already makes — a deleted session takes its agent state, evidence,
        # confirmation records and execution receipts with it.
        try:
            AUTHORING_TRACE_STORE.delete_session(session_id)
        except Exception:
            # Trace cleanup is best-effort; the session is gone.
            pass
    return deleted
