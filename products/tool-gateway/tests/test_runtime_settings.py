import unittest

from tool_gateway.core.config import GatewaySettings
from tool_gateway.core.runtime import GatewayRunSettings


class GatewayRunSettingsTests(unittest.TestCase):
    def test_gateway_settings_default_tool_scoped_values(self) -> None:
        settings = GatewaySettings.from_env()

        self.assertEqual(settings.identity_service_url, "http://identity-service:8000")
        self.assertEqual(settings.token_audience, "tool-gateway")
        self.assertTrue(settings.redaction_enabled)
        self.assertEqual(settings.redaction_overflow_fraction, 0.2)

    def test_gateway_settings_require_auth_defaults_to_true(self) -> None:
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GATEWAY_REQUIRE_AUTH", None)
            settings = GatewaySettings.from_env()

        self.assertTrue(settings.require_auth)

    def test_gateway_settings_require_auth_reads_env(self) -> None:
        import os
        from unittest.mock import patch

        for raw_value, expected in [
            ("true", True),
            ("1", True),
            ("YES", True),
            ("false", False),
            ("off", False),
        ]:
            with patch.dict(os.environ, {"GATEWAY_REQUIRE_AUTH": raw_value}):
                settings = GatewaySettings.from_env()
            self.assertEqual(settings.require_auth, expected, raw_value)

    def test_gateway_settings_incidents_connector_defaults(self) -> None:
        """SPEC-015 R-4: incidents connector settings default off."""
        import os
        from unittest.mock import patch

        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GATEWAY_INCIDENTS_")
        }
        with patch.dict(os.environ, env, clear=True):
            settings = GatewaySettings.from_env()

        self.assertEqual(settings.incidents_service_url, "")
        self.assertEqual(settings.incidents_client_id, "tool-gateway")
        self.assertEqual(settings.incidents_client_secret, "")

    def test_gateway_settings_incidents_connector_reads_env(self) -> None:
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {
            "GATEWAY_INCIDENTS_SERVICE_URL": "http://incident-service:8000",
            "GATEWAY_INCIDENTS_CLIENT_ID": "gateway",
            "GATEWAY_INCIDENTS_CLIENT_SECRET": "secret",
        }):
            settings = GatewaySettings.from_env()

        self.assertEqual(
            settings.incidents_service_url, "http://incident-service:8000"
        )
        self.assertEqual(settings.incidents_client_id, "gateway")
        self.assertEqual(settings.incidents_client_secret, "secret")

    def test_gateway_run_settings_read_env(self) -> None:
        import os

        old_host = os.environ.get("GATEWAY_HOST")
        old_port = os.environ.get("GATEWAY_PORT")
        os.environ["GATEWAY_HOST"] = "127.0.0.1"
        os.environ["GATEWAY_PORT"] = "9100"
        try:
            settings = GatewayRunSettings.from_env()
        finally:
            if old_host is None:
                os.environ.pop("GATEWAY_HOST", None)
            else:
                os.environ["GATEWAY_HOST"] = old_host

            if old_port is None:
                os.environ.pop("GATEWAY_PORT", None)
            else:
                os.environ["GATEWAY_PORT"] = old_port

        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.port, 9100)

    def test_gateway_run_settings_ignore_kubernetes_service_link_port(self) -> None:
        import os

        old_port = os.environ.get("GATEWAY_PORT")
        os.environ["GATEWAY_PORT"] = "tcp://192.168.194.145:8000"
        try:
            settings = GatewayRunSettings.from_env()
        finally:
            if old_port is None:
                os.environ.pop("GATEWAY_PORT", None)
            else:
                os.environ["GATEWAY_PORT"] = old_port

        self.assertEqual(settings.port, 8000)


if __name__ == "__main__":
    unittest.main()
