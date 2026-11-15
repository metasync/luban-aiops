"""Runtime-status projections for the AgentKernel (decomposition Stage 1).

``KernelStatus`` owns the kernel's read-only "how is the runtime doing"
surface — mode / state / provider / metadata / feature-flags / hint — plus the
``_last_error`` slot and its ``remember_error`` / ``clear_error`` mutators, and
the deployment-level ``routing_available()`` accessor.

``AgentKernel`` keeps a thin delegator for every method here (and a
read/write-through ``_last_error`` property), so the public API consumed by
``api/v2/routes.py`` and ``entrypoints/runtime.py`` — and every existing test —
is unchanged. Method bodies are extracted verbatim from
``runtime_kernel.AgentKernel`` (behavior byte-identical); see
``docs/workspace/agent-kernel-decomposition-spike.md``.
"""

from agent_service.runtime_settings import RuntimeSettings
from agent_service.services.prose_redaction import redact_assistant_text
from agent_service.services.serialization import make_serializable


class KernelStatus:
    """The kernel's runtime-status projection surface.

    Holds a back-reference to the owning ``AgentKernel`` and reads ``settings``
    / ``_provider`` / ``_generated_literals`` *live* through it (never a
    captured snapshot), so a later ``kernel.settings = ...`` reassignment is
    observed exactly as the pre-extraction methods did. ``_last_error`` is owned
    here; ``AgentKernel`` exposes it through a read/write-through property.
    """

    def __init__(self, kernel) -> None:
        self._kernel = kernel
        self._last_error: str | None = None

    @property
    def settings(self) -> RuntimeSettings:
        return self._kernel.settings

    @property
    def _provider(self):
        return self._kernel._provider

    @property
    def _generated_literals(self):
        return self._kernel._generated_literals

    def mode(self) -> str:
        return "agentscope" if self.is_configured() else "placeholder"

    def is_configured(self) -> bool:
        return self.settings.is_configured()

    def runtime_state(self) -> str:
        if not self.is_configured():
            return "not_configured"
        if self._last_error:
            return "provider_error"
        return "ready"

    def provider_name(self) -> str:
        return self._provider.provider_name

    def provider_description(self) -> str:
        return self._provider.describe(self.settings)

    def last_error(self) -> str | None:
        return self._last_error

    def runtime_metadata(self) -> dict[str, object]:
        return {
            "runtime_mode": self.mode(),
            "runtime_state": self.runtime_state(),
            "agentscope_enabled": self.is_configured(),
            "profile": self.settings.profile,
            "provider": self.provider_name(),
            "provider_description": self.provider_description(),
            "model_name": self._provider.resolved_model_name(self.settings),
            "base_url": self._provider.resolved_base_url(self.settings),
            "provider_options": make_serializable(self.settings.provider_options),
            "hint": self.configuration_hint(),
            "last_error": self.last_error(),
        }

    def feature_flags(self) -> list[dict[str, object]]:
        """The curated feature-flag inventory (SPEC-072 R-4).

        A discovery-safe allowlist of deployment *toggles* derived from live
        settings — each entry is a stable snake_case ``name``, a boolean
        ``enabled``, and an optional human ``label``. Never a key, URL, JWKS,
        budget, or timeout *value*: a flag whose knob is a secret (e.g.
        ``execution_signing_key``) reports only configured / not configured.
        ``model_routing`` reuses ``routing_available()`` so the catalog boolean
        (R-1), the ``auto`` resolution branch (R-2), and this flag (R-4) read
        one value and can never disagree (failure-matrix F3). Always-on
        invariants with no knob (permission, evidence, token-observation) are
        deliberately absent — the inventory reports toggles, not invariants.
        """
        settings = self.settings
        return [
            {
                "name": "model_routing",
                "enabled": self.routing_available(),
                "label": "Per-turn model routing",
            },
            {
                "name": "model_discovery",
                "enabled": bool(settings.model_discovery_enabled),
                "label": "Live model discovery",
            },
            {
                "name": "context_compression",
                "enabled": bool(settings.compress_context_enabled),
                "label": "Agent-driven context compression",
            },
            {
                "name": "outbound_delegated_identity",
                "enabled": bool(settings.target_authorization_enabled),
                "label": "Outbound delegated identity",
            },
            {
                "name": "kernel_tracing",
                "enabled": bool(settings.kernel_tracing),
                "label": "Kernel tracing",
            },
            {
                "name": "task_tools",
                "enabled": bool(settings.task_tools_enabled),
                "label": "Task tools",
            },
            {
                "name": "reply_token_budget",
                "enabled": settings.reply_token_budget is not None,
                "label": "Reply token budget",
            },
            {
                "name": "hitl_bridging",
                "enabled": settings.hitl_confirm_timeout > 0,
                "label": "HITL confirmation bridging",
            },
            {
                "name": "signed_execution",
                "enabled": bool(settings.execution_signing_key),
                "label": "Signed execution requests",
            },
        ]

    def configuration_hint(self) -> str:
        if not self.is_configured():
            return (
                "AgentScope runtime is not configured. "
                "Set AGENTSCOPE_API_KEY to enable the runtime kernel."
            )
        if self._last_error:
            return (
                "AgentScope runtime is configured through the "
                f"{self.provider_name()} provider, but the last provider call failed: "
                f"{self._last_error}"
            )
        return f"AgentScope runtime ready through {self.provider_description()}."

    def remember_error(self, exc: Exception, turn_literals=()) -> None:
        literals = set(turn_literals).union(*self._generated_literals.values())
        self._last_error = redact_assistant_text(str(exc), literals)

    def clear_error(self) -> None:
        self._last_error = None

    def routing_available(self) -> bool:
        """Whether per-turn routing is configured at all (SPEC-072 R-1).

        The deployment-level half of ``_router_armed`` — the router knob is on
        and a candidate map is configured — independent of any single turn's
        ``routing_allowed``. The single source of truth for the catalog's
        ``routing_available`` envelope boolean (R-1), ``_resolve_model``'s
        ``auto`` branch (R-2), and the ``model_routing`` feature flag (R-4), so
        the three surfaces can never disagree (failure-matrix F3).
        """
        return bool(
            self.settings.model_router_enabled
            and self.settings.model_router_candidates
        )
