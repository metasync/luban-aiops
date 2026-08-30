"""skills-hub validation client for skill-draft generation (SPEC-044 R-2).

Agent-platform validates every generated skill draft against Skill Format
v1 before it reaches the operator, on skills-hub's own ingestion code
path (``POST /api/v1/skills/validate``). The client authenticates with
agent-platform's own registered Basic query credential (a
``SKILLS_QUERY_CLIENTS`` entry) — the same posture as the SPEC-043
incident client, no new auth mechanism. The call is strictly read-only:
skills-hub stores, syncs, and emits nothing for it.

Errors surface as a small structured hierarchy so the generation route
maps them to the house posture — 503 when the dependency is not
configured, 502 on transport failure or upstream 5xx — and an
unvalidated draft is never returned (consistency outranks availability
on a knowledge-production path).
"""

from __future__ import annotations

import logging

import httpx

from agent_service.runtime_settings import RuntimeSettings

LOGGER = logging.getLogger(__name__)

VALIDATE_PATH = "/api/v1/skills/validate"


class SkillsClientError(Exception):
    """Base class for skills-client failures (never a raw traceback)."""


class SkillsDependencyNotConfigured(SkillsClientError):
    """The skills client knobs are unset — generation answers 503."""


class SkillsServiceUnavailable(SkillsClientError):
    """Transport failure or upstream 5xx — generation answers 502."""


class SkillsClientRejected(SkillsClientError):
    """Any upstream 4xx, passed through with its status code."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def is_configured(settings: RuntimeSettings) -> bool:
    """Both the URL and the query secret must be present to call out."""
    return bool(settings.skills_service_url and settings.skills_client_secret)


def _upstream_message(response: httpx.Response) -> str:
    """Extract the skills-hub error message when present."""
    try:
        payload = response.json()
        upstream = payload.get("error", {}) if isinstance(payload, dict) else {}
        if isinstance(upstream, dict) and upstream.get("message"):
            return str(upstream["message"])
    except ValueError:
        pass
    return "skills service request failed"


async def validate_skill_draft(
    settings: RuntimeSettings,
    request_id: str | None,
    markdown: str,
) -> tuple[bool, str | None]:
    """Validate one candidate skill document against Skill Format v1.

    Returns ``(valid, reason)`` using skills-hub's ingestion report
    vocabulary verbatim. Raises the structured hierarchy above; callers
    map it to HTTP responses and never fall back to returning the
    unvalidated draft.
    """
    if not is_configured(settings):
        raise SkillsDependencyNotConfigured(
            "skills service not configured for skill-draft validation"
        )
    url = (
        settings.skills_service_url.rstrip("/")  # type: ignore[union-attr]
        + VALIDATE_PATH
    )
    headers = {"x-request-id": request_id} if request_id else {}
    try:
        async with httpx.AsyncClient(
            timeout=settings.skills_client_timeout_seconds
        ) as client:
            response = await client.post(
                url,
                json={"document": markdown},
                auth=(
                    settings.skills_client_id,
                    settings.skills_client_secret,  # type: ignore[arg-type]
                ),
                headers=headers,
            )
    except httpx.HTTPError as exc:
        LOGGER.warning("skills client transport failure: %s", exc)
        raise SkillsServiceUnavailable("skills service unavailable") from exc

    if response.status_code >= 300:
        if response.status_code >= 500:
            raise SkillsServiceUnavailable("skills service request failed")
        raise SkillsClientRejected(response.status_code, _upstream_message(response))
    payload = response.json()
    valid = bool(payload.get("valid"))
    reason = payload.get("reason") if not valid else None
    return valid, str(reason) if reason is not None else None
