import asyncio
import json
import logging
from collections import OrderedDict
from collections.abc import AsyncIterator
from dataclasses import dataclass

from agent_service.core.metrics import record_evidence_write
from agent_service.providers import get_provider
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services.agent_role import AgentRole, current_agent_role_value
# Decomposition Stage 2: the persisted-state store binding stays re-exported
# here even though ``restore_state`` / ``snapshot_state`` now live in the
# AgentRegistry collaborator. The collaborator resolves ``AGENT_STATE_STORE``
# through *this* module namespace at call time, so the long-standing test
# surface ``monkeypatch.setattr(runtime_kernel, "AGENT_STATE_STORE", ...)``
# stays authoritative after the move (behavior byte-identical). Do not drop it.
from agent_service.services.agent_state_store import AGENT_STATE_STORE
from agent_service.services.audit_emitter import (
    # Decomposition Stage 3: ``build_audit_event`` moved with the emitter into
    # the ExecutionDispatcher collaborator. ``emit_audit_event`` stays
    # re-exported here even though ``_emit_execution_event`` now lives in the
    # collaborator: the dispatcher resolves it through *this* module namespace
    # at call time, so the long-standing test surface
    # ``monkeypatch.setattr("agent_service.runtime_kernel.emit_audit_event", ...)``
    # stays authoritative after the move (behavior byte-identical). Do not drop it.
    emit_audit_event,
)
from agent_service.services.authoring_trace import (
    AUTHORING_TRACE_STORE,
    make_trace_step,
    origin_of_url,
)
from agent_service.services.evidence_store import (
    EVIDENCE_STORE,
    prepare_frames,
)
from agent_service.services.execution_records import (
    EXECUTION_RECORD_STORE,
)
from agent_service.services.delegated_identity import (
    DelegatedIdentityError, VerifiedHuman,
    session_requester, verify_delegated_human,
)
from agent_service.services.execution_signing import (
    REASON_ARGS_DIGEST_MISMATCH,
    build_receipt,
)
from agent_service.services.flow_approvals import (
    BROWSER_WRITE_TOOLS,
    FLOW_APPROVALS,
    FLOW_CONTEXTS,
    FLOW_KILLING_ERROR_CODES,
)
from agent_service.services.hitl_confirmations import (
    PendingConfirmation,
)
from agent_service.schemas.v2 import AuthorizationRequired
from agent_service.services.kernel_agents import AgentRegistry
from agent_service.services.kernel_confirmations import ConfirmationCoordinator
from agent_service.services.kernel_executions import ExecutionDispatcher
from agent_service.services.kernel_middleware import (
    AuthorizationTurn,
)
from agent_service.services.kernel_models import ModelResolver
from agent_service.services.kernel_status import KernelStatus
from agent_service.services.kernel_streaming import TurnStreamer
from agent_service.services.kernel_toolkits import ToolkitAssembler
# Decomposition Stage 4a: ``MODEL_CATALOG`` stays re-exported here even though
# the unknown-model fail-closed guard + provider-error attribution now live in
# the TurnStreamer collaborator. The collaborator resolves ``MODEL_CATALOG``
# through *this* module namespace at call time, so the long-standing test
# surface ``monkeypatch.setattr(runtime_kernel, "MODEL_CATALOG", ...)`` stays
# authoritative after the move (behavior byte-identical). Do not drop it.
from agent_service.services.model_catalog import MODEL_CATALOG
from agent_service.services.prose_redaction import (
    StreamingProseRedactor,
    credential_literals,
    generated_credential_literals,
)
from agent_service.services.secret_params import parameterize_for_trace
from agent_service.services.serialization import make_serializable

LOGGER = logging.getLogger(__name__)
MAX_CACHED_AGENTS = 1000


@dataclass(frozen=True)
class BlockingReply:
    content: str
    structured_output: dict | None = None
    authorization_required: AuthorizationRequired | None = None
    # SPEC-071 R-2: the catalog id the per-turn router actually served when
    # routing fired; ``None`` when the turn kept its resolved model. Additive —
    # the two-value ``__iter__`` unpacking contract below is unchanged.
    effective_model: str | None = None

    def __iter__(self):
        """Preserve the existing two-value internal unpacking contract."""
        yield self.content
        yield self.structured_output


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

# Frames that settle a turn for the portal: it marks the turn complete and
# never rewrites the accumulated reply text afterwards, so a streaming prose
# redactor must release its held-back tail *before* one of these is yielded.
# Mirrors the portal decoder's own TERMINAL_EVENT_TYPES.
TERMINAL_STREAM_EVENTS = frozenset({"message_end", "reply_end"})

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


def flush_prose_frames(
    redactor: StreamingProseRedactor,
    request_id: str,
    session_id: str,
) -> list[dict[str, object]]:
    """A redactor's held-back tail as a final ``message_delta`` frame.

    Streaming prose redaction withholds the last characters of a chunk until
    it knows they are not the start of a credential, so every stream exit has
    to release them. The portal accumulates deltas (``turn.replyText +=
    frame.text``) and has no handler that overwrites them from a
    complete-message frame, so a tail that is never flushed is dropped from
    the live view rather than merely arriving late.

    ``flush`` empties the buffer, which makes this safe to call at more than
    one exit point on the same stream: only the first returns a frame.
    """
    tail = redactor.flush()
    if not tail:
        return []
    return [
        {
            "event": "message_delta",
            "request_id": request_id,
            "session_id": session_id,
            "delta": tail,
        }
    ]


