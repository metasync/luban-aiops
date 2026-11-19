"""SPEC-078 Stage 3 (R-1/R-5): the gateway conversational-remediation entry.

The platform-gateway chat proxy carries the **opt-in** remediation-intent flag on
both surfaces (``POST /api/v1/chat`` body, ``GET /api/v1/chat/stream`` query) and
gates the widening on the **reused** deny-by-default ``remediate:stage`` action
(OQ-3): a token that holds ``chat`` but not ``remediate:stage`` — including the
deliberately-excluded ``approver`` (stager/approver disjointness) — is refused
``403`` before the composition opens, so the turn stays unscoped and the proxy is
never called. A turn **without** the flag calls the proxy with today's exact
arguments (byte-identical unscoped path, R-1 acceptance) and evaluates only
``chat``. The route binds **no** ``agent_role`` (SPEC-073 R-3): the executor role
binds in-process at the staging seam, so ``enforce_policy`` rides the human axis
only. The coupled flag threads verbatim to agent-service over the existing
``remediate_response_timeout_seconds`` budget (no new knob), and ``extra="forbid"``
refuses a smuggled ``agent_role`` at the edge.
"""

import unittest
from unittest.mock import patch

from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from platform_gateway.app import create_app
from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.schemas.api import IdentityContext
from platform_gateway.services import agent_client
from platform_gateway.services.policy_engine import reset_policy_state


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


def _identity_resolver(identity: IdentityContext):
    async def _resolve(settings, request, request_id):
        return identity

    return _resolve


def _narrative(request_id: str = "req-1") -> dict:
    return {
        "session_id": "ses-1",
        "request_id": request_id,
        "content": "diagnosis::post-deploy-verify\n\nstaged::post-deploy-verify",
        "status": "ok",
        "model": None,
    }


