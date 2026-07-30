import asyncio
import json
import logging
from collections import OrderedDict
from collections.abc import AsyncIterator

from agent_service.providers import get_provider
from agent_service.runtime_settings import RuntimeSettings

LOGGER = logging.getLogger(__name__)
MAX_CACHED_AGENTS = 1000
TEXT_DELTA_EVENTS = {
    "message_delta",
    "text_block_start",
    "text_block_delta",
    "thinking_block_start",
    "thinking_block_delta",
}


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


def extract_stream_text(value: object) -> str:
    normalized = make_serializable(value)
    if normalized is None:
        return ""
    if isinstance(normalized, str):
        return normalized
    if isinstance(normalized, list):
        parts = [extract_stream_text(item) for item in normalized]
        return " ".join(part for part in parts if part).strip()
    if isinstance(normalized, dict):
        for key in ("text", "delta", "message", "content"):
            if key in normalized:
                text = extract_stream_text(normalized[key])
                if text:
                    return text
        return ""
    return ""


class AgentKernel:
    def __init__(
        self,
        settings: RuntimeSettings | None = None,
        max_cached_agents: int = MAX_CACHED_AGENTS,
    ) -> None:
        self.settings = settings or RuntimeSettings.from_env()
        self._provider = get_provider(self.settings.provider)
        self._agents: OrderedDict[str, tuple[object, type]] = OrderedDict()
        self._max_cached_agents = max_cached_agents
        self._last_error: str | None = None
        self._toolkit = None  # Lazily built Toolkit (shared across agents)
        self._toolkit_lock = asyncio.Lock()
        self._agent_lock = asyncio.Lock()

    def mode(self) -> str:
        return "agentscope" if self.is_configured() else "placeholder"

    def is_configured(self) -> bool:
        return self.settings.is_configured()

    def runtime_state(self) -> str:
        if not self.is_configured():
            return "not_configured"
        if self._last_error:
            return "provider_error"
        return "ready"

    def provider_name(self) -> str:
        return self._provider.provider_name

    def provider_description(self) -> str:
        return self._provider.describe(self.settings)

    def last_error(self) -> str | None:
        return self._last_error

    def runtime_metadata(self) -> dict[str, object]:
        return {
            "runtime_mode": self.mode(),
            "runtime_state": self.runtime_state(),
            "agentscope_enabled": self.is_configured(),
            "profile": self.settings.profile,
            "provider": self.provider_name(),
            "provider_description": self.provider_description(),
            "model_name": self._provider.resolved_model_name(self.settings),
            "base_url": self._provider.resolved_base_url(self.settings),
            "provider_options": make_serializable(self.settings.provider_options),
            "hint": self.configuration_hint(),
            "last_error": self.last_error(),
        }

    def configuration_hint(self) -> str:
        if not self.is_configured():
            return (
                "AgentScope runtime is not configured. "
                "Set AGENTSCOPE_API_KEY to enable the runtime kernel."
            )
        if self._last_error:
            return (
                "AgentScope runtime is configured through the "
                f"{self.provider_name()} provider, but the last provider call failed: "
                f"{self._last_error}"
            )
        return f"AgentScope runtime ready through {self.provider_description()}."

    def remember_error(self, exc: Exception) -> None:
        self._last_error = str(exc)

    def clear_error(self) -> None:
        self._last_error = None

    def _build_model(self):
        return self._provider.build_model(self.settings)

    async def _ensure_toolkit(self):
        """Build (once) and return the Toolkit with gateway tools."""
        if self._toolkit is not None:
            return self._toolkit

        from agentscope.tool import Toolkit

        async with self._toolkit_lock:
            # Re-check: a concurrent caller may have built it while we waited.
            if self._toolkit is not None:
                return self._toolkit

            if self.settings.tool_gateway_url:
                from agent_service.tools.gateway_tools import build_toolkit

                try:
                    self._toolkit = await build_toolkit(self.settings.tool_gateway_url)
                    return self._toolkit
                except Exception as exc:
                    LOGGER.warning("failed to build gateway toolkit: %s", exc)

            self._toolkit = Toolkit()
            return self._toolkit

    async def _build_agent(self):
        from agentscope.agent import Agent
        from agentscope.message import UserMsg

        toolkit = await self._ensure_toolkit()
        agent = Agent(
            name=self.settings.agent_name,
            system_prompt=self.settings.system_prompt,
            model=self._build_model(),
            toolkit=toolkit,
        )
        return agent, UserMsg

    async def ensure_agent(self, session_id: str):
        """Return the agent bound to `session_id`, creating it on first use.

        Agents are keyed by session so conversation memory never crosses
        sessions; the cache is LRU-bounded to match the session store.
        Creation is serialised because it awaits: without the lock two
        concurrent turns on the same session would each build an agent and
        one would be discarded along with its memory.
        """
        cached = self._agents.get(session_id)
        if cached is not None:
            self._agents.move_to_end(session_id)
            return cached
        async with self._agent_lock:
            cached = self._agents.get(session_id)
            if cached is not None:
                self._agents.move_to_end(session_id)
                return cached
            agent, user_msg_cls = await self._build_agent()
            self._agents[session_id] = (agent, user_msg_cls)
            while len(self._agents) > self._max_cached_agents:
                self._agents.popitem(last=False)
            return agent, user_msg_cls

    def build_unconfigured_message(self, message: str, session_id: str) -> str:
        return (
            "Platform baseline placeholder response. "
            f"AgentScope runtime not configured for session {session_id}. "
            f"Received '{message}'."
        )

    def build_provider_error_message(self, message: str, session_id: str) -> str:
        detail = self._last_error or "Unknown provider error."
        return (
            "Platform runtime fallback response. "
            f"AgentScope provider {self.provider_name()} failed for session {session_id}. "
            f"Received '{message}'. Last error: {detail}"
        )

    async def fallback_stream(
        self,
        request_id: str,
        session_id: str,
        delta: str,
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
            "delta": delta,
        }
        yield {
            "event": "message_end",
            "request_id": request_id,
            "session_id": session_id,
            "message": "complete",
        }

    async def reply_text(self, message: str, session_id: str, user_name: str) -> str:
        if not self.is_configured():
            return self.build_unconfigured_message(message, session_id)

        try:
            agent, user_msg_cls = await self.ensure_agent(session_id)
            reply_msg = await agent.reply(user_msg_cls(name=user_name, content=message))
            self.clear_error()
            return extract_text(getattr(reply_msg, "content", reply_msg))
        except Exception as exc:  # pragma: no cover - defensive fallback
            self.remember_error(exc)
            LOGGER.exception("AgentScope reply failed; falling back to runtime error response: %s", exc)
            return self.build_provider_error_message(message, session_id)

    def normalize_event(
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

        text = extract_stream_text(payload)
        if event_type in TEXT_DELTA_EVENTS and text:
            data["delta"] = text
        return data

    async def stream_events(
        self,
        message: str,
        request_id: str,
        session_id: str,
        user_name: str,
    ) -> AsyncIterator[dict[str, object]]:
        if not self.is_configured():
            async for event in self.fallback_stream(
                request_id=request_id,
                session_id=session_id,
                delta=self.build_unconfigured_message(message, session_id),
            ):
                yield event
            return

        try:
            agent, user_msg_cls = await self.ensure_agent(session_id)
            async for event in agent.reply_stream(user_msg_cls(name=user_name, content=message)):
                self.clear_error()
                yield self.normalize_event(event, request_id, session_id)
        except Exception as exc:  # pragma: no cover - defensive fallback
            self.remember_error(exc)
            LOGGER.exception("AgentScope streaming failed; falling back to runtime error response: %s", exc)
            async for event in self.fallback_stream(
                request_id=request_id,
                session_id=session_id,
                delta=self.build_provider_error_message(message, session_id),
            ):
                yield event
