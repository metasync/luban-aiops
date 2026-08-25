"""Kernel middleware tests (SPEC-018 R-1/R-2/R-3/R-4/R-5).

Middlewares are exercised through their hook signatures with stub
``next_handler``s — no live agentscope agent is required.
"""

import asyncio
import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import jsonschema

from agent_service.services.kernel_middleware import (
    AUTO_ALLOW_ENV,
    TASK_TOOL_NAMES,
    STRUCTURED_OUTPUT_TOOL_NAME,
    TOOL_EVIDENCE_SINK,
    GatewayPermissionMiddleware,
    ToolEvidenceMiddleware,
    _load_auto_allowed_tools,
    _make_data_summary,
    _make_full_data,
)

SCHEMAS_DIR = (
    Path(__file__).resolve().parents[3] / "shared" / "shared-contracts" / "schemas"
)


def _run(coro):
    return asyncio.run(coro)


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / name).read_text())


# --- Stubs -----------------------------------------------------------------


class _StubTool:
    def __init__(self, name, gateway_tool_name=None, is_read_only=True):
        self.name = name
        self.is_read_only = is_read_only
        if gateway_tool_name is not None:
            self.gateway_tool_name = gateway_tool_name


class _StubAgent:
    """Minimal agent stand-in exposing only the toolkit lookup surface."""

    def __init__(self, tools):
        self.toolkit = SimpleNamespace(
            tool_groups=[SimpleNamespace(tools=tools)],
        )


def _permission_next(decision, calls):
    async def next_handler(**kwargs):
        calls.append(kwargs)
        return decision

    return next_handler


def _acting_next(*items):
    async def next_handler(**kwargs):
        for item in items:
            yield item

    return next_handler


def _drain(gen):
    async def _collect():
        items = []
        async for item in gen:
            items.append(item)
        return items

    return asyncio.run(_collect())


def _tool_call_block(tool_name, parameters, call_id="call-1"):
    from agentscope.message import ToolCallBlock

    return ToolCallBlock(
        id=call_id,
        name=tool_name,
        input=json.dumps(parameters),
    )


# --- R-2 helper: data_summary truncation ------------------------------------


class DataSummaryTests(unittest.TestCase):
    """Test data_summary truncation (SPEC-011 R-2, Q-1)."""

    def test_none_data_returns_none(self) -> None:
        self.assertIsNone(_make_data_summary(None))

    def test_small_data_returned_unchanged(self) -> None:
        data = {"pods": [{"name": "web-1"}]}
        result = _make_data_summary(data)
        self.assertEqual(result, data)

    def test_large_data_truncated_with_marker(self) -> None:
        data = {"logs": "x" * 5000}
        result = _make_data_summary(data, max_chars=100)
        self.assertTrue(result["_truncated"])
        self.assertEqual(len(result["_preview"]), 100)
        self.assertGreater(result["_original_length"], 100)

    def test_exact_boundary_not_truncated(self) -> None:
        data = {"key": "val"}
        serialized = json.dumps(data, default=str)
        result = _make_data_summary(data, max_chars=len(serialized))
        self.assertEqual(result, data)

    def test_empty_match_skills_payload_passes_through(self) -> None:
        """SPEC-014 R-5 empty-match contract: a skills.search success with
        no hits keeps its exact shape through the evidence panel pipeline."""
        data = {"matches": [], "total": 0}
        self.assertEqual(_make_data_summary(data), data)

    def test_empty_catalog_skills_payload_passes_through(self) -> None:
        """Same contract for skills.list: an empty catalog keeps its exact
        shape through the evidence panel pipeline."""
        data = {"skills": [], "total": 0}
        self.assertEqual(_make_data_summary(data), data)


