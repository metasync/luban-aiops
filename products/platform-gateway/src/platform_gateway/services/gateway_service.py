from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

import httpx
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import StreamingResponse

from platform_gateway.core.config import PlatformGatewaySettings
from platform_gateway.core.metrics import (
    record_policy_decision,
    record_token_verification,
)
from platform_gateway.metadata import SERVICE_NAME, SERVICE_VERSION
from platform_gateway.schemas.api import IdentityContext
from platform_gateway.services import agent_client
from platform_gateway.services.audit_emitter import build_audit_event, emit_audit_event
from platform_gateway.services.policy_engine import (
    PolicyDecision,
    PolicyLoadError,
    evaluate,
    load_bundle,
)
from platform_gateway.services.token_verifier import TokenVerificationError, verify_token

LOGGER = logging.getLogger(__name__)


def _service_headers(request_id: str) -> dict[str, str]:
    return {"x-request-id": request_id}


def live_status(settings: PlatformGatewaySettings) -> dict[str, str]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
    }


async def ready_status(settings: PlatformGatewaySettings) -> dict[str, object]:
    """Readiness: the policy bundle must load and the agent service must respond."""
    try:
        rules = load_bundle(settings)
        agent_health = await agent_client.health(settings)
        return {
            "status": "ok",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "agent_service": agent_health,
            "policy_rules": len(rules),
        }
    except httpx.HTTPError as exc:
        return {
            "status": "degraded",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "agent_service_error": str(exc),
        }
    except PolicyLoadError as exc:
        return {
            "status": "degraded",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "policy_error": str(exc),
        }


async def runtime_status(settings: PlatformGatewaySettings) -> dict[str, object]:
    return await agent_client.runtime_metadata(settings)


async def fetch_login_url(settings: PlatformGatewaySettings, request_id: str) -> dict:
    headers = _service_headers(request_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{settings.identity_service_url}/api/v1/auth/login-url",
            headers=headers,
        )
    response.raise_for_status()
    return response.json()


async def start_login(settings: PlatformGatewaySettings, request_id: str) -> dict:
    headers = _service_headers(request_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{settings.identity_service_url}/api/v1/auth/login",
            headers=headers,
        )
    response.raise_for_status()
    return response.json()


async def complete_login(
    settings: PlatformGatewaySettings,
    request_id: str,
    payload: dict,
) -> dict:
    headers = _service_headers(request_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{settings.identity_service_url}/api/v1/auth/callback",
            json=payload,
            headers=headers,
        )
    response.raise_for_status()
    return response.json()


async def build_logout_url(
    settings: PlatformGatewaySettings,
    request_id: str,
    payload: dict,
) -> dict:
    headers = _service_headers(request_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{settings.identity_service_url}/api/v1/auth/logout-url",
            json=payload,
            headers=headers,
        )
    response.raise_for_status()
    return response.json()


async def refresh_token(
    settings: PlatformGatewaySettings,
    request_id: str,
    payload: dict,
) -> dict:
    headers = _service_headers(request_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{settings.identity_service_url}/api/v1/auth/refresh",
            json=payload,
            headers=headers,
        )
    response.raise_for_status()
    return response.json()


async def normalize_identity(
    settings: PlatformGatewaySettings,
    request: Request,
    request_id: str,
) -> dict:
    headers = _service_headers(request_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{settings.identity_service_url}/api/v1/identity/normalize",
            json=await request.json(),
            headers=headers,
        )
    response.raise_for_status()
    return response.json()


