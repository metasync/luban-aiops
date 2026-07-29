"""Validate v2 adapter responses against the platform-owned JSON Schema contracts."""

import json
from pathlib import Path

import jsonschema
from fastapi.testclient import TestClient

from agent_service.app import create_app

SCHEMAS_DIR = (
    Path(__file__).resolve().parents[3] / "shared" / "shared-contracts" / "schemas"
)


def load_schema(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / name).read_text())


def _client() -> TestClient:
    return TestClient(create_app())


def test_runtime_metadata_conforms_to_contract() -> None:
    response = _client().get("/api/v2/runtime")
    assert response.status_code == 200
    jsonschema.validate(response.json(), load_schema("agent-runtime-metadata.schema.json"))


def test_health_conforms_to_contract() -> None:
    response = _client().get("/api/v2/health")
    assert response.status_code == 200
    jsonschema.validate(response.json(), load_schema("agent-health.schema.json"))


def test_session_creation_conforms_to_contract() -> None:
    response = _client().post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    assert response.status_code == 201
    jsonschema.validate(response.json(), load_schema("agent-session.schema.json"))


def test_session_read_conforms_to_contract() -> None:
    client = _client()
    created = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = created.json()["session_id"]

    response = client.get(
        f"/api/v2/sessions/{session_id}", headers={"X-User-ID": "alice"}
    )
    assert response.status_code == 200
    jsonschema.validate(response.json(), load_schema("agent-session.schema.json"))


def test_chat_response_conforms_to_contract() -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]

    response = client.post(
        "/api/v2/chat",
        json={"message": "hello", "session_id": session_id},
        headers={"X-User-ID": "alice", "x-request-id": "req-contract"},
    )
    assert response.status_code == 200
    jsonschema.validate(response.json(), load_schema("agent-chat-response.schema.json"))


def test_chat_response_does_not_leak_framework_types() -> None:
    """The response must not contain AgentScope-specific field names."""
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]

    response = client.post(
        "/api/v2/chat",
        json={"message": "hello", "session_id": session_id},
        headers={"X-User-ID": "alice"},
    )
    payload = response.json()
    # v1 leaked 'response'; v2 uses 'content'
    assert "response" not in payload
    assert "content" in payload
    # No AgentScope internals
    assert "payload" not in payload
    assert "msg" not in payload
