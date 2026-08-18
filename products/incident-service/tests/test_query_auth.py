"""Platform-caller auth tests (SPEC-015 R-2, SPEC-014 R-3 vocabulary).

Static Basic path against the query registry; workload path requires a
configured issuer (dev default: disabled).
"""

from __future__ import annotations

import unittest

from incident_service.core.config import IncidentSettings, QueryClient
from incident_service.services.query_auth import (
    QueryAuthError,
    authenticate_static,
    authenticate_workload,
)


def _settings(**overrides) -> IncidentSettings:
    fields = {
        "query_clients": (
            QueryClient(client_id="platform-gateway", secret="pg-secret"),
            QueryClient(client_id="tool-gateway", secret="tg-secret"),
        ),
    }
    fields.update(overrides)
    return IncidentSettings(**fields)


class StaticAuthTests(unittest.TestCase):
    def test_valid_credential_returns_client_id(self) -> None:
        client_id = authenticate_static(_settings(), "tool-gateway", "tg-secret")
        self.assertEqual(client_id, "tool-gateway")

    def test_invalid_secret_rejected(self) -> None:
        with self.assertRaises(QueryAuthError):
            authenticate_static(_settings(), "tool-gateway", "wrong")

    def test_unknown_client_rejected(self) -> None:
        with self.assertRaises(QueryAuthError):
            authenticate_static(_settings(), "stranger", "tg-secret")

    def test_missing_credential_rejected(self) -> None:
        with self.assertRaises(QueryAuthError):
            authenticate_static(_settings(), None, None)

    def test_empty_registry_rejects_everything(self) -> None:
        with self.assertRaises(QueryAuthError):
            authenticate_static(IncidentSettings(), "tool-gateway", "tg-secret")


class WorkloadAuthTests(unittest.TestCase):
    def test_disabled_without_issuer(self) -> None:
        with self.assertRaises(QueryAuthError):
            authenticate_workload(_settings(), "any-token")


if __name__ == "__main__":
    unittest.main()
