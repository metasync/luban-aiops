from __future__ import annotations

import os
from dataclasses import dataclass

import uvicorn


@dataclass(frozen=True)
class NativeServiceSettings:
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    workspace_dir: str = ".workspaces/agent-platform"
    workspace_ttl_seconds: float = 3600.0
    host: str = "0.0.0.0"
    port: int = 8080
    title: str = "Luban Agent Service"
    version: str = "0.1.0"

    @classmethod
    def from_env(cls) -> "NativeServiceSettings":
        return cls(
            redis_host=os.getenv("AGENTSCOPE_REDIS_HOST", "127.0.0.1"),
            redis_port=int(os.getenv("AGENTSCOPE_REDIS_PORT", "6379")),
            redis_db=int(os.getenv("AGENTSCOPE_REDIS_DB", "0")),
            redis_password=os.getenv("AGENTSCOPE_REDIS_PASSWORD"),
            workspace_dir=os.getenv(
                "AGENTSCOPE_WORKSPACE_DIR",
                ".workspaces/agent-platform",
            ),
            workspace_ttl_seconds=float(
                os.getenv("AGENTSCOPE_WORKSPACE_TTL_SECONDS", "3600")
            ),
            host=os.getenv("AGENT_SERVICE_HOST", "0.0.0.0"),
            port=int(os.getenv("AGENT_SERVICE_PORT", "8080")),
            title=os.getenv("AGENT_SERVICE_TITLE", "Luban Agent Service"),
            version=os.getenv("AGENT_SERVICE_VERSION", "0.1.0"),
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
    settings = NativeServiceSettings.from_env()
    app = build_native_service_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port)
