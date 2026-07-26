from __future__ import annotations

import json
from collections.abc import AsyncIterator

from agent_service.metadata import SERVICE_NAME, SERVICE_VERSION
from agent_service.schemas.api import ChatResponse
from agent_service.services.runtime_dependencies import get_runtime_kernel
from agent_service.services.session_service import ensure_session


def live_status() -> dict[str, str | bool]:
    kernel = get_runtime_kernel()
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "agentscope_enabled": kernel.is_configured(),
    }


def ready_status() -> dict[str, str | bool | None]:
    kernel = get_runtime_kernel()
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "runtime_mode": kernel.mode(),
        "runtime_state": kernel.runtime_state(),
        "agentscope_enabled": kernel.is_configured(),
        "provider": kernel.provider_name(),
    }


def runtime_metadata() -> dict[str, object]:
    return get_runtime_kernel().runtime_metadata()


async def chat(
    message: str,
    session_id: str | None,
    user_id: str | None,
    request_id: str,
) -> ChatResponse:
    session = ensure_session(session_id, user_id)
    response = await get_runtime_kernel().reply_text(
        message=message,
        session_id=session.session_id,
        user_name=user_id or "user",
    )
    return ChatResponse(
        session_id=session.session_id,
        request_id=request_id,
        response=response,
    )


async def stream_chat(
    message: str,
    session_id: str | None,
    user_id: str | None,
    request_id: str,
) -> AsyncIterator[str]:
    session = ensure_session(session_id, user_id)
    async for chunk in get_runtime_kernel().stream_events(
        message=message,
        request_id=request_id,
        session_id=session.session_id,
        user_name=user_id or "user",
    ):
        yield f"data: {json.dumps(chunk, default=str)}\n\n"
