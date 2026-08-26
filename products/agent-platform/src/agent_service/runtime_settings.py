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
    "When you quote log lines or command output in a reply, place them in a fenced code "
    "block with real line breaks — quote the raw lines, never the JSON-serialized string "
    "with escaped \\n sequences — and keep the excerpt to the lines that matter. "
    "For procedure, interpretation, or remediation questions, consult skills.search for "
    "team-owned guidance and use skills.get to read a full skill when needed; "
    "use skills.list to discover what skills exist when asked what guidance is available. "
    "Cite any skill you rely on by its title (its skill_id is also acceptable). "
    "Skill guidance is not live "
    "cluster data, and tool evidence is not a procedure — keep the two clearly separated. "
    "If no skills match, say no team guidance matched instead of inventing steps. "
    "When asked to triage an incident, work strictly read-only: gather live evidence with the "
    "available tools, consult matching runbooks via skills.search, and produce a triage report "
    "covering the fields incident_id, summary, severity_assessment, evidence, hypotheses, "
    "next_steps, skills_cited, session_id, generated_at, and generated_by. Ground every "
    "hypothesis and next step in evidence you actually gathered or a cited skill, and keep next "
    "steps advisory only (the platform executes nothing). When a structured output requirement "
    "is active for the turn, deliver the report by calling the provided structured-output tool "
    "rather than formatting it in prose."
)

