"""Route-level policy enforcement tests (SPEC-004 R-3)."""

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from api_gateway.app import create_app
from api_gateway.core.config import GatewaySettings, get_settings
from api_gateway.schemas.api import IdentityContext
from api_gateway.services.policy_engine import reset_policy_state


def _identity(role: str) -> IdentityContext:
    return IdentityContext(
        subject=f"user-{role}",
        username=f"{role}.user",
        roles=[role],
    )


class PolicyEnforcementRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_policy_state()
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: GatewaySettings(
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
            "api_gateway.api.routes.chat.resolve_request_identity",
            fake_identity,
        ), patch(
            "api_gateway.api.routes.sessions.resolve_request_identity",
            fake_identity,
        )

    def test_operator_allowed_chat(self) -> None:
        async def fake_chat(
            settings, request_id, user_id, message, session_id, delegated_token=None
        ):
            return {"session_id": "ses-1", "content": "ok", "status": "ok"}

        chat_patch, session_patch = self._patch_identity("operator")
        with (
            chat_patch,
            session_patch,
            patch("api_gateway.api.routes.chat.chat", fake_chat),
        ):
            response = self.client.post("/api/v1/chat", json={"message": "hi"})

        self.assertEqual(response.status_code, 200)

    def test_observer_allowed_chat(self) -> None:
        async def fake_chat(
            settings, request_id, user_id, message, session_id, delegated_token=None
        ):
            return {"session_id": "ses-1", "content": "ok", "status": "ok"}

        chat_patch, session_patch = self._patch_identity("read-only-observer")
        with (
            chat_patch,
            session_patch,
            patch("api_gateway.api.routes.chat.chat", fake_chat),
        ):
            response = self.client.post("/api/v1/chat", json={"message": "hi"})

        self.assertEqual(response.status_code, 200)

    def test_ungranted_role_denied_chat_with_structured_body(self) -> None:
        chat_patch, session_patch = self._patch_identity("auditor")
        with chat_patch, session_patch:
            response = self.client.post("/api/v1/chat", json={"message": "hi"})

        self.assertEqual(response.status_code, 403)
        body = response.json()["detail"]
        self.assertEqual(body["action"], "chat")
        self.assertEqual(body["detail"], "action denied by policy")
        self.assertIn("no matching policy rule", body["reason"])

    def test_ungranted_role_denied_session_create(self) -> None:
        chat_patch, session_patch = self._patch_identity("auditor")
        with chat_patch, session_patch:
            response = self.client.post("/api/v1/sessions", json={})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["action"], "session:create")

    def test_ungranted_role_denied_chat_stream_before_streaming(self) -> None:
        chat_patch, session_patch = self._patch_identity("auditor")
        with chat_patch, session_patch:
            response = self.client.get(
                "/api/v1/chat/stream", params={"message": "hi"}
            )

        # Plain 403 JSON before any SSE response starts.
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["action"], "chat")

    def test_synthetic_developer_allowed_all_actions(self) -> None:
        async def fake_chat(
            settings, request_id, user_id, message, session_id, delegated_token=None
        ):
            return {"session_id": "ses-1", "content": "ok", "status": "ok"}

        async def fake_create(settings, request_id, user_id):
            return {"session_id": "ses-1"}

        # require_auth=False + no token -> synthetic developer identity.
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: GatewaySettings(
            require_auth=False, dev_user="demo.operator"
        )
        client = TestClient(app)
        with (
            patch("api_gateway.api.routes.chat.chat", fake_chat),
            patch("api_gateway.api.routes.sessions.create_session", fake_create),
        ):
            chat_resp = client.post("/api/v1/chat", json={"message": "hi"})
            session_resp = client.post("/api/v1/sessions", json={})

        self.assertEqual(chat_resp.status_code, 200)
        self.assertEqual(session_resp.status_code, 200)

    def test_exempt_routes_not_policy_checked(self) -> None:
        # Health and runtime routes carry no action and never call enforce_policy.
        with patch(
            "api_gateway.services.gateway_service.agent_client.health",
            AsyncMock(return_value={"status": "ok"}),
        ):
            live = self.client.get("/health/live")
            ready = self.client.get("/health/ready")

        self.assertEqual(live.status_code, 200)
        self.assertEqual(ready.status_code, 200)


if __name__ == "__main__":
    unittest.main()
