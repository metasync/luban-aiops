"""Gateway tools integration tests (SPEC-007 R-6, SPEC-008 R-5, SPEC-018 R-2)."""

import asyncio
import json
import os
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

from agent_service.services.execution_signing import canonical_digest
from agent_service.services.execution_worker_client import (
    WorkerHandoffError,
    WorkerHandoffTimeout,
)
from agent_service.services.kernel_middleware import AUTO_ALLOW_ENV
from agent_service.tools.gateway_tools import (
    CURRENT_CALL_ID,
    DELEGATED_TOKEN,
    EXECUTION_AUDIT_CONTEXT,
    EXECUTION_REJECTION,
    EXECUTION_REQUESTS,
    _make_tool_fn,
    build_function_tools,
    build_gateway_toolkit,
    build_toolkit,
    discover_tools,
    invoke_gateway_tool,
)


def _run(coro):
    return asyncio.run(coro)


MOCK_TOOL_DEFINITIONS = [
    {
        "name": "k8s.list_pods",
        "description": "List pods in a namespace.",
        "risk_level": "read",
        "category": "kubernetes",
        "parameters_schema": {"type": "object"},
    },
    {
        "name": "k8s.get_pod",
        "description": "Get pod details.",
        "risk_level": "read",
        "category": "kubernetes",
        "parameters_schema": {"type": "object", "required": ["name"]},
    },
]


def _mock_client(response=None, get_side_effect=None):
    mock_client = AsyncMock()
    if get_side_effect is not None:
        mock_client.get.side_effect = get_side_effect
    else:
        mock_client.get.return_value = response
    mock_client.post.return_value = response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class DiscoverToolsTests(unittest.TestCase):
    def test_discover_success_sends_bearer_header(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = MOCK_TOOL_DEFINITIONS
        mock_response.raise_for_status = MagicMock()

        with patch("agent_service.tools.gateway_tools.httpx.AsyncClient") as mock_client_cls:
            mock_client = _mock_client(response=mock_response)
            mock_client_cls.return_value = mock_client

            tools = _run(discover_tools("http://gateway:8080", bearer_token="delegated-token"))

        self.assertEqual(len(tools), 2)
        self.assertEqual(tools[0]["name"], "k8s.list_pods")
        headers = mock_client.get.call_args[1]["headers"]
        self.assertEqual(headers["Authorization"], "Bearer delegated-token")

    def test_discover_without_token_returns_empty_no_network(self) -> None:
        with patch("agent_service.tools.gateway_tools.httpx.AsyncClient") as mock_client_cls:
            tools = _run(discover_tools("http://gateway:8080"))

        self.assertEqual(tools, [])
        mock_client_cls.assert_not_called()

    def test_discover_failure_returns_empty(self) -> None:
        with patch("agent_service.tools.gateway_tools.httpx.AsyncClient") as mock_client_cls:
            mock_client = _mock_client(get_side_effect=Exception("connection refused"))
            mock_client_cls.return_value = mock_client

            tools = _run(discover_tools("http://gateway:8080", bearer_token="tok"))

        self.assertEqual(tools, [])


class InvokeGatewayToolTests(unittest.TestCase):
    def test_invoke_sends_bearer_header_and_no_identity_in_body(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "success", "data": {}}

        with patch("agent_service.tools.gateway_tools.httpx.AsyncClient") as mock_client_cls:
            mock_client = _mock_client(response=mock_response)
            mock_client_cls.return_value = mock_client

            result = _run(invoke_gateway_tool(
                gateway_url="http://gateway:8080",
                tool_name="k8s.list_pods",
                parameters={"namespace": "prod"},
                bearer_token="delegated-token",
            ))

        self.assertEqual(result["status"], "success")
        call_args = mock_client.post.call_args
        self.assertIn("/api/v2/tools/invoke", call_args[0][0])
        # Bearer header is presented; identity is carried by the token only.
        headers = call_args[1]["headers"]
        self.assertEqual(headers["Authorization"], "Bearer delegated-token")
        payload = call_args[1]["json"]
        self.assertEqual(payload["tool_name"], "k8s.list_pods")
        self.assertEqual(payload["parameters"], {"namespace": "prod"})
        self.assertIn("request_id", payload)
        # identity_context must never appear in the body (SPEC-008 R-5).
        self.assertNotIn("identity_context", payload)

    def test_invoke_without_token_returns_structured_error(self) -> None:
        with patch("agent_service.tools.gateway_tools.httpx.AsyncClient") as mock_client_cls:
            result = _run(invoke_gateway_tool(
                gateway_url="http://gateway:8080",
                tool_name="k8s.list_pods",
                parameters={},
            ))

        # No network call is made; a structured error is returned, never raised.
        mock_client_cls.assert_not_called()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "NO_CREDENTIAL")
        self.assertEqual(result["tool_name"], "k8s.list_pods")


