from __future__ import annotations

from typing import Any

from agent_service.providers.base import (
    _NON_CHAT_MARKERS,
    AgentScopeProvider,
    ProviderConfigurationError,
)
from agent_service.runtime_settings import DashScopeOptions, RuntimeSettings


class DashScopeProvider(AgentScopeProvider):
    provider_name = "dashscope"
    default_model = "qwen-plus"
    default_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    # SPEC-027 R-6: curated series refreshed to the decimal-generation
    # lineup plus the stable tier aliases. Re-verified against the live
    # compatible-mode API 2026-11-02: dropped ``qwen-turbo`` (no longer
    # advertised; only the dated ``qwen-turbo-0919`` remains and it 404s on
    # call) and added the current ``qwen3.8`` flash/27b tier. Every id below
    # returns 200 on a real chat completion with the dev credential.
    model_series = (
        "qwen-plus",
        "qwen-max",
        "qwen3.8-max",
        "qwen3.8-flash",
        "qwen3.8-27b",
        "qwen3.7-plus",
        "qwen3.7-flash",
    )
    # SPEC-027 R-4: DashScope's /models payload is huge — restrict to the
    # qwen chat families and drop vision/omni/translation/OCR modalities
    # on top of the shared non-chat markers.
    discover_family_prefixes = ("qwen",)
    discover_exclude_markers = _NON_CHAT_MARKERS + (
        "-vl",
        "-mt",
        "-ocr",
        "omni",
    )

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
