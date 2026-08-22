"""SPEC-023 R-4: voice-readiness parity for the gateway streaming surface.

``GET /api/v1/chat/stream`` accepts the additive ``input_modality`` query
parameter (``text``|``voice``, default ``text``) mirroring POST
``/api/v1/chat``'s body field: it is recorded on the ``chat_started``
audit/log surface and forwarded upstream as metadata only.
"""

import unittest
from unittest.mock import patch

from fastapi.responses import StreamingResponse
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


class ChatStreamModalityTests(unittest.TestCase):
    def _run(self, params: dict) -> tuple:
        captured: dict = {}

        def fake_chat_stream(
            settings,
            request_id,
            user_id,
            message,
            session_id,
            delegated_token=None,
            input_modality="text",
        ):
            captured["input_modality"] = input_modality

            async def _events():
                yield 'data: {"type": "message_end"}\n\n'

            return StreamingResponse(
                _events(), media_type="text/event-stream"
            )

        app = create_app()
        app.dependency_overrides[get_settings] = (
            lambda: PlatformGatewaySettings(require_auth=True)
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
                "platform_gateway.api.routes.chat.chat_stream",
                fake_chat_stream,
            ),
            self.assertLogs(
                "platform_gateway.api.routes.chat", level="INFO"
            ) as logs,
        ):
            response = TestClient(app).get(
                "/api/v1/chat/stream", params=params
            )
        return response, captured, logs

    def test_default_modality_is_text(self) -> None:
        response, captured, logs = self._run({"message": "hi"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["input_modality"], "text")
        started = [
            line for line in logs.output if "chat_stream_started" in line
        ]
        self.assertTrue(started)
        self.assertIn('"input_modality": "text"', started[0])

    def test_voice_modality_flows_through(self) -> None:
        response, captured, logs = self._run(
            {"message": "hi", "input_modality": "voice"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["input_modality"], "voice")
        started = [
            line for line in logs.output if "chat_stream_started" in line
        ]
        self.assertIn('"input_modality": "voice"', started[0])

    def test_invalid_modality_rejected(self) -> None:
        app = create_app()
        app.dependency_overrides[get_settings] = (
            lambda: PlatformGatewaySettings(require_auth=True)
        )
        # FastAPI rejects the Literal query parameter with 422 before the
        # route body runs, so no identity/delegation patching is needed.
        response = TestClient(app).get(
            "/api/v1/chat/stream",
            params={"message": "hi", "input_modality": "telepathy"},
        )

        self.assertEqual(response.status_code, 422)


class StreamChatClientTests(unittest.IsolatedAsyncioTestCase):
    """The agent client forwards modality as query metadata (SPEC-022 R-2)."""

    async def test_stream_chat_sends_modality_param(self) -> None:
        from platform_gateway.services import agent_client

        recorded: dict = {}

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
                self.timeout = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args) -> None:
                return None

            def stream(self, method, url, params=None, headers=None):
                recorded["params"] = params
                return _FakeStreamContext()

        class _FakeStreamContext:
            async def __aenter__(self):
                return FakeStreamResponse()

            async def __aexit__(self, *args) -> None:
                return None

        settings = PlatformGatewaySettings(
            require_auth=True, agent_service_url="http://agent:8000"
        )
        with patch.object(agent_client.httpx, "AsyncClient", FakeClient):
            frames = [
                frame
                async for frame in agent_client.stream_chat(
                    settings,
                    "req-1",
                    "alice",
                    "hi",
                    None,
                    input_modality="voice",
                )
            ]

        self.assertEqual(frames, ['data: {"type": "message_end"}\n\n'])
        self.assertEqual(recorded["params"]["input_modality"], "voice")
