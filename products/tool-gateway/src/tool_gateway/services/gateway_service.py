from __future__ import annotations

import logging

from fastapi import HTTPException
from fastapi import Request

from tool_gateway.core.config import GatewaySettings
from tool_gateway.core.metrics import (
    record_policy_decision,
    record_redacted_spans,
    record_token_verification,
)
from tool_gateway.core.observability import log_event
from tool_gateway.core.request_context import execution_correlation
from tool_gateway.metadata import SERVICE_NAME, SERVICE_VERSION
from tool_gateway.schemas.api import IdentityContext
from tool_gateway.services.audit_emitter import build_audit_event, emit_audit_event
from tool_gateway.services.policy_engine import (
    PolicyLoadError,
    bundle_sha256,
    evaluate,
    load_bundle,
)
from tool_gateway.services.token_verifier import TokenVerificationError, verify_token
from tool_gateway.tools.auth_resolution import DELEGATION_MODE
from tool_gateway.tools.base import (
    TARGET_AUTHORIZATION_REQUIRED,
    ToolResult,
    make_denied_result,
    make_error_result,
)
from tool_gateway.tools.redaction import redact_result
from tool_gateway.tools.registry import ToolRegistry

LOGGER = logging.getLogger(__name__)

# SPEC-069 R-4/R-5: keys ``invoke_tool`` writes into the ``tool_invoked`` record
# itself (plus ``execution_id`` from the correlation hint). A connector-declared
# attribution colliding with one would raise ``TypeError`` on the ``**`` splat,
# turning an audit enrichment into an HTTP 500 *after* the tool already ran, so
# collisions are dropped with a warning rather than propagated.
_RESERVED_AUDIT_KEYS = frozenset({
    "request_id", "tool_name", "status", "duration_ms", "risk_level",
    "target_system", "user_id", "sub", "act", "redacted_spans", "execution_id",
})

# SPEC-070 producer wiring. The acquisition seam returns the transitional
# ``DELEGATED_REAUTHORIZATION_REQUIRED`` denial when a delegated credential set
# has no usable grant yet; the producer upgrades it to a durable challenge under
# the reserved ``TARGET_AUTHORIZATION_REQUIRED`` code the kernel promotes to a
# bounded stop. The promoted message is deliberately generic — it names no owner,
# target internals, or credential detail (the safe metadata rides the validated
# ``authorization_required`` envelope instead).
_DELEGATED_REAUTH_CODE = "DELEGATED_REAUTHORIZATION_REQUIRED"
_AUTHORIZATION_REQUIRED_MESSAGE = (
    "target authorization required: the owner must approve this target before "
    "the call can proceed"
)


def resolve_audit_attribution(target: object, result: object, tool_name: str,
                      request_id: str) -> dict:
    """Read a connector's opt-in audit attribution, dropping reserved keys.

    Duck-typed and opt-in (SPEC-069 R-4/R-5): a target that does not declare
    ``audit_attribution`` yields ``{}``, so its audit record is byte-identical
    to before the hook existed.
    """
    attributor = getattr(target, "audit_attribution", None)
    if not callable(attributor):
        return {}
    attribution = attributor(result)
    if not isinstance(attribution, dict) or not attribution:
        return {}
    clash = sorted(_RESERVED_AUDIT_KEYS.intersection(attribution))
    if clash:
        LOGGER.warning(
            "audit attribution dropped reserved keys",
            extra={
                "request_id": request_id,
                "tool_name": tool_name,
                "reserved_keys": clash,
            },
        )
        return {k: v for k, v in attribution.items()
                if k not in _RESERVED_AUDIT_KEYS}
    return attribution


def live_status(settings: GatewaySettings) -> dict[str, str]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
    }


async def ready_status(settings: GatewaySettings) -> dict[str, object]:
    """Readiness: the policy bundle must load; nothing else is a dependency."""
    try:
        rules = load_bundle(settings)
        return {
            "status": "ok",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "policy_rules": len(rules),
            # SPEC-048 R-1: bundle fingerprint on the readiness surface.
            "policy_bundle_sha256": bundle_sha256(),
        }
    except PolicyLoadError as exc:
        return {
            "status": "degraded",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "policy_error": str(exc),
        }


