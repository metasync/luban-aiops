"""incident-service proxy client (SPEC-015 R-7).

Every portal call to incident-service flows through this module. The gateway
authenticates to incident-service with its own Basic query credential (an
``INCIDENT_QUERY_CLIENTS`` entry) — the user's token is never forwarded for
query or intake. Triage is the one flow that also carries operator identity
upstream: ``X-User-ID`` names the operator and ``X-Delegated-Token`` relays
the broker-mediated delegated bearer, so the agent turn runs under a real
operator identity exactly like chat (SPEC-008 chain, unchanged).

Error mapping follows the audit-proxy precedent: 503 when the incident
service is not configured, 502 on transport failure or upstream 5xx, and
4xx passed through with the upstream message so callers can distinguish a
bad request from an outage.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException

from platform_gateway.core.config import PlatformGatewaySettings

LOGGER = logging.getLogger(__name__)

PROXY_TIMEOUT_SECONDS = 10.0
LIST_PATH = "/api/v1/incidents"
DETAIL_PATH_TEMPLATE = "/api/v1/incidents/{incident_id}"
REPORT_PATH_TEMPLATE = "/api/v1/incidents/{incident_id}/report"
TRIAGE_PATH_TEMPLATE = "/api/v1/incidents/{incident_id}/triage"


def _base_url(settings: PlatformGatewaySettings) -> str:
    if not settings.incident_service_url:
        raise HTTPException(
            status_code=503, detail="incident service not configured"
        )
    return settings.incident_service_url.rstrip("/")


def _credential(settings: PlatformGatewaySettings) -> tuple[str, str]:
    return (settings.incident_client_id, settings.incident_client_secret)


def _raise_upstream(response: httpx.Response) -> None:
    """Translate a non-2xx upstream response into a gateway HTTPException."""
    message = "incident service request failed"
    try:
        payload = response.json()
        upstream = payload.get("error", {}) if isinstance(payload, dict) else {}
        if isinstance(upstream, dict) and upstream.get("message"):
            message = str(upstream["message"])
    except ValueError:
        pass
    if 400 <= response.status_code < 500:
        # Pass client errors through unchanged (unknown incident, bad
        # filters, validation) so callers can tell them apart from an
        # upstream outage, which alone warrants the 502 mapping.
        raise HTTPException(status_code=response.status_code, detail=message)
    raise HTTPException(status_code=502, detail="incident service request failed")


async def list_incidents(
    settings: PlatformGatewaySettings,
    request_id: str,
    params: dict[str, str | int],
) -> dict:
    url = f"{_base_url(settings)}{LIST_PATH}"
    try:
        async with httpx.AsyncClient(timeout=PROXY_TIMEOUT_SECONDS) as client:
            response = await client.get(
                url,
                params=params,
                auth=_credential(settings),
                headers={"x-request-id": request_id},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="incident service unavailable"
        ) from exc
    if response.status_code >= 300:
        _raise_upstream(response)
    return response.json()


async def get_incident(
    settings: PlatformGatewaySettings,
    request_id: str,
    incident_id: str,
) -> dict:
    url = f"{_base_url(settings)}{DETAIL_PATH_TEMPLATE.format(incident_id=incident_id)}"
    try:
        async with httpx.AsyncClient(timeout=PROXY_TIMEOUT_SECONDS) as client:
            response = await client.get(
                url,
                auth=_credential(settings),
                headers={"x-request-id": request_id},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="incident service unavailable"
        ) from exc
    if response.status_code >= 300:
        _raise_upstream(response)
    return response.json()


async def get_report(
    settings: PlatformGatewaySettings,
    request_id: str,
    incident_id: str,
) -> dict:
    url = f"{_base_url(settings)}{REPORT_PATH_TEMPLATE.format(incident_id=incident_id)}"
    try:
        async with httpx.AsyncClient(timeout=PROXY_TIMEOUT_SECONDS) as client:
            response = await client.get(
                url,
                auth=_credential(settings),
                headers={"x-request-id": request_id},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="incident service unavailable"
        ) from exc
    if response.status_code >= 300:
        _raise_upstream(response)
    return response.json()


async def create_incident(
    settings: PlatformGatewaySettings,
    request_id: str,
    payload: dict,
    reported_by: str,
) -> dict:
    url = f"{_base_url(settings)}{LIST_PATH}"
    try:
        async with httpx.AsyncClient(timeout=PROXY_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url,
                json=payload,
                auth=_credential(settings),
                headers={
                    "x-request-id": request_id,
                    "x-reported-by": reported_by,
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="incident service unavailable"
        ) from exc
    if response.status_code >= 300:
        _raise_upstream(response)
    return response.json()


async def run_triage(
    settings: PlatformGatewaySettings,
    request_id: str,
    incident_id: str,
    operator: str,
    delegated_token: str,
) -> dict:
    """Forward an operator-initiated triage run to incident-service.

    The gateway's Basic credential authenticates the call; the operator's
    name and delegated bearer travel in dedicated headers so the agent turn
    keeps the operator's identity and tool authority.
    """
    url = f"{_base_url(settings)}{TRIAGE_PATH_TEMPLATE.format(incident_id=incident_id)}"
    try:
        async with httpx.AsyncClient(
            timeout=settings.incident_triage_timeout_seconds
        ) as client:
            response = await client.post(
                url,
                auth=_credential(settings),
                headers={
                    "x-request-id": request_id,
                    "x-user-id": operator,
                    "x-delegated-token": delegated_token,
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="incident service unavailable"
        ) from exc
    if response.status_code >= 300:
        _raise_upstream(response)
    return response.json()
