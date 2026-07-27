import unittest
from unittest.mock import patch

from starlette.requests import Request

from api_gateway.core.config import GatewaySettings
from api_gateway.core.request_context import resolve_user_id
from api_gateway.services.gateway_service import (
    fetch_current_identity,
    resolve_authenticated_identity,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError(f"HTTP error {self.status_code}")


class FakeAsyncClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.gets: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, headers: dict | None = None):
        self.gets.append({"url": url, "headers": headers or {}})
        return self.response


class GatewayAuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_current_identity_forwards_bearer_token(self) -> None:
        fake_client = FakeAsyncClient(
            FakeResponse(
                200,
                {
                    "subject": "user-123",
                    "username": "alice",
                    "roles": ["operator"],
                    "groups": ["ops-operators"],
                    "email": "alice@example.com",
                },
            )
        )

        with patch(
            "api_gateway.services.gateway_service.httpx.AsyncClient",
            return_value=fake_client,
        ):
            payload = await fetch_current_identity(
                GatewaySettings(identity_service_url="http://identity-service:8000"),
                "req-123",
                "Bearer access-token",
            )

        self.assertEqual(payload["username"], "alice")
        self.assertEqual(
            fake_client.gets[0]["headers"]["authorization"],
            "Bearer access-token",
        )
        self.assertEqual(fake_client.gets[0]["headers"]["x-request-id"], "req-123")

    async def test_resolve_authenticated_identity_returns_none_without_authorization(self) -> None:
        request = Request({"type": "http", "headers": []})

        payload = await resolve_authenticated_identity(
            GatewaySettings(),
            request,
            "req-123",
        )

        self.assertIsNone(payload)

    def test_resolve_user_id_prefers_authenticated_user(self) -> None:
        resolved_user_id = resolve_user_id(
            default_user_id="demo.operator",
            explicit_user_id="body-user",
            header_user_id="header-user",
            authenticated_user_id="alice",
        )

        self.assertEqual(resolved_user_id, "alice")


if __name__ == "__main__":
    unittest.main()
