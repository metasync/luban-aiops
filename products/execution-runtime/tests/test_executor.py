"""Executor result/timeout mapping and token redaction (SPEC-038 R-3)."""

from __future__ import annotations

import asyncio
import logging
import unittest
from unittest import mock

import httpx

from execution_runtime.core.config import ExecutionSettings
from execution_runtime.services import executor


def _settings(**overrides) -> ExecutionSettings:
    return ExecutionSettings(
        tool_gateway_url="http://tool-gateway:8000", **overrides
    )


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient driven by queued outcomes."""

    def __init__(self, outcomes, captured):
        self._outcomes = outcomes
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        self._captured.append({"url": url, "json": json, "headers": headers})
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _JsonResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _run(coro):
    return asyncio.run(coro)


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.captured: list[dict] = []
        self.outcomes: list = []
        patcher = mock.patch.object(
            executor.httpx,
            "AsyncClient",
            lambda timeout=None: _FakeAsyncClient(self.outcomes, self.captured),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_success_result_passes_through(self) -> None:
        gateway_result = {"tool_name": "k8s.scale_deployment", "status": "success"}
        self.outcomes.append(_JsonResponse(gateway_result))
        result = _run(
            executor.execute_tool(
                _settings(), "k8s.scale_deployment", {"replicas": 3}, "tok", "req-1"
            )
        )
        self.assertEqual(result, gateway_result)
        call = self.captured[0]
        self.assertEqual(
            call["url"], "http://tool-gateway:8000/api/v2/tools/invoke"
        )
        # The forwarded x-request-id rides the gateway payload.
        self.assertEqual(call["json"]["request_id"], "req-1")
        self.assertEqual(call["json"]["parameters"], {"replicas": 3})
        self.assertEqual(call["headers"]["Authorization"], "Bearer tok")

    def test_session_id_forwarded_in_payload(self) -> None:
        # SPEC-049 R-1: the signed envelope's chat session id rides the
        # gateway payload so a stateful connector keys the resumed write
        # onto the owner's session, not the approver's subject.
        self.outcomes.append(_JsonResponse({"status": "success"}))
        _run(
            executor.execute_tool(
                _settings(), "web.type", {"ref": 1}, "tok", "req-s",
                session_id="ses-flow-1",
            )
        )
        self.assertEqual(self.captured[0]["json"]["session_id"], "ses-flow-1")

    def test_session_id_absent_when_not_provided(self) -> None:
        # A stateless tool call forwards no session id: the field is
        # omitted, never sent empty.
        self.outcomes.append(_JsonResponse({"status": "success"}))
        _run(
            executor.execute_tool(
                _settings(), "k8s.scale_deployment", {"replicas": 3},
                "tok", "req-n",
            )
        )
        self.assertNotIn("session_id", self.captured[0]["json"])

    def test_timeout_maps_to_structured_timeout(self) -> None:
        self.outcomes.append(httpx.TimeoutException("slow"))
        result = _run(
            executor.execute_tool(_settings(), "t.x", {}, "tok", "req-2")
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "TIMEOUT")
        self.assertEqual(result["request_id"], "req-2")

    def test_transport_error_maps_to_failed_result(self) -> None:
        self.outcomes.append(httpx.ConnectError("refused"))
        result = _run(
            executor.execute_tool(_settings(), "t.x", {}, "tok", "req-3")
        )
        self.assertEqual(result["error"]["code"], "TRANSPORT_ERROR")

    def test_non_json_body_maps_to_failed_result(self) -> None:
        self.outcomes.append(_JsonResponse(ValueError("not json"), 502))
        result = _run(
            executor.execute_tool(_settings(), "t.x", {}, "tok", "req-4")
        )
        self.assertEqual(result["error"]["code"], "BAD_GATEWAY_RESPONSE")

    def test_missing_gateway_url_fails_closed(self) -> None:
        result = _run(
            executor.execute_tool(
                ExecutionSettings(tool_gateway_url=""), "t.x", {}, "tok", "r"
            )
        )
        self.assertEqual(result["error"]["code"], "NO_GATEWAY")
        self.assertEqual(self.captured, [])

    def test_missing_delegated_token_never_calls_gateway(self) -> None:
        result = _run(
            executor.execute_tool(_settings(), "t.x", {}, None, "req-5")
        )
        self.assertEqual(result["error"]["code"], "NO_CREDENTIAL")
        self.assertEqual(self.captured, [])

    def test_delegated_token_never_reaches_logs(self) -> None:
        self.outcomes.append(httpx.ConnectError("connection refused"))
        with self.assertLogs(executor.LOGGER, level="WARNING") as captured:
            _run(
                executor.execute_tool(
                    _settings(), "t.x", {}, "tok-secret", "req-6"
                )
            )
        joined = "\n".join(captured.output)
        self.assertNotIn("tok-secret", joined)


class ResultStatusMappingTests(unittest.TestCase):
    def test_success_maps_to_succeeded(self) -> None:
        self.assertEqual(
            executor.map_result_status({"status": "success"}), "succeeded"
        )

    def test_timeout_error_maps_to_timeout(self) -> None:
        self.assertEqual(
            executor.map_result_status(
                {"status": "error", "error": {"code": "TIMEOUT"}}
            ),
            "timeout",
        )

    def test_other_errors_map_to_failed(self) -> None:
        self.assertEqual(
            executor.map_result_status(
                {"status": "error", "error": {"code": "DENIED"}}
            ),
            "failed",
        )
        self.assertEqual(executor.map_result_status({}), "failed")


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    unittest.main()
