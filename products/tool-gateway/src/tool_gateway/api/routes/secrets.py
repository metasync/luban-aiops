"""One-time secret-delivery redemption route (SPEC-062 R-3).

``GET /api/v2/secrets/delivery/{delivery_id}`` releases a stashed generated
value exactly once, to the identity that generated it. This is the *only* place
the value leaves the tool-gateway process after generation: it rides no stream
frame, no render tree, no log line and no durable transcript. The portal's
Copy-password control performs this authenticated single-use fetch and writes the
response to the clipboard.

The endpoint deliberately exposes a single "unavailable" posture for
not-found / already-spent / expired / wrong-owner: distinguishing them would be
an oracle over the handle space. ``delivery_id`` is an unguessable ``uuid4`` and
the buffer is owner-scoped, so the posture leaks nothing.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from tool_gateway.core.config import GatewaySettings, get_settings
from tool_gateway.core.request_context import resolve_request_id
from tool_gateway.services.audit_emitter import build_audit_event, emit_audit_event
from tool_gateway.services.gateway_service import resolve_request_identity

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/secrets", tags=["secrets"])


# The single "unavailable" body — never distinguished by cause (no oracle).
def _unavailable() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        content={
            "detail": "This delivery is no longer available. It may have already "
            "been retrieved, expired, or been issued to a different session."
        },
    )


@router.get("/delivery/{delivery_id}")
async def redeem_delivery(
    delivery_id: str,
    request: Request,
    x_request_id: str | None = Header(default=None),
    settings: GatewaySettings = Depends(get_settings),
) -> JSONResponse:
    """Redeem a stashed secret once, for the identity that generated it."""
    request_id = resolve_request_id(x_request_id)
    identity = await resolve_request_identity(replace(settings, require_auth=True), request, request_id)
    try:
        if str(UUID(delivery_id)) != delivery_id:
            return _unavailable()
    except ValueError:
        return _unavailable()

    buffer = getattr(request.app.state, "secret_delivery_buffer", None)
    if buffer is None or identity is None or not identity.subject:
        return _unavailable()

    # Single-use, owner-scoped, TTL-bounded: a wrong identity (including an
    # approver) cannot redeem, and the value is gone after this call regardless.
    try:
        value = buffer.redeem(delivery_id, identity.subject)
    except Exception:
        return _unavailable()
    if value is None:
        return _unavailable()

    # The value reached a human: fire ``secret_delivered`` (portal_copy). The
    # event carries the delivery metadata and the recipient, never the value.
    emit_audit_event(
        settings,
        build_audit_event(
            "secret_delivered",
            request_id,
            "success",
            subject=identity.subject,
            username=identity.username,
            actor=identity.actor,
            roles=identity.roles,
            details={
                "delivery_id": delivery_id,
                "channel": "portal_copy",
                "recipient": identity.username,
            },
        ),
    )
    LOGGER.info(
        "secret delivery redeemed",
        extra={
            "request_id": request_id,
            "channel": "portal_copy",
            "sub": identity.subject,
        },
    )
    # The value is returned only on this one-time authenticated call. The
    # response body is never logged (the request middleware records method,
    # path and status only).
    return JSONResponse(
        status_code=200, content={"value": value},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
