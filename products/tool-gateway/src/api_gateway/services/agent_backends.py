from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

import httpx
from fastapi import HTTPException

ConfiguredAgentBackendMode = Literal["auto", "transitional", "native"]
ResolvedAgentBackendMode = Literal["transitional", "native"]
NATIVE_PROBE_USER_ID = "gateway.runtime-probe"
NATIVE_PROBE_REQUEST_ID = "req-native-runtime-probe"


def build_service_headers(
    request_id: str,
    user_id: str | None = None,
) -> dict[str, str]:
    headers = {"x-request-id": request_id}
    if user_id:
        headers["X-User-ID"] = user_id
    return headers


def sse_frame(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def build_native_probe_headers() -> dict[str, str]:
    return build_service_headers(NATIVE_PROBE_REQUEST_ID, NATIVE_PROBE_USER_ID)


@dataclass(frozen=True)
class AgentBackendContext:
    agent_service_url: str
    default_agent_name: str
    default_agent_system_prompt: str
    chat_response_timeout_seconds: float


@dataclass(frozen=True)
class AgentBackendResolution:
    configured_mode: ConfiguredAgentBackendMode
    resolved_mode: ResolvedAgentBackendMode
    reason: str
    backend: "AgentServiceBackend"


class AgentServiceBackend(ABC):
    mode: ResolvedAgentBackendMode

    @abstractmethod
    async def create_session(
        self,
        client: httpx.AsyncClient,
        request_id: str,
        user_id: str,
        payload: dict,
    ) -> dict:
        """Create a session through the selected backend."""

    @abstractmethod
    async def get_session(
        self,
        client: httpx.AsyncClient,
        request_id: str,
        session_id: str,
        user_id: str,
    ) -> dict:
        """Fetch session state through the selected backend."""

    @abstractmethod
    async def chat(
        self,
        client: httpx.AsyncClient,
        request_id: str,
        user_id: str,
        payload: dict,
    ) -> dict:
        """Send a chat request through the selected backend."""

    @abstractmethod
    def stream_chat(
        self,
        client: httpx.AsyncClient,
        request_id: str,
        user_id: str,
        message: str,
        session_id: str | None,
    ) -> AsyncIterator[bytes | str]:
        """Stream a chat request through the selected backend."""

    @abstractmethod
    async def runtime_metadata(self, client: httpx.AsyncClient) -> dict[str, object]:
        """Return backend runtime metadata when available."""


class TransitionalAgentServiceBackend(AgentServiceBackend):
    mode: ResolvedAgentBackendMode = "transitional"

    def __init__(self, context: AgentBackendContext) -> None:
        self.context = context

    @staticmethod
    def _with_user_id(payload: dict, user_id: str) -> dict:
        forwarded_payload = dict(payload)
        if user_id and not forwarded_payload.get("user_id"):
            forwarded_payload["user_id"] = user_id
        return forwarded_payload

    async def create_session(
        self,
        client: httpx.AsyncClient,
        request_id: str,
        user_id: str,
        payload: dict,
    ) -> dict:
        response = await client.post(
            f"{self.context.agent_service_url}/api/v1/sessions",
            json=self._with_user_id(payload, user_id),
            headers=build_service_headers(request_id, user_id),
        )
        response.raise_for_status()
        return response.json()

    async def get_session(
        self,
        client: httpx.AsyncClient,
        request_id: str,
        session_id: str,
        user_id: str,
    ) -> dict:
        response = await client.get(
            f"{self.context.agent_service_url}/api/v1/sessions/{session_id}",
            headers=build_service_headers(request_id),
        )
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="session not found")
        response.raise_for_status()
        return response.json()

    async def chat(
        self,
        client: httpx.AsyncClient,
        request_id: str,
        user_id: str,
        payload: dict,
    ) -> dict:
        response = await client.post(
            f"{self.context.agent_service_url}/api/v1/chat",
            json=self._with_user_id(payload, user_id),
            headers=build_service_headers(request_id, user_id),
        )
        response.raise_for_status()
        return response.json()

    async def runtime_metadata(self, client: httpx.AsyncClient) -> dict[str, object]:
        response = await client.get(f"{self.context.agent_service_url}/api/v1/runtime")
        response.raise_for_status()
        payload = response.json()
        payload.setdefault("resolved_backend_mode", self.mode)
        return payload

    async def _stream_transitional(
        self,
        client: httpx.AsyncClient,
        request_id: str,
        user_id: str,
        message: str,
        session_id: str | None,
    ) -> AsyncIterator[bytes]:
        params = {"message": message}
        if session_id:
            params["session_id"] = session_id
        if user_id:
            params["user_id"] = user_id

        async with client.stream(
            "GET",
            f"{self.context.agent_service_url}/api/v1/chat/stream",
            params=params,
            headers=build_service_headers(request_id),
        ) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                yield chunk

    def stream_chat(
        self,
        client: httpx.AsyncClient,
        request_id: str,
        user_id: str,
        message: str,
        session_id: str | None,
    ) -> AsyncIterator[bytes]:
        return self._stream_transitional(client, request_id, user_id, message, session_id)


