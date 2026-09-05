"""skills-hub inventory proxy client (SPEC-019 R-4).

Read-only skills inventory for the portal's Workspace view. The gateway
authenticates to skills-hub with its own Basic query credential (a
``SKILLS_QUERY_CLIENTS`` entry) — the user's token is never forwarded for
inventory reads, the same posture as the audit and incident proxies.

Error mapping follows the incident-client precedent: 503 when skills-hub
is not configured, 502 on transport failure or upstream 5xx, and 4xx
passed through with the upstream message.
"""

from __future__ import annotations

import logging
import re

import httpx
from fastapi import HTTPException

from platform_gateway.core.config import PlatformGatewaySettings

LOGGER = logging.getLogger(__name__)

PROXY_TIMEOUT_SECONDS = 10.0
LIST_PATH = "/api/v1/skills"

# SPEC-052 R-1 hardening: the detail hop folds ``skill_id`` into an upstream URL
# path segment, so it is held to skills-hub's own producer contract — one or more
# ``[a-z0-9]`` runs joined by single ``-`` within a segment, and at least two
# ``/``-separated segments (``<source_id>/<slug>``). Anything else (``..``
# traversal, absolute paths, ``%``-encoded octets, spaces, uppercase, empty or
# duplicate slashes) is rejected before it can reach the URL. skills-hub itself
# only ever does a keyed store lookup, so this is defense-in-depth at the edge,
# not the sole barrier.
_SKILL_ID_RE = re.compile(
    r"^[a-z0-9]+(?:-[a-z0-9]+)*(?:/[a-z0-9]+(?:-[a-z0-9]+)*)+$"
)


def _base_url(settings: PlatformGatewaySettings) -> str:
    if not settings.skills_hub_url:
        raise HTTPException(
            status_code=503, detail="skills hub not configured"
        )
    return settings.skills_hub_url.rstrip("/")


def _credential(settings: PlatformGatewaySettings) -> tuple[str, str]:
    return (settings.skills_client_id, settings.skills_client_secret)


def _raise_upstream(response: httpx.Response) -> None:
    """Translate a non-2xx upstream response into a gateway HTTPException."""
    message = "skills hub request failed"
    try:
        payload = response.json()
        upstream = payload.get("error", {}) if isinstance(payload, dict) else {}
        if isinstance(upstream, dict) and upstream.get("message"):
            message = str(upstream["message"])
    except ValueError:
        pass
    if 400 <= response.status_code < 500:
        # Pass client errors through unchanged (bad filters, credential
        # mismatch) so callers can tell them apart from an upstream outage,
        # which alone warrants the 502 mapping.
        raise HTTPException(status_code=response.status_code, detail=message)
    raise HTTPException(status_code=502, detail="skills hub request failed")


async def list_skills(
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
            status_code=502, detail="skills hub unavailable"
        ) from exc
    if response.status_code >= 300:
        _raise_upstream(response)
    return response.json()


async def get_skill(
    settings: PlatformGatewaySettings,
    request_id: str,
    skill_id: str,
) -> dict:
    """Fetch one full skill record (SPEC-052 R-1).

    The list payload omits ``body`` by contract, so the portal reads a
    skill's content through this detail hop. ``skill_id`` is the namespaced
    ``<source_id>/<slug>`` form; it is checked against ``_SKILL_ID_RE`` before
    being folded into the upstream URL, so a traversal-shaped or otherwise
    malformed identifier is rejected here rather than forwarded. Valid ids keep
    their segment separators literally for skills-hub's ``{skill_id:path}``
    matcher. Same credential and error posture as :func:`list_skills` — the
    user's token is never forwarded.
    """
    if not _SKILL_ID_RE.match(skill_id):
        # Reject at the sink, before any URL is built. The generic 404 mirrors
        # skills-hub's SKILL_NOT_FOUND, so a structural reject is
        # indistinguishable from an absent skill (no enumeration oracle).
        raise HTTPException(status_code=404, detail="unknown skill id")
    url = f"{_base_url(settings)}{LIST_PATH}/{skill_id}"
    try:
        async with httpx.AsyncClient(timeout=PROXY_TIMEOUT_SECONDS) as client:
            response = await client.get(
                url,
                auth=_credential(settings),
                headers={"x-request-id": request_id},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="skills hub unavailable"
        ) from exc
    if response.status_code >= 300:
        _raise_upstream(response)
    return response.json()
