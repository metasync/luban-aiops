"""Validate v2 adapter responses against the platform-owned JSON Schema contracts."""

import json
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent_service.api.v2.routes import _FLOW_SUMMARY_FIELDS, _normalize_stream_event
from agent_service.app import create_app
from agent_service.schemas.api import SessionRecord
from agent_service.schemas.v2 import (
    AgentSession,
    AgentSessionCreateRequest,
    AgentSessionList,
    AgentSessionSummary,
    SessionType,
)

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


# --- SPEC-056 R-1: the additive ``session_type`` discriminator ---
#
# ``additionalProperties:false`` on both live session schemas forces the field
# *name* onto every emitting model the moment a response carries it. What no
# property-name guard can see is enum *vocabulary* drift — the audit-service
# ``event_type`` and model-catalog ``provider`` incidents, where parity passed
# while a new value was rejected at runtime. The assertions below close that
# gap for the session vocabulary.

_SESSION_TYPE_CONSUMERS = (
    AgentSession,
    AgentSessionSummary,
    AgentSessionCreateRequest,
    SessionRecord,
)


def _session_type_enum(schema_name: str) -> set[str]:
    contract = load_schema(schema_name)
    properties = (
        contract["properties"]
        if schema_name == "agent-session.schema.json"
        else contract["properties"]["sessions"]["items"]["properties"]
    )
    return set(properties["session_type"]["enum"])


def test_session_type_enum_values_match_contract() -> None:
    model_values = set(getattr(SessionType, "__args__", SessionType))
    assert model_values == {"operation", "development"}
    for schema_name in (
        "agent-session.schema.json",
        "agent-session-list.schema.json",
    ):
        assert _session_type_enum(schema_name) == model_values, schema_name
    for model in _SESSION_TYPE_CONSUMERS:
        annotation = model.model_fields["session_type"].annotation
        assert set(getattr(annotation, "__args__", annotation)) == model_values, (
            model.__name__
        )
        # Additive everywhere: the default carries a create body that omits the
        # field, so an un-updated client behaves exactly as before SPEC-056.
        assert model.model_fields["session_type"].default == "operation"


def test_session_type_enum_parity_guard_fires_on_drift() -> None:
    """Prove the parity assertion is sensitive rather than vacuously true."""
    contract_values = _session_type_enum("agent-session.schema.json")
    model_values = set(getattr(SessionType, "__args__", SessionType))
    assert contract_values == model_values

    # A schema that grew a value the models do not carry, and a model that
    # dropped one the schema still accepts, are both drift the property-name
    # guard is blind to.
    assert contract_values | {"archived"} != model_values
    assert contract_values - {"development"} != model_values

    # The runtime consequence the guard exists to prevent: the widened value is
    # refused at every consuming model boundary.
    for model in _SESSION_TYPE_CONSUMERS:
        with pytest.raises(ValidationError):
            model.model_validate(_session_type_payload(model, "archived"))


def _session_type_payload(model, session_type: str) -> dict:
    """A minimal valid payload for ``model`` carrying ``session_type``."""
    if model is AgentSessionCreateRequest:
        return {"session_type": session_type}
    if model is AgentSessionSummary:
        return {
            "session_id": "ses-1",
            "created_at": "2026-09-12T00:00:00Z",
            "session_type": session_type,
        }
    return {
        "session_id": "ses-1",
        "user_id": "alice",
        "created_at": "2026-09-12T00:00:00Z",
        "session_type": session_type,
    }


def test_session_record_with_session_type_conforms_to_both_contracts() -> None:
    for session_type in ("operation", "development"):
        detail = AgentSession(
            session_id="ses-1",
            user_id="alice",
            created_at="2026-09-12T00:00:00Z",
            session_type=session_type,
        )
        jsonschema.validate(
            detail.model_dump(mode="json", exclude_none=True),
            load_schema("agent-session.schema.json"),
        )
        listing = AgentSessionList(
            sessions=[
                AgentSessionSummary(
                    session_id="ses-1",
                    created_at="2026-09-12T00:00:00Z",
                    session_type=session_type,
                )
            ]
        )
        jsonschema.validate(
            listing.model_dump(mode="json", exclude_none=True),
            load_schema("agent-session-list.schema.json"),
        )
        assert detail.model_dump(mode="json")["session_type"] == session_type


