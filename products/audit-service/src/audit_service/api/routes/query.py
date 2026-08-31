"""Query endpoint (SPEC-013 R-4).

Returns stored audit envelopes verbatim, newest-first, with keyset cursor
pagination. User-level authorization (the ``audit:read`` policy action) is
enforced by platform-gateway before it proxies here under its own service
credential; this route additionally requires a registered service caller.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from audit_service.core.config import get_settings
from audit_service.core.metrics import record_query, record_rejected
from audit_service.core.observability import log_event
from audit_service.schemas.audit import AuditQuery, Outcome
from audit_service.services.audit_store import StoreError, decode_cursor
from audit_service.services.ingest_auth import (
    IngestAuthError,
    authenticate_caller,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter()

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


@router.get("/api/v1/audit/events")
async def query_events(
    request: Request,
    username: str | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    event_type: str | None = None,
    service: str | None = None,
    outcome: Outcome | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    cursor: str | None = None,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> JSONResponse:
    settings = get_settings()

    try:
        client_id = await authenticate_caller(settings, request)
    except IngestAuthError as exc:
        record_rejected("auth")
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    if cursor is not None:
        try:
            decode_cursor(cursor)
        except StoreError as exc:
            return JSONResponse(
                status_code=400, content={"detail": str(exc)}
            )

    filters = AuditQuery(
        username=username,
        session_id=session_id,
        request_id=request_id,
        event_type=event_type,
        service=service,
        outcome=outcome,
        since=since,
        until=until,
    )
    store = request.app.state.audit_store
    page = await store.query(filters, cursor, limit)
    record_query()
    log_event(
        LOGGER,
        "audit_events_queried",
        client=client_id,
        returned=len(page.events),
        event_type=event_type,
        username=username,
    )
    return JSONResponse(
        status_code=200,
        content={
            "events": [
                event.model_dump(mode="json") for event in page.events
            ],
            "next_cursor": page.next_cursor,
        },
    )
