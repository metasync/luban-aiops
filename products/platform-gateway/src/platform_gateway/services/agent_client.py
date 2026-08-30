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


async def list_models(
    settings: PlatformGatewaySettings,
    request_id: str,
    user_id: str,
) -> dict:
    """Credential-gated model catalog discovery (SPEC-024 R-2)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{settings.agent_service_url}/api/v2/models",
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
    model: str | None = None,
) -> dict:
    timeout = httpx.Timeout(settings.chat_response_timeout_seconds, connect=5.0)
    payload: dict[str, str] = {"message": message}
    if session_id:
        payload["session_id"] = session_id
    # SPEC-022 R-2: modality rides the payload as metadata only.
    payload["input_modality"] = input_modality
    # SPEC-024 R-3: per-turn model selection relays verbatim; the runtime
    # validates it against the credential-gated catalog (fail-closed 422).
    if model:
        payload["model"] = model
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
    model: str | None = None,
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
    # SPEC-024 R-3: model selection rides the query, mirroring the POST
    # payload convention; upstream fail-closed 422 passes through.
    if model:
        params["model"] = model
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


async def fetch_pending_confirmation(
    settings: PlatformGatewaySettings,
    request_id: str,
    user_id: str,
    session_id: str,
) -> dict | None:
    """Parked-confirmation metadata for the approval bridge (SPEC-030 R-3).

    Returns the parked batch's policy action and owner username, or
    ``None`` when the session has no pending confirmation (upstream 404).
    Transport failures and upstream 5xx raise so the confirm bridge can
    fail closed instead of bypassing tier enforcement.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{settings.agent_service_url}/api/v2/chat/pending-confirmation",
            params={"session_id": session_id},
            headers=_headers(request_id, user_id),
        )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


async def fetch_approvals_inbox(
    settings: PlatformGatewaySettings,
    request_id: str,
    user_id: str,
    history_limit: int = 10,
    history_offset: int = 0,
) -> dict:
    """Cross-session confirmation inbox (SPEC-031 R-3).

    Authorization is enforced by the gateway route (`approvals:list`);
    agent-service serves the durable records. Transport failures and
    upstream 5xx raise so the route answers 502 rather than an empty
    inbox that would hide parked work. SPEC-036 R-4: history pagination
    params forward as query params; the pending queue is never paginated.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{settings.agent_service_url}/api/v2/confirmations",
            headers=_headers(request_id, user_id),
            params={
                "history_limit": history_limit,
                "history_offset": history_offset,
            },
        )
    response.raise_for_status()
    return response.json()


async def create_document(
    settings: PlatformGatewaySettings,
    request_id: str,
    user_id: str,
    payload: dict,
    foreign_coverage: str,
) -> dict:
    """Create an operations document (SPEC-039 R-1).

    ``foreign_coverage`` carries the gateway-computed ``approvals:list``
    capability as the trusted internal ``X-Foreign-Coverage`` header; the
    agent layer fails closed on any value other than ``allowed``. The
    timeout is generous because an opt-in prose pass makes one model call.
    """
    timeout = httpx.Timeout(60.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{settings.agent_service_url}/api/v2/documents",
            headers={
                **_headers(request_id, user_id),
                "X-Foreign-Coverage": foreign_coverage,
            },
            json=payload,
        )
    response.raise_for_status()
    return response.json()


async def list_documents(
    settings: PlatformGatewaySettings,
    request_id: str,
    user_id: str,
    scope: str,
) -> dict:
    """List documents (SPEC-039 R-2): ``mine`` includes drafts, ``published`` does not."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{settings.agent_service_url}/api/v2/documents",
            headers=_headers(request_id, user_id),
            params={"scope": scope},
        )
    response.raise_for_status()
    return response.json()


async def fetch_document(
    settings: PlatformGatewaySettings,
    request_id: str,
    document_id: str,
    user_id: str,
) -> dict:
    """Fetch one document; upstream 404 (unknown/foreign draft) passes through."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{settings.agent_service_url}/api/v2/documents/{document_id}",
            headers=_headers(request_id, user_id),
        )
    response.raise_for_status()
    return response.json()


async def publish_document(
    settings: PlatformGatewaySettings,
    request_id: str,
    document_id: str,
    user_id: str,
) -> dict:
    """One-way owner publish; upstream 404/409 pass through (SPEC-039 R-1)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{settings.agent_service_url}/api/v2/documents/{document_id}/publish",
            headers=_headers(request_id, user_id),
        )
    response.raise_for_status()
    return response.json()


async def delete_document(
    settings: PlatformGatewaySettings,
    request_id: str,
    document_id: str,
    user_id: str,
) -> dict:
    """Owner-only document delete; upstream 404 passes through (SPEC-039 R-1)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.delete(
            f"{settings.agent_service_url}/api/v2/documents/{document_id}",
            headers=_headers(request_id, user_id),
        )
    response.raise_for_status()
    return response.json()


async def update_session_title(
    settings: PlatformGatewaySettings,
    request_id: str,
    session_id: str,
    user_id: str,
    title: str,
) -> dict:
    """Owner session rename (SPEC-039 R-7); upstream 400/404 pass through."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.patch(
            f"{settings.agent_service_url}/api/v2/sessions/{session_id}/title",
            headers=_headers(request_id, user_id),
            json={"title": title},
        )
    response.raise_for_status()
    return response.json()


async def create_skill_draft(
    settings: PlatformGatewaySettings,
    request_id: str,
    session_id: str,
    user_id: str,
) -> dict:
    """Generate a validated skill draft from one session (SPEC-044 R-1).

    The timeout is generous because the agent layer makes one bounded
    model call plus a skills-hub validation round-trip (and a bounded
    regeneration on rejection). Upstream 404 answers foreign/unknown
    sessions; 502/503 mean the draft failed validation legs and is
    never returned.
    """
    timeout = httpx.Timeout(60.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{settings.agent_service_url}/api/v2/sessions/{session_id}/skill-draft",
            headers=_headers(request_id, user_id),
        )
    response.raise_for_status()
    return response.json()


async def create_incident_skill_draft(
    settings: PlatformGatewaySettings,
    request_id: str,
    incident_id: str,
    user_id: str,
) -> dict:
    """Generate a validated skill draft from one incident (SPEC-045 R-1).

    Same generous timeout as the session sibling: one bounded model call
    plus a skills-hub validation round-trip (and a bounded regeneration
    on rejection). Upstream 404 answers unknown incident ids, 409 means
    the incident has no validated triage report; 502/503 mean the draft
    failed validation legs and is never returned.
    """
    timeout = httpx.Timeout(60.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{settings.agent_service_url}/api/v2/incidents/{incident_id}/skill-draft",
            headers=_headers(request_id, user_id),
        )
    response.raise_for_status()
    return response.json()


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