async def resolve_request_identity(
    settings: GatewaySettings,
    request: Request,
    request_id: str,
) -> IdentityContext | None:
    """Resolve identity via local JWT verification.

    - If a bearer token is present, verify it locally (no network call).
    - If auth is required and no valid token, raise 401.
    - If auth is optional and no token, return a synthetic dev identity.
    """
    authorization = request.headers.get("authorization")

    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            record_token_verification("invalid")
            raise HTTPException(status_code=401, detail="malformed authorization header")
        try:
            identity = verify_token(settings, token)
            record_token_verification("valid")
            LOGGER.info(
                "identity verified locally",
                extra={
                    "request_id": request_id,
                    "sub": identity.subject,
                    "username": identity.username,
                    "roles": identity.roles,
                    "authenticated": True,
                    "synthetic": False,
                },
            )
            return identity
        except TokenVerificationError as exc:
            record_token_verification(
                "expired" if exc.detail == "token expired" else "invalid"
            )
            raise HTTPException(status_code=401, detail=exc.detail) from exc

    # No token present.
    record_token_verification("missing")
    if settings.require_auth:
        raise HTTPException(status_code=401, detail="authentication required")

    # Synthetic dev identity (R-4).
    synthetic = IdentityContext(
        subject="dev",
        username=settings.dev_user,
        roles=["developer"],
        groups=[],
    )
    LOGGER.info(
        "using synthetic dev identity",
        extra={
            "request_id": request_id,
            "username": synthetic.username,
            "authenticated": False,
            "synthetic": True,
        },
    )
    return synthetic


def enforce_policy(
    settings: GatewaySettings,
    identity: IdentityContext,
    action: str,
    request_id: str,
    agent_role: str | None = None,
) -> None:
    """Evaluate the action against the policy bundle; raise 403 on deny (R-3/R-4).

    Verified and synthetic identities take the identical path — the developer
    role is granted access by policy, never by bypass.

    SPEC-074: ``agent_role`` is the optional agent-role axis forwarded to
    ``evaluate()``. It defaults to ``None`` and **no deployed caller passes a
    non-``None`` value**: SPEC-073 R-3 keeps the bound role off every wire field,
    so even with the SPEC-076 phase-5 in-process producer the axis stays
    ready-but-inert — it goes live only via the phase-6 wire contract or the
    ``FU-076-c`` in-process evaluation point. A reachability guard test enforces
    the zero-offender invariant.
    """
    decision = evaluate(settings, identity.roles, action, agent_role)
    record_policy_decision(action, decision.decision)
    log_extra = {
        "request_id": request_id,
        "subject": identity.subject,
        "roles": identity.roles,
        "action": action,
        "decision": decision.decision,
        "matched_rule_ids": decision.matched_rule_ids,
    }
    if decision.decision == "deny":
        LOGGER.warning("policy decision", extra=log_extra)
        raise HTTPException(
            status_code=403,
            detail={
                "detail": "action denied by policy",
                "action": action,
                "reason": decision.reason,
            },
        )
    LOGGER.info("policy decision", extra=log_extra)


