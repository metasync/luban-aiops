"""Platform-owned agent-service contract v2 routes.

This module is the adapter layer between the HTTP boundary and the AgentScope
kernel. No AgentScope types leak through route signatures or response bodies.
Identity is conveyed via headers (X-User-ID, x-request-id), never in bodies.
The gateway-forwarded delegated token arrives as ``Authorization: Bearer`` and
is relayed opaquely to the kernel for tool calls (SPEC-008 R-5); the platform
never inspects or signs it.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from agent_service.core.config import get_settings
from agent_service.core.metrics import record_chat_request
from agent_service.schemas.v2 import (
    AgentChatConfirmRequest,
    AgentChatRequest,
    AgentChatResponse,
    AgentHealth,
    AgentModelCatalog,
    AgentRuntimeMetadata,
    AgentSession,
    AgentSessionCreateRequest,
    AgentSessionList,
    AgentSessionSummary,
    AgentStreamEvent,
    ConfirmationRecordModel,
    DocumentCreateRequest,
    EvidenceTurn,
    SessionTitleUpdateRequest,
)
from agent_service.services.agent_state_store import AGENT_STATE_STORE
from agent_service.services.audit_emitter import (
    build_audit_event,
    emit_audit_event,
)
from agent_service.services.confirmation_records import (
    CONFIRMATION_RECORD_STORE,
)
from agent_service.services.document_prose import generate_prose
from agent_service.services.evidence_store import EVIDENCE_STORE
from agent_service.services.execution_records import EXECUTION_RECORD_STORE
from agent_service.services.hitl_confirmations import (
    ConfirmationExpired,
    ConfirmationNotFound,
)
from agent_service.services.incident_client import (
    IncidentClientRejected,
    IncidentDependencyNotConfigured,
    IncidentNotFound,
    IncidentServiceUnavailable,
    fetch_incident_bundle,
)
from agent_service.services.incident_report import (
    build_digest as build_incident_digest,
    document_summary as incident_document_summary,
)
from agent_service.services.model_catalog import MODEL_CATALOG
from agent_service.services.operation_documents import (
    OPERATION_DOCUMENT_STORE,
    make_document,
)
from agent_service.services.runtime_dependencies import (
    get_confirmation_registry,
    get_runtime_kernel,
)
from agent_service.services.session_service import (
    create_named_session,
    delete_session,
    ensure_session,
    get_session,
    list_sessions,
    mark_session_turn,
    pin_session_model,
    rename_session_title,
)
from agent_service.services.session_store import SESSION_STORE
from agent_service.services.session_transcript import extract_transcript
from agent_service.services.shift_summary import (
    MAX_LABEL_LENGTH,
    DigestInputError,
    ForeignSessionDenied,
    UnknownSessionError,
    build_digest,
    document_summary,
)
from agent_service.services.incident_client import (
    IncidentClientRejected,
    IncidentDependencyNotConfigured,
    IncidentNotFound,
    IncidentServiceUnavailable,
)
from agent_service.services.skill_draft import (
    ANCHOR_INCIDENT,
    ANCHOR_SESSION,
    MODE_GENERATED,
    MODE_SKELETON,
    NoValidatedTriageReport,
    assemble_markdown,
    build_incident_skeleton,
    build_incident_skill_draft_bundle,
    build_skill_draft_bundle,
    build_skeleton,
    generate_skill_draft,
)
from agent_service.services.skills_client import (
    SkillsClientRejected,
    SkillsDependencyNotConfigured,
    SkillsServiceUnavailable,
    is_configured as skills_validation_configured,
    validate_skill_draft,
)

router = APIRouter(prefix="/api/v2")

LOGGER = logging.getLogger(__name__)


def _user_id(x_user_id: str | None) -> str:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-ID header required")
    return x_user_id


def _bearer_token(authorization: str | None) -> str | None:
    """Extract the raw bearer token forwarded by the gateway (SPEC-008 R-5)."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


async def _reject_if_parked(session_id: str) -> None:
    """SPEC-020 R-2: a parked session rejects new turns until resolved.

    A TTL-expired park is closed through ``expire_confirmation``
    (``UserInterruptEvent``) before the new turn proceeds — the kernel
    cannot accept a fresh message while a reply sits parked, so silent
    eviction would wedge the session.
    """
    kernel = get_runtime_kernel()
    pending = get_confirmation_registry().peek_parked(session_id)
    if pending is None:
        return
    if pending.is_expired(kernel.settings.hitl_confirm_timeout):
        try:
            await kernel.expire_confirmation(session_id, pending.confirm_id)
        except ConfirmationNotFound:
            # A concurrent confirm or expiry claimed the entry first — the
            # session is still busy with the resumed stream, so the new
            # turn stays rejected until that stream resolves the entry.
            raise HTTPException(
                status_code=409,
                detail="confirmation pending: the parked tool confirmation "
                "is being resolved; retry shortly",
            ) from None
        return
    raise HTTPException(
        status_code=409,
        detail="confirmation pending: answer or expire the parked "
        "tool confirmation before sending a new message",
    )


def _resolve_model(requested: str | None, pinned: str | None) -> str | None:
    """Resolve the model id for a turn (SPEC-024 R-3): request > pinned > default.

    An explicitly requested id must exist in the credential-gated
    catalog — unknown ids fail closed with 422, never a silent default.
    A pinned id is honored only while it still exists in the catalog
    (a key revocation degrades the session back to the default).
    Resolved ids are normalized to the concrete catalog entry (bare
    provider names alias to the provider default, SPEC-026 R-3), so
    pinning and audit attribution carry model names.
    """
    if requested:
        entry = MODEL_CATALOG.get(requested)
        if entry is None:
            raise HTTPException(
                status_code=422,
                detail=f"unknown model id: {requested}",
            )
        return entry.id
    if pinned:
        entry = MODEL_CATALOG.get(pinned)
        if entry is not None:
            return entry.id
    default = MODEL_CATALOG.default_entry()
    return default.id if default is not None else None


