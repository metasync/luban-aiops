import asyncio
import json
import logging
from collections import OrderedDict
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import datetime, timezone

from agent_service.core.metrics import (
    record_agent_state_error,
    record_evidence_write,
)
from agent_service.providers import get_provider
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services.agent_state_store import AGENT_STATE_STORE
from agent_service.services.audit_emitter import (
    build_audit_event,
    emit_audit_event,
)
from agent_service.services.confirmation_records import (
    CONFIRMATION_RECORD_STORE,
    make_record as make_confirmation_record,
)
from agent_service.services.evidence_store import (
    EVIDENCE_FRAME_TYPES,
    EVIDENCE_STORE,
    prepare_frames,
)
from agent_service.services.execution_records import (
    EXECUTION_RECORD_STORE,
    make_execution_record,
)
from agent_service.services.execution_signing import (
    REASON_ARGS_DIGEST_MISMATCH,
    REASON_SIGNING_UNAVAILABLE,
    build_receipt,
    build_requests,
)
from agent_service.services.hitl_confirmations import (
    CONFIRMATION_REGISTRY,
    PendingConfirmation,
)
from agent_service.services.model_catalog import MODEL_CATALOG

LOGGER = logging.getLogger(__name__)
MAX_CACHED_AGENTS = 1000


class UnknownModelError(ValueError):
    """A requested model id is absent from the credential-gated catalog.

    Selection fails closed (SPEC-024 R-1): routes map this to 4xx; the
    kernel never silently falls back to the default model.
    """


TEXT_DELTA_EVENTS = {
    "message_delta",
    "text_block_start",
    "text_block_delta",
    "thinking_block_start",
    "thinking_block_delta",
}

# Deterministic guard injected into the turn when a tool gateway is configured
# but no tool could be registered. A standing system prompt is only a
# probabilistic hint; when the toolkit is empty the model has no real data to
# ground in and tends to fabricate, so this explicit per-turn notice is added
# by code exactly when the risk exists.
NO_TOOLS_NOTICE = (
    "[SYSTEM NOTICE] No operational tools are currently reachable. Tool "
    "discovery returned no available tools, so you have NO live cluster, log, "
    "or metric data. Do NOT report, estimate, or imply any infrastructure "
    "status, health, counts, or metrics. Tell the user that operational "
    "tooling is currently unavailable and that you cannot perform the "
    "requested check right now."
)

# Deterministic guard for the HITL-disabled posture (SPEC-021 R-3): when
# confirmation bridging is off, mutating tools are excluded from the toolkit
# entirely; this notice keeps that posture honest instead of letting the
# model imply it could act.
MUTATING_TOOLS_UNAVAILABLE_NOTICE = (
    "[SYSTEM NOTICE] Mutating operational actions (e.g. deleting or "
    "restarting workloads) are currently unavailable in this workspace; only "
    "read-only diagnostics can be executed. Human confirmation bridging is "
    "disabled, so do NOT propose, promise, or imply that you can perform any "
    "mutating action. If the user asks for one, say it requires operator "
    "enablement of HITL confirmation."
)