class MakeToolFnTests(unittest.TestCase):
    """The closure factory: metadata and token carriage (SPEC-018 R-2)."""

    def test_function_name_sanitized(self) -> None:
        fn = _make_tool_fn("http://gw:8080", "k8s.list_pods", "List pods.")
        self.assertEqual(fn.__name__, "k8s_list_pods")

    def test_function_docstring_set(self) -> None:
        fn = _make_tool_fn(
            "http://gw:8080", "k8s.list_pods", "List pods in a namespace.",
        )
        self.assertEqual(fn.__doc__, "List pods in a namespace.")

    def test_closure_reads_token_contextvar_and_dotted_name(self) -> None:
        """The delegated token rides the DELEGATED_TOKEN contextvar (set per
        turn by the kernel), so cached toolkits survive token refresh."""
        fn = _make_tool_fn("http://gw:8080", "k8s.list_pods", "d")
        mock_result = {"status": "success", "data": {"pods": []}}
        with patch(
            "agent_service.tools.gateway_tools.invoke_gateway_tool",
            new_callable=AsyncMock,
        ) as mock_invoke:
            mock_invoke.return_value = mock_result
            token_var = DELEGATED_TOKEN.set("user-token")
            try:
                chunk = _run(fn(namespace="test"))
            finally:
                DELEGATED_TOKEN.reset(token_var)

        # The gateway receives the ORIGINAL dotted tool name; identity rides on
        # the token only (never in the body).
        mock_invoke.assert_called_once_with(
            gateway_url="http://gw:8080",
            tool_name="k8s.list_pods",
            parameters={"namespace": "test"},
            bearer_token="user-token",
        )
        # The ToolChunk carries the gateway result on its metadata for the
        # evidence middleware, and the model-visible text is the JSON result.
        self.assertEqual(chunk.metadata["gateway_result"], mock_result)
        self.assertEqual(
            json.loads(chunk.content[0].text),
            mock_result,
        )

    def test_closure_without_token_contextvar_passes_none(self) -> None:
        fn = _make_tool_fn("http://gw:8080", "k8s.list_pods", "d")
        with patch(
            "agent_service.tools.gateway_tools.invoke_gateway_tool",
            new_callable=AsyncMock,
        ) as mock_invoke:
            mock_invoke.return_value = {"status": "error"}
            _run(fn())
        self.assertIsNone(mock_invoke.call_args[1]["bearer_token"])


