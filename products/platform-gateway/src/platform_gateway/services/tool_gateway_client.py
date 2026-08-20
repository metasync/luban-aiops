"""tool-gateway inventory proxy client (SPEC-019 R-4).

Read-only tool discovery for the portal's Workspace view. The gateway
forwards a broker-mediated delegated token (audience ``tool-gateway``,
SPEC-008 chain) so the downstream sees real operator authority — the
portal's session token itself never crosses the service boundary.

Error mapping follows the incident-client precedent: 503 when the
tool-gateway is not configured, 502 on transport failure or upstream 5xx,
and 4xx passed through so callers can tell a rejected request from an
outage.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException

from platform_gateway.core.config import PlatformGatewaySettings

LOGGER = logging.getLogger(__name__)

PROXY_TIMEOUT_SECONDS = 10.0
LIST_PATH = "/api/v2/tools"


def _base_url(settings: PlatformGatewaySettings) -> str:
    if not settings.tool_gateway_url:
        raise HTTPException(
            status_code=503, detail="tool gateway not configured"
        )
    return settings.tool_gateway_url.rstrip("/")


def _raise_upstream(response: httpx.Response) -> None:
    """Translate a non-2xx upstream response into a gateway HTTPException."""
    message = "tool gateway request failed"
    try:
        payload = response.json()
        if isinstance(payload, dict) and payload.get("detail"):
            message = str(payload["detail"])
    except ValueError:
        pass
    if 400 <= response.status_code < 500:
        # Pass client errors through unchanged (e.g. the delegated token was
        # rejected upstream) so callers can tell them apart from an upstream
        # outage, which alone warrants the 502 mapping.
        raise HTTPException(status_code=response.status_code, detail=message)
    raise HTTPException(status_code=502, detail="tool gateway request failed")


async def list_tools(
    settings: PlatformGatewaySettings,
    request_id: str,
    delegated_token: str,
) -> list:
    url = f"{_base_url(settings)}{LIST_PATH}"
    try:
        async with httpx.AsyncClient(timeout=PROXY_TIMEOUT_SECONDS) as client:
            response = await client.get(
                url,
                headers={
                    "authorization": f"Bearer {delegated_token}",
                    "x-request-id": request_id,
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="tool gateway unavailable"
        ) from exc
    if response.status_code >= 300:
        _raise_upstream(response)
    return response.json()
