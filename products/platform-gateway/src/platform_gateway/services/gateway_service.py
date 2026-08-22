from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

import httpx
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import StreamingResponse

from platform_gateway.core.config import PlatformGatewaySettings
from platform_gateway.core.metrics import (
    record_policy_decision,
    record_token_verification,
)
from platform_gateway.metadata import SERVICE_NAME, SERVICE_VERSION
from platform_gateway.schemas.api import IdentityContext
from platform_gateway.services import agent_client
from platform_gateway.services.audit_emitter import build_audit_event, emit_audit_event
from platform_gateway.services.policy_engine import (
    PolicyDecision,
    PolicyLoadError,
    evaluate,
    load_bundle,
)
from platform_gateway.services.token_verifier import TokenVerificationError, verify_token

LOGGER = logging.getLogger(__name__)


def _service_headers(request_id: str) -> dict[str, str]:
    return {"x-request-id": request_id}


def live_status(settings: PlatformGatewaySettings) -> dict[str, str]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
    }


async def ready_status(settings: PlatformGatewaySettings) -> dict[str, object]:
    """Readiness: the policy bundle must load and the agent service must respond."""
    try:
        rules = load_bundle(settings)
        agent_health = await agent_client.health(settings)
        return {
            "status": "ok",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "agent_service": agent_health,
            "policy_rules": len(rules),
        }
    except httpx.HTTPError as exc:
        return {
            "status": "degraded",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "agent_service_error": str(exc),
        }
    except PolicyLoadError as exc:
        return {
            "status": "degraded",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "policy_error": str(exc),
        }


async def runtime_status(settings: PlatformGatewaySettings) -> dict[str, object]:
    return await agent_client.runtime_metadata(settings)


async def fetch_login_url(settings: PlatformGatewaySettings, request_id: str) -> dict:
    headers = _service_headers(request_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{settings.identity_service_url}/api/v1/auth/login-url",
            headers=headers,
        )
    response.raise_for_status()
    return response.json()


async def start_login(settings: PlatformGatewaySettings, request_id: str) -> dict:
    headers = _service_headers(request_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{settings.identity_service_url}/api/v1/auth/login",
            headers=headers,
        )
    response.raise_for_status()
    return response.json()


async def complete_login(
    settings: PlatformGatewaySettings,
    request_id: str,
    payload: dict,
) -> dict:
    headers = _service_headers(request_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{settings.identity_service_url}/api/v1/auth/callback",
            json=payload,
            headers=headers,
        )
    response.raise_for_status()
    return response.json()


async def build_logout_url(
    settings: PlatformGatewaySettings,
    request_id: str,
    payload: dict,
) -> dict:
    headers = _service_headers(request_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{settings.identity_service_url}/api/v1/auth/logout-url",
            json=payload,
            headers=headers,
        )
    response.raise_for_status()
    return response.json()


async def refresh_token(
    settings: PlatformGatewaySettings,
    request_id: str,
    payload: dict,
) -> dict:
    headers = _service_headers(request_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{settings.identity_service_url}/api/v1/auth/refresh",
            json=payload,
            headers=headers,
        )
    response.raise_for_status()
    return response.json()


async def normalize_identity(
    settings: PlatformGatewaySettings,
    request: Request,
    request_id: str,
) -> dict:
    headers = _service_headers(request_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{settings.identity_service_url}/api/v1/identity/normalize",
            json=await request.json(),
            headers=headers,
        )
    response.raise_for_status()
    return response.json()


