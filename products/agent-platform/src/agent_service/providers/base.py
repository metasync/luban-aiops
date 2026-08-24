from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_service.runtime_settings import RuntimeProvider, RuntimeSettings


# SPEC-027 R-4: provider /models payloads carry dated snapshots and
# non-chat modalities; the shared discovery filter drops both.
_DATED_SNAPSHOT_RE = re.compile(r"-\d{4}-\d{2}-\d{2}")
_NON_CHAT_MARKERS = (
    "embedding",
    "rerank",
    "tts",
    "whisper",
    "audio",
    "image",
    "moderation",
    "transcrib",
    "guard",
    "realtime",
)


class ProviderConfigurationError(ValueError):
    """Raised when provider settings are incomplete or invalid."""


class AgentScopeProvider(ABC):
    """App-level adapter that resolves config into a concrete AgentScope model."""

    provider_name: "RuntimeProvider"
    default_model: str
    default_base_url: str | None = None
    # SPEC-026 R-1: the curated model series offered whenever this
    # provider's API key resolves; ``<PROVIDER>_MODELS`` can override it.
    # Must include ``default_model`` and stay collision-free across
    # providers (the catalog enforces both at startup).
    model_series: tuple[str, ...] = ()
    # SPEC-027 R-4: live-discovery hygiene. Family prefixes restrict the
    # discovered ids when non-empty; exclude markers drop non-chat
    # modalities on top of the shared dated-snapshot filter.
    discover_family_prefixes: tuple[str, ...] = ()
    discover_exclude_markers: tuple[str, ...] = _NON_CHAT_MARKERS

    def discover_filter(self, model_id: str) -> bool:
        """Whether a live-discovered model id joins the catalog (R-4)."""
        if _DATED_SNAPSHOT_RE.search(model_id):
            return False
        lowered = model_id.lower()
        if any(marker in lowered for marker in self.discover_exclude_markers):
            return False
        if self.discover_family_prefixes:
            return lowered.startswith(self.discover_family_prefixes)
        return True

    def validate(self, settings: "RuntimeSettings") -> None:
        if settings.provider != self.provider_name:
            raise ProviderConfigurationError(
                f"Provider adapter {self.provider_name} cannot handle "
                f"{settings.provider} settings."
            )
        if not settings.api_key:
            raise ProviderConfigurationError(
                "AGENTSCOPE_API_KEY is required to enable the runtime kernel."
            )

    def resolved_model_name(self, settings: "RuntimeSettings") -> str:
        return settings.resolved_model_name(self.default_model)

    def resolved_base_url(self, settings: "RuntimeSettings") -> str | None:
        return settings.resolved_base_url(self.default_base_url)

    def describe(self, settings: "RuntimeSettings") -> str:
        location = self.resolved_base_url(settings) or "provider default endpoint"
        return (
            f"{self.provider_name} provider using model "
            f"{self.resolved_model_name(settings)} "
            f"at {location}"
        )

    @abstractmethod
    def build_model(self, settings: "RuntimeSettings") -> Any:
        """Build the AgentScope model instance for this provider."""
