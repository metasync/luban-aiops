"""SPEC-039 R-2/R-5: agent document routes, visibility matrix, audit.

End-to-end through the v2 app: creation (bounded input, foreign
gating), the visibility matrix (drafts owner-only; published
team-visible), one-way publish, owner delete, cross-owner read audit,
and contract validation against operation-document.schema.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from agent_service.api.v2 import routes as v2_routes
from agent_service.app import create_app
from agent_service.services.operation_documents import (
    OPERATION_DOCUMENT_STORE,
)
from agent_service.services.session_store import SESSION_STORE

SCHEMAS_DIR = (
    Path(__file__).resolve().parents[3]
    / "shared"
    / "shared-contracts"
    / "schemas"
)


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _clean_stores(monkeypatch):
    documents = getattr(OPERATION_DOCUMENT_STORE, "_by_document_id", None)
    sessions = getattr(SESSION_STORE, "_sessions", None)
    last_accessed = getattr(SESSION_STORE, "_last_accessed", None)
    if documents is not None:
        documents.clear()
    if sessions is not None:
        sessions.clear()
    if last_accessed is not None:
        last_accessed.clear()

    emitted: list[dict] = []

    def _capture(settings, event: dict) -> None:
        emitted.append(event)

    monkeypatch.setattr(v2_routes, "emit_audit_event", _capture)
    yield emitted
    if documents is not None:
        documents.clear()
    if sessions is not None:
        sessions.clear()
    if last_accessed is not None:
        last_accessed.clear()


def _session(client: TestClient, user: str) -> str:
    response = client.post("/api/v2/sessions", headers={"X-User-ID": user})
    assert response.status_code == 201
    return response.json()["session_id"]


def _create_draft(client: TestClient, user: str, session_ids: list[str], **extra):
    body = {
        "document_type": "shift_summary",
        "session_ids": session_ids,
        "label": "night shift",
        "include_prose": False,
        **extra,
    }
    return client.post("/api/v2/documents", json=body, headers={"X-User-ID": user})


class TestCreateDocument:
    def test_create_own_draft(self) -> None:
        app_client = TestClient(create_app())
        session_id = _session(app_client, "alice")
        response = _create_draft(app_client, "alice", [session_id])
        assert response.status_code == 201
        document = response.json()
        assert document["state"] == "draft"
        assert document["document_type"] == "shift_summary"
        assert document["owner_user_id"] == "alice"
        assert document["prose_status"] == "not_requested"
        assert document["prose"] is None
        entry = document["digest"]["sessions"][0]
        assert entry["coverage"] == "owner"
        assert document["provenance"]["sessions"][0]["session_id"] == session_id
        # The envelope validates against the shared contract.
        jsonschema.validate(document, _load_schema("operation-document.schema.json"))

    def test_create_emits_document_created_audit(self, _clean_stores) -> None:
        app_client = TestClient(create_app())
        session_id = _session(app_client, "alice")
        response = _create_draft(app_client, "alice", [session_id])
        assert response.status_code == 201
        events = [e for e in _clean_stores if e["event_type"] == "document_created"]
        assert len(events) == 1
        details = events[0]["details"]
        assert details["own_session_count"] == 1
        assert details["foreign_session_count"] == 0
        assert details["prose_status"] == "not_requested"
        assert events[0]["username"] == "alice"

    def test_unknown_session_ids_rejected_structurally(self) -> None:
        app_client = TestClient(create_app())
        response = _create_draft(app_client, "alice", ["nope-1", "nope-2"])
        assert response.status_code == 400
        assert "nope-1" in response.json()["detail"]

    def test_bounded_input_enforced(self) -> None:
        app_client = TestClient(create_app())
        session_id = _session(app_client, "alice")
        response = _create_draft(
            app_client, "alice", [session_id] + [f"x-{i}" for i in range(25)]
        )
        # 26 ids violate the contract bound (max 20) before assembly.
        assert response.status_code == 422

    def test_blank_label_rejected(self) -> None:
        app_client = TestClient(create_app())
        session_id = _session(app_client, "alice")
        response = app_client.post(
            "/api/v2/documents",
            json={
                "document_type": "shift_summary",
                "session_ids": [session_id],
                "label": "   ",
            },
            headers={"X-User-ID": "alice"},
        )
        # Whitespace-only labels fail the trimmed-length check.
        assert response.status_code == 400

    def test_foreign_session_without_capability_rejected(self) -> None:
        app_client = TestClient(create_app())
        foreign_id = _session(app_client, "carol")
        response = _create_draft(app_client, "alice", [foreign_id])
        assert response.status_code == 403
        assert "approvals:list" in response.json()["detail"]

    def test_foreign_session_with_capability_metadata_only(
        self, _clean_stores
    ) -> None:
        app_client = TestClient(create_app())
        foreign_id = _session(app_client, "carol")
        response = app_client.post(
            "/api/v2/documents",
            json={
                "document_type": "shift_summary",
                "session_ids": [foreign_id],
                "label": "covering carol",
            },
            headers={
                "X-User-ID": "alice",
                "X-Foreign-Coverage": "allowed",
            },
        )
        assert response.status_code == 201
        entry = response.json()["digest"]["sessions"][0]
        assert entry["coverage"] == "foreign"
        assert "title" not in entry
        events = [e for e in _clean_stores if e["event_type"] == "document_created"]
        assert events[0]["details"]["foreign_session_count"] == 1


class TestVisibilityMatrix:
    def _seed_published(self, client: TestClient) -> str:
        session_id = _session(client, "alice")
        created = _create_draft(client, "alice", [session_id]).json()
        published = client.post(
            f"/api/v2/documents/{created['document_id']}/publish",
            headers={"X-User-ID": "alice"},
        )
        assert published.status_code == 200
        return created["document_id"]

    def test_mine_scope_is_owner_scoped(self) -> None:
        app_client = TestClient(create_app())
        session_id = _session(app_client, "alice")
        _create_draft(app_client, "alice", [session_id])
        bob_rows = app_client.get(
            "/api/v2/documents", params={"scope": "mine"},
            headers={"X-User-ID": "bob"},
        ).json()["documents"]
        assert bob_rows == []

    def test_published_scope_never_carries_drafts(self, _clean_stores) -> None:
        app_client = TestClient(create_app())
        draft_id = _create_draft(
            app_client, "alice", [_session(app_client, "alice")]
        ).json()["document_id"]
        published_id = self._seed_published(app_client)
        rows = app_client.get(
            "/api/v2/documents",
            params={"scope": "published"},
            headers={"X-User-ID": "bob"},
        ).json()["documents"]
        ids = [row["document_id"] for row in rows]
        assert published_id in ids
        assert draft_id not in ids

    def test_foreign_draft_is_indistinguishable_from_unknown(self) -> None:
        app_client = TestClient(create_app())
        session_id = _session(app_client, "alice")
        draft_id = _create_draft(app_client, "alice", [session_id]).json()[
            "document_id"
        ]
        foreign = app_client.get(
            f"/api/v2/documents/{draft_id}", headers={"X-User-ID": "bob"}
        )
        unknown = app_client.get(
            "/api/v2/documents/doc-does-not-exist", headers={"X-User-ID": "bob"}
        )
        assert foreign.status_code == unknown.status_code == 404

    def test_cross_owner_read_is_audited_own_read_is_not(
        self, _clean_stores
    ) -> None:
        app_client = TestClient(create_app())
        document_id = self._seed_published(app_client)
        own = app_client.get(
            f"/api/v2/documents/{document_id}", headers={"X-User-ID": "alice"}
        )
        assert own.status_code == 200
        cross = app_client.get(
            f"/api/v2/documents/{document_id}", headers={"X-User-ID": "bob"}
        )
        assert cross.status_code == 200
        reads = [e for e in _clean_stores if e["event_type"] == "document_read"]
        assert len(reads) == 1
        assert reads[0]["username"] == "bob"
        assert reads[0]["details"]["owner_user_id"] == "alice"


class TestPublishAndDelete:
    def test_publish_is_one_way_and_audited(self, _clean_stores) -> None:
        app_client = TestClient(create_app())
        session_id = _session(app_client, "alice")
        document_id = _create_draft(app_client, "alice", [session_id]).json()[
            "document_id"
        ]
        first = app_client.post(
            f"/api/v2/documents/{document_id}/publish",
            headers={"X-User-ID": "alice"},
        )
        assert first.status_code == 200
        assert first.json()["state"] == "published"
        assert first.json()["published_at"] is not None
        # Publishing is one-way: a second publish is a conflict.
        again = app_client.post(
            f"/api/v2/documents/{document_id}/publish",
            headers={"X-User-ID": "alice"},
        )
        assert again.status_code == 409
        events = [
            e for e in _clean_stores if e["event_type"] == "document_published"
        ]
        assert len(events) == 1
        assert events[0]["details"]["document_id"] == document_id

    def test_publish_foreign_document_404(self) -> None:
        app_client = TestClient(create_app())
        session_id = _session(app_client, "alice")
        document_id = _create_draft(app_client, "alice", [session_id]).json()[
            "document_id"
        ]
        response = app_client.post(
            f"/api/v2/documents/{document_id}/publish",
            headers={"X-User-ID": "bob"},
        )
        assert response.status_code == 404

    def test_delete_own_document(self) -> None:
        app_client = TestClient(create_app())
        session_id = _session(app_client, "alice")
        document_id = _create_draft(app_client, "alice", [session_id]).json()[
            "document_id"
        ]
        foreign = app_client.delete(
            f"/api/v2/documents/{document_id}", headers={"X-User-ID": "bob"}
        )
        assert foreign.status_code == 404
        own = app_client.delete(
            f"/api/v2/documents/{document_id}", headers={"X-User-ID": "alice"}
        )
        assert own.status_code == 200
        assert own.json() == {"document_id": document_id, "deleted": True}
        gone = app_client.get(
            f"/api/v2/documents/{document_id}", headers={"X-User-ID": "alice"}
        )
        assert gone.status_code == 404


class TestSessionRename:
    def test_owner_rename_overwrites_minted_title(self) -> None:
        app_client = TestClient(create_app())
        session_id = _session(app_client, "alice")
        response = app_client.patch(
            f"/api/v2/sessions/{session_id}/title",
            json={"title": "  night shift 2026-08-27  "},
            headers={"X-User-ID": "alice"},
        )
        assert response.status_code == 200
        assert response.json()["title"] == "night shift 2026-08-27"
        # The list surface reflects the new title.
        rows = app_client.get(
            "/api/v2/sessions", headers={"X-User-ID": "alice"}
        ).json()["sessions"]
        assert rows[0]["title"] == "night shift 2026-08-27"

    def test_rename_foreign_or_unknown_session_404(self) -> None:
        app_client = TestClient(create_app())
        session_id = _session(app_client, "alice")
        foreign = app_client.patch(
            f"/api/v2/sessions/{session_id}/title",
            json={"title": "hijack"},
            headers={"X-User-ID": "bob"},
        )
        unknown = app_client.patch(
            "/api/v2/sessions/nope/title",
            json={"title": "hijack"},
            headers={"X-User-ID": "bob"},
        )
        assert foreign.status_code == unknown.status_code == 404

    def test_rename_blank_title_rejected(self) -> None:
        app_client = TestClient(create_app())
        session_id = _session(app_client, "alice")
        response = app_client.patch(
            f"/api/v2/sessions/{session_id}/title",
            json={"title": "    "},
            headers={"X-User-ID": "alice"},
        )
        assert response.status_code == 400

    def test_rename_supersedes_minted_title(self) -> None:
        app_client = TestClient(create_app())
        session_id = _session(app_client, "alice")
        # Mint a title through a chat-turn bookkeeping call.
        from agent_service.services.session_service import mark_session_turn

        mark_session_turn(session_id, "investigate the payment outage")
        response = app_client.patch(
            f"/api/v2/sessions/{session_id}/title",
            json={"title": "renamed by owner"},
            headers={"X-User-ID": "alice"},
        )
        assert response.status_code == 200
        assert response.json()["title"] == "renamed by owner"
