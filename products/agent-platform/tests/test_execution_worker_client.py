"""Execution worker handoff client tests (SPEC-038 R-4)."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from agent_service.runtime_settings import RuntimeSettings
from agent_service.services.execution_worker_client import (
    REASON_WORKER_UNAVAILABLE,
    WorkerHandoffError,
    WorkerHandoffTimeout,
    handoff,
)


def _run(coro):
    return asyncio.run(coro)


def _settings(**overrides) -> RuntimeSettings:
    kwargs = {
        "execution_worker_url": "http://execution-runtime:8000",
        "execution_handoff_token": "handoff-secret",
        "execution_worker_timeout_seconds": 60.0,
    }
    kwargs.update(overrides)
    return RuntimeSettings(**kwargs)


def _request() -> dict:
    return {
        "execution_id": "exec-1",
        "confirm_id": "cf-1",
        "call_id": "call-1",
        "session_id": "ses-1",
        "tool_name": "k8s.scale_deployment",
        "args_digest": "d" * 64,
        "requested_at": "2026-08-27T10:00:00Z",
        "signature": "f" * 64,
    }


def _mock_client(response=None, post_side_effect=None):
    mock_client = AsyncMock()
    if post_side_effect is not None:
        mock_client.post.side_effect = post_side_effect
    else:
        mock_client.post.return_value = response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class HandoffHappyPathTests(unittest.TestCase):
    def test_success_returns_worker_result(self) -> None:
        gateway_result = {"tool_name": "k8s.scale_deployment", "status": "success"}
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "receipt": {"execution_id": "exec-1", "status": "succeeded"},
            "result": gateway_result,
        }
        with patch(
            "agent_service.services.execution_worker_client.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_client = _mock_client(response=response)
            mock_client_cls.return_value = mock_client
            result = _run(
                handoff(
                    request=_request(),
                    arguments={"replicas": 3},
                    delegated_token="confirmer-token",
                    settings=_settings(),
                    request_id="req-1",
                )
            )
        self.assertEqual(result, gateway_result)

    def test_request_carries_bearer_token_request_id_and_body(self) -> None:
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"receipt": {}, "result": {"status": "success"}}
        with patch(
            "agent_service.services.execution_worker_client.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_client = _mock_client(response=response)
            mock_client_cls.return_value = mock_client
            _run(
                handoff(
                    request=_request(),
                    arguments={"replicas": 3},
                    delegated_token="confirmer-token",
                    settings=_settings(execution_worker_timeout_seconds=45.0),
                    request_id="req-1",
                )
            )
        # The client budget comes from the settings knob.
        self.assertEqual(
            mock_client_cls.call_args[1]["timeout"], 45.0
        )
        call_args = mock_client.post.call_args
        self.assertEqual(
            call_args[0][0],
            "http://execution-runtime:8000/api/v1/executions/handoff",
        )
        headers = call_args[1]["headers"]
        self.assertEqual(headers["Authorization"], "Bearer handoff-secret")
        self.assertEqual(headers["x-request-id"], "req-1")
        body = call_args[1]["json"]
        self.assertEqual(body["request"], _request())
        self.assertEqual(body["arguments"], {"replicas": 3})
        self.assertEqual(body["delegated_token"], "confirmer-token")


class HandoffFailClosedTests(unittest.TestCase):
    def _assert_rejects(self, settings, *, expect_network: bool = False):
        with patch(
            "agent_service.services.execution_worker_client.httpx.AsyncClient"
        ) as mock_client_cls:
            with self.assertRaises(WorkerHandoffError) as captured:
                _run(
                    handoff(
                        request=_request(),
                        arguments={},
                        delegated_token="tok",
                        settings=settings,
                    )
                )
        self.assertEqual(captured.exception.reason, REASON_WORKER_UNAVAILABLE)
        if expect_network:
            return mock_client_cls
        mock_client_cls.assert_not_called()
        return mock_client_cls

    def test_missing_settings_rejects_before_network(self) -> None:
        self._assert_rejects(None)

    def test_missing_worker_url_rejects_before_network(self) -> None:
        self._assert_rejects(_settings(execution_worker_url=None))

    def test_missing_handoff_token_rejects_before_network(self) -> None:
        self._assert_rejects(_settings(execution_handoff_token=None))

    def test_transport_error_rejects_worker_unavailable(self) -> None:
        with patch(
            "agent_service.services.execution_worker_client.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_client = _mock_client(
                post_side_effect=httpx.ConnectError("connection refused")
            )
            mock_client_cls.return_value = mock_client
            with self.assertRaises(WorkerHandoffError) as captured:
                _run(
                    handoff(
                        request=_request(),
                        arguments={},
                        delegated_token="tok",
                        settings=_settings(),
                    )
                )
        self.assertEqual(captured.exception.reason, REASON_WORKER_UNAVAILABLE)

    def test_timeout_raises_worker_handoff_timeout(self) -> None:
        with patch(
            "agent_service.services.execution_worker_client.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_client = _mock_client(
                post_side_effect=httpx.ReadTimeout("read timed out")
            )
            mock_client_cls.return_value = mock_client
            with self.assertRaises(WorkerHandoffTimeout):
                _run(
                    handoff(
                        request=_request(),
                        arguments={},
                        delegated_token="tok",
                        settings=_settings(),
                    )
                )

    def test_malformed_success_payload_rejects(self) -> None:
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"receipt": {}}  # no result dict
        self._assert_rejects_response(response)

    def _assert_rejects_response(self, response):
        with patch(
            "agent_service.services.execution_worker_client.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_client = _mock_client(response=response)
            mock_client_cls.return_value = mock_client
            with self.assertRaises(WorkerHandoffError) as captured:
                _run(
                    handoff(
                        request=_request(),
                        arguments={},
                        delegated_token="tok",
                        settings=_settings(),
                    )
                )
        self.assertEqual(captured.exception.reason, REASON_WORKER_UNAVAILABLE)


class HandoffWorkerRejectionTests(unittest.TestCase):
    def _reject(self, status_code: int, body) -> WorkerHandoffError:
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = body
        with patch(
            "agent_service.services.execution_worker_client.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_client = _mock_client(response=response)
            mock_client_cls.return_value = mock_client
            with self.assertRaises(WorkerHandoffError) as captured:
                _run(
                    handoff(
                        request=_request(),
                        arguments={},
                        delegated_token="tok",
                        settings=_settings(),
                    )
                )
        return captured.exception

    def test_worker_401_carries_unauthorized_reason(self) -> None:
        exc = self._reject(
            401, {"error": {"code": "EXECUTION_REJECTED", "reason": "unauthorized"}}
        )
        self.assertEqual(exc.reason, "unauthorized")

    def test_worker_400_carries_signature_reason(self) -> None:
        exc = self._reject(
            400,
            {"error": {"code": "EXECUTION_REJECTED", "reason": "signature_invalid"}},
        )
        self.assertEqual(exc.reason, "signature_invalid")

    def test_unparsable_rejection_degrades_to_worker_unavailable(self) -> None:
        exc = self._reject(502, None)
        self.assertEqual(exc.reason, REASON_WORKER_UNAVAILABLE)


class HandoffLogRedactionTests(unittest.TestCase):
    def test_tokens_never_appear_in_logs(self) -> None:
        with patch(
            "agent_service.services.execution_worker_client.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_client = _mock_client(
                post_side_effect=httpx.ConnectError("connection refused")
            )
            mock_client_cls.return_value = mock_client
            with self.assertLogs(
                "agent_service.services.execution_worker_client", level="DEBUG"
            ) as captured:
                with self.assertRaises(WorkerHandoffError):
                    _run(
                        handoff(
                            request=_request(),
                            arguments={},
                            delegated_token="delegated-super-secret",
                            settings=_settings(
                                execution_handoff_token="handoff-super-secret"
                            ),
                        )
                    )
        joined = "\n".join(captured.output)
        self.assertNotIn("handoff-super-secret", joined)
        self.assertNotIn("delegated-super-secret", joined)


if __name__ == "__main__":
    unittest.main()
