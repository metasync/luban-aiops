"""Signed-execution orchestration for the AgentKernel (decomposition Stage 3).

``ExecutionDispatcher`` owns the kernel's signed-request / receipt / ledger
orchestration path (SPEC-037/051/063/077): the lazily built durable recovery
store (SPEC-063 R-2), the durable run-identity + ``RunGuard`` bind (R-4), the
per-action signing site (``_prepare_executions``), the best-effort durable
request write (``_persist_execution_request``), the flow-unlock auto-signer
(``_sign_flow_execution``, armed as the permission middleware's ``flow_signer``),
the receipt-timing helper (``_execution_duration_ms``), and the canonical
execution-audit emitter (``_emit_execution_event``).

``AgentKernel`` keeps a thin delegator for every method here plus read/write-
through ``_recovery`` / ``_recovery_built`` properties, so the public surface —
including ``api/v2/routes.py`` and ``services/execution_recovery.py`` calling
``kernel._execution_recovery()``, the ``flow_signer=self._sign_flow_execution``
middleware binding, and every test that calls ``kernel._prepare_executions`` /
``kernel._sign_flow_execution`` / ``kernel._resolve_run_id`` / ``kernel._bind_guard``
or monkeypatches ``kernel._execution_recovery`` / ``kernel._bind_guard`` on the
instance — is unchanged.

Two invariants keep the move byte-identical:

* Sibling calls route back through ``self._kernel._X(...)`` (never the
  dispatcher's own bound method), so an instance-level
  ``monkeypatch.setattr(kernel, "_execution_recovery"/"_emit_execution_event"/
  "_persist_execution_request"/...)`` stays authoritative — the same route-back
  discipline Stage 2's collaborators follow.
* ``emit_audit_event`` is resolved through the ``runtime_kernel`` namespace at
  call time (never a module-level import here), so the long-standing
  ``monkeypatch.setattr("agent_service.runtime_kernel.emit_audit_event", ...)``
  test surface still intercepts execution audits after the move (the exact
  hazard class Stage 2 hit with ``AGENT_STATE_STORE``).

The crypto / canonicalization core (``build_requests`` / ``build_flow_request`` /
``build_receipt`` and friends) stays in ``services/execution_signing.py`` and is
imported by identity here, so signature bytes are untouched. Method bodies are
extracted verbatim from ``runtime_kernel.AgentKernel`` (behavior byte-identical);
see ``docs/workspace/agent-kernel-decomposition-spike.md``.
"""

import json
import logging
from datetime import datetime, timezone

from agent_service.runtime_settings import RuntimeSettings
from agent_service.services.agent_role import current_agent_role_value
from agent_service.services.audit_emitter import build_audit_event
from agent_service.services.delegated_identity import (
    DECIDER_IDENTITY,
    REQUESTER_IDENTITY,
    DelegatedIdentityError,
    VerifiedHuman,
)
from agent_service.services.execution_records import (
    EXECUTION_RECORD_STORE,
    make_execution_record,
)
from agent_service.services.execution_recovery import ExecutionRecovery
from agent_service.services.execution_signing import (
    REASON_REQUEST_MISSING,
    REASON_SIGNING_UNAVAILABLE,
    build_flow_request,
    build_requests,
)
from agent_service.services.flow_approvals import (
    BROWSER_WRITE_TOOLS,
    FLOW_APPROVALS,
    FLOW_CONTEXTS,
)
from agent_service.services.hitl_confirmations import (
    PendingConfirmation,
    RISK_LEVEL_ACTIONS,
)

LOGGER = logging.getLogger(__name__)


