"""SPEC-067 R-2 tests: the native read-only ServiceNow Table-API connector.

Modelled on ``test_http_connector.py`` (a single injected ``httpx.MockTransport``
at the connector's one ``_table_request`` call site) and ``test_ansible_native.py``
(registration, fail-closed, audit attribution). Asserts the six OQ-4 read tools
register read-tier-only, the tool set is operator-declared (never target-derived),
every record is projected to the gateway-owned field allowlist (a ``sys_user``
``password`` column can never leak), a ``sys_id``/``limit`` is validated before the
transport is reached, an upstream 4xx/5xx or timeout fails closed rather than
fabricating an empty success, the credential resolves through the SPEC-068 seam
with no token in any result, and ``change_request`` is in scope while
attachments/``problem`` are absent.
"""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from tool_gateway.core.config import GatewaySettings
from tool_gateway.ingestion.servicenow_binding import (
    SERVICENOW_ADMITTED_TOOLS,
    build_servicenow_connector,
)
from tool_gateway.ingestion.servicenow_native import (
    MAX_LIMIT,
    ServiceNowNativeConnector,
    ServiceNowTableTool,
    _project,
)
from tool_gateway.schemas.api import IdentityContext
from tool_gateway.services.gateway_service import invoke_tool
from tool_gateway.services.policy_engine import reset_policy_state
from tool_gateway.tools.base import ToolResult, build_evidence, make_error_result
from tool_gateway.tools.registry import ToolRegistry

BASE_URL = "https://snow.example.com"
SYS_ID = "0123456789abcdef0123456789abcdef"  # a valid 32-char hex sys_id
EXPECTED_TOOLS = {
    "servicenow.incident.list",
    "servicenow.incident.get",
    "servicenow.change_request.list",
    "servicenow.change_request.get",
    "servicenow.user.get",
    "servicenow.cmdb_ci.get",
}


def _run(coro):
    return asyncio.run(coro)


class _Router:
    """A ``MockTransport`` handler routing on ``(method, path)``.

    Records every request so a test can assert the transport was never reached
    (a pre-transport refusal). A route value may be an ``httpx.Response``, a
    callable ``request -> Response``, or an ``Exception`` instance to raise.
    """

    def __init__(self, routes: dict) -> None:
        self.routes = routes
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        entry = self.routes.get((request.method, request.url.path))
        if entry is None:
            entry = self.routes.get(request.url.path)
        if entry is None:
            return httpx.Response(404, json={"error": {"message": "no route"}})
        if isinstance(entry, Exception):
            raise entry
        if callable(entry):
            return entry(request)
        return entry

    @property
    def call_count(self) -> int:
        return len(self.calls)


def _connector(router, *, base_url=BASE_URL, **kwargs) -> ServiceNowNativeConnector:
    return ServiceNowNativeConnector(
        base_url=base_url,
        admitted=SERVICENOW_ADMITTED_TOOLS,
        transport=httpx.MockTransport(router),
        **kwargs,
    )


def _call(connector, tool, params, *, allow_mutating=False, identity=None):
    registry = ToolRegistry(allow_mutating=allow_mutating)
    connector.register_tools(registry)
    return _run(registry.invoke(tool, params, identity or {}))


