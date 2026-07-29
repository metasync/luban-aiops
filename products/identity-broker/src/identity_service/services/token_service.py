"""JWT token issuance and JWKS key management.

Owns the RSA key lifecycle (load / generate / persist), signs platform JWTs,
and serializes the public key set in RFC 7517 (JWKS) format.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from identity_service.core.config import IdentitySettings
from identity_service.core.metrics import record_token_issued

LOGGER = logging.getLogger(__name__)

# Module-level singleton, initialized on first use.
_private_key: rsa.RSAPrivateKey | None = None
_kid: str | None = None


def _generate_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _compute_kid(key: rsa.RSAPrivateKey) -> str:
    """Deterministic kid from SHA-256 thumbprint of the public key DER."""
    pub_der = key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(pub_der).hexdigest()[:16]


def _load_or_create_key(settings: IdentitySettings) -> rsa.RSAPrivateKey:
    """Load key from configured path, or generate (and optionally persist)."""
    path_str = settings.jwt_private_key_path

    if path_str:
        path = Path(path_str)
        if path.exists():
            LOGGER.info("loading JWT signing key from %s", path)
            return serialization.load_pem_private_key(path.read_bytes(), password=None)
        # Dev first-boot: generate and persist.
        key = _generate_key()
        path.parent.mkdir(parents=True, exist_ok=True)
        pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        path.write_bytes(pem)
        LOGGER.warning("generated dev JWT signing key at %s (insecure, dev only)", path)
        return key

    # No path configured — ephemeral in-memory key (CI / tests).
    LOGGER.warning("using ephemeral in-memory JWT signing key (insecure)")
    return _generate_key()


def _ensure_key(settings: IdentitySettings) -> tuple[rsa.RSAPrivateKey, str]:
    global _private_key, _kid
    if _private_key is None:
        _private_key = _load_or_create_key(settings)
        _kid = _compute_kid(_private_key)
    return _private_key, _kid  # type: ignore[return-value]


def reset_key_state() -> None:
    """Reset module state (for tests)."""
    global _private_key, _kid
    _private_key = None
    _kid = None


def issue_token(settings: IdentitySettings, identity: dict[str, Any]) -> tuple[str, int]:
    """Sign a JWT for the given identity claims.

    Returns (token_string, expires_in_seconds).
    """
    key, kid = _ensure_key(settings)
    now = int(time.time())
    ttl = settings.jwt_token_ttl_seconds

    claims: dict[str, Any] = {
        "iss": settings.jwt_issuer,
        "sub": identity.get("sub", identity.get("subject", "")),
        "username": identity.get("username", ""),
        "email": identity.get("email"),
        "roles": identity.get("roles", []),
        "groups": identity.get("groups", []),
        "iat": now,
        "exp": now + ttl,
    }

    token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})
    record_token_issued()
    return token, ttl


def jwks_response(settings: IdentitySettings) -> dict[str, Any]:
    """Return the public key set in RFC 7517 JWKS format."""
    key, kid = _ensure_key(settings)
    pub = key.public_key()
    pub_numbers = pub.public_numbers()

    # Encode n and e as base64url unsigned big-endian integers.
    def _b64url_uint(value: int) -> str:
        import base64

        byte_length = (value.bit_length() + 7) // 8
        raw = value.to_bytes(byte_length, byteorder="big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": kid,
                "n": _b64url_uint(pub_numbers.n),
                "e": _b64url_uint(pub_numbers.e),
            }
        ]
    }