class BuildFunctionToolsTests(unittest.TestCase):
    def test_builds_function_tool_per_definition(self) -> None:
        from agentscope.tool import FunctionTool

        tools = build_function_tools("http://gw:8080", MOCK_TOOL_DEFINITIONS)
        self.assertEqual(len(tools), 2)
        self.assertTrue(all(isinstance(t, FunctionTool) for t in tools))

    def test_tool_names_sanitized(self) -> None:
        tools = build_function_tools("http://gw:8080", MOCK_TOOL_DEFINITIONS)
        self.assertEqual(tools[0].name, "k8s_list_pods")
        self.assertEqual(tools[1].name, "k8s_get_pod")

    def test_input_schema_bound_from_definition(self) -> None:
        tools = build_function_tools("http://gw:8080", MOCK_TOOL_DEFINITIONS)
        # Normalized: AgentScope requires an object schema with a properties
        # dict, so one is filled in when the gateway omits it.
        self.assertEqual(
            tools[1].input_schema,
            {"type": "object", "required": ["name"], "properties": {}},
        )

    def test_schema_without_properties_normalized(self) -> None:
        defs = [{
            "name": "k8s.list_pods",
            "description": "x",
            "risk_level": "read",
            "parameters_schema": {"type": "object"},
        }]
        tools = build_function_tools("http://gw:8080", defs)
        self.assertEqual(
            tools[0].input_schema, {"type": "object", "properties": {}}
        )

    def test_non_object_schema_replaced_with_default(self) -> None:
        defs = [{
            "name": "k8s.list_pods",
            "description": "x",
            "risk_level": "read",
            "parameters_schema": {"type": "array"},
        }]
        tools = build_function_tools("http://gw:8080", defs)
        self.assertEqual(
            tools[0].input_schema, {"type": "object", "properties": {}}
        )

    def test_missing_schema_defaults_to_empty_object(self) -> None:
        defs = [{"name": "k8s.noargs", "description": "x", "risk_level": "read"}]
        tools = build_function_tools("http://gw:8080", defs)
        self.assertEqual(
            tools[0].input_schema, {"type": "object", "properties": {}}
        )

    def test_read_only_flag_from_risk_level(self) -> None:
        tools = build_function_tools("http://gw:8080", MOCK_TOOL_DEFINITIONS)
        self.assertTrue(tools[0].is_read_only)

    def test_gateway_tool_name_carries_dotted_name(self) -> None:
        """SPEC-018 R-2: each tool stashes its dotted gateway name so the
        evidence middleware can emit frames with the original tool name."""
        tools = build_function_tools("http://gw:8080", MOCK_TOOL_DEFINITIONS)
        self.assertEqual(tools[0].gateway_tool_name, "k8s.list_pods")
        self.assertEqual(tools[1].gateway_tool_name, "k8s.get_pod")

    def test_tools_are_plain_function_tools(self) -> None:
        """SPEC-018 R-1: permission decisions moved to
        GatewayPermissionMiddleware; no FunctionTool subclass remains."""
        from agentscope.tool import FunctionTool

        tools = build_function_tools("http://gw:8080", MOCK_TOOL_DEFINITIONS)
        for tool in tools:
            self.assertEqual(type(tool), FunctionTool)

    def test_skills_tool_names_sanitized(self) -> None:
        """SPEC-014 R-5: skills tools keep sanitized FunctionTool names."""
        defs = [
            {
                "name": "skills.search",
                "description": "Search skills.",
                "risk_level": "read",
                "category": "skills",
                "parameters_schema": {"type": "object"},
            },
            {
                "name": "skills.get",
                "description": "Fetch one skill.",
                "risk_level": "read",
                "category": "skills",
                "parameters_schema": {"type": "object"},
            },
            {
                "name": "skills.list",
                "description": "List registered skills.",
                "risk_level": "read",
                "category": "skills",
                "parameters_schema": {"type": "object"},
            },
        ]
        tools = build_function_tools("http://gw:8080", defs)
        self.assertEqual(tools[0].name, "skills_search")
        self.assertEqual(tools[1].name, "skills_get")
        self.assertEqual(tools[2].name, "skills_list")

    def test_incidents_tool_names_sanitized(self) -> None:
        """SPEC-015 R-4: incidents tools keep sanitized FunctionTool names."""
        defs = [
            {
                "name": "incidents.list",
                "description": "List tracked incidents.",
                "risk_level": "read",
                "category": "incidents",
                "parameters_schema": {"type": "object"},
            },
            {
                "name": "incidents.get",
                "description": "Fetch one incident with its triage report.",
                "risk_level": "read",
                "category": "incidents",
                "parameters_schema": {"type": "object"},
            },
        ]
        tools = build_function_tools("http://gw:8080", defs)
        self.assertEqual(tools[0].name, "incidents_list")
        self.assertEqual(tools[1].name, "incidents_get")

    def test_non_read_only_flag_from_risk_level(self) -> None:
        defs = [{
            "name": "k8s.restart_pod",
            "description": "x",
            "risk_level": "write",
            "parameters_schema": {"type": "object"},
        }]
        tools = build_function_tools("http://gw:8080", defs)
        self.assertFalse(tools[0].is_read_only)

    def test_gateway_risk_level_carries_risk_tier(self) -> None:
        """SPEC-021 R-3: the risk tier rides each tool so parked
        confirmations can flag mutating calls on their stream frames."""
        defs = [
            {
                "name": "k8s.list_pods",
                "description": "x",
                "risk_level": "read",
                "parameters_schema": {"type": "object"},
            },
            {
                "name": "k8s.delete_pod",
                "description": "x",
                "risk_level": "write",
                "parameters_schema": {"type": "object"},
            },
        ]
        tools = build_function_tools("http://gw:8080", defs)
        self.assertEqual(tools[0].gateway_risk_level, "read")
        self.assertEqual(tools[1].gateway_risk_level, "write")


