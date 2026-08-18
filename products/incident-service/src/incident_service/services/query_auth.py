"""Platform-caller authentication (SPEC-015 R-2, SPEC-014 R-3 vocabulary).

Reuses the SPEC-008/009 credential vocabulary, verified locally — no runtime
dependency on the identity broker:

- static path: HTTP Basic against the ``INCIDENT_QUERY_CLIENTS`` registry
  (platform-gateway and tool-gateway hold these credentials)
- workload path: Kubernetes projected service-account token presented as a
  Bearer token, validated against the cluster OIDC issuer JWKS with audience
  and subject-registry checks
"""

from __future__ import annotations

import base64
import binascii
import logging
from typing import Any

import httpx
import jwt
from fastapi import Request

from incident_service.core.config import IncidentSettings

LOGGER = logging.getLogger(__name__)


class QueryAuthError(Exception):
    """Raised when the caller cannot be authenticated (maps to 401)."""


def authenticate_static(
    settings: IncidentSettings, client_id: str | None, client_secret: str | None
) -> str:
    """Validate an HTTP Basic credential against the platform-caller registry."""
    if not client_id or not client_secret:
        raise QueryAuthError("service credential required")
    for client in settings.query_clients:
        if client.client_id == client_id and client.secret == client_secret:
            return client.client_id
    raise QueryAuthError("invalid service credential")


# Cached JWKS clients per workload issuer URL (module-level so repeated
# create_app() calls never re-fetch per request).
_workload_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def _get_workload_jwks_client(settings: IncidentSettings) -> jwt.PyJWKClient:
    """Resolve the cluster OIDC issuer's JWKS via discovery."""
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


def authenticate_workload(settings: IncidentSettings, bearer_token: str) -> str:
    """Validate a projected workload token and map it to a registered client."""
    if not settings.workload_issuer_url:
        raise QueryAuthError("workload identity not enabled")
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
        raise QueryAuthError("workload token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise QueryAuthError("workload token invalid") from exc
    subject = str(claims.get("sub", ""))
    for mapping in settings.workload_clients:
        if mapping.workload_subject == subject:
            return mapping.client_id
    raise QueryAuthError("workload subject not registered")


def _parse_basic(header_value: str) -> tuple[str | None, str | None]:
    try:
        decoded = base64.b64decode(header_value.strip()).decode()
    except (binascii.Error, UnicodeDecodeError):
        return None, None
    client_id, _, secret = decoded.partition(":")
    return client_id or None, secret or None


async def authenticate_caller(settings: IncidentSettings, request: Request) -> str:
    """Resolve the calling platform service from the Authorization header.

    Bearer tokens take the workload path; Basic credentials take the static
    registry path. Anything else (or a failure on either path) yields 401.
    """
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return authenticate_workload(settings, header[7:].strip())
    if header.lower().startswith("basic "):
        client_id, secret = _parse_basic(header[6:])
        return authenticate_static(settings, client_id, secret)
    raise QueryAuthError("service credential required")
