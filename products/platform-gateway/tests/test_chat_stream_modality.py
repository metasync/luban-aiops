"""SPEC-023 R-4: voice-readiness parity for the gateway streaming surface.

``GET /api/v1/chat/stream`` accepts the additive ``input_modality`` query
parameter (``text``|``voice``, default ``text``) mirroring POST
``/api/v1/chat``'s body field: it is recorded on the ``chat_started``
audit/log surface and forwarded upstream as metadata only.
"""

import unittest
from unittest.mock import patch

import httpx
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

        async def fake_chat_stream(
            settings,
            request_id,
            identity,
            message,
            session_id,
            delegated_token=None,
            input_modality="text",
            model=None,
        ):
            captured["input_modality"] = input_modality
            captured["model"] = model

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


class OpenChatStreamClientTests(unittest.IsolatedAsyncioTestCase):
    """The agent client forwards modality as query metadata (SPEC-022 R-2)."""

    def _fake_httpx(self, recorded: dict, response):
        from platform_gateway.services import agent_client

        class FakeRequest:
            pass

        class FakeClient:
            def __init__(self, timeout=None) -> None:
                self.timeout = timeout

            def build_request(self, method, url, params=None, headers=None):
                recorded["params"] = params
                return FakeRequest()

            async def send(self, request, stream=False):
                return response

            async def aclose(self) -> None:
                return None

        return patch.object(agent_client.httpx, "AsyncClient", FakeClient)

    async def test_open_chat_stream_sends_modality_param(self) -> None:
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

        settings = PlatformGatewaySettings(
            require_auth=True, agent_service_url="http://agent:8000"
        )
        with self._fake_httpx(recorded, FakeStreamResponse()):
            frames = [
                frame
                async for frame in await agent_client.open_chat_stream(
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

    async def test_open_chat_stream_raises_upstream_404_eagerly(self) -> None:
        # Regression: an unknown session must surface as an HTTP error
        # before any frame is yielded, never as 200 + empty SSE stream.
        import httpx

        from platform_gateway.services import agent_client

        recorded: dict = {}

        class FakeErrorResponse:
            status_code = 404

            def raise_for_status(self) -> None:
                raise httpx.HTTPStatusError(
                    "404 Not Found",
                    request=httpx.Request("GET", "http://agent:8000"),
                    response=httpx.Response(404),
                )

            async def aread(self) -> None:
                return None

            async def aclose(self) -> None:
                return None

        settings = PlatformGatewaySettings(
            require_auth=True, agent_service_url="http://agent:8000"
        )
        with self._fake_httpx(recorded, FakeErrorResponse()):
            with self.assertRaises(httpx.HTTPStatusError):
                await agent_client.open_chat_stream(
                    settings, "req-1", "alice", "hi", "ses-gone"
                )


class ChatStreamErrorPropagationTests(unittest.TestCase):
    """Upstream failures must surface as HTTP errors, never as 200 + empty SSE.

    Regression: a stale session pointer (deleted session) used to make the
    gateway answer 200 with a zero-frame stream because the upstream 404
    only fired inside the generator after the response had been committed.
    """

    def _run_with_open(self, fake_open):
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
                "platform_gateway.services.agent_client.open_chat_stream",
                fake_open,
            ),
        ):
            return TestClient(app).get(
                "/api/v1/chat/stream", params={"message": "hi"}
            )

    @staticmethod
    def _status_error(status_code: int) -> httpx.HTTPStatusError:
        request = httpx.Request("GET", "http://agent:8000/api/v2/chat/stream")
        response = httpx.Response(status_code, request=request)
        return httpx.HTTPStatusError(
            f"{status_code}", request=request, response=response
        )

    def test_upstream_404_unknown_session_passes_through(self) -> None:
        async def fake_open(*args, **kwargs):
            raise self._status_error(404)

        response = self._run_with_open(fake_open)
        self.assertEqual(response.status_code, 404)

    def test_upstream_409_parked_conflict_passes_through(self) -> None:
        async def fake_open(*args, **kwargs):
            raise self._status_error(409)

        response = self._run_with_open(fake_open)
        self.assertEqual(response.status_code, 409)

    def test_upstream_500_maps_to_502(self) -> None:
        async def fake_open(*args, **kwargs):
            raise self._status_error(500)

        response = self._run_with_open(fake_open)
        self.assertEqual(response.status_code, 502)

    def test_transport_failure_maps_to_502(self) -> None:
        async def fake_open(*args, **kwargs):
            raise httpx.ConnectError("connection refused")

        response = self._run_with_open(fake_open)
        self.assertEqual(response.status_code, 502)
