"""Default entrypoint: runs the platform-owned agent-service (v2 contract)."""

from __future__ import annotations

import uvicorn

from agent_service.app import app
from agent_service.core.config import get_settings
from agent_service.core.env import get_env_int, get_env_value
from agent_service.metadata import DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT


def run() -> None:
    get_settings()
    host = get_env_value("AGENT_SERVICE_HOST", default=DEFAULT_HTTP_HOST)
    port = get_env_int("AGENT_SERVICE_PORT", default=DEFAULT_HTTP_PORT)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
