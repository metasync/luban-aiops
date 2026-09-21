"""SPEC-062 R-1/R-2/R-4/R-5: exercise real connector, fake only transport."""
import asyncio
import json
import os
import smtplib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

from tool_gateway.core.config import GatewaySettings
from tool_gateway.tools.password_policy import DEFAULT_POLICY, PasswordPolicyStore
from tool_gateway.tools.redaction import redact_result
from tool_gateway.tools.registry import ToolRegistry
from tool_gateway.tools.secret_delivery import DeliveryOutcome, InMemorySecretDeliveryBuffer
from tool_gateway.tools.secrets_connector import EmailChannel, SecretsConnector

OWNER = {"sub": "owner", "chat_session_id": "session", "request_id": "request"}
VALUE = "Fixture-Only9!abc"


def invoke(connector, name="secrets.generate_password", **params):
    registry = ToolRegistry(allow_mutating=True)
    connector.register_tools(registry)
    return asyncio.run(registry.invoke(name, params, OWNER))


class SecretsConnectorTests(unittest.TestCase):
    def test_generation_shares_injected_empty_buffer(self):
        buffer = InMemorySecretDeliveryBuffer()
        connector = SecretsConnector(buffer=buffer)
        self.assertIs(connector.buffer, buffer)
        result = invoke(connector)
        self.assertEqual(result.status, "success")
        value = result.data["generated_password"]
        self.assertGreaterEqual(len(value), 16)
        for predicate in (str.isupper, str.islower, str.isdigit, lambda c: not c.isalnum()):
            self.assertTrue(any(predicate(c) for c in value))
        self.assertEqual(buffer.redeem(result.data["delivery_id"], "owner"), value)
        self.assertIsNone(buffer.redeem(result.data["delivery_id"], "owner"))
        self.assertNotEqual(invoke(connector).data["generated_password"], value)
        # R-1: still real on the gateway-to-kernel working-context path.
        self.assertEqual(redact_result(result)[0].data["generated_password"], value)

    def test_csprng_and_tightening(self):
        connector = SecretsConnector()
        with patch("tool_gateway.tools.password_policy.secrets.choice", side_effect=lambda s: s[-1]) as choice:
            result = invoke(connector, length=24, exclude_ambiguous=True, handoff="none")
        self.assertEqual(result.status, "success")
        self.assertTrue(choice.called)
        self.assertEqual(len(result.data["generated_password"]), 24)
        self.assertFalse(set("Il1O0o") & set(result.data["generated_password"]))
        self.assertNotIn("delivery_id", result.data)
        self.assertEqual(invoke(connector, length=12).data["length"], 16)

    def test_invalid_parameters_are_bounded_and_do_not_echo(self):
        connector = SecretsConnector()
        for params in ({"length": 2}, {"length": True}, {"length": 16.5},
                       {"length": 129}, {"length": VALUE}, {"policy": VALUE},
                       {"handoff": VALUE}, {"exclude_ambiguous": "false"}):
            with self.subTest(params=params):
                result = invoke(connector, **params)
                self.assertEqual(result.status, "error")
                self.assertEqual(result.error["code"], "INVALID_PARAMETERS")
                self.assertNotIn(VALUE, json.dumps(result.to_dict()))

    def test_external_channel_registry_is_the_only_extension_seam(self):
        class ChatChannel:
            name = "test_chat"
            async def send(self, value, recipient, context):
                return DeliveryOutcome(channel=self.name, delivered=True, recipient=recipient)
        events = []
        connector = SecretsConnector(secret_delivered_sink=lambda d, i: events.append(d))
        connector.register_channel(ChatChannel())
        result = invoke(connector, "secrets.deliver", channel="test_chat", password=VALUE, recipient="operator")
        self.assertEqual(result.status, "success")
        self.assertEqual(events[0]["channel"], "test_chat")
        self.assertTrue(events[0]["delivery_id"])
        self.assertNotIn(VALUE, json.dumps(events))
        refused = invoke(connector, "secrets.deliver", channel="portal_copy", password=VALUE)
        self.assertEqual(refused.status, "error")

    def test_email_fail_closed_and_allowlist(self):
        transport = Mock()
        connector = SecretsConnector(email_transport=transport)
        result = invoke(connector, "secrets.deliver", channel="email", password=VALUE, recipient="alice@example.com")
        self.assertEqual(result.error["code"], "EMAIL_NOT_CONFIGURED")
        transport.assert_not_called()
        channel = EmailChannel(host="smtp.example.com", sender="sender@example.com", strict_allowlist=True,
                               recipient_allowlist=("example.com", "alice@other.test"), transport=transport)
        for address in ("a@example.com", "alice@other.test"):
            self.assertTrue(channel.recipient_allowed(address))
        for address in ("b@other.test", "a@evil-example.com", "x@sub.example.com"):
            self.assertFalse(channel.recipient_allowed(address))
        result = asyncio.run(channel.send(VALUE, "x@outside.test", {}))
        self.assertEqual(result.error_code, "EMAIL_RECIPIENT_NOT_ALLOWED")
        transport.assert_not_called()
        for address in ("x@example.com\r\nBcc: y@evil.test", "a@example.com,b@evil.test", "name <a@example.com>"):
            result = asyncio.run(channel.send(VALUE, address, {}))
            self.assertEqual(result.error_code, "INVALID_PARAMETERS")
        transport.assert_not_called()

    def test_email_success_body_and_audit_do_not_leak(self):
        transport = Mock()
        events = []
        connector = SecretsConnector(email_host="smtp.example.com", email_from="sender@example.com",
                                     email_transport=transport, secret_delivered_sink=lambda d, i: events.append(d))
        result = invoke(connector, "secrets.deliver", channel="email", password=VALUE, recipient="alice@example.com")
        self.assertEqual(result.status, "success")
        self.assertIn(VALUE, transport.call_args.args[0].get_body().get_content())
        self.assertNotIn(VALUE, json.dumps(result.to_dict()))
        self.assertNotIn(VALUE, json.dumps(events))
        self.assertTrue(events[0]["delivery_id"])
        transport.side_effect = smtplib.SMTPException(VALUE)
        with self.assertLogs("tool_gateway.tools.secrets_connector", "WARNING") as logs:
            failed = invoke(connector, "secrets.deliver", channel="email", password=VALUE, recipient="alice@example.com")
        self.assertNotIn(VALUE, str(logs.output) + json.dumps(failed.to_dict()))
        self.assertEqual(len(events), 1)

    def test_tls_cannot_be_disabled(self):
        channel = EmailChannel(host="smtp.example.com", sender="sender@example.com", use_tls=False, transport=Mock())
        result = asyncio.run(channel.send(VALUE, "alice@example.com", {}))
        self.assertEqual(result.error_code, "EMAIL_NOT_CONFIGURED")
        channel._transport.assert_not_called()
        with patch("tool_gateway.tools.secrets_connector.smtplib.SMTP") as smtp:
            smtp.return_value.__enter__.return_value.send_message.return_value = {}
            channel = EmailChannel(host="smtp.example.com", sender="sender@example.com")
            self.assertTrue(asyncio.run(channel.send(VALUE, "alice@example.com", {})).delivered)
            context = smtp.return_value.__enter__.return_value.starttls.call_args.kwargs["context"]
            self.assertTrue(context.check_hostname)


