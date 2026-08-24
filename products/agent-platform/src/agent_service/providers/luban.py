from __future__ import annotations

from typing import Any

from agent_service.providers.base import AgentScopeProvider, ProviderConfigurationError
from agent_service.runtime_settings import OpenAIOptions, RuntimeSettings


class LubanProvider(AgentScopeProvider):
    """Team-hosted OpenAI-compatible server adapter (SPEC-028).

    Covers self-hosted endpoints such as Ollama, vLLM, and llama.cpp
    ``llama-server``. Authentication is bearer-token based (R-2), and
    the base URL is mandatory — there is no sensible default endpoint for
    a server the team hosts, so ``LUBAN_BASE_URL`` gates the provider in
    alongside ``LUBAN_API_KEY`` (R-1).
    """

    provider_name = "luban"
    # Reference model for the Ollama hosting guide (R-6); operators
    # normally override via LUBAN_MODEL_NAME / LUBAN_MODELS with the
    # concrete served model id (fixed-point pinning, R-3).
    default_model = "qwen3-8b"
    # R-1: no default endpoint — resolve_credentials drops the provider
    # when LUBAN_BASE_URL is unset.
    default_base_url = None
    # R-3: the curated series is empty; only the force-included default
    # model is served when neither LUBAN_MODELS nor live discovery is
    # available.
    model_series = ()
    # R-3: permissive discovery filter — self-hosted model names have no
    # vendor taxonomy, so only the shared dated-snapshot / non-chat
    # marker hygiene applies (no family prefixes).
    discover_family_prefixes = ()

    def validate(self, settings: RuntimeSettings) -> None:
        super().validate(settings)
        if not settings.base_url:
            raise ProviderConfigurationError(
                "LUBAN_BASE_URL is required for the luban provider — "
                "self-hosted endpoints have no default base URL."
            )

    def build_model(self, settings: RuntimeSettings) -> Any:
        from agentscope.credential import OpenAICredential
        from agentscope.model import OpenAIChatModel

        self.validate(settings)
        options = settings.provider_options
        if not isinstance(options, OpenAIOptions):
            raise ProviderConfigurationError(
                "luban provider received non-OpenAI options."
            )
        # R-2: fail-closed — a luban turn never dials anywhere but the
        # operator-declared endpoint, and never without a bearer token.
        base_url = self.resolved_base_url(settings)
        return OpenAIChatModel(
            credential=OpenAICredential(
                api_key=settings.api_key,
                base_url=base_url,
            ),
            model=self.resolved_model_name(settings),
            parameters=OpenAIChatModel.Parameters(
                max_tokens=options.max_tokens,
                # R-4: thinking stays off unless the options explicitly
                # enable it; no reasoning effort for small models.
                thinking_enable=options.thinking_enable,
                reasoning_effort=None,
                temperature=options.temperature,
                top_p=options.top_p,
                parallel_tool_calls=options.parallel_tool_calls,
            ),
        )
