import json
import unittest
from pathlib import Path

import jsonschema
from fastapi.testclient import TestClient
from pydantic import ValidationError

from platform_gateway.app import create_app
from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.schemas.api import (
    ChatRequest,
    ChatResponse,
    CreateSessionRequest,
    IdentityContext,
    PolicyMatrixResponse,
    SessionRecord,
    SessionType,
)

SCHEMAS_DIR = (
    Path(__file__).resolve().parents[3] / "shared" / "shared-contracts" / "schemas"
)


def load_schema(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / name).read_text())


class ContractAlignmentTests(unittest.TestCase):
    """Bind gateway pydantic models to the shared-contracts JSON schemas."""

    model_schema_pairs = [
        (ChatRequest, "chat-request.schema.json"),
        (ChatResponse, "agent-chat-response.schema.json"),
        (SessionRecord, "agent-session.schema.json"),
        (IdentityContext, "identity-context.schema.json"),
        (PolicyMatrixResponse, "policy-matrix.schema.json"),
    ]

    def test_model_properties_match_contract_properties(self) -> None:
        for model, schema_name in self.model_schema_pairs:
            with self.subTest(model=model.__name__):
                contract = load_schema(schema_name)
                model_properties = set(model.model_json_schema()["properties"])
                contract_properties = set(contract["properties"])
                self.assertEqual(model_properties, contract_properties)

    def test_contract_required_fields_are_required_or_defaulted(self) -> None:
        for model, schema_name in self.model_schema_pairs:
            with self.subTest(model=model.__name__):
                contract = load_schema(schema_name)
                for field_name in contract.get("required", []):
                    field = model.model_fields[field_name]
                    self.assertTrue(
                        field.is_required() or field.get_default() is not None,
                        f"{model.__name__}.{field_name} may serialize as absent "
                        f"but the contract requires it",
                    )

    def test_models_forbid_extras_when_contract_does(self) -> None:
        for model, schema_name in self.model_schema_pairs:
            with self.subTest(model=model.__name__):
                contract = load_schema(schema_name)
                if contract.get("additionalProperties") is False:
                    self.assertEqual(model.model_config.get("extra"), "forbid")

    def test_model_instances_validate_against_contracts(self) -> None:
        samples = [
            (
                ChatRequest(message="restart the payment pods", session_id="ses-1"),
                "chat-request.schema.json",
            ),
            (
                ChatResponse(session_id="ses-1", request_id="req-1", content="done"),
                "agent-chat-response.schema.json",
            ),
            (
                SessionRecord(
                    session_id="ses-1",
                    user_id="alice",
                    created_at="2026-07-28T00:00:00Z",
                    evidence_turns=[
                        {
                            "turn_index": 0,
                            "request_id": "req-1",
                            "created_at": "2026-07-28T00:00:01Z",
                            "frames": [
                                {
                                    "type": "tool_result",
                                    "tool_name": "k8s.list_pods",
                                    "call_id": "call-1",
                                    "status": "success",
                                    "truncated": {
                                        "reason": "session_budget"
                                    },
                                }
                            ],
                        }
                    ],
                ),
                "agent-session.schema.json",
            ),
            (
                IdentityContext(
                    subject="user-123",
                    username="alice",
                    roles=["operator"],
                    groups=["ops-operators"],
                ),
                "identity-context.schema.json",
            ),
            (
                PolicyMatrixResponse(
                    version=1,
                    source="packaged-default",
                    sha256="0" * 64,
                    scope="own",
                    roles=["operator"],
                    actions=["chat", "policy:read"],
                    matrix={"operator": {"chat": True, "policy:read": True}},
                ),
                "policy-matrix.schema.json",
            ),
        ]
        for instance, schema_name in samples:
            with self.subTest(model=type(instance).__name__):
                jsonschema.validate(
                    instance.model_dump(mode="json", exclude_none=True),
                    load_schema(schema_name),
                )

    def test_models_reject_what_contracts_reject(self) -> None:
        rejected = [
            (ChatRequest, {"session_id": "ses-1"}, "chat-request.schema.json"),
            (ChatRequest, {"message": ""}, "chat-request.schema.json"),
            (
                ChatRequest,
                {"message": "hi", "unexpected": "field"},
                "chat-request.schema.json",
            ),
            (
                ChatResponse,
                {"session_id": "ses-1", "request_id": "req-1"},
                "agent-chat-response.schema.json",
            ),
            (
                IdentityContext,
                {"subject": "user-123", "roles": []},
                "identity-context.schema.json",
            ),
        ]
        for model, payload, schema_name in rejected:
            with self.subTest(model=model.__name__, payload=payload):
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.validate(payload, load_schema(schema_name))
                with self.assertRaises(ValidationError):
                    model.model_validate(payload)


