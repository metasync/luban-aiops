from fastapi.testclient import TestClient

from agent_service.app import create_app


def test_v2_contract_surface_smoke() -> None:
    client = TestClient(create_app())

    runtime = client.get("/api/v2/runtime")
    assert runtime.status_code == 200
    assert runtime.json()["runtime_mode"] == "placeholder"

    health = client.get("/api/v2/health")
    assert health.status_code == 200
    assert health.json()["status"] == "not_ready"

    session = client.post(
        "/api/v2/sessions",
        headers={"X-User-ID": "alice"},
    )
    assert session.status_code == 201
    session_payload = session.json()
    assert session_payload["user_id"] == "alice"
    assert session_payload["status"] == "active"

    chat = client.post(
        "/api/v2/chat",
        json={
            "message": "hello",
            "session_id": session_payload["session_id"],
        },
        headers={"X-User-ID": "alice", "x-request-id": "req-test"},
    )
    assert chat.status_code == 200
    chat_payload = chat.json()
    assert chat_payload["request_id"] == "req-test"
    assert chat_payload["session_id"] == session_payload["session_id"]
    assert "placeholder response" in chat_payload["content"]


def test_v2_chat_requires_user_id_header() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v2/chat", json={"message": "hello"})
    assert response.status_code == 401
