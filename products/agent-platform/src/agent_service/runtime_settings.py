import os
from dataclasses import dataclass
from typing import Literal

from agent_service.metadata import RUNTIME_APP_NAME


DEFAULT_SYSTEM_PROMPT = (
    "You are the runtime kernel for the Luban AIOps platform. "
    "Answer clearly and concisely, and keep the response grounded in the current platform state. "
    "Ground every factual claim in data actually returned by a tool call. "
    "Never invent, estimate, or imply infrastructure data you did not retrieve: "
    "if no tools are available, a tool call fails, or a call is denied, say so explicitly "
    "and answer only with what you genuinely know. Do not emit tool-call markup as text. "
    "For procedure, interpretation, or remediation questions, consult skills.search for "
    "team-owned guidance and use skills.get to read a full skill when needed; "
    "use skills.list to discover what skills exist when asked what guidance is available. "
    "Cite any skill you rely on by its title (its skill_id is also acceptable). "
    "Skill guidance is not live "
    "cluster data, and tool evidence is not a procedure — keep the two clearly separated. "
    "If no skills match, say no team guidance matched instead of inventing steps."
)

RuntimeProvider = Literal["dashscope", "deepseek", "openai"]
SUPPORTED_RUNTIME_PROVIDERS = ("dashscope", "deepseek", "openai")
RuntimeProfile = Literal["dashscope", "deepseek", "openai"]
SUPPORTED_RUNTIME_PROFILES = SUPPORTED_RUNTIME_PROVIDERS
DeepSeekReasoningEffort = Literal["high", "max"]
OpenAIReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh"]


