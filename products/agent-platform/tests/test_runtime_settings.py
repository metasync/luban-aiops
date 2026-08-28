import pytest

from agent_service.native_service import NativeServiceSettings
from agent_service.runtime_settings import (
    DEFAULT_SYSTEM_PROMPT,
    DashScopeOptions,
    DeepSeekOptions,
    OpenAIOptions,
    RuntimeSettings,
)


def test_default_system_prompt_carries_skills_discipline(monkeypatch):
    """SPEC-014 R-5: the default prompt teaches the skills discipline."""
    assert "skills.search" in DEFAULT_SYSTEM_PROMPT
    assert "skills.get" in DEFAULT_SYSTEM_PROMPT
    assert "skills.list" in DEFAULT_SYSTEM_PROMPT
    # Cite used skills by title (skill_id acceptable too).
    assert "cite" in DEFAULT_SYSTEM_PROMPT.lower()
    # Guidance vs live-data separation.
    assert "not live" in DEFAULT_SYSTEM_PROMPT
    # Honest no-match reporting.
    assert "no team guidance matched" in DEFAULT_SYSTEM_PROMPT

    monkeypatch.delenv("AGENTSCOPE_SYSTEM_PROMPT", raising=False)
    settings = RuntimeSettings.from_env()
    assert settings.system_prompt == DEFAULT_SYSTEM_PROMPT


def test_default_system_prompt_carries_log_quoting_discipline():
    """0.18.1 live-check finding: replies quoted pod logs as one
    JSON-serialized string; the default prompt steers the model to
    fenced code blocks with real line breaks instead."""
    assert "fenced code" in DEFAULT_SYSTEM_PROMPT
    assert "real line breaks" in DEFAULT_SYSTEM_PROMPT
    assert "JSON-serialized" in DEFAULT_SYSTEM_PROMPT


def test_default_system_prompt_carries_triage_discipline(monkeypatch):
    """SPEC-015 R-3 (updated by SPEC-017 R-2): the default prompt teaches the
    triage discipline; delivery is format-neutral — the structured-output
    tool carries the report when active, and the incident-service turn
    prompt supplies any fallback format."""
    # Read-only evidence gathering.
    assert "read-only" in DEFAULT_SYSTEM_PROMPT
    # The report fields the capture pipeline validates.
    for field in (
        "incident_id", "summary", "severity_assessment", "evidence",
        "hypotheses", "next_steps", "skills_cited", "session_id",
        "generated_at", "generated_by",
    ):
        assert field in DEFAULT_SYSTEM_PROMPT
    # Next steps are advisory only — R3 executes nothing.
    assert "advisory" in DEFAULT_SYSTEM_PROMPT
    # Structured output is delivered through the kernel tool, not prose.
    assert "structured-output" in DEFAULT_SYSTEM_PROMPT

    monkeypatch.delenv("AGENTSCOPE_SYSTEM_PROMPT", raising=False)
    settings = RuntimeSettings.from_env()
    assert settings.system_prompt == DEFAULT_SYSTEM_PROMPT


