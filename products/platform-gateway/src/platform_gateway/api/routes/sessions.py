import logging

from fastapi import APIRouter, Depends, Header, Request

from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.core.observability import log_event
from platform_gateway.core.request_context import resolve_request_id
from platform_gateway.schemas.api import (
    CreateSessionRequest,
    SessionTitleUpdateRequest,
    SkillTargetDeclareRequest,
)
from platform_gateway.services.audit_emitter import build_audit_event, emit_audit_event
from platform_gateway.services.gateway_service import (
    create_session,
    create_skill_draft,
    declare_skill_target,
    delete_session,
    enforce_policy,
    get_session,
    graduate_session_skill,
    list_sessions,
    resolve_request_identity,
    update_session_title,
)
from platform_gateway.services.policy_engine import (
    ACTION_SESSION_CREATE,
    ACTION_SESSION_DELETE,
    ACTION_SESSION_LIST,
    ACTION_SESSION_READ,
    ACTION_SESSION_SKILL_DRAFT,
    ACTION_SESSION_SKILL_GRADUATE,
    ACTION_SESSION_UPDATE,
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.post("/api/v1/sessions")
async def create_session_route(
    request: Request,
    body: CreateSessionRequest,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, ACTION_SESSION_CREATE, request_id)
    user_id = identity.username  # type: ignore[union-attr]
    response = await create_session(
        settings,
        request_id,
        user_id,
        body.skill_target,
    )
    log_event(
        LOGGER,
        "session_created",
        request_id=request_id,
        session_id=response.get("session_id"),
        user_id=user_id,
        # Whether this opened a develop-as-you-go session (SPEC-055 R-4). The
        # flag, never the target: a declared URL may carry a query string and
        # the gateway holds no normalization to strip it with.
        skill_target_declared=body.skill_target is not None,
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    emit_audit_event(
        settings,
        build_audit_event(
            "session_created",
            request_id,
            "success",
            subject=identity.subject,  # type: ignore[union-attr]
            username=user_id,
            actor=identity.actor,  # type: ignore[union-attr]
            roles=identity.roles,  # type: ignore[union-attr]
            session_id=response.get("session_id"),
        ),
    )
    return response


@router.get("/api/v1/sessions")
async def list_sessions_route(
    request: Request,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    """The caller's workspace session list (SPEC-022 R-1)."""
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, ACTION_SESSION_LIST, request_id)
    user_id = identity.username  # type: ignore[union-attr]
    response = await list_sessions(settings, request_id, user_id)
    log_event(
        LOGGER,
        "sessions_listed",
        request_id=request_id,
        session_count=len(response.get("sessions", [])),
        user_id=user_id,
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    return response


@router.get("/api/v1/sessions/{session_id}")
async def get_session_route(
    request: Request,
    session_id: str,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, ACTION_SESSION_READ, request_id)
    user_id = identity.username  # type: ignore[union-attr]
    response = await get_session(settings, request_id, session_id, user_id)
    log_event(
        LOGGER,
        "session_retrieved",
        request_id=request_id,
        session_id=session_id,
        user_id=user_id,
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    return response


@router.patch("/api/v1/sessions/{session_id}/title")
async def update_session_title_route(
    request: Request,
    session_id: str,
    body: SessionTitleUpdateRequest,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    """Owner session rename (SPEC-039 R-7).

    Ownership is enforced server-side by the agent layer (foreign/unknown
    sessions answer the anti-enumeration 404). Renames are deliberately
    unaudited — they are cosmetic metadata, not an operational act.
    """
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, ACTION_SESSION_UPDATE, request_id)
    user_id = identity.username  # type: ignore[union-attr]
    response = await update_session_title(
        settings, request_id, session_id, user_id, body.title
    )
    log_event(
        LOGGER,
        "session_title_updated",
        request_id=request_id,
        session_id=session_id,
        user_id=user_id,
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    return response


@router.post("/api/v1/sessions/{session_id}/skill-target")
async def declare_skill_target_route(
    request: Request,
    session_id: str,
    body: SkillTargetDeclareRequest,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    """Declare a session's skill-development target (SPEC-055 R-4).

    Authorization (``session:skill_graduate``) is enforced here;
    ownership is re-checked by the agent layer, so a foreign session
    answers the same structural 404 as an unknown one.

    Deliberately unaudited *here*: the declaration is not an operational
    act against an external system, it is a scope that only becomes
    consequential at graduation — and the ``skill_graduated`` event carries
    ``web_target`` and ``declaration``, the binding the graduated flow was
    given and where that declaration sat relative to the first captured
    step, which is what a reviewer needs to tell an authorization scope
    from a post-hoc claim (both pinned in the audit-event contract's
    ``details`` ledger, and both emitted by the agent layer's graduation
    route rather than by this proxy). The agent layer still logs the
    declaration (including a rejected attempt to widen a first-wins scope)
    on the structured log path.

    The target itself is never logged: a declared URL may carry a query
    string or embedded credentials, and the gateway holds no normalization
    to strip either with — the agent layer drops both before storing the
    target and logs the derived origin.
    """
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, ACTION_SESSION_SKILL_GRADUATE, request_id)
    user_id = identity.username  # type: ignore[union-attr]
    response = await declare_skill_target(
        settings, request_id, session_id, user_id, body.target
    )
    log_event(
        LOGGER,
        "skill_target_declared",
        request_id=request_id,
        session_id=session_id,
        user_id=user_id,
        already_declared=response.get("already_declared"),
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    return response


@router.post("/api/v1/sessions/{session_id}/skill-graduate")
async def graduate_session_skill_route(
    request: Request,
    session_id: str,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    """Graduate a session's authoring trace into an executable-flow draft.

    SPEC-055 R-4. Authorized by the same ``session:skill_graduate`` action as
    the declaration route above it — declaring a target is the first half of
    graduating, not a second capability (OQ-3's one action, on the
    ``documents:create`` precedent) — and this is the consequential half: it
    produces an executable *mutating* artifact, which is why the action exists
    separately from ``session:skill_draft`` at all.

    Ownership is re-checked by the agent layer, so a foreign session answers
    the same structural 404 as an unknown one. The draft is passed through
    verbatim and the gateway holds no graduation state; the agent layer emits
    the ``skill_graduated`` audit event, whose ``details`` name the target that
    was in force and whether it was declared before the first captured step.

    A 409 from upstream is the agent's deterministic blast-radius refusal and
    is passed through with its detail intact: it names every guard the trace
    failed and the steps responsible, which is the answer an operator needs
    rather than a bare "not graduable".
    """
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, ACTION_SESSION_SKILL_GRADUATE, request_id)
    user_id = identity.username  # type: ignore[union-attr]
    response = await graduate_session_skill(settings, request_id, session_id, user_id)
    log_event(
        LOGGER,
        "skill_graduated",
        request_id=request_id,
        session_id=session_id,
        user_id=user_id,
        mode=response.get("mode"),
        step_count=response.get("step_count"),
        declaration=response.get("declaration"),
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    return response


@router.post("/api/v1/sessions/{session_id}/skill-draft")
async def create_skill_draft_route(
    request: Request,
    session_id: str,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    """Skill-draft export from one of the caller's sessions (SPEC-044 R-1).

    Authorization (``session:skill_draft``) is enforced here; ownership
    is re-checked by the agent layer (foreign/unknown sessions answer
    the anti-enumeration 404). The validated draft is passed through
    verbatim — the gateway holds no draft state; the agent layer emits
    the ``skill_draft_generated`` audit event.
    """
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, ACTION_SESSION_SKILL_DRAFT, request_id)
    user_id = identity.username  # type: ignore[union-attr]
    response = await create_skill_draft(settings, request_id, session_id, user_id)
    log_event(
        LOGGER,
        "skill_draft_generated",
        request_id=request_id,
        session_id=session_id,
        user_id=user_id,
        mode=response.get("mode"),
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    return response


@router.delete("/api/v1/sessions/{session_id}")
async def delete_session_route(
    request: Request,
    session_id: str,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    """Owner-only session delete; parked sessions 409 (SPEC-022 R-1)."""
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, ACTION_SESSION_DELETE, request_id)
    user_id = identity.username  # type: ignore[union-attr]
    response = await delete_session(settings, request_id, session_id, user_id)
    log_event(
        LOGGER,
        "session_deleted",
        request_id=request_id,
        session_id=session_id,
        user_id=user_id,
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    emit_audit_event(
        settings,
        build_audit_event(
            "session_deleted",
            request_id,
            "success",
            subject=identity.subject,  # type: ignore[union-attr]
            username=user_id,
            actor=identity.actor,  # type: ignore[union-attr]
            roles=identity.roles,  # type: ignore[union-attr]
            session_id=session_id,
        ),
    )
    return response
