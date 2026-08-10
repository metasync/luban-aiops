"""Gateway tools integration tests (SPEC-007 R-6, SPEC-008 R-5)."""

import asyncio
import json
import os
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

from agent_service.tools.gateway_tools import (
    _make_tool_fn,
    build_function_tools,
    build_gateway_toolkit,
    build_toolkit,
    discover_tools,
    invoke_gateway_tool,
)


def _run(coro):
    return asyncio.run(coro)


MOCK_TOOL_DEFINITIONS = [
    {
        "name": "k8s.list_pods",
        "description": "List pods in a namespace.",
        "risk_level": "read",
        "category": "kubernetes",
        "parameters_schema": {"type": "object"},
    },
    {
        "name": "k8s.get_pod",
        "description": "Get pod details.",
        "risk_level": "read",
        "category": "kubernetes",
        "parameters_schema": {"type": "object", "required": ["name"]},
    },
]


def _mock_client(response=None, get_side_effect=None):
    mock_client = AsyncMock()
    if get_side_effect is not None:
        mock_client.get.side_effect = get_side_effect
    else:
        mock_client.get.return_value = response
    mock_client.post.return_value = response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class DiscoverToolsTests(unittest.TestCase):
    def test_discover_success_sends_bearer_header(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = MOCK_TOOL_DEFINITIONS
        mock_response.raise_for_status = MagicMock()

        with patch("agent_service.tools.gateway_tools.httpx.AsyncClient") as mock_client_cls:
            mock_client = _mock_client(response=mock_response)
            mock_client_cls.return_value = mock_client

            tools = _run(discover_tools("http://gateway:8080", bearer_token="delegated-token"))

        self.assertEqual(len(tools), 2)
        self.assertEqual(tools[0]["name"], "k8s.list_pods")
        headers = mock_client.get.call_args[1]["headers"]
        self.assertEqual(headers["Authorization"], "Bearer delegated-token")

    def test_discover_without_token_returns_empty_no_network(self) -> None:
        with patch("agent_service.tools.gateway_tools.httpx.AsyncClient") as mock_client_cls:
            tools = _run(discover_tools("http://gateway:8080"))

        self.assertEqual(tools, [])
        mock_client_cls.assert_not_called()

    def test_discover_failure_returns_empty(self) -> None:
        with patch("agent_service.tools.gateway_tools.httpx.AsyncClient") as mock_client_cls:
            mock_client = _mock_client(get_side_effect=Exception("connection refused"))
            mock_client_cls.return_value = mock_client

            tools = _run(discover_tools("http://gateway:8080", bearer_token="tok"))

        self.assertEqual(tools, [])


class InvokeGatewayToolTests(unittest.TestCase):
    def test_invoke_sends_bearer_header_and_no_identity_in_body(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "success", "data": {}}

        with patch("agent_service.tools.gateway_tools.httpx.AsyncClient") as mock_client_cls:
            mock_client = _mock_client(response=mock_response)
            mock_client_cls.return_value = mock_client

            result = _run(invoke_gateway_tool(
                gateway_url="http://gateway:8080",
                tool_name="k8s.list_pods",
                parameters={"namespace": "prod"},
                bearer_token="delegated-token",
            ))

        self.assertEqual(result["status"], "success")
        call_args = mock_client.post.call_args
        self.assertIn("/api/v2/tools/invoke", call_args[0][0])
        # Bearer header is presented; identity is carried by the token only.
        headers = call_args[1]["headers"]
        self.assertEqual(headers["Authorization"], "Bearer delegated-token")
        payload = call_args[1]["json"]
        self.assertEqual(payload["tool_name"], "k8s.list_pods")
        self.assertEqual(payload["parameters"], {"namespace": "prod"})
        self.assertIn("request_id", payload)
        # identity_context must never appear in the body (SPEC-008 R-5).
        self.assertNotIn("identity_context", payload)

    def test_invoke_without_token_returns_structured_error(self) -> None:
        with patch("agent_service.tools.gateway_tools.httpx.AsyncClient") as mock_client_cls:
            result = _run(invoke_gateway_tool(
                gateway_url="http://gateway:8080",
                tool_name="k8s.list_pods",
                parameters={},
            ))

        # No network call is made; a structured error is returned, never raised.
        mock_client_cls.assert_not_called()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "NO_CREDENTIAL")
        self.assertEqual(result["tool_name"], "k8s.list_pods")


