"""SPEC-076 R-7: the operator-invoked ``POST /api/v2/diagnose`` trigger.

These pin the *route wiring* — profile resolution (fail-closed on unknown), the
incident anchor, the read-only orchestration hand-off, and the response mapping
onto the **existing** ``AgentChatResponse`` (a budget-limited run surfaces as
``status="partial"``). The bounded loop itself is exercised by
``test_orchestration.py``; here ``run_bounded_diagnosis`` is patched so the route
is tested deterministically without a live model fan-out. The route binds **no**
agent-role itself — the orchestration frame inside the loop is the only binder.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from agent_service.app import create_app
from agent_service.services.agent_role import current_agent_role_value
from agent_service.services.orchestration import DiagnosisResult
from agent_service.services.runbooks import get_profile


def _client() -> TestClient:
    return TestClient(create_app())


def _new_session(client: TestClient) -> str:
    response = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    assert response.status_code == 201, response.text
    return response.json()["session_id"]


def _result(profile: str, *, budget_limited: bool = False) -> DiagnosisResult:
    return DiagnosisResult(
        profile=profile,
        goal="g",
        diagnosis=f"diagnosis::{profile}",
        member_summaries=(),
        steps_used=1,
        budget=20,
        budget_limited=budget_limited,
    )


def test_diagnose_resolves_profile_and_returns_diagnosis() -> None:
    client = _client()
    session_id = _new_session(client)
    captured: dict = {}

    async def fake_run(kernel, **kwargs):
        captured.update(kwargs)
        # The route itself binds no role before handing off to the loop.
        captured["role_at_entry"] = current_agent_role_value()
        return _result(kwargs["profile"].name)

    with patch("agent_service.api.v2.routes.run_bounded_diagnosis", fake_run):
        response = client.post(
            "/api/v2/diagnose",
            json={
                "profile": "k8s-pod-degradation",
                "goal": "pod is crash-looping",
                "session_id": session_id,
            },
            headers={"X-User-ID": "alice"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session_id"] == session_id
    assert body["status"] == "ok"
    assert body["content"] == "diagnosis::k8s-pod-degradation"
    # The route resolved the declared profile and forwarded the goal verbatim.
    assert captured["profile"] is get_profile("k8s-pod-degradation")
    assert captured["goal"] == "pod is crash-looping"
    assert captured["role_at_entry"] is None  # no role bound at the route


def test_diagnose_unknown_profile_fails_closed_422() -> None:
    client = _client()
    _new_session(client)

    async def fake_run(kernel, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("run_bounded_diagnosis must not run for an unknown profile")

    with patch("agent_service.api.v2.routes.run_bounded_diagnosis", fake_run):
        response = client.post(
            "/api/v2/diagnose",
            json={"profile": "reboot-everything", "goal": "g"},
            headers={"X-User-ID": "alice"},
        )

    # Fail closed: an unknown profile is refused, never coerced to a wider runbook.
    assert response.status_code == 422
    assert "unknown diagnosis profile" in response.json()["detail"]


def test_diagnose_budget_limited_surfaces_as_partial() -> None:
    client = _client()
    _new_session(client)

    async def fake_run(kernel, **kwargs):
        return _result(kwargs["profile"].name, budget_limited=True)

    with patch("agent_service.api.v2.routes.run_bounded_diagnosis", fake_run):
        response = client.post(
            "/api/v2/diagnose",
            json={"profile": "observability-alert", "goal": "why the latency spike"},
            headers={"X-User-ID": "alice"},
        )

    assert response.status_code == 200, response.text
    # R-1 fail-closed: a budget-limited partial diagnosis reports status=partial.
    assert response.json()["status"] == "partial"


def test_diagnose_incident_anchor_rides_the_goal_not_a_wire_role() -> None:
    client = _client()
    _new_session(client)
    captured: dict = {}

    async def fake_run(kernel, **kwargs):
        captured.update(kwargs)
        return _result(kwargs["profile"].name)

    with patch("agent_service.api.v2.routes.run_bounded_diagnosis", fake_run):
        response = client.post(
            "/api/v2/diagnose",
            json={
                "profile": "servicenow-incident",
                "goal": "why is the incident breaching SLA",
                "incident_id": "inc-1234",
            },
            headers={"X-User-ID": "alice"},
        )

    assert response.status_code == 200, response.text
    # The anchor is folded into the goal as context; it never becomes a role or a
    # separate wire field (SPEC-073 R-3).
    assert captured["goal"].endswith("(incident inc-1234)")
    assert "agent_role" not in response.json()


def test_diagnose_requires_user_identity() -> None:
    client = _client()
    # No X-User-ID header: the route refuses before any orchestration (401), the
    # same posture as POST /api/v2/chat.
    response = client.post(
        "/api/v2/diagnose",
        json={"profile": "post-deploy-verify", "goal": "verify the rollout"},
    )
    assert response.status_code == 401
