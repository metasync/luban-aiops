"""Skills connector unit tests with a fake skills-hub double (SPEC-014 R-4)."""

import asyncio
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import jsonschema

from tool_gateway.tools.registry import ToolRegistry
from tool_gateway.tools.skills_connector import (
    SkillsConnector,
    _coerce_limit,
)

SCHEMAS_DIR = (
    Path(__file__).resolve().parents[3] / "shared" / "shared-contracts" / "schemas"
)

SKILL_ENVELOPE = {
    "skill_id": "sre-alerting/alerts/kubepodnotready",
    "source_id": "sre-alerting",
    "source_path": "alerts/KubePodNotReady.md",
    "source_ref": "abc123",
    "title": "KubePodNotReady",
    "description": "Pod stuck not ready — triage steps.",
    "tags": ["kubernetes", "KubePodNotReady"],
    "version": "1.0",
    "source_url": "https://github.com/prometheus-operator/runbooks",
    "updated_at": "2026-08-15T12:00:00+00:00",
    "body": "Check the pod events first.",
}

SEARCH_MATCH = {
    "skill_id": "sre-alerting/alerts/kubepodnotready",
    "source_id": "sre-alerting",
    "source_path": "alerts/KubePodNotReady.md",
    "source_ref": "abc123",
    "title": "KubePodNotReady",
    "description": "Pod stuck not ready — triage steps.",
    "updated_at": "2026-08-15T12:00:00+00:00",
    "score": 6.0,
    "excerpt": "Check the pod events first.",
}

# The list endpoint returns summary envelopes (full envelope minus body).
LIST_SUMMARY = {key: value for key, value in SKILL_ENVELOPE.items() if key != "body"}


def _run(coro):
    return asyncio.run(coro)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class SkillsConnectorBase(unittest.TestCase):
    def setUp(self) -> None:
        self.connector = SkillsConnector(
            url="http://skills-hub:8000",
            client_id="tool-gateway",
            client_secret="secret",
        )
        self.requests: list[tuple[str, dict | None]] = []
        self.request_ids: list[str | None] = []

    def _fake_get(self, response: FakeResponse | Exception):
        async def _get(path, params=None, request_id=None):
            self.requests.append((path, params))
            self.request_ids.append(request_id)
            if isinstance(response, Exception):
                raise response
            return response

        return _get


class SkillsConnectorRegistrationTests(unittest.TestCase):
    def test_registers_three_tools(self) -> None:
        connector = SkillsConnector(url="http://skills-hub:8000")
        registry = ToolRegistry()
        connector.register_tools(registry)
        names = {d.name for d in registry.list_definitions()}
        self.assertEqual(
            names, {"skills.search", "skills.get", "skills.list"}
        )

    def test_all_tools_are_read_level_skills_category(self) -> None:
        connector = SkillsConnector(url="http://skills-hub:8000")
        registry = ToolRegistry()
        connector.register_tools(registry)
        for defn in registry.list_definitions():
            self.assertEqual(defn.risk_level, "read")
            self.assertEqual(defn.category, "skills")