def test_session_record_omitting_session_type_still_conforms() -> None:
    # Additive and defaulted: both schemas accept a record that predates the
    # field, and every model supplies ``operation``.
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
    assert SessionRecord.model_validate(legacy_detail).session_type == "operation"
    assert (
        AgentSession.model_validate(legacy_detail).session_type == "operation"
    )
    assert (
        AgentSessionSummary.model_validate(legacy_row).session_type == "operation"
    )


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


def test_pending_calls_pass_through_schema_conformant_risk_level() -> None:
    """v6 (SPEC-021 R-3): the portal flags mutating batches from the
    per-call risk_level, so the route must not strip schema-conformant
    values; non-enum values are omitted, keeping frames valid."""
    raw = {
        "type": "confirmation_request",
        "confirm_id": "cf-3",
        "pending_calls": [
            {
                "call_id": "call-1",
                "tool_name": "k8s.restart_service",
                "risk_level": "write",
            },
            {
                "call_id": "call-2",
                "tool_name": "k8s.get_pod_logs",
                "risk_level": "read",
            },
            {"call_id": "call-3", "tool_name": "task.note", "risk_level": 7},
            {"call_id": "call-4", "tool_name": "task.note"},
        ],
    }
    event = _normalize_stream_event(raw, "ses-1", "req-1")
    dumped = json.loads(event.model_dump_json(exclude_none=True))
    jsonschema.validate(dumped, load_schema("agent-stream-event.schema.json"))
    calls = dumped["pending_calls"]
    assert calls[0]["risk_level"] == "write"
    assert calls[1]["risk_level"] == "read"
    assert "risk_level" not in calls[2]
    assert "risk_level" not in calls[3]


def test_confirmation_request_frame_preserves_flow_summary() -> None:
    """v10 (SPEC-051 R-6 / SPEC-053 R-2): the live operator card reads its
    browser-flow headline off the confirmation_request frame, so the route must
    carry every contract field through — especially ``description``, whose loss
    left the live card blank while the durable record (approver inbox) still
    showed it, and the SPEC-053 ``flow_intent`` lead decision line. The frame
    must stay schema-conformant."""
    raw = {
        "type": "confirmation_request",
        "confirm_id": "cf-flow",
        "pending_calls": [
            {
                "call_id": "call-1",
                "tool_name": "browser.click",
                "parameters": {"ref": "e12"},
            }
        ],
        "flow_summary": {
            "skill_id": "browser.check.reset",
            "origin": "browser-flow",
            "title": "Reset the check target",
            "description": "Clears the SPEC-051 Design 1 form and re-runs the check.",
            "flow_intent": "Submit the password reset for the user.",
            "risk_class": "write",
        },
        "message": "Tool execution requires your confirmation.",
    }
    event = _normalize_stream_event(raw, "ses-1", "req-1")
    dumped = json.loads(event.model_dump_json(exclude_none=True))
    summary = dumped["flow_summary"]
    assert summary["description"] == (
        "Clears the SPEC-051 Design 1 form and re-runs the check."
    )
    assert summary["skill_id"] == "browser.check.reset"
    assert summary["origin"] == "browser-flow"
    assert summary["title"] == "Reset the check target"
    assert summary["flow_intent"] == "Submit the password reset for the user."
    assert summary["risk_class"] == "write"
    jsonschema.validate(dumped, load_schema("agent-stream-event.schema.json"))


