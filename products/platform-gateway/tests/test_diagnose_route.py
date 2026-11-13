"""SPEC-076 R-7: the gateway ``POST /api/v1/diagnose`` operator-invoked trigger.

The gateway proxy admits the diagnosis at the **existing** ``chat`` action (no new
policy vocabulary — the canonical bundle change stays exactly the SPEC-074
agent-role rule), obtains **one** delegated token for the whole fan-out (R-3),
relays the trigger verbatim to agent-service, and audits the completion by
reusing the closed ``chat_completed`` event type with the runbook ``profile`` in
``details`` (R-6 keeps the enum closed). The route binds no ``agent_role``: the
orchestration frame inside the loop is the only binder.
"""

import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from platform_gateway.app import create_app
from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.schemas.api import IdentityContext

OPERATOR = IdentityContext(subject="user-1", username="alice", roles=["operator"])


async def _fake_identity(settings, request, request_id):
    return OPERATOR


def _app() -> object:
    app = create_app()
    app.dependency_overrides[get_settings] = (
        lambda: PlatformGatewaySettings(require_auth=True)
    )
    return app


class DiagnoseRouteTests(unittest.TestCase):
    def test_operator_trigger_relays_and_returns_the_diagnosis(self) -> None:
        captured: dict = {}
        actions: list[str] = []
        delegations: list = []

        async def fake_diagnose(
            settings,
            request_id,
            user_id,
            profile,
            goal,
            session_id,
            delegated_token=None,
            model=None,
            incident_id=None,
        ):
            captured.update(
                user_id=user_id,
                profile=profile,
                goal=goal,
                session_id=session_id,
                delegated_token=delegated_token,
                model=model,
                incident_id=incident_id,
            )
            return {
                "session_id": session_id or "ses-1",
                "request_id": request_id,
                "content": "diagnosis::k8s-pod-degradation",
                "status": "ok",
                "model": model,
            }

        def fake_enforce(settings, identity, action, request_id, agent_role=None):
            actions.append(action)
            # The trigger admission rides the human axis only. The bound
            # agent_role never crosses the wire to the gateway (SPEC-073 R-3), so
            # it is None here; the read-only posture is enforced in-process by
            # SPEC-073 toolkit narrowing inside the loop, not by a gateway
            # agent-role evaluation on this path (the axis stays ready-but-inert).
            self.assertIsNone(agent_role)

        async def fake_delegation(settings, subject, bearer_token):
            delegations.append(subject)
            return "delegated-token"

        with (
            patch(
                "platform_gateway.api.routes.chat.resolve_request_identity",
                _fake_identity,
            ),
            patch(
                "platform_gateway.api.routes.chat.obtain_delegated_token",
                fake_delegation,
            ),
            patch("platform_gateway.api.routes.chat.enforce_policy", fake_enforce),
            patch("platform_gateway.api.routes.chat.diagnose", fake_diagnose),
        ):
            response = TestClient(_app()).post(
                "/api/v1/diagnose",
                json={
                    "profile": "k8s-pod-degradation",
                    "goal": "pod is crash-looping",
                    "session_id": "ses-1",
                    "incident_id": "inc-9",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["content"], "diagnosis::k8s-pod-degradation"
        )
        # Gated by the reused ``chat`` action — no new policy vocabulary.
        self.assertEqual(actions, ["chat"])
        # Exactly one delegated token for the whole fan-out (R-3).
        self.assertEqual(delegations, ["user-1"])
        # The trigger fields relay verbatim; the one token rides the fan-out.
        self.assertEqual(captured["profile"], "k8s-pod-degradation")
        self.assertEqual(captured["goal"], "pod is crash-looping")
        self.assertEqual(captured["session_id"], "ses-1")
        self.assertEqual(captured["incident_id"], "inc-9")
        self.assertEqual(captured["delegated_token"], "delegated-token")
        self.assertEqual(captured["user_id"], "alice")

    def test_completion_audits_via_the_closed_chat_completed_type(self) -> None:
        emitted: list = []

        async def fake_diagnose(*args, **kwargs):
            return {
                "session_id": "ses-2",
                "request_id": args[1],
                "content": "d",
                "status": "partial",
                "model": None,
            }

        def capture_emit(settings, event):
            emitted.append(event)

        with (
            patch(
                "platform_gateway.api.routes.chat.resolve_request_identity",
                _fake_identity,
            ),
            patch(
                "platform_gateway.api.routes.chat.obtain_delegated_token",
                lambda *a, **k: _none(),
            ),
            patch("platform_gateway.api.routes.chat.diagnose", fake_diagnose),
            patch("platform_gateway.api.routes.chat.emit_audit_event", capture_emit),
        ):
            response = TestClient(_app()).post(
                "/api/v1/diagnose",
                json={"profile": "observability-alert", "goal": "why the spike"},
            )

        self.assertEqual(response.status_code, 200)
        completed = [e for e in emitted if e.get("event_type") == "chat_completed"]
        # The enum stays closed (R-6): the diagnosis reuses chat_completed and
        # carries the runbook profile + budget-limited status in details.
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["details"]["profile"], "observability-alert")
        self.assertEqual(completed[0]["details"]["diagnosis_status"], "partial")
        self.assertEqual(completed[0]["session_id"], "ses-2")

    def test_request_body_carries_no_agent_role_field(self) -> None:
        # SPEC-073 R-3: the role is never a wire field. An attempt to smuggle one
        # is rejected by the strict (extra=forbid) request schema.
        response = TestClient(_app()).post(
            "/api/v1/diagnose",
            json={
                "profile": "post-deploy-verify",
                "goal": "verify",
                "agent_role": "executor",
            },
        )
        self.assertEqual(response.status_code, 422)


