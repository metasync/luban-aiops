"""SPEC-070 OQ-7 target-authorization runtime routes (tool-gateway internal edge).

Six ``/api/v2/targets/authorizations`` endpoints drive the human-initiated
enrollment/renewal workflow. Two independent trust bars guard them:

- Owner-scoped human edges (start, status, cancel, browser-reset) require a
  genuine delegated-human bearer (``authenticate_authorization_human``) plus the
  ``targets:authorize`` policy. The owner is derived from the verified claims; the
  request never asserts one.
- Bearerless browser handoffs (provider-url, callback) require the exact
  platform-gateway projected service-account token
  (``authenticate_authorization_workload``, dedicated
  ``luban-target-authorization-handoff`` audience). Workload authentication alone
  is never authority: the owner and credential set are recovered from the stored
  transaction selected by an opaque single-use handle plus a browser proof.

Off by default (``GATEWAY_DELEGATED_AUTHORIZATION_ENABLED``); disabled fails
closed. Wrong-owner/unknown/expired collapse to a single 404 no-oracle, terminal
challenges to 409, and entitlement/policy gaps to 403. No bearer, code, state,
PKCE verifier, browser secret, or provider URL is ever logged — the request
middleware records method/path/status only — and every secret-bearing or
owner-scoped response is returned ``no-store``. SecretStr response fields are
unwrapped only at this serialization boundary, so they never reach a repr, a log
line, or an ordinary model dump.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from tool_gateway.core.config import GatewaySettings, get_settings
from tool_gateway.core.request_context import resolve_request_id
from tool_gateway.schemas.authorization import (
    AuthorizationCallbackRequest,
    AuthorizationStartRequest,
    BrowserResetRequest,
    ChallengeId,
    ProviderUrlRequest,
)
from tool_gateway.services.authorization_service import (
    AuthorizationError,
    authenticate_authorization_human,
    authenticate_authorization_workload,
)
from tool_gateway.services.gateway_service import enforce_policy

router = APIRouter(prefix="/api/v2/targets/authorizations", tags=["authorizations"])

# Authorization responses are secret-bearing or owner-scoped; never cache them and
# never let a provider URL/code leak through a referrer.
_NO_STORE = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
}


def _require_service(settings: GatewaySettings, request: Request):
    """Fail closed when the workflow is disabled or its runtime is absent."""
    if not settings.delegated_authorization_enabled:
        raise HTTPException(status_code=403, detail="target authorization not enabled")
    service = getattr(request.app.state, "authorization_service", None)
    if service is None:
        raise HTTPException(status_code=403, detail="target authorization unavailable")
    return service


def _request_id(request: Request, x_request_id: str | None) -> str:
    return getattr(request.state, "request_id", None) or resolve_request_id(x_request_id)


@router.post("/{challenge_id}/start")
async def start_authorization(
    challenge_id: ChallengeId,
    body: AuthorizationStartRequest,
    request: Request,
    x_request_id: str | None = Header(default=None),
    settings: GatewaySettings = Depends(get_settings),
) -> JSONResponse:
    """Mint a single-use start handle for an owned, pending, entitled challenge.

    Verified human bearer; the body carries only the initiating browser's fresh
    per-challenge cookie secret. Policy, the administered owner->target mapping,
    current invocation entitlement, and challenge ownership are all rechecked
    before a handle is issued.
    """
    service = _require_service(settings, request)
    request_id = _request_id(request, x_request_id)
    try:
        identity = authenticate_authorization_human(settings, request)
        enforce_policy(settings, identity, "targets:authorize", request_id)
        result = await service.start(settings, identity, challenge_id, body)
    except AuthorizationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return JSONResponse(
        status_code=200,
        content={
            "start_token": result.start_token.get_secret_value(),
            "expires_at": result.expires_at.isoformat(),
        },
        headers=_NO_STORE,
    )


@router.post("/provider-url")
async def provider_authorization_url(
    body: ProviderUrlRequest,
    request: Request,
    settings: GatewaySettings = Depends(get_settings),
) -> JSONResponse:
    """Consume the start handle with a browser proof; return the secret provider URL.

    Platform-gateway workload only. Bearerless navigation knows the single-use
    start token (not a trustworthy owner) and re-presents its whole cookie jar; the
    owner and set are recovered from the stored transaction, so a repeated
    navigation cannot obtain another URL.
    """
    service = _require_service(settings, request)
    try:
        authenticate_authorization_workload(settings, request)
        result = await service.provider_url(body)
    except AuthorizationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return JSONResponse(
        status_code=200,
        content={
            "provider_url": result.provider_url.get_secret_value(),
            "expires_at": result.expires_at.isoformat(),
        },
        headers=_NO_STORE,
    )


@router.post("/callback")
async def authorization_callback(
    body: AuthorizationCallbackRequest,
    request: Request,
    settings: GatewaySettings = Depends(get_settings),
) -> JSONResponse:
    """Resolve a browser-verified provider callback; dispatches no tool.

    Platform-gateway workload only. The discriminated body carries the state, the
    cookie jar, and either a code or a normalized denial — never the provider's
    ``error_description`` free text. The stored state selects the owner and set.
    """
    service = _require_service(settings, request)
    try:
        authenticate_authorization_workload(settings, request)
        result = await service.callback(body)
    except AuthorizationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return JSONResponse(
        status_code=200,
        content=result.model_dump(mode="json", exclude_none=True),
        headers=_NO_STORE,
    )


@router.post("/browser-reset")
async def browser_reset(
    body: BrowserResetRequest,
    request: Request,
    x_request_id: str | None = Header(default=None),
    settings: GatewaySettings = Depends(get_settings),
) -> JSONResponse:
    """Portal-logout cleanup: cancel this owner's matching pending browser work.

    Verified human bearer plus matching cookie proofs. Bounded cleanup only — it
    never revokes a target credential, creates a login session, or accepts a
    caller-asserted owner.
    """
    service = _require_service(settings, request)
    request_id = _request_id(request, x_request_id)
    try:
        identity = authenticate_authorization_human(settings, request)
        enforce_policy(settings, identity, "targets:authorize", request_id)
        canceled = await service.browser_reset(settings, identity, body)
    except AuthorizationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return JSONResponse(status_code=200, content={"canceled": canceled}, headers=_NO_STORE)


@router.get("/{challenge_id}")
async def authorization_status(
    challenge_id: ChallengeId,
    request: Request,
    x_request_id: str | None = Header(default=None),
    settings: GatewaySettings = Depends(get_settings),
) -> JSONResponse:
    """Non-destructive owner-scoped status projection; wrong-owner/unknown → 404."""
    service = _require_service(settings, request)
    request_id = _request_id(request, x_request_id)
    try:
        identity = authenticate_authorization_human(settings, request)
        enforce_policy(settings, identity, "targets:authorize", request_id)
        result = await service.status(settings, identity, challenge_id)
    except AuthorizationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return JSONResponse(status_code=200, content=result.model_dump(mode="json"), headers=_NO_STORE)


@router.post("/{challenge_id}/cancel")
async def cancel_authorization(
    challenge_id: ChallengeId,
    request: Request,
    x_request_id: str | None = Header(default=None),
    settings: GatewaySettings = Depends(get_settings),
) -> Response:
    """Idempotent, no-oracle cancellation: found/spent/expired/wrong-owner all → 204.

    Burns the pending transaction and verifier but never revokes an installed
    credential; cancellation leaves existing approvals and executions unchanged.
    """
    service = _require_service(settings, request)
    request_id = _request_id(request, x_request_id)
    try:
        identity = authenticate_authorization_human(settings, request)
        enforce_policy(settings, identity, "targets:authorize", request_id)
        await service.cancel(settings, identity, challenge_id)
    except AuthorizationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    return Response(status_code=204, headers=_NO_STORE)
