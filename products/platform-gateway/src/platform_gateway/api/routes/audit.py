"""Audit trail query proxy (SPEC-013 R-4).

Proxies GET /api/v1/audit/events to the durable audit service after
enforcing the ``audit:read`` action. The auditor's bearer identity is
resolved and authorized at the gateway; the audit service only ever sees
the gateway's own ingest credential.
"""

import logging

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.core.observability import log_event
from platform_gateway.core.request_context import resolve_request_id
from platform_gateway.services.gateway_service import (
    enforce_policy,
    resolve_request_identity,
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)

QUERY_PATH = "/api/v1/audit/events"
PROXY_TIMEOUT_SECONDS = 10.0


@router.get("/api/v1/audit/events")
async def query_audit_events(
    request: Request,
    username: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    request_id_filter: str | None = Query(default=None, alias="request_id"),
    event_type: str | None = Query(default=None),
    service: str | None = Query(default=None),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, "audit:read", request_id)
    if not settings.audit_service_url:
        raise HTTPException(status_code=503, detail="audit service not configured")
    params: dict[str, str | int] = {"limit": limit}
    for key, value in (
        ("username", username),
        ("session_id", session_id),
        ("request_id", request_id_filter),
        ("event_type", event_type),
        ("service", service),
        ("since", since),
        ("until", until),
        ("cursor", cursor),
    ):
        if value is not None:
            params[key] = value
    url = f"{settings.audit_service_url.rstrip('/')}{QUERY_PATH}"
    try:
        async with httpx.AsyncClient(timeout=PROXY_TIMEOUT_SECONDS) as client:
            response = await client.get(
                url,
                params=params,
                auth=(settings.audit_client_id, settings.audit_client_secret),
                headers={"x-request-id": request_id},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="audit service unavailable"
        ) from exc
    if response.status_code >= 300:
        # Pass client errors through unchanged (bad cursor/filter, ingest
        # credential mismatch) so operators can tell them apart from an
        # upstream outage, which alone warrants the 502 mapping.
        if 400 <= response.status_code < 500:
            raise HTTPException(
                status_code=response.status_code,
                detail="audit service rejected the query",
            )
        raise HTTPException(status_code=502, detail="audit service query failed")
    log_event(
        LOGGER,
        "audit_query_proxied",
        request_id=request_id,
        user_id=identity.username,  # type: ignore[union-attr]
    )
    return response.json()
