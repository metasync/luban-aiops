"""Settings + env-parsing tests for audit-service (SPEC-013 R-2).

Covers the ``AUDIT_INGEST_CLIENTS`` / ``AUDIT_WORKLOAD_CLIENTS`` registry
parsers and the frozen ``AuditSettings``/``AuditRunSettings`` env bindings.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from audit_service.core.config import (
    AuditSettings,
    parse_ingest_clients,
    parse_positive_int,
    parse_workload_clients,
)
from audit_service.core.runtime import AuditRunSettings


class ParseIngestClientsTests(unittest.TestCase):
    def test_parses_client_id_secret_pairs(self) -> None:
        clients = parse_ingest_clients("tool-gateway=s1,platform-gateway=s2")
        self.assertEqual(len(clients), 2)
        self.assertEqual(clients[0].client_id, "tool-gateway")
        self.assertEqual(clients[0].secret, "s1")
        self.assertEqual(clients[1].client_id, "platform-gateway")
        self.assertEqual(clients[1].secret, "s2")

    def test_skips_blank_and_malformed_entries(self) -> None:
        clients = parse_ingest_clients("a=1,,b,   ,c=3")
        self.assertEqual([c.client_id for c in clients], ["a", "c"])

    def test_empty_string_yields_no_clients(self) -> None:
        self.assertEqual(parse_ingest_clients(""), ())


class ParseWorkloadClientsTests(unittest.TestCase):
    def test_parses_subject_client_mappings(self) -> None:
        mappings = parse_workload_clients(
            "system:serviceaccount:ns:gw=platform-gateway"
        )
        self.assertEqual(len(mappings), 1)
        self.assertEqual(
            mappings[0].workload_subject, "system:serviceaccount:ns:gw"
        )
        self.assertEqual(mappings[0].client_id, "platform-gateway")

    def test_empty_string_yields_no_mappings(self) -> None:
        self.assertEqual(parse_workload_clients(""), ())


class AuditSettingsTests(unittest.TestCase):
    def test_defaults_are_dev_safe(self) -> None:
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("AUDIT_")
        }
        with patch.dict(os.environ, env, clear=True):
            settings = AuditSettings.from_env()
        self.assertEqual(settings.store_backend, "memory")
        self.assertEqual(settings.db_url, "")
        self.assertEqual(settings.ingest_clients, ())
        self.assertEqual(settings.retention_days, 30)
        self.assertEqual(settings.max_events, 100_000)
        self.assertEqual(settings.max_batch, 50)
        self.assertEqual(settings.export_max_rows, 10_000)

    def test_reads_env_overrides(self) -> None:
        overrides = {
            "AUDIT_STORE_BACKEND": "POSTGRES",
            "AUDIT_DB_URL": "postgresql://audit@db/audit",
            "AUDIT_INGEST_CLIENTS": "tool-gateway=secret",
            "AUDIT_RETENTION_DAYS": "7",
            "AUDIT_MAX_EVENTS": "500",
            "AUDIT_MAX_BATCH": "5",
            "AUDIT_EXPORT_MAX_ROWS": "250",
        }
        with patch.dict(os.environ, overrides):
            settings = AuditSettings.from_env()
        self.assertEqual(settings.store_backend, "postgres")
        self.assertEqual(settings.db_url, "postgresql://audit@db/audit")
        self.assertEqual(settings.ingest_clients[0].client_id, "tool-gateway")
        self.assertEqual(settings.retention_days, 7)
        self.assertEqual(settings.max_events, 500)
        self.assertEqual(settings.max_batch, 5)
        self.assertEqual(settings.export_max_rows, 250)


class ParsePositiveIntTests(unittest.TestCase):
    def test_rejects_zero_and_negative(self) -> None:
        # SPEC-046 R-2: a non-positive export cap is a startup error.
        for raw in ("0", "-1"):
            with self.assertRaises(ValueError):
                parse_positive_int(raw, "AUDIT_EXPORT_MAX_ROWS")

    def test_accepts_positive(self) -> None:
        self.assertEqual(parse_positive_int("1", "X"), 1)
        self.assertEqual(parse_positive_int("10000", "X"), 10000)


class AuditRunSettingsTests(unittest.TestCase):
    def test_defaults(self) -> None:
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"AUDIT_HOST", "AUDIT_PORT"}
        }
        with patch.dict(os.environ, env, clear=True):
            settings = AuditRunSettings.from_env()
        self.assertEqual(settings.host, "0.0.0.0")
        self.assertEqual(settings.port, 8000)

    def test_reads_env(self) -> None:
        with patch.dict(os.environ, {"AUDIT_HOST": "127.0.0.1", "AUDIT_PORT": "9300"}):
            settings = AuditRunSettings.from_env()
        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.port, 9300)

    def test_ignores_kubernetes_service_link_port(self) -> None:
        with patch.dict(os.environ, {"AUDIT_PORT": "tcp://10.0.0.1:8000"}):
            settings = AuditRunSettings.from_env()
        self.assertEqual(settings.port, 8000)


if __name__ == "__main__":
    unittest.main()
