"""ConfirmationCoordinator — the HITL park / resume / expire collaborator.

Decomposition Stage 4b: the confirmation cluster (SPEC-020/030/031/051/054/055/
062/063) moves out of ``AgentKernel`` wholesale. ``AgentKernel`` keeps thin
delegators, so every caller (``api/v2/routes`` confirm + expiry sweeper) and
every test that patches ``kernel.resume_confirmation`` /
``kernel.expire_confirmation`` / ``kernel._resume_identities`` on the instance
stays byte-identical.

Three invariants hold the move byte-identical:

1. Route-back-through-kernel. Every sibling call — including to this
   coordinator's own moved methods — goes through ``self._kernel._X(...)``, so
   an instance-level ``monkeypatch.setattr(kernel, "_X", ...)`` stays
   authoritative. Shared helpers that stay on the kernel (``ensure_agent``,
   ``_prose_redactor``, ``_count_user_turns``, ``_resume_identities``,
   ``_prepare_executions``, ``_execution_recovery``, ``_bind_guard``,
   ``_persist_evidence``, ``_snapshot_state``, ``_drain_trace_queue``,
   ``normalize_event``, ``fallback_stream``, ``_drain_held_deliveries``,
   ``_discard_burned_deliveries``, ``_flush_pending_deliveries``,
   ``_finish_authorization_stream``, ``_toolkit_risk_map``,
   ``_toolkit_gateway_name_map``, ``_observe_original_step_origin``,
   ``clear_error`` / ``remember_error`` / ``_last_error``) are reached the same
   way.

2. Lazy-resolve the ``runtime_kernel``-defined stream primitives.
   ``TERMINAL_STREAM_EVENTS`` and ``flush_prose_frames`` are defined in
   ``runtime_kernel`` (which imports this module), so they are imported inside
   ``_resume_confirmation`` at call time — never module-level — to avoid the
   circular import and keep behavior identical.

3. Async-generator delegators return the inner generator directly.
   ``resume_confirmation`` / ``_resume_confirmation`` are async generators whose
   ``finally`` resets ~15 contextvars and clears the parked entry; the kernel
   delegators are plain ``def`` returning this coordinator's generator (no
   wrapper frame), so an early ``aclose()`` propagates inward and the ``finally``
   always runs.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from agent_service.runtime_settings import RuntimeSettings
from agent_service.services.agent_role import current_agent_role_value
from agent_service.services.confirmation_records import (
    CONFIRMATION_RECORD_STORE,
    make_record as make_confirmation_record,
)
from agent_service.services.delegated_identity import (
    DECIDER_IDENTITY,
    REQUESTER_IDENTITY,
)
from agent_service.services.execution_signing import REASON_REQUEST_MISSING
from agent_service.services.flow_approvals import (
    BROWSER_WRITE_TOOLS,
    FLOW_APPROVALS,
    FLOW_CONTEXTS,
)
from agent_service.services.hitl_confirmations import (
    CONFIRMATION_REGISTRY,
    PendingConfirmation,
    curated_effect_sentence,
    redact_pending_calls,
)
from agent_service.services.kernel_middleware import (
    AuthorizationTurn,
    CURRENT_AUTHORIZATION_TURN,
)
from agent_service.services.prose_redaction import (
    CURRENT_PROSE_REDACTOR,
    redact_assistant_text,
    redact_structure,
)

LOGGER = logging.getLogger(__name__)


class ConfirmationCoordinator:
    """The HITL park / resume / expire path, assembled by ``AgentKernel``.

    Owns no mutable state: the parked entries live in ``CONFIRMATION_REGISTRY``
    and the durable cards in ``CONFIRMATION_RECORD_STORE``; the per-turn
    contextvars travel with ``_resume_confirmation`` and are reset in its
    ``finally``. ``settings`` is read live off the kernel.
    """

    def __init__(self, kernel) -> None:
        self._kernel = kernel

    @property
    def settings(self) -> RuntimeSettings:
        return self._kernel.settings

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
        browser_element_map = self._kernel._extract_browser_element_map(
            evidence_frames or []
        )
        # SPEC-051 R-6: render the card from the maintained session FlowContext
        # (populated by _drain_trace_queue from web.navigate), not a park-time
        # frame walk — authoritative and correct across turns and frame order.
        # Empty when no flow is bound, so the card falls back to tool-level.
        #
        # The headline must describe *this parked batch*: attach the bound
        # flow's summary only when the batch actually carries a browser write —
        # the same predicate (_tool_names_have_browser_write) that arms
        # flow-unlock in _record_flow_approval, so framing and authority can
        # never disagree. A non-browser batch (k8s.*, etc.) parked while a
        # browser flow lingers in the session falls back to action-level
        # rendering instead of inheriting the stale flow headline (the
        # reset-password headline leaking onto a k8s.delete_pod card).
        tool_calls = list(getattr(event, "tool_calls", None) or [])
        gateway_names = self._kernel._toolkit_gateway_name_map(toolkit)
        flow_context = FLOW_CONTEXTS.get(session_id)
        browser_flow = (
            flow_context.summary()
            if flow_context is not None
            and self._kernel._tool_names_have_browser_write(
                [str(getattr(tc, "name", "") or "") for tc in tool_calls],
                gateway_names,
            )
            else {}
        )
        # SPEC-054 R-1: the card's declared kind comes from the SAME branch as
        # the flow headline, so ``approval_kind`` and ``flow_summary`` can never
        # disagree — ``"flow"`` exactly when a browser-write batch has a bound
        # flow (``browser_flow`` non-empty), ``"action"`` otherwise. This
        # subsumes the v0.34.1 headline-leak patch: a non-browser batch parked
        # while a flow lingers is ``"action"`` and carries no headline, so the
        # leak class is structurally impossible rather than merely gated.
        approval_kind = "flow" if browser_flow else "action"
        pending = CONFIRMATION_REGISTRY.register(
            session_id=session_id,
            user_id=user_name,
            reply_id=str(getattr(event, "reply_id", "") or ""),
            tool_calls=tool_calls,
            timeout=self.settings.hitl_confirm_timeout,
            risk_levels=self._kernel._toolkit_risk_map(toolkit),
            gateway_names=gateway_names,
            browser_element_map=browser_element_map,
            browser_flow=browser_flow,
            approval_kind=approval_kind,
            run_id=run_id,
        )
        # SPEC-054 R-3/R-4: assemble the parked payload and the card message
        # ONCE here, so the live frame below and the durable record are fed
        # from a single value and the two paths can never diverge.
        from agent_service.tools.gateway_tools import generation_bearer_token

        pending.requester_delegated_token = generation_bearer_token()
        pending.requester_identity = REQUESTER_IDENTITY.get()
        # SPEC-073 R-4 / SPEC-076 R-4: label which agent-role staged this parked
        # mutation, from the process-local AGENT_ROLE contextvar. Kernel-internal
        # provenance only (ephemeral like the requester token above — never
        # persisted to the durable record below, never a contract/wire field).
        # Live on the SPEC-076 executor staging path (staged_by_role="executor");
        # ``None`` on the unscoped single-agent path, so that park is byte-identical.
        pending.staged_by_role = current_agent_role_value()
        pending.email_recipient_allowlist = self.settings.email_recipient_allowlist
        # SPEC-062 R-3 reveal-on-commit: attach this stream's held portal_copy
        # deliveries so they ride the park across resume and are released only
        # when the approved gated mutation commits. Ephemeral (like the requester
        # token above): never persisted to the durable record below, so a
        # mid-approval restart drops it and the delivery expires unreleased.
        pending.pending_deliveries = self._kernel._drain_held_deliveries()
        pending_calls = pending.pending_calls_payload()
        message = self._kernel._confirmation_message(pending_calls)
        # SPEC-055 R-7: redact secret-bearing raw parameter values on the
        # single payload that feeds BOTH the durable record below and the
        # live frame, so an action card never persists or streams a plaintext
        # secret alongside its masked change_request. Runs AFTER the message
        # (which reads raw parameters via curated_effect_sentence) and never
        # touches the fresh payload build_requests re-reads at resume, so the
        # signed args_digest stays byte-identical. flow/legacy cards are left
        # as-is (the helper gates on the action kind).
        redact_pending_calls(pending, pending_calls)
        redactor = CURRENT_PROSE_REDACTOR.get()
        flow_summary = pending.flow_summary()
        if redactor is not None:
            pending_calls = redact_structure(pending_calls, redactor.literals)
            message = redact_assistant_text(message, redactor.literals)
            flow_summary = redact_structure(flow_summary, redactor.literals)
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
                    pending_calls=pending_calls,
                    action=pending.highest_action(),
                    # SPEC-033 R-1: anchor the durable card under the
                    # parking turn (same ordinal convention as evidence).
                    turn_index=turn_index,
                    # SPEC-051 R-6: persist the flow headline so the inbox
                    # and session detail replay the same workflow framing.
                    flow_summary=flow_summary,
                    # SPEC-054 R-1/R-4: persist the declared kind and the
                    # card message from the same values the live frame below
                    # carries, so a replayed card states its own kind and
                    # shows the message the operator saw.
                    approval_kind=approval_kind,
                    message=message,
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
        frame: dict[str, object] = {
            "type": "confirmation_request",
            "confirm_id": pending.confirm_id,
            "pending_calls": pending_calls,
            "message": message,
            # SPEC-054 R-1: the declared kind rides the live frame so the
            # operator card renders the flow headline (``flow``) or the
            # change-request layout (``action``) from a stated kind rather
            # than inferred ambient session state.
            "approval_kind": approval_kind,
        }
        # SPEC-051 R-6: card-level flow headline rendered above the per-call
        # tool detail; absent when no flow is bound (tool-level fallback).
        # SPEC-054 R-1: emitted from the same branch as approval_kind, so it
        # is present iff approval_kind == "flow".
        if flow_summary is not None:
            frame["flow_summary"] = flow_summary
        return frame

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

    @staticmethod
    def _confirmation_message(pending_calls: list[dict[str, object]]) -> str:
        """The card's informative top-line message (SPEC-054 R-3/R-4).

        Sources from the curated change-request effect sentence where the
        parked batch has one, so the card explains *what changes*; otherwise
        falls back to the deterministic generic constant. The gateway
        middleware's ASK reason is deliberately **not** wired through verbatim:
        it interpolates the *sanitized* tool name (``web_click``), breaking the
        dotted-canonical convention, and explains an implementation detail
        ("outside the auto-approve allow-list") rather than the change (R-3).
        Computed once at park time and fed to both the live frame and the
        durable record from that single value, so the two cannot diverge (R-4).
        """
        for call in pending_calls:
            if call.get("tool_name") == "secrets.deliver" and call.get("change_request"):
                return call["change_request"]["summary"]
            sentence = curated_effect_sentence(
                str(call.get("tool_name", "")),
                call.get("parameters") or {},
                call.get("display_hint"),
            )
            if sentence:
                return sentence
        return "Tool execution requires your confirmation."

    @staticmethod
    def _tool_names_have_browser_write(
        tool_names: list[str], gateway_names: dict[str, str]
    ) -> bool:
        """True when any sanitized tool name maps to a write-tier browser tool.

        Single source of truth for the R-1 browser-write predicate, shared by
        the card-headline gate (``_build_confirmation_frame``) and flow-unlock
        authority arming (``_record_flow_approval``) so framing and authority
        can never disagree about whether a batch is a browser-write batch.
        Uses the canonical dotted gateway names captured at park time (the
        model-visible names are sanitized) matched against
        ``BROWSER_WRITE_TOOLS``.
        """
        for sanitized in tool_names:
            gateway_name = gateway_names.get(sanitized, sanitized)
            if gateway_name in BROWSER_WRITE_TOOLS:
                return True
        return False

    @staticmethod
    def _batch_has_browser_write(pending: PendingConfirmation) -> bool:
        """True when the parked batch contains a write-tier browser tool (R-1).

        A batch of only non-browser writes (``k8s.*``, etc.) or only read-tier
        browser probes does not arm flow-unlock.
        """
        return ConfirmationCoordinator._tool_names_have_browser_write(
            pending.tool_names(), pending.gateway_names
        )

    def _record_flow_approval(
        self,
        pending: PendingConfirmation,
        decider_user_id: str,
        session_id: str,
    ) -> None:
        """Record the flow authority when an approved batch holds a browser write.

        SPEC-051 R-1: the authority is scoped to the session AND the approved
        flow's identity (``skill_id`` + ``origin``) captured on the parked
        card's ``browser_flow`` (R-6), so only that flow's subsequent browser
        writes unlock. With no bound flow identity there is nothing to scope to,
        and a batch without a browser write must not arm browser flow-unlock —
        either way nothing is recorded and every write keeps parking. TTL comes
        from settings; ``0`` records an immediately-expired authority
        (flow-unlock disabled — the pre-fix posture).

        SPEC-054 R-2 adds a third condition: the bound flow must be
        ``risk_class == "write"``. A read-class binding can never execute an
        unlocked write — the gateway refuses it ``BROWSER_FLOW_READ_ONLY`` on
        every attempt — so arming an authority there produced an approval that
        silently bought nothing while the card claimed a flow gate. The card
        still renders the read-class binding's headline; only the auto-signing
        authority is withheld, and each write keeps parking.
        """
        if not self._kernel._batch_has_browser_write(pending):
            return
        browser_flow = pending.browser_flow or {}
        skill_id = str(browser_flow.get("skill_id") or "")
        origin = str(browser_flow.get("origin") or "")
        if not skill_id and not origin:
            return
        if str(browser_flow.get("risk_class") or "") != "write":
            return
        FLOW_APPROVALS.record(
            session_id=session_id,
            confirm_id=pending.confirm_id,
            owner_user_id=pending.user_id,
            decider_user_id=decider_user_id,
            skill_id=skill_id,
            origin=origin,
            ttl=self.settings.browser_flow_approval_ttl,
            # SPEC-063 R-4: the flow authority retains the parked batch's
            # originating run, so a later auto-signed write in this flow
            # inherits the same ``run_id`` instead of minting a replacement.
            run_id=pending.run_id,
        )

    async def resume_confirmation(
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
        """Own the claimed park's cleanup, including setup failure and disconnect."""
        from contextlib import aclosing

        try:
            async with aclosing(self._kernel._resume_confirmation(
                session_id, pending, decision, user_name, request_id,
                bearer_token, model_id, owner_user_name, routing_allowed,
            )) as stream:
                async for frame in stream:
                    yield frame
        except Exception:
            LOGGER.warning("confirmation resume unavailable")
            yield {"type": "error", "message": "The resumed turn failed. Start a new turn.",
                   "request_id": request_id, "session_id": pending.session_id}
        finally:
            try:
                if pending.pending_deliveries:
                    await self._kernel._discard_burned_deliveries(
                        list(pending.pending_deliveries), pending.requester_delegated_token
                    )
            finally:
                pending.requester_delegated_token = None
                pending.requester_identity = None
                pending.pending_deliveries = ()
                CONFIRMATION_REGISTRY.resolve(pending.session_id, pending.confirm_id)

    async def _resume_confirmation(
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

        ``user_name`` is the DECIDER (the approver who answered this
        card) and attributes the resolution, the signed executions, and
        the flow authority. ``owner_user_name`` is the SESSION OWNER
        (the original requester); SPEC-054 R-2 lets an unbound resumed
        turn park ANOTHER per-action card, and that new card must be
        owned by the requester — not the approver who happened to resume
        the turn — or the tier_2 self-approval rule would block the same
        approver from deciding the next card. It defaults to ``user_name``
        when the caller cannot supply the owner (e.g. an ownerless
        session), preserving the prior attribution.
        """
        from agentscope.event import ConfirmResult, UserConfirmResultEvent

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
            EXECUTION_REJECTION,
            EXECUTION_REQUESTS,
            GENERATION_OWNER_TOKEN,
        )

        # Decomposition Stage 4b: the ``runtime_kernel``-defined stream-frame
        # primitives resolve through ``runtime_kernel`` at call time (module
        # docstring): avoids the circular import (runtime_kernel imports this
        # module) and keeps behavior byte-identical after the move.
        from agent_service.runtime_kernel import (
            TERMINAL_STREAM_EVENTS,
            flush_prose_frames,
        )

        requester = decider = None
        identity_failed = session_id != pending.session_id
        if self.settings.target_authorization_enabled:
            identity_failed = identity_failed or owner_user_name not in (None, pending.user_id)
            owner_user_name = pending.user_id
        # A rejected caller binding can close only the original parked reply.
        session_id = pending.session_id
        if not identity_failed:
            try:
                requester, decider = await asyncio.to_thread(
                    self._kernel._resume_identities, pending, session_id, user_name, bearer_token
                )
            except Exception:
                identity_failed = True

        # Pass the session's pinned model (SPEC-024 R-3) so the resumed
        # stream rebuilds against the same model that parked it.
        agent, _user_msg_cls, _bound_model_id = await self._kernel.ensure_agent(
            session_id, None if identity_failed else bearer_token, model_id,
            False, routing_allowed,
        )
        # SPEC-025 R-1: resumed frames belong to the same assistant turn as
        # the pre-park frames — no user message was added by the park, so
        # the count reproduces the original turn ordinal.  The original
        # stream captured its turn_index BEFORE the user message entered
        # the context (stream_events line ~892); the confirmation stream
        # runs AFTER the user message is already in context, so subtract 1
        # to align with the pre-park ordinal.
        turn_index = max(0, self._kernel._count_user_turns(agent) - 1)
        evidence_frames: list[dict[str, object]] = []
        # SPEC-049 R-5 applied to chat prose, resumed: the operator's message
        # is already in the context here, so the harvest needs no extra text.
        # A resumed turn is a continuation of the same assistant reply, and
        # the model restating the password after an approval is exactly as
        # much a leak as restating it before one.
        prose = self._kernel._prose_redactor(agent, "", session_id)
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
        if identity_failed:
            execution_requests, execution_rejection = {}, REASON_REQUEST_MISSING
        else:
            execution_requests, execution_rejection = self._kernel._prepare_executions(
                pending, user_name, confirmed, request_id, session_id,
                requester=requester, decider=decider,
            )

        # SPEC-051 R-1: approving a card whose batch contains a browser write
        # records a session+identity-scoped flow authority BEFORE the resumed
        # stream, so same-turn subsequent writes in that flow unlock (auto-sign)
        # instead of re-parking. Denials and non-browser batches record nothing;
        # a batch rejected fail-closed (e.g. ``signing_unavailable``) records
        # nothing either, so the authority is never broader than the batch that
        # actually executed.
        if confirmed and execution_rejection is None:
            self._kernel._record_flow_approval(pending, user_name, session_id)

        # Resolve fallible guard dependencies before binding any task context.
        resume_recovery = self._kernel._execution_recovery()
        resume_guard = (
            self._kernel._bind_guard(resume_recovery, pending.run_id, session_id, pending.user_id)
            if resume_recovery is not None and pending.run_id is not None else None
        )
        trace_queue: asyncio.Queue = asyncio.Queue()
        auth_turn = AuthorizationTurn() if self.settings.target_authorization_enabled else None
        auth_var = CURRENT_AUTHORIZATION_TURN.set(auth_turn)
        sink_var = TOOL_EVIDENCE_SINK.set(trace_queue)
        # SPEC-062 R-3 reveal-on-commit: carry the parked card's held deliveries
        # into PENDING_RELEASE so the middleware emits them the instant an
        # approved gated mutation commits — and only on an approval. A deny (or a
        # batch that never executes) leaves the buffer empty, so nothing is
        # revealed and the delivery burns. STREAM_PENDING collects any NEW
        # delivery generated during this resumed stream (flushed at its normal
        # end, or re-attached to a new card on a re-park).
        release_deliveries_var = PENDING_RELEASE_DELIVERIES.set(
            list(pending.pending_deliveries) if confirmed else []
        )
        pending_deliveries_var = STREAM_PENDING_DELIVERIES.set([])
        # SPEC-063 R-4: arm the secret-release permit map for the resumed stream
        # exactly as stream_events does, so an approved gated mutation that
        # durably commits here can reveal its held portal_copy delivery.
        permits_var = RELEASE_PERMITS.set({})
        prose_var = CURRENT_PROSE_REDACTOR.set(prose)
        token_var = DELEGATED_TOKEN.set(None if identity_failed else bearer_token)
        requester_var = REQUESTER_IDENTITY.set(requester)
        decider_var = DECIDER_IDENTITY.set(decider)
        session_var = CHAT_SESSION_ID.set(session_id)
        owner_token_var = GENERATION_OWNER_TOKEN.set((pending.requester_delegated_token,))
        requests_var = EXECUTION_REQUESTS.set(execution_requests or None)
        rejection_var = EXECUTION_REJECTION.set(execution_rejection)
        audit_var = EXECUTION_AUDIT_CONTEXT.set(
            {
                "settings": self.settings,
                "confirm_id": pending.confirm_id,
                "session_id": session_id,
                "request_id": request_id,
                "decider_user_id": user_name,
                "observe_original": self._kernel._observe_original_step_origin,
            }
            if confirmed
            else None
        )
        # SPEC-063 R-4: rebind the guard to the parked batch's originating run.
        # A resume NEVER mints a replacement identity — it inherits
        # ``pending.run_id``; when admission is enabled but the identity is
        # missing, no guard is bound here and the mutation lane fails closed at
        # registration rather than proceeding under a fresh run. Inert when
        # admission is disabled (recovery is None).
        guard_var = CURRENT_RUN_GUARD.set(resume_guard) if resume_guard is not None else None
        reply_stream = None
        try:
            yield {
                "type": "confirmation_result",
                "confirm_id": pending.confirm_id,
                "status": "approved" if confirmed else "denied",
                # Echo the parked batch so downstream consumers (gateway
                # audit, portal card) can name the decided tools.
                # SPEC-055 R-7: redact the echoed batch too, so the result
                # frame never streams a plaintext secret either (the gateway
                # audit reads only tool_name; signing uses build_requests).
                "pending_calls": redact_structure(redact_pending_calls(
                    pending, pending.pending_calls_payload()
                ), prose.literals),
                "request_id": request_id,
                "session_id": session_id,
            }
            if identity_failed:
                from agentscope.event import UserInterruptEvent

                try:
                    async for _event in agent.reply_stream(UserInterruptEvent(reply_id=pending.reply_id)):
                        pass
                except Exception:
                    LOGGER.warning("requester identity rejection could not close parked reply")
                if pending.pending_deliveries:
                    await self._kernel._discard_burned_deliveries(list(pending.pending_deliveries), pending.requester_delegated_token)
                async for frame in self._kernel.fallback_stream(request_id, session_id,
                        "The requester identity is unavailable or expired. Start a fresh requester turn; no pending tool was dispatched."):
                    yield frame
                return
            reply_stream = agent.reply_stream(confirm_event)
            async for event in reply_stream:
                self._kernel.clear_error()
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
                    # SPEC-035 R-2, as in stream_events: release the held tail
                    # before the tool frames so the portal's paragraph break
                    # falls on the segment boundary and not one hold-length
                    # early inside the preceding word.
                    for flushed in flush_prose_frames(
                        prose, request_id, session_id
                    ):
                        yield flushed
                for decorated in drained:
                    yield decorated
                # A resumed turn can park again on another ASK-gated tool.
                # SPEC-054 R-2: attribute the re-parked card to the SESSION
                # OWNER (the original requester), not the approver whose
                # confirm resumed this turn — otherwise the tier_2
                # self-approval rule blocks that same approver from deciding
                # the next unbound per-action card. ``user_name`` (the
                # decider) still attributes this card's own resolution above.
                frame = self._kernel._build_confirmation_frame(
                    event,
                    session_id,
                    owner_user_name or user_name,
                    agent.toolkit,
                    turn_index=turn_index,
                    evidence_frames=evidence_frames,
                    run_id=pending.run_id,
                )
                if frame is not None:
                    # A re-park ends this stream without a terminal frame, so
                    # this is its only chance to release the held-back tail.
                    for flushed in flush_prose_frames(
                        prose, request_id, session_id
                    ):
                        yield flushed
                    yield {
                        **frame,
                        "request_id": request_id,
                        "session_id": session_id,
                    }
                    return
                frame = self._kernel.normalize_event(
                    event, request_id, session_id, redactor=prose
                )
                if frame.get("event") in TERMINAL_STREAM_EVENTS:
                    for flushed in flush_prose_frames(
                        prose, request_id, session_id
                    ):
                        yield flushed
                yield frame
            # Safety net for a resumed stream that ends without a terminal
            # frame, released before the closing trace frames for the same
            # paragraph reason as in the loop. flush is idempotent, so the
            # paths above add nothing here.
            for flushed in flush_prose_frames(prose, request_id, session_id):
                yield flushed
            # SPEC-062 R-3 reveal-on-commit: flush only deliveries GENERATED
            # during this resumed stream (a standalone generate with no further
            # gate). Held deliveries from the prior park live in PENDING_RELEASE
            # and are NOT flushed here — if the gated mutation never committed
            # they burn silently, which is the deny/failure posture.
            self._kernel._flush_pending_deliveries(trace_queue)
            for decorated in self._kernel._drain_trace_queue(
                trace_queue,
                request_id,
                session_id,
                evidence_frames,
                execution_requests,
            ):
                yield decorated
            # SPEC-062 R-3 deny-path hardening: actively discard the deliveries
            # that burned — never released because the gate was denied, or because
            # an approved gate's mutation failed/never committed — so the handle is
            # not redeemable even by a direct owner-scoped fetch during the hold
            # TTL. On a deny these are the parked card's deliveries (never carried
            # into PENDING_RELEASE); on an approve, the unreleased remainder. A
            # re-park returned early above (its deliveries ride the new card), so a
            # still-pending handle is never discarded. Best-effort: a failure here
            # degrades to the hold-TTL expiry burn.
            burned = (
                list(pending.pending_deliveries)
                if not confirmed
                else list(PENDING_RELEASE_DELIVERIES.get() or [])
            )
            if burned:
                await self._kernel._discard_burned_deliveries(
                    burned, pending.requester_delegated_token
                )
        except Exception as exc:
            self._kernel.remember_error(exc, prose.literals if prose is not None else ())
            LOGGER.error("AgentScope confirmation resume failed: %s", self._kernel._last_error)
            yield {"type": "error", "message": "The resumed turn failed. Start a new turn.",
                   "request_id": request_id, "session_id": session_id}
        finally:
            if auth_turn is not None:
                await self._kernel._finish_authorization_stream(auth_turn, reply_stream)
                self._kernel._drain_trace_queue(trace_queue, request_id, session_id, evidence_frames, execution_requests)
            # Covers both completion and re-park (the early return above):
            # either way the frames drained so far belong to this turn.
            self._kernel._persist_evidence(
                session_id, request_id, turn_index, evidence_frames
            )
            CURRENT_PROSE_REDACTOR.reset(prose_var)
            DELEGATED_TOKEN.reset(token_var)
            REQUESTER_IDENTITY.reset(requester_var)
            DECIDER_IDENTITY.reset(decider_var)
            CHAT_SESSION_ID.reset(session_var)
            EXECUTION_REQUESTS.reset(requests_var)
            EXECUTION_REJECTION.reset(rejection_var)
            GENERATION_OWNER_TOKEN.reset(owner_token_var)
            pending.requester_delegated_token = None
            pending.requester_identity = None
            # SPEC-062 R-3: drop the held deliveries after resume — released on a
            # gated commit, burned on a deny/failure, or re-attached to a re-parked
            # card by _drain_held_deliveries — so a resolved entry never retains a
            # live secret handle.
            pending.pending_deliveries = ()
            STREAM_PENDING_DELIVERIES.reset(pending_deliveries_var)
            PENDING_RELEASE_DELIVERIES.reset(release_deliveries_var)
            RELEASE_PERMITS.reset(permits_var)
            EXECUTION_AUDIT_CONTEXT.reset(audit_var)
            if guard_var is not None:
                CURRENT_RUN_GUARD.reset(guard_var)
            TOOL_EVIDENCE_SINK.reset(sink_var)
            if auth_turn is not None:
                auth_turn.close()
            CURRENT_AUTHORIZATION_TURN.reset(auth_var)
            CONFIRMATION_REGISTRY.resolve(session_id, pending.confirm_id)
            # SPEC-031 R-1: idempotent safety net — the confirm route
            # already wrote the outcome at claim time (R-4), so this only
            # covers paths that resolved without a claim-time write.
            self._kernel._record_resolution(
                session_id,
                pending.confirm_id,
                "approved" if confirmed else "denied",
                user_name,
                decision,
            )
            self._kernel._snapshot_state(session_id, agent, prose.literals)

    async def expire_confirmation(
        self,
        session_id: str,
        confirm_id: str,
        model_id: str | None = None,
        routing_allowed: bool = False,
    ) -> None:
        """Close a TTL-expired parked reply without resuming it (SPEC-020 R-2).

        Feeds ``UserInterruptEvent`` so the kernel closes the parked calls
        with an interrupted result, then drops the registry entry. Never
        streams to a client; a failed interrupt still resolves the entry so
        the session cannot wedge. Claimed entries are unreachable here:
        an in-flight resume owns the entry and resolves it in its own
        ``finally``, so a racing expiry can never interrupt an approved
        batch mid-stream (``take_for_expiry`` raises instead).

        ``model_id`` must be the session's resolved pin, exactly as
        ``resume_confirmation`` receives it. Left ``None`` it normalizes to
        ``settings.provider`` — a bare provider name — which never equals a
        session pinned to a concrete model, so ``ensure_agent`` evicts and
        rebuilds the agent before the interrupt is fed. The rebuilt agent
        restores persisted *memory* but not the in-flight parked reply, so
        the ``UserInterruptEvent`` lands on nothing: the parked call never
        receives its interrupted result and the turn is left with no
        closure. Expiry must not change the model a session runs on.
        """
        from agentscope.event import UserInterruptEvent

        # Take-for-expiry ignores TTL (this path exists precisely to close
        # an expired entry) but claims the entry first, keeping the
        # interrupt single-flight against confirms and concurrent expiries.
        pending = CONFIRMATION_REGISTRY.take_for_expiry(session_id, confirm_id)
        try:
            agent, _user_msg_cls, _bound_model_id = await self._kernel.ensure_agent(
                session_id, None, model_id, False, routing_allowed
            )
            prose = self._kernel._prose_redactor(agent, "", session_id)
            interrupt = UserInterruptEvent(reply_id=pending.reply_id)
            async for _event in agent.reply_stream(interrupt):
                pass
            self._kernel._snapshot_state(session_id, agent, prose.literals)
        except Exception as exc:  # pragma: no cover - defensive cleanup
            LOGGER.warning(
                "expiring confirmation %s failed to interrupt parked reply: %s",
                confirm_id,
                type(exc).__name__,
            )
        finally:
            # SPEC-062 R-3 deny-path hardening: an expired park burns its held
            # deliveries too, so actively discard them rather than leaving the
            # handle redeemable for the remainder of the hold TTL. Best-effort —
            # the requester token may itself have expired by now, which degrades
            # to the gateway hold-TTL burn.
            if pending.pending_deliveries:
                await self._kernel._discard_burned_deliveries(
                    list(pending.pending_deliveries),
                    pending.requester_delegated_token,
                )
            pending.requester_delegated_token = None
            pending.requester_identity = None
            pending.pending_deliveries = ()
            CONFIRMATION_REGISTRY.resolve(session_id, confirm_id)
            # SPEC-031 R-1: surface expiry as an outcome, not a
            # disappearance — the record stays visible as expired.
            self._kernel._record_resolution(
                session_id, confirm_id, "expired", None, None
            )
        LOGGER.info(
            "kernel confirmation expired",
            extra={"session_id": session_id, "confirm_id": confirm_id},
        )
