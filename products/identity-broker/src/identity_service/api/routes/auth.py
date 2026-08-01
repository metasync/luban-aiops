import httpx
import logging

from fastapi import APIRouter, Depends, Header, HTTPException

from identity_service.core.config import IdentitySettings, get_settings
from identity_service.core.observability import log_event
from identity_service.schemas.auth import (
    AuthenticatedSession,
    AuthorizationCodeExchangeRequest,
    LoginStartResponse,
    LogoutRequest,
    LogoutResponse,
    TokenExchangeRequest,
    TokenExchangeResponse,
    TokenRefreshRequest,
    TokenRequest,
    TokenResponse,
)
from identity_service.services.exchange_service import ExchangeError, exchange_token
from identity_service.services.identity_service import (
    build_login_start,
    build_logout_response,
    exchange_authorization_code,
    refresh_session,
)
from identity_service.services.token_service import issue_token, jwks_response

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.get("/api/v1/auth/login-url")
def login_url(
    x_request_id: str | None = Header(default=None),
    settings: IdentitySettings = Depends(get_settings),
) -> dict[str, str]:
    payload = build_login_start(settings)
    log_event(LOGGER, "auth_login_url_requested", request_id=x_request_id)
    return {"login_url": payload.authorization_url}


@router.get("/api/v1/auth/login", response_model=LoginStartResponse)
def login_start(
    x_request_id: str | None = Header(default=None),
    settings: IdentitySettings = Depends(get_settings),
) -> LoginStartResponse:
    payload = build_login_start(settings)
    log_event(LOGGER, "auth_login_started", request_id=x_request_id)
    return payload


@router.post("/api/v1/auth/callback", response_model=AuthenticatedSession)
async def auth_callback(
    payload: AuthorizationCodeExchangeRequest,
    x_request_id: str | None = Header(default=None),
    settings: IdentitySettings = Depends(get_settings),
) -> AuthenticatedSession:
    try:
        response = await exchange_authorization_code(settings, payload)
        log_event(
            LOGGER,
            "auth_login_completed",
            request_id=x_request_id,
            user_id=response.identity.username,
        )
        return response
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="oidc token exchange failed") from exc


@router.post("/api/v1/auth/logout-url", response_model=LogoutResponse)
def logout_url(
    payload: LogoutRequest,
    x_request_id: str | None = Header(default=None),
    settings: IdentitySettings = Depends(get_settings),
) -> LogoutResponse:
    response = build_logout_response(settings, payload)
    log_event(LOGGER, "auth_logout_requested", request_id=x_request_id)
    return response


@router.post("/api/v1/auth/token", response_model=TokenResponse)
def issue_platform_token(
    payload: TokenRequest,
    x_request_id: str | None = Header(default=None),
    settings: IdentitySettings = Depends(get_settings),
) -> TokenResponse:
    identity = {
        "sub": payload.username,
        "username": payload.username,
        "email": payload.email,
        "roles": payload.roles or ["developer"],
        "groups": payload.groups or [],
    }
    token, expires_in = issue_token(settings, identity)
    log_event(
        LOGGER,
        "platform_token_issued",
        request_id=x_request_id,
        user_id=payload.username,
    )
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/.well-known/jwks.json")
def jwks_endpoint(
    settings: IdentitySettings = Depends(get_settings),
) -> dict:
    return jwks_response(settings)


@router.post("/api/v1/auth/exchange", response_model=TokenExchangeResponse)
def exchange_delegated_token(
    payload: TokenExchangeRequest,
    authorization: str | None = Header(default=None),
    x_request_id: str | None = Header(default=None),
    settings: IdentitySettings = Depends(get_settings),
) -> TokenExchangeResponse:
    """Exchange a verified subject token for a short-lived delegated token (R-2).

    The service credential is presented via HTTP Basic (``client_id:secret``)
    in the ``Authorization`` header (R-3).
    """
    client_id, client_secret = _parse_basic_credential(authorization)
    try:
        token, expires_in = exchange_token(
            settings,
            client_id,
            client_secret,
            payload.subject_token,
            payload.audience,
        )
    except ExchangeError as exc:
        log_event(
            LOGGER,
            "token_exchange_rejected",
            request_id=x_request_id,
            audience=payload.audience,
            reason=exc.detail,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    log_event(
        LOGGER,
        "token_exchange_completed",
        request_id=x_request_id,
        client_id=client_id,
        audience=payload.audience,
    )
    return TokenExchangeResponse(access_token=token, expires_in=expires_in)


def _parse_basic_credential(authorization: str | None) -> tuple[str | None, str | None]:
    """Extract (client_id, client_secret) from an HTTP Basic Authorization header."""
    import base64
    import binascii

    if not authorization:
        return None, None
    scheme, _, encoded = authorization.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return None, None
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None, None
    client_id, _, client_secret = decoded.partition(":")
    return client_id, client_secret


@router.post("/api/v1/auth/refresh", response_model=AuthenticatedSession)
async def auth_refresh(
    payload: TokenRefreshRequest,
    x_request_id: str | None = Header(default=None),
    settings: IdentitySettings = Depends(get_settings),
) -> AuthenticatedSession:
    try:
        response = await refresh_session(settings, payload)
        log_event(
            LOGGER,
            "auth_token_refreshed",
            request_id=x_request_id,
            user_id=response.identity.username,
        )
        return response
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=401, detail="token refresh failed") from exc
