"""SPEC-077 R-1/R-3/R-7: the gateway ``POST /api/v1/remediate`` staging trigger.

The gateway proxy admits the operator-initiated diagnose→act staging behind the
**new** ``remediate:stage`` deny-by-default action (R-3) — an ungranted role
(including the deliberately-excluded ``approver``) is refused ``403`` before any
staging turn opens, while ``platform-admin`` and ``operator`` pass. It obtains
**one** delegated token for the turn (the single broker exchange), relays the
request-carried diagnosis verbatim to agent-service ``POST /api/v2/remediate``
over the dedicated ``remediate_response_timeout_seconds`` budget (R-7 / OQ-7), and
audits by reusing the closed ``chat_completed`` event type with the runbook
``profile`` in ``details`` (R-5 / OQ-5 keep the enum closed). The route binds no
``agent_role`` (SPEC-073 R-3): the executor role is bound inside the staging frame,
never on the wire, so ``enforce_policy`` rides the human axis only (OQ-6).
"""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from platform_gateway.app import create_app
from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.schemas.api import IdentityContext
from platform_gateway.services.policy_engine import reset_policy_state

OPERATOR = IdentityContext(subject="user-1", username="alice", roles=["operator"])


async def _fake_identity(settings, request, request_id):
    return OPERATOR


async def _none():
    return None


def _app() -> object:
    app = create_app()
    app.dependency_overrides[get_settings] = (
        lambda: PlatformGatewaySettings(require_auth=True)
    )
    return app


def _identity(role: str) -> IdentityContext:
    return IdentityContext(subject=f"user-{role}", username=f"{role}.user", roles=[role])


