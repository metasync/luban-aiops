"""Contract alignment: Incident/TriageReport bind to the shared schemas (SPEC-015 R-1).

incident-service builds and serves envelopes verbatim, so its pydantic models
must bind tightly to the shared contracts — same pattern as the SPEC-013
audit-event and SPEC-014 skill contract tests.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
from pydantic import ValidationError

from incident_service.schemas.incident import (
    Incident,
    IncidentSource,
    IncidentStatus,
    TriageReport,
)

SCHEMAS_DIR = (
    Path(__file__).resolve().parents[3] / "shared" / "shared-contracts" / "schemas"
)


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / name).read_text())


def _incident(**overrides) -> Incident:
    fields = {
        "incident_id": "inc-abc123def456",
        "fingerprint": "{}:alertname=KubePodNotReady",
        "source": IncidentSource.ALERTMANAGER,
        "severity": "warning",
        "status": IncidentStatus.NEW,
        "title": "Pod stuck not ready",
        "summary": "Pod default/web-1 has been not ready for 15 minutes.",
        "labels": {"alertname": "KubePodNotReady", "severity": "warning"},
        "created_at": datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc),
    }
    fields.update(overrides)
    return Incident(**fields)


def _report(**overrides) -> TriageReport:
    fields = {
        "incident_id": "inc-abc123def456",
        "summary": "Node pressure is evicting pods in the web namespace.",
        "severity_assessment": "critical",
        "evidence": [
            {
                "source": "k8s.list_events",
                "description": "Eviction events on node worker-2.",
            }
        ],
        "hypotheses": ["Node memory pressure", "Bad liveness probe"],
        "next_steps": [
            {
                "title": "Inspect node worker-2 memory usage",
                "rationale": "Eviction events point at node pressure.",
                "priority": "high",
            }
        ],
        "skills_cited": ["sre-alerting/kubepodnotready"],
        "session_id": "incident-inc-abc123def456",
        "generated_at": datetime(2026, 8, 17, 12, 5, 0, tzinfo=timezone.utc),
        "generated_by": "alice",
    }
    fields.update(overrides)
    return TriageReport(**fields)


class IncidentContractTests(unittest.TestCase):
    schema_name = "incident.schema.json"

    def _schema(self) -> dict:
        return _load_schema(self.schema_name)

    def test_model_properties_match_contract_properties(self) -> None:
        model_properties = set(Incident.model_json_schema()["properties"])
        contract_properties = set(self._schema()["properties"])
        self.assertEqual(model_properties, contract_properties)

    def test_contract_required_fields_are_required_or_defaulted(self) -> None:
        contract = self._schema()
        for field_name in contract.get("required", []):
            field = Incident.model_fields[field_name]
            self.assertTrue(
                field.is_required() or field.get_default() is not None,
                f"Incident.{field_name} may serialize as absent but the "
                f"contract requires it",
            )

    def test_model_forbids_extras_like_contract(self) -> None:
        contract = self._schema()
        if contract.get("additionalProperties") is False:
            self.assertEqual(Incident.model_config.get("extra"), "forbid")

    def test_full_incident_validates_against_contract(self) -> None:
        jsonschema.validate(_incident().envelope(), self._schema())

    def test_incident_with_triage_fields_validates(self) -> None:
        incident = _incident(
            status=IncidentStatus.TRIAGE_FAILED,
            reported_by="alice",
            session_id="incident-inc-abc123def456",
            triage_raw="the agent said something unparseable",
            resolved_at=None,
        )
        jsonschema.validate(incident.envelope(), self._schema())

    def test_contract_rejects_invalid_incident_id(self) -> None:
        with self.assertRaises(ValidationError):
            _incident(incident_id="INC-UPPER")

    def test_contract_rejects_unknown_status(self) -> None:
        payload = _incident().envelope()
        payload["status"] = "closed"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(payload, self._schema())

    def test_list_entry_excludes_summary(self) -> None:
        entry = _incident().list_entry()
        self.assertNotIn("summary", entry)
        self.assertEqual(entry["incident_id"], "inc-abc123def456")


class TriageReportContractTests(unittest.TestCase):
    schema_name = "triage-report.schema.json"

    def _schema(self) -> dict:
        return _load_schema(self.schema_name)

    def test_model_properties_match_contract_properties(self) -> None:
        model_properties = set(TriageReport.model_json_schema()["properties"])
        contract_properties = set(self._schema()["properties"])
        self.assertEqual(model_properties, contract_properties)

    def test_contract_required_fields_are_required_or_defaulted(self) -> None:
        contract = self._schema()
        for field_name in contract.get("required", []):
            field = TriageReport.model_fields[field_name]
            self.assertTrue(
                field.is_required() or field.get_default() is not None,
                f"TriageReport.{field_name} may serialize as absent but the "
                f"contract requires it",
            )

    def test_model_forbids_extras_like_contract(self) -> None:
        contract = self._schema()
        if contract.get("additionalProperties") is False:
            self.assertEqual(TriageReport.model_config.get("extra"), "forbid")

    def test_full_report_validates_against_contract(self) -> None:
        jsonschema.validate(_report().envelope(), self._schema())

    def test_model_rejects_unknown_priority(self) -> None:
        with self.assertRaises(ValidationError):
            _report(
                next_steps=[
                    {"title": "t", "rationale": "r", "priority": "urgent"}
                ]
            )

    def test_model_rejects_foreign_incident_id(self) -> None:
        with self.assertRaises(ValidationError):
            _report(incident_id="not-an-incident-id")

    def test_contract_rejects_oversize_hypothesis(self) -> None:
        payload = _report().envelope()
        payload["hypotheses"] = ["x" * 401]
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(payload, self._schema())

    def test_model_rejects_hypothesis_and_skill_items_like_contract(self) -> None:
        # Item bounds are enforced at the model level too, so a
        # kernel-validated structured report can never be persisted in a
        # shape the canonical contract would reject.
        with self.assertRaises(ValidationError):
            _report(hypotheses=["x" * 401])
        with self.assertRaises(ValidationError):
            _report(hypotheses=[""])
        with self.assertRaises(ValidationError):
            _report(skills_cited=["x" * 257])
        with self.assertRaises(ValidationError):
            _report(skills_cited=[""])


if __name__ == "__main__":
    unittest.main()