class MutatingAutoAllowExclusionTests(unittest.TestCase):
    """Auto-allow is read-only by construction (SPEC-021 R-3)."""

    _WRITE_DEF = {
        "name": "k8s.delete_pod",
        "description": "Delete one pod.",
        "risk_level": "write",
        "parameters_schema": {"type": "object"},
    }

    def test_mutating_tool_in_auto_allow_list_is_logged(self) -> None:
        with patch.dict(os.environ, {AUTO_ALLOW_ENV: "k8s.delete_pod"}):
            with self.assertLogs(
                "agent_service.tools.gateway_tools", level="WARNING"
            ) as captured:
                build_gateway_toolkit([self._WRITE_DEF], "http://gw:8080")
        self.assertTrue(
            any("read-only" in line and "k8s.delete_pod" in line
                for line in captured.output),
            captured.output,
        )

    def test_mutating_tool_still_registered_despite_exclusion_log(self) -> None:
        """Exclusion from auto-approval is not exclusion from the toolkit:
        the tool stays available and parks for HITL confirmation."""
        with patch.dict(os.environ, {AUTO_ALLOW_ENV: "k8s.delete_pod"}):
            toolkit = build_gateway_toolkit([self._WRITE_DEF], "http://gw:8080")
        schemas = _run(toolkit.get_tool_schemas())
        names = {
            s["function"]["name"]
            for s in schemas
            if s.get("type") == "function"
        }
        self.assertEqual(names, {"k8s_delete_pod"})

    def test_read_tool_in_auto_allow_list_not_warned(self) -> None:
        defs = [dict(MOCK_TOOL_DEFINITIONS[0])]
        with patch.dict(os.environ, {AUTO_ALLOW_ENV: "k8s.list_pods"}):
            with self.assertLogs(
                "agent_service.tools.gateway_tools", level="INFO"
            ) as captured:
                build_gateway_toolkit(defs, "http://gw:8080")
        self.assertFalse(
            any("read-only by construction" in line for line in captured.output)
        )


class BuildToolkitRegressionTests(unittest.TestCase):
    """Regression: tools must actually register into a real AgentScope Toolkit.

    The prior implementation called ``Toolkit.add()``, which does not exist in
    AgentScope 2.x, silently yielding an empty toolkit and fabricated answers.
    """

    def test_build_toolkit_registers_discovered_tools(self) -> None:
        with patch(
            "agent_service.tools.gateway_tools.discover_tools",
            new_callable=AsyncMock,
        ) as mock_discover:
            mock_discover.return_value = MOCK_TOOL_DEFINITIONS
            toolkit = _run(build_toolkit("http://gw:8080", bearer_token="tok"))

        schemas = _run(toolkit.get_tool_schemas())
        function_schemas = [s for s in schemas if s.get("type") == "function"]
        names = {s["function"]["name"] for s in function_schemas}
        self.assertEqual(names, {"k8s_list_pods", "k8s_get_pod"})
        # Parameters survive end-to-end so the model can actually call them.
        by_name = {s["function"]["name"]: s for s in function_schemas}
        self.assertEqual(
            by_name["k8s_get_pod"]["function"]["parameters"],
            {"type": "object", "required": ["name"], "properties": {}},
        )

    def test_build_gateway_toolkit_empty_definitions(self) -> None:
        toolkit = build_gateway_toolkit([], "http://gw:8080")
        schemas = _run(toolkit.get_tool_schemas())
        self.assertEqual(
            [s for s in schemas if s.get("type") == "function"], []
        )


class RuntimeSettingsToolGatewayTests(unittest.TestCase):
    def test_tool_gateway_url_default_none(self) -> None:
        from agent_service.runtime_settings import RuntimeSettings

        settings = RuntimeSettings()
        self.assertIsNone(settings.tool_gateway_url)

    def test_tool_gateway_url_from_env(self) -> None:
        from agent_service.runtime_settings import RuntimeSettings

        with patch.dict("os.environ", {"TOOL_GATEWAY_URL": "http://gw:8080"}):
            settings = RuntimeSettings.from_env()
        self.assertEqual(settings.tool_gateway_url, "http://gw:8080")


