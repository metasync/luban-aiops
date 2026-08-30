"""Runtime version surface and auth-leg error mapping tests (v0.27.2).

B: `/api/v1/runtime` carries the gateway's own `SERVICE_VERSION` so probes
and the portal's Settings inventory can read the deployed platform version
without another endpoint. C: the identity-service legs (login-url, login,
callback, logout-url, refresh) ride the house proxy error model — the
identity service's 4xx postures pass through with their detail, while 5xx
and transport failures become a structured 502, never a raw 500.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

from platform_gateway.app import create_app
from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.metadata import SERVICE_VERSION
from platform_gateway.services import agent_client, gateway_service

AGENT_RUNTIME_PAYLOAD = {
    "service": "agent-service",
    "version": "9.9.9-agent",
    "models": [],
}

IDENTITY_CALLBACK_PAYLOAD = {
    "tokens": {"access_token": "at-1", "refresh_token": "rt-1"},
    "identity": {"username": "luban-operator"},
}


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://identity-service/api/v1/auth")
            response = httpx.Response(self.status_code, json=self._payload, request=request)
            raise httpx.HTTPStatusError(
                f"{self.status_code} error", request=request, response=response
            )

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient on the identity legs."""

    def __init__(self, response=None, raise_exc=None) -> None:
        self._response = response
        self._raise = raise_exc
        self.calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def request(self, method, url, headers=None, json=None):
        self.calls.append({"method": method, "url": url, "json": json})
        if self._raise is not None:
            raise self._raise
        return self._response


class _FakeAgentAsyncClient:
    """Stand-in for httpx.AsyncClient on the agent runtime leg."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, url):
        return _FakeResponse(200, self._payload)


def _settings(**overrides) -> PlatformGatewaySettings:
    defaults = dict(
        require_auth=True,
        identity_service_url="http://identity-service:8000",
        agent_service_url="http://agent-service:8000",
    )
    defaults.update(overrides)
    return PlatformGatewaySettings(**defaults)


class RuntimeVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: _settings()
        self.client = TestClient(app)

    def test_runtime_status_merges_platform_version(self) -> None:
        async def fake_runtime_metadata(settings):
            return dict(AGENT_RUNTIME_PAYLOAD)

        with patch.object(agent_client, "runtime_metadata", fake_runtime_metadata):
            payload = self.client.get("/api/v1/runtime").json()

        self.assertEqual(payload["version"], SERVICE_VERSION)
        # The agent surface rides through untouched.
        self.assertEqual(payload["service"], "agent-service")
        self.assertEqual(payload["models"], [])

    def test_gateway_version_wins_when_agent_reports_its_own(self) -> None:
        async def fake_runtime_metadata(settings):
            return {"version": "9.9.9-agent"}

        with patch.object(agent_client, "runtime_metadata", fake_runtime_metadata):
            payload = self.client.get("/api/v1/runtime").json()

        self.assertEqual(payload["version"], SERVICE_VERSION)


class IdentityLegTests(unittest.TestCase):
    def setUp(self) -> None:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: _settings()
        self.client = TestClient(app, raise_server_exceptions=False)

    def _patch_httpx(self, fake: _FakeAsyncClient):
        return patch(
            "platform_gateway.services.gateway_service.httpx.AsyncClient",
            return_value=fake,
        )

    def test_callback_passes_identity_payload_through(self) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(200, IDENTITY_CALLBACK_PAYLOAD))

        with self._patch_httpx(fake):
            response = self.client.post(
                "/api/v1/auth/callback", json={"code": "auth-code-1"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), IDENTITY_CALLBACK_PAYLOAD)
        self.assertEqual(fake.calls[0]["method"], "POST")
        self.assertEqual(
            fake.calls[0]["url"], "http://identity-service:8000/api/v1/auth/callback"
        )
        self.assertEqual(fake.calls[0]["json"], {"code": "auth-code-1"})

    def test_identity_4xx_passes_through_with_detail(self) -> None:
        fake = _FakeAsyncClient(
            response=_FakeResponse(401, {"detail": "invalid or expired code"})
        )

        with self._patch_httpx(fake):
            response = self.client.post(
                "/api/v1/auth/callback", json={"code": "stale-code"}
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "invalid or expired code")

    def test_identity_4xx_without_json_detail_falls_back(self) -> None:
        class _OpaqueResponse:
            status_code = 400

            def raise_for_status(self):
                request = httpx.Request("GET", "http://identity-service/api/v1/auth")
                response = httpx.Response(400, content=b"<html>bad</html>", request=request)
                raise httpx.HTTPStatusError("400", request=request, response=response)

        fake = _FakeAsyncClient(response=_OpaqueResponse())

        with self._patch_httpx(fake):
            response = self.client.post(
                "/api/v1/auth/callback", json={"code": "bad"}
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "identity service rejected the request")

    def test_identity_5xx_becomes_structured_502(self) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(503, {"detail": "boom"}))

        with self._patch_httpx(fake):
            response = self.client.post(
                "/api/v1/auth/callback", json={"code": "auth-code-1"}
            )

        self.assertEqual(response.status_code, 502)
        self.assertIn("identity service unavailable", response.json()["detail"])

    def test_identity_transport_failure_becomes_structured_502(self) -> None:
        fake = _FakeAsyncClient(raise_exc=httpx.ConnectError("connection refused"))

        with self._patch_httpx(fake):
            response = self.client.get("/api/v1/auth/login-url")

        self.assertEqual(response.status_code, 502)
        self.assertIn("identity service unreachable", response.json()["detail"])

    def test_login_and_refresh_share_the_leg_mapping(self) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(200, {"url": "http://kc/..."}))
        with self._patch_httpx(fake):
            response = self.client.get("/api/v1/auth/login")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake.calls[0]["url"], "http://identity-service:8000/api/v1/auth/login")

        fake = _FakeAsyncClient(response=_FakeResponse(400, {"detail": "bad refresh token"}))
        with self._patch_httpx(fake):
            response = self.client.post("/api/v1/auth/refresh", json={"refresh_token": "rt-x"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "bad refresh token")


class IdentityLegUnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_leg_raises_http_exception_never_raw_error(self) -> None:
        fake = _FakeAsyncClient(raise_exc=httpx.ConnectError("connection refused"))

        with patch(
            "platform_gateway.services.gateway_service.httpx.AsyncClient",
            return_value=fake,
        ):
            with self.assertRaises(HTTPException) as ctx:
                await gateway_service.complete_login(
                    _settings(), "req-1", {"code": "c"}
                )

        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIn("retry the sign-in", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
