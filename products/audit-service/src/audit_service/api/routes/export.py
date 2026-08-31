"""Bounded CSV export endpoint (SPEC-046 R-2).

Streams the filtered trail newest-first into RFC-4180 CSV with a fixed
column set. The row count is hard-capped by ``AUDIT_EXPORT_MAX_ROWS``;
rows are collected page-by-page up front (200-row store pages) so the
``X-Audit-Export-*`` headers are decided before the first byte streams —
consumers can always tell a complete export from a truncated one. The
read is recorded as a structured stdout log line — never self-ingested —
matching the query/summary posture.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from audit_service.core.config import get_settings
from audit_service.core.metrics import record_export, record_rejected
from audit_service.core.observability import log_event
from audit_service.schemas.audit import AuditEvent, AuditQuery
from audit_service.services.ingest_auth import (
    IngestAuthError,
    authenticate_caller,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter()

# Store pages are read 200 at a time (the query route's max limit), so a
# capped export never materializes more than the cap itself.
EXPORT_PAGE_SIZE = 200

# Fixed column set: the envelope columns plus the verbatim ``details``
# payload rendered as sorted-key JSON. Any column change is a contract
# change — consumers key off this order.
CSV_COLUMNS = (
    "occurred_at",
    "event_type",
    "service",
    "outcome",
    "username",
    "actor",
    "subject",
    "session_id",
    "request_id",
    "details",
)


def _format_timestamp(occurred_at: datetime) -> str:
    """RFC-3339 UTC with a ``Z`` suffix."""
    return occurred_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _csv_line(values: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(values)
    return buffer.getvalue()


def _event_row(event: AuditEvent) -> str:
    return _csv_line(
        [
            _format_timestamp(event.occurred_at),
            event.event_type,
            event.service,
            event.outcome,
            event.username or "",
            event.actor or "",
            event.subject or "",
            event.session_id or "",
            event.request_id,
            json.dumps(event.details, sort_keys=True, separators=(",", ":")),
        ]
    )


@router.get("/api/v1/audit/export")
async def export_events(
    request: Request,
    username: str | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    event_type: str | None = None,
    service: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Response:
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
    cap = settings.export_max_rows

    # Page through the trail until it ends or the cap is reached. The
    # truncation flag is decided here — headers must be final before the
    # body streams, and a non-null ``next_cursor`` always means more rows
    # match (both store backends only set it on overflow).
    events: list[AuditEvent] = []
    cursor: str | None = None
    truncated = False
    while len(events) < cap:
        page = await store.query(
            filters, cursor, min(EXPORT_PAGE_SIZE, cap - len(events))
        )
        events.extend(page.events)
        if page.next_cursor is None:
            break
        if len(events) >= cap:
            truncated = True
            break
        cursor = page.next_cursor

    record_export()
    log_event(
        LOGGER,
        "audit_export_generated",
        client=client_id,
        rows=len(events),
        truncated=truncated,
    )

    def stream() -> AsyncIterator[str]:
        yield _csv_line(list(CSV_COLUMNS))
        for event in events:
            yield _event_row(event)

    generated_at = datetime.now(timezone.utc)
    filename = f"audit-export-{generated_at:%Y%m%dT%H%M%SZ}.csv"
    return StreamingResponse(
        stream(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Audit-Export-Truncated": "true" if truncated else "false",
            "X-Audit-Export-Rows": str(len(events)),
        },
    )
