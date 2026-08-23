"""Single HTTP client for the platform-owned agent-service contract (v2).

Replaces the dual-backend abstraction (transitional + native) with a direct
binding to the /api/v2/ surface defined in shared/shared-contracts.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from platform_gateway.core.config import PlatformGatewaySettings


def _headers(
    request_id: str,
    user_id: str,
    bearer_token: str | None = None,
) -> dict[str, str]:
    headers = {
        "x-request-id": request_id,
        "X-User-ID": user_id,
    }
    if bearer_token:
        # Forward the delegated token (SPEC-008 R-4) so agent-platform can
        # present a least-privilege credential on its loopback tool calls.
        headers["Authorization"] = f"Bearer {bearer_token}"
    return headers


async def create_session(
    settings: PlatformGatewaySettings,
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
    settings: PlatformGatewaySettings,
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


async def list_sessions(
    settings: PlatformGatewaySettings,
    request_id: str,
    user_id: str,
) -> dict:
    """The caller's workspace session list (SPEC-022 R-1)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{settings.agent_service_url}/api/v2/sessions",
            headers=_headers(request_id, user_id),
        )
    response.raise_for_status()
    return response.json()


async def delete_session(
    settings: PlatformGatewaySettings,
    request_id: str,
    session_id: str,
    user_id: str,
) -> dict:
    """Owner-only session delete; upstream 404/409 pass through (SPEC-022 R-1)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.delete(
            f"{settings.agent_service_url}/api/v2/sessions/{session_id}",
            headers=_headers(request_id, user_id),
        )
    response.raise_for_status()
    return response.json()


async def chat(
    settings: PlatformGatewaySettings,
    request_id: str,
    user_id: str,
    message: str,
    session_id: str | None,
    delegated_token: str | None = None,
    input_modality: str = "text",
) -> dict:
    timeout = httpx.Timeout(settings.chat_response_timeout_seconds, connect=5.0)
    payload: dict[str, str] = {"message": message}
    if session_id:
        payload["session_id"] = session_id
    # SPEC-022 R-2: modality rides the payload as metadata only.
    payload["input_modality"] = input_modality
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{settings.agent_service_url}/api/v2/chat",
            json=payload,
            headers=_headers(request_id, user_id, delegated_token),
        )
    response.raise_for_status()
    return response.json()


async def open_chat_stream(
    settings: PlatformGatewaySettings,
    request_id: str,
    user_id: str,
    message: str,
    session_id: str | None,
    delegated_token: str | None = None,
    input_modality: str = "text",
) -> AsyncIterator[str]:
    """Open the chat stream and return an SSE line iterator.

    The upstream status is checked eagerly, before any frame is yielded, so
    the caller can map 4xx (unknown session, parked conflict) and outages
    to HTTP responses instead of answering 200 with an empty SSE stream.
    Raises ``httpx.HTTPStatusError`` on upstream 4xx/5xx and
    ``httpx.HTTPError`` on transport failure.
    """
    timeout = httpx.Timeout(connect=5.0, read=None, write=None, pool=None)
    params: dict[str, str] = {"message": message}
    if session_id:
        params["session_id"] = session_id
    # SPEC-023 R-4: modality rides the query as metadata only, matching
    # the POST /api/v2/chat payload convention (SPEC-022 R-2).
    params["input_modality"] = input_modality
    client = httpx.AsyncClient(timeout=timeout)
    try:
        request = client.build_request(
            "GET",
            f"{settings.agent_service_url}/api/v2/chat/stream",
            params=params,
            headers=_headers(request_id, user_id, delegated_token),
        )
        response = await client.send(request, stream=True)
    except httpx.HTTPError:
        await client.aclose()
        raise
    if response.status_code >= 400:
        # Read the body to release the connection, then surface the status.
        # Cleanup is finally-guarded so a failed error-body read cannot leak
        # the response or client.
        try:
            await response.aread()
        finally:
            await response.aclose()
            await client.aclose()
        response.raise_for_status()

    async def _iter() -> AsyncIterator[str]:
        try:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    yield line + "\n\n"
        finally:
            await response.aclose()
            await client.aclose()

    return _iter()


async def open_chat_confirm_stream(
    settings: PlatformGatewaySettings,
    request_id: str,
    user_id: str,
    session_id: str,
    confirm_id: str,
    decision: str,
    delegated_token: str | None = None,
) -> AsyncIterator[str]:
    """Open the confirm stream and return an SSE line iterator (SPEC-020 R-3).

    The upstream status is checked eagerly, before any frame is yielded, so
    the caller can map 4xx (unknown/expired/parked) and outages to HTTP
    responses instead of corrupting an already-open SSE stream. Raises
    ``httpx.HTTPStatusError`` on upstream 4xx/5xx and ``httpx.HTTPError``
    on transport failure.
    """
    timeout = httpx.Timeout(connect=5.0, read=None, write=None, pool=None)
    payload = {
        "session_id": session_id,
        "confirm_id": confirm_id,
        "decision": decision,
    }
    client = httpx.AsyncClient(timeout=timeout)
    try:
        request = client.build_request(
            "POST",
            f"{settings.agent_service_url}/api/v2/chat/confirm",
            json=payload,
            headers=_headers(request_id, user_id, delegated_token),
        )
        response = await client.send(request, stream=True)
    except httpx.HTTPError:
        await client.aclose()
        raise
    if response.status_code >= 400:
        # Read the body to release the connection, then surface the status.
        # Cleanup is finally-guarded so a failed error-body read cannot leak
        # the response or client.
        try:
            await response.aread()
        finally:
            await response.aclose()
            await client.aclose()
        response.raise_for_status()

    async def _iter() -> AsyncIterator[str]:
        try:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    yield line + "\n\n"
        finally:
            await response.aclose()
            await client.aclose()

    return _iter()


async def runtime_metadata(settings: PlatformGatewaySettings) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{settings.agent_service_url}/api/v2/runtime",
        )
    response.raise_for_status()
    return response.json()


async def health(settings: PlatformGatewaySettings) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(
            f"{settings.agent_service_url}/api/v2/health",
        )
    response.raise_for_status()
    return response.json()
