from __future__ import annotations

from typing import Any

from agent_service.providers.base import AgentScopeProvider, ProviderConfigurationError
from agent_service.runtime_settings import DeepSeekOptions, RuntimeSettings


class DeepSeekProvider(AgentScopeProvider):
    provider_name = "deepseek"
    default_model = "deepseek-v4-flash"
    default_base_url = "https://api.deepseek.com"
    # SPEC-027 R-6: curated series refreshed to the V4 family (verified
    # 2026-08-24; the discontinued deepseek-chat/deepseek-reasoner names
    # stay resolvable via the SPEC-026 legacy alias map).
    model_series = (
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "deepseek-v4-flash-vision-exp",
    )
    # SPEC-027 R-4: DeepSeek's /models list is small and chat-centric;
    # restrict to the family as a defensive guard.
    discover_family_prefixes = ("deepseek",)

    def build_model(self, settings: RuntimeSettings) -> Any:
        from agentscope.credential import DeepSeekCredential
        from agentscope.model import DeepSeekChatModel

        self.validate(settings)
        options = settings.provider_options
        if not isinstance(options, DeepSeekOptions):
            raise ProviderConfigurationError(
                "DeepSeek provider received non-DeepSeek options."
            )
        credential_kwargs: dict[str, Any] = {"api_key": settings.api_key}
        resolved_base_url = self.resolved_base_url(settings)
        if resolved_base_url:
            credential_kwargs["base_url"] = resolved_base_url
        return DeepSeekChatModel(
            credential=DeepSeekCredential(**credential_kwargs),
            model=self.resolved_model_name(settings),
            parameters=DeepSeekChatModel.Parameters(
                max_tokens=options.max_tokens,
                thinking_enable=options.thinking_enable,
                reasoning_effort=options.reasoning_effort,
                temperature=options.temperature,
                top_p=options.top_p,
            ),
        )
