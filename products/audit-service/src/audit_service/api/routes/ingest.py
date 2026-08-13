"""Ingest endpoint (SPEC-013 R-3).

Accepts batches of audit events from registered platform services. Callers
authenticate with the SPEC-008/009 service-identity credential vocabulary;
malformed batches are rejected wholesale (nothing is partially stored).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from audit_service.core.config import get_settings
from audit_service.core.metrics import (
    record_ingested,
    record_rejected,
    record_store_growth,
)
from audit_service.core.observability import log_event
from audit_service.schemas.audit import IngestRequest
from audit_service.services.ingest_auth import (
    IngestAuthError,
    authenticate_caller,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/v1/audit/events")
async def ingest_events(request: Request) -> JSONResponse:
    settings = get_settings()

    try:
        client_id = await authenticate_caller(settings, request)
    except IngestAuthError as exc:
        record_rejected("auth")
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - any parse failure is a client error
        record_rejected("malformed")
        return JSONResponse(
            status_code=400, content={"detail": "invalid JSON body"}
        )
    try:
        payload = IngestRequest.model_validate(body)
    except Exception as exc:  # noqa: BLE001 - pydantic raises many subclasses
        record_rejected("malformed")
        return JSONResponse(
            status_code=400, content={"detail": f"invalid audit batch: {exc}"}
        )

    if len(payload.events) > settings.max_batch:
        record_rejected("batch_too_large")
        return JSONResponse(
            status_code=400,
            content={
                "detail": f"batch exceeds AUDIT_MAX_BATCH ({settings.max_batch})"
            },
        )

    store = request.app.state.audit_store
    inserted = await store.add(payload.events)
    record_store_growth(inserted)
    for event in payload.events:
        record_ingested(event.service, event.event_type)
    log_event(
        LOGGER,
        "audit_events_ingested",
        client=client_id,
        count=len(payload.events),
        inserted=inserted,
    )
    return JSONResponse(
        status_code=202,
        content={"accepted": len(payload.events), "inserted": inserted},
    )
