"""SPEC-070 private delegated execution verification.

Independently re-verifies the execution-runtime workload identity and the two
human bearers (requester + approver) against the signed execution projection,
then hands a policy-ready approver identity back to the shared dispatch path.

Trust boundaries held here:

- The execution HMAC signing secret is never distributed to tool-gateway, and
  workload authentication alone is never treated as execution authority — the
  worker remains the single non-retrying dispatch owner and this module only
  re-proves the human identities and their equality to the projection.
- Human and workload bearers are identity/transport material only: they are
  verified, matched, and discarded. They are never persisted, echoed, or logged,
  and a verification failure surfaces a generic detail with no token material.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import jwt

from tool_gateway.core.config import GatewaySettings
from tool_gateway.schemas.api import IdentityContext

LOGGER = logging.getLogger(__name__)

MAX_TOKEN_BYTES = 16384

# Fields the worker's verified projection must carry for the gateway to bind the
# humans and re-derive the dispatch. Absence of any one is a malformed handoff.
_PROJECTION_FIELDS = (
    "tool_name",
    "session_id",
    "approval_kind",
    "execution_id",
    "args_digest",
    "requester_namespace",
    "requester_sub",
    "decider_namespace",
    "decider_sub",
    "owner_user_id",
    "decider_user_id",
)

# Cached JWKS clients per configured URL (module-level so repeated create_app()
# calls never re-fetch per request); cleared by ``reset_delegated_state``.
_WORKLOAD_JWKS: dict[str, jwt.PyJWKClient] = {}
_HUMAN_JWKS: dict[str, jwt.PyJWKClient] = {}


class DelegatedInvokeError(Exception):
    """A fail-closed refusal carrying an HTTP status and a non-sensitive detail."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def reset_delegated_state() -> None:
    """Clear cached JWKS clients (for tests)."""
    _WORKLOAD_JWKS.clear()
    _HUMAN_JWKS.clear()


def _bounded(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 256
        and value == value.strip()
        and not any(ord(char) < 32 or char == "\x7f" for char in value)
    )


