"""Gateway tools integration tests (SPEC-007 R-6, SPEC-008 R-5)."""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

from agent_service.tools.gateway_tools import (
    build_toolkit_functions,
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


class BuildToolkitFunctionsTests(unittest.TestCase):
    def test_builds_functions_for_each_tool(self) -> None:
        functions = build_toolkit_functions("http://gw:8080", MOCK_TOOL_DEFINITIONS)
        self.assertEqual(len(functions), 2)
        self.assertEqual(functions[0][0], "k8s.list_pods")
        self.assertEqual(functions[1][0], "k8s.get_pod")

    def test_function_names_are_sanitized(self) -> None:
        functions = build_toolkit_functions("http://gw:8080", MOCK_TOOL_DEFINITIONS)
        _, fn = functions[0]
        self.assertEqual(fn.__name__, "k8s_list_pods")

    def test_function_docstring_set(self) -> None:
        functions = build_toolkit_functions("http://gw:8080", MOCK_TOOL_DEFINITIONS)
        _, fn = functions[0]
        self.assertEqual(fn.__doc__, "List pods in a namespace.")

    def test_function_binds_token_into_closure(self) -> None:
        functions = build_toolkit_functions(
            "http://gw:8080", MOCK_TOOL_DEFINITIONS, bearer_token="user-token"
        )
        _, fn = functions[0]

        mock_result = {"status": "success", "data": {"pods": []}}
        with patch(
            "agent_service.tools.gateway_tools.invoke_gateway_tool",
            new_callable=AsyncMock,
        ) as mock_invoke:
            mock_invoke.return_value = mock_result
            result_str = _run(fn(namespace="test"))

        result = json.loads(result_str)
        self.assertEqual(result["status"], "success")
        mock_invoke.assert_called_once_with(
            gateway_url="http://gw:8080",
            tool_name="k8s.list_pods",
            parameters={"namespace": "test"},
            bearer_token="user-token",
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