def resolve_delegated_read_requester(
    settings: GatewaySettings, request: Request
) -> tuple[str, str] | None:
    """Derive the verified delegated requester for a read invocation, or ``None``.

    SPEC-070 R-2a (plan line 66): *reads use their directly verified requester
    context* — never a caller-supplied override. When the acquisition seam is
    provisioned, the presentation bearer is re-verified against the
    delegated-human trust bar (the identical bar the execution handoff and the
    authorization owner edges hold: RS256 under the delegated-identity JWKS,
    pinned issuer/audience, ``oidc`` provenance, an allowlisted RFC-8693 ``act``
    actor, and bounded immutable ``sub``) and the pinned
    ``(delegated_identity_issuer, sub)`` is returned as the inert acquisition
    binding.

    This is independent of the portal ``verify_token`` that drives policy: a token
    valid for policy is not automatically a delegated human. Any disabled
    runtime, unprovisioned trust set, missing bearer, or verification failure
    yields ``None``, so a delegated credential set then fails closed at the
    connector rather than acquiring under an unverified owner. The bearer is never
    persisted, echoed, or logged.
    """
    if not settings.delegated_acquisition_enabled:
        return None
    if not (
        settings.delegated_identity_issuer
        and settings.delegated_identity_audience
        and settings.delegated_identity_jwks_url
        and settings.delegated_identity_actors
    ):
        return None
    authorization = request.headers.get("authorization")
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    from tool_gateway.services.delegated_invoke import decode_delegated_human_claims

    try:
        claims = decode_delegated_human_claims(settings, token.strip())
    except Exception:
        return None
    return settings.delegated_identity_issuer, str(claims["sub"])


async def _produce_authorization_challenge(
    result: ToolResult,
    identity_dict: dict,
    producer,
) -> ToolResult:
    """Upgrade a verified delegated re-authorization denial to a durable challenge.

    SPEC-070 producer wiring. This is the bridge between the acquisition seam
    (which fails closed with the transitional ``DELEGATED_REAUTHORIZATION_REQUIRED``
    denial when a delegated credential set has no usable grant) and the kernel
    bounded stop (which promotes the reserved ``TARGET_AUTHORIZATION_REQUIRED``
    result). It fires only when *every* gate holds:

    * the authorization runtime is wired (``producer`` is not ``None``);
    * the result is exactly that transitional denial;
    * the invocation carries the DIRECTLY verified owner — the
      ``delegated_requester_namespace``/``_sub`` threaded from the re-verified
      read bearer, never a caller-supplied override;
    * the invocation carries the session/call correlation to bind the challenge
      to the exact call (a delegated *write* handoff has no ``call_id``, so it
      naturally never produces — Continue is always a fresh read turn).

    The producer mints one pending ``AuthorizationTransaction`` and returns only
    safe metadata; a fail-closed ``None`` (unavailable configuration,
    unadministered linkage, or a store conflict) leaves the denial untouched. The
    promoted result carries the reserved code plus the ``authorization_required``
    envelope the kernel middleware validates, and preserves the connector's own
    evidence so audit attribution is unchanged.
    """
    if producer is None or result.status != "denied":
        return result
    error = result.error
    if not isinstance(error, dict) or error.get("code") != _DELEGATED_REAUTH_CODE:
        return result
    owner_namespace = identity_dict.get("delegated_requester_namespace")
    owner_sub = identity_dict.get("delegated_requester_sub")
    session_id = identity_dict.get("chat_session_id")
    call_id = identity_dict.get("chat_call_id")
    if not (owner_namespace and owner_sub and session_id and call_id):
        return result
    challenge = await producer.produce_challenge(
        owner_namespace=owner_namespace,
        owner_sub=owner_sub,
        session_id=session_id,
        call_id=call_id,
    )
    if challenge is None:
        return result
    return ToolResult(
        tool_name=result.tool_name,
        status="error",
        evidence=result.evidence,
        error={
            "code": TARGET_AUTHORIZATION_REQUIRED,
            "message": _AUTHORIZATION_REQUIRED_MESSAGE,
        },
        authorization_required=challenge.model_dump(mode="json", exclude_none=True),
    )


