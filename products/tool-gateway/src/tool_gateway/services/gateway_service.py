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
from tool_gateway.metadata import SERVICE_NAME, SERVICE_VERSION
from tool_gateway.schemas.api import IdentityContext
from tool_gateway.services.audit_emitter import build_audit_event, emit_audit_event
from tool_gateway.services.policy_engine import (
    PolicyLoadError,
    evaluate,
    load_bundle,
)
from tool_gateway.services.token_verifier import TokenVerificationError, verify_token
from tool_gateway.tools.base import make_denied_result, make_error_result
from tool_gateway.tools.redaction import redact_result
from tool_gateway.tools.registry import ToolRegistry

LOGGER = logging.getLogger(__name__)


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
) -> None:
    """Evaluate the action against the policy bundle; raise 403 on deny (R-3/R-4).

    Verified and synthetic identities take the identical path — the developer
    role is granted access by policy, never by bypass.
    """
    decision = evaluate(settings, identity.roles, action)
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


async def invoke_tool(
    settings: GatewaySettings,
    registry: ToolRegistry,
    request: Request,
    identity: IdentityContext | None,
    request_id: str,
) -> "JSONResponse":
    """Orchestrate tool invocation: policy check -> dispatch -> audit log."""
    from fastapi.responses import JSONResponse

    body = await request.json()
    tool_name = body.get("tool_name", "")
    parameters = body.get("parameters", {})

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
                    },
                ),
            )
            result = make_denied_result(
                tool_name, mutate_decision.reason, target.definition.risk_level
            )
            return JSONResponse(content=result.to_dict(), status_code=403)

    # Dispatch to registry. request_id rides along so connectors can
    # propagate correlation to downstream services (SPEC-029 R-3).
    identity_dict = {
        "sub": identity.subject,
        "username": identity.username,
        "roles": identity.roles,
        "request_id": request_id,
    }
    result = await registry.invoke(tool_name, parameters, identity_dict)

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
            result = make_error_result(
                tool_name,
                "REDACTION_OVERFLOW",
                "tool output withheld: too much of the result appears to "
                "contain credentials; re-run with tighter parameters",
                duration_ms=result.evidence.get("duration_ms", 0),
            )
        else:
            result = redacted

    # Audit log.
    log_event(
        LOGGER,
        "tool_invoked",
        request_id=request_id,
        tool_name=tool_name,
        status=result.status,
        duration_ms=result.evidence.get("duration_ms", 0),
        risk_level=result.evidence.get("risk_level", "read"),
        user_id=identity.username,
        sub=identity.subject,
        act=identity.actor,
        redacted_spans=redacted_spans,
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
            details={
                "tool_name": tool_name,
                "status": result.status,
                "duration_ms": result.evidence.get("duration_ms", 0),
                "risk_level": result.evidence.get("risk_level", "read"),
                "redacted_spans": redacted_spans,
            },
        ),
    )

    status_code = 200 if result.status == "success" else 400
    if result.status == "denied":
        status_code = 403
    return JSONResponse(content=result.to_dict(), status_code=status_code)
