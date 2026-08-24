"""SPEC-024 R-3/R-4: gateway chat model relay and audit enrichment.

The gateway relays the additive ``model`` field verbatim on both chat
surfaces (validation is the runtime's fail-closed job) and enriches the
audit trail: ``chat_started`` carries the requested model, and
``chat_completed`` carries the serving model — from the upstream response
on POST, and from the ``message_end`` tee on the stream.
"""

import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from platform_gateway.app import create_app
from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.schemas.api import IdentityContext

IDENTITY = IdentityContext(
    subject="user-1", username="alice", roles=["operator"]
)


async def _fake_identity(settings, request, request_id):
    return IDENTITY


async def _fake_delegation(settings, subject, bearer_token):
    return None


def _app() -> object:
    app = create_app()
    app.dependency_overrides[get_settings] = (
        lambda: PlatformGatewaySettings(require_auth=True)
    )
    return app


class ChatModelRelayTests(unittest.TestCase):
    def test_post_chat_relays_model_and_echoes_resolution(self) -> None:
        captured: dict = {}

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
            captured["model"] = model
            return {
                "session_id": "ses-1",
                "request_id": request_id,
                "content": "ok",
                "model": model,
            }

        with (
            patch(
                "platform_gateway.api.routes.chat.resolve_request_identity",
                _fake_identity,
            ),
            patch(
                "platform_gateway.api.routes.chat.obtain_delegated_token",
                _fake_delegation,
            ),
            patch("platform_gateway.api.routes.chat.chat", fake_chat),
        ):
            response = TestClient(_app()).post(
                "/api/v1/chat",
                json={"message": "hi", "model": "deepseek"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["model"], "deepseek")
        self.assertEqual(response.json()["model"], "deepseek")

    def test_stream_relays_model_query_param(self) -> None:
        captured: dict = {}

        async def fake_open(*args, **kwargs):
            captured["model"] = args[7] if len(args) > 7 else kwargs.get("model")

            async def _frames():
                yield 'data: {"type": "message_end"}\n\n'

            return _frames()

        with (
            patch(
                "platform_gateway.api.routes.chat.resolve_request_identity",
                _fake_identity,
            ),
            patch(
                "platform_gateway.api.routes.chat.obtain_delegated_token",
                _fake_delegation,
            ),
            patch(
                "platform_gateway.services.agent_client.open_chat_stream",
                fake_open,
            ),
        ):
            response = TestClient(_app()).get(
                "/api/v1/chat/stream",
                params={"message": "hi", "model": "deepseek"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["model"], "deepseek")

    def test_stream_unknown_model_422_passes_through(self) -> None:
        # The runtime fails closed with 422; the gateway must relay the
        # status instead of answering 200 with an empty stream.
        request = httpx.Request("GET", "http://agent:8000/api/v2/chat/stream")

        async def fake_open(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "422", request=request, response=httpx.Response(
                    422, request=request
                )
            )

        with (
            patch(
                "platform_gateway.api.routes.chat.resolve_request_identity",
                _fake_identity,
            ),
            patch(
                "platform_gateway.api.routes.chat.obtain_delegated_token",
                _fake_delegation,
            ),
            patch(
                "platform_gateway.services.agent_client.open_chat_stream",
                fake_open,
            ),
        ):
            response = TestClient(_app()).get(
                "/api/v1/chat/stream",
                params={"message": "hi", "model": "ghost"},
            )

        self.assertEqual(response.status_code, 422)


class StreamAuditEnrichmentTests(unittest.TestCase):
    """The tee audits chat_completed with the serving model (SPEC-024 R-4)."""

    def _run(self, frames, model: str | None = None) -> list:
        emitted: list = []

        async def fake_open(*args, **kwargs):
            async def _frames():
                for frame in frames:
                    yield frame

            return _frames()

        def capture_emit(settings, event):
            emitted.append(event)

        with (
            patch(
                "platform_gateway.api.routes.chat.resolve_request_identity",
                _fake_identity,
            ),
            patch(
                "platform_gateway.api.routes.chat.obtain_delegated_token",
                _fake_delegation,
            ),
            patch(
                "platform_gateway.services.agent_client.open_chat_stream",
                fake_open,
            ),
            patch(
                "platform_gateway.services.gateway_service.emit_audit_event",
                capture_emit,
            ),
        ):
            params: dict = {"message": "hi"}
            if model is not None:
                params["model"] = model
            response = TestClient(_app()).get(
                "/api/v1/chat/stream", params=params
            )
        self.assertEqual(response.status_code, 200)
        return emitted

    def test_message_end_model_reaches_chat_completed_audit(self) -> None:
        emitted = self._run(
            [
                'data: {"type": "message_start", "session_id": "ses-1"}\n\n',
                'data: {"type": "message_end", "session_id": "ses-1", '
                '"model": "deepseek"}\n\n',
            ]
        )
        completed = [e for e in emitted if e.get("event_type") == "chat_completed"]
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["details"]["model"], "deepseek")
        self.assertEqual(completed[0]["session_id"], "ses-1")

    def test_chat_completed_emitted_once_and_only_at_stream_end(self) -> None:
        emitted = self._run(
            [
                'data: {"type": "message_start", "session_id": "ses-1"}\n\n',
                'data: {"type": "message_delta", "delta": "x"}\n\n',
                'data: {"type": "message_end", "session_id": "ses-1"}\n\n',
                'data: {"type": "message_end", "session_id": "ses-1"}\n\n',
            ]
        )
        completed = [e for e in emitted if e.get("event_type") == "chat_completed"]
        # Exactly one completion per turn; a missing model degrades to null.
        self.assertEqual(len(completed), 1)
        self.assertIsNone(completed[0]["details"]["model"])

    def test_aborted_stream_emits_no_completion(self) -> None:
        # No message_end (e.g. a park) means the turn never completed.
        emitted = self._run(
            ['data: {"type": "confirmation_request"}\n\n']
        )
        completed = [e for e in emitted if e.get("event_type") == "chat_completed"]
        self.assertEqual(completed, [])

    def test_delta_only_stream_falls_back_to_requested_model(self) -> None:
        # Live-walkthrough edge: the kernel may close the stream right
        # after the last delta with no message_end. The turn completed,
        # so chat_completed rides the requested model as attribution.
        emitted = self._run(
            [
                'data: {"type": "message_delta", "delta": "ok", '
                '"session_id": "ses-1"}\n\n',
            ],
            model="deepseek",
        )
        completed = [e for e in emitted if e.get("event_type") == "chat_completed"]
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["details"]["model"], "deepseek")
        self.assertEqual(completed[0]["session_id"], "ses-1")

    def test_delta_only_stream_without_request_model_degrades_to_null(self) -> None:
        emitted = self._run(
            ['data: {"type": "message_delta", "delta": "ok"}\n\n']
        )
        completed = [e for e in emitted if e.get("event_type") == "chat_completed"]
        self.assertEqual(len(completed), 1)
        self.assertIsNone(completed[0]["details"]["model"])


class AgentClientModelParamTests(unittest.IsolatedAsyncioTestCase):
    """The client forwards model on both chat surfaces (SPEC-024 R-3)."""

    async def test_open_chat_stream_sends_model_param(self) -> None:
        from platform_gateway.services import agent_client

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

        settings = PlatformGatewaySettings(
            require_auth=True, agent_service_url="http://agent:8000"
        )
        with patch.object(agent_client.httpx, "AsyncClient", FakeClient):
            stream = await agent_client.open_chat_stream(
                settings, "req-1", "alice", "hi", None, model="deepseek"
            )
            frames = [frame async for frame in stream]

        self.assertEqual(recorded["params"]["model"], "deepseek")
        self.assertEqual(frames, ['data: {"type": "message_end"}\n\n'])

    async def test_open_chat_stream_omits_model_when_absent(self) -> None:
        from platform_gateway.services import agent_client

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

        settings = PlatformGatewaySettings(
            require_auth=True, agent_service_url="http://agent:8000"
        )
        with patch.object(agent_client.httpx, "AsyncClient", FakeClient):
            stream = await agent_client.open_chat_stream(
                settings, "req-1", "alice", "hi", None
            )
            _frames = [frame async for frame in stream]

        self.assertNotIn("model", recorded["params"])
