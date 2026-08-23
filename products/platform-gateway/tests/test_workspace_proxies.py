"""Workspace inventory proxy tests (SPEC-019 R-4).

Validates the gateway-side gates for the Tools and Skills workspace views:
per-action policy enforcement (tools:list / skills:read), delegated-bearer
forwarding to tool-gateway, gateway-held Basic credential to skills-hub
(never the user's token), 503 when unconfigured or delegation is absent,
and upstream error mapping (502 on transport/5xx, 4xx passthrough).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import jsonschema
from fastapi.testclient import TestClient

from platform_gateway.app import create_app
from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.schemas.api import IdentityContext
from platform_gateway.services.policy_engine import reset_policy_state

TOOL_DEFINITIONS = [
    {
        "name": "kubernetes.get_pod_logs",
        "description": "Fetch recent logs for a pod.",
        "read_only": True,
    },
    {
        "name": "kubernetes.restart_deployment",
        "description": "Restart a deployment.",
        "read_only": False,
    },
]

SKILLS_PAYLOAD = {
    "skills": [
        {
            "name": "incident-triage",
            "version": "1.2.0",
            "source": "git:ops-skills",
            "tags": ["incident", "triage"],
        }
    ],
    "total": 1,
    "offset": 0,
    "limit": 100,
}


def _identity(role: str) -> IdentityContext:
    return IdentityContext(
        subject=f"user-{role}",
        username=f"{role}.user",
        roles=[role],
    )


class _FakeResponse:
    def __init__(self, status_code: int, payload) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient capturing the proxied calls."""

    def __init__(self, response=None, raise_exc=None) -> None:
        self._response = response
        self._raise = raise_exc
        self.calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, url, params=None, auth=None, headers=None):
        self.calls.append(
            {"url": url, "params": params, "auth": auth, "headers": headers}
        )
        if self._raise is not None:
            raise self._raise
        return self._response


def _settings(**overrides) -> PlatformGatewaySettings:
    defaults = dict(
        require_auth=True,
        tool_gateway_url="http://tool-gateway:8000",
        skills_hub_url="http://skills-hub:8000",
        skills_client_id="platform-gateway",
        skills_client_secret="pg-skills-secret",
    )
    defaults.update(overrides)
    return PlatformGatewaySettings(**defaults)


class WorkspaceProxyBase(unittest.TestCase):
    def setUp(self) -> None:
        reset_policy_state()
        self.app = create_app()
        self._use_settings(_settings())
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        reset_policy_state()

    def _use_settings(self, settings: PlatformGatewaySettings) -> None:
        self.app.dependency_overrides[get_settings] = lambda: settings

    def _patch_identity(self, role: str, route_module: str):
        identity = _identity(role)

        async def fake_identity(settings, request, request_id):
            return identity

        return patch(
            f"platform_gateway.api.routes.{route_module}.resolve_request_identity",
            fake_identity,
        )

    def _patch_httpx(self, fake: _FakeAsyncClient, module: str):
        return patch(
            f"platform_gateway.services.{module}.httpx.AsyncClient",
            return_value=fake,
        )