class RemediationIntentRelayTests(unittest.TestCase):
    """The proxy carries the flag and gates the widening on ``remediate:stage``.

    ``enforce_policy`` is patched here to observe the *wiring* (which actions the
    route evaluates, and that no ``agent_role`` crosses the wire); the real
    deny-by-default outcome is proven separately in ``RemediationIntentGateTests``.
    """

    def _post(self, role: str, payload: dict):
        actions: list[str] = []
        chat_kwargs: dict = {}

        def fake_enforce(settings, identity, action, request_id, agent_role=None):
            actions.append(action)
            # SPEC-073 R-3: the bound executor role never crosses the wire, so the
            # gate rides the human axis only (ready-but-inert, OQ-6).
            self.assertIsNone(agent_role)

        async def fake_chat(*args, **kwargs):
            # The route threads the base args positionally and the coupled flag as
            # kwargs, so kwargs is exactly the remediation forward (empty when off).
            chat_kwargs.update(kwargs)
            return _narrative(args[1])

        with (
            patch(
                "platform_gateway.api.routes.chat.resolve_request_identity",
                _identity_resolver(_identity(role)),
            ),
            patch(
                "platform_gateway.api.routes.chat.obtain_delegated_token",
                lambda *a, **k: _none(),
            ),
            patch("platform_gateway.api.routes.chat.enforce_policy", fake_enforce),
            patch("platform_gateway.api.routes.chat.chat", fake_chat),
        ):
            response = TestClient(_app()).post("/api/v1/chat", json=payload)
        return response, actions, chat_kwargs

    def test_operator_intent_relays_flag_and_gates_on_remediate_stage(self) -> None:
        response, actions, chat_kwargs = self._post(
            "operator",
            {
                "message": "remediate the crash-loop",
                "remediation_intent": True,
                "remediation_profile": "post-deploy-verify",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"], _narrative()["content"])
        # The baseline chat action plus the reused mutation-adjacent gate (R-5).
        self.assertEqual(actions, ["chat", "remediate:stage"])
        # The coupled flag threads verbatim to agent-service.
        self.assertEqual(
            chat_kwargs,
            {"remediation_intent": True, "remediation_profile": "post-deploy-verify"},
        )

    def test_unscoped_post_turn_relays_no_flag_and_gates_only_chat(self) -> None:
        response, actions, chat_kwargs = self._post("operator", {"message": "hi"})
        self.assertEqual(response.status_code, 200)
        # remediate:stage is NOT evaluated for a normal turn.
        self.assertEqual(actions, ["chat"])
        # Byte-identical: no remediation kwargs threaded to the proxy (R-1).
        self.assertEqual(chat_kwargs, {})

    def test_intent_without_profile_is_refused_422_at_the_edge(self) -> None:
        # The coupled ChatRequest validator fails closed before the handler runs,
        # so neither the gate nor the proxy is reached.
        response = TestClient(_app()).post(
            "/api/v1/chat",
            json={"message": "remediate", "remediation_intent": True},
        )
        self.assertEqual(response.status_code, 422)

    def test_profile_without_intent_is_refused_422_at_the_edge(self) -> None:
        # A profile with no intent flag would silently widen a normal turn — the
        # exact accident the explicit affordance (OQ-2) exists to prevent.
        response = TestClient(_app()).post(
            "/api/v1/chat",
            json={"message": "hi", "remediation_profile": "post-deploy-verify"},
        )
        self.assertEqual(response.status_code, 422)

    def test_smuggled_agent_role_is_refused_422(self) -> None:
        # SPEC-073 R-3 / R-5: the role is never a wire field. extra="forbid"
        # rejects an attempt to smuggle one before the handler runs.
        response = TestClient(_app()).post(
            "/api/v1/chat",
            json={
                "message": "remediate",
                "remediation_intent": True,
                "remediation_profile": "post-deploy-verify",
                "agent_role": "executor",
            },
        )
        self.assertEqual(response.status_code, 422)

    def _get_stream(self, role: str, params: dict):
        actions: list[str] = []
        captured: dict = {}

        def fake_enforce(settings, identity, action, request_id, agent_role=None):
            actions.append(action)
            self.assertIsNone(agent_role)

        async def fake_open(*args, **kwargs):
            # gateway_service.chat_stream forwards positionally; args[8]/args[9]
            # are the coupled remediation flag/profile.
            captured["remediation_intent"] = (
                args[8] if len(args) > 8 else kwargs.get("remediation_intent")
            )
            captured["remediation_profile"] = (
                args[9] if len(args) > 9 else kwargs.get("remediation_profile")
            )

            async def _frames():
                yield 'data: {"type": "message_end"}\n\n'

            return _frames()

        with (
            patch(
                "platform_gateway.api.routes.chat.resolve_request_identity",
                _identity_resolver(_identity(role)),
            ),
            patch(
                "platform_gateway.api.routes.chat.obtain_delegated_token",
                lambda *a, **k: _none(),
            ),
            patch("platform_gateway.api.routes.chat.enforce_policy", fake_enforce),
            patch(
                "platform_gateway.services.agent_client.open_chat_stream",
                fake_open,
            ),
        ):
            response = TestClient(_app()).get("/api/v1/chat/stream", params=params)
        return response, actions, captured

    def test_stream_intent_relays_flag_and_gates_on_remediate_stage(self) -> None:
        response, actions, captured = self._get_stream(
            "operator",
            {
                "message": "remediate the crash-loop",
                "remediation_intent": "true",
                "remediation_profile": "post-deploy-verify",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(actions, ["chat", "remediate:stage"])
        self.assertTrue(captured["remediation_intent"])
        self.assertEqual(captured["remediation_profile"], "post-deploy-verify")

    def test_stream_unscoped_relays_no_flag_and_gates_only_chat(self) -> None:
        response, actions, captured = self._get_stream(
            "operator", {"message": "hi"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(actions, ["chat"])
        self.assertFalse(captured["remediation_intent"])
        self.assertIsNone(captured["remediation_profile"])

    def test_stream_intent_without_profile_is_refused_422_at_the_edge(self) -> None:
        # The streaming surface has no pydantic body, so the route guards the wire
        # shape itself and fails closed before identity/policy/proxy.
        response = TestClient(_app()).get(
            "/api/v1/chat/stream",
            params={"message": "remediate", "remediation_intent": "true"},
        )
        self.assertEqual(response.status_code, 422)


class RemediationIntentGateTests(unittest.TestCase):
    """R-5 HTTP acceptance: the real deny-by-default gate on the deployed bundle.

    Uses the packaged default policy (carrying ``allow-operators-remediate-stage``)
    through the *real* ``enforce_policy`` — not a patched one — so the ``403`` is
    the actual gateway admission outcome for the reused action.
    """

    def setUp(self) -> None:
        reset_policy_state()

    def tearDown(self) -> None:
        reset_policy_state()

    def _post(self, role: str):
        calls: list = []

        async def fake_chat(*args, **kwargs):
            calls.append(kwargs)
            return _narrative(args[1])

        with (
            patch(
                "platform_gateway.api.routes.chat.resolve_request_identity",
                _identity_resolver(_identity(role)),
            ),
            patch(
                "platform_gateway.api.routes.chat.obtain_delegated_token",
                lambda *a, **k: _none(),
            ),
            patch("platform_gateway.api.routes.chat.chat", fake_chat),
        ):
            response = TestClient(_app()).post(
                "/api/v1/chat",
                json={
                    "message": "remediate the crash-loop",
                    "remediation_intent": True,
                    "remediation_profile": "post-deploy-verify",
                },
            )
        return response, calls

    def test_chat_capable_roles_without_stage_are_denied_403(self) -> None:
        # approver/developer/read-only-observer hold ``chat`` but NOT the reused
        # deny-by-default ``remediate:stage``, so the widening is refused on that
        # action before the composition opens. ``approver`` is deliberately
        # excluded so the stager and the distinct-human approver stay disjoint
        # (SPEC-074 / SPEC-030). None may reach the proxy.
        for role in ["approver", "developer", "read-only-observer"]:
            response, calls = self._post(role)
            self.assertEqual(response.status_code, 403, role)
            self.assertEqual(
                response.json()["detail"]["action"], "remediate:stage", role
            )
            self.assertEqual(calls, [], role)

    def test_roles_without_chat_are_denied_403_on_the_baseline(self) -> None:
        # auditor and an unknown role hold neither ``chat`` nor ``remediate:stage``;
        # the baseline chat gate refuses them first. Either way, no composition.
        for role in ["auditor", "ghost-role"]:
            response, calls = self._post(role)
            self.assertEqual(response.status_code, 403, role)
            self.assertEqual(response.json()["detail"]["action"], "chat", role)
            self.assertEqual(calls, [], role)

    def test_operator_and_platform_admin_pass_and_relay_the_flag(self) -> None:
        for role in ["operator", "platform-admin"]:
            response, calls = self._post(role)
            self.assertEqual(response.status_code, 200, role)
            self.assertEqual(
                calls,
                [
                    {
                        "remediation_intent": True,
                        "remediation_profile": "post-deploy-verify",
                    }
                ],
                role,
            )

    def test_unscoped_turn_is_not_gated_on_stage_for_any_chat_role(self) -> None:
        # Without the flag the reused gate never fires: a role that only holds
        # ``chat`` (observer) still chats, proving the widening is opt-in and the
        # unscoped path is unchanged for every chat-capable role.
        for role in ["read-only-observer", "approver", "developer"]:
            calls: list = []

            async def fake_chat(*args, **kwargs):
                calls.append(kwargs)
                return _narrative(args[1])

            with (
                patch(
                    "platform_gateway.api.routes.chat.resolve_request_identity",
                    _identity_resolver(_identity(role)),
                ),
                patch(
                    "platform_gateway.api.routes.chat.obtain_delegated_token",
                    lambda *a, **k: _none(),
                ),
                patch("platform_gateway.api.routes.chat.chat", fake_chat),
            ):
                response = TestClient(_app()).post(
                    "/api/v1/chat", json={"message": "hi"}
                )
            self.assertEqual(response.status_code, 200, role)
            self.assertEqual(calls, [{}], role)

    def test_stream_denies_ungranted_role_403_before_the_composition(self) -> None:
        calls: list = []

        async def fake_chat_stream(*args, **kwargs):
            calls.append(
                {
                    k: kwargs[k]
                    for k in ("remediation_intent", "remediation_profile")
                    if k in kwargs
                }
            )

            async def _frames():
                yield 'data: {"type": "message_end"}\n\n'

            return StreamingResponse(_frames(), media_type="text/event-stream")

        with (
            patch(
                "platform_gateway.api.routes.chat.resolve_request_identity",
                _identity_resolver(_identity("approver")),
            ),
            patch(
                "platform_gateway.api.routes.chat.obtain_delegated_token",
                lambda *a, **k: _none(),
            ),
            patch(
                "platform_gateway.api.routes.chat.chat_stream",
                fake_chat_stream,
            ),
        ):
            response = TestClient(_app()).get(
                "/api/v1/chat/stream",
                params={
                    "message": "remediate",
                    "remediation_intent": "true",
                    "remediation_profile": "post-deploy-verify",
                },
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["action"], "remediate:stage")
        self.assertEqual(calls, [])


class AgentClientRemediationWireTests(unittest.IsolatedAsyncioTestCase):
    """The client threads the flag onto the wire only when intent is set (R-1).

    Proves the unscoped payload/query is byte-identical and that a
    remediation-intent turn rides the existing ``remediate_response_timeout_seconds``
    budget (no new knob, plan rollout).
    """

    def _settings(self) -> PlatformGatewaySettings:
        return PlatformGatewaySettings(
            require_auth=True, agent_service_url="http://agent:8000"
        )

    async def test_chat_payload_omits_flag_and_rides_chat_budget_when_unscoped(
        self,
    ) -> None:
        recorded: dict = {}

        class FakeResponse:
            status_code = 200

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"session_id": "ses-1", "content": "ok"}

        class FakeClient:
            def __init__(self, timeout=None) -> None:
                recorded["timeout"] = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc) -> None:
                return None

            async def post(self, url, json=None, headers=None):
                recorded["json"] = json
                return FakeResponse()

        settings = self._settings()
        with patch.object(agent_client.httpx, "AsyncClient", FakeClient):
            await agent_client.chat(settings, "req-1", "alice", "hi", None)

        self.assertNotIn("remediation_intent", recorded["json"])
        self.assertNotIn("remediation_profile", recorded["json"])
        self.assertEqual(
            recorded["timeout"].read, settings.chat_response_timeout_seconds
        )

    async def test_chat_payload_carries_flag_and_staging_budget_when_intent(
        self,
    ) -> None:
        recorded: dict = {}

        class FakeResponse:
            status_code = 200

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"session_id": "ses-1", "content": "staged"}

        class FakeClient:
            def __init__(self, timeout=None) -> None:
                recorded["timeout"] = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc) -> None:
                return None

            async def post(self, url, json=None, headers=None):
                recorded["json"] = json
                return FakeResponse()

        settings = self._settings()
        with patch.object(agent_client.httpx, "AsyncClient", FakeClient):
            await agent_client.chat(
                settings,
                "req-1",
                "alice",
                "remediate the crash-loop",
                None,
                remediation_intent=True,
                remediation_profile="post-deploy-verify",
            )

        self.assertTrue(recorded["json"]["remediation_intent"])
        self.assertEqual(
            recorded["json"]["remediation_profile"], "post-deploy-verify"
        )
        self.assertEqual(
            recorded["timeout"].read, settings.remediate_response_timeout_seconds
        )

    async def _open_stream(self, **kwargs) -> dict:
        recorded: dict = {}

        class FakeRequest:
            pass

        class FakeStreamResponse:
            status_code = 200

            def raise_for_status(self) -> None:
                return None

            async def aiter_lines(self):
                yield 'data: {"type": "message_end"}'

            async def aclose(self) -> None:
                return None

        class FakeClient:
            def __init__(self, timeout=None) -> None:
                pass

            def build_request(self, method, url, params=None, headers=None):
                recorded["params"] = params
                return FakeRequest()

            async def send(self, request, stream=False):
                return FakeStreamResponse()

            async def aclose(self) -> None:
                return None

        with patch.object(agent_client.httpx, "AsyncClient", FakeClient):
            stream = await agent_client.open_chat_stream(
                self._settings(), "req-1", "alice", "hi", None, **kwargs
            )
            _frames = [frame async for frame in stream]
        return recorded

    async def test_stream_query_omits_flag_when_unscoped(self) -> None:
        recorded = await self._open_stream()
        self.assertNotIn("remediation_intent", recorded["params"])
        self.assertNotIn("remediation_profile", recorded["params"])

    async def test_stream_query_carries_flag_when_intent(self) -> None:
        recorded = await self._open_stream(
            remediation_intent=True, remediation_profile="post-deploy-verify"
        )
        self.assertEqual(recorded["params"]["remediation_intent"], "true")
        self.assertEqual(
            recorded["params"]["remediation_profile"], "post-deploy-verify"
        )


if __name__ == "__main__":
    unittest.main()
