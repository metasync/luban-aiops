"""Ingest/query caller authentication tests (SPEC-013 R-3).

Covers the static HTTP Basic registry path, the header parsing, the workload
bearer path's not-enabled guard, and the full projected-token ladder against
a locally minted RS256 token (mirroring identity-broker's workload tests,
since this module deliberately reuses that vocabulary).
"""

from __future__ import annotations

import asyncio
import base64
import time
import unittest
from unittest.mock import patch

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa

import audit_service.services.ingest_auth as ingest_auth
from audit_service.core.config import AuditSettings, IngestClient, WorkloadClient
from audit_service.services.ingest_auth import (
    IngestAuthError,
    _parse_basic,
    authenticate_caller,
    authenticate_static,
    authenticate_workload,
)


def _settings(**overrides) -> AuditSettings:
    defaults = {
        "ingest_clients": (
            IngestClient(client_id="tool-gateway", secret="tg-secret"),
            IngestClient(client_id="platform-gateway", secret="pg-secret"),
        ),
    }
    defaults.update(overrides)
    return AuditSettings(**defaults)


class _FakeRequest:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


def _basic(client_id: str, secret: str) -> str:
    raw = f"{client_id}:{secret}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


class AuthenticateStaticTests(unittest.TestCase):
    def test_valid_credential_returns_client_id(self) -> None:
        settings = _settings()
        self.assertEqual(
            authenticate_static(settings, "tool-gateway", "tg-secret"),
            "tool-gateway",
        )

    def test_wrong_secret_rejected(self) -> None:
        settings = _settings()
        with self.assertRaises(IngestAuthError):
            authenticate_static(settings, "tool-gateway", "bad")

    def test_unknown_client_rejected(self) -> None:
        settings = _settings()
        with self.assertRaises(IngestAuthError):
            authenticate_static(settings, "intruder", "tg-secret")

    def test_missing_credential_rejected(self) -> None:
        settings = _settings()
        with self.assertRaises(IngestAuthError):
            authenticate_static(settings, None, None)


class ParseBasicTests(unittest.TestCase):
    def test_parses_valid_header(self) -> None:
        header = base64.b64encode(b"tool-gateway:tg-secret").decode()
        self.assertEqual(_parse_basic(header), ("tool-gateway", "tg-secret"))

    def test_invalid_base64_returns_nones(self) -> None:
        self.assertEqual(_parse_basic("!!!not-base64!!!"), (None, None))


class AuthenticateCallerTests(unittest.TestCase):
    def test_basic_header_resolves_client(self) -> None:
        settings = _settings()
        request = _FakeRequest({"authorization": _basic("platform-gateway", "pg-secret")})
        client_id = asyncio.run(authenticate_caller(settings, request))
        self.assertEqual(client_id, "platform-gateway")

    def test_missing_authorization_rejected(self) -> None:
        settings = _settings()
        request = _FakeRequest({})
        with self.assertRaises(IngestAuthError):
            asyncio.run(authenticate_caller(settings, request))

    def test_bad_basic_rejected(self) -> None:
        settings = _settings()
        request = _FakeRequest({"authorization": _basic("tool-gateway", "wrong")})
        with self.assertRaises(IngestAuthError):
            asyncio.run(authenticate_caller(settings, request))

    def test_unsupported_scheme_rejected(self) -> None:
        settings = _settings()
        request = _FakeRequest({"authorization": "Digest abc"})
        with self.assertRaises(IngestAuthError):
            asyncio.run(authenticate_caller(settings, request))


class AuthenticateWorkloadTests(unittest.TestCase):
    def test_workload_not_enabled_rejected(self) -> None:
        settings = _settings(workload_issuer_url="")
        with self.assertRaises(IngestAuthError):
            authenticate_workload(settings, "some-bearer-token")

    def test_bearer_routes_to_workload_path_and_fails_when_disabled(self) -> None:
        settings = _settings(workload_issuer_url="")
        request = _FakeRequest({"authorization": "Bearer abc.def.ghi"})
        with self.assertRaises(IngestAuthError):
            asyncio.run(authenticate_caller(settings, request))


