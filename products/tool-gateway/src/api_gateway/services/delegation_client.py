"""Gateway-side token delegation (SPEC-008 R-4, ADR-0004).

The gateway exchanges the verified user token for a short-lived, audience-bound
delegated token at the identity-broker and forwards it to agent-platform as a
bearer token. Delegated tokens are cached per user subject (the token's
authority is per-user, so it is interchangeable across that user's sessions);
the gateway deliberately does not reach into agent-platform's session store.

Exchange failure is non-fatal: ``obtain_delegated_token`` returns ``None`` so
the chat request still succeeds and the agent simply runs without tools.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from api_gateway.core.config import GatewaySettings
from api_gateway.core.metrics import (
    record_delegation_cache,
    record_delegation_exchange,
)

LOGGER = logging.getLogger(__name__)

# Re-exchange once a delegated token is within this fraction of its TTL.
_REFRESH_FRACTION = 0.8


@dataclass
class _CacheEntry:
    token: str
    expires_at: float
    refresh_at: float


class DelegationClient:
    """Per-replica, per-user delegated-token cache backed by broker exchange."""

    def __init__(self) -> None:
        self._cache: dict[str, _CacheEntry] = {}
        self._dev_key: rsa.RSAPrivateKey | None = None
        self._workload_fallback_warned = False

    def reset(self) -> None:
        """Clear the cache and dev key (for tests)."""
        self._cache.clear()
        self._dev_key = None
        self._workload_fallback_warned = False

    def get_cached(self, subject: str) -> str | None:
        """Return a still-valid (not near-expiry) delegated token, if any."""
        entry = self._cache.get(subject)
        now = time.time()
        if entry is not None and now < entry.refresh_at:
            record_delegation_cache("hit")
            return entry.token
        if entry is not None:
            self._cache.pop(subject, None)
        record_delegation_cache("miss")
        return None

    def put(self, subject: str, token: str, expires_in: int) -> None:
        now = time.time()
        self._cache[subject] = _CacheEntry(
            token=token,
            expires_at=now + expires_in,
            refresh_at=now + max(1, int(expires_in * _REFRESH_FRACTION)),
        )

    async def exchange(self, settings: GatewaySettings, subject_token: str) -> tuple[str, int]:
        """Exchange a subject token for a delegated token at the broker.

        Returns (delegated_token, expires_in_seconds). Raises on any failure.
        The service credential is the projected workload token when available
        (SPEC-009 R-3), else the static client credential (dev fallback).
        """
        url = f"{settings.identity_service_url}/api/v1/auth/exchange"
        payload = {
            "subject_token": subject_token,
            "audience": settings.delegation_audience,
        }
        workload_token = self._read_workload_token(settings)
        if workload_token is not None:
            headers = {"Authorization": f"Bearer {workload_token}"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, headers=headers)
        else:
            auth = (settings.service_client_id, settings.service_client_secret)
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, auth=auth)
        response.raise_for_status()
        body = response.json()
        return str(body["access_token"]), int(body["expires_in"])

    def _read_workload_token(self, settings: GatewaySettings) -> str | None:
        """Read the projected workload token file, if configured (SPEC-009 R-3).

        The kubelet rotates the projected file in place, so it is re-read on
        every exchange. When the file is missing or unreadable the client
        falls back to the static credential and warns once per process.
        """
        path_str = settings.workload_token_path
        if not path_str:
            return None
        try:
            token = Path(path_str).read_text().strip()
        except OSError:
            token = ""
        if token:
            return token
        if not self._workload_fallback_warned:
            LOGGER.warning(
                "workload token unavailable; falling back to the static "
                "service credential",
                extra={"path": path_str},
            )
            self._workload_fallback_warned = True
        return None

    def mint_dev_subject_token(self, settings: GatewaySettings) -> str:
        """Mint a local subject token for the synthetic dev identity (R-4).

        The synthetic identity goes through the same exchange path — the gateway
        signs a short-lived subject token for the dev user and exchanges it, so
        there is no delegation bypass. The broker trusts this issuer in dev.
        """
        key = self._load_dev_key(settings)
        now = int(time.time())
        claims = {
            "iss": settings.identity_token_issuer,
            "sub": "dev",
            "username": settings.dev_user,
            "roles": ["developer"],
            "groups": [],
            "aud": [settings.token_audience],
            "iat": now,
            "exp": now + settings.identity_jwks_cache_seconds,
        }
        return jwt.encode(claims, key, algorithm="RS256")

    def _load_dev_key(self, settings: GatewaySettings) -> rsa.RSAPrivateKey:
        if self._dev_key is not None:
            return self._dev_key
        path_str = settings.dev_signing_key_path
        if path_str:
            path = Path(path_str)
            if path.exists():
                self._dev_key = serialization.load_pem_private_key(
                    path.read_bytes(), password=None
                )
                return self._dev_key
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
            LOGGER.warning("generated dev delegation signing key at %s", path)
            self._dev_key = key
            return key
        # Ephemeral in-memory key (tests / single-replica dev).
        self._dev_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        return self._dev_key


# Module-level singleton (per replica).
_delegation_client = DelegationClient()


def get_delegation_client() -> DelegationClient:
    return _delegation_client


def reset_delegation_state() -> None:
    """Reset module state (for tests)."""
    _delegation_client.reset()


async def obtain_delegated_token(
    settings: GatewaySettings,
    subject: str,
    subject_token: str | None,
) -> str | None:
    """Return a delegated token for the user, or None on any failure.

    Uses the per-user cache first; on a miss, exchanges the supplied subject
    token (minting a dev subject token for the synthetic identity). Failures
    are logged, counted, and swallowed so chat never breaks on delegation.
    """
    client = get_delegation_client()

    cached = client.get_cached(subject)
    if cached is not None:
        return cached

    if not settings.workload_token_path and (
        not settings.service_client_id or not settings.service_client_secret
    ):
        # Delegation is not configured (no workload token path and no static
        # service credential); run tool-less rather than attempting an
        # exchange that cannot authenticate.
        return None

    try:
        token_to_exchange = subject_token or client.mint_dev_subject_token(settings)
        delegated, expires_in = await client.exchange(settings, token_to_exchange)
    except Exception as exc:  # noqa: BLE001 - delegation failure must be non-fatal
        record_delegation_exchange("failure")
        LOGGER.warning(
            "delegation exchange failed; proceeding tool-less",
            extra={"subject": subject, "error": str(exc)},
        )
        return None

    record_delegation_exchange("success")
    client.put(subject, delegated, expires_in)
    return delegated
