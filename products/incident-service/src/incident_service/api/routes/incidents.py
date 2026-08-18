"""Manual intake, query API, and triage trigger (SPEC-015 R-2/R-3).

All endpoints require a registered platform-caller credential (Basic
registry or projected workload token). The triage endpoint additionally
carries the operator identity (``X-User-ID``) and the operator's delegated
bearer (``X-Delegated-Token``) relayed by platform-gateway — triage always
runs under a real operator identity, never under service-owned authority.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from incident_service.core.config import IncidentSettings, get_settings
from incident_service.core.metrics import record_intake, set_open_incidents
from incident_service.core.observability import log_event
from incident_service.core.request_context import resolve_request_id
from incident_service.schemas.incident import (
    Incident,
    IncidentSeverity,
    IncidentSource,
    IncidentStatus,
)
from incident_service.services.connectors import dispatch_report
from incident_service.services.incident_store import IncidentStore
from incident_service.services.normalization import MAX_LABELS, MAX_LABEL_LENGTH
from incident_service.services.query_auth import (
    QueryAuthError,
    authenticate_caller,
)
from incident_service.services.triage import run_triage

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

MAX_LIST_LIMIT = 100

_STATUSES = {status.value for status in IncidentStatus}
_SEVERITIES = {severity.value for severity in IncidentSeverity}
_SOURCES = {source.value for source in IncidentSource}


class ManualIncidentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=2000)
    severity: IncidentSeverity = IncidentSeverity.WARNING
    labels: dict[str, str] = Field(default_factory=dict)


def _store(request: Request) -> IncidentStore:
    return request.app.state.incident_store


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def _new_incident_id() -> str:
    return f"inc-{uuid.uuid4().hex[:12]}"


@router.post("/incidents")
async def create_incident(
    request: Request, settings: IncidentSettings = Depends(get_settings)
) -> JSONResponse:
    try:
        caller = await authenticate_caller(settings, request)
    except QueryAuthError as exc:
        return _error(401, "UNAUTHORIZED", str(exc))

    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - any parse failure is a client error
        return _error(400, "INVALID_PAYLOAD", "body must be valid JSON")
    try:
        payload = ManualIncidentRequest.model_validate(body)
    except ValidationError as exc:
        return _error(400, "INVALID_PAYLOAD", f"invalid incident: {exc}")
    if len(payload.labels) > MAX_LABELS:
        return _error(
            400, "INVALID_PAYLOAD", f"labels exceed {MAX_LABELS} entries"
        )
    for key, value in payload.labels.items():
        if len(key) > MAX_LABEL_LENGTH or len(value) > MAX_LABEL_LENGTH:
            return _error(400, "INVALID_PAYLOAD", "label entry too long")

    now = datetime.now(timezone.utc)
    reported_by = (request.headers.get("x-reported-by") or caller).strip()[:200]
    incident = Incident(
        incident_id=_new_incident_id(),
        # Manual reports always create: the uuid suffix makes the
        # fingerprint unique by construction (SPEC-015 plan, R-2).
        fingerprint=f"manual:{uuid.uuid4().hex}",
        source=IncidentSource.MANUAL,
        severity=payload.severity,
        status=IncidentStatus.NEW,
        title=payload.title,
        summary=payload.summary,
        labels=payload.labels,
        reported_by=reported_by,
        created_at=now,
        updated_at=now,
    )
    store = _store(request)
    await store.create(incident)
    record_intake("manual", "created")
    set_open_incidents(await store.count(open_only=True))
    log_event(
        LOGGER,
        "incident_created",
        incident_id=incident.incident_id,
        source="manual",
        reported_by=reported_by,
        severity=incident.severity.value,
    )
    return JSONResponse(status_code=201, content=incident.envelope())


@router.get("/incidents")
async def list_incidents(
    request: Request,
    offset: int = Query(default=0),
    limit: int = Query(default=20),
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    source: str | None = Query(default=None),
    settings: IncidentSettings = Depends(get_settings),
) -> JSONResponse:
    try:
        await authenticate_caller(settings, request)
    except QueryAuthError as exc:
        return _error(401, "UNAUTHORIZED", str(exc))
    if offset < 0 or limit < 1 or limit > MAX_LIST_LIMIT:
        return _error(
            400,
            "INVALID_PARAMETERS",
            f"offset must be >= 0 and limit within 1..{MAX_LIST_LIMIT}",
        )
    if status is not None and status not in _STATUSES:
        return _error(
            400, "INVALID_PARAMETERS", f"status must be one of {sorted(_STATUSES)}"
        )
    if severity is not None and severity not in _SEVERITIES:
        return _error(
            400,
            "INVALID_PARAMETERS",
            f"severity must be one of {sorted(_SEVERITIES)}",
        )
    if source is not None and source not in _SOURCES:
        return _error(
            400, "INVALID_PARAMETERS", f"source must be one of {sorted(_SOURCES)}"
        )
    store = _store(request)
    incidents, total = await store.list(
        offset, limit, status=status, severity=severity, source=source
    )
    return JSONResponse(
        content={
            "incidents": [incident.list_entry() for incident in incidents],
            "total": total,
            "offset": offset,
            "limit": limit,
        }
    )


@router.get("/incidents/{incident_id}")
async def get_incident(
    incident_id: str,
    request: Request,
    settings: IncidentSettings = Depends(get_settings),
) -> JSONResponse:
    try:
        await authenticate_caller(settings, request)
    except QueryAuthError as exc:
        return _error(401, "UNAUTHORIZED", str(exc))
    store = _store(request)
    incident = await store.get(incident_id)
    if incident is None:
        return _error(
            404, "INCIDENT_NOT_FOUND", f"unknown incident id: {incident_id}"
        )
    report = await store.get_report(incident_id)
    dispatches = await store.get_dispatches(incident_id)
    return JSONResponse(
        content={
            "incident": incident.envelope(),
            "report": report.envelope() if report else None,
            "dispatches": [
                dispatch.model_dump(mode="json", exclude_none=True)
                for dispatch in dispatches
            ],
        }
    )


@router.get("/incidents/{incident_id}/report")
async def get_report(
    incident_id: str,
    request: Request,
    settings: IncidentSettings = Depends(get_settings),
) -> JSONResponse:
    try:
        await authenticate_caller(settings, request)
    except QueryAuthError as exc:
        return _error(401, "UNAUTHORIZED", str(exc))
    store = _store(request)
    incident = await store.get(incident_id)
    if incident is None:
        return _error(
            404, "INCIDENT_NOT_FOUND", f"unknown incident id: {incident_id}"
        )
    report = await store.get_report(incident_id)
    if report is None:
        return _error(
            404,
            "REPORT_NOT_FOUND",
            f"no triage report for incident: {incident_id}",
        )
    return JSONResponse(content=report.envelope())


@router.post("/incidents/{incident_id}/triage")
async def triage_incident(
    incident_id: str,
    request: Request,
    settings: IncidentSettings = Depends(get_settings),
) -> JSONResponse:
    try:
        await authenticate_caller(settings, request)
    except QueryAuthError as exc:
        return _error(401, "UNAUTHORIZED", str(exc))
    operator = request.headers.get("x-user-id", "").strip()
    if not operator:
        return _error(
            400, "INVALID_PARAMETERS", "X-User-ID header is required for triage"
        )
    bearer_token = request.headers.get("x-delegated-token", "").strip()
    if not bearer_token:
        return _error(
            400,
            "INVALID_PARAMETERS",
            "X-Delegated-Token header is required for triage",
        )

    store = _store(request)
    incident = await store.get(incident_id)
    if incident is None:
        return _error(
            404, "INCIDENT_NOT_FOUND", f"unknown incident id: {incident_id}"
        )

    request_id = resolve_request_id(request.headers.get("x-request-id"))
    incident, report = await run_triage(
        settings, store, incident, operator, bearer_token, request_id
    )
    dispatches = []
    if report is not None:
        connectors = request.app.state.connectors
        dispatches = await dispatch_report(store, connectors, incident, report)
    return JSONResponse(
        content={
            "incident": incident.envelope(),
            "report": report.envelope() if report else None,
            "dispatches": [
                dispatch.model_dump(mode="json", exclude_none=True)
                for dispatch in dispatches
            ],
        }
    )