def test_flow_summary_coercion_drops_malformed_and_unknown_fields() -> None:
    """v10 (SPEC-051 R-6 / SPEC-053 R-2): a non-dict summary degrades to absent
    (the card falls back to plain tool-action rendering) and a dict keeps only
    the contract's string fields, so a malformed or over-eager summary can
    never fail the frame's additionalProperties:false validation."""
    for malformed in ("not-a-dict", ["skill_id"], 7):
        raw = {
            "type": "confirmation_request",
            "confirm_id": "cf-bad",
            "pending_calls": [{"call_id": "c1", "tool_name": "browser.click"}],
            "flow_summary": malformed,
        }
        event = _normalize_stream_event(raw, "ses-1", "req-1")
        dumped = json.loads(event.model_dump_json(exclude_none=True))
        assert "flow_summary" not in dumped
        jsonschema.validate(dumped, load_schema("agent-stream-event.schema.json"))

    # Unknown keys and non-string values are stripped; valid fields survive.
    raw = {
        "type": "confirmation_request",
        "confirm_id": "cf-mixed",
        "pending_calls": [{"call_id": "c1", "tool_name": "browser.click"}],
        "flow_summary": {
            "title": "Reset the check target",
            "description": "Clears the form.",
            "flow_intent": "Submit the reset.",
            "skill_id": 99,
            "origin": None,
            "risk_class": "write",
            "surprise": "not in contract",
        },
    }
    event = _normalize_stream_event(raw, "ses-1", "req-1")
    dumped = json.loads(event.model_dump_json(exclude_none=True))
    assert dumped["flow_summary"] == {
        "title": "Reset the check target",
        "description": "Clears the form.",
        "flow_intent": "Submit the reset.",
        "risk_class": "write",
    }
    jsonschema.validate(dumped, load_schema("agent-stream-event.schema.json"))


def test_confirmation_record_with_flow_summary_conforms_to_session_contract() -> None:
    """v10 (SPEC-051 R-6 / SPEC-053 R-2): the durable card model carries
    flow_summary, so the session-detail contract must allow it — a browser-flow
    card served to the approver inbox / owner transcript would otherwise fail the
    confirmation item's additionalProperties:false. Locks the model<->schema
    parity, including the SPEC-053 ``flow_intent`` lead line."""
    from agent_service.schemas.v2 import ConfirmationRecordModel

    card = ConfirmationRecordModel(
        confirm_id="cf-flow",
        session_id="ses-1",
        owner_user_id="alice",
        pending_calls=[{"call_id": "c1", "tool_name": "browser.click"}],
        action="tools:mutate",
        flow_summary={
            "skill_id": "browser.check.reset",
            "origin": "browser-flow",
            "title": "Reset the check target",
            "description": "Clears the SPEC-051 Design 1 form.",
            "flow_intent": "Submit the password reset for the user.",
            "risk_class": "write",
        },
    )
    dumped = json.loads(card.model_dump_json())
    item_schema = load_schema("agent-session.schema.json")["properties"][
        "confirmations"
    ]["items"]
    jsonschema.validate(dumped, item_schema)
    assert dumped["flow_summary"]["description"] == (
        "Clears the SPEC-051 Design 1 form."
    )
    assert dumped["flow_summary"]["flow_intent"] == (
        "Submit the password reset for the user."
    )


def test_flow_summary_field_parity_across_coercion_and_both_schemas() -> None:
    """SPEC-053 R-2: three sources of truth define the flow-summary shape — the
    route's ``_FLOW_SUMMARY_FIELDS`` coercion allow-list, the live
    ``agent-stream-event`` schema, and the durable ``agent-session``
    confirmation-item schema. A name-only parity check elsewhere missed drift, so
    pin all three property sets to the same field names: adding ``flow_intent`` to
    one but not another would silently drop it (coercion) or reject the frame
    (additionalProperties:false)."""
    expected = set(_FLOW_SUMMARY_FIELDS)

    stream_props = set(
        load_schema("agent-stream-event.schema.json")["properties"]["flow_summary"][
            "properties"
        ]
    )
    assert stream_props == expected

    session_item = load_schema("agent-session.schema.json")["properties"][
        "confirmations"
    ]["items"]
    session_props = set(session_item["properties"]["flow_summary"]["properties"])
    assert session_props == expected


