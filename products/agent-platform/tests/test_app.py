from fastapi.testclient import TestClient

from agent_service.app import create_app


def test_transitional_fastapi_surface_smoke() -> None:
    client = TestClient(create_app())

    live = client.get("/health/live")
    assert live.status_code == 200
    assert live.json()["service"] == "agent-service"

    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["runtime_mode"] == "placeholder"

    runtime = client.get("/api/v1/runtime")
    assert runtime.status_code == 200
    assert runtime.json()["runtime_mode"] == "placeholder"

    session = client.post("/api/v1/sessions", json={"user_id": "alice"})
    assert session.status_code == 200
    session_payload = session.json()
    assert session_payload["user_id"] == "alice"
    assert session_payload["status"] == "active"

    chat = client.post(
        "/api/v1/chat",
        json={
            "message": "hello",
            "session_id": session_payload["session_id"],
            "user_id": "alice",
        },
        headers={"X-Request-ID": "req-test"},
    )
    assert chat.status_code == 200
    chat_payload = chat.json()
    assert chat_payload["request_id"] == "req-test"
    assert chat_payload["session_id"] == session_payload["session_id"]
    assert "placeholder response" in chat_payload["response"]
