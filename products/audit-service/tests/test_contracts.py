"""Contract alignment: AuditEvent conforms to audit-event.schema.json (SPEC-013 R-1).

The audit service stores and returns envelopes verbatim, so its pydantic model
must bind tightly to the shared contract that all emitters produce.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
from pydantic import ValidationError

from audit_service.schemas.audit import AuditEvent, IngestRequest, EventType, Outcome
from audit_service.schemas.summary import AuditSummaryResponse

SCHEMAS_DIR = (
    Path(__file__).resolve().parents[3] / "shared" / "shared-contracts" / "schemas"
)


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / name).read_text())


def _event(**overrides) -> AuditEvent:
    fields = {
        "event_id": "evt-1",
        "occurred_at": datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc),
        "event_type": "tool_invoked",
        "service": "tool-gateway",
        "request_id": "req-1",
        "outcome": "success",
        "details": {"tool_name": "k8s.list_pods"},
    }
    fields.update(overrides)
    return AuditEvent(**fields)


class AuditEventContractTests(unittest.TestCase):
    schema_name = "audit-event.schema.json"

    def test_model_properties_match_contract_properties(self) -> None:
        contract = _load_schema(self.schema_name)
        model_properties = set(AuditEvent.model_json_schema()["properties"])
        contract_properties = set(contract["properties"])
        self.assertEqual(model_properties, contract_properties)

    def test_contract_required_fields_are_required_or_defaulted(self) -> None:
        contract = _load_schema(self.schema_name)
        for field_name in contract.get("required", []):
            field = AuditEvent.model_fields[field_name]
            self.assertTrue(
                field.is_required() or field.get_default() is not None,
                f"AuditEvent.{field_name} may serialize as absent but the "
                f"contract requires it",
            )

    def test_model_forbids_extras_like_contract(self) -> None:
        contract = _load_schema(self.schema_name)
        if contract.get("additionalProperties") is False:
            self.assertEqual(AuditEvent.model_config.get("extra"), "forbid")

    def test_full_event_validates_against_contract(self) -> None:
        event = _event(
            subject="user-1",
            username="alice",
            actor="platform-gateway",
            roles=["operator"],
            session_id="ses-1",
        )
        jsonschema.validate(
            event.model_dump(mode="json", exclude_none=True),
            _load_schema(self.schema_name),
        )

    def test_minimal_event_validates_against_contract(self) -> None:
        # Optional identity fields omitted entirely (not nulled).
        event = _event()
        dumped = event.model_dump(mode="json", exclude_none=True)
        self.assertNotIn("subject", dumped)
        self.assertNotIn("username", dumped)
        jsonschema.validate(dumped, _load_schema(self.schema_name))

    def test_model_enum_values_match_contract(self) -> None:
        # An emitter-side event type accepted by the contract but missing
        # from the model gets the whole batch rejected with 400 at ingest,
        # so the enum vocabulary must stay in lockstep with the schema.
        contract = _load_schema(self.schema_name)
        contract_types = set(contract["properties"]["event_type"]["enum"])
        model_types = set(getattr(EventType, "__args__", EventType))
        self.assertEqual(model_types, contract_types)
        contract_outcomes = set(contract["properties"]["outcome"]["enum"])
        model_outcomes = set(getattr(Outcome, "__args__", Outcome))
        self.assertEqual(model_outcomes, contract_outcomes)

    def test_session_deleted_event_validates(self) -> None:
        # SPEC-022 R-1: the gateway emits session_deleted on workspace
        # deletes; the model must accept it like the contract does.
        event = _event(event_type="session_deleted", session_id="ses-1")
        jsonschema.validate(
            event.model_dump(mode="json", exclude_none=True),
            _load_schema(self.schema_name),
        )

    def test_incident_skill_draft_generated_event_validates(self) -> None:
        # SPEC-045 R-3: agent-platform emits the incident-anchored entry
        # point's event; it carries the incident id, never a session id.
        event = _event(
            event_type="incident_skill_draft_generated",
            details={
                "incident_id": "inc-abc123",
                "mode": "generated",
                "validation": "passed",
            },
        )
        jsonschema.validate(
            event.model_dump(mode="json", exclude_none=True),
            _load_schema(self.schema_name),
        )

    def test_document_events_validate(self) -> None:
        # SPEC-039 R-5: agent-service emits document_created /
        # document_published / cross-owner document_read; the model must
        # accept all three like the contract does.
        for event_type, details in (
            (
                "document_created",
                {
                    "document_id": "doc-1",
                    "document_type": "shift_summary",
                    "own_session_count": 1,
                    "foreign_session_count": 0,
                    "cited_record_count": 3,
                    "prose_status": "not_requested",
                },
            ),
            (
                "document_published",
                {"document_id": "doc-1", "document_type": "shift_summary"},
            ),
            (
                "document_read",
                {
                    "document_id": "doc-1",
                    "document_type": "shift_summary",
                    "owner_user_id": "alice",
                },
            ),
        ):
            event = _event(
                event_type=event_type, service="agent-service", details=details
            )
            jsonschema.validate(
                event.model_dump(mode="json", exclude_none=True),
                _load_schema(self.schema_name),
            )

    def test_model_rejects_unknown_event_type(self) -> None:
        with self.assertRaises(ValidationError):
            _event(event_type="not_a_type")

    def test_model_rejects_unknown_outcome(self) -> None:
        with self.assertRaises(ValidationError):
            _event(outcome="maybe")

    def test_model_rejects_extra_field_like_contract(self) -> None:
        payload = _event().model_dump(mode="json", exclude_none=True)
        payload["unexpected"] = "field"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(payload, _load_schema(self.schema_name))
        with self.assertRaises(ValidationError):
            AuditEvent.model_validate(
                {**payload, "occurred_at": "2026-08-01T12:00:00+00:00"}
            )


class IngestRequestContractTests(unittest.TestCase):
    def test_requires_at_least_one_event(self) -> None:
        with self.assertRaises(ValidationError):
            IngestRequest.model_validate({"events": []})

    def test_accepts_event_batch(self) -> None:
        request = IngestRequest.model_validate(
            {"events": [_event().model_dump(mode="json", exclude_none=True)]}
        )
        self.assertEqual(len(request.events), 1)


class AuditSummaryContractTests(unittest.TestCase):
    """Summary response binds to audit-summary.schema.json (SPEC-046 R-4)."""

    schema_name = "audit-summary.schema.json"

    def _summary_payload(self) -> dict:
        return AuditSummaryResponse(
            total_events=3,
            window={"event_type": "tool_invoked"},
            by_event_type=[{"name": "tool_invoked", "count": 3}],
            by_outcome=[{"name": "success", "count": 3}],
            by_service=[
                {"name": "platform-gateway", "count": 2},
                {"name": "tool-gateway", "count": 1},
            ],
            top_actors=[{"name": "alice", "count": 3}],
            decision_chain={
                "confirmation_decided": 0,
                "execution_requested": 0,
                "execution_completed": 0,
                "execution_rejected": 0,
            },
        ).model_dump(mode="json")

    def test_model_properties_match_contract_properties(self) -> None:
        contract = _load_schema(self.schema_name)
        model_properties = set(AuditSummaryResponse.model_json_schema()["properties"])
        contract_properties = set(contract["properties"])
        self.assertEqual(model_properties, contract_properties)

    def test_full_summary_validates_against_contract(self) -> None:
        jsonschema.validate(self._summary_payload(), _load_schema(self.schema_name))

    def test_empty_summary_validates_against_contract(self) -> None:
        payload = AuditSummaryResponse(
            total_events=0,
            window={},
            by_event_type=[],
            by_outcome=[],
            by_service=[],
            top_actors=[],
            decision_chain={
                "confirmation_decided": 0,
                "execution_requested": 0,
                "execution_completed": 0,
                "execution_rejected": 0,
            },
        ).model_dump(mode="json")
        jsonschema.validate(payload, _load_schema(self.schema_name))

    def test_contract_rejects_extra_section(self) -> None:
        payload = self._summary_payload()
        payload["by_details"] = []
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(payload, _load_schema(self.schema_name))

    def test_model_forbids_extras_like_contract(self) -> None:
        with self.assertRaises(ValidationError):
            AuditSummaryResponse.model_validate(
                {**self._summary_payload(), "unexpected": 1}
            )


if __name__ == "__main__":
    unittest.main()
