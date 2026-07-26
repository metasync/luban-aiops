from __future__ import annotations

from typing import Any

from agent_service.providers.base import AgentScopeProvider, ProviderConfigurationError
from agent_service.runtime_settings import OpenAIOptions, RuntimeSettings


class OpenAIProvider(AgentScopeProvider):
    provider_name = "openai"
    default_model = "gpt-4o-mini"
    default_base_url = None

    def build_model(self, settings: RuntimeSettings) -> Any:
        from agentscope.credential import OpenAICredential
        from agentscope.model import OpenAIChatModel

        self.validate(settings)
        options = settings.provider_options
        if not isinstance(options, OpenAIOptions):
            raise ProviderConfigurationError(
                "OpenAI provider received non-OpenAI options."
            )
        credential_kwargs: dict[str, Any] = {"api_key": settings.api_key}
        resolved_base_url = self.resolved_base_url(settings)
        if resolved_base_url:
            credential_kwargs["base_url"] = resolved_base_url
        if settings.organization:
            credential_kwargs["organization"] = settings.organization
        return OpenAIChatModel(
            credential=OpenAICredential(**credential_kwargs),
            model=self.resolved_model_name(settings),
            parameters=OpenAIChatModel.Parameters(
                max_tokens=options.max_tokens,
                thinking_enable=options.thinking_enable,
                reasoning_effort=options.reasoning_effort,
                temperature=options.temperature,
                top_p=options.top_p,
                parallel_tool_calls=options.parallel_tool_calls,
            ),
        )