def make_serializable(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [make_serializable(item) for item in value]
    if isinstance(value, tuple):
        return [make_serializable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): make_serializable(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return make_serializable(value.model_dump())
    if hasattr(value, "__dict__"):
        return make_serializable(
            {
                key: item
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        )
    return str(value)


def extract_text(value: object) -> str:
    normalized = make_serializable(value)
    if normalized is None:
        return ""
    if isinstance(normalized, str):
        return normalized
    if isinstance(normalized, list):
        parts = [extract_text(item) for item in normalized]
        return " ".join(part for part in parts if part).strip()
    if isinstance(normalized, dict):
        for key in ("text", "delta", "message", "content"):
            if key in normalized:
                text = extract_text(normalized[key])
                if text:
                    return text
        return json.dumps(normalized, default=str)
    return str(normalized)


def extract_stream_text(value: object) -> str:
    normalized = make_serializable(value)
    if normalized is None:
        return ""
    if isinstance(normalized, str):
        return normalized
    if isinstance(normalized, list):
        parts = [extract_stream_text(item) for item in normalized]
        return " ".join(part for part in parts if part).strip()
    if isinstance(normalized, dict):
        for key in ("text", "delta", "message", "content"):
            if key in normalized:
                text = extract_stream_text(normalized[key])
                if text:
                    return text
        return ""
    return ""


class AgentKernel:
    def __init__(
        self,
        settings: RuntimeSettings | None = None,
        max_cached_agents: int = MAX_CACHED_AGENTS,
    ) -> None:
        self.settings = settings or RuntimeSettings.from_env()
        self._provider = get_provider(self.settings.provider)
        self._agents: OrderedDict[str, tuple[object, type]] = OrderedDict()
        self._max_cached_agents = max_cached_agents
        self._last_error: str | None = None
        # Per-token toolkit cache (SPEC-008 R-5): a toolkit is built per owning
        # user's delegated token so discovery runs once per token. Tool
        # closures read the current token from the DELEGATED_TOKEN contextvar
        # at call time (SPEC-018 R-2), so cached toolkits keep working across
        # portal token refresh.
        self._toolkits: dict[str, object] = {}
        self._toolkit_lock = asyncio.Lock()
        self._agent_lock = asyncio.Lock()
        # SPEC-021 R-3: set when a toolkit build excluded mutating tools
        # because HITL bridging is disabled, so streamed turns surface the
        # mutating-unavailable posture honestly.
        self._mutating_tools_excluded = False

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

    def remember_error(self, exc: Exception) -> None:
        self._last_error = str(exc)

    def clear_error(self) -> None:
        self._last_error = None

    def _build_model(self, model_id: str | None = None):
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

    def _normalize_model_id(self, model_id: str | None) -> str:
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

    async def _ensure_toolkit(
        self, bearer_token: str | None = None, read_only: bool = False
    ):
        """Build (once per token) and return the Toolkit with gateway tools.

        Toolkits are cached per delegated token so discovery runs once per
        token; tool closures read the current token from ``DELEGATED_TOKEN``
        at call time, so a cached toolkit keeps working across portal token
        refresh (SPEC-018 R-2). Empty discovery results are intentionally NOT
        cached: the next caller retries discovery instead of being poisoned.

        ``read_only`` selects a separate cache entry whose toolkit is
        restricted to read-level tools (automated diagnostic turns).
        """
        cache_key = (bearer_token or "") + ("::read-only" if read_only else "")
        cached = self._toolkits.get(cache_key)
        if cached is not None:
            return cached

        from agentscope.tool import Toolkit

        async with self._toolkit_lock:
            # Re-check: a concurrent caller may have built it while we waited.
            cached = self._toolkits.get(cache_key)
            if cached is not None:
                return cached

            task_tools = (
                self._build_task_tools()
                if self.settings.task_tools_enabled
                else []
            )

            if self.settings.tool_gateway_url:
                from agent_service.tools.gateway_tools import (
                    build_gateway_toolkit,
                    discover_tools,
                )

                try:
                    definitions = await discover_tools(
                        self.settings.tool_gateway_url, bearer_token
                    )
                    if definitions:
                        definitions = self._filter_mutating_for_hitl(
                            definitions
                        )
                    if definitions and read_only:
                        definitions = self._filter_read_only(definitions)
                    if definitions:
                        toolkit = build_gateway_toolkit(
                            definitions,
                            self.settings.tool_gateway_url,
                        )
                        if task_tools:
                            toolkit.tool_groups[0].tools.extend(task_tools)
                        self._toolkits[cache_key] = toolkit
                        return toolkit
                except Exception as exc:
                    LOGGER.warning("failed to build gateway toolkit: %s", exc)

            # No gateway (or nothing discovered): task tools only, returned
            # uncached so a later turn can retry discovery.
            return Toolkit(tools=task_tools)

    def _filter_mutating_for_hitl(self, definitions: list[dict]) -> list[dict]:
        """Drop non-read tools when HITL bridging is disabled (SPEC-021 R-3).

        A mutating tool can never execute without a human confirmation; when
        ``AGENT_HITL_CONFIRM_TIMEOUT=0`` there is no confirmation surface, so
        non-read tools are excluded from the toolkit entirely instead of
        parking silently. Read tools are untouched.
        """
        if self.settings.hitl_confirm_timeout > 0:
            return definitions
        kept = [
            definition
            for definition in definitions
            if definition.get("risk_level", "read") == "read"
        ]
        excluded = len(definitions) - len(kept)
        if excluded:
            self._mutating_tools_excluded = True
            LOGGER.warning(
                "HITL bridging disabled (AGENT_HITL_CONFIRM_TIMEOUT=0); "
                "excluded %d mutating tool(s) from the agent toolkit",
                excluded,
            )
        return kept

    def _filter_read_only(self, definitions: list[dict]) -> list[dict]:
        """Restrict the toolkit to read-level tools for read-only turns.

        Automated diagnostic turns (incident triage) must never invoke — or
        silently park on — a mutating tool, regardless of what the model
        decides, so non-read tools are excluded structurally instead of
        relying on prompt discipline alone.
        """
        kept = [
            definition
            for definition in definitions
            if definition.get("risk_level", "read") == "read"
        ]
        excluded = len(definitions) - len(kept)
        if excluded:
            LOGGER.info(
                "read-only turn: excluded %d mutating tool(s) from the "
                "agent toolkit",
                excluded,
            )
        return kept

    def _build_task_tools(self) -> list:
        """Built-in agentscope task tools, opt-in (SPEC-018 R-5).

        These mutate only session-local agent state, so the SPEC-017
        snapshot/restore persists them with no extra work.
        """
        from agentscope.tool import TaskCreate, TaskGet, TaskList, TaskUpdate

        return [TaskCreate(), TaskGet(), TaskList(), TaskUpdate()]

    def _build_middlewares(self) -> list:
        """Compose the kernel middleware stack (SPEC-018).

        Permission and evidence middlewares are always registered; OTel
        kernel tracing (R-3) and the reply token budget (R-4) are opt-in
        via settings and stay absent when unconfigured.
        """
        from agent_service.services.kernel_middleware import (
            GatewayPermissionMiddleware,
            ToolEvidenceMiddleware,
        )

        settings = self.settings
        middlewares: list = [
            GatewayPermissionMiddleware(),
            ToolEvidenceMiddleware(
                data_summary_max_chars=settings.tool_data_summary_max_chars,
                data_max_chars=settings.tool_data_max_chars,
            ),
        ]
        if settings.kernel_tracing:
            from agentscope.middleware import TracingMiddleware

            middlewares.append(TracingMiddleware())
        if settings.reply_token_budget is not None:
            from agentscope.middleware import ReplyBudgetControlMiddleware

            middlewares.append(
                ReplyBudgetControlMiddleware(
                    token_budget=settings.reply_token_budget,
                    input_token_weight=settings.reply_input_token_weight,
                    output_token_weight=settings.reply_output_token_weight,
                )
            )
        return middlewares

    def _count_gateway_tools(self, toolkit) -> int:
        """Count gateway-backed tools in a toolkit.

        Task tools and builtins are excluded: only gateway tools ground the
        model in live data, which is what the no-tools guard cares about
        (SPEC-018 R-5).
        """
        count = 0
        for group in getattr(toolkit, "tool_groups", None) or []:
            for tool in getattr(group, "tools", None) or []:
                if getattr(tool, "gateway_tool_name", None):
                    count += 1
        return count

    def _build_kernel_configs(self):
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
            "context_config": ContextConfig(
                trigger_ratio=settings.context_trigger_ratio,
                tool_result_limit=settings.tool_result_limit,
            ),
            "react_config": ReActConfig(max_iters=settings.max_iters),
            "injection_config": InjectionConfig(
                inject_runtime_state=True,
                timezone=settings.timezone,
            ),
        }

    def _restore_state(self, session_id: str):
        """Load a persisted AgentState for the session, if any (SPEC-017 R-3).

        A missing row returns None (fresh agent); a corrupt row is discarded
        with a WARNING and a counter so a poisoned snapshot can never wedge
        a session.
        """
        try:
            raw = AGENT_STATE_STORE.load_state(session_id)
        except Exception as exc:
            record_agent_state_error("restore")
            LOGGER.warning(
                "agent state restore failed for session %s: %s", session_id, exc
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
                exc,
            )
            return None

    def _snapshot_state(self, session_id: str, agent) -> None:
        """Persist the agent state after a completed turn (SPEC-017 R-3).

        Never raises: a failed snapshot degrades durability, not the turn.
        """
        try:
            state_json = agent.state.model_dump_json()
            AGENT_STATE_STORE.save_state(session_id, state_json)
        except Exception as exc:
            record_agent_state_error("snapshot")
            LOGGER.warning(
                "agent state snapshot failed for session %s: %s", session_id, exc
            )

    @staticmethod
    def _count_user_turns(agent) -> int:
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

    def _persist_evidence(
        self,
        session_id: str,
        request_id: str,
        turn_index: int,
        frames: list[dict[str, object]],
    ) -> None:
        """Persist a turn's evidence frames best-effort (SPEC-025 R-1).

        Never raises: a failed write degrades replay parity, not the turn.
        Entry caps apply before insert; the session budget is enforced by
        the store itself.
        """
        if not frames:
            return
        try:
            prepared = prepare_frames(
                frames, self.settings.evidence_entry_max_chars
            )
            EVIDENCE_STORE.save_turn(
                session_id,
                request_id,
                turn_index,
                prepared,
                self.settings.evidence_session_max_bytes,
            )
            record_evidence_write("ok")
        except Exception as exc:
            record_evidence_write("error")
            LOGGER.warning(
                "evidence persistence failed for session %s: %s",
                session_id,
                exc,
            )

    async def _build_agent(
        self,
        session_id: str,
        bearer_token: str | None = None,
        model_id: str | None = None,
        read_only: bool = False,
    ):
        from agentscope.agent import Agent
        from agentscope.message import UserMsg

        toolkit = await self._ensure_toolkit(bearer_token, read_only)
        configs = self._build_kernel_configs()
        state = self._restore_state(session_id)
        agent = Agent(
            name=self.settings.agent_name,
            system_prompt=self.settings.system_prompt,
            model=self._build_model(model_id),
            toolkit=toolkit,
            middlewares=self._build_middlewares(),
            state=state,
            **configs,
        )
        LOGGER.info(
            "kernel agent constructed",
            extra={
                "session_id": session_id,
                "model_id": self._normalize_model_id(model_id),
                "max_iters": self.settings.max_iters,
                "context_trigger_ratio": self.settings.context_trigger_ratio,
                "tool_result_limit": self.settings.tool_result_limit,
                "timezone": self.settings.timezone,
                "model_max_retries": self.settings.model_max_retries,
                "state_restored": state is not None,
            },
        )
        return agent, UserMsg, self._normalize_model_id(model_id)

    async def ensure_agent(
        self,
        session_id: str,
        bearer_token: str | None = None,
        model_id: str | None = None,
        read_only: bool = False,
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
        bound_id = self._normalize_model_id(model_id)
        agent_key = f"{session_id}::read-only" if read_only else session_id
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
                current_toolkit = await self._ensure_toolkit(
                    bearer_token, read_only
                )
                if (
                    self._count_gateway_tools(getattr(agent, "toolkit", None)) == 0
                    and self._count_gateway_tools(current_toolkit) > 0
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
            agent, user_msg_cls, cached_model_id = await self._build_agent(
                session_id, bearer_token, model_id, read_only
            )
            self._agents[agent_key] = (agent, user_msg_cls, cached_model_id)
            while len(self._agents) > self._max_cached_agents:
                self._agents.popitem(last=False)
            return agent, user_msg_cls, cached_model_id

    def build_unconfigured_message(self, message: str, session_id: str) -> str:
        return (
            "Platform baseline placeholder response. "
            f"AgentScope runtime not configured for session {session_id}. "
            f"Received '{message}'."
        )

    def build_provider_error_message(
        self,
        message: str,
        session_id: str,
        model_id: str | None = None,
    ) -> str:
        detail = self._last_error or "Unknown provider error."
        # Name the provider that actually served (attempted) the turn:
        # a resolved catalog entry carries its own provider, so a
        # dashscope model failure never blames the deepseek profile.
        entry = MODEL_CATALOG.get(model_id) if model_id else None
        if entry is not None:
            attribution = f"{entry.provider} (model {entry.id})"
        elif model_id:
            attribution = f"{self.provider_name()} (model {model_id})"
        else:
            attribution = self.provider_name()
        return (
            "Platform runtime fallback response. "
            f"AgentScope provider {attribution} failed for session {session_id}. "
            f"Received '{message}'. Last error: {detail}"
        )

    async def fallback_stream(
        self,
        request_id: str,
        session_id: str,
        delta: str,
    ) -> AsyncIterator[dict[str, object]]:
        yield {
            "event": "message_start",
            "request_id": request_id,
            "session_id": session_id,
        }
        yield {
            "event": "message_delta",
            "request_id": request_id,
            "session_id": session_id,
            "delta": delta,
        }
        yield {
            "event": "message_end",
            "request_id": request_id,
            "session_id": session_id,
            "message": "complete",
        }

    async def reply_text(
        self,
        message: str,
        session_id: str,
        user_name: str,
        bearer_token: str | None = None,
        response_schema: dict | None = None,
        model_id: str | None = None,
        read_only: bool = False,
    ) -> tuple[str, dict | None]:
        """Run one blocking turn.

        Returns the reply text and, when ``response_schema`` was supplied,
        the kernel-validated structured output carried on the final message
        (SPEC-017 R-2) — ``None`` when the turn ended without producing one.

        ``model_id`` selects the catalog entry for this turn (SPEC-024 R-3);
        callers validate it against the catalog first, so an unknown id
        never reaches ``_build_model`` here.

        ``read_only`` restricts the turn's toolkit to read-level tools
        (automated diagnostic turns such as incident triage).
        """
        if not self.is_configured():
            return self.build_unconfigured_message(message, session_id), None

        from agent_service.tools.gateway_tools import (
            CHAT_SESSION_ID,
            DELEGATED_TOKEN,
        )

        serving_model: str | None = None
        try:
            agent, user_msg_cls, serving_model = await self.ensure_agent(
                session_id, bearer_token, model_id, read_only
            )
            # Expose the turn's delegated token to the cached tool closures
            # (SPEC-018 R-2). No evidence sink is set: blocking turns emit
            # no trace frames.
            token_var = DELEGATED_TOKEN.set(bearer_token)
            session_var = CHAT_SESSION_ID.set(session_id)
            try:
                reply_msg = await agent.reply(
                    user_msg_cls(name=user_name, content=message),
                    structured_schema=response_schema,
                )
            finally:
                DELEGATED_TOKEN.reset(token_var)
                CHAT_SESSION_ID.reset(session_var)
            self.clear_error()
            structured = getattr(reply_msg, "structured_output", None)
            if not isinstance(structured, dict):
                structured = None
            self._snapshot_state(session_id, agent)
            return (
                extract_text(getattr(reply_msg, "content", reply_msg)),
                structured,
            )
        except Exception as exc:  # pragma: no cover - defensive fallback
            self.remember_error(exc)
            LOGGER.exception("AgentScope reply failed; falling back to runtime error response: %s", exc)
            return (
                self.build_provider_error_message(
                    message, session_id, serving_model or model_id
                ),
                None,
            )

    def normalize_event(
        self,
        event: object,
        request_id: str,
        session_id: str,
    ) -> dict[str, object]:
        payload = make_serializable(event)
        event_type = "agentscope_event"
        if isinstance(payload, dict) and "type" in payload:
            event_type = str(payload["type"]).lower()
        else:
            raw_type = getattr(event, "type", None)
            if raw_type is not None:
                event_type = str(getattr(raw_type, "name", raw_type)).lower()

        data: dict[str, object] = {
            "event": event_type,
            "request_id": request_id,
            "session_id": session_id,
            "payload": payload,
        }

        text = extract_stream_text(payload)
        if event_type in TEXT_DELTA_EVENTS and text:
            data["delta"] = text
        return data

    async def stream_events(
        self,
        message: str,
        request_id: str,
        session_id: str,
        user_name: str,
        bearer_token: str | None = None,
        model_id: str | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        # SPEC-024 R-3: an unknown model id fails closed before any agent
        # work — a deterministic error frame, never a silent default.
        if model_id is not None and MODEL_CATALOG.get(model_id) is None:
            LOGGER.warning(
                "stream rejected unknown model %r for session %s",
                model_id,
                session_id,
            )
            yield {
                "event": "error",
                "request_id": request_id,
                "session_id": session_id,
                "error": {
                    "code": "unknown_model",
                    "message": f"unknown model id: {model_id}",
                },
            }
            return

        if not self.is_configured():
            async for event in self.fallback_stream(
                request_id=request_id,
                session_id=session_id,
                delta=self.build_unconfigured_message(message, session_id),
            ):
                yield event
            return

        from agent_service.services.kernel_middleware import TOOL_EVIDENCE_SINK
        from agent_service.tools.gateway_tools import (
            CHAT_SESSION_ID,
            DELEGATED_TOKEN,
        )

        bound_model_id: str | None = None
        try:
            # Ensure the agent (with the token-cached toolkit) exists.
            agent, user_msg_cls, bound_model_id = await self.ensure_agent(
                session_id, bearer_token, model_id
            )

            # SPEC-025 R-1: the replay turn ordinal for this stream's
            # evidence, captured before the turn mutates the context.
            turn_index = self._count_user_turns(agent)
            evidence_frames: list[dict[str, object]] = []

            # Deterministic anti-hallucination guard: with a gateway
            # configured but zero gateway tools registered the model has no
            # real data to ground in, so inject an explicit notice for this
            # turn instead of relying on the standing system prompt. Task
            # tools never count: they provide no live data (SPEC-018 R-5).
            effective_message = message
            if (
                self.settings.tool_gateway_url
                and self._count_gateway_tools(agent.toolkit) == 0
            ):
                LOGGER.warning(
                    "tool gateway configured but no tools registered; "
                    "injecting no-tools notice to prevent fabrication"
                )
                effective_message = f"{NO_TOOLS_NOTICE}\n\n{message}"
            elif self._mutating_tools_excluded:
                effective_message = (
                    f"{MUTATING_TOOLS_UNAVAILABLE_NOTICE}\n\n{message}"
                )

            # SPEC-018 R-2: a request-scoped evidence sink consumed by
            # ToolEvidenceMiddleware replaces the per-request toolkit
            # rebuild; the delegated token is exposed the same way for the
            # cached tool closures.
            trace_queue: asyncio.Queue = asyncio.Queue()
            sink_var = TOOL_EVIDENCE_SINK.set(trace_queue)
            token_var = DELEGATED_TOKEN.set(bearer_token)
            session_var = CHAT_SESSION_ID.set(session_id)
            try:
                async for event in agent.reply_stream(
                    user_msg_cls(name=user_name, content=effective_message)
                ):
                    self.clear_error()
                    # Drain any accumulated trace events before yielding text.
                    while not trace_queue.empty():
                        trace = trace_queue.get_nowait()
                        decorated = {
                            **trace,
                            "request_id": request_id,
                            "session_id": session_id,
                        }
                        if decorated.get("type") in EVIDENCE_FRAME_TYPES:
                            evidence_frames.append(decorated)
                        yield decorated
                    # SPEC-020 R-2: a kernel ASK park surfaces as a
                    # confirmation_request frame and ends the stream without
                    # message_end; the confirm endpoint resumes it.
                    frame = self._build_confirmation_frame(
                        event,
                        session_id,
                        user_name,
                        agent.toolkit,
                        turn_index=turn_index,
                        evidence_frames=evidence_frames,
                    )
                    if frame is not None:
                        yield {
                            **frame,
                            "request_id": request_id,
                            "session_id": session_id,
                        }
                        break
                    frame = self.normalize_event(event, request_id, session_id)
                    if frame.get("event") == "message_end":
                        # SPEC-024 R-3: attribute the turn to the model that
                        # actually served it (resolved or session default).
                        frame["model"] = bound_model_id
                    yield frame

                # Drain any remaining trace events after the stream completes.
                while not trace_queue.empty():
                    trace = trace_queue.get_nowait()
                    decorated = {
                        **trace,
                        "request_id": request_id,
                        "session_id": session_id,
                    }
                    if decorated.get("type") in EVIDENCE_FRAME_TYPES:
                        evidence_frames.append(decorated)
                    yield decorated
            finally:
                DELEGATED_TOKEN.reset(token_var)
                CHAT_SESSION_ID.reset(session_var)
                TOOL_EVIDENCE_SINK.reset(sink_var)

            # Persist the turn's evidence frames best-effort (SPEC-025 R-1)
            # alongside the conversation snapshot; also covers the park
            # path, which breaks out of the loop above.
            self._persist_evidence(
                session_id, request_id, turn_index, evidence_frames
            )

            # Persist conversation state after the completed turn so it
            # survives restarts (SPEC-017 R-3). Fail-open by design.
            self._snapshot_state(session_id, agent)
        except Exception as exc:  # pragma: no cover - defensive fallback
            self.remember_error(exc)
            LOGGER.exception("AgentScope streaming failed; falling back to runtime error response: %s", exc)
            async for event in self.fallback_stream(
                request_id=request_id,
                session_id=session_id,
                delta=self.build_provider_error_message(
                    message, session_id, bound_model_id or model_id
                ),
            ):
                yield event

    # --- HITL confirmation bridging (SPEC-020 R-2) ---

    def _build_confirmation_frame(
        self,
        event: object,
        session_id: str,
        user_name: str,
        toolkit: object | None = None,
        turn_index: int = 0,
        evidence_frames: list[dict[str, object]] | None = None,
    ) -> dict[str, object] | None:
        """Register a kernel ASK park and build its confirmation_request frame.

        Returns None for non-park events and when bridging is disabled
        (``hitl_confirm_timeout == 0``), preserving the legacy silent-park
        posture. A parked reply is registered per session and the stream
        ends without ``message_end``; the confirm endpoint resumes it.
        """
        if self.settings.hitl_confirm_timeout <= 0:
            return None
        from agentscope.event import RequireUserConfirmEvent

        if not isinstance(event, RequireUserConfirmEvent):
            return None
        # SPEC-050 follow-up: extract browser element map from the last
        # web.snapshot so confirmation cards show what element will be
        # clicked/typed into, not just the raw ref number.
        browser_element_map = self._extract_browser_element_map(
            evidence_frames or []
        )
        pending = CONFIRMATION_REGISTRY.register(
            session_id=session_id,
            user_id=user_name,
            reply_id=str(getattr(event, "reply_id", "") or ""),
            tool_calls=list(getattr(event, "tool_calls", None) or []),
            timeout=self.settings.hitl_confirm_timeout,
            risk_levels=self._toolkit_risk_map(toolkit),
            gateway_names=self._toolkit_gateway_name_map(toolkit),
            browser_element_map=browser_element_map,
        )
        # SPEC-031 R-1: the durable record is written before the frame
        # below reaches the client, so the card survives re-login and
        # restarts. Best-effort: a store failure degrades to live-only
        # cards, never blocks the park.
        try:
            CONFIRMATION_RECORD_STORE.save_parked(
                make_confirmation_record(
                    confirm_id=pending.confirm_id,
                    session_id=session_id,
                    owner_user_id=user_name,
                    pending_calls=pending.pending_calls_payload(),
                    action=pending.highest_action(),
                    # SPEC-033 R-1: anchor the durable card under the
                    # parking turn (same ordinal convention as evidence).
                    turn_index=turn_index,
                )
            )
        except Exception as exc:
            LOGGER.warning(
                "confirmation record persistence failed for session %s: %s",
                session_id,
                exc,
            )
        LOGGER.info(
            "kernel confirmation parked",
            extra={
                "session_id": session_id,
                "confirm_id": pending.confirm_id,
                "tool_names": pending.tool_names(),
            },
        )
        return {
            "type": "confirmation_request",
            "confirm_id": pending.confirm_id,
            "pending_calls": pending.pending_calls_payload(),
            "message": self._confirmation_message(event),
        }

    @staticmethod
    def _extract_browser_element_map(
        evidence_frames: list[dict[str, object]],
    ) -> dict[int, str]:
        """Extract element map from the last web.snapshot result (SPEC-050).

        Confirmation cards for browser interaction tools (web.click, web.type,
        etc.) show the element description from the snapshot, not just the
        raw ref number. Returns an empty dict if no snapshot is found.
        """
        from agent_service.services.hitl_confirmations import (
            parse_snapshot_elements,
        )

        # Walk backwards to find the last web.snapshot result.
        for frame in reversed(evidence_frames):
            if (
                frame.get("type") == "tool_result"
                and frame.get("tool_name") == "web.snapshot"
                and frame.get("status") == "success"
            ):
                # The snapshot text is in data.snapshot.
                data = frame.get("data")
                if isinstance(data, dict):
                    snapshot_text = data.get("snapshot")
                    if isinstance(snapshot_text, str):
                        return parse_snapshot_elements(snapshot_text)
        return {}

    @staticmethod
    def _record_resolution(
        session_id: str,
        confirm_id: str,
        status: str,
        decider_user_id: str | None,
        decision: str | None,
    ) -> None:
        """Best-effort durable outcome write (SPEC-031 R-1).

        The live stream already carried the result; a store failure only
        degrades the persisted card/inbox history, never the decision.
        """
        try:
            CONFIRMATION_RECORD_STORE.mark_resolved(
                session_id, confirm_id, status, decider_user_id, decision
            )
        except Exception as exc:
            LOGGER.warning(
                "confirmation record resolution failed for session %s: %s",
                session_id,
                exc,
            )

    # --- Signed execution requests and receipts (SPEC-037 R-2/R-4/R-5) ---

    def _prepare_executions(
        self,
        pending: PendingConfirmation,
        decider_user_id: str,
        confirmed: bool,
        request_id: str,
        session_id: str,
    ) -> tuple[dict[str, dict], str | None]:
        """Build, persist, and audit the signed requests (SPEC-037 R-2).

        Returns ``(requests_by_call_id, rejection_reason)``. Approved
        batches with a provisioned key produce one signed request per
        parked call; a missing key rejects the whole batch fail-closed
        (the resumed stream reports the rejection through the tool
        boundary) and audits ``execution_rejected``
        (``signing_unavailable``). Denials construct nothing.
        """
        if not confirmed:
            return {}, None
        key = self.settings.execution_signing_key
        if not key:
            LOGGER.warning(
                "mutating resume rejected: no execution signing key "
                "provisioned (confirm_id=%s)",
                pending.confirm_id,
            )
            for call in pending.pending_calls_payload():
                self._emit_execution_event(
                    "execution_rejected",
                    "deny",
                    {
                        "confirm_id": pending.confirm_id,
                        "call_id": call.get("call_id"),
                        "tool_name": call.get("tool_name"),
                        "reason": REASON_SIGNING_UNAVAILABLE,
                    },
                    request_id,
                    session_id,
                    decider_user_id,
                )
            return {}, REASON_SIGNING_UNAVAILABLE
        requests_by_call: dict[str, dict] = {}
        for request in build_requests(pending, decider_user_id, key):
            requests_by_call[request["call_id"]] = request
            self._persist_execution_request(request)
            self._emit_execution_event(
                "execution_requested",
                "success",
                {
                    "confirm_id": request["confirm_id"],
                    "execution_id": request["execution_id"],
                    "call_id": request["call_id"],
                    "tool_name": request["tool_name"],
                    "args_digest": request["args_digest"],
                    "decider_user_id": request["decider_user_id"],
                    "owner_user_id": request["owner_user_id"],
                },
                request_id,
                session_id,
                decider_user_id,
            )
        return requests_by_call, None

    def _persist_execution_request(self, request: dict) -> None:
        """Best-effort durable request write (SPEC-037 R-4).

        Same posture as the SPEC-031 claim-time writes: a store failure
        degrades audit completeness, never the resumed stream.
        """
        try:
            EXECUTION_RECORD_STORE.save_request(make_execution_record(request))
        except Exception as exc:
            LOGGER.warning(
                "execution record request write failed for %s: %s",
                request["execution_id"],
                exc,
            )

    def _drain_trace_queue(
        self,
        trace_queue: asyncio.Queue,
        request_id: str,
        session_id: str,
        evidence_frames: list[dict[str, object]],
        execution_requests: dict[str, dict],
    ) -> list[dict[str, object]]:
        """Decorate queued trace frames and close any landed executions."""
        frames: list[dict[str, object]] = []
        while not trace_queue.empty():
            trace = trace_queue.get_nowait()
            decorated = {
                **trace,
                "request_id": request_id,
                "session_id": session_id,
            }
            if decorated.get("type") in EVIDENCE_FRAME_TYPES:
                evidence_frames.append(decorated)
            self._observe_tool_result(decorated, execution_requests)
            frames.append(decorated)
        return frames

    def _observe_tool_result(
        self,
        frame: dict[str, object],
        execution_requests: dict[str, dict],
    ) -> None:
        """Close the signed execution when its tool result lands (SPEC-037 R-4/R-5).

        A receipt closes a request that actually ran; an invocation-boundary
        rejection (R-3) marks the row rejected without a receipt — the call
        never reached the gateway. Requests are looked up by the parked
        call id riding the evidence frame.
        """
        if frame.get("type") != "tool_result":
            return
        request = execution_requests.get(frame.get("call_id"))
        key = self.settings.execution_signing_key
        if request is None or not key:
            return
        error = frame.get("error")
        error = error if isinstance(error, dict) else {}
        if error.get("code") == "EXECUTION_REJECTED":
            reason = error.get("reason") or "unknown"
            digest_match = (
                False if reason == REASON_ARGS_DIGEST_MISMATCH else None
            )
            try:
                EXECUTION_RECORD_STORE.mark_rejected(
                    request["confirm_id"],
                    request["call_id"],
                    reason,
                    digest_match,
                )
            except Exception as exc:
                LOGGER.warning(
                    "execution record rejection write failed for %s: %s",
                    request["execution_id"],
                    exc,
                )
            # The rejection audit already went out at the invocation
            # boundary (gateway_tools); nothing more to emit here.
            return
        if frame.get("status") == "success":
            status = "succeeded"
        elif error.get("code") == "TIMEOUT":
            status = "timeout"
        else:
            status = "failed"
        receipt = build_receipt(
            request,
            status,
            frame,
            str(frame.get("request_id") or ""),
            key,
        )
        try:
            EXECUTION_RECORD_STORE.save_receipt(
                request["confirm_id"],
                request["call_id"],
                receipt,
                True,
            )
        except Exception as exc:
            LOGGER.warning(
                "execution record receipt write failed for %s: %s",
                request["execution_id"],
                exc,
            )
        self._emit_execution_event(
            "execution_completed",
            "success" if status == "succeeded" else "error",
            {
                "confirm_id": request["confirm_id"],
                "execution_id": request["execution_id"],
                "call_id": request["call_id"],
                "tool_name": request["tool_name"],
                "status": status,
                "duration_ms": self._execution_duration_ms(request),
                "request_id": receipt["request_id"],
            },
            str(frame.get("request_id") or ""),
            str(frame.get("session_id") or ""),
            request["decider_user_id"],
        )

    @staticmethod
    def _execution_duration_ms(request: dict) -> int:
        """Whole-milliseconds between request signing and receipt close."""
        try:
            started = datetime.strptime(
                request["requested_at"], "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            return 0
        elapsed = datetime.now(timezone.utc) - started
        return max(int(elapsed.total_seconds() * 1000), 0)

    def _emit_execution_event(
        self,
        event_type: str,
        outcome: str,
        details: dict,
        request_id: str,
        session_id: str,
        decider_user_id: str,
    ) -> None:
        """Emit one execution audit event through the canonical emitter.

        Fire-and-forget with ``confirm_id`` in details and the resume's
        ``x-request-id`` forwarded, so the trail correlates
        ``confirmation_decided`` → ``execution_requested`` →
        ``tool_invoked`` → ``execution_completed`` (SPEC-037 R-5).
        """
        event = build_audit_event(
            event_type,
            request_id,
            outcome,
            details=details,
            subject=decider_user_id,
            username=decider_user_id,
            session_id=session_id,
        )
        emit_audit_event(self.settings, event)

    @staticmethod
    def _toolkit_risk_map(toolkit: object | None) -> dict[str, str]:
        """Map sanitized tool names to gateway risk tiers (SPEC-021 R-3).

        Only gateway-backed tools carry ``gateway_risk_level``; task tools
        and builtins stay absent, so their parked entries (which cannot
        happen today — they are auto-allowed) would omit ``risk_level``.
        """
        risks: dict[str, str] = {}
        for group in getattr(toolkit, "tool_groups", None) or []:
            for tool in getattr(group, "tools", None) or []:
                name = getattr(tool, "name", None)
                risk = getattr(tool, "gateway_risk_level", None)
                if name and risk:
                    risks[name] = risk
        return risks

    @staticmethod
    def _toolkit_gateway_name_map(toolkit: object | None) -> dict[str, str]:
        """Map sanitized tool names to dotted gateway canonical names.

        Parked tool calls carry the model-visible sanitized name, but the
        signed execution envelope (and the worker's gateway invocation)
        needs the canonical name the registry resolves; the envelope would
        otherwise fail closed with TOOL_NOT_FOUND after approval.
        """
        names: dict[str, str] = {}
        for group in getattr(toolkit, "tool_groups", None) or []:
            for tool in getattr(group, "tools", None) or []:
                name = getattr(tool, "name", None)
                gateway_name = getattr(tool, "gateway_tool_name", None)
                if name and gateway_name:
                    names[name] = gateway_name
        return names

    @staticmethod
    def _confirmation_message(event: object) -> str:
        """Prefer a kernel-provided message; fall back to a deterministic one."""
        metadata = getattr(event, "metadata", None)
        if isinstance(metadata, dict):
            message = metadata.get("message")
            if isinstance(message, str) and message.strip():
                return message
        return "Tool execution requires your confirmation."

    async def resume_confirmation(
        self,
        session_id: str,
        pending: PendingConfirmation,
        decision: str,
        user_name: str,
        request_id: str,
        bearer_token: str | None = None,
        model_id: str | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        """Resume a parked reply with the operator's decision (SPEC-020 R-2).

        The caller must pass the entry as returned by
        ``ConfirmationRegistry.claim`` — the claim runs before response
        headers go out, so one parked batch can never be resumed twice.
        Who may decide is enforced upstream by the platform-gateway
        approval-tier bridge (SPEC-030 R-3): a tier_2 confirmation can
        legitimately be resumed by a confirmer other than the session
        owner, so the kernel no longer asserts registry ownership.
        The resumed stream follows the v2 frame contract and begins with
        the matching ``confirmation_result`` frame. The confirmer's
        bearer token rides ``DELEGATED_TOKEN`` so the tool-gateway sees
        the approving identity on any resulting invocation.
        """
        from agentscope.event import ConfirmResult, UserConfirmResultEvent

        from agent_service.services.kernel_middleware import TOOL_EVIDENCE_SINK
        from agent_service.tools.gateway_tools import (
            CHAT_SESSION_ID,
            DELEGATED_TOKEN,
            EXECUTION_AUDIT_CONTEXT,
            EXECUTION_REJECTION,
            EXECUTION_REQUESTS,
        )

        # Pass the session's pinned model (SPEC-024 R-3) so the resumed
        # stream rebuilds against the same model that parked it.
        agent, _user_msg_cls, _bound_model_id = await self.ensure_agent(
            session_id, bearer_token, model_id
        )
        # SPEC-025 R-1: resumed frames belong to the same assistant turn as
        # the pre-park frames — no user message was added by the park, so
        # the count reproduces the original turn ordinal.  The original
        # stream captured its turn_index BEFORE the user message entered
        # the context (stream_events line ~892); the confirmation stream
        # runs AFTER the user message is already in context, so subtract 1
        # to align with the pre-park ordinal.
        turn_index = max(0, self._count_user_turns(agent) - 1)
        evidence_frames: list[dict[str, object]] = []
        confirmed = decision == "approve"
        confirm_event = UserConfirmResultEvent(
            reply_id=pending.reply_id,
            confirm_results=[
                ConfirmResult(confirmed=confirmed, tool_call=tool_call)
                for tool_call in pending.tool_calls
            ],
        )

        # SPEC-037 R-2: the signing envelope is built where the decision
        # and the parked arguments are both in hand — one signed request
        # per approved parked call, persisted and audited before any
        # invocation. Denials construct nothing; a missing key rejects
        # the whole batch fail-closed.
        execution_requests, execution_rejection = self._prepare_executions(
            pending, user_name, confirmed, request_id, session_id
        )

        trace_queue: asyncio.Queue = asyncio.Queue()
        sink_var = TOOL_EVIDENCE_SINK.set(trace_queue)
        token_var = DELEGATED_TOKEN.set(bearer_token)
        session_var = CHAT_SESSION_ID.set(session_id)
        requests_var = EXECUTION_REQUESTS.set(execution_requests or None)
        rejection_var = EXECUTION_REJECTION.set(execution_rejection)
        audit_var = EXECUTION_AUDIT_CONTEXT.set(
            {
                "settings": self.settings,
                "confirm_id": pending.confirm_id,
                "session_id": session_id,
                "request_id": request_id,
                "decider_user_id": user_name,
            }
            if confirmed
            else None
        )
        try:
            yield {
                "type": "confirmation_result",
                "confirm_id": pending.confirm_id,
                "status": "approved" if confirmed else "denied",
                # Echo the parked batch so downstream consumers (gateway
                # audit, portal card) can name the decided tools.
                "pending_calls": pending.pending_calls_payload(),
                "request_id": request_id,
                "session_id": session_id,
            }
            async for event in agent.reply_stream(confirm_event):
                self.clear_error()
                for decorated in self._drain_trace_queue(
                    trace_queue,
                    request_id,
                    session_id,
                    evidence_frames,
                    execution_requests,
                ):
                    yield decorated
                # A resumed turn can park again on another ASK-gated tool.
                frame = self._build_confirmation_frame(
                    event,
                    session_id,
                    user_name,
                    agent.toolkit,
                    turn_index=turn_index,
                    evidence_frames=evidence_frames,
                )
                if frame is not None:
                    yield {
                        **frame,
                        "request_id": request_id,
                        "session_id": session_id,
                    }
                    return
                yield self.normalize_event(event, request_id, session_id)
            for decorated in self._drain_trace_queue(
                trace_queue,
                request_id,
                session_id,
                evidence_frames,
                execution_requests,
            ):
                yield decorated
        finally:
            # Covers both completion and re-park (the early return above):
            # either way the frames drained so far belong to this turn.
            self._persist_evidence(
                session_id, request_id, turn_index, evidence_frames
            )
            DELEGATED_TOKEN.reset(token_var)
            CHAT_SESSION_ID.reset(session_var)
            EXECUTION_REQUESTS.reset(requests_var)
            EXECUTION_REJECTION.reset(rejection_var)
            EXECUTION_AUDIT_CONTEXT.reset(audit_var)
            TOOL_EVIDENCE_SINK.reset(sink_var)
            CONFIRMATION_REGISTRY.resolve(session_id, pending.confirm_id)
            # SPEC-031 R-1: idempotent safety net — the confirm route
            # already wrote the outcome at claim time (R-4), so this only
            # covers paths that resolved without a claim-time write.
            self._record_resolution(
                session_id,
                pending.confirm_id,
                "approved" if confirmed else "denied",
                user_name,
                decision,
            )

        self._snapshot_state(session_id, agent)

    async def expire_confirmation(
        self,
        session_id: str,
        confirm_id: str,
    ) -> None:
        """Close a TTL-expired parked reply without resuming it (SPEC-020 R-2).

        Feeds ``UserInterruptEvent`` so the kernel closes the parked calls
        with an interrupted result, then drops the registry entry. Never
        streams to a client; a failed interrupt still resolves the entry so
        the session cannot wedge. Claimed entries are unreachable here:
        an in-flight resume owns the entry and resolves it in its own
        ``finally``, so a racing expiry can never interrupt an approved
        batch mid-stream (``take_for_expiry`` raises instead).
        """
        from agentscope.event import UserInterruptEvent

        # Take-for-expiry ignores TTL (this path exists precisely to close
        # an expired entry) but claims the entry first, keeping the
        # interrupt single-flight against confirms and concurrent expiries.
        pending = CONFIRMATION_REGISTRY.take_for_expiry(session_id, confirm_id)
        try:
            agent, _user_msg_cls, _bound_model_id = await self.ensure_agent(
                session_id, None
            )
            interrupt = UserInterruptEvent(reply_id=pending.reply_id)
            async for _event in agent.reply_stream(interrupt):
                pass
            self._snapshot_state(session_id, agent)
        except Exception as exc:  # pragma: no cover - defensive cleanup
            LOGGER.warning(
                "expiring confirmation %s failed to interrupt parked reply: %s",
                confirm_id,
                exc,
            )
        finally:
            CONFIRMATION_REGISTRY.resolve(session_id, confirm_id)
            # SPEC-031 R-1: surface expiry as an outcome, not a
            # disappearance — the record stays visible as expired.
            self._record_resolution(
                session_id, confirm_id, "expired", None, None
            )
        LOGGER.info(
            "kernel confirmation expired",
            extra={"session_id": session_id, "confirm_id": confirm_id},
        )