async def _none():
    return None


def _upstream_status_error(status_code: int, detail: str) -> httpx.HTTPStatusError:
    """Build the httpx error ``agent_client`` raises on an upstream ``status_code``."""
    request = httpx.Request("POST", "http://agent-service/api/v2/diagnose")
    response = httpx.Response(status_code, request=request, json={"detail": detail})
    return httpx.HTTPStatusError(
        f"upstream {status_code}", request=request, response=response
    )


class DiagnoseUpstreamRelayTests(unittest.TestCase):
    """v0.58.1 regression: the diagnose proxy relays agent-service's status too.

    ``gateway_service.diagnose`` (SPEC-076 R-7) shared the identical
    unhandled-``httpx.HTTPStatusError`` gap as ``remediate``: an upstream 4xx
    escaped as a gateway 500. These tests drive the **real** relay — patching
    only the transport underneath it — so the ``_identity_leg``-mirrored
    4xx-passthrough / 502 mapping is the actual route outcome.
    """

    def _post_with_upstream(self, exc: Exception):
        async def fake_agent_diagnose(*args, **kwargs):
            raise exc

        with (
            patch(
                "platform_gateway.api.routes.chat.resolve_request_identity",
                _fake_identity,
            ),
            patch(
                "platform_gateway.api.routes.chat.obtain_delegated_token",
                lambda *a, **k: _none(),
            ),
            patch(
                "platform_gateway.api.routes.chat.enforce_policy",
                lambda *a, **k: None,
            ),
            patch(
                "platform_gateway.services.gateway_service.agent_client.diagnose",
                fake_agent_diagnose,
            ),
        ):
            return TestClient(_app()).post(
                "/api/v1/diagnose",
                json={"profile": "k8s-pod-degradation", "goal": "why crash-loop"},
            )

    def test_upstream_4xx_is_relayed_with_its_status_and_detail(self) -> None:
        response = self._post_with_upstream(
            _upstream_status_error(422, "bounded diagnosis refused")
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "bounded diagnosis refused")

    def test_upstream_5xx_maps_to_502(self) -> None:
        response = self._post_with_upstream(_upstream_status_error(503, "boom"))
        self.assertEqual(response.status_code, 502)

    def test_transport_failure_maps_to_502(self) -> None:
        response = self._post_with_upstream(httpx.ConnectError("connection refused"))
        self.assertEqual(response.status_code, 502)


if __name__ == "__main__":
    unittest.main()
