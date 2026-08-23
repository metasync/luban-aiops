"""SPEC-022 R-1: session workspace API — list, get-with-transcript, delete.

Covers ownership/cap/ordering on the list surface, transcript
reconstruction and fallback, parked-confirmation protection on delete,
server-side title minting, and the voice-readiness contract invariants
(R-2) at the schema level.
"""

import json
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent_service.app import create_app
from agent_service.schemas.v2 import AgentChatRequest
from agent_service.services import session_service, session_transcript
from agent_service.services.agent_state_store import InMemoryAgentStateStore
from agent_service.services.hitl_confirmations import CONFIRMATION_REGISTRY
from agent_service.services.session_store import InMemorySessionStore

SCHEMAS_DIR = (
    Path(__file__).resolve().parents[3] / "shared" / "shared-contracts" / "schemas"
)


def load_schema(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / name).read_text())


def _client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture()
def workspace(monkeypatch):
    session_store = InMemorySessionStore()
    state_store = InMemoryAgentStateStore()
    monkeypatch.setattr(session_service, "SESSION_STORE", session_store)
    monkeypatch.setattr(session_service, "AGENT_STATE_STORE", state_store)
    monkeypatch.setattr(session_transcript, "AGENT_STATE_STORE", state_store)
    CONFIRMATION_REGISTRY._by_session.clear()
    yield session_store, state_store
    CONFIRMATION_REGISTRY._by_session.clear()


def _snapshot_json(turns: list[dict]) -> str:
    """Build a kernel-shaped AgentState snapshot carrying chat messages."""
    return json.dumps(
        {
            "session_id": "ses-1",
            "context": turns,
        }
    )


# --- List ---


def test_list_sessions_returns_own_sessions_most_recent_first(workspace):
    session_store, _ = workspace
    client = _client()
    oldest = session_store.create_session("alice")
    newest = session_store.create_session("alice")
    session_store.create_session("bob")
    # Bump the older session so ordering follows activity, not creation.
    session_store.touch_session(oldest.session_id)

    response = client.get("/api/v2/sessions", headers={"X-User-ID": "alice"})
    assert response.status_code == 200
    body = response.json()
    assert [s["session_id"] for s in body["sessions"]] == [
        oldest.session_id,
        newest.session_id,
    ]
    # Foreign sessions never appear in another user's workspace.
    assert "bob" not in json.dumps(body)


def test_list_sessions_capped_at_50(workspace):
    session_store, _ = workspace
    for _ in range(55):
        session_store.create_session("alice")

    response = _client().get("/api/v2/sessions", headers={"X-User-ID": "alice"})
    assert response.status_code == 200
    assert len(response.json()["sessions"]) == 50


def test_list_sessions_requires_identity():
    response = _client().get("/api/v2/sessions")
    assert response.status_code == 401


def test_list_sessions_conforms_to_contract(workspace):
    session_store, _ = workspace
    session_store.create_session("alice")
    response = _client().get("/api/v2/sessions", headers={"X-User-ID": "alice"})
    jsonschema.validate(
        response.json(), load_schema("agent-session-list.schema.json")
    )


# --- Get with transcript ---


def test_get_session_surfaces_workspace_fields_without_snapshot(workspace):
    session_store, _ = workspace
    record = session_store.create_session("alice")
    session_service.mark_session_turn(record.session_id, "check the web-ui pod")

    response = _client().get(
        f"/api/v2/sessions/{record.session_id}", headers={"X-User-ID": "alice"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "check the web-ui pod"
    assert body["last_active_at"] is not None
    assert body["pending_confirmation"] is False
    # No kernel state snapshot yet: explicit fallback, never a failure.
    assert body["transcript_available"] is False
    assert body["transcript"] == []


def test_get_session_reconstructs_transcript_from_state_snapshot(workspace):
    session_store, state_store = workspace
    record = session_store.create_session("alice")
    state_store.save_state(
        record.session_id,
        _snapshot_json(
            [
                {"role": "system", "content": [{"type": "text", "text": "prompt"}]},
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "check the pods"}],
                    "created_at": "2026-08-22T10:00:00Z",
                },
                {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "text": "internal"},
                        {"type": "text", "text": "All pods are running."},
                    ],
                },
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_call",
                            "name": "k8s.list_pods",
                            "input": "{}",
                        }
                    ],
                },
            ]
        ),
    )

    response = _client().get(
        f"/api/v2/sessions/{record.session_id}", headers={"X-User-ID": "alice"}
    )
    body = response.json()
    assert body["transcript_available"] is True
    # Chat text only: system and tool frames stay out of v1 transcripts.
    assert body["transcript"] == [
        {
            "role": "user",
            "content": "check the pods",
            "created_at": "2026-08-22T10:00:00Z",
        },
        {"role": "assistant", "content": "All pods are running."},
    ]
    jsonschema.validate(body, load_schema("agent-session.schema.json"))


