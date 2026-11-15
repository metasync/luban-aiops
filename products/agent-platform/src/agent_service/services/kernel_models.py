"""Model resolution for the AgentKernel (decomposition Stage 2).

``ModelResolver`` owns the kernel's model-selection surface — building the
AgentScope model for a turn (SPEC-024 R-3), canonicalizing a bound model id
(SPEC-026 R-3), and the SPEC-071 R-2 per-turn router attribution trio
(``routed_candidate_name`` / ``candidate_model_id`` / ``effective_model_id``)
plus the ``router_armed`` predicate shared by ``_build_middlewares`` and
``ensure_agent``.

``AgentKernel`` keeps a thin delegator for every method here, so the public
surface — including the ``kernel._build_model(None)`` callers in
``services/document_prose.py`` / ``services/skill_draft.py`` and every existing
test that monkeypatches ``kernel._build_model`` — is unchanged. Method bodies
are extracted verbatim from ``runtime_kernel.AgentKernel`` (behavior
byte-identical); see ``docs/workspace/agent-kernel-decomposition-spike.md``.
"""

from dataclasses import replace

from agent_service.providers import get_provider
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services.model_catalog import MODEL_CATALOG

# SPEC-071 R-2: the stock ModelRouterMiddleware records its per-reply choice in
# ``agent.state.middle_context[<key>][reply_id]``; ``get_middleware_key()``
# defaults to the class name, so this is the stable read key for attribution.
_MODEL_ROUTER_MIDDLEWARE_KEY = "ModelRouterMiddleware"


class ModelResolver:
    """The kernel's model-selection + router-attribution surface.

    Holds a back-reference to the owning ``AgentKernel`` and reads ``settings``
    / ``_provider`` *live* through it (never a captured snapshot), so a later
    ``kernel.settings = ...`` reassignment — which the contract tests rely on —
    is observed exactly as the pre-extraction methods did. ``router_armed``
    delegates its deployment half back through the kernel's ``routing_available``
    (KernelStatus), the single source of truth, so the two can never disagree.
    """

    def __init__(self, kernel) -> None:
        self._kernel = kernel

    @property
    def settings(self) -> RuntimeSettings:
        return self._kernel.settings

    @property
    def _provider(self):
        return self._kernel._provider

    def build_model(self, model_id: str | None = None):
        """Build the AgentScope model for a turn (SPEC-024 R-3).

        ``model_id=None`` keeps the deploy-time settings path untouched.
        A concrete id derives a replaced RuntimeSettings from the catalog
        entry and reuses the existing provider adapters; an unknown id
        raises ``UnknownModelError`` (fail-closed). Bare provider names
        alias to the provider's default entry (SPEC-026 R-3).
        """
        if model_id is None:
            return self._provider.build_model(self.settings)
        entry = MODEL_CATALOG.get(model_id)
        if entry is None:
            # Imported lazily: ``UnknownModelError`` stays defined in
            # ``runtime_kernel`` (its public re-export path is unchanged) and a
            # module-level import here would be circular. This is the cold
            # fail-closed path, never the hot build path.
            from agent_service.runtime_kernel import UnknownModelError

            raise UnknownModelError(f"Unknown model id: {model_id!r}.")
        if entry.provider == self.settings.provider:
            # Active provider: keep the deploy-time credentials/options
            # and swap only the model name, so non-default series entries
            # build against the same provider (SPEC-026 R-1).
            settings = replace(self.settings, model_name=entry.model_name)
        else:
            settings = replace(
                self.settings,
                provider=entry.provider,
                api_key=entry.api_key,
                model_name=entry.model_name,
                base_url=entry.base_url,
                provider_options=RuntimeSettings.default_provider_options(
                    entry.provider
                ),
            )
        return get_provider(entry.provider).build_model(settings)

    def normalize_model_id(self, model_id: str | None) -> str:
        """Canonical id bound to a turn (SPEC-026 R-3).

        Legacy provider-name ids resolve through the catalog alias map to
        the concrete default-model entry; unknown ids pass through verbatim
        (explicit-request paths reject them upstream, so they only surface
        as the deploy-time provider fallback marker).
        """
        if model_id:
            entry = MODEL_CATALOG.get(model_id)
            if entry is not None:
                return entry.id
            return model_id
        return self.settings.provider

    def routed_candidate_name(self, agent) -> str | None:
        """The candidate the per-turn router chose for this reply (SPEC-071 R-2).

        Reads the stock ``ModelRouterMiddleware``'s own record in
        ``agent.state.middle_context``. Returns ``None`` when routing is off,
        did not fire, or failed soft — the turn then keeps its resolved model.
        Never raises: attribution must not wedge a completed turn.
        """
        try:
            state = getattr(agent, "state", None)
            if state is None:
                return None
            routed = (getattr(state, "middle_context", None) or {}).get(
                _MODEL_ROUTER_MIDDLEWARE_KEY, {}
            )
            name = routed.get(getattr(state, "reply_id", None))
            return name if isinstance(name, str) else None
        except Exception:  # pragma: no cover - defensive
            return None

    def candidate_model_id(self, name: str | None) -> str | None:
        """Map a routed candidate name back to its catalog model id."""
        if not name:
            return None
        for spec in self.settings.model_router_candidates:
            if spec.name == name:
                return spec.model_id
        return None

    def effective_model_id(self, agent) -> str | None:
        """The catalog id the per-turn router served, or ``None`` if it did not
        fire (SPEC-071 R-2). ``None`` lets a caller keep its resolved tier and
        report ``model_selected_by`` accurately."""
        return self.candidate_model_id(self.routed_candidate_name(agent))

    def router_armed(self, routing_allowed: bool) -> bool:
        """Whether the per-turn router is registered for this turn (SPEC-071 R-2).

        The single condition shared by ``_build_middlewares`` (register the
        middleware) and ``ensure_agent`` (split the cache key), so the two can
        never drift: the cache splits *exactly* when the built stack could
        differ. An inert router (knob off, or no candidate map) never splits the
        cache — no wasted entry in the default-off deployment.
        """
        return bool(routing_allowed and self._kernel.routing_available())
