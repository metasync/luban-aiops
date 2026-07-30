"""Tool invocation endpoint tests (SPEC-007 R-4)."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api_gateway.app import create_app
from api_gateway.api.routes.tools import init_tool_registry
from api_gateway.core.config import GatewaySettings, get_settings
from api_gateway.schemas.api import IdentityContext
from api_gateway.services.policy_engine import reset_policy_state
from api_gateway.tools.base import BaseTool, ToolDefinition, ToolResult, build_evidence
from api_gateway.tools.registry import ToolRegistry


class _EchoTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="test.echo",
            description="Echoes parameters.",
            risk_level="read",
            category="test",
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        return ToolResult(
            tool_name="test.echo",
            status="success",
            data={"echo": parameters, "caller": identity.get("username")},
            evidence=build_evidence("read", "test", 5),
        )


def _build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(_EchoTool())
    return registry


def _identity(role: str) -> IdentityContext:
    return IdentityContext(
        subject=f"user-{role}",
        username=f"{role}.user",
        roles=[role],
    )


class ToolListEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_policy_state()
        app = create_app()
        init_tool_registry(_build_registry())
        app.dependency_overrides[get_settings] = lambda: GatewaySettings(
            require_auth=False
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_policy_state()
        init_tool_registry(ToolRegistry())

    def test_list_tools_returns_definitions(self) -> None:
        response = self.client.get("/api/v2/tools")
        self.assertEqual(response.status_code, 200)
        tools = response.json()
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["name"], "test.echo")
        self.assertEqual(tools[0]["risk_level"], "read")


class ToolInvokeEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_policy_state()
        app = create_app()
        init_tool_registry(_build_registry())
        app.dependency_overrides[get_settings] = lambda: GatewaySettings(
            require_auth=True
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_policy_state()
        init_tool_registry(ToolRegistry())

    def _patch_identity(self, role: str):
        identity = _identity(role)

        async def fake_identity(settings, request, request_id):
            return identity

        return patch(
            "api_gateway.api.routes.tools.resolve_request_identity",
            fake_identity,
        )

    def test_invoke_success_operator(self) -> None:
        with self._patch_identity("operator"):
            response = self.client.post(
                "/api/v2/tools/invoke",
                json={"tool_name": "test.echo", "parameters": {"msg": "hi"}, "request_id": "req-1"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["data"]["echo"], {"msg": "hi"})
        self.assertEqual(body["data"]["caller"], "operator.user")
        self.assertEqual(body["evidence"]["risk_level"], "read")

    def test_invoke_denied_for_observer(self) -> None:
        with self._patch_identity("read-only-observer"):
            response = self.client.post(
                "/api/v2/tools/invoke",
                json={"tool_name": "test.echo", "parameters": {}, "request_id": "req-2"},
            )
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertEqual(body["status"], "denied")
        self.assertEqual(body["error"]["code"], "POLICY_DENIED")

    def test_invoke_unknown_tool(self) -> None:
        with self._patch_identity("operator"):
            response = self.client.post(
                "/api/v2/tools/invoke",
                json={"tool_name": "nonexistent", "parameters": {}, "request_id": "req-3"},
            )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], "TOOL_NOT_FOUND")

    def test_invoke_developer_allowed(self) -> None:
        with self._patch_identity("developer"):
            response = self.client.post(
                "/api/v2/tools/invoke",
                json={"tool_name": "test.echo", "parameters": {}, "request_id": "req-4"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
