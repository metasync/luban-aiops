"""Incidents proxy route tests (SPEC-015 R-7).

Validates the gateway-side gates for the incidents surface: per-action
policy enforcement (incident:read / incident:create / incident:triage),
gateway-held Basic credential upstream (never the user's token), delegation
forwarding on triage, 503 when unconfigured, and upstream error mapping.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from platform_gateway.app import create_app
from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.schemas.api import IdentityContext
from platform_gateway.services.policy_engine import reset_policy_state

INCIDENT_ENVELOPE = {
    "incident_id": "inc-9f2c1ab34de5",
    "fingerprint": "manual:abc",
    "source": "manual",
    "severity": "warning",
    "status": "new",
    "title": "Payments API degraded",
    "summary": "Elevated 5xx on payments/api.",
    "labels": {"team": "payments"},
    "reported_by": "operator.user",
    "created_at": "2026-08-20T09:00:00+00:00",
    "updated_at": "2026-08-20T09:00:00+00:00",
}

DETAIL_PAYLOAD = {
    "incident": INCIDENT_ENVELOPE,
    "report": None,
    "dispatches": [],
}


def _identity(role: str) -> IdentityContext:
    return IdentityContext(
        subject=f"user-{role}",
        username=f"{role}.user",
        roles=[role],
    )


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient capturing the proxied calls."""

    def __init__(self, response=None, raise_exc=None) -> None:
        self._response = response
        self._raise = raise_exc
        self.calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    def _record(self, method, url, params, json, auth, headers) -> _FakeResponse:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "json": json,
                "auth": auth,
                "headers": headers,
            }
        )
        if self._raise is not None:
            raise self._raise
        return self._response

    async def get(self, url, params=None, auth=None, headers=None):
        return self._record("GET", url, params, None, auth, headers)

    async def post(self, url, json=None, auth=None, headers=None):
        return self._record("POST", url, None, json, auth, headers)


def _settings(**overrides) -> PlatformGatewaySettings:
    defaults = dict(
        require_auth=True,
        incident_service_url="http://incident-service:8000",
        incident_client_id="platform-gateway",
        incident_client_secret="pg-secret",
    )
    defaults.update(overrides)
    return PlatformGatewaySettings(**defaults)


class IncidentsProxyBase(unittest.TestCase):
    def setUp(self) -> None:
        reset_policy_state()
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: _settings()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_policy_state()

    def _patch_identity(self, role: str):
        identity = _identity(role)

        async def fake_identity(settings, request, request_id):
            return identity

        return patch(
            "platform_gateway.api.routes.incidents.resolve_request_identity",
            fake_identity,
        )

    def _patch_httpx(self, fake: _FakeAsyncClient):
        return patch(
            "platform_gateway.services.incident_client.httpx.AsyncClient",
            return_value=fake,
        )


class IncidentsListTests(IncidentsProxyBase):
    def test_operator_allowed_and_proxied_with_gateway_credential(self) -> None:
        fake = _FakeAsyncClient(
            response=_FakeResponse(
                200, {"incidents": [INCIDENT_ENVELOPE], "total": 1,
                      "offset": 0, "limit": 20}
            )
        )
        with self._patch_identity("operator"), self._patch_httpx(fake):
            response = self.client.get("/api/v1/incidents")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        call = fake.calls[0]
        self.assertEqual(call["method"], "GET")
        self.assertEqual(call["url"], "http://incident-service:8000/api/v1/incidents")
        # The proxy authenticates with its own credential, never the user's.
        self.assertEqual(call["auth"], ("platform-gateway", "pg-secret"))
        self.assertEqual(call["params"]["limit"], 20)
        self.assertEqual(call["params"]["offset"], 0)

    def test_observer_allowed_to_read(self) -> None:
        fake = _FakeAsyncClient(
            response=_FakeResponse(200, {"incidents": [], "total": 0})
        )
        with self._patch_identity("read-only-observer"), self._patch_httpx(fake):
            response = self.client.get("/api/v1/incidents")
        self.assertEqual(response.status_code, 200)

    def test_ungranted_role_denied_before_upstream(self) -> None:
        fake = _FakeAsyncClient(
            response=_FakeResponse(200, {"incidents": [], "total": 0})
        )
        with self._patch_identity("auditor"), self._patch_httpx(fake):
            response = self.client.get("/api/v1/incidents")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["action"], "incident:read")
        self.assertEqual(fake.calls, [])

    def test_filters_forwarded_to_upstream(self) -> None:
        fake = _FakeAsyncClient(
            response=_FakeResponse(200, {"incidents": [], "total": 0})
        )
        with self._patch_identity("operator"), self._patch_httpx(fake):
            response = self.client.get(
                "/api/v1/incidents",
                params={
                    "status": "triaged",
                    "severity": "critical",
                    "source": "alertmanager",
                    "limit": 5,
                    "offset": 10,
                },
            )
        self.assertEqual(response.status_code, 200)
        params = fake.calls[0]["params"]
        self.assertEqual(params["status"], "triaged")
        self.assertEqual(params["severity"], "critical")
        self.assertEqual(params["source"], "alertmanager")
        self.assertEqual(params["limit"], 5)
        self.assertEqual(params["offset"], 10)


