"""Route-level policy enforcement tests (SPEC-004 R-3)."""

import hashlib
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from platform_gateway.app import create_app
from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.schemas.api import IdentityContext
from platform_gateway.services.policy_engine import PolicyLoadError, reset_policy_state

SHARED_BUNDLE = (
    Path(__file__).resolve().parents[3]
    / "shared"
    / "shared-contracts"
    / "policies"
    / "policy-default.yaml"
)


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
        ), patch(
            "platform_gateway.api.routes.sessions.resolve_request_identity",
            fake_identity,
        )

    def test_operator_allowed_chat(self) -> None:
        async def fake_chat(
            settings,
            request_id,
            user_id,
            message,
            session_id,
            delegated_token=None,
            input_modality="text",
            model=None,
        ):
            return {"session_id": "ses-1", "content": "ok", "status": "ok"}

        chat_patch, session_patch = self._patch_identity("operator")
        with (
            chat_patch,
            session_patch,
            patch("platform_gateway.api.routes.chat.chat", fake_chat),
        ):
            response = self.client.post("/api/v1/chat", json={"message": "hi"})

        self.assertEqual(response.status_code, 200)

    def test_observer_allowed_chat(self) -> None:
        async def fake_chat(
            settings,
            request_id,
            user_id,
            message,
            session_id,
            delegated_token=None,
            input_modality="text",
            model=None,
        ):
            return {"session_id": "ses-1", "content": "ok", "status": "ok"}

        chat_patch, session_patch = self._patch_identity("read-only-observer")
        with (
            chat_patch,
            session_patch,
            patch("platform_gateway.api.routes.chat.chat", fake_chat),
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
            settings,
            request_id,
            user_id,
            message,
            session_id,
            delegated_token=None,
            input_modality="text",
            model=None,
        ):
            return {"session_id": "ses-1", "content": "ok", "status": "ok"}

        async def fake_create(settings, request_id, user_id):
            return {"session_id": "ses-1"}

        # require_auth=False + no token -> synthetic developer identity.
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: PlatformGatewaySettings(
            require_auth=False, dev_user="demo.operator"
        )
        client = TestClient(app)
        with (
            patch("platform_gateway.api.routes.chat.chat", fake_chat),
            patch("platform_gateway.api.routes.sessions.create_session", fake_create),
        ):
            chat_resp = client.post("/api/v1/chat", json={"message": "hi"})
            session_resp = client.post("/api/v1/sessions", json={})

        self.assertEqual(chat_resp.status_code, 200)
        self.assertEqual(session_resp.status_code, 200)

    def test_exempt_routes_not_policy_checked(self) -> None:
        # Health and runtime routes carry no action and never call enforce_policy.
        with patch(
            "platform_gateway.services.gateway_service.agent_client.health",
            AsyncMock(return_value={"status": "ok"}),
        ):
            live = self.client.get("/health/live")
            ready = self.client.get("/health/ready")

        self.assertEqual(live.status_code, 200)
        self.assertEqual(ready.status_code, 200)
        # SPEC-048 R-1: readiness carries the enforced bundle's fingerprint.
        body = ready.json()
        self.assertEqual(
            body["policy_bundle_sha256"],
            hashlib.sha256(
                SHARED_BUNDLE.read_text(encoding="utf-8").encode("utf-8")
            ).hexdigest(),
        )

    def test_readiness_degrades_when_policy_bundle_missing(self) -> None:
        # Readiness must surface policy load failures, not report ok.
        with patch(
            "platform_gateway.services.gateway_service.load_bundle",
            side_effect=PolicyLoadError("policy bundle not found at '/nope'"),
        ):
            ready = self.client.get("/health/ready")

        body = ready.json()
        self.assertEqual(body["status"], "degraded")
        self.assertIn("policy bundle not found", body["policy_error"])


if __name__ == "__main__":
    unittest.main()