def test_get_session_corrupt_snapshot_falls_back(workspace):
    session_store, state_store = workspace
    record = session_store.create_session("alice")
    state_store.save_state(record.session_id, "{not-json")

    response = _client().get(
        f"/api/v2/sessions/{record.session_id}", headers={"X-User-ID": "alice"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["transcript_available"] is False
    assert body["transcript"] == []


# --- Persisted evidence (SPEC-025 R-2) ---


def _evidence_frames(session_id: str) -> list[dict]:
    return [
        {
            "type": "tool_call",
            "session_id": session_id,
            "request_id": "req-1",
            "tool_name": "k8s.list_pods",
            "call_id": "call-1",
            "parameters": {"namespace": "dev-luban-aiops"},
        },
        {
            "type": "tool_result",
            "session_id": session_id,
            "request_id": "req-1",
            "tool_name": "k8s.list_pods",
            "call_id": "call-1",
            "status": "success",
            "evidence": {"duration_ms": 42, "risk_level": "read"},
            "data": {"count": 3},
        },
    ]


def test_get_session_returns_persisted_evidence_turns(workspace, monkeypatch):
    from agent_service.api.v2 import routes
    from agent_service.services.evidence_store import InMemoryEvidenceStore

    session_store, _ = workspace
    evidence_store = InMemoryEvidenceStore()
    monkeypatch.setattr(routes, "EVIDENCE_STORE", evidence_store)
    record = session_store.create_session("alice")
    evidence_store.save_turn(
        record.session_id, "req-1", 0, _evidence_frames(record.session_id), 1 << 30
    )

    response = _client().get(
        f"/api/v2/sessions/{record.session_id}", headers={"X-User-ID": "alice"}
    )
    assert response.status_code == 200
    body = response.json()
    turns = body["evidence_turns"]
    assert len(turns) == 1
    assert turns[0]["turn_index"] == 0
    assert turns[0]["request_id"] == "req-1"
    assert turns[0]["created_at"]
    # Frame order and metadata survive the round trip untouched.
    assert [f["type"] for f in turns[0]["frames"]] == ["tool_call", "tool_result"]
    assert turns[0]["frames"][1]["data"] == {"count": 3}
    jsonschema.validate(body, load_schema("agent-session.schema.json"))
    for turn in turns:
        jsonschema.validate(turn, load_schema("session-evidence.schema.json"))


def test_get_session_evidence_turns_empty_when_none_stored(workspace, monkeypatch):
    from agent_service.api.v2 import routes
    from agent_service.services.evidence_store import InMemoryEvidenceStore

    session_store, _ = workspace
    monkeypatch.setattr(routes, "EVIDENCE_STORE", InMemoryEvidenceStore())
    record = session_store.create_session("alice")

    response = _client().get(
        f"/api/v2/sessions/{record.session_id}", headers={"X-User-ID": "alice"}
    )
    assert response.status_code == 200
    # No stored evidence: explicit empty list, never null, never a failure.
    assert response.json()["evidence_turns"] == []


def test_get_session_degrades_to_null_when_evidence_store_unreadable(
    workspace, monkeypatch
):
    from agent_service.api.v2 import routes

    class BrokenEvidenceStore:
        def load_turns(self, session_id):
            raise RuntimeError("evidence store down")

    session_store, _ = workspace
    monkeypatch.setattr(routes, "EVIDENCE_STORE", BrokenEvidenceStore())
    record = session_store.create_session("alice")

    response = _client().get(
        f"/api/v2/sessions/{record.session_id}", headers={"X-User-ID": "alice"}
    )
    # Degrades like transcript_available=false: null field, never a 500.
    assert response.status_code == 200
    assert response.json()["evidence_turns"] is None


# --- Delete ---


def test_delete_session_removes_session_and_state(workspace):
    session_store, state_store = workspace
    record = session_store.create_session("alice")
    state_store.save_state(record.session_id, _snapshot_json([]))

    response = _client().delete(
        f"/api/v2/sessions/{record.session_id}", headers={"X-User-ID": "alice"}
    )
    assert response.status_code == 200
    assert response.json() == {"session_id": record.session_id, "deleted": True}
    assert session_store.get_session(record.session_id) is None
    assert state_store.load_state(record.session_id) is None


def test_delete_unknown_or_foreign_session_returns_404(workspace):
    session_store, _ = workspace
    record = session_store.create_session("alice")
    client = _client()

    unknown = client.delete(
        "/api/v2/sessions/ses-does-not-exist", headers={"X-User-ID": "alice"}
    )
    foreign = client.delete(
        f"/api/v2/sessions/{record.session_id}", headers={"X-User-ID": "bob"}
    )
    # Anti-enumeration: both cases are indistinguishable.
    assert unknown.status_code == 404
    assert foreign.status_code == 404
    assert session_store.get_session(record.session_id) is not None


def test_delete_parked_session_returns_409(workspace):
    session_store, _ = workspace
    record = session_store.create_session("alice")
    CONFIRMATION_REGISTRY.register(
        session_id=record.session_id,
        user_id="alice",
        reply_id="reply-1",
        tool_calls=[],
        timeout=300,
    )

    response = _client().delete(
        f"/api/v2/sessions/{record.session_id}", headers={"X-User-ID": "alice"}
    )
    assert response.status_code == 409
    assert session_store.get_session(record.session_id) is not None


def test_pending_confirmation_flag_rides_list_and_get(workspace):
    session_store, _ = workspace
    record = session_store.create_session("alice")
    CONFIRMATION_REGISTRY.register(
        session_id=record.session_id,
        user_id="alice",
        reply_id="reply-1",
        tool_calls=[],
        timeout=300,
    )
    client = _client()

    listed = client.get("/api/v2/sessions", headers={"X-User-ID": "alice"}).json()
    assert listed["sessions"][0]["pending_confirmation"] is True

    detail = client.get(
        f"/api/v2/sessions/{record.session_id}", headers={"X-User-ID": "alice"}
    ).json()
    assert detail["pending_confirmation"] is True


def test_has_pending_is_ttl_agnostic(workspace):
    session_store, _ = workspace
    record = session_store.create_session("alice")
    pending = CONFIRMATION_REGISTRY.register(
        session_id=record.session_id,
        user_id="alice",
        reply_id="reply-1",
        tool_calls=[],
        timeout=1,
    )
    # Force the entry past its TTL: an expired park still awaits closure,
    # so the workspace must keep badging it.
    pending.created_at -= 3600
    assert CONFIRMATION_REGISTRY.has_pending(record.session_id) is True

    CONFIRMATION_REGISTRY.resolve(record.session_id, pending.confirm_id)
    assert CONFIRMATION_REGISTRY.has_pending(record.session_id) is False


# --- Title minting ---


def test_title_minted_once_capped_and_whitespace_collapsed(workspace):
    session_store, _ = workspace
    record = session_store.create_session("alice")
    long_message = "please   check the deployment status of the web-ui pod " * 5
    session_service.mark_session_turn(record.session_id, long_message)

    titled = session_store.get_session(record.session_id)
    assert titled is not None
    assert titled.title is not None
    assert len(titled.title) <= 80
    assert "  " not in titled.title

    # Later turns never rewrite the minted title.
    session_service.mark_session_turn(record.session_id, "a different question")
    assert session_store.get_session(record.session_id).title == titled.title


def test_blank_message_never_mints_title(workspace):
    session_store, _ = workspace
    record = session_store.create_session("alice")
    session_service.mark_session_turn(record.session_id, "   ")
    assert session_store.get_session(record.session_id).title is None


# --- Voice-readiness contract (R-2) ---


def test_chat_request_accepts_modality_enum_and_defaults_text():
    assert AgentChatRequest(message="hi").input_modality == "text"
    assert AgentChatRequest(message="hi", input_modality="voice").input_modality == "voice"
    with pytest.raises(ValidationError):
        AgentChatRequest(message="hi", input_modality="audio")


def test_chat_contract_rejects_unknown_modality():
    schema = load_schema("agent-chat-request.schema.json")
    jsonschema.validate(
        {"message": "hi", "input_modality": "voice"}, schema
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"message": "hi", "input_modality": "audio"}, schema)


def test_confirm_contract_rejects_modality_fields():
    """Invariant II: the decision surface is unchanged — no modality field
    may ride a confirm request, so voice input can never approve or deny."""
    schema = load_schema("chat-confirm.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {
                "session_id": "ses-1",
                "confirm_id": "c-1",
                "decision": "approve",
                "input_modality": "voice",
            },
            schema,
        )
