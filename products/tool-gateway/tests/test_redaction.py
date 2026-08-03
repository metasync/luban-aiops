"""Tool output redaction tests (SPEC-009 R-1/R-2).

Unit tests cover the code-owned pattern set and the bounded explicit key
list; route tests prove redaction happens at the invoke choke point (before
response and audit), that overflow is fail-closed, and that the dev-mode
opt-out switch works.
"""

import time
import unittest
from unittest.mock import patch

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from api_gateway.app import create_app
from api_gateway.core.config import GatewaySettings, get_settings
from api_gateway.services import token_verifier
from api_gateway.services.policy_engine import reset_policy_state
from api_gateway.tools.base import BaseTool, ToolDefinition, ToolResult, build_evidence
from api_gateway.tools.redaction import (
    REDACTION_MARKER,
    RedactionStats,
    redact_result,
)
from api_gateway.tools.registry import ToolRegistry

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

_JWT = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJzZXJ2aWNlLWFjY291bnQifQ.sig-value-12345678"
_PEM = (
    "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA7\n-----END RSA PRIVATE KEY-----"
)


def _result(data: dict | None) -> ToolResult:
    return ToolResult(
        tool_name="test.tool",
        status="success",
        data=data,
        evidence=build_evidence("read", "test", 1),
    )


class ValuePatternTests(unittest.TestCase):
    def test_jwt_in_log_text_is_redacted(self) -> None:
        redacted, stats = redact_result(
            _result({"logs": [f"auth started, sa token {_JWT} attached, done"]})
        )
        self.assertNotIn(_JWT, redacted.data["logs"][0])
        self.assertIn(REDACTION_MARKER, redacted.data["logs"][0])
        self.assertEqual(stats.spans, 1)

    def test_bearer_value_is_redacted(self) -> None:
        redacted, stats = redact_result(
            _result({"logs": ["proxy saw Bearer abc123secret-token.value"]})
        )
        self.assertNotIn("abc123secret-token.value", redacted.data["logs"][0])
        self.assertEqual(stats.spans, 1)

    def test_pem_private_key_block_is_redacted(self) -> None:
        redacted, stats = redact_result(_result({"dump": f"key:\n{_PEM}\nend"}))
        self.assertNotIn("MIIEpAIBAAKCAQEA7", redacted.data["dump"])
        self.assertEqual(stats.spans, 1)

    def test_aws_access_key_is_redacted(self) -> None:
        redacted, stats = redact_result(_result({"logs": ["using AKIAABCDEFGHIJKLMNOP"]}))
        self.assertNotIn("AKIAABCDEFGHIJKLMNOP", redacted.data["logs"][0])
        self.assertEqual(stats.spans, 1)


class ExplicitKeyListTests(unittest.TestCase):
    def test_sensitive_string_values_are_redacted_key_visible(self) -> None:
        redacted, stats = redact_result(
            _result(
                {
                    "config": {
                        "password": "hunter2",
                        "api_key": "sk-12345",
                        "TOKEN": "tok-67890",
                        "client_secret": "shh",
                    }
                }
            )
        )
        config = redacted.data["config"]
        self.assertEqual(config["password"], REDACTION_MARKER)
        self.assertEqual(config["api_key"], REDACTION_MARKER)
        self.assertEqual(config["TOKEN"], REDACTION_MARKER)
        self.assertEqual(config["client_secret"], REDACTION_MARKER)
        self.assertEqual(stats.spans, 4)

    def test_non_string_sensitive_keys_are_not_blanked(self) -> None:
        # token_count is numeric diagnostic data, not a credential.
        redacted, stats = redact_result(_result({"token_count": 42, "token": "x-secret"}))
        self.assertEqual(redacted.data["token_count"], 42)
        self.assertEqual(redacted.data["token"], REDACTION_MARKER)
        self.assertEqual(stats.spans, 1)

    def test_unlisted_key_names_are_not_redacted(self) -> None:
        redacted, stats = redact_result(
            _result({"monkey_patch": "enabled", "notes": "token refreshed ok"})
        )
        self.assertEqual(redacted.data["monkey_patch"], "enabled")
        self.assertEqual(redacted.data["notes"], "token refreshed ok")
        self.assertEqual(stats.spans, 0)


class PassthroughTests(unittest.TestCase):
    def test_clean_output_passes_through_unchanged(self) -> None:
        original = _result({"pods": [{"name": "web-1", "ready": True, "restarts": 0}]})
        redacted, stats = redact_result(original)
        self.assertIs(redacted, original)
        self.assertEqual(stats.spans, 0)
        self.assertFalse(stats.overflow(0.2))

    def test_overflow_fraction_math(self) -> None:
        stats = RedactionStats(spans=1, original_chars=100, redacted_chars=21)
        self.assertTrue(stats.overflow(0.2))
        stats_at_bound = RedactionStats(spans=1, original_chars=100, redacted_chars=20)
        self.assertFalse(stats_at_bound.overflow(0.2))
        empty = RedactionStats(spans=0, original_chars=0, redacted_chars=0)
        self.assertFalse(empty.overflow(0.2))


