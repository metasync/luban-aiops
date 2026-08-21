from __future__ import annotations

from functools import lru_cache

from agent_service.core.config import get_settings
from agent_service.runtime_kernel import AgentKernel
from agent_service.services.hitl_confirmations import (
    CONFIRMATION_REGISTRY,
    ConfirmationRegistry,
)


@lru_cache(maxsize=1)
def get_runtime_kernel() -> AgentKernel:
    return AgentKernel(settings=get_settings())


def get_confirmation_registry() -> ConfirmationRegistry:
    """Process-wide parked-confirmation registry (SPEC-020 R-2)."""
    return CONFIRMATION_REGISTRY