# --- Chat ---


@router.post("/chat", response_model=AgentChatResponse)
async def chat(
    body: AgentChatRequest,
    x_user_id: str | None = Header(None),
    x_request_id: str | None = Header(None),
    authorization: str | None = Header(None),
) -> AgentChatResponse:
    user_id = _user_id(x_user_id)
    request_id = x_request_id or "untracked"
    record_chat_request()
    session = ensure_session(body.session_id, user_id)
    await _reject_if_parked(session.session_id)
    resolved_model = _resolve_model(body.model, session.model)
    pin_session_model(session.session_id, resolved_model)
    # SPEC-024 R-4: the serving model rides the audit trail via the
    # response; the structured log keeps the runtime-side view.
    LOGGER.info(
        "chat turn model resolved",
        extra={
            "request_id": request_id,
            "session_id": session.session_id,
            "model": resolved_model,
            "requested_model": body.model,
        },
    )
    mark_session_turn(session.session_id, body.message)
    content, structured_output = await get_runtime_kernel().reply_text(
        message=body.message,
        session_id=session.session_id,
        user_name=user_id,
        bearer_token=_bearer_token(authorization),
        response_schema=body.response_schema,
        model_id=resolved_model,
        read_only=body.read_only,
    )
    return AgentChatResponse(
        session_id=session.session_id,
        request_id=request_id,
        content=content,
        structured_output=structured_output,
        model=resolved_model,
    )


@router.get("/chat/stream")
async def chat_stream(
    message: str,
    session_id: str | None = None,
    # SPEC-024 R-3: per-turn model selection, resolved request > pinned >
    # default; unknown ids fail closed with 422 before headers go out.
    model: str | None = None,
    # SPEC-023 R-4: voice-readiness parity with POST /chat's body field —
    # modality is metadata only and never changes policy or HITL outcomes.
    input_modality: Literal["text", "voice"] = "text",
    x_user_id: str | None = Header(None),
    x_request_id: str | None = Header(None),
    authorization: str | None = Header(None),
) -> StreamingResponse:
    user_id = _user_id(x_user_id)
    request_id = x_request_id or "untracked"
    record_chat_request()
    session = ensure_session(session_id, user_id)
    await _reject_if_parked(session.session_id)
    resolved_model = _resolve_model(model, session.model)
    pin_session_model(session.session_id, resolved_model)
    LOGGER.info(
        "chat stream model resolved",
        extra={
            "request_id": request_id,
            "session_id": session.session_id,
            "model": resolved_model,
            "requested_model": model,
        },
    )
    mark_session_turn(session.session_id, message)
    bearer_token = _bearer_token(authorization)

    async def _events() -> AsyncIterator[str]:
        async for chunk in get_runtime_kernel().stream_events(
            message=message,
            request_id=request_id,
            session_id=session.session_id,
            user_name=user_id,
            bearer_token=bearer_token,
            model_id=resolved_model,
        ):
            event = _normalize_stream_event(chunk, session.session_id, request_id)
            yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"

    return StreamingResponse(_events(), media_type="text/event-stream")


@router.post("/chat/confirm")
async def chat_confirm(
    body: AgentChatConfirmRequest,
    x_user_id: str | None = Header(None),
    x_request_id: str | None = Header(None),
    authorization: str | None = Header(None),
) -> StreamingResponse:
    """Answer a parked kernel confirmation and stream the resumed turn.

    SPEC-020 R-2, relaxed by SPEC-030 R-3: who may decide is enforced by
    the platform-gateway approval-tier bridge before the decision is
    proxied, so the session lookup no longer asserts ownership — a
    tier_2 approver legitimately confirms a session they do not own.
    Registry errors still map to 404/410, and the entry is claimed
    before any headers go out, so a duplicate confirm fails closed with
    404 instead of double-resuming the parked batch.
    """
    user_id = _user_id(x_user_id)
    request_id = x_request_id or "untracked"
    session = get_session(body.session_id)
    kernel = get_runtime_kernel()
    registry = get_confirmation_registry()
    try:
        pending = registry.claim(
            session.session_id,
            body.confirm_id,
            kernel.settings.hitl_confirm_timeout,
        )
    except ConfirmationExpired:
        try:
            await kernel.expire_confirmation(
                session.session_id, body.confirm_id
            )
        except ConfirmationNotFound:
            # A concurrent request already closed the expired entry.
            pass
        raise HTTPException(
            status_code=410, detail="confirmation expired"
        ) from None
    except ConfirmationNotFound:
        # SPEC-031 R-4: a record that already resolved answers with its
        # outcome (stale tab, racing approver) instead of an opaque 404;
        # genuinely unknown ids stay 404 for anti-enumeration.
        record = _resolved_record(session.session_id, body.confirm_id)
        if record is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "reason": "already_resolved",
                    "status": record["status"],
                    "decider_user_id": record["decider_user_id"],
                    "decision": record["decision"],
                    "decided_at": record["decided_at"],
                },
            ) from None
        raise HTTPException(
            status_code=404, detail="confirmation not found"
        ) from None

    # SPEC-031 R-4: persist the outcome at claim time — the claim is
    # single-flight and the decision irrevocable once claimed, so racing
    # approvers answering while the resumed turn still streams get the
    # structured 409 above instead of an opaque 404. The resume's
    # ``finally`` write remains as an idempotent safety net.
    _persist_claimed_outcome(
        session.session_id, body.confirm_id, body.decision, user_id
    )

    async def _events() -> AsyncIterator[str]:
        async for chunk in kernel.resume_confirmation(
            session_id=session.session_id,
            pending=pending,
            decision=body.decision,
            user_name=user_id,
            request_id=request_id,
            bearer_token=_bearer_token(authorization),
            # SPEC-024 R-3: the resumed stream stays on the model that
            # parked it; a stale pin (evicted by discovery refresh or
            # key revocation) degrades to the default like other turns
            # instead of raising UnknownModelError mid-resume.
            model_id=_resolve_model(None, session.model),
        ):
            event = _normalize_stream_event(
                chunk, session.session_id, request_id
            )
            yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"

    return StreamingResponse(_events(), media_type="text/event-stream")


