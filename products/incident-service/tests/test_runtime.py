"""Runtime settings tests: env-driven host/port with service-link tolerance.

Kubernetes service links can inject values like ``tcp://IP:PORT`` into
``INCIDENT_PORT``; the resolver must fall back to the default instead of
crashing the entrypoint.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from incident_service.core.runtime import IncidentRunSettings, _resolve_port
from incident_service.metadata import DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT


class ResolvePortTests(unittest.TestCase):
    def test_none_returns_default(self) -> None:
        self.assertEqual(_resolve_port(None, 8000), 8000)

    def test_numeric_string_parsed(self) -> None:
        self.assertEqual(_resolve_port("9090", 8000), 9090)

    def test_service_link_value_falls_back_to_default(self) -> None:
        self.assertEqual(_resolve_port("tcp://10.0.0.1:8000", 8000), 8000)


class IncidentRunSettingsTests(unittest.TestCase):
    def test_defaults_without_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = IncidentRunSettings.from_env()
        self.assertEqual(settings.host, DEFAULT_HTTP_HOST)
        self.assertEqual(settings.port, DEFAULT_HTTP_PORT)

    def test_env_overrides_host_and_port(self) -> None:
        env = {"INCIDENT_HOST": "127.0.0.1", "INCIDENT_PORT": "9101"}
        with patch.dict(os.environ, env, clear=True):
            settings = IncidentRunSettings.from_env()
        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.port, 9101)


if __name__ == "__main__":
    unittest.main()
