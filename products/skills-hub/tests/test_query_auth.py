"""Query auth tests (SPEC-014 R-3).

Static Basic path against the distinct query registry; workload path requires
a configured issuer (dev default: disabled).
"""

from __future__ import annotations

import unittest

from skills_hub.core.config import QueryClient, SkillsSettings
from skills_hub.services.query_auth import (
    QueryAuthError,
    authenticate_static,
    authenticate_workload,
)


def _settings(**overrides) -> SkillsSettings:
    fields = {
        "query_clients": (QueryClient(client_id="tool-gateway", secret="s3cret"),),
    }
    fields.update(overrides)
    return SkillsSettings(**fields)


class StaticAuthTests(unittest.TestCase):
    def test_valid_credential_returns_client_id(self) -> None:
        client_id = authenticate_static(_settings(), "tool-gateway", "s3cret")
        self.assertEqual(client_id, "tool-gateway")

    def test_invalid_secret_rejected(self) -> None:
        with self.assertRaises(QueryAuthError):
            authenticate_static(_settings(), "tool-gateway", "wrong")

    def test_unknown_client_rejected(self) -> None:
        with self.assertRaises(QueryAuthError):
            authenticate_static(_settings(), "stranger", "s3cret")

    def test_missing_credential_rejected(self) -> None:
        with self.assertRaises(QueryAuthError):
            authenticate_static(_settings(), None, None)

    def test_empty_registry_rejects_everything(self) -> None:
        with self.assertRaises(QueryAuthError):
            authenticate_static(
                SkillsSettings(), "tool-gateway", "s3cret"
            )


class WorkloadAuthTests(unittest.TestCase):
    def test_disabled_without_issuer(self) -> None:
        with self.assertRaises(QueryAuthError):
            authenticate_workload(_settings(), "any-token")


if __name__ == "__main__":
    unittest.main()
