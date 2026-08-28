"""Incident-report digest assembly (SPEC-043 R-2).

Builds the ``incident_report`` digest from one fetched incident bundle
(envelope, validated triage report, connector dispatches — all copied
verbatim) plus the platform's own durable stores for the incident's
linked triage session. Like shift summaries, facts are copied verbatim
and record ids are provenance anchors, never live references.

The digest carries four deterministic sections:

- ``incident`` — the envelope minus the raw triage text (the prose
  contract never sees raw triage; a ``has_triage_raw`` presence marker
  replaces it);
- ``triage`` — the validated triage report, or the ``not_triaged``
  marker when the incident has none;
- ``dispatches`` — connector dispatch outcomes, possibly empty;
- ``session`` — the linked triage session under the SPEC-039 R-3
  two-tier posture: full digest when the requester owns the session,
  metadata-only when it is foreign and the requester holds
  ``approvals:list``, the ``foreign_denied`` marker when foreign
  without it, ``missing`` when the incident carries no session id, and
  ``unavailable`` when the session store cannot cover it.

Assembly is read-only with respect to incident state and never 500s on
incident content.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from agent_service.services.session_store import SESSION_STORE
from agent_service.services.shift_summary import (
    _digest_foreign_session,
    _digest_own_session,
)

LOGGER = logging.getLogger(__name__)

NOT_TRIAGED = {"status": "not_triaged"}

# Envelope fields copied into the incident section. ``triage_raw`` is
# deliberately excluded — the raw triage text never reaches the digest
# (and therefore never the prose prompt); its presence rides a marker.
_INCIDENT_SECTION_FIELDS = (
    "incident_id",
    "fingerprint",
    "source",
    "severity",
    "status",
    "title",
    "summary",
    "labels",
    "reported_by",
    "session_id",
    "created_at",
    "updated_at",
    "resolved_at",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _incident_section(envelope: dict[str, Any]) -> dict[str, Any]:
    section = {
        key: envelope.get(key)
        for key in _INCIDENT_SECTION_FIELDS
        if envelope.get(key) is not None
    }
    section["has_triage_raw"] = bool(envelope.get("triage_raw"))
    return section


def _dispatch_section(dispatches: Any) -> list[dict[str, Any]]:
    """Dispatch outcomes copied verbatim (possibly empty)."""
    if not isinstance(dispatches, list):
        return []
    return [dict(row) for row in dispatches if isinstance(row, dict)]


def _session_section(
    envelope: dict[str, Any],
    requester_user_id: str,
    can_view_foreign: bool,
) -> tuple[dict[str, Any], list[str]]:
    """The linked triage session under the two-tier posture.

    Returns ``(section, cited_record_ids)``; the cited ids flow the
    provenance block exactly as shift summaries do.
    """
    session_id = envelope.get("session_id")
    if not session_id:
        return {"status": "missing"}, []

    try:
        record = SESSION_STORE.get_session(session_id)
    except Exception as exc:  # noqa: BLE001 — per-source degradation
        LOGGER.warning("incident report session read failed: %s", exc)
        return {"status": "unavailable", "session_id": session_id}, []
    if record is None:
        # The linked session can no longer be covered (retention or
        # never persisted); the incident sections still assemble.
        return {"status": "unavailable", "session_id": session_id}, []

    if (record.user_id or "") == requester_user_id:
        entry, cited = _digest_own_session(record, session_id)
        entry = {"status": "owner", **entry}
        return entry, cited

    if not can_view_foreign:
        # Foreign coverage fails closed exactly as SPEC-039 R-3: the
        # marker rides the digest instead of rejecting the whole
        # report, because the incident facts themselves only require
        # incident:read (server-derived coverage, not caller input).
        return {"status": "foreign_denied", "session_id": session_id}, []

    entry, cited = _digest_foreign_session(session_id)
    entry = {"status": "foreign", **entry}
    return entry, cited


def build_digest(
    requester_user_id: str,
    bundle: dict[str, Any],
    can_view_foreign: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Assemble the incident-report digest and its provenance block.

    ``bundle`` is the incident-service single-incident payload
    (``incident`` / ``report`` / ``dispatches``). Returns
    ``(digest, provenance)``.
    """
    envelope = bundle.get("incident") or {}
    report = bundle.get("report")

    session_section, cited = _session_section(
        envelope, requester_user_id, can_view_foreign
    )

    provenance_sessions: list[dict[str, Any]] = []
    session_id = envelope.get("session_id")
    if session_id and session_section.get("status") in ("owner", "foreign"):
        provenance_sessions.append(
            {
                "session_id": session_id,
                "coverage": session_section["status"],
                "cited_record_ids": cited,
            }
        )

    digest = {
        "generated_at": _utc_now_iso(),
        "requester_user_id": requester_user_id,
        "incident": _incident_section(envelope),
        "triage": dict(report) if isinstance(report, dict) else dict(NOT_TRIAGED),
        "dispatches": _dispatch_section(bundle.get("dispatches")),
        "session": session_section,
    }
    provenance: dict[str, Any] = {
        "incident_id": envelope.get("incident_id"),
        "sessions": provenance_sessions,
    }
    return digest, provenance


def _plural(count: int, noun: str) -> str:
    if count == 1:
        return f"{count} {noun}"
    suffix = "es" if noun.endswith(("ch", "sh", "s", "x", "z")) else "s"
    return f"{count} {noun}{suffix}"


def document_summary(digest: dict[str, Any]) -> str | None:
    """Deterministic counts-only one-liner for the list surface.

    Severity, status, triage presence, and dispatch/session counts —
    never the incident title or summary text — so the string may flow
    through the envelope-only listing. Returns ``None`` when the digest
    carries no incident section.
    """
    incident = digest.get("incident")
    if not isinstance(incident, dict):
        return None
    parts: list[str] = []
    if incident.get("severity"):
        parts.append(str(incident["severity"]))
    if incident.get("status"):
        parts.append(str(incident["status"]))
    triage = digest.get("triage")
    if isinstance(triage, dict) and triage.get("status") == "not_triaged":
        parts.append("not triaged")
    else:
        parts.append("triage report present")
    dispatches = digest.get("dispatches")
    if isinstance(dispatches, list):
        parts.append(_plural(len(dispatches), "dispatch"))
    session = digest.get("session")
    if isinstance(session, dict):
        status = session.get("status")
        if status == "owner":
            parts.append("own session")
        elif status == "foreign":
            parts.append("foreign session (metadata only)")
        elif status == "foreign_denied":
            parts.append("foreign session denied")
        elif status == "missing":
            parts.append("no linked session")
        elif status == "unavailable":
            parts.append("session unavailable")
    return " · ".join(parts) if parts else None
