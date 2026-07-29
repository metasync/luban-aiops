from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import httpx
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import StreamingResponse

from api_gateway.core.config import GatewaySettings
from api_gateway.core.metrics import record_policy_decision, record_token_verification
from api_gateway.metadata import SERVICE_NAME, SERVICE_VERSION
from api_gateway.schemas.api import IdentityContext
from api_gateway.services import agent_client
from api_gateway.services.policy_engine import PolicyLoadError, evaluate
from api_gateway.services.token_verifier import TokenVerificationError, verify_token

LOGGER = logging.getLogger(__name__)


def _service_headers(request_id: str) -> dict[str, str]:
    return {"x-request-id": request_id}


def live_status(settings: GatewaySettings) -> dict[str, str]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
    }


async def ready_status(settings: GatewaySettings) -> dict[str, object]:
    try:
        agent_health = await agent_client.health(settings)
        return {
            "status": "ok",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "agent_service": agent_health,
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


async def runtime_status(settings: GatewaySettings) -> dict[str, object]:
    return await agent_client.runtime_metadata(settings)


async def fetch_login_url(settings: GatewaySettings, request_id: str) -> dict:
    headers = _service_headers(request_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{settings.identity_service_url}/api/v1/auth/login-url",
            headers=headers,
        )
    response.raise_for_status()
    return response.json()


async def start_login(settings: GatewaySettings, request_id: str) -> dict:
    headers = _service_headers(request_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{settings.identity_service_url}/api/v1/auth/login",
            headers=headers,
        )
    response.raise_for_status()
    return response.json()


async def complete_login(
    settings: GatewaySettings,
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
    settings: GatewaySettings,
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


async def normalize_identity(
    settings: GatewaySettings,
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
    settings: GatewaySettings,
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
    settings: GatewaySettings,
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
        raise HTTPException(
            status_code=403,
            detail={
                "detail": "action denied by policy",
                "action": action,
                "reason": decision.reason,
            },
        )
    LOGGER.info("policy decision", extra=log_extra)


async def create_session(
    settings: GatewaySettings,
    request_id: str,
    user_id: str,
) -> dict:
    return await agent_client.create_session(settings, request_id, user_id)


async def get_session(
    settings: GatewaySettings,
    request_id: str,
    session_id: str,
    user_id: str,
) -> dict:
    return await agent_client.get_session(settings, request_id, session_id, user_id)


async def chat(
    settings: GatewaySettings,
    request_id: str,
    user_id: str,
    message: str,
    session_id: str | None,
) -> dict:
    return await agent_client.chat(settings, request_id, user_id, message, session_id)


def chat_stream(
    settings: GatewaySettings,
    request_id: str,
    user_id: str,
    message: str,
    session_id: str | None,
) -> StreamingResponse:
    async def _stream() -> AsyncIterator[str]:
        async for chunk in agent_client.stream_chat(
            settings, request_id, user_id, message, session_id
        ):
            yield chunk

    return StreamingResponse(_stream(), media_type="text/event-stream")
