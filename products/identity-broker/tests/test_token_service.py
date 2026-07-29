"""Tests for identity_service.services.token_service (R-1: JWT issuer + JWKS)."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

import jwt as pyjwt

from identity_service.core.config import IdentitySettings
from identity_service.services.token_service import (
    issue_token,
    jwks_response,
    reset_key_state,
)


def _settings(**overrides) -> IdentitySettings:
    defaults = {
        "jwt_private_key_path": None,
        "jwt_token_ttl_seconds": 900,
        "jwt_issuer": "luban-identity-broker",
    }
    defaults.update(overrides)
    return IdentitySettings(**defaults)


class TokenIssuanceTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_key_state()

    def test_issue_token_returns_valid_jwt(self) -> None:
        settings = _settings()
        identity = {
            "sub": "user-1",
            "username": "alice",
            "email": "alice@example.com",
            "roles": ["operator"],
            "groups": ["ops-operators"],
        }
        token, expires_in = issue_token(settings, identity)

        self.assertEqual(expires_in, 900)
        self.assertTrue(token.startswith("eyJ"))

        # Decode without verification to inspect claims.
        claims = pyjwt.decode(token, options={"verify_signature": False})
        self.assertEqual(claims["iss"], "luban-identity-broker")
        self.assertEqual(claims["sub"], "user-1")
        self.assertEqual(claims["username"], "alice")
        self.assertEqual(claims["roles"], ["operator"])
        self.assertIn("iat", claims)
        self.assertIn("exp", claims)
        self.assertEqual(claims["exp"] - claims["iat"], 900)

    def test_issue_token_custom_ttl(self) -> None:
        settings = _settings(jwt_token_ttl_seconds=300)
        token, expires_in = issue_token(settings, {"sub": "u", "username": "u"})
        self.assertEqual(expires_in, 300)
        claims = pyjwt.decode(token, options={"verify_signature": False})
        self.assertEqual(claims["exp"] - claims["iat"], 300)

    def test_kid_header_present(self) -> None:
        settings = _settings()
        token, _ = issue_token(settings, {"sub": "u", "username": "u"})
        header = pyjwt.get_unverified_header(token)
        self.assertEqual(header["alg"], "RS256")
        self.assertIn("kid", header)
        self.assertTrue(len(header["kid"]) > 0)


class JwksTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_key_state()

    def test_jwks_response_format(self) -> None:
        settings = _settings()
        # Ensure key is initialized.
        issue_token(settings, {"sub": "u", "username": "u"})

        jwks = jwks_response(settings)
        self.assertIn("keys", jwks)
        self.assertEqual(len(jwks["keys"]), 1)

        key_entry = jwks["keys"][0]
        self.assertEqual(key_entry["kty"], "RSA")
        self.assertEqual(key_entry["use"], "sig")
        self.assertEqual(key_entry["alg"], "RS256")
        self.assertIn("kid", key_entry)
        self.assertIn("n", key_entry)
        self.assertIn("e", key_entry)

    def test_jwks_kid_matches_token_header(self) -> None:
        settings = _settings()
        token, _ = issue_token(settings, {"sub": "u", "username": "u"})
        header = pyjwt.get_unverified_header(token)
        jwks = jwks_response(settings)
        self.assertEqual(header["kid"], jwks["keys"][0]["kid"])


class KeyPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_key_state()

    def tearDown(self) -> None:
        reset_key_state()

    def test_key_persisted_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            key_path = str(Path(tmp) / "sub" / "private.pem")
            settings = _settings(jwt_private_key_path=key_path)

            # First call generates and writes.
            token1, _ = issue_token(settings, {"sub": "u", "username": "u"})
            self.assertTrue(Path(key_path).exists())

            # Reset and reload — should produce same kid (same key).
            reset_key_state()
            jwks1 = jwks_response(settings)

            reset_key_state()
            token2, _ = issue_token(settings, {"sub": "u", "username": "u"})
            jwks2 = jwks_response(settings)

            self.assertEqual(jwks1["keys"][0]["kid"], jwks2["keys"][0]["kid"])

    def test_ephemeral_key_no_file(self) -> None:
        settings = _settings(jwt_private_key_path=None)
        token, _ = issue_token(settings, {"sub": "u", "username": "u"})
        self.assertTrue(token.startswith("eyJ"))


if __name__ == "__main__":
    unittest.main()
