"""SPEC-022 R-1: session workspace API — list, get-with-transcript, delete.

Covers ownership/cap/ordering on the list surface, transcript
reconstruction and fallback, parked-confirmation protection on delete,
server-side title minting, and the voice-readiness contract invariants
(R-2) at the schema level.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent_service.api.v2 import routes as v2_routes
from agent_service.app import create_app
from agent_service.schemas.v2 import AgentChatRequest
from agent_service.services import session_service, session_transcript
from agent_service.services.agent_state_store import InMemoryAgentStateStore
from agent_service.services.confirmation_records import (
    CONFIRMATION_RECORD_STORE,
    make_record,
)
from agent_service.services.execution_records import EXECUTION_RECORD_STORE
from agent_service.services.execution_recovery import ExecutionRecovery
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


def test_get_session_joins_text_blocks_with_paragraph_break(workspace):
    """SPEC-035 R-1: each text block is one reasoning segment between tool
    calls; they must join with a blank line so a segment that starts with
    block markdown (a heading, list, or rule) still renders as markdown
    instead of gluing onto the previous segment's last sentence."""
    session_store, state_store = workspace
    record = session_store.create_session("alice")
    state_store.save_state(
        record.session_id,
        _snapshot_json(
            [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "restart the pod"}],
                },
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Checking the controller."},
                        {
                            "type": "tool_call",
                            "name": "k8s.delete_pod",
                            "input": "{}",
                        },
                        {"type": "tool_result", "output": "ok"},
                        {"type": "text", "text": "## Pod Restart Summary"},
                    ],
                },
            ]
        ),
    )

    response = _client().get(
        f"/api/v2/sessions/{record.session_id}", headers={"X-User-ID": "alice"}
    )
    body = response.json()
    assert body["transcript"] == [
        {"role": "user", "content": "restart the pod"},
        {
            "role": "assistant",
            "content": "Checking the controller.\n\n## Pod Restart Summary",
        },
    ]


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


def test_delete_session_removes_session_and_state(workspace, monkeypatch):
    from agent_service.api.v2 import routes
    from agent_service.runtime_kernel import AgentKernel

    kernel = AgentKernel()
    monkeypatch.setattr(routes, "get_runtime_kernel", lambda: kernel)
    session_store, state_store = workspace
    record = session_store.create_session("alice")
    kernel._generated_literals[record.session_id] = {"fixture-generated!"}
    state_store.save_state(record.session_id, _snapshot_json([]))

    response = _client().delete(
        f"/api/v2/sessions/{record.session_id}", headers={"X-User-ID": "alice"}
    )
    assert response.status_code == 200
    assert response.json() == {"session_id": record.session_id, "deleted": True}
    assert session_store.get_session(record.session_id) is None
    assert state_store.load_state(record.session_id) is None
    assert record.session_id not in kernel._generated_literals


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


# --- Title secret masking (SPEC-049 R-5 applied to a UI label) ---
#
# The title is minted from the *user's own* message, which is the one
# credential carrier no tool-side redactor ever sees, and it is rendered in
# front of a second identity: an approver's inbox lists a pending card by its
# session title. Everything below is asserted through ``mark_session_turn``
# rather than against the private projection, so the layer that actually
# stores the label is the one under test.


def _mint(workspace, message: str) -> str | None:
    session_store, _ = workspace
    record = session_store.create_session("alice")
    session_service.mark_session_turn(record.session_id, message)
    return session_store.get_session(record.session_id).title


def test_title_masks_a_bare_password_the_operator_typed(workspace):
    """The flow sample's own prompt. No pinned shape, no ``key=value``, no URL
    query — a bare literal in prose, caught only by the credential-literal
    layer that fires because the message names a secret."""
    title = _mint(
        workspace,
        "Reset the password for user alice@example.com to TempPass123! in the "
        "admin portal. Use skill samples/password-reset-resetuserpassword.",
    )

    assert "TempPass123" not in title
    assert "***" in title
    # Surgical, not wholesale: the address and the opening of the request
    # survive, so the label still says what the session is about.
    assert "alice@example.com" in title
    assert title.startswith("Reset the password for user")


