import asyncio
import json
import logging
from collections import OrderedDict
from collections.abc import AsyncIterator

from agent_service.core.metrics import (
    record_agent_state_error,
    record_evidence_write,
)
from agent_service.providers import get_provider
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services.agent_state_store import AGENT_STATE_STORE
from agent_service.services.evidence_store import (
    EVIDENCE_FRAME_TYPES,
    EVIDENCE_STORE,
    prepare_frames,
)
from agent_service.services.hitl_confirmations import (
    CONFIRMATION_REGISTRY,
    ConfirmationOwnerMismatch,
    PendingConfirmation,
)

LOGGER = logging.getLogger(__name__)
MAX_CACHED_AGENTS = 1000
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

    def _build_model(self):
        return self._provider.build_model(self.settings)

    async def _ensure_toolkit(self, bearer_token: str | None = None):
        """Build (once per token) and return the Toolkit with gateway tools.

        Toolkits are cached per delegated token so discovery runs once per
        token; tool closures read the current token from ``DELEGATED_TOKEN``
        at call time, so a cached toolkit keeps working across portal token
        refresh (SPEC-018 R-2). Empty discovery results are intentionally NOT
        cached: the next caller retries discovery instead of being poisoned.
        """
        cache_key = bearer_token or ""
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

    async def _build_agent(self, session_id: str, bearer_token: str | None = None):
        from agentscope.agent import Agent
        from agentscope.message import UserMsg

        toolkit = await self._ensure_toolkit(bearer_token)
        configs = self._build_kernel_configs()
        state = self._restore_state(session_id)
        agent = Agent(
            name=self.settings.agent_name,
            system_prompt=self.settings.system_prompt,
            model=self._build_model(),
            toolkit=toolkit,
            middlewares=self._build_middlewares(),
            state=state,
            **configs,
        )
        LOGGER.info(
            "kernel agent constructed",
            extra={
                "session_id": session_id,
                "max_iters": self.settings.max_iters,
                "context_trigger_ratio": self.settings.context_trigger_ratio,
                "tool_result_limit": self.settings.tool_result_limit,
                "timezone": self.settings.timezone,
                "model_max_retries": self.settings.model_max_retries,
                "state_restored": state is not None,
            },
        )
        return agent, UserMsg

    async def ensure_agent(self, session_id: str, bearer_token: str | None = None):
        """Return the agent bound to `session_id`, creating it on first use.

        Agents are keyed by session so conversation memory never crosses
        sessions; the cache is LRU-bounded to match the session store.
        Creation is serialised because it awaits: without the lock two
        concurrent turns on the same session would each build an agent and
        one would be discarded along with its memory.
        """
        cached = self._agents.get(session_id)
        if cached is not None:
            # Gateway tools recovered after this agent was built with an
            # empty toolkit (discovery failure): rebuild so the turn can see
            # them. Persisted state (SPEC-017 R-3) restores the memory.
            agent, _user_msg_cls = cached
            current_toolkit = await self._ensure_toolkit(bearer_token)
            if (
                self._count_gateway_tools(getattr(agent, "toolkit", None)) == 0
                and self._count_gateway_tools(current_toolkit) > 0
            ):
                LOGGER.info(
                    "gateway tools recovered; rebuilding kernel agent for "
                    "session %s",
                    session_id,
                )
                self._agents.pop(session_id, None)
            else:
                # Re-check membership: the await above opens a preemption
                # window where a concurrent turn's recovery branch may pop
                # this entry, or LRU eviction may remove it. A vanished
                # entry falls through to the locked path, which re-checks
                # the cache before building.
                if session_id in self._agents:
                    self._agents.move_to_end(session_id)
                    return cached
        async with self._agent_lock:
            cached = self._agents.get(session_id)
            if cached is not None:
                self._agents.move_to_end(session_id)
                return cached
            agent, user_msg_cls = await self._build_agent(session_id, bearer_token)
            self._agents[session_id] = (agent, user_msg_cls)
            while len(self._agents) > self._max_cached_agents:
                self._agents.popitem(last=False)
            return agent, user_msg_cls

    def build_unconfigured_message(self, message: str, session_id: str) -> str:
        return (
            "Platform baseline placeholder response. "
            f"AgentScope runtime not configured for session {session_id}. "
            f"Received '{message}'."
        )

    def build_provider_error_message(self, message: str, session_id: str) -> str:
        detail = self._last_error or "Unknown provider error."
        return (
            "Platform runtime fallback response. "
            f"AgentScope provider {self.provider_name()} failed for session {session_id}. "
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
    ) -> tuple[str, dict | None]:
        """Run one blocking turn.

        Returns the reply text and, when ``response_schema`` was supplied,
        the kernel-validated structured output carried on the final message
        (SPEC-017 R-2) — ``None`` when the turn ended without producing one.
        """
        if not self.is_configured():
            return self.build_unconfigured_message(message, session_id), None

        from agent_service.tools.gateway_tools import DELEGATED_TOKEN

        try:
            agent, user_msg_cls = await self.ensure_agent(session_id, bearer_token)
            # Expose the turn's delegated token to the cached tool closures
            # (SPEC-018 R-2). No evidence sink is set: blocking turns emit
            # no trace frames.
            token_var = DELEGATED_TOKEN.set(bearer_token)
            try:
                reply_msg = await agent.reply(
                    user_msg_cls(name=user_name, content=message),
                    structured_schema=response_schema,
                )
            finally:
                DELEGATED_TOKEN.reset(token_var)
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
            return self.build_provider_error_message(message, session_id), None

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
    ) -> AsyncIterator[dict[str, object]]:
        if not self.is_configured():
            async for event in self.fallback_stream(
                request_id=request_id,
                session_id=session_id,
                delta=self.build_unconfigured_message(message, session_id),
            ):
                yield event
            return

        from agent_service.services.kernel_middleware import TOOL_EVIDENCE_SINK
        from agent_service.tools.gateway_tools import DELEGATED_TOKEN

        try:
            # Ensure the agent (with the token-cached toolkit) exists.
            agent, user_msg_cls = await self.ensure_agent(session_id, bearer_token)

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
                        event, session_id, user_name, agent.toolkit
                    )
                    if frame is not None:
                        yield {
                            **frame,
                            "request_id": request_id,
                            "session_id": session_id,
                        }
                        break
                    yield self.normalize_event(event, request_id, session_id)

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
                delta=self.build_provider_error_message(message, session_id),
            ):
                yield event

    # --- HITL confirmation bridging (SPEC-020 R-2) ---

    def _build_confirmation_frame(
        self,
        event: object,
        session_id: str,
        user_name: str,
        toolkit: object | None = None,
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
        pending = CONFIRMATION_REGISTRY.register(
            session_id=session_id,
            user_id=user_name,
            reply_id=str(getattr(event, "reply_id", "") or ""),
            tool_calls=list(getattr(event, "tool_calls", None) or []),
            timeout=self.settings.hitl_confirm_timeout,
            risk_levels=self._toolkit_risk_map(toolkit),
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
    ) -> AsyncIterator[dict[str, object]]:
        """Resume a parked reply with the operator's decision (SPEC-020 R-2).

        The caller must pass the entry as returned by
        ``ConfirmationRegistry.claim`` — the claim runs before response
        headers go out, so one parked batch can never be resumed twice.
        Raises ``ConfirmationOwnerMismatch`` when the confirmer does not
        own the parked entry; the v2 route maps it to an error frame.
        The resumed stream follows the v2 frame contract and begins with
        the matching ``confirmation_result`` frame. The confirmer's
        bearer token rides ``DELEGATED_TOKEN`` so the tool-gateway sees
        the approving identity on any resulting invocation.
        """
        from agentscope.event import ConfirmResult, UserConfirmResultEvent

        from agent_service.services.kernel_middleware import TOOL_EVIDENCE_SINK
        from agent_service.tools.gateway_tools import DELEGATED_TOKEN

        if pending.user_id != user_name:
            raise ConfirmationOwnerMismatch(user_name)

        agent, _user_msg_cls = await self.ensure_agent(session_id, bearer_token)
        # SPEC-025 R-1: resumed frames belong to the same assistant turn as
        # the pre-park frames — no user message was added by the park, so
        # the count reproduces the original turn ordinal.
        turn_index = self._count_user_turns(agent)
        evidence_frames: list[dict[str, object]] = []
        confirmed = decision == "approve"
        confirm_event = UserConfirmResultEvent(
            reply_id=pending.reply_id,
            confirm_results=[
                ConfirmResult(confirmed=confirmed, tool_call=tool_call)
                for tool_call in pending.tool_calls
            ],
        )

        trace_queue: asyncio.Queue = asyncio.Queue()
        sink_var = TOOL_EVIDENCE_SINK.set(trace_queue)
        token_var = DELEGATED_TOKEN.set(bearer_token)
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
                # A resumed turn can park again on another ASK-gated tool.
                frame = self._build_confirmation_frame(
                    event, session_id, user_name, agent.toolkit
                )
                if frame is not None:
                    yield {
                        **frame,
                        "request_id": request_id,
                        "session_id": session_id,
                    }
                    return
                yield self.normalize_event(event, request_id, session_id)
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
            # Covers both completion and re-park (the early return above):
            # either way the frames drained so far belong to this turn.
            self._persist_evidence(
                session_id, request_id, turn_index, evidence_frames
            )
            DELEGATED_TOKEN.reset(token_var)
            TOOL_EVIDENCE_SINK.reset(sink_var)
            CONFIRMATION_REGISTRY.resolve(session_id, pending.confirm_id)

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
            agent, _user_msg_cls = await self.ensure_agent(session_id, None)
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
        LOGGER.info(
            "kernel confirmation expired",
            extra={"session_id": session_id, "confirm_id": confirm_id},
        )