class RemediateRouteTests(unittest.TestCase):
    """The proxy relays the trigger verbatim and gates on ``remediate:stage``."""

    def test_operator_trigger_relays_and_returns_the_staged_proposal(self) -> None:
        captured: dict = {}
        actions: list[str] = []
        delegations: list = []

        async def fake_remediate(
            settings,
            request_id,
            user_id,
            profile,
            goal,
            diagnosis,
            session_id,
            delegated_token=None,
            model=None,
        ):
            captured.update(
                user_id=user_id,
                profile=profile,
                goal=goal,
                diagnosis=diagnosis,
                session_id=session_id,
                delegated_token=delegated_token,
                model=model,
            )
            return {
                "session_id": session_id or "ses-1",
                "request_id": request_id,
                "content": "staged::post-deploy-verify",
                "status": "ok",
                "model": model,
            }

        def fake_enforce(settings, identity, action, request_id, agent_role=None):
            actions.append(action)
            # The staging admission rides the human axis only. The bound executor
            # role never crosses the wire to the gateway (SPEC-073 R-3), so it is
            # None here; the live control is in-process toolkit narrowing plus the
            # HITL park, not a gateway agent-role evaluation (the axis stays
            # ready-but-inert, OQ-6).
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
            patch("platform_gateway.api.routes.chat.remediate", fake_remediate),
        ):
            response = TestClient(_app()).post(
                "/api/v1/remediate",
                json={
                    "profile": "post-deploy-verify",
                    "goal": "verify the rollout",
                    "diagnosis": "readiness probe failing on 2/3 pods",
                    "session_id": "ses-1",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"], "staged::post-deploy-verify")
        # Gated by the NEW remediate:stage action (R-3) — not the reused chat one.
        self.assertEqual(actions, ["remediate:stage"])
        # Exactly one delegated token for the staging turn (the single exchange).
        self.assertEqual(delegations, ["user-1"])
        # The trigger fields relay verbatim, including the request-carried
        # diagnosis (OQ-2) — the bridge does not re-run the bounded fan-out.
        self.assertEqual(captured["profile"], "post-deploy-verify")
        self.assertEqual(captured["goal"], "verify the rollout")
        self.assertEqual(captured["diagnosis"], "readiness probe failing on 2/3 pods")
        self.assertEqual(captured["session_id"], "ses-1")
        self.assertEqual(captured["delegated_token"], "delegated-token")
        self.assertEqual(captured["user_id"], "alice")

    def test_completion_audits_via_the_closed_chat_completed_type(self) -> None:
        emitted: list = []

        async def fake_remediate(*args, **kwargs):
            return {
                "session_id": "ses-2",
                "request_id": args[1],
                "content": "s",
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
            patch("platform_gateway.api.routes.chat.enforce_policy", lambda *a, **k: None),
            patch("platform_gateway.api.routes.chat.remediate", fake_remediate),
            patch("platform_gateway.api.routes.chat.emit_audit_event", capture_emit),
        ):
            response = TestClient(_app()).post(
                "/api/v1/remediate",
                json={
                    "profile": "k8s-pod-degradation",
                    "goal": "remediate the crash-loop",
                    "diagnosis": "pod crash-looping on readiness",
                },
            )

        self.assertEqual(response.status_code, 200)
        completed = [e for e in emitted if e.get("event_type") == "chat_completed"]
        # The enum stays closed (R-5/OQ-5): staging reuses chat_completed and
        # carries the runbook profile + staging status in details — no new type.
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["details"]["profile"], "k8s-pod-degradation")
        self.assertEqual(completed[0]["details"]["staging_status"], "partial")
        self.assertEqual(completed[0]["session_id"], "ses-2")

    def test_request_body_carries_no_agent_role_field(self) -> None:
        # SPEC-073 R-3 / R-6: the role is never a wire field. An attempt to smuggle
        # one is rejected by the strict (extra=forbid) request schema.
        response = TestClient(_app()).post(
            "/api/v1/remediate",
            json={
                "profile": "post-deploy-verify",
                "goal": "verify",
                "diagnosis": "d",
                "agent_role": "executor",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_request_carried_diagnosis_is_required(self) -> None:
        # OQ-2 / R-2: the diagnosis is request-carried; an empty one is refused 4xx
        # at the edge (min_length=1) before any staging turn opens.
        response = TestClient(_app()).post(
            "/api/v1/remediate",
            json={"profile": "post-deploy-verify", "goal": "verify", "diagnosis": ""},
        )
        self.assertEqual(response.status_code, 422)


class RemediateGateTests(unittest.TestCase):
    """R-3 HTTP acceptance: the real deny-by-default gate on the deployed bundle.

    Uses the packaged default policy (the synced mirror carrying
    ``allow-operators-remediate-stage``) through the *real* ``enforce_policy`` —
    not a patched one — so the 403 is the actual gateway admission outcome.
    """

    def setUp(self) -> None:
        reset_policy_state()

    def tearDown(self) -> None:
        reset_policy_state()

    def _post(self, role: str):
        calls: list = []

        async def fake_remediate(*args, **kwargs):
            calls.append(args)
            return {
                "session_id": "ses-9",
                "request_id": args[1],
                "content": "staged",
                "status": "ok",
                "model": None,
            }

        identity = _identity(role)

        async def fake_identity(settings, request, request_id):
            return identity

        with (
            patch(
                "platform_gateway.api.routes.chat.resolve_request_identity",
                fake_identity,
            ),
            patch(
                "platform_gateway.api.routes.chat.obtain_delegated_token",
                lambda *a, **k: _none(),
            ),
            patch("platform_gateway.api.routes.chat.remediate", fake_remediate),
        ):
            response = TestClient(_app()).post(
                "/api/v1/remediate",
                json={
                    "profile": "post-deploy-verify",
                    "goal": "verify",
                    "diagnosis": "readiness failing",
                },
            )
        return response, calls

    def test_ungranted_roles_are_denied_403_before_any_staging_turn(self) -> None:
        # approver is deliberately excluded (stager/approver disjointness, SPEC-074
        # / SPEC-030); developer/observer/auditor and an unknown role are denied by
        # default. None may reach the staging proxy.
        for role in [
            "approver", "developer", "read-only-observer", "auditor", "ghost-role",
        ]:
            response, calls = self._post(role)
            self.assertEqual(response.status_code, 403, role)
            self.assertEqual(
                response.json()["detail"]["action"], "remediate:stage", role
            )
            self.assertEqual(calls, [], role)

    def test_operator_and_platform_admin_pass_the_gate(self) -> None:
        for role in ["operator", "platform-admin"]:
            response, calls = self._post(role)
            self.assertEqual(response.status_code, 200, role)
            self.assertEqual(len(calls), 1, role)


class RemediateTimeoutBudgetTests(unittest.TestCase):
    """R-7 / OQ-7: a dedicated proxy budget, code default 300s."""

    def test_dedicated_budget_defaults_to_300s(self) -> None:
        settings = PlatformGatewaySettings()
        # A single executor staging turn is a real provider call, so it gets its
        # own budget rather than chat's 30s; the v0.57.0 live-check finding (a
        # ~140s bounded diagnosis over the 120s diagnose default) is why 300s.
        self.assertEqual(settings.remediate_response_timeout_seconds, 300.0)
        # Distinct from — and longer than — the diagnose code default it carries
        # the finding against.
        self.assertGreater(
            settings.remediate_response_timeout_seconds,
            settings.diagnose_response_timeout_seconds,
        )


if __name__ == "__main__":
    unittest.main()