class SkillsSearchTests(SkillsConnectorBase):
    def test_search_success_projects_match_keys(self) -> None:
        self.connector._get = self._fake_get(
            FakeResponse(200, {"matches": [SEARCH_MATCH], "total": 1})
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("skills.search", {"query": "pod"}, {}))

        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["total"], 1)
        match = result.data["matches"][0]
        self.assertEqual(
            set(match),
            {
                "skill_id", "title", "excerpt", "source_id",
                "source_path", "source_ref", "updated_at",
            },
        )
        self.assertEqual(match["excerpt"], "Check the pod events first.")
        # score/description are dropped from the projection.
        self.assertNotIn("score", match)
        self.assertNotIn("description", match)
        self.assertEqual(result.evidence["source_system"], "skills")
        self.assertEqual(result.evidence["risk_level"], "read")
        # Upstream query parameters forwarded.
        path, params = self.requests[0]
        self.assertEqual(path, "/api/v1/skills/search")
        self.assertEqual(params["q"], "pod")
        self.assertEqual(params["limit"], 5)

    def test_search_forwards_filters_and_limit(self) -> None:
        self.connector._get = self._fake_get(
            FakeResponse(200, {"matches": [], "total": 0})
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        _run(registry.invoke(
            "skills.search",
            {"query": "pod", "source": "sre-alerting", "tag": "kubernetes",
             "limit": 3},
            {},
        ))
        _, params = self.requests[0]
        self.assertEqual(params["source"], "sre-alerting")
        self.assertEqual(params["tag"], "kubernetes")
        self.assertEqual(params["limit"], 3)

    def test_search_empty_matches_is_success(self) -> None:
        """Empty-match contract: success with matches: [] (SPEC-014 R-5)."""
        self.connector._get = self._fake_get(
            FakeResponse(200, {"matches": [], "total": 0})
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("skills.search", {"query": "nope"}, {}))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data, {"matches": [], "total": 0})

    def test_search_missing_query(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("skills.search", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")

    def test_search_limit_clamped(self) -> None:
        self.connector._get = self._fake_get(
            FakeResponse(200, {"matches": [], "total": 0})
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        _run(registry.invoke("skills.search", {"query": "pod", "limit": 999}, {}))
        _, params = self.requests[0]
        self.assertEqual(params["limit"], 20)

    def test_search_bad_limit_type(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(
            registry.invoke("skills.search", {"query": "pod", "limit": "x"}, {})
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")

    def test_search_unreachable_maps_to_tool_execution_error(self) -> None:
        self.connector._get = self._fake_get(
            httpx.ConnectError("connection refused")
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("skills.search", {"query": "pod"}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "TOOL_EXECUTION_ERROR")
        self.assertEqual(result.evidence["source_system"], "skills")

    def test_search_upstream_4xx_passes_through_code(self) -> None:
        self.connector._get = self._fake_get(
            FakeResponse(
                400,
                {"error": {"code": "INVALID_PARAMETERS", "message": "q is required"}},
            )
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("skills.search", {"query": "pod"}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")
        self.assertEqual(result.error["message"], "q is required")


class SkillsGetTests(SkillsConnectorBase):
    def test_get_success_returns_full_envelope(self) -> None:
        self.connector._get = self._fake_get(FakeResponse(200, SKILL_ENVELOPE))
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke(
            "skills.get",
            {"skill_id": "sre-alerting/alerts/kubepodnotready"},
            {},
        ))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data, SKILL_ENVELOPE)
        path, _ = self.requests[0]
        self.assertEqual(
            path, "/api/v1/skills/sre-alerting/alerts/kubepodnotready"
        )

    def test_get_missing_skill_id(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("skills.get", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")

    def test_get_rejects_ids_outside_the_contract_pattern(self) -> None:
        """The id is interpolated into the upstream URL path; anything that
        could inject path or query segments must be rejected before use."""
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        for bad_id in (
            "../health/live",
            "a/b?limit=100",
            "a/b#frag",
            "UPPER/case",
            "single-segment",
        ):
            result = _run(
                registry.invoke("skills.get", {"skill_id": bad_id}, {})
            )
            self.assertEqual(result.status, "error", bad_id)
            self.assertEqual(
                result.error["code"], "INVALID_PARAMETERS", bad_id
            )
        self.assertEqual(self.requests, [])

    def test_get_404_maps_to_skill_not_found(self) -> None:
        self.connector._get = self._fake_get(
            FakeResponse(
                404,
                {"error": {"code": "SKILL_NOT_FOUND", "message": "unknown"}},
            )
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("skills.get", {"skill_id": "a/b"}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "SKILL_NOT_FOUND")

    def test_get_unreachable_maps_to_tool_execution_error(self) -> None:
        self.connector._get = self._fake_get(
            httpx.ConnectError("connection refused")
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("skills.get", {"skill_id": "a/b"}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "TOOL_EXECUTION_ERROR")

    def test_get_payload_conforms_to_skill_schema(self) -> None:
        """Contract binding: connector payloads validate against
        skill.schema.json (SPEC-014 R-4)."""
        schema = json.loads((SCHEMAS_DIR / "skill.schema.json").read_text())
        jsonschema.validate(SKILL_ENVELOPE, schema)
        self.connector._get = self._fake_get(FakeResponse(200, SKILL_ENVELOPE))
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("skills.get", {"skill_id": "a/b"}, {}))
        jsonschema.validate(result.data, schema)


class SkillsListTests(SkillsConnectorBase):
    def test_list_success_projects_summary_keys(self) -> None:
        self.connector._get = self._fake_get(
            FakeResponse(
                200,
                {
                    "skills": [LIST_SUMMARY],
                    "total": 1,
                    "offset": 0,
                    "limit": 20,
                },
            )
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("skills.list", {}, {}))

        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["total"], 1)
        entry = result.data["skills"][0]
        self.assertEqual(
            set(entry),
            {
                "skill_id", "title", "description", "source_id",
                "tags", "updated_at",
            },
        )
        self.assertEqual(result.evidence["source_system"], "skills")
        self.assertEqual(result.evidence["risk_level"], "read")
        # Upstream pagination defaults forwarded.
        path, params = self.requests[0]
        self.assertEqual(path, "/api/v1/skills")
        self.assertEqual(params["limit"], 20)
        self.assertEqual(params["offset"], 0)

    def test_list_forwards_filters_and_pagination(self) -> None:
        self.connector._get = self._fake_get(
            FakeResponse(200, {"skills": [], "total": 0})
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        _run(registry.invoke(
            "skills.list",
            {"source": "sre-alerting", "tag": "kubernetes",
             "limit": 5, "offset": 10},
            {},
        ))
        _, params = self.requests[0]
        self.assertEqual(params["source"], "sre-alerting")
        self.assertEqual(params["tag"], "kubernetes")
        self.assertEqual(params["limit"], 5)
        self.assertEqual(params["offset"], 10)

    def test_list_empty_catalog_is_success(self) -> None:
        self.connector._get = self._fake_get(
            FakeResponse(200, {"skills": [], "total": 0})
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("skills.list", {}, {}))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data, {"skills": [], "total": 0})

    def test_list_bad_offset_rejected(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        for bad in ("x", -1):
            result = _run(
                registry.invoke("skills.list", {"offset": bad}, {})
            )
            self.assertEqual(result.status, "error")
            self.assertEqual(result.error["code"], "INVALID_PARAMETERS")

    def test_list_bad_limit_type(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("skills.list", {"limit": "x"}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")

    def test_list_unreachable_maps_to_tool_execution_error(self) -> None:
        self.connector._get = self._fake_get(
            httpx.ConnectError("connection refused")
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("skills.list", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "TOOL_EXECUTION_ERROR")
        self.assertEqual(result.evidence["source_system"], "skills")

    def test_list_upstream_error_passes_through_code(self) -> None:
        self.connector._get = self._fake_get(
            FakeResponse(
                400,
                {"error": {"code": "INVALID_PARAMETERS", "message": "bad"}},
            )
        )
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("skills.list", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")


class CoerceLimitTests(unittest.TestCase):
    def test_defaults(self) -> None:
        self.assertEqual(_coerce_limit(None), (5, None))

    def test_rejects_non_integer(self) -> None:
        _, error = _coerce_limit("abc")
        self.assertIn("must be an integer", error)

    def test_rejects_below_one(self) -> None:
        _, error = _coerce_limit(0)
        self.assertIn("at least 1", error)

    def test_clamps_upper_bound(self) -> None:
        self.assertEqual(_coerce_limit(100), (20, None))


class RegistryGatingTests(unittest.TestCase):
    """_build_tool_registry gates the skills connector on the URL setting."""

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

    def test_skills_tools_absent_when_url_unset(self) -> None:
        names = self._registry_names({})
        self.assertNotIn("skills.search", names)
        self.assertNotIn("skills.get", names)
        self.assertNotIn("skills.list", names)
        # Defaults disable k8s/elastic, so the registry is empty: byte
        # parity with the pre-SPEC-014 gateway.
        self.assertEqual(names, set())

    def test_skills_tools_registered_when_url_set(self) -> None:
        names = self._registry_names(
            {
                "GATEWAY_SKILLS_SERVICE_URL": "http://skills-hub:8000",
                "GATEWAY_SKILLS_CLIENT_SECRET": "secret",
            }
        )
        self.assertEqual(
            names, {"skills.search", "skills.get", "skills.list"}
        )


class RequestIdCorrelationTests(SkillsConnectorBase):
    """Tools forward the caller's request id to skills-hub (SPEC-029 R-3)."""

    _PAYLOAD = {"matches": [], "skills": [], "total": 0}

    def test_tools_forward_identity_request_id(self) -> None:
        cases = (
            ("skills.search", {"query": "pod"}),
            ("skills.get", {"skill_id": "sre-alerting/alerts/kubepodnotready"}),
            ("skills.list", {}),
        )
        for tool_name, params in cases:
            with self.subTest(tool=tool_name):
                self.request_ids.clear()
                self.connector._get = self._fake_get(
                    FakeResponse(200, self._PAYLOAD)
                )
                registry = ToolRegistry()
                self.connector.register_tools(registry)
                _run(
                    registry.invoke(
                        tool_name, params, {"request_id": "req-corr-1"}
                    )
                )
                self.assertEqual(self.request_ids, ["req-corr-1"])

    def test_missing_request_id_forwards_none(self) -> None:
        self.connector._get = self._fake_get(FakeResponse(200, self._PAYLOAD))
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        _run(registry.invoke("skills.search", {"query": "pod"}, {}))
        self.assertEqual(self.request_ids, [None])


class ConnectorGetHeaderTests(unittest.TestCase):
    """_get sets the x-request-id header only when a request id is given."""

    def _captured_get(self, request_id: str | None) -> dict:
        connector = SkillsConnector(
            url="http://skills-hub:8000",
            client_id="tool-gateway",
            client_secret="secret",
        )
        captured: dict = {}

        class _FakeAsyncClient:
            def __init__(self, timeout=None):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, url, params=None, headers=None, auth=None):
                captured.update(
                    {"url": url, "headers": headers, "auth": auth}
                )
                return FakeResponse(200, {})

        with patch(
            "tool_gateway.tools.skills_connector.httpx.AsyncClient",
            _FakeAsyncClient,
        ):
            _run(connector._get("/api/v1/skills", request_id=request_id))
        return captured

    def test_header_set_when_request_id_given(self) -> None:
        captured = self._captured_get("req-9")
        self.assertEqual(captured["headers"], {"x-request-id": "req-9"})
        self.assertEqual(captured["auth"], ("tool-gateway", "secret"))

    def test_header_omitted_without_request_id(self) -> None:
        captured = self._captured_get(None)
        self.assertIsNone(captured["headers"])


if __name__ == "__main__":
    unittest.main()
