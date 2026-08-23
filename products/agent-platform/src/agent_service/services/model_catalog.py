"""Credential-gated model catalog (SPEC-024 R-1).

The catalog derives the set of selectable LLM models from per-provider
environment knobs at startup. Each supported provider contributes at most
one entry — named by its configured model — when an API key is present:

- ``<PROVIDER>_API_KEY`` / ``<PROVIDER>_MODEL_NAME`` / ``<PROVIDER>_BASE_URL``
  (e.g. ``OPENAI_API_KEY``) configure an additional model, and
- the active profile's provider (``AGENTSCOPE_PROVIDER``) additionally
  falls back to the existing ``AGENTSCOPE_API_KEY`` / ``AGENTSCOPE_MODEL_NAME``
  / ``AGENTSCOPE_BASE_URL`` knobs, so a single-provider deployment needs
  zero new configuration.

Providers without a resolvable API key are dropped. A zero-entry catalog
is allowed and degrades exactly like ``settings.is_configured() == False``
today (runtime metadata ``not_configured``). Entry ids are provider names,
so chat requests select a model with e.g. ``"model": "openai"``; the label
carries the model name for portal display. Credentials never leave this
module: route layers serialize ``to_public_dict()`` only.
"""

from __future__ import annotations

import logging
import os
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
    """One selectable model: a configured provider + its credentials."""

    id: str  # provider name (one entry per provider, SPEC-024 Q-1)
    label: str  # resolved model name, shown in the portal selector
    provider: RuntimeProvider
    api_key: str
    model_name: str
    base_url: str | None
    default: bool  # True for the deploy-time active profile's provider

    def to_public_dict(self) -> dict[str, object]:
        """Discovery-safe view: no credentials, no base URLs (SPEC-024 R-2)."""
        return {
            "id": self.id,
            "label": self.label,
            "provider": self.provider,
            "default": self.default,
        }


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _resolve_entry(
    provider: RuntimeProvider,
    settings: RuntimeSettings,
) -> ModelCatalogEntry | None:
    prefix = provider.upper()
    api_key = _env(f"{prefix}_API_KEY")
    model_name = _env(f"{prefix}_MODEL_NAME")
    base_url = _env(f"{prefix}_BASE_URL")
    if provider == settings.provider:
        # The active profile's provider keeps working with the existing
        # AGENTSCOPE_* knobs (deploy-time default, zero-change upgrades).
        api_key = api_key or settings.api_key
        model_name = model_name or settings.model_name
        base_url = base_url or settings.base_url
    if not api_key:
        return None
    adapter = get_provider(provider)
    resolved_model = model_name or adapter.default_model
    resolved_base_url = base_url or adapter.default_base_url
    return ModelCatalogEntry(
        id=provider,
        label=resolved_model,
        provider=provider,
        api_key=api_key,
        model_name=resolved_model,
        base_url=resolved_base_url,
        default=(provider == settings.provider),
    )


def build_model_catalog(settings: RuntimeSettings) -> tuple[ModelCatalogEntry, ...]:
    """Derive the credential-gated model catalog from env + settings."""
    entries: list[ModelCatalogEntry] = []
    for provider in SUPPORTED_RUNTIME_PROVIDERS:
        entry = _resolve_entry(provider, settings)
        if entry is not None:
            entries.append(entry)
    LOGGER.info(
        "model catalog: %d model(s) enabled (default: %s)",
        len(entries),
        next((e.id for e in entries if e.default), "none"),
    )
    return tuple(entries)


class ModelCatalog:
    """Immutable lookup over the startup-derived catalog entries."""

    def __init__(self, entries: tuple[ModelCatalogEntry, ...]) -> None:
        self._entries = entries
        self._by_id = {entry.id: entry for entry in entries}

    @property
    def entries(self) -> tuple[ModelCatalogEntry, ...]:
        return self._entries

    def get(self, model_id: str) -> ModelCatalogEntry | None:
        return self._by_id.get(model_id)

    def default_entry(self) -> ModelCatalogEntry | None:
        return next((e for e in self._entries if e.default), None)

    def public_models(self) -> dict[str, object]:
        """Discovery payload per shared-contracts model-catalog schema."""
        default = self.default_entry()
        return {
            "models": [entry.to_public_dict() for entry in self._entries],
            "default": default.id if default is not None else None,
        }


# Module-level singleton — imported by runtime_kernel.py / routes, same
# posture as EVIDENCE_STORE in evidence_store.py.
MODEL_CATALOG = ModelCatalog(build_model_catalog(RuntimeSettings.from_env()))
