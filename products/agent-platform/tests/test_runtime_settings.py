from agent_service.native_service import NativeServiceSettings
from agent_service.runtime_settings import RuntimeSettings


def test_runtime_settings_defaults(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("AGENTSCOPE_AGENT_NAME", raising=False)
    settings = RuntimeSettings.from_env()

    assert settings.agent_name == "LubanOpsRuntime"
    assert settings.model_name == "qwen-plus"
    assert settings.is_configured() is False


def test_runtime_settings_reads_env(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("AGENTSCOPE_MODEL_NAME", "qwen-max")
    settings = RuntimeSettings.from_env()

    assert settings.dashscope_api_key == "test-key"
    assert settings.model_name == "qwen-max"
    assert settings.is_configured() is True


def test_native_service_settings_reads_env(monkeypatch):
    monkeypatch.setenv("AGENTSCOPE_REDIS_HOST", "redis.internal")
    monkeypatch.setenv("AGENTSCOPE_REDIS_PORT", "6380")
    monkeypatch.setenv("AGENTSCOPE_WORKSPACE_DIR", "/tmp/agent-platform")
    monkeypatch.setenv("AGENT_SERVICE_PORT", "8090")

    settings = NativeServiceSettings.from_env()

    assert settings.redis_host == "redis.internal"
    assert settings.redis_port == 6380
    assert settings.workspace_dir == "/tmp/agent-platform"
    assert settings.port == 8090
