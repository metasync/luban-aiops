"""Tool registry — in-process lookup and dispatch (SPEC-007 R-2)."""

from __future__ import annotations

import logging

from tool_gateway.tools.base import (
    VALID_RISK_LEVELS,
    BaseTool,
    ToolDefinition,
    ToolResult,
    make_error_result,
)

LOGGER = logging.getLogger(__name__)


class ToolRegistry:
    """Holds registered tools and dispatches invocations by name.

    Risk-tier admission (SPEC-021 R-1): every definition's ``risk_level``
    must belong to the validated vocabulary, and mutating (write/admin)
    tools are refused registration unless ``allow_mutating`` is set — the
    mechanical backstop behind ``GATEWAY_MUTATING_TOOLS_ENABLED``.
    """

    def __init__(self, allow_mutating: bool = False) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._allow_mutating = allow_mutating

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance. Overwrites if name already exists."""
        definition = tool.definition
        if definition.risk_level not in VALID_RISK_LEVELS:
            raise ValueError(
                f"tool '{definition.name}' declares invalid risk_level "
                f"{definition.risk_level!r}; expected one of "
                f"{sorted(VALID_RISK_LEVELS)}"
            )
        if definition.risk_level != "read" and not self._allow_mutating:
            LOGGER.info(
                "mutating tool not registered (GATEWAY_MUTATING_TOOLS_ENABLED is off): %s",
                definition.name,
            )
            return
        name = definition.name
        if name in self._tools:
            LOGGER.warning("overwriting existing tool registration: %s", name)
        self._tools[name] = tool
        LOGGER.info(
            "registered tool: %s (%s, risk=%s)",
            name,
            definition.category,
            definition.risk_level,
        )

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
