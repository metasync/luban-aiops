import logging

from fastapi import APIRouter, Depends, Header, Request

from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.core.observability import log_event
from platform_gateway.core.request_context import resolve_request_id
from platform_gateway.schemas.api import CreateSessionRequest, SessionTitleUpdateRequest
from platform_gateway.services.audit_emitter import build_audit_event, emit_audit_event
from platform_gateway.services.gateway_service import (
    create_session,
    create_skill_draft,
    delete_session,
    enforce_policy,
    get_session,
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
    )
    log_event(
        LOGGER,
        "session_created",
        request_id=request_id,
        session_id=response.get("session_id"),
        user_id=user_id,
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
