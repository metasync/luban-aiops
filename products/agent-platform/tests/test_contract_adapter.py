"""Validate v2 adapter responses against the platform-owned JSON Schema contracts."""

import json
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from agent_service.api.v2.routes import _normalize_stream_event
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


# --- Stream event adapter (SPEC-011 R-1 evidence frames) ---


def test_tool_call_frame_passes_through() -> None:
    raw = {
        "type": "tool_call",
        "tool_name": "k8s.list_pods",
        "call_id": "call-1",
        "parameters": {"namespace": "argocd"},
    }
    event = _normalize_stream_event(raw, "ses-1", "req-1")
    dumped = json.loads(event.model_dump_json(exclude_none=True))
    assert dumped["type"] == "tool_call"
    assert dumped["tool_name"] == "k8s.list_pods"
    assert dumped["call_id"] == "call-1"
    assert dumped["parameters"] == {"namespace": "argocd"}
    jsonschema.validate(dumped, load_schema("agent-stream-event.schema.json"))


def test_tool_result_frame_passes_through() -> None:
    raw = {
        "type": "tool_result",
        "tool_name": "k8s.list_pods",
        "call_id": "call-1",
        "status": "success",
        "evidence": {
            "executed_at": "2026-08-05T10:00:00Z",
            "duration_ms": 12,
            "risk_level": "read",
            "source_system": "kubernetes",
        },
        "data_summary": {"count": 3},
    }
    event = _normalize_stream_event(raw, "ses-1", "req-1")
    dumped = json.loads(event.model_dump_json(exclude_none=True))
    assert dumped["type"] == "tool_result"
    assert dumped["status"] == "success"
    assert dumped["evidence"]["risk_level"] == "read"
    jsonschema.validate(dumped, load_schema("agent-stream-event.schema.json"))


def test_denied_tool_result_keeps_denied_status() -> None:
    raw = {
        "type": "tool_result",
        "tool_name": "k8s.list_pods",
        "call_id": "call-2",
        "status": "denied",
        "error": {"code": "policy_denied", "message": "action not granted"},
    }
    event = _normalize_stream_event(raw, "ses-1", "req-1")
    dumped = json.loads(event.model_dump_json(exclude_none=True))
    assert dumped["status"] == "denied"
    assert dumped["error"]["code"] == "policy_denied"
    jsonschema.validate(dumped, load_schema("agent-stream-event.schema.json"))


def test_non_object_data_summary_is_wrapped() -> None:
    raw = {
        "type": "tool_result",
        "tool_name": "k8s.get_pod_logs",
        "call_id": "call-3",
        "status": "success",
        "data_summary": ["line-a", "line-b"],
    }
    event = _normalize_stream_event(raw, "ses-1", "req-1")
    assert event.data_summary == {"value": ["line-a", "line-b"]}


def test_unknown_event_type_still_degrades_to_message_delta() -> None:
    event = _normalize_stream_event({"type": "thinking_block"}, "ses-1", "req-1")
    assert event.type == "message_delta"


# --- Confirmation frames (SPEC-020 R-1, stream schema v5) ---


def test_confirmation_request_frame_conforms_to_contract() -> None:
    raw = {
        "type": "confirmation_request",
        "confirm_id": "cf-1",
        "pending_calls": [
            {
                "call_id": "call-1",
                "tool_name": "k8s.restart_service",
                "parameters": {"namespace": "ops"},
            }
        ],
        "message": "Tool execution requires your confirmation.",
    }
    event = _normalize_stream_event(raw, "ses-1", "req-1")
    dumped = json.loads(event.model_dump_json(exclude_none=True))
    assert dumped["type"] == "confirmation_request"
    assert dumped["confirm_id"] == "cf-1"
    assert dumped["pending_calls"][0]["tool_name"] == "k8s.restart_service"
    jsonschema.validate(dumped, load_schema("agent-stream-event.schema.json"))


def test_confirmation_result_frame_conforms_to_contract() -> None:
    for status in ("approved", "denied", "expired", "interrupted"):
        raw = {
            "type": "confirmation_result",
            "confirm_id": "cf-1",
            "status": status,
        }
        event = _normalize_stream_event(raw, "ses-1", "req-1")
        dumped = json.loads(event.model_dump_json(exclude_none=True))
        assert dumped["status"] == status
        jsonschema.validate(
            dumped, load_schema("agent-stream-event.schema.json")
        )


def test_pending_calls_coercion_drops_malformed_entries() -> None:
    raw = {
        "type": "confirmation_request",
        "confirm_id": "cf-2",
        "pending_calls": [
            "not-a-dict",
            {"call_id": 7, "tool_name": "k8s.restart_service"},
            {
                "call_id": "call-1",
                "tool_name": "k8s.restart_service",
                "parameters": "not-a-dict",
            },
        ],
    }
    event = _normalize_stream_event(raw, "ses-1", "req-1")
    dumped = json.loads(event.model_dump_json(exclude_none=True))
    jsonschema.validate(dumped, load_schema("agent-stream-event.schema.json"))


def test_chat_confirm_request_conforms_to_contract() -> None:
    schema = load_schema("chat-confirm.schema.json")
    jsonschema.validate(
        {"session_id": "ses-1", "confirm_id": "cf-1", "decision": "approve"},
        schema,
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {"session_id": "ses-1", "confirm_id": "cf-1", "decision": "maybe"},
            schema,
        )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {"session_id": "ses-1", "decision": "approve", "user_id": "alice"},
            schema,
        )
