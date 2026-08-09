"""Tool trace emission tests (SPEC-011 R-1, R-2)."""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from agent_service.tools.gateway_tools import (
    _make_data_summary,
    build_function_tools,
)


def _run(coro):
    return asyncio.run(coro)


def _build_tool_fn(**kwargs):
    """Return the raw callable wrapped by the first built FunctionTool."""
    tools = build_function_tools(
        "http://gw:8080",
        MOCK_TOOL_DEFINITIONS,
        **kwargs,
    )
    return tools[0]._func


MOCK_TOOL_DEFINITIONS = [
    {
        "name": "k8s.list_pods",
        "description": "List pods in a namespace.",
        "risk_level": "read",
        "category": "kubernetes",
        "parameters_schema": {"type": "object"},
    },
]


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


class TraceEmissionTests(unittest.TestCase):
    """Test tool_call / tool_result trace events from toolkit closures."""

    def test_closure_emits_tool_call_before_and_result_after(self) -> None:
        queue = asyncio.Queue()
        fn = _build_tool_fn(bearer_token="tok", trace_queue=queue)

        mock_result = {
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
        with patch(
            "agent_service.tools.gateway_tools.invoke_gateway_tool",
            new_callable=AsyncMock,
        ) as mock_invoke:
            mock_invoke.return_value = mock_result
            _run(fn(namespace="test"))

        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

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

    def test_no_trace_events_without_queue(self) -> None:
        fn = _build_tool_fn(bearer_token="tok")  # trace_queue=None (default)

        with patch(
            "agent_service.tools.gateway_tools.invoke_gateway_tool",
            new_callable=AsyncMock,
        ) as mock_invoke:
            mock_invoke.return_value = {"status": "success", "data": {}}
            _run(fn())

        # No queue, no events — just verify it doesn't crash.

    def test_trace_event_includes_error_on_failure(self) -> None:
        queue = asyncio.Queue()
        fn = _build_tool_fn(bearer_token="tok", trace_queue=queue)

        mock_result = {
            "tool_name": "k8s.list_pods",
            "status": "error",
            "error": {"code": "K8S_API_ERROR", "message": "timeout"},
            "evidence": {
                "executed_at": "2026-08-05T00:00:00+00:00",
                "duration_ms": 30000,
                "risk_level": "read",
                "source_system": "kubernetes",
            },
        }
        with patch(
            "agent_service.tools.gateway_tools.invoke_gateway_tool",
            new_callable=AsyncMock,
        ) as mock_invoke:
            mock_invoke.return_value = mock_result
            _run(fn())

        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        self.assertEqual(events[1]["type"], "tool_result")
        self.assertEqual(events[1]["status"], "error")
        self.assertEqual(events[1]["error"]["code"], "K8S_API_ERROR")

    def test_data_summary_truncated_in_trace_event(self) -> None:
        queue = asyncio.Queue()
        fn = _build_tool_fn(
            bearer_token="tok",
            trace_queue=queue,
            data_summary_max_chars=50,
        )

        mock_result = {
            "tool_name": "k8s.list_pods",
            "status": "success",
            "data": {"pods": [{"name": "web-1", "phase": "Running"}] * 20},
            "evidence": {"duration_ms": 10, "risk_level": "read"},
        }
        with patch(
            "agent_service.tools.gateway_tools.invoke_gateway_tool",
            new_callable=AsyncMock,
        ) as mock_invoke:
            mock_invoke.return_value = mock_result
            _run(fn())

        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        result_event = events[1]
        summary = result_event["data_summary"]
        self.assertTrue(summary["_truncated"])
        self.assertEqual(len(summary["_preview"]), 50)


class StreamEventContractTests(unittest.TestCase):
    """Validate tool trace events conform to the stream event schema (R-1)."""

    def test_tool_call_event_has_required_fields(self) -> None:
        queue = asyncio.Queue()
        fn = _build_tool_fn(bearer_token="tok", trace_queue=queue)

        with patch(
            "agent_service.tools.gateway_tools.invoke_gateway_tool",
            new_callable=AsyncMock,
        ) as mock_invoke:
            mock_invoke.return_value = {"status": "success", "data": {}}
            _run(fn())

        call_event = queue.get_nowait()
        # tool_call must have type, tool_name, call_id, parameters.
        self.assertEqual(call_event["type"], "tool_call")
        self.assertIsInstance(call_event["tool_name"], str)
        self.assertIsInstance(call_event["call_id"], str)
        self.assertIsInstance(call_event["parameters"], dict)

    def test_tool_result_event_has_required_fields(self) -> None:
        queue = asyncio.Queue()
        fn = _build_tool_fn(bearer_token="tok", trace_queue=queue)

        with patch(
            "agent_service.tools.gateway_tools.invoke_gateway_tool",
            new_callable=AsyncMock,
        ) as mock_invoke:
            mock_invoke.return_value = {
                "status": "success",
                "data": {},
                "evidence": {
                    "executed_at": "2026-08-05T00:00:00+00:00",
                    "duration_ms": 10,
                    "risk_level": "read",
                    "source_system": "kubernetes",
                },
            }
            _run(fn())

        queue.get_nowait()  # skip tool_call
        result_event = queue.get_nowait()
        # tool_result must have type, tool_name, call_id, status.
        self.assertEqual(result_event["type"], "tool_result")
        self.assertIsInstance(result_event["tool_name"], str)
        self.assertIsInstance(result_event["call_id"], str)
        self.assertIn(result_event["status"], {"success", "error", "denied"})
        self.assertIn("evidence", result_event)