class MakeToolFnTests(unittest.TestCase):
    """The closure factory: metadata and token binding (SPEC-008 R-5)."""

    def test_function_name_sanitized(self) -> None:
        fn = _make_tool_fn(
            "http://gw:8080", "k8s.list_pods", "List pods.", None, None, 2000
        )
        self.assertEqual(fn.__name__, "k8s_list_pods")

    def test_function_docstring_set(self) -> None:
        fn = _make_tool_fn(
            "http://gw:8080", "k8s.list_pods",
            "List pods in a namespace.", None, None, 2000,
        )
        self.assertEqual(fn.__doc__, "List pods in a namespace.")

    def test_closure_binds_token_and_dotted_name(self) -> None:
        fn = _make_tool_fn(
            "http://gw:8080", "k8s.list_pods", "d", "user-token", None, 2000
        )
        mock_result = {"status": "success", "data": {"pods": []}}
        with patch(
            "agent_service.tools.gateway_tools.invoke_gateway_tool",
            new_callable=AsyncMock,
        ) as mock_invoke:
            mock_invoke.return_value = mock_result
            result_str = _run(fn(namespace="test"))

        result = json.loads(result_str)
        self.assertEqual(result["status"], "success")
        # The gateway receives the ORIGINAL dotted tool name; identity rides on
        # the token only (never in the body).
        mock_invoke.assert_called_once_with(
            gateway_url="http://gw:8080",
            tool_name="k8s.list_pods",
            parameters={"namespace": "test"},
            bearer_token="user-token",
        )


class BuildFunctionToolsTests(unittest.TestCase):
    def test_builds_function_tool_per_definition(self) -> None:
        from agentscope.tool import FunctionTool

        tools = build_function_tools("http://gw:8080", MOCK_TOOL_DEFINITIONS)
        self.assertEqual(len(tools), 2)
        self.assertTrue(all(isinstance(t, FunctionTool) for t in tools))

    def test_tool_names_sanitized(self) -> None:
        tools = build_function_tools("http://gw:8080", MOCK_TOOL_DEFINITIONS)
        self.assertEqual(tools[0].name, "k8s_list_pods")
        self.assertEqual(tools[1].name, "k8s_get_pod")

    def test_input_schema_bound_from_definition(self) -> None:
        tools = build_function_tools("http://gw:8080", MOCK_TOOL_DEFINITIONS)
        # Normalized: AgentScope requires an object schema with a properties
        # dict, so one is filled in when the gateway omits it.
        self.assertEqual(
            tools[1].input_schema,
            {"type": "object", "required": ["name"], "properties": {}},
        )

    def test_schema_without_properties_normalized(self) -> None:
        defs = [{
            "name": "k8s.list_pods",
            "description": "x",
            "risk_level": "read",
            "parameters_schema": {"type": "object"},
        }]
        tools = build_function_tools("http://gw:8080", defs)
        self.assertEqual(
            tools[0].input_schema, {"type": "object", "properties": {}}
        )

    def test_non_object_schema_replaced_with_default(self) -> None:
        defs = [{
            "name": "k8s.list_pods",
            "description": "x",
            "risk_level": "read",
            "parameters_schema": {"type": "array"},
        }]
        tools = build_function_tools("http://gw:8080", defs)
        self.assertEqual(
            tools[0].input_schema, {"type": "object", "properties": {}}
        )

    def test_missing_schema_defaults_to_empty_object(self) -> None:
        defs = [{"name": "k8s.noargs", "description": "x", "risk_level": "read"}]
        tools = build_function_tools("http://gw:8080", defs)
        self.assertEqual(
            tools[0].input_schema, {"type": "object", "properties": {}}
        )

    def test_read_only_flag_from_risk_level(self) -> None:
        tools = build_function_tools("http://gw:8080", MOCK_TOOL_DEFINITIONS)
        self.assertTrue(tools[0].is_read_only)

    def test_vetted_read_only_tools_auto_allowed_without_user_confirmation(self) -> None:
        """Regression: AgentScope 2.x defaults custom tools to ASK, which
        stalls a headless SSE stream at RequireUserConfirmEvent. Read-only
        gateway tools on the vetted allow-list must be pre-approved so
        invocations actually run."""
        from agentscope.permission import PermissionBehavior

        tools = build_function_tools("http://gw:8080", MOCK_TOOL_DEFINITIONS)
        decision = _run(tools[0].check_permissions())
        self.assertEqual(decision.behavior, PermissionBehavior.ALLOW)

    def test_read_only_tool_outside_allow_list_still_requires_confirmation(self) -> None:
        """Auto-approval is allow-listed, not blanket: a read-only tool that
        is not vetted keeps the ASK default."""
        from agentscope.permission import PermissionBehavior

        defs = [{
            "name": "k8s.list_secrets",
            "description": "x",
            "risk_level": "read",
            "parameters_schema": {"type": "object"},
        }]
        tools = build_function_tools("http://gw:8080", defs)
        self.assertTrue(tools[0].is_read_only)
        decision = _run(tools[0].check_permissions())
        self.assertEqual(decision.behavior, PermissionBehavior.ASK)

    def test_auto_allow_list_env_override(self) -> None:
        """AGENT_GATEWAY_TOOL_AUTO_ALLOW scopes auto-approval per deployment."""
        from agentscope.permission import PermissionBehavior

        with patch.dict(os.environ, {"AGENT_GATEWAY_TOOL_AUTO_ALLOW": "k8s.get_pod"}):
            tools = build_function_tools("http://gw:8080", MOCK_TOOL_DEFINITIONS)
        # k8s.list_pods is read-only but no longer on the allow-list.
        self.assertEqual(
            _run(tools[0].check_permissions()).behavior,
            PermissionBehavior.ASK,
        )
        self.assertEqual(
            _run(tools[1].check_permissions()).behavior,
            PermissionBehavior.ALLOW,
        )

    def test_non_read_only_tools_still_require_confirmation(self) -> None:
        from agentscope.permission import PermissionBehavior

        defs = [{
            "name": "k8s.restart_pod",
            "description": "x",
            "risk_level": "write",
            "parameters_schema": {"type": "object"},
        }]
        tools = build_function_tools("http://gw:8080", defs)
        self.assertFalse(tools[0].is_read_only)
        decision = _run(tools[0].check_permissions())
        self.assertEqual(decision.behavior, PermissionBehavior.ASK)


