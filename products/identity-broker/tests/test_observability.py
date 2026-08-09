"""SPEC-005 observability tests: /metrics surface, token counter, OTel gating."""

from __future__ import annotations

import logging
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from identity_service.app import create_app
from identity_service.core.observability import configure_logging
from identity_service.core.config import IdentitySettings
from identity_service.services.token_service import issue_token, reset_key_state


def _sample(name: str, labels: dict[str, str] | None = None) -> float:
    return REGISTRY.get_sample_value(name, labels or {}) or 0.0


class MetricsEndpointTests(unittest.TestCase):
    def test_metrics_returns_prometheus_exposition(self) -> None:
        client = TestClient(create_app())
        client.get("/health/live")
        response = client.get("/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/plain"))
        body = response.text
        for expected in (
            "http_requests_total",
            "http_request_duration_seconds",
            "identity_tokens_issued_total",
        ):
            self.assertIn(expected, body)

    def test_metrics_available_with_otel_enabled(self) -> None:
        with patch.dict(os.environ, {"OTEL_ENABLED": "true"}):
            client = TestClient(create_app())
            self.assertEqual(client.get("/metrics").status_code, 200)


class TokenCounterTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_key_state()

    def test_issue_token_increments_counter(self) -> None:
        before = _sample("identity_tokens_issued_total")
        issue_token(IdentitySettings(), {"sub": "user-1", "username": "user-1"})
        self.assertEqual(_sample("identity_tokens_issued_total"), before + 1)


class LoggingConfigTests(unittest.TestCase):
    def test_defaults_to_info_so_audit_events_survive(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "LOG_LEVEL"}
        with patch.dict(os.environ, env, clear=True):
            configure_logging()
        self.assertEqual(logging.getLogger().level, logging.INFO)

    def test_log_level_env_overrides(self) -> None:
        with patch.dict(os.environ, {"LOG_LEVEL": "WARNING"}):
            configure_logging()
        self.assertEqual(logging.getLogger().level, logging.WARNING)
        configure_logging()  # restore default for later tests


if __name__ == "__main__":
    unittest.main()
