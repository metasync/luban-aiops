from __future__ import annotations

from functools import lru_cache

from agent_service.core.config import get_settings
from agent_service.runtime_kernel import AgentKernel


@lru_cache(maxsize=1)
def get_runtime_kernel() -> AgentKernel:
    return AgentKernel(settings=get_settings())
