"""Tool endpoint tests (SPEC-007 R-4, re-pointed per SPEC-008 R-6).

Invoke tests exercise the real token-verification path: a delegated-style
token (audience ``tool-gateway``, RFC 8693 ``act`` actor) is minted and
verified through ``verify_token`` (JWKS client patched to a controlled key),
so the auth path that hid the original 401 is genuinely exercised rather than
monkeypatched away.
"""

import time
import unittest
from unittest.mock import patch

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from tool_gateway.app import create_app
from tool_gateway.core.config import GatewaySettings, get_settings
from tool_gateway.services import token_verifier
from tool_gateway.services.policy_engine import reset_policy_state
from tool_gateway.tools.base import BaseTool, ToolDefinition, ToolResult, build_evidence
from tool_gateway.tools.registry import ToolRegistry

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


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


class _ExplodingTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="test.explode",
            description="Raises an unhandled exception.",
            risk_level="read",
            category="test",
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        raise RuntimeError("boom")


class _WriteTool(BaseTool):
    """Mutating test tool (SPEC-021 R-1 endpoint tests)."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="test.mutate",
            description="Pretends to mutate something.",
            risk_level="write",
            category="test",
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        return ToolResult(
            tool_name="test.mutate",
            status="success",
            data={"mutated_by": identity.get("username")},
            evidence=build_evidence("write", "test", 5),
        )


def _build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(_EchoTool())
    registry.register(_ExplodingTool())
    return registry


def _mint_delegated(role: str, audience: str = "tool-gateway") -> str:
    """Mint a delegated-style token for a user acting via agent-platform."""
    now = int(time.time())
    claims = {
        "iss": "luban-identity-broker",
        "sub": f"user-{role}",
        "username": f"{role}.user",
        "roles": [role],
        "groups": [],
        "aud": [audience],
        "act": {"sub": "agent-platform"},
        "iat": now,
        "exp": now + 300,
    }
    return pyjwt.encode(claims, _KEY, algorithm="RS256")


def _patch_jwks():
    """Patch the JWKS client to resolve the controlled test public key."""
    public_key = _KEY.public_key()
    fake_client = type(
        "FakeClient",
        (),
        {
            "get_signing_key_from_jwt": lambda _self, _t: type(
                "K", (), {"key": public_key}
            )()
        },
    )()
    return patch.object(
        token_verifier, "_get_jwks_client", return_value=fake_client
    )


class ToolListEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_policy_state()
        token_verifier.reset_verifier_state()
        app = create_app()
        app.state.tool_registry = _build_registry()
        app.dependency_overrides[get_settings] = lambda: GatewaySettings(
            require_auth=True
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_policy_state()
        token_verifier.reset_verifier_state()

    def test_list_tools_requires_authentication(self) -> None:
        response = self.client.get("/api/v2/tools")
        self.assertEqual(response.status_code, 401)

    def test_list_tools_allowed_for_operator(self) -> None:
        with _patch_jwks():
            response = self.client.get(
                "/api/v2/tools",
                headers={"Authorization": f"Bearer {_mint_delegated('operator')}"},
            )
        self.assertEqual(response.status_code, 200)
        tools = {tool["name"]: tool for tool in response.json()}
        self.assertEqual(set(tools), {"test.echo", "test.explode"})
        self.assertEqual(tools["test.echo"]["risk_level"], "read")

    def test_list_tools_allowed_for_observer(self) -> None:
        # Authorization matrix: read-only-observer may perform tier-0 reads; all
        # registered tools are read-only, so discovery is granted.
        with _patch_jwks():
            response = self.client.get(
                "/api/v2/tools",
                headers={
                    "Authorization": f"Bearer {_mint_delegated('read-only-observer')}"
                },
            )
        self.assertEqual(response.status_code, 200)
        tools = {tool["name"]: tool for tool in response.json()}
        self.assertEqual(set(tools), {"test.echo", "test.explode"})

    def test_list_tools_rejects_wrong_audience_before_policy(self) -> None:
        with _patch_jwks():
            response = self.client.get(
                "/api/v2/tools",
                headers={
                    "Authorization": f"Bearer {_mint_delegated('operator', 'other')}"
                },
            )
        self.assertEqual(response.status_code, 401)


class ToolInvokeEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_policy_state()
        token_verifier.reset_verifier_state()
        app = create_app()
        app.state.tool_registry = _build_registry()
        app.dependency_overrides[get_settings] = lambda: GatewaySettings(
            require_auth=True
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_policy_state()
        token_verifier.reset_verifier_state()

    def _invoke(self, token: str, tool_name: str, parameters: dict, request_id: str):
        return self.client.post(
            "/api/v2/tools/invoke",
            json={"tool_name": tool_name, "parameters": parameters, "request_id": request_id},
            headers={"Authorization": f"Bearer {token}"},
        )

    def test_invoke_requires_authentication(self) -> None:
        response = self.client.post(
            "/api/v2/tools/invoke",
            json={"tool_name": "test.echo", "parameters": {}, "request_id": "req-0"},
        )
        self.assertEqual(response.status_code, 401)

    def test_invoke_success_operator(self) -> None:
        with _patch_jwks():
            response = self._invoke(
                _mint_delegated("operator"), "test.echo", {"msg": "hi"}, "req-1"
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["data"]["echo"], {"msg": "hi"})
        self.assertEqual(body["data"]["caller"], "operator.user")
        self.assertEqual(body["evidence"]["risk_level"], "read")

    def test_invoke_allowed_for_observer(self) -> None:
        # Authorization matrix: read-only-observer may perform tier-0 reads; all
        # registered tools are read-only, so invocation is granted.
        with _patch_jwks():
            response = self._invoke(
                _mint_delegated("read-only-observer"), "test.echo", {}, "req-2"
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["data"]["caller"], "read-only-observer.user")

    def test_invoke_unknown_tool(self) -> None:
        with _patch_jwks():
            response = self._invoke(
                _mint_delegated("operator"), "nonexistent", {}, "req-3"
            )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], "TOOL_NOT_FOUND")

    def test_invoke_developer_allowed(self) -> None:
        with _patch_jwks():
            response = self._invoke(
                _mint_delegated("developer"), "test.echo", {}, "req-4"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")

    def test_invoke_tool_exception_returns_structured_error(self) -> None:
        """A raising tool must still yield a tool-result envelope, not a 500."""
        with _patch_jwks():
            response = self._invoke(
                _mint_delegated("operator"), "test.explode", {}, "req-5"
            )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], "TOOL_EXECUTION_ERROR")
        self.assertIn("boom", body["error"]["message"])
        self.assertEqual(body["evidence"]["risk_level"], "read")

    def test_invoke_rejects_wrong_audience_before_policy(self) -> None:
        with _patch_jwks():
            response = self._invoke(
                _mint_delegated("operator", "other-service"), "test.echo", {}, "req-6"
            )
        self.assertEqual(response.status_code, 401)


class MutatingInvokeEndpointTests(unittest.TestCase):
    """Risk-tier admission at the invoke endpoint (SPEC-021 R-1)."""

    def setUp(self) -> None:
        reset_policy_state()
        token_verifier.reset_verifier_state()
        app = create_app()
        registry = ToolRegistry(allow_mutating=True)
        registry.register(_EchoTool())
        registry.register(_WriteTool())
        app.state.tool_registry = registry
        app.dependency_overrides[get_settings] = lambda: GatewaySettings(
            require_auth=True
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_policy_state()
        token_verifier.reset_verifier_state()

    def _invoke(self, token: str, tool_name: str, request_id: str):
        return self.client.post(
            "/api/v2/tools/invoke",
            json={"tool_name": tool_name, "parameters": {}, "request_id": request_id},
            headers={"Authorization": f"Bearer {token}"},
        )

    def test_operator_may_invoke_mutating_tool(self) -> None:
        with _patch_jwks():
            response = self._invoke(
                _mint_delegated("operator"), "test.mutate", "req-m1"
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["evidence"]["risk_level"], "write")

    def test_platform_admin_may_invoke_mutating_tool(self) -> None:
        with _patch_jwks():
            response = self._invoke(
                _mint_delegated("platform-admin"), "test.mutate", "req-m2"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")

    def test_observer_denied_mutating_tool(self) -> None:
        with _patch_jwks():
            response = self._invoke(
                _mint_delegated("read-only-observer"), "test.mutate", "req-m3"
            )
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertEqual(body["status"], "denied")
        # The denied envelope must carry the tool's true tier, not "read".
        self.assertEqual(body["evidence"]["risk_level"], "write")

    def test_developer_denied_mutating_tool(self) -> None:
        with _patch_jwks():
            response = self._invoke(
                _mint_delegated("developer"), "test.mutate", "req-m4"
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["status"], "denied")

    def test_approver_denied_mutating_tool(self) -> None:
        with _patch_jwks():
            response = self._invoke(
                _mint_delegated("approver"), "test.mutate", "req-m5"
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["status"], "denied")

    def test_observer_still_allowed_read_tool(self) -> None:
        with _patch_jwks():
            response = self._invoke(
                _mint_delegated("read-only-observer"), "test.echo", "req-m6"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")

    def test_discovery_exposes_mutating_tool_risk(self) -> None:
        with _patch_jwks():
            response = self.client.get(
                "/api/v2/tools",
                headers={"Authorization": f"Bearer {_mint_delegated('operator')}"},
            )
        self.assertEqual(response.status_code, 200)
        tools = {tool["name"]: tool for tool in response.json()}
        self.assertEqual(tools["test.mutate"]["risk_level"], "write")


class MutatingToolsDisabledEndpointTests(unittest.TestCase):
    """Default registry refuses mutating tools (SPEC-021 R-1)."""

    def setUp(self) -> None:
        reset_policy_state()
        token_verifier.reset_verifier_state()
        app = create_app()
        registry = ToolRegistry()
        registry.register(_EchoTool())
        registry.register(_WriteTool())
        app.state.tool_registry = registry
        app.dependency_overrides[get_settings] = lambda: GatewaySettings(
            require_auth=True
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_policy_state()
        token_verifier.reset_verifier_state()

    def test_discovery_excludes_mutating_tool(self) -> None:
        with _patch_jwks():
            response = self.client.get(
                "/api/v2/tools",
                headers={"Authorization": f"Bearer {_mint_delegated('operator')}"},
            )
        self.assertEqual(response.status_code, 200)
        names = {tool["name"] for tool in response.json()}
        self.assertNotIn("test.mutate", names)

    def test_invoke_mutating_tool_not_found(self) -> None:
        with _patch_jwks():
            response = self.client.post(
                "/api/v2/tools/invoke",
                json={"tool_name": "test.mutate", "parameters": {}, "request_id": "req-d1"},
                headers={"Authorization": f"Bearer {_mint_delegated('operator')}"},
            )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], "TOOL_NOT_FOUND")


class ToolRegistryDependencyTests(unittest.TestCase):
    def test_missing_registry_returns_service_unavailable(self) -> None:
        """An app assembled without a registry fails loudly, not silently empty."""
        from fastapi import FastAPI

        from tool_gateway.api.routes.tools import router

        app = FastAPI()
        app.include_router(router)
        # tools:list now requires auth; with no registry the dependency still
        # resolves the registry first, yielding 503 once auth is satisfied.
        app.dependency_overrides[get_settings] = lambda: GatewaySettings(
            require_auth=False
        )
        response = TestClient(app).get("/api/v2/tools")
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
