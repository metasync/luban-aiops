"""SPEC-069 R-2 tests: the generic MCP-ingestion adapter + Ansible binding.

Covers the invariants the pilot exists to prove: typed read-tier-only
registration, server-agnostic mapping (one adapter class, many binding configs),
server-advertised metadata treated as untrusted (never setting tier, never
auto-admitting an unlisted tool), fail-closed transport/error mapping (no
fabricated success), argument validation + arg projection, credential resolution
through the SPEC-068 seam with no token leakage, and identity threading.

No test contacts a live server: a fake session opener stands in for the MCP SDK
transport, so CI makes no live external call (OQ-5).
"""

import asyncio
import json
import os
import tempfile
import unittest
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from unittest.mock import patch

from tool_gateway.ingestion.ansible_binding import (
    ANSIBLE_ADMITTED_TOOLS,
    DENIED_SERVER_TOOLS,
    build_ansible_mcp_connector,
)
from tool_gateway.ingestion.mcp_adapter import (
    AdmittedTool,
    McpIngestionConnector,
    McpTransport,
)
from tool_gateway.core.config import GatewaySettings
from tool_gateway.schemas.api import IdentityContext
from tool_gateway.services.gateway_service import invoke_tool
from tool_gateway.services.policy_engine import reset_policy_state
from tool_gateway.tools.registry import ToolRegistry


def _run(coro):
    return asyncio.run(coro)


# --- Test doubles for the MCP SDK client session (no live server) ---


@dataclass
class FakeTextContent:
    text: str
    type: str = "text"


@dataclass
class FakeCallToolResult:
    content: list = field(default_factory=list)
    structured_content: dict | None = None
    is_error: bool = False


@dataclass
class FakeListToolsResult:
    tools: list


@dataclass
class FakeTool:
    """A server-advertised tool. Its annotations are UNTRUSTED metadata."""

    name: str
    annotations: dict = field(default_factory=dict)


class FakeSession:
    def __init__(self, server: "FakeServer") -> None:
        self._server = server

    async def call_tool(self, name, arguments=None):
        self._server.calls.append((name, arguments or {}))
        response = self._server.responses.get(name)
        if isinstance(response, Exception):
            raise response
        if response is None:
            return FakeCallToolResult(structured_content={"ok": True})
        return response

    async def list_tools(self):
        self._server.discoveries += 1
        return FakeListToolsResult(self._server.tools)


class FakeServer:
    """Records calls/discoveries/bearers and serves canned tool responses."""

    def __init__(self, tools=None, responses=None) -> None:
        self.tools = list(tools or [])
        self.responses = dict(responses or {})
        self.calls: list[tuple[str, dict]] = []
        self.bearers: list[str | None] = []
        self.discoveries = 0

    def opener(self):
        server = self

        @asynccontextmanager
        async def _open(transport, bearer):
            server.bearers.append(bearer)
            yield FakeSession(server)

        return _open


@asynccontextmanager
async def _import_error_opener(transport, bearer):
    raise ImportError("No module named 'mcp'")
    yield  # pragma: no cover


@asynccontextmanager
async def _connection_error_opener(transport, bearer):
    raise ConnectionError("connection refused")
    yield  # pragma: no cover


@asynccontextmanager
async def _timeout_opener(transport, bearer):
    raise TimeoutError("read timed out")
    yield  # pragma: no cover


def _connector(admitted, server=None, opener=None, **kwargs) -> McpIngestionConnector:
    return McpIngestionConnector(
        transport=McpTransport(url="http://awx-mcp.local/mcp"),
        admitted=tuple(admitted),
        source_system="ansible",
        session_opener=opener or (server.opener() if server else _connection_error_opener),
        **kwargs,
    )


def _ansible_names() -> set[str]:
    return {spec.name for spec in ANSIBLE_ADMITTED_TOOLS}


def _unlink(path: str) -> None:
    with suppress(FileNotFoundError):
        os.unlink(path)


def _write_cred_file(test: unittest.TestCase, payload: dict) -> str:
    """Write a temp credential-set file whose removal is guaranteed.

    The bearer inside is a fake, but a ``delete=False`` temp file per test still
    litters the runner's tmpdir across the suite, so every write registers its
    own cleanup.
    """
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(payload, handle)
    handle.close()
    test.addCleanup(_unlink, handle.name)
    return handle.name


