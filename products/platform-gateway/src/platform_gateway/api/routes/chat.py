import logging

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.core.observability import log_event
from platform_gateway.core.request_context import resolve_request_id
from platform_gateway.schemas.api import ChatConfirmRequest, ChatRequest
from platform_gateway.services.audit_emitter import build_audit_event, emit_audit_event
from platform_gateway.services.delegation_client import obtain_delegated_token
from platform_gateway.services.gateway_service import (
    chat,
    chat_confirm,
    chat_stream,
    enforce_policy,
    resolve_request_identity,
)
from platform_gateway.services.policy_engine import ACTION_CHAT_CONFIRM

router = APIRouter()
LOGGER = logging.getLogger(__name__)


def _bearer_token(request: Request) -> str | None:
    """Return the raw bearer token from the request, if present."""
    authorization = request.headers.get("authorization")
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


@router.post("/api/v1/chat")
async def chat_route(
    request: Request,
    body: ChatRequest,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, "chat", request_id)
    user_id = identity.username  # type: ignore[union-attr]
    delegated_token = await obtain_delegated_token(
        settings,
        identity.subject,  # type: ignore[union-attr]
        _bearer_token(request),
    )
    response = await chat(
        settings,
        request_id,
        user_id,
        body.message,
        body.session_id,
        delegated_token,
    )
    log_event(
        LOGGER,
        "chat_completed",
        request_id=request_id,
        session_id=response.get("session_id"),
        user_id=user_id,
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    emit_audit_event(
        settings,
        build_audit_event(
            "chat_completed",
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


@router.get("/api/v1/chat/stream")
async def chat_stream_route(
    request: Request,
    message: str,
    session_id: str | None = None,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> StreamingResponse:
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, "chat", request_id)
    user_id = identity.username  # type: ignore[union-attr]
    delegated_token = await obtain_delegated_token(
        settings,
        identity.subject,  # type: ignore[union-attr]
        _bearer_token(request),
    )
    log_event(
        LOGGER,
        "chat_stream_started",
        request_id=request_id,
        session_id=session_id,
        user_id=user_id,
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    emit_audit_event(
        settings,
        build_audit_event(
            "chat_started",
            request_id,
            "success",
            subject=identity.subject,  # type: ignore[union-attr]
            username=user_id,
            actor=identity.actor,  # type: ignore[union-attr]
            roles=identity.roles,  # type: ignore[union-attr]
            session_id=session_id,
        ),
    )
    return chat_stream(
        settings=settings,
        request_id=request_id,
        user_id=user_id,
        message=message,
        session_id=session_id,
        delegated_token=delegated_token,
    )


@router.post("/api/v1/chat/confirm")
async def chat_confirm_route(
    request: Request,
    body: ChatConfirmRequest,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> StreamingResponse:
    """Answer a parked kernel confirmation (SPEC-020 R-3).

    The response is the resumed SSE stream; the durable
    ``confirmation_decided`` audit event is emitted by the proxy once the
    kernel confirms the decision was applied.
    """
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, ACTION_CHAT_CONFIRM, request_id)
    delegated_token = await obtain_delegated_token(
        settings,
        identity.subject,  # type: ignore[union-attr]
        _bearer_token(request),
    )
    log_event(
        LOGGER,
        "chat_confirm_started",
        request_id=request_id,
        session_id=body.session_id,
        confirm_id=body.confirm_id,
        decision=body.decision,
        user_id=identity.username,  # type: ignore[union-attr]
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    return await chat_confirm(
        settings=settings,
        request_id=request_id,
        identity=identity,  # type: ignore[arg-type]
        session_id=body.session_id,
        confirm_id=body.confirm_id,
        decision=body.decision,
        delegated_token=delegated_token,
    )
