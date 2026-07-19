import json
import logging
import os
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

LOGGER = logging.getLogger(__name__)


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


def resolve_request_id(request_id: str | None) -> str:
    return request_id or f"req-{uuid4()}"


def make_serializable(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [make_serializable(item) for item in value]
    if isinstance(value, tuple):
        return [make_serializable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): make_serializable(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return make_serializable(value.model_dump())
    if hasattr(value, "__dict__"):
        return make_serializable(
            {
                key: item
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        )
    return str(value)


def extract_text(value: object) -> str:
    normalized = make_serializable(value)
    if normalized is None:
        return ""
    if isinstance(normalized, str):
        return normalized
    if isinstance(normalized, list):
        parts = [extract_text(item) for item in normalized]
        return " ".join(part for part in parts if part).strip()
    if isinstance(normalized, dict):
        for key in ("text", "delta", "message", "content"):
            if key in normalized:
                text = extract_text(normalized[key])
                if text:
                    return text
        return json.dumps(normalized, default=str)
    return str(normalized)


class AgentKernel:
    def __init__(self) -> None:
        self._agent = None
        self._user_msg_cls = None

    def mode(self) -> str:
        return "agentscope" if self.is_configured() else "placeholder"

    def is_configured(self) -> bool:
        return bool(os.getenv("DASHSCOPE_API_KEY"))

    def configuration_hint(self) -> str:
        if self.is_configured():
            return "AgentScope runtime enabled through DashScope credentials."
        return (
            "AgentScope runtime is not configured. "
            "Set DASHSCOPE_API_KEY to enable the runtime kernel."
        )

    def _ensure_agent(self):
        if self._agent is not None and self._user_msg_cls is not None:
            return self._agent, self._user_msg_cls

        from agentscope.agent import Agent
        from agentscope.credential import DashScopeCredential
        from agentscope.message import UserMsg
        from agentscope.model import DashScopeChatModel
        from agentscope.tool import Toolkit

        model = DashScopeChatModel(
            credential=DashScopeCredential(api_key=os.environ["DASHSCOPE_API_KEY"]),
            model=os.getenv("AGENTSCOPE_MODEL_NAME", "qwen-plus"),
        )
        self._agent = Agent(
            name=os.getenv("AGENTSCOPE_AGENT_NAME", "LubanOpsRuntime"),
            system_prompt=os.getenv(
                "AGENTSCOPE_SYSTEM_PROMPT",
                "You are the Release 0 runtime kernel for the Luban AIOps platform. "
                "Answer clearly and concisely, and keep the response grounded in the current platform state.",
            ),
            model=model,
            toolkit=Toolkit(),
        )
        self._user_msg_cls = UserMsg
        return self._agent, self._user_msg_cls

    def _placeholder_reply(self, message: str, session_id: str) -> str:
        return (
            "Release 0 placeholder response. "
            f"AgentScope runtime not configured for session {session_id}. "
            f"Received '{message}'."
        )

    async def _placeholder_stream(
        self,
        message: str,
        request_id: str,
        session_id: str,
    ) -> AsyncIterator[dict[str, object]]:
        yield {
            "event": "message_start",
            "request_id": request_id,
            "session_id": session_id,
        }
        yield {
            "event": "message_delta",
            "request_id": request_id,
            "session_id": session_id,
            "delta": self._placeholder_reply(message, session_id),
        }
        yield {
            "event": "message_end",
            "request_id": request_id,
            "session_id": session_id,
            "message": "complete",
        }

    async def reply(self, message: str, session_id: str, user_name: str) -> str:
        if not self.is_configured():
            return self._placeholder_reply(message, session_id)

        try:
            agent, user_msg_cls = self._ensure_agent()
            reply_msg = await agent.reply(user_msg_cls(name=user_name, content=message))
            return extract_text(getattr(reply_msg, "content", reply_msg))
        except Exception as exc:  # pragma: no cover - defensive fallback
            LOGGER.exception("AgentScope reply failed; falling back to placeholder mode: %s", exc)
            return self._placeholder_reply(message, session_id)

    def _normalize_event(
        self,
        event: object,
        request_id: str,
        session_id: str,
    ) -> dict[str, object]:
        payload = make_serializable(event)
        event_type = "agentscope_event"
        if isinstance(payload, dict) and "type" in payload:
            event_type = str(payload["type"]).lower()
        else:
            raw_type = getattr(event, "type", None)
            if raw_type is not None:
                event_type = str(getattr(raw_type, "name", raw_type)).lower()

        data: dict[str, object] = {
            "event": event_type,
            "request_id": request_id,
            "session_id": session_id,
            "payload": payload,
        }

        text = extract_text(payload)
        if text:
            data["delta"] = text
        return data

    async def stream_reply(
        self,
        message: str,
        request_id: str,
        session_id: str,
        user_name: str,
    ) -> AsyncIterator[dict[str, object]]:
        if not self.is_configured():
            async for event in self._placeholder_stream(message, request_id, session_id):
                yield event
            return

        try:
            agent, user_msg_cls = self._ensure_agent()
            async for event in agent.reply_stream(user_msg_cls(name=user_name, content=message)):
                yield self._normalize_event(event, request_id, session_id)
        except Exception as exc:  # pragma: no cover - defensive fallback
            LOGGER.exception("AgentScope streaming failed; falling back to placeholder mode: %s", exc)
            async for event in self._placeholder_stream(message, request_id, session_id):
                yield event


app = FastAPI(title="agent-service", version="0.1.0")
SESSIONS: dict[str, SessionRecord] = {}
KERNEL = AgentKernel()


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
def live() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "service": "agent-service",
        "version": "0.1.0",
        "agentscope_enabled": KERNEL.is_configured(),
    }


@app.get("/health/ready")
def ready() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "service": "agent-service",
        "version": "0.1.0",
        "runtime_mode": KERNEL.mode(),
        "agentscope_enabled": KERNEL.is_configured(),
    }


@app.get("/api/v1/runtime")
def runtime_metadata() -> dict[str, str | bool]:
    return {
        "runtime_mode": KERNEL.mode(),
        "agentscope_enabled": KERNEL.is_configured(),
        "hint": KERNEL.configuration_hint(),
    }


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
async def chat(
    payload: ChatRequest,
    x_request_id: str | None = Header(default=None),
) -> ChatResponse:
    request_id = resolve_request_id(x_request_id)
    session = ensure_session(payload.session_id, payload.user_id)
    response = await KERNEL.reply(
        message=payload.message,
        session_id=session.session_id,
        user_name=payload.user_id or "user",
    )
    return ChatResponse(
        session_id=session.session_id,
        request_id=request_id,
        response=response,
    )


@app.get("/api/v1/chat/stream")
async def chat_stream(
    message: str,
    session_id: str | None = None,
    user_id: str | None = None,
    x_request_id: str | None = Header(default=None),
) -> StreamingResponse:
    request_id = resolve_request_id(x_request_id)
    session = ensure_session(session_id, user_id)
    async def event_stream() -> AsyncIterator[str]:
        async for chunk in KERNEL.stream_reply(
            message=message,
            request_id=request_id,
            session_id=session.session_id,
            user_name=user_id or "user",
        ):
            yield f"data: {json.dumps(chunk, default=str)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def run() -> None:
    uvicorn.run("agent_service.main:app", host="0.0.0.0", port=8000)
