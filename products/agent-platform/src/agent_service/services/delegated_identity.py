"""Strict, non-model human identity for requester-owned target grants (SPEC-070).

General development authentication is deliberately unrelated to this verifier.
A context contains verified identity facts only, never a bearer or target token.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from functools import lru_cache
import time

import jwt

_AUTHORITY = object()


class DelegatedIdentityError(ValueError):
    def __init__(self):
        super().__init__("delegated_identity_invalid")


def _bounded(value):
    return (isinstance(value, str) and 0 < len(value) <= 256 and value == value.strip()
            and not any(ord(char) < 32 or ord(char) == 127 for char in value))


@dataclass(frozen=True, slots=True, init=False)
class VerifiedHuman:
    namespace: str
    subject: str
    user_id: str
    actor: str
    expires_at: int

    def __init__(self, authority, namespace, subject, user_id, actor, expires_at):
        if authority is not _AUTHORITY:
            raise TypeError("verified identity requires verification")
        for name, value in (("namespace", namespace), ("subject", subject), ("user_id", user_id),
                            ("actor", actor), ("expires_at", expires_at)):
            object.__setattr__(self, name, value)

    def __reduce_ex__(self, protocol):
        raise TypeError("verified identity is process-local")

    def require_live(self):
        if self.expires_at <= time.time():
            raise DelegatedIdentityError()

    def matches(self, namespace, subject):
        return self.namespace == namespace and self.subject == subject


REQUESTER_IDENTITY: ContextVar[VerifiedHuman | None] = ContextVar("REQUESTER_IDENTITY", default=None)
DECIDER_IDENTITY: ContextVar[VerifiedHuman | None] = ContextVar("DECIDER_IDENTITY", default=None)


class DelegatedIdentityVerifier:
    def __init__(self, issuer, audience, actors, jwks_client):
        if not _bounded(issuer) or not _bounded(audience) or not actors or any(not _bounded(a) for a in actors):
            raise DelegatedIdentityError()
        self.issuer, self.audience, self.actors = issuer, audience, frozenset(actors)
        self._jwks = jwks_client

    def verify(self, token, *, user_id=None):
        try:
            if not isinstance(token, str) or not 0 < len(token) <= 16384:
                raise DelegatedIdentityError()
            key = self._jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(token, key.key, algorithms=["RS256"], issuer=self.issuer, audience=self.audience,
                                options={"require": ["exp", "iat", "iss", "sub", "aud", "authentication_source", "act"]})
            actor = claims["act"]
            if (claims["authentication_source"] != "oidc" or not _bounded(claims["sub"])
                    or not _bounded(claims.get("username")) or type(claims["exp"]) is not int
                    or type(claims["iat"]) is not int or claims["exp"] <= claims["iat"]
                    or not isinstance(actor, dict) or set(actor) != {"sub"}
                    or not isinstance(actor["sub"], str) or actor["sub"] not in self.actors
                    or (user_id is not None and claims["username"] != user_id)):
                raise DelegatedIdentityError()
            identity = VerifiedHuman(_AUTHORITY, self.issuer, claims["sub"], claims["username"], actor["sub"], claims["exp"])
            identity.require_live()
            return identity
        except Exception:
            # Never expose a JWT, claims, JWKS URL, or library exception text.
            raise DelegatedIdentityError() from None


@lru_cache(maxsize=8)
def _verifier(issuer, audience, actors, jwks_url):
    if not jwks_url:
        raise DelegatedIdentityError()
    return DelegatedIdentityVerifier(issuer, audience, actors,
                                    jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=300, timeout=5))


def verify_delegated_human(settings, token, *, user_id=None):
    return _verifier(settings.delegated_identity_issuer, settings.delegated_identity_audience,
                     settings.delegated_identity_actors, settings.delegated_identity_jwks_url).verify(token, user_id=user_id)


def session_birth_fields(requester: VerifiedHuman | None, user_id: str | None) -> dict[str, str]:
    if requester is None:
        return {}
    if not isinstance(requester, VerifiedHuman) or requester.user_id != user_id:
        raise DelegatedIdentityError()
    requester.require_live()
    return {"requester_namespace": requester.namespace, "requester_sub": requester.subject}


def session_requester(session, requester: VerifiedHuman | None) -> VerifiedHuman | None:
    """Only an already-bound backend session can authorize delegated acquisition."""
    if requester is not None:
        session_birth_fields(requester, session.user_id)
    if session.requester_namespace is None and session.requester_sub is None:
        return None
    if requester is None or not requester.matches(session.requester_namespace, session.requester_sub):
        raise DelegatedIdentityError()
    return requester


def signed_identity_fields(requester, decider, owner_user_id, decider_user_id):
    if requester is None and decider is None:
        return {}
    if (not isinstance(requester, VerifiedHuman) or not isinstance(decider, VerifiedHuman)
            or requester.user_id != owner_user_id or decider.user_id != decider_user_id):
        raise DelegatedIdentityError()
    requester.require_live()
    decider.require_live()
    return {"requester_namespace": requester.namespace, "requester_sub": requester.subject,
            "decider_namespace": decider.namespace, "decider_sub": decider.subject}