class _FakeRequest:
    """Minimal stand-in for a FastAPI Request (invoke_tool reads .json()/.headers)."""

    def __init__(self, body: dict, headers: dict | None = None) -> None:
        self._body = body
        self.headers = headers or {}

    async def json(self) -> dict:
        return self._body


# A delegated-style identity: the requesting user (sub) acting via a service (act).
_IDENTITY = IdentityContext(
    subject="user-carol", username="carol.ops", roles=["operator"], actor="agent-platform",
)


def _invoke_captured(connector, tool_name, parameters, identity=_IDENTITY):
    """Drive the real audit choke point (``gateway_service.invoke_tool``).

    Returns ``(response, audit_event, log_calls_str)`` with the durable-audit
    emitter and the structured logger captured, so R-4/R-5 assert on exactly what
    would be recorded. No live server: the connector carries a fake opener.
    """
    registry = ToolRegistry()
    connector.register_tools(registry)
    request = _FakeRequest({"tool_name": tool_name, "parameters": parameters})
    reset_policy_state()
    with patch("tool_gateway.services.gateway_service.emit_audit_event") as emit, \
            patch("tool_gateway.services.gateway_service.log_event") as log:
        response = _run(invoke_tool(GatewaySettings(), registry, request, identity, "req-1"))
    event = emit.call_args.args[1] if emit.call_args else None
    return response, event, str(log.call_args_list)


class RegistrationTests(unittest.TestCase):
    """Typed registration, read-tier-only, and the deny-by-default allowlist."""

    def test_registers_six_read_tier_typed_tools(self) -> None:
        registry = ToolRegistry()
        _connector(ANSIBLE_ADMITTED_TOOLS).register_tools(registry)
        defs = registry.list_definitions()
        self.assertEqual(len(defs), 6)
        for d in defs:
            self.assertEqual(d.risk_level, "read")
            self.assertEqual(d.category, "ansible")
            self.assertTrue(d.name.startswith("ansible."))

    def test_admitted_set_matches_stage0(self) -> None:
        self.assertEqual(
            _ansible_names(),
            {
                "ansible.list_inventories",
                "ansible.get_inventory",
                "ansible.list_job_templates",
                "ansible.get_job",
                "ansible.get_job_stdout",
                "ansible.get_environment_health",
            },
        )

    def test_no_mutating_playbook_runbook_or_check_name_admitted(self) -> None:
        names = _ansible_names()
        server_names = {spec.server_name for spec in ANSIBLE_ADMITTED_TOOLS}
        # The three mutating server tools are never mapped (R-2/R-3 deny).
        self.assertFalse(DENIED_SERVER_TOOLS & server_names)
        # No playbook-run / runbook-execution / dry-run surface exists.
        for token in ("launch", "cancel", "update", "run", "playbook", "runbook", "check", "dry"):
            for name in names:
                self.assertNotIn(token, name.lower())

    def test_registration_is_config_driven_and_never_contacts_server(self) -> None:
        server = FakeServer(tools=[FakeTool("job_launch", {"readOnlyHint": True})])
        registry = ToolRegistry()
        _connector(ANSIBLE_ADMITTED_TOOLS, server=server).register_tools(registry)
        # Registration reads only gateway config — no discovery, no call.
        self.assertEqual(server.discoveries, 0)
        self.assertEqual(server.calls, [])