class ExecutionDispatcher:
    """The kernel's signed-request / receipt / ledger orchestration surface.

    Holds a back-reference to the owning ``AgentKernel`` and reads ``settings``
    *live* through it (never a captured snapshot). It owns the durable recovery
    slot (``_recovery`` / ``_recovery_built``); the kernel exposes both through
    read/write-through properties. Sibling execution calls (and the authoring-
    trace capture, which stays on the kernel) route back through ``self._kernel``
    so the kernel's delegators — and any monkeypatch on them — stay authoritative.
    """

    def __init__(self, kernel) -> None:
        self._kernel = kernel
        # SPEC-063 R-2: agent-side durable execution recovery/admission store,
        # built lazily and only when admission is enabled. ``None`` (the
        # default) keeps the legacy in-process handoff path byte-identical, so
        # a partially upgraded mutation path is never enabled by construction.
        self._recovery: ExecutionRecovery | None = None
        self._recovery_built = False

    @property
    def settings(self) -> RuntimeSettings:
        return self._kernel.settings

    def _execution_recovery(self) -> ExecutionRecovery | None:
        """The agent-side durable recovery store, or ``None`` when disabled.

        Admission is disabled by default (SPEC-063 R-2a): with the flag off the
        kernel returns ``None`` and every execution seam stays on the legacy
        path. When enabled, ``RuntimeSettings.__post_init__`` has already
        guaranteed a ledger DSN and epoch at startup, so this builds the store
        once and caches it. Construction never connects (the connection factory
        is per-call and bounded), so building is cheap and side-effect free.
        """
        if not self.settings.execution_admission_enabled:
            return None
        if not self._recovery_built:
            self._recovery = ExecutionRecovery(
                self.settings.execution_state_db_url,
                self.settings.execution_signing_key,
                self.settings.execution_admission_epoch,
                admission_enabled=True,
            )
            self._recovery_built = True
        return self._recovery

    def _resolve_run_id(
        self, recovery, session_id, owner_user_id, flow_approval=None
    ) -> str | None:
        """The durable run identity for this human root turn (SPEC-063 R-4).

        A reused flow authority inherits its originating run across later turns;
        otherwise a new human root turn mints one via the ledger. Returns
        ``None`` when the identity cannot be established (store unavailable), so
        the mutation lane fails closed rather than proceeding without a durable
        run — a missing identity is never silently replaced.
        """
        inherited = getattr(flow_approval, "run_id", None) if flow_approval else None
        if inherited:
            return str(inherited)
        from agent_service.services.execution_protocol import ProtocolError

        try:
            return recovery.create_run(session_id, owner_user_id)
        except ProtocolError as exc:
            LOGGER.warning(
                "execution run creation failed for session %s: %s",
                session_id,
                exc.reason,
            )
            return None

    def _bind_guard(self, recovery, run_id, session_id, owner_user_id):
        """Build the turn's ``RunGuard`` bound to a resolved run identity."""
        from agent_service.services.execution_run_guard import RunGuard, RunIdentity

        return RunGuard(
            RunIdentity(str(run_id), session_id, owner_user_id), recovery=recovery
        )

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
                self._kernel._emit_execution_event(
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
        # The signed envelope carries an ``args_digest``, never the raw
        # arguments, so the authoring-trace capture below has to be handed
        # them separately (SPEC-055 R-2). One read of the parked payload
        # yields both the arguments and the risk tier the toolkit
        # snapshotted at park time; it is raw at resume because
        # ``redact_parameters`` is a display/at-rest projection applied to
        # copies, never to a signing input.
        calls_by_id: dict[str, dict] = {
            str(call.get("call_id")): call
            for call in pending.pending_calls_payload()
        }
        # SPEC-063 R-4: an approved resume under durable admission signs a v3
        # envelope bound to the parked batch's originating run. The identity is
        # inherited from ``pending.run_id`` and never re-minted here; a resume
        # missing it (e.g. a card parked before the cutover) fails closed rather
        # than degrading to a v2 envelope that the bound v3 guard would reject
        # mid-dispatch. Inert when admission is disabled (recovery is None).
        sign_run_id: str | None = None
        sign_epoch: str | None = None
        if self._kernel._execution_recovery() is not None:
            if not pending.run_id:
                LOGGER.warning(
                    "mutating resume rejected: no durable run identity on the "
                    "parked batch (confirm_id=%s)",
                    pending.confirm_id,
                )
                for call in pending.pending_calls_payload():
                    self._kernel._emit_execution_event(
                        "execution_rejected",
                        "deny",
                        {
                            "confirm_id": pending.confirm_id,
                            "call_id": call.get("call_id"),
                            "tool_name": call.get("tool_name"),
                            "reason": REASON_REQUEST_MISSING,
                        },
                        request_id,
                        session_id,
                        decider_user_id,
                    )
                return {}, REASON_REQUEST_MISSING
            sign_run_id = pending.run_id
            sign_epoch = self.settings.execution_admission_epoch
        try:
            if self.settings.target_authorization_enabled and pending.requester_identity is not None and requester is None:
                raise DelegatedIdentityError()
            requests = build_requests(
                pending, decider_user_id, key, run_id=sign_run_id,
                admission_epoch=sign_epoch, requester=requester, decider=decider,
            )
        except DelegatedIdentityError:
            return {}, REASON_REQUEST_MISSING
        for request in requests:
            requests_by_call[request["call_id"]] = request
            self._kernel._persist_execution_request(request)
            call = calls_by_id.get(str(request["call_id"])) or {}
            # Being *signed* is not the same as being a mutation, so the
            # trace gate is the tier rather than the signature. A read-tier
            # call reaches this seam whenever it is off the middleware's
            # curated auto-allow list — an unvetted read tool parks and is
            # signed like any other ASK-gated call — and it is not a replay
            # step: a graduated flow declares ``risk_class: write``, so a
            # read in its step list is refused by R-4's blast-radius
            # re-validation, which derives read-tier from the same
            # ``BROWSER_WRITE_TOOLS`` set rather than keeping a second list.
            # The platform's single risk→action mapping decides, so this seam
            # and the policy bridge cannot disagree about what a mutation
            # is; a call with no known tier is not captured either, which
            # degrades to "no graduation candidate" — the outcome R-2
            # already accepts for a store failure — rather than polluting a
            # store that outlives every receipt. The flow-unlock site needs
            # no such gate: it is reachable only through
            # ``BROWSER_WRITE_TOOLS``.
            if RISK_LEVEL_ACTIONS.get(call.get("risk_level")) == "tools:mutate":
                self._kernel._capture_authoring_step(
                    request, dict(call.get("parameters") or {})
                )
            self._kernel._emit_execution_event(
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

    def _sign_flow_execution(
        self, tool_call: object, gateway_tool_name: str
    ) -> dict | None:
        """Auto-sign one unlocked browser write under a flow authority (SPEC-051 R-1/R-3).

        Armed as ``GatewayPermissionMiddleware``'s ``flow_signer``. Returns a
        signed execution envelope — injecting it into the shared
        ``EXECUTION_REQUESTS`` map so the tool closure verifies and hands off
        exactly like a card-approved call — or ``None`` to fail safe and let the
        write park. ``None`` (→ ASK) whenever: the tool is not a browser write;
        the session id is absent; no live flow authority exists (TTL lapse or
        ``ttl <= 0`` disable); the bound ``FlowContext`` identity no longer
        matches the approval (a rebind — the guard that eliminates the ADR-0007
        cross-flow window); the execution state is not armed
        (``EXECUTION_REQUESTS`` is not a dict); or no signing key is
        provisioned. Each unlocked write is still individually signed,
        persisted, audited (``execution_requested``), and appended to the
        session's authoring trace, and the tool-gateway deviation guard still
        bounds it on invocation.
        """
        from agent_service.tools.gateway_tools import (
            CHAT_SESSION_ID,
            EXECUTION_AUDIT_CONTEXT,
            EXECUTION_REQUESTS,
        )

        if gateway_tool_name not in BROWSER_WRITE_TOOLS:
            # SPEC-055 R-5: enforce this function's own stated scope — "one
            # unlocked *browser* write" — rather than inheriting it from the
            # middleware that happens to be its only caller today. A browser
            # flow authority is scoped to a web target the operator approved;
            # auto-signing an infra mutation under it would execute a write no
            # decision of theirs covers, which is the one thing the OQ-2
            # per-action fallback must never do. Ahead of every side effect
            # below — the ``EXECUTION_REQUESTS`` injection, the durable
            # execution record, the authoring-trace step and the
            # ``execution_requested`` audit — so a refused name leaves no
            # trace of a request that was never made. (The lookups it also
            # precedes are pure reads every other ``None`` path takes too;
            # the side effects are what the position buys.) Fail-safe:
            # ``None`` parks the call, exactly as an absent authority would.
            return None

        # SPEC-063 R-4 (T-21): gate at the flow-signing seam itself, not only at
        # the permission middleware that precedes it. A stopped run must never
        # auto-sign a flow-unlocked browser write — signing persists an intent
        # registration, an authoring-trace step, and an ``execution_requested``
        # audit, so the check belongs ahead of every one of those side effects.
        # Fail safe: ``None`` parks the write exactly as an absent authority
        # would, and the durable worker claim/final-send gates stay the backstop.
        # Inert when no guard is bound (admission disabled), so the legacy
        # flow-unlock path is byte-identical.
        from agent_service.services.execution_run_guard import current_guard

        flow_guard = current_guard()
        if flow_guard is not None and flow_guard.stopped():
            return None

        session_id = CHAT_SESSION_ID.get()
        if not session_id:
            return None
        approval = FLOW_APPROVALS.get(session_id)
        if approval is None:
            return None
        context = FLOW_CONTEXTS.get(session_id)
        if context is None or context.identity() != approval.identity():
            # No bound flow, or the flow was rebound to a different skill/origin
            # since approval — fail safe and re-park (SPEC-051 R-1 identity
            # guard). This is what eliminates the cross-flow auto-sign window.
            return None
        requests = EXECUTION_REQUESTS.get()
        if not isinstance(requests, dict):
            # Execution state not armed for this turn — nothing to inject into,
            # so the write cannot be verified/handed off; park it instead.
            return None
        key = self.settings.execution_signing_key
        if not key:
            return None
        call_id = str(getattr(tool_call, "id", "") or "")
        if not call_id:
            return None
        # Parse the parked arguments exactly as the card path does, so the
        # args_digest matches what the tool closure recomputes from the invoked
        # kwargs (SPEC-037 R-3). Display enrichment never touches parameters.
        raw = getattr(tool_call, "input", "") or ""
        try:
            parsed = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            parsed = {}
        parameters = parsed if isinstance(parsed, dict) else {}
        # SPEC-063 R-4: a flow-unlocked write under durable admission signs a v3
        # envelope bound to the flow authority's run. The authority recorded at
        # the approving card carries ``run_id``; if it predates the cutover the
        # identity is absent, so fail safe and park (return None) rather than
        # sign a v2 envelope the bound v3 guard would reject mid-dispatch.
        sign_run_id: str | None = None
        sign_epoch: str | None = None
        if self._kernel._execution_recovery() is not None:
            if not approval.run_id:
                return None
            sign_run_id = approval.run_id
            sign_epoch = self.settings.execution_admission_epoch
        requester = REQUESTER_IDENTITY.get() if self.settings.target_authorization_enabled else None
        decider = DECIDER_IDENTITY.get() if requester is not None else None
        try:
            envelope = build_flow_request(
                call_id=call_id,
                tool_name=gateway_tool_name,
                parameters=parameters,
                flow_approval=approval,
                key=key,
                run_id=sign_run_id,
                admission_epoch=sign_epoch,
                requester=requester,
                decider=decider,
            )
        except DelegatedIdentityError:
            return None  # A new turn cannot impersonate a previous approver.
        # Inject BEFORE the tool closure runs (the permission check precedes
        # acting), so _verify_execution_request finds it by call_id and
        # _handoff_execution presents it to the worker.
        requests[call_id] = envelope
        self._kernel._persist_execution_request(envelope)
        # Same seam as the card path, so a session mixing per-action writes
        # and flow-unlocked writes yields one ordered trace (SPEC-055 R-2).
        # ``parameters`` here is the very object just digested into
        # ``envelope["args_digest"]``.
        self._kernel._capture_authoring_step(envelope, parameters)
        audit_context = EXECUTION_AUDIT_CONTEXT.get() or {}
        self._kernel._emit_execution_event(
            "execution_requested",
            "success",
            {
                "confirm_id": envelope["confirm_id"],
                "execution_id": envelope["execution_id"],
                "call_id": envelope["call_id"],
                "tool_name": envelope["tool_name"],
                "args_digest": envelope["args_digest"],
                "decider_user_id": envelope["decider_user_id"],
                "owner_user_id": envelope["owner_user_id"],
            },
            str(audit_context.get("request_id") or ""),
            session_id,
            envelope["decider_user_id"],
        )
        return envelope

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
            # SPEC-075/076: attribute the execution to the acting agent-role.
            # Live on the SPEC-076 orchestration path (a bound diagnostician /
            # orchestrator role projects verbatim); the unscoped single-agent
            # turn binds none, so the emitter omits the field and that event
            # stays byte-identical.
            agent_role=current_agent_role_value(),
        )
        # Resolved through ``runtime_kernel``'s binding — not a module-level
        # import here — so the existing
        # ``monkeypatch.setattr("agent_service.runtime_kernel.emit_audit_event", ...)``
        # test surface stays authoritative after the Stage-3 move (the same
        # call-time indirection AgentRegistry uses for ``AGENT_STATE_STORE``).
        from agent_service.runtime_kernel import emit_audit_event

        emit_audit_event(self.settings, event)
