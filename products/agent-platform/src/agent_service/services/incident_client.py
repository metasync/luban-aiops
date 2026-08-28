"""incident-service client for incident-report assembly (SPEC-043 R-3).

Agent-platform fetches one incident bundle — envelope, triage report,
and connector dispatches — when assembling an ``incident_report``
document. The client authenticates with agent-platform's own registered
Basic query credential (an ``INCIDENT_QUERY_CLIENTS`` entry), the same
posture the platform-gateway's incident client uses — no new auth
mechanism. The call is strictly read-only: incident state is never
mutated from the document surface.

Errors surface as a small structured hierarchy so the documents route
maps them to the house posture — 503 when the dependency is not
configured, 502 on transport failure or upstream 5xx, and 4xx passed
through (unknown incident ids answer the same structural 404 the
incidents surface returns) — never a raw stack trace.
"""

from __future__ import annotations

import logging

import httpx

from agent_service.runtime_settings import RuntimeSettings

LOGGER = logging.getLogger(__name__)

DETAIL_PATH_TEMPLATE = "/api/v1/incidents/{incident_id}"


class IncidentClientError(Exception):
    """Base class for incident-client failures (never a raw traceback)."""


class IncidentDependencyNotConfigured(IncidentClientError):
    """The incident client knobs are unset — creation answers 503."""


class IncidentServiceUnavailable(IncidentClientError):
    """Transport failure or upstream 5xx — creation answers 502."""


class IncidentNotFound(IncidentClientError):
    """Unknown incident id — creation answers the structural 404."""

    def __init__(self, incident_id: str) -> None:
        super().__init__(f"unknown incident id: {incident_id}")
        self.incident_id = incident_id


class IncidentClientRejected(IncidentClientError):
    """Any other upstream 4xx, passed through with its status code."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def is_configured(settings: RuntimeSettings) -> bool:
    """Both the URL and the query secret must be present to call out."""
    return bool(settings.incident_service_url and settings.incident_client_secret)


def _upstream_message(response: httpx.Response) -> str:
    """Extract the incident-service error message when present."""
    try:
        payload = response.json()
        upstream = payload.get("error", {}) if isinstance(payload, dict) else {}
        if isinstance(upstream, dict) and upstream.get("message"):
            return str(upstream["message"])
    except ValueError:
        pass
    return "incident service request failed"


async def fetch_incident_bundle(
    settings: RuntimeSettings,
    request_id: str | None,
    incident_id: str,
) -> dict:
    """Fetch ``{incident, report, dispatches}`` for one incident.

    The incident-service single-incident surface returns all three in
    one call, so assembly makes exactly one upstream request. Raises
    the structured hierarchy above; callers map it to HTTP responses.
    """
    if not is_configured(settings):
        raise IncidentDependencyNotConfigured(
            "incident service not configured for document assembly"
        )
    url = (
        settings.incident_service_url.rstrip("/")  # type: ignore[union-attr]
        + DETAIL_PATH_TEMPLATE.format(incident_id=incident_id)
    )
    headers = {"x-request-id": request_id} if request_id else {}
    try:
        async with httpx.AsyncClient(
            timeout=settings.incident_client_timeout_seconds
        ) as client:
            response = await client.get(
                url,
                auth=(
                    settings.incident_client_id,
                    settings.incident_client_secret,  # type: ignore[arg-type]
                ),
                headers=headers,
            )
    except httpx.HTTPError as exc:
        LOGGER.warning(
            "incident client transport failure for %s: %s", incident_id, exc
        )
        raise IncidentServiceUnavailable("incident service unavailable") from exc

    if response.status_code == 404:
        raise IncidentNotFound(incident_id)
    if response.status_code >= 300:
        if response.status_code >= 500:
            raise IncidentServiceUnavailable("incident service request failed")
        raise IncidentClientRejected(response.status_code, _upstream_message(response))
    return response.json()