def test_runtime_settings_defaults(monkeypatch):
    monkeypatch.delenv("AGENTSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("AGENTSCOPE_PROVIDER", raising=False)
    monkeypatch.delenv("AGENTSCOPE_PROFILE", raising=False)
    monkeypatch.delenv("AGENTSCOPE_AGENT_NAME", raising=False)
    settings = RuntimeSettings.from_env()

    assert settings.profile is None
    assert settings.provider == "dashscope"
    assert settings.agent_name == "LubanOpsRuntime"
    assert settings.model_name is None
    assert settings.resolved_model_name("qwen-plus") == "qwen-plus"
    assert settings.provider_options == DashScopeOptions()
    assert settings.is_configured() is False


def test_runtime_settings_reads_env(monkeypatch):
    monkeypatch.setenv("AGENTSCOPE_PROFILE", "deepseek")
    monkeypatch.setenv("AGENTSCOPE_PROVIDER", "deepseek")
    monkeypatch.setenv("AGENTSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("AGENTSCOPE_MODEL_NAME", "deepseek-v4-flash")
    monkeypatch.setenv("AGENTSCOPE_BASE_URL", "https://api.deepseek.com")
    settings = RuntimeSettings.from_env()

    assert settings.profile == "deepseek"
    assert settings.provider == "deepseek"
    assert settings.api_key == "test-key"
    assert settings.model_name == "deepseek-v4-flash"
    assert settings.base_url == "https://api.deepseek.com"
    assert settings.provider_options == DeepSeekOptions()
    assert settings.is_configured() is True


def test_runtime_settings_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("AGENTSCOPE_PROVIDER", "unknown")

    try:
        RuntimeSettings.from_env()
    except ValueError as exc:
        assert "Unsupported AGENTSCOPE_PROVIDER" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("RuntimeSettings.from_env() should reject unknown providers")


def test_runtime_settings_accepts_any_profile_label(monkeypatch):
    # SPEC-026 R-5: the profile is a free-form deploy label, decoupled
    # from the provider (one generic profile hosts every provider).
    monkeypatch.setenv("AGENTSCOPE_PROFILE", "default")
    monkeypatch.setenv("AGENTSCOPE_PROVIDER", "deepseek")
    settings = RuntimeSettings.from_env()
    assert settings.profile == "default"
    assert settings.provider == "deepseek"


def test_runtime_settings_empty_profile_is_unset(monkeypatch):
    monkeypatch.setenv("AGENTSCOPE_PROFILE", "   ")
    settings = RuntimeSettings.from_env()
    assert settings.profile is None


def test_model_discovery_settings_defaults(monkeypatch):
    """SPEC-027 R-5: discovery is on by default with sane cadence."""
    monkeypatch.delenv("AGENT_MODEL_DISCOVERY_ENABLED", raising=False)
    monkeypatch.delenv("AGENT_MODEL_DISCOVERY_REFRESH_SECONDS", raising=False)
    monkeypatch.delenv("AGENT_MODEL_DISCOVERY_TIMEOUT_SECONDS", raising=False)
    settings = RuntimeSettings.from_env()
    assert settings.model_discovery_enabled is True
    assert settings.model_discovery_refresh_seconds == 1800
    assert settings.model_discovery_timeout_seconds == 5.0


def test_model_discovery_settings_read_env(monkeypatch):
    monkeypatch.setenv("AGENT_MODEL_DISCOVERY_ENABLED", "false")
    monkeypatch.setenv("AGENT_MODEL_DISCOVERY_REFRESH_SECONDS", "300")
    monkeypatch.setenv("AGENT_MODEL_DISCOVERY_TIMEOUT_SECONDS", "2.5")
    settings = RuntimeSettings.from_env()
    assert settings.model_discovery_enabled is False
    assert settings.model_discovery_refresh_seconds == 300
    assert settings.model_discovery_timeout_seconds == 2.5


def test_execution_signing_settings_defaults(monkeypatch):
    """SPEC-037 R-2/R-5: unset signing key and audit emission knobs."""
    monkeypatch.delenv("AGENT_EXECUTION_SIGNING_KEY", raising=False)
    monkeypatch.delenv("AGENT_AUDIT_SERVICE_URL", raising=False)
    monkeypatch.delenv("AGENT_AUDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("AGENT_AUDIT_CLIENT_SECRET", raising=False)
    settings = RuntimeSettings.from_env()
    assert settings.execution_signing_key is None
    assert settings.audit_service_url is None
    assert settings.audit_client_id == "agent-service"
    assert settings.audit_client_secret is None


def test_execution_signing_settings_read_env(monkeypatch):
    monkeypatch.setenv("AGENT_EXECUTION_SIGNING_KEY", "signing-key-1")
    monkeypatch.setenv("AGENT_AUDIT_SERVICE_URL", "http://audit-service:8000")
    monkeypatch.setenv("AGENT_AUDIT_CLIENT_ID", "agent-service")
    monkeypatch.setenv("AGENT_AUDIT_CLIENT_SECRET", "ingest-secret")
    settings = RuntimeSettings.from_env()
    assert settings.execution_signing_key == "signing-key-1"
    assert settings.audit_service_url == "http://audit-service:8000"
    assert settings.audit_client_id == "agent-service"
    assert settings.audit_client_secret == "ingest-secret"


def test_incident_client_settings_defaults(monkeypatch):
    """SPEC-043 R-3: unset incident knobs keep the fail-closed posture —
    incident-report creation answers 503 until both URL and secret land;
    the shift-summary path never touches these knobs."""
    monkeypatch.delenv("AGENT_INCIDENT_SERVICE_URL", raising=False)
    monkeypatch.delenv("AGENT_INCIDENT_CLIENT_ID", raising=False)
    monkeypatch.delenv("AGENT_INCIDENT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("AGENT_INCIDENT_CLIENT_TIMEOUT_SECONDS", raising=False)
    settings = RuntimeSettings.from_env()
    assert settings.incident_service_url is None
    assert settings.incident_client_id == "agent-service"
    assert settings.incident_client_secret is None
    assert settings.incident_client_timeout_seconds == 10.0


def test_incident_client_settings_read_env(monkeypatch):
    monkeypatch.setenv("AGENT_INCIDENT_SERVICE_URL", "http://incident-service:8000")
    monkeypatch.setenv("AGENT_INCIDENT_CLIENT_ID", "agent-service")
    monkeypatch.setenv("AGENT_INCIDENT_CLIENT_SECRET", "query-secret")
    monkeypatch.setenv("AGENT_INCIDENT_CLIENT_TIMEOUT_SECONDS", "4.5")
    settings = RuntimeSettings.from_env()
    assert settings.incident_service_url == "http://incident-service:8000"
    assert settings.incident_client_id == "agent-service"
    assert settings.incident_client_secret == "query-secret"
    assert settings.incident_client_timeout_seconds == 4.5


def test_model_discovery_settings_validation():
    with pytest.raises(ValueError, match="REFRESH_SECONDS must be >= 1"):
        RuntimeSettings(model_discovery_refresh_seconds=0)
    with pytest.raises(ValueError, match="TIMEOUT_SECONDS must be > 0"):
        RuntimeSettings(model_discovery_timeout_seconds=0.0)


def test_execution_worker_settings_defaults(monkeypatch):
    """SPEC-038 R-4: unset worker knobs keep the fail-closed posture."""
    monkeypatch.delenv("AGENT_EXECUTION_WORKER_URL", raising=False)
    monkeypatch.delenv("AGENT_EXECUTION_HANDOFF_TOKEN", raising=False)
    monkeypatch.delenv("AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS", raising=False)
    settings = RuntimeSettings.from_env()
    assert settings.execution_worker_url is None
    assert settings.execution_handoff_token is None
    assert settings.execution_worker_timeout_seconds == 60.0


def test_execution_worker_settings_read_env(monkeypatch):
    monkeypatch.setenv("AGENT_EXECUTION_WORKER_URL", "http://execution-runtime:8000")
    monkeypatch.setenv("AGENT_EXECUTION_HANDOFF_TOKEN", "handoff-secret")
    monkeypatch.setenv("AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS", "45")
    settings = RuntimeSettings.from_env()
    assert settings.execution_worker_url == "http://execution-runtime:8000"
    assert settings.execution_handoff_token == "handoff-secret"
    assert settings.execution_worker_timeout_seconds == 45.0


def test_execution_worker_timeout_validation():
    with pytest.raises(ValueError, match="WORKER_TIMEOUT_SECONDS must be > 0"):
        RuntimeSettings(execution_worker_timeout_seconds=0.0)


def test_native_service_settings_reads_env(monkeypatch):
    monkeypatch.setenv("AGENTSCOPE_REDIS_HOST", "redis.internal")
    monkeypatch.setenv("AGENTSCOPE_REDIS_PORT", "6380")
    monkeypatch.setenv("AGENTSCOPE_WORKSPACE_DIR", "/tmp/agent-platform")
    monkeypatch.setenv("AGENT_NATIVE_PORT", "8090")

    settings = NativeServiceSettings.from_env()

    assert settings.redis_host == "redis.internal"
    assert settings.redis_port == 6380
    assert settings.workspace_dir == "/tmp/agent-platform"
    assert settings.port == 8090


def test_dashscope_provider_options_read_env(monkeypatch):
    monkeypatch.setenv("AGENTSCOPE_PROVIDER", "dashscope")
    monkeypatch.setenv("AGENTSCOPE_MAX_TOKENS", "2048")
    monkeypatch.setenv("AGENTSCOPE_TEMPERATURE", "0.3")
    monkeypatch.setenv("AGENTSCOPE_TOP_P", "0.8")
    monkeypatch.setenv("DASHSCOPE_THINKING_ENABLE", "true")
    monkeypatch.setenv("DASHSCOPE_THINKING_BUDGET", "512")
    monkeypatch.setenv("DASHSCOPE_TOP_K", "30")
    monkeypatch.setenv("DASHSCOPE_PARALLEL_TOOL_CALLS", "false")

    settings = RuntimeSettings.from_env()

    assert settings.provider_options == DashScopeOptions(
        max_tokens=2048,
        temperature=0.3,
        top_p=0.8,
        thinking_enable=True,
        thinking_budget=512,
        top_k=30,
        parallel_tool_calls=False,
    )


def test_deepseek_provider_options_read_env(monkeypatch):
    monkeypatch.setenv("AGENTSCOPE_PROVIDER", "deepseek")
    monkeypatch.setenv("AGENTSCOPE_MAX_TOKENS", "1024")
    monkeypatch.setenv("AGENTSCOPE_TEMPERATURE", "0.1")
    monkeypatch.setenv("AGENTSCOPE_TOP_P", "0.7")
    monkeypatch.setenv("DEEPSEEK_THINKING_ENABLE", "true")
    monkeypatch.setenv("DEEPSEEK_REASONING_EFFORT", "max")

    settings = RuntimeSettings.from_env()

    assert settings.provider_options == DeepSeekOptions(
        max_tokens=1024,
        temperature=0.1,
        top_p=0.7,
        thinking_enable=True,
        reasoning_effort="max",
    )


def test_openai_provider_options_read_env(monkeypatch):
    monkeypatch.setenv("AGENTSCOPE_PROVIDER", "openai")
    monkeypatch.setenv("AGENTSCOPE_MAX_TOKENS", "4096")
    monkeypatch.setenv("AGENTSCOPE_TEMPERATURE", "0.2")
    monkeypatch.setenv("AGENTSCOPE_TOP_P", "0.9")
    monkeypatch.setenv("OPENAI_THINKING_ENABLE", "true")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "medium")
    monkeypatch.setenv("OPENAI_PARALLEL_TOOL_CALLS", "false")

    settings = RuntimeSettings.from_env()

    assert settings.provider_options == OpenAIOptions(
        max_tokens=4096,
        temperature=0.2,
        top_p=0.9,
        thinking_enable=True,
        reasoning_effort="medium",
        parallel_tool_calls=False,
    )


def test_openai_provider_options_reject_invalid_reasoning_effort(monkeypatch):
    monkeypatch.setenv("AGENTSCOPE_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "extreme")

    try:
        RuntimeSettings.from_env()
    except ValueError as exc:
        assert "OPENAI_REASONING_EFFORT" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Invalid OpenAI reasoning effort should be rejected")


def test_luban_provider_options_default_thinking_off(monkeypatch):
    """SPEC-028 R-1/R-4: OpenAI-shaped options with thinking off by default."""
    monkeypatch.setenv("AGENTSCOPE_PROVIDER", "luban")
    monkeypatch.delenv("LUBAN_THINKING_ENABLE", raising=False)
    monkeypatch.setenv("AGENTSCOPE_MAX_TOKENS", "1024")
    monkeypatch.setenv("AGENTSCOPE_TEMPERATURE", "0.2")

    settings = RuntimeSettings.from_env()

    assert settings.provider_options == OpenAIOptions(
        max_tokens=1024,
        temperature=0.2,
    )
    assert settings.provider_options.thinking_enable is False


def test_luban_provider_options_thinking_opt_in(monkeypatch):
    monkeypatch.setenv("AGENTSCOPE_PROVIDER", "luban")
    monkeypatch.setenv("LUBAN_THINKING_ENABLE", "true")

    settings = RuntimeSettings.from_env()

    assert settings.provider_options.thinking_enable is True


def test_runtime_settings_reject_mismatched_provider_options():
    try:
        RuntimeSettings(
            provider="deepseek",
            provider_options=DashScopeOptions(),
        )
    except ValueError as exc:
        assert "provider_options type does not match" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Mismatched provider options should be rejected")


# ---------------------------------------------------------------------------
# SPEC-017 R-1: kernel utilization settings
# ---------------------------------------------------------------------------


def test_kernel_settings_defaults_match_agentscope(monkeypatch):
    """Unset deployments behave exactly as before the settings existed."""
    for name in (
        "AGENTSCOPE_MAX_ITERS",
        "AGENTSCOPE_CONTEXT_TRIGGER_RATIO",
        "AGENTSCOPE_TOOL_RESULT_LIMIT",
        "AGENTSCOPE_TIMEZONE",
        "AGENTSCOPE_MODEL_MAX_RETRIES",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = RuntimeSettings.from_env()

    assert settings.max_iters == 20
    assert settings.context_trigger_ratio == 0.8
    assert settings.tool_result_limit == 50000
    assert settings.timezone == "UTC"
    assert settings.model_max_retries == 0


def test_kernel_settings_read_env(monkeypatch):
    monkeypatch.setenv("AGENTSCOPE_MAX_ITERS", "30")
    monkeypatch.setenv("AGENTSCOPE_CONTEXT_TRIGGER_RATIO", "0.6")
    monkeypatch.setenv("AGENTSCOPE_TOOL_RESULT_LIMIT", "20000")
    monkeypatch.setenv("AGENTSCOPE_TIMEZONE", "Asia/Shanghai")
    monkeypatch.setenv("AGENTSCOPE_MODEL_MAX_RETRIES", "2")

    settings = RuntimeSettings.from_env()

    assert settings.max_iters == 30
    assert settings.context_trigger_ratio == 0.6
    assert settings.tool_result_limit == 20000
    assert settings.timezone == "Asia/Shanghai"
    assert settings.model_max_retries == 2


def test_kernel_settings_reject_zero_max_iters():
    try:
        RuntimeSettings(max_iters=0)
    except ValueError as exc:
        assert "AGENTSCOPE_MAX_ITERS" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("max_iters < 1 should be rejected")


@pytest.mark.parametrize("ratio", [0.0, -0.1, 0.9, 1.2])
def test_kernel_settings_reject_out_of_range_trigger_ratio(ratio):
    # agentscope ContextConfig requires 0 < trigger_ratio < 0.9.
    try:
        RuntimeSettings(context_trigger_ratio=ratio)
    except ValueError as exc:
        assert "AGENTSCOPE_CONTEXT_TRIGGER_RATIO" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError(f"trigger_ratio={ratio} should be rejected")


def test_kernel_settings_reject_zero_tool_result_limit():
    try:
        RuntimeSettings(tool_result_limit=0)
    except ValueError as exc:
        assert "AGENTSCOPE_TOOL_RESULT_LIMIT" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("tool_result_limit < 1 should be rejected")


def test_kernel_settings_reject_negative_model_max_retries():
    try:
        RuntimeSettings(model_max_retries=-1)
    except ValueError as exc:
        assert "AGENTSCOPE_MODEL_MAX_RETRIES" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("model_max_retries < 0 should be rejected")


def test_kernel_settings_reject_unknown_timezone():
    try:
        RuntimeSettings(timezone="Mars/Olympus_Mons")
    except ValueError as exc:
        assert "AGENTSCOPE_TIMEZONE" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Unknown timezone should be rejected")


def test_default_system_prompt_is_format_neutral_for_triage():
    """SPEC-017 R-2: structured output is delivered through the kernel's
    structured-output tool when active; the prompt must not hard-wire the
    fenced-block format as the only channel."""
    assert "structured-output" in DEFAULT_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# SPEC-018: kernel middleware settings
# ---------------------------------------------------------------------------


def test_middleware_settings_default_to_off(monkeypatch):
    """All SPEC-018 knobs are opt-in: unset deployments behave exactly as
    before the middleware migration."""
    for name in (
        "AGENTSCOPE_KERNEL_TRACING",
        "AGENTSCOPE_REPLY_TOKEN_BUDGET",
        "AGENTSCOPE_REPLY_INPUT_TOKEN_WEIGHT",
        "AGENTSCOPE_REPLY_OUTPUT_TOKEN_WEIGHT",
        "AGENTSCOPE_TASK_TOOLS_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = RuntimeSettings.from_env()

    assert settings.kernel_tracing is False
    assert settings.reply_token_budget is None
    assert settings.reply_input_token_weight == 1.0
    assert settings.reply_output_token_weight == 1.0
    assert settings.task_tools_enabled is False


def test_middleware_settings_read_env(monkeypatch):
    monkeypatch.setenv("AGENTSCOPE_KERNEL_TRACING", "true")
    monkeypatch.setenv("AGENTSCOPE_REPLY_TOKEN_BUDGET", "20000")
    monkeypatch.setenv("AGENTSCOPE_REPLY_INPUT_TOKEN_WEIGHT", "0.5")
    monkeypatch.setenv("AGENTSCOPE_REPLY_OUTPUT_TOKEN_WEIGHT", "2.0")
    monkeypatch.setenv("AGENTSCOPE_TASK_TOOLS_ENABLED", "yes")

    settings = RuntimeSettings.from_env()

    assert settings.kernel_tracing is True
    assert settings.reply_token_budget == 20000.0
    assert settings.reply_input_token_weight == 0.5
    assert settings.reply_output_token_weight == 2.0
    assert settings.task_tools_enabled is True


def test_middleware_settings_weight_zero_is_valid(monkeypatch):
    """Regression guard: an explicit 0.0 weight (e.g. count output tokens
    only) must survive parsing — a truthiness fallback would turn it into
    1.0."""
    monkeypatch.setenv("AGENTSCOPE_REPLY_INPUT_TOKEN_WEIGHT", "0")
    monkeypatch.setenv("AGENTSCOPE_REPLY_OUTPUT_TOKEN_WEIGHT", "0.0")

    settings = RuntimeSettings.from_env()

    assert settings.reply_input_token_weight == 0.0
    assert settings.reply_output_token_weight == 0.0


@pytest.mark.parametrize("budget", ["0", "-5"])
def test_middleware_settings_reject_nonpositive_budget(monkeypatch, budget):
    monkeypatch.setenv("AGENTSCOPE_REPLY_TOKEN_BUDGET", budget)

    try:
        RuntimeSettings.from_env()
    except ValueError as exc:
        assert "AGENTSCOPE_REPLY_TOKEN_BUDGET" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError(f"budget={budget} should be rejected")


@pytest.mark.parametrize(
    "env_name",
    ["AGENTSCOPE_REPLY_INPUT_TOKEN_WEIGHT", "AGENTSCOPE_REPLY_OUTPUT_TOKEN_WEIGHT"],
)
def test_middleware_settings_reject_negative_weight(monkeypatch, env_name):
    monkeypatch.setenv(env_name, "-0.5")

    try:
        RuntimeSettings.from_env()
    except ValueError as exc:
        assert env_name in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError(f"{env_name}=-0.5 should be rejected")


@pytest.mark.parametrize(
    "env_name",
    ["AGENTSCOPE_KERNEL_TRACING", "AGENTSCOPE_TASK_TOOLS_ENABLED"],
)
def test_middleware_settings_reject_non_boolean(monkeypatch, env_name):
    monkeypatch.setenv(env_name, "maybe")

    try:
        RuntimeSettings.from_env()
    except ValueError as exc:
        assert env_name in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError(f"{env_name}=maybe should be rejected")


def test_hitl_confirm_timeout_defaults_and_reads_env(monkeypatch):
    """SPEC-020 R-2: parked-confirmation TTL; 0 disables the bridge."""
    monkeypatch.delenv("AGENT_HITL_CONFIRM_TIMEOUT", raising=False)
    assert RuntimeSettings.from_env().hitl_confirm_timeout == 600

    monkeypatch.setenv("AGENT_HITL_CONFIRM_TIMEOUT", "0")
    assert RuntimeSettings.from_env().hitl_confirm_timeout == 0

    monkeypatch.setenv("AGENT_HITL_CONFIRM_TIMEOUT", "120")
    assert RuntimeSettings.from_env().hitl_confirm_timeout == 120


def test_hitl_confirm_timeout_rejects_negative(monkeypatch):
    monkeypatch.setenv("AGENT_HITL_CONFIRM_TIMEOUT", "-1")

    try:
        RuntimeSettings.from_env()
    except ValueError as exc:
        assert "AGENT_HITL_CONFIRM_TIMEOUT" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("AGENT_HITL_CONFIRM_TIMEOUT=-1 should be rejected")
