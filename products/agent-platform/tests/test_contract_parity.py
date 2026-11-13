"""SPEC-076 R-8: the no-new-frame contract boundary + the four-point gate.

Phase 5 surfaces the bounded diagnosis through **existing** frames only (OQ-5,
ADR-0017 Decision 6): a normal assistant turn for the orchestrator's synthesis,
the existing SPEC-025 evidence frames with SPEC-075 role attribution for the
member reads, and the existing SPEC-031 confirmation card for the proposed
remediation. It therefore changes **no** contract schema — the multi-agent wire
framing is a separate later spec (phase 6). These assertions pin that boundary so
a later change cannot silently widen the v2 contract under phase 5's name:

* ``agent-stream-event.schema.json`` and ``execution-request.schema.json`` stay
  **byte-unchanged** — no role/orchestration/member vocabulary, no new stream
  frame type, and the one mutation-path envelope stays byte-identical across its
  three packaged replicas;
* the operator-invoked trigger returns the **existing** ``agent-chat-response``
  frame (a budget-limited run rides its closed ``status="partial"``), and its
  request body is a pydantic model, never a new JSON contract file, carrying no
  ``agent_role`` wire field (SPEC-073 R-3).

Four-point-gate mapping (SPEC-018, re-affirmed by SPEC-076 R-8):

* **point 1 — deny-by-default policy + audit: preserved; attribution live.** The
  fan-out rides the same governed gateway. SPEC-075's attribution dimension is
  *populated* per participant (R-6, live). SPEC-074's agent-role axis + canonical
  rules land *ready-but-inert*: R-3 keeps the bound role off every wire field, so no
  deployed ``evaluate()`` threads a non-``None`` role and the rules never match on the
  live path — the live read-only control is in-process toolkit narrowing (point 3),
  per R-8/OQ-4. The ``event_type`` enum stays closed.
* **point 2 — identity on the one token.** Carried only by the single
  gateway-forwarded delegated token: exactly one broker exchange per user across
  the whole fan-out, no new principal, claim, identity edge, or per-role mint
  (R-3).
* **point 3 — read-only posture.** Enforced by SPEC-073 toolkit narrowing (a
  ``diagnostician`` toolkit carries no mutating tool) **plus** the loop's
  read-only admission; any remediation only *parks* on HITL and dispatches solely
  through the signed at-most-one worker with a **distinct human** approver
  (R-1/R-2/R-4). Autonomous resolve stays deferred (Decision 2).
* **point 4 — no agentscope type on the v2 contract.** The loop is
  platform-owned (no ``TeamPipeline``/``GoalPipeline``/``A2AAgent``) and the
  diagnosis surfaces through existing frames, so the two schemas below stay
  byte-unchanged (OQ-5). A guard in ``test_orchestration.py`` asserts the loop
  constructs no agentscope orchestration type.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema

from agent_service.schemas.v2 import (
    AgentChatResponse,
    AgentDiagnoseRequest,
    RemediateRequest,
)

_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA_DIR = _ROOT / "shared" / "shared-contracts" / "schemas"

# The two schemas R-8 names as byte-unchanged for phase 5.
_FROZEN_SCHEMAS = (
    "agent-stream-event.schema.json",
    "execution-request.schema.json",
)

# R-8 "byte-unchanged", encoded literally: the phase-5 sha256 baseline of each
# frozen canonical schema. Stronger than the vocabulary scan below — it fails on
# *any* byte edit — so phase 6 must re-pin these deliberately when the
# multi-agent wire frame lands, never silently.
_FROZEN_SCHEMA_SHA256 = {
    "agent-stream-event.schema.json": (
        "f2d663d9db94f0b2e8754065e53cd07abffc5ddd09ab1d97fa6e0d0d67bf4044"
    ),
    "execution-request.schema.json": (
        "c31b5ba0e7e3491fc0b7a3fa7816024528c75f06d8a452baca36d5f374369c8d"
    ),
}

# Vocabulary that would betray a multi-agent / orchestration / role frame leaking
# into the phase-5 contract. Confirmed absent from both frozen schemas today; the
# scan is the semantic "byte-unchanged w.r.t. SPEC-076" guarantee (the multi-agent
# wire framing is phase 6, so none of these may appear in phase 5).
_MULTI_AGENT_VOCAB = (
    "agent_role",
    "orchestrat",
    "diagnos",
    "member",
    "fanout",
    "fan_out",
    "runbook",
    "staged_by_role",
    "sub_agent",
    "subagent",
    "step_budget",
)

# ``execution-request.schema.json`` is packaged as three byte-identical replicas
# (canonical + the two mutation-path products that sign/verify it).
_EXECUTION_REQUEST_REPLICAS = (
    "shared/shared-contracts/schemas/execution-request.schema.json",
    "products/agent-platform/src/agent_service/contracts/execution-request.schema.json",
    "products/execution-runtime/src/execution_runtime/contracts/execution-request.schema.json",
)

# The v13 stream-frame vocabulary (SPEC-070 OQ-7 was the last additive frame).
# Phase 5 adds **no** frame type; phase 6 will deliberately extend this set.
_STREAM_FRAME_TYPES = {
    "message_start",
    "message_delta",
    "message_end",
    "error",
    "tool_call",
    "tool_result",
    "confirmation_request",
    "confirmation_result",
    "secret_delivery",
    "authorization_required",
}


def _read_bytes(rel: str) -> bytes:
    return (_ROOT / rel).read_bytes()


class TestNoNewFrameContractBoundary:
    def test_frozen_schemas_carry_no_multi_agent_vocabulary(self) -> None:
        # OQ-5 / Decision 6: the multi-agent wire frame is phase 6, so neither
        # frozen schema may name a role/orchestration/member concept in phase 5.
        for name in _FROZEN_SCHEMAS:
            text = (_SCHEMA_DIR / name).read_text()
            for token in _MULTI_AGENT_VOCAB:
                assert token not in text, (
                    f"{name} leaked multi-agent vocabulary {token!r} — the "
                    f"phase-6 frame must not widen the phase-5 contract"
                )

    def test_frozen_schemas_are_well_formed_closed_documents(self) -> None:
        # Sensitivity guard: prove the vocabulary scan above is not vacuously
        # true over an empty/stub file. Both are real, closed object schemas.
        for name in _FROZEN_SCHEMAS:
            doc = json.loads((_SCHEMA_DIR / name).read_text())
            assert doc.get("type") == "object"
            assert doc.get("additionalProperties") is False
            assert doc.get("properties"), f"{name} has no properties to freeze"

    def test_stream_event_frame_vocabulary_is_unchanged(self) -> None:
        # No orchestration/member/diagnosis frame type was added: the stream
        # contract's closed ``type`` enum is exactly the v13 set.
        doc = json.loads(
            (_SCHEMA_DIR / "agent-stream-event.schema.json").read_text()
        )
        assert set(doc["properties"]["type"]["enum"]) == _STREAM_FRAME_TYPES

    def test_execution_request_replicas_are_byte_identical(self) -> None:
        # R-4: zero new mutation-path code. The one signed envelope stays a
        # single byte-identical contract across its three packaged replicas.
        canonical = _read_bytes(_EXECUTION_REQUEST_REPLICAS[0])
        for rel in _EXECUTION_REQUEST_REPLICAS[1:]:
            assert _read_bytes(rel) == canonical, (
                f"{rel} drifted from the canonical execution-request schema"
            )

    def test_frozen_schemas_match_their_recorded_byte_baseline(self) -> None:
        # R-8 "byte-unchanged", encoded literally: any byte edit to either
        # frozen canonical schema fails here until the pin is deliberately
        # re-recorded (phase 6). Complements the vocabulary scan (semantic) and
        # the replica-identity check (cross-package) with an absolute byte-freeze
        # of the canonical documents.
        for name, expected in _FROZEN_SCHEMA_SHA256.items():
            digest = hashlib.sha256(
                _read_bytes(f"shared/shared-contracts/schemas/{name}")
            ).hexdigest()
            assert digest == expected, (
                f"{name} changed byte-for-byte (sha256 {digest} != pinned "
                f"{expected}) — R-8 freezes it for phase 5; re-pin deliberately "
                f"when the phase-6 multi-agent frame lands"
            )


class TestDiagnoseRidesExistingFrames:
    def test_no_dedicated_diagnose_contract_file_exists(self) -> None:
        # The trigger reuses the existing chat-response frame; it introduces no
        # new JSON contract document (the request body is a pydantic model only).
        for candidate in (
            "agent-diagnose-request.schema.json",
            "agent-diagnose-response.schema.json",
            "diagnose-response.schema.json",
            "diagnosis.schema.json",
        ):
            assert not (_SCHEMA_DIR / candidate).exists(), (
                f"{candidate} would be a new phase-5 frame — OQ-5 forbids it"
            )

    def test_diagnose_request_model_carries_no_agent_role_wire_field(self) -> None:
        # SPEC-073 R-3: the role is process-local, never a wire field. The
        # trigger body names a profile + goal, not a role.
        assert "agent_role" not in AgentDiagnoseRequest.model_fields
        assert (
            "agent_role"
            not in AgentDiagnoseRequest.model_json_schema()["properties"]
        )

    def test_remediate_request_model_carries_no_agent_role_wire_field(self) -> None:
        # SPEC-077 R-6 / SPEC-073 R-3: the diagnose→act trigger body names a
        # profile + the request-carried goal/diagnosis, never a role. The
        # executor role is bound inside stage_remediation and stays process-local.
        assert "agent_role" not in RemediateRequest.model_fields
        assert (
            "agent_role"
            not in RemediateRequest.model_json_schema()["properties"]
        )
        # OQ-2 request-carried: the diagnosis the operator acts on rides the body,
        # and extra="forbid" makes the no-role contract enforced, not documented.
        assert "diagnosis" in RemediateRequest.model_fields
        assert RemediateRequest.model_config.get("extra") == "forbid"

    def test_diagnose_response_validates_against_the_existing_chat_frame(self) -> None:
        # R-7/R-8: the route returns AgentChatResponse; a budget-limited run
        # rides its closed status="partial" (no new response frame, OQ-5).
        contract = json.loads(
            (_SCHEMA_DIR / "agent-chat-response.schema.json").read_text()
        )
        for status in ("ok", "partial"):
            response = AgentChatResponse(
                session_id="ses-1",
                request_id="req-1",
                content=f"diagnosis::{status}",
                status=status,
                model=None,
            )
            jsonschema.validate(
                response.model_dump(mode="json", exclude_none=True), contract
            )
