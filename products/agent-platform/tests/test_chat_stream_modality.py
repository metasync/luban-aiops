"""SPEC-023 R-4: voice-readiness parity for the streaming surface.

The stream route accepts the additive ``input_modality`` query parameter
(``text``|``voice``, default ``text``) mirroring POST /api/v2/chat's body
field. Modality is metadata only — it never changes policy or HITL
outcomes; these tests pin acceptance, validation, and pass-through.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from agent_service.app import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_chat_stream_accepts_voice_modality() -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]

    response = client.get(
        "/api/v2/chat/stream",
        params={
            "message": "hello",
            "session_id": session_id,
            "input_modality": "voice",
        },
        headers={"X-User-ID": "alice"},
    )

    assert response.status_code == 200
    assert response.text.startswith("data: ")


def test_chat_stream_defaults_to_text_modality() -> None:
    client = _client()
    session = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    session_id = session.json()["session_id"]

    response = client.get(
        "/api/v2/chat/stream",
        params={"message": "hello", "session_id": session_id},
        headers={"X-User-ID": "alice"},
    )

    assert response.status_code == 200


def test_chat_stream_rejects_unknown_modality() -> None:
    client = _client()

    response = client.get(
        "/api/v2/chat/stream",
        params={"message": "hello", "input_modality": "telepathy"},
        headers={"X-User-ID": "alice"},
    )

    assert response.status_code == 422