class FullDataTests(unittest.TestCase):
    """Test the size-guarded full-payload passthrough (stream schema v5)."""

    def test_none_data_returns_none(self) -> None:
        self.assertIsNone(_make_full_data(None))

    def test_data_within_cap_returned_unchanged(self) -> None:
        data = {"logs": "\n".join(f"line-{i}" for i in range(50))}
        self.assertEqual(_make_full_data(data), data)

    def test_oversized_data_returns_none(self) -> None:
        data = {"logs": "x" * 5000}
        self.assertIsNone(_make_full_data(data, max_chars=100))

    def test_exact_boundary_included(self) -> None:
        data = {"key": "val"}
        serialized = json.dumps(data, default=str)
        self.assertEqual(_make_full_data(data, max_chars=len(serialized)), data)


# --- R-1: permission middleware ---------------------------------------------


class AllowListTests(unittest.TestCase):
    def test_default_allow_list_normalized_to_sanitized_names(self) -> None:
        allow = _load_auto_allowed_tools()
        self.assertIn("k8s_list_pods", allow)
        self.assertIn("skills_search", allow)
        self.assertIn("incidents_get", allow)
        self.assertNotIn("k8s.list_pods", allow)

    def test_env_override_replaces_default(self) -> None:
        with patch.dict(os.environ, {AUTO_ALLOW_ENV: "k8s.get_pod"}):
            self.assertEqual(_load_auto_allowed_tools(), frozenset({"k8s_get_pod"}))

    def test_env_override_empty_approves_nothing(self) -> None:
        with patch.dict(os.environ, {AUTO_ALLOW_ENV: ""}):
            self.assertEqual(_load_auto_allowed_tools(), frozenset())


