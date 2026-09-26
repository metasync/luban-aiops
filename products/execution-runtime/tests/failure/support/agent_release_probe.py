"""Run the real evidence middleware in its own product environment, without an LLM.

Only counts leave this process. The unsafe variant deliberately replays the old
release predicate at the evidence sink, so the oracle remains useful after the
production middleware is hardened.
"""
import asyncio
import json
import logging
import os
from types import SimpleNamespace
from uuid import uuid4

os.environ["OTEL_SDK_DISABLED"] = "true"
logging.disable(logging.CRITICAL)

from agentscope.message import ToolCallBlock
from agentscope.tool import ToolResponse
from agent_service.services.kernel_middleware import (
    PENDING_RELEASE_DELIVERIES, TOOL_EVIDENCE_SINK, ToolEvidenceMiddleware,
)
from agent_service.tools.gateway_tools import EXECUTION_REQUESTS


async def probe(unsafe):
    frames = []
    held = {"delivery_id": str(uuid4()), "channel": "portal_copy",
            "expires_at": "2099-01-01T00:00:00Z"}

    class Sink:
        async def put(self, frame):
            frames.append(frame)
            if unsafe and frame.get("type") == "tool_result" and frame.get("status") == "success":
                frames.append({"type": "secret_delivery", **held})

    tool = SimpleNamespace(name="web_click", gateway_tool_name="web.click")
    agent = SimpleNamespace(toolkit=SimpleNamespace(tool_groups=[SimpleNamespace(tools=[tool])]))
    call = ToolCallBlock(id="replayed-call", name="web_click", input="{}")
    tokens = [(TOOL_EVIDENCE_SINK, TOOL_EVIDENCE_SINK.set(Sink())),
              (PENDING_RELEASE_DELIVERIES, PENDING_RELEASE_DELIVERIES.set([held])),
              (EXECUTION_REQUESTS, EXECUTION_REQUESTS.set({call.id: {"call_id": call.id}}))]

    async def replay(**kwargs):
        yield ToolResponse(metadata={"gateway_result": {"tool_name": "web.click",
                           "status": "success", "data": {}}, "execution_replay": True})

    try:
        async for _ in ToolEvidenceMiddleware().on_acting(agent, {"tool_call": call}, replay):
            pass
        return {"release_count": sum(f["type"] == "secret_delivery" for f in frames)}
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)


if __name__ == "__main__":
    import sys
    print(json.dumps(asyncio.run(probe("--unsafe" in sys.argv))))
