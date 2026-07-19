import json
from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


class SessionRecord(BaseModel):
    session_id: str
    user_id: str | None = None
    created_at: datetime
    status: str = "active"


class CreateSessionRequest(BaseModel):
    user_id: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None
    user_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    request_id: str
    response: str
    status: str = "ok"


app = FastAPI(title="agent-service", version="0.1.0")
SESSIONS: dict[str, SessionRecord] = {}


def resolve_request_id(request_id: str | None) -> str:
    return request_id or f"req-{uuid4()}"


def ensure_session(session_id: str | None, user_id: str | None) -> SessionRecord:
    if session_id and session_id in SESSIONS:
        return SESSIONS[session_id]
    record = SessionRecord(
        session_id=session_id or f"ses-{uuid4()}",
        user_id=user_id,
        created_at=datetime.now(timezone.utc),
    )
    SESSIONS[record.session_id] = record
    return record


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok", "service": "agent-service", "version": "0.1.0"}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    return {"status": "ok", "service": "agent-service", "version": "0.1.0"}


@app.post("/api/v1/sessions", response_model=SessionRecord)
def create_session(
    payload: CreateSessionRequest,
    x_request_id: str | None = Header(default=None),
) -> SessionRecord:
    _ = resolve_request_id(x_request_id)
    return ensure_session(None, payload.user_id)


@app.get("/api/v1/sessions/{session_id}", response_model=SessionRecord)
def get_session(session_id: str) -> SessionRecord:
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="session not found")
    return SESSIONS[session_id]


@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    x_request_id: str | None = Header(default=None),
) -> ChatResponse:
    request_id = resolve_request_id(x_request_id)
    session = ensure_session(payload.session_id, payload.user_id)
    response = (
        "Release 0 placeholder response. "
        f"Received '{payload.message}' for session {session.session_id}."
    )
    return ChatResponse(
        session_id=session.session_id,
        request_id=request_id,
        response=response,
    )


@app.get("/api/v1/chat/stream")
def chat_stream(
    message: str,
    session_id: str | None = None,
    user_id: str | None = None,
    x_request_id: str | None = Header(default=None),
) -> StreamingResponse:
    request_id = resolve_request_id(x_request_id)
    session = ensure_session(session_id, user_id)
    chunks = [
        {"event": "message_start", "request_id": request_id, "session_id": session.session_id},
        {
            "event": "message_delta",
            "request_id": request_id,
            "session_id": session.session_id,
            "delta": "Release 0 placeholder response streaming from agent-service. ",
        },
        {
            "event": "message_delta",
            "request_id": request_id,
            "session_id": session.session_id,
            "delta": f"Received '{message}'.",
        },
        {
            "event": "message_end",
            "request_id": request_id,
            "session_id": session.session_id,
            "message": "complete",
        },
    ]

    def event_stream() -> Iterator[str]:
        for chunk in chunks:
            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