class GatewayPermissionMiddlewareTests(unittest.TestCase):
    def _decide(self, middleware, tool, next_decision=None, tool_call=None):
        from agentscope.permission import PermissionBehavior, PermissionDecision

        if next_decision is None:
            next_decision = PermissionDecision(
                behavior=PermissionBehavior.ASK, message="stub-ask",
            )
        calls = []
        input_kwargs = {
            "tool": tool, "tool_call": tool_call, "tool_input": {},
        }
        decision = _run(
            middleware.on_check_permission(
                None, input_kwargs, _permission_next(next_decision, calls),
            )
        )
        return decision, calls

    def test_allow_listed_read_only_tool_allowed_without_delegation(self) -> None:
        from agentscope.permission import PermissionBehavior

        mw = GatewayPermissionMiddleware()
        tool = _StubTool("k8s_list_pods", is_read_only=True)
        decision, calls = self._decide(mw, tool)
        self.assertEqual(decision.behavior, PermissionBehavior.ALLOW)
        self.assertEqual(calls, [])  # built-in resolution bypassed

    def test_read_only_tool_outside_allow_list_asks_without_delegation(self) -> None:
        """Auto-approval is allow-listed, not blanket: unvetted read-only
        tools get an explicit ASK. Delegation to the built-in engine is
        bypassed because its read-only fast path auto-allows read-only
        invocations in every mode, silently skipping the allow-list."""
        from agentscope.permission import PermissionBehavior

        mw = GatewayPermissionMiddleware()
        tool = _StubTool("k8s_list_secrets", is_read_only=True)
        decision, calls = self._decide(mw, tool)
        self.assertEqual(decision.behavior, PermissionBehavior.ASK)
        self.assertEqual(calls, [])  # engine fast path never reached

    def test_non_read_only_tool_asks_even_if_name_listed(self) -> None:
        from agentscope.permission import PermissionBehavior

        mw = GatewayPermissionMiddleware(
            auto_allowed=frozenset({"k8s_restart_pod"}),
        )
        tool = _StubTool("k8s_restart_pod", is_read_only=False)
        decision, calls = self._decide(mw, tool)
        self.assertEqual(decision.behavior, PermissionBehavior.ASK)
        self.assertEqual(calls, [])

    def test_missing_tool_still_delegates_to_builtin(self) -> None:
        """Without a tool surface there is nothing to policy-check; the
        built-in resolution is preserved."""
        from agentscope.permission import PermissionBehavior

        mw = GatewayPermissionMiddleware()
        decision, calls = self._decide(mw, None)
        self.assertEqual(decision.behavior, PermissionBehavior.ASK)
        self.assertEqual(len(calls), 1)

    def test_allowed_state_call_delegates_instead_of_re_asking(self) -> None:
        """SPEC-020 resume regression: agentscope re-traverses the
        middleware chain for calls the operator already confirmed (state
        ALLOWED). The middleware must delegate so the built-in resolution
        short-circuits them to ALLOW — an explicit ASK here would re-park
        the resumed reply forever (live check: approve loop on
        k8s.get_pod_logs)."""
        from agentscope.message import ToolCallState
        from agentscope.permission import (
            PermissionBehavior,
            PermissionDecision,
        )

        mw = GatewayPermissionMiddleware()
        tool = _StubTool("k8s_list_secrets", is_read_only=True)
        tool_call = SimpleNamespace(state=ToolCallState.ALLOWED)
        already_allowed = PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="Already allowed by user confirmation.",
        )
        decision, calls = self._decide(
            mw, tool, next_decision=already_allowed, tool_call=tool_call,
        )
        self.assertEqual(decision.behavior, PermissionBehavior.ALLOW)
        self.assertEqual(len(calls), 1)

    def test_pending_state_call_still_asks(self) -> None:
        """Only the ALLOWED state short-circuits; fresh calls (PENDING)
        keep the explicit ASK even when the tool_call block is present."""
        from agentscope.message import ToolCallState
        from agentscope.permission import PermissionBehavior

        mw = GatewayPermissionMiddleware()
        tool = _StubTool("k8s_list_secrets", is_read_only=True)
        tool_call = SimpleNamespace(state=ToolCallState.PENDING)
        decision, calls = self._decide(mw, tool, tool_call=tool_call)
        self.assertEqual(decision.behavior, PermissionBehavior.ASK)
        self.assertEqual(calls, [])

    def test_task_tools_always_allowed(self) -> None:
        """R-5: state-local task tools must never hit the interactive ASK
        gate on a headless stream."""
        from agentscope.permission import PermissionBehavior

        mw = GatewayPermissionMiddleware()
        for name in TASK_TOOL_NAMES:
            tool = _StubTool(name, is_read_only=False)
            decision, calls = self._decide(mw, tool)
            self.assertEqual(decision.behavior, PermissionBehavior.ALLOW)
            self.assertEqual(calls, [])

    def test_structured_output_tool_always_allowed(self) -> None:
        """response_schema turns deliver via the kernel's built-in
        GenerateStructuredOutput tool; parking it wedges every structured
        turn (incident triage) on a headless stream."""
        from agentscope.permission import PermissionBehavior

        mw = GatewayPermissionMiddleware()
        tool = _StubTool(STRUCTURED_OUTPUT_TOOL_NAME, is_read_only=False)
        decision, calls = self._decide(mw, tool)
        self.assertEqual(decision.behavior, PermissionBehavior.ALLOW)
        self.assertEqual(calls, [])

    def test_env_override_scopes_auto_approval(self) -> None:
        from agentscope.permission import PermissionBehavior

        with patch.dict(os.environ, {AUTO_ALLOW_ENV: "k8s.get_pod"}):
            mw = GatewayPermissionMiddleware()
        allowed, _ = self._decide(mw, _StubTool("k8s_get_pod"))
        asked, _ = self._decide(mw, _StubTool("k8s_list_pods"))
        self.assertEqual(allowed.behavior, PermissionBehavior.ALLOW)
        self.assertEqual(asked.behavior, PermissionBehavior.ASK)

    def test_headless_no_stall_parity_for_vetted_tools(self) -> None:
        """Regression: AgentScope 2.x defaults custom function tools to ASK,
        which stalls a headless SSE stream at RequireUserConfirmEvent. Every
        vetted default allow-list entry must resolve to ALLOW through the
        middleware so invocations actually run."""
        from agentscope.permission import PermissionBehavior

        mw = GatewayPermissionMiddleware()
        for sanitized in _load_auto_allowed_tools():
            decision, _ = self._decide(
                mw, _StubTool(sanitized, is_read_only=True),
            )
            self.assertEqual(decision.behavior, PermissionBehavior.ALLOW)


# --- R-2: evidence middleware ------------------------------------------------


