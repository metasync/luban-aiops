"""Retrieval API (SPEC-014 R-3).

All endpoints require a registered query credential (Basic registry or
projected workload token); the status endpoint lives in its own router
because it is auth-exempt operational surface. Route order matters:
``search`` is declared before the ``{skill_id:path}`` catch-all.

Search and get emit usage audit events (SPEC-029 R-2); list and auth
failures are deliberately not audited.
"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from skills_hub.core import metrics
from skills_hub.core.config import SkillsSettings, get_settings
from skills_hub.core.request_context import resolve_request_id
from skills_hub.services.audit_emitter import build_audit_event, emit_audit_event
from skills_hub.services.query_auth import QueryAuthError, authenticate_caller
from skills_hub.services.skill_store import SkillStore

router = APIRouter(prefix="/api/v1")

MAX_LIST_LIMIT = 100
MAX_SEARCH_LIMIT = 20


def _store(request: Request) -> SkillStore:
    return request.app.state.skills_store


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def _emit_usage(
    settings: SkillsSettings,
    request: Request,
    event_type: str,
    outcome: str,
    details: dict,
    actor: str,
) -> None:
    # SPEC-029 R-2: correlate on the caller's x-request-id; no user identity.
    emit_audit_event(
        settings,
        build_audit_event(
            event_type,
            resolve_request_id(request.headers.get("x-request-id")),
            outcome,
            details=details,
            actor=actor,
        ),
    )


@router.get("/skills")
async def list_skills(
    request: Request,
    offset: int = Query(default=0),
    limit: int = Query(default=20),
    source: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    settings: SkillsSettings = Depends(get_settings),
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
    store = _store(request)
    skills, total = await store.list(offset, limit, source=source, tag=tag)
    return JSONResponse(
        content={
            "skills": [skill.summary() for skill in skills],
            "total": total,
            "offset": offset,
            "limit": limit,
        }
    )


@router.get("/skills/search")
async def search_skills(
    request: Request,
    q: str = Query(default=""),
    limit: int = Query(default=5),
    source: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    settings: SkillsSettings = Depends(get_settings),
) -> JSONResponse:
    try:
        client_id = await authenticate_caller(settings, request)
    except QueryAuthError as exc:
        return _error(401, "UNAUTHORIZED", str(exc))
    if not q.strip():
        return _error(400, "INVALID_PARAMETERS", "q is required")
    if limit < 1 or limit > MAX_SEARCH_LIMIT:
        return _error(
            400,
            "INVALID_PARAMETERS",
            f"limit must be within 1..{MAX_SEARCH_LIMIT}",
        )
    store = _store(request)
    hits = await store.search(q, limit, source=source, tag=tag)
    metrics.record_search()
    details: dict = {
        "query": q,
        "limit": limit,
        "result_count": len(hits),
        "skill_ids": [hit.skill.skill_id for hit in hits],
    }
    if source:
        details["source"] = source
    if tag:
        details["tag"] = tag
    _emit_usage(settings, request, "skill_searched", "success", details, client_id)
    return JSONResponse(
        content={
            "matches": [
                {
                    **hit.skill.summary(),
                    "score": hit.score,
                    "excerpt": hit.excerpt,
                }
                for hit in hits
            ],
            "total": len(hits),
        }
    )


@router.get("/skills/{skill_id:path}")
async def get_skill(
    skill_id: str,
    request: Request,
    settings: SkillsSettings = Depends(get_settings),
) -> JSONResponse:
    try:
        client_id = await authenticate_caller(settings, request)
    except QueryAuthError as exc:
        return _error(401, "UNAUTHORIZED", str(exc))
    store = _store(request)
    skill = await store.get(skill_id)
    if skill is None:
        _emit_usage(
            settings,
            request,
            "skill_retrieved",
            "error",
            {"skill_id": skill_id, "reason": "not_found"},
            client_id,
        )
        return _error(404, "SKILL_NOT_FOUND", f"unknown skill id: {skill_id}")
    _emit_usage(
        settings,
        request,
        "skill_retrieved",
        "success",
        {"skill_id": skill.skill_id, "source": skill.source_id},
        client_id,
    )
    return JSONResponse(content=skill.model_dump(mode="json", exclude_none=True))
