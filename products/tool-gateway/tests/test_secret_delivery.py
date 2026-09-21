"""SPEC-062: buffer contract and authenticated one-time handoff."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from fastapi.testclient import TestClient

from tool_gateway.app import create_app
from tool_gateway.core.config import GatewaySettings, get_settings
from tool_gateway.services.policy_engine import reset_policy_state
from tool_gateway.tools.secret_delivery import (
    InMemorySecretDeliveryBuffer, RedisSecretDeliveryBuffer,
    SecretDeliveryBuffer, build_secret_delivery_buffer,
)
from test_tool_invoke import _mint_delegated, _patch_jwks

VALUE = "Fixture-Only9!abc"


class RedisTransport:
    """Only Redis I/O is replaced; exercise the production backend logic."""
    def __init__(self, clock):
        self.clock, self.entries = clock, {}

    def set(self, key, payload, ex):
        self.entries[key] = (payload, self.clock() + ex)
        return True

    def getdel(self, key):
        item = self.entries.pop(key, None)
        return item[0] if item and self.clock() < item[1] else None

    def ping(self):
        return True

    def keys(self, pattern):
        return list(self.entries)


class BufferContractTests(unittest.TestCase):
    def test_both_backends_single_use_ttl_and_owner(self):
        now = [0]
        clock = lambda: now[0]
        for buffer in (InMemorySecretDeliveryBuffer(clock=clock),
                       RedisSecretDeliveryBuffer(RedisTransport(clock))):
            with self.subTest(backend=buffer.backend_name):
                self.assertIsInstance(buffer, SecretDeliveryBuffer)
                self.assertTrue(buffer.is_ready())
                handle = buffer.stash(VALUE, "owner", "session", 5)
                self.assertEqual(buffer.redeem(handle, "owner"), VALUE)
                self.assertIsNone(buffer.redeem(handle, "owner"))
                for stranger in ("approver", "other-owner", ""):
                    handle = buffer.stash(VALUE, "owner", "session", 5)
                    self.assertIsNone(buffer.redeem(handle, stranger))
                    self.assertIsNone(buffer.redeem(handle, "owner"))
                handle = buffer.stash(VALUE, "owner", "session", 5)
                now[0] += 5
                self.assertIsNone(buffer.redeem(handle, "owner"))

    def test_owner_scope_mutation_is_detected_for_each_backend(self):
        """R-8: replay the contract with caller authority ignored, in memory."""
        for backend in (InMemorySecretDeliveryBuffer, RedisSecretDeliveryBuffer):
            redeem = backend.redeem
            with self.subTest(backend=backend.backend_name), patch.object(
                backend, "redeem", lambda buffer, handle, caller: redeem(buffer, handle, "owner")
            ), self.assertRaises(AssertionError):
                # A direct assertion is used here: unittest subTest would collect
                # failures instead of raising if we nested the full contract test.
                buffer = backend() if backend is InMemorySecretDeliveryBuffer else backend(RedisTransport(lambda: 0))
                handle = buffer.stash(VALUE, "owner", "session", 5)
                self.assertIsNone(buffer.redeem(handle, "approver"))

    def test_capacity_evicts_oldest(self):
        buffer = InMemorySecretDeliveryBuffer(max_entries=1)
        first = buffer.stash(VALUE, "owner", None, 5)
        second = buffer.stash(VALUE, "owner", None, 5)
        self.assertEqual(len(buffer), 1)
        self.assertIsNone(buffer.redeem(first, "owner"))
        self.assertEqual(buffer.redeem(second, "owner"), VALUE)

    def test_factory_and_malformed_redis(self):
        self.assertEqual(build_secret_delivery_buffer().backend_name, "memory")
        with self.assertRaises(ValueError):
            build_secret_delivery_buffer("typo")
        with patch("redis.Redis", side_effect=ConnectionError(VALUE)), self.assertLogs(
            "tool_gateway.tools.secret_delivery", "WARNING"
        ) as logs:
            self.assertEqual(build_secret_delivery_buffer("redis").backend_name, "memory")
        self.assertNotIn(VALUE, str(logs.output))
        transport = RedisTransport(lambda: 0)
        with patch("redis.Redis", return_value=transport):
            self.assertEqual(build_secret_delivery_buffer("redis").backend_name, "redis")
        buffer = RedisSecretDeliveryBuffer(transport)
        for raw in ("[]", "null", "bad-json", '{"value":42,"owner_sub":"owner"}'):
            transport.set("secret_delivery:bad", raw, 5)
            self.assertIsNone(buffer.redeem("bad", "owner"))


class RedemptionTests(unittest.TestCase):
    def setUp(self):
        reset_policy_state()
        self.addCleanup(reset_policy_state)
        self.jwks = _patch_jwks()
        self.jwks.start()
        self.addCleanup(self.jwks.stop)
        self.settings = GatewaySettings(secrets_enabled=True, mutating_tools_enabled=True)
        with patch("tool_gateway.app.get_settings", return_value=self.settings):
            self.app = create_app()
        self.app.dependency_overrides[get_settings] = lambda: self.settings
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": f"Bearer {_mint_delegated('operator')}"}

    def generate(self):
        response = self.client.post("/api/v2/tools/invoke", headers=self.headers,
                                    json={"tool_name": "secrets.generate_password", "parameters": {}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        return response.json()["data"]

    def test_shared_buffer_redeems_once_with_no_store_and_metadata_only_audit(self):
        data = self.generate()
        url = "/api/v2/secrets/delivery/" + data["delivery_id"]
        with patch("tool_gateway.api.routes.secrets.emit_audit_event") as emit:
            first = self.client.get(url, headers=self.headers)
            second = self.client.get(url, headers=self.headers)
        self.assertEqual(first.json(), {"value": data["generated_password"]})
        self.assertEqual(first.headers["cache-control"], "no-store")
        self.assertEqual(second.status_code, 404)
        self.assertEqual(emit.call_count, 1)
        event = emit.call_args.args[1]
        self.assertEqual(event["event_type"], "secret_delivered")
        self.assertEqual(event["details"]["channel"], "portal_copy")
        self.assertNotIn(data["generated_password"], json.dumps(event))

    def test_foreign_approver_expiry_and_unknown_have_same_posture(self):
        data = self.generate()
        url = "/api/v2/secrets/delivery/" + data["delivery_id"]
        foreign = self.client.get(url, headers={"Authorization": f"Bearer {_mint_delegated('approver')}"})
        spent = self.client.get(url, headers=self.headers)
        unknown = self.client.get("/api/v2/secrets/delivery/unknown", headers=self.headers)
        expired_id = self.app.state.secret_delivery_buffer.stash(VALUE, "user-operator", None, 0)
        expired = self.client.get("/api/v2/secrets/delivery/" + expired_id, headers=self.headers)
        for response in (foreign, spent, unknown, expired):
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json(), unknown.json())

    def test_authentication_is_mandatory_even_in_dev_posture(self):
        self.settings = GatewaySettings(require_auth=False)
        handle = self.app.state.secret_delivery_buffer.stash(VALUE, "dev", None, 5)
        url = "/api/v2/secrets/delivery/" + handle
        self.assertEqual(self.client.get(url).status_code, 401)
        wrong = {"Authorization": f"Bearer {_mint_delegated('operator', 'wrong')}"}
        self.assertEqual(self.client.get(url, headers=wrong).status_code, 401)

    def test_disabled_discovery_and_read_only_registration(self):
        for enabled, mutating, expected in ((False, True, set()), (True, False, {"secrets.generate_password"})):
            with patch("tool_gateway.app.get_settings", return_value=GatewaySettings(
                secrets_enabled=enabled, mutating_tools_enabled=mutating
            )):
                app = create_app()
            names = {d.name for d in app.state.tool_registry.list_definitions() if d.name.startswith("secrets.")}
            self.assertEqual(names, expected)

    def test_extra_action_denied_before_transport_even_when_mutate_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.yaml"
            path.write_text(yaml.safe_dump({"version": 1, "default_decision": "deny", "rules": [
                {"id": "mutate-only", "domain": "action_authz", "enabled": True, "priority": 100,
                 "match": {"roles_any": ["operator"], "actions_any": ["tools:invoke", "tools:mutate"]},
                 "decision": {"outcome": "allow"}}, 
            ]}))
            self.settings = GatewaySettings(secrets_enabled=True, mutating_tools_enabled=True, policy_path=str(path))
            with patch("tool_gateway.tools.secrets_connector.EmailChannel.send") as send:
                response = self.client.post("/api/v2/tools/invoke", headers=self.headers, json={
                    "tool_name": "secrets.deliver",
                    "parameters": {"channel": "email", "password": VALUE, "recipient": "alice@example.com"},
                })
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["error"]["code"], "POLICY_DENIED")
            send.assert_not_called()
