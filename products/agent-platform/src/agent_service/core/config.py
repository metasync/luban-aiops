from __future__ import annotations

from functools import lru_cache

from agent_service.runtime_settings import RuntimeSettings


@lru_cache(maxsize=1)
def get_settings() -> RuntimeSettings:
    return RuntimeSettings.from_env()