class ToolEvidenceMiddlewareTests(unittest.TestCase):
    def _gateway_result(self, status="success"):
        result = {
            "tool_name": "k8s.list_pods",
            "status": status,
            "data": {"pods": []},
            "evidence": {
                "executed_at": "2026-08-05T00:00:00+00:00",
                "duration_ms": 42,
                "risk_level": "read",
                "source_system": "kubernetes",
            },
        }
        if status == "error":
            result["error"] = {"code": "K8S_API_ERROR", "message": "timeout"}
        return result

    def _run_on_acting(self, mw, agent, tool_call, items):
        input_kwargs = {"tool_call": tool_call}
        gen = mw.on_acting(agent, input_kwargs, _acting_next(*items))
        return _drain(gen)

    def _with_sink(self, fn):
        queue = asyncio.Queue()

        async def _scope():
            token = TOOL_EVIDENCE_SINK.set(queue)
            try:
                return await fn(queue)
            finally:
                TOOL_EVIDENCE_SINK.reset(token)

        return asyncio.run(_scope())

    def _emit(self, mw, agent, tool_call, items):
        async def _scope(queue):
            gen = mw.on_acting(
                agent, {"tool_call": tool_call}, _acting_next(*items),
            )
            async for _ in gen:
                pass
            events = []
            while not queue.empty():
                events.append(queue.get_nowait())
            return events

        return self._with_sink(_scope)

    def test_emits_tool_call_and_tool_result_frames(self) -> None:
        from agentscope.message import TextBlock
        from agentscope.tool import ToolChunk, ToolResponse

        result = self._gateway_result()
        tool = _StubTool("k8s_list_pods", gateway_tool_name="k8s.list_pods")
        agent = _StubAgent([tool])
        tool_call = _tool_call_block(
            "k8s_list_pods", {"namespace": "test"},
        )
        items = [
            ToolChunk(
                content=[TextBlock(text=json.dumps(result, default=str))],
                metadata={"gateway_result": result},
            ),
            ToolResponse(metadata={"gateway_result": result}),
        ]
        events = self._emit(
            ToolEvidenceMiddleware(), agent, tool_call, items,
        )

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["type"], "tool_call")
        self.assertEqual(events[0]["tool_name"], "k8s.list_pods")
        self.assertEqual(events[0]["parameters"], {"namespace": "test"})
        self.assertIn("call_id", events[0])

        self.assertEqual(events[1]["type"], "tool_result")
        self.assertEqual(events[1]["tool_name"], "k8s.list_pods")
        self.assertEqual(events[1]["status"], "success")
        self.assertEqual(events[1]["call_id"], events[0]["call_id"])
        self.assertEqual(events[1]["evidence"]["duration_ms"], 42)
        self.assertEqual(events[1]["data_summary"], {"pods": []})

    def test_tool_result_frame_includes_error_on_failure(self) -> None:
        from agentscope.tool import ToolResponse

        result = self._gateway_result(status="error")
        tool = _StubTool("k8s_list_pods", gateway_tool_name="k8s.list_pods")
        agent = _StubAgent([tool])
        tool_call = _tool_call_block("k8s_list_pods", {})
        events = self._emit(
            ToolEvidenceMiddleware(),
            agent,
            tool_call,
            [ToolResponse(metadata={"gateway_result": result})],
        )
        self.assertEqual(events[1]["status"], "error")
        self.assertEqual(events[1]["error"]["code"], "K8S_API_ERROR")

    def test_data_summary_truncated_in_tool_result_frame(self) -> None:
        from agentscope.tool import ToolResponse

        result = {
            "tool_name": "k8s.list_pods",
            "status": "success",
            "data": {"pods": [{"name": "web-1"}] * 20},
        }
        tool = _StubTool("k8s_list_pods", gateway_tool_name="k8s.list_pods")
        agent = _StubAgent([tool])
        tool_call = _tool_call_block("k8s_list_pods", {})
        mw = ToolEvidenceMiddleware(data_summary_max_chars=50)
        events = self._emit(
            mw, agent, tool_call,
            [ToolResponse(metadata={"gateway_result": result})],
        )
        summary = events[1]["data_summary"]
        self.assertTrue(summary["_truncated"])
        self.assertEqual(len(summary["_preview"]), 50)

    def test_tool_result_frame_carries_full_data_within_cap(self) -> None:
        from agentscope.tool import ToolResponse

        result = self._gateway_result()
        tool = _StubTool("k8s_list_pods", gateway_tool_name="k8s.list_pods")
        agent = _StubAgent([tool])
        tool_call = _tool_call_block("k8s_list_pods", {})
        events = self._emit(
            ToolEvidenceMiddleware(), agent, tool_call,
            [ToolResponse(metadata={"gateway_result": result})],
        )
        self.assertEqual(events[1]["data"], {"pods": []})

    def test_tool_result_frame_omits_full_data_when_oversized(self) -> None:
        from agentscope.tool import ToolResponse

        result = self._gateway_result()
        result["data"] = {"logs": "x" * 5000}
        tool = _StubTool("k8s_list_pods", gateway_tool_name="k8s.list_pods")
        agent = _StubAgent([tool])
        tool_call = _tool_call_block("k8s_list_pods", {})
        events = self._emit(
            ToolEvidenceMiddleware(data_max_chars=100), agent, tool_call,
            [ToolResponse(metadata={"gateway_result": result})],
        )
        # The frame stays bounded: no full payload, truncated summary only.
        self.assertNotIn("data", events[1])
        self.assertTrue(events[1]["data_summary"]["_truncated"])

    def test_no_frames_when_sink_unset(self) -> None:
        """Blocking turns (reply_text) never set the sink: the middleware
        passes items through and emits nothing."""
        from agentscope.tool import ToolResponse

        result = self._gateway_result()
        tool = _StubTool("k8s_list_pods", gateway_tool_name="k8s.list_pods")
        agent = _StubAgent([tool])
        tool_call = _tool_call_block("k8s_list_pods", {})
        items = [ToolResponse(metadata={"gateway_result": result})]
        yielded = self._run_on_acting(
            ToolEvidenceMiddleware(), agent, tool_call, items,
        )
        self.assertEqual(yielded, items)

    def test_non_gateway_tool_passes_through_silently(self) -> None:
        """Task tools and builtins emit no evidence frames (parity: only
        gateway closures traced before the middleware migration)."""
        from agentscope.tool import ToolResponse

        tool = _StubTool("TaskCreate", is_read_only=False)
        agent = _StubAgent([tool])
        tool_call = _tool_call_block("TaskCreate", {})
        items = [ToolResponse()]
        events = self._emit(
            ToolEvidenceMiddleware(), agent, tool_call, items,
        )
        self.assertEqual(events, [])

    def test_missing_gateway_result_keeps_frame_schema_valid(self) -> None:
        from agentscope.tool import ToolResponse

        tool = _StubTool("k8s_list_pods", gateway_tool_name="k8s.list_pods")
        agent = _StubAgent([tool])
        tool_call = _tool_call_block("k8s_list_pods", {})
        events = self._emit(
            ToolEvidenceMiddleware(), agent, tool_call, [ToolResponse()],
        )
        self.assertEqual(events[1]["status"], "error")
        self.assertIsNone(events[1]["data_summary"])