class ServerAgnosticTests(unittest.TestCase):
    """One adapter class binds different servers purely by config (no code change)."""

    def test_same_adapter_maps_two_different_server_configs(self) -> None:
        # A self-hosted AWX-style binding and an AAP-read-only-style binding are
        # just two AdmittedTool tuples handed to the SAME adapter class.
        awx = (
            AdmittedTool("list_inventories", "ansible.list_inventories", "d",
                         "read", "ansible", {"type": "object", "properties": {}}),
        )
        aap = (
            AdmittedTool("aap_inventory_list", "ansible.aap_list_inventories", "d",
                         "read", "ansible", {"type": "object", "properties": {}}),
            AdmittedTool("aap_job_get", "ansible.aap_get_job", "d",
                         "read", "ansible", {"type": "object", "properties": {}}),
        )
        r_awx, r_aap = ToolRegistry(), ToolRegistry()
        _connector(awx).register_tools(r_awx)
        _connector(aap).register_tools(r_aap)
        self.assertEqual({d.name for d in r_awx.list_definitions()},
                         {"ansible.list_inventories"})
        self.assertEqual({d.name for d in r_aap.list_definitions()},
                         {"ansible.aap_list_inventories", "ansible.aap_get_job"})

    def test_argument_map_renames_canonical_to_server_arg(self) -> None:
        spec = AdmittedTool(
            "get_inventory", "ansible.get_inventory", "d", "read", "ansible",
            {"type": "object", "required": ["inventory"],
             "properties": {"inventory": {"type": "string"}}},
            argument_map={"inventory": "inventory_id"},
        )
        server = FakeServer()
        registry = ToolRegistry()
        _connector((spec,), server=server).register_tools(registry)
        _run(registry.invoke("ansible.get_inventory", {"inventory": "demo"}, {}))
        self.assertEqual(server.calls[-1], ("get_inventory", {"inventory_id": "demo"}))


class UntrustedMetadataTests(unittest.TestCase):
    """Server-advertised metadata never sets tier nor auto-admits a tool."""

    def test_lying_readonly_hint_on_unlisted_mutating_tool_is_not_admitted(self) -> None:
        # The server advertises job_launch as readOnlyHint=True. It is not in the
        # allowlist, so it is never registered regardless of what it claims.
        server = FakeServer(tools=[
            FakeTool("job_launch", {"readOnlyHint": True}),
            FakeTool("list_inventories", {"readOnlyHint": True}),
        ])
        registry = ToolRegistry()
        _connector(ANSIBLE_ADMITTED_TOOLS, server=server).register_tools(registry)
        names = {d.name for d in registry.list_definitions()}
        self.assertNotIn("job_launch", names)
        self.assertNotIn("ansible.job_launch", names)
        self.assertEqual(names, _ansible_names())

    def test_tier_comes_from_config_not_server(self) -> None:
        # Even a server that would advertise a write tier cannot change the
        # gateway-owned read tier: the definition is built from AdmittedTool.
        spec = AdmittedTool("get_job", "ansible.get_job", "d", "read", "ansible",
                            {"type": "object", "properties": {}})
        server = FakeServer(tools=[FakeTool("get_job", {"readOnlyHint": False})])
        registry = ToolRegistry()
        _connector((spec,), server=server).register_tools(registry)
        self.assertEqual(registry.list_definitions()[0].risk_level, "read")

    def test_discovery_lists_server_tools_but_does_not_register_them(self) -> None:
        server = FakeServer(tools=[FakeTool("list_inventories"), FakeTool("job_launch")])
        connector = _connector(ANSIBLE_ADMITTED_TOOLS, server=server)
        names, err = _run(connector.list_server_tools())
        self.assertIsNone(err)
        self.assertEqual(sorted(names), ["job_launch", "list_inventories"])
        # Discovery is diagnostic only; registration stays the allowlist.
        registry = ToolRegistry()
        connector.register_tools(registry)
        self.assertEqual({d.name for d in registry.list_definitions()}, _ansible_names())


