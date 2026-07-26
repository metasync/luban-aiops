from agent_service.native_service import NativeServiceSettings
from agent_service.runtime_settings import (
    DashScopeOptions,
    DeepSeekOptions,
    OpenAIOptions,
    RuntimeSettings,
)


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


def test_runtime_settings_rejects_unknown_profile(monkeypatch):
    monkeypatch.setenv("AGENTSCOPE_PROFILE", "unknown")

    try:
        RuntimeSettings.from_env()
    except ValueError as exc:
        assert "AGENTSCOPE_PROFILE" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("RuntimeSettings.from_env() should reject unknown profiles")


def test_runtime_settings_rejects_mismatched_profile_and_provider(monkeypatch):
    monkeypatch.setenv("AGENTSCOPE_PROFILE", "dashscope")
    monkeypatch.setenv("AGENTSCOPE_PROVIDER", "deepseek")

    try:
        RuntimeSettings.from_env()
    except ValueError as exc:
        assert "AGENTSCOPE_PROFILE must match AGENTSCOPE_PROVIDER" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Mismatched profile/provider should be rejected")


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
