"""Turn-streaming and reply orchestration for the AgentKernel (Stage 4a).

``TurnStreamer`` owns the kernel's reply / SSE path: the streaming turn
(``stream_events``), the blocking turn (``reply_text``), the event -> frame
normalizer (``normalize_event``), the deterministic fallback stream
(``fallback_stream``) and its two message builders, the authorization-stream
cleanup (``_finish_authorization_stream``), the SPEC-062 R-3 reveal-on-commit
delivery buffers (``_flush_pending_deliveries`` / ``_drain_held_deliveries`` /
``_discard_burned_deliveries``) and the trace-queue drainer
(``_drain_trace_queue``).

``AgentKernel`` keeps a thin delegator for every method here, so the public
surface is unchanged: ``api/v2/routes.py`` and ``services/runtime_service.py`` /
``services/orchestration.py`` still call ``kernel.stream_events`` /
``kernel.reply_text``; tests still call ``kernel.normalize_event`` and
monkeypatch ``kernel._build_agent`` / ``kernel._snapshot_state`` /
``kernel._persist_evidence`` / ``kernel._observe_*`` on the instance.

Three invariants keep the move byte-identical:

* Sibling calls route back through ``self._kernel._X(...)`` (never the
  streamer's own bound method), so an instance-level
  ``monkeypatch.setattr(kernel, "_snapshot_state"/"_persist_evidence"/
  "_observe_*"/"ensure_agent"/...)`` stays authoritative — the same route-back
  discipline Stages 2-3 follow. This is load-bearing here: ``stream_events``
  and the resume path arm and reset ~13 ContextVars around await / yield
  boundaries and fan out to ~20 sibling methods.
* ``MODEL_CATALOG`` (a long-standing ``monkeypatch.setattr(runtime_kernel,
  "MODEL_CATALOG", ...)`` test surface) and the stream-frame primitives defined
  in ``runtime_kernel`` (``TEXT_DELTA_EVENTS`` / ``TERMINAL_STREAM_EVENTS`` /
  ``NO_TOOLS_NOTICE`` / ``MUTATING_TOOLS_UNAVAILABLE_NOTICE`` / ``extract_text``
  / ``extract_stream_text`` / ``flush_prose_frames`` / ``BlockingReply``) are
  resolved through the ``runtime_kernel`` namespace at call time — never a
  module-level import here — both to avoid a circular import (``runtime_kernel``
  imports this module) and so that patch surface still intercepts after the
  move. This is the exact hazard class Stage 2 hit with ``AGENT_STATE_STORE``
  and Stage 3 with ``emit_audit_event``.
* The async-generator protocol is preserved: the kernel's ``stream_events`` /
  ``fallback_stream`` delegators return the streamer's async generator *directly*
  (no wrapper frame), so ``async for`` / ``aclosing`` semantics — and the
  ``finally`` ContextVar resets that depend on ``aclose`` reaching the generator
  that armed them — are byte-identical.

Method bodies are extracted verbatim from ``runtime_kernel.AgentKernel``
(behavior byte-identical); see
``docs/workspace/agent-kernel-decomposition-spike.md``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from agent_service.runtime_settings import RuntimeSettings
from agent_service.services.delegated_identity import (
    DECIDER_IDENTITY,
    REQUESTER_IDENTITY,
)
from agent_service.services.evidence_store import EVIDENCE_FRAME_TYPES
from agent_service.services.flow_approvals import FLOW_APPROVALS
from agent_service.services.kernel_middleware import (
    AuthorizationTurn,
    CURRENT_AUTHORIZATION_TURN,
    authorization_turn,
)
from agent_service.services.prose_redaction import (
    CURRENT_PROSE_REDACTOR,
    StreamingProseRedactor,
    redact_assistant_text,
    redact_structure,
    redact_user_text,
)
from agent_service.services.serialization import make_serializable

LOGGER = logging.getLogger(__name__)


class TurnStreamer:
    """The kernel's turn-streaming / reply collaborator (decomposition Stage 4a).

    Holds only a back-reference to the owning ``AgentKernel``; it owns no
    mutable state. ``settings`` reads live through the kernel so a test that
    swaps the kernel's settings is honored.
    """

    def __init__(self, kernel) -> None:
        self._kernel = kernel

    @property
    def settings(self) -> RuntimeSettings:
        return self._kernel.settings

    def build_unconfigured_message(self, message: str, session_id: str) -> str:
        # The operator's own text is interpolated into a kernel-authored
        # string, so it carries a typed credential exactly as the prompt did.
        # This is user-authored text inside a display projection, which is the
        # scope ``prose_redaction`` allows its heuristic to run in.
        return (
            "Platform baseline placeholder response. "
            f"AgentScope runtime not configured for session {session_id}. "
            f"Received '{redact_user_text(message)}'."
        )

    def build_provider_error_message(
        self,
        message: str,
        session_id: str,
        model_id: str | None = None,
    ) -> str:
        # ``MODEL_CATALOG`` resolves through ``runtime_kernel`` at call time
        # (module docstring): avoids the circular import and keeps the
        # ``monkeypatch.setattr(runtime_kernel, "MODEL_CATALOG", ...)`` test
        # surface authoritative after the move.
        from agent_service.runtime_kernel import MODEL_CATALOG

        detail = self._kernel._last_error or "Unknown provider error."
        # Name the provider that actually served (attempted) the turn:
        # a resolved catalog entry carries its own provider, so a
        # dashscope model failure never blames the deepseek profile.
        entry = MODEL_CATALOG.get(model_id) if model_id else None
        if entry is not None:
            attribution = f"{entry.provider} (model {entry.id})"
        elif model_id:
            attribution = f"{self._kernel.provider_name()} (model {model_id})"
        else:
            attribution = self._kernel.provider_name()
        return (
            "Platform runtime fallback response. "
            f"AgentScope provider {attribution} failed for session {session_id}. "
            f"Received '{redact_user_text(message)}'. Last error: {detail}"
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
        routing_allowed: bool = False,
    ) -> BlockingReply:
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
        from agent_service.runtime_kernel import BlockingReply, extract_text
        from agent_service.services.agent_role import AgentRole, current_agent_role

        # Executor staging must consume the ASK event through the same handler
        # as SSE. SDK reply() discards it and returns only the last message.
        # Read-only and unscoped blocking turns retain their existing behavior.
        if not read_only and current_agent_role() == AgentRole.EXECUTOR:
            from contextlib import aclosing
            from agent_service.schemas.v2 import AuthorizationRequired

            text: list[str] = []
            confirmation = None
            challenge = None
            effective_model = None
            async with aclosing(self._kernel.stream_events(
                message=message, request_id="staging", session_id=session_id,
                user_name=user_name, bearer_token=bearer_token,
                model_id=model_id, routing_allowed=routing_allowed,
            )) as stream:
                async for frame in stream:
                    if frame.get("delta"):
                        text.append(str(frame["delta"]))
                    if frame.get("type") == "confirmation_request":
                        confirmation = frame
                        text.append(str(frame.get("message") or "Awaiting human approval."))
                    if frame.get("type") == "authorization_required":
                        challenge = AuthorizationRequired(
                            challenge_id=frame["auth_challenge_id"], target=frame["target"],
                            expires_at=frame.get("expires_at"),
                        )
                    if frame.get("model"):
                        effective_model = str(frame["model"])
            return BlockingReply("".join(text), authorization_required=challenge,
                                 effective_model=effective_model,
                                 confirmation_request=confirmation)

        if not self._kernel.is_configured():
            return BlockingReply(self._kernel.build_unconfigured_message(message, session_id))

        from agent_service.tools.gateway_tools import (
            CHAT_SESSION_ID,
            DELEGATED_TOKEN,
        )

        serving_model: str | None = None
        prose: StreamingProseRedactor | None = None
        try:
            requester = await asyncio.to_thread(self._kernel._requester_for_turn, session_id, user_name, bearer_token)
            agent, user_msg_cls, serving_model = await self._kernel.ensure_agent(
                session_id, bearer_token, model_id, read_only, routing_allowed
            )
            # Prose redaction for a blocking turn: no streaming, so the reply
            # is masked whole and no hold-back is needed.
            prose = self._kernel._prose_redactor(agent, message, session_id)
            # Expose the turn's delegated token to the cached tool closures
            # (SPEC-018 R-2). No evidence sink is set: blocking turns emit
            # no trace frames.
            prose_var = CURRENT_PROSE_REDACTOR.set(prose)
            token_var = DELEGATED_TOKEN.set(bearer_token)
            requester_var = REQUESTER_IDENTITY.set(requester)
            decider_var = DECIDER_IDENTITY.set(requester)
            session_var = CHAT_SESSION_ID.set(session_id)
            from agent_service.services.kernel_middleware import TOOL_EVIDENCE_SINK

            turn_index = self._kernel._count_user_turns(agent)
            trace_queue = asyncio.Queue() if self.settings.target_authorization_enabled else None
            sink_var = TOOL_EVIDENCE_SINK.set(trace_queue)
            try:
                with authorization_turn(self.settings.target_authorization_enabled) as auth_turn:
                    reply_msg = await agent.reply(
                        user_msg_cls(name=user_name, content=message),
                        structured_schema=response_schema,
                    )
            finally:
                TOOL_EVIDENCE_SINK.reset(sink_var)
                CURRENT_PROSE_REDACTOR.reset(prose_var)
                DELEGATED_TOKEN.reset(token_var)
                REQUESTER_IDENTITY.reset(requester_var)
                DECIDER_IDENTITY.reset(decider_var)
                CHAT_SESSION_ID.reset(session_var)
            self._kernel.clear_error()
            structured = getattr(reply_msg, "structured_output", None)
            if not isinstance(structured, dict):
                structured = None
            self._kernel._snapshot_state(session_id, agent, prose.literals)
            if trace_queue is not None:
                evidence_frames = []
                self._kernel._drain_trace_queue(trace_queue, "blocking", session_id, evidence_frames, {})
                self._kernel._persist_evidence(session_id, "blocking", turn_index, evidence_frames)
            # SPEC-071 R-2: attribute the turn to the model that actually served
            # it — the routed candidate when the router fired, else None so the
            # caller keeps its resolved tier and reports ``model_selected_by``.
            routed_model = self._kernel._effective_model_id(agent)
            if routed_model:
                LOGGER.info(
                    "model routing served turn",
                    extra={
                        "session_id": session_id,
                        "routed_model": routed_model,
                        "resolved_model": serving_model,
                        "model_selected_by": "router",
                    },
                )
            return BlockingReply(
                redact_assistant_text(
                    extract_text(getattr(reply_msg, "content", reply_msg)),
                    prose.literals,
                ),
                redact_structure(structured, prose.literals),
                auth_turn.challenge if auth_turn is not None else None,
                routed_model,
            )
        except Exception as exc:  # pragma: no cover - defensive fallback
            self._kernel.remember_error(exc, prose.literals if prose is not None else ())
            LOGGER.error("AgentScope reply failed; falling back to runtime error response: %s", self._kernel._last_error)
            return BlockingReply(
                self._kernel.build_provider_error_message(
                    message, session_id, serving_model or model_id
                ),
            )

    def normalize_event(
        self,
        event: object,
        request_id: str,
        session_id: str,
        redactor: StreamingProseRedactor | None = None,
    ) -> dict[str, object]:
        """One AgentScope event as a normalized stream frame.

        ``redactor`` carries the turn's harvested credential literals and the
        held-back tail of a stream in progress (SPEC-049 R-5 applied to chat
        prose). Callers that pass one own flushing it: a delta boundary can
        fall inside a credential, so the redactor withholds a tail that the
        caller must emit at every stream exit.
        """
        from agent_service.runtime_kernel import (
            TEXT_DELTA_EVENTS,
            extract_stream_text,
        )

        payload = make_serializable(event)
        event_type = "agentscope_event"
        if isinstance(payload, dict) and "type" in payload:
            event_type = str(payload["type"]).lower()
        else:
            raw_type = getattr(event, "type", None)
            if raw_type is not None:
                event_type = str(getattr(raw_type, "name", raw_type)).lower()

        if self.settings.target_authorization_enabled:
            # An SDK model message can end before its tools execute. Only the
            # reply end closes an authorization-enabled turn on the wire.
            if event_type == "message_end":
                event_type = "model_message_end"
            elif event_type == "reply_end":
                event_type = "message_end"

        data: dict[str, object] = {
            "event": event_type,
            "request_id": request_id,
            "session_id": session_id,
            "payload": payload,
        }

        text = extract_stream_text(payload)
        if event_type in TEXT_DELTA_EVENTS and text:
            if redactor is None:
                data["delta"] = text
            else:
                masked = redactor.feed(text)
                # An empty result means the whole chunk was held back. Omit
                # the key rather than send "": that is the shape this already
                # produces for a text-block start with no text, and the
                # portal's decoder gates on a truthy delta either way.
                if masked:
                    data["delta"] = masked
                # The payload is the same text again in raw event form. It
                # reaches no wire today — the v2 contract strips it as an
                # AgentScope internal and the v1 stream helper has no caller
                # — so this is a chunk-local mask of a duplicate, not the
                # guarantee: the hold-back lives in ``delta`` above.
                data["payload"] = {"type": event_type, "delta": masked}
        elif redactor is not None:
            data["payload"] = redact_structure(payload, redactor.literals)
        return data

    async def stream_events(
        self,
        message: str,
        request_id: str,
        session_id: str,
        user_name: str,
        bearer_token: str | None = None,
        model_id: str | None = None,
        routing_allowed: bool = False,
    ) -> AsyncIterator[dict[str, object]]:
        # Stream-frame primitives + the model catalog resolve through
        # ``runtime_kernel`` at call time (module docstring): avoids the
        # circular import (runtime_kernel imports this module) and keeps the
        # ``monkeypatch.setattr(runtime_kernel, "MODEL_CATALOG", ...)`` surface
        # authoritative after the move.
        from agent_service.runtime_kernel import (
            MODEL_CATALOG,
            MUTATING_TOOLS_UNAVAILABLE_NOTICE,
            NO_TOOLS_NOTICE,
            TERMINAL_STREAM_EVENTS,
            flush_prose_frames,
        )

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

        if not self._kernel.is_configured():
            async for event in self._kernel.fallback_stream(
                request_id=request_id,
                session_id=session_id,
                delta=self._kernel.build_unconfigured_message(message, session_id),
            ):
                yield event
            return

        from agent_service.services.kernel_middleware import (
            PENDING_RELEASE_DELIVERIES,
            RELEASE_PERMITS,
            STREAM_PENDING_DELIVERIES,
            TOOL_EVIDENCE_SINK,
        )
        from agent_service.services.execution_run_guard import CURRENT_RUN_GUARD
        from agent_service.tools.gateway_tools import (
            CHAT_SESSION_ID,
            DELEGATED_TOKEN,
            EXECUTION_AUDIT_CONTEXT,
            EXECUTION_REQUESTS,
        )

        bound_model_id: str | None = None
        prose: StreamingProseRedactor | None = None
        try:
            requester = await asyncio.to_thread(self._kernel._requester_for_turn, session_id, user_name, bearer_token)
            # Ensure the agent (with the token-cached toolkit) exists.
            agent, user_msg_cls, bound_model_id = await self._kernel.ensure_agent(
                session_id, bearer_token, model_id, False, routing_allowed
            )

            # SPEC-025 R-1: the replay turn ordinal for this stream's
            # evidence, captured before the turn mutates the context.
            turn_index = self._kernel._count_user_turns(agent)
            evidence_frames: list[dict[str, object]] = []
            # SPEC-049 R-5 applied to chat prose: harvest what the operator
            # typed so the model's own reply cannot restate it. Built from the
            # raw message rather than effective_message — the notices injected
            # below are kernel text and carry no credential.
            prose = self._kernel._prose_redactor(agent, message, session_id)

            # Deterministic anti-hallucination guard: with a gateway
            # configured but zero gateway tools registered the model has no
            # real data to ground in, so inject an explicit notice for this
            # turn instead of relying on the standing system prompt. Task
            # tools never count: they provide no live data (SPEC-018 R-5).
            effective_message = message
            if (
                self.settings.tool_gateway_url
                and self._kernel._count_gateway_tools(agent.toolkit) == 0
            ):
                LOGGER.warning(
                    "tool gateway configured but no tools registered; "
                    "injecting no-tools notice to prevent fabrication"
                )
                effective_message = f"{NO_TOOLS_NOTICE}\n\n{message}"
            elif self._kernel._mutating_tools_excluded:
                effective_message = (
                    f"{MUTATING_TOOLS_UNAVAILABLE_NOTICE}\n\n{message}"
                )

            # SPEC-018 R-2: a request-scoped evidence sink consumed by
            # ToolEvidenceMiddleware replaces the per-request toolkit
            # rebuild; the delegated token is exposed the same way for the
            # cached tool closures.
            trace_queue: asyncio.Queue = asyncio.Queue()
            # SPEC-051 R-1: arm the same execution plumbing the resume path uses
            # so a browser write unlocked by a flow authority recorded in an
            # EARLIER turn can auto-sign, execute, and receipt here. Both are
            # inert for turns without a live flow authority: the empty requests
            # map is never consulted (mutating tools still park) and the audit
            # context stays None, so the common hot path is behavior-preserving.
            execution_requests: dict[str, dict] = {}
            flow_approval = FLOW_APPROVALS.get(session_id)
            # SPEC-063 R-4: resolve this root turn's durable run identity and
            # bind the shared in-process guard BEFORE the reply stream runs, so
            # the permission middleware's stop check and the mutation lane see
            # it. Inert when admission is disabled (recovery is None): no run is
            # minted, no guard is bound, and the legacy path is unchanged.
            recovery = self._kernel._execution_recovery()
            run_id = (
                self._kernel._resolve_run_id(
                    recovery, session_id, user_name, flow_approval
                )
                if recovery is not None
                else None
            )
            flow_audit_context = (
                {
                    "settings": self.settings,
                    "confirm_id": flow_approval.confirm_id,
                    "session_id": session_id,
                    "request_id": request_id,
                    "decider_user_id": flow_approval.decider_user_id,
                    "observe_original": self._kernel._observe_original_step_origin,
                }
                if flow_approval is not None
                else None
            )
            auth_turn = AuthorizationTurn() if self.settings.target_authorization_enabled else None
            auth_var = CURRENT_AUTHORIZATION_TURN.set(auth_turn)
            sink_var = TOOL_EVIDENCE_SINK.set(trace_queue)
            # SPEC-062 R-3 reveal-on-commit: arm the per-stream delivery buffers.
            # A fresh turn generates into STREAM_PENDING (flushed at a normal end
            # or drained onto a parked card); PENDING_RELEASE stays empty here —
            # only an approved resume carries held deliveries into it, so the
            # middleware's release branch can never fire on a non-resumed turn.
            pending_deliveries_var = STREAM_PENDING_DELIVERIES.set([])
            release_deliveries_var = PENDING_RELEASE_DELIVERIES.set([])
            # SPEC-063 R-4: arm the per-stream secret-release permit map the v3
            # invocation coordinator writes into and ToolEvidenceMiddleware
            # consumes before revealing a held portal_copy delivery. Unused and
            # never consulted when admission is disabled (no guard is bound).
            permits_var = RELEASE_PERMITS.set({})
            prose_var = CURRENT_PROSE_REDACTOR.set(prose)
            token_var = DELEGATED_TOKEN.set(bearer_token)
            requester_var = REQUESTER_IDENTITY.set(requester)
            decider_var = DECIDER_IDENTITY.set(requester)
            session_var = CHAT_SESSION_ID.set(session_id)
            requests_var = EXECUTION_REQUESTS.set(execution_requests)
            audit_var = EXECUTION_AUDIT_CONTEXT.set(flow_audit_context)
            guard_var = (
                CURRENT_RUN_GUARD.set(
                    self._kernel._bind_guard(recovery, run_id, session_id, user_name)
                )
                if recovery is not None and run_id is not None
                else None
            )
            reply_stream = agent.reply_stream(
                user_msg_cls(name=user_name, content=effective_message)
            )
            try:
                async for event in reply_stream:
                    self._kernel.clear_error()
                    # Drain any accumulated trace events before yielding text.
                    drained = list(
                        self._kernel._drain_trace_queue(
                            trace_queue,
                            request_id,
                            session_id,
                            evidence_frames,
                            execution_requests,
                        )
                    )
                    if drained:
                        # SPEC-035 R-2: the portal opens a new paragraph on the
                        # first delta following a tool frame. A tail the
                        # redactor is still holding belongs to the segment
                        # *before* that tool call, so release it first — left
                        # held, it rides out in the same delta as the new
                        # segment's opening text, the portal prepends "\n\n" to
                        # the whole frame, and the paragraph break lands one
                        # hold-length early, mid-word.
                        for flushed in flush_prose_frames(
                            prose, request_id, session_id
                        ):
                            yield flushed
                    for decorated in drained:
                        yield decorated
                    # SPEC-020 R-2: a kernel ASK park surfaces as a
                    # confirmation_request frame and ends the stream without
                    # message_end; the confirm endpoint resumes it.
                    frame = self._kernel._build_confirmation_frame(
                        event,
                        session_id,
                        user_name,
                        agent.toolkit,
                        turn_index=turn_index,
                        evidence_frames=evidence_frames,
                        run_id=run_id,
                    )
                    if frame is not None:
                        # A parked stream ends without message_end, so this is
                        # its only chance to release the held-back tail.
                        for flushed in flush_prose_frames(
                            prose, request_id, session_id
                        ):
                            yield flushed
                        yield {
                            **frame,
                            "request_id": request_id,
                            "session_id": session_id,
                        }
                        break
                    frame = self._kernel.normalize_event(
                        event, request_id, session_id, redactor=prose
                    )
                    if frame.get("event") in TERMINAL_STREAM_EVENTS:
                        # Release the tail before the terminal frame: the
                        # portal settles the turn here and never rewrites
                        # replyText afterwards.
                        for flushed in flush_prose_frames(
                            prose, request_id, session_id
                        ):
                            yield flushed
                    if frame.get("event") == "message_end":
                        # SPEC-024 R-3 / SPEC-071 R-2: attribute the turn to the
                        # model that actually served it — the routed candidate
                        # when the per-turn router fired, else the resolved model
                        # (or session default). Rides the existing ``model``
                        # field; no agent-stream-event schema change.
                        routed_model = self._kernel._effective_model_id(agent)
                        if routed_model:
                            LOGGER.info(
                                "model routing served turn",
                                extra={
                                    "request_id": request_id,
                                    "session_id": session_id,
                                    "routed_model": routed_model,
                                    "resolved_model": bound_model_id,
                                    "model_selected_by": "router",
                                },
                            )
                        frame["model"] = routed_model or bound_model_id
                    yield frame

                # Release the tail before the closing trace frames, for the
                # same paragraph reason as in the loop, and as a safety net for
                # a provider that closes without message_end. flush is
                # idempotent, so the paths above add nothing here.
                for flushed in flush_prose_frames(
                    prose, request_id, session_id
                ):
                    yield flushed
                # SPEC-062 R-3 reveal-on-commit: a normal (unparked) end flushes
                # any portal_copy deliveries generated this turn as secret_delivery
                # frames — the standalone generate-and-copy path, where no gate
                # follows so the Copy button appears at turn end. A turn that
                # parked already drained these onto its card (and broke out above),
                # so the buffer is empty and this is a no-op there.
                self._kernel._flush_pending_deliveries(trace_queue)
                # Drain any remaining trace events after the stream completes.
                for decorated in self._kernel._drain_trace_queue(
                    trace_queue,
                    request_id,
                    session_id,
                    evidence_frames,
                    execution_requests,
                ):
                    yield decorated
            finally:
                if auth_turn is not None:
                    await self._kernel._finish_authorization_stream(auth_turn, reply_stream)
                    self._kernel._drain_trace_queue(trace_queue, request_id, session_id, evidence_frames, execution_requests)
                    self._kernel._persist_evidence(session_id, request_id, turn_index, evidence_frames)
                    self._kernel._snapshot_state(session_id, agent, prose.literals)
                CURRENT_PROSE_REDACTOR.reset(prose_var)
                DELEGATED_TOKEN.reset(token_var)
                REQUESTER_IDENTITY.reset(requester_var)
                DECIDER_IDENTITY.reset(decider_var)
                CHAT_SESSION_ID.reset(session_var)
                EXECUTION_REQUESTS.reset(requests_var)
                EXECUTION_AUDIT_CONTEXT.reset(audit_var)
                if guard_var is not None:
                    CURRENT_RUN_GUARD.reset(guard_var)
                STREAM_PENDING_DELIVERIES.reset(pending_deliveries_var)
                PENDING_RELEASE_DELIVERIES.reset(release_deliveries_var)
                RELEASE_PERMITS.reset(permits_var)
                TOOL_EVIDENCE_SINK.reset(sink_var)
                if auth_turn is not None:
                    auth_turn.close()
                CURRENT_AUTHORIZATION_TURN.reset(auth_var)

            # Persist the turn's evidence frames best-effort (SPEC-025 R-1)
            # alongside the conversation snapshot; also covers the park
            # path, which breaks out of the loop above.
            if auth_turn is None:
                self._kernel._persist_evidence(
                    session_id, request_id, turn_index, evidence_frames
                )

            # Persist conversation state after the completed turn so it
            # survives restarts (SPEC-017 R-3). Fail-open by design.
                self._kernel._snapshot_state(session_id, agent, prose.literals)
        except Exception as exc:  # pragma: no cover - defensive fallback
            self._kernel.remember_error(exc, prose.literals if prose is not None else ())
            LOGGER.error("AgentScope streaming failed; falling back to runtime error response: %s", self._kernel._last_error)
            async for event in self._kernel.fallback_stream(
                request_id=request_id,
                session_id=session_id,
                delta=self._kernel.build_provider_error_message(
                    message, session_id, bound_model_id or model_id
                ),
            ):
                yield event

    @staticmethod
    async def _finish_authorization_stream(turn: AuthorizationTurn, stream) -> None:
        """Finish a latched SDK reply in its owning task even after disconnect.

        No provider or tool may run after the latch. Draining that bounded tail
        lets the SDK persist final tool blocks and unwind its nested generators;
        closing only the outer iterator leaves ContextVar resets to another task.
        """
        turn.close()
        if not turn.stopped or stream is None:
            return
        try:
            async with asyncio.timeout(5):
                async for _ in stream:
                    pass
        except (Exception, asyncio.CancelledError):
            LOGGER.warning("authorization-stopped reply cleanup incomplete")

    def _flush_pending_deliveries(self, trace_queue: asyncio.Queue) -> None:
        """Emit this stream's buffered portal_copy deliveries as frames.

        SPEC-062 R-3 reveal-on-commit: the standalone generate-and-copy path.
        Drains ``STREAM_PENDING_DELIVERIES`` onto the trace queue so the frames
        are decorated, persisted as evidence, and yielded like any other frame.
        A turn that parked already drained the buffer onto its card, so this is a
        no-op there. ``PENDING_RELEASE_DELIVERIES`` is deliberately NOT flushed:
        a held delivery releases only on a gated commit, so an ungated turn end
        burns it silently (the deny/failure posture).
        """
        from agent_service.services.kernel_middleware import (
            STREAM_PENDING_DELIVERIES,
        )

        pending = STREAM_PENDING_DELIVERIES.get()
        if not pending:
            return
        for delivery in list(pending):
            trace_queue.put_nowait({"type": "secret_delivery", **delivery})
        pending.clear()

    async def _discard_burned_deliveries(
        self, deliveries: list[dict], owner_token: str | None
    ) -> None:
        """Actively discard held portal_copy deliveries that burned (SPEC-062 R-3).

        The deny/failure counterpart to ``_flush_pending_deliveries``: rather than
        reveal a held delivery, destroy it at the gateway so the handle is not
        redeemable — even by a direct owner-scoped fetch — during the hold TTL.
        Best-effort and never fatal: a missing gateway/token or a transport
        failure degrades to the expiry burn. Only the opaque ``delivery_id`` rides
        the call, never the plaintext, and ``owner_token`` is the requester's, so
        the gateway discard is owner-scoped exactly like a redemption.
        """
        delivery_ids = [
            delivery_id
            for delivery_id in (
                delivery.get("delivery_id")
                for delivery in deliveries
                if isinstance(delivery, dict)
            )
            if delivery_id
        ]
        if not delivery_ids:
            return
        from agent_service.tools.gateway_tools import discard_deliveries

        await discard_deliveries(
            self.settings.tool_gateway_url, delivery_ids, owner_token
        )

    def _drain_held_deliveries(self) -> tuple[dict, ...]:
        """Drain both per-stream delivery buffers into a tuple for a parked card.

        SPEC-062 R-3 reveal-on-commit: called from ``_build_confirmation_frame``
        so the held portal_copy handles ride the park across resume. Combines the
        deliveries generated in this stream (``STREAM_PENDING_DELIVERIES``) with
        any carried in from a prior park and not yet released
        (``PENDING_RELEASE_DELIVERIES`` — non-empty only on a re-park that happens
        before a gated commit). Clears both so a later normal-end flush cannot
        double-emit them. Only the opaque handles ride along, never the plaintext.
        """
        from agent_service.services.kernel_middleware import (
            PENDING_RELEASE_DELIVERIES,
            STREAM_PENDING_DELIVERIES,
        )

        held: list[dict] = []
        for buffer in (
            STREAM_PENDING_DELIVERIES.get(),
            PENDING_RELEASE_DELIVERIES.get(),
        ):
            if buffer:
                held.extend(buffer)
                buffer.clear()
        return tuple(held)

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
            # SPEC-051 R-1/R-6: keep the session FlowContext current before any
            # later write in this turn parks (card headline) or auto-signs
            # (identity guard). Single population point for both streams.
            self._kernel._observe_flow_binding(decorated, session_id)
            # SPEC-054 R-2: and the single invalidation point, so a flow-killing
            # refusal drops the reflection and the auto-signing authority
            # together before any later write in this turn can ride them.
            self._kernel._observe_flow_invalidation(
                decorated, session_id, evidence_frames
            )
            self._kernel._observe_tool_result(decorated, execution_requests)
            frames.append(decorated)
        return frames