async def invoke_tool(
    settings: GatewaySettings,
    registry: ToolRegistry,
    request: Request,
    identity: IdentityContext | None,
    request_id: str,
    *,
    challenge_producer=None,
) -> "JSONResponse":
    """Orchestrate tool invocation: policy check -> dispatch -> audit log."""
    body = await request.json()
    # SPEC-063 R-5b: a syntactically bounded correlation hint, not authority.
    correlation = execution_correlation(request.headers.get("x-execution-id"))
    tool_name = body.get("tool_name", "")
    parameters = body.get("parameters", {})
    # Chat-session correlation handle (SPEC-049 R-1). Injected by trusted
    # internal callers only — the agent-platform kernel forwards the
    # turn's session id and the execution worker forwards it from the
    # signed envelope — never taken from model-controlled ``parameters``.
    # It carries no authority (identity and policy still ride the bearer
    # token); the browser connector uses it to keep one stateful session
    # per chat across the owner→approver HITL identity switch.
    raw_session_id = body.get("session_id")
    chat_session_id = (
        raw_session_id if isinstance(raw_session_id, str) and raw_session_id
        else None
    )
    # SPEC-070: the in-flight tool-call id, forwarded by the agent-platform
    # kernel from CURRENT_CALL_ID (never a model parameter). It is a correlation
    # handle only — identity and policy still ride the bearer — so a produced
    # authorization challenge can be bound to the exact call that needs it. The
    # id is provider-generated, so it is syntactically bounded and an oversized
    # or non-string value is dropped rather than threaded into a challenge.
    raw_call_id = body.get("call_id")
    chat_call_id = (
        raw_call_id
        if isinstance(raw_call_id, str) and 0 < len(raw_call_id) <= 256
        else None
    )
    # Authority-provenance handle (SPEC-054 R-2 / ADR-0010). Like session_id
    # it is injected only by trusted internal callers — the execution worker
    # forwards it from the signed envelope, where it sits inside the HMAC —
    # never taken from model-controlled ``parameters``. It carries no authority
    # (identity and policy still ride the bearer token); the browser
    # connector's write path reads it solely to refuse a flow-provenance
    # execution when no flow is bound any more. Its only permitted effect is a
    # refusal, so a value outside the {flow, action} vocabulary is dropped and
    # can never widen access.
    raw_approval_kind = body.get("approval_kind")
    approval_kind = (
        raw_approval_kind if raw_approval_kind in ("flow", "action") else None
    )

    return await _dispatch_invocation(
        settings, registry, identity, tool_name, parameters,
        chat_session_id, approval_kind, correlation, request_id,
        chat_call_id=chat_call_id,
        # SPEC-070 R-2a: a read threads its DIRECTLY verified requester (never a
        # caller-supplied override) as the inert acquisition-seam binding. ``None``
        # when the runtime is disabled or the bearer is not a genuine delegated
        # human, so a delegated set then fails closed at the connector.
        delegated_requester=resolve_delegated_read_requester(settings, request),
        # SPEC-070 producer wiring: the authorization runtime (when provisioned)
        # upgrades a verified delegated re-authorization denial into a durable
        # challenge. ``None`` leaves the transitional denial untouched.
        challenge_producer=challenge_producer,
    )


