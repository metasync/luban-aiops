"""V3 route contracts. Durable authority itself is proven in tests/failure/."""

from __future__ import annotations

import os
import unittest
import uuid
from copy import deepcopy
from types import SimpleNamespace
from unittest import mock
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from execution_runtime.app import create_app
from execution_runtime.services.execution_ledger import ClaimDecision, ExecutionLedger
from execution_runtime.core.config import get_settings
from execution_runtime.services import execution_signing as signing

KEY = "unit-signing-key"
TOKEN = "unit-handoff-token"
HANDOFF_PATH = "/api/v1/executions/handoff"

GATEWAY_RESULT = {
    "tool_name": "k8s.scale_deployment",
    "status": "success",
    "data": {"scaled": True},
    "evidence": {"executed_at": "2026-09-23T00:00:00Z", "duration_ms": 1,
                 "risk_level": "write", "source_system": "fixture"},
}


def _arguments() -> dict:
    return {"namespace": "prod", "replicas": 3}


def _envelope(arguments: dict, key: str = KEY, **overrides) -> dict:
    envelope = {
        "protocol_version": 3,
        "run_id": str(uuid.uuid4()),
        "admission_epoch": str(uuid.uuid4()),
        "approval_kind": "action",
        "expires_at": "2026-08-27T10:10:00Z",
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


class RouteLedger(ExecutionLedger):
    """Explicit route-only double; no environment can select this implementation."""
    def __init__(self):
        super().__init__("", KEY, "")
        self.envelope, self.facts, self.claims = None, [], 0
        self.connection_open = False

    def claim(self, envelope, current_request_id):
        if self.claims:
            return ClaimDecision(reason="metadata_replay")
        self.envelope, self.claims = deepcopy(envelope), 1
        return ClaimDecision(SimpleNamespace(owner_id=str(uuid.uuid4())))

    def open_send(self, permit, envelope):
        conn = SimpleNamespace(closed=False)
        self.connection_open = True
        def close():
            conn.closed = True
            self.connection_open = False
        conn.close = close
        return conn

    def finish(self, conn, envelope, fact, *, stop_reason=None):
        assert self.connection_open and not conn.closed
        self.facts.append(deepcopy(fact))
        return "inserted"

    def lookup(self, execution_id, *, replay=True):
        result = self.empty("available", execution_id, replay=replay, as_of="2026-08-27T10:01:00Z")
        result.update({name: self.envelope[name] for name in
                       ("confirm_id", "call_id", "session_id", "run_id", "admission_epoch", "tool_name", "requested_at", "expires_at")})
        result.update(request_digest=signing.canonical_digest(self.envelope), attempt_request_id="resume-req-1",
                      claimed_at="2026-08-27T10:00:01Z", observe_by="2026-08-27T10:02:01Z",
                      state="result_recorded" if self.facts else "dispatch_claimed",
                      receipt=self.facts[0]["receipt"] if self.facts else None, observations=deepcopy(self.facts))
        return result


class HandoffTestBase(unittest.TestCase):
    """TestClient wired with configured secrets and a mocked executor."""

    ENV = {
        "EXECUTION_SIGNING_KEY": KEY,
        "EXECUTION_HANDOFF_TOKEN": TOKEN,
        "EXECUTION_STATE_STORE_BACKEND": "memory",
        "TOOL_GATEWAY_URL": "http://fixture.invalid",
        "EXECUTION_ADMISSION_ENABLED": "false",
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
        self.ledger = RouteLedger()
        client = TestClient(create_app(ledger=self.ledger))
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
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["status"], "unavailable")
        self.assertEqual(body["configured_backend"], "memory")
        self.assertEqual(body["actual_backend"], "unavailable")
        self.assertFalse(body["protocol_ready"])
        self.assertTrue(body["signing_key_configured"])
        self.assertTrue(body["handoff_token_configured"])


class HappyPathTests(HandoffTestBase):
    def test_handoff_executes_and_signs_receipt(self) -> None:
        client = self._start()
        response = client.post(HANDOFF_PATH, json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["result"], GATEWAY_RESULT)
        receipt = payload["observation"]["receipt"]
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
        self.assertEqual(kwargs["execution_id"], self.envelope["execution_id"])
        self.assertEqual(_args[4], "resume-req-1")

    def test_completion_audit_references_the_durable_observation(self) -> None:
        client = self._start()
        with mock.patch("execution_runtime.api.routes.handoff.emit_audit_event") as emit:
            response = client.post(HANDOFF_PATH, json=self.body, headers=self.headers)
        fact = response.json()["observation"]
        event = emit.call_args.args[1]
        self.assertEqual(event["request_id"], "resume-req-1")
        self.assertEqual(event["details"]["state"], "result_recorded")
        self.assertEqual(event["details"]["reason_code"], "none")
        self.assertEqual(event["details"]["observation_id"], fact["observation_id"])
        self.assertEqual(event["details"]["attempt_request_id"], fact["attempt_request_id"])
        self.assertEqual(self.ledger.facts[0], fact)

    def test_audit_start_failure_cannot_erase_recorded_result(self) -> None:
        client = self._start()
        with mock.patch("execution_runtime.api.routes.handoff.emit_audit_event",
                        side_effect=RuntimeError("audit unavailable")):
            response = client.post(HANDOFF_PATH, json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["kind"], "original_result")
        self.assertEqual(self.ledger.facts[0], response.json()["observation"])
        self.assertEqual(self.execute_tool_mock.call_count, 1)

    def test_handoff_closes_execution_record(self) -> None:
        client = self._start()
        response = client.post(HANDOFF_PATH, json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.ledger.facts[0], response.json()["observation"])
        self.assertEqual(self.ledger.facts[0]["receipt"]["status"], "succeeded")
        self.assertFalse(self.ledger.connection_open)

    def test_late_arrival_keeps_existing_receipt(self) -> None:
        client = self._start()
        # The resumed stream's timeout close lands before the worker does.
        from execution_runtime.services.execution_records import InMemoryExecutionRecordStore
        store = InMemoryExecutionRecordStore()
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
        self.assertEqual(response.json()["observation"]["receipt"]["status"], "succeeded")
        row = store._by_key[
            (self.envelope["confirm_id"], self.envelope["call_id"])
        ]
        self.assertEqual(row["status"], "timeout")


class ApprovalKindForwardingTests(HandoffTestBase):
    """SPEC-054 R-2 / ADR-0010: the worker forwards the provenance it verified.

    The gateway never sees the signed envelope — verification happens here, and
    the invoke hop carries a plain payload — so R-2's "the gateway enforces
    provenance on the browser write path" needs the value threaded through. It
    is a provenance handle, not authority: this route evaluates no provenance
    semantics, and ``verify_envelope`` needed no change because it already
    covers every field present.
    """

    def _post_with_kind(self, client, kind: str | None, *, re_sign: bool = True):
        envelope = dict(self.envelope)
        if kind is not None:
            envelope["approval_kind"] = kind
        if re_sign:
            envelope["signature"] = signing.sign_envelope(envelope, KEY)
        body = dict(self.body)
        body["request"] = envelope
        return client.post(HANDOFF_PATH, json=body, headers=self.headers), envelope

    def test_flow_provenance_reaches_the_executor(self) -> None:
        client = self._start()
        response, envelope = self._post_with_kind(client, "flow")
        self.assertEqual(response.status_code, 200)
        _args, kwargs = self.execute_tool_mock.call_args
        self.assertEqual(kwargs["approval_kind"], "flow")
        # The signature covered the field, so verification accepted it as
        # signed rather than as a body-supplied claim.
        self.assertTrue(
            signing.verify_envelope(envelope, envelope["signature"], KEY)
        )

    def test_action_provenance_reaches_the_executor(self) -> None:
        client = self._start()
        response, _envelope = self._post_with_kind(client, "action")
        self.assertEqual(response.status_code, 200)
        _args, kwargs = self.execute_tool_mock.call_args
        self.assertEqual(kwargs["approval_kind"], "action")

    def test_absent_provenance_is_not_executable(self) -> None:
        client = self._start()
        self.body["request"].pop("approval_kind")
        self.body["request"]["signature"] = signing.sign_envelope(self.body["request"], KEY)
        response = client.post(HANDOFF_PATH, json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["reason_code"], "bad_request")
        self.execute_tool_mock.assert_not_called()

    def test_forged_provenance_rejected_before_execution(self) -> None:
        """Flipping the declared kind without re-signing is tampering: the
        value sits inside the HMAC, so it cannot be talked up from ``action``
        to ``flow`` (or down) in transit."""
        client = self._start()
        response, _envelope = self._post_with_kind(
            client, "flow", re_sign=False
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["reason_code"], "signature_invalid"
        )
        self.execute_tool_mock.assert_not_called()

    def test_receipt_shape_is_unchanged_by_the_field(self) -> None:
        """The receipt closes the request identically whichever builder signed
        it — provenance is a browser-path concern, not a receipt input."""
        client = self._start()
        response, envelope = self._post_with_kind(client, "flow")
        receipt = response.json()["observation"]["receipt"]
        self.assertEqual(receipt["status"], "succeeded")
        self.assertEqual(receipt["execution_id"], envelope["execution_id"])
        self.assertNotIn("approval_kind", receipt)
        self.assertTrue(
            signing.verify_envelope(receipt, receipt["signature"], KEY)
        )


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
        self.assertEqual(response.json()["reason_code"], "unauthorized")
        self.execute_tool_mock.assert_not_called()

    def test_wrong_token_rejected(self) -> None:
        client = self._start()
        headers = {**self.headers, "Authorization": "Bearer wrong-token"}
        response = self._post(client, headers=headers)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["reason_code"], "unauthorized")
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
        self.assertEqual(response.json()["reason_code"], "unauthorized")
        self.execute_tool_mock.assert_not_called()

    def test_non_ascii_signature_rejected_structurally(self) -> None:
        client = self._start()
        body = {
            **self.body,
            "request": {**self.envelope, "signature": "caf\u00e9" * 4},
        }
        response = self._post(client, body=body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["reason_code"], "bad_request")
        self.execute_tool_mock.assert_not_called()

    def test_unset_handoff_token_rejects_everything(self) -> None:
        get_settings.cache_clear()
        os.environ["EXECUTION_HANDOFF_TOKEN"] = ""
        self.addCleanup(get_settings.cache_clear)
        client = self._start()
        response = self._post(client)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["reason_code"], "unauthorized")
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
            response.json()["reason_code"], "signature_invalid"
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
            response.json()["reason_code"], "signing_unavailable"
        )
        self.execute_tool_mock.assert_not_called()

    def test_mutated_arguments_rejected(self) -> None:
        client = self._start()
        mutated = dict(self.body)
        mutated["arguments"] = {"namespace": "prod", "replicas": 99}
        response = self._post(client, body=mutated)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["reason_code"], "args_digest_mismatch"
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
        self.assertEqual(response.json()["reason_code"], "bad_request")
        self.execute_tool_mock.assert_not_called()

    def test_incomplete_envelope_rejected(self) -> None:
        client = self._start()
        incomplete = dict(self.body)
        envelope = dict(self.envelope)
        del envelope["call_id"]
        incomplete["request"] = envelope
        response = self._post(client, body=incomplete)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["reason_code"], "bad_request")
        self.execute_tool_mock.assert_not_called()


class MetadataReplayHandoffTests(HandoffTestBase):
    def test_replayed_handoff_does_not_reexecute(self) -> None:
        client = self._start()
        first = client.post(HANDOFF_PATH, json=self.body, headers=self.headers)
        second = client.post(HANDOFF_PATH, json=self.body, headers=self.headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["kind"], "original_result")
        self.assertEqual(second.json()["kind"], "status_only")
        self.assertNotIn("result", second.json())
        self.assertEqual(first.json()["observation"]["receipt"], second.json()["recovery"]["receipt"])
        self.assertEqual(self.execute_tool_mock.call_count, 1)

    def test_error_results_still_close_with_receipt(self) -> None:
        failed_result = {
            "tool_name": "k8s.scale_deployment",
            "status": "error",
            "evidence": GATEWAY_RESULT["evidence"],
            "error": {"code": "TIMEOUT", "message": "gateway timed out"},
        }
        client = self._start(result=failed_result)
        response = client.post(HANDOFF_PATH, json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        receipt = response.json()["observation"]["receipt"]
        self.assertEqual(receipt["status"], "timeout")
        self.assertEqual(self.ledger.facts[0]["receipt"]["status"], "timeout")


if __name__ == "__main__":
    unittest.main()
