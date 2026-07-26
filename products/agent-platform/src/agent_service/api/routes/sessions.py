from fastapi import APIRouter, Header

from agent_service.core.request_context import resolve_request_id
from agent_service.schemas.api import CreateSessionRequest, SessionRecord
from agent_service.services.session_service import create_session, get_session

router = APIRouter()


@router.post("/api/v1/sessions", response_model=SessionRecord)
def create_session_route(
    payload: CreateSessionRequest,
    x_request_id: str | None = Header(default=None),
) -> SessionRecord:
    _ = resolve_request_id(x_request_id)
    return create_session(payload.user_id)


@router.get("/api/v1/sessions/{session_id}", response_model=SessionRecord)
def get_session_route(session_id: str) -> SessionRecord:
    return get_session(session_id)
