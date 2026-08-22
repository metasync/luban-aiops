"""Session workspace proxy tests (SPEC-022 R-1) and voice-readiness (R-2).

Covers the gateway-side gates for the session lifecycle surface:
session:list/session:delete policy enforcement, upstream payload
passthrough, error mapping (4xx passthrough, transport/5xx to 502),
the session_deleted audit emission, and the R-2 invariant that input
modality is metadata only — never decision-bearing.
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient

from platform_gateway.app import create_app
from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.schemas.api import IdentityContext
from platform_gateway.services.policy_engine import reset_policy_state

CHAT_PATH = "/api/v1/chat"
SESSIONS_PATH = "/api/v1/sessions"
LIST_PATCH = "platform_gateway.services.gateway_service.agent_client.list_sessions"
GET_PATCH = "platform_gateway.services.gateway_service.agent_client.get_session"
DELETE_PATCH = "platform_gateway.services.gateway_service.agent_client.delete_session"
CHAT_PATCH = "platform_gateway.services.gateway_service.agent_client.chat"

LIST_PAYLOAD = {
    "sessions": [
        {
            "session_id": "ses-1",
            "title": "check the pods",
            "created_at": "2026-08-22T10:00:00Z",
            "last_active_at": "2026-08-22T10:05:00Z",
            "pending_confirmation": False,
        }
    ]
}
DELETE_PAYLOAD = {"session_id": "ses-1", "deleted": True}
GET_PAYLOAD = {
    "session_id": "ses-1",
    "title": "check the pods",
    "created_at": "2026-08-22T10:00:00Z",
    "last_active_at": "2026-08-22T10:05:00Z",
    "pending_confirmation": False,
    "transcript_available": True,
    "transcript": [
        {"role": "user", "content": "check the pods"},
        {"role": "assistant", "content": "all pods running."},
    ],
}


def _identity(role: str) -> IdentityContext:
    return IdentityContext(
        subject=f"user-{role}",
        username=f"{role}.user",
        roles=[role],
    )


def _status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("DELETE", "http://agent-service/api/v2/sessions/ses-1")
    return httpx.HTTPStatusError(
        "upstream error", request=request, response=httpx.Response(status_code)
    )


class SessionWorkspaceProxyBase(unittest.TestCase):
    def setUp(self) -> None:
        reset_policy_state()
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: PlatformGatewaySettings(
            require_auth=True
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_policy_state()

    def _patch_identity(self, role: str, route_module: str = "sessions"):
        identity = _identity(role)

        async def fake_identity(settings, request, request_id):
            return identity

        return patch(
            f"platform_gateway.api.routes.{route_module}.resolve_request_identity",
            fake_identity,
        )

    def _patch_delegation(self, token: str | None = "delegated-token"):
        return patch(
            "platform_gateway.api.routes.chat.obtain_delegated_token",
            new=AsyncMock(return_value=token),
        )


class ListSessionsProxyTests(SessionWorkspaceProxyBase):
    def test_operator_lists_own_sessions_via_upstream(self) -> None:
        upstream = AsyncMock(return_value=LIST_PAYLOAD)
        with (
            self._patch_identity("operator"),
            patch(LIST_PATCH, upstream),
        ):
            response = self.client.get(SESSIONS_PATH)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), LIST_PAYLOAD)
        # The proxy forwards the caller's identity; scoping is server-side.
        _, args, kwargs = upstream.mock_calls[0]
        self.assertEqual(args[2], "operator.user")

    def test_ungranted_role_denied_before_upstream(self) -> None:
        upstream = AsyncMock(return_value=LIST_PAYLOAD)
        with (
            self._patch_identity("auditor"),
            patch(LIST_PATCH, upstream),
        ):
            response = self.client.get(SESSIONS_PATH)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["action"], "session:list")
        upstream.assert_not_called()

    def test_upstream_4xx_passes_through(self) -> None:
        # Same posture as the get/delete proxies: upstream client errors
        # reach the caller unchanged instead of surfacing as a 502.
        upstream = AsyncMock(side_effect=_status_error(400))
        with (
            self._patch_identity("operator"),
            patch(LIST_PATCH, upstream),
        ):
            response = self.client.get(SESSIONS_PATH)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"], "agent service rejected the session list"
        )

    def test_upstream_status_error_maps_to_502(self) -> None:
        upstream = AsyncMock(side_effect=_status_error(500))
        with (
            self._patch_identity("operator"),
            patch(LIST_PATCH, upstream),
        ):
            response = self.client.get(SESSIONS_PATH)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"], "agent service session list failed"
        )

    def test_transport_failure_maps_to_502(self) -> None:
        upstream = AsyncMock(side_effect=httpx.ConnectError("boom"))
        with (
            self._patch_identity("operator"),
            patch(LIST_PATCH, upstream),
        ):
            response = self.client.get(SESSIONS_PATH)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "agent service unavailable")


class GetSessionProxyTests(SessionWorkspaceProxyBase):
    def test_operator_fetches_session_detail(self) -> None:
        upstream = AsyncMock(return_value=GET_PAYLOAD)
        with (
            self._patch_identity("operator"),
            patch(GET_PATCH, upstream),
        ):
            response = self.client.get(f"{SESSIONS_PATH}/ses-1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), GET_PAYLOAD)

    def test_upstream_404_passes_through(self) -> None:
        # The anti-enumeration 404 for unknown/foreign sessions must reach
        # the caller unchanged, not surface as a gateway 500.
        upstream = AsyncMock(side_effect=_status_error(404))
        with (
            self._patch_identity("operator"),
            patch(GET_PATCH, upstream),
        ):
            response = self.client.get(f"{SESSIONS_PATH}/ses-1")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["detail"], "agent service rejected the session fetch"
        )

    def test_upstream_5xx_maps_to_502(self) -> None:
        upstream = AsyncMock(side_effect=_status_error(500))
        with (
            self._patch_identity("operator"),
            patch(GET_PATCH, upstream),
        ):
            response = self.client.get(f"{SESSIONS_PATH}/ses-1")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"], "agent service session fetch failed"
        )

    def test_transport_failure_maps_to_502(self) -> None:
        upstream = AsyncMock(side_effect=httpx.ConnectError("boom"))
        with (
            self._patch_identity("operator"),
            patch(GET_PATCH, upstream),
        ):
            response = self.client.get(f"{SESSIONS_PATH}/ses-1")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "agent service unavailable")


class DeleteSessionProxyTests(SessionWorkspaceProxyBase):
    def test_operator_deletes_and_audit_event_emitted(self) -> None:
        upstream = AsyncMock(return_value=DELETE_PAYLOAD)
        emit_mock = MagicMock()
        with (
            self._patch_identity("operator"),
            patch(DELETE_PATCH, upstream),
            patch(
                "platform_gateway.api.routes.sessions.emit_audit_event", emit_mock
            ),
        ):
            response = self.client.delete(f"{SESSIONS_PATH}/ses-1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), DELETE_PAYLOAD)
        # The durable session_deleted audit event rides the delete surface.
        emit_mock.assert_called_once()
        event = emit_mock.call_args[0][1]
        self.assertEqual(event["event_type"], "session_deleted")
        self.assertEqual(event["session_id"], "ses-1")
        self.assertEqual(event["outcome"], "success")

    def test_upstream_404_passes_through(self) -> None:
        # Unknown and foreign sessions are indistinguishable upstream; the
        # proxy preserves the anti-enumeration posture unchanged.
        upstream = AsyncMock(side_effect=_status_error(404))
        with (
            self._patch_identity("operator"),
            patch(DELETE_PATCH, upstream),
        ):
            response = self.client.delete(f"{SESSIONS_PATH}/ses-1")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["detail"], "agent service rejected the session delete"
        )

    def test_upstream_409_parked_passes_through(self) -> None:
        upstream = AsyncMock(side_effect=_status_error(409))
        with (
            self._patch_identity("operator"),
            patch(DELETE_PATCH, upstream),
        ):
            response = self.client.delete(f"{SESSIONS_PATH}/ses-1")
        self.assertEqual(response.status_code, 409)

    def test_upstream_5xx_maps_to_502(self) -> None:
        upstream = AsyncMock(side_effect=_status_error(500))
        with (
            self._patch_identity("operator"),
            patch(DELETE_PATCH, upstream),
        ):
            response = self.client.delete(f"{SESSIONS_PATH}/ses-1")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"], "agent service session delete failed"
        )

    def test_transport_failure_maps_to_502(self) -> None:
        upstream = AsyncMock(side_effect=httpx.ConnectError("boom"))
        with (
            self._patch_identity("operator"),
            patch(DELETE_PATCH, upstream),
        ):
            response = self.client.delete(f"{SESSIONS_PATH}/ses-1")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "agent service unavailable")

    def test_ungranted_role_denied_before_upstream(self) -> None:
        upstream = AsyncMock(return_value=DELETE_PAYLOAD)
        with (
            self._patch_identity("auditor"),
            patch(DELETE_PATCH, upstream),
        ):
            response = self.client.delete(f"{SESSIONS_PATH}/ses-1")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["action"], "session:delete")
        upstream.assert_not_called()

    def test_failed_delete_emits_no_audit_event(self) -> None:
        upstream = AsyncMock(side_effect=_status_error(404))
        emit_mock = MagicMock()
        with (
            self._patch_identity("operator"),
            patch(DELETE_PATCH, upstream),
            patch(
                "platform_gateway.api.routes.sessions.emit_audit_event", emit_mock
            ),
        ):
            self.client.delete(f"{SESSIONS_PATH}/ses-1")
        emit_mock.assert_not_called()


class VoiceReadinessInvariantTests(SessionWorkspaceProxyBase):
    """R-2 Invariant I: modality is metadata only.

    The policy decision, the enforced action, and every downstream effect
    of a chat request must be identical for text and voice; modality may
    only appear in logs and audit details.
    """

    def _chat(self, modality: str | None, upstream, emit_mock):
        body = {"message": "check the pods"}
        if modality is not None:
            body["input_modality"] = modality
        with (
            self._patch_identity("operator", route_module="chat"),
            self._patch_delegation(),
            patch(CHAT_PATCH, upstream),
            patch("platform_gateway.api.routes.chat.emit_audit_event", emit_mock),
        ):
            return self.client.post(CHAT_PATH, json=body)

    def test_text_and_voice_share_identical_policy_decision(self) -> None:
        chat_payload = {"session_id": "ses-1", "reply": "ok"}
        results = []
        for modality in ("text", "voice"):
            upstream = AsyncMock(return_value=chat_payload)
            emit_mock = MagicMock()
            response = self._chat(modality, upstream, emit_mock)
            # Same role, same action, same outcome — modality never gates.
            self.assertEqual(response.status_code, 200, modality)
            _, args, _ = upstream.mock_calls[0]
            # gateway_service.chat forwards positionally; modality is last.
            self.assertEqual(args[6], modality)
            event = emit_mock.call_args[0][1]
            self.assertEqual(event["details"]["input_modality"], modality)
            results.append(response.json())
        self.assertEqual(results[0], results[1])

    def test_modality_defaults_to_text_when_absent(self) -> None:
        upstream = AsyncMock(return_value={"session_id": "ses-1", "reply": "ok"})
        emit_mock = MagicMock()
        response = self._chat(None, upstream, emit_mock)
        self.assertEqual(response.status_code, 200)
        _, args, _ = upstream.mock_calls[0]
        self.assertEqual(args[6], "text")
        event = emit_mock.call_args[0][1]
        self.assertEqual(event["details"]["input_modality"], "text")

    def test_unknown_modality_rejected_before_policy(self) -> None:
        upstream = AsyncMock(return_value={"session_id": "ses-1", "reply": "ok"})
        with (
            self._patch_identity("operator", route_module="chat"),
            self._patch_delegation(),
            patch(CHAT_PATCH, upstream),
        ):
            response = self.client.post(
                CHAT_PATH, json={"message": "hi", "input_modality": "audio"}
            )
        self.assertEqual(response.status_code, 422)
        upstream.assert_not_called()


if __name__ == "__main__":
    unittest.main()