class IncidentsGetTests(IncidentsProxyBase):
    def test_get_detail_proxied(self) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(200, DETAIL_PAYLOAD))
        with self._patch_identity("operator"), self._patch_httpx(fake):
            response = self.client.get("/api/v1/incidents/inc-9f2c1ab34de5")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["incident"]["incident_id"], "inc-9f2c1ab34de5")
        self.assertEqual(
            fake.calls[0]["url"],
            "http://incident-service:8000/api/v1/incidents/inc-9f2c1ab34de5",
        )

    def test_get_report_proxied(self) -> None:
        report = {"incident_id": "inc-9f2c1ab34de5", "summary": "x"}
        fake = _FakeAsyncClient(response=_FakeResponse(200, report))
        with self._patch_identity("operator"), self._patch_httpx(fake):
            response = self.client.get(
                "/api/v1/incidents/inc-9f2c1ab34de5/report"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            fake.calls[0]["url"],
            "http://incident-service:8000/api/v1/incidents/inc-9f2c1ab34de5/report",
        )

    def test_invalid_incident_id_rejected_before_upstream(self) -> None:
        """The id is interpolated into the upstream URL path; ids outside
        the contract pattern are rejected before any upstream call."""
        fake = _FakeAsyncClient(response=_FakeResponse(200, DETAIL_PAYLOAD))
        with self._patch_identity("operator"), self._patch_httpx(fake):
            for bad_id in ("inc-XYZ", "plain", "inc-", "INC-abc123"):
                response = self.client.get(f"/api/v1/incidents/{bad_id}")
                self.assertEqual(response.status_code, 400, bad_id)
        self.assertEqual(fake.calls, [])

    def test_upstream_404_passes_through(self) -> None:
        fake = _FakeAsyncClient(
            response=_FakeResponse(
                404,
                {"error": {"code": "INCIDENT_NOT_FOUND",
                           "message": "unknown incident"}},
            )
        )
        with self._patch_identity("operator"), self._patch_httpx(fake):
            response = self.client.get("/api/v1/incidents/inc-missing123")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "unknown incident")


class IncidentsCreateTests(IncidentsProxyBase):
    def test_operator_creates_with_reported_by(self) -> None:
        created = dict(INCIDENT_ENVELOPE)
        fake = _FakeAsyncClient(response=_FakeResponse(201, created))
        with self._patch_identity("operator"), self._patch_httpx(fake):
            response = self.client.post(
                "/api/v1/incidents",
                json={"title": "Payments API degraded",
                      "summary": "Elevated 5xx on payments/api.",
                      "severity": "warning",
                      "labels": {"team": "payments"}},
            )
        self.assertEqual(response.status_code, 201)
        call = fake.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["url"], "http://incident-service:8000/api/v1/incidents")
        self.assertEqual(call["json"]["title"], "Payments API degraded")
        # The gateway records the authenticated operator as reporter.
        self.assertEqual(call["headers"]["x-reported-by"], "operator.user")

    def test_observer_denied_create(self) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(201, INCIDENT_ENVELOPE))
        with self._patch_identity("read-only-observer"), self._patch_httpx(fake):
            response = self.client.post(
                "/api/v1/incidents", json={"title": "x"}
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["action"], "incident:create")
        self.assertEqual(fake.calls, [])

    def test_upstream_validation_error_passes_through(self) -> None:
        fake = _FakeAsyncClient(
            response=_FakeResponse(
                400,
                {"error": {"code": "INVALID_PARAMETERS", "message": "bad body"}},
            )
        )
        with self._patch_identity("operator"), self._patch_httpx(fake):
            response = self.client.post(
                "/api/v1/incidents", json={"title": "x"}
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "bad body")


