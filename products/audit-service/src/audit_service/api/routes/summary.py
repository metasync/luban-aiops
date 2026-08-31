"""Summary aggregate endpoint (SPEC-046 R-1).

Deterministic envelope-column aggregates over the stored trail: totals,
by type/outcome/service buckets, top actors, and the SPEC-037
decision-chain projection. Like the query route (SPEC-013 R-4), the read
is recorded as a structured stdout log line — never self-ingested — and
user-level authorization (``audit:read``) is enforced by platform-gateway
before it proxies here under its own service credential.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from audit_service.core.config import get_settings
from audit_service.core.metrics import record_rejected, record_summary_query
from audit_service.core.observability import log_event
from audit_service.schemas.audit import AuditQuery
from audit_service.schemas.summary import to_response
from audit_service.services.ingest_auth import (
    IngestAuthError,
    authenticate_caller,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/v1/audit/summary")
async def summarize_events(
    request: Request,
    username: str | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    event_type: str | None = None,
    service: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> JSONResponse:
    settings = get_settings()

    try:
        client_id = await authenticate_caller(settings, request)
    except IngestAuthError as exc:
        record_rejected("auth")
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    filters = AuditQuery(
        username=username,
        session_id=session_id,
        request_id=request_id,
        event_type=event_type,
        service=service,
        since=since,
        until=until,
    )
    store = request.app.state.audit_store
    summary = await store.summarize(filters)
    record_summary_query()
    log_event(
        LOGGER,
        "audit_summary_queried",
        client=client_id,
        total_events=summary.total_events,
        event_type=event_type,
        username=username,
    )
    return JSONResponse(
        status_code=200,
        content=to_response(summary).model_dump(mode="json"),
    )
