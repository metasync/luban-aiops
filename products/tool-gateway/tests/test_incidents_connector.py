"""Tests for the incidents connector (SPEC-015 R-4)."""

import asyncio
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import jsonschema

from tool_gateway.tools.incidents_connector import (
    IncidentsConnector,
    _coerce_limit,
)
from tool_gateway.tools.registry import ToolRegistry

SCHEMAS_DIR = (
    Path(__file__).resolve().parents[3] / "shared" / "shared-contracts" / "schemas"
)

INCIDENT_ENVELOPE = {
    "incident_id": "inc-9f2c1ab34de5",
    "fingerprint": "alertmanager:{groupkey}",
    "source": "alertmanager",
    "severity": "critical",
    "status": "triaged",
    "title": "KubePodNotReady payments/api",
    "summary": "Pod payments/api stuck not ready for 15 minutes.",
    "labels": {"alertname": "KubePodNotReady", "namespace": "payments"},
    "session_id": "incident-inc-9f2c1ab34de5",
    "created_at": "2026-08-20T09:00:00+00:00",
    "updated_at": "2026-08-20T09:05:00+00:00",
}

REPORT_ENVELOPE = {
    "incident_id": "inc-9f2c1ab34de5",
    "summary": "Pod payments/api is CrashLooping due to a bad config key.",
    "severity_assessment": "critical",
    "evidence": [
        {"source": "k8s.get_pod", "description": "Pod restartCount=7, CrashLoopBackOff."}
    ],
    "hypotheses": ["Invalid config key in payments configmap."],
    "next_steps": [
        {
            "title": "Inspect the payments configmap",
            "rationale": "Crash log references missing key 'db_url'.",
            "priority": "high",
        }
    ],
    "skills_cited": ["sre-alerting/alerts/kubepodnotready"],
    "session_id": "incident-inc-9f2c1ab34de5",
    "generated_at": "2026-08-20T09:05:00+00:00",
    "generated_by": "alice",
}

DISPATCH = {
    "connector": "audit",
    "status": "delivered",
    "reference": "evt-2f0f",
    "error": None,
    "created_at": "2026-08-20T09:05:01+00:00",
}

DETAIL_PAYLOAD = {
    "incident": INCIDENT_ENVELOPE,
    "report": REPORT_ENVELOPE,
    "dispatches": [DISPATCH],
}

# The list endpoint returns entries without the summary field.
LIST_ENTRY = {
    key: value for key, value in INCIDENT_ENVELOPE.items() if key != "summary"
}


def _run(coro):
    return asyncio.run(coro)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class IncidentsConnectorBase(unittest.TestCase):
    def setUp(self) -> None:
        self.connector = IncidentsConnector(
            url="http://incident-service:8000",
            client_id="tool-gateway",
            client_secret="secret",
        )
        self.requests: list[tuple[str, dict | None]] = []

    def _fake_get(self, response: FakeResponse | Exception):
        async def _get(path, params=None):
            self.requests.append((path, params))
            if isinstance(response, Exception):
                raise response
            return response

        return _get


class IncidentsConnectorRegistrationTests(unittest.TestCase):
    def test_registers_two_tools(self) -> None:
        connector = IncidentsConnector(url="http://incident-service:8000")
        registry = ToolRegistry()
        connector.register_tools(registry)
        names = {d.name for d in registry.list_definitions()}
        self.assertEqual(names, {"incidents.list", "incidents.get"})

    def test_all_tools_are_read_level_incidents_category(self) -> None:
        connector = IncidentsConnector(url="http://incident-service:8000")
        registry = ToolRegistry()
        connector.register_tools(registry)
        for defn in registry.list_definitions():
            self.assertEqual(defn.risk_level, "read")
            self.assertEqual(defn.category, "incidents")