@router.get("/chat/pending-confirmation")
async def get_pending_confirmation(
    session_id: str,
    x_user_id: str | None = Header(None),
) -> dict:
    """Parked-confirmation metadata for the approval bridge (SPEC-030 R-3).

    The platform-gateway confirm bridge reads the parked batch's policy
    action and the owner username before proxying a decision, so the
    tier checks (decider role, self-approval) run against authoritative
    state. No ownership assertion here — the gateway decides who may
    approve; unknown or unparked sessions 404.
    """
    _user_id(x_user_id)
    # Unknown session ids stay indistinguishable from unparked ones.
    get_session(session_id)
    pending = get_confirmation_registry().peek_parked(session_id)
    if pending is not None:
        return {
            "session_id": session_id,
            "confirm_id": pending.confirm_id,
            "owner_user_id": pending.user_id,
            "action": pending.highest_action(),
            "pending_calls": pending.pending_calls_payload(),
        }
    # SPEC-031 R-1: the durable record answers the approval bridge when
    # the in-memory registry does not hold the park (a replica that did
    # not park it). Resume still requires the parking process; the bridge
    # only needs the authoritative metadata for its tier checks.
    record = CONFIRMATION_RECORD_STORE.load_pending_for_session(session_id)
    if record is None:
        raise HTTPException(
            status_code=404, detail="no pending confirmation"
        )
    return {
        "session_id": session_id,
        "confirm_id": record["confirm_id"],
        "owner_user_id": record["owner_user_id"],
        "action": record["action"],
        "pending_calls": record["pending_calls"],
    }


def _persist_claimed_outcome(
    session_id: str, confirm_id: str, decision: str, decider_user_id: str
) -> None:
    """Best-effort durable outcome write at claim time (SPEC-031 R-4).

    Mirrors the kernel's resolution write posture: a store failure only
    degrades the race response and persisted history, never the decision
    itself (the resumed stream still flows).
    """
    status = "approved" if decision == "approve" else "denied"
    try:
        CONFIRMATION_RECORD_STORE.mark_resolved(
            session_id, confirm_id, status, decider_user_id, decision
        )
    except Exception as exc:
        LOGGER.warning(
            "confirmation record claim-time resolution failed for session %s: %s",
            session_id,
            exc,
        )


def _resolved_record(session_id: str, confirm_id: str) -> dict | None:
    """A durable record that already resolved (SPEC-031 R-4).

    ``None`` for unknown ids and for records still pending (a pending
    record without a registry entry cannot be resumed here; it keeps the
    404 posture of the confirm path instead of masquerading as decided).
    """
    try:
        record = CONFIRMATION_RECORD_STORE.load_record(session_id, confirm_id)
    except Exception as exc:
        LOGGER.warning(
            "confirmation record store unreadable for %s: %s",
            session_id,
            exc,
        )
        return None
    if record is None or record["status"] == "pending":
        return None
    return record


_STREAM_EVENT_TYPES = frozenset(
    {
        "message_start",
        "message_delta",
        "message_end",
        "error",
        "tool_call",
        "tool_result",
        "confirmation_request",
        "confirmation_result",
    }
)

_TOOL_RESULT_STATUSES = frozenset(
    {"success", "error", "denied", "approved", "expired", "interrupted"}
)

# v6 stream schema allows these risk levels on pending_calls entries.
_PENDING_CALL_RISK_LEVELS = frozenset({"read", "write", "admin"})

# v8 (SPEC-030 R-3): the policy action a parked call maps to, derived
# from its risk tier; the confirm bridge evaluates this action.
_PENDING_CALL_ACTIONS = frozenset({"tools:invoke", "tools:mutate"})

# v9 (SPEC-051 R-6): the card-level browser-flow headline fields the
# stream schema allows on a confirmation_request frame. Mirrors the
# kernel's FlowContext.summary() and the durable record's flow_summary.
# v10 (SPEC-053 R-2) adds ``flow_intent`` — the author-written gated-step
# intent the card renders as its lead decision line (display-only).
_FLOW_SUMMARY_FIELDS = (
    "skill_id",
    "origin",
    "title",
    "description",
    "flow_intent",
    "risk_class",
)


def _normalize_stream_event(
    raw: dict[str, object], session_id: str, request_id: str
) -> AgentStreamEvent:
    """Translate a kernel stream chunk into a contract-conformant event.

    tool_call / tool_result frames carry the evidence-panel payload
    (SPEC-011 R-1) and must pass through untouched; anything unrecognized
    still degrades to message_delta for safety.
    """
    event_type = str(raw.get("event", raw.get("type", "message_delta")))
    if event_type not in _STREAM_EVENT_TYPES:
        event_type = "message_delta"
    return AgentStreamEvent(
        type=event_type,  # type: ignore[arg-type]
        session_id=session_id,
        request_id=request_id,
        delta=raw.get("delta") if isinstance(raw.get("delta"), str) else None,
        message=raw.get("message") if isinstance(raw.get("message"), str) else None,
        confirm_id=(
            raw.get("confirm_id")
            if isinstance(raw.get("confirm_id"), str)
            else None
        ),
        pending_calls=_coerce_pending_calls(raw.get("pending_calls")),
        # SPEC-051 R-6: the browser-flow headline rides confirmation_request
        # frames so the live operator card matches the durable record the
        # approver inbox renders; coerced to the contract fields or None.
        flow_summary=_coerce_flow_summary(raw.get("flow_summary")),
        tool_name=raw.get("tool_name") if isinstance(raw.get("tool_name"), str) else None,
        call_id=raw.get("call_id") if isinstance(raw.get("call_id"), str) else None,
        parameters=(
            raw.get("parameters") if isinstance(raw.get("parameters"), dict) else None
        ),
        status=(
            raw.get("status")  # type: ignore[arg-type]
            if raw.get("status") in _TOOL_RESULT_STATUSES
            else None
        ),
        evidence=raw.get("evidence") if isinstance(raw.get("evidence"), dict) else None,
        data_summary=_coerce_data_summary(raw.get("data_summary")),
        # SPEC-024 R-3: message_end frames carry the serving model id.
        model=raw.get("model") if isinstance(raw.get("model"), str) else None,
        # Full tool payload (v5): already size-capped by the evidence
        # middleware, so pass it through untouched.
        data=raw.get("data"),
        error=raw.get("error") if isinstance(raw.get("error"), dict) else None,
    )