# ---------------------------------------------------------------------------
# Route-level: choke point, fail-closed overflow, opt-out.
# ---------------------------------------------------------------------------


class _SecretTool(BaseTool):
    """Returns a payload that is almost entirely a credential."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="test.secret", description="Leaks.", risk_level="read", category="test"
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        return ToolResult(
            tool_name="test.secret",
            status="success",
            data={"logs": [_JWT * 4]},
            evidence=build_evidence("read", "test", 1),
        )


class _LeakyTool(BaseTool):
    """Returns a payload with one credential among benign content."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="test.leaky", description="Leaks a little.", risk_level="read",
            category="test",
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        benign = "pod web-1 ready; " * 40
        return ToolResult(
            tool_name="test.leaky",
            status="success",
            data={"logs": [f"{benign} sa token {_JWT} end"]},
            evidence=build_evidence("read", "test", 1),
        )


def _build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(_SecretTool())
    registry.register(_LeakyTool())
    return registry


def _mint_delegated(role: str = "operator") -> str:
    now = int(time.time())
    claims = {
        "iss": "luban-identity-broker",
        "sub": f"user-{role}",
        "username": f"{role}.user",
        "roles": [role],
        "groups": [],
        "aud": ["tool-gateway"],
        "act": {"sub": "agent-platform"},
        "iat": now,
        "exp": now + 300,
    }
    return pyjwt.encode(claims, _KEY, algorithm="RS256")


def _patch_jwks():
    public_key = _KEY.public_key()
    fake_client = type(
        "FakeClient",
        (),
        {
            "get_signing_key_from_jwt": lambda _self, _t: type(
                "K", (), {"key": public_key}
            )()
        },
    )()
    return patch.object(token_verifier, "_get_jwks_client", return_value=fake_client)


class RedactionRouteTests(unittest.TestCase):
    def _client(self, settings: GatewaySettings) -> TestClient:
        reset_policy_state()
        token_verifier.reset_verifier_state()
        app = create_app()
        app.state.tool_registry = _build_registry()
        app.dependency_overrides[get_settings] = lambda: settings
        return TestClient(app)

    def tearDown(self) -> None:
        reset_policy_state()
        token_verifier.reset_verifier_state()

    def _invoke(self, client: TestClient, tool_name: str):
        return client.post(
            "/api/v2/tools/invoke",
            json={"tool_name": tool_name, "parameters": {}, "request_id": "req-r"},
            headers={"Authorization": f"Bearer {_mint_delegated()}"},
        )

    def test_credential_redacted_before_response(self) -> None:
        client = self._client(GatewaySettings(require_auth=True))
        with _patch_jwks():
            response = self._invoke(client, "test.leaky")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "success")
        self.assertNotIn(_JWT, body["data"]["logs"][0])
        self.assertIn(REDACTION_MARKER, body["data"]["logs"][0])
        self.assertIn("pod web-1 ready", body["data"]["logs"][0])

    def test_overflow_is_fail_closed(self) -> None:
        client = self._client(GatewaySettings(require_auth=True))
        with _patch_jwks():
            response = self._invoke(client, "test.secret")
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], "REDACTION_OVERFLOW")
        self.assertNotIn(_JWT, str(body))

    def test_opt_out_switch_disables_redaction(self) -> None:
        client = self._client(GatewaySettings(require_auth=True, redaction_enabled=False))
        with _patch_jwks():
            response = self._invoke(client, "test.leaky")
        self.assertEqual(response.status_code, 200)
        self.assertIn(_JWT, response.json()["data"]["logs"][0])

    def test_audit_log_records_redacted_spans(self) -> None:
        client = self._client(GatewaySettings(require_auth=True))
        with _patch_jwks(), self.assertLogs(
            "api_gateway.services.gateway_service", level="INFO"
        ) as captured:
            self._invoke(client, "test.leaky")
        audit = [r for r in captured.records if "tool_invoked" in r.getMessage()]
        self.assertTrue(audit)
        self.assertIn('"redacted_spans": 1', audit[-1].getMessage())

    def test_redacted_spans_metric_recorded(self) -> None:
        client = self._client(GatewaySettings(require_auth=True))
        with _patch_jwks():
            self._invoke(client, "test.leaky")
        latest = generate_latest().decode()
        self.assertIn('gateway_tool_redacted_spans_total{tool="test.leaky"}', latest)


if __name__ == "__main__":
    unittest.main()