async def resolve_request_identity(
    settings: PlatformGatewaySettings,
    request: Request,
    request_id: str,
) -> IdentityContext | None:
    """Resolve identity via local JWT verification.

    - If a bearer token is present, verify it locally (no network call).
    - If auth is required and no valid token, raise 401.
    - If auth is optional and no token, return a synthetic dev identity.
    """
    authorization = request.headers.get("authorization")

    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            record_token_verification("invalid")
            raise HTTPException(status_code=401, detail="malformed authorization header")
        try:
            identity = verify_token(settings, token)
            record_token_verification("valid")
            LOGGER.info(
                "identity verified locally",
                extra={
                    "request_id": request_id,
                    "sub": identity.subject,
                    "username": identity.username,
                    "roles": identity.roles,
                    "authenticated": True,
                    "synthetic": False,
                },
            )
            return identity
        except TokenVerificationError as exc:
            record_token_verification(
                "expired" if exc.detail == "token expired" else "invalid"
            )
            raise HTTPException(status_code=401, detail=exc.detail) from exc

    # No token present.
    record_token_verification("missing")
    if settings.require_auth:
        raise HTTPException(status_code=401, detail="authentication required")

    # Synthetic dev identity (R-4).
    synthetic = IdentityContext(
        subject="dev",
        username=settings.dev_user,
        roles=["developer"],
        groups=[],
    )
    LOGGER.info(
        "using synthetic dev identity",
        extra={
            "request_id": request_id,
            "username": synthetic.username,
            "authenticated": False,
            "synthetic": True,
        },
    )
    return synthetic


def enforce_policy(
    settings: PlatformGatewaySettings,
    identity: IdentityContext,
    action: str,
    request_id: str,
) -> None:
    """Evaluate the action against the policy bundle; raise 403 on deny (R-3/R-4).

    Verified and synthetic identities take the identical path — the developer
    role is granted access by policy, never by bypass.
    """
    decision = evaluate(settings, identity.roles, action)
    record_policy_decision(action, decision.decision)
    log_extra = {
        "request_id": request_id,
        "subject": identity.subject,
        "roles": identity.roles,
        "action": action,
        "decision": decision.decision,
        "matched_rule_ids": decision.matched_rule_ids,
    }
    if decision.decision == "deny":
        LOGGER.warning("policy decision", extra=log_extra)
        _emit_policy_decision(settings, identity, action, request_id, decision)
        raise HTTPException(
            status_code=403,
            detail={
                "detail": "action denied by policy",
                "action": action,
                "reason": decision.reason,
            },
        )
    LOGGER.info("policy decision", extra=log_extra)
    _emit_policy_decision(settings, identity, action, request_id, decision)


def _emit_policy_decision(
    settings: PlatformGatewaySettings,
    identity: IdentityContext,
    action: str,
    request_id: str,
    decision: PolicyDecision,
) -> None:
    """Mirror every policy decision to the durable audit trail (SPEC-013 R-3)."""
    emit_audit_event(
        settings,
        build_audit_event(
            "policy_decision",
            request_id,
            decision.decision,
            subject=identity.subject,
            username=identity.username,
            actor=identity.actor,
            roles=identity.roles,
            details={
                "action": action,
                "decision": decision.decision,
                "reason": decision.reason,
                "matched_rule_ids": decision.matched_rule_ids,
            },
        ),
    )


async def create_session(
    settings: PlatformGatewaySettings,
    request_id: str,
    user_id: str,
) -> dict:
    return await agent_client.create_session(settings, request_id, user_id)


async def get_session(
    settings: PlatformGatewaySettings,
    request_id: str,
    session_id: str,
    user_id: str,
) -> dict:
    """Proxy a session detail fetch (SPEC-022 R-1).

    Upstream 4xx (unknown/foreign session) passes through unchanged so
    the anti-enumeration 404 reaches the caller; transport failures and
    upstream 5xx map to 502 — the same posture as the delete proxy.
    """
    try:
        return await agent_client.get_session(
            settings, request_id, session_id, user_id
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if 400 <= status < 500:
            raise HTTPException(
                status_code=status,
                detail="agent service rejected the session fetch",
            ) from exc
        raise HTTPException(
            status_code=502, detail="agent service session fetch failed"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="agent service unavailable"
        ) from exc


async def list_sessions(
    settings: PlatformGatewaySettings,
    request_id: str,
    user_id: str,
) -> dict:
    """Proxy the caller's workspace session list (SPEC-022 R-1)."""
    try:
        return await agent_client.list_sessions(settings, request_id, user_id)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail="agent service session list failed"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="agent service unavailable"
        ) from exc