_CLUSTER_ISSUER = "https://cluster.example/oidc"
_SA_SUBJECT = "system:serviceaccount:dev-luban-aiops:skills-hub"
_CLUSTER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _workload_settings(**overrides) -> AuditSettings:
    defaults = {
        "workload_issuer_url": _CLUSTER_ISSUER,
        "workload_audience": "audit-service",
        "workload_clients": (
            WorkloadClient(workload_subject=_SA_SUBJECT, client_id="skills-hub"),
        ),
    }
    defaults.update(overrides)
    return _settings(**defaults)


def _mint_workload_token(**overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": _CLUSTER_ISSUER,
        "sub": _SA_SUBJECT,
        "aud": ["audit-service"],
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    return pyjwt.encode(claims, _CLUSTER_KEY, algorithm="RS256")


def _patch_jwks_client():
    public_key = _CLUSTER_KEY.public_key()
    fake_client = type(
        "FakeClient",
        (),
        {
            "get_signing_key_from_jwt": lambda _self, _t: type(
                "K", (), {"key": public_key}
            )()
        },
    )()
    return patch.object(
        ingest_auth, "_get_workload_jwks_client", return_value=fake_client
    )


class WorkloadTokenLadderTests(unittest.TestCase):
    """Projected-token validation ladder with a locally minted RS256 token."""

    def setUp(self) -> None:
        ingest_auth.reset_workload_state()

    def tearDown(self) -> None:
        ingest_auth.reset_workload_state()

    def test_valid_token_maps_to_registered_client(self) -> None:
        with _patch_jwks_client():
            client_id = authenticate_workload(
                _workload_settings(), _mint_workload_token()
            )
        self.assertEqual(client_id, "skills-hub")

    def test_expired_token_rejected(self) -> None:
        now = int(time.time())
        token = _mint_workload_token(exp=now - 10, iat=now - 70)
        with _patch_jwks_client(), self.assertRaises(IngestAuthError) as ctx:
            authenticate_workload(_workload_settings(), token)
        self.assertIn("expired", str(ctx.exception))

    def test_wrong_audience_rejected(self) -> None:
        token = _mint_workload_token(aud=["some-other-service"])
        with _patch_jwks_client(), self.assertRaises(IngestAuthError) as ctx:
            authenticate_workload(_workload_settings(), token)
        self.assertIn("invalid", str(ctx.exception))

    def test_wrong_issuer_rejected(self) -> None:
        token = _mint_workload_token(iss="https://evil.example")
        with _patch_jwks_client(), self.assertRaises(IngestAuthError):
            authenticate_workload(_workload_settings(), token)

    def test_unregistered_subject_rejected(self) -> None:
        token = _mint_workload_token(sub="system:serviceaccount:other:unknown")
        with _patch_jwks_client(), self.assertRaises(IngestAuthError) as ctx:
            authenticate_workload(_workload_settings(), token)
        self.assertIn("not registered", str(ctx.exception))

    def test_bearer_header_routes_to_workload_path(self) -> None:
        request = _FakeRequest(
            {"authorization": f"Bearer {_mint_workload_token()}"}
        )
        with _patch_jwks_client():
            client_id = asyncio.run(
                authenticate_caller(_workload_settings(), request)
            )
        self.assertEqual(client_id, "skills-hub")


class WorkloadJwksDiscoveryTests(unittest.TestCase):
    """JWKS resolution over OIDC discovery, with per-issuer caching."""

    def setUp(self) -> None:
        ingest_auth.reset_workload_state()

    def tearDown(self) -> None:
        ingest_auth.reset_workload_state()

    def test_discovery_resolves_and_caches_jwks_client(self) -> None:
        fake_response = type(
            "FakeResponse",
            (),
            {"json": staticmethod(lambda: {"jwks_uri": "https://fake/jwks"})},
        )()
        settings = _workload_settings()
        with patch.object(
            ingest_auth.httpx, "get", return_value=fake_response
        ) as fake_get:
            first = ingest_auth._get_workload_jwks_client(settings)
            second = ingest_auth._get_workload_jwks_client(settings)
        self.assertIs(first, second)
        fake_get.assert_called_once()
        self.assertIn(
            "/.well-known/openid-configuration", fake_get.call_args[0][0]
        )
        ingest_auth.reset_workload_state()
        with patch.object(
            ingest_auth.httpx, "get", return_value=fake_response
        ) as fake_get_again:
            ingest_auth._get_workload_jwks_client(settings)
        fake_get_again.assert_called_once()


if __name__ == "__main__":
    unittest.main()