class NativeAgentServiceBackend(AgentServiceBackend):
    mode: ResolvedAgentBackendMode = "native"

    def __init__(self, context: AgentBackendContext) -> None:
        self.context = context

    @staticmethod
    def _build_native_chat_input(user_id: str, message: str) -> dict[str, object]:
        return {
            "name": user_id,
            "role": "user",
            "content": [{"type": "text", "text": message}],
        }

    async def ensure_native_agent(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
    ) -> str:
        response = await client.get(f"{self.context.agent_service_url}/agent/", headers=headers)
        response.raise_for_status()
        agents = response.json().get("agents", [])
        for agent in agents:
            data = agent.get("data", {})
            if data.get("name") == self.context.default_agent_name:
                agent_id = agent.get("id")
                if agent_id:
                    return agent_id

        response = await client.post(
            f"{self.context.agent_service_url}/agent/",
            json={
                "name": self.context.default_agent_name,
                "system_prompt": self.context.default_agent_system_prompt,
            },
            headers=headers,
        )
        response.raise_for_status()
        return response.json()["agent_id"]

    async def ensure_native_session(
        self,
        client: httpx.AsyncClient,
        request_id: str,
        user_id: str,
        requested_session_id: str | None = None,
    ) -> tuple[str, str]:
        headers = build_service_headers(request_id, user_id)
        agent_id = await self.ensure_native_agent(client, headers)
        if requested_session_id:
            return requested_session_id, agent_id

        response = await client.post(
            f"{self.context.agent_service_url}/sessions/",
            json={"agent_id": agent_id, "name": f"Luban AIOps session for {user_id}"},
            headers=headers,
        )
        response.raise_for_status()
        return response.json()["session_id"], agent_id

    async def translate_native_sse(
        self,
        client: httpx.AsyncClient,
        request_id: str,
        user_id: str,
        session_id: str,
        agent_id: str,
    ) -> AsyncIterator[str]:
        headers = build_service_headers(request_id, user_id)
        current_reply_id: str | None = None

        async with client.stream(
            "GET",
            f"{self.context.agent_service_url}/sessions/{session_id}/stream",
            params={"agent_id": agent_id},
            headers=headers,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = json.loads(line[6:])
                event_type = payload.get("type")
                reply_id = payload.get("reply_id")

                if event_type == "REPLY_START":
                    current_reply_id = reply_id
                    yield sse_frame(
                        {
                            "event": "message_start",
                            "request_id": request_id,
                            "session_id": session_id,
                        }
                    )
                    continue

                if current_reply_id and reply_id and reply_id != current_reply_id:
                    continue

                if event_type == "TEXT_BLOCK_DELTA":
                    yield sse_frame(
                        {
                            "event": "message_delta",
                            "request_id": request_id,
                            "session_id": session_id,
                            "delta": payload.get("delta", ""),
                        }
                    )
                    continue

                if event_type == "REPLY_END" and current_reply_id is not None:
                    yield sse_frame(
                        {
                            "event": "message_end",
                            "request_id": request_id,
                            "session_id": session_id,
                            "message": payload.get("finished_reason", "completed"),
                        }
                    )
                    break

    async def collect_native_chat_response(
        self,
        client: httpx.AsyncClient,
        request_id: str,
        user_id: str,
        session_id: str,
        agent_id: str,
    ) -> str:
        chunks: list[str] = []

        async def consume() -> None:
            async for frame in self.translate_native_sse(
                client=client,
                request_id=request_id,
                user_id=user_id,
                session_id=session_id,
                agent_id=agent_id,
            ):
                payload = json.loads(frame[6:].strip())
                if payload.get("delta"):
                    chunks.append(payload["delta"])
                if payload.get("event") == "message_end":
                    return

        await asyncio.wait_for(
            consume(),
            timeout=self.context.chat_response_timeout_seconds,
        )
        return "".join(chunks).strip()

    async def create_session(
        self,
        client: httpx.AsyncClient,
        request_id: str,
        user_id: str,
        payload: dict,
    ) -> dict:
        session_id, _agent_id = await self.ensure_native_session(
            client=client,
            request_id=request_id,
            user_id=user_id,
        )
        return {"session_id": session_id}

    async def get_session(
        self,
        client: httpx.AsyncClient,
        request_id: str,
        session_id: str,
        user_id: str,
    ) -> dict:
        _session_id, agent_id = await self.ensure_native_session(
            client=client,
            request_id=request_id,
            user_id=user_id,
            requested_session_id=session_id,
        )
        response = await client.get(
            f"{self.context.agent_service_url}/sessions/{session_id}/status",
            params={"agent_id": agent_id},
            headers=build_service_headers(request_id, user_id),
        )
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="session not found")
        response.raise_for_status()
        status_payload = response.json()
        return {"session_id": session_id, "status": status_payload.get("status", "unknown")}

    async def chat(
        self,
        client: httpx.AsyncClient,
        request_id: str,
        user_id: str,
        payload: dict,
    ) -> dict:
        session_id, agent_id = await self.ensure_native_session(
            client=client,
            request_id=request_id,
            user_id=user_id,
            requested_session_id=payload.get("session_id"),
        )
        response = await client.post(
            f"{self.context.agent_service_url}/chat/",
            json={
                "agent_id": agent_id,
                "session_id": session_id,
                "input": self._build_native_chat_input(user_id, payload["message"]),
            },
            headers=build_service_headers(request_id, user_id),
        )
        response.raise_for_status()
        text_response = await self.collect_native_chat_response(
            client=client,
            request_id=request_id,
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
        )
        return {
            "session_id": session_id,
            "request_id": request_id,
            "response": text_response,
            "status": "ok",
        }

    async def runtime_metadata(self, client: httpx.AsyncClient) -> dict[str, object]:
        response = await client.get(
            f"{self.context.agent_service_url}/agent/",
            headers=build_native_probe_headers(),
        )
        response.raise_for_status()
        payload = response.json()
        return {
            "runtime_mode": "agentscope-native",
            "runtime_state": "ready",
            "agentscope_enabled": True,
            "resolved_backend_mode": self.mode,
            "agent_count": len(payload.get("agents", [])),
            "hint": "Gateway resolved the agent service as AgentScope native mode.",
        }

    async def _stream_native(
        self,
        client: httpx.AsyncClient,
        request_id: str,
        user_id: str,
        message: str,
        session_id: str | None,
    ) -> AsyncIterator[str]:
        active_session_id, agent_id = await self.ensure_native_session(
            client=client,
            request_id=request_id,
            user_id=user_id,
            requested_session_id=session_id,
        )
        response = await client.post(
            f"{self.context.agent_service_url}/chat/",
            json={
                "agent_id": agent_id,
                "session_id": active_session_id,
                "input": self._build_native_chat_input(user_id, message),
            },
            headers=build_service_headers(request_id, user_id),
        )
        response.raise_for_status()
        async for frame in self.translate_native_sse(
            client=client,
            request_id=request_id,
            user_id=user_id,
            session_id=active_session_id,
            agent_id=agent_id,
        ):
            yield frame

    def stream_chat(
        self,
        client: httpx.AsyncClient,
        request_id: str,
        user_id: str,
        message: str,
        session_id: str | None,
    ) -> AsyncIterator[str]:
        return self._stream_native(client, request_id, user_id, message, session_id)


