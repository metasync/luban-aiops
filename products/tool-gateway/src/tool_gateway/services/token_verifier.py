"""Local JWT verification via JWKS (R-2).

Replaces per-request HTTP introspection with local cryptographic verification.
The gateway holds only the public key — it can verify but never forge tokens.
"""

from __future__ import annotations

import logging
from typing import Any

import jwt
from jwt import PyJWKClient

from tool_gateway.core.config import GatewaySettings
from tool_gateway.schemas.api import IdentityContext

LOGGER = logging.getLogger(__name__)

# Module-level JWKS client singleton.
_jwks_client: PyJWKClient | None = None
_configured_url: str | None = None


def _get_jwks_client(settings: GatewaySettings) -> PyJWKClient:
    global _jwks_client, _configured_url
    if _jwks_client is None or _configured_url != settings.identity_jwks_url:
        _jwks_client = PyJWKClient(
            settings.identity_jwks_url,
            cache_keys=True,
            lifespan=settings.identity_jwks_cache_seconds,
        )
        _configured_url = settings.identity_jwks_url
    return _jwks_client


def reset_verifier_state() -> None:
    """Reset module state (for tests)."""
    global _jwks_client, _configured_url
    _jwks_client = None
    _configured_url = None


class TokenVerificationError(Exception):
    """Raised when a token cannot be verified."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def verify_token(settings: GatewaySettings, token: str) -> IdentityContext:
    """Verify a JWT locally and return the identity context.

    Raises TokenVerificationError on any verification failure.
    """
    client = _get_jwks_client(settings)

    try:
        signing_key = client.get_signing_key_from_jwt(token)
    except Exception as exc:
        raise TokenVerificationError("unable to resolve signing key") from exc

    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.identity_token_issuer,
            audience=settings.token_audience,
            options={"require": ["exp", "iss", "sub", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenVerificationError("token expired") from exc
    except jwt.InvalidIssuerError as exc:
        raise TokenVerificationError("invalid token issuer") from exc
    except jwt.InvalidAudienceError as exc:
        raise TokenVerificationError("invalid token audience") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenVerificationError(f"invalid token: {exc}") from exc

    return IdentityContext(
        subject=str(claims.get("sub", "")),
        username=str(claims.get("username", claims.get("sub", ""))),
        email=claims.get("email"),
        groups=claims.get("groups", []),
        roles=claims.get("roles", []),
        actor=_extract_actor(claims.get("act")),
    )


def _extract_actor(act: Any) -> str | None:
    """Return the acting service subject from an RFC 8693 ``act`` claim."""
    if isinstance(act, dict):
        actor_sub = act.get("sub")
        if isinstance(actor_sub, str) and actor_sub:
            return actor_sub
    return None
