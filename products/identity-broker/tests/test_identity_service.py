import unittest
from unittest.mock import patch

from identity_service.core.config import IdentitySettings
from identity_service.core.runtime import IdentityRunSettings
from identity_service.schemas.auth import AuthorizationCodeExchangeRequest, LogoutRequest, TokenRefreshRequest
from identity_service.schemas.identity import ClaimsPayload
from identity_service.services.identity_service import (
    build_login_start,
    build_logout_response,
    exchange_authorization_code,
    fetch_identity_from_authorization,
    normalize_identity,
    normalize_userinfo,
    refresh_session,
    resolve_roles,
)


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.status_code = 200

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        return None


class FakeAsyncClient:
    def __init__(self, token_payload: dict | None = None, userinfo_payload: dict | None = None) -> None:
        self.token_payload = token_payload or {}
        self.userinfo_payload = userinfo_payload or {}
        self.posts: list[dict] = []
        self.gets: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, data: dict | None = None, headers: dict | None = None):
        self.posts.append({"url": url, "data": data or {}, "headers": headers or {}})
        return FakeResponse(self.token_payload)

    async def get(self, url: str, headers: dict | None = None):
        self.gets.append({"url": url, "headers": headers or {}})
        return FakeResponse(self.userinfo_payload)


class IdentityServiceTests(unittest.TestCase):
    def test_resolve_roles_returns_default_observer_role(self) -> None:
        self.assertEqual(resolve_roles(["unknown-group"]), ["read-only-observer"])

    def test_resolve_roles_maps_known_groups(self) -> None:
        self.assertEqual(
            resolve_roles(["ops-approvers", "ops-admins"]),
            ["approver", "platform-admin"],
        )

    def test_build_login_start_uses_settings(self) -> None:
        payload = build_login_start(
            IdentitySettings(
                keycloak_base_url="https://sso.example.com",
                keycloak_realm="luban-local",
                oidc_client_id="portal-client",
                oidc_scopes="openid groups",
                oidc_redirect_uri="http://localhost:8080/callback",
            )
        )

        self.assertIn("https://sso.example.com/realms/luban-local", payload.authorization_url)
        self.assertIn("client_id=portal-client", payload.authorization_url)
        self.assertIn("scope=openid+groups", payload.authorization_url)
        self.assertIn("code_challenge=", payload.authorization_url)
        self.assertEqual(payload.redirect_uri, "http://localhost:8080/callback")

    def test_normalize_identity_returns_expected_context(self) -> None:
        result = normalize_identity(
            ClaimsPayload(
                sub="user-123",
                preferred_username="alice",
                email="alice@example.com",
                groups=["ops-operators"],
            )
        )

        self.assertEqual(result.subject, "user-123")
        self.assertEqual(result.username, "alice")
        self.assertEqual(result.roles, ["operator"])

    def test_normalize_userinfo_uses_profile_claims(self) -> None:
        result = normalize_userinfo(
            {
                "sub": "user-123",
                "preferred_username": "alice",
                "email": "alice@example.com",
                "groups": ["ops-admins"],
            }
        )

        self.assertEqual(result.username, "alice")
        self.assertEqual(result.roles, ["platform-admin"])

    def test_build_logout_response_uses_defaults(self) -> None:
        payload = build_logout_response(
            IdentitySettings(
                keycloak_base_url="https://sso.example.com",
                keycloak_realm="luban-local",
                oidc_client_id="portal-client",
                oidc_post_logout_redirect_uri="http://localhost:8080/",
            ),
            LogoutRequest(id_token_hint="id-token"),
        )

        self.assertIn("protocol/openid-connect/logout", payload.logout_url)
        self.assertIn("id_token_hint=id-token", payload.logout_url)
        self.assertIn("client_id=portal-client", payload.logout_url)

    def test_identity_run_settings_read_env(self) -> None:
        import os

        old_host = os.environ.get("IDENTITY_SERVICE_HOST")
        old_port = os.environ.get("IDENTITY_SERVICE_PORT")
        os.environ["IDENTITY_SERVICE_HOST"] = "127.0.0.1"
        os.environ["IDENTITY_SERVICE_PORT"] = "9200"
        try:
            settings = IdentityRunSettings.from_env()
        finally:
            if old_host is None:
                os.environ.pop("IDENTITY_SERVICE_HOST", None)
            else:
                os.environ["IDENTITY_SERVICE_HOST"] = old_host

            if old_port is None:
                os.environ.pop("IDENTITY_SERVICE_PORT", None)
            else:
                os.environ["IDENTITY_SERVICE_PORT"] = old_port

        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.port, 9200)

    def test_identity_run_settings_ignore_kubernetes_service_link_port(self) -> None:
        import os

        old_port = os.environ.get("IDENTITY_SERVICE_PORT")
        os.environ["IDENTITY_SERVICE_PORT"] = "tcp://192.168.194.189:8000"
        try:
            settings = IdentityRunSettings.from_env()
        finally:
            if old_port is None:
                os.environ.pop("IDENTITY_SERVICE_PORT", None)
            else:
                os.environ["IDENTITY_SERVICE_PORT"] = old_port

        self.assertEqual(settings.port, 8000)

class IdentityAsyncServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_exchange_authorization_code_returns_normalized_identity(self) -> None:
        fake_client = FakeAsyncClient(
            token_payload={
                "access_token": "access-token",
                "token_type": "Bearer",
                "expires_in": 300,
                "refresh_token": "refresh-token",
                "id_token": "id-token",
            },
            userinfo_payload={
                "sub": "user-123",
                "preferred_username": "alice",
                "email": "alice@example.com",
                "groups": ["ops-operators"],
            },
        )
        settings = IdentitySettings(
            keycloak_base_url="https://sso.example.com",
            keycloak_realm="luban",
            oidc_client_id="portal-client",
            oidc_client_secret="secret",
            oidc_redirect_uri="http://localhost:8080/callback",
        )

        with patch(
            "identity_service.services.identity_service.httpx.AsyncClient",
            return_value=fake_client,
        ):
            result = await exchange_authorization_code(
                settings,
                AuthorizationCodeExchangeRequest(
                    code="auth-code",
                    code_verifier="verifier",
                ),
            )

        # access_token is now a platform JWT (not the raw OIDC token).
        self.assertTrue(result.access_token.startswith("eyJ"))
        self.assertEqual(result.token_type, "Bearer")
        self.assertEqual(result.expires_in, 900)
        self.assertEqual(result.identity.username, "alice")
        self.assertEqual(result.identity.roles, ["operator"])
        self.assertEqual(fake_client.posts[0]["data"]["client_secret"], "secret")
        self.assertEqual(
            fake_client.gets[0]["headers"]["authorization"],
            "Bearer access-token",
        )

    async def test_fetch_identity_from_authorization_returns_normalized_identity(self) -> None:
        fake_client = FakeAsyncClient(
            userinfo_payload={
                "sub": "user-123",
                "preferred_username": "alice",
                "email": "alice@example.com",
                "groups": ["ops-observers"],
            }
        )
        with patch(
            "identity_service.services.identity_service.httpx.AsyncClient",
            return_value=fake_client,
        ):
            identity = await fetch_identity_from_authorization(
                IdentitySettings(),
                "Bearer access-token",
            )

        self.assertEqual(identity.username, "alice")
        self.assertEqual(identity.roles, ["read-only-observer"])

    async def test_fetch_identity_from_authorization_requires_bearer_token(self) -> None:
        with self.assertRaises(ValueError):
            await fetch_identity_from_authorization(IdentitySettings(), "Basic abc")

    async def test_refresh_session_returns_new_platform_jwt(self) -> None:
        fake_client = FakeAsyncClient(
            token_payload={
                "access_token": "new-oidc-access-token",
                "token_type": "Bearer",
                "expires_in": 300,
                "refresh_token": "new-refresh-token",
                "id_token": "new-id-token",
            },
            userinfo_payload={
                "sub": "user-456",
                "preferred_username": "bob",
                "email": "bob@example.com",
                "groups": ["ops-admins"],
            },
        )
        settings = IdentitySettings(
            keycloak_base_url="https://sso.example.com",
            keycloak_realm="luban",
            oidc_client_id="portal-client",
            oidc_client_secret="secret",
        )

        with patch(
            "identity_service.services.identity_service.httpx.AsyncClient",
            return_value=fake_client,
        ):
            result = await refresh_session(
                settings,
                TokenRefreshRequest(refresh_token="old-refresh-token"),
            )

        self.assertTrue(result.access_token.startswith("eyJ"))
        self.assertEqual(result.token_type, "Bearer")
        self.assertEqual(result.expires_in, 900)
        self.assertEqual(result.refresh_token, "new-refresh-token")
        self.assertEqual(result.identity.username, "bob")
        self.assertEqual(result.identity.roles, ["platform-admin"])
        # Verify the refresh_token grant was used.
        self.assertEqual(
            fake_client.posts[0]["data"]["grant_type"], "refresh_token"
        )
        self.assertEqual(
            fake_client.posts[0]["data"]["refresh_token"], "old-refresh-token"
        )


if __name__ == "__main__":
    unittest.main()
