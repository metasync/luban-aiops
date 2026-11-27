"""Clarification answer proxy tests (SPEC-080 R-4).

Covers the gateway ``POST /api/v1/sessions/{id}/clarification/answer`` route —
the sibling to the confirm bridge for the read-only clarification park kind:

* admission rides the **existing** ``chat`` action (no new policy vocabulary) and
  runs **no** approval-tier bridge (the session OWNER answers in-line, OQ-5 — no
  approver, no distinct-human routing, no self-approval concern);
* the answers relay verbatim under the one delegated token and the resumed
  SAME-turn SSE stream passes through untouched;
* upstream 4xx passes through (including the structured ``already_resolved``
  race), transport/5xx map to 502;
* the resumed turn's completion audits via the **closed** ``chat_completed``
  event type (R-8 keeps the enum unchanged); a turn that re-parks stays
  unattributed, exactly as the chat stream tee treats a park.
"""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient

from platform_gateway.app import create_app
from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.schemas.api import IdentityContext
from platform_gateway.services.policy_engine import reset_policy_state

ANSWER_PATH = "/api/v1/sessions/ses-1/clarification/answer"
ANSWER_BODY = {
    "clarification_id": "cl-1",
    "answers": [{"question": "Which cluster?", "selected": ["prod"]}],
}
CLARIFICATION_RESULT_FRAME = {
    "type": "clarification_result",
    "clarification_id": "cl-1",
    "status": "answered",
    "answers": [{"question": "Which cluster?", "selected": ["prod"]}],
    "session_id": "ses-1",
    "request_id": "req-1",
}
# The normalized upstream frame carries ``type`` (not ``event``); the gateway
# tee's ``_extract_message_end`` keys off ``type == "message_end"``.
END_FRAME = {
    "type": "message_end",
    "message": "complete",
    "model": "deepseek-v4-flash",
    "session_id": "ses-1",
}
DELTA_FRAME = {"type": "message_delta", "delta": "partial", "session_id": "ses-1"}
REPARK_FRAME = {
    "type": "clarification_request",
    "clarification_id": "cl-2",
    "questions": [
        {
            "question": "Which namespace?",
            "header": "Namespace",
            "options": [
                {"label": "ops", "description": "Operations"},
                {"label": "dev", "description": "Development"},
            ],
        }
    ],
    "session_id": "ses-1",
}
OPEN_PATCH = "platform_gateway.services.agent_client.open_clarification_answer_stream"
FETCH_PATCH = "platform_gateway.services.agent_client.fetch_pending_confirmation"
ENFORCE_PATCH = "platform_gateway.api.routes.chat.enforce_policy"
EMIT_PATCH = "platform_gateway.services.gateway_service.emit_audit_event"


def _identity(role: str) -> IdentityContext:
    return IdentityContext(
        subject=f"user-{role}",
        username=f"{role}.user",
        roles=[role],
    )


def _sse(frame: dict) -> str:
    return "data: " + json.dumps(frame) + "\n\n"


class ClarificationAnswerRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_policy_state()
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: PlatformGatewaySettings(
            require_auth=True
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_policy_state()

    def _patch_identity(self, role: str):
        identity = _identity(role)

        async def fake_identity(settings, request, request_id):
            return identity

        return patch(
            "platform_gateway.api.routes.chat.resolve_request_identity",
            fake_identity,
        )

    def _patch_delegation(self, token: str | None = "delegated-token"):
        return patch(
            "platform_gateway.api.routes.chat.obtain_delegated_token",
            new=AsyncMock(return_value=token),
        )

    def _patch_open_stream(self, frames: list[dict], calls: list | None = None):
        async def fake_open(
            settings,
            request_id,
            user_id,
            session_id,
            clarification_id,
            answers,
            delegated_token=None,
        ):
            if calls is not None:
                calls.append(
                    {
                        "request_id": request_id,
                        "user_id": user_id,
                        "session_id": session_id,
                        "clarification_id": clarification_id,
                        "answers": answers,
                        "delegated_token": delegated_token,
                    }
                )

            async def _iter():
                for frame in frames:
                    yield _sse(frame)

            return _iter()

        return patch(OPEN_PATCH, fake_open)

    # --- Policy: the reused ``chat`` action, no approval-tier bridge ---

    def test_enforces_the_reused_chat_action_not_confirm(self) -> None:
        """SPEC-080 R-4: admission rides the **existing** ``chat`` action — an
        owner answering their own parked question is admitted at the same trust
        level as the chat turn that parked it. No new policy vocabulary, and
        specifically not the approver-gated ``chat:confirm``."""
        actions: list[str] = []

        def fake_enforce(settings, identity, action, request_id, *args, **kwargs):
            actions.append(action)

        with (
            self._patch_identity("operator"),
            self._patch_delegation(),
            patch(ENFORCE_PATCH, fake_enforce),
            self._patch_open_stream([CLARIFICATION_RESULT_FRAME, END_FRAME]),
        ):
            response = self.client.post(ANSWER_PATH, json=ANSWER_BODY)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(actions, ["chat"])

    def test_no_approval_tier_bridge_runs(self) -> None:
        """SPEC-080 R-4: the owner answers in-line (OQ-5) — there is no approver,
        so the confirm path's parked-state tier lookup never runs. The parked
        clarification is not fetched and no tier/self-approval gate is applied."""
        fetch_mock = MagicMock()
        calls: list = []
        with (
            self._patch_identity("operator"),
            self._patch_delegation(),
            patch(FETCH_PATCH, fetch_mock),
            self._patch_open_stream([CLARIFICATION_RESULT_FRAME, END_FRAME], calls),
        ):
            response = self.client.post(ANSWER_PATH, json=ANSWER_BODY)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(calls), 1)
        fetch_mock.assert_not_called()

    def test_observer_owner_is_admitted_at_chat_level(self) -> None:
        """The ``chat`` action is broadly held (a read-only observer may chat);
        the owner-answers-in-line invariant is enforced downstream by the
        agent-service ownership assertion, not by a gateway approver tier — so
        an observer who owns the session is admitted here (contrast the confirm
        bridge, which an observer is denied)."""
        calls: list = []
        with (
            self._patch_identity("read-only-observer"),
            self._patch_delegation(),
            self._patch_open_stream([CLARIFICATION_RESULT_FRAME, END_FRAME], calls),
        ):
            response = self.client.post(ANSWER_PATH, json=ANSWER_BODY)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(calls), 1)

    # --- Proxying ---

    def test_forwards_identity_clarification_id_answers_and_token(self) -> None:
        calls: list = []
        with (
            self._patch_identity("operator"),
            self._patch_delegation("tok-delegated"),
            self._patch_open_stream([CLARIFICATION_RESULT_FRAME, END_FRAME], calls),
        ):
            self.client.post(ANSWER_PATH, json=ANSWER_BODY)
        call = calls[0]
        self.assertEqual(call["user_id"], "operator.user")
        self.assertEqual(call["session_id"], "ses-1")
        self.assertEqual(call["clarification_id"], "cl-1")
        self.assertEqual(
            call["answers"], [{"question": "Which cluster?", "selected": ["prod"]}]
        )
        self.assertEqual(call["delegated_token"], "tok-delegated")

    def test_other_free_text_is_dropped_when_absent(self) -> None:
        """The passthrough mirror excludes ``other`` when unset, so the relayed
        answer batch stays byte-aligned with the agent-platform model."""
        calls: list = []
        body = {
            "clarification_id": "cl-1",
            "answers": [
                {"question": "Which cluster?", "selected": [], "other": "canary-3"}
            ],
        }
        with (
            self._patch_identity("operator"),
            self._patch_delegation(),
            self._patch_open_stream([CLARIFICATION_RESULT_FRAME, END_FRAME], calls),
        ):
            response = self.client.post(ANSWER_PATH, json=body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            calls[0]["answers"],
            [{"question": "Which cluster?", "selected": [], "other": "canary-3"}],
        )

    def test_sse_passthrough_preserves_frames(self) -> None:
        with (
            self._patch_identity("operator"),
            self._patch_delegation(),
            self._patch_open_stream([CLARIFICATION_RESULT_FRAME, END_FRAME]),
        ):
            response = self.client.post(ANSWER_PATH, json=ANSWER_BODY)
        self.assertEqual(response.status_code, 200)
        self.assertIn("clarification_result", response.text)
        self.assertIn('"answered"', response.text)
        self.assertIn("message_end", response.text)

    # --- Upstream error mapping ---

    def test_upstream_client_error_passes_through(self) -> None:
        request = httpx.Request("POST", "http://agent/api/v2/sessions/ses-1/clarification/answer")

        async def fake_open(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "gone", request=request, response=httpx.Response(410, request=request)
            )

        with (
            self._patch_identity("operator"),
            self._patch_delegation(),
            patch(OPEN_PATCH, fake_open),
        ):
            response = self.client.post(ANSWER_PATH, json=ANSWER_BODY)
        self.assertEqual(response.status_code, 410)

    def test_upstream_already_resolved_body_passes_through_structured(self) -> None:
        """SPEC-031 R-4 posture: a racing second answer's 409 keeps the decider
        and outcome instead of degrading to an opaque error string."""
        request = httpx.Request("POST", "http://agent/api/v2/sessions/ses-1/clarification/answer")
        detail = {
            "reason": "already_resolved",
            "status": "answered",
            "decider_user_id": "operator.user",
            "decision": "answer",
            "decided_at": "2026-11-25T12:00:00Z",
        }

        async def fake_open(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "resolved",
                request=request,
                response=httpx.Response(409, request=request, json={"detail": detail}),
            )

        with (
            self._patch_identity("operator"),
            self._patch_delegation(),
            patch(OPEN_PATCH, fake_open),
        ):
            response = self.client.post(ANSWER_PATH, json=ANSWER_BODY)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], detail)

    def test_upstream_mis_routed_confirmation_409_passes_through(self) -> None:
        """Pointing the answer endpoint at a mutating confirmation park yields a
        409 naming the confirmation kind upstream; it rides through untouched so
        the portal can route the owner to the approval bridge."""
        request = httpx.Request("POST", "http://agent/api/v2/sessions/ses-1/clarification/answer")

        async def fake_open(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "conflict",
                request=request,
                response=httpx.Response(
                    409,
                    request=request,
                    json={"detail": "confirmation pending: this park is a tool "
                          "confirmation; answer it via the confirmation endpoint"},
                ),
            )

        with (
            self._patch_identity("operator"),
            self._patch_delegation(),
            patch(OPEN_PATCH, fake_open),
        ):
            response = self.client.post(ANSWER_PATH, json=ANSWER_BODY)
        self.assertEqual(response.status_code, 409)
        self.assertIn("confirmation pending", response.json()["detail"])

    def test_upstream_unparsable_4xx_degrades_to_fallback_detail(self) -> None:
        request = httpx.Request("POST", "http://agent/api/v2/sessions/ses-1/clarification/answer")

        async def fake_open(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "gone",
                request=request,
                response=httpx.Response(404, request=request, json={}),
            )

        with (
            self._patch_identity("operator"),
            self._patch_delegation(),
            patch(OPEN_PATCH, fake_open),
        ):
            response = self.client.post(ANSWER_PATH, json=ANSWER_BODY)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["detail"],
            "agent service rejected the clarification answer",
        )

    def test_upstream_server_error_maps_to_502(self) -> None:
        request = httpx.Request("POST", "http://agent/api/v2/sessions/ses-1/clarification/answer")

        async def fake_open(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "boom", request=request, response=httpx.Response(500, request=request)
            )

        with (
            self._patch_identity("operator"),
            self._patch_delegation(),
            patch(OPEN_PATCH, fake_open),
        ):
            response = self.client.post(ANSWER_PATH, json=ANSWER_BODY)
        self.assertEqual(response.status_code, 502)

    def test_transport_error_maps_to_502(self) -> None:
        request = httpx.Request("POST", "http://agent/api/v2/sessions/ses-1/clarification/answer")

        async def fake_open(*args, **kwargs):
            raise httpx.ConnectError("unreachable", request=request)

        with (
            self._patch_identity("operator"),
            self._patch_delegation(),
            patch(OPEN_PATCH, fake_open),
        ):
            response = self.client.post(ANSWER_PATH, json=ANSWER_BODY)
        self.assertEqual(response.status_code, 502)

    # --- Request validation (the passthrough model is closed) ---

    def test_empty_answers_rejected_with_422(self) -> None:
        with (
            self._patch_identity("operator"),
            patch(OPEN_PATCH) as upstream,
        ):
            response = self.client.post(
                ANSWER_PATH, json={"clarification_id": "cl-1", "answers": []}
            )
        self.assertEqual(response.status_code, 422)
        upstream.assert_not_called()

    def test_answer_without_question_rejected_with_422(self) -> None:
        with (
            self._patch_identity("operator"),
            patch(OPEN_PATCH) as upstream,
        ):
            response = self.client.post(
                ANSWER_PATH,
                json={"clarification_id": "cl-1", "answers": [{"selected": ["prod"]}]},
            )
        self.assertEqual(response.status_code, 422)
        upstream.assert_not_called()

    def test_extra_field_rejected_with_422(self) -> None:
        """``extra="forbid"``: an unknown field (e.g. a smuggled ``decision``)
        is refused at the edge rather than relayed upstream."""
        with (
            self._patch_identity("operator"),
            patch(OPEN_PATCH) as upstream,
        ):
            response = self.client.post(
                ANSWER_PATH, json={**ANSWER_BODY, "decision": "approve"}
            )
        self.assertEqual(response.status_code, 422)
        upstream.assert_not_called()