RuntimeProvider = Literal["dashscope", "deepseek", "openai", "luban"]
SUPPORTED_RUNTIME_PROVIDERS = ("dashscope", "deepseek", "openai", "luban")
# SPEC-026 R-5: the profile is a free-form deploy label decoupled from the
# provider (one generic profile hosts every configured provider), so there
# is no supported-profiles allowlist anymore.
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
    profile: str | None = None
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
    tool_data_max_chars: int = 32000
    # Kernel tuning surfaces (SPEC-017 R-1). Defaults mirror the agentscope
    # defaults so unset deployments behave exactly as before.
    max_iters: int = 20
    context_trigger_ratio: float = 0.8
    tool_result_limit: int = 50000
    timezone: str = "UTC"
    model_max_retries: int = 0
    # Kernel middleware surfaces (SPEC-018). All opt-in: unset deployments
    # behave exactly as before the settings existed.
    kernel_tracing: bool = False
    reply_token_budget: float | None = None
    reply_input_token_weight: float = 1.0
    reply_output_token_weight: float = 1.0
    task_tools_enabled: bool = False
    # HITL confirmation bridging (SPEC-020 R-2): seconds a parked kernel
    # confirmation stays answerable. 0 disables the bridge and restores the
    # pre-SPEC-020 silent-park posture.
    hitl_confirm_timeout: int = 600
    # Evidence persistence caps (SPEC-025 R-1): per-entry data cap in chars
    # and per-session storage budget in bytes. Defaults are measured-derived
    # (dev-k8s pass, SPEC-025 plan §Q3) and deliberately decoupled from the
    # SSE data cap, which protects live bandwidth rather than storage.
    evidence_entry_max_chars: int = 131072
    evidence_session_max_bytes: int = 4194304
    # Live model discovery (SPEC-027 R-5): periodic provider /models
    # queries feed the catalog behind a fail-soft fallback ladder.
    # Disabled restores the pure SPEC-026 curated-series behavior.
    model_discovery_enabled: bool = True
    model_discovery_refresh_seconds: int = 1800
    model_discovery_timeout_seconds: float = 5.0

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
        # SPEC-026 R-5: the profile is an arbitrary deploy label; only the
        # provider is constrained (parsed against the supported set in
        # from_env). The former profile == provider equality check is gone.

        # Kernel tuning validation (SPEC-017 R-1): out-of-range values fail
        # startup with a clear error. Bounds mirror the agentscope config
        # constraints so an invalid setting cannot reach the kernel.
        if self.max_iters < 1:
            raise ValueError("AGENTSCOPE_MAX_ITERS must be >= 1.")
        if not 0.0 < self.context_trigger_ratio < 0.9:
            raise ValueError(
                "AGENTSCOPE_CONTEXT_TRIGGER_RATIO must be in the open "
                "interval (0, 0.9)."
            )
        if self.tool_result_limit < 1:
            raise ValueError("AGENTSCOPE_TOOL_RESULT_LIMIT must be >= 1.")
        if self.model_max_retries < 0:
            raise ValueError("AGENTSCOPE_MODEL_MAX_RETRIES must be >= 0.")
        # Kernel middleware validation (SPEC-018): opt-in knobs fail startup
        # with a clear error instead of reaching the kernel misconfigured.
        if self.reply_token_budget is not None and self.reply_token_budget <= 0:
            raise ValueError(
                "AGENTSCOPE_REPLY_TOKEN_BUDGET must be > 0 when set."
            )
        if self.reply_input_token_weight < 0:
            raise ValueError(
                "AGENTSCOPE_REPLY_INPUT_TOKEN_WEIGHT must be >= 0."
            )
        if self.reply_output_token_weight < 0:
            raise ValueError(
                "AGENTSCOPE_REPLY_OUTPUT_TOKEN_WEIGHT must be >= 0."
            )
        if not self.timezone:
            raise ValueError("AGENTSCOPE_TIMEZONE must not be empty.")
        if self.hitl_confirm_timeout < 0:
            raise ValueError("AGENT_HITL_CONFIRM_TIMEOUT must be >= 0.")
        # Live model discovery validation (SPEC-027 R-5).
        if self.model_discovery_refresh_seconds < 1:
            raise ValueError("AGENT_MODEL_DISCOVERY_REFRESH_SECONDS must be >= 1.")
        if self.model_discovery_timeout_seconds <= 0:
            raise ValueError("AGENT_MODEL_DISCOVERY_TIMEOUT_SECONDS must be > 0.")
        try:
            from zoneinfo import ZoneInfo

            ZoneInfo(self.timezone)
        except Exception as exc:  # noqa: BLE001 - zoneinfo raises several types
            raise ValueError(
                f"AGENTSCOPE_TIMEZONE is not a valid IANA timezone: "
                f"{self.timezone!r}."
            ) from exc

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

        # SPEC-028 R-1/R-4: the luban provider (team-hosted OpenAI-
        # compatible servers) reuses the OpenAI options shape; thinking
        # stays off unless explicitly opted in — self-hosted small models
        # rarely have a thinking mode and the flag must not 4xx the turn.
        if provider == "luban":
            return OpenAIOptions(
                **common_kwargs,
                thinking_enable=_optional_bool("LUBAN_THINKING_ENABLE") or False,
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
        profile = _optional_str("AGENTSCOPE_PROFILE")
        provider = os.getenv("AGENTSCOPE_PROVIDER", "dashscope").strip().lower()
        if provider not in SUPPORTED_RUNTIME_PROVIDERS:
            raise ValueError(
                "Unsupported AGENTSCOPE_PROVIDER. "
                f"Expected one of: {', '.join(SUPPORTED_RUNTIME_PROVIDERS)}."
            )
        input_token_weight = _optional_float(
            "AGENTSCOPE_REPLY_INPUT_TOKEN_WEIGHT"
        )
        output_token_weight = _optional_float(
            "AGENTSCOPE_REPLY_OUTPUT_TOKEN_WEIGHT"
        )
        model_discovery_enabled = _optional_bool("AGENT_MODEL_DISCOVERY_ENABLED")
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
            tool_data_max_chars=int(
                os.getenv("AGENT_TOOL_DATA_MAX_CHARS", "32000")
            ),
            max_iters=int(os.getenv("AGENTSCOPE_MAX_ITERS", "20")),
            context_trigger_ratio=float(
                os.getenv("AGENTSCOPE_CONTEXT_TRIGGER_RATIO", "0.8")
            ),
            tool_result_limit=int(os.getenv("AGENTSCOPE_TOOL_RESULT_LIMIT", "50000")),
            timezone=os.getenv("AGENTSCOPE_TIMEZONE", "UTC").strip() or "UTC",
            model_max_retries=int(os.getenv("AGENTSCOPE_MODEL_MAX_RETRIES", "0")),
            kernel_tracing=_optional_bool("AGENTSCOPE_KERNEL_TRACING") or False,
            reply_token_budget=_optional_float("AGENTSCOPE_REPLY_TOKEN_BUDGET"),
            reply_input_token_weight=(
                1.0 if input_token_weight is None else input_token_weight
            ),
            reply_output_token_weight=(
                1.0 if output_token_weight is None else output_token_weight
            ),
            task_tools_enabled=(
                _optional_bool("AGENTSCOPE_TASK_TOOLS_ENABLED") or False
            ),
            hitl_confirm_timeout=int(os.getenv("AGENT_HITL_CONFIRM_TIMEOUT", "600")),
            evidence_entry_max_chars=int(
                os.getenv("AGENT_EVIDENCE_ENTRY_MAX_CHARS", "131072")
            ),
            evidence_session_max_bytes=int(
                os.getenv("AGENT_EVIDENCE_SESSION_MAX_BYTES", "4194304")
            ),
            model_discovery_enabled=(
                True if model_discovery_enabled is None else model_discovery_enabled
            ),
            model_discovery_refresh_seconds=int(
                os.getenv("AGENT_MODEL_DISCOVERY_REFRESH_SECONDS", "1800")
            ),
            model_discovery_timeout_seconds=float(
                os.getenv("AGENT_MODEL_DISCOVERY_TIMEOUT_SECONDS", "5")
            ),
        )

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def resolved_model_name(self, default_model: str) -> str:
        return self.model_name or default_model

    def resolved_base_url(self, default_base_url: str | None) -> str | None:
        return self.base_url or default_base_url