def _coerce_data_summary(value: object) -> dict[str, object] | None:
    """The contract requires an object; wrap non-object summaries safely."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    return {"value": value}


def _coerce_pending_calls(value: object) -> list[dict[str, object]] | None:
    """Keep confirmation_request batches schema-conformant (SPEC-020 R-1)."""
    if not isinstance(value, list):
        return None
    calls: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        call_id = item.get("call_id")
        tool_name = item.get("tool_name")
        parameters = item.get("parameters")
        entry: dict[str, object] = {
            "call_id": call_id if isinstance(call_id, str) else "",
            "tool_name": tool_name if isinstance(tool_name, str) else "",
            "parameters": (
                parameters if isinstance(parameters, dict) else {}
            ),
        }
        # v6 (SPEC-021 R-3): the portal flags mutating batches from this
        # field, so pass through schema-conformant values and omit the
        # optional field otherwise (task tools carry no risk level).
        risk_level = item.get("risk_level")
        if isinstance(risk_level, str) and risk_level in _PENDING_CALL_RISK_LEVELS:
            entry["risk_level"] = risk_level
        # v8 (SPEC-030 R-3): pass the bridged policy action through when
        # schema-conformant; omitted for calls without a gateway risk tier.
        action = item.get("action")
        if isinstance(action, str) and action in _PENDING_CALL_ACTIONS:
            entry["action"] = action
        # SPEC-050 follow-up: pass the element description for browser
        # interaction tools so the portal shows what element will be
        # affected, not just the raw ref number.
        display_hint = item.get("display_hint")
        if isinstance(display_hint, str) and display_hint:
            entry["display_hint"] = display_hint
        calls.append(entry)
    return calls or None


def _coerce_flow_summary(value: object) -> dict[str, object] | None:
    """Keep the confirmation_request flow headline schema-conformant
    (SPEC-051 R-6). Returns None when no browser flow is bound so the
    card falls back to plain tool-action rendering; only the contract's
    string fields survive, so a malformed summary can never make the
    frame fail additionalProperties:false validation."""
    if not isinstance(value, dict):
        return None
    summary: dict[str, object] = {}
    for field in _FLOW_SUMMARY_FIELDS:
        item = value.get(field)
        if isinstance(item, str):
            summary[field] = item
    return summary or None


# --- Sessions ---


def _load_evidence_turns(session_id: str) -> list[EvidenceTurn] | None:
    """Persisted evidence groups for the session-detail surface (SPEC-025 R-2).

    Empty list when the session stored none; ``None`` when the evidence
    store is unreadable — degrades like ``transcript_available=false``,
    never a 500.
    """
    try:
        return [
            EvidenceTurn(**turn) for turn in EVIDENCE_STORE.load_turns(session_id)
        ]
    except Exception as exc:
        LOGGER.warning(
            "evidence store unreadable for session %s: %s", session_id, exc
        )
        return None


def _load_confirmation_cards(
    session_id: str,
) -> list[ConfirmationRecordModel] | None:
    """Durable confirmation cards for the session detail (SPEC-031 R-2).

    ``None`` when the record store is unreadable — degrades like
    ``evidence_turns``, never a 500. Approved-execution rows ride each
    card under ``executions`` (SPEC-037 R-4); an unreadable execution
    store degrades to empty rows, never a card failure.
    """
    try:
        records = CONFIRMATION_RECORD_STORE.load_for_session(session_id)
    except Exception as exc:
        LOGGER.warning(
            "confirmation record store unreadable for session %s: %s",
            session_id,
            exc,
        )
        return None
    try:
        executions = EXECUTION_RECORD_STORE.load_for_session(session_id)
    except Exception as exc:
        LOGGER.warning(
            "execution record store unreadable for session %s: %s",
            session_id,
            exc,
        )
        executions = []
    by_confirm: dict[str, list[dict]] = {}
    for row in executions:
        by_confirm.setdefault(row["confirm_id"], []).append(row)
    return [
        ConfirmationRecordModel(
            **record, executions=by_confirm.get(record["confirm_id"], [])
        )
        for record in records
    ]


@router.post("/sessions", response_model=AgentSession, status_code=201)
async def create_session(
    body: AgentSessionCreateRequest | None = None,
    x_user_id: str | None = Header(None),
) -> AgentSession:
    user_id = _user_id(x_user_id)
    requested_id = body.session_id.strip() if body and body.session_id else ""
    if requested_id:
        # Dedicated named session (SPEC-015 R-3): idempotent for the owner.
        session = create_named_session(requested_id, user_id)
    else:
        session = ensure_session(None, user_id)
    return AgentSession(
        session_id=session.session_id,
        user_id=session.user_id or user_id,
        created_at=session.created_at,
        status=session.status,  # type: ignore[arg-type]
    )


@router.get("/sessions", response_model=AgentSessionList)
async def list_sessions_route(
    x_user_id: str | None = Header(None),
) -> AgentSessionList:
    """The caller's sessions, most-recently-active first, capped (SPEC-022 R-1)."""
    user_id = _user_id(x_user_id)
    registry = get_confirmation_registry()
    return AgentSessionList(
        sessions=[
            AgentSessionSummary(
                session_id=record.session_id,
                title=record.title,
                created_at=record.created_at,
                last_active_at=record.last_active_at,
                pending_confirmation=registry.has_pending(record.session_id),
            )
            for record in list_sessions(user_id)
        ]
    )


