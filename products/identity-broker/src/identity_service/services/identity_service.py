from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx

from identity_service.core.config import IdentitySettings
from identity_service.metadata import SERVICE_NAME, SERVICE_VERSION
from identity_service.schemas.auth import (
    AuthenticatedSession,
    AuthorizationCodeExchangeRequest,
    LoginStartResponse,
    LogoutRequest,
    LogoutResponse,
)
from identity_service.schemas.identity import ClaimsPayload, IdentityContext
from identity_service.services.token_service import issue_token

ROLE_MAPPINGS = {
    "ops-admins": "platform-admin",
    "ops-approvers": "approver",
    "ops-operators": "operator",
    "ops-observers": "read-only-observer",
}


def resolve_roles(groups: list[str]) -> list[str]:
    roles = {ROLE_MAPPINGS[group] for group in groups if group in ROLE_MAPPINGS}
    if not roles:
        roles.add("read-only-observer")
    return sorted(roles)


def health_status() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}


def _authorization_endpoint(settings: IdentitySettings) -> str:
    return (
        f"{settings.keycloak_base_url}/realms/{settings.keycloak_realm}"
        "/protocol/openid-connect/auth"
    )


def _token_endpoint(settings: IdentitySettings) -> str:
    return (
        f"{settings.keycloak_base_url}/realms/{settings.keycloak_realm}"
        "/protocol/openid-connect/token"
    )


def _userinfo_endpoint(settings: IdentitySettings) -> str:
    return (
        f"{settings.keycloak_base_url}/realms/{settings.keycloak_realm}"
        "/protocol/openid-connect/userinfo"
    )


def _logout_endpoint(settings: IdentitySettings) -> str:
    return (
        f"{settings.keycloak_base_url}/realms/{settings.keycloak_realm}"
        "/protocol/openid-connect/logout"
    )


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _pkce_challenge(code_verifier: str) -> str:
    return _base64url(hashlib.sha256(code_verifier.encode("ascii")).digest())


def _resolved_redirect_uri(
    settings: IdentitySettings,
    redirect_uri: str | None = None,
) -> str:
    return redirect_uri or settings.oidc_redirect_uri


def build_login_start(
    settings: IdentitySettings,
    redirect_uri: str | None = None,
) -> LoginStartResponse:
    code_verifier = _base64url(secrets.token_bytes(32))
    state = _base64url(secrets.token_bytes(24))
    resolved_redirect_uri = _resolved_redirect_uri(settings, redirect_uri)
    query = urlencode(
        {
            "client_id": settings.oidc_client_id,
            "response_type": "code",
            "scope": settings.oidc_scopes,
            "redirect_uri": resolved_redirect_uri,
            "state": state,
            "code_challenge": _pkce_challenge(code_verifier),
            "code_challenge_method": "S256",
        }
    )
    return LoginStartResponse(
        authorization_url=f"{_authorization_endpoint(settings)}?{query}",
        state=state,
        code_verifier=code_verifier,
        redirect_uri=resolved_redirect_uri,
    )


def normalize_identity(payload: ClaimsPayload) -> IdentityContext:
    return IdentityContext(
        subject=payload.sub,
        username=payload.preferred_username,
        email=payload.email,
        groups=payload.groups,
        roles=resolve_roles(payload.groups),
    )


def normalize_userinfo(payload: dict[str, Any]) -> IdentityContext:
    chosen_username = str(
        payload.get("preferred_username") or payload.get("email") or payload["sub"]
    )
    return normalize_identity(
        ClaimsPayload(
            sub=str(payload["sub"]),
            preferred_username=chosen_username,
            email=payload.get("email"),
            groups=[
                str(group)
                for group in payload.get("groups", [])
                if isinstance(group, str)
            ],
        )
    )


async def exchange_authorization_code(
    settings: IdentitySettings,
    payload: AuthorizationCodeExchangeRequest,
) -> AuthenticatedSession:
    form_data = {
        "grant_type": "authorization_code",
        "client_id": settings.oidc_client_id,
        "code": payload.code,
        "code_verifier": payload.code_verifier,
        "redirect_uri": _resolved_redirect_uri(settings, payload.redirect_uri),
    }
    if settings.oidc_client_secret:
        form_data["client_secret"] = settings.oidc_client_secret

    async with httpx.AsyncClient(timeout=10.0) as client:
        token_response = await client.post(
            _token_endpoint(settings),
            data=form_data,
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        token_response.raise_for_status()
        token_payload = token_response.json()
        access_token = str(token_payload["access_token"])
        userinfo_response = await client.get(
            _userinfo_endpoint(settings),
            headers={"authorization": f"Bearer {access_token}"},
        )
        userinfo_response.raise_for_status()
        userinfo_payload = userinfo_response.json()
        identity = normalize_userinfo(userinfo_payload)

    # Issue a platform JWT as the primary access token.
    platform_token, expires_in = issue_token(
        settings,
        {
            "sub": identity.subject,
            "username": identity.username,
            "email": identity.email,
            "roles": identity.roles,
            "groups": identity.groups,
        },
    )

    return AuthenticatedSession(
        access_token=platform_token,
        token_type="Bearer",
        expires_in=expires_in,
        refresh_token=token_payload.get("refresh_token"),
        id_token=token_payload.get("id_token"),
        identity=identity,
    )


async def fetch_identity_from_authorization(
    settings: IdentitySettings,
    authorization: str,
) -> IdentityContext:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ValueError("Expected an Authorization header with a Bearer token.")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            _userinfo_endpoint(settings),
            headers={"authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        userinfo_payload = response.json()
        identity = normalize_userinfo(userinfo_payload)
        return identity


def build_logout_response(
    settings: IdentitySettings,
    payload: LogoutRequest,
) -> LogoutResponse:
    query: dict[str, str] = {
        "client_id": settings.oidc_client_id,
        "post_logout_redirect_uri": (
            payload.post_logout_redirect_uri or settings.oidc_post_logout_redirect_uri
        ),
    }
    if payload.id_token_hint:
        query["id_token_hint"] = payload.id_token_hint
    return LogoutResponse(logout_url=f"{_logout_endpoint(settings)}?{urlencode(query)}")
