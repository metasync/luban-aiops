"""Base abstractions for the tool execution framework (SPEC-007 R-2)."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class ToolDefinition:
    """Metadata describing a registered tool."""

    name: str
    description: str
    risk_level: str  # "read" | "write" | "admin"
    category: str  # e.g. "kubernetes"
    parameters_schema: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "risk_level": self.risk_level,
            "category": self.category,
            "parameters_schema": self.parameters_schema,
        }


@dataclass
class ToolResult:
    """Structured result envelope matching tool-result.schema.json."""

    tool_name: str
    status: str  # "success" | "error" | "denied"
    data: dict | None = None
    evidence: dict = field(default_factory=dict)
    error: dict | None = None

    def to_dict(self) -> dict:
        result: dict = {
            "tool_name": self.tool_name,
            "status": self.status,
            "evidence": self.evidence,
        }
        if self.data is not None:
            result["data"] = self.data
        if self.error is not None:
            result["error"] = self.error
        return result


def build_evidence(
    risk_level: str,
    source_system: str,
    duration_ms: int,
) -> dict:
    """Build the evidence sub-object for a tool result."""
    return {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": duration_ms,
        "risk_level": risk_level,
        "source_system": source_system,
    }


def make_error_result(
    tool_name: str,
    code: str,
    message: str,
    risk_level: str = "read",
    source_system: str = "platform",
    duration_ms: int = 0,
) -> ToolResult:
    """Create a structured error result."""
    return ToolResult(
        tool_name=tool_name,
        status="error",
        evidence=build_evidence(risk_level, source_system, duration_ms),
        error={"code": code, "message": message},
    )


def make_denied_result(
    tool_name: str,
    reason: str,
) -> ToolResult:
    """Create a structured policy-denied result."""
    return ToolResult(
        tool_name=tool_name,
        status="denied",
        evidence=build_evidence("read", "platform", 0),
        error={"code": "POLICY_DENIED", "message": reason},
    )


class BaseTool(ABC):
    """Abstract base class for executable tools."""

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Return the tool's metadata definition."""

    @abstractmethod
    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        """Execute the tool with the given parameters and identity context.

        Implementations should measure their own execution time and build
        the evidence envelope using build_evidence().
        """

    async def _timed_execute(self, parameters: dict, identity: dict) -> ToolResult:
        """Wrapper that times execution — convenience for simple tools."""
        start = time.perf_counter()
        result = await self.execute(parameters, identity)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        if not result.evidence:
            result.evidence = build_evidence(
                self.definition.risk_level,
                self.definition.category,
                elapsed_ms,
            )
        return result
