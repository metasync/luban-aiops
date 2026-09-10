from __future__ import annotations

import logging
import re

from fastapi import HTTPException

from agent_service.core.metrics import record_session_created
from agent_service.schemas.api import SessionRecord
from agent_service.services.agent_state_store import AGENT_STATE_STORE
from agent_service.services.authoring_trace import AUTHORING_TRACE_STORE
from agent_service.services.confirmation_records import CONFIRMATION_RECORD_STORE
from agent_service.services.evidence_store import EVIDENCE_STORE
from agent_service.services.execution_records import EXECUTION_RECORD_STORE
from agent_service.services.flow_approvals import FLOW_APPROVALS, FLOW_CONTEXTS
from agent_service.services.secret_params import (
    MASK,
    SECRET_PARAM_SUBSTRINGS,
    redact_secret_query,
)
from agent_service.services.session_store import SESSION_STORE
# Imported for the *vocabulary*, not the service: the secret-shape patterns are
# pinned as exactly two copies (``validate_secret_vocabulary.py`` fails the build
# on divergence), so a third caller must reuse one rather than declare its own.
from agent_service.services.skill_draft import REDACTION_VALUE_PATTERNS

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
# Three of the four layers reuse a pinned vocabulary: the secret-*shape*
# patterns (PEM/JWT/Bearer-Basic/AKIA, shared with the gateway and the skill
# draft), the secret-*name* substrings applied to a ``key=value`` pair, and the
# same substrings applied to a URL query via ``redact_secret_query``. None of
# those matches a bare password literal in prose — "reset the password for
# alice to TempPass123!" has no shape, no key and no query — so the fourth
# layer masks a credential-*looking* token, fired only when the message already
# names a secret.
#
# That fourth layer is a heuristic, and it is scoped to titles *alone* on
# purpose. Here a false positive costs an 80-character label some of its
# informativeness — the cost curve ``secret_params.is_secret_value`` documents
# for a display projection — while a false negative publishes a credential into
# another identity's inbox. In tool output the curve inverts: masking a pod
# name or a session id breaks the evidence, which is why ``redaction.py``
# records rejecting a generic substring matcher there (its Q-3 note). This
# predicate must never be promoted to a tool-output or trace redactor.
#
# Known accepted false positives, all checked against the sample prompts: a
# mixed-alnum identifier in a message that also names a secret (``k8s.list_pods``
# beside the word "password") masks. Known accepted false negative: an
# all-alphabetic password with no punctuation (``CorrectHorse``) has one
# character class and does not mask.
_TITLE_SECRET_NAME = "|".join(
    sorted(
        {re.escape(name) for name in SECRET_PARAM_SUBSTRINGS},
        key=lambda item: (-len(item), item),
    )
)
# ``password: TempPass123!`` / ``newpw=TempPass123!`` in prose. The value stops
# at ``&``/``;``/quotes so an already-masked URL query keeps its non-secret
# params visible instead of swallowing the rest of the string.
_TITLE_KEY_VALUE = re.compile(
    rf"\b([\w.-]*(?:{_TITLE_SECRET_NAME})[\w.-]*)(\s*[=:]\s*)([^\s&;,\"']+)",
    re.IGNORECASE,
)
_TITLE_SECRET_HINT = re.compile(_TITLE_SECRET_NAME, re.IGNORECASE)
_TITLE_TOKEN = re.compile(r"\S+")
_TITLE_CREDENTIAL_MIN_CHARS = 8


def _is_credential_literal(token: str) -> bool:
    """True when a whitespace-delimited token looks like a typed credential."""
    candidate = token.strip(".,;:!?()[]{}<>\"'`")
    if len(candidate) < _TITLE_CREDENTIAL_MIN_CHARS:
        return False
    # An address or anything carrying a path separator is an identifier or a
    # URL, not a password — and a URL's secret is the query layer's job, which
    # has already run by the time this is consulted.
    if "@" in candidate or "/" in candidate or "\\" in candidate:
        return False
    has_alpha = any(char.isalpha() for char in candidate)
    has_digit = any(char.isdigit() for char in candidate)
    classes = sum((
        any(char.islower() for char in candidate),
        any(char.isupper() for char in candidate),
        has_digit,
        any(not char.isalnum() for char in candidate),
    ))
    # Mixed alnum (``TempPass123``) or three-plus character classes
    # (``Crrct!Horse``). Requiring one of the two is what keeps the hyphenated
    # and dotted identifiers this product is full of — ``browser-check-target``,
    # ``dev-luban-aiops``, ``web-ui`` — out of the match: they carry two
    # classes at most (lowercase plus punctuation) and no digit.
    return (has_alpha and has_digit) or classes >= 3


def _mask_title_secrets(message: str) -> str:
    """The message with credential material masked, before it becomes a title.

    Layers run most-deterministic first, and each is idempotent on the
    previous one's output (``MASK`` is too short to re-match).
    """
    text = message
    for pattern in REDACTION_VALUE_PATTERNS:
        text = pattern.sub(MASK, text)
    text = redact_secret_query(text)
    text = _TITLE_KEY_VALUE.sub(rf"\1\2{MASK}", text)
    if _TITLE_SECRET_HINT.search(text):
        text = _TITLE_TOKEN.sub(
            lambda match: (
                MASK if _is_credential_literal(match.group(0))
                else match.group(0)
            ),
            text,
        )
    return text


def _assert_session_owner(session: SessionRecord, user_id: str | None) -> None:
    # 404 instead of 403 so foreign session IDs are indistinguishable from
    # unknown ones.
    if session.user_id and user_id and session.user_id != user_id:
        raise HTTPException(status_code=404, detail="session not found")


def create_session(user_id: str | None) -> SessionRecord:
    record_session_created()
    return SESSION_STORE.create_session(user_id)


def create_named_session(session_id: str, user_id: str | None) -> SessionRecord:
    """Get-or-create a caller-supplied dedicated session (SPEC-015 R-3).

    Idempotent for the owning user so re-triage of an incident reuses the
    same session; a foreign owner is indistinguishable from an unknown id.
    The post-create re-read resolves the check-then-create race (Redis
    last-writer-wins) by surfacing a lost race as 404 instead of letting
    two owners share one session.
    """
    existing = SESSION_STORE.get_session(session_id)
    if existing is not None:
        _assert_session_owner(existing, user_id)
        return existing
    record_session_created()
    record = SESSION_STORE.create_session(user_id, session_id=session_id)
    stored = SESSION_STORE.get_session(session_id)
    if stored is None:
        return record
    _assert_session_owner(stored, user_id)
    return stored


def ensure_session(session_id: str | None, user_id: str | None) -> SessionRecord:
    if session_id is None:
        record_session_created()
        return SESSION_STORE.create_session(user_id)
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


def list_sessions(user_id: str) -> list[SessionRecord]:
    """The caller's sessions, most-recently-active first (SPEC-022 R-1).

    Backends that cannot order server-side (memory, Redis) are sorted here;
    the Postgres backend already returns the capped, ordered window.
    """
    records = SESSION_STORE.list_sessions_by_user(user_id)
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
    title = " ".join(_mask_title_secrets(message).split())[:SESSION_TITLE_MAX_LENGTH]
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