class EvidenceFrameSchemaParityTests(unittest.TestCase):
    """Emitted frames validate against agent-stream-event.schema.json
    (SPEC-018 R-2 contract test; the schema file is unmodified)."""

    def test_frames_conform_to_stream_event_schema(self) -> None:
        from agentscope.tool import ToolResponse

        schema = _load_schema("agent-stream-event.schema.json")
        result = {
            "tool_name": "k8s.list_pods",
            "status": "success",
            "data": {"pods": []},
            "evidence": {
                "executed_at": "2026-08-05T00:00:00+00:00",
                "duration_ms": 42,
                "risk_level": "read",
                "source_system": "kubernetes",
            },
        }
        tool = _StubTool("k8s_list_pods", gateway_tool_name="k8s.list_pods")
        agent = _StubAgent([tool])
        tool_call = _tool_call_block("k8s_list_pods", {"namespace": "test"})

        mw = ToolEvidenceMiddleware()

        async def _scope(queue):
            token = TOOL_EVIDENCE_SINK.set(queue)
            try:
                gen = mw.on_acting(
                    agent, {"tool_call": tool_call},
                    _acting_next(ToolResponse(
                        metadata={"gateway_result": result},
                    )),
                )
                async for _ in gen:
                    pass
            finally:
                TOOL_EVIDENCE_SINK.reset(token)

        queue = asyncio.Queue()
        asyncio.run(_scope(queue))

        # stream_events decorates each frame with request/session ids.
        while not queue.empty():
            frame = queue.get_nowait()
            decorated = {
                **frame, "request_id": "req-1", "session_id": "ses-1",
            }
            jsonschema.validate(decorated, schema)