async def _dispatch_invocation(
    settings: GatewaySettings,
    registry: ToolRegistry,
    identity: IdentityContext | None,
    tool_name: str,
    parameters: dict,
    chat_session_id: str | None,
    approval_kind: str | None,
    correlation: dict[str, str],
    request_id: str,
    *,
    chat_call_id: str | None = None,
    delegated_requester: tuple[str, str] | None = None,
    challenge_producer=None,
) -> "JSONResponse":
    """Policy check -> dispatch -> redaction -> audit for one resolved invocation.

    Shared by the public ``invoke_tool`` path and the SPEC-070 private delegated
    route so both enforce the identical invocation/mutation policy and audit the
    same way. ``delegated_requester`` — a verified, projection-matched
    ``(namespace, sub)`` — is threaded into connector identity as the inert
    target-acquisition seam binding; it carries no policy authority (identity and
    policy still ride the resolved ``identity``).
    """
    from fastapi.responses import JSONResponse

    # Policy enforcement.
    if identity is None:
        emit_audit_event(
            settings,
            build_audit_event(
                "policy_decision",
                request_id,
                "deny",
                details={
                    "action": "tools:invoke",
                    "decision": "deny",
                    "reason": "no identity context",
                    **correlation,
                },
            ),
        )
        result = make_denied_result(tool_name, "no identity context")
        return JSONResponse(content=result.to_dict(), status_code=403)

    decision = evaluate(settings, identity.roles, "tools:invoke")
    record_policy_decision("tools:invoke", decision.decision)

    if decision.decision == "deny":
        LOGGER.warning(
            "tool invocation denied by policy",
            extra={
                "request_id": request_id,
                "tool_name": tool_name,
                "subject": identity.subject,
                "roles": identity.roles,
                "reason": decision.reason,
            },
        )
        emit_audit_event(
            settings,
            build_audit_event(
                "policy_decision",
                request_id,
                "deny",
                subject=identity.subject,
                username=identity.username,
                actor=identity.actor,
                roles=identity.roles,
                details={
                    "action": "tools:invoke",
                    "decision": "deny",
                    "reason": decision.reason,
                    "matched_rule_ids": decision.matched_rule_ids,
                    **correlation,
                },
            ),
        )
        result = make_denied_result(tool_name, decision.reason)
        return JSONResponse(content=result.to_dict(), status_code=403)

    # Risk-tier gating (SPEC-021 R-1): mutating (write/admin) tools
    # additionally require tools:mutate; read tools are unaffected.
    target = registry.get(tool_name)
    if target is not None and target.definition.risk_level != "read":
        mutate_decision = evaluate(settings, identity.roles, "tools:mutate")
        record_policy_decision("tools:mutate", mutate_decision.decision)
        if mutate_decision.decision == "deny":
            LOGGER.warning(
                "mutating tool invocation denied by policy",
                extra={
                    "request_id": request_id,
                    "tool_name": tool_name,
                    "risk_level": target.definition.risk_level,
                    "subject": identity.subject,
                    "roles": identity.roles,
                    "reason": mutate_decision.reason,
                },
            )
            emit_audit_event(
                settings,
                build_audit_event(
                    "policy_decision",
                    request_id,
                    "deny",
                    subject=identity.subject,
                    username=identity.username,
                    actor=identity.actor,
                    roles=identity.roles,
                    details={
                        "action": "tools:mutate",
                        "decision": "deny",
                        "reason": mutate_decision.reason,
                        "tool_name": tool_name,
                        "risk_level": target.definition.risk_level,
                        "matched_rule_ids": mutate_decision.matched_rule_ids,
                        **correlation,
                    },
                ),
            )
            result = make_denied_result(
                tool_name, mutate_decision.reason, target.definition.risk_level
            )
            return JSONResponse(content=result.to_dict(), status_code=403)

    # Per-tool extra-action admission (SPEC-062 R-4): a tool may require a
    # capability-specific action *in addition to* its static risk-tier gate —
    # ``secrets.deliver`` declares ``("secrets:deliver",)``. Evaluated after the
    # tier check so the denial names the specific missing capability; the first
    # refusal wins, is audited, and returns the standard denied envelope. The
    # field defaults to ``()``, so every existing tool skips this loop entirely.
    if target is not None:
        for extra_action in target.definition.extra_required_actions:
            extra_decision = evaluate(settings, identity.roles, extra_action)
            record_policy_decision(extra_action, extra_decision.decision)
            if extra_decision.decision == "deny":
                LOGGER.warning(
                    "tool invocation denied by extra required action",
                    extra={
                        "request_id": request_id,
                        "tool_name": tool_name,
                        "action": extra_action,
                        "subject": identity.subject,
                        "roles": identity.roles,
                        "reason": extra_decision.reason,
                    },
                )
                emit_audit_event(
                    settings,
                    build_audit_event(
                        "policy_decision",
                        request_id,
                        "deny",
                        subject=identity.subject,
                        username=identity.username,
                        actor=identity.actor,
                        roles=identity.roles,
                        details={
                            "action": extra_action,
                            "decision": "deny",
                            "reason": extra_decision.reason,
                            "tool_name": tool_name,
                            "risk_level": target.definition.risk_level,
                            "matched_rule_ids": extra_decision.matched_rule_ids,
                            **correlation,
                        },
                    ),
                )
                result = make_denied_result(
                    tool_name,
                    extra_decision.reason,
                    target.definition.risk_level,
                )
                return JSONResponse(content=result.to_dict(), status_code=403)

    # Dispatch to registry. request_id rides along so connectors can
    # propagate correlation to downstream services (SPEC-029 R-3).
    identity_dict = {
        "sub": identity.subject,
        "username": identity.username,
        "roles": identity.roles,
        "request_id": request_id,
        "actor": identity.actor,
    }
    if chat_session_id is not None:
        identity_dict["chat_session_id"] = chat_session_id
    # SPEC-070: the in-flight tool-call id rides beside the session id so a
    # connector that must produce an authorization challenge can bind it to the
    # exact call. Correlation only — never a policy input.
    if chat_call_id is not None:
        identity_dict["chat_call_id"] = chat_call_id
    if approval_kind is not None:
        identity_dict["approval_kind"] = approval_kind
    # SPEC-070: the verified, projection-matched requester is bound for the
    # target-acquisition seam (an owner-scoped grant lookup downstream). It is
    # never a policy input — invocation/mutation authority rides ``identity``
    # (the approver on the delegated path). Inert until a connector reads it.
    if delegated_requester is not None:
        identity_dict["delegated_requester_namespace"] = delegated_requester[0]
        identity_dict["delegated_requester_sub"] = delegated_requester[1]
    # SPEC-070 R-4a/R-4c: establish a clean per-invocation baseline for the
    # derived delegation mode, then read it back from the acquisition seam
    # *before* redaction can replace the result. The ContextVar is per-task, so
    # concurrent invocations never cross-contaminate; reading it here (not from
    # ``result``) means the REDACTION_OVERFLOW envelope synthesized below cannot
    # drop it. A tool that never touches the seam leaves it ``None`` → omitted,
    # so its audit record stays byte-identical to before.
    _delegation_token = DELEGATION_MODE.set(None)
    result = await registry.invoke(tool_name, parameters, identity_dict)
    delegation_mode = DELEGATION_MODE.get()
    DELEGATION_MODE.reset(_delegation_token)

    # SPEC-069 R-4/R-5: name the target system and fold in any tool-declared
    # attribution. Both are read from the connector's OWN result, *before*
    # redaction can replace it: the fail-closed REDACTION_OVERFLOW envelope
    # below is synthesized by the gateway, so reading it afterwards would
    # attribute a withheld call to the target it never reached and drop the
    # connector's ``target_unavailable`` class. ``target_system`` mirrors the
    # ``source_system`` every result already carries in evidence (universal).
    # The attribution hook is opt-in and duck-typed — the Ansible connectors
    # declare a ``target_identity_mode`` (dev acting-service vs SPEC-070
    # user-delegated) and, on an unreachable target, a ``target_unavailable``
    # failure class distinct from a policy denial — so a tool that does not
    # declare it audits byte-identically to before.
    target_system = result.evidence.get("source_system")
    attribution = resolve_audit_attribution(target, result, tool_name, request_id)

    # Redaction (SPEC-009 R-1/R-2): applied at the single choke point before
    # both the response and the audit log. Fail-closed on overflow.
    redacted_spans = 0
    if settings.redaction_enabled:
        redacted, stats = redact_result(result)
        redacted_spans = stats.spans
        record_redacted_spans(tool_name, stats.spans)
        if stats.overflow(settings.redaction_overflow_fraction):
            LOGGER.warning(
                "tool output withheld: redaction overflow",
                extra={
                    "request_id": request_id,
                    "tool_name": tool_name,
                    "redacted_spans": stats.spans,
                    "redaction_fraction": round(
                        stats.redacted_chars / max(1, stats.original_chars), 3
                    ),
                },
            )
            # The withheld result keeps the connector's own risk tier and source
            # system: the envelope must not silently re-attribute the call to
            # the platform (SPEC-069 R-4).
            result = make_error_result(
                tool_name,
                "REDACTION_OVERFLOW",
                "tool output withheld: too much of the result appears to "
                "contain credentials; re-run with tighter parameters",
                risk_level=result.evidence.get("risk_level", "read"),
                source_system=result.evidence.get("source_system", "platform"),
                duration_ms=result.evidence.get("duration_ms", 0),
            )
        else:
            result = redacted

    # SPEC-070 producer wiring: upgrade a verified delegated re-authorization
    # denial to a durable challenge plus the reserved TARGET_AUTHORIZATION_REQUIRED
    # result the kernel promotes to a bounded stop. Runs after redaction (the
    # challenge metadata is already safe and must never be withheld) and before
    # the audit log (so the trail reflects the promoted result). A no-op unless
    # every producer gate holds — no producer, no verified owner, no correlation,
    # or a fail-closed producer all leave the original denial untouched.
    result = await _produce_authorization_challenge(
        result, identity_dict, challenge_producer
    )

    # Audit log.
    log_event(
        LOGGER,
        "tool_invoked",
        request_id=request_id,
        tool_name=tool_name,
        status=result.status,
        duration_ms=result.evidence.get("duration_ms", 0),
        risk_level=result.evidence.get("risk_level", "read"),
        target_system=target_system,
        user_id=identity.username,
        sub=identity.subject,
        act=identity.actor,
        redacted_spans=redacted_spans,
        **attribution,
        **correlation,
    )

    # Durable audit trail (SPEC-013 R-3): mirror the audit log, fire-and-forget.
    emit_audit_event(
        settings,
        build_audit_event(
            "tool_invoked",
            request_id,
            "success" if result.status == "success" else "error",
            subject=identity.subject,
            username=identity.username,
            actor=identity.actor,
            roles=identity.roles,
            # SPEC-070 R-4a/R-4c: the already-ratified top-level mode, derived
            # from the verified acquisition outcome (captured above, before
            # redaction). ``None`` → omitted, so a no-credential tool's record is
            # unchanged; a failed acquisition is ``none``, never a false success.
            delegation_mode=delegation_mode,
            details={
                "tool_name": tool_name,
                "status": result.status,
                "duration_ms": result.evidence.get("duration_ms", 0),
                "risk_level": result.evidence.get("risk_level", "read"),
                "target_system": target_system,
                "redacted_spans": redacted_spans,
                **attribution,
                **correlation,
            },
        ),
    )

    status_code = 200 if result.status == "success" else 400
    if result.status == "denied":
        status_code = 403
    return JSONResponse(content=result.to_dict(), status_code=status_code)


