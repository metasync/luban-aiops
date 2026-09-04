"""Worker signing copy: round-trip, tamper, cross-verification (SPEC-038 R-2).

The cross-verification leg loads agent-platform's ``execution_signing``
module from source (its ``PendingConfirmation`` import is stubbed) and
pins the two copies together: an envelope signed there verifies under
the worker copy and vice versa, so canonicalization and HMAC usage can
never drift between the signer and its first verifier.
"""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
import uuid
from pathlib import Path

from execution_runtime.services import execution_signing as worker

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_SIGNING_PATH = (
    REPO_ROOT
    / "products"
    / "agent-platform"
    / "src"
    / "agent_service"
    / "services"
    / "execution_signing.py"
)

KEY = "unit-test-signing-key"


def _load_agent_signing():
    """Load agent-platform's signing module with the kernel import stubbed."""
    stubbed = [
        "agent_service",
        "agent_service.services",
        "agent_service.services.hitl_confirmations",
        "agent_service.services.flow_approvals",
    ]
    saved = {name: sys.modules.get(name) for name in stubbed}
    package = types.ModuleType("agent_service")
    services = types.ModuleType("agent_service.services")
    hitl = types.ModuleType("agent_service.services.hitl_confirmations")
    hitl.PendingConfirmation = object  # type annotation target only
    # SPEC-051 R-3: build_flow_request annotates its flow authority with
    # FlowApproval (a lazy ``from __future__ import annotations`` string), so
    # the isolated load only needs the name to resolve — mirror the hitl stub.
    flow_approvals = types.ModuleType("agent_service.services.flow_approvals")
    flow_approvals.FlowApproval = object  # type annotation target only
    package.services = services
    services.hitl_confirmations = hitl
    services.flow_approvals = flow_approvals
    sys.modules["agent_service"] = package
    sys.modules["agent_service.services"] = services
    sys.modules["agent_service.services.hitl_confirmations"] = hitl
    sys.modules["agent_service.services.flow_approvals"] = flow_approvals
    try:
        spec = importlib.util.spec_from_file_location(
            "agent_execution_signing_under_test", AGENT_SIGNING_PATH
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


def _make_envelope(key: str, **overrides) -> dict:
    envelope = {
        "execution_id": str(uuid.uuid4()),
        "confirm_id": str(uuid.uuid4()),
        "call_id": str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
        "owner_user_id": "owner",
        "decider_user_id": "decider",
        "tool_name": "k8s.scale_deployment",
        "args_digest": worker.canonical_digest({"replicas": 3}),
        "requested_at": "2026-08-27T10:00:00Z",
        **overrides,
    }
    envelope["signature"] = worker.sign_envelope(envelope, key)
    return envelope


class CanonicalizationTests(unittest.TestCase):
    def test_canonical_json_sorts_keys_without_whitespace(self) -> None:
        self.assertEqual(
            worker.canonical_json({"b": 1, "a": {"d": [1, 2], "c": True}}),
            '{"a":{"c":true,"d":[1,2]},"b":1}',
        )

    def test_canonical_digest_ignores_key_order(self) -> None:
        self.assertEqual(
            worker.canonical_digest({"a": 1, "b": 2}),
            worker.canonical_digest({"b": 2, "a": 1}),
        )


class EnvelopeRoundTripTests(unittest.TestCase):
    def test_sign_and_verify_round_trip(self) -> None:
        envelope = _make_envelope(KEY)
        self.assertTrue(
            worker.verify_envelope(envelope, envelope["signature"], KEY)
        )

    def test_tampered_field_rejected(self) -> None:
        envelope = _make_envelope(KEY)
        envelope["tool_name"] = "k8s.delete_namespace"
        self.assertFalse(
            worker.verify_envelope(envelope, envelope["signature"], KEY)
        )

    def test_wrong_key_rejected(self) -> None:
        envelope = _make_envelope(KEY)
        self.assertFalse(
            worker.verify_envelope(envelope, envelope["signature"], "other-key")
        )

    def test_signature_field_excluded_from_signed_payload(self) -> None:
        envelope = _make_envelope(KEY)
        # Re-signing with a pre-existing signature field present yields
        # the same signature (the field never enters the payload).
        self.assertEqual(
            worker.sign_envelope(envelope, KEY), envelope["signature"]
        )


class ReceiptTests(unittest.TestCase):
    def test_build_receipt_signs_mapped_outcome(self) -> None:
        request = _make_envelope(KEY)
        outcome = {"tool_name": request["tool_name"], "status": "success"}
        receipt = worker.build_receipt(request, "succeeded", outcome, "req-1", KEY)
        self.assertEqual(receipt["execution_id"], request["execution_id"])
        self.assertEqual(receipt["status"], "succeeded")
        self.assertEqual(receipt["request_id"], "req-1")
        self.assertEqual(
            receipt["outcome_digest"], worker.canonical_digest(outcome)
        )
        self.assertTrue(
            worker.verify_envelope(receipt, receipt["signature"], KEY)
        )
        # The outcome itself is never carried in full.
        self.assertNotIn("outcome", receipt)


class CrossVerificationTests(unittest.TestCase):
    """Pins the worker copy against agent-platform's signer."""

    def setUp(self) -> None:
        self.agent = _load_agent_signing()

    def test_agent_signed_envelope_verifies_under_worker_copy(self) -> None:
        arguments = {"namespace": "prod", "replicas": 5}
        envelope = {
            "execution_id": str(uuid.uuid4()),
            "confirm_id": str(uuid.uuid4()),
            "call_id": str(uuid.uuid4()),
            "session_id": str(uuid.uuid4()),
            "owner_user_id": "owner",
            "decider_user_id": "decider",
            "tool_name": "k8s.scale_deployment",
            "args_digest": self.agent.canonical_digest(arguments),
            "requested_at": "2026-08-27T10:00:00Z",
        }
        envelope["signature"] = self.agent.sign_envelope(envelope, KEY)
        self.assertTrue(
            worker.verify_envelope(envelope, envelope["signature"], KEY)
        )
        self.assertEqual(
            worker.canonical_digest(arguments), envelope["args_digest"]
        )

    def test_worker_signed_receipt_verifies_under_agent_copy(self) -> None:
        request = _make_envelope(KEY)
        receipt = worker.build_receipt(
            request, "failed", {"status": "error"}, "req-9", KEY
        )
        self.assertTrue(
            self.agent.verify_envelope(receipt, receipt["signature"], KEY)
        )

    def test_canonicalization_agrees_across_copies(self) -> None:
        obj = {"z": [3, {"q": None}], "a": "b"}
        self.assertEqual(
            worker.canonical_json(obj), self.agent.canonical_json(obj)
        )
        self.assertEqual(
            worker.canonical_digest(obj), self.agent.canonical_digest(obj)
        )


if __name__ == "__main__":
    unittest.main()