def _optional_str(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _optional_int(name: str) -> int | None:
    value = _optional_str(name)
    return None if value is None else int(value)


def _optional_float(name: str) -> float | None:
    value = _optional_str(name)
    return None if value is None else float(value)


def _optional_bool(name: str) -> bool | None:
    value = _optional_str(name)
    if value is None:
        return None
    lowered = value.lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value.")


def _optional_choice(name: str, supported: set[str]) -> str | None:
    value = _optional_str(name)
    if value is None:
        return None
    if value not in supported:
        supported_values = ", ".join(sorted(supported))
        raise ValueError(f"{name} must be one of: {supported_values}.")
    return value


@dataclass(frozen=True)
class DashScopeOptions:
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    thinking_enable: bool = False
    thinking_budget: int | None = None
    top_k: int | None = None
    parallel_tool_calls: bool = True


@dataclass(frozen=True)
class DeepSeekOptions:
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    thinking_enable: bool = False
    reasoning_effort: DeepSeekReasoningEffort | None = None


@dataclass(frozen=True)
class OpenAIOptions:
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    thinking_enable: bool = False
    reasoning_effort: OpenAIReasoningEffort | None = None
    parallel_tool_calls: bool = True


RuntimeProviderOptions = DashScopeOptions | DeepSeekOptions | OpenAIOptions


@dataclass(frozen=True)
class RuntimeSettings:
    profile: RuntimeProfile | None = None
    provider: RuntimeProvider = "dashscope"
    agent_name: str = RUNTIME_APP_NAME
    model_name: str | None = None
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    api_key: str | None = None
    base_url: str | None = None
    organization: str | None = None
    provider_options: RuntimeProviderOptions | None = None
    tool_gateway_url: str | None = None
    tool_data_summary_max_chars: int = 2000

    @staticmethod
    def default_provider_options(provider: RuntimeProvider) -> RuntimeProviderOptions:
        if provider == "dashscope":
            return DashScopeOptions()
        if provider == "deepseek":
            return DeepSeekOptions()
        return OpenAIOptions()

    @staticmethod
    def provider_options_type(
        provider: RuntimeProvider,
    ) -> type[DashScopeOptions] | type[DeepSeekOptions] | type[OpenAIOptions]:
        if provider == "dashscope":
            return DashScopeOptions
        if provider == "deepseek":
            return DeepSeekOptions
        return OpenAIOptions

    def __post_init__(self) -> None:
        if self.profile is not None and self.profile != self.provider:
            raise ValueError(
                "AGENTSCOPE_PROFILE must match AGENTSCOPE_PROVIDER when both are set. "
                f"Got profile={self.profile!r} and provider={self.provider!r}."
            )

        if self.provider_options is None:
            object.__setattr__(
                self,
                "provider_options",
                self.default_provider_options(self.provider),
            )
            return

        expected_type = self.provider_options_type(self.provider)
        if not isinstance(self.provider_options, expected_type):
            raise ValueError(
                "provider_options type does not match AGENTSCOPE_PROVIDER. "
                f"Expected {expected_type.__name__}."
            )

    @staticmethod
    def _provider_options_from_env(provider: RuntimeProvider) -> RuntimeProviderOptions:
        common_kwargs = {
            "max_tokens": _optional_int("AGENTSCOPE_MAX_TOKENS"),
            "temperature": _optional_float("AGENTSCOPE_TEMPERATURE"),
            "top_p": _optional_float("AGENTSCOPE_TOP_P"),
        }

        if provider == "dashscope":
            parallel_tool_calls = _optional_bool("DASHSCOPE_PARALLEL_TOOL_CALLS")
            return DashScopeOptions(
                **common_kwargs,
                thinking_enable=_optional_bool("DASHSCOPE_THINKING_ENABLE") or False,
                thinking_budget=_optional_int("DASHSCOPE_THINKING_BUDGET"),
                top_k=_optional_int("DASHSCOPE_TOP_K"),
                parallel_tool_calls=(
                    parallel_tool_calls if parallel_tool_calls is not None else True
                ),
            )

        if provider == "deepseek":
            reasoning_effort = _optional_choice(
                "DEEPSEEK_REASONING_EFFORT",
                {"high", "max"},
            )
            return DeepSeekOptions(
                **common_kwargs,
                thinking_enable=_optional_bool("DEEPSEEK_THINKING_ENABLE") or False,
                reasoning_effort=reasoning_effort,
            )

        reasoning_effort = _optional_choice(
            "OPENAI_REASONING_EFFORT",
            {"none", "minimal", "low", "medium", "high", "xhigh"},
        )
        parallel_tool_calls = _optional_bool("OPENAI_PARALLEL_TOOL_CALLS")
        return OpenAIOptions(
            **common_kwargs,
            thinking_enable=_optional_bool("OPENAI_THINKING_ENABLE") or False,
            reasoning_effort=reasoning_effort,
            parallel_tool_calls=(
                parallel_tool_calls if parallel_tool_calls is not None else True
            ),
        )

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        profile = _optional_choice(
            "AGENTSCOPE_PROFILE",
            set(SUPPORTED_RUNTIME_PROFILES),
        )
        provider = os.getenv("AGENTSCOPE_PROVIDER", "dashscope").strip().lower()
        if provider not in SUPPORTED_RUNTIME_PROVIDERS:
            raise ValueError(
                "Unsupported AGENTSCOPE_PROVIDER. "
                f"Expected one of: {', '.join(SUPPORTED_RUNTIME_PROVIDERS)}."
            )
        return cls(
            profile=profile,
            provider=provider,
            agent_name=os.getenv("AGENTSCOPE_AGENT_NAME", RUNTIME_APP_NAME),
            model_name=_optional_str("AGENTSCOPE_MODEL_NAME"),
            system_prompt=os.getenv("AGENTSCOPE_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
            api_key=os.getenv("AGENTSCOPE_API_KEY"),
            base_url=_optional_str("AGENTSCOPE_BASE_URL"),
            organization=_optional_str("AGENTSCOPE_ORGANIZATION"),
            provider_options=cls._provider_options_from_env(provider),
            tool_gateway_url=_optional_str("TOOL_GATEWAY_URL"),
            tool_data_summary_max_chars=int(
                os.getenv("AGENT_TOOL_DATA_SUMMARY_MAX_CHARS", "2000")
            ),
        )

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def resolved_model_name(self, default_model: str) -> str:
        return self.model_name or default_model

    def resolved_base_url(self, default_base_url: str | None) -> str | None:
        return self.base_url or default_base_url
