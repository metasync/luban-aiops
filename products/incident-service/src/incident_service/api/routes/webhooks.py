"""Alertmanager webhook intake (SPEC-015 R-2).

One alert group becomes one incident. The route authenticates with a shared
bearer token (``INCIDENT_WEBHOOK_TOKEN``) and fails closed (503) when the
token is not configured. Dedupe is fingerprint-based: a firing payload with
a known open fingerprint updates the existing incident, and a ``resolved``
payload closes it; a resolution for an unknown fingerprint is an idempotent
no-op success.
"""

from __future__ import annotations

import hmac
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from incident_service.core.config import IncidentSettings, get_settings
from incident_service.core.metrics import record_intake, set_open_incidents
from incident_service.core.observability import log_event
from incident_service.schemas.incident import (
    Incident,
    IncidentSeverity,
    IncidentSource,
    IncidentStatus,
)
from incident_service.services.incident_store import IncidentStore
from incident_service.services.normalization import (
    IncidentInput,
    NormalizationError,
    normalize_alertmanager,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


def _store(request: Request) -> IncidentStore:
    return request.app.state.incident_store


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def _new_incident_id() -> str:
    return f"inc-{uuid.uuid4().hex[:12]}"


def _check_webhook_token(request: Request, settings: IncidentSettings) -> bool:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return False
    presented = header[7:].strip()
    # Encode to bytes so non-ASCII header values (latin-1 decoded by the
    # ASGI server) cannot raise TypeError inside compare_digest.
    return hmac.compare_digest(
        presented.encode("utf-8"), settings.webhook_token.encode("utf-8")
    )


@router.post("/webhooks/alertmanager")
async def alertmanager_webhook(
    request: Request, settings: IncidentSettings = Depends(get_settings)
) -> JSONResponse:
    if not settings.webhook_token:
        # Fail closed: an unconfigured token must never accept webhooks.
        return _error(
            503,
            "WEBHOOK_NOT_CONFIGURED",
            "INCIDENT_WEBHOOK_TOKEN is not configured",
        )
    if not _check_webhook_token(request, settings):
        record_intake("alertmanager", "rejected_auth")
        return _error(401, "UNAUTHORIZED", "invalid webhook token")

    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 - any parse failure is a client error
        record_intake("alertmanager", "rejected_malformed")
        return _error(400, "INVALID_PAYLOAD", "body must be valid JSON")
    try:
        normalized = normalize_alertmanager(payload)
    except NormalizationError as exc:
        record_intake("alertmanager", "rejected_malformed")
        return _error(400, "INVALID_PAYLOAD", str(exc))

    store = _store(request)
    now = datetime.now(timezone.utc)
    if normalized.resolved:
        response = await _resolve(store, normalized, now)
    else:
        response = await _fire(store, normalized, now)
    set_open_incidents(await store.count(open_only=True))
    return response


async def _resolve(
    store: IncidentStore, normalized: IncidentInput, now: datetime
) -> JSONResponse:
    existing = await store.get_open_by_fingerprint(normalized.fingerprint)
    if existing is None:
        # Idempotent webhook semantics: nothing open to resolve.
        log_event(
            LOGGER,
            "webhook_resolution_ignored",
            fingerprint=normalized.fingerprint,
        )
        return JSONResponse(
            content={
                "action": "ignored",
                "incident_id": None,
                "fingerprint": normalized.fingerprint,
            }
        )
    resolved = existing.model_copy(
        update={
            "status": IncidentStatus.RESOLVED,
            "resolved_at": now,
            "updated_at": now,
        }
    )
    await store.save(resolved)
    record_intake("alertmanager", "resolved")
    log_event(
        LOGGER,
        "incident_resolved",
        incident_id=resolved.incident_id,
        fingerprint=normalized.fingerprint,
    )
    return JSONResponse(
        content={
            "action": "resolved",
            "incident_id": resolved.incident_id,
            "fingerprint": normalized.fingerprint,
        }
    )


async def _fire(
    store: IncidentStore, normalized: IncidentInput, now: datetime
) -> JSONResponse:
    existing = await store.get_open_by_fingerprint(normalized.fingerprint)
    if existing is not None:
        updated = existing.model_copy(
            update={
                "severity": IncidentSeverity(normalized.severity),
                "title": normalized.title,
                "summary": normalized.summary,
                "labels": normalized.labels,
                "updated_at": now,
            }
        )
        await store.save(updated)
        record_intake("alertmanager", "updated")
        log_event(
            LOGGER,
            "incident_updated",
            incident_id=updated.incident_id,
            fingerprint=normalized.fingerprint,
        )
        return JSONResponse(
            content={
                "action": "updated",
                "incident_id": updated.incident_id,
                "fingerprint": normalized.fingerprint,
            }
        )
    incident = Incident(
        incident_id=_new_incident_id(),
        fingerprint=normalized.fingerprint,
        source=IncidentSource.ALERTMANAGER,
        severity=normalized.severity,
        status=IncidentStatus.NEW,
        title=normalized.title,
        summary=normalized.summary,
        labels=normalized.labels,
        created_at=now,
        updated_at=now,
    )
    await store.create(incident)
    record_intake("alertmanager", "created")
    log_event(
        LOGGER,
        "incident_created",
        incident_id=incident.incident_id,
        source="alertmanager",
        fingerprint=normalized.fingerprint,
        severity=incident.severity.value,
    )
    return JSONResponse(
        status_code=201,
        content={
            "action": "created",
            "incident_id": incident.incident_id,
            "fingerprint": normalized.fingerprint,
        },
    )