@router.get("/sessions/{session_id}", response_model=AgentSession)
async def read_session(
    session_id: str,
    x_user_id: str | None = Header(None),
) -> AgentSession:
    user_id = _user_id(x_user_id)
    session = get_session(session_id, user_id)
    transcript_available, transcript = extract_transcript(session.session_id)
    return AgentSession(
        session_id=session.session_id,
        user_id=session.user_id or user_id,
        created_at=session.created_at,
        status=session.status,  # type: ignore[arg-type]
        title=session.title,
        last_active_at=session.last_active_at,
        model=session.model,
        pending_confirmation=get_confirmation_registry().has_pending(
            session.session_id
        ),
        transcript_available=transcript_available,
        transcript=transcript,
        evidence_turns=_load_evidence_turns(session.session_id),
        confirmations=_load_confirmation_cards(session.session_id),
    )


@router.delete("/sessions/{session_id}")
async def delete_session_route(
    session_id: str,
    x_user_id: str | None = Header(None),
) -> dict:
    """Owner-only session delete (SPEC-022 R-1).

    Foreign or unknown ids 404 per the anti-enumeration house convention;
    a session holding a parked confirmation 409s so a delete can never
    orphan an awaiting-approval workflow.

    Known limitation: the parked check is check-then-act. If a chat turn
    is still in flight on this session during the delete, its tail may
    park a confirmation and re-snapshot agent state after the delete
    completed, recreating the durable snapshot. Avoid deleting a session
    while its last turn is still streaming; a conditional-delete design
    is tracked as follow-up hardening.
    """
    user_id = _user_id(x_user_id)
    session = get_session(session_id, user_id)
    if get_confirmation_registry().has_pending(session.session_id):
        raise HTTPException(
            status_code=409,
            detail="session has a parked confirmation: resolve it before "
            "deleting the session",
        )
    if not delete_session(session.session_id, user_id):
        raise HTTPException(status_code=404, detail="session not found")
    return {"session_id": session.session_id, "deleted": True}


@router.patch("/sessions/{session_id}/title", response_model=AgentSession)
async def rename_session_route(
    session_id: str,
    body: SessionTitleUpdateRequest,
    x_user_id: str | None = Header(None),
) -> AgentSession:
    """Owner session rename (SPEC-039 R-7).

    Supersedes the SPEC-022 server-minted set-once title: the rename
    overwrites whatever title the session carries. 1–80 characters after
    trimming; foreign or unknown ids answer 404 per the anti-enumeration
    convention. Renames are not audited (owner-side cosmetic act on
    one's own record; recorded design decision).
    """
    user_id = _user_id(x_user_id)
    title = " ".join(body.title.split())
    if not title or len(title) > 80:
        raise HTTPException(
            status_code=400,
            detail="title must be 1-80 characters after trimming",
        )
    session = rename_session_title(session_id, title, user_id)
    return AgentSession(
        session_id=session.session_id,
        user_id=session.user_id or user_id,
        created_at=session.created_at,
        status=session.status,  # type: ignore[arg-type]
        title=session.title,
        last_active_at=session.last_active_at,
        model=session.model,
    )


# --- Skill-draft export (SPEC-044) ---


async def _validate_skill_markdown(
    settings, request_id: str | None, markdown: str
) -> tuple[bool, str | None]:
    """Validate a draft on skills-hub's own ingestion code path (R-2).

    Structured errors map to the house posture: not configured 503,
    unreachable or upstream 5xx 502, any other 4xx passed through — an
    unvalidated draft is never returned.
    """
    try:
        return await validate_skill_draft(settings, request_id, markdown)
    except SkillsDependencyNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except SkillsServiceUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except SkillsClientRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None


@router.post("/sessions/{session_id}/skill-draft")
async def create_skill_draft(
    session_id: str,
    x_user_id: str | None = Header(None),
    x_request_id: str | None = Header(None),
) -> dict:
    """Generate a validated skill draft from one session (SPEC-044 R-1/R-2).

    Authorization (``session:skill_draft``) is enforced by the
    platform-gateway; ownership is re-checked server-side — foreign or
    unknown ids answer the structural 404. The draft is validated against
    Skill Format v1 before it is returned: validation not configured 503,
    unreachable 502 — an unvalidated draft is never returned. Nothing is
    persisted; the response is the artifact (ephemeral by construction).
    """
    user_id = _user_id(x_user_id)
    session = get_session(session_id, user_id)
    settings = get_settings()
    if not skills_validation_configured(settings):
        raise HTTPException(
            status_code=503,
            detail="skills service not configured for skill-draft validation",
        )
    bundle, incident_id = await build_skill_draft_bundle(
        settings, user_id, session.session_id, x_request_id
    )

    markdown, slug, mode = await _validated_draft_sequence(
        settings,
        x_request_id,
        bundle,
        session_id=session.session_id,
        incident_id=incident_id,
        skeleton_builder=build_skeleton,
    )

    details: dict = {
        "session_id": session.session_id,
        "mode": mode,
        "validation": "passed",
    }
    if incident_id:
        details["incident_id"] = incident_id
    _emit_document_audit("skill_draft_generated", user_id, x_request_id, details)
    LOGGER.info(
        "skill draft generated",
        extra={
            "request_id": x_request_id,
            "session_id": session.session_id,
            "incident_id": incident_id,
            "user_id": user_id,
            "mode": mode,
        },
    )
    return {
        "markdown": markdown,
        "mode": mode,
        "validation": "passed",
        "suggested_filename": f"{slug}.md",
    }


