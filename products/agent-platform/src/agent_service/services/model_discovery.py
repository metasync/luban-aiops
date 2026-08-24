"""Live model discovery with cached fallback (SPEC-027).

Periodically re-resolves each configured provider's model series from
its OpenAI-compatible ``/models`` endpoint behind a fail-soft ladder
(R-2):

    live fetch -> in-memory last-good -> Postgres last-good -> curated

Successful fetches update both cache tiers and atomically swap the
catalog via :func:`agent_service.services.model_catalog.refresh_catalog`.
The persistent tier lives in the sessions Postgres (``SESSION_DB_URL``),
keeping Redis coupled exclusively to the AgentScope kernel message bus
(ADR-0003 framework-swap hygiene). Every failure path is logged and
swallowed: discovery can never block chat or startup.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx

from agent_service.core.metrics import (
    record_model_discovery_models,
    record_model_discovery_refresh,
)
from agent_service.providers import get_provider
from agent_service.runtime_settings import RuntimeProvider, RuntimeSettings
from agent_service.services.model_catalog import (
    ProviderCredentials,
    curated_series,
    force_include_default,
    refresh_catalog,
)

LOGGER = logging.getLogger(__name__)


_BOOTSTRAP_SQL = (
    "CREATE TABLE IF NOT EXISTS model_discovery_cache ("
    "provider TEXT PRIMARY KEY, "
    "models JSONB NOT NULL, "
    "updated_at TIMESTAMPTZ NOT NULL DEFAULT now());"
)
_UPSERT_SQL = (
    "INSERT INTO model_discovery_cache (provider, models) "
    "VALUES (%(provider)s, %(models)s) "
    "ON CONFLICT (provider) DO UPDATE "
    "SET models = EXCLUDED.models, updated_at = now();"
)
_READ_SQL = (
    "SELECT models FROM model_discovery_cache WHERE provider = %(provider)s;"
)


def _sessions_db_url() -> str | None:
    """Sessions Postgres DSN; the cache tier degrades away when absent."""
    for name in ("SESSION_DB_URL", "AGENT_STATE_DB_URL"):
        value = os.getenv(name, "").strip()
        if value:
            return value
    return None


class PostgresDiscoveryCache:
    """Best-effort last-good persistence in the sessions Postgres.

    Mirrors the sessions-store bootstrap pattern (``CREATE TABLE IF NOT
    EXISTS`` on first use). All failures are logged and swallowed — the
    ladder simply skips this tier when Postgres is unreachable.
    """

    def __init__(self, db_url: str) -> None:
        self._db_url = db_url
        self._bootstrapped = False

    def _connect(self) -> Any:
        import psycopg

        conn = psycopg.connect(
            self._db_url, autocommit=True, connect_timeout=5
        )
        try:
            if not self._bootstrapped:
                with conn.cursor() as cursor:
                    cursor.execute(_BOOTSTRAP_SQL)
                self._bootstrapped = True
        except Exception:
            # A bootstrap failure must not leak the open connection —
            # callers only see the exception out of _connect().
            conn.close()
            raise
        return conn

    def read(self, provider: str) -> tuple[str, ...] | None:
        try:
            conn = self._connect()
        except Exception:
            LOGGER.warning(
                "model discovery cache: postgres unreachable for read (%s)",
                provider,
            )
            return None
        try:
            with conn.cursor() as cursor:
                row = cursor.execute(
                    _READ_SQL, {"provider": provider}
                ).fetchone()
        except Exception:
            LOGGER.warning(
                "model discovery cache: read failed (%s)", provider
            )
            return None
        finally:
            conn.close()
        if row is None:
            return None
        payload = row[0]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (TypeError, ValueError):
                return None
        if not isinstance(payload, list):
            return None
        models = tuple(
            item for item in payload if isinstance(item, str) and item
        )
        return models or None

    def write(self, provider: str, models: tuple[str, ...]) -> None:
        try:
            conn = self._connect()
        except Exception:
            LOGGER.warning(
                "model discovery cache: postgres unreachable for write (%s)",
                provider,
            )
            return
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    _UPSERT_SQL,
                    {
                        "provider": provider,
                        "models": json.dumps(list(models)),
                    },
                )
        except Exception:
            LOGGER.warning(
                "model discovery cache: write failed (%s)", provider
            )
        finally:
            conn.close()


async def fetch_provider_models(
    credentials: ProviderCredentials,
    timeout_seconds: float,
) -> tuple[str, ...] | None:
    """Live ``GET /models`` against the provider's OpenAI-compatible API.

    Returns the raw advertised ids (no filtering), or None on any
    failure — the ladder treats every error the same way (R-2).
    """
    if not credentials.base_url:
        return None
    url = credentials.base_url.rstrip("/") + "/models"
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {credentials.api_key}"},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception:
        LOGGER.warning(
            "model discovery: live fetch failed for %s", credentials.provider
        )
        return None
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        LOGGER.warning(
            "model discovery: unexpected /models envelope for %s",
            credentials.provider,
        )
        return None
    models = []
    for item in items:
        if isinstance(item, dict):
            model_id = item.get("id")
            if isinstance(model_id, str) and model_id:
                models.append(model_id)
    return tuple(models)


class ModelDiscoveryService:
    """Ladder resolver + periodic catalog refresh for one process.

    Constructed once from the startup settings; the lifespan task in
    ``app.py`` runs :meth:`run_loop` (initial fetch, then sleep loop).
    """

    def __init__(
        self,
        settings: RuntimeSettings,
        credentials: tuple[ProviderCredentials, ...],
    ) -> None:
        self._settings = settings
        self._credentials = credentials
        db_url = _sessions_db_url()
        self._cache = PostgresDiscoveryCache(db_url) if db_url else None
        self._last_good: dict[RuntimeProvider, tuple[str, ...]] = {}

    def _apply_filter(
        self,
        credentials: ProviderCredentials,
        models: tuple[str, ...],
    ) -> tuple[str, ...]:
        """R-4: per-provider predicate, dedupe, force-include default."""
        adapter = get_provider(credentials.provider)
        filtered = tuple(
            model_id for model_id in models if adapter.discover_filter(model_id)
        )
        deduped = tuple(dict.fromkeys(filtered))
        return force_include_default(deduped, credentials.default_model)

    async def _resolve_series(
        self,
        credentials: ProviderCredentials,
    ) -> tuple[str, ...]:
        provider = credentials.provider
        if credentials.models_override is not None:
            # ``<PROVIDER>_MODELS`` stays authoritative (R-5):
            # deterministic pinning skips discovery for this provider.
            record_model_discovery_refresh(provider, "override")
            return force_include_default(
                credentials.models_override, credentials.default_model
            )
        if not self._settings.model_discovery_enabled:
            record_model_discovery_refresh(provider, "disabled")
            return curated_series(credentials)
        live = await fetch_provider_models(
            credentials, self._settings.model_discovery_timeout_seconds
        )
        if live is not None:
            series = self._apply_filter(credentials, live)
            self._last_good[provider] = series
            if self._cache is not None:
                await asyncio.to_thread(
                    self._cache.write, provider, series
                )
            record_model_discovery_refresh(provider, "live")
            return series
        memory = self._last_good.get(provider)
        if memory is not None:
            record_model_discovery_refresh(provider, "memory")
            return memory
        if self._cache is not None:
            cached = await asyncio.to_thread(self._cache.read, provider)
            if cached is not None:
                record_model_discovery_refresh(provider, "cache")
                return force_include_default(cached, credentials.default_model)
        record_model_discovery_refresh(provider, "curated")
        return curated_series(credentials)

    async def refresh_once(self) -> None:
        """Resolve every provider's series and swap the catalog (R-3)."""
        series_map: dict[RuntimeProvider, tuple[str, ...]] = {}
        for credentials in self._credentials:
            series = await self._resolve_series(credentials)
            series_map[credentials.provider] = series
            record_model_discovery_models(credentials.provider, len(series))
        refresh_catalog(series_map, self._settings)

    async def run_loop(self) -> None:
        """Initial refresh at startup, then periodic background swaps."""
        while True:
            try:
                await self.refresh_once()
            except Exception:
                LOGGER.exception("model discovery: refresh cycle failed")
            await asyncio.sleep(self._settings.model_discovery_refresh_seconds)


def build_discovery_service(
    settings: RuntimeSettings,
    credentials: tuple[ProviderCredentials, ...],
) -> ModelDiscoveryService | None:
    """The lifespan entry point; None when there is nothing to discover
    (discovery disabled, or no provider has a resolvable API key)."""
    if not settings.model_discovery_enabled or not credentials:
        return None
    return ModelDiscoveryService(settings, credentials)