class IncidentsTriageTests(IncidentsProxyBase):
    def _patch_delegation(self, token: str | None):
        async def fake_obtain(settings, subject, subject_token):
            return token

        return patch(
            "platform_gateway.api.routes.incidents.obtain_delegated_token",
            fake_obtain,
        )

    def test_triage_forwards_operator_identity_and_delegated_token(self) -> None:
        triaged = dict(INCIDENT_ENVELOPE, status="triaged")
        fake = _FakeAsyncClient(
            response=_FakeResponse(
                200, {"incident": triaged, "report": {"summary": "r"},
                      "dispatches": []}
            )
        )
        with (
            self._patch_identity("operator"),
            self._patch_delegation("delegated-jwt"),
            self._patch_httpx(fake),
        ):
            response = self.client.post(
                "/api/v1/incidents/inc-9f2c1ab34de5/triage"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["incident"]["status"], "triaged")
        call = fake.calls[0]
        self.assertEqual(
            call["url"],
            "http://incident-service:8000/api/v1/incidents/inc-9f2c1ab34de5/triage",
        )
        # Gateway credential authenticates; operator identity travels in
        # dedicated headers (the Authorization header carries Basic).
        self.assertEqual(call["auth"], ("platform-gateway", "pg-secret"))
        self.assertEqual(call["headers"]["x-user-id"], "operator.user")
        self.assertEqual(call["headers"]["x-delegated-token"], "delegated-jwt")

    def test_observer_denied_triage(self) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(200, {}))
        with (
            self._patch_identity("read-only-observer"),
            self._patch_delegation("delegated-jwt"),
            self._patch_httpx(fake),
        ):
            response = self.client.post(
                "/api/v1/incidents/inc-9f2c1ab34de5/triage"
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["action"], "incident:triage")
        self.assertEqual(fake.calls, [])

    def test_triage_without_delegation_fails_closed(self) -> None:
        """Triage must run under a real operator delegation; there is no
        tool-less fallback, so a missing delegated token fails fast."""
        fake = _FakeAsyncClient(response=_FakeResponse(200, {}))
        with (
            self._patch_identity("operator"),
            self._patch_delegation(None),
            self._patch_httpx(fake),
        ):
            response = self.client.post(
                "/api/v1/incidents/inc-9f2c1ab34de5/triage"
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(fake.calls, [])


class IncidentsProxyErrorTests(IncidentsProxyBase):
    def test_missing_incident_url_returns_503(self) -> None:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: _settings(
            incident_service_url=""
        )
        client = TestClient(app)
        with self._patch_identity("operator"):
            response = client.get("/api/v1/incidents")
        self.assertEqual(response.status_code, 503)

    def test_upstream_unreachable_returns_502(self) -> None:
        fake = _FakeAsyncClient(raise_exc=httpx.ConnectError("unreachable"))
        with self._patch_identity("operator"), self._patch_httpx(fake):
            response = self.client.get("/api/v1/incidents")
        self.assertEqual(response.status_code, 502)

    def test_upstream_5xx_maps_to_502(self) -> None:
        fake = _FakeAsyncClient(
            response=_FakeResponse(
                500, {"error": {"code": "INTERNAL", "message": "boom"}}
            )
        )
        with self._patch_identity("operator"), self._patch_httpx(fake):
            response = self.client.get("/api/v1/incidents")
        self.assertEqual(response.status_code, 502)


if __name__ == "__main__":
    unittest.main()