class AgentKernel:
    def __init__(
        self,
        settings: RuntimeSettings | None = None,
        max_cached_agents: int = MAX_CACHED_AGENTS,
    ) -> None:
        self.settings = settings or RuntimeSettings.from_env()
        self._provider = get_provider(self.settings.provider)
        # Ephemeral masking knowledge survives context compaction, never a snapshot.
        self._generated_literals: OrderedDict[str, set[str]] = OrderedDict()
        # Decomposition Stage 1: the runtime-status projections (mode / state /
        # metadata / feature-flags / hint) and the ``_last_error`` slot live in a
        # KernelStatus collaborator; the per-token toolkit cache (SPEC-008 R-5)
        # and the discovery → HITL / read-only / role-narrow pipeline live in a
        # ToolkitAssembler collaborator. AgentKernel keeps thin delegators plus
        # read/write-through properties for ``_last_error`` and
        # ``_mutating_tools_excluded`` (SPEC-021 R-3), so the public API and
        # every caller/test stay byte-identical. See
        # docs/workspace/agent-kernel-decomposition-spike.md.
        self._status = KernelStatus(self)
        self._toolkit_asm = ToolkitAssembler(self)
        # Decomposition Stage 2: model selection + router attribution
        # (SPEC-024/026/027/071) live in a ModelResolver collaborator; the
        # per-session agent cache (LRU-bounded ``_agents`` + ``_agent_lock``) and
        # its build / restore / snapshot lifecycle (SPEC-017) live in an
        # AgentRegistry collaborator. AgentKernel keeps thin delegators plus
        # read-through ``_agents`` / ``_max_cached_agents`` properties, so every
        # caller and test — including direct ``kernel._agents[...]`` access and
        # ``monkeypatch.setattr(kernel, "_build_agent", ...)`` — stays
        # byte-identical. Cross-cluster calls route back through these
        # delegators. See the decomposition spike memo (Stage 2).
        self._model_resolver = ModelResolver(self)
        self._agent_registry = AgentRegistry(self, max_cached_agents)
        # Decomposition Stage 3: the signed-request / receipt / ledger
        # orchestration path (SPEC-037/051/063/077) — the durable recovery
        # store, the run-identity / ``RunGuard`` bind, the per-action and
        # flow-unlock signing sites, the durable request write, the receipt
        # timing helper and the execution-audit emitter — lives in an
        # ExecutionDispatcher collaborator. It owns the ``_recovery`` /
        # ``_recovery_built`` slot (SPEC-063 R-2: built lazily and only when
        # admission is enabled; ``None`` keeps the legacy in-process handoff
        # path byte-identical). AgentKernel keeps thin delegators plus
        # read/write-through ``_recovery`` / ``_recovery_built`` properties, so
        # every caller and test stays byte-identical — ``kernel._execution_recovery()``
        # in api/v2/routes + services/execution_recovery, the
        # ``flow_signer=self._sign_flow_execution`` middleware binding, and
        # ``monkeypatch.setattr(kernel, "_execution_recovery"/"_bind_guard", ...)``.
        # Sibling execution calls route back through these delegators, and the
        # emitter resolves ``emit_audit_event`` through this module namespace at
        # call time. See the decomposition spike memo (Stage 3).
        self._executions = ExecutionDispatcher(self)
        # Decomposition Stage 4a: the turn-streaming / reply path — the
        # streaming turn (``stream_events``), the blocking turn
        # (``reply_text``), the event→frame normalizer, the fallback stream +
        # message builders, the authorization-stream cleanup, the SPEC-062 R-3
        # reveal-on-commit delivery buffers and the trace-queue drainer — lives
        # in a TurnStreamer collaborator that owns no mutable state. AgentKernel
        # keeps thin delegators, so every caller (api/v2/routes +
        # services/runtime_service / orchestration) and every test that calls
        # ``kernel.stream_events`` / ``kernel.reply_text`` /
        # ``kernel.normalize_event`` or monkeypatches ``kernel._build_agent`` /
        # ``kernel._snapshot_state`` / ``kernel._persist_evidence`` on the
        # instance stays byte-identical. Sibling calls route back through these
        # delegators; ``MODEL_CATALOG`` + the stream-frame primitives resolve
        # through this module namespace at call time. See the decomposition
        # spike memo (Stage 4a).
        self._stream = TurnStreamer(self)
        # Decomposition Stage 4b: the HITL park / resume / expire path
        # (SPEC-020/030/031/051/054/055/062/063) — the park registration +
        # ``confirmation_request`` frame build, the browser-write predicate +
        # flow-authority arming, the durable-resolution write, the resume
        # stream and the TTL expiry interrupt — lives in a
        # ConfirmationCoordinator collaborator that owns no mutable state (the
        # parked entries live in CONFIRMATION_REGISTRY, the durable cards in
        # CONFIRMATION_RECORD_STORE). AgentKernel keeps thin delegators, so the
        # confirm route + expiry sweeper and every test that patches
        # ``kernel.resume_confirmation`` / ``kernel.expire_confirmation`` /
        # ``kernel._resume_identities`` on the instance stay byte-identical.
        # Sibling calls route back through these delegators; the
        # ``runtime_kernel``-defined stream primitives resolve through this
        # module namespace at call time. See the decomposition spike memo
        # (Stage 4b).
        self._confirm = ConfirmationCoordinator(self)

    @property
    def _recovery(self):
        """Read/write-through to the ExecutionDispatcher's durable recovery slot.

        Kept as a property so the direct ``kernel._recovery`` /
        ``kernel._recovery_built`` reads (test_runtime_kernel) and the lazy
        build/cache inside ``_execution_recovery`` stay unchanged after the
        Stage-3 extraction — the collaborator owns the live slot.
        """
        return self._executions._recovery

    @_recovery.setter
    def _recovery(self, value) -> None:
        self._executions._recovery = value

    @property
    def _recovery_built(self) -> bool:
        return self._executions._recovery_built

    @_recovery_built.setter
    def _recovery_built(self, value: bool) -> None:
        self._executions._recovery_built = value

    def _execution_recovery(self):
        """The agent-side durable recovery store, or ``None`` when disabled
        (SPEC-063 R-2) — delegates to ExecutionDispatcher, the single source
        shared with the api/v2 + execution_recovery availability projections."""
        return self._executions._execution_recovery()

    def _resolve_run_id(
        self, recovery, session_id, owner_user_id, flow_approval=None
    ):
        """The durable run identity for this human root turn (SPEC-063 R-4) —
        delegates to ExecutionDispatcher (behavior byte-identical)."""
        return self._executions._resolve_run_id(
            recovery, session_id, owner_user_id, flow_approval=flow_approval
        )

    def _bind_guard(self, recovery, run_id, session_id, owner_user_id):
        """Build the turn's ``RunGuard`` bound to a resolved run identity —
        delegates to ExecutionDispatcher (behavior byte-identical)."""
        return self._executions._bind_guard(
            recovery, run_id, session_id, owner_user_id
        )

    @property
    def _last_error(self) -> str | None:
        """Read/write-through to the KernelStatus collaborator's error slot.

        Kept as a property so the direct ``kernel._last_error = ...`` test
        coupling (test_runtime_kernel / test_prose_redaction) and any reader
        stay unchanged after the Stage-1 extraction.
        """
        return self._status._last_error

    @_last_error.setter
    def _last_error(self, value: str | None) -> None:
        self._status._last_error = value

    def mode(self) -> str:
        return self._status.mode()

    def is_configured(self) -> bool:
        return self._status.is_configured()

    def runtime_state(self) -> str:
        return self._status.runtime_state()

    def provider_name(self) -> str:
        return self._status.provider_name()

    def provider_description(self) -> str:
        return self._status.provider_description()

    def last_error(self) -> str | None:
        return self._status.last_error()

    def runtime_metadata(self) -> dict[str, object]:
        return self._status.runtime_metadata()

    def feature_flags(self) -> list[dict[str, object]]:
        """The curated feature-flag inventory (SPEC-072 R-4) — delegates to
        KernelStatus, the single source shared with ``routing_available()``."""
        return self._status.feature_flags()

    def configuration_hint(self) -> str:
        return self._status.configuration_hint()

    def remember_error(self, exc: Exception, turn_literals=()) -> None:
        self._status.remember_error(exc, turn_literals)

    def clear_error(self) -> None:
        self._status.clear_error()

    def _build_model(self, model_id: str | None = None):
        """Build the AgentScope model for a turn (SPEC-024 R-3) — delegates to
        the ModelResolver collaborator."""
        return self._model_resolver.build_model(model_id)

    def _normalize_model_id(self, model_id: str | None) -> str:
        """Canonical id bound to a turn (SPEC-026 R-3) — delegates to the
        ModelResolver collaborator."""
        return self._model_resolver.normalize_model_id(model_id)

    @property
    def _mutating_tools_excluded(self) -> bool:
        """Read-through to the ToolkitAssembler's SPEC-021 R-3 posture flag.

        Kept as a property so the direct ``kernel._mutating_tools_excluded``
        test coupling (test_hitl_confirmations) stays unchanged; the flag is
        written only inside the collaborator's ``filter_mutating_for_hitl``.
        """
        return self._toolkit_asm._mutating_tools_excluded

    async def _ensure_toolkit(
        self, bearer_token: str | None = None, read_only: bool = False
    ):
        """Per-token toolkit assembly — delegates to ToolkitAssembler (the
        SPEC-073/076 ``_ensure_toolkit(read_only=True)`` narrowing seam)."""
        return await self._toolkit_asm.ensure_toolkit(bearer_token, read_only)

    def _filter_mutating_for_hitl(self, definitions: list[dict]) -> list[dict]:
        return self._toolkit_asm.filter_mutating_for_hitl(definitions)

    def _filter_read_only(self, definitions: list[dict]) -> list[dict]:
        return self._toolkit_asm.filter_read_only(definitions)

    def _narrow_for_role(
        self, definitions: list[dict], role: AgentRole
    ) -> list[dict]:
        return self._toolkit_asm.narrow_for_role(definitions, role)

    def _build_task_tools(self) -> list:
        return self._toolkit_asm.build_task_tools()

    def _routed_candidate_name(self, agent) -> str | None:
        """The candidate the per-turn router chose for this reply (SPEC-071 R-2)
        — delegates to the ModelResolver collaborator."""
        return self._model_resolver.routed_candidate_name(agent)

    def _candidate_model_id(self, name: str | None) -> str | None:
        """Map a routed candidate name back to its catalog model id — delegates
        to the ModelResolver collaborator."""
        return self._model_resolver.candidate_model_id(name)

    def _effective_model_id(self, agent) -> str | None:
        """The catalog id the per-turn router served, or ``None`` (SPEC-071 R-2)
        — delegates to the ModelResolver collaborator."""
        return self._model_resolver.effective_model_id(agent)

    def routing_available(self) -> bool:
        """Whether per-turn routing is configured at all (SPEC-072 R-1).

        Delegates to KernelStatus — the single source of truth shared by the
        catalog boolean (R-1), ``_resolve_model``'s ``auto`` branch (R-2), and
        the ``model_routing`` feature flag (R-4), so they can never disagree.
        """
        return self._status.routing_available()

    def _router_armed(self, routing_allowed: bool) -> bool:
        """Whether the per-turn router is registered for this turn (SPEC-071 R-2)
        — delegates to the ModelResolver collaborator, which reads the
        deployment half back through ``routing_available()``."""
        return self._model_resolver.router_armed(routing_allowed)

    def _build_middlewares(self, routing_allowed: bool = False) -> list:
        """Compose the kernel middleware stack (SPEC-018).

        Permission, evidence, and LLM-token (SPEC-065 R-1) middlewares are
        always registered; OTel kernel tracing (R-3) and the reply token budget
        (R-4) are opt-in via settings and stay absent when unconfigured.

        SPEC-071 R-2: the opt-in ``ModelRouterMiddleware`` is appended only when
        the knob is on, a candidate map is configured, and ``routing_allowed``
        (this turn resolved to the default — no explicit request or pin). It is
        an ``on_reply`` middleware, a separate hook chain from
        ``TokenUsageMiddleware``'s ``on_model_call``, so its list position does
        not affect token observation of the routed model's reply (Stage-0 S0-1).
        """
        from agent_service.services.kernel_middleware import (
            GatewayPermissionMiddleware,
            TokenUsageMiddleware,
            ToolEvidenceMiddleware,
        )

        settings = self.settings
        middlewares: list = [
            GatewayPermissionMiddleware(flow_signer=self._sign_flow_execution),
            ToolEvidenceMiddleware(
                data_summary_max_chars=settings.tool_data_summary_max_chars,
                data_max_chars=settings.tool_data_max_chars,
            ),
            # SPEC-065 R-1: always-on LLM token observation (no knob) — a pure
            # ``on_model_call`` mirror of the provider's own usage into
            # ``agent_llm_tokens_total``. Streaming-aware; records no cost.
            TokenUsageMiddleware(),
        ]
        if settings.target_authorization_enabled:
            from agent_service.services.kernel_middleware import TargetAuthorizationMiddleware

            # Evidence observes sanitized and stopped results; authorization owns
            # permission before the existing gate and model calls before budgets.
            middlewares = [middlewares[1], TargetAuthorizationMiddleware(), middlewares[0], *middlewares[2:]]
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
        if self._router_armed(routing_allowed):
            from agentscope.middleware import (
                ChatModelCandidate,
                ModelRouterMiddleware,
            )

            # An unknown/revoked catalog id in the map raises UnknownModelError
            # here (fail-closed at build, SPEC-071 R-2): a router is never armed
            # against a model the credential-gated catalog does not have. The
            # classifier rides an existing catalog ChatModelBase and routes via
            # ``generate_structured_output`` — no dedicated classifier provider.
            middlewares.append(
                ModelRouterMiddleware(
                    classifier_model=self._build_model(settings.model_router_model),
                    candidates=[
                        ChatModelCandidate(
                            name=spec.name,
                            model=self._build_model(spec.model_id),
                            description=spec.description,
                        )
                        for spec in settings.model_router_candidates
                    ],
                )
            )
        return middlewares

    def _count_gateway_tools(self, toolkit) -> int:
        return self._toolkit_asm.count_gateway_tools(toolkit)

    @property
    def _agents(self):
        """Read-through to the AgentRegistry's live per-session agent cache.

        Kept as a property so the direct ``kernel._agents[...]`` test coupling
        (test_prose_redaction) and ``_prose_redactor``'s protected-key scan stay
        unchanged; item assignment mutates the registry's OrderedDict in place.
        """
        return self._agent_registry._agents

    @property
    def _max_cached_agents(self) -> int:
        """Read-through to the AgentRegistry's LRU bound (SPEC-017)."""
        return self._agent_registry._max_cached_agents

    def _build_kernel_configs(self):
        """Settings-driven kernel configs (SPEC-017 R-1) — delegates to the
        AgentRegistry collaborator."""
        return self._agent_registry.build_kernel_configs()

    def _restore_state(self, session_id: str):
        """Load a persisted AgentState for the session, if any (SPEC-017 R-3) —
        delegates to the AgentRegistry collaborator."""
        return self._agent_registry.restore_state(session_id)

    def _snapshot_state(self, session_id: str, agent, turn_literals=()) -> None:
        """Persist the agent state after a completed turn (SPEC-017 R-3) —
        delegates to the AgentRegistry collaborator."""
        return self._agent_registry.snapshot_state(session_id, agent, turn_literals)

    @staticmethod
    def _count_user_turns(agent) -> int:
        """User-message count in the agent context (SPEC-025 turn index) —
        delegates to the AgentRegistry collaborator."""
        return AgentRegistry.count_user_turns(agent)

    def _user_text_literals(self, agent, message: str) -> frozenset[str]:
        """Credential literals the operator typed in this session's prose.

        Harvested from every user turn in the agent context plus the message
        being sent now, which the context does not yet hold: ``stream_events``
        captures its turn ordinal before the turn mutates the context, so the
        current message is appended only as the reply runs. Including it is
        what lets the very first turn mask its own echoed password, and
        walking the rest is what catches a cross-turn echo.

        Best-effort by design — a context this cannot read yields the current
        message's literals alone, which is still the turn that matters.
        """
        texts = [message]
        try:
            for msg in getattr(agent.state, "context", None) or []:
                if getattr(msg, "role", None) != "user":
                    continue
                texts.append(extract_text(getattr(msg, "content", "")))
        except Exception as exc:  # pragma: no cover - defensive harvest
            LOGGER.debug("prose literal harvest from context failed: %s", type(exc).__name__)
        literals: set[str] = set()
        for text in texts:
            literals |= credential_literals(text)
        return frozenset(literals)

    def _prose_redactor(self, agent, message: str, session_id: str) -> StreamingProseRedactor:
        generated = self._generated_literals.setdefault(session_id, set())
        generated.update(generated_credential_literals(make_serializable(getattr(agent, "state", None))))
        self._generated_literals.move_to_end(session_id)
        # A live agent may retain a compacted prose copy after its tool block
        # disappears. Never evict its masking knowledge on an independent LRU.
        protected = {key.removesuffix("::read-only") for key in self._agents}
        protected.add(session_id)
        for key in list(self._generated_literals):
            if len(self._generated_literals) <= max(1, self._max_cached_agents):
                break
            if key not in protected:
                self._generated_literals.pop(key)
        return StreamingProseRedactor(self._user_text_literals(agent, message), generated)

    def forget_session(self, session_id: str) -> None:
        """Drop ephemeral agents and literal knowledge after an owner deletion —
        delegates to the AgentRegistry collaborator."""
        return self._agent_registry.forget_session(session_id)

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
                # SPEC-075/076: attribute the turn's evidence to the acting
                # agent-role. Live on the SPEC-076 orchestration path — a
                # diagnostician member / orchestrator synthesis turn binds one,
                # so its evidence row carries it verbatim. The unscoped single-
                # agent turn binds none, so the store omits it and a legacy turn
                # replays byte-identically with no empty artifact.
                agent_role=current_agent_role_value(),
            )
            record_evidence_write("ok")
        except Exception as exc:
            record_evidence_write("error")
            LOGGER.warning(
                "evidence persistence failed for session %s: %s",
                session_id,
                type(exc).__name__,
            )

    async def _build_agent(
        self,
        session_id: str,
        bearer_token: str | None = None,
        model_id: str | None = None,
        read_only: bool = False,
        routing_allowed: bool = False,
    ):
        """Construct a session agent — delegates to the AgentRegistry collaborator."""
        return await self._agent_registry.build_agent(
            session_id, bearer_token, model_id, read_only, routing_allowed
        )

    async def ensure_agent(
        self,
        session_id: str,
        bearer_token: str | None = None,
        model_id: str | None = None,
        read_only: bool = False,
        routing_allowed: bool = False,
    ):
        """Return the agent bound to ``session_id``, creating it on first use
        (SPEC-024 R-3 model-switch cache, SPEC-071 R-2 router split, LRU bound)
        — delegates to the AgentRegistry collaborator."""
        return await self._agent_registry.ensure_agent(
            session_id, bearer_token, model_id, read_only, routing_allowed
        )

    def build_unconfigured_message(self, message: str, session_id: str) -> str:
        """Baseline placeholder reply text — delegates to TurnStreamer."""
        return self._stream.build_unconfigured_message(message, session_id)

    def build_provider_error_message(
        self,
        message: str,
        session_id: str,
        model_id: str | None = None,
    ) -> str:
        """Provider-failure fallback reply text — delegates to TurnStreamer."""
        return self._stream.build_provider_error_message(message, session_id, model_id)

    def fallback_stream(
        self,
        request_id: str,
        session_id: str,
        delta: str,
    ) -> AsyncIterator[dict[str, object]]:
        """Deterministic 3-frame fallback stream — delegates to TurnStreamer.

        Returns the collaborator's async generator directly (no wrapper frame),
        so ``async for`` semantics are byte-identical.
        """
        return self._stream.fallback_stream(request_id, session_id, delta)

    def _requester_for_turn(self, session_id: str, user_id: str, bearer: str | None):
        if not self.settings.target_authorization_enabled:
            return None
        from agent_service.services.session_service import get_session

        human = verify_delegated_human(self.settings, bearer, user_id=user_id)
        return session_requester(get_session(session_id, user_id), human)

    def _resume_identities(self, pending, session_id, user_id, bearer):
        if not self.settings.target_authorization_enabled:
            return None, None
        from agent_service.services.session_service import get_session

        session = get_session(session_id, pending.user_id)
        if session.session_id != pending.session_id:
            raise DelegatedIdentityError()
        if session.requester_sub is None and pending.requester_identity is None:
            return None, None  # Legacy sessions never gain a requester binding.
        requester = verify_delegated_human(self.settings, pending.requester_delegated_token, user_id=pending.user_id)
        session_requester(session, requester)
        saved = pending.requester_identity
        if not isinstance(saved, VerifiedHuman) or not requester.matches(saved.namespace, saved.subject):
            raise DelegatedIdentityError()
        decider = verify_delegated_human(self.settings, bearer, user_id=user_id)
        return requester, decider

    async def reply_text(
        self,
        message: str,
        session_id: str,
        user_name: str,
        bearer_token: str | None = None,
        response_schema: dict | None = None,
        model_id: str | None = None,
        read_only: bool = False,
        routing_allowed: bool = False,
    ) -> BlockingReply:
        """Run one blocking turn — delegates to TurnStreamer (byte-identical)."""
        return await self._stream.reply_text(
            message,
            session_id,
            user_name,
            bearer_token=bearer_token,
            response_schema=response_schema,
            model_id=model_id,
            read_only=read_only,
            routing_allowed=routing_allowed,
        )

    def normalize_event(
        self,
        event: object,
        request_id: str,
        session_id: str,
        redactor: StreamingProseRedactor | None = None,
    ) -> dict[str, object]:
        """One AgentScope event as a normalized stream frame — delegates to
        TurnStreamer (the ``agent-stream-event`` contract is byte-identical)."""
        return self._stream.normalize_event(
            event, request_id, session_id, redactor=redactor
        )

    def stream_events(
        self,
        message: str,
        request_id: str,
        session_id: str,
        user_name: str,
        bearer_token: str | None = None,
        model_id: str | None = None,
        routing_allowed: bool = False,
    ) -> AsyncIterator[dict[str, object]]:
        """Stream one turn as v2 frames — delegates to TurnStreamer.

        Returns the collaborator's async generator *directly* (no wrapper
        frame), so ``async for`` / ``aclosing`` semantics and the ``finally``
        ContextVar resets (which depend on ``aclose`` reaching the generator
        that armed them) are byte-identical to the pre-extraction method.
        """
        return self._stream.stream_events(
            message,
            request_id,
            session_id,
            user_name,
            bearer_token=bearer_token,
            model_id=model_id,
            routing_allowed=routing_allowed,
        )

    @staticmethod
    async def _finish_authorization_stream(turn: AuthorizationTurn, stream) -> None:
        """Finish a latched SDK reply in its owning task — delegates to
        TurnStreamer (byte-identical)."""
        await TurnStreamer._finish_authorization_stream(turn, stream)

    # --- HITL confirmation bridging (SPEC-020 R-2) ---

    def _flush_pending_deliveries(self, trace_queue: asyncio.Queue) -> None:
        """Drain STREAM_PENDING_DELIVERIES onto the trace queue — delegates to
        TurnStreamer (SPEC-062 R-3 reveal-on-commit)."""
        self._stream._flush_pending_deliveries(trace_queue)

    async def _discard_burned_deliveries(
        self, deliveries: list[dict], owner_token: str | None
    ) -> None:
        """Discard burned held deliveries at the gateway — delegates to
        TurnStreamer (SPEC-062 R-3 deny-path hardening)."""
        await self._stream._discard_burned_deliveries(deliveries, owner_token)

    def _drain_held_deliveries(self) -> tuple[dict, ...]:
        """Drain both delivery buffers into a tuple for a parked card —
        delegates to TurnStreamer (SPEC-062 R-3)."""
        return self._stream._drain_held_deliveries()

    def _build_confirmation_frame(
        self,
        event: object,
        session_id: str,
        user_name: str,
        toolkit: object | None = None,
        turn_index: int = 0,
        evidence_frames: list[dict[str, object]] | None = None,
        run_id: str | None = None,
    ) -> dict[str, object] | None:
        """Decomposition Stage 4b: delegates to ConfirmationCoordinator (the
        kernel ASK park registration + ``confirmation_request`` frame build).
        Also reached cross-collaborator from TurnStreamer's ``stream_events``."""
        return self._confirm._build_confirmation_frame(
            event,
            session_id,
            user_name,
            toolkit,
            turn_index=turn_index,
            evidence_frames=evidence_frames,
            run_id=run_id,
        )

    @staticmethod
    def _extract_browser_element_map(
        evidence_frames: list[dict[str, object]],
    ) -> dict[int, str]:
        """Decomposition Stage 4b: delegates to ConfirmationCoordinator."""
        return ConfirmationCoordinator._extract_browser_element_map(evidence_frames)

    @staticmethod
    def _record_resolution(
        session_id: str,
        confirm_id: str,
        status: str,
        decider_user_id: str | None,
        decision: str | None,
    ) -> None:
        """Decomposition Stage 4b: delegates to ConfirmationCoordinator."""
        ConfirmationCoordinator._record_resolution(
            session_id, confirm_id, status, decider_user_id, decision
        )

    # --- Signed execution requests and receipts (SPEC-037 R-2/R-4/R-5) ---

    def _prepare_executions(
        self,
        pending: PendingConfirmation,
        decider_user_id: str,
        confirmed: bool,
        request_id: str,
        session_id: str,
        *,
        requester: VerifiedHuman | None = None,
        decider: VerifiedHuman | None = None,
    ) -> tuple[dict[str, dict], str | None]:
        """Build, persist, and audit the signed requests (SPEC-037 R-2) —
        delegates to ExecutionDispatcher (behavior byte-identical). The sibling
        calls it makes (``_emit_execution_event`` / ``_persist_execution_request``
        / ``_capture_authoring_step`` / ``_execution_recovery``) route back
        through this kernel, so an instance-level monkeypatch on any of them
        stays authoritative after the Stage-3 move."""
        return self._executions._prepare_executions(
            pending,
            decider_user_id,
            confirmed,
            request_id,
            session_id,
            requester=requester,
            decider=decider,
        )

    def _persist_execution_request(self, request: dict) -> None:
        """Best-effort durable request write (SPEC-037 R-4) — delegates to
        ExecutionDispatcher (behavior byte-identical)."""
        return self._executions._persist_execution_request(request)

    def _capture_authoring_step(self, envelope: dict, parameters: dict) -> None:
        """Best-effort authoring-trace append (SPEC-055 R-2).

        Runs at the same seam as ``_persist_execution_request`` and on the
        same already-signed envelope, so a trace step exists only for a
        *mutating* call a human authorized (per-action, SPEC-054) or
        admitted under a flow authority (SPEC-051) **and** a key signed —
        never for a parked, denied or read-tier call, and never for an
        unsigned one (a missing signing key rejects the batch before this
        seam is reached). The tier gate lives at the two call sites, not
        here: the per-action site reads the parked call's snapshotted
        ``risk_level``, and the flow-unlock site is reachable only through
        ``BROWSER_WRITE_TOOLS``. Both approval kinds append, so a mixed
        session yields one coherent ordered trace; the store assigns the
        position, because only the store sees the whole sequence.

        Same posture as the write beside it: a trace failure degrades
        graduation candidacy — the session simply produces no candidate —
        and never blocks the mutation's execution, its signed request, or
        its receipt. Called *after* ``_persist_execution_request`` so the
        tamper evidence is durable before the derived trace is attempted.

        The arguments are parameterized here, before the write: the store
        persists exactly what it is given, and a trace outlives the receipts
        that would otherwise be the only copy of those arguments, so a
        literal credential must never reach it. Only ``execution_id`` /
        ``confirm_id`` *references* are stored — the signed request, receipt
        and outcome stay in ``execution_records``, so the trace never
        duplicates tamper evidence (ADR-0009).
        """
        session_id = str(envelope.get("session_id") or "")
        if not session_id:
            return
        tool_name = str(envelope.get("tool_name") or "")
        execution_id = str(envelope.get("execution_id") or "")
        try:
            AUTHORING_TRACE_STORE.append_step(
                make_trace_step(
                    session_id=session_id,
                    tool_name=tool_name,
                    # The signed envelope carries an ``args_digest``, never
                    # the raw arguments, so the caller hands them in from the
                    # same in-memory copy the signer digested.
                    args=parameterize_for_trace(tool_name, parameters),
                    # Date the step from the signature, not from the append:
                    # ``requested_at`` is the moment the mutation was
                    # authorized, and it is already in the trace store's
                    # canonical ``%Y-%m-%dT%H:%M:%SZ`` form.
                    captured_at=str(envelope.get("requested_at") or ""),
                    execution_id=execution_id or None,
                    confirm_id=str(envelope.get("confirm_id") or "") or None,
                )
            )
        except Exception as exc:
            LOGGER.warning(
                "authoring trace capture failed for %s: %s",
                execution_id or session_id,
                exc,
            )

    def _sign_flow_execution(
        self, tool_call: object, gateway_tool_name: str
    ) -> dict | None:
        """Auto-sign one unlocked browser write under a flow authority
        (SPEC-051 R-1/R-3) — delegates to ExecutionDispatcher (behavior
        byte-identical). Armed as ``GatewayPermissionMiddleware``'s
        ``flow_signer`` via ``self._sign_flow_execution``; the sibling calls it
        makes (``_execution_recovery`` / ``_persist_execution_request`` /
        ``_capture_authoring_step`` / ``_emit_execution_event``) route back
        through this kernel, so an instance-level monkeypatch on any of them
        stays authoritative after the Stage-3 move."""
        return self._executions._sign_flow_execution(tool_call, gateway_tool_name)

    @staticmethod
    def _observe_flow_binding(frame: dict[str, object], session_id: str) -> None:
        """Record the session's FlowContext from a web.navigate result (SPEC-051 R-1/R-6).

        The tool-gateway binds a flow on ``web.navigate`` and rides it back on
        ``data["flow"]``; this is the single population point for the kernel's
        reflection of that binding (both the live and resumed streams drain
        through ``_drain_trace_queue``). A successful navigate binding a
        different skill/origin overwrites the context — exactly how a rebind is
        detected and the next write re-parks. Non-navigate frames, failures, and
        results without a flow dict are ignored.
        """
        if frame.get("type") != "tool_result":
            return
        if frame.get("tool_name") != "web.navigate":
            return
        if frame.get("status") != "success":
            return
        data = frame.get("data")
        if not isinstance(data, dict):
            return
        flow = data.get("flow")
        if not isinstance(flow, dict):
            return
        FLOW_CONTEXTS.record(session_id, flow)

    @staticmethod
    def _observe_flow_invalidation(
        frame: dict[str, object],
        session_id: str,
        evidence_frames: list[dict[str, object]],
    ) -> None:
        """Drop the session's flow reflection and authority when the binding dies.

        SPEC-054 R-2: ``FLOW_APPROVALS`` auto-signs later browser writes under
        an authority scoped to the gateway's flow binding, so it must never
        outlive that binding. Two shapes end it:

        - a refusal in ``FLOW_KILLING_ERROR_CODES`` — the origin deviated, the
          flow was denied, a redirect was halted, or an envelope claimed a flow
          authority the gateway no longer holds;
        - a failed ``web.navigate`` that **was binding** a flow (it carried a
          ``skill_id``). The gateway nulls ``entry.flow`` on that path only —
          "A pre-existing flow is left intact — the page did not move" — so a
          plain in-flow navigation failure keeps the binding, the kernel's
          reflection stays truthful, and clearing would cost a legitimately
          one-gated flow an extra approval card (ADR-0007).

        Both stores drop together: a context without an authority re-renders the
        next card tool-level, and an authority without a context is what the R-1
        identity guard already refuses to auto-sign, so dropping either alone
        would only leave the two disagreeing.

        This is the kernel-side half of ADR-0010's two-part backstop and is not
        sufficient alone — it depends on the kernel draining the refusal before
        the next write is auto-signed, which is a race. The gateway's own
        ``approval_kind`` refusal is the enforcement boundary; this keeps the
        card honest and avoids spending a denied call to find out.
        """
        if frame.get("type") != "tool_result":
            return
        error = frame.get("error")
        error = error if isinstance(error, dict) else {}
        code = str(error.get("code") or "")
        killed = code in FLOW_KILLING_ERROR_CODES or (
            frame.get("tool_name") == "web.navigate"
            and code == "BROWSER_NAVIGATION_ERROR"
            and AgentKernel._navigate_bound_a_flow(frame, evidence_frames)
        )
        if not killed:
            return
        FLOW_CONTEXTS.clear(session_id)
        FLOW_APPROVALS.clear(session_id)
        LOGGER.info(
            "browser flow authority cleared",
            extra={
                "session_id": session_id,
                "tool_name": str(frame.get("tool_name") or ""),
                "error_code": code,
            },
        )

    @staticmethod
    def _navigate_bound_a_flow(
        frame: dict[str, object],
        evidence_frames: list[dict[str, object]],
    ) -> bool:
        """True when the failed navigate carried a ``skill_id`` (a bind attempt).

        Pairs the result with its ``tool_call`` frame by ``call_id`` — the same
        backward walk ``_extract_browser_element_map`` uses over the turn's
        evidence frames, which the drain loop appends to in emission order. An
        unpaired result (no call frame in this turn) answers ``False``: the
        kernel declines to guess and leaves the refusal to the gateway, which is
        the fail-closed boundary either way.
        """
        call_id = frame.get("call_id")
        if not call_id:
            return False
        for candidate in reversed(evidence_frames):
            if (
                candidate.get("type") == "tool_call"
                and candidate.get("call_id") == call_id
            ):
                parameters = candidate.get("parameters")
                return (
                    isinstance(parameters, dict)
                    and bool(parameters.get("skill_id"))
                )
        return False

    def _drain_trace_queue(
        self,
        trace_queue: asyncio.Queue,
        request_id: str,
        session_id: str,
        evidence_frames: list[dict[str, object]],
        execution_requests: dict[str, dict],
    ) -> list[dict[str, object]]:
        """Decorate queued trace frames and close landed executions — delegates
        to TurnStreamer (byte-identical)."""
        return self._stream._drain_trace_queue(
            trace_queue,
            request_id,
            session_id,
            evidence_frames,
            execution_requests,
        )

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
        if error.get("code") == "OUTCOME_UNKNOWN":
            # SPEC-063 R-3b (T-17): a v3 caller timeout / transport uncertainty
            # is typed uncertainty, never a definitive outcome. The invocation
            # coordinator already stopped the run and appended the attributed
            # ``wait_expired`` / ``transport_uncertain`` observation to the
            # durable ledger, where a late worker result stays appendable
            # without deleting that observation. Writing the legacy synthetic
            # receipt here would falsely close the v2 row as ``timeout`` /
            # ``failed`` and contradict the unknown outcome, so the row is
            # deliberately left unclosed (``requested``) and no completion event
            # is emitted. The admission-disabled ``TIMEOUT`` receipt path below
            # is unchanged, and read-tier calls never reach the coordinator, so
            # legacy and read-tier handling stay separate.
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
        # After the receipt, so the tamper evidence is durable before the
        # derived trace amendment is attempted (same ordering R-2 uses
        # between _persist_execution_request and _capture_authoring_step).
        self._observe_step_origin(request, frame, status)
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

    def _observe_original_step_origin(self, request, original, current_request_id):
        """Consume accepted original evidence synchronously, outside tool frames."""
        self._observe_step_origin(
            request, {}, "succeeded", original=original,
            signing_key=self.settings.execution_signing_key,
            current_request_id=current_request_id,
        )

    @staticmethod
    def _observe_step_origin(
        request: dict, frame: dict[str, object], status: str, *,
        original=None, signing_key=None, current_request_id=None,
    ) -> None:
        """Amend the captured step with the origin it landed on (SPEC-055 R-4).

        R-2 appends a trace step at the *signing* seam, before the call runs,
        so the step cannot carry the origin the interaction landed on. This is
        the only place the kernel can read it: the tool-gateway reports
        ``data["url"]`` on every browser result, and by the time the frame
        reaches the receipt the value is already gone elsewhere —
        ``build_receipt`` digests the outcome into ``outcome_digest`` and never
        stores it, and the execution records are swept at 30 days while a trace
        must outlive them (ADR-0009). The URL is legible for exactly one
        moment; recording it here is what makes it durable.

        Only a ``succeeded`` result is recorded, and ``status`` is the value
        just written into the receipt rather than a second reading of the
        frame, so the trace and the receipt cannot disagree about which
        mutations landed. A failed or timed-out write may still report the URL
        it was attempting — corroborating that as "landed on target" would let
        a mutation that never happened count toward graduation.

        Scoped to ``BROWSER_WRITE_TOOLS`` rather than to "any frame with a
        url". ``flow_origin`` is evidence about the web target a *mutation*
        landed on, and a read-tier result carrying an unrelated link would
        otherwise attach an origin to a step graduation has no reason to
        compare — or, worse, to a step that is not in the trace at all. The
        same set already gates the flow-unlock capture site, so the two ends
        of the amendment cannot disagree about which steps carry origins.

        A step whose origin is never observed stays ``NULL``, which R-4 reads
        as *unverified* rather than as a drift. Three shapes produce that, and
        all fail toward refusing the draft: a result that did not succeed, a
        payload over the evidence frame's size guard (``_make_full_data`` omits
        ``data`` entirely rather than truncating it), and a gateway that
        reported no URL.

        Best-effort on the same terms as the capture beside it: a store
        failure degrades graduation candidacy and never touches the receipt
        already written, the audit event about to be emitted, or the resumed
        stream.
        """
        if request.get("protocol_version") == 3:
            from agent_service.services.execution_protocol import ProtocolError, VerifiedOriginal

            if not isinstance(original, VerifiedOriginal) or not current_request_id:
                return
            try:
                original.revalidate(request, signing_key)
            except ProtocolError:
                return
            if original.observation["request_id"] != current_request_id:
                return
            frame = original.result
            status = "succeeded" if frame.get("status") == "success" else "failed"
        if status != "succeeded":
            return
        if request.get("tool_name") not in BROWSER_WRITE_TOOLS:
            return
        session_id = str(request.get("session_id") or "")
        execution_id = str(request.get("execution_id") or "")
        if not session_id or not execution_id:
            return
        data = frame.get("data")
        if not isinstance(data, dict):
            return
        origin = origin_of_url(data.get("url"))
        if origin is None:
            return
        try:
            AUTHORING_TRACE_STORE.record_step_origin(
                session_id, execution_id, origin
            )
        except Exception:
            LOGGER.warning("authoring trace origin write failed")

    @staticmethod
    def _execution_duration_ms(request: dict) -> int:
        """Whole-milliseconds between request signing and receipt close —
        delegates to ExecutionDispatcher (pure/static; behavior byte-identical)."""
        return ExecutionDispatcher._execution_duration_ms(request)

    def _emit_execution_event(
        self,
        event_type: str,
        outcome: str,
        details: dict,
        request_id: str,
        session_id: str,
        decider_user_id: str,
    ) -> None:
        """Emit one execution audit event through the canonical emitter
        (SPEC-037 R-5) — delegates to ExecutionDispatcher (behavior
        byte-identical). The dispatcher resolves ``emit_audit_event`` through
        *this* module namespace at call time, so the long-standing
        ``monkeypatch.setattr("agent_service.runtime_kernel.emit_audit_event", ...)``
        test surface stays authoritative after the Stage-3 move."""
        return self._executions._emit_execution_event(
            event_type,
            outcome,
            details,
            request_id,
            session_id,
            decider_user_id,
        )

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
    def _confirmation_message(pending_calls: list[dict[str, object]]) -> str:
        """Decomposition Stage 4b: delegates to ConfirmationCoordinator."""
        return ConfirmationCoordinator._confirmation_message(pending_calls)

    @staticmethod
    def _tool_names_have_browser_write(
        tool_names: list[str], gateway_names: dict[str, str]
    ) -> bool:
        """Decomposition Stage 4b: delegates to ConfirmationCoordinator."""
        return ConfirmationCoordinator._tool_names_have_browser_write(
            tool_names, gateway_names
        )

    @staticmethod
    def _batch_has_browser_write(pending: PendingConfirmation) -> bool:
        """Decomposition Stage 4b: delegates to ConfirmationCoordinator."""
        return ConfirmationCoordinator._batch_has_browser_write(pending)

    def _record_flow_approval(
        self,
        pending: PendingConfirmation,
        decider_user_id: str,
        session_id: str,
    ) -> None:
        """Decomposition Stage 4b: delegates to ConfirmationCoordinator."""
        self._confirm._record_flow_approval(pending, decider_user_id, session_id)

    def resume_confirmation(
        self,
        session_id: str,
        pending: PendingConfirmation,
        decision: str,
        user_name: str,
        request_id: str,
        bearer_token: str | None = None,
        model_id: str | None = None,
        owner_user_name: str | None = None,
        routing_allowed: bool = False,
    ) -> AsyncIterator[dict[str, object]]:
        """Decomposition Stage 4b: returns the ConfirmationCoordinator's async
        generator *directly* (no wrapper frame), so an early ``aclose()``
        propagates into the inner ``finally`` that resets the contextvars and
        clears the parked entry."""
        return self._confirm.resume_confirmation(
            session_id,
            pending,
            decision,
            user_name,
            request_id,
            bearer_token,
            model_id,
            owner_user_name,
            routing_allowed,
        )

    def _resume_confirmation(
        self,
        session_id: str,
        pending: PendingConfirmation,
        decision: str,
        user_name: str,
        request_id: str,
        bearer_token: str | None = None,
        model_id: str | None = None,
        owner_user_name: str | None = None,
        routing_allowed: bool = False,
    ) -> AsyncIterator[dict[str, object]]:
        """Decomposition Stage 4b: returns the ConfirmationCoordinator's async
        generator *directly* (no wrapper frame) — ``resume_confirmation`` wraps
        it in ``aclosing``, which must reach the inner ``finally``."""
        return self._confirm._resume_confirmation(
            session_id,
            pending,
            decision,
            user_name,
            request_id,
            bearer_token,
            model_id,
            owner_user_name,
            routing_allowed,
        )

    async def expire_confirmation(
        self,
        session_id: str,
        confirm_id: str,
        model_id: str | None = None,
        routing_allowed: bool = False,
    ) -> None:
        """Decomposition Stage 4b: delegates to ConfirmationCoordinator."""
        await self._confirm.expire_confirmation(
            session_id, confirm_id, model_id=model_id, routing_allowed=routing_allowed
        )
