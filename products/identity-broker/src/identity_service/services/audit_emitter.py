"""Fire-and-forget audit event emitter (SPEC-013 R-3).

Ships audit events to the durable audit service over HTTP. Emission is
strictly non-blocking: each event is delivered on a daemon thread with a
short timeout, and failures are swallowed (counted, logged) so the audit
service can never degrade the exchange path. Delivery is synchronous httpx
on a worker thread because the exchange route itself is synchronous. An
unset ``IDENTITY_AUDIT_SERVICE_URL`` keeps the historical log-only
behavior byte-for-byte.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import UTC, datetime

import httpx

from identity_service.core.config import IdentitySettings
from identity_service.core.metrics import record_audit_emit
from identity_service.metadata import SERVICE_NAME

LOGGER = logging.getLogger(__name__)

INGEST_PATH = "/api/v1/audit/events"
EMIT_TIMEOUT_SECONDS = 2.0


def build_audit_event(
    event_type: str,
    request_id: str | None,
    outcome: str,
    *,
    details: dict | None = None,
    subject: str | None = None,
    username: str | None = None,
    actor: str | None = None,
    roles: list[str] | None = None,
    session_id: str | None = None,
) -> dict:
    """Build an envelope matching shared-contracts audit-event.schema.json.

    Optional identity fields are omitted (not nulled) when absent, keeping
    the payload valid against the contract schema.
    """
    event: dict = {
        "event_id": str(uuid.uuid4()),
        "occurred_at": datetime.now(UTC).isoformat(),
        "event_type": event_type,
        "service": SERVICE_NAME,
        "request_id": request_id or "unknown",
        "outcome": outcome,
        "details": details or {},
    }
    for key, value in (
        ("subject", subject),
        ("username", username),
        ("actor", actor),
        ("roles", roles),
        ("session_id", session_id),
    ):
        if value is not None:
            event[key] = value
    return event


def emit_audit_event(settings: IdentitySettings, event: dict) -> None:
    """Fire-and-forget delivery; a no-op when the audit service is not configured."""
    if not settings.audit_service_url:
        return
    threading.Thread(
        target=_deliver, args=(settings, event), daemon=True, name="audit-emit"
    ).start()


def _deliver(settings: IdentitySettings, event: dict) -> None:
    url = f"{settings.audit_service_url.rstrip('/')}{INGEST_PATH}"
    try:
        with httpx.Client(timeout=EMIT_TIMEOUT_SECONDS) as client:
            response = client.post(
                url,
                json={"events": [event]},
                auth=(settings.audit_client_id, settings.audit_client_secret),
            )
        if response.status_code >= 300:
            raise RuntimeError(f"ingest rejected with {response.status_code}")
        record_audit_emit("ok")
    except Exception as exc:  # noqa: BLE001 — fire-and-forget never propagates
        record_audit_emit("error")
        LOGGER.warning(
            "audit emit failed",
            extra={
                "request_id": event.get("request_id"),
                "event_type": event.get("event_type"),
                "error": str(exc),
            },
        )
