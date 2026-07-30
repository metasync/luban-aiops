"""Tool registry — in-process lookup and dispatch (SPEC-007 R-2)."""

from __future__ import annotations

import logging

from api_gateway.tools.base import BaseTool, ToolDefinition, ToolResult, make_error_result

LOGGER = logging.getLogger(__name__)


class ToolRegistry:
    """Holds registered tools and dispatches invocations by name."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance. Overwrites if name already exists."""
        name = tool.definition.name
        if name in self._tools:
            LOGGER.warning("overwriting existing tool registration: %s", name)
        self._tools[name] = tool
        LOGGER.info("registered tool: %s (%s)", name, tool.definition.category)

    def get(self, name: str) -> BaseTool | None:
        """Look up a tool by name. Returns None if not found."""
        return self._tools.get(name)

    def list_definitions(self) -> list[ToolDefinition]:
        """Return metadata for all registered tools."""
        return [tool.definition for tool in self._tools.values()]

    async def invoke(self, name: str, parameters: dict, identity: dict) -> ToolResult:
        """Dispatch an invocation to the named tool.

        Unknown tools and tools that raise both yield a structured error
        result, so callers always receive a tool-result envelope.
        """
        tool = self._tools.get(name)
        if tool is None:
            return make_error_result(
                tool_name=name,
                code="TOOL_NOT_FOUND",
                message=f"No tool registered with name '{name}'.",
            )
        try:
            return await tool.execute(parameters, identity)
        except Exception as exc:
            LOGGER.exception("tool execution failed: %s", name)
            return make_error_result(
                tool_name=name,
                code="TOOL_EXECUTION_ERROR",
                message=str(exc),
                risk_level=tool.definition.risk_level,
                source_system=tool.definition.category,
            )
