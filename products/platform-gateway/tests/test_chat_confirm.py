"""Chat confirm proxy tests (SPEC-020 R-3).

Covers the gateway confirm route: chat:confirm policy enforcement,
delegated-token forwarding, SSE passthrough, upstream error mapping
(4xx passthrough, transport/5xx to 502), and the confirmation_decided
audit emission tee'd off the confirmation_result frame.
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

CONFIRM_PATH = "/api/v1/chat/confirm"
CONFIRM_BODY = {
    "session_id": "ses-1",
    "confirm_id": "cf-1",
    "decision": "approve",
}
CONFIRM_RESULT_FRAME = {
    "type": "confirmation_result",
    "confirm_id": "cf-1",
    "status": "approved",
    "pending_calls": [
        {
            "call_id": "call-1",
            "tool_name": "k8s.restart_service",
            "parameters": {"namespace": "ops"},
        }
    ],
    "session_id": "ses-1",
    "request_id": "req-1",
}
OPEN_PATCH = "platform_gateway.services.agent_client.open_chat_confirm_stream"


def _identity(role: str) -> IdentityContext:
    return IdentityContext(
        subject=f"user-{role}",
        username=f"{role}.user",
        roles=[role],
    )


def _sse(frame: dict) -> str:
    return "data: " + json.dumps(frame) + "\n\n"


class ChatConfirmRouteTests(unittest.TestCase):
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
            confirm_id,
            decision,
            delegated_token=None,
        ):
            if calls is not None:
                calls.append(
                    {
                        "request_id": request_id,
                        "user_id": user_id,
                        "session_id": session_id,
                        "confirm_id": confirm_id,
                        "decision": decision,
                        "delegated_token": delegated_token,
                    }
                )

            async def _iter():
                for frame in frames:
                    yield _sse(frame)

            return _iter()

        return patch(OPEN_PATCH, fake_open)

    # --- Policy enforcement ---

    def test_observer_denied_chat_confirm_with_structured_body(self) -> None:
        with self._patch_identity("read-only-observer"):
            response = self.client.post(CONFIRM_PATH, json=CONFIRM_BODY)
        self.assertEqual(response.status_code, 403)
        body = response.json()["detail"]
        self.assertEqual(body["action"], "chat:confirm")

    def test_operator_allowed_chat_confirm(self) -> None:
        calls: list = []
        with (
            self._patch_identity("operator"),
            self._patch_delegation(),
            self._patch_open_stream([CONFIRM_RESULT_FRAME], calls),
        ):
            response = self.client.post(CONFIRM_PATH, json=CONFIRM_BODY)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(calls), 1)

    # --- Proxying ---

    def test_forwards_identity_decision_and_delegated_token(self) -> None:
        calls: list = []
        with (
            self._patch_identity("operator"),
            self._patch_delegation("tok-delegated"),
            self._patch_open_stream([CONFIRM_RESULT_FRAME], calls),
        ):
            self.client.post(CONFIRM_PATH, json=CONFIRM_BODY)
        call = calls[0]
        self.assertEqual(call["user_id"], "operator.user")
        self.assertEqual(call["session_id"], "ses-1")
        self.assertEqual(call["confirm_id"], "cf-1")
        self.assertEqual(call["decision"], "approve")
        self.assertEqual(call["delegated_token"], "tok-delegated")

    def test_sse_passthrough_preserves_frames(self) -> None:
        end_frame = {"event": "message_end", "message": "complete"}
        with (
            self._patch_identity("operator"),
            self._patch_delegation(),
            self._patch_open_stream([CONFIRM_RESULT_FRAME, end_frame]),
        ):
            response = self.client.post(CONFIRM_PATH, json=CONFIRM_BODY)
        self.assertEqual(response.status_code, 200)
        self.assertIn("confirmation_result", response.text)
        self.assertIn('"approved"', response.text)
        self.assertIn("message_end", response.text)

    # --- Upstream error mapping ---

    def test_upstream_client_error_passes_through(self) -> None:
        request = httpx.Request("POST", "http://agent/api/v2/chat/confirm")

        async def fake_open(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "gone", request=request, response=httpx.Response(410, request=request)
            )

        with (
            self._patch_identity("operator"),
            self._patch_delegation(),
            patch(OPEN_PATCH, fake_open),
        ):
            response = self.client.post(CONFIRM_PATH, json=CONFIRM_BODY)
        self.assertEqual(response.status_code, 410)

    def test_upstream_server_error_maps_to_502(self) -> None:
        request = httpx.Request("POST", "http://agent/api/v2/chat/confirm")

        async def fake_open(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "boom", request=request, response=httpx.Response(500, request=request)
            )

        with (
            self._patch_identity("operator"),
            self._patch_delegation(),
            patch(OPEN_PATCH, fake_open),
        ):
            response = self.client.post(CONFIRM_PATH, json=CONFIRM_BODY)
        self.assertEqual(response.status_code, 502)

    def test_transport_error_maps_to_502(self) -> None:
        request = httpx.Request("POST", "http://agent/api/v2/chat/confirm")

        async def fake_open(*args, **kwargs):
            raise httpx.ConnectError("unreachable", request=request)

        with (
            self._patch_identity("operator"),
            self._patch_delegation(),
            patch(OPEN_PATCH, fake_open),
        ):
            response = self.client.post(CONFIRM_PATH, json=CONFIRM_BODY)
        self.assertEqual(response.status_code, 502)

    # --- Request validation ---

    def test_invalid_decision_rejected_with_422(self) -> None:
        with self._patch_identity("operator"):
            response = self.client.post(
                CONFIRM_PATH,
                json={
                    "session_id": "ses-1",
                    "confirm_id": "cf-1",
                    "decision": "maybe",
                },
            )
        self.assertEqual(response.status_code, 422)


class ChatConfirmAuditTests(unittest.TestCase):
    """confirmation_decided is tee'd off the confirmation_result frame."""

    def setUp(self) -> None:
        reset_policy_state()
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: PlatformGatewaySettings(
            require_auth=True
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_policy_state()

    def _post_decision(self, decision: str, frames: list[dict], emit_mock):
        identity = _identity("operator")

        async def fake_identity(settings, request, request_id):
            return identity

        async def fake_open(*args, **kwargs):
            async def _iter():
                for frame in frames:
                    yield _sse(frame)

            return _iter()

        with (
            patch(
                "platform_gateway.api.routes.chat.resolve_request_identity",
                fake_identity,
            ),
            patch(
                "platform_gateway.api.routes.chat.obtain_delegated_token",
                new=AsyncMock(return_value="tok"),
            ),
            patch(OPEN_PATCH, fake_open),
            patch(
                "platform_gateway.services.gateway_service.emit_audit_event",
                emit_mock,
            ),
        ):
            return self.client.post(
                CONFIRM_PATH,
                json={
                    "session_id": "ses-1",
                    "confirm_id": "cf-1",
                    "decision": decision,
                },
            )

    def _confirmation_events(self, emit_mock) -> list:
        """Filter to confirmation_decided: enforce_policy also emits
        policy_decision through the same patched emitter."""
        return [
            call.args[1]
            for call in emit_mock.call_args_list
            if call.args[1]["event_type"] == "confirmation_decided"
        ]

    def test_approve_emits_confirmation_decided_with_tool_names(self) -> None:
        emit_mock = MagicMock()
        response = self._post_decision(
            "approve", [CONFIRM_RESULT_FRAME], emit_mock
        )
        self.assertEqual(response.status_code, 200)
        events = self._confirmation_events(emit_mock)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["event_type"], "confirmation_decided")
        self.assertEqual(event["outcome"], "allow")
        self.assertEqual(event["session_id"], "ses-1")
        self.assertEqual(event["username"], "operator.user")
        self.assertEqual(event["details"]["confirm_id"], "cf-1")
        self.assertEqual(event["details"]["decision"], "approve")
        self.assertEqual(
            event["details"]["tool_names"], ["k8s.restart_service"]
        )

    def test_deny_outcome_is_deny(self) -> None:
        denied_frame = dict(
            CONFIRM_RESULT_FRAME, status="denied", pending_calls=[]
        )
        emit_mock = MagicMock()
        response = self._post_decision("deny", [denied_frame], emit_mock)
        self.assertEqual(response.status_code, 200)
        event = self._confirmation_events(emit_mock)[0]
        self.assertEqual(event["outcome"], "deny")
        self.assertEqual(event["details"]["decision"], "deny")
        self.assertEqual(event["details"]["tool_names"], [])

    def test_no_audit_without_confirmation_result_frame(self) -> None:
        emit_mock = MagicMock()
        response = self._post_decision("approve", [], emit_mock)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._confirmation_events(emit_mock), [])


if __name__ == "__main__":
    unittest.main()
