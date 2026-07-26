from __future__ import annotations

from typing import Any

from agent_service.providers.base import AgentScopeProvider, ProviderConfigurationError
from agent_service.runtime_settings import DashScopeOptions, RuntimeSettings


class DashScopeProvider(AgentScopeProvider):
    provider_name = "dashscope"
    default_model = "qwen-plus"
    default_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def build_model(self, settings: RuntimeSettings) -> Any:
        from agentscope.credential import DashScopeCredential
        from agentscope.model import DashScopeChatModel

        self.validate(settings)
        options = settings.provider_options
        if not isinstance(options, DashScopeOptions):
            raise ProviderConfigurationError(
                "DashScope provider received non-DashScope options."
            )
        return DashScopeChatModel(
            credential=DashScopeCredential(
                api_key=settings.api_key,
                base_url=self.resolved_base_url(settings),
            ),
            model=self.resolved_model_name(settings),
            parameters=DashScopeChatModel.Parameters(
                max_tokens=options.max_tokens,
                thinking_enable=options.thinking_enable,
                thinking_budget=options.thinking_budget,
                temperature=options.temperature,
                top_p=options.top_p,
                top_k=options.top_k,
                parallel_tool_calls=options.parallel_tool_calls,
            ),
        )