class IncidentsListTests(IncidentsConnectorBase):
    def test_list_success_projects_entry_keys(self) -> None:
        self.connector._get = self._fake_get(
            FakeResponse(
                200,
                {
                    "incidents": [LIST_ENTRY],
                    "total": 1,
                    "offset": 0,
                    "limit": 20,
                },
            )
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("incidents.list", {}, {}))

        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["total"], 1)
        entry = result.data["incidents"][0]
        self.assertEqual(
            set(entry),
            {
                "incident_id", "fingerprint", "source", "severity",
                "status", "title", "labels", "session_id",
                "created_at", "updated_at",
            },
        )
        # summary stays out of the list view; absent optionals dropped.
        self.assertNotIn("summary", entry)
        self.assertNotIn("resolved_at", entry)
        self.assertEqual(result.evidence["source_system"], "incidents")
        self.assertEqual(result.evidence["risk_level"], "read")
        # Upstream pagination defaults forwarded.
        path, params = self.requests[0]
        self.assertEqual(path, "/api/v1/incidents")
        self.assertEqual(params["limit"], 20)
        self.assertEqual(params["offset"], 0)

    def test_list_forwards_filters_and_pagination(self) -> None:
        self.connector._get = self._fake_get(
            FakeResponse(200, {"incidents": [], "total": 0})
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        _run(registry.invoke(
            "incidents.list",
            {"status": "triaged", "severity": "critical",
             "source": "alertmanager", "limit": 5, "offset": 10},
            {},
        ))
        _, params = self.requests[0]
        self.assertEqual(params["status"], "triaged")
        self.assertEqual(params["severity"], "critical")
        self.assertEqual(params["source"], "alertmanager")
        self.assertEqual(params["limit"], 5)
        self.assertEqual(params["offset"], 10)

    def test_list_empty_is_success(self) -> None:
        self.connector._get = self._fake_get(
            FakeResponse(200, {"incidents": [], "total": 0})
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("incidents.list", {}, {}))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data, {"incidents": [], "total": 0})

    def test_list_rejects_unknown_enum_values(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        for params in (
            {"status": "bogus"},
            {"severity": "panic"},
            {"source": "pagerduty"},
        ):
            result = _run(registry.invoke("incidents.list", params, {}))
            self.assertEqual(result.status, "error", params)
            self.assertEqual(result.error["code"], "INVALID_PARAMETERS")
        self.assertEqual(self.requests, [])

    def test_list_bad_offset_rejected(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        for bad in ("x", -1):
            result = _run(
                registry.invoke("incidents.list", {"offset": bad}, {})
            )
            self.assertEqual(result.status, "error")
            self.assertEqual(result.error["code"], "INVALID_PARAMETERS")

    def test_list_bad_limit_type(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("incidents.list", {"limit": "x"}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")

    def test_list_limit_clamped(self) -> None:
        self.connector._get = self._fake_get(
            FakeResponse(200, {"incidents": [], "total": 0})
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        _run(registry.invoke("incidents.list", {"limit": 999}, {}))
        _, params = self.requests[0]
        self.assertEqual(params["limit"], 50)

    def test_list_unreachable_maps_to_tool_execution_error(self) -> None:
        self.connector._get = self._fake_get(
            httpx.ConnectError("connection refused")
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("incidents.list", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "TOOL_EXECUTION_ERROR")
        self.assertEqual(result.evidence["source_system"], "incidents")

    def test_list_upstream_error_passes_through_code(self) -> None:
        self.connector._get = self._fake_get(
            FakeResponse(
                400,
                {"error": {"code": "INVALID_PARAMETERS", "message": "bad"}},
            )
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("incidents.list", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")


class IncidentsGetTests(IncidentsConnectorBase):
    def test_get_success_returns_detail_verbatim(self) -> None:
        self.connector._get = self._fake_get(FakeResponse(200, DETAIL_PAYLOAD))
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke(
            "incidents.get", {"incident_id": "inc-9f2c1ab34de5"}, {}
        ))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data, DETAIL_PAYLOAD)
        path, _ = self.requests[0]
        self.assertEqual(path, "/api/v1/incidents/inc-9f2c1ab34de5")
        self.assertEqual(result.evidence["source_system"], "incidents")
        self.assertEqual(result.evidence["risk_level"], "read")

    def test_get_missing_incident_id(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("incidents.get", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")

    def test_get_rejects_ids_outside_the_contract_pattern(self) -> None:
        """The id is interpolated into the upstream URL path; anything that
        could inject path or query segments must be rejected before use."""
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        for bad_id in (
            "../health/live",
            "inc-a?limit=100",
            "inc-a#frag",
            "inc-XYZ",
            "inc-..",
            "plain-id",
            "inc-",
        ):
            result = _run(
                registry.invoke("incidents.get", {"incident_id": bad_id}, {})
            )
            self.assertEqual(result.status, "error", bad_id)
            self.assertEqual(
                result.error["code"], "INVALID_PARAMETERS", bad_id
            )
        self.assertEqual(self.requests, [])

    def test_get_404_maps_to_incident_not_found(self) -> None:
        self.connector._get = self._fake_get(
            FakeResponse(
                404,
                {"error": {"code": "INCIDENT_NOT_FOUND", "message": "unknown"}},
            )
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(
            registry.invoke("incidents.get", {"incident_id": "inc-abc123"}, {})
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INCIDENT_NOT_FOUND")

    def test_get_unreachable_maps_to_tool_execution_error(self) -> None:
        self.connector._get = self._fake_get(
            httpx.ConnectError("connection refused")
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(
            registry.invoke("incidents.get", {"incident_id": "inc-abc123"}, {})
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "TOOL_EXECUTION_ERROR")

    def test_get_payload_conforms_to_contracts(self) -> None:
        """Contract binding: connector payloads validate against
        incident.schema.json / triage-report.schema.json (SPEC-015 R-4)."""
        incident_schema = json.loads(
            (SCHEMAS_DIR / "incident.schema.json").read_text()
        )
        report_schema = json.loads(
            (SCHEMAS_DIR / "triage-report.schema.json").read_text()
        )
        jsonschema.validate(INCIDENT_ENVELOPE, incident_schema)
        jsonschema.validate(REPORT_ENVELOPE, report_schema)
        self.connector._get = self._fake_get(FakeResponse(200, DETAIL_PAYLOAD))
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke(
            "incidents.get", {"incident_id": "inc-9f2c1ab34de5"}, {}
        ))
        jsonschema.validate(result.data["incident"], incident_schema)
        jsonschema.validate(result.data["report"], report_schema)


class CoerceLimitTests(unittest.TestCase):
    def test_defaults(self) -> None:
        self.assertEqual(_coerce_limit(None), (20, None))

    def test_rejects_non_integer(self) -> None:
        _, error = _coerce_limit("abc")
        self.assertIn("must be an integer", error)

    def test_rejects_below_one(self) -> None:
        _, error = _coerce_limit(0)
        self.assertIn("at least 1", error)

    def test_clamps_upper_bound(self) -> None:
        self.assertEqual(_coerce_limit(100), (50, None))


class RegistryGatingTests(unittest.TestCase):
    """_build_tool_registry gates the incidents connector on the URL setting."""

    def _registry_names(self, env_overrides: dict) -> set:
        from tool_gateway.app import _build_tool_registry
        from tool_gateway.core.config import get_settings

        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GATEWAY_")
        }
        env.update(env_overrides)
        with patch.dict(os.environ, env, clear=True):
            get_settings.cache_clear()
            try:
                registry, _ = _build_tool_registry()
                return {d.name for d in registry.list_definitions()}
            finally:
                get_settings.cache_clear()

    def test_incidents_tools_absent_when_url_unset(self) -> None:
        names = self._registry_names({})
        self.assertNotIn("incidents.list", names)
        self.assertNotIn("incidents.get", names)

    def test_incidents_tools_registered_when_url_set(self) -> None:
        names = self._registry_names(
            {
                "GATEWAY_INCIDENTS_SERVICE_URL": "http://incident-service:8000",
                "GATEWAY_INCIDENTS_CLIENT_SECRET": "secret",
            }
        )
        self.assertEqual(names, {"incidents.list", "incidents.get"})

    def test_incidents_and_skills_tools_coexist(self) -> None:
        names = self._registry_names(
            {
                "GATEWAY_SKILLS_SERVICE_URL": "http://skills-hub:8000",
                "GATEWAY_SKILLS_CLIENT_SECRET": "secret",
                "GATEWAY_INCIDENTS_SERVICE_URL": "http://incident-service:8000",
                "GATEWAY_INCIDENTS_CLIENT_SECRET": "secret",
            }
        )
        self.assertEqual(
            names,
            {
                "skills.search", "skills.get", "skills.list",
                "incidents.list", "incidents.get",
            },
        )


if __name__ == "__main__":
    unittest.main()
