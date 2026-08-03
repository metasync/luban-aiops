"""Tests for broker-mediated token delegation (SPEC-008 R-2/R-3).

Workload-identity tests (SPEC-009 R-3) cover the projected service-account
token path: OIDC discovery is patched so no network is touched.
"""

from __future__ import annotations

import base64
import time
import unittest
from unittest.mock import patch

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from identity_service.app import create_app
from identity_service.core.config import (
    IdentitySettings,
    ServiceClient,
    WorkloadClient,
    get_settings,
)
from identity_service.services import exchange_service
from identity_service.services.exchange_service import ExchangeError, exchange_token
from identity_service.services.token_service import issue_token, reset_key_state

_CLUSTER_ISSUER = "https://cluster.example/oidc"
_SA_SUBJECT = "system:serviceaccount:prod-luban:api-gateway"
_CLUSTER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _settings(**overrides) -> IdentitySettings:
    defaults = {
        "jwt_private_key_path": None,
        "jwt_token_ttl_seconds": 900,
        "jwt_issuer": "luban-identity-broker",
        "jwt_audience": "tool-gateway",
        "delegated_token_ttl_seconds": 300,
        "service_clients": (
            ServiceClient(
                client_id="tool-gateway",
                secret="gw-secret",
                allowed_audiences=("tool-gateway",),
            ),
        ),
    }
    defaults.update(overrides)
    return IdentitySettings(**defaults)


def _basic(client_id: str, secret: str) -> str:
    raw = f"{client_id}:{secret}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


class ExchangeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_key_state()

    def tearDown(self) -> None:
        reset_key_state()

    def _subject_token(self, settings: IdentitySettings, **overrides) -> str:
        identity = {
            "sub": "user-1",
            "username": "alice",
            "email": "alice@example.com",
            "roles": ["operator"],
            "groups": ["ops-operators"],
        }
        identity.update(overrides)
        token, _ = issue_token(settings, identity)
        return token

    def test_exchange_mints_delegated_token(self) -> None:
        settings = _settings()
        subject = self._subject_token(settings)

        token, expires_in = exchange_token(
            settings, "tool-gateway", "gw-secret", subject, "tool-gateway"
        )

        self.assertEqual(expires_in, 300)
        claims = pyjwt.decode(token, options={"verify_signature": False})
        self.assertEqual(claims["sub"], "user-1")
        self.assertEqual(claims["username"], "alice")
        self.assertEqual(claims["roles"], ["operator"])
        self.assertEqual(claims["aud"], ["tool-gateway"])
        self.assertEqual(claims["act"], {"sub": "tool-gateway"})
        self.assertEqual(claims["iss"], "luban-identity-broker")
        self.assertEqual(claims["exp"] - claims["iat"], 300)

    def test_missing_credential_rejected(self) -> None:
        settings = _settings()
        subject = self._subject_token(settings)
        with self.assertRaises(ExchangeError) as ctx:
            exchange_token(settings, None, None, subject, "tool-gateway")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_invalid_credential_rejected(self) -> None:
        settings = _settings()
        subject = self._subject_token(settings)
        with self.assertRaises(ExchangeError) as ctx:
            exchange_token(settings, "tool-gateway", "wrong", subject, "tool-gateway")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_invalid_subject_token_rejected(self) -> None:
        settings = _settings()
        with self.assertRaises(ExchangeError) as ctx:
            exchange_token(
                settings, "tool-gateway", "gw-secret", "not.a.jwt", "tool-gateway"
            )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_expired_subject_token_rejected(self) -> None:
        settings = _settings(jwt_token_ttl_seconds=-10)
        subject = self._subject_token(settings)
        with self.assertRaises(ExchangeError) as ctx:
            exchange_token(
                settings, "tool-gateway", "gw-secret", subject, "tool-gateway"
            )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_disallowed_audience_rejected(self) -> None:
        settings = _settings()
        subject = self._subject_token(settings)
        with self.assertRaises(ExchangeError) as ctx:
            exchange_token(
                settings, "tool-gateway", "gw-secret", subject, "agent-platform"
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_roles_never_elevated(self) -> None:
        settings = _settings()
        subject = self._subject_token(settings, roles=["read-only-observer"])
        token, _ = exchange_token(
            settings, "tool-gateway", "gw-secret", subject, "tool-gateway"
        )
        claims = pyjwt.decode(token, options={"verify_signature": False})
        self.assertEqual(claims["roles"], ["read-only-observer"])


class ExchangeRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_key_state()
        self.settings = _settings()
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: self.settings
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_key_state()

    def _subject_token(self) -> str:
        token, _ = issue_token(
            self.settings,
            {
                "sub": "user-1",
                "username": "alice",
                "roles": ["operator"],
                "groups": ["ops-operators"],
            },
        )
        return token

    def test_exchange_endpoint_success(self) -> None:
        response = self.client.post(
            "/api/v1/auth/exchange",
            json={"subject_token": self._subject_token(), "audience": "tool-gateway"},
            headers={"Authorization": _basic("tool-gateway", "gw-secret")},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["token_type"], "Bearer")
        self.assertEqual(body["expires_in"], 300)
        claims = pyjwt.decode(body["access_token"], options={"verify_signature": False})
        self.assertEqual(claims["act"], {"sub": "tool-gateway"})
        self.assertEqual(claims["aud"], ["tool-gateway"])

    def test_exchange_endpoint_missing_credential_returns_401(self) -> None:
        response = self.client.post(
            "/api/v1/auth/exchange",
            json={"subject_token": self._subject_token(), "audience": "tool-gateway"},
        )
        self.assertEqual(response.status_code, 401)

    def test_exchange_endpoint_invalid_subject_returns_401(self) -> None:
        response = self.client.post(
            "/api/v1/auth/exchange",
            json={"subject_token": "not.a.jwt", "audience": "tool-gateway"},
            headers={"Authorization": _basic("tool-gateway", "gw-secret")},
        )
        self.assertEqual(response.status_code, 401)

    def test_exchange_endpoint_disallowed_audience_returns_400(self) -> None:
        response = self.client.post(
            "/api/v1/auth/exchange",
            json={"subject_token": self._subject_token(), "audience": "agent-platform"},
            headers={"Authorization": _basic("tool-gateway", "gw-secret")},
        )
        self.assertEqual(response.status_code, 400)


def _workload_settings(**overrides) -> IdentitySettings:
    defaults = {
        "jwt_private_key_path": None,
        "jwt_issuer": "luban-identity-broker",
        "jwt_audience": "tool-gateway",
        "delegated_token_ttl_seconds": 300,
        "service_clients": (
            ServiceClient(
                client_id="tool-gateway",
                secret="gw-secret",
                allowed_audiences=("tool-gateway",),
            ),
        ),
        "workload_issuer_url": _CLUSTER_ISSUER,
        "workload_audience": "identity-broker",
        "workload_clients": (
            WorkloadClient(
                workload_subject=_SA_SUBJECT,
                client_id="tool-gateway",
                allowed_audiences=("tool-gateway",),
            ),
        ),
    }
    defaults.update(overrides)
    return IdentitySettings(**defaults)


def _mint_workload_token(**overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": _CLUSTER_ISSUER,
        "sub": _SA_SUBJECT,
        "aud": ["identity-broker"],
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    return pyjwt.encode(claims, _CLUSTER_KEY, algorithm="RS256")


def _patch_discovery():
    """Patch OIDC discovery; PyJWKClient fetches the patched jwks_uri."""
    fake_response = type(
        "FakeResponse", (), {"json": staticmethod(lambda: {"jwks_uri": "https://fake/jwks"})}
    )()
    return patch.object(
        exchange_service.httpx, "get", return_value=fake_response
    )


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
        exchange_service, "_get_workload_jwks_client", return_value=fake_client
    )


class WorkloadExchangeServiceTests(unittest.TestCase):
    """Workload-token branch of the exchange (SPEC-009 R-3)."""

    def setUp(self) -> None:
        reset_key_state()
        exchange_service.reset_workload_state()

    def tearDown(self) -> None:
        reset_key_state()
        exchange_service.reset_workload_state()

    def _subject_token(self, settings: IdentitySettings) -> str:
        token, _ = issue_token(
            settings,
            {
                "sub": "user-1",
                "username": "alice",
                "roles": ["operator"],
                "groups": ["ops-operators"],
            },
        )
        return token

    def test_workload_token_mints_same_claims_as_static_path(self) -> None:
        settings = _workload_settings()
        subject = self._subject_token(settings)
        with _patch_jwks_client():
            token, expires_in = exchange_token(
                settings,
                None,
                None,
                subject,
                "tool-gateway",
                workload_token=_mint_workload_token(),
            )
        self.assertEqual(expires_in, 300)
        claims = pyjwt.decode(token, options={"verify_signature": False})
        self.assertEqual(claims["sub"], "user-1")
        self.assertEqual(claims["username"], "alice")
        self.assertEqual(claims["roles"], ["operator"])
        self.assertEqual(claims["aud"], ["tool-gateway"])
        self.assertEqual(claims["act"], {"sub": "tool-gateway"})

    def test_expired_workload_token_rejected(self) -> None:
        settings = _workload_settings()
        subject = self._subject_token(settings)
        now = int(time.time())
        with _patch_jwks_client(), self.assertRaises(ExchangeError) as ctx:
            exchange_token(
                settings,
                None,
                None,
                subject,
                "tool-gateway",
                workload_token=_mint_workload_token(exp=now - 10, iat=now - 70),
            )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_audience_workload_token_rejected(self) -> None:
        settings = _workload_settings()
        subject = self._subject_token(settings)
        with _patch_jwks_client(), self.assertRaises(ExchangeError) as ctx:
            exchange_token(
                settings,
                None,
                None,
                subject,
                "tool-gateway",
                workload_token=_mint_workload_token(aud=["other-service"]),
            )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_unregistered_workload_subject_rejected(self) -> None:
        settings = _workload_settings()
        subject = self._subject_token(settings)
        with _patch_jwks_client(), self.assertRaises(ExchangeError) as ctx:
            exchange_token(
                settings,
                None,
                None,
                subject,
                "tool-gateway",
                workload_token=_mint_workload_token(
                    sub="system:serviceaccount:prod-luban:rogue"
                ),
            )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_workload_branch_disabled_when_issuer_unset(self) -> None:
        settings = _workload_settings(workload_issuer_url="")
        subject = self._subject_token(settings)
        with self.assertRaises(ExchangeError) as ctx:
            exchange_token(
                settings,
                None,
                None,
                subject,
                "tool-gateway",
                workload_token=_mint_workload_token(),
            )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_disallowed_audience_rejected_on_workload_path(self) -> None:
        settings = _workload_settings()
        subject = self._subject_token(settings)
        with _patch_jwks_client(), self.assertRaises(ExchangeError) as ctx:
            exchange_token(
                settings,
                None,
                None,
                subject,
                "agent-platform",
                workload_token=_mint_workload_token(),
            )
        self.assertEqual(ctx.exception.status_code, 400)


class WorkloadExchangeRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_key_state()
        exchange_service.reset_workload_state()
        self.settings = _workload_settings()
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: self.settings
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_key_state()
        exchange_service.reset_workload_state()

    def _subject_token(self) -> str:
        token, _ = issue_token(
            self.settings,
            {
                "sub": "user-1",
                "username": "alice",
                "roles": ["operator"],
                "groups": ["ops-operators"],
            },
        )
        return token

    def test_exchange_endpoint_accepts_bearer_workload_token(self) -> None:
        with _patch_jwks_client():
            response = self.client.post(
                "/api/v1/auth/exchange",
                json={
                    "subject_token": self._subject_token(),
                    "audience": "tool-gateway",
                },
                headers={"Authorization": f"Bearer {_mint_workload_token()}"},
            )
        self.assertEqual(response.status_code, 200)
        claims = pyjwt.decode(
            response.json()["access_token"], options={"verify_signature": False}
        )
        self.assertEqual(claims["act"], {"sub": "tool-gateway"})

    def test_exchange_endpoint_rejects_unregistered_bearer_token(self) -> None:
        with _patch_jwks_client():
            response = self.client.post(
                "/api/v1/auth/exchange",
                json={
                    "subject_token": self._subject_token(),
                    "audience": "tool-gateway",
                },
                headers={
                    "Authorization": "Bearer "
                    + _mint_workload_token(sub="system:serviceaccount:prod-luban:rogue")
                },
            )
        self.assertEqual(response.status_code, 401)

    def test_discovery_fetched_from_configured_issuer(self) -> None:
        """The JWKS client is built from the issuer's discovery document."""
        exchange_service._workload_jwks_clients.clear()
        with _patch_discovery() as mock_get, patch.object(
            pyjwt, "PyJWKClient"
        ) as mock_jwks_cls:
            exchange_service._get_workload_jwks_client(self.settings)
        mock_get.assert_called_once_with(
            f"{_CLUSTER_ISSUER}/.well-known/openid-configuration", timeout=5.0
        )
        mock_jwks_cls.assert_called_once_with("https://fake/jwks", cache_keys=True)


if __name__ == "__main__":
    unittest.main()
