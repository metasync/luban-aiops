from agent_service.core import config
from agent_service.services import runtime_dependencies


def test_get_settings_reads_env_once(monkeypatch):
    config.get_settings.cache_clear()
    monkeypatch.setenv("AGENTSCOPE_PROVIDER", "deepseek")
    monkeypatch.setenv("AGENTSCOPE_API_KEY", "test-key")

    settings = config.get_settings()

    assert settings.provider == "deepseek"
    assert settings.api_key == "test-key"

    config.get_settings.cache_clear()


def test_get_runtime_kernel_is_cached(monkeypatch):
    config.get_settings.cache_clear()
    runtime_dependencies.get_runtime_kernel.cache_clear()
    monkeypatch.setenv("AGENTSCOPE_PROVIDER", "deepseek")
    monkeypatch.setenv("AGENTSCOPE_API_KEY", "test-key")

    first = runtime_dependencies.get_runtime_kernel()
    second = runtime_dependencies.get_runtime_kernel()

    assert first is second
    assert first.settings.provider == "deepseek"

    runtime_dependencies.get_runtime_kernel.cache_clear()
    config.get_settings.cache_clear()
