"""Single HTTP client for the platform-owned agent-service contract (v2).

Replaces the dual-backend abstraction (transitional + native) with a direct
binding to the /api/v2/ surface defined in shared/shared-contracts.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from api_gateway.core.config import GatewaySettings


def _headers(request_id: str, user_id: str) -> dict[str, str]:
    return {
        "x-request-id": request_id,
        "X-User-ID": user_id,
    }


async def create_session(
    settings: GatewaySettings,
    request_id: str,
    user_id: str,
) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{settings.agent_service_url}/api/v2/sessions",
            headers=_headers(request_id, user_id),
        )
    response.raise_for_status()
    return response.json()


async def get_session(
    settings: GatewaySettings,
    request_id: str,
    session_id: str,
    user_id: str,
) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{settings.agent_service_url}/api/v2/sessions/{session_id}",
            headers=_headers(request_id, user_id),
        )
    response.raise_for_status()
    return response.json()


async def chat(
    settings: GatewaySettings,
    request_id: str,
    user_id: str,
    message: str,
    session_id: str | None,
) -> dict:
    timeout = httpx.Timeout(settings.chat_response_timeout_seconds, connect=5.0)
    payload: dict[str, str] = {"message": message}
    if session_id:
        payload["session_id"] = session_id
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{settings.agent_service_url}/api/v2/chat",
            json=payload,
            headers=_headers(request_id, user_id),
        )
    response.raise_for_status()
    return response.json()


async def stream_chat(
    settings: GatewaySettings,
    request_id: str,
    user_id: str,
    message: str,
    session_id: str | None,
) -> AsyncIterator[str]:
    timeout = httpx.Timeout(connect=5.0, read=None, write=None, pool=None)
    params: dict[str, str] = {"message": message}
    if session_id:
        params["session_id"] = session_id
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "GET",
            f"{settings.agent_service_url}/api/v2/chat/stream",
            params=params,
            headers=_headers(request_id, user_id),
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    yield line + "\n\n"


async def runtime_metadata(settings: GatewaySettings) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{settings.agent_service_url}/api/v2/runtime",
        )
    response.raise_for_status()
    return response.json()


async def health(settings: GatewaySettings) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(
            f"{settings.agent_service_url}/api/v2/health",
        )
    response.raise_for_status()
    return response.json()
