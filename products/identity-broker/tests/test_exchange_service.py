"""Tests for broker-mediated token delegation (SPEC-008 R-2/R-3)."""

from __future__ import annotations

import base64
import unittest

import jwt as pyjwt
from fastapi.testclient import TestClient

from identity_service.app import create_app
from identity_service.core.config import IdentitySettings, ServiceClient, get_settings
from identity_service.services.exchange_service import ExchangeError, exchange_token
from identity_service.services.token_service import issue_token, reset_key_state


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


if __name__ == "__main__":
    unittest.main()