def test_confirmation_request_frame_v11_fields_conform() -> None:
    """v11 (SPEC-054 R-1/R-3): a parked browser frame carrying every new field
    — ``approval_kind``, ``flow_summary``, a per-call ``display_hint`` and a
    secret-masked ``change_request`` — must validate against the stream schema's
    ``additionalProperties:false``. (The kernel emits ``flow_summary`` and
    ``change_request`` on mutually-exclusive kinds — that gating is pinned in
    ``test_runtime_kernel.py``; here we lock the contract's capacity to carry
    all four so a v11 frame is never rejected.)"""
    raw = {
        "type": "confirmation_request",
        "confirm_id": "cf-v11",
        "approval_kind": "flow",
        "flow_summary": {
            "skill_id": "samples/password-reset",
            "origin": "http://admin.local",
            "title": "Reset User Password",
            "description": "Reset a user's password in the admin portal",
            "flow_intent": "Submit the password reset for the user.",
            "risk_class": "write",
        },
        "pending_calls": [
            {
                "call_id": "call-1",
                "tool_name": "web.type",
                "parameters": {"ref": 3, "text": "hunter2"},
                "display_hint": "Password input",
                "change_request": {
                    "summary": 'Type into "Password input"',
                    "fields": [
                        {"label": "text", "value": "***", "masked": True}
                    ],
                },
            }
        ],
        "message": 'Type into "Password input"',
    }
    event = _normalize_stream_event(raw, "ses-1", "req-1")
    dumped = json.loads(event.model_dump_json(exclude_none=True))
    assert dumped["approval_kind"] == "flow"
    call = dumped["pending_calls"][0]
    assert call["display_hint"] == "Password input"
    assert call["change_request"]["fields"][0]["masked"] is True
    # The projection is a sibling of parameters, never nested inside it.
    assert "change_request" not in call["parameters"]
    jsonschema.validate(dumped, load_schema("agent-stream-event.schema.json"))


def test_change_request_and_approval_kind_coercion_drops_malformed() -> None:
    """v11 (SPEC-054 R-1/R-3): an out-of-vocabulary ``approval_kind`` degrades
    to absent (today's tool-level card) and a ``change_request`` without a
    summary sentence is dropped, so a malformed projection can never fail the
    frame's ``additionalProperties:false`` validation."""
    raw = {
        "type": "confirmation_request",
        "confirm_id": "cf-bad",
        "approval_kind": "admin",  # not in the {flow, action} vocabulary
        "pending_calls": [
            {
                "call_id": "c1",
                "tool_name": "k8s.delete_pod",
                "change_request": {"fields": []},  # no summary -> dropped
            }
        ],
    }
    event = _normalize_stream_event(raw, "ses-1", "req-1")
    dumped = json.loads(event.model_dump_json(exclude_none=True))
    assert "approval_kind" not in dumped
    assert "change_request" not in dumped["pending_calls"][0]
    jsonschema.validate(dumped, load_schema("agent-stream-event.schema.json"))


def test_confirmation_record_with_approval_kind_and_message_conforms_to_session_contract() -> None:
    """v11 (SPEC-054 R-1/R-4): the durable card model carries ``approval_kind``
    and ``message``, and a pending call carries the ``change_request``
    projection, so the session-detail contract must allow them — an action card
    served to the approver inbox / owner transcript would otherwise fail the
    confirmation item's ``additionalProperties:false``. Locks model<->schema
    parity for the SPEC-054 record fields."""
    from agent_service.schemas.v2 import ConfirmationRecordModel

    sentence = 'Delete pod "scratch-restart-demo" in namespace "default"'
    card = ConfirmationRecordModel(
        confirm_id="cf-action",
        session_id="ses-1",
        owner_user_id="alice",
        pending_calls=[
            {
                "call_id": "c1",
                "tool_name": "k8s.delete_pod",
                "parameters": {"name": "scratch-restart-demo"},
                "change_request": {"summary": sentence},
            }
        ],
        action="tools:mutate",
        approval_kind="action",
        message=sentence,
    )
    dumped = json.loads(card.model_dump_json())
    item_schema = load_schema("agent-session.schema.json")["properties"][
        "confirmations"
    ]["items"]
    jsonschema.validate(dumped, item_schema)
    assert dumped["approval_kind"] == "action"
    assert dumped["message"] == sentence


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