async def _validated_draft_sequence(
    settings,
    request_id: str | None,
    bundle: dict,
    *,
    session_id: str | None,
    incident_id: str | None,
    skeleton_builder,
    anchor: str = ANCHOR_SESSION,
) -> tuple[str, str, str]:
    """Shared generate → validate → bounded-regenerate → skeleton sequence.

    Both anchors run the identical SPEC-044 sequence (shared helpers,
    SPEC-045 R-1): generation never raises — any failure degrades to the
    anchor's facts-only skeleton, which is always format-valid; a second
    validation failure answers 502, never an unvalidated draft.
    Returns ``(markdown, slug, mode)``.
    """

    async def _generate(rejection_reason: str | None = None):
        if anchor == ANCHOR_SESSION:
            # The v0.26.0 call shape, pinned by the session suite.
            return await generate_skill_draft(
                get_runtime_kernel(), bundle, rejection_reason
            )
        return await generate_skill_draft(
            get_runtime_kernel(), bundle, rejection_reason, anchor=anchor
        )

    parsed = await _generate()
    if parsed is not None:
        frontmatter, body = parsed
        mode = MODE_GENERATED
    else:
        frontmatter, body = skeleton_builder(bundle)
        mode = MODE_SKELETON
    markdown, slug = assemble_markdown(
        frontmatter, body, session_id, incident_id, mode
    )

    valid, reason = await _validate_skill_markdown(settings, request_id, markdown)
    if not valid and mode == MODE_GENERATED:
        # One bounded regeneration with the rejection reason in the prompt.
        parsed = await _generate(reason)
        if parsed is not None:
            frontmatter, body = parsed
            markdown, slug = assemble_markdown(
                frontmatter, body, session_id, incident_id, MODE_GENERATED
            )
            valid, reason = await _validate_skill_markdown(
                settings, request_id, markdown
            )
    if not valid:
        # Second failure degrades to the facts-only skeleton, validated on
        # the same path — the operator always holds a format-valid file.
        frontmatter, body = skeleton_builder(bundle)
        mode = MODE_SKELETON
        markdown, slug = assemble_markdown(
            frontmatter, body, session_id, incident_id, mode
        )
        valid, reason = await _validate_skill_markdown(
            settings, request_id, markdown
        )
        if not valid:
            raise HTTPException(
                status_code=502,
                detail="skill-draft skeleton failed format validation",
            )
    return markdown, slug, mode


@router.post("/incidents/{incident_id}/skill-draft")
async def create_incident_skill_draft(
    incident_id: str,
    x_user_id: str | None = Header(None),
    x_request_id: str | None = Header(None),
) -> dict:
    """Generate a validated skill draft from one incident (SPEC-045 R-1).

    Authorization (``incident:skill_draft`` dual-gated with
    ``incident:read``) is enforced by the platform-gateway. The bundle is
    the incident envelope (``triage_raw`` stripped) plus the validated
    triage report — never anyone's session. Without a validated triage
    report the route answers a deterministic 409 before any generation
    work. The draft is validated against Skill Format v1 before it is
    returned: validation not configured 503, unreachable 502 — an
    unvalidated draft is never returned. Nothing is persisted.
    """
    user_id = _user_id(x_user_id)
    settings = get_settings()
    if not skills_validation_configured(settings):
        raise HTTPException(
            status_code=503,
            detail="skills service not configured for skill-draft validation",
        )
    try:
        bundle = await build_incident_skill_draft_bundle(
            settings, x_request_id, incident_id
        )
    except IncidentDependencyNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except IncidentServiceUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except IncidentNotFound as exc:
        raise HTTPException(status_code=404, detail="incident not found") from exc
    except IncidentClientRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
    except NoValidatedTriageReport as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "no validated triage report to draft from — run triage first"
            ),
        ) from exc

    markdown, slug, mode = await _validated_draft_sequence(
        settings,
        x_request_id,
        bundle,
        session_id=None,
        incident_id=incident_id,
        skeleton_builder=build_incident_skeleton,
        anchor=ANCHOR_INCIDENT,
    )

    details: dict = {
        "incident_id": incident_id,
        "mode": mode,
        "validation": "passed",
    }
    _emit_document_audit(
        "incident_skill_draft_generated", user_id, x_request_id, details
    )
    LOGGER.info(
        "incident skill draft generated",
        extra={
            "request_id": x_request_id,
            "incident_id": incident_id,
            "user_id": user_id,
            "mode": mode,
        },
    )
    return {
        "markdown": markdown,
        "mode": mode,
        "validation": "passed",
        "suggested_filename": f"{slug}.md",
    }


# --- Operations document repository (SPEC-039) ---


def _emit_document_audit(
    event_type: str,
    user_id: str,
    request_id: str | None,
    details: dict,
) -> None:
    """Fire-and-forget document audit event (SPEC-039 R-5).

    Emission failures never block the document operation; an
    unconfigured audit service keeps the historical log-only behavior.
    """
    event = build_audit_event(
        event_type,
        request_id,
        "success",
        details=details,
        subject=user_id,
        username=user_id,
    )
    emit_audit_event(get_settings(), event)