class ToolsProxyTests(WorkspaceProxyBase):
    def _patch_delegation(self, token: str | None = "delegated-token"):
        return patch(
            "platform_gateway.api.routes.tools.obtain_delegated_token",
            new=AsyncMock(return_value=token),
        )

    def test_operator_allowed_and_proxied_with_delegated_bearer(self) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(200, TOOL_DEFINITIONS))
        with (
            self._patch_identity("operator", "tools"),
            self._patch_delegation(),
            self._patch_httpx(fake, "tool_gateway_client"),
        ):
            response = self.client.get(
                "/api/v1/tools",
                headers={"authorization": "Bearer session-token"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)
        call = fake.calls[0]
        self.assertEqual(call["url"], "http://tool-gateway:8000/api/v2/tools")
        # The upstream sees the delegated token, never the session token.
        self.assertEqual(call["headers"]["authorization"], "Bearer delegated-token")
        self.assertIn("x-request-id", call["headers"])

    def test_observer_allowed_to_list_tools(self) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(200, []))
        with (
            self._patch_identity("read-only-observer", "tools"),
            self._patch_delegation(),
            self._patch_httpx(fake, "tool_gateway_client"),
        ):
            response = self.client.get("/api/v1/tools")
        self.assertEqual(response.status_code, 200)

    def test_ungranted_role_denied_before_upstream(self) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(200, []))
        with (
            self._patch_identity("auditor", "tools"),
            self._patch_delegation(),
            self._patch_httpx(fake, "tool_gateway_client"),
        ):
            response = self.client.get("/api/v1/tools")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["action"], "tools:list")
        self.assertEqual(fake.calls, [])

    def test_missing_delegation_returns_503(self) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(200, []))
        with (
            self._patch_identity("operator", "tools"),
            self._patch_delegation(token=None),
            self._patch_httpx(fake, "tool_gateway_client"),
        ):
            response = self.client.get("/api/v1/tools")
        self.assertEqual(response.status_code, 503)
        self.assertIn("delegation chain", response.json()["detail"])
        self.assertEqual(fake.calls, [])

    def test_unconfigured_upstream_returns_503(self) -> None:
        self._use_settings(_settings(tool_gateway_url=""))
        with (
            self._patch_identity("operator", "tools"),
            self._patch_delegation(),
        ):
            response = self.client.get("/api/v1/tools")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "tool gateway not configured")

    def test_transport_failure_returns_502(self) -> None:
        fake = _FakeAsyncClient(raise_exc=httpx.ConnectError("boom"))
        with (
            self._patch_identity("operator", "tools"),
            self._patch_delegation(),
            self._patch_httpx(fake, "tool_gateway_client"),
        ):
            response = self.client.get("/api/v1/tools")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "tool gateway unavailable")

    def test_upstream_5xx_mapped_to_502(self) -> None:
        fake = _FakeAsyncClient(
            response=_FakeResponse(500, {"detail": "internal error"})
        )
        with (
            self._patch_identity("operator", "tools"),
            self._patch_delegation(),
            self._patch_httpx(fake, "tool_gateway_client"),
        ):
            response = self.client.get("/api/v1/tools")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "tool gateway request failed")

    def test_upstream_4xx_passed_through(self) -> None:
        fake = _FakeAsyncClient(
            response=_FakeResponse(403, {"detail": "action denied by policy"})
        )
        with (
            self._patch_identity("operator", "tools"),
            self._patch_delegation(),
            self._patch_httpx(fake, "tool_gateway_client"),
        ):
            response = self.client.get("/api/v1/tools")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "action denied by policy")


class SkillsProxyTests(WorkspaceProxyBase):
    def test_operator_allowed_and_proxied_with_gateway_credential(self) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(200, SKILLS_PAYLOAD))
        with (
            self._patch_identity("operator", "skills"),
            self._patch_httpx(fake, "skills_hub_client"),
        ):
            response = self.client.get("/api/v1/skills")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        call = fake.calls[0]
        self.assertEqual(call["url"], "http://skills-hub:8000/api/v1/skills")
        # The proxy authenticates with its own credential, never the user's.
        self.assertEqual(call["auth"], ("platform-gateway", "pg-skills-secret"))
        self.assertEqual(call["params"]["offset"], 0)
        self.assertEqual(call["params"]["limit"], 100)
        self.assertNotIn("source", call["params"])
        self.assertNotIn("tag", call["params"])

    def test_filters_forwarded_to_upstream(self) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(200, SKILLS_PAYLOAD))
        with (
            self._patch_identity("operator", "skills"),
            self._patch_httpx(fake, "skills_hub_client"),
        ):
            response = self.client.get(
                "/api/v1/skills",
                params={"offset": 10, "limit": 5, "source": "git:ops", "tag": "triage"},
            )
        self.assertEqual(response.status_code, 200)
        params = fake.calls[0]["params"]
        self.assertEqual(params["offset"], 10)
        self.assertEqual(params["limit"], 5)
        self.assertEqual(params["source"], "git:ops")
        self.assertEqual(params["tag"], "triage")

    def test_invalid_pagination_rejected_before_upstream(self) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(200, SKILLS_PAYLOAD))
        with (
            self._patch_identity("operator", "skills"),
            self._patch_httpx(fake, "skills_hub_client"),
        ):
            for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
                response = self.client.get("/api/v1/skills", params=params)
                self.assertEqual(response.status_code, 422, params)
        self.assertEqual(fake.calls, [])

    def test_ungranted_role_denied_before_upstream(self) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(200, SKILLS_PAYLOAD))
        with (
            self._patch_identity("auditor", "skills"),
            self._patch_httpx(fake, "skills_hub_client"),
        ):
            response = self.client.get("/api/v1/skills")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["action"], "skills:read")
        self.assertEqual(fake.calls, [])

    def test_unconfigured_upstream_returns_503(self) -> None:
        self._use_settings(_settings(skills_hub_url=""))
        with self._patch_identity("operator", "skills"):
            response = self.client.get("/api/v1/skills")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "skills hub not configured")

    def test_transport_failure_returns_502(self) -> None:
        fake = _FakeAsyncClient(raise_exc=httpx.ConnectError("boom"))
        with (
            self._patch_identity("operator", "skills"),
            self._patch_httpx(fake, "skills_hub_client"),
        ):
            response = self.client.get("/api/v1/skills")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "skills hub unavailable")

    def test_upstream_4xx_passed_through_with_message(self) -> None:
        fake = _FakeAsyncClient(
            response=_FakeResponse(
                401, {"error": {"code": "unauthorized", "message": "bad credential"}}
            )
        )
        with (
            self._patch_identity("operator", "skills"),
            self._patch_httpx(fake, "skills_hub_client"),
        ):
            response = self.client.get("/api/v1/skills")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "bad credential")