def test_title_masks_before_the_cap_so_no_fragment_survives(workspace):
    """The ad-hoc sample's prompt put the secret across the 80-char boundary,
    so truncating first left a sidebar reading ``... to Temp``. Masking runs
    before the cap."""
    title = _mint(
        workspace,
        "Ad-hoc, without binding a flow, reset the password for "
        "alice@example.com to TempPass-2026! in the admin portal.",
    )

    assert "TempPass" not in title
    assert "Temp" not in title
    assert "to ***" in title
    # The cap still bites, and it bites the masked text: the words after the
    # secret are what got truncated away, not the secret's first characters.
    assert len(title) == 80
    assert "admin portal" not in title


def test_title_masks_a_key_anchored_secret(workspace):
    """``password=<value>`` in prose: the name vocabulary catches it with no
    help from the heuristic, and the key stays visible so the label still says
    a password was involved."""
    title = _mint(
        workspace,
        "rotate the db password=hunter2secret for the payment service",
    )

    assert "hunter2secret" not in title
    assert "password=***" in title


def test_title_masks_a_secret_url_query_and_keeps_the_other_params(workspace):
    """The URL layer, exercised on free text: the secret param masks and the
    non-secret one beside it stays readable. Prose *after* the query survives
    too — the parse is bounded to the whitespace-delimited URL rather than
    handed the whole sentence, which used to read "and confirm" as part of
    the last query value and mask it away."""
    title = _mint(
        workspace,
        "open https://target/reset?user=alice&newpw=TempPass123%21 and confirm",
    )

    assert "TempPass123" not in title
    assert "newpw=***" in title
    assert "user=alice" in title
    assert title.endswith("and confirm")


def test_title_masks_a_pinned_secret_shape(workspace):
    """The shape vocabulary is reused, not re-declared: it is pinned as exactly
    two copies across products, so a third caller must import one."""
    title = _mint(
        workspace,
        "call the api with Bearer abcdefgh12345678 for the payments service",
    )

    assert "abcdefgh12345678" not in title
    assert "***" in title


def test_title_masking_leaves_an_ordinary_message_alone(workspace):
    """The heuristic is gated on the message naming a secret, so a normal
    operations request is not touched — and the hyphenated identifiers this
    product is full of survive even when the gate does open."""
    assert _mint(workspace, "check the web-ui pod in dev-luban-aiops") == (
        "check the web-ui pod in dev-luban-aiops"
    )

    gated = _mint(
        workspace,
        "reset the password using runbook acme-admin on "
        "dev-luban-aiops",
    )
    assert "acme-admin" in gated
    assert "dev-luban-aiops" in gated
    assert "runbook" in gated


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


# --- SPEC-056 R-1/R-2: session_type birth, carry, and list scope ---


