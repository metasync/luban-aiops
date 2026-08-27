"""Settings validation for the execution worker (SPEC-038 R-1)."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from execution_runtime.core.config import ExecutionSettings, get_settings


class ExecutionSettingsTests(unittest.TestCase):
    def test_defaults_are_fail_closed_friendly(self) -> None:
        settings = ExecutionSettings()
        self.assertIsNone(settings.execution_signing_key)
        self.assertIsNone(settings.handoff_token)
        self.assertEqual(settings.tool_gateway_url, "")
        self.assertEqual(settings.gateway_timeout_seconds, 30.0)
        self.assertEqual(settings.state_store_backend, "memory")
        self.assertIsNone(settings.audit_service_url)
        self.assertEqual(settings.audit_client_id, "execution-runtime")
        self.assertEqual(settings.flight_retention_seconds, 900)

    def test_from_env_reads_execution_prefixed_knobs(self) -> None:
        env = {
            "EXECUTION_SIGNING_KEY": "signing-key",
            "EXECUTION_HANDOFF_TOKEN": "handoff-token",
            "TOOL_GATEWAY_URL": " http://tool-gateway:8000 ",
            "EXECUTION_GATEWAY_TIMEOUT_SECONDS": "45",
            "EXECUTION_STATE_STORE_BACKEND": "Postgres",
            "EXECUTION_STATE_DB_URL": "postgresql://u:p@host/db",
            "EXECUTION_AUDIT_SERVICE_URL": "http://audit-service:8000",
            "EXECUTION_AUDIT_CLIENT_ID": "worker",
            "EXECUTION_AUDIT_CLIENT_SECRET": "secret",
            "EXECUTION_FLIGHT_RETENTION_SECONDS": "60",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            settings = ExecutionSettings.from_env()
        self.assertEqual(settings.execution_signing_key, "signing-key")
        self.assertEqual(settings.handoff_token, "handoff-token")
        self.assertEqual(settings.tool_gateway_url, "http://tool-gateway:8000")
        self.assertEqual(settings.gateway_timeout_seconds, 45.0)
        self.assertEqual(settings.state_store_backend, "postgres")
        self.assertEqual(settings.state_db_url, "postgresql://u:p@host/db")
        self.assertEqual(settings.audit_service_url, "http://audit-service:8000")
        self.assertEqual(settings.audit_client_id, "worker")
        self.assertEqual(settings.audit_client_secret, "secret")
        self.assertEqual(settings.flight_retention_seconds, 60)

    def test_empty_secret_env_values_stay_unset(self) -> None:
        env = {
            "EXECUTION_SIGNING_KEY": "",
            "EXECUTION_HANDOFF_TOKEN": "   ",
            "EXECUTION_AUDIT_SERVICE_URL": "",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            settings = ExecutionSettings.from_env()
        self.assertIsNone(settings.execution_signing_key)
        self.assertIsNone(settings.handoff_token)
        self.assertIsNone(settings.audit_service_url)

    def test_nonpositive_gateway_timeout_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ExecutionSettings(gateway_timeout_seconds=0)

    def test_unknown_store_backend_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ExecutionSettings(state_store_backend="sqlite")

    def test_postgres_backend_requires_db_url(self) -> None:
        with self.assertRaises(ValueError):
            ExecutionSettings(state_store_backend="postgres", state_db_url="")

    def test_zero_flight_retention_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ExecutionSettings(flight_retention_seconds=0)

    def test_get_settings_caches(self) -> None:
        get_settings.cache_clear()
        try:
            with mock.patch.dict(os.environ, {"EXECUTION_SIGNING_KEY": "k1"}):
                first = get_settings()
            with mock.patch.dict(os.environ, {"EXECUTION_SIGNING_KEY": "k2"}):
                second = get_settings()
            self.assertIs(first, second)
            self.assertEqual(first.execution_signing_key, "k1")
        finally:
            get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