@router.post("/documents", status_code=201)
async def create_document(
    body: DocumentCreateRequest,
    x_user_id: str | None = Header(None),
    x_request_id: str | None = Header(None),
    x_foreign_coverage: str | None = Header(default=None),
) -> dict:
    """Create a typed operations document (SPEC-039 R-1/R-3, SPEC-043).

    Authorization (``documents:create``, plus ``incident:read`` for
    ``incident_report``) is enforced by the platform-gateway.
    ``X-Foreign-Coverage`` is the gateway-computed ``approvals:list``
    capability marker (trusted internal header, same trust model as
    ``X-User-ID``); it fails closed — an absent or unrecognized value
    denies foreign coverage.
    """
    user_id = _user_id(x_user_id)
    label = " ".join(body.label.split())
    if not label or len(label) > MAX_LABEL_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"label must be 1-{MAX_LABEL_LENGTH} characters after trimming",
        )
    can_view_foreign = (x_foreign_coverage or "").strip().lower() == "allowed"
    if body.document_type == "incident_report":
        digest, provenance = await _build_incident_report_digest(
            user_id, body.incident_id, can_view_foreign, x_request_id
        )
        summary = incident_document_summary(digest)
    else:
        try:
            digest, provenance = build_digest(
                user_id, list(body.session_ids), can_view_foreign
            )
        except UnknownSessionError as exc:
            # Structural rejection; nothing about ownership is revealed.
            raise HTTPException(
                status_code=400, detail=f"unknown session ids: {exc.session_ids}"
            ) from None
        except ForeignSessionDenied as exc:
            raise HTTPException(
                status_code=403,
                detail=(
                    "foreign session coverage requires the approvals:list "
                    f"capability: {exc.session_ids}"
                ),
            ) from None
        except DigestInputError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        # SPEC-041 R-4: counts-only list summary, derived at creation.
        summary = document_summary(digest)

    if body.include_prose:
        prose, blurb, prose_status = await generate_prose(
            get_runtime_kernel(), body.document_type, digest
        )
    else:
        prose, blurb, prose_status = None, None, "not_requested"

    document_id = f"doc-{uuid.uuid4()}"
    document = make_document(
        document_id=document_id,
        document_type=body.document_type,
        owner_user_id=user_id,
        label=label,
        provenance=provenance,
        digest=digest,
        prose=prose,
        prose_status=prose_status,
        summary=summary,
        # v0.23.3: the AI one-liner rides with the prose reply.
        blurb=blurb,
    )
    OPERATION_DOCUMENT_STORE.create(document)
    own_count = sum(
        1 for row in provenance["sessions"] if row["coverage"] == "owner"
    )
    foreign_count = len(provenance["sessions"]) - own_count
    cited_count = sum(
        len(row["cited_record_ids"]) for row in provenance["sessions"]
    )
    audit_details = {
        "document_id": document_id,
        "document_type": body.document_type,
        "own_session_count": own_count,
        "foreign_session_count": foreign_count,
        "cited_record_count": cited_count,
        "prose_status": prose_status,
    }
    # SPEC-043 R-5: the only audit payload addition — the covered
    # incident id rides document_created as provenance.
    if body.document_type == "incident_report":
        audit_details["incident_id"] = provenance.get("incident_id")
    _emit_document_audit(
        "document_created",
        user_id,
        x_request_id,
        audit_details,
    )
    LOGGER.info(
        "operation document created",
        extra={
            "request_id": x_request_id,
            "document_id": document_id,
            "document_type": body.document_type,
            "user_id": user_id,
            "prose_status": prose_status,
            "incident_id": provenance.get("incident_id"),
        },
    )
    return OPERATION_DOCUMENT_STORE.load(document_id) or document


async def _build_incident_report_digest(
    user_id: str,
    incident_id: str | None,
    can_view_foreign: bool,
    request_id: str | None,
) -> tuple[dict, dict]:
    """Fetch the incident bundle and assemble the digest (SPEC-043 R-2).

    Degradation is the house posture, never a 500: not configured is
    503, an unreachable incident-service is 502, an unknown incident id
    answers the same structural 404 the incidents surface returns, and
    any other upstream 4xx passes through.
    """
    try:
        bundle = await fetch_incident_bundle(
            get_settings(), request_id, incident_id or ""
        )
    except IncidentDependencyNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except IncidentServiceUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except IncidentNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail=f"unknown incident id: {exc.incident_id}",
        ) from None
    except IncidentClientRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
    return build_incident_digest(user_id, bundle, can_view_foreign)


@router.get("/documents")
async def list_documents(
    scope: Literal["mine", "published"] = Query(default="mine"),
    x_user_id: str | None = Header(None),
) -> dict:
    """List document envelopes (SPEC-039 R-2).

    ``mine`` returns the caller's drafts and published documents;
    ``published`` returns the team-visible surface — drafts never
    appear there for anyone, including admins.

    Rows are envelope-only: ``digest`` and ``prose`` are stripped so
    the full content of someone else's document is only ever served
    by the single fetch below, which is the audited surface (R-5).
    """
    user_id = _user_id(x_user_id)
    if scope == "mine":
        rows = OPERATION_DOCUMENT_STORE.list_for_owner(user_id)
    else:
        rows = OPERATION_DOCUMENT_STORE.list_published()
    envelopes = [
        {key: value for key, value in row.items() if key not in ("digest", "prose")}
        for row in rows
    ]
    return {"documents": envelopes}


@router.get("/documents/{document_id}")
async def read_document(
    document_id: str,
    x_user_id: str | None = Header(None),
    x_request_id: str | None = Header(None),
) -> dict:
    """Read one document; drafts stay owner-only (SPEC-039 R-2).

    Cross-owner reads of published documents are the policed surface
    and always emit ``document_read`` (SPEC-039 R-5); own reads are
    not audited.
    """
    user_id = _user_id(x_user_id)
    document = OPERATION_DOCUMENT_STORE.load(document_id)
    # Foreign drafts are indistinguishable from unknown documents.
    if document is None or (
        document["state"] == "draft" and document["owner_user_id"] != user_id
    ):
        raise HTTPException(status_code=404, detail="document not found")
    if document["owner_user_id"] != user_id:
        _emit_document_audit(
            "document_read",
            user_id,
            x_request_id,
            {
                "document_id": document_id,
                "document_type": document["document_type"],
                "owner_user_id": document["owner_user_id"],
            },
        )
    return document