class ExecutionRequestVerificationTests(unittest.TestCase):
    """SPEC-037 R-3: invoked-args digest verification at the gateway
    boundary for mutating tools; read-only tools never consult the
    envelope."""

    def _request(self, parameters) -> dict:
        return {
            "execution_id": "exec-1",
            "confirm_id": "cf-1",
            "call_id": "call-1",
            "session_id": "ses-1",
            "owner_user_id": "alice",
            "decider_user_id": "bob",
            "tool_name": "k8s.delete_pod",
            "args_digest": canonical_digest(parameters),
            "requested_at": "2026-08-27T10:00:00Z",
            "signature": "f" * 64,
        }

    def _mutating_fn(self):
        return _make_tool_fn(
            "http://gw:8080", "k8s.delete_pod", "d", is_read_only=False
        )

    def _worker_settings(self):
        from agent_service.runtime_settings import RuntimeSettings

        return RuntimeSettings(
            execution_worker_url="http://execution-runtime:8000",
            execution_handoff_token="handoff-secret",
        )

    def _worker_audit_context(self):
        return {
            "settings": self._worker_settings(),
            "confirm_id": "cf-1",
            "session_id": "ses-1",
            "request_id": "req-1",
            "decider_user_id": "bob",
        }

    def test_matching_arguments_hand_off_to_worker(self) -> None:
        """SPEC-038 R-4: a verified mutating call hands the signed
        envelope, parked arguments, and delegated token to the worker;
        the gateway is never called inline."""
        fn = self._mutating_fn()
        with patch(
            "agent_service.tools.gateway_tools.invoke_gateway_tool",
            new_callable=AsyncMock,
        ) as mock_invoke, patch(
            "agent_service.tools.gateway_tools._handoff_execution",
            new_callable=AsyncMock,
        ) as mock_handoff:
            mock_handoff.return_value = {"status": "success"}
            requests_var = EXECUTION_REQUESTS.set(
                {"call-1": self._request({"name": "web-1"})}
            )
            call_var = CURRENT_CALL_ID.set("call-1")
            audit_var = EXECUTION_AUDIT_CONTEXT.set(self._worker_audit_context())
            token_var = DELEGATED_TOKEN.set("confirmer-token")
            try:
                chunk = _run(fn(name="web-1"))
            finally:
                DELEGATED_TOKEN.reset(token_var)
                EXECUTION_AUDIT_CONTEXT.reset(audit_var)
                CURRENT_CALL_ID.reset(call_var)
                EXECUTION_REQUESTS.reset(requests_var)
        mock_invoke.assert_not_called()
        mock_handoff.assert_awaited_once_with(
            "k8s.delete_pod", "call-1", {"name": "web-1"}, "confirmer-token"
        )
        self.assertEqual(chunk.metadata["gateway_result"]["status"], "success")

    def test_reordered_arguments_still_match(self) -> None:
        fn = self._mutating_fn()
        signed = self._request({"force": True, "name": "web-1"})
        with patch(
            "agent_service.tools.gateway_tools._handoff_execution",
            new_callable=AsyncMock,
        ) as mock_handoff:
            mock_handoff.return_value = {"status": "success"}
            requests_var = EXECUTION_REQUESTS.set({"call-1": signed})
            call_var = CURRENT_CALL_ID.set("call-1")
            audit_var = EXECUTION_AUDIT_CONTEXT.set(self._worker_audit_context())
            try:
                _run(fn(name="web-1", force=True))
            finally:
                EXECUTION_AUDIT_CONTEXT.reset(audit_var)
                CURRENT_CALL_ID.reset(call_var)
                EXECUTION_REQUESTS.reset(requests_var)
        # The canonical-digest match accepts reordered arguments, so the
        # handoff receives the invoked kwargs.
        mock_handoff.assert_awaited_once()
        self.assertEqual(
            mock_handoff.await_args[0][2], {"name": "web-1", "force": True}
        )

    def test_mutated_arguments_blocked_and_audited(self) -> None:
        fn = self._mutating_fn()
        audit_context = {
            "settings": None,
            "confirm_id": "cf-1",
            "session_id": "ses-1",
            "request_id": "req-2",
            "decider_user_id": "bob",
        }
        with patch(
            "agent_service.tools.gateway_tools.invoke_gateway_tool",
            new_callable=AsyncMock,
        ) as mock_invoke, patch(
            "agent_service.services.audit_emitter.emit_audit_event"
        ) as mock_emit:
            requests_var = EXECUTION_REQUESTS.set(
                {"call-1": self._request({"name": "web-1"})}
            )
            call_var = CURRENT_CALL_ID.set("call-1")
            audit_var = EXECUTION_AUDIT_CONTEXT.set(audit_context)
            try:
                chunk = _run(fn(name="prod-1"))
            finally:
                EXECUTION_AUDIT_CONTEXT.reset(audit_var)
                CURRENT_CALL_ID.reset(call_var)
                EXECUTION_REQUESTS.reset(requests_var)
        # The gateway never sees the mutated invocation.
        mock_invoke.assert_not_called()
        result = chunk.metadata["gateway_result"]
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "EXECUTION_REJECTED")
        self.assertEqual(result["error"]["reason"], "args_digest_mismatch")
        # The rejection is audited with confirm_id correlation.
        event = mock_emit.call_args[0][1]
        self.assertEqual(event["event_type"], "execution_rejected")
        self.assertEqual(event["outcome"], "deny")
        self.assertEqual(event["details"]["reason"], "args_digest_mismatch")
        self.assertEqual(event["details"]["confirm_id"], "cf-1")
        self.assertEqual(event["details"]["call_id"], "call-1")
        self.assertEqual(event["session_id"], "ses-1")

    def test_absent_envelope_blocks_mutating_call(self) -> None:
        """Fail closed: a mutating call with no signed request (a path
        that bypassed resume) never reaches the gateway."""
        fn = self._mutating_fn()
        with patch(
            "agent_service.tools.gateway_tools.invoke_gateway_tool",
            new_callable=AsyncMock,
        ) as mock_invoke:
            chunk = _run(fn(name="web-1"))
        mock_invoke.assert_not_called()
        result = chunk.metadata["gateway_result"]
        self.assertEqual(result["error"]["code"], "EXECUTION_REJECTED")
        self.assertEqual(result["error"]["reason"], "request_missing")

    def test_unknown_call_id_blocks_mutating_call(self) -> None:
        fn = self._mutating_fn()
        with patch(
            "agent_service.tools.gateway_tools.invoke_gateway_tool",
            new_callable=AsyncMock,
        ) as mock_invoke:
            requests_var = EXECUTION_REQUESTS.set(
                {"call-1": self._request({"name": "web-1"})}
            )
            call_var = CURRENT_CALL_ID.set("call-other")
            try:
                chunk = _run(fn(name="web-1"))
            finally:
                CURRENT_CALL_ID.reset(call_var)
                EXECUTION_REQUESTS.reset(requests_var)
        mock_invoke.assert_not_called()
        result = chunk.metadata["gateway_result"]
        self.assertEqual(result["error"]["reason"], "request_missing")

    def test_resume_wide_rejection_reason_wins(self) -> None:
        """SPEC-037 R-2 fail-closed posture: a missing signing key sets a
        resume-wide rejection that blocks every mutating call."""
        fn = self._mutating_fn()
        with patch(
            "agent_service.tools.gateway_tools.invoke_gateway_tool",
            new_callable=AsyncMock,
        ) as mock_invoke:
            requests_var = EXECUTION_REQUESTS.set(
                {"call-1": self._request({"name": "web-1"})}
            )
            call_var = CURRENT_CALL_ID.set("call-1")
            rejection_var = EXECUTION_REJECTION.set("signing_unavailable")
            try:
                chunk = _run(fn(name="web-1"))
            finally:
                EXECUTION_REJECTION.reset(rejection_var)
                CURRENT_CALL_ID.reset(call_var)
                EXECUTION_REQUESTS.reset(requests_var)
        mock_invoke.assert_not_called()
        result = chunk.metadata["gateway_result"]
        self.assertEqual(result["error"]["reason"], "signing_unavailable")

    def test_read_only_invocations_never_consult_envelope(self) -> None:
        fn = _make_tool_fn(
            "http://gw:8080", "k8s.list_pods", "d", is_read_only=True
        )
        with patch(
            "agent_service.tools.gateway_tools.invoke_gateway_tool",
            new_callable=AsyncMock,
        ) as mock_invoke:
            mock_invoke.return_value = {"status": "success"}
            # Even with a resume-wide rejection set, read-only calls pass.
            rejection_var = EXECUTION_REJECTION.set("signing_unavailable")
            try:
                chunk = _run(fn(namespace="ops"))
            finally:
                EXECUTION_REJECTION.reset(rejection_var)
        mock_invoke.assert_called_once()
        self.assertEqual(chunk.metadata["gateway_result"]["status"], "success")

    def test_rejection_without_audit_context_still_blocks(self) -> None:
        fn = self._mutating_fn()
        with patch(
            "agent_service.tools.gateway_tools.invoke_gateway_tool",
            new_callable=AsyncMock,
        ) as mock_invoke, patch(
            "agent_service.services.audit_emitter.emit_audit_event"
        ) as mock_emit:
            chunk = _run(fn(name="web-1"))
        mock_invoke.assert_not_called()
        # No correlation context (outside a resume): no audit, block stands.
        mock_emit.assert_not_called()
        self.assertEqual(
            chunk.metadata["gateway_result"]["error"]["code"],
            "EXECUTION_REJECTED",
        )