async def resolve_request_identity(
    settings: PlatformGatewaySettings,
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
    settings: PlatformGatewaySettings,
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
        _emit_policy_decision(settings, identity, action, request_id, decision)
        raise HTTPException(
            status_code=403,
            detail={
                "detail": "action denied by policy",
                "action": action,
                "reason": decision.reason,
            },
        )
    LOGGER.info("policy decision", extra=log_extra)
    _emit_policy_decision(settings, identity, action, request_id, decision)


def _emit_policy_decision(
    settings: PlatformGatewaySettings,
    identity: IdentityContext,
    action: str,
    request_id: str,
    decision: PolicyDecision,
) -> None:
    """Mirror every policy decision to the durable audit trail (SPEC-013 R-3)."""
    emit_audit_event(
        settings,
        build_audit_event(
            "policy_decision",
            request_id,
            decision.decision,
            subject=identity.subject,
            username=identity.username,
            actor=identity.actor,
            roles=identity.roles,
            details={
                "action": action,
                "decision": decision.decision,
                "reason": decision.reason,
                "matched_rule_ids": decision.matched_rule_ids,
            },
        ),
    )


async def create_session(
    settings: PlatformGatewaySettings,
    request_id: str,
    user_id: str,
) -> dict:
    return await agent_client.create_session(settings, request_id, user_id)


async def get_session(
    settings: PlatformGatewaySettings,
    request_id: str,
    session_id: str,
    user_id: str,
) -> dict:
    """Proxy a session detail fetch (SPEC-022 R-1).

    Upstream 4xx (unknown/foreign session) passes through unchanged so
    the anti-enumeration 404 reaches the caller; transport failures and
    upstream 5xx map to 502 — the same posture as the delete proxy.
    """
    try:
        return await agent_client.get_session(
            settings, request_id, session_id, user_id
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if 400 <= status < 500:
            raise HTTPException(
                status_code=status,
                detail="agent service rejected the session fetch",
            ) from exc
        raise HTTPException(
            status_code=502, detail="agent service session fetch failed"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="agent service unavailable"
        ) from exc


async def list_sessions(
    settings: PlatformGatewaySettings,
    request_id: str,
    user_id: str,
) -> dict:
    """Proxy the caller's workspace session list (SPEC-022 R-1).


    Same posture as the get/delete proxies: upstream 4xx passes through
    unchanged; transport failures and upstream 5xx map to 502.
    """
    try:
        return await agent_client.list_sessions(settings, request_id, user_id)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if 400 <= status < 500:
            raise HTTPException(
                status_code=status,
                detail="agent service rejected the session list",
            ) from exc
        raise HTTPException(
            status_code=502, detail="agent service session list failed"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="agent service unavailable"
        ) from exc


async def approvals_inbox(
    settings: PlatformGatewaySettings,
    request_id: str,
    user_id: str,
    history_limit: int = 10,
    history_offset: int = 0,
) -> dict:
    """Proxy the approver's cross-session confirmation inbox (SPEC-031 R-3).

    Same posture as the session-list proxy: upstream 4xx passes through
    unchanged; transport failures and upstream 5xx map to 502 so an
    outage can never masquerade as an empty inbox. SPEC-036 R-4: the
    history pagination params forward verbatim.
    """
    try:
        return await agent_client.fetch_approvals_inbox(
            settings, request_id, user_id, history_limit, history_offset
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if 400 <= status < 500:
            raise HTTPException(
                status_code=status,
                detail="agent service rejected the approvals inbox",
            ) from exc
        raise HTTPException(
            status_code=502, detail="agent service approvals inbox failed"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="agent service unavailable"
        ) from exc


async def list_models(
    settings: PlatformGatewaySettings,
    request_id: str,
    user_id: str,
) -> dict:
    """Proxy model catalog discovery (SPEC-024 R-2).

    Same posture as the session-list proxy: upstream 4xx passes through
    unchanged; transport failures and upstream 5xx map to 502.
    """
    try:
        return await agent_client.list_models(settings, request_id, user_id)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if 400 <= status < 500:
            raise HTTPException(
                status_code=status,
                detail="agent service rejected the model list",
            ) from exc
        raise HTTPException(
            status_code=502, detail="agent service model list failed"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="agent service unavailable"
        ) from exc


async def delete_session(
    settings: PlatformGatewaySettings,
    request_id: str,
    session_id: str,
    user_id: str,
) -> dict:
    """Proxy an owner-only session delete (SPEC-022 R-1).

    Upstream 4xx (unknown/foreign session, parked confirmation) passes
    through unchanged; transport failures and upstream 5xx map to 502 —
    the same posture as the confirm proxy.
    """
    try:
        return await agent_client.delete_session(
            settings, request_id, session_id, user_id
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if 400 <= status < 500:
            raise HTTPException(
                status_code=status,
                detail="agent service rejected the session delete",
            ) from exc
        raise HTTPException(
            status_code=502, detail="agent service session delete failed"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="agent service unavailable"
        ) from exc


async def chat(
    settings: PlatformGatewaySettings,
    request_id: str,
    user_id: str,
    message: str,
    session_id: str | None,
    delegated_token: str | None = None,
    input_modality: str = "text",
    model: str | None = None,
) -> dict:
    return await agent_client.chat(
        settings,
        request_id,
        user_id,
        message,
        session_id,
        delegated_token,
        input_modality,
        model,
    )


async def chat_stream(
    settings: PlatformGatewaySettings,
    request_id: str,
    identity: IdentityContext,
    message: str,
    session_id: str | None,
    delegated_token: str | None = None,
    input_modality: str = "text",
    model: str | None = None,
) -> StreamingResponse:
    """Proxy the chat stream to agent-service.

    The upstream status is checked before the SSE response opens: 4xx
    (unknown session, parked conflict, unknown model) passes through
    unchanged and transport failures or upstream 5xx map to 502, so
    failures surface as HTTP statuses instead of a 200 with an empty
    stream. The tee audits ``chat_completed`` — enriched with the serving
    model from the ``message_end`` frame — only once the turn actually
    completes (SPEC-024 R-4).
    """
    try:
        upstream = await agent_client.open_chat_stream(
            settings,
            request_id,
            identity.username,
            message,
            session_id,
            delegated_token,
            input_modality,
            model,
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if 400 <= status < 500:
            raise HTTPException(
                status_code=status,
                detail="agent service rejected the chat stream",
            ) from exc
        raise HTTPException(
            status_code=502, detail="agent service chat stream failed"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="agent service unavailable"
        ) from exc

    audited = False
    saw_delta = False
    parked = False
    last_frame_session: str | None = None

    async def _stream() -> AsyncIterator[str]:
        nonlocal audited, saw_delta, parked, last_frame_session
        async for chunk in upstream:
            if not audited:
                frame = _extract_message_end(chunk)
                if frame is not None:
                    audited = True
                    _emit_stream_chat_completed(
                        settings, request_id, identity,
                        session_id, input_modality, frame,
                    )
            kind = _frame_type(chunk)
            if kind == "message_delta":
                saw_delta = True
            elif kind == "confirmation_request":
                parked = True
            frame_session = _frame_session_id(chunk)
            if frame_session is not None:
                last_frame_session = frame_session
            yield chunk
        # Normal stream end without a message_end frame (the kernel may
        # close right after the last delta, legacy parity): a turn that
        # produced text still completed, so attribute it with the
        # requested model — resolution is request > pinned > default and
        # unknown ids already failed closed before the stream opened.
        # Parked turns (confirmation_request, no completion yet) and
        # empty streams stay unattributed (SPEC-024 R-4).
        if not audited and saw_delta and not parked:
            _emit_stream_chat_completed(
                settings, request_id, identity,
                last_frame_session or session_id, input_modality, None,
                fallback_model=model,
            )

    return StreamingResponse(_stream(), media_type="text/event-stream")


async def chat_confirm(
    settings: PlatformGatewaySettings,
    request_id: str,
    identity: IdentityContext,
    session_id: str,
    confirm_id: str,
    decision: str,
    delegated_token: str | None = None,
) -> StreamingResponse:
    """Proxy a parked-confirmation decision to agent-service (SPEC-020 R-3).

    SPEC-030 R-3: before proxying, the bridge evaluates the parked
    batch's policy action against the bundle and enforces the matched
    approval tier (decider role, self-approval); blocked attempts get a
    structured 403, are audited, and leave the parked call parked.
    Upstream 4xx (unknown/expired confirmation, parked session) passes
    through unchanged; transport failures and upstream 5xx map to 502.
    The ``confirmation_decided`` audit event is emitted when the matching
    ``confirmation_result`` frame flows through, so only decisions the
    kernel actually applied reach the durable trail.
    """
    try:
        parked = await agent_client.fetch_pending_confirmation(
            settings, request_id, identity.username, session_id
        )
    except httpx.HTTPError as exc:
        # Fail closed: without the parked state the tier cannot be
        # checked, and bypassing enforcement would run a mutating batch
        # under a weaker guarantee than the bundle promises.
        raise HTTPException(
            status_code=502, detail="approval check unavailable"
        ) from exc
    approval_context = _enforce_approval_tier(
        settings, request_id, identity, session_id, confirm_id,
        decision, parked,
    )
    try:
        upstream = await agent_client.open_chat_confirm_stream(
            settings,
            request_id,
            identity.username,
            session_id,
            confirm_id,
            decision,
            delegated_token,
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if 400 <= status < 500:
            # Pass client errors through unchanged (unknown/expired
            # confirmation, parked session) so operators can tell them
            # apart from an upstream outage. SPEC-031 R-4: a structured
            # upstream body (e.g. already_resolved with the decider and
            # outcome) rides through untouched so the portal can render
            # the resolution instead of an opaque error.
            raise HTTPException(
                status_code=status,
                detail=_upstream_error_detail(
                    exc.response, "agent service rejected the confirmation"
                ),
            ) from exc
        raise HTTPException(
            status_code=502, detail="agent service confirm failed"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="agent service unavailable"
        ) from exc

    audited = False

    async def _stream() -> AsyncIterator[str]:
        nonlocal audited
        async for chunk in upstream:
            if not audited:
                frame = _extract_confirmation_result(chunk)
                if frame is not None:
                    audited = True
                    _emit_confirmation_decided(
                        settings, request_id, identity,
                        session_id, confirm_id, decision, frame,
                        approval_context,
                    )
            yield chunk

    return StreamingResponse(_stream(), media_type="text/event-stream")


def _upstream_error_detail(response: httpx.Response, fallback: str) -> object:
    """Preserve a structured upstream error body on passthrough (SPEC-031 R-4).

    The agent-service already_resolved response carries the decider and
    outcome in its ``detail``; relaying it keeps the race observable.
    Anything unparsable degrades to the fallback string.
    """
    try:
        body = response.json()
    except ValueError:
        return fallback
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, (str, dict, list)):
        return detail
    return fallback


def _enforce_approval_tier(
    settings: PlatformGatewaySettings,
    request_id: str,
    identity: IdentityContext,
    session_id: str,
    confirm_id: str,
    decision: str,
    parked: dict | None,
) -> dict | None:
    """Enforce the matched approval tier before proxying (SPEC-030 R-3).

    Evaluates the parked batch's bridged action against the bundle. On
    ``require_approval`` an approve needs a designated decider role, and
    the requester cannot approve their own call when the effective
    self-approval rule is false (the tier_2 default); the decider check
    applies to approvals only, so any ``chat:confirm`` holder may still
    deny a parked call to cancel it. Blocked attempts are audited and
    answered with a structured 403; the parked call stays parked.
    Returns the matched approval context (rule id + tier) so the decided
    audit tee can enrich it, or ``None`` when the batch carries no
    approval requirement (no parked state, no bridged action, or an
    allow/deny evaluation).
    """
    if parked is None or decision != "approve":
        return None
    action = parked.get("action")
    if not isinstance(action, str) or not action:
        return None
    result = evaluate(settings, identity.roles, action)
    if result.decision != "require_approval" or result.approval is None:
        return None
    approval = result.approval
    context = {
        "approval_rule_id": (
            result.matched_rule_ids[0] if result.matched_rule_ids else None
        ),
        "approval_tier": approval.tier,
    }
    roles = identity.roles or []
    if not set(roles) & set(approval.decided_by_roles):
        _emit_confirmation_blocked(
            settings, request_id, identity, session_id, confirm_id,
            "not_a_designated_approver", context,
        )
        raise HTTPException(
            status_code=403,
            detail={
                "action": action,
                "reason": "not_a_designated_approver",
                "requirement": "require_approval",
                "approval_tier": approval.tier,
            },
        )
    # agent-platform parks the requester's username (its X-User-ID), so
    # the self-approval comparison runs on usernames, not subjects.
    owner_user_id = parked.get("owner_user_id")
    if (
        not approval.effective_self_approval()
        and identity.username
        and owner_user_id == identity.username
    ):
        _emit_confirmation_blocked(
            settings, request_id, identity, session_id, confirm_id,
            "self_approval", context,
        )
        raise HTTPException(
            status_code=403,
            detail={
                "action": action,
                "reason": "self_approval",
                "requirement": "require_approval",
                "approval_tier": approval.tier,
            },
        )
    return context


def _emit_confirmation_blocked(
    settings: PlatformGatewaySettings,
    request_id: str,
    identity: IdentityContext,
    session_id: str,
    confirm_id: str,
    reason: str,
    approval_context: dict,
) -> None:
    """Audit a tier-blocked approval attempt (SPEC-030 R-3/R-5).

    The parked call stays parked (nothing was decided), so the blocked
    attempt rides the same ``confirmation_decided`` event type with a
    deny outcome and the block reason in details.
    """
    emit_audit_event(
        settings,
        build_audit_event(
            "confirmation_decided",
            request_id,
            "deny",
            subject=identity.subject,
            username=identity.username,
            actor=identity.actor,
            roles=identity.roles,
            session_id=session_id,
            details={
                "session_id": session_id,
                "confirm_id": confirm_id,
                "decision": "approve",
                "blocked": True,
                "blocked_reason": reason,
                "approval_rule_id": approval_context.get("approval_rule_id"),
                "approval_tier": approval_context.get("approval_tier"),
            },
        ),
    )


def _extract_confirmation_result(chunk: str) -> dict | None:
    """Parse an SSE chunk into a confirmation_result frame, or None."""
    if not chunk.startswith("data: "):
        return None
    try:
        frame = json.loads(chunk.removeprefix("data: ").strip())
    except ValueError:
        return None
    if isinstance(frame, dict) and frame.get("type") == "confirmation_result":
        return frame
    return None


def _extract_message_end(chunk: str) -> dict | None:
    """Parse an SSE chunk into a message_end frame, or None (SPEC-024 R-4)."""
    if not chunk.startswith("data: "):
        return None
    try:
        frame = json.loads(chunk.removeprefix("data: ").strip())
    except ValueError:
        return None
    if isinstance(frame, dict) and frame.get("type") == "message_end":
        return frame
    return None


def _frame_type(chunk: str) -> str | None:
    """Best-effort frame type of an SSE chunk (SPEC-024 R-4 fallback gate)."""
    if not chunk.startswith("data: "):
        return None
    try:
        frame = json.loads(chunk.removeprefix("data: ").strip())
    except ValueError:
        return None
    if isinstance(frame, dict):
        kind = frame.get("type")
        return kind if isinstance(kind, str) else None
    return None


def _frame_session_id(chunk: str) -> str | None:
    """Best-effort session id of an SSE chunk (SPEC-024 R-4 attribution)."""
    if not chunk.startswith("data: "):
        return None
    try:
        frame = json.loads(chunk.removeprefix("data: ").strip())
    except ValueError:
        return None
    if isinstance(frame, dict):
        sid = frame.get("session_id")
        return str(sid) if isinstance(sid, str) and sid else None
    return None


def _emit_stream_chat_completed(
    settings: PlatformGatewaySettings,
    request_id: str,
    identity: IdentityContext,
    session_id: str | None,
    input_modality: str,
    frame: dict | None,
    fallback_model: str | None = None,
) -> None:
    """Audit the completed streamed turn with its serving model (SPEC-024 R-4).

    Emitted from the tee when the ``message_end`` frame flows through; a
    stream that closes without one (known kernel edge) still completes the
    turn, so the requested model rides as the fallback attribution.
    """
    frame = frame or {}
    serving_model = frame.get("model")
    if not isinstance(serving_model, str):
        serving_model = fallback_model
    emit_audit_event(
        settings,
        build_audit_event(
            "chat_completed",
            request_id,
            "success",
            details={
                "input_modality": input_modality,
                "model": (
                    serving_model if isinstance(serving_model, str) else None
                ),
            },
            subject=identity.subject,
            username=identity.username,
            actor=identity.actor,
            roles=identity.roles,
            session_id=str(frame.get("session_id") or session_id or ""),
        ),
    )


def _emit_confirmation_decided(
    settings: PlatformGatewaySettings,
    request_id: str,
    identity: IdentityContext,
    session_id: str,
    confirm_id: str,
    decision: str,
    frame: dict,
    approval_context: dict | None = None,
) -> None:
    """Record the applied decision in the durable audit trail (SPEC-020 R-3).

    SPEC-030 R-5: when the batch matched a ``require_approval`` rule,
    the matched rule id and tier enrich the event (empty for
    non-approval confirmations).
    """
    tool_names = [
        str(call.get("tool_name") or "")
        for call in frame.get("pending_calls") or []
        if isinstance(call, dict)
    ]
    details: dict = {
        "session_id": session_id,
        "confirm_id": confirm_id,
        "decision": decision,
        "tool_names": tool_names,
    }
    if approval_context:
        details["approval_rule_id"] = approval_context.get("approval_rule_id")
        details["approval_tier"] = approval_context.get("approval_tier")
    emit_audit_event(
        settings,
        build_audit_event(
            "confirmation_decided",
            request_id,
            "allow" if decision == "approve" else "deny",
            subject=identity.subject,
            username=identity.username,
            actor=identity.actor,
            roles=identity.roles,
            session_id=session_id,
            details=details,
        ),
    )
