from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from fastapi import Request
from fastapi.responses import StreamingResponse

from api_gateway.core.config import GatewaySettings
from api_gateway.metadata import SERVICE_NAME, SERVICE_VERSION
from api_gateway.services.agent_backends import build_service_headers, resolve_agent_backend


def live_status(settings: GatewaySettings) -> dict[str, str]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "agent_backend_mode": settings.agent_backend_mode,
    }


async def ready_status(settings: GatewaySettings) -> dict[str, object]:
    configured_mode = settings.configured_agent_backend_mode()
    async with httpx.AsyncClient(timeout=5.0) as client:
        resolution = await resolve_agent_backend(
            client,
            settings.backend_context(),
            configured_mode,
        )
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "configured_agent_backend_mode": configured_mode,
        "resolved_agent_backend_mode": resolution.resolved_mode,
        "resolution_reason": resolution.reason,
    }


async def runtime_status(settings: GatewaySettings) -> dict[str, object]:
    configured_mode = settings.configured_agent_backend_mode()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resolution = await resolve_agent_backend(
            client,
            settings.backend_context(),
            configured_mode,
        )
        payload = await resolution.backend.runtime_metadata(client)
    payload["configured_agent_backend_mode"] = configured_mode
    payload["resolved_agent_backend_mode"] = resolution.resolved_mode
    payload["resolution_reason"] = resolution.reason
    return payload


async def fetch_login_url(settings: GatewaySettings, request_id: str) -> dict:
    headers = build_service_headers(request_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{settings.identity_service_url}/api/v1/auth/login-url",
            headers=headers,
        )
    response.raise_for_status()
    return response.json()


async def normalize_identity(
    settings: GatewaySettings,
    request: Request,
    request_id: str,
) -> dict:
    headers = build_service_headers(request_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{settings.identity_service_url}/api/v1/identity/normalize",
            json=await request.json(),
            headers=headers,
        )
    response.raise_for_status()
    return response.json()


async def create_session(
    settings: GatewaySettings,
    request_id: str,
    user_id: str,
    payload: dict,
) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resolution = await resolve_agent_backend(
            client,
            settings.backend_context(),
            settings.configured_agent_backend_mode(),
        )
        return await resolution.backend.create_session(
            client=client,
            request_id=request_id,
            user_id=user_id,
            payload=payload,
        )


async def get_session(
    settings: GatewaySettings,
    request_id: str,
    session_id: str,
    user_id: str,
) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resolution = await resolve_agent_backend(
            client,
            settings.backend_context(),
            settings.configured_agent_backend_mode(),
        )
        return await resolution.backend.get_session(
            client=client,
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
        )


async def chat(
    settings: GatewaySettings,
    request_id: str,
    user_id: str,
    payload: dict,
) -> dict:
    async with httpx.AsyncClient(timeout=None) as client:
        resolution = await resolve_agent_backend(
            client,
            settings.backend_context(),
            settings.configured_agent_backend_mode(),
        )
        return await resolution.backend.chat(
            client=client,
            request_id=request_id,
            user_id=user_id,
            payload=payload,
        )


def chat_stream(
    settings: GatewaySettings,
    request_id: str,
    user_id: str,
    message: str,
    session_id: str | None,
) -> StreamingResponse:
    async def stream_selected_backend() -> AsyncIterator[bytes | str]:
        async with httpx.AsyncClient(timeout=None) as client:
            resolution = await resolve_agent_backend(
                client,
                settings.backend_context(),
                settings.configured_agent_backend_mode(),
            )
            async for chunk in resolution.backend.stream_chat(
                client=client,
                request_id=request_id,
                user_id=user_id,
                message=message,
                session_id=session_id,
            ):
                yield chunk

    return StreamingResponse(
        stream_selected_backend(),
        media_type="text/event-stream",
    )