async def resolve_agent_backend(
    client: httpx.AsyncClient,
    context: AgentBackendContext,
    configured_mode: ConfiguredAgentBackendMode,
) -> AgentBackendResolution:
    transitional_backend = TransitionalAgentServiceBackend(context)
    native_backend = NativeAgentServiceBackend(context)

    if configured_mode == "transitional":
        return AgentBackendResolution(
            configured_mode=configured_mode,
            resolved_mode="transitional",
            reason="Configured explicitly for transitional mode.",
            backend=transitional_backend,
        )

    if configured_mode == "native":
        return AgentBackendResolution(
            configured_mode=configured_mode,
            resolved_mode="native",
            reason="Configured explicitly for native mode.",
            backend=native_backend,
        )

    transitional_runtime_url = f"{context.agent_service_url}/api/v1/runtime"
    try:
        response = await client.get(transitional_runtime_url)
        if response.is_success:
            return AgentBackendResolution(
                configured_mode=configured_mode,
                resolved_mode="transitional",
                reason="Detected transitional runtime metadata endpoint.",
                backend=transitional_backend,
            )
    except httpx.HTTPError:
        pass

    native_agent_url = f"{context.agent_service_url}/agent/"
    try:
        response = await client.get(
            native_agent_url,
            headers=build_native_probe_headers(),
        )
        if response.is_success:
            return AgentBackendResolution(
                configured_mode=configured_mode,
                resolved_mode="native",
                reason="Detected native AgentScope agent endpoint.",
                backend=native_backend,
            )
    except httpx.HTTPError:
        pass

    raise HTTPException(
        status_code=503,
        detail=(
            "Unable to resolve the agent-service backend mode. "
            "Neither the transitional runtime endpoint nor the native AgentScope "
            "agent endpoint responded successfully."
        ),
    )