class ClarificationAnswerAuditTests(unittest.TestCase):
    """The resumed turn's completion rides the closed ``chat_completed`` type."""

    def setUp(self) -> None:
        reset_policy_state()
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: PlatformGatewaySettings(
            require_auth=True
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_policy_state()

    def _post(self, frames: list[dict], emit_mock):
        identity = _identity("operator")

        async def fake_identity(settings, request, request_id):
            return identity

        async def fake_open(*args, **kwargs):
            async def _iter():
                for frame in frames:
                    yield _sse(frame)

            return _iter()

        def fake_enforce(settings, identity_arg, action, request_id, *a, **k):
            return None

        with (
            patch(
                "platform_gateway.api.routes.chat.resolve_request_identity",
                fake_identity,
            ),
            patch(
                "platform_gateway.api.routes.chat.obtain_delegated_token",
                new=AsyncMock(return_value="tok"),
            ),
            patch(ENFORCE_PATCH, fake_enforce),
            patch(OPEN_PATCH, fake_open),
            patch(EMIT_PATCH, emit_mock),
        ):
            return self.client.post(ANSWER_PATH, json=ANSWER_BODY)

    def _completed_events(self, emit_mock) -> list:
        return [
            call.args[1]
            for call in emit_mock.call_args_list
            if call.args[1]["event_type"] == "chat_completed"
        ]

    def test_message_end_emits_chat_completed_with_serving_model(self) -> None:
        emit_mock = MagicMock()
        response = self._post(
            [CLARIFICATION_RESULT_FRAME, END_FRAME], emit_mock
        )
        self.assertEqual(response.status_code, 200)
        events = self._completed_events(emit_mock)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "chat_completed")
        self.assertEqual(events[0]["session_id"], "ses-1")
        self.assertEqual(events[0]["details"]["model"], "deepseek-v4-flash")

    def test_repark_after_delta_stays_unattributed(self) -> None:
        """SPEC-080 R-8: a resumed turn that re-parks (a fresh
        ``clarification_request``) ends with no ``message_end`` — the turn is not
        complete, so no ``chat_completed`` fires even though a delta flowed,
        exactly as the chat stream tee suppresses a parked turn."""
        emit_mock = MagicMock()
        response = self._post([DELTA_FRAME, REPARK_FRAME], emit_mock)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._completed_events(emit_mock), [])

    def test_delta_without_message_end_emits_fallback_completion(self) -> None:
        """Legacy parity with the chat stream tee: a turn that produced text but
        closed without a ``message_end`` still completed, so it is attributed
        with the fallback model (None here — the route pins no model)."""
        emit_mock = MagicMock()
        response = self._post([DELTA_FRAME], emit_mock)
        self.assertEqual(response.status_code, 200)
        events = self._completed_events(emit_mock)
        self.assertEqual(len(events), 1)
        self.assertIsNone(events[0]["details"]["model"])

    def test_no_audit_without_completion_or_delta(self) -> None:
        emit_mock = MagicMock()
        response = self._post([CLARIFICATION_RESULT_FRAME], emit_mock)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._completed_events(emit_mock), [])


if __name__ == "__main__":
    unittest.main()
