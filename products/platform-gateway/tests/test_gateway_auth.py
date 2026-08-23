"""Gateway identity tests (SPEC-003: local JWT verification + synthetic dev identity)."""

import unittest
from unittest.mock import patch

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from platform_gateway.app import create_app
from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.schemas.api import IdentityContext
from platform_gateway.services import token_verifier
from platform_gateway.services.gateway_service import resolve_request_identity
from platform_gateway.services.token_verifier import TokenVerificationError, verify_token


class ResolveRequestIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_unauthenticated_when_required(self) -> None:
        request = Request({"type": "http", "headers": []})

        with self.assertRaises(HTTPException) as ctx:
            await resolve_request_identity(
                PlatformGatewaySettings(require_auth=True),
                request,
                "req-123",
            )

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("authentication required", ctx.exception.detail)

    async def test_returns_synthetic_identity_when_optional(self) -> None:
        request = Request({"type": "http", "headers": []})

        identity = await resolve_request_identity(
            PlatformGatewaySettings(require_auth=False, dev_user="test.dev"),
            request,
            "req-123",
        )

        self.assertIsNotNone(identity)
        self.assertEqual(identity.username, "test.dev")
        self.assertEqual(identity.subject, "dev")
        self.assertEqual(identity.roles, ["developer"])

    async def test_rejects_malformed_authorization_header(self) -> None:
        request = Request(
            {"type": "http", "headers": [(b"authorization", b"Basic abc123")]}
        )

        with self.assertRaises(HTTPException) as ctx:
            await resolve_request_identity(
                PlatformGatewaySettings(require_auth=True),
                request,
                "req-123",
            )

        self.assertEqual(ctx.exception.status_code, 401)

    async def test_rejects_invalid_token(self) -> None:
        request = Request(
            {"type": "http", "headers": [(b"authorization", b"Bearer invalid.token.here")]}
        )

        with patch(
            "platform_gateway.services.gateway_service.verify_token",
            side_effect=TokenVerificationError("unable to resolve signing key"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await resolve_request_identity(
                    PlatformGatewaySettings(require_auth=True),
                    request,
                    "req-123",
                )

        self.assertEqual(ctx.exception.status_code, 401)

    async def test_returns_verified_identity_for_valid_token(self) -> None:
        expected = IdentityContext(
            subject="user-1",
            username="alice",
            roles=["operator"],
            groups=["ops-operators"],
        )
        request = Request(
            {"type": "http", "headers": [(b"authorization", b"Bearer valid.jwt.token")]}
        )

        with patch(
            "platform_gateway.services.gateway_service.verify_token",
            return_value=expected,
        ):
            identity = await resolve_request_identity(
                PlatformGatewaySettings(require_auth=True),
                request,
                "req-123",
            )

        self.assertEqual(identity.username, "alice")
        self.assertEqual(identity.roles, ["operator"])


class RequiredAuthRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: PlatformGatewaySettings(
            require_auth=True
        )
        self.client = TestClient(app)

    def test_create_session_unauthenticated_returns_401(self) -> None:
        response = self.client.post("/api/v1/sessions", json={})
        self.assertEqual(response.status_code, 401)

    def test_get_session_unauthenticated_returns_401(self) -> None:
        response = self.client.get("/api/v1/sessions/ses-123")
        self.assertEqual(response.status_code, 401)

    def test_chat_unauthenticated_returns_401(self) -> None:
        response = self.client.post("/api/v1/chat", json={"message": "hello"})
        self.assertEqual(response.status_code, 401)

    def test_chat_stream_unauthenticated_returns_401(self) -> None:
        response = self.client.get("/api/v1/chat/stream", params={"message": "hello"})
        self.assertEqual(response.status_code, 401)


class RolePropagationTests(unittest.TestCase):
    def test_chat_log_event_includes_roles_and_authenticated_user(self) -> None:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: PlatformGatewaySettings(
            require_auth=True
        )
        identity = IdentityContext(
            subject="user-123",
            username="alice",
            roles=["operator"],
        )

        async def fake_identity(settings, request, request_id):
            return identity

        async def fake_chat(
            settings,
            request_id,
            user_id,
            message,
            session_id,
            delegated_token=None,
            input_modality="text",
            model=None,
        ):
            return {
                "session_id": "ses-1",
                "request_id": request_id,
                "content": "done",
                "status": "ok",
            }

        with (
            patch(
                "platform_gateway.api.routes.chat.resolve_request_identity",
                fake_identity,
            ),
            patch("platform_gateway.api.routes.chat.chat", fake_chat),
            self.assertLogs("platform_gateway.api.routes.chat", level="INFO") as logs,
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/chat",
                json={"message": "hi"},
            )

        self.assertEqual(response.status_code, 200)
        chat_events = [line for line in logs.output if "chat_completed" in line]
        self.assertTrue(chat_events)
        self.assertIn('"roles": ["operator"]', chat_events[0])
        self.assertIn('"user_id": "alice"', chat_events[0])


class TokenAudienceEnforcementTests(unittest.TestCase):
    """R-1: verify_token enforces the configured audience."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self) -> None:
        token_verifier.reset_verifier_state()

    def tearDown(self) -> None:
        token_verifier.reset_verifier_state()

    def _mint(self, **claims) -> str:
        payload = {
            "iss": "luban-identity-broker",
            "sub": "user-1",
            "username": "alice",
            "roles": ["operator"],
            "aud": ["tool-gateway"],
            "iat": 1_000_000,
            "exp": 9_999_999_999,
        }
        payload.update(claims)
        return pyjwt.encode(payload, self._key, algorithm="RS256")

    def _verify(self, token: str) -> IdentityContext:
        settings = PlatformGatewaySettings(token_audience="tool-gateway")
        public_key = self._key.public_key()
        fake_client = type(
            "FakeClient",
            (),
            {
                "get_signing_key_from_jwt": lambda _self, _t: type(
                    "K", (), {"key": public_key}
                )()
            },
        )()
        with patch.object(
            token_verifier, "_get_jwks_client", return_value=fake_client
        ):
            return verify_token(settings, token)

    def test_valid_audience_is_accepted(self) -> None:
        identity = self._verify(self._mint())
        self.assertEqual(identity.subject, "user-1")
        self.assertEqual(identity.roles, ["operator"])

    def test_wrong_audience_is_rejected(self) -> None:
        with self.assertRaises(TokenVerificationError) as ctx:
            self._verify(self._mint(aud=["other-service"]))
        self.assertIn("audience", ctx.exception.detail)

    def test_missing_audience_is_rejected(self) -> None:
        # Mint a token without the aud claim.
        payload = {
            "iss": "luban-identity-broker",
            "sub": "user-1",
            "username": "alice",
            "roles": ["operator"],
            "iat": 1_000_000,
            "exp": 9_999_999_999,
        }
        token = pyjwt.encode(payload, self._key, algorithm="RS256")
        with self.assertRaises(TokenVerificationError):
            self._verify(token)


if __name__ == "__main__":
    unittest.main()
