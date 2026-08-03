"""Tool registry unit tests (SPEC-007 R-2)."""

import asyncio
import unittest

from tool_gateway.tools.base import BaseTool, ToolDefinition, ToolResult, build_evidence
from tool_gateway.tools.registry import ToolRegistry


class _EchoTool(BaseTool):
    """Test tool that echoes parameters back."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="test.echo",
            description="Echoes parameters.",
            risk_level="read",
            category="test",
            parameters_schema={"type": "object"},
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        return ToolResult(
            tool_name="test.echo",
            status="success",
            data={"echo": parameters},
            evidence=build_evidence("read", "test", 1),
        )


class ToolRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ToolRegistry()

    def test_register_and_get(self) -> None:
        tool = _EchoTool()
        self.registry.register(tool)
        self.assertIs(self.registry.get("test.echo"), tool)

    def test_get_unknown_returns_none(self) -> None:
        self.assertIsNone(self.registry.get("nonexistent"))

    def test_list_definitions(self) -> None:
        self.registry.register(_EchoTool())
        definitions = self.registry.list_definitions()
        self.assertEqual(len(definitions), 1)
        self.assertEqual(definitions[0].name, "test.echo")
        self.assertEqual(definitions[0].risk_level, "read")

    def test_invoke_success(self) -> None:
        self.registry.register(_EchoTool())
        result = asyncio.run(
            self.registry.invoke("test.echo", {"msg": "hello"}, {})
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data, {"echo": {"msg": "hello"}})

    def test_invoke_unknown_tool_returns_error(self) -> None:
        result = asyncio.run(
            self.registry.invoke("nonexistent", {}, {})
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "TOOL_NOT_FOUND")

    def test_register_overwrites(self) -> None:
        self.registry.register(_EchoTool())
        self.registry.register(_EchoTool())
        self.assertEqual(len(self.registry.list_definitions()), 1)


class ToolDefinitionTests(unittest.TestCase):
    def test_to_dict(self) -> None:
        defn = ToolDefinition(
            name="k8s.list_pods",
            description="List pods.",
            risk_level="read",
            category="kubernetes",
            parameters_schema={"type": "object"},
        )
        d = defn.to_dict()
        self.assertEqual(d["name"], "k8s.list_pods")
        self.assertEqual(d["risk_level"], "read")
        self.assertEqual(d["category"], "kubernetes")


class ToolResultTests(unittest.TestCase):
    def test_to_dict_success(self) -> None:
        result = ToolResult(
            tool_name="test.echo",
            status="success",
            data={"key": "value"},
            evidence=build_evidence("read", "test", 42),
        )
        d = result.to_dict()
        self.assertEqual(d["status"], "success")
        self.assertEqual(d["data"], {"key": "value"})
        self.assertNotIn("error", d)
        self.assertEqual(d["evidence"]["duration_ms"], 42)

    def test_to_dict_error(self) -> None:
        result = ToolResult(
            tool_name="test.fail",
            status="error",
            evidence=build_evidence("read", "test", 0),
            error={"code": "FAIL", "message": "something broke"},
        )
        d = result.to_dict()
        self.assertEqual(d["status"], "error")
        self.assertNotIn("data", d)
        self.assertEqual(d["error"]["code"], "FAIL")
