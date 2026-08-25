"""Chat confirm proxy tests (SPEC-020 R-3).

Covers the gateway confirm route: chat:confirm policy enforcement,
delegated-token forwarding, SSE passthrough, upstream error mapping
(4xx passthrough, transport/5xx to 502), and the confirmation_decided
audit emission tee'd off the confirmation_result frame.
"""

import contextlib
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
FETCH_PATCH = "platform_gateway.services.agent_client.fetch_pending_confirmation"


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

    def _patch_fetch(self, parked: dict | None = None):
        """SPEC-030 R-3: parked-state lookup the tier bridge runs first;
        default None keeps the legacy no-parked-info behavior."""
        return patch(FETCH_PATCH, new=AsyncMock(return_value=parked))

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
            self._patch_fetch(),
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
            self._patch_fetch(),
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
            self._patch_fetch(),
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
            self._patch_fetch(),
            patch(OPEN_PATCH, fake_open),
        ):
            response = self.client.post(CONFIRM_PATH, json=CONFIRM_BODY)
        self.assertEqual(response.status_code, 410)

    def test_upstream_already_resolved_body_passes_through_structured(self) -> None:
        """SPEC-031 R-4: the racing approver's 409 keeps the decider and
        outcome instead of degrading to an opaque error string."""
        request = httpx.Request("POST", "http://agent/api/v2/chat/confirm")
        detail = {
            "reason": "already_resolved",
            "status": "approved",
            "decider_user_id": "luban-approver",
            "decision": "approve",
            "decided_at": "2026-08-25T12:00:00Z",
        }

        async def fake_open(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "resolved",
                request=request,
                response=httpx.Response(
                    409, request=request, json={"detail": detail}
                ),
            )

        with (
            self._patch_identity("operator"),
            self._patch_delegation(),
            self._patch_fetch(),
            patch(OPEN_PATCH, fake_open),
        ):
            response = self.client.post(CONFIRM_PATH, json=CONFIRM_BODY)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], detail)

    def test_upstream_unparsable_4xx_degrades_to_fallback_detail(self) -> None:
        """SPEC-031 R-4: a body without a relayable detail keeps the
        passthrough posture with the bridge's fallback message."""
        request = httpx.Request("POST", "http://agent/api/v2/chat/confirm")

        async def fake_open(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "gone",
                request=request,
                response=httpx.Response(404, request=request, json={}),
            )

        with (
            self._patch_identity("operator"),
            self._patch_delegation(),
            self._patch_fetch(),
            patch(OPEN_PATCH, fake_open),
        ):
            response = self.client.post(CONFIRM_PATH, json=CONFIRM_BODY)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["detail"], "agent service rejected the confirmation"
        )

    def test_upstream_server_error_maps_to_502(self) -> None:
        request = httpx.Request("POST", "http://agent/api/v2/chat/confirm")

        async def fake_open(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "boom", request=request, response=httpx.Response(500, request=request)
            )

        with (
            self._patch_identity("operator"),
            self._patch_delegation(),
            self._patch_fetch(),
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
            self._patch_fetch(),
            patch(OPEN_PATCH, fake_open),
        ):
            response = self.client.post(CONFIRM_PATH, json=CONFIRM_BODY)
        self.assertEqual(response.status_code, 502)

    def test_parked_fetch_failure_fails_closed_with_502(self) -> None:
        """SPEC-030 R-3: without the parked state the tier cannot be
        checked, so the bridge refuses to proxy instead of bypassing."""

        async def fake_fetch(*args, **kwargs):
            raise httpx.ConnectError(
                "unreachable", request=httpx.Request("GET", "http://agent")
            )

        with (
            self._patch_identity("operator"),
            self._patch_delegation(),
            patch(FETCH_PATCH, fake_fetch),
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
            patch(FETCH_PATCH, new=AsyncMock(return_value=None)),
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


class ApprovalTierBridgeTests(unittest.TestCase):
    """SPEC-030 R-3: tiered enforcement on the confirm path.

    The default bundle's tier_2 require_approval rule on tools:mutate
    (deciders: approver, platform-admin; self-approval forbidden) drives
    every case.
    """

    def setUp(self) -> None:
        reset_policy_state()
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: PlatformGatewaySettings(
            require_auth=True
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_policy_state()

    def _parked(self, action: str | None, owner: str = "operator.user") -> dict:
        return {
            "session_id": "ses-1",
            "confirm_id": "cf-1",
            "owner_user_id": owner,
            "action": action,
            "pending_calls": [
                {
                    "call_id": "call-1",
                    "tool_name": "k8s.restart_service",
                    "parameters": {"namespace": "ops"},
                }
            ],
        }

    def _post(
        self,
        role: str,
        parked: dict | None,
        decision: str = "approve",
        emit_mock=None,
    ):
        identity = _identity(role)

        async def fake_identity(settings, request, request_id):
            return identity

        self.calls: list = []

        async def fake_open(
            settings, request_id, user_id, session_id,
            confirm_id, decision_arg, delegated_token=None,
        ):
            self.calls.append(decision_arg)

            async def _iter():
                frame = dict(
                    CONFIRM_RESULT_FRAME,
                    status="approved" if decision_arg == "approve" else "denied",
                )
                yield _sse(frame)

            return _iter()

        patches = [
            patch(
                "platform_gateway.api.routes.chat.resolve_request_identity",
                fake_identity,
            ),
            patch(
                "platform_gateway.api.routes.chat.obtain_delegated_token",
                new=AsyncMock(return_value="tok"),
            ),
            patch(FETCH_PATCH, new=AsyncMock(return_value=parked)),
            patch(OPEN_PATCH, fake_open),
        ]
        if emit_mock is not None:
            patches.append(
                patch(
                    "platform_gateway.services.gateway_service.emit_audit_event",
                    emit_mock,
                )
            )
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            return self.client.post(
                CONFIRM_PATH,
                json={
                    "session_id": "ses-1",
                    "confirm_id": "cf-1",
                    "decision": decision,
                },
            )

    def test_non_decider_approval_blocked_with_structured_403(self) -> None:
        emit_mock = MagicMock()
        response = self._post(
            "operator", self._parked("tools:mutate"), emit_mock=emit_mock
        )
        self.assertEqual(response.status_code, 403)
        detail = response.json()["detail"]
        self.assertEqual(detail["action"], "tools:mutate")
        self.assertEqual(detail["reason"], "not_a_designated_approver")
        self.assertEqual(detail["requirement"], "require_approval")
        # The parked call stays parked: upstream is never called.
        self.assertEqual(self.calls, [])
        # The blocked attempt is audited with the block reason.
        events = [
            call.args[1]
            for call in emit_mock.call_args_list
            if call.args[1]["event_type"] == "confirmation_decided"
        ]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["outcome"], "deny")
        self.assertTrue(events[0]["details"]["blocked"])
        self.assertEqual(
            events[0]["details"]["blocked_reason"], "not_a_designated_approver"
        )
        self.assertEqual(
            events[0]["details"]["approval_rule_id"],
            "require-approval-tools-mutate",
        )
        self.assertEqual(events[0]["details"]["approval_tier"], "tier_2")

    def test_tier2_self_approval_blocked(self) -> None:
        # The approver owns the parked session: tier_2 forbids approving
        # your own request even when you hold a decider role.
        response = self._post(
            "approver", self._parked("tools:mutate", owner="approver.user")
        )
        self.assertEqual(response.status_code, 403)
        detail = response.json()["detail"]
        self.assertEqual(detail["reason"], "self_approval")
        self.assertEqual(detail["requirement"], "require_approval")
        self.assertEqual(self.calls, [])

    def test_tier2_distinct_decider_approves_and_audits_tier(self) -> None:
        emit_mock = MagicMock()
        response = self._post(
            "approver",
            self._parked("tools:mutate", owner="operator.user"),
            emit_mock=emit_mock,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.calls, ["approve"])
        events = [
            call.args[1]
            for call in emit_mock.call_args_list
            if call.args[1]["event_type"] == "confirmation_decided"
        ]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["outcome"], "allow")
        self.assertEqual(
            events[0]["details"]["approval_rule_id"],
            "require-approval-tools-mutate",
        )
        self.assertEqual(events[0]["details"]["approval_tier"], "tier_2")

    def test_tier2_deny_by_requester_still_allowed(self) -> None:
        # The decider check applies to approvals only: the requester can
        # still deny (cancel) their own parked mutating call.
        response = self._post(
            "operator", self._parked("tools:mutate"), decision="deny"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.calls, ["deny"])

    def test_non_mutating_park_keeps_legacy_behavior(self) -> None:
        emit_mock = MagicMock()
        response = self._post(
            "operator", self._parked("tools:invoke"), emit_mock=emit_mock
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.calls, ["approve"])
        events = [
            call.args[1]
            for call in emit_mock.call_args_list
            if call.args[1]["event_type"] == "confirmation_decided"
        ]
        self.assertEqual(len(events), 1)
        self.assertNotIn("approval_rule_id", events[0]["details"])
        self.assertNotIn("approval_tier", events[0]["details"])

    def test_park_without_bridged_action_keeps_legacy_behavior(self) -> None:
        response = self._post("operator", self._parked(None))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.calls, ["approve"])


if __name__ == "__main__":
    unittest.main()
