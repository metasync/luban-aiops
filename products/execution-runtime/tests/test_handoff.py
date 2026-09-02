"""Handoff route: auth + verification matrix, receipts, single-flight (R-2/R-3/R-5)."""

from __future__ import annotations

import os
import unittest
import uuid
from unittest import mock
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from execution_runtime.app import app
from execution_runtime.core.config import get_settings
from execution_runtime.services import execution_signing as signing

KEY = "unit-signing-key"
TOKEN = "unit-handoff-token"
HANDOFF_PATH = "/api/v1/executions/handoff"

GATEWAY_RESULT = {
    "tool_name": "k8s.scale_deployment",
    "status": "success",
    "request_id": "resume-req-1",
}


def _arguments() -> dict:
    return {"namespace": "prod", "replicas": 3}


def _envelope(arguments: dict, key: str = KEY, **overrides) -> dict:
    envelope = {
        "execution_id": str(uuid.uuid4()),
        "confirm_id": str(uuid.uuid4()),
        "call_id": str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
        "owner_user_id": "owner",
        "decider_user_id": "decider",
        "tool_name": "k8s.scale_deployment",
        "args_digest": signing.canonical_digest(arguments),
        "requested_at": "2026-08-27T10:00:00Z",
        **overrides,
    }
    envelope["signature"] = signing.sign_envelope(envelope, key)
    return envelope


class HandoffTestBase(unittest.TestCase):
    """TestClient wired with configured secrets and a mocked executor."""

    ENV = {
        "EXECUTION_SIGNING_KEY": KEY,
        "EXECUTION_HANDOFF_TOKEN": TOKEN,
        "EXECUTION_STATE_STORE_BACKEND": "memory",
    }

    def setUp(self):
        get_settings.cache_clear()
        env_patcher = mock.patch.dict(os.environ, self.ENV, clear=False)
        env_patcher.start()
        self.addCleanup(env_patcher.stop)
        self.addCleanup(get_settings.cache_clear)
        self.arguments = _arguments()
        self.envelope = _envelope(self.arguments)
        self.body = {
            "request": self.envelope,
            "arguments": self.arguments,
            "delegated_token": "delegated-tok",
        }
        self.headers = {
            "Authorization": f"Bearer {TOKEN}",
            "x-request-id": "resume-req-1",
        }

    def _start(self, result: dict | None = None):
        """Enter lifespan with the executor mocked; returns the client."""
        executor_patch = mock.patch(
            "execution_runtime.api.routes.handoff.execute_tool",
            new=AsyncMock(return_value=result or dict(GATEWAY_RESULT)),
        )
        executor_patch.start()
        self.addCleanup(executor_patch.stop)
        client = TestClient(app)
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        from execution_runtime.api.routes import handoff as handoff_module

        self.execute_tool_mock = handoff_module.execute_tool
        return client


class HealthTests(HandoffTestBase):
    def test_health_live(self) -> None:
        client = self._start()
        response = client.get("/health/live")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "execution-runtime")

    def test_health_ready_reports_configuration(self) -> None:
        client = self._start()
        response = client.get("/health/ready")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["store_backend"], "memory")
        self.assertTrue(body["store_ready"])
        self.assertTrue(body["signing_key_configured"])
        self.assertTrue(body["handoff_token_configured"])


