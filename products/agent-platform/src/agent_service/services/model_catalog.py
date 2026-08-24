"""Credential-gated model catalog (SPEC-024 R-1, SPEC-026, SPEC-027).

The catalog derives the set of selectable LLM models from per-provider
environment knobs at startup. Each supported provider with a resolvable
API key contributes its model series — one entry per model, named by the
model name (SPEC-026 R-2):

- ``<PROVIDER>_API_KEY`` / ``<PROVIDER>_BASE_URL`` (e.g. ``OPENAI_API_KEY``)
  gate the provider; ``<PROVIDER>_MODELS`` optionally replaces the
  adapter's curated series (SPEC-026 R-4), and
- the active profile's provider (``AGENTSCOPE_PROVIDER``) additionally
  falls back to the existing ``AGENTSCOPE_API_KEY`` / ``AGENTSCOPE_MODEL_NAME``
  / ``AGENTSCOPE_BASE_URL`` knobs, so a single-provider deployment needs
  zero new configuration.

Providers without a resolvable API key are dropped. A zero-entry catalog
is allowed and degrades exactly like ``settings.is_configured() == False``
today (runtime metadata ``not_configured``). Entry ids are model names,
so chat requests select a model with e.g. ``"model": "qwen-plus"``; bare
provider names (the pre-SPEC-026 entry ids) alias to that provider's
default model for backward compatibility (SPEC-026 R-3).

Live model discovery (SPEC-027) periodically re-resolves each provider's
series from its ``/models`` endpoint behind a fail-soft ladder and swaps
the catalog contents in place via :meth:`ModelCatalog._swap` — the
``MODEL_CATALOG`` object reference imported by kernel and routes stays
valid across swaps. Credentials never leave this module: route layers
serialize ``to_public_dict()`` only.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass

from agent_service.providers import get_provider
from agent_service.runtime_settings import (
    SUPPORTED_RUNTIME_PROVIDERS,
    RuntimeProvider,
    RuntimeSettings,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelCatalogEntry:
    """One selectable model: a provider + credentials + concrete model."""

    id: str  # the model name (SPEC-026 R-2)
    label: str  # shown in the portal selector
    provider: RuntimeProvider
    api_key: str
    model_name: str
    base_url: str | None
    default: bool  # True only for the active profile's resolved model

    def to_public_dict(self) -> dict[str, object]:
        """Discovery-safe view: no credentials, no base URLs (SPEC-024 R-2)."""
        return {
            "id": self.id,
            "label": self.label,
            "provider": self.provider,
            "default": self.default,
        }


@dataclass(frozen=True)
class ProviderCredentials:
    """Resolved non-secret resolution state for one configured provider."""

    provider: RuntimeProvider
    api_key: str
    base_url: str | None
    default_model: str
    models_override: tuple[str, ...] | None


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _model_list(name: str) -> tuple[str, ...] | None:
    """Parse a ``<PROVIDER>_MODELS`` comma list (SPEC-026 R-4)."""
    value = _env(name)
    if value is None:
        return None
    parts = tuple(part.strip() for part in value.split(","))
    parts = tuple(part for part in parts if part)
    return parts or None


def resolve_credentials(
    provider: RuntimeProvider,
    settings: RuntimeSettings,
) -> ProviderCredentials | None:
    """Resolve credentials + defaults for one provider, or None (gated)."""
    prefix = provider.upper()
    api_key = _env(f"{prefix}_API_KEY")
    model_name = _env(f"{prefix}_MODEL_NAME")
    base_url = _env(f"{prefix}_BASE_URL")
    models_override = _model_list(f"{prefix}_MODELS")
    if provider == settings.provider:
        # The active profile's provider keeps working with the existing
        # AGENTSCOPE_* knobs (deploy-time default, zero-change upgrades).
        api_key = api_key or settings.api_key
        model_name = model_name or settings.model_name
        base_url = base_url or settings.base_url
    if not api_key:
        return None
    adapter = get_provider(provider)
    return ProviderCredentials(
        provider=provider,
        api_key=api_key,
        base_url=base_url or adapter.default_base_url,
        default_model=model_name or adapter.default_model,
        models_override=models_override,
    )


def configured_providers(
    settings: RuntimeSettings,
) -> tuple[ProviderCredentials, ...]:
    """Every supported provider whose API key resolves (credential gate)."""
    resolved = []
    for provider in SUPPORTED_RUNTIME_PROVIDERS:
        credentials = resolve_credentials(provider, settings)
        if credentials is not None:
            resolved.append(credentials)
    return tuple(resolved)


def force_include_default(
    models: tuple[str, ...],
    default_model: str,
) -> tuple[str, ...]:
    """The provider's default model is always selectable (SPEC-026 R-1)."""
    return tuple(dict.fromkeys((default_model, *models)))


def curated_series(credentials: ProviderCredentials) -> tuple[str, ...]:
    """SPEC-026 series resolution: override wins, else the adapter series."""
    adapter = get_provider(credentials.provider)
    series = (
        credentials.models_override
        if credentials.models_override is not None
        else adapter.model_series
    )
    return force_include_default(series, credentials.default_model)


