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
        self.assertFalse(settings.admission_enabled)
        self.assertEqual(settings.admission_epoch, "")

    def test_from_env_reads_execution_prefixed_knobs(self) -> None:
        env = {
            "EXECUTION_SIGNING_KEY": "signing-key",
            "EXECUTION_HANDOFF_TOKEN": "handoff-token",
            "TOOL_GATEWAY_URL": " http://tool-gateway:8000 ",
            "EXECUTION_GATEWAY_TIMEOUT_SECONDS": "25",
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
        self.assertEqual(settings.gateway_timeout_seconds, 25.0)
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

    def test_missing_postgres_url_can_start_but_cannot_admit(self) -> None:
        from execution_runtime.services.execution_ledger import ExecutionLedger
        settings = ExecutionSettings(state_store_backend="postgres", state_db_url="")
        health = ExecutionLedger(settings.state_db_url, "key", None).health()
        self.assertEqual(health["actual_backend"], "unavailable")
        self.assertFalse(health["admission_enabled"])

    def test_gateway_exchange_cannot_exceed_thirty_seconds(self) -> None:
        with self.assertRaises(ValueError):
            ExecutionSettings(gateway_timeout_seconds=31)

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


class CutoverWrapperTests(unittest.TestCase):
    """Exercise the shipped shell gate with the real decision CLI, never a cluster."""

    def test_disabled_recovery_requires_verified_empty_sender_inventory(self):
        import json
        from pathlib import Path
        import shlex
        import subprocess
        import sys
        import tempfile

        root = Path(__file__).resolve().parents[3]
        wrapper = root / "shared/platform-ops/gitops/execution-cutover.sh"
        cases = ("empty", "drained", "wait_failure", "worker_remains", "issuer_remains",
                 "inventory_failure", "issuer_inventory_failure", "scale_failure", "unconfirmed")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                # Strip only uv's known launcher arguments; run the actual product CLI.
                uv = folder / "uv"
                uv.write_text("#!/bin/sh\nshift 6\nexec " + shlex.quote(sys.executable) + ' "$@"\n')
                uv.chmod(0o700)
                calls = folder / "calls.jsonl"
                kubectl = folder / "kubectl"
                kubectl.write_text(f"#!{sys.executable}\n" + '''import json, os, sys
from pathlib import Path
args = sys.argv[1:]
case = os.environ["CUTOVER_TEST_CASE"]
path = Path(os.environ["CUTOVER_TEST_CALLS"])
previous = path.read_text().splitlines() if path.exists() else []
with path.open("a") as stream:
    stream.write(json.dumps(args) + "\\n")
if "scale" in args:
    sys.exit(1 if case == "scale_failure" else 0)
if "wait" in args:
    sys.exit(1 if case == "wait_failure" else 0)
if "get" not in args:
    sys.exit(99)
worker = "app=execution-runtime" in args
if case == "inventory_failure" or (not worker and case == "issuer_inventory_failure"):
    sys.exit(1)
first_worker_read = not any("app=execution-runtime" in json.loads(line) for line in previous)
if worker and (case == "worker_remains" or (first_worker_read and case in ("drained", "wait_failure"))):
    print("pod/old-worker")
if not worker and case == "issuer_remains":
    print("pod/old-issuer")
''')
                kubectl.chmod(0o700)
                env = {**os.environ, "PATH": str(folder) + os.pathsep + os.environ["PATH"],
                       "PYTHONPATH": str(root / "products/execution-runtime/src"),
                       "EXECUTION_RECOVERY_MODE": "disabled-recovery",
                       "EXECUTION_CUTOVER_PLAN_ONLY": "false",
                       "EXECUTION_MUTATIONS_DISABLED": "false" if case == "unconfirmed" else "true",
                       "CUTOVER_TEST_CASE": case, "CUTOVER_TEST_CALLS": str(calls)}
                result = subprocess.run(["sh", str(wrapper), "--current", "0.43.0",
                                         "--target", "0.42.0", "spec063-test-only"],
                                        env=env, text=True, capture_output=True, timeout=15)
                success = case in ("empty", "drained")
                self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
                self.assertEqual("You may now replace the binary" in result.stdout, success)
                invocations = [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
                if case == "unconfirmed":
                    self.assertEqual(invocations, [])
                for args in invocations:
                    self.assertIn("spec063-test-only", args)
                    self.assertIn("--request-timeout=15s", args)
                if case == "drained":
                    self.assertTrue(any("wait" in args and "--for=delete" in args for args in invocations))


if __name__ == "__main__":
    unittest.main()
