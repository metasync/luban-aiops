"""SPEC-077 R-1/R-2: the operator-initiated ``POST /api/v2/remediate`` trigger.

These pin the *route wiring* — profile resolution (fail-closed on an unknown
profile **and** on a diagnosis-only profile), the request-carried ``goal`` +
``diagnosis`` hand-off to the delivered ``stage_remediation(...)`` on the same
delegated token, and the response mapping onto the **existing**
``AgentChatResponse``. The staging turn's ``executor`` role binding + park are
exercised by ``test_orchestration.py``; here ``stage_remediation`` is patched so
the route is tested deterministically without a live executor turn. The route
binds **no** agent-role itself — ``stage_remediation`` is the only binder — and
carries none in the body (R-6, ``extra="forbid"``).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agent_service.app import create_app
from agent_service.runtime_kernel import BlockingReply
from agent_service.services.agent_role import current_agent_role_value
from agent_service.services.runbooks import get_profile

# The two profiles that declare a remediation_shape (stageable) and the two that
# do not (diagnosis-only — they fail closed at the trigger, R-2).
STAGEABLE = ("post-deploy-verify", "k8s-pod-degradation")
DIAGNOSIS_ONLY = ("servicenow-incident", "observability-alert")


def _client() -> TestClient:
    return TestClient(create_app())


def _new_session(client: TestClient) -> str:
    response = client.post("/api/v2/sessions", headers={"X-User-ID": "alice"})
    assert response.status_code == 201, response.text
    return response.json()["session_id"]


@pytest.mark.parametrize("profile_name", STAGEABLE)
def test_remediate_stages_a_stageable_profile_and_returns_the_turn(
    profile_name: str,
) -> None:
    client = _client()
    session_id = _new_session(client)
    captured: dict = {}

    async def fake_stage(kernel, **kwargs):
        captured.update(kwargs)
        # The route itself binds no role before handing off to stage_remediation.
        captured["role_at_entry"] = current_agent_role_value()
        return BlockingReply(f"staged::{kwargs['profile'].name}")

    with patch("agent_service.api.v2.routes.stage_remediation", fake_stage):
        response = client.post(
            "/api/v2/remediate",
            json={
                "profile": profile_name,
                "goal": "roll back the bad deploy",
                "diagnosis": "the rollout spiked 5xx on the new revision",
                "session_id": session_id,
            },
            headers={"X-User-ID": "alice", "Authorization": "Bearer tok-123"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session_id"] == session_id
    assert body["status"] == "ok"
    assert body["content"] == f"staged::{profile_name}"
    # R-6: no agent-role crosses the response wire.
    assert "agent_role" not in body
    # The route resolved the declared profile and forwarded the request-carried
    # goal + diagnosis verbatim, on the same delegated token, for the same human
    # (R-1/OQ-2 request-carried; R-3 identity preservation).
    assert captured["profile"] is get_profile(profile_name)
    assert captured["goal"] == "roll back the bad deploy"
    assert captured["diagnosis"] == "the rollout spiked 5xx on the new revision"
    assert captured["session_id"] == session_id
    assert captured["user_name"] == "alice"
    assert captured["bearer_token"] == "tok-123"
    assert captured["role_at_entry"] is None  # no role bound at the route


def test_remediate_unknown_profile_fails_closed_422() -> None:
    client = _client()
    _new_session(client)

    async def fake_stage(kernel, **kwargs):  # pragma: no cover - must not run
        raise AssertionError(
            "stage_remediation must not run for an unknown profile"
        )

    with patch("agent_service.api.v2.routes.stage_remediation", fake_stage):
        response = client.post(
            "/api/v2/remediate",
            json={"profile": "reboot-everything", "goal": "g", "diagnosis": "d"},
            headers={"X-User-ID": "alice"},
        )

    # Fail closed: an unknown profile is refused, never coerced to a wider runbook.
    assert response.status_code == 422
    assert "unknown diagnosis profile" in response.json()["detail"]


@pytest.mark.parametrize("profile_name", DIAGNOSIS_ONLY)
def test_remediate_diagnosis_only_profile_fails_closed_422(
    profile_name: str,
) -> None:
    client = _client()
    _new_session(client)

    async def fake_stage(kernel, **kwargs):  # pragma: no cover - must not run
        raise AssertionError(
            "stage_remediation must not run for a diagnosis-only profile"
        )

    with patch("agent_service.api.v2.routes.stage_remediation", fake_stage):
        response = client.post(
            "/api/v2/remediate",
            json={"profile": profile_name, "goal": "g", "diagnosis": "d"},
            headers={"X-User-ID": "alice"},
        )

    # R-2 fail closed: a profile with no remediation_shape is refused before any
    # executor turn is opened — the trigger never widens a read-only runbook.
    assert response.status_code == 422
    assert "diagnosis-only" in response.json()["detail"]


def test_remediate_requires_user_identity() -> None:
    client = _client()
    # No X-User-ID header: the route refuses before any staging (401), the same
    # posture as POST /api/v2/diagnose and POST /api/v2/chat.
    response = client.post(
        "/api/v2/remediate",
        json={
            "profile": "post-deploy-verify",
            "goal": "roll back",
            "diagnosis": "bad deploy",
        },
    )
    assert response.status_code == 401


def test_remediate_refuses_a_smuggled_agent_role() -> None:
    # R-6: extra="forbid" makes "carries no agent_role" enforced, not merely
    # documented — a smuggled role (like any unknown field) is refused 4xx rather
    # than silently ignored.
    client = _client()
    session_id = _new_session(client)

    async def fake_stage(kernel, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("stage_remediation must not run for a smuggled role")

    with patch("agent_service.api.v2.routes.stage_remediation", fake_stage):
        response = client.post(
            "/api/v2/remediate",
            json={
                "profile": "post-deploy-verify",
                "goal": "roll back",
                "diagnosis": "bad deploy",
                "session_id": session_id,
                "agent_role": "executor",
            },
            headers={"X-User-ID": "alice"},
        )
    assert response.status_code == 422


def test_remediate_requires_the_request_carried_diagnosis() -> None:
    # OQ-2 request-carried: an absent/empty diagnosis is refused 4xx — there is
    # nothing to stage from, and re-running the bounded fan-out is out of scope.
    client = _client()
    session_id = _new_session(client)

    async def fake_stage(kernel, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("stage_remediation must not run without a diagnosis")

    with patch("agent_service.api.v2.routes.stage_remediation", fake_stage):
        response = client.post(
            "/api/v2/remediate",
            json={
                "profile": "post-deploy-verify",
                "goal": "roll back",
                "diagnosis": "",
                "session_id": session_id,
            },
            headers={"X-User-ID": "alice"},
        )
    assert response.status_code == 422