def build_entries(
    series_map: Mapping[RuntimeProvider, tuple[str, ...]],
    settings: RuntimeSettings,
) -> tuple[ModelCatalogEntry, ...]:
    """Build catalog entries from per-provider series (curated fallback
    for providers missing from the map)."""
    entries: list[ModelCatalogEntry] = []
    for credentials in configured_providers(settings):
        models = series_map.get(credentials.provider)
        if models is None:
            models = curated_series(credentials)
        for name in models:
            entries.append(
                ModelCatalogEntry(
                    id=name,
                    label=name,
                    provider=credentials.provider,
                    api_key=credentials.api_key,
                    model_name=name,
                    base_url=credentials.base_url,
                    default=(
                        credentials.provider == settings.provider
                        and name == credentials.default_model
                    ),
                )
            )
    seen: dict[str, RuntimeProvider] = {}
    for entry in entries:
        if entry.id in seen:
            raise ValueError(
                f"Duplicate model id {entry.id!r} configured by providers "
                f"{seen[entry.id]!r} and {entry.provider!r}; model names "
                "must be unique across the catalog."
            )
        seen[entry.id] = entry.provider
    return tuple(entries)


def build_aliases(
    entries: tuple[ModelCatalogEntry, ...],
    settings: RuntimeSettings,
) -> dict[str, ModelCatalogEntry]:
    """Map bare provider names to each provider's default-model entry."""
    aliases: dict[str, ModelCatalogEntry] = {}
    for credentials in configured_providers(settings):
        entry = next(
            (e for e in entries if e.id == credentials.default_model), None
        )
        if entry is not None:
            aliases[credentials.provider] = entry
    return aliases


def build_model_catalog(settings: RuntimeSettings) -> tuple[ModelCatalogEntry, ...]:
    """Derive the startup (SPEC-026 curated) catalog from env + settings."""
    entries = build_entries({}, settings)
    LOGGER.info(
        "model catalog: %d model(s) enabled (default: %s)",
        len(entries),
        next((e.id for e in entries if e.default), "none"),
    )
    return entries


class ModelCatalog:
    """Immutable-per-snapshot lookup over the startup-derived catalog.

    SPEC-027 R-3: live discovery swaps the contents in place under a lock;
    readers snapshot the internal references, and the object identity that
    kernel/routes imported stays valid across swaps.
    """

    def __init__(
        self,
        entries: tuple[ModelCatalogEntry, ...],
        aliases: Mapping[str, ModelCatalogEntry] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._entries = entries
        self._by_id = {entry.id: entry for entry in entries}
        # Legacy aliases (SPEC-026 R-3): pre-SPEC-026 sessions and
        # requests carry bare provider names as model ids; each aliases
        # to that provider's default-model entry.
        self._aliases: dict[str, ModelCatalogEntry] = dict(aliases or {})

    def _swap(
        self,
        entries: tuple[ModelCatalogEntry, ...],
        aliases: Mapping[str, ModelCatalogEntry],
    ) -> None:
        with self._lock:
            self._entries = entries
            self._by_id = {entry.id: entry for entry in entries}
            self._aliases = dict(aliases)

    @property
    def entries(self) -> tuple[ModelCatalogEntry, ...]:
        with self._lock:
            return self._entries

    def get(self, model_id: str) -> ModelCatalogEntry | None:
        """Look up a model by name; bare provider names alias to the
        provider's default entry (SPEC-026 R-3)."""
        with self._lock:
            entry = self._by_id.get(model_id)
            if entry is not None:
                return entry
            return self._aliases.get(model_id)

    def default_entry(self) -> ModelCatalogEntry | None:
        with self._lock:
            return next((e for e in self._entries if e.default), None)

    def public_models(self) -> dict[str, object]:
        """Discovery payload per shared-contracts model-catalog schema."""
        with self._lock:
            entries = self._entries
        default = next((e for e in entries if e.default), None)
        return {
            "models": [entry.to_public_dict() for entry in entries],
            "default": default.id if default is not None else None,
        }


def refresh_catalog(
    series_map: Mapping[RuntimeProvider, tuple[str, ...]],
    settings: RuntimeSettings,
) -> bool:
    """Rebuild the catalog from discovered series and swap it in place.

    Fail-soft (SPEC-027 R-2): a misconfigured live list (duplicate ids)
    keeps the previous catalog instead of raising into the refresh loop.
    """
    try:
        entries = build_entries(series_map, settings)
    except ValueError as exc:
        LOGGER.error("model catalog refresh rejected, keeping previous: %s", exc)
        return False
    MODEL_CATALOG._swap(entries, build_aliases(entries, settings))
    LOGGER.info(
        "model catalog: refreshed to %d model(s) (default: %s)",
        len(entries),
        next((e.id for e in entries if e.default), "none"),
    )
    return True


# Module-level singleton — imported by runtime_kernel.py / routes, same
# posture as EVIDENCE_STORE in evidence_store.py.
_STARTUP_SETTINGS = RuntimeSettings.from_env()
_STARTUP_ENTRIES = build_model_catalog(_STARTUP_SETTINGS)
MODEL_CATALOG = ModelCatalog(
    _STARTUP_ENTRIES, build_aliases(_STARTUP_ENTRIES, _STARTUP_SETTINGS)
)


def startup_settings() -> RuntimeSettings:
    """The settings snapshot the startup catalog was derived from."""
    return _STARTUP_SETTINGS
