"""Broker-mediated token delegation (SPEC-008 R-2/R-3, ADR-0004).

Authenticates a registered service caller, verifies the presented subject
token locally (the broker holds its own signing key), and mints a short-lived,
audience-bound delegated token. Roles are copied verbatim from the subject
token — the exchange can never grant authority the subject token lacks.
"""

from __future__ import annotations

import logging
from typing import Any

import jwt

from identity_service.core.config import IdentitySettings, ServiceClient
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
) -> tuple[str, int]:
    """Authenticate the caller, verify the subject token, mint a delegated token.

    Returns (delegated_token, expires_in_seconds).
    """
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
