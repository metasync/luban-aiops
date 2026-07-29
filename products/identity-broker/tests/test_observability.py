"""SPEC-005 observability tests: /metrics surface, token counter, OTel gating."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from identity_service.app import create_app
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


if __name__ == "__main__":
    unittest.main()