def test_create_session_persists_development_type(workspace):
    """A ``development`` body writes the birth type once and every read surface
    (create return, stored record, ``read_session``) carries it (R-1)."""
    session_store, _ = workspace
    client = _client()
    response = client.post(
        "/api/v2/sessions",
        json={"session_type": "development"},
        headers={"X-User-ID": "alice"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["session_type"] == "development"
    assert session_store.get_session(body["session_id"]).session_type == "development"
    detail = client.get(
        f"/api/v2/sessions/{body['session_id']}", headers={"X-User-ID": "alice"}
    )
    assert detail.status_code == 200
    assert detail.json()["session_type"] == "development"
    jsonschema.validate(detail.json(), load_schema("agent-session.schema.json"))


def test_create_session_defaults_to_operation_without_body(workspace):
    """The historical one-click Chat path (no body) still births ``operation``."""
    response = _client().post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    assert response.status_code == 201
    assert response.json()["session_type"] == "operation"


def test_create_session_operation_body_persists_operation(workspace):
    response = _client().post(
        "/api/v2/sessions",
        json={"session_type": "operation"},
        headers={"X-User-ID": "alice"},
    )
    assert response.status_code == 201
    assert response.json()["session_type"] == "operation"


def test_list_rows_carry_session_type(workspace):
    session_store, _ = workspace
    session_store.create_session("alice", session_type="operation")
    session_store.create_session("alice", session_type="development")
    response = _client().get("/api/v2/sessions", headers={"X-User-ID": "alice"})
    assert response.status_code == 200
    assert {s["session_type"] for s in response.json()["sessions"]} == {
        "operation",
        "development",
    }
    jsonschema.validate(
        response.json(), load_schema("agent-session-list.schema.json")
    )


def test_list_sessions_scopes_by_session_type(workspace):
    """The optional ``session_type`` query param scopes the list server-side;
    omitted returns every session exactly as before (R-2 / R-4)."""
    session_store, _ = workspace
    op = session_store.create_session("alice", session_type="operation")
    dev = session_store.create_session("alice", session_type="development")
    client = _client()

    only_op = client.get(
        "/api/v2/sessions",
        params={"session_type": "operation"},
        headers={"X-User-ID": "alice"},
    )
    assert [s["session_id"] for s in only_op.json()["sessions"]] == [op.session_id]

    only_dev = client.get(
        "/api/v2/sessions",
        params={"session_type": "development"},
        headers={"X-User-ID": "alice"},
    )
    assert [s["session_id"] for s in only_dev.json()["sessions"]] == [dev.session_id]

    all_sessions = client.get("/api/v2/sessions", headers={"X-User-ID": "alice"})
    assert {s["session_id"] for s in all_sessions.json()["sessions"]} == {
        op.session_id,
        dev.session_id,
    }


def test_list_sessions_rejects_unknown_session_type(workspace):
    """The query param is a bounded enum: an unknown value is a 422, never a
    silent fall-through to "all"."""
    response = _client().get(
        "/api/v2/sessions",
        params={"session_type": "staging"},
        headers={"X-User-ID": "alice"},
    )
    assert response.status_code == 422


# --- SPEC-063 R-5a / T-25: bounded owner recovery on the session detail ---
#
# These exercise the *route wiring* only: the session detail extends (never
# replaces) with a top-level ``execution_recovery_availability`` and an optional
# ledger-backed ``recovery`` projection on each execution row. A fake recovery
# store stands in for ``ExecutionRecovery`` so the wiring is proven without a
# ledger; the projection's closed-schema fidelity and owner-scoped paging are
# proven against a real ledger by the F-24 cross-product family. The recovery
# object is typed loosely in agent-session.schema.json (like ``receipt``), so
# responses are validated against that contract here.

_EXEC_ONE = "11111111-1111-1111-1111-111111111111"
_EXEC_TWO = "22222222-2222-2222-2222-222222222222"


def _clear_record_stores():
    for store, attr in (
        (CONFIRMATION_RECORD_STORE, "_by_confirm_id"),
        (EXECUTION_RECORD_STORE, "_by_key"),
    ):
        bucket = getattr(store, attr, None)
        if bucket is not None:
            bucket.clear()


def _seed_recovery_session(session_store, owner="alice"):
    """Own a session carrying one approved card with two signed execution rows
    (SPEC-037 R-4 shape), clearing the durable singletons first for isolation."""
    _clear_record_stores()
    session_id = session_store.create_session(owner).session_id
    confirm_id = "conf-1"
    CONFIRMATION_RECORD_STORE.save_parked(
        make_record(
            confirm_id,
            session_id,
            owner,
            [
                {"call_id": "call-1", "tool_name": "k8s.restart_service"},
                {"call_id": "call-2", "tool_name": "k8s.scale_deployment"},
            ],
            "tools:mutate",
            turn_index=0,
        )
    )
    CONFIRMATION_RECORD_STORE.mark_resolved(
        session_id, confirm_id, "approved", owner, "approve"
    )
    for call_id, execution_id, requested_at in (
        ("call-1", _EXEC_ONE, "2026-09-24T10:00:00Z"),
        ("call-2", _EXEC_TWO, "2026-09-24T10:00:01Z"),
    ):
        EXECUTION_RECORD_STORE.save_request(
            {
                "confirm_id": confirm_id,
                "call_id": call_id,
                "session_id": session_id,
                "execution_id": execution_id,
                "tool_name": "k8s.restart_service",
                "requested_at": requested_at,
                "status": "requested",
            }
        )
    return SimpleNamespace(session_id=session_id, confirm_id=confirm_id, owner=owner)


class _FakeRecovery:
    """Stand-in for ``ExecutionRecovery``: records each ``owner_recovery`` call
    and returns a canned projection so route wiring is exercised ledger-free."""

    def __init__(self, availability="available"):
        self.calls = []
        self.list_calls = []
        self.availability = availability
        self.cursors = ExecutionRecovery("", "test-cursor-key", "")

    def owner_session_recovery(self, session_id, owner_user_id, *, execution=None, cursor=None, page_size=50):
        self.list_calls.append((session_id, owner_user_id, execution, cursor, page_size))
        scope = ("observations", session_id, owner_user_id, execution) if execution else (
            "executions", session_id, owner_user_id)
        position = self.cursors._decode_cursor(scope, cursor)
        ids = [_EXEC_ONE, _EXEC_TWO]
        if execution:
            ids = [execution] if execution in ids else []
        elif position:
            ids = ids[position:]
        more = len(ids) > page_size
        return {
            "availability": self.availability,
            "executions": [self.owner_recovery(value, session_id, owner_user_id,
                cursor=cursor if execution else None) for value in ids[:page_size]]
                if self.availability == "available" else [],
            "executions_truncated": more,
            "next_execution_cursor": self.cursors._encode_cursor(scope, page_size) if more else None,
        }

    def owner_recovery(
        self, execution_id, session_id, owner_user_id, *, cursor=None, replay=False
    ):
        self.calls.append(
            {
                "execution_id": execution_id,
                "session_id": session_id,
                "owner_user_id": owner_user_id,
                "cursor": cursor,
            }
        )
        projection = ExecutionRecovery.empty(
            self.availability,
            execution_id,
            as_of="2026-09-24T10:05:00Z",
            replay=False,
        )
        projection["session_id"] = session_id
        if self.availability == "available":
            projection.update(
                state="result_recorded",
                confirm_id="conf-1",
                call_id="call-1" if execution_id == _EXEC_ONE else "call-2",
                requested_at="2026-09-24T10:00:00Z",
                tool_name="k8s.restart_service",
                receipt={
                    "status": "succeeded",
                    "completed_at": "2026-09-24T10:04:00Z",
                },
                observations=[{"observation_id": "1", "kind": "worker_result"}],
            )
        return projection


def _patch_recovery(monkeypatch, recovery):
    """Route ``read_session``'s kernel lookup at a fake recovery store."""
    monkeypatch.setattr(
        v2_routes,
        "get_runtime_kernel",
        lambda: SimpleNamespace(_execution_recovery=lambda: recovery),
    )


def _execution_rows(detail):
    rows = {}
    for card in detail.json()["confirmations"] or []:
        for execution in card["executions"]:
            rows[execution["execution_id"]] = execution
    return rows


def test_session_detail_recovery_inert_when_admission_disabled(workspace):
    """Default (admission disabled): the recovery path is ``None``, so the
    detail reports availability ``unavailable`` and every execution row stays
    byte-identical with a null ``recovery`` (R-5a inert-by-default)."""
    session_store, _ = workspace
    seeded = _seed_recovery_session(session_store)
    # No patch: the real kernel returns None because admission is disabled.
    detail = _client().get(
        f"/api/v2/sessions/{seeded.session_id}", headers={"X-User-ID": "alice"}
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["execution_recovery_availability"] == "unavailable"
    rows = _execution_rows(detail)
    assert set(rows) == {_EXEC_ONE, _EXEC_TWO}
    assert all(row["recovery"] is None for row in rows.values())
    jsonschema.validate(body, load_schema("agent-session.schema.json"))


def test_session_detail_enriches_owned_executions_when_available(
    workspace, monkeypatch
):
    """With a recovery store bound, the owner reads availability ``available``
    and each execution row carries a ledger-backed projection; the owner
    identity flows through to ``owner_recovery`` (owner-scoped read)."""
    session_store, _ = workspace
    seeded = _seed_recovery_session(session_store)
    fake = _FakeRecovery()
    _patch_recovery(monkeypatch, fake)

    detail = _client().get(
        f"/api/v2/sessions/{seeded.session_id}", headers={"X-User-ID": "alice"}
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["execution_recovery_availability"] == "available"
    rows = _execution_rows(detail)
    for execution_id in (_EXEC_ONE, _EXEC_TWO):
        recovery = rows[execution_id]["recovery"]
        assert recovery["availability"] == "available"
        assert recovery["state"] == "result_recorded"
        assert recovery["execution_id"] == execution_id
        assert recovery["target_verification_required"] is True
    # Both rows were read for the owner, with no cursor (no filter supplied).
    assert {
        (c["execution_id"], c["owner_user_id"], c["cursor"]) for c in fake.calls
    } == {(_EXEC_ONE, "alice", None), (_EXEC_TWO, "alice", None)}
    jsonschema.validate(body, load_schema("agent-session.schema.json"))


def test_session_detail_execution_filter_routes_cursor_to_match(
    workspace, monkeypatch
):
    """The optional ``execution`` filter selects the one execution whose
    observation window is paged with ``execution_cursor``; every other row is
    read with a null cursor (R-5a paging through the session-detail query)."""
    session_store, _ = workspace
    seeded = _seed_recovery_session(session_store)
    fake = _FakeRecovery()
    _patch_recovery(monkeypatch, fake)
    cursor = fake.cursors._encode_cursor(("observations", seeded.session_id, "alice", _EXEC_TWO), 42)

    detail = _client().get(
        f"/api/v2/sessions/{seeded.session_id}",
        params={"execution": _EXEC_TWO, "execution_cursor": cursor},
        headers={"X-User-ID": "alice"},
    )
    assert detail.status_code == 200
    by_id = {c["execution_id"]: c["cursor"] for c in fake.calls}
    assert by_id == {_EXEC_TWO: cursor}
    # The filter reads only its named execution, independently of the list page.
    rows = _execution_rows(detail)
    assert rows[_EXEC_TWO]["recovery"]["availability"] == "available"
    assert rows[_EXEC_ONE]["recovery"] is None


def test_session_detail_page_size_bounds_enrichment(workspace, monkeypatch):
    """``page_size`` bounds how many execution rows are enriched per read; the
    row beyond the page keeps a null ``recovery`` while the session-level flag
    stays ``available`` (the flag is independent of the row window)."""
    session_store, _ = workspace
    seeded = _seed_recovery_session(session_store)
    fake = _FakeRecovery()
    _patch_recovery(monkeypatch, fake)

    detail = _client().get(
        f"/api/v2/sessions/{seeded.session_id}",
        params={"page_size": 1},
        headers={"X-User-ID": "alice"},
    )
    assert detail.status_code == 200
    assert detail.json()["execution_recovery_availability"] == "available"
    rows = _execution_rows(detail)
    # requested_at order: exec-one first (enriched), exec-two beyond the page.
    assert rows[_EXEC_ONE]["recovery"] is not None
    assert rows[_EXEC_TWO]["recovery"] is None
    assert [c["execution_id"] for c in fake.calls] == [_EXEC_ONE]
    assert detail.json()["executions_truncated"] is True
    cursor = detail.json()["next_execution_cursor"]
    next_page = _client().get(f"/api/v2/sessions/{seeded.session_id}",
        params={"page_size": 1, "execution_cursor": cursor}, headers={"X-User-ID": "alice"})
    assert next_page.status_code == 200
    assert next_page.json()["next_execution_cursor"] is None
    assert next_page.json()["executions_truncated"] is False
    assert _execution_rows(next_page)[_EXEC_TWO]["recovery"]["availability"] == "available"


def test_session_detail_recovery_foreign_session_still_404(workspace, monkeypatch):
    """An execution id / request header never bypasses ownership: a non-owner
    read is the existing anti-enumeration 404, and no recovery projection is
    fetched for the intruder (the owner check precedes the ledger read)."""
    session_store, _ = workspace
    seeded = _seed_recovery_session(session_store)
    fake = _FakeRecovery()
    _patch_recovery(monkeypatch, fake)

    detail = _client().get(
        f"/api/v2/sessions/{seeded.session_id}",
        params={"execution": _EXEC_ONE},
        headers={"X-User-ID": "bob"},
    )
    assert detail.status_code == 404
    assert fake.calls == []
    assert fake.list_calls == []


def test_session_detail_availability_survives_presentation_store_outage(
    workspace, monkeypatch
):
    """R-5a: ledger facts are fetched independently of the legacy presentation
    write. An unreadable execution-record store degrades the legacy rows but
    never hides availability — the session still reports ``available`` rather
    than silently substituting an empty history for a recorded outcome."""
    session_store, _ = workspace
    seeded = _seed_recovery_session(session_store)
    fake = _FakeRecovery()
    _patch_recovery(monkeypatch, fake)

    def _boom(_session_id):
        raise RuntimeError("presentation store down")

    monkeypatch.setattr(
        v2_routes,
        "EXECUTION_RECORD_STORE",
        SimpleNamespace(load_for_session=_boom),
    )

    detail = _client().get(
        f"/api/v2/sessions/{seeded.session_id}", headers={"X-User-ID": "alice"}
    )
    assert detail.status_code == 200
    body = detail.json()
    # Availability is computed from the recovery path, not the presentation rows.
    assert body["execution_recovery_availability"] == "available"
    assert set(_execution_rows(detail)) == {_EXEC_ONE, _EXEC_TWO}
    assert all(row["recovery"]["state"] == "result_recorded" for row in _execution_rows(detail).values())
    assert body["confirmations"][0]["turn_index"] == 0
    assert len(fake.calls) == 2
    jsonschema.validate(body, load_schema("agent-session.schema.json"))


@pytest.mark.parametrize("missing", ["empty", "unreadable", "pending"])
def test_session_detail_recovers_without_confirmation_presentation(workspace, monkeypatch, missing):
    session_store, _ = workspace
    seeded = _seed_recovery_session(session_store)
    fake = _FakeRecovery()
    _patch_recovery(monkeypatch, fake)
    old = CONFIRMATION_RECORD_STORE.load_for_session(seeded.session_id)[0]
    def records(_session_id):
        if missing == "unreadable":
            raise RuntimeError("presentation-canary")
        return [{**old, "status": "pending"}] if missing == "pending" else []
    monkeypatch.setattr(v2_routes, "CONFIRMATION_RECORD_STORE", SimpleNamespace(load_for_session=records))
    monkeypatch.setattr(v2_routes, "EXECUTION_RECORD_STORE", SimpleNamespace(load_for_session=lambda _: []))
    detail = _client().get(f"/api/v2/sessions/{seeded.session_id}", headers={"X-User-ID": "alice"})
    assert detail.status_code == 200
    body = detail.json()
    assert set(_execution_rows(detail)) == {_EXEC_ONE, _EXEC_TWO}
    card = body["confirmations"][0]
    assert card["confirm_id"] == seeded.confirm_id and card["recovery_only"] is True
    assert card["status"] == "approved" and card["pending_calls"] == []
    assert card["turn_index"] == (0 if missing == "pending" else None)
    assert "presentation-canary" not in detail.text
    jsonschema.validate(body, load_schema("agent-session.schema.json"))


def test_session_detail_truthfully_reports_ledger_outage(workspace, monkeypatch):
    session_store, _ = workspace
    seeded = _seed_recovery_session(session_store)
    _patch_recovery(monkeypatch, _FakeRecovery("unavailable"))
    detail = _client().get(f"/api/v2/sessions/{seeded.session_id}", headers={"X-User-ID": "alice"})
    assert detail.status_code == 200
    assert detail.json()["execution_recovery_availability"] == "unavailable"
    assert set(_execution_rows(detail)) == {_EXEC_ONE, _EXEC_TWO}
    assert all(row["recovery"]["availability"] == "unavailable" for row in _execution_rows(detail).values())
    assert all(row.get("recovery") is None for row in EXECUTION_RECORD_STORE.load_for_session(seeded.session_id))


@pytest.mark.parametrize("cursor_kind", ["numeric", "wrong_owner", "wrong_session", "wrong_kind", "tampered"])
def test_session_detail_rejects_unscoped_cursors(workspace, monkeypatch, cursor_kind):
    session_store, _ = workspace
    seeded = _seed_recovery_session(session_store)
    fake = _FakeRecovery()
    _patch_recovery(monkeypatch, fake)
    scope = ("executions", seeded.session_id, "alice")
    if cursor_kind == "wrong_owner":
        scope = ("executions", seeded.session_id, "bob")
    if cursor_kind == "wrong_session":
        scope = ("executions", "elsewhere", "alice")
    if cursor_kind == "wrong_kind":
        scope = ("observations", seeded.session_id, "alice", _EXEC_ONE)
    cursor = fake.cursors._encode_cursor(scope, 1)
    if cursor_kind == "numeric":
        cursor = "42"
    if cursor_kind == "tampered":
        cursor = ("A" if cursor[0] != "A" else "B") + cursor[1:]
    detail = _client().get(f"/api/v2/sessions/{seeded.session_id}",
        params={"execution_cursor": cursor}, headers={"X-User-ID": "alice"})
    assert detail.status_code == 400
    assert fake.calls == []
