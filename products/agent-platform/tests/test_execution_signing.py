"""SPEC-037 R-1/R-2: canonicalization, signing, and envelope builders.

Pins the canonicalization stability contract (same input ⇒ same digest,
reordered input ⇒ same digest, changed value ⇒ different digest), the
HMAC sign/verify round-trip with tamper rejection, the request builder
shape (one signed envelope per parked call, digest over the *parked*
arguments), and both envelopes against their shared-contracts schemas.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import jsonschema
from agentscope.message import ToolCallBlock

from agent_service.services.execution_signing import (
    build_flow_request,
    build_receipt,
    build_requests,
    canonical_digest,
    canonical_json,
    sign_envelope,
    verify_envelope,
)
from agent_service.services.flow_approvals import FlowApproval
from agent_service.services.hitl_confirmations import (
    ConfirmationRegistry,
)

SCHEMAS_DIR = (
    Path(__file__).resolve().parents[3] / "shared" / "shared-contracts" / "schemas"
)

KEY = "unit-execution-signing-key"


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / name).read_text(encoding="utf-8"))


def _parked(calls=None):
    registry = ConfirmationRegistry()
    tool_calls = calls if calls is not None else [
        ToolCallBlock(
            id="call-1", name="k8s.restart_service", input='{"namespace": "ops"}'
        ),
    ]
    return registry.register("ses-1", "alice", "reply-1", tool_calls, 600)


class CanonicalizationTests(unittest.TestCase):
    def test_same_input_same_digest(self) -> None:
        args = {"namespace": "ops", "force": True}
        self.assertEqual(canonical_digest(args), canonical_digest(dict(args)))

    def test_reordered_keys_same_digest(self) -> None:
        original = {"namespace": "ops", "force": True, "grace": 30}
        reordered = {"grace": 30, "force": True, "namespace": "ops"}
        self.assertEqual(canonical_digest(original), canonical_digest(reordered))

    def test_nested_key_order_irrelevant(self) -> None:
        one = {"outer": {"b": 2, "a": 1}, "list": [{"y": 2, "x": 1}]}
        two = {"list": [{"x": 1, "y": 2}], "outer": {"a": 1, "b": 2}}
        self.assertEqual(canonical_digest(one), canonical_digest(two))

    def test_changed_value_different_digest(self) -> None:
        original = {"namespace": "ops", "force": True}
        mutated = {"namespace": "prod", "force": True}
        self.assertNotEqual(
            canonical_digest(original), canonical_digest(mutated)
        )

    def test_canonical_json_has_sorted_keys_no_whitespace(self) -> None:
        serialized = canonical_json({"b": 2, "a": [1, {"d": 4, "c": 3}]})
        self.assertEqual(serialized, '{"a":[1,{"c":3,"d":4}],"b":2}')


class SignVerifyTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        envelope = {"execution_id": "e1", "tool_name": "k8s.restart_service"}
        signature = sign_envelope(envelope, KEY)
        self.assertTrue(verify_envelope(envelope, signature, KEY))

    def test_signature_ignores_signature_field(self) -> None:
        envelope = {"execution_id": "e1", "tool_name": "t"}
        signature = sign_envelope(envelope, KEY)
        with_signature = {**envelope, "signature": signature}
        self.assertEqual(sign_envelope(with_signature, KEY), signature)
        self.assertTrue(verify_envelope(with_signature, signature, KEY))

    def test_tampered_field_rejected(self) -> None:
        envelope = {"execution_id": "e1", "args_digest": canonical_digest({"a": 1})}
        signature = sign_envelope(envelope, KEY)
        tampered = {**envelope, "args_digest": canonical_digest({"a": 2})}
        self.assertFalse(verify_envelope(tampered, signature, KEY))

    def test_wrong_key_rejected(self) -> None:
        envelope = {"execution_id": "e1", "tool_name": "t"}
        signature = sign_envelope(envelope, KEY)
        self.assertFalse(verify_envelope(envelope, signature, "other-key"))


class BuildRequestsTests(unittest.TestCase):
    def test_one_signed_request_per_parked_call(self) -> None:
        calls = [
            ToolCallBlock(
                id="call-1", name="k8s.restart_service", input='{"namespace": "ops"}'
            ),
            ToolCallBlock(
                id="call-2", name="k8s.delete_pod", input='{"name": "web-1"}'
            ),
        ]
        pending = _parked(calls)
        requests = build_requests(pending, "bob-approver", KEY)

        self.assertEqual(len(requests), 2)
        execution_ids = {request["execution_id"] for request in requests}
        self.assertEqual(len(execution_ids), 2)
        for request, call in zip(requests, calls):
            self.assertEqual(request["confirm_id"], pending.confirm_id)
            self.assertEqual(request["call_id"], call.id)
            self.assertEqual(request["session_id"], "ses-1")
            self.assertEqual(request["owner_user_id"], "alice")
            self.assertEqual(request["decider_user_id"], "bob-approver")
            self.assertEqual(request["tool_name"], call.name)
            self.assertTrue(verify_envelope(request, request["signature"], KEY))

    def test_envelope_carries_gateway_canonical_tool_name(self) -> None:
        """The envelope must name the tool the gateway registry resolves.

        Parked calls carry the sanitized model-visible name; the worker
        invokes the gateway with the envelope's tool_name verbatim, so a
        sanitized name fails closed with TOOL_NOT_FOUND (v0.23.1 fix).
        """
        registry = ConfirmationRegistry()
        pending = registry.register(
            "ses-1",
            "alice",
            "reply-1",
            [
                ToolCallBlock(
                    id="call-1",
                    name="k8s_delete_pod",
                    input='{"name": "web-1"}',
                )
            ],
            600,
            gateway_names={"k8s_delete_pod": "k8s.delete_pod"},
        )
        request = build_requests(pending, "bob-approver", KEY)[0]
        self.assertEqual(request["tool_name"], "k8s.delete_pod")
        self.assertTrue(verify_envelope(request, request["signature"], KEY))

    def test_args_digest_binds_parked_arguments(self) -> None:
        pending = _parked()
        request = build_requests(pending, "bob-approver", KEY)[0]
        self.assertEqual(
            request["args_digest"], canonical_digest({"namespace": "ops"})
        )
        # Reordered parked arguments produce the identical digest.
        pending_reordered = _parked([
            ToolCallBlock(
                id="call-1", name="k8s.restart_service",
                input='{"namespace": "ops"}',
            ),
        ])
        reordered = build_requests(pending_reordered, "bob", KEY)[0]
        self.assertEqual(reordered["args_digest"], request["args_digest"])

    def test_request_validates_against_contract(self) -> None:
        request = build_requests(_parked(), "bob-approver", KEY)[0]
        jsonschema.validate(
            request, _load_schema("execution-request.schema.json")
        )

    def test_empty_batch_builds_nothing(self) -> None:
        self.assertEqual(build_requests(_parked([]), "bob", KEY), [])


def _flow_authority(**overrides):
    """A recorded flow authority (SPEC-051 R-1) as ``build_flow_request`` keys on."""
    kwargs = dict(
        session_id="ses-1",
        confirm_id="conf-flow-1",
        owner_user_id="alice",
        decider_user_id="bob-approver",
        skill_id="samples/password-reset",
        origin="http://admin.local",
        ttl=900.0,
    )
    kwargs.update(overrides)
    return FlowApproval(**kwargs)


class BuildFlowRequestTests(unittest.TestCase):
    """SPEC-051 R-3: signing one auto-unlocked browser write under a flow
    authority — a single-call sibling to ``build_requests`` that reuses the
    approving card's correlation/identity but binds the *new* call's args."""

    def test_envelope_shape_and_signature_verifies(self) -> None:
        request = build_flow_request(
            call_id="call-9",
            tool_name="web.click",
            parameters={"ref": 12},
            flow_approval=_flow_authority(),
            key=KEY,
        )
        for field in (
            "execution_id",
            "confirm_id",
            "call_id",
            "session_id",
            "owner_user_id",
            "decider_user_id",
            "tool_name",
            "args_digest",
            "requested_at",
            "signature",
        ):
            self.assertIn(field, request)
        self.assertEqual(request["call_id"], "call-9")
        self.assertEqual(request["tool_name"], "web.click")
        self.assertTrue(verify_envelope(request, request["signature"], KEY))

    def test_correlation_and_identity_come_from_flow_authority(self) -> None:
        """ADR-0007: one operator decision per flow — the envelope reuses the
        approving card's confirm_id/session/owner/decider, not the new call's."""
        authority = _flow_authority(
            confirm_id="conf-approving-card",
            session_id="ses-flow",
            owner_user_id="owner-op",
            decider_user_id="approver-op",
        )
        request = build_flow_request(
            call_id="call-9",
            tool_name="web.click",
            parameters={"ref": 1},
            flow_approval=authority,
            key=KEY,
        )
        self.assertEqual(request["confirm_id"], "conf-approving-card")
        self.assertEqual(request["session_id"], "ses-flow")
        self.assertEqual(request["owner_user_id"], "owner-op")
        self.assertEqual(request["decider_user_id"], "approver-op")

    def test_args_digest_binds_the_new_call_parameters(self) -> None:
        """Each unlocked write is individually bound to its own arguments —
        the digest is over the new call's parameters, not the approving card's."""
        request = build_flow_request(
            call_id="call-9",
            tool_name="web.click",
            parameters={"ref": 12, "double_click": False},
            flow_approval=_flow_authority(),
            key=KEY,
        )
        self.assertEqual(
            request["args_digest"],
            canonical_digest({"ref": 12, "double_click": False}),
        )
        # Reordered parameters produce the identical digest.
        reordered = build_flow_request(
            call_id="call-9",
            tool_name="web.click",
            parameters={"double_click": False, "ref": 12},
            flow_approval=_flow_authority(),
            key=KEY,
        )
        self.assertEqual(reordered["args_digest"], request["args_digest"])
        # Changed parameters produce a different digest.
        changed = build_flow_request(
            call_id="call-9",
            tool_name="web.click",
            parameters={"ref": 13, "double_click": False},
            flow_approval=_flow_authority(),
            key=KEY,
        )
        self.assertNotEqual(changed["args_digest"], request["args_digest"])

    def test_execution_id_is_fresh_per_call(self) -> None:
        authority = _flow_authority()
        first = build_flow_request("call-1", "web.click", {"ref": 1}, authority, KEY)
        second = build_flow_request("call-2", "web.type", {"ref": 2}, authority, KEY)
        self.assertNotEqual(first["execution_id"], second["execution_id"])
        self.assertEqual(first["call_id"], "call-1")
        self.assertEqual(second["call_id"], "call-2")
        # Both still reuse the same approving card's confirm_id.
        self.assertEqual(first["confirm_id"], second["confirm_id"])

    def test_validates_against_execution_request_contract(self) -> None:
        """The auto-signed envelope is indistinguishable from a card-signed one
        at the contract boundary, so the worker verifies it identically."""
        request = build_flow_request(
            call_id="call-9",
            tool_name="web.click",
            parameters={"ref": 12},
            flow_approval=_flow_authority(),
            key=KEY,
        )
        jsonschema.validate(
            request, _load_schema("execution-request.schema.json")
        )

    def test_tampered_envelope_rejected(self) -> None:
        request = build_flow_request(
            call_id="call-9",
            tool_name="web.click",
            parameters={"ref": 12},
            flow_approval=_flow_authority(),
            key=KEY,
        )
        forged = {**request, "tool_name": "web.evaluate"}
        self.assertFalse(verify_envelope(forged, forged["signature"], KEY))


class BuildReceiptTests(unittest.TestCase):
    def test_receipt_closes_request_and_validates(self) -> None:
        request = build_requests(_parked(), "bob-approver", KEY)[0]
        outcome = {"status": "success", "data": {"restarted": True}}
        receipt = build_receipt(request, "succeeded", outcome, "req-9", KEY)

        self.assertEqual(receipt["execution_id"], request["execution_id"])
        self.assertEqual(receipt["status"], "succeeded")
        self.assertEqual(receipt["outcome_digest"], canonical_digest(outcome))
        self.assertEqual(receipt["request_id"], "req-9")
        self.assertTrue(verify_envelope(receipt, receipt["signature"], KEY))
        jsonschema.validate(
            receipt, _load_schema("execution-receipt.schema.json")
        )

    def test_receipt_tamper_rejected(self) -> None:
        request = build_requests(_parked(), "bob-approver", KEY)[0]
        receipt = build_receipt(request, "succeeded", {"ok": True}, "req-9", KEY)
        forged = {**receipt, "status": "failed"}
        self.assertFalse(verify_envelope(forged, forged["signature"], KEY))


if __name__ == "__main__":
    unittest.main()