def canonical_json(obj: Any) -> str:
    """Canonical JSON: sorted keys, no insignificant whitespace (non-secret)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def canonical_digest(obj: Any) -> str:
    """SHA-256 hex of the canonical JSON of ``obj``.

    A pure digest, not the execution HMAC: it lets the gateway re-derive the
    signed ``args_digest`` from the parameters it will actually dispatch without
    ever holding the signing secret.
    """
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def _workload_jwks_client(settings: GatewaySettings) -> jwt.PyJWKClient:
    cached = _WORKLOAD_JWKS.get(settings.execution_workload_jwks_url)
    if cached is None:
        cached = jwt.PyJWKClient(
            settings.execution_workload_jwks_url,
            cache_keys=True,
            lifespan=settings.identity_jwks_cache_seconds,
            timeout=5,
        )
        _WORKLOAD_JWKS[settings.execution_workload_jwks_url] = cached
    return cached


def _human_jwks_client(settings: GatewaySettings) -> jwt.PyJWKClient:
    cached = _HUMAN_JWKS.get(settings.delegated_identity_jwks_url)
    if cached is None:
        cached = jwt.PyJWKClient(
            settings.delegated_identity_jwks_url,
            cache_keys=True,
            lifespan=settings.identity_jwks_cache_seconds,
            timeout=5,
        )
        _HUMAN_JWKS[settings.delegated_identity_jwks_url] = cached
    return cached


def _bearer(request: Any) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise DelegatedInvokeError(401, "workload authentication required")
    token = token.strip()
    if len(token) > MAX_TOKEN_BYTES:
        raise DelegatedInvokeError(401, "workload token invalid")
    return token


def authenticate_execution_workload(settings: GatewaySettings, request: Any) -> str:
    """Verify the projected execution-runtime SA token; return its subject.

    Mirrors the audit-service workload path: RS256 via the cluster JWKS, a
    dedicated audience, and an exact subject allowlist. Any failure is a generic
    401 that never echoes the token or the library exception text.
    """
    token = _bearer(request)
    try:
        key = _workload_jwks_client(settings).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            issuer=settings.execution_workload_issuer,
            audience=settings.execution_workload_audience,
            options={"require": ["exp", "iss", "sub", "aud"]},
        )
    except Exception:
        raise DelegatedInvokeError(401, "workload token invalid") from None
    subject = str(claims.get("sub", ""))
    if subject not in settings.execution_workload_subjects:
        raise DelegatedInvokeError(401, "workload subject not authorized")
    return subject


def decode_delegated_human_claims(settings: GatewaySettings, token: object) -> dict:
    """Decode and structurally validate one delegated human bearer; return claims.

    Shared by the execution-handoff projection binding (``_verify_human``) and the
    target-authorization workflow's owner derivation, so both hold the identical
    human-trust bar: RS256 under the delegated-identity trust config, ``oidc``
    provenance, an RFC-8693 ``act`` actor on the allowlist, integer ``exp>iat``,
    and bounded immutable ``sub``/``username``. Raises ``ValueError`` (or the
    library's own token error) on any failure so each caller wraps it in its own
    fixed refusal; the token and the library exception text are never echoed.
    """
    if not isinstance(token, str) or not 0 < len(token) <= MAX_TOKEN_BYTES:
        raise ValueError("malformed human bearer")
    key = _human_jwks_client(settings).get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        key.key,
        algorithms=["RS256"],
        issuer=settings.delegated_identity_issuer,
        audience=settings.delegated_identity_audience,
        options={
            "require": [
                "iss", "aud", "sub", "exp", "iat", "act", "authentication_source",
            ]
        },
    )
    actor = claims["act"]
    if (
        claims["authentication_source"] != "oidc"
        or type(claims["exp"]) is not int
        or type(claims["iat"]) is not int
        or claims["exp"] <= claims["iat"]
        or not _bounded(claims["sub"])
        or not _bounded(claims.get("username"))
        or not isinstance(actor, dict)
        or set(actor) != {"sub"}
        or not isinstance(actor["sub"], str)
        or actor["sub"] not in settings.delegated_identity_actors
    ):
        raise ValueError("human bearer failed structural validation")
    return claims


def _verify_human(
    settings: GatewaySettings,
    token: object,
    *,
    namespace: str,
    subject: str,
    username: str,
) -> IdentityContext:
    """Strictly verify one delegated human bearer and bind it to the projection.

    Delegates the shared structural human-trust checks to
    ``decode_delegated_human_claims``, then additionally binds the bearer to the
    signed projection's namespace/sub and username. Returns an ``IdentityContext``
    carrying the human's roles so the shared dispatch path can apply policy under
    the approver's authority.
    """
    try:
        claims = decode_delegated_human_claims(settings, token)
        if (
            namespace != settings.delegated_identity_issuer
            or claims["sub"] != subject
            or claims.get("username") != username
            or not _bounded(subject)
            or not _bounded(username)
        ):
            raise ValueError()
    except Exception:
        raise DelegatedInvokeError(
            403, "delegated identity verification failed"
        ) from None
    actor = claims["act"]
    roles = claims.get("roles", [])
    groups = claims.get("groups", [])
    return IdentityContext(
        subject=str(claims["sub"]),
        username=str(claims["username"]),
        email=claims.get("email"),
        groups=[str(g) for g in groups] if isinstance(groups, list) else [],
        roles=[str(r) for r in roles] if isinstance(roles, list) else [],
        actor=actor["sub"],
    )


def verify_delegated_invocation(
    settings: GatewaySettings, body: object
) -> tuple[dict, dict, IdentityContext, IdentityContext]:
    """Verify the full delegated handoff and return the dispatch inputs.

    Returns ``(projection, parameters, requester_identity, decider_identity)``.
    The parameters the gateway will dispatch must re-derive the projection's
    signed ``args_digest``, and each human bearer must independently verify and
    equal its signed identity — otherwise the handoff fails closed.
    """
    if not isinstance(body, dict):
        raise DelegatedInvokeError(400, "malformed delegated invocation")
    projection = body.get("projection")
    parameters = body.get("parameters")
    if not isinstance(projection, dict) or not isinstance(parameters, dict):
        raise DelegatedInvokeError(400, "malformed delegated invocation")
    if any(field not in projection for field in _PROJECTION_FIELDS):
        raise DelegatedInvokeError(400, "incomplete execution projection")
    if canonical_digest(parameters) != projection["args_digest"]:
        raise DelegatedInvokeError(400, "parameter digest does not match projection")
    requester = _verify_human(
        settings,
        body.get("requester_token"),
        namespace=projection["requester_namespace"],
        subject=projection["requester_sub"],
        username=projection["owner_user_id"],
    )
    decider = _verify_human(
        settings,
        body.get("decider_token"),
        namespace=projection["decider_namespace"],
        subject=projection["decider_sub"],
        username=projection["decider_user_id"],
    )
    return projection, parameters, requester, decider
