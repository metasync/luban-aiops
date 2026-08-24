"""Live model discovery tests (SPEC-027).

Exercises the fallback ladder levels (live -> memory -> postgres -> curated),
the per-provider filter predicates, override precedence, the enable knob,
the Postgres last-good tier against a stubbed psycopg driver, and the
httpx fetch parsing.
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from agent_service.providers import get_provider
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services import model_discovery
from agent_service.services.model_catalog import (
    ModelCatalog,
    ProviderCredentials,
    build_aliases,
    build_model_catalog,
)
from agent_service.services.model_discovery import (
    ModelDiscoveryService,
    PostgresDiscoveryCache,
    build_discovery_service,
    fetch_provider_models,
)

CATALOG_ENV_KNOBS = (
    "DASHSCOPE_API_KEY",
    "DASHSCOPE_MODELS",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_MODELS",
    "OPENAI_API_KEY",
    "OPENAI_MODELS",
    "SESSION_DB_URL",
    "AGENT_STATE_DB_URL",
)


@pytest.fixture
def clean_env(monkeypatch):
    for name in CATALOG_ENV_KNOBS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _settings(**overrides) -> RuntimeSettings:
    kwargs = {"provider": "deepseek", "api_key": "sk-active"}
    kwargs.update(overrides)
    return RuntimeSettings(**kwargs)


def _credentials(**overrides) -> ProviderCredentials:
    kwargs = {
        "provider": "deepseek",
        "api_key": "sk-test",
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-v4-flash",
        "models_override": None,
    }
    kwargs.update(overrides)
    return ProviderCredentials(**kwargs)


class FakeCache:
    """Stubbed Postgres tier with an in-memory backing store."""

    def __init__(self, stored=None):
        self.stored = dict(stored or {})
        self.writes: list[tuple[str, tuple[str, ...]]] = []

    def read(self, provider):
        return self.stored.get(provider)

    def write(self, provider, models):
        self.writes.append((provider, models))
        self.stored[provider] = models


@pytest.fixture
def patch_fetch(monkeypatch):
    """Route the service through a controllable fetch double."""
    calls: list[str] = []

    async def fake_fetch(credentials, timeout_seconds):
        calls.append(credentials.provider)
        return fake_fetch.payload

    fake_fetch.calls = calls
    fake_fetch.payload = None
    monkeypatch.setattr(model_discovery, "fetch_provider_models", fake_fetch)
    return fake_fetch


def _patched_catalog(monkeypatch, settings) -> ModelCatalog:
    """Point the module singleton at a fresh catalog for swap checks."""
    entries = build_model_catalog(settings)
    catalog = ModelCatalog(entries, build_aliases(entries, settings))
    monkeypatch.setattr(
        "agent_service.services.model_catalog.MODEL_CATALOG", catalog
    )
    return catalog


def _refresh_once(service) -> None:
    asyncio.run(service.refresh_once())


# --- Filter predicates (R-4) ---


def test_discover_filter_drops_dated_snapshots():
    adapter = get_provider("dashscope")
    assert adapter.discover_filter("qwen-plus-2025-04-28") is False
    assert adapter.discover_filter("qwen-plus") is True


def test_discover_filter_drops_non_chat_modalities():
    openai = get_provider("openai")
    assert openai.discover_filter("gpt-4o-audio-preview") is False
    assert openai.discover_filter("text-embedding-3-small") is False
    dashscope = get_provider("dashscope")
    assert dashscope.discover_filter("qwen-vl-max") is False
    assert dashscope.discover_filter("qwen-mt-turbo") is False
    assert dashscope.discover_filter("qwen-omni-turbo") is False
    assert dashscope.discover_filter("gte-rerank-v2") is False


def test_discover_filter_accepts_chat_families():
    assert get_provider("deepseek").discover_filter("deepseek-v4-flash")
    assert get_provider("openai").discover_filter("gpt-4o")
    assert get_provider("openai").discover_filter("o3-mini")
    assert get_provider("dashscope").discover_filter("qwen3.8-max")


# --- Ladder levels (R-2) ---


def test_live_fetch_filters_swaps_and_caches(clean_env, monkeypatch, patch_fetch):
    settings = _settings()
    catalog = _patched_catalog(monkeypatch, settings)
    cache = FakeCache()
    patch_fetch.payload = (
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "deepseek-v4-flash-2026-01-01",  # dated snapshot -> dropped
        "deepseek-embeddings",            # modality -> dropped
        "other-vendor-model",             # outside family -> dropped
    )
    service = ModelDiscoveryService(settings, (_credentials(),))
    service._cache = cache

    _refresh_once(service)

    assert patch_fetch.calls == ["deepseek"]
    ids = [e.id for e in catalog.entries]
    assert ids == ["deepseek-v4-flash", "deepseek-v4-pro"]
    # Both cache tiers carry the last-good list.
    assert service._last_good["deepseek"] == (
        "deepseek-v4-flash",
        "deepseek-v4-pro",
    )
    assert cache.writes == [
        ("deepseek", ("deepseek-v4-flash", "deepseek-v4-pro"))
    ]


def test_live_failure_falls_back_to_memory(clean_env, monkeypatch, patch_fetch):
    settings = _settings()
    catalog = _patched_catalog(monkeypatch, settings)
    service = ModelDiscoveryService(settings, (_credentials(),))
    service._cache = FakeCache()
    memory_series = ("deepseek-v4-flash", "deepseek-v4-pro")
    service._last_good["deepseek"] = memory_series
    patch_fetch.payload = None

    _refresh_once(service)

    assert [e.id for e in catalog.entries] == list(memory_series)


def test_restart_hits_postgres_cache_when_live_fails(
    clean_env, monkeypatch, patch_fetch
):
    """Fresh process (empty memory) + dead provider -> Postgres tier wins,
    and the provider default is force-included back in."""
    settings = _settings()
    catalog = _patched_catalog(monkeypatch, settings)
    cache = FakeCache(stored={"deepseek": ("deepseek-v4-pro",)})
    service = ModelDiscoveryService(settings, (_credentials(),))
    service._cache = cache
    patch_fetch.payload = None

    _refresh_once(service)

    assert [e.id for e in catalog.entries] == [
        "deepseek-v4-flash",  # default force-included
        "deepseek-v4-pro",
    ]


def test_all_levels_miss_degrades_to_curated(
    clean_env, monkeypatch, patch_fetch
):
    settings = _settings()
    catalog = _patched_catalog(monkeypatch, settings)
    service = ModelDiscoveryService(settings, (_credentials(),))
    service._cache = FakeCache()  # empty postgres tier
    patch_fetch.payload = None

    _refresh_once(service)

    curated = get_provider("deepseek").model_series
    assert [e.id for e in catalog.entries] == list(curated)


def test_missing_pg_dsn_degrades_to_memory_only_tier(clean_env):
    service = ModelDiscoveryService(_settings(), (_credentials(),))
    assert service._cache is None


# --- Override precedence + enable knob (R-5) ---


def test_override_skips_discovery(clean_env, monkeypatch, patch_fetch):
    settings = _settings()
    catalog = _patched_catalog(monkeypatch, settings)
    creds = _credentials(models_override=("deepseek-chat",))
    service = ModelDiscoveryService(settings, (creds,))
    service._cache = FakeCache()

    _refresh_once(service)

    assert patch_fetch.calls == []  # deterministic pinning, no live fetch
    assert [e.id for e in catalog.entries] == [
        "deepseek-v4-flash",  # default force-included
        "deepseek-chat",
    ]


def test_disabled_discovery_uses_curated(clean_env, monkeypatch, patch_fetch):
    settings = _settings(model_discovery_enabled=False)
    catalog = _patched_catalog(monkeypatch, settings)
    service = ModelDiscoveryService(settings, (_credentials(),))
    service._cache = FakeCache()

    _refresh_once(service)

    assert patch_fetch.calls == []
    curated = get_provider("deepseek").model_series
    assert [e.id for e in catalog.entries] == list(curated)


def test_build_discovery_service_gates(clean_env):
    credentials = (_credentials(),)
    assert build_discovery_service(_settings(), credentials) is not None
    # Disabled knob and zero configured providers both skip the task.
    assert (
        build_discovery_service(
            _settings(model_discovery_enabled=False), credentials
        )
        is None
    )
    assert build_discovery_service(_settings(), ()) is None


# --- Postgres cache tier (stubbed psycopg) ---


class FakeCursor:
    def __init__(self, rows=None):
        self.executed: list[tuple[str, dict | None]] = []
        self.rows = rows or []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return self

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, rows=None):
        self.cursor_obj = FakeCursor(rows)
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def _stub_psycopg(monkeypatch, conn):
    monkeypatch.setitem(
        sys.modules, "psycopg", SimpleNamespace(connect=lambda *a, **k: conn)
    )


def test_postgres_cache_round_trip(monkeypatch):
    conn = FakeConn(rows=(['["deepseek-v4-flash", "deepseek-v4-pro"]'],))
    _stub_psycopg(monkeypatch, conn)
    cache = PostgresDiscoveryCache("postgresql://fake")

    models = cache.read("deepseek")
    assert models == ("deepseek-v4-flash", "deepseek-v4-pro")
    bootstrap, read = conn.cursor_obj.executed
    assert "CREATE TABLE IF NOT EXISTS model_discovery_cache" in bootstrap[0]
    assert "SELECT models" in read[0]
    assert read[1] == {"provider": "deepseek"}
    assert conn.closed is True

    cache.write("deepseek", ("deepseek-v4-flash",))
    upsert = conn.cursor_obj.executed[-1]
    assert "ON CONFLICT (provider)" in upsert[0]
    assert upsert[1]["provider"] == "deepseek"
    assert upsert[1]["models"] == '["deepseek-v4-flash"]'


def test_postgres_cache_read_miss_and_failure_swallowed(monkeypatch):
    conn = FakeConn(rows=[])
    _stub_psycopg(monkeypatch, conn)
    cache = PostgresDiscoveryCache("postgresql://fake")
    assert cache.read("deepseek") is None

    def broken(*args, **kwargs):
        raise RuntimeError("postgres down")

    monkeypatch.setitem(
        sys.modules, "psycopg", SimpleNamespace(connect=broken)
    )
    # Never raises: the ladder skips the tier instead.
    assert cache.read("deepseek") is None
    cache.write("deepseek", ("deepseek-v4-flash",))


def test_postgres_cache_bootstrap_failure_closes_connection(monkeypatch):
    """A failing bootstrap DDL must not leak the opened connection —
    read/write swallow the error and retry on every refresh cycle.
    """
    conn = FakeConn()

    def broken_execute(sql, params=None):
        raise RuntimeError("permission denied")

    conn.cursor_obj.execute = broken_execute
    _stub_psycopg(monkeypatch, conn)
    cache = PostgresDiscoveryCache("postgresql://fake")

    assert cache.read("deepseek") is None
    assert conn.closed


# --- Live fetch parsing (mocked httpx) ---


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class FakeAsyncClient:
    requests: list[tuple[str, dict]] = []

    def __init__(self, response=None, timeout=None):
        self.response = response or FakeResponse({"data": []})
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        FakeAsyncClient.requests.append((url, headers or {}))
        return self.response


def test_fetch_parses_openai_envelope(monkeypatch):
    FakeAsyncClient.requests = []
    response = FakeResponse(
        {"data": [{"id": "deepseek-v4-flash"}, {"id": "deepseek-v4-pro"}, {}]}
    )
    monkeypatch.setattr(
        model_discovery.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(response, **kwargs),
    )

    models = asyncio.run(fetch_provider_models(_credentials(), 5.0))

    assert models == ("deepseek-v4-flash", "deepseek-v4-pro")
    url, headers = FakeAsyncClient.requests[0]
    assert url == "https://api.deepseek.com/models"
    assert headers["Authorization"] == "Bearer sk-test"


def test_fetch_returns_none_on_any_failure(monkeypatch):
    FakeAsyncClient.requests = []
    monkeypatch.setattr(
        model_discovery.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(FakeResponse({}, status=401), **kwargs),
    )
    assert asyncio.run(fetch_provider_models(_credentials(), 5.0)) is None

    monkeypatch.setattr(
        model_discovery.httpx,
        "AsyncClient",
        lambda **kwargs: FakeAsyncClient(FakeResponse({"unexpected": True})),
    )
    assert asyncio.run(fetch_provider_models(_credentials(), 5.0)) is None

    # No base URL at all: never hit the network.
    creds = _credentials(base_url=None)
    assert asyncio.run(fetch_provider_models(creds, 5.0)) is None
