"""Contract alignment: Skill conforms to skill.schema.json (SPEC-014 R-1).

skills-hub builds and serves envelopes verbatim, so its pydantic model must
bind tightly to the shared contract — same pattern as the SPEC-013
audit-event contract tests.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
from pydantic import ValidationError

from skills_hub.schemas.skill import Skill

SCHEMAS_DIR = (
    Path(__file__).resolve().parents[3] / "shared" / "shared-contracts" / "schemas"
)

SCHEMA_NAME = "skill.schema.json"


def _load_schema() -> dict:
    return json.loads((SCHEMAS_DIR / SCHEMA_NAME).read_text())


def _skill(**overrides) -> Skill:
    fields = {
        "skill_id": "sre-alerting/alerts/kubepodnotready",
        "source_id": "sre-alerting",
        "source_path": "alerts/KubePodNotReady.md",
        "source_ref": "abc123",
        "title": "KubePodNotReady",
        "description": "Pod stuck not ready — triage steps.",
        "tags": ["kubernetes", "KubePodNotReady"],
        "version": "1.0",
        "source_url": "https://github.com/prometheus-operator/runbooks",
        "updated_at": datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc),
        "body": "Check the pod events first.",
    }
    fields.update(overrides)
    return Skill(**fields)


class SkillContractTests(unittest.TestCase):
    def test_model_properties_match_contract_properties(self) -> None:
        contract = _load_schema()
        model_properties = set(Skill.model_json_schema()["properties"])
        contract_properties = set(contract["properties"])
        self.assertEqual(model_properties, contract_properties)

    def test_contract_required_fields_are_required_or_defaulted(self) -> None:
        contract = _load_schema()
        for field_name in contract.get("required", []):
            field = Skill.model_fields[field_name]
            self.assertTrue(
                field.is_required() or field.get_default() is not None,
                f"Skill.{field_name} may serialize as absent but the "
                f"contract requires it",
            )

    def test_model_forbids_extras_like_contract(self) -> None:
        contract = _load_schema()
        if contract.get("additionalProperties") is False:
            self.assertEqual(Skill.model_config.get("extra"), "forbid")

    def test_full_skill_validates_against_contract(self) -> None:
        jsonschema.validate(
            _skill().model_dump(mode="json", exclude_none=True), _load_schema()
        )

    def test_minimal_skill_validates_against_contract(self) -> None:
        # Optional frontmatter fields omitted entirely (not nulled).
        skill = _skill(tags=None, version=None, source_url=None)
        dumped = skill.model_dump(mode="json", exclude_none=True)
        self.assertNotIn("tags", dumped)
        self.assertNotIn("source_url", dumped)
        jsonschema.validate(dumped, _load_schema())

    def test_executable_flow_skill_validates_against_contract(self) -> None:
        # SPEC-055 R-3: an executable_flow skill carries a kind discriminator
        # and an ordered steps replay list, and may declare risk_class=write
        # without a web_target (decoupled). Credential args are references,
        # never literals.
        skill = _skill(
            kind="executable_flow",
            risk_class="write",
            steps=[
                {"tool": "web.navigate", "args": {"url": "https://app.example"}},
                {
                    "tool": "web.fill_credential",
                    "args": {"credential_set": "admin", "field": "password"},
                    "expect": "password field populated",
                },
            ],
        )
        dumped = skill.model_dump(mode="json", exclude_none=True)
        self.assertEqual(dumped["kind"], "executable_flow")
        self.assertNotIn("web_target", dumped)
        jsonschema.validate(dumped, _load_schema())

    def test_composition_skill_validates_against_contract(self) -> None:
        # SPEC-057 R-1: a composition carries kind=composition and an ordered
        # sub_skills reference list, declares no web_target and no steps, and
        # reuses the top-level risk_class for its derived display value.
        skill = _skill(
            kind="composition",
            risk_class="write",
            sub_skills=[
                {
                    "skill_id": "samples/password-reset-resetacmepassword",
                    "note": "Reset the password first.",
                },
                {"skill_id": "samples/lock-unlock-user-lockunlockuser"},
            ],
        )
        dumped = skill.model_dump(mode="json", exclude_none=True)
        self.assertEqual(dumped["kind"], "composition")
        self.assertNotIn("web_target", dumped)
        self.assertNotIn("steps", dumped)
        self.assertEqual(len(dumped["sub_skills"]), 2)
        # exclude_none drops the omitted note so the item is skill_id-only.
        self.assertEqual(
            dumped["sub_skills"][1],
            {"skill_id": "samples/lock-unlock-user-lockunlockuser"},
        )
        jsonschema.validate(dumped, _load_schema())

    def test_contract_kind_enum_parity_includes_composition(self) -> None:
        # The kind enum is the contract's class vocabulary; the model's kind
        # pattern must accept exactly the same set (SPEC-057 R-1 adds
        # composition). Assert parity behaviorally: every contract enum value
        # builds a Skill, and a value outside the enum is rejected.
        contract = _load_schema()
        enum_values = contract["properties"]["kind"]["enum"]
        self.assertEqual(
            set(enum_values), {"knowledge", "executable_flow", "composition"}
        )
        for kind in enum_values:
            _skill(kind=kind)  # must not raise
        with self.assertRaises(ValidationError):
            _skill(kind="composite")

    def test_property_parity_guard_is_sensitive(self) -> None:
        # Prove test_model_properties_match_contract_properties is not
        # vacuous: dropping sub_skills from either mirror breaks the equality
        # it asserts, so a mirror that forgets the field fails the suite.
        contract = _load_schema()
        model_properties = set(Skill.model_json_schema()["properties"])
        contract_properties = set(contract["properties"])
        self.assertEqual(model_properties, contract_properties)
        self.assertIn("sub_skills", model_properties)
        self.assertNotEqual(
            model_properties - {"sub_skills"}, contract_properties
        )
        self.assertNotEqual(
            model_properties, contract_properties - {"sub_skills"}
        )

    def test_contract_rejects_sub_skill_item_extra_key(self) -> None:
        # SPEC-057 R-3: the item is additionalProperties:false, so a
        # sequencing key (if/loop/retry/on_fail) cannot be smuggled in. Built
        # as a plain dict so only the JSON schema is exercised.
        payload = _skill().model_dump(mode="json", exclude_none=True)
        payload["kind"] = "composition"
        payload["sub_skills"] = [
            {
                "skill_id": "samples/password-reset-resetacmepassword",
                "on_fail": "rollback",
            }
        ]
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(payload, _load_schema())

    def test_model_rejects_sub_skill_item_extra_key(self) -> None:
        # The pydantic mirror enforces the same invariant (extra="forbid").
        with self.assertRaises(ValidationError):
            _skill(
                kind="composition",
                sub_skills=[
                    {
                        "skill_id": "samples/password-reset-resetacmepassword",
                        "loop": 3,
                    }
                ],
            )

    def test_contract_rejects_invalid_skill_id(self) -> None:
        payload = _skill(skill_id="Not_Valid/ID").model_dump(
            mode="json", exclude_none=True
        )
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(payload, _load_schema())

    def test_contract_rejects_oversize_body(self) -> None:
        # Build the payload as a plain dict so only the JSON schema (not the
        # pydantic model) is exercised.
        payload = _skill().model_dump(mode="json", exclude_none=True)
        payload["body"] = "x" * 65537
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(payload, _load_schema())

    def test_model_rejects_extra_field_like_contract(self) -> None:
        with self.assertRaises(ValidationError):
            _skill(unexpected="field")

    def test_summary_excludes_body(self) -> None:
        summary = _skill().summary()
        self.assertNotIn("body", summary)
        self.assertEqual(summary["skill_id"], "sre-alerting/alerts/kubepodnotready")


if __name__ == "__main__":
    unittest.main()
