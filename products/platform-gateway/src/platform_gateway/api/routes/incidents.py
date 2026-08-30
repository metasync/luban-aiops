"""Incidents proxy routes (SPEC-015 R-7).

The portal reaches incident-service exclusively through these routes. The
gateway resolves and authorizes the caller (``incident:read`` /
``incident:create`` / ``incident:triage``), then speaks to incident-service
with its own Basic query credential. Triage additionally forwards the
operator's name (``X-User-ID``) and delegated bearer (``X-Delegated-Token``)
so the agent turn runs under the operator's identity and tool authority —
the same broker-mediated delegation chain chat uses (SPEC-008), unchanged.
"""

import logging
import re

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.core.observability import log_event
from platform_gateway.core.request_context import resolve_request_id
from platform_gateway.schemas.api import ReportIncidentRequest
from platform_gateway.services.delegation_client import obtain_delegated_token
from platform_gateway.services.gateway_service import (
    create_incident_skill_draft,
    enforce_policy,
    resolve_request_identity,
)
from platform_gateway.services.incident_client import (
    create_incident,
    get_incident,
    get_report,
    list_incidents,
    run_triage,
)
from platform_gateway.services.policy_engine import (
    ACTION_INCIDENT_READ,
    ACTION_INCIDENT_SKILL_DRAFT,
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)

# Contract pattern from shared/shared-contracts/schemas/incident.schema.json;
# the id is interpolated into the upstream URL path, so anything else is
# rejected before use.
_INCIDENT_ID_PATTERN = re.compile(r"^inc-[a-z0-9-]+$")


def _check_incident_id(incident_id: str) -> None:
    if not _INCIDENT_ID_PATTERN.match(incident_id):
        raise HTTPException(
            status_code=400,
            detail="incident_id is not a valid incident id "
            "(expected inc-<lowercase alphanumeric>)",
        )


def _bearer_token(request: Request) -> str | None:
    """Return the raw bearer token from the request, if present."""
    authorization = request.headers.get("authorization")
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


@router.get("/api/v1/incidents")
async def list_incidents_route(
    request: Request,
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    source: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, "incident:read", request_id)
    params: dict[str, str | int] = {"limit": limit, "offset": offset}
    for key, value in (("status", status), ("severity", severity), ("source", source)):
        if value is not None:
            params[key] = value
    response = await list_incidents(settings, request_id, params)
    log_event(
        LOGGER,
        "incidents_listed",
        request_id=request_id,
        user_id=identity.username,  # type: ignore[union-attr]
        total=response.get("total"),
    )
    return response


@router.post("/api/v1/incidents", status_code=201)
async def report_incident_route(
    request: Request,
    body: ReportIncidentRequest,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, "incident:create", request_id)
    user_id = identity.username  # type: ignore[union-attr]
    response = await create_incident(
        settings,
        request_id,
        body.model_dump(),
        reported_by=user_id,
    )
    log_event(
        LOGGER,
        "incident_reported",
        request_id=request_id,
        user_id=user_id,
        incident_id=response.get("incident_id"),
    )
    return response


@router.get("/api/v1/incidents/{incident_id}")
async def get_incident_route(
    request: Request,
    incident_id: str,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, "incident:read", request_id)
    _check_incident_id(incident_id)
    return await get_incident(settings, request_id, incident_id)


@router.get("/api/v1/incidents/{incident_id}/report")
async def get_incident_report_route(
    request: Request,
    incident_id: str,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, "incident:read", request_id)
    _check_incident_id(incident_id)
    return await get_report(settings, request_id, incident_id)


@router.post("/api/v1/incidents/{incident_id}/skill-draft")
async def create_incident_skill_draft_route(
    request: Request,
    incident_id: str,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    """Incident-anchored skill draft (SPEC-045 R-2).

    Dual-gated per the SPEC-043 pattern: ``incident:skill_draft`` first,
    then ``incident:read`` — denial reports the first failing action and
    blocked attempts ride the gateway's blocked-attempt audit. The
    validated draft is passed through verbatim — the gateway holds no
    draft state; the agent layer emits the
    ``incident_skill_draft_generated`` audit event.
    """
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, ACTION_INCIDENT_SKILL_DRAFT, request_id)
    enforce_policy(settings, identity, ACTION_INCIDENT_READ, request_id)
    _check_incident_id(incident_id)
    user_id = identity.username  # type: ignore[union-attr]
    response = await create_incident_skill_draft(
        settings, request_id, incident_id, user_id
    )
    log_event(
        LOGGER,
        "incident_skill_draft_generated",
        request_id=request_id,
        incident_id=incident_id,
        user_id=user_id,
        mode=response.get("mode"),
        authenticated=identity.subject != "dev",  # type: ignore[union-attr]
        roles=identity.roles,  # type: ignore[union-attr]
    )
    return response


@router.post("/api/v1/incidents/{incident_id}/triage")
async def triage_incident_route(
    request: Request,
    incident_id: str,
    x_request_id: str | None = Header(default=None),
    settings: PlatformGatewaySettings = Depends(get_settings),
) -> dict:
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(settings, request, request_id)
    enforce_policy(settings, identity, "incident:triage", request_id)
    _check_incident_id(incident_id)
    user_id = identity.username  # type: ignore[union-attr]
    delegated_token = await obtain_delegated_token(
        settings,
        identity.subject,  # type: ignore[union-attr]
        _bearer_token(request),
    )
    if not delegated_token:
        # Triage must run under a real operator delegation (SPEC-015 R-3):
        # unlike chat, there is no useful tool-less fallback, so fail fast.
        raise HTTPException(
            status_code=503,
            detail="delegated token unavailable; triage requires the delegation chain",
        )
    response = await run_triage(
        settings, request_id, incident_id, user_id, delegated_token
    )
    log_event(
        LOGGER,
        "incident_triage_requested",
        request_id=request_id,
        user_id=user_id,
        incident_id=incident_id,
        status=response.get("incident", {}).get("status"),
    )
    return response
