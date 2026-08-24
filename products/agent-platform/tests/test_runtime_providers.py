import sys
from types import SimpleNamespace

import pytest

from agent_service.providers import get_provider
from agent_service.providers.base import ProviderConfigurationError
from agent_service.runtime_settings import OpenAIOptions, RuntimeSettings


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


# ---------------------------------------------------------------------------
# SPEC-028: luban (team-hosted) provider adapter
# ---------------------------------------------------------------------------


def test_luban_adapter_shape():
    adapter = get_provider("luban")
    assert adapter.provider_name == "luban"
    # No well-known public endpoint: the base URL is operator-declared.
    assert adapter.default_base_url is None
    # No curated series: only the force-included default model is served
    # when neither LUBAN_MODELS nor live discovery is available (R-3).
    assert adapter.model_series == ()


def test_luban_discover_filter_is_permissive():
    """R-3: no family prefixes — self-hosted names have no vendor taxonomy,
    but the shared dated-snapshot / non-chat marker hygiene still applies."""
    adapter = get_provider("luban")
    assert adapter.discover_filter("qwen3-8b") is True
    assert adapter.discover_filter("llama3.2:3b") is True
    assert adapter.discover_filter("team-finetune-v2") is True
    assert adapter.discover_filter("qwen3-8b-2026-08-01") is False
    assert adapter.discover_filter("text-embedding-v3") is False


def test_luban_validate_requires_base_url():
    """R-1: the active-provider path fails closed without a base URL."""
    adapter = get_provider("luban")
    with pytest.raises(ProviderConfigurationError, match="LUBAN_BASE_URL"):
        adapter.validate(
            RuntimeSettings(provider="luban", api_key="tok-luban")
        )
    adapter.validate(
        RuntimeSettings(
            provider="luban",
            api_key="tok-luban",
            base_url="http://ollama:11434/v1",
        )
    )


class _FakeParameters:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeChatModel:
    Parameters = _FakeParameters

    def __init__(self, credential, model, parameters):
        self.credential = credential
        self.model = model
        self.parameters = parameters


def _stub_agentscope_openai(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "agentscope.credential",
        SimpleNamespace(OpenAICredential=lambda **kw: kw),
    )
    monkeypatch.setitem(
        sys.modules,
        "agentscope.model",
        SimpleNamespace(OpenAIChatModel=_FakeChatModel),
    )


def test_luban_build_model_defaults_thinking_off(monkeypatch):
    """R-2/R-4: bearer auth against the declared endpoint, thinking off,
    no reasoning effort — the small-model-safe parameter set."""
    _stub_agentscope_openai(monkeypatch)
    adapter = get_provider("luban")
    settings = RuntimeSettings(
        provider="luban",
        api_key="tok-luban",
        base_url="http://ollama.llm-hosting.svc:11434/v1",
        model_name="qwen3-8b",
    )

    model = adapter.build_model(settings)

    assert model.credential == {
        "api_key": "tok-luban",
        "base_url": "http://ollama.llm-hosting.svc:11434/v1",
    }
    assert model.model == "qwen3-8b"
    assert model.parameters.kwargs["thinking_enable"] is False
    assert model.parameters.kwargs["reasoning_effort"] is None


def test_luban_build_model_honors_thinking_opt_in(monkeypatch):
    _stub_agentscope_openai(monkeypatch)
    adapter = get_provider("luban")
    settings = RuntimeSettings(
        provider="luban",
        api_key="tok-luban",
        base_url="http://ollama:11434/v1",
        provider_options=OpenAIOptions(thinking_enable=True),
    )

    model = adapter.build_model(settings)

    assert model.parameters.kwargs["thinking_enable"] is True


def test_luban_build_model_rejects_missing_base_url(monkeypatch):
    _stub_agentscope_openai(monkeypatch)
    adapter = get_provider("luban")
    settings = RuntimeSettings(provider="luban", api_key="tok-luban")
    with pytest.raises(ProviderConfigurationError, match="LUBAN_BASE_URL"):
        adapter.build_model(settings)
