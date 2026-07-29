import unittest

from api_gateway.core.config import GatewaySettings
from api_gateway.core.runtime import GatewayRunSettings


class GatewayRunSettingsTests(unittest.TestCase):
    def test_gateway_settings_default_downstream_urls(self) -> None:
        settings = GatewaySettings.from_env()

        self.assertEqual(settings.agent_service_url, "http://agent-service:8000")
        self.assertEqual(settings.identity_service_url, "http://identity-service:8000")

    def test_gateway_settings_require_auth_defaults_to_false(self) -> None:
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GATEWAY_REQUIRE_AUTH", None)
            settings = GatewaySettings.from_env()

        self.assertFalse(settings.require_auth)

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

    def test_gateway_run_settings_read_env(self) -> None:
        import os

        old_host = os.environ.get("API_GATEWAY_HOST")
        old_port = os.environ.get("API_GATEWAY_PORT")
        os.environ["API_GATEWAY_HOST"] = "127.0.0.1"
        os.environ["API_GATEWAY_PORT"] = "9100"
        try:
            settings = GatewayRunSettings.from_env()
        finally:
            if old_host is None:
                os.environ.pop("API_GATEWAY_HOST", None)
            else:
                os.environ["API_GATEWAY_HOST"] = old_host

            if old_port is None:
                os.environ.pop("API_GATEWAY_PORT", None)
            else:
                os.environ["API_GATEWAY_PORT"] = old_port

        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.port, 9100)

    def test_gateway_run_settings_ignore_kubernetes_service_link_port(self) -> None:
        import os

        old_port = os.environ.get("API_GATEWAY_PORT")
        os.environ["API_GATEWAY_PORT"] = "tcp://192.168.194.145:8000"
        try:
            settings = GatewayRunSettings.from_env()
        finally:
            if old_port is None:
                os.environ.pop("API_GATEWAY_PORT", None)
            else:
                os.environ["API_GATEWAY_PORT"] = old_port

        self.assertEqual(settings.port, 8000)


if __name__ == "__main__":
    unittest.main()
