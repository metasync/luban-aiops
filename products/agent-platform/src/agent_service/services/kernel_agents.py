"""Agent build / cache / restore / snapshot lifecycle (decomposition Stage 2).

``AgentRegistry`` owns the kernel's per-session agent cache — the LRU-bounded
``_agents`` map and its ``_agent_lock`` — and the lifecycle around it: the
settings-driven kernel configs (SPEC-017 R-1), persisted-state restore /
snapshot (SPEC-017 R-3), the user-turn index (SPEC-025), agent construction,
the ``ensure_agent`` cache/eviction/router-split path (SPEC-024 R-3, SPEC-071
R-2), and ``forget_session`` owner-deletion cleanup (SPEC-076).

``AgentKernel`` keeps a thin delegator for every method here plus read-through
``_agents`` / ``_max_cached_agents`` properties, so the public surface —
including ``entrypoints/runtime.py``'s ``ensure_agent`` caller and every test
that monkeypatches ``kernel._build_agent`` / ``kernel._snapshot_state`` or writes
``kernel._agents[...]`` directly — is unchanged. Cross-cluster calls (model
resolution, toolkit assembly, middleware) route back through the kernel's
delegators so a monkeypatch on the kernel is still honored. The persisted-state
store binding is likewise resolved through ``runtime_kernel`` at call time (never
a module-level import here), so the long-standing
``monkeypatch.setattr(runtime_kernel, "AGENT_STATE_STORE", ...)`` test surface
stays authoritative after the move. Method bodies are extracted verbatim from
``runtime_kernel.AgentKernel`` (behavior byte-identical); see
``docs/workspace/agent-kernel-decomposition-spike.md``.
"""

import asyncio
import json
import logging
from collections import OrderedDict

from agent_service.core.metrics import record_agent_state_error
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services.prose_redaction import (
    generated_credential_literals,
    redact_structure,
)

LOGGER = logging.getLogger(__name__)


