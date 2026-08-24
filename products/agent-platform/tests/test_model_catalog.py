"""Model catalog tests (SPEC-024 R-1, extended by SPEC-026).

Exercises the credential-gated catalog derivation: per-provider env knobs,
AGENTSCOPE_* fallback for the active provider, drop-without-key, per-model
series entries with model-name ids, ``<PROVIDER>_MODELS`` overrides,
default flagging, legacy provider-name aliases, the duplicate-id guard,
and the credential-free discovery view.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from agent_service.app import create_app
from agent_service.providers import get_provider
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services.model_catalog import (
    ModelCatalog,
    ModelCatalogEntry,
    _legacy_aliases,
    build_model_catalog,
)

CATALOG_ENV_KNOBS = (
    "DASHSCOPE_API_KEY",
    "DASHSCOPE_MODEL_NAME",
    "DASHSCOPE_BASE_URL",
    "DASHSCOPE_MODELS",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_MODEL_NAME",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODELS",
    "OPENAI_API_KEY",
    "OPENAI_MODEL_NAME",
    "OPENAI_BASE_URL",
    "OPENAI_MODELS",
)

DEEPSEEK_SERIES = get_provider("deepseek").model_series


@pytest.fixture
def clean_env(monkeypatch):
    for name in CATALOG_ENV_KNOBS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _settings(**overrides) -> RuntimeSettings:
    kwargs = {"provider": "deepseek", "api_key": "sk-active"}
    kwargs.update(overrides)
    return RuntimeSettings(**kwargs)


def _catalog(settings: RuntimeSettings) -> ModelCatalog:
    entries = build_model_catalog(settings)
    return ModelCatalog(entries, _legacy_aliases(entries, settings))


def test_active_provider_falls_back_to_agentscope_settings(clean_env):
    """The deploy-time profile needs zero new knobs (plan §D-1)."""
    entries = build_model_catalog(_settings(model_name="deepseek-chat"))
    by_id = {e.id: e for e in entries}
    # SPEC-026: ids are model names; the configured model is the default.
    assert set(by_id) == set(DEEPSEEK_SERIES)
    entry = by_id["deepseek-chat"]
    assert entry.api_key == "sk-active"
    assert entry.default is True
    assert sum(1 for e in entries if e.default) == 1


def test_active_provider_uses_adapter_defaults_when_unconfigured(clean_env):
    entries = build_model_catalog(_settings())
    by_id = {e.id: e for e in entries}
    assert set(by_id) == set(DEEPSEEK_SERIES)
    entry = by_id["deepseek-v4-flash"]
    assert entry.label == "deepseek-v4-flash"
    assert entry.base_url == "https://api.deepseek.com"
    assert entry.default is True


def test_additional_provider_contributes_its_full_series(clean_env):
    clean_env.setenv("OPENAI_API_KEY", "sk-openai")
    entries = build_model_catalog(_settings())
    by_id = {e.id: e for e in entries}
    openai_series = get_provider("openai").model_series
    assert set(by_id) == set(DEEPSEEK_SERIES) | set(openai_series)
    for name in openai_series:
        entry = by_id[name]
        assert entry.provider == "openai"
        assert entry.api_key == "sk-openai"
        assert entry.base_url is None  # OpenAI adapter has no default base URL
        assert entry.default is False


def test_per_provider_knobs_override_adapter_defaults(clean_env):
    clean_env.setenv("OPENAI_API_KEY", "sk-openai")
    clean_env.setenv("OPENAI_MODEL_NAME", "gpt-5")
    clean_env.setenv("OPENAI_BASE_URL", "https://proxy.internal/v1")
    entries = build_model_catalog(_settings())
    by_id = {e.id: e for e in entries if e.provider == "openai"}
    # The configured model is force-included ahead of the curated series.
    assert list(by_id)[0] == "gpt-5"
    assert all(e.base_url == "https://proxy.internal/v1" for e in by_id.values())


def test_models_override_replaces_curated_series(clean_env):
    clean_env.setenv("DEEPSEEK_MODELS", "deepseek-chat, deepseek-reasoner")
    entries = build_model_catalog(_settings())
    # The default model stays force-included even if the override omits it.
    assert [e.id for e in entries] == [
        "deepseek-v4-flash",
        "deepseek-chat",
        "deepseek-reasoner",
    ]


def test_empty_models_override_is_inert(clean_env):
    clean_env.setenv("DEEPSEEK_MODELS", " , ,")
    entries = build_model_catalog(_settings())
    assert {e.id for e in entries} == set(DEEPSEEK_SERIES)


def test_duplicate_model_ids_fail_startup(clean_env):
    clean_env.setenv("OPENAI_API_KEY", "sk-openai")
    clean_env.setenv("OPENAI_MODELS", "deepseek-chat")
    with pytest.raises(ValueError, match="Duplicate model id"):
        build_model_catalog(_settings())


def test_per_provider_knobs_never_fall_back_to_agentscope_key(clean_env):
    """A non-active provider must not inherit AGENTSCOPE_API_KEY."""
    clean_env.setenv("OPENAI_MODEL_NAME", "gpt-5")  # model without key
    entries = build_model_catalog(_settings())
    assert {e.provider for e in entries} == {"deepseek"}


def test_providers_without_keys_are_dropped(clean_env):
    entries = build_model_catalog(_settings())
    assert {e.provider for e in entries} == {"deepseek"}


def test_empty_catalog_allowed_when_nothing_configured(clean_env):
    entries = build_model_catalog(_settings(provider="dashscope", api_key=None))
    assert entries == ()
    catalog = ModelCatalog(entries)
    assert catalog.default_entry() is None
    assert catalog.public_models() == {"models": [], "default": None}


def test_public_view_never_exposes_credentials(clean_env):
    clean_env.setenv("OPENAI_API_KEY", "sk-openai")
    catalog = _catalog(_settings())
    payload = catalog.public_models()
    assert payload["default"] == "deepseek-v4-flash"
    serialized = str(payload)
    assert "sk-openai" not in serialized
    assert "sk-active" not in serialized
    assert "api_key" not in serialized
    assert "base_url" not in serialized
    for model in payload["models"]:
        assert set(model) == {"id", "label", "provider", "default"}


def test_catalog_lookup_fails_closed_for_unknown_ids(clean_env):
    catalog = _catalog(_settings())
    assert catalog.get("deepseek-chat") is not None
    assert catalog.get("bogus") is None
    assert catalog.get("") is None


def test_catalog_aliases_legacy_provider_ids(clean_env):
    """Pre-SPEC-026 ids (bare provider names) alias to the provider default."""
    clean_env.setenv("OPENAI_API_KEY", "sk-openai")
    catalog = _catalog(_settings())
    aliased = catalog.get("deepseek")
    assert aliased is not None
    assert aliased.id == "deepseek-v4-flash"
    assert catalog.get("openai").id == "gpt-4o-mini"
    # Aliases never shadow real entries or invent providers.
    assert catalog.get("dashscope") is None


def test_unknown_provider_config_fails_startup(clean_env):
    """Unknown AGENTSCOPE_PROVIDER is rejected by settings (R-1 posture)."""
    clean_env.setenv("AGENTSCOPE_PROVIDER", "anthropic")
    with pytest.raises(ValueError, match="Unsupported AGENTSCOPE_PROVIDER"):
        RuntimeSettings.from_env()


# --- Discovery route (SPEC-024 R-2) ---

SCHEMAS_DIR = (
    Path(__file__).resolve().parents[3] / "shared" / "shared-contracts" / "schemas"
)


def test_models_route_returns_contract_shaped_catalog(monkeypatch):
    """GET /api/v2/models exposes only id/label/provider/default."""
    catalog = ModelCatalog(
        (
            ModelCatalogEntry(
                id="deepseek-v4-flash",
                label="deepseek-v4-flash",
                provider="deepseek",
                api_key="sk-secret",
                model_name="deepseek-v4-flash",
                base_url="https://api.deepseek.com",
                default=True,
            ),
        )
    )
    monkeypatch.setattr(
        "agent_service.api.v2.routes.MODEL_CATALOG", catalog
    )
    client = TestClient(create_app())
    response = client.get("/api/v2/models", headers={"X-User-ID": "alice"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["default"] == "deepseek-v4-flash"
    assert "sk-secret" not in json.dumps(payload)
    schema = json.loads((SCHEMAS_DIR / "model-catalog.schema.json").read_text())
    jsonschema.validate(payload, schema)


def test_models_route_requires_user_id_header():
    client = TestClient(create_app())
    response = client.get("/api/v2/models")
    assert response.status_code in {400, 401, 403}


def test_models_route_empty_catalog_is_not_an_error(monkeypatch):
    monkeypatch.setattr(
        "agent_service.api.v2.routes.MODEL_CATALOG", ModelCatalog(())
    )
    client = TestClient(create_app())
    response = client.get("/api/v2/models", headers={"X-User-ID": "alice"})
    assert response.status_code == 200
    assert response.json() == {"models": [], "default": None}
