import logging

from fastapi import APIRouter, Header

from agent_service.core.observability import log_event
from agent_service.core.request_context import resolve_request_id
from agent_service.schemas.api import CreateSessionRequest, SessionRecord
from agent_service.services.session_service import create_session, get_session

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.post("/api/v1/sessions", response_model=SessionRecord)
def create_session_route(
    payload: CreateSessionRequest,
    x_request_id: str | None = Header(default=None),
) -> SessionRecord:
    request_id = resolve_request_id(x_request_id)
    session = create_session(payload.user_id)
    log_event(
        LOGGER,
        "session_created",
        request_id=request_id,
        session_id=session.session_id,
        user_id=session.user_id or "user",
    )
    return session


@router.get("/api/v1/sessions/{session_id}", response_model=SessionRecord)
def get_session_route(
    session_id: str,
    x_request_id: str | None = Header(default=None),
) -> SessionRecord:
    request_id = resolve_request_id(x_request_id)
    session = get_session(session_id)
    log_event(
        LOGGER,
        "session_retrieved",
        request_id=request_id,
        session_id=session.session_id,
        user_id=session.user_id or "user",
    )
    return session