def _write_credentials(mapping: dict) -> str:
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(mapping, handle)
    return path


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
    emitter and the structured logger captured, so R-3/R-4/R-5 assert on exactly
    what would be recorded. No live target: the connector carries a
    ``MockTransport``, so CI makes no external call (OQ-5).
    """
    registry = ToolRegistry()
    connector.register_tools(registry)
    request = _FakeRequest({"tool_name": tool_name, "parameters": parameters})
    reset_policy_state()
    with patch("tool_gateway.services.gateway_service.emit_audit_event") as emit, \
            patch("tool_gateway.services.gateway_service.log_event") as log:
        response = _run(
            invoke_tool(GatewaySettings(), registry, request, identity, "req-1")
        )
    event = emit.call_args.args[1] if emit.call_args else None
    return response, event, str(log.call_args_list)


# --- Registration, tier, and the operator-declared tool set (R-2) ---


class RegistrationTests(unittest.TestCase):
    def test_registers_exactly_the_six_read_tier_tools(self) -> None:
        registry = ToolRegistry()
        _connector(_Router({})).register_tools(registry)
        defs = registry.list_definitions()
        self.assertEqual({d.name for d in defs}, EXPECTED_TOOLS)
        self.assertTrue(all(d.risk_level == "read" for d in defs))
        self.assertTrue(all(d.category == "servicenow" for d in defs))

    def test_change_request_in_scope_attachments_and_problem_absent(self) -> None:
        """OQ-4 operator amendment: change_request first-class; the rest deferred."""
        names = {spec.name for spec in SERVICENOW_ADMITTED_TOOLS}
        self.assertIn("servicenow.change_request.list", names)
        self.assertIn("servicenow.change_request.get", names)
        self.assertFalse(any("attachment" in n for n in names))
        self.assertFalse(any("problem" in n for n in names))

    def test_all_tools_register_even_with_mutating_disabled(self) -> None:
        """Read-tier tools ride tools:invoke; the mutating flag never gates them."""
        registry = ToolRegistry(allow_mutating=False)
        _connector(_Router({})).register_tools(registry)
        self.assertEqual(len(registry.list_definitions()), 6)

    def test_not_configured_fails_closed(self) -> None:
        result = _call(_connector(_Router({}), base_url=""), "servicenow.incident.list", {})
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "SERVICENOW_NOT_CONFIGURED")

    def test_tool_set_is_operator_declared_not_target_derived(self) -> None:
        """The registered set comes from binding config, not a server handshake."""
        self.assertEqual(
            {spec.name for spec in SERVICENOW_ADMITTED_TOOLS}, EXPECTED_TOOLS
        )
        # Every admitted spec is a read op over a fixed table.
        for spec in SERVICENOW_ADMITTED_TOOLS:
            self.assertIn(spec.op, {"list", "get"})
            self.assertTrue(spec.table)
            self.assertTrue(spec.fields)


# --- Happy-path reads, projection, and URL discipline ---


class ReadExecutionTests(unittest.TestCase):
    def test_list_success_projects_and_bounds(self) -> None:
        router = _Router({
            ("GET", "/api/now/table/incident"): httpx.Response(200, json={
                "result": [
                    {"sys_id": SYS_ID, "number": "INC0010001", "state": "New",
                     "priority": "1 - Critical", "password": "SHOULD-NOT-APPEAR"},
                ]
            })
        })
        result = _call(_connector(router), "servicenow.incident.list", {"limit": 5})
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["table"], "incident")
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(result.data["records"][0]["number"], "INC0010001")
        # The non-allowlisted column is dropped by projection.
        self.assertNotIn("password", result.data["records"][0])
        self.assertNotIn("SHOULD-NOT-APPEAR", json.dumps(result.to_dict()))
        # sysparm_limit reflects the (clamped) model arg; sysparm_fields is set.
        sent = router.calls[0]
        self.assertEqual(sent.url.params.get("sysparm_limit"), "5")
        self.assertIn("number", sent.url.params.get("sysparm_fields", ""))

    def test_get_success_builds_sys_id_path(self) -> None:
        router = _Router({
            ("GET", f"/api/now/table/incident/{SYS_ID}"): httpx.Response(200, json={
                "result": {"sys_id": SYS_ID, "number": "INC0010002", "state": "Closed"}
            })
        })
        result = _call(_connector(router), "servicenow.incident.get", {"sys_id": SYS_ID})
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["record"]["number"], "INC0010002")
        self.assertEqual(router.calls[0].url.path, f"/api/now/table/incident/{SYS_ID}")

    def test_limit_clamped_to_max(self) -> None:
        router = _Router({
            ("GET", "/api/now/table/incident"): httpx.Response(200, json={"result": []})
        })
        _call(_connector(router), "servicenow.incident.list", {"limit": 99999})
        self.assertEqual(router.calls[0].url.params.get("sysparm_limit"), str(MAX_LIMIT))

    def test_project_drops_unknown_columns(self) -> None:
        projected = _project(
            {"sys_id": "a", "name": "n", "user_password": "x", "password": "y"},
            ("sys_id", "name"),
        )
        self.assertEqual(projected, {"sys_id": "a", "name": "n"})


# --- Argument validation happens before the transport is touched ---


class ValidationTests(unittest.TestCase):
    def test_missing_sys_id_is_rejected_pre_transport(self) -> None:
        router = _Router({})
        result = _call(_connector(router), "servicenow.incident.get", {})
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")
        self.assertEqual(router.call_count, 0)

    def test_malformed_sys_id_is_rejected_pre_transport(self) -> None:
        router = _Router({})
        result = _call(
            _connector(router), "servicenow.incident.get",
            {"sys_id": "../../etc/passwd"},
        )
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")
        self.assertEqual(router.call_count, 0)

    def test_non_integer_limit_is_rejected_pre_transport(self) -> None:
        router = _Router({})
        result = _call(
            _connector(router), "servicenow.incident.list", {"limit": "many"}
        )
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")
        self.assertEqual(router.call_count, 0)

    def test_invalid_base_url_fails_closed(self) -> None:
        router = _Router({})
        result = _call(
            _connector(router, base_url="ftp://snow.example.com"),
            "servicenow.incident.list", {},
        )
        self.assertEqual(result.error["code"], "SERVICENOW_INVALID_BASE_URL")
        self.assertEqual(router.call_count, 0)

    def test_base_url_with_userinfo_fails_closed(self) -> None:
        router = _Router({})
        result = _call(
            _connector(router, base_url="https://user:pass@snow.example.com"),
            "servicenow.incident.list", {},
        )
        self.assertEqual(result.error["code"], "SERVICENOW_INVALID_BASE_URL")
        self.assertEqual(router.call_count, 0)


# --- Fail-closed / no-fabrication guardrail (R-2 bullet, R-5) ---


class FailClosedTests(unittest.TestCase):
    def test_upstream_500_is_an_error_not_an_empty_success(self) -> None:
        router = _Router({
            ("GET", "/api/now/table/incident"): httpx.Response(500, json={"error": {}})
        })
        result = _call(_connector(router), "servicenow.incident.list", {})
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "SERVICENOW_UPSTREAM_ERROR")

    def test_upstream_404_on_get_is_an_error(self) -> None:
        router = _Router({
            ("GET", f"/api/now/table/incident/{SYS_ID}"):
                httpx.Response(404, json={"error": {"message": "not found"}})
        })
        result = _call(_connector(router), "servicenow.incident.get", {"sys_id": SYS_ID})
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "SERVICENOW_UPSTREAM_ERROR")

    def test_timeout_fails_closed(self) -> None:
        router = _Router({
            ("GET", "/api/now/table/incident"):
                httpx.ConnectTimeout("timed out"),
        })
        result = _call(_connector(router), "servicenow.incident.list", {})
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "SERVICENOW_TIMEOUT")

    def test_connect_error_fails_closed(self) -> None:
        router = _Router({
            ("GET", "/api/now/table/incident"): httpx.ConnectError("refused"),
        })
        result = _call(_connector(router), "servicenow.incident.list", {})
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "SERVICENOW_UNREACHABLE")

    def test_non_json_body_fails_closed(self) -> None:
        router = _Router({
            ("GET", "/api/now/table/incident"):
                httpx.Response(200, text="<html>login page</html>"),
        })
        result = _call(_connector(router), "servicenow.incident.list", {})
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "SERVICENOW_RESPONSE_INVALID")

    def test_missing_result_key_fails_closed(self) -> None:
        router = _Router({
            ("GET", "/api/now/table/incident"): httpx.Response(200, json={"nope": []})
        })
        result = _call(_connector(router), "servicenow.incident.list", {})
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "SERVICENOW_RESPONSE_INVALID")


# --- Credential resolution through the SPEC-068 seam; no token leak ---


class CredentialTests(unittest.TestCase):
    def test_oauth2_token_attached_but_never_in_result(self) -> None:
        token = "s3cr3t-access-token-DO-NOT-LEAK"
        router = _Router({
            ("POST", "/oauth_token.do"): httpx.Response(200, json={
                "access_token": token, "token_type": "bearer", "expires_in": 1800,
            }),
            ("GET", "/api/now/table/incident"): httpx.Response(200, json={
                "result": [{"sys_id": SYS_ID, "number": "INC0010003"}]
            }),
        })
        path = _write_credentials({
            "snow-read": {
                "scheme": "oauth2_client_credentials",
                "token_url": f"{BASE_URL}/oauth_token.do",
                "client_id": "svc", "client_secret": "shhh",
            }
        })
        try:
            result = _call(
                _connector(router, credential_set="snow-read", credential_sets_path=path),
                "servicenow.incident.list", {},
            )
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertEqual(result.status, "success")
        # The token reached the target as a bearer header...
        table_call = next(
            c for c in router.calls if c.url.path == "/api/now/table/incident"
        )
        self.assertEqual(table_call.headers.get("Authorization"), f"Bearer {token}")
        # ...but never appears in the result envelope, and neither does the secret.
        blob = json.dumps(result.to_dict())
        self.assertNotIn(token, blob)
        self.assertNotIn("shhh", blob)

    def test_unknown_credential_set_fails_closed(self) -> None:
        router = _Router({
            ("GET", "/api/now/table/incident"): httpx.Response(200, json={"result": []})
        })
        path = _write_credentials({"other": {"username": "u", "password": "p"}})
        try:
            result = _call(
                _connector(router, credential_set="snow-read", credential_sets_path=path),
                "servicenow.incident.list", {},
            )
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "CREDENTIAL_SET_NOT_FOUND")
        # The table endpoint was never reached without a resolved credential.
        self.assertTrue(
            all(c.url.path != "/api/now/table/incident" for c in router.calls)
        )

    def test_credential_set_bound_without_store_fails_closed(self) -> None:
        router = _Router({
            ("GET", "/api/now/table/incident"): httpx.Response(200, json={"result": []})
        })
        result = _call(
            _connector(router, credential_set="snow-read", credential_sets_path=""),
            "servicenow.incident.list", {},
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "CREDENTIAL_SET_NOT_FOUND")

    def test_no_credential_set_makes_an_unauthenticated_call(self) -> None:
        """A loopback dev mock needs no credential; the call still succeeds."""
        router = _Router({
            ("GET", "/api/now/table/incident"): httpx.Response(200, json={"result": []})
        })
        result = _call(_connector(router), "servicenow.incident.list", {})
        self.assertEqual(result.status, "success")
        self.assertNotIn("Authorization", router.calls[0].headers)


# --- Audit attribution (R-2 bullet: acting-service identity, no user delegation) ---


class AuditAttributionTests(unittest.TestCase):
    def _tool(self) -> ServiceNowTableTool:
        connector = ServiceNowNativeConnector(
            base_url=BASE_URL, admitted=SERVICENOW_ADMITTED_TOOLS
        )
        return ServiceNowTableTool(connector, SERVICENOW_ADMITTED_TOOLS[0])

    def test_success_attribution_is_acting_service_only(self) -> None:
        ok = ToolResult(
            tool_name="servicenow.incident.list", status="success",
            data={}, evidence=build_evidence("read", "servicenow", 1),
        )
        self.assertEqual(
            self._tool().audit_attribution(ok),
            {"target_identity_mode": "acting_service"},
        )

    def test_timeout_attribution_is_target_unavailable(self) -> None:
        err = make_error_result(
            "servicenow.incident.list", "SERVICENOW_TIMEOUT", "timed out",
            source_system="servicenow",
        )
        self.assertEqual(
            self._tool().audit_attribution(err),
            {"target_identity_mode": "acting_service",
             "failure_class": "target_unavailable"},
        )

    def test_upstream_error_is_not_target_unavailable(self) -> None:
        """The target answered (a fact) — not an unreachable-target class."""
        err = make_error_result(
            "servicenow.incident.list", "SERVICENOW_UPSTREAM_ERROR", "500",
            source_system="servicenow",
        )
        self.assertNotIn("failure_class", self._tool().audit_attribution(err))

    def test_config_gap_is_not_target_unavailable(self) -> None:
        err = make_error_result(
            "servicenow.incident.list", "SERVICENOW_NOT_CONFIGURED", "unset",
            source_system="servicenow",
        )
        self.assertNotIn("failure_class", self._tool().audit_attribution(err))


# --- Factory + config wiring ---


class FactoryTests(unittest.TestCase):
    def test_factory_binds_settings(self) -> None:
        settings = GatewaySettings(
            servicenow_enabled=True,
            servicenow_base_url=BASE_URL,
            servicenow_credential_set="snow-read",
            servicenow_credential_sets_path="/tmp/sets.json",
            servicenow_timeout_ms=5000,
        )
        connector = build_servicenow_connector(settings)
        self.assertTrue(connector.configured)
        registry = ToolRegistry()
        connector.register_tools(registry)
        self.assertEqual({d.name for d in registry.list_definitions()}, EXPECTED_TOOLS)

    def test_from_env_reads_servicenow_knobs(self) -> None:
        env = {
            "GATEWAY_SERVICENOW_ENABLED": "true",
            "GATEWAY_SERVICENOW_BASE_URL": BASE_URL,
            "GATEWAY_SERVICENOW_CREDENTIAL_SET": "snow-read",
            "GATEWAY_SERVICENOW_TIMEOUT_MS": "7000",
        }
        base = {k: v for k, v in os.environ.items() if not k.startswith("GATEWAY_")}
        base.update(env)
        with patch.dict(os.environ, base, clear=True):
            settings = GatewaySettings.from_env()
        self.assertTrue(settings.servicenow_enabled)
        self.assertEqual(settings.servicenow_base_url, BASE_URL)
        self.assertEqual(settings.servicenow_credential_set, "snow-read")
        self.assertEqual(settings.servicenow_timeout_ms, 7000)

    def test_disabled_by_default(self) -> None:
        base = {k: v for k, v in os.environ.items() if not k.startswith("GATEWAY_")}
        with patch.dict(os.environ, base, clear=True):
            settings = GatewaySettings.from_env()
        self.assertFalse(settings.servicenow_enabled)
        self.assertEqual(settings.servicenow_base_url, "")


# --- R-3: deny-by-default is the admission allowlist, not a bundle edit ---


class DenyByDefaultTests(unittest.TestCase):
    """SPEC-067 R-3 (faithful reinterpretation, mirroring SPEC-069 R-3).

    The canonical bundle is action-based (role x ``tools:invoke``/``tools:mutate``)
    and names no tool, so a read-tier ``servicenow.*`` tool rides the existing
    ``allow-operators-tools`` grant with NO bundle edit. Deny-by-default is enforced
    at the gateway admission allowlist: an unlisted capability is never registered,
    so invoking it fails closed with ``TOOL_NOT_FOUND`` — never a target outage and
    never a policy denial.
    """

    def test_unlisted_servicenow_tool_is_denied_by_absence(self) -> None:
        registry = ToolRegistry()
        _connector(_Router({})).register_tools(registry)
        # A deferred (problem/attachment) or mutating (delete) name is never in the
        # admitted set, so it is not registered and cannot be invoked.
        for name in (
            "servicenow.problem.get",
            "servicenow.attachment.get",
            "servicenow.incident.delete",
        ):
            result = _run(registry.invoke(name, {}, {}))
            self.assertEqual(result.status, "error")
            self.assertEqual(result.error["code"], "TOOL_NOT_FOUND")

    def test_read_tier_never_derives_mutate_or_extra_actions(self) -> None:
        registry = ToolRegistry()
        _connector(_Router({})).register_tools(registry)
        for definition in registry.list_definitions():
            # read tier => tools:invoke alone; no capability-specific extra action,
            # so no servicenow tool can ever derive tools:mutate.
            self.assertEqual(definition.risk_level, "read")
            self.assertEqual(definition.extra_required_actions, ())

    def test_unlisted_tool_at_gateway_is_not_a_target_outage(self) -> None:
        """Deny-by-default (absence) and target-unavailable never collapse."""
        response, event, _log = _invoke_captured(
            _connector(_Router({})), "servicenow.problem.get", {},
        )
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"]["code"], "TOOL_NOT_FOUND")
        self.assertEqual(event["event_type"], "tool_invoked")  # not a policy_decision
        self.assertEqual(event["details"]["status"], "error")
        self.assertNotIn("failure_class", event["details"])


# --- R-4: audit fidelity for external ingestion ---


class AuditFidelityTests(unittest.TestCase):
    """SPEC-067 R-4: the ``tool_invoked`` audit record for a ServiceNow read carries
    requester + acting-service + target + tool + outcome, keeps requester and
    acting-service separate (ADR-0004 ``sub``/``act``), names the acting-service
    target-identity mode, and never a secret."""

    def test_success_audit_carries_all_five_fields_and_delegation_mode(self) -> None:
        router = _Router({
            ("GET", "/api/now/table/incident"): httpx.Response(200, json={
                "result": [{"sys_id": SYS_ID, "number": "INC0010001", "state": "New"}]
            })
        })
        response, event, _log = _invoke_captured(
            _connector(router), "servicenow.incident.list", {"limit": 5},
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
        self.assertEqual(details["target_system"], "servicenow")
        self.assertEqual(details["tool_name"], "servicenow.incident.list")
        self.assertEqual(event["outcome"], "success")
        self.assertEqual(details["status"], "success")
        # The connector addresses the target as the acting service, NOT the
        # requesting user's delegated identity (per-user delegation is SPEC-070).
        self.assertEqual(details["target_identity_mode"], "acting_service")
        self.assertNotIn("failure_class", details)

    def test_no_secret_or_token_reaches_audit_or_logs(self) -> None:
        token = "SUPERSECRET-SNOW-TOKEN-9"
        client_secret = "shhh-client-secret"
        router = _Router({
            ("POST", "/oauth_token.do"): httpx.Response(200, json={
                "access_token": token, "token_type": "bearer", "expires_in": 1800,
            }),
            ("GET", "/api/now/table/incident"): httpx.Response(200, json={
                "result": [{"sys_id": SYS_ID, "number": "INC0010001"}]
            }),
        })
        path = _write_credentials({
            "snow-read": {
                "scheme": "oauth2_client_credentials",
                "token_url": f"{BASE_URL}/oauth_token.do",
                "client_id": "svc", "client_secret": client_secret,
            }
        })
        try:
            response, event, log_str = _invoke_captured(
                _connector(router, credential_set="snow-read",
                           credential_sets_path=path),
                "servicenow.incident.list", {},
            )
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertEqual(response.status_code, 200)
        blob = json.dumps(event) + log_str
        for secret in (token, client_secret, "client_secret", "password"):
            self.assertNotIn(secret, blob)
        # The token still reached the target (SPEC-068), so the call truly ran.
        table_call = next(
            c for c in router.calls if c.url.path == "/api/now/table/incident"
        )
        self.assertEqual(table_call.headers.get("Authorization"), f"Bearer {token}")


# --- R-5: fail-closed / no-fabrication at the audit choke point ---


class FailClosedAuditTests(unittest.TestCase):
    """SPEC-067 R-5: an unreachable/timed-out target is a *failed* outcome attributed
    ``target_unavailable`` — distinct from a policy denial and never a fabricated
    success; an upstream error the target answered is a fact, not an unavailability."""

    def test_timeout_is_failed_and_attributed_target_unavailable(self) -> None:
        router = _Router({
            ("GET", "/api/now/table/incident"): httpx.ConnectTimeout("timed out"),
        })
        response, event, _log = _invoke_captured(
            _connector(router), "servicenow.incident.list", {},
        )
        self.assertEqual(response.status_code, 400)
        # A failed outcome, never an empty/fabricated "success".
        self.assertEqual(json.loads(response.body)["status"], "error")
        self.assertEqual(event["event_type"], "tool_invoked")  # not a policy_decision
        self.assertEqual(event["outcome"], "error")
        self.assertEqual(event["details"]["status"], "error")
        self.assertEqual(event["details"]["failure_class"], "target_unavailable")
        self.assertEqual(event["details"]["target_system"], "servicenow")

    def test_connect_error_is_attributed_target_unavailable(self) -> None:
        router = _Router({
            ("GET", "/api/now/table/incident"): httpx.ConnectError("refused"),
        })
        _response, event, _log = _invoke_captured(
            _connector(router), "servicenow.incident.list", {},
        )
        self.assertEqual(event["outcome"], "error")
        self.assertEqual(event["details"]["failure_class"], "target_unavailable")

    def test_upstream_error_is_not_target_unavailable(self) -> None:
        # The target WAS available and answered with an error: a fact, not an
        # unavailability (SPEC-058 "an upstream 4xx/5xx is a fact, not an error").
        router = _Router({
            ("GET", "/api/now/table/incident"): httpx.Response(500, json={"error": {}}),
        })
        _response, event, _log = _invoke_captured(
            _connector(router), "servicenow.incident.list", {},
        )
        self.assertEqual(event["outcome"], "error")
        self.assertNotIn("failure_class", event["details"])

    def test_target_unavailable_is_distinct_from_policy_denial(self) -> None:
        # No identity -> a policy_decision/deny event carrying no failure_class:
        # a denial and a target outage never collapse into one another.
        router = _Router({
            ("GET", "/api/now/table/incident"): httpx.Response(200, json={"result": []}),
        })
        response, event, _log = _invoke_captured(
            _connector(router), "servicenow.incident.list", {}, identity=None,
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(event["event_type"], "policy_decision")
        self.assertEqual(event["outcome"], "deny")
        self.assertNotIn("failure_class", event["details"])


if __name__ == "__main__":
    unittest.main()