MODELS_PAYLOAD = {
    "models": [
        {
            "id": "deepseek",
            "label": "deepseek-v4-flash",
            "provider": "deepseek",
            "default": True,
        },
        {
            "id": "openai",
            "label": "gpt-4o-mini",
            "provider": "openai",
            "default": False,
        },
    ],
    "default": "deepseek",
}

MODELS_CLIENT = "platform_gateway.services.gateway_service.agent_client.list_models"


def _models_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "http://agent-service/api/v2/models")
    return httpx.HTTPStatusError(
        "upstream error", request=request, response=httpx.Response(status_code)
    )


class ModelsProxyTests(WorkspaceProxyBase):
    """Model catalog discovery pass-through (SPEC-024 R-2)."""

    def test_operator_allowed_and_payload_proxied_verbatim(self) -> None:
        upstream = AsyncMock(return_value=MODELS_PAYLOAD)
        with (
            self._patch_identity("operator", "models"),
            patch(MODELS_CLIENT, upstream),
        ):
            response = self.client.get("/api/v1/models")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), MODELS_PAYLOAD)
        upstream.assert_awaited_once()

    def test_observer_allowed(self) -> None:
        upstream = AsyncMock(return_value=MODELS_PAYLOAD)
        with (
            self._patch_identity("read-only-observer", "models"),
            patch(MODELS_CLIENT, upstream),
        ):
            response = self.client.get("/api/v1/models")
        self.assertEqual(response.status_code, 200)

    def test_ungranted_role_denied_before_upstream(self) -> None:
        upstream = AsyncMock(return_value=MODELS_PAYLOAD)
        with (
            self._patch_identity("auditor", "models"),
            patch(MODELS_CLIENT, upstream),
        ):
            response = self.client.get("/api/v1/models")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["action"], "models:list")
        upstream.assert_not_awaited()

    def test_upstream_4xx_passed_through(self) -> None:
        upstream = AsyncMock(side_effect=_models_status_error(401))
        with (
            self._patch_identity("operator", "models"),
            patch(MODELS_CLIENT, upstream),
        ):
            response = self.client.get("/api/v1/models")
        self.assertEqual(response.status_code, 401)

    def test_upstream_5xx_mapped_to_502(self) -> None:
        upstream = AsyncMock(side_effect=_models_status_error(500))
        with (
            self._patch_identity("operator", "models"),
            patch(MODELS_CLIENT, upstream),
        ):
            response = self.client.get("/api/v1/models")
        self.assertEqual(response.status_code, 502)

    def test_transport_failure_returns_502(self) -> None:
        upstream = AsyncMock(side_effect=httpx.ConnectError("boom"))
        with (
            self._patch_identity("operator", "models"),
            patch(MODELS_CLIENT, upstream),
        ):
            response = self.client.get("/api/v1/models")
        self.assertEqual(response.status_code, 502)

    def test_payload_validates_against_model_catalog_contract(self) -> None:
        """Lockstep: the proxied shape must satisfy model-catalog.schema.json."""
        schema = json.loads(
            (
                Path(__file__).resolve().parents[3]
                / "shared"
                / "shared-contracts"
                / "schemas"
                / "model-catalog.schema.json"
            ).read_text()
        )
        jsonschema.validate(MODELS_PAYLOAD, schema)
        # Credentials or base URLs must never be part of the contract shape.
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(
                {
                    "models": [
                        {
                            "id": "deepseek",
                            "label": "deepseek-v4-flash",
                            "provider": "deepseek",
                            "default": True,
                            "api_key": "sk-secret",
                        }
                    ],
                    "default": "deepseek",
                },
                schema,
            )


if __name__ == "__main__":
    unittest.main()
