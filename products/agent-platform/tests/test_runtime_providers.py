from agent_service.providers import get_provider
from agent_service.providers.base import ProviderConfigurationError


def test_provider_registry_returns_deepseek_adapter():
    provider = get_provider("deepseek")

    assert provider.provider_name == "deepseek"
    assert provider.default_model == "deepseek-v4-flash"


def test_provider_registry_rejects_unknown_provider():
    try:
        get_provider("unknown")
    except ProviderConfigurationError as exc:
        assert "Supported providers" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Unknown providers should be rejected")
