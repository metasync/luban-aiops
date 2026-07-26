import unittest

from identity_service.core.config import IdentitySettings
from identity_service.core.runtime import IdentityRunSettings
from identity_service.schemas.identity import ClaimsPayload
from identity_service.services.identity_service import (
    build_login_url,
    normalize_identity,
    resolve_roles,
)


class IdentityServiceTests(unittest.TestCase):
    def test_resolve_roles_returns_default_observer_role(self) -> None:
        self.assertEqual(resolve_roles(["unknown-group"]), ["read-only-observer"])

    def test_resolve_roles_maps_known_groups(self) -> None:
        self.assertEqual(
            resolve_roles(["ops-approvers", "ops-admins"]),
            ["approver", "platform-admin"],
        )

    def test_build_login_url_uses_settings(self) -> None:
        payload = build_login_url(
            IdentitySettings(
                keycloak_base_url="https://sso.example.com",
                keycloak_realm="luban-local",
                oidc_client_id="portal-client",
                oidc_redirect_uri="http://localhost:8080/callback",
            )
        )

        self.assertIn("https://sso.example.com/realms/luban-local", payload["login_url"])
        self.assertIn("client_id=portal-client", payload["login_url"])

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


if __name__ == "__main__":
    unittest.main()
