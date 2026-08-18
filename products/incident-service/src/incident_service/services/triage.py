"""Operator-initiated agent triage (SPEC-015 R-3, SPEC-017 R-2).

The triage run is a single agent turn in a dedicated session
(``incident-<incident_id>``): incident-service builds the prompt from a
service template, relays the operator's delegated bearer to agent-platform
``/api/v2/chat``, and captures the reply as a schema-validated triage
report. The turn requests kernel-validated structured output by sending
the triage-report JSON schema as ``response_schema``; the kernel-validated
``structured_output`` is preferred, and the legacy fenced ``triage-report``
block parser remains as fallback when ``structured_output`` is ``null``.
Anything that does not validate marks the incident ``triage_failed`` with
the raw agent text preserved — tool-gateway stays strictly read-only, so
no write tool is involved.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from incident_service.core.config import IncidentSettings
from incident_service.core.metrics import record_triage
from incident_service.core.observability import log_event
from incident_service.schemas.incident import (
    Incident,
    IncidentStatus,
    TriageReport,
)

LOGGER = logging.getLogger(__name__)

CHAT_PATH = "/api/v2/chat"
SESSIONS_PATH = "/api/v2/sessions"
TRIAGE_BLOCK_FENCE = re.compile(
    r"```triage-report[ \t]*\r?\n(.*?)\r?\n?[ \t]*```", re.DOTALL
)

TRIAGE_PROMPT_TEMPLATE = """\
You are triaging an incident on the Luban AIOps platform. Work read-only,
gather evidence, and produce a structured triage report.

## Incident under triage
- Incident ID: {incident_id}
- Source: {source}
- Reported severity: {severity}
- Status: {status}
- Title: {title}
- Summary: {summary}
- Labels: {labels}

## Triage discipline
1. Gather live evidence with the read-only tools (k8s.*, elastic.*,
   skills.search, incidents.*). Prefer evidence that matches the labels and
   title above.
2. Run skills.search for runbooks matching this incident and cite every
   skill you relied on in `skills_cited`.
3. Ground every hypothesis and every next step in evidence you actually
   gathered or in a cited skill — never fabricate observations.
4. Next steps are advisory only: this platform does not execute actions.

## Output format
If a structured output requirement is active for this turn, deliver the
report by calling the provided structured-output tool with the report
fields. Otherwise, reply with exactly one fenced code block tagged
`triage-report` containing only a JSON object with this shape:

```triage-report
{{
  "incident_id": "{incident_id}",
  "summary": "<one-paragraph assessment of what is happening>",
  "severity_assessment": "critical|warning|info",
  "evidence": [{{"source": "<tool or skill>", "description": "<finding>"}}],
  "hypotheses": ["<ranked likely causes>"],
  "next_steps": [
    {{"title": "<action>", "rationale": "<why>", "priority": "high|medium|low"}}
  ],
  "skills_cited": ["<skill ids used>"],
  "session_id": "{session_id}",
  "generated_at": "<RFC 3339 timestamp>",
  "generated_by": "{operator}"
}}
```

