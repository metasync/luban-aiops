import json
import unittest
from pathlib import Path

import jsonschema
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api_gateway.app import create_app
from api_gateway.core.config import GatewaySettings, get_settings
from api_gateway.schemas.api import (
    ChatRequest,
    ChatResponse,
    IdentityContext,
    SessionRecord,
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


class RouteValidationTests(unittest.TestCase):
    """Malformed bodies must fail with 422 before any backend call happens."""

    def setUp(self) -> None:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: GatewaySettings(
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
