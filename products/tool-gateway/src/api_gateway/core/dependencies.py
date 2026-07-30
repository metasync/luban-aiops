"""Shared FastAPI dependency providers (SPEC-007 R-2)."""

from __future__ import annotations

from fastapi import HTTPException, Request

from api_gateway.tools.registry import ToolRegistry


def get_tool_registry(request: Request) -> ToolRegistry:
    """Return the tool registry attached to the running application.

    The registry is built once in `create_app()` and stored on `app.state`
    so request handling never depends on module import order.
    """
    registry = getattr(request.app.state, "tool_registry", None)
    if registry is None:
        raise HTTPException(status_code=503, detail="tool registry not initialised")
    return registry
