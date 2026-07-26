import unittest

from fastapi import HTTPException

from api_gateway.services.agent_backends import (
    AgentBackendContext,
    NativeAgentServiceBackend,
    TransitionalAgentServiceBackend,
    build_native_probe_headers,
    build_service_headers,
    resolve_agent_backend,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if not self.is_success:
            raise AssertionError(f"HTTP error {self.status_code}")


class FakeClient:
    def __init__(self, responses: dict[str, FakeResponse]) -> None:
        self.responses = responses
        self.gets: list[dict] = []

    async def get(self, url: str, headers: dict | None = None, params: dict | None = None):
        self.gets.append(
            {
                "url": url,
                "headers": headers or {},
                "params": params or {},
            }
        )
        response = self.responses.get(url)
        if response is None:
            raise AssertionError(f"Unexpected GET {url}")
        return response


class RecordingClient(FakeClient):
    def __init__(self, responses: dict[str, FakeResponse]) -> None:
        super().__init__(responses)
        self.posts: list[dict] = []

    async def post(self, url: str, json: dict | None = None, headers: dict | None = None):
        self.posts.append(
            {
                "url": url,
                "json": json or {},
                "headers": headers or {},
            }
        )
        response = self.responses.get(url)
        if response is None:
            raise AssertionError(f"Unexpected POST {url}")
        return response


class AgentBackendTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.context = AgentBackendContext(
            agent_service_url="http://agent-service:8000",
            default_agent_name="Luban AIOps Runtime Agent",
            default_agent_system_prompt="Test prompt",
            chat_response_timeout_seconds=30.0,
        )

    def test_build_service_headers(self) -> None:
        headers = build_service_headers("req-123", "demo.operator")

        self.assertEqual(headers["x-request-id"], "req-123")
        self.assertEqual(headers["X-User-ID"], "demo.operator")

    def test_build_native_probe_headers(self) -> None:
        headers = build_native_probe_headers()

        self.assertEqual(headers["x-request-id"], "req-native-runtime-probe")
        self.assertEqual(headers["X-User-ID"], "gateway.runtime-probe")

    async def test_transitional_create_session_forwards_resolved_user_id(self) -> None:
        client = RecordingClient(
            {
                "http://agent-service:8000/api/v1/sessions": FakeResponse(
                    200,
                    {"session_id": "ses-123"},
                ),
            }
        )
        backend = TransitionalAgentServiceBackend(self.context)

        payload = await backend.create_session(
            client=client,
            request_id="req-123",
            user_id="demo.operator",
            payload={},
        )

        self.assertEqual(payload["session_id"], "ses-123")
        self.assertEqual(client.posts[0]["json"]["user_id"], "demo.operator")
        self.assertEqual(client.posts[0]["headers"]["X-User-ID"], "demo.operator")

    async def test_transitional_chat_preserves_payload_user_id(self) -> None:
        client = RecordingClient(
            {
                "http://agent-service:8000/api/v1/chat": FakeResponse(
                    200,
                    {"session_id": "ses-123", "request_id": "req-123", "response": "ok"},
                ),
            }
        )
        backend = TransitionalAgentServiceBackend(self.context)

        await backend.chat(
            client=client,
            request_id="req-123",
            user_id="header-user",
            payload={"message": "hello", "user_id": "body-user"},
        )

        self.assertEqual(client.posts[0]["json"]["user_id"], "body-user")
        self.assertEqual(client.posts[0]["headers"]["X-User-ID"], "header-user")

    async def test_resolve_agent_backend_prefers_transitional_runtime_endpoint(self) -> None:
        client = FakeClient(
            {
                "http://agent-service:8000/api/v1/runtime": FakeResponse(200, {}),
            }
        )

        resolution = await resolve_agent_backend(client, self.context, "auto")

        self.assertEqual(resolution.resolved_mode, "transitional")
        self.assertIn("transitional runtime metadata endpoint", resolution.reason)

    async def test_resolve_agent_backend_falls_back_to_native_agent_endpoint(self) -> None:
        client = FakeClient(
            {
                "http://agent-service:8000/api/v1/runtime": FakeResponse(404, {}),
                "http://agent-service:8000/agent/": FakeResponse(200, {"agents": []}),
            }
        )

        resolution = await resolve_agent_backend(client, self.context, "auto")

        self.assertEqual(resolution.resolved_mode, "native")
        self.assertIn("native AgentScope agent endpoint", resolution.reason)
        self.assertEqual(client.gets[-1]["headers"]["X-User-ID"], "gateway.runtime-probe")

    async def test_native_runtime_metadata_uses_probe_headers(self) -> None:
        client = FakeClient(
            {
                "http://agent-service:8000/agent/": FakeResponse(200, {"agents": []}),
            }
        )
        backend = NativeAgentServiceBackend(self.context)

        payload = await backend.runtime_metadata(client)

        self.assertEqual(payload["resolved_backend_mode"], "native")
        self.assertEqual(client.gets[0]["headers"]["X-User-ID"], "gateway.runtime-probe")

    async def test_native_chat_wraps_message_in_text_blocks(self) -> None:
        class NativeChatClient(RecordingClient):
            def __init__(self) -> None:
                super().__init__(
                    {
                        "http://agent-service:8000/agent/": FakeResponse(
                            200,
                            {"agents": [{"id": "agent-123", "data": {"name": "Luban AIOps Runtime Agent"}}]},
                        ),
                        "http://agent-service:8000/chat/": FakeResponse(200, {"status": "accepted"}),
                    }
                )

            def stream(self, method: str, url: str, params: dict | None = None, headers: dict | None = None):
                self.stream_request = {
                    "method": method,
                    "url": url,
                    "params": params or {},
                    "headers": headers or {},
                }

                class StreamResponse:
                    status_code = 200

                    def raise_for_status(self) -> None:
                        return None

                    async def aiter_lines(self):
                        yield 'data: {"type":"REPLY_START","reply_id":"reply-1"}'
                        yield 'data: {"type":"TEXT_BLOCK_DELTA","reply_id":"reply-1","delta":"Hello"}'
                        yield 'data: {"type":"REPLY_END","reply_id":"reply-1","finished_reason":"completed"}'

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, exc_type, exc, tb):
                        return False

                return StreamResponse()

        client = NativeChatClient()
        backend = NativeAgentServiceBackend(self.context)

        payload = await backend.chat(
            client=client,
            request_id="req-123",
            user_id="demo.operator",
            payload={"session_id": "ses-123", "message": "hello"},
        )

        self.assertEqual(payload["response"], "Hello")
        self.assertEqual(
            client.posts[0]["json"]["input"]["content"],
            [{"type": "text", "text": "hello"}],
        )
        self.assertEqual(client.posts[0]["headers"]["X-User-ID"], "demo.operator")

    async def test_resolve_agent_backend_raises_when_no_backend_is_detected(self) -> None:
        client = FakeClient(
            {
                "http://agent-service:8000/api/v1/runtime": FakeResponse(404, {}),
                "http://agent-service:8000/agent/": FakeResponse(404, {}),
            }
        )

        with self.assertRaises(HTTPException) as exc:
            await resolve_agent_backend(client, self.context, "auto")

        self.assertEqual(exc.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
