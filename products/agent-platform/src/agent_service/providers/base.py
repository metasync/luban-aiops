from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_service.runtime_settings import RuntimeProvider, RuntimeSettings


class ProviderConfigurationError(ValueError):
    """Raised when provider settings are incomplete or invalid."""


class AgentScopeProvider(ABC):
    """App-level adapter that resolves config into a concrete AgentScope model."""

    provider_name: "RuntimeProvider"
    default_model: str
    default_base_url: str | None = None

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