class WorkerHandoffRoutingTests(unittest.TestCase):
    """SPEC-038 R-4: verified mutating calls hand off to the worker;
    the fail-closed posture covers missing configuration, transport
    failure, and handoff timeout."""

    def _request(self, parameters) -> dict:
        return {
            "execution_id": "exec-1",
            "confirm_id": "cf-1",
            "call_id": "call-1",
            "session_id": "ses-1",
            "owner_user_id": "alice",
            "decider_user_id": "bob",
            "tool_name": "k8s.delete_pod",
            "args_digest": canonical_digest(parameters),
            "requested_at": "2026-08-27T10:00:00Z",
            "signature": "f" * 64,
        }

    def _mutating_fn(self):
        return _make_tool_fn(
            "http://gw:8080", "k8s.delete_pod", "d", is_read_only=False
        )

    def _worker_settings(self):
        from agent_service.runtime_settings import RuntimeSettings

        return RuntimeSettings(
            execution_worker_url="http://execution-runtime:8000",
            execution_handoff_token="handoff-secret",
        )

    def _worker_audit_context(self):
        return {
            "settings": self._worker_settings(),
            "confirm_id": "cf-1",
            "session_id": "ses-1",
            "request_id": "req-1",
            "decider_user_id": "bob",
        }

    def _verified_context(self):
        """Contextvars for one approved resume with a matching envelope."""
        return (
            EXECUTION_REQUESTS.set({"call-1": self._request({"name": "web-1"})}),
            CURRENT_CALL_ID.set("call-1"),
        )

    @staticmethod
    def _reset(*tokens_and_vars):
        for var, token in tokens_and_vars:
            var.reset(token)

    def test_missing_worker_config_rejects_worker_unavailable(self) -> None:
        """No in-process fallback: an unset worker URL or token rejects
        before any handoff attempt."""
        fn = self._mutating_fn()
        with patch(
            "agent_service.services.execution_worker_client.httpx.AsyncClient"
        ) as mock_client_cls, patch(
            "agent_service.services.audit_emitter.emit_audit_event"
        ) as mock_emit:
            requests_var, call_var = self._verified_context()
            audit_var = EXECUTION_AUDIT_CONTEXT.set(
                {
                    "settings": None,
                    "confirm_id": "cf-1",
                    "session_id": "ses-1",
                    "request_id": "req-1",
                    "decider_user_id": "bob",
                }
            )
            try:
                chunk = _run(fn(name="web-1"))
            finally:
                self._reset(
                    (EXECUTION_AUDIT_CONTEXT, audit_var),
                    (CURRENT_CALL_ID, call_var),
                    (EXECUTION_REQUESTS, requests_var),
                )
        mock_client_cls.assert_not_called()
        result = chunk.metadata["gateway_result"]
        self.assertEqual(result["error"]["code"], "EXECUTION_REJECTED")
        self.assertEqual(result["error"]["reason"], "worker_unavailable")
        event = mock_emit.call_args[0][1]
        self.assertEqual(event["event_type"], "execution_rejected")
        self.assertEqual(event["details"]["reason"], "worker_unavailable")

    def test_handoff_timeout_yields_structured_timeout_result(self) -> None:
        fn = self._mutating_fn()
        with patch(
            "agent_service.services.execution_worker_client.handoff",
            new_callable=AsyncMock,
        ) as mock_handoff:
            mock_handoff.side_effect = WorkerHandoffTimeout("slow worker")
            requests_var, call_var = self._verified_context()
            audit_var = EXECUTION_AUDIT_CONTEXT.set(self._worker_audit_context())
            try:
                chunk = _run(fn(name="web-1"))
            finally:
                self._reset(
                    (EXECUTION_AUDIT_CONTEXT, audit_var),
                    (CURRENT_CALL_ID, call_var),
                    (EXECUTION_REQUESTS, requests_var),
                )
        result = chunk.metadata["gateway_result"]
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "TIMEOUT")
        self.assertIn("worker", result["error"]["message"])

    def test_transport_failure_rejects_worker_unavailable(self) -> None:
        fn = self._mutating_fn()
        with patch(
            "agent_service.services.execution_worker_client.handoff",
            new_callable=AsyncMock,
        ) as mock_handoff:
            mock_handoff.side_effect = WorkerHandoffError(
                "worker_unavailable", "execution worker is unreachable"
            )
            requests_var, call_var = self._verified_context()
            audit_var = EXECUTION_AUDIT_CONTEXT.set(self._worker_audit_context())
            try:
                chunk = _run(fn(name="web-1"))
            finally:
                self._reset(
                    (EXECUTION_AUDIT_CONTEXT, audit_var),
                    (CURRENT_CALL_ID, call_var),
                    (EXECUTION_REQUESTS, requests_var),
                )
        result = chunk.metadata["gateway_result"]
        self.assertEqual(result["error"]["code"], "EXECUTION_REJECTED")
        self.assertEqual(result["error"]["reason"], "worker_unavailable")

    def test_worker_verification_rejection_carries_reason(self) -> None:
        fn = self._mutating_fn()
        with patch(
            "agent_service.services.execution_worker_client.handoff",
            new_callable=AsyncMock,
        ) as mock_handoff:
            mock_handoff.side_effect = WorkerHandoffError(
                "signature_invalid", "worker rejected the handoff (400)"
            )
            requests_var, call_var = self._verified_context()
            audit_var = EXECUTION_AUDIT_CONTEXT.set(self._worker_audit_context())
            try:
                chunk = _run(fn(name="web-1"))
            finally:
                self._reset(
                    (EXECUTION_AUDIT_CONTEXT, audit_var),
                    (CURRENT_CALL_ID, call_var),
                    (EXECUTION_REQUESTS, requests_var),
                )
        result = chunk.metadata["gateway_result"]
        self.assertEqual(result["error"]["code"], "EXECUTION_REJECTED")
        self.assertEqual(result["error"]["reason"], "signature_invalid")

    def test_read_only_invocations_never_hand_off(self) -> None:
        fn = _make_tool_fn(
            "http://gw:8080", "k8s.list_pods", "d", is_read_only=True
        )
        with patch(
            "agent_service.tools.gateway_tools.invoke_gateway_tool",
            new_callable=AsyncMock,
        ) as mock_invoke, patch(
            "agent_service.tools.gateway_tools._handoff_execution",
            new_callable=AsyncMock,
        ) as mock_handoff:
            mock_invoke.return_value = {"status": "success"}
            requests_var, call_var = self._verified_context()
            audit_var = EXECUTION_AUDIT_CONTEXT.set(self._worker_audit_context())
            try:
                chunk = _run(fn(name="web-1"))
            finally:
                self._reset(
                    (EXECUTION_AUDIT_CONTEXT, audit_var),
                    (CURRENT_CALL_ID, call_var),
                    (EXECUTION_REQUESTS, requests_var),
                )
        mock_handoff.assert_not_awaited()
        mock_invoke.assert_awaited_once()
        self.assertEqual(chunk.metadata["gateway_result"]["status"], "success")
