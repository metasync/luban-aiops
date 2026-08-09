"""SPEC-005 observability tests: /metrics surface, domain counters, OTel gating."""

from __future__ import annotations

import logging
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from tool_gateway.app import create_app
from tool_gateway.core.config import GatewaySettings, get_settings
from tool_gateway.core.observability import configure_logging
from tool_gateway.core.request_context import resolve_request_id
from tool_gateway.services.policy_engine import reset_policy_state


def _sample(name: str, labels: dict[str, str]) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def _client(**settings_overrides) -> TestClient:
    reset_policy_state()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: GatewaySettings(
        **settings_overrides
    )
    return TestClient(app)


class MetricsEndpointTests(unittest.TestCase):
    def test_metrics_returns_prometheus_exposition(self) -> None:
        client = _client()
        client.get("/health/live")
        response = client.get("/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/plain"))
        body = response.text
        for expected in (
            "http_requests_total",
            "http_request_duration_seconds",
            "gateway_policy_decisions_total",
            "gateway_token_verification_total",
        ):
            self.assertIn(expected, body)

    def test_metrics_labels_use_templated_handler(self) -> None:
        client = _client()
        client.get("/health/live")
        self.assertGreater(
            _sample(
                "http_requests_total",
                {"method": "GET", "handler": "/health/live", "status": "200"},
            ),
            0.0,
        )

    def test_metrics_exempt_from_authentication(self) -> None:
        client = _client(require_auth=True)
        response = client.get("/metrics")
        self.assertEqual(response.status_code, 200)


class DomainCounterTests(unittest.TestCase):
    def test_policy_decision_and_token_verification_counters_increment(self) -> None:
        client = _client(require_auth=False)
        allow_before = _sample(
            "gateway_policy_decisions_total",
            {"action": "tools:list", "decision": "allow"},
        )
        missing_before = _sample(
            "gateway_token_verification_total", {"result": "missing"}
        )
        response = client.get("/api/v2/tools")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            _sample(
                "gateway_policy_decisions_total",
                {"action": "tools:list", "decision": "allow"},
            ),
            allow_before + 1,
        )
        self.assertEqual(
            _sample("gateway_token_verification_total", {"result": "missing"}),
            missing_before + 1,
        )

    def test_invalid_token_counter_increments(self) -> None:
        client = _client()
        invalid_before = _sample(
            "gateway_token_verification_total", {"result": "invalid"}
        )
        response = client.get(
            "/api/v2/tools",
            headers={"Authorization": "NotBearer xyz"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            _sample("gateway_token_verification_total", {"result": "invalid"}),
            invalid_before + 1,
        )


class CorrelationBridgeTests(unittest.TestCase):
    def test_inbound_request_id_wins(self) -> None:
        self.assertEqual(resolve_request_id("req-abc"), "req-abc")

    def test_uuid_fallback_when_otel_disabled(self) -> None:
        with patch.dict(os.environ, {"OTEL_ENABLED": "false"}):
            self.assertTrue(resolve_request_id(None).startswith("req-"))

    def test_trace_id_bridge_when_tracing_active(self) -> None:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        # set_tracer_provider is set-once per process; a repeated call logs
        # a warning and keeps the first real provider, which is fine here.
        trace.set_tracer_provider(TracerProvider())
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("test-span") as span:
            expected = format(span.get_span_context().trace_id, "032x")
            with patch.dict(os.environ, {"OTEL_ENABLED": "true"}):
                self.assertEqual(resolve_request_id(None), expected)


class OtelGatingTests(unittest.TestCase):
    def test_enabled_with_unreachable_collector_fails_open(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OTEL_ENABLED": "true",
                "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:1",
            },
        ):
            client = _client()
            self.assertEqual(client.get("/health/live").status_code, 200)
            self.assertEqual(client.get("/metrics").status_code, 200)


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