@router.post("/documents/{document_id}/publish")
async def publish_document(
    document_id: str,
    x_user_id: str | None = Header(None),
    x_request_id: str | None = Header(None),
) -> dict:
    """Publish one's own draft (SPEC-039 R-1: one-way owner action)."""
    user_id = _user_id(x_user_id)
    document = OPERATION_DOCUMENT_STORE.load(document_id)
    if document is None or document["owner_user_id"] != user_id:
        raise HTTPException(status_code=404, detail="document not found")
    if document["state"] == "published":
        raise HTTPException(
            status_code=409, detail="document is already published"
        )
    if not OPERATION_DOCUMENT_STORE.publish(user_id, document_id):
        raise HTTPException(
            status_code=409, detail="document could not be published"
        )
    _emit_document_audit(
        "document_published",
        user_id,
        x_request_id,
        {
            "document_id": document_id,
            "document_type": document["document_type"],
        },
    )
    return OPERATION_DOCUMENT_STORE.load(document_id)


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    x_user_id: str | None = Header(None),
) -> dict:
    """Delete one's own document (SPEC-039 R-1).

    Published documents can be deleted by their owner but never edited;
    own deletes are not audited (no cross-user surface is policed).
    """
    user_id = _user_id(x_user_id)
    document = OPERATION_DOCUMENT_STORE.load(document_id)
    if document is None or document["owner_user_id"] != user_id:
        raise HTTPException(status_code=404, detail="document not found")
    OPERATION_DOCUMENT_STORE.delete(user_id, document_id)
    return {"document_id": document_id, "deleted": True}


# --- Approvals inbox (SPEC-031 R-3) ---


@router.get("/confirmations")
async def list_confirmations(
    history_limit: int = Query(default=10, ge=1, le=50),
    history_offset: int = Query(default=0, ge=0),
    x_user_id: str | None = Header(None),
) -> dict:
    """Cross-session confirmation inbox for designated approvers.

    Authorization lives in the platform-gateway (`approvals:list` is
    granted to decider roles only); this endpoint serves the durable
    records with metadata only, never the owner's transcript text
    (SPEC-030 Q-1 posture). SPEC-036 R-3: the pending queue is always
    complete (hiding parked work must stay impossible) while the
    resolved history pages server-side — the combined payload's old
    100-row cap silently dropped older decisions as volume grew.
    """
    _user_id(x_user_id)

    def _shape(record: dict) -> dict:
        session = SESSION_STORE.get_session(record["session_id"])
        return ConfirmationRecordModel(
            **record,
            session_title=session.title if session is not None else None,
        ).model_dump()

    pending = [
        _shape(record)
        for record in CONFIRMATION_RECORD_STORE.load_pending_inbox()
    ]
    history_rows, history_total = CONFIRMATION_RECORD_STORE.load_inbox_history(
        history_limit, history_offset
    )
    return {
        "confirmations": pending,
        "history": [_shape(record) for record in history_rows],
        "history_total": history_total,
    }


# --- Model discovery (SPEC-024 R-2) ---


@router.get("/models", response_model=AgentModelCatalog)
async def list_models(x_user_id: str | None = Header(None)) -> AgentModelCatalog:
    """Credential-gated model catalog, discovery-safe by construction.

    Returns only id/label/provider/default — never credentials or base
    URLs (SPEC-024 R-2). Always 200; an empty list when no model is
    configured, mirroring the ``not_configured`` runtime posture.
    """
    _user_id(x_user_id)
    payload = MODEL_CATALOG.public_models()
    return AgentModelCatalog.model_validate(payload)


# --- Runtime metadata ---


@router.get("/runtime", response_model=AgentRuntimeMetadata)
async def runtime_metadata() -> AgentRuntimeMetadata:
    kernel = get_runtime_kernel()
    meta = kernel.runtime_metadata()
    return AgentRuntimeMetadata(
        runtime_mode=str(meta.get("runtime_mode", kernel.mode())),
        runtime_state=str(meta.get("runtime_state", kernel.runtime_state())),  # type: ignore[arg-type]
        provider=str(meta.get("provider", kernel.provider_name())),
        model_name=meta.get("model_name") if isinstance(meta.get("model_name"), str) else None,
        hint=meta.get("hint") if isinstance(meta.get("hint"), str) else None,
        last_error=meta.get("last_error") if isinstance(meta.get("last_error"), str) else None,
    )


# --- Health (v2-conformant) ---


def _tech_versions() -> dict[str, str | None]:
    """Best-effort tech-stack versions for the platform inventory (v0.23.4).

    Informational only — any lookup failure yields ``None`` for that
    entry rather than disturbing the readiness contract.
    """
    import platform as _platform

    def _pkg(name: str) -> str | None:
        try:
            from importlib.metadata import version as _v

            return _v(name)
        except Exception:
            return None

    return {
        "python_version": _platform.python_version(),
        "fastapi_version": _pkg("fastapi"),
        "agentscope_version": _pkg("agentscope"),
    }


@router.get("/health", response_model=AgentHealth)
async def health() -> AgentHealth:
    kernel = get_runtime_kernel()
    configured = kernel.is_configured()
    tech = _tech_versions()
    return AgentHealth(
        status="ready" if configured else "not_ready",
        runtime_mode=kernel.mode(),
        runtime_state=kernel.runtime_state(),  # type: ignore[arg-type]
        provider=kernel.provider_name(),
        configured=configured,
        session_store=SESSION_STORE.backend_name,
        session_store_ready=SESSION_STORE.is_ready(),
        agent_state=AGENT_STATE_STORE.backend_name,
        agent_state_ready=AGENT_STATE_STORE.is_ready(),
        python_version=tech["python_version"],
        fastapi_version=tech["fastapi_version"],
        agentscope_version=tech["agentscope_version"],
        session_store_version=SESSION_STORE.server_version(),
        agent_state_version=AGENT_STATE_STORE.server_version(),
    )