class SessionTypeContractTests(unittest.TestCase):
    """SPEC-056 R-1: the additive ``session_type`` discriminator, in lockstep.

    Property-set equality above forces the field *name* onto every bound
    mirror; it cannot see an enum *value* drifting, which is the gap the
    audit ``event_type`` and model-catalog ``provider`` incidents fell into —
    the parity test passed while the new value was rejected at runtime. These
    assertions close it for the session vocabulary.
    """

    schema_names = [
        "agent-session.schema.json",
        "agent-session-list.schema.json",
    ]

    def _contract_values(self, schema_name: str) -> set[str]:
        contract = load_schema(schema_name)
        properties = (
            contract["properties"]
            if schema_name == "agent-session.schema.json"
            else contract["properties"]["sessions"]["items"]["properties"]
        )
        return set(properties["session_type"]["enum"])

    def test_session_type_enum_values_match_every_model(self) -> None:
        model_values = set(getattr(SessionType, "__args__", SessionType))
        for schema_name in self.schema_names:
            with self.subTest(schema=schema_name):
                self.assertEqual(self._contract_values(schema_name), model_values)
        # Both consuming mirrors read the one alias, so a third value added to
        # a schema without the models cannot slip past on one side only.
        for model in (SessionRecord, CreateSessionRequest):
            with self.subTest(model=model.__name__):
                annotation = model.model_fields["session_type"].annotation
                self.assertEqual(
                    set(getattr(annotation, "__args__", annotation)), model_values
                )

    def test_session_type_defaults_to_operation_on_every_surface(self) -> None:
        for schema_name in self.schema_names:
            with self.subTest(schema=schema_name):
                contract = load_schema(schema_name)
                properties = (
                    contract["properties"]
                    if schema_name == "agent-session.schema.json"
                    else contract["properties"]["sessions"]["items"]["properties"]
                )
                self.assertEqual(
                    properties["session_type"]["default"], "operation"
                )
                # Additive: never in ``required``, so a pre-SPEC-056 record
                # still validates and an un-updated client behaves as today.
                required = (
                    contract.get("required", [])
                    if schema_name == "agent-session.schema.json"
                    else contract["properties"]["sessions"]["items"].get(
                        "required", []
                    )
                )
                self.assertNotIn("session_type", required)
        self.assertEqual(
            SessionRecord.model_fields["session_type"].default, "operation"
        )
        self.assertEqual(
            CreateSessionRequest.model_fields["session_type"].default, "operation"
        )

    def test_session_record_with_session_type_validates_against_contract(self) -> None:
        for session_type in ("operation", "development"):
            with self.subTest(session_type=session_type):
                record = SessionRecord(
                    session_id="ses-1",
                    user_id="alice",
                    created_at="2026-09-12T00:00:00Z",
                    session_type=session_type,
                )
                jsonschema.validate(
                    record.model_dump(mode="json", exclude_none=True),
                    load_schema("agent-session.schema.json"),
                )
                self.assertEqual(
                    record.model_dump(mode="json")["session_type"], session_type
                )

    def test_record_omitting_session_type_still_validates(self) -> None:
        # Additive and defaulted: both schemas accept a record that predates
        # the field, and the model supplies ``operation``.
        legacy_detail = {
            "session_id": "ses-legacy",
            "user_id": "alice",
            "created_at": "2026-09-12T00:00:00Z",
            "status": "active",
        }
        legacy_row = {
            "session_id": "ses-legacy",
            "created_at": "2026-09-12T00:00:00Z",
            "pending_confirmation": False,
        }
        jsonschema.validate(legacy_detail, load_schema("agent-session.schema.json"))
        jsonschema.validate(
            {"sessions": [legacy_row]}, load_schema("agent-session-list.schema.json")
        )
        self.assertEqual(
            SessionRecord.model_validate(legacy_detail).session_type, "operation"
        )

    def test_enum_parity_guard_fires_on_vocabulary_drift(self) -> None:
        """Prove the parity assertion is sensitive, not vacuously true.

        A schema that grew a value the models do not carry is the incident
        this guard exists for: property-name parity still passes, and the new
        value is then rejected at the model boundary.
        """
        contract_values = self._contract_values("agent-session.schema.json")
        model_values = set(getattr(SessionType, "__args__", SessionType))
        self.assertEqual(contract_values, model_values)

        widened = contract_values | {"archived"}
        narrowed = contract_values - {"development"}
        self.assertNotEqual(widened, model_values)
        self.assertNotEqual(narrowed, model_values)

        # The runtime consequence, on both mirrors: a value the drifted schema
        # would accept is refused by the gateway body contract and by the
        # relayed record.
        with self.assertRaises(ValidationError):
            CreateSessionRequest.model_validate({"session_type": "archived"})
        with self.assertRaises(ValidationError):
            SessionRecord.model_validate(
                {
                    "session_id": "ses-1",
                    "user_id": "alice",
                    "created_at": "2026-09-12T00:00:00Z",
                    "session_type": "archived",
                }
            )
        # ... and the contract side rejects it too, so the drift is caught
        # whichever boundary a value arrives at.
        drifted_property = {
            "type": "object",
            "properties": {"session_type": {"enum": sorted(contract_values)}},
        }
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate({"session_type": "archived"}, drifted_property)


class RouteValidationTests(unittest.TestCase):
    """Malformed bodies must fail with 422 before any backend call happens."""

    def setUp(self) -> None:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: PlatformGatewaySettings(
            require_auth=False
        )
        self.client = TestClient(app)

    def test_chat_missing_message_returns_422(self) -> None:
        response = self.client.post("/api/v1/chat", json={})
        self.assertEqual(response.status_code, 422)

    def test_chat_empty_message_returns_422(self) -> None:
        response = self.client.post("/api/v1/chat", json={"message": ""})
        self.assertEqual(response.status_code, 422)

    def test_chat_unknown_field_returns_422(self) -> None:
        response = self.client.post(
            "/api/v1/chat",
            json={"message": "hi", "unexpected": "field"},
        )
        self.assertEqual(response.status_code, 422)

    def test_chat_non_json_body_returns_422(self) -> None:
        response = self.client.post(
            "/api/v1/chat",
            content=b"not-json",
            headers={"content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 422)

    def test_create_session_unknown_field_returns_422(self) -> None:
        response = self.client.post(
            "/api/v1/sessions",
            json={"unexpected": "field"},
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