class ExecutionTests(unittest.TestCase):
    """Argument validation, projection, and result normalization."""

    def _registry(self, server):
        registry = ToolRegistry()
        _connector(ANSIBLE_ADMITTED_TOOLS, server=server).register_tools(registry)
        return registry

    def test_success_passes_through_structured_content(self) -> None:
        server = FakeServer(responses={
            "controller.inventories_list": FakeCallToolResult(structured_content={"inventories": ["demo"]}),
        })
        result = _run(self._registry(server).invoke("ansible.list_inventories", {}, {}))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data, {"inventories": ["demo"]})
        self.assertEqual(result.evidence["risk_level"], "read")
        self.assertEqual(result.evidence["source_system"], "ansible")

    def test_success_extracts_text_content(self) -> None:
        # Keyed by the SERVER tool name (controller.ping_list), which is what
        # the binding dispatches to — not the canonical ansible.* name.
        server = FakeServer(responses={
            "controller.ping_list": FakeCallToolResult(
                content=[FakeTextContent("healthy")]),
        })
        result = _run(self._registry(server).invoke("ansible.get_environment_health", {}, {}))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data, {"text": "healthy"})

    def test_missing_required_param_is_invalid_and_not_dispatched(self) -> None:
        server = FakeServer()
        result = _run(self._registry(server).invoke("ansible.get_inventory", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")
        self.assertEqual(server.calls, [])

    def test_wrong_type_param_is_invalid(self) -> None:
        server = FakeServer()
        result = _run(self._registry(server).invoke(
            "ansible.get_job", {"job_id": 123}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")
        self.assertEqual(server.calls, [])

    def test_integer_bound_is_enforced(self) -> None:
        server = FakeServer()
        result = _run(self._registry(server).invoke(
            "ansible.list_inventories", {"limit": 0}, {}))
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")

    def test_unknown_args_are_dropped_not_forwarded(self) -> None:
        server = FakeServer()
        _run(self._registry(server).invoke(
            "ansible.list_inventories", {"limit": 5, "bogus": "x", "--check": True}, {}))
        self.assertEqual(server.calls[-1], ("controller.inventories_list", {"limit": 5}))

    def test_identity_threads_through_execute(self) -> None:
        # R-2: the identity context is carried into the tool (full five-field
        # audit attribution is R-4/Stage-3, asserted there).
        server = FakeServer()
        identity = {"sub": "alice", "actor": "tool-gateway", "request_id": "r-1"}
        result = _run(self._registry(server).invoke(
            "ansible.list_inventories", {}, identity))
        self.assertEqual(result.status, "success")
        self.assertEqual(len(server.calls), 1)


class FailClosedTests(unittest.TestCase):
    """Transport/SDK/tool errors become structured errors, never a success."""

    def test_sdk_unavailable_maps_to_structured_error(self) -> None:
        registry = ToolRegistry()
        _connector(ANSIBLE_ADMITTED_TOOLS, opener=_import_error_opener).register_tools(registry)
        result = _run(registry.invoke("ansible.list_inventories", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "MCP_SDK_UNAVAILABLE")

    def test_connection_error_maps_to_transport_error(self) -> None:
        registry = ToolRegistry()
        _connector(ANSIBLE_ADMITTED_TOOLS, opener=_connection_error_opener).register_tools(registry)
        result = _run(registry.invoke("ansible.list_inventories", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "MCP_TRANSPORT_ERROR")

    def test_timeout_maps_to_transport_error_not_success(self) -> None:
        @asynccontextmanager
        async def _timeout(transport, bearer):
            raise TimeoutError("read timed out")
            yield  # pragma: no cover

        registry = ToolRegistry()
        _connector(ANSIBLE_ADMITTED_TOOLS, opener=_timeout).register_tools(registry)
        result = _run(registry.invoke("ansible.get_job", {"job_id": "1"}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "MCP_TRANSPORT_ERROR")

    def test_server_reported_tool_error_is_not_a_success(self) -> None:
        server = FakeServer(responses={
            "controller.jobs_read": FakeCallToolResult(
                content=[FakeTextContent("job 1 not found")], is_error=True),
        })
        registry = ToolRegistry()
        _connector(ANSIBLE_ADMITTED_TOOLS, server=server).register_tools(registry)
        result = _run(registry.invoke("ansible.get_job", {"job_id": "1"}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "MCP_TOOL_ERROR")
        self.assertIn("not found", result.error["message"])


class CredentialResolutionTests(unittest.TestCase):
    """Credentials resolve through the SPEC-068 seam; the token never leaks."""

    def _cred_file(self, payload: dict) -> str:
        return _write_cred_file(self, payload)

    def test_bearer_set_resolves_and_token_reaches_transport_only(self) -> None:
        token = "SUPERSECRET-BEARER-9"
        path = self._cred_file({"awx-read": {"scheme": "bearer", "token": token}})
        server = FakeServer()
        connector = _connector(
            ANSIBLE_ADMITTED_TOOLS, server=server,
            credential_set="awx-read", credential_sets_path=path,
        )
        registry = ToolRegistry()
        connector.register_tools(registry)
        result = _run(registry.invoke("ansible.list_inventories", {}, {}))
        self.assertEqual(result.status, "success")
        # The token reached the transport (SPEC-068 bearer path)...
        self.assertEqual(server.bearers, [token])
        # ...and never appears in the tool result envelope.
        self.assertNotIn(token, json.dumps(result.to_dict()))

    def test_basic_set_has_no_bearer_form_and_fails_closed(self) -> None:
        path = self._cred_file({"awx-basic": {"username": "u", "password": "p"}})
        server = FakeServer()
        connector = _connector(
            ANSIBLE_ADMITTED_TOOLS, server=server,
            credential_set="awx-basic", credential_sets_path=path,
        )
        registry = ToolRegistry()
        connector.register_tools(registry)
        result = _run(registry.invoke("ansible.list_inventories", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "CREDENTIAL_SCHEME_UNSUPPORTED")
        self.assertEqual(server.calls, [])

    def test_unknown_set_fails_closed(self) -> None:
        path = self._cred_file({"awx-read": {"scheme": "bearer", "token": "t"}})
        connector = _connector(
            ANSIBLE_ADMITTED_TOOLS, server=FakeServer(),
            credential_set="nope", credential_sets_path=path,
        )
        registry = ToolRegistry()
        connector.register_tools(registry)
        result = _run(registry.invoke("ansible.list_inventories", {}, {}))
        self.assertEqual(result.error["code"], "CREDENTIAL_SET_NOT_FOUND")

    def test_no_credential_set_is_an_unauthenticated_loopback_session(self) -> None:
        server = FakeServer()
        connector = _connector(ANSIBLE_ADMITTED_TOOLS, server=server)
        registry = ToolRegistry()
        connector.register_tools(registry)
        result = _run(registry.invoke("ansible.list_inventories", {}, {}))
        self.assertEqual(result.status, "success")
        self.assertEqual(server.bearers, [None])


class BindingFactoryTests(unittest.TestCase):
    """The settings-driven factory wires transport + credential config."""

    def test_factory_builds_connector_from_settings(self) -> None:
        settings = GatewaySettings(
            ansible_mcp_enabled=True,
            ansible_mcp_transport="streamable_http",
            ansible_mcp_url="http://awx-mcp.local/mcp",
            ansible_mcp_timeout_ms=4321,
            ansible_mcp_credential_set="awx-read",
        )
        connector = build_ansible_mcp_connector(settings)
        self.assertEqual(connector.admitted, ANSIBLE_ADMITTED_TOOLS)
        registry = ToolRegistry()
        connector.register_tools(registry)
        self.assertEqual({d.name for d in registry.list_definitions()}, _ansible_names())


class AuditFidelityTests(unittest.TestCase):
    """SPEC-069 R-4: the ``tool_invoked`` audit record for an Ansible read carries
    requester + acting-service + target + tool + outcome, keeps requester and
    acting-service separate (ADR-0004 ``sub``/``act``), names the dev target-identity
    mode, and never a secret."""

    def test_success_audit_carries_all_five_fields_and_delegation_mode(self) -> None:
        server = FakeServer(responses={
            "controller.inventories_list": FakeCallToolResult(structured_content={"inventories": ["demo"]}),
        })
        response, event, _log = _invoke_captured(
            _connector(ANSIBLE_ADMITTED_TOOLS, server=server),
            "ansible.list_inventories", {},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(event["event_type"], "tool_invoked")
        # (1) requester identity and (2) acting-service identity, kept separate.
        self.assertEqual(event["subject"], "user-carol")
        self.assertEqual(event["username"], "carol.ops")
        self.assertEqual(event["actor"], "agent-platform")
        self.assertNotEqual(event["subject"], event["actor"])
        self.assertEqual(event["roles"], ["operator"])
        details = event["details"]
        # (3) target system, (4) tool name, (5) outcome.
        self.assertEqual(details["target_system"], "ansible")
        self.assertEqual(details["tool_name"], "ansible.list_inventories")
        self.assertEqual(event["outcome"], "success")
        self.assertEqual(details["status"], "success")
        # OQ-4 delegation distinction: dev addresses the target as the acting
        # service, NOT the requesting user's delegated identity (SPEC-070).
        self.assertEqual(details["target_identity_mode"], "acting_service")
        self.assertNotIn("failure_class", details)

    def test_no_secret_or_token_reaches_audit_or_logs(self) -> None:
        token = "SUPERSECRET-BEARER-9"
        path = _write_cred_file(self, {"awx-read": {"scheme": "bearer", "token": token}})
        server = FakeServer()
        response, event, log_str = _invoke_captured(
            _connector(ANSIBLE_ADMITTED_TOOLS, server=server,
                       credential_set="awx-read", credential_sets_path=path),
            "ansible.list_inventories", {},
        )
        self.assertEqual(response.status_code, 200)
        blob = json.dumps(event) + log_str
        for secret in (token, "client_secret", "password"):
            self.assertNotIn(secret, blob)
        # The token still reached the transport (SPEC-068), so the call truly ran.
        self.assertEqual(server.bearers, [token])


class FailClosedAuditTests(unittest.TestCase):
    """SPEC-069 R-5: an unreachable/timed-out target is a *failed* outcome attributed
    ``target_unavailable`` — distinct from a policy denial and never a fabricated
    success; a server-reported tool error is a fact, not an unavailability."""

    def test_transport_outage_is_failed_and_attributed_target_unavailable(self) -> None:
        response, event, _log = _invoke_captured(
            _connector(ANSIBLE_ADMITTED_TOOLS, opener=_connection_error_opener),
            "ansible.list_inventories", {},
        )
        self.assertEqual(response.status_code, 400)
        # A failed outcome, never an empty/fabricated "success".
        self.assertEqual(json.loads(response.body)["status"], "error")
        self.assertEqual(event["event_type"], "tool_invoked")  # not a policy_decision
        self.assertEqual(event["outcome"], "error")
        self.assertEqual(event["details"]["status"], "error")
        self.assertEqual(event["details"]["failure_class"], "target_unavailable")
        self.assertEqual(event["details"]["target_system"], "ansible")

    def test_timeout_is_attributed_target_unavailable(self) -> None:
        _response, event, _log = _invoke_captured(
            _connector(ANSIBLE_ADMITTED_TOOLS, opener=_timeout_opener),
            "ansible.get_job", {"job_id": "1"},
        )
        self.assertEqual(event["outcome"], "error")
        self.assertEqual(event["details"]["failure_class"], "target_unavailable")

    def test_server_reported_error_is_not_target_unavailable(self) -> None:
        # The target WAS available and answered with an error: a fact, not an
        # unavailability (SPEC-058 "an upstream 4xx/5xx is a fact, not an error").
        server = FakeServer(responses={
            "controller.jobs_read": FakeCallToolResult(content=[FakeTextContent("nope")], is_error=True),
        })
        _response, event, _log = _invoke_captured(
            _connector(ANSIBLE_ADMITTED_TOOLS, server=server),
            "ansible.get_job", {"job_id": "1"},
        )
        self.assertEqual(event["outcome"], "error")
        self.assertNotIn("failure_class", event["details"])

    def test_target_unavailable_is_distinct_from_policy_denial(self) -> None:
        # No identity -> a policy_decision/deny event carrying no failure_class:
        # a denial and a target outage never collapse into one another.
        response, event, _log = _invoke_captured(
            _connector(ANSIBLE_ADMITTED_TOOLS, server=FakeServer()),
            "ansible.list_inventories", {}, identity=None,
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(event["event_type"], "policy_decision")
        self.assertEqual(event["outcome"], "deny")
        self.assertNotIn("failure_class", event["details"])


class DryRunExclusionTests(unittest.TestCase):
    """SPEC-069 R-5 / OQ-3: ``--check``/dry-run is never read tier. The admitted set
    holds no operation whose safety depends on check mode; a dry-run preview is a
    Layer-2 action-tier concern (a fact about a *plan*), never a read guarantee."""

    def test_no_admitted_operation_depends_on_check_mode(self) -> None:
        forbidden = ("check", "dry", "diff", "plan", "preview",
                     "launch", "cancel", "update", "run", "playbook",
                     "runbook", "mutate", "apply", "execute")
        for spec in ANSIBLE_ADMITTED_TOOLS:
            self.assertEqual(spec.risk_level, "read")
            haystack = f"{spec.name} {spec.server_name}".lower()
            for token in forbidden:
                self.assertNotIn(
                    token, haystack,
                    f"{spec.name} admits a check-mode/mutating '{token}' operation",
                )
        # The three mutating server tools stay structurally absent from the allowlist.
        server_names = {spec.server_name for spec in ANSIBLE_ADMITTED_TOOLS}
        self.assertFalse(DENIED_SERVER_TOOLS & server_names)


if __name__ == "__main__":
    unittest.main()