async def delete_session(
    settings: PlatformGatewaySettings,
    request_id: str,
    session_id: str,
    user_id: str,
) -> dict:
    """Proxy an owner-only session delete (SPEC-022 R-1).

    Upstream 4xx (unknown/foreign session, parked confirmation) passes
    through unchanged; transport failures and upstream 5xx map to 502 —
    the same posture as the confirm proxy.
    """
    try:
        return await agent_client.delete_session(
            settings, request_id, session_id, user_id
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if 400 <= status < 500:
            raise HTTPException(
                status_code=status,
                detail="agent service rejected the session delete",
            ) from exc
        raise HTTPException(
            status_code=502, detail="agent service session delete failed"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="agent service unavailable"
        ) from exc


async def chat(
    settings: PlatformGatewaySettings,
    request_id: str,
    user_id: str,
    message: str,
    session_id: str | None,
    delegated_token: str | None = None,
    input_modality: str = "text",
) -> dict:
    return await agent_client.chat(
        settings,
        request_id,
        user_id,
        message,
        session_id,
        delegated_token,
        input_modality,
    )


def chat_stream(
    settings: PlatformGatewaySettings,
    request_id: str,
    user_id: str,
    message: str,
    session_id: str | None,
    delegated_token: str | None = None,
) -> StreamingResponse:
    async def _stream() -> AsyncIterator[str]:
        async for chunk in agent_client.stream_chat(
            settings, request_id, user_id, message, session_id, delegated_token
        ):
            yield chunk

    return StreamingResponse(_stream(), media_type="text/event-stream")


async def chat_confirm(
    settings: PlatformGatewaySettings,
    request_id: str,
    identity: IdentityContext,
    session_id: str,
    confirm_id: str,
    decision: str,
    delegated_token: str | None = None,
) -> StreamingResponse:
    """Proxy a parked-confirmation decision to agent-service (SPEC-020 R-3).

    Upstream 4xx (unknown/expired confirmation, parked session) passes
    through unchanged; transport failures and upstream 5xx map to 502.
    The ``confirmation_decided`` audit event is emitted when the matching
    ``confirmation_result`` frame flows through, so only decisions the
    kernel actually applied reach the durable trail.
    """
    try:
        upstream = await agent_client.open_chat_confirm_stream(
            settings,
            request_id,
            identity.username,
            session_id,
            confirm_id,
            decision,
            delegated_token,
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if 400 <= status < 500:
            # Pass client errors through unchanged (unknown/expired
            # confirmation, parked session) so operators can tell them
            # apart from an upstream outage.
            raise HTTPException(
                status_code=status,
                detail="agent service rejected the confirmation",
            ) from exc
        raise HTTPException(
            status_code=502, detail="agent service confirm failed"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="agent service unavailable"
        ) from exc

    audited = False

    async def _stream() -> AsyncIterator[str]:
        nonlocal audited
        async for chunk in upstream:
            if not audited:
                frame = _extract_confirmation_result(chunk)
                if frame is not None:
                    audited = True
                    _emit_confirmation_decided(
                        settings, request_id, identity,
                        session_id, confirm_id, decision, frame,
                    )
            yield chunk

    return StreamingResponse(_stream(), media_type="text/event-stream")


def _extract_confirmation_result(chunk: str) -> dict | None:
    """Parse an SSE chunk into a confirmation_result frame, or None."""
    if not chunk.startswith("data: "):
        return None
    try:
        frame = json.loads(chunk.removeprefix("data: ").strip())
    except ValueError:
        return None
    if isinstance(frame, dict) and frame.get("type") == "confirmation_result":
        return frame
    return None


def _emit_confirmation_decided(
    settings: PlatformGatewaySettings,
    request_id: str,
    identity: IdentityContext,
    session_id: str,
    confirm_id: str,
    decision: str,
    frame: dict,
) -> None:
    """Record the applied decision in the durable audit trail (SPEC-020 R-3)."""
    tool_names = [
        str(call.get("tool_name") or "")
        for call in frame.get("pending_calls") or []
        if isinstance(call, dict)
    ]
    emit_audit_event(
        settings,
        build_audit_event(
            "confirmation_decided",
            request_id,
            "allow" if decision == "approve" else "deny",
            subject=identity.subject,
            username=identity.username,
            actor=identity.actor,
            roles=identity.roles,
            session_id=session_id,
            details={
                "session_id": session_id,
                "confirm_id": confirm_id,
                "decision": decision,
                "tool_names": tool_names,
            },
        ),
    )