class PasswordPolicyTests(unittest.TestCase):
    def test_validator_rejects_drift_missing_consumers_and_malformed_classes(self):
        import runpy
        import sys

        root = Path(__file__).resolve().parents[3]
        validator = runpy.run_path(str(root / "shared/shared-contracts/scripts/validate_password_policy.py"))
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            relatives = [validator["CONTRACT_REL"], validator["CONNECTOR_REL"],
                         "products/tool-gateway/src/tool_gateway/policies/password-policy.yaml"]
            for rel in relatives:
                path = target / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((root / rel).read_bytes())
            with patch.object(sys, "argv", ["validate", str(target)]):
                self.assertEqual(validator["main"](), 0)
                connector = target / relatives[1]
                original = connector.read_text()
                connector.write_text(original.replace("(16, 12, 64)", "(-16, 12, 64)"))
                self.assertEqual(validator["main"](), 1)
                connector.write_text(original)
                packaged = target / relatives[2]
                packaged.write_text("version: 1\n")
                self.assertEqual(validator["main"](), 1)
                packaged.write_bytes((root / relatives[2]).read_bytes())
                connector.unlink()
                self.assertEqual(validator["main"](), 1)
            contract = target / relatives[0]
            for malformed in ([{}], [["upper"]], ["upper", "upper"], None):
                contract.write_text(yaml.safe_dump(self._contract(required_classes=malformed)))
                errors = []
                validator["validate_contract"](errors, contract)
                self.assertTrue(errors)

    def _contract(self, **overrides):
        default = dict(min_length=16, hard_floor=12, entropy_floor_bits=64,
                       required_classes=["upper", "lower", "digit", "symbol"], exclude_ambiguous=False)
        default.update(overrides)
        return {"version": 1, "policies": {"default": default}}

    def test_missing_and_invalid_policy_refuse_without_stale_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.yaml"
            store = PasswordPolicyStore(str(path))
            self.assertIsNone(store.get())
            path.write_text(yaml.safe_dump(self._contract()))
            self.assertEqual(store.get(), DEFAULT_POLICY)
            for overrides in ({"min_length": 4, "hard_floor": 4}, {"min_length": True},
                              {"exclude_ambiguous": "false"}, {"required_classes": ["lower"]}):
                path.write_text(yaml.safe_dump(self._contract(**overrides)))
                self.assertIsNone(store.get())
            path.unlink()
            self.assertIsNone(store.get())

    def test_named_policy_and_env_tightening_against_loaded_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.yaml"
            contract = self._contract(min_length=24)
            contract["policies"]["strict"] = {**contract["policies"]["default"], "min_length": 32}
            path.write_text(yaml.safe_dump(contract))
            with self.assertRaises(ValueError):
                GatewaySettings(password_policy_path=str(path), password_min_length=20)
            connector = SecretsConnector(policy_path=str(path))
            self.assertEqual(invoke(connector, policy="strict").data["length"], 32)

    def test_config_defaults_and_validation(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = GatewaySettings.from_env()
        self.assertFalse(settings.secrets_enabled)
        self.assertFalse(settings.email_host)
        self.assertEqual(settings.secret_delivery_backend, "memory")
        for kwargs in ({"password_min_length": 12}, {"password_min_length": 129},
                       {"password_required_classes": ("lower",)},
                       {"password_required_classes": ("upper", "lower", "digit", "symbol", "unknown")},
                       {"secret_delivery_ttl_seconds": 0}, {"secret_delivery_backend": "typo"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                GatewaySettings(**kwargs)