# --- R-3/R-4/R-5: settings-driven middleware + task tool composition --------


class MiddlewareCompositionTests(unittest.TestCase):
    def _kernel(self, **overrides):
        from agent_service.runtime_kernel import AgentKernel
        from agent_service.runtime_settings import RuntimeSettings

        return AgentKernel(
            settings=RuntimeSettings(api_key="test-key", **overrides),
        )

    def test_default_stack_is_permission_and_evidence(self) -> None:
        kernel = self._kernel()
        middlewares = kernel._build_middlewares()
        self.assertEqual(len(middlewares), 2)
        self.assertIsInstance(middlewares[0], GatewayPermissionMiddleware)
        self.assertIsInstance(middlewares[1], ToolEvidenceMiddleware)

    def test_kernel_tracing_adds_tracing_middleware(self) -> None:
        from agentscope.middleware import TracingMiddleware

        kernel = self._kernel(kernel_tracing=True)
        middlewares = kernel._build_middlewares()
        self.assertTrue(
            any(isinstance(mw, TracingMiddleware) for mw in middlewares),
        )

    def test_budget_adds_reply_budget_middleware(self) -> None:
        from agentscope.middleware import ReplyBudgetControlMiddleware

        kernel = self._kernel(
            reply_token_budget=1000.0,
            reply_input_token_weight=0.5,
            reply_output_token_weight=2.0,
        )
        middlewares = kernel._build_middlewares()
        budget = [
            mw for mw in middlewares
            if isinstance(mw, ReplyBudgetControlMiddleware)
        ]
        self.assertEqual(len(budget), 1)
        self.assertEqual(budget[0].token_budget, 1000.0)
        self.assertEqual(budget[0].input_token_weight, 0.5)
        self.assertEqual(budget[0].output_token_weight, 2.0)

    def test_budget_unset_adds_no_budget_middleware(self) -> None:
        from agentscope.middleware import ReplyBudgetControlMiddleware

        kernel = self._kernel()
        self.assertFalse(
            any(
                isinstance(mw, ReplyBudgetControlMiddleware)
                for mw in kernel._build_middlewares()
            ),
        )

    def test_task_tools_registered_when_enabled(self) -> None:
        kernel = self._kernel(task_tools_enabled=True)
        names = {tool.name for tool in kernel._build_task_tools()}
        self.assertEqual(names, TASK_TOOL_NAMES)

    def test_task_tools_absent_when_disabled(self) -> None:
        kernel = self._kernel()
        self.assertFalse(kernel.settings.task_tools_enabled)

    def test_evidence_middleware_receives_summary_limit(self) -> None:
        kernel = self._kernel(tool_data_summary_max_chars=123)
        evidence = [
            mw for mw in kernel._build_middlewares()
            if isinstance(mw, ToolEvidenceMiddleware)
        ][0]
        self.assertEqual(evidence._max_chars, 123)

    def test_evidence_middleware_receives_full_data_limit(self) -> None:
        kernel = self._kernel(tool_data_max_chars=456)
        evidence = [
            mw for mw in kernel._build_middlewares()
            if isinstance(mw, ToolEvidenceMiddleware)
        ][0]
        self.assertEqual(evidence._data_max_chars, 456)


if __name__ == "__main__":
    unittest.main()
