"""Settings parsing tests (SPEC-015 R-2)."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from incident_service.core.config import (
    IncidentSettings,
    get_settings,
    parse_connectors,
    parse_query_clients,
    parse_workload_clients,
)


class ParseQueryClientsTests(unittest.TestCase):
    def test_parses_comma_separated_pairs(self) -> None:
        clients = parse_query_clients("platform-gateway=pg-secret,tool-gateway=tg")
        self.assertEqual(
            [(c.client_id, c.secret) for c in clients],
            [("platform-gateway", "pg-secret"), ("tool-gateway", "tg")],
        )

    def test_skips_blank_and_malformed_entries(self) -> None:
        clients = parse_query_clients("a=b,,=x,c=,d")
        self.assertEqual([c.client_id for c in clients], ["a"])


class ParseWorkloadClientsTests(unittest.TestCase):
    def test_parses_subject_mappings(self) -> None:
        mappings = parse_workload_clients(
            "system:serviceaccount:ns:pg=platform-gateway"
        )
        self.assertEqual(mappings[0].workload_subject, "system:serviceaccount:ns:pg")
        self.assertEqual(mappings[0].client_id, "platform-gateway")


class ParseConnectorsTests(unittest.TestCase):
    def test_empty_selects_builtin_audit_sink(self) -> None:
        self.assertEqual(parse_connectors(""), ("audit",))
        self.assertEqual(parse_connectors(" , "), ("audit",))

    def test_parses_comma_list(self) -> None:
        self.assertEqual(parse_connectors("audit,slack"), ("audit", "slack"))


class FromEnvTests(unittest.TestCase):
    def test_from_env_reads_incident_prefixed_vars(self) -> None:
        env = {
            "INCIDENT_WEBHOOK_TOKEN": "hook-secret",
            "INCIDENT_QUERY_CLIENTS": "tool-gateway=tg-secret",
            "INCIDENT_STORE_BACKEND": "postgres",
            "INCIDENT_DB_URL": "postgresql://db/incidents",
            "INCIDENT_CONNECTORS": "audit",
            "INCIDENT_TRIAGE_TIMEOUT_SECONDS": "45",
            "INCIDENT_AUDIT_SERVICE_URL": "http://audit-service:8000",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = IncidentSettings.from_env()
        self.assertEqual(settings.webhook_token, "hook-secret")
        self.assertEqual(settings.query_clients[0].client_id, "tool-gateway")
        self.assertEqual(settings.store_backend, "postgres")
        self.assertEqual(settings.db_url, "postgresql://db/incidents")
        self.assertEqual(settings.connectors, ("audit",))
        self.assertEqual(settings.triage_timeout_seconds, 45.0)
        self.assertEqual(settings.audit_service_url, "http://audit-service:8000")

    def test_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = IncidentSettings.from_env()
        self.assertEqual(settings.store_backend, "memory")
        self.assertEqual(settings.connectors, ("audit",))
        self.assertEqual(settings.agent_service_url, "http://agent-service:8000")
        self.assertEqual(settings.workload_audience, "incident-service")
        self.assertEqual(settings.audit_client_id, "incident-service")

    def test_get_settings_is_cached(self) -> None:
        get_settings.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            self.assertIs(get_settings(), get_settings())
        get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
