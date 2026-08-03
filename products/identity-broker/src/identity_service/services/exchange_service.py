"""Broker-mediated token delegation (SPEC-008 R-2/R-3, ADR-0004).

Authenticates a registered service caller, verifies the presented subject
token locally (the broker holds its own signing key), and mints a short-lived,
audience-bound delegated token. Roles are copied verbatim from the subject
token — the exchange can never grant authority the subject token lacks.

Service credentials (SPEC-009 R-3): the caller authenticates either via the
static HTTP Basic client credential (SPEC-008 R-3, the dev fallback) or via
a Kubernetes projected service-account token presented as a Bearer token,
validated against the configured cluster OIDC issuer and mapped to a
registered client by subject.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
import jwt

from identity_service.core.config import (
    IdentitySettings,
    ServiceClient,
)
from identity_service.core.metrics import record_token_exchange
from identity_service.services.token_service import _ensure_key, issue_token

LOGGER = logging.getLogger(__name__)


class ExchangeError(Exception):
    """Raised when a delegation exchange cannot be completed.

    ``status_code`` maps to the HTTP response: 401 for credential or subject
    verification failures, 400 for a disallowed audience.
    """

    def __init__(self, detail: str, status_code: int) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def authenticate_client(
    settings: IdentitySettings,
    client_id: str | None,
    client_secret: str | None,
) -> ServiceClient:
    """Resolve and validate a service credential against the registry (R-3)."""
    if not client_id or not client_secret:
        raise ExchangeError("service credential required", 401)
    for client in settings.service_clients:
        if client.client_id == client_id and client.secret == client_secret:
            return client
    raise ExchangeError("invalid service credential", 401)


# Cached JWKS clients per workload issuer URL (module-level so repeated
# create_app() calls never re-fetch per request).
_workload_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def _get_workload_jwks_client(settings: IdentitySettings) -> jwt.PyJWKClient:
    """Resolve the cluster OIDC issuer's JWKS via discovery (SPEC-009 R-3)."""
    cached = _workload_jwks_clients.get(settings.workload_issuer_url)
    if cached is None:
        discovery_url = (
            f"{settings.workload_issuer_url.rstrip('/')}/.well-known/openid-configuration"
        )
        discovery = httpx.get(discovery_url, timeout=5.0).json()
        cached = jwt.PyJWKClient(discovery["jwks_uri"], cache_keys=True)
        _workload_jwks_clients[settings.workload_issuer_url] = cached
    return cached


def reset_workload_state() -> None:
    """Clear cached workload JWKS clients (for tests)."""
    _workload_jwks_clients.clear()


def authenticate_workload_client(
    settings: IdentitySettings, bearer_token: str
) -> ServiceClient:
    """Validate a projected workload token and map it to a registered client.

    The token must be issued by the configured cluster OIDC issuer and carry
    the configured workload audience; its ``sub`` must be registered in
    ``workload_clients``. The mapped client reuses the same audience
    allow-list semantics as the static registry, so the delegated token's
    claims are identical to the static-secret path.
    """
    if not settings.workload_issuer_url:
        raise ExchangeError("workload identity not enabled", 401)
    try:
        key = _get_workload_jwks_client(settings).get_signing_key_from_jwt(
            bearer_token
        )
        claims: dict[str, Any] = jwt.decode(
            bearer_token,
            key.key,
            algorithms=["RS256"],
            issuer=settings.workload_issuer_url,
            audience=settings.workload_audience,
            options={"require": ["exp", "iss", "sub", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ExchangeError("workload token expired", 401) from exc
    except jwt.InvalidTokenError as exc:
        raise ExchangeError("workload token invalid", 401) from exc
    subject = str(claims.get("sub", ""))
    for mapping in settings.workload_clients:
        if mapping.workload_subject == subject:
            return ServiceClient(
                client_id=mapping.client_id,
                secret="",
                allowed_audiences=mapping.allowed_audiences,
            )
    raise ExchangeError("workload subject not registered", 401)


def verify_subject_token(settings: IdentitySettings, subject_token: str) -> dict[str, Any]:
    """Verify a subject token against the broker's own signing key.

    The broker is the issuer, so it verifies directly with the private key's
    public half rather than over JWKS. The subject token is audience-bound to
    the gateway (R-1), so it is validated against ``settings.jwt_audience``;
    the exchange then re-targets the delegated token to the requested audience.
    """
    key, _ = _ensure_key(settings)
    try:
        claims: dict[str, Any] = jwt.decode(
            subject_token,
            key.public_key(),
            algorithms=["RS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["exp", "iss", "sub", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ExchangeError("subject token expired", 401) from exc
    except jwt.InvalidTokenError as exc:
        raise ExchangeError("subject token invalid", 401) from exc
    return claims


def exchange_token(
    settings: IdentitySettings,
    client_id: str | None,
    client_secret: str | None,
    subject_token: str,
    audience: str,
    workload_token: str | None = None,
) -> tuple[str, int]:
    """Authenticate the caller, verify the subject token, mint a delegated token.

    The service credential is either a Bearer workload token (preferred when
    present, SPEC-009 R-3) or the static HTTP Basic client credential.
    Returns (delegated_token, expires_in_seconds).
    """
    if workload_token:
        client = authenticate_workload_client(settings, workload_token)
    else:
        client = authenticate_client(settings, client_id, client_secret)

    claims = verify_subject_token(settings, subject_token)

    if audience not in client.allowed_audiences:
        record_token_exchange("error")
        raise ExchangeError("audience not permitted for this client", 400)

    delegated_identity = {
        "sub": claims.get("sub", ""),
        "username": claims.get("username", claims.get("sub", "")),
        "email": claims.get("email"),
        "roles": claims.get("roles", []),
        "groups": claims.get("groups", []),
    }
    token, expires_in = issue_token(
        settings,
        delegated_identity,
        audience=audience,
        actor={"sub": client.client_id},
        ttl_seconds=settings.delegated_token_ttl_seconds,
    )
    record_token_exchange("success")
    LOGGER.info(
        "token_exchange client=%s subject=%s audience=%s",
        client.client_id,
        delegated_identity["sub"],
        audience,
    )
    return token, expires_in
