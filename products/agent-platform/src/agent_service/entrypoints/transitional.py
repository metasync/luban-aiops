from __future__ import annotations

from dataclasses import dataclass

import uvicorn

from agent_service.app import app
from agent_service.core.config import get_settings
from agent_service.core.env import get_env_int, get_env_value
from agent_service.metadata import DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT


@dataclass(frozen=True)
class TransitionalServiceSettings:
    host: str = DEFAULT_HTTP_HOST
    port: int = DEFAULT_HTTP_PORT

    @classmethod
    def from_env(cls) -> "TransitionalServiceSettings":
        return cls(
            host=get_env_value(
                "AGENT_TRANSITIONAL_HOST",
                default=DEFAULT_HTTP_HOST,
            ),
            port=get_env_int(
                "AGENT_TRANSITIONAL_PORT",
                default=DEFAULT_HTTP_PORT,
            ),
        )


def run() -> None:
    get_settings()
    settings = TransitionalServiceSettings.from_env()
    uvicorn.run(app, host=settings.host, port=settings.port)