No prose inside the block; the JSON must parse."""


class TriageError(Exception):
    """Raised when the agent turn or report capture cannot succeed."""


def session_id_for(incident_id: str) -> str:
    """Dedicated agent session for one incident."""
    return f"incident-{incident_id}"


def _operator_slug(operator: str) -> str:
    """Safe suffix for per-operator fallback sessions."""
    slug = re.sub(r"[^A-Za-z0-9._-]", "-", operator or "").strip("-")
    return slug[:64] or "operator"


def session_candidates_for(incident_id: str, operator: str) -> list[str]:
    """Candidate dedicated sessions for one incident.

    The shared ``incident-<id>`` session comes first so repeat triage by
    the owning operator keeps one conversation; the per-operator fallback
    keeps re-triage working for a second operator (agent-platform sessions
    are single-owner and hide foreign owners behind 404).
    """
    primary = session_id_for(incident_id)
    return [primary, f"{primary}--{_operator_slug(operator)}"]


def build_triage_prompt(
    incident: Incident, operator: str, session_id: str
) -> str:
    labels = ", ".join(f"{k}={v}" for k, v in sorted(incident.labels.items()))
    return TRIAGE_PROMPT_TEMPLATE.format(
        incident_id=incident.incident_id,
        source=incident.source.value,
        severity=incident.severity.value,
        status=incident.status.value,
        title=incident.title,
        summary=incident.summary or "(none)",
        labels=labels or "(none)",
        session_id=session_id,
        operator=operator,
    )


def extract_triage_block(text: str) -> str | None:
    """Return the contents of the last fenced ``triage-report`` block."""
    matches = TRIAGE_BLOCK_FENCE.findall(text or "")
    if not matches:
        return None
    return matches[-1].strip()


def _finalize_report(
    payload: Any, incident: Incident, operator: str, session_id: str
) -> TriageReport:
    """Force server-minted attribution and validate against the contract.

    Attribution is never trusted from agent output: incident_id /
    session_id / generated_at / generated_by are forced to the
    server-known facts so prompt injection via the incident content
    cannot spoof who ran the triage on the durable trail.
    """
    if not isinstance(payload, dict):
        raise TriageError("triage report must be a JSON object")
    payload["incident_id"] = incident.incident_id
    payload["session_id"] = session_id
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    payload["generated_by"] = operator
    try:
        return TriageReport.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 - pydantic raises many subclasses
        raise TriageError(
            f"triage-report does not conform to the schema: {exc}"
        ) from exc


def parse_triage_report(
    raw_text: str, incident: Incident, operator: str, session_id: str
) -> TriageReport:
    """Extract and validate the report from a fenced block in the reply.

    Legacy fallback path (SPEC-017 R-2): used when the kernel did not
    return a ``structured_output`` for the turn.
    """
    block = extract_triage_block(raw_text)
    if block is None:
        raise TriageError("no fenced triage-report block in agent reply")
    try:
        payload = json.loads(block)
    except json.JSONDecodeError as exc:
        raise TriageError(f"triage-report block is not valid JSON: {exc}") from exc
    return _finalize_report(payload, incident, operator, session_id)


async def _establish_session(
    client: httpx.AsyncClient,
    base_url: str,
    candidates: list[str],
    headers: dict[str, str],
) -> str:
    """Create the dedicated session, falling back per operator on 404.

    A 404 means the session exists but is owned by another operator
    (agent-platform hides foreign owners behind 404), so the next
    candidate is tried; any other non-2xx aborts the triage.
    """
    for candidate in candidates:
        response = await client.post(
            f"{base_url}{SESSIONS_PATH}",
            json={"session_id": candidate},
            headers=headers,
        )
        if response.status_code in (200, 201):
            return candidate
        if response.status_code != 404:
            raise TriageError(
                "agent-platform session create returned "
                f"{response.status_code}"
            )
    raise TriageError(
        "agent-platform rejected every candidate triage session"
    )


async def _call_agent(
    settings: IncidentSettings,
    incident: Incident,
    operator: str,
    bearer_token: str,
    request_id: str,
) -> tuple[str, dict[str, Any] | None, str]:
    """Run one triage turn.

    Returns the agent reply text, the kernel-validated structured output
    (or ``None`` when the kernel did not produce one), and the session
    used. The turn requests structured output by sending the triage
    report JSON schema as ``response_schema`` (SPEC-017 R-2).
    """
    timeout = httpx.Timeout(settings.triage_timeout_seconds, connect=5.0)
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "X-User-ID": operator,
        "X-Request-Id": request_id,
    }
    base_url = settings.agent_service_url.rstrip("/")
    async with httpx.AsyncClient(timeout=timeout) as client:
        # agent-platform rejects unknown session ids on /chat, so establish
        # the dedicated session first (idempotent for the owning operator).
        session_id = await _establish_session(
            client,
            base_url,
            session_candidates_for(incident.incident_id, operator),
            headers,
        )
        prompt = build_triage_prompt(incident, operator, session_id)
        response = await client.post(
            f"{base_url}{CHAT_PATH}",
            json={
                "message": prompt,
                "session_id": session_id,
                "response_schema": TriageReport.model_json_schema(),
            },
            headers=headers,
        )
    if response.status_code != 200:
        raise TriageError(f"agent-platform returned {response.status_code}")
    try:
        body = response.json()
    except ValueError as exc:
        raise TriageError("agent-platform returned a non-JSON body") from exc
    content = body.get("content")
    if not isinstance(content, str) or not content:
        raise TriageError("agent-platform reply has no content")
    structured_output = body.get("structured_output")
    if not isinstance(structured_output, dict):
        structured_output = None
    return content, structured_output, session_id


def _mark_failed(incident: Incident, reason: str, raw_text: str) -> Incident:
    preserved = raw_text.strip() or f"triage failed: {reason}"
    return incident.model_copy(
        update={
            "status": IncidentStatus.TRIAGE_FAILED,
            "triage_raw": preserved[:65536],
            "updated_at": datetime.now(timezone.utc),
        }
    )


async def run_triage(
    settings: IncidentSettings,
    store,
    incident: Incident,
    operator: str,
    bearer_token: str,
    request_id: str,
) -> tuple[Incident, TriageReport | None]:
    """Run one triage turn and persist the outcome (latest report wins).

    Returns the updated incident and, on success, the validated report.
    Connector dispatch is the caller's responsibility (R-5).
    """
    session_id = session_id_for(incident.incident_id)
    incident = incident.model_copy(
        update={
            "status": IncidentStatus.TRIAGING,
            "session_id": session_id,
            "triage_raw": None,
            "updated_at": datetime.now(timezone.utc),
        }
    )
    await store.save(incident)
    log_event(
        LOGGER,
        "triage_started",
        incident_id=incident.incident_id,
        session_id=session_id,
        operator=operator,
    )

    raw_text = ""
    session_used = session_id
    try:
        raw_text, structured_output, session_used = await _call_agent(
            settings, incident, operator, bearer_token, request_id
        )
        # Kernel-validated structured output is preferred; the fenced-block
        # parser remains as fallback when the kernel returned none.
        if structured_output is not None:
            report = _finalize_report(
                structured_output, incident, operator, session_used
            )
        else:
            report = parse_triage_report(
                raw_text, incident, operator, session_used
            )
    except (TriageError, httpx.HTTPError) as exc:
        failed = _mark_failed(incident, str(exc), raw_text)
        if failed.session_id != session_used:
            failed = failed.model_copy(update={"session_id": session_used})
        incident = await store.save(failed)
        record_triage("failed")
        log_event(
            LOGGER,
            "triage_failed",
            incident_id=incident.incident_id,
            reason=str(exc),
        )
        return incident, None

    await store.set_report(incident.incident_id, report)
    incident = await store.save(
        incident.model_copy(
            update={
                "status": IncidentStatus.TRIAGED,
                "session_id": session_used,
                "updated_at": datetime.now(timezone.utc),
            }
        )
    )
    record_triage("triaged")
    log_event(
        LOGGER,
        "triage_completed",
        incident_id=incident.incident_id,
        session_id=session_used,
        operator=operator,
        next_steps=len(report.next_steps),
    )
    return incident, report