class HappyPathTests(HandoffTestBase):
    def test_handoff_executes_and_signs_receipt(self) -> None:
        client = self._start()
        response = client.post(HANDOFF_PATH, json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["result"], GATEWAY_RESULT)
        receipt = payload["receipt"]
        self.assertEqual(receipt["status"], "succeeded")
        self.assertEqual(receipt["execution_id"], self.envelope["execution_id"])
        self.assertEqual(receipt["request_id"], "resume-req-1")
        self.assertTrue(
            signing.verify_envelope(receipt, receipt["signature"], KEY)
        )
        # The executor saw the forwarded delegated token.
        _args, kwargs = self.execute_tool_mock.call_args
        self.assertIn("delegated-tok", _args)
        # SPEC-049 R-1: the signed envelope's chat session id is threaded
        # to the executor so the gateway call carries it for stateful
        # session continuity across the owner→approver switch.
        self.assertEqual(kwargs["session_id"], self.envelope["session_id"])

    def test_handoff_closes_execution_record(self) -> None:
        client = self._start()
        response = client.post(HANDOFF_PATH, json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        store = client.app.state.execution_record_store
        row = store._by_key[
            (self.envelope["confirm_id"], self.envelope["call_id"])
        ]
        self.assertEqual(row["status"], "succeeded")
        self.assertTrue(row["digest_match"])

    def test_late_arrival_keeps_existing_receipt(self) -> None:
        client = self._start()
        # The resumed stream's timeout close lands before the worker does.
        store = client.app.state.execution_record_store
        timeout_receipt = signing.build_receipt(
            self.envelope, "timeout", {"status": "error"}, "resume-req-1", KEY
        )
        from execution_runtime.services.execution_records import (
            make_execution_record,
        )

        store.close_execution(
            make_execution_record(self.envelope), timeout_receipt, True
        )

        response = client.post(HANDOFF_PATH, json=self.body, headers=self.headers)
        # The handoff itself succeeded; the record keeps the first close.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["receipt"]["status"], "succeeded")
        row = store._by_key[
            (self.envelope["confirm_id"], self.envelope["call_id"])
        ]
        self.assertEqual(row["status"], "timeout")


class RejectionMatrixTests(HandoffTestBase):
    def _post(self, client, body=None, headers=None):
        return client.post(
            HANDOFF_PATH,
            json=body if body is not None else self.body,
            headers=headers if headers is not None else self.headers,
        )

    def test_missing_authorization_rejected(self) -> None:
        client = self._start()
        headers = {k: v for k, v in self.headers.items() if k != "Authorization"}
        response = self._post(client, headers=headers)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["reason"], "unauthorized")
        self.execute_tool_mock.assert_not_called()

    def test_wrong_token_rejected(self) -> None:
        client = self._start()
        headers = {**self.headers, "Authorization": "Bearer wrong-token"}
        response = self._post(client, headers=headers)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["reason"], "unauthorized")
        self.execute_tool_mock.assert_not_called()

    def test_non_ascii_bearer_rejected_structurally(self) -> None:
        # compare_digest on str raises TypeError for non-ASCII; the
        # route compares bytes so an attacker-controlled header still
        # lands the audited unauthorized rejection, never a bare 500.
        # Headers arrive latin-1 decoded off the wire, so send the raw
        # bytes to replicate the vector.
        client = self._start()
        headers = {**self.headers, "Authorization": "Bearer café".encode("latin-1")}
        response = self._post(client, headers=headers)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["reason"], "unauthorized")
        self.execute_tool_mock.assert_not_called()

    def test_non_ascii_signature_rejected_structurally(self) -> None:
        client = self._start()
        body = {
            **self.body,
            "request": {**self.envelope, "signature": "caf\u00e9" * 4},
        }
        response = self._post(client, body=body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["reason"], "signature_invalid")
        self.execute_tool_mock.assert_not_called()

    def test_unset_handoff_token_rejects_everything(self) -> None:
        get_settings.cache_clear()
        os.environ["EXECUTION_HANDOFF_TOKEN"] = ""
        self.addCleanup(get_settings.cache_clear)
        client = self._start()
        response = self._post(client)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["reason"], "unauthorized")
        self.execute_tool_mock.assert_not_called()

    def test_tampered_envelope_rejected(self) -> None:
        client = self._start()
        tampered = dict(self.body)
        envelope = dict(self.envelope)
        envelope["tool_name"] = "k8s.delete_namespace"
        tampered["request"] = envelope
        response = self._post(client, body=tampered)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["reason"], "signature_invalid"
        )
        self.execute_tool_mock.assert_not_called()

    def test_unset_signing_key_rejects_everything(self) -> None:
        get_settings.cache_clear()
        os.environ["EXECUTION_SIGNING_KEY"] = ""
        self.addCleanup(get_settings.cache_clear)
        client = self._start()
        response = self._post(client)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["reason"], "signature_invalid"
        )
        self.execute_tool_mock.assert_not_called()

    def test_mutated_arguments_rejected(self) -> None:
        client = self._start()
        mutated = dict(self.body)
        mutated["arguments"] = {"namespace": "prod", "replicas": 99}
        response = self._post(client, body=mutated)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["reason"], "args_digest_mismatch"
        )
        self.execute_tool_mock.assert_not_called()

    def test_malformed_body_rejected(self) -> None:
        client = self._start()
        response = client.post(
            HANDOFF_PATH,
            content=b"this is not json",
            headers={**self.headers, "content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["reason"], "bad_request")
        self.execute_tool_mock.assert_not_called()

    def test_incomplete_envelope_rejected(self) -> None:
        client = self._start()
        incomplete = dict(self.body)
        envelope = dict(self.envelope)
        del envelope["call_id"]
        incomplete["request"] = envelope
        response = self._post(client, body=incomplete)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["reason"], "bad_request")
        self.execute_tool_mock.assert_not_called()


class SingleFlightHandoffTests(HandoffTestBase):
    def test_replayed_handoff_does_not_reexecute(self) -> None:
        client = self._start()
        first = client.post(HANDOFF_PATH, json=self.body, headers=self.headers)
        second = client.post(HANDOFF_PATH, json=self.body, headers=self.headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["receipt"], second.json()["receipt"])
        self.assertEqual(self.execute_tool_mock.call_count, 1)

    def test_error_results_still_close_with_receipt(self) -> None:
        failed_result = {
            "tool_name": "k8s.scale_deployment",
            "status": "error",
            "request_id": "resume-req-1",
            "error": {"code": "TIMEOUT", "message": "gateway timed out"},
        }
        client = self._start(result=failed_result)
        response = client.post(HANDOFF_PATH, json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        receipt = response.json()["receipt"]
        self.assertEqual(receipt["status"], "timeout")
        store = client.app.state.execution_record_store
        row = store._by_key[
            (self.envelope["confirm_id"], self.envelope["call_id"])
        ]
        self.assertEqual(row["status"], "timeout")


if __name__ == "__main__":
    unittest.main()
