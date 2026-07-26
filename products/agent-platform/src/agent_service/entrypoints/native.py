from __future__ import annotations

from dataclasses import dataclass

import uvicorn

from agent_service.core.config import get_settings
from agent_service.core.env import get_env_int, get_env_value
from agent_service.metadata import (
    DEFAULT_HTTP_HOST,
    DEFAULT_NATIVE_HTTP_PORT,
    NATIVE_SERVICE_TITLE,
    SERVICE_VERSION,
)


@dataclass(frozen=True)
class NativeServiceSettings:
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    workspace_dir: str = ".workspaces/agent-platform"
    workspace_ttl_seconds: float = 3600.0
    host: str = DEFAULT_HTTP_HOST
    port: int = DEFAULT_NATIVE_HTTP_PORT
    title: str = NATIVE_SERVICE_TITLE
    version: str = SERVICE_VERSION

    @classmethod
    def from_env(cls) -> "NativeServiceSettings":
        return cls(
            redis_host=get_env_value("AGENTSCOPE_REDIS_HOST", default="127.0.0.1"),
            redis_port=get_env_int("AGENTSCOPE_REDIS_PORT", default=6379),
            redis_db=get_env_int("AGENTSCOPE_REDIS_DB", default=0),
            redis_password=get_env_value("AGENTSCOPE_REDIS_PASSWORD", default=None),
            workspace_dir=get_env_value(
                "AGENTSCOPE_WORKSPACE_DIR",
                default=".workspaces/agent-platform",
            ),
            workspace_ttl_seconds=float(
                get_env_value("AGENTSCOPE_WORKSPACE_TTL_SECONDS", default="3600")
            ),
            host=get_env_value(
                "AGENT_NATIVE_HOST",
                default=DEFAULT_HTTP_HOST,
            ),
            port=get_env_int(
                "AGENT_NATIVE_PORT",
                default=DEFAULT_NATIVE_HTTP_PORT,
            ),
            title=get_env_value(
                "AGENT_NATIVE_TITLE",
                default=NATIVE_SERVICE_TITLE,
            ),
            version=get_env_value(
                "AGENT_NATIVE_VERSION",
                default=SERVICE_VERSION,
            ),
        )


def build_native_service_app(settings: NativeServiceSettings | None = None):
    active_settings = settings or NativeServiceSettings.from_env()

    from agentscope.app import create_app
    from agentscope.app.message_bus import RedisMessageBus
    from agentscope.app.storage import RedisStorage
    from agentscope.app.workspace_manager import LocalWorkspaceManager

    storage = RedisStorage(
        host=active_settings.redis_host,
        port=active_settings.redis_port,
        db=active_settings.redis_db,
        password=active_settings.redis_password,
    )
    message_bus = RedisMessageBus(
        host=active_settings.redis_host,
        port=active_settings.redis_port,
        db=active_settings.redis_db,
        password=active_settings.redis_password,
    )
    workspace_manager = LocalWorkspaceManager(
        basedir=active_settings.workspace_dir,
        ttl=active_settings.workspace_ttl_seconds,
    )
    return create_app(
        storage=storage,
        message_bus=message_bus,
        workspace_manager=workspace_manager,
        title=active_settings.title,
        version=active_settings.version,
    )


def run() -> None:
    get_settings()
    settings = NativeServiceSettings.from_env()
    app = build_native_service_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port)