class BuildToolkitRegressionTests(unittest.TestCase):
    """Regression: tools must actually register into a real AgentScope Toolkit.

    The prior implementation called ``Toolkit.add()``, which does not exist in
    AgentScope 2.x, silently yielding an empty toolkit and fabricated answers.
    """

    def test_build_toolkit_registers_discovered_tools(self) -> None:
        with patch(
            "agent_service.tools.gateway_tools.discover_tools",
            new_callable=AsyncMock,
        ) as mock_discover:
            mock_discover.return_value = MOCK_TOOL_DEFINITIONS
            toolkit = _run(build_toolkit("http://gw:8080", bearer_token="tok"))

        schemas = _run(toolkit.get_tool_schemas())
        function_schemas = [s for s in schemas if s.get("type") == "function"]
        names = {s["function"]["name"] for s in function_schemas}
        self.assertEqual(names, {"k8s_list_pods", "k8s_get_pod"})
        # Parameters survive end-to-end so the model can actually call them.
        by_name = {s["function"]["name"]: s for s in function_schemas}
        self.assertEqual(
            by_name["k8s_get_pod"]["function"]["parameters"],
            {"type": "object", "required": ["name"], "properties": {}},
        )

    def test_build_gateway_toolkit_empty_definitions(self) -> None:
        toolkit = build_gateway_toolkit([], "http://gw:8080")
        schemas = _run(toolkit.get_tool_schemas())
        self.assertEqual(
            [s for s in schemas if s.get("type") == "function"], []
        )


class RuntimeSettingsToolGatewayTests(unittest.TestCase):
    def test_tool_gateway_url_default_none(self) -> None:
        from agent_service.runtime_settings import RuntimeSettings

        settings = RuntimeSettings()
        self.assertIsNone(settings.tool_gateway_url)

    def test_tool_gateway_url_from_env(self) -> None:
        from agent_service.runtime_settings import RuntimeSettings

        with patch.dict("os.environ", {"TOOL_GATEWAY_URL": "http://gw:8080"}):
            settings = RuntimeSettings.from_env()
        self.assertEqual(settings.tool_gateway_url, "http://gw:8080")
