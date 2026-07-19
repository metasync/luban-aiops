import json
import logging
from collections.abc import AsyncIterator

from agent_service.runtime_settings import RuntimeSettings

LOGGER = logging.getLogger(__name__)


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
    def __init__(self, settings: RuntimeSettings | None = None) -> None:
        self.settings = settings or RuntimeSettings.from_env()
        self._agent = None
        self._user_msg_cls = None

    def mode(self) -> str:
        return "agentscope" if self.is_configured() else "placeholder"

    def is_configured(self) -> bool:
        return self.settings.is_configured()

    def configuration_hint(self) -> str:
        if self.is_configured():
            return "AgentScope runtime enabled through DashScope credentials."
        return (
            "AgentScope runtime is not configured. "
            "Set DASHSCOPE_API_KEY to enable the runtime kernel."
        )

    def _build_agent(self):
        from agentscope.agent import Agent
        from agentscope.credential import DashScopeCredential
        from agentscope.message import UserMsg
        from agentscope.model import DashScopeChatModel
        from agentscope.tool import Toolkit

        model = DashScopeChatModel(
            credential=DashScopeCredential(api_key=self.settings.dashscope_api_key),
            model=self.settings.model_name,
        )
        agent = Agent(
            name=self.settings.agent_name,
            system_prompt=self.settings.system_prompt,
            model=model,
            toolkit=Toolkit(),
        )
        return agent, UserMsg

    def ensure_agent(self):
        if self._agent is None or self._user_msg_cls is None:
            self._agent, self._user_msg_cls = self._build_agent()
        return self._agent, self._user_msg_cls

    def build_placeholder_message(self, message: str, session_id: str) -> str:
        return (
            "Release 0 placeholder response. "
            f"AgentScope runtime not configured for session {session_id}. "
            f"Received '{message}'."
        )

    async def placeholder_stream(
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
            "delta": self.build_placeholder_message(message, session_id),
        }
        yield {
            "event": "message_end",
            "request_id": request_id,
            "session_id": session_id,
            "message": "complete",
        }

    async def reply_text(self, message: str, session_id: str, user_name: str) -> str:
        if not self.is_configured():
            return self.build_placeholder_message(message, session_id)

        try:
            agent, user_msg_cls = self.ensure_agent()
            reply_msg = await agent.reply(user_msg_cls(name=user_name, content=message))
            return extract_text(getattr(reply_msg, "content", reply_msg))
        except Exception as exc:  # pragma: no cover - defensive fallback
            LOGGER.exception("AgentScope reply failed; falling back to placeholder mode: %s", exc)
            return self.build_placeholder_message(message, session_id)

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

        text = extract_text(payload)
        if text:
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
            async for event in self.placeholder_stream(message, request_id, session_id):
                yield event
            return

        try:
            agent, user_msg_cls = self.ensure_agent()
            async for event in agent.reply_stream(user_msg_cls(name=user_name, content=message)):
                yield self.normalize_event(event, request_id, session_id)
        except Exception as exc:  # pragma: no cover - defensive fallback
            LOGGER.exception("AgentScope streaming failed; falling back to placeholder mode: %s", exc)
            async for event in self.placeholder_stream(message, request_id, session_id):
                yield event