class AgentRegistry:
    """The kernel's per-session agent cache and build/restore/snapshot lifecycle.

    Holds a back-reference to the owning ``AgentKernel`` and reads ``settings``
    and the ``_generated_literals`` masking knowledge *live* through it (never a
    captured snapshot). It owns ``_agents`` / ``_agent_lock`` /
    ``_max_cached_agents``; the kernel exposes the cache through a read-through
    property so direct ``kernel._agents[...]`` test access mutates this live map.
    Model / toolkit / middleware calls go back through ``self._kernel`` so the
    kernel's delegators — and any monkeypatch on them — stay authoritative.
    """

    def __init__(self, kernel, max_cached_agents: int) -> None:
        self._kernel = kernel
        self._agents: OrderedDict[str, tuple[object, type]] = OrderedDict()
        self._agent_lock = asyncio.Lock()
        self._max_cached_agents = max_cached_agents

    @property
    def settings(self) -> RuntimeSettings:
        return self._kernel.settings

    @property
    def _generated_literals(self):
        return self._kernel._generated_literals

    def build_kernel_configs(self):
        """Settings-driven kernel configs (SPEC-017 R-1).

        Defaults mirror agentscope's own defaults, so unset deployments
        behave exactly as before the settings existed.
        """
        from agentscope.agent import (
            ContextConfig,
            InjectionConfig,
            ModelConfig,
            ReActConfig,
        )

        settings = self.settings
        return {
            "model_config": ModelConfig(max_retries=settings.model_max_retries),
            # SPEC-064 R-2: ``compression_tool_enabled`` adds the opt-in
            # ``CompressContext`` tool (default off). Deliberately no
            # ``offloader`` is wired into the Agent: the offloader would write
            # compressed context to a Workspace filesystem path, which breaches
            # the read-only posture (gate point 3) and lands pod-local state on
            # the emptyDir workspace volume — invisible to other replicas and
            # lost on reschedule. Compression state stays in
            # ``state.summary``/``state.context`` and rides the SPEC-017
            # snapshot, which is shared and durable across replicas.
            "context_config": ContextConfig(
                trigger_ratio=settings.context_trigger_ratio,
                tool_result_limit=settings.tool_result_limit,
                compression_tool_enabled=settings.compress_context_enabled,
            ),
            "react_config": ReActConfig(max_iters=settings.max_iters),
            "injection_config": InjectionConfig(
                inject_runtime_state=True,
                timezone=settings.timezone,
            ),
        }

    def restore_state(self, session_id: str):
        """Load a persisted AgentState for the session, if any (SPEC-017 R-3).

        A missing row returns None (fresh agent); a corrupt row is discarded
        with a WARNING and a counter so a poisoned snapshot can never wedge
        a session.
        """
        # Resolved through ``runtime_kernel``'s binding — not a module-level
        # import here — so the existing
        # ``monkeypatch.setattr(runtime_kernel, "AGENT_STATE_STORE", ...)`` test
        # surface stays authoritative after the Stage-2 move (the same call-time
        # indirection ModelResolver uses for UnknownModelError). A sys.modules
        # hit; never raises, so the restore-error semantics below are unchanged.
        from agent_service.runtime_kernel import AGENT_STATE_STORE

        try:
            raw = AGENT_STATE_STORE.load_state(session_id)
        except Exception as exc:
            record_agent_state_error("restore")
            LOGGER.warning(
                "agent state restore failed for session %s: %s", session_id, type(exc).__name__
            )
            return None
        if raw is None:
            return None
        try:
            from agentscope.state import AgentState

            return AgentState.model_validate_json(raw)
        except Exception as exc:
            record_agent_state_error("restore")
            LOGGER.warning(
                "discarding corrupt persisted agent state for session %s: %s",
                session_id,
                type(exc).__name__,
            )
            return None

    def snapshot_state(self, session_id: str, agent, turn_literals=()) -> None:
        """Persist the agent state after a completed turn (SPEC-017 R-3).

        Never raises: a failed snapshot degrades durability, not the turn.
        """
        # Resolved through ``runtime_kernel`` (see ``restore_state``) so the
        # ``monkeypatch.setattr(runtime_kernel, "AGENT_STATE_STORE", ...)`` test
        # surface stays authoritative after the Stage-2 move.
        from agent_service.runtime_kernel import AGENT_STATE_STORE

        try:
            state = json.loads(agent.state.model_dump_json())
            literals = set(self._generated_literals.get(session_id, ()))
            literals.update(turn_literals)
            literals.update(generated_credential_literals(state))
            # Only the serialized projection changes; live tool/signing inputs stay raw.
            state_json = json.dumps(redact_structure(state, literals))
            AGENT_STATE_STORE.save_state(session_id, state_json)
        except Exception as exc:
            record_agent_state_error("snapshot")
            LOGGER.warning(
                "agent state snapshot failed for session %s: %s", session_id, type(exc).__name__
            )

    @staticmethod
    def count_user_turns(agent) -> int:
        """User-message count in the agent context (SPEC-025 turn index).

        The replay path attaches persisted evidence groups to the assistant
        turn at this ordinal, so the index is captured from the context
        before the streamed turn appends to it. Counting user messages (not
        assistant) keeps the index stable across HITL park/resume: parking
        may add a partial assistant message but never a user one.
        """
        try:
            context = getattr(agent.state, "context", None) or []
            return sum(
                1 for msg in context if getattr(msg, "role", None) == "user"
            )
        except Exception:  # pragma: no cover - defensive index fallback
            return 0

    def forget_session(self, session_id: str) -> None:
        """Drop ephemeral agents and literal knowledge after an owner deletion."""
        self._agents.pop(session_id, None)
        self._agents.pop(f"{session_id}::read-only", None)
        # SPEC-076: a bounded-diagnosis run fans member turns out under derived
        # "<session>::orch::<task>" / "::orch::synthesis" agent keys (each with a
        # further "::read-only" variant). Drop the whole family so an owner
        # deletion cannot orphan them in the LRU (m1 leak).
        orch_prefix = f"{session_id}::orch::"
        for key in [k for k in self._agents if k.startswith(orch_prefix)]:
            self._agents.pop(key, None)
        # In-flight redactors retain their own reference until the turn ends.
        self._generated_literals.pop(session_id, None)
        for key in [k for k in self._generated_literals if k.startswith(orch_prefix)]:
            self._generated_literals.pop(key, None)

    async def build_agent(
        self,
        session_id: str,
        bearer_token: str | None = None,
        model_id: str | None = None,
        read_only: bool = False,
        routing_allowed: bool = False,
    ):
        from agentscope.agent import Agent
        from agentscope.message import UserMsg

        toolkit = await self._kernel._ensure_toolkit(bearer_token, read_only)
        configs = self.build_kernel_configs()
        state = self.restore_state(session_id)
        agent = Agent(
            name=self.settings.agent_name,
            system_prompt=self.settings.system_prompt,
            model=self._kernel._build_model(model_id),
            toolkit=toolkit,
            middlewares=self._kernel._build_middlewares(routing_allowed),
            state=state,
            **configs,
        )
        LOGGER.info(
            "kernel agent constructed",
            extra={
                "session_id": session_id,
                "model_id": self._kernel._normalize_model_id(model_id),
                "max_iters": self.settings.max_iters,
                "context_trigger_ratio": self.settings.context_trigger_ratio,
                "tool_result_limit": self.settings.tool_result_limit,
                "timezone": self.settings.timezone,
                "model_max_retries": self.settings.model_max_retries,
                "state_restored": state is not None,
            },
        )
        return agent, UserMsg, self._kernel._normalize_model_id(model_id)

    async def ensure_agent(
        self,
        session_id: str,
        bearer_token: str | None = None,
        model_id: str | None = None,
        read_only: bool = False,
        routing_allowed: bool = False,
    ):
        """Return the agent bound to `session_id`, creating it on first use.

        Agents are keyed by session so conversation memory never crosses
        sessions; the cache is LRU-bounded to match the session store.
        Creation is serialised because it awaits: without the lock two
        concurrent turns on the same session would each build an agent and
        one would be discarded along with its memory.

        ``read_only`` turns use a distinct cache key for the same session so
        a restricted toolkit never leaks into interactive turns (and vice
        versa); both entries restore the same persisted memory.

        Model switching (SPEC-024 R-3): the cache tracks the bound model
        id; a turn whose resolved model differs evicts and rebuilds, and
        ``_restore_state`` rebuilds memory — the same path as a pod
        restart, so the switch never loses conversation history.
        """
        bound_id = self._kernel._normalize_model_id(model_id)
        agent_key = f"{session_id}::read-only" if read_only else session_id
        # SPEC-071 R-2: an agent built with the router must not be reused for a
        # turn where routing is disarmed (an explicit request/pin that happens
        # to resolve to the same model id), and vice versa, so the routing
        # posture joins the cache key — mirroring ``read_only``. Gated on the
        # same ``_router_armed`` predicate that registers the middleware, so an
        # inert (default-off) router never splits the cache. Both entries
        # restore the same persisted memory.
        if self._kernel._router_armed(routing_allowed):
            agent_key = f"{agent_key}::routed"
        cached = self._agents.get(agent_key)
        if cached is not None:
            # Gateway tools recovered after this agent was built with an
            # empty toolkit (discovery failure): rebuild so the turn can see
            # them. Persisted state (SPEC-017 R-3) restores the memory.
            agent, _user_msg_cls, cached_model_id = cached
            if cached_model_id != bound_id:
                LOGGER.info(
                    "model switch for session %s: %s -> %s; rebuilding "
                    "agent with restored state",
                    session_id,
                    cached_model_id,
                    bound_id,
                )
                self._agents.pop(agent_key, None)
            else:
                current_toolkit = await self._kernel._ensure_toolkit(
                    bearer_token, read_only
                )
                if (
                    self._kernel._count_gateway_tools(getattr(agent, "toolkit", None)) == 0
                    and self._kernel._count_gateway_tools(current_toolkit) > 0
                ):
                    LOGGER.info(
                        "gateway tools recovered; rebuilding kernel agent for "
                        "session %s",
                        session_id,
                    )
                    self._agents.pop(agent_key, None)
                else:
                    # Re-check membership: the await above opens a preemption
                    # window where a concurrent turn's recovery branch may pop
                    # this entry, or LRU eviction may remove it. A vanished
                    # entry falls through to the locked path, which re-checks
                    # the cache before building.
                    if agent_key in self._agents:
                        self._agents.move_to_end(agent_key)
                        return cached
        async with self._agent_lock:
            cached = self._agents.get(agent_key)
            if cached is not None and cached[2] == bound_id:
                self._agents.move_to_end(agent_key)
                return cached
            agent, user_msg_cls, cached_model_id = await self._kernel._build_agent(
                session_id, bearer_token, model_id, read_only, routing_allowed
            )
            self._agents[agent_key] = (agent, user_msg_cls, cached_model_id)
            while len(self._agents) > self._max_cached_agents:
                self._agents.popitem(last=False)
            return agent, user_msg_cls, cached_model_id
