"""Contract alignment: issued tokens conform to identity-token.schema.json (SPEC-008 R-7).

The identity-broker is the sole signing authority, so its emitted claim sets —
both portal tokens and delegated tokens — must validate against the shared
identity-token schema. This binds the issuer to the contract the gateway
verifies against.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import jsonschema
import jwt as pyjwt

from identity_service.core.config import IdentitySettings, ServiceClient
from identity_service.services import exchange_service
from identity_service.services.token_service import issue_token, reset_key_state

SCHEMAS_DIR = (
    Path(__file__).resolve().parents[3] / "shared" / "shared-contracts" / "schemas"
)


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / name).read_text())


def _settings(**overrides) -> IdentitySettings:
    defaults = {
        "jwt_private_key_path": None,
        "jwt_token_ttl_seconds": 900,
        "jwt_issuer": "luban-identity-broker",
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


_IDENTITY = {
    "sub": "user-1",
    "username": "alice",
    "email": "alice@example.com",
    "roles": ["operator"],
    "groups": ["ops-operators"],
}


class IssuedTokenContractTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_key_state()

    def test_portal_token_conforms_to_schema(self) -> None:
        settings = _settings()
        token, _ = issue_token(settings, _IDENTITY)
        claims = pyjwt.decode(token, options={"verify_signature": False})

        jsonschema.validate(claims, _load_schema("identity-token.schema.json"))
        # Portal tokens are audience-bound to the gateway and carry no actor.
        self.assertEqual(claims["aud"], ["tool-gateway"])
        self.assertNotIn("act", claims)

    def test_delegated_token_conforms_to_schema(self) -> None:
        settings = _settings()
        delegated_token, _ = exchange_service.exchange_token(
            settings,
            client_id="tool-gateway",
            client_secret="gw-secret",
            subject_token=issue_token(settings, _IDENTITY)[0],
            audience="tool-gateway",
        )
        claims = pyjwt.decode(
            delegated_token, options={"verify_signature": False}
        )

        jsonschema.validate(claims, _load_schema("identity-token.schema.json"))
        # Delegated tokens carry the actor claim and the requested audience.
        self.assertEqual(claims["act"], {"sub": "tool-gateway"})
        self.assertEqual(claims["aud"], ["tool-gateway"])
        self.assertEqual(claims["sub"], "user-1")
        self.assertEqual(claims["roles"], ["operator"])


if __name__ == "__main__":
    unittest.main()
