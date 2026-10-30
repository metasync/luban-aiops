"""Worker-owned human verification and private, memory-only delegated send context.

A signed envelope and its durable send claim remain execution authority. Human
JWTs supply identity only; neither one is an external target credential.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import hmac
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

import jwt

from execution_runtime.services.execution_protocol import ProtocolError, validate_request
from execution_runtime.services.execution_signing import canonical_digest

_AUTHORITY = object()
IDENTITY_FIELDS = frozenset({"requester_namespace", "requester_sub", "decider_namespace", "decider_sub"})
WORKLOAD_AUDIENCE = "luban-target-execution-handoff"
MAX_TOKEN_BYTES = 16384


def _bounded(value):
    return (isinstance(value, str) and 0 < len(value) <= 256 and value == value.strip()
            and not any(ord(char) < 32 or ord(char) == 127 for char in value))


def validate_trust(settings):
    try:
        values = (settings.delegated_identity_issuer, settings.delegated_identity_audience)
        actors = settings.delegated_identity_actors
        url = urlsplit(settings.delegated_identity_jwks_url or "")
        if (not all(_bounded(value) for value in values) or not actors
                or any(not _bounded(actor) for actor in actors)
                or url.scheme not in {"http", "https"} or not url.hostname
                or url.username is not None or url.password is not None or url.query or url.fragment
                or not settings.target_execution_token_path
                or not Path(settings.target_execution_token_path).is_absolute()):
            raise ValueError()
        _ = url.port
    except (ValueError, TypeError, AttributeError):
        raise ValueError("delegated execution requires explicit identity trust and workload token mount") from None


@lru_cache(maxsize=8)
def _jwks(url):
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=300, timeout=5)


def _human(settings, token, namespace, subject, username):
    try:
        if not isinstance(token, str) or not 0 < len(token) <= MAX_TOKEN_BYTES:
            raise ValueError()
        key = _jwks(settings.delegated_identity_jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=["RS256"],
                            issuer=settings.delegated_identity_issuer, audience=settings.delegated_identity_audience,
                            options={"require": ["iss", "aud", "sub", "exp", "iat", "act", "authentication_source"]})
        actor = claims["act"]
        if (namespace != settings.delegated_identity_issuer or claims["sub"] != subject
                or claims.get("username") != username or not _bounded(subject) or not _bounded(username)
                or claims["authentication_source"] != "oidc" or type(claims["exp"]) is not int
                or type(claims["iat"]) is not int or claims["exp"] <= claims["iat"]
                or not isinstance(actor, dict) or set(actor) != {"sub"}
                or not isinstance(actor["sub"], str) or actor["sub"] not in settings.delegated_identity_actors):
            raise ValueError()
        return claims["exp"]
    except Exception:
        raise ProtocolError("unauthorized") from None


@dataclass(frozen=True, slots=True, init=False)
class VerifiedDelegatedExecution:
    _projection: tuple = field(repr=False)
    requester_token: str = field(repr=False)
    _decider_token: str = field(repr=False)
    _expires_at: int = field(repr=False)

    def __init__(self, authority, projection, requester_token, decider_token, expires_at):
        if authority is not _AUTHORITY:
            raise TypeError("delegated execution requires verification")
        for name, value in (("_projection", tuple(projection.items())), ("requester_token", requester_token),
                            ("_decider_token", decider_token), ("_expires_at", expires_at)):
            object.__setattr__(self, name, value)

    def __reduce_ex__(self, protocol):
        raise TypeError("delegated execution is process-local")

    @property
    def projection(self):
        return dict(self._projection)

    def require_live(self):
        if self._expires_at <= time.time():
            raise ProtocolError("unauthorized")

    def check_send(self, tool_name, arguments, decider_token, session_id, approval_kind, execution_id):
        self.require_live()
        projection = self.projection
        if (not isinstance(decider_token, str)
                or not hmac.compare_digest(decider_token.encode(), self._decider_token.encode())
                or any(projection[name] != value for name, value in (
                    ("tool_name", tool_name), ("session_id", session_id), ("approval_kind", approval_kind),
                    ("execution_id", execution_id), ("args_digest", canonical_digest(arguments))))):
            raise ProtocolError("identity_conflict")


def verify_handoff(settings, envelope, arguments, decider_token, requester_token):
    """Validate the complete signed binding before the durable claim; no tokens persist."""
    validate_request(envelope, settings.execution_signing_key)
    if not IDENTITY_FIELDS.issubset(envelope):
        raise ProtocolError("bad_request")
    if not settings.target_authorization_enabled:
        raise ProtocolError("gateway_not_configured")
    try:
        validate_trust(settings)
    except ValueError:
        raise ProtocolError("gateway_not_configured") from None
    if not isinstance(arguments, dict) or canonical_digest(arguments) != envelope["args_digest"]:
        raise ProtocolError("args_digest_mismatch")
    owner_exp = _human(settings, requester_token, envelope["requester_namespace"],
                       envelope["requester_sub"], envelope["owner_user_id"])
    decider_exp = _human(settings, decider_token, envelope["decider_namespace"],
                         envelope["decider_sub"], envelope["decider_user_id"])
    projection = {name: value for name, value in envelope.items() if name != "signature"}
    projection["request_digest"] = canonical_digest(envelope)
    verified = VerifiedDelegatedExecution(_AUTHORITY, projection, requester_token, decider_token,
                                          min(owner_exp, decider_exp))
    verified.require_live()
    return verified


def read_workload_token(settings):
    """Reread a bounded projected JWT per send. No static credential fallback."""
    try:
        with open(settings.target_execution_token_path, "rb") as source:
            value = source.read(MAX_TOKEN_BYTES + 1)
        if len(value) > MAX_TOKEN_BYTES:
            raise ValueError()
        token = value.decode("ascii").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token):
            raise ValueError()
        return token
    except (OSError, ValueError, TypeError):
        raise ProtocolError("credential_missing") from None
