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
        outcome.headers.setdefault("x-request-id", headers["x-request-id"])
        return outcome


class _JsonResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.headers = {}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _result(tool="k8s.scale_deployment", **overrides):
    return {"tool_name": tool, "status": "success", "data": {},
            "evidence": {"executed_at": "2026-09-23T00:00:00Z", "duration_ms": 1,
                         "risk_level": "write", "source_system": "fixture"}, **overrides}


def _run(coro):
    return asyncio.run(coro)


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.captured: list[dict] = []
        self.outcomes: list = []
        patcher = mock.patch.object(
            executor.httpx,
            "AsyncClient",
            lambda **kwargs: _FakeAsyncClient(self.outcomes, self.captured),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_success_result_passes_through(self) -> None:
        gateway_result = _result()
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
        self.assertEqual(call["headers"]["x-request-id"], "req-1")

    def test_execution_id_is_a_header_not_connector_parameters(self) -> None:
        self.outcomes.append(_JsonResponse(_result()))
        execution_id = "11111111-2222-4333-8444-555555555555"
        _run(executor.execute_tool(_settings(), "k8s.scale_deployment", {}, "tok", "original",
                                   execution_id=execution_id))
        self.assertEqual(self.captured[0]["headers"]["x-execution-id"], execution_id)
        self.assertEqual(self.captured[0]["headers"]["x-request-id"], "original")
        self.assertNotIn("execution_id", self.captured[0]["json"])
        self.assertEqual(self.captured[0]["json"]["parameters"], {})

    def test_session_id_forwarded_in_payload(self) -> None:
        # SPEC-049 R-1: the signed envelope's chat session id rides the
        # gateway payload so a stateful connector keys the resumed write
        # onto the owner's session, not the approver's subject.
        self.outcomes.append(_JsonResponse(_result("web.type")))
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
        self.outcomes.append(_JsonResponse(_result()))
        _run(
            executor.execute_tool(
                _settings(), "k8s.scale_deployment", {"replicas": 3},
                "tok", "req-n",
            )
        )
        self.assertNotIn("session_id", self.captured[0]["json"])

    def test_approval_kind_forwarded_in_payload(self) -> None:
        # SPEC-054 R-2 / ADR-0010: the verified authority provenance rides the
        # gateway payload so the browser write path can tell a per-action
        # approval from a write auto-signed under a session-scoped flow
        # authority, and refuse the latter when no flow is bound any more.
        for kind in ("action", "flow"):
            self.outcomes.append(_JsonResponse(_result("web.click")))
            _run(
                executor.execute_tool(
                    _settings(), "web.click", {"ref": 1}, "tok", f"req-{kind}",
                    session_id="ses-flow-1", approval_kind=kind,
                )
            )
        self.assertEqual(self.captured[0]["json"]["approval_kind"], "action")
        self.assertEqual(self.captured[1]["json"]["approval_kind"], "flow")
        # Forwarding it never disturbs the correlation handle beside it.
        self.assertEqual(self.captured[1]["json"]["session_id"], "ses-flow-1")

    def test_approval_kind_absent_when_envelope_predates_it(self) -> None:
        # An envelope signed before the field forwards nothing: the gateway
        # reads absence as "no extra refusal", so today's behavior stays the
        # default rather than a widening. The field is omitted, never sent empty.
        self.outcomes.append(_JsonResponse(_result()))
        _run(
            executor.execute_tool(
                _settings(), "k8s.scale_deployment", {"replicas": 3},
                "tok", "req-legacy",
            )
        )
        self.assertNotIn("approval_kind", self.captured[0]["json"])

    def test_timeout_is_uncertainty_not_a_tool_report(self) -> None:
        self.outcomes.append(httpx.TimeoutException("slow"))
        with self.assertRaisesRegex(executor.GatewayUncertain, "transport_error"):
            _run(executor.execute_tool(_settings(), "t.x", {}, "tok", "req-2"))
        self.assertEqual(len(self.captured), 1)

    def test_transport_error_is_uncertainty(self) -> None:
        self.outcomes.append(httpx.ConnectError("refused"))
        with self.assertRaisesRegex(executor.GatewayUncertain, "transport_error"):
            _run(executor.execute_tool(_settings(), "t.x", {}, "tok", "req-3"))

    def test_non_json_body_is_uncertainty(self) -> None:
        self.outcomes.append(_JsonResponse(ValueError("not json"), 502))
        with self.assertRaisesRegex(executor.GatewayUncertain, "response_invalid"):
            _run(executor.execute_tool(_settings(), "t.x", {}, "tok", "req-4"))

    def test_missing_gateway_url_fails_closed(self) -> None:
        with self.assertRaisesRegex(executor.GatewayUncertain, "gateway_not_configured"):
            _run(executor.execute_tool(ExecutionSettings(tool_gateway_url=""), "t.x", {}, "tok", "r"))
        self.assertEqual(self.captured, [])

    def test_missing_delegated_token_never_calls_gateway(self) -> None:
        with self.assertRaisesRegex(executor.GatewayUncertain, "credential_missing"):
            _run(executor.execute_tool(_settings(), "t.x", {}, None, "req-5"))
        self.assertEqual(self.captured, [])

    def test_delegated_token_never_reaches_logs(self) -> None:
        self.outcomes.append(httpx.ConnectError("tok-secret in upstream exception"))
        with mock.patch.object(logging.Logger, "_log") as logged:
            with self.assertRaises(executor.GatewayUncertain) as captured:
                _run(executor.execute_tool(_settings(), "t.x", {}, "tok-secret", "req-6"))
        self.assertNotIn("tok-secret", str(captured.exception))
        self.assertNotIn("tok-secret", str(logged.call_args_list))


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
        with self.assertRaises(KeyError):
            executor.map_result_status({})


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    unittest.main()
