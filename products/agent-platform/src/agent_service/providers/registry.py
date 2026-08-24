from __future__ import annotations

from agent_service.providers.base import AgentScopeProvider, ProviderConfigurationError
from agent_service.providers.dashscope import DashScopeProvider
from agent_service.providers.deepseek import DeepSeekProvider
from agent_service.providers.luban import LubanProvider
from agent_service.providers.openai import OpenAIProvider

_PROVIDERS: dict[str, AgentScopeProvider] = {
    "dashscope": DashScopeProvider(),
    "deepseek": DeepSeekProvider(),
    "luban": LubanProvider(),
    "openai": OpenAIProvider(),
}


def get_provider(provider_name: str) -> AgentScopeProvider:
    try:
        return _PROVIDERS[provider_name]
    except KeyError as exc:
        supported = ", ".join(sorted(_PROVIDERS))
        raise ProviderConfigurationError(
            f"Unsupported AgentScope provider: {provider_name}. "
            f"Supported providers: {supported}."
        ) from exc


def supported_provider_names() -> tuple[str, ...]:
    return tuple(sorted(_PROVIDERS))