async def invoke_delegated(
    settings: GatewaySettings,
    registry: ToolRegistry,
    request: Request,
    request_id: str,
) -> "JSONResponse":
    """SPEC-070 private delegated execution route.

    Callable only by the exact execution-runtime workload identity. The worker
    forwards its verified execution projection plus the requester and approver
    bearers; tool-gateway independently re-verifies the humans and their equality
    to the projection, then applies the identical invocation/mutation policy
    under the *approver's* roles. The execution HMAC signing secret is never held
    here and workload authentication alone is never execution authority — the
    worker remains the single non-retrying dispatch owner.
    """
    from tool_gateway.services.delegated_invoke import (
        DelegatedInvokeError,
        authenticate_execution_workload,
        verify_delegated_invocation,
    )

    if not settings.delegated_invoke_enabled:
        raise HTTPException(status_code=403, detail="delegated execution not enabled")

    try:
        authenticate_execution_workload(settings, request)
        body = await request.json()
        projection, parameters, requester, decider = verify_delegated_invocation(
            settings, body
        )
    except DelegatedInvokeError as exc:
        LOGGER.warning(
            "delegated invocation refused",
            extra={"request_id": request_id, "reason": exc.detail},
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    tool_name = projection["tool_name"]
    raw_session_id = projection["session_id"]
    chat_session_id = (
        raw_session_id if isinstance(raw_session_id, str) and raw_session_id else None
    )
    raw_approval_kind = projection["approval_kind"]
    approval_kind = (
        raw_approval_kind if raw_approval_kind in ("flow", "action") else None
    )
    correlation = execution_correlation(projection.get("execution_id"))
    return await _dispatch_invocation(
        settings, registry, decider, tool_name, parameters,
        chat_session_id, approval_kind, correlation, request_id,
        delegated_requester=(
            projection["requester_namespace"], requester.subject
        ),
    )
