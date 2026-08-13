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

from audit_service.schemas.audit import AuditEvent, IngestRequest

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


if __name__ == "__main__":
    unittest.main()
