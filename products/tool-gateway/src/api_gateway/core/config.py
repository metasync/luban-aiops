from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from api_gateway.services.agent_backends import (
    AgentBackendContext,
    ConfiguredAgentBackendMode,
)

DEFAULT_AGENT_SERVICE_HOST = "agent-service"
DEFAULT_AGENT_SERVICE_PORT = 8000
DEFAULT_IDENTITY_SERVICE_HOST = "identity-service"
DEFAULT_IDENTITY_SERVICE_PORT = 8000
DEFAULT_AGENT_SERVICE_URL = (
    f"http://{DEFAULT_AGENT_SERVICE_HOST}:{DEFAULT_AGENT_SERVICE_PORT}"
)
DEFAULT_IDENTITY_SERVICE_URL = (
    f"http://{DEFAULT_IDENTITY_SERVICE_HOST}:{DEFAULT_IDENTITY_SERVICE_PORT}"
)


@dataclass(frozen=True)
class GatewaySettings:
    agent_service_url: str = DEFAULT_AGENT_SERVICE_URL
    identity_service_url: str = DEFAULT_IDENTITY_SERVICE_URL
    agent_backend_mode: str = "auto"
    default_agent_name: str = "Luban AIOps Runtime Agent"
    default_agent_system_prompt: str = (
        "You are the Luban AIOps runtime agent. "
        "Answer clearly, stay grounded, and favor operationally useful responses."
    )
    default_user_id: str = "demo.operator"
    chat_response_timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "GatewaySettings":
        return cls(
            agent_service_url=os.getenv(
                "AGENT_SERVICE_URL",
                DEFAULT_AGENT_SERVICE_URL,
            ),
            identity_service_url=os.getenv(
                "IDENTITY_SERVICE_URL",
                DEFAULT_IDENTITY_SERVICE_URL,
            ),
            agent_backend_mode=os.getenv("AGENT_BACKEND_MODE", "auto").strip().lower(),
            default_agent_name=os.getenv(
                "AGENTSCOPE_DEFAULT_AGENT_NAME",
                "Luban AIOps Runtime Agent",
            ),
            default_agent_system_prompt=os.getenv(
                "AGENTSCOPE_DEFAULT_AGENT_SYSTEM_PROMPT",
                (
                    "You are the Luban AIOps runtime agent. "
                    "Answer clearly, stay grounded, and favor operationally useful responses."
                ),
            ),
            default_user_id=os.getenv("DEFAULT_USER_ID", "demo.operator"),
            chat_response_timeout_seconds=float(
                os.getenv("CHAT_RESPONSE_TIMEOUT_SECONDS", "30")
            ),
        )

    def configured_agent_backend_mode(self) -> ConfiguredAgentBackendMode:
        mode = self.agent_backend_mode.lower()
        if mode in {"agentscope", "agentscope-native", "native"}:
            return "native"
        if mode in {"transitional", "fastapi"}:
            return "transitional"
        if mode == "auto":
            return "auto"
        raise ValueError(
            "Unsupported AGENT_BACKEND_MODE. Expected one of: auto, transitional, native."
        )

    def backend_context(self) -> AgentBackendContext:
        return AgentBackendContext(
            agent_service_url=self.agent_service_url,
            default_agent_name=self.default_agent_name,
            default_agent_system_prompt=self.default_agent_system_prompt,
            chat_response_timeout_seconds=self.chat_response_timeout_seconds,
        )


@lru_cache(maxsize=1)
def get_settings() -> GatewaySettings:
    return GatewaySettings.from_env()
