"""Audit trail read proxy tests (SPEC-013 R-4, SPEC-046 R-3).

Validates the gateway-side authorization gate: only governance roles
(auditor, platform-admin) may read the audit trail; all other roles are
denied by the deny-by-default policy engine before any upstream call. The
audit service itself only ever sees the gateway's service credential.
Covers the raw trail query plus the summary and export reporting legs —
all three ride the same existing ``audit:read`` action (no new policy
cells).
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from platform_gateway.app import create_app
from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.schemas.api import IdentityContext
from platform_gateway.services.policy_engine import reset_policy_state


def _identity(role: str) -> IdentityContext:
    return IdentityContext(
        subject=f"user-{role}",
        username=f"{role}.user",
        roles=[role],
    )


class _FakeResponse:
    def __init__(
        self, status_code: int, payload: dict | None = None,
        content: bytes = b"", headers: dict | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.headers = headers or {}

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient capturing the proxied GET."""

    def __init__(self, response=None, raise_exc=None) -> None:
        self._response = response
        self._raise = raise_exc
        self.calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, url, params=None, auth=None, headers=None):
        self.calls.append(
            {"url": url, "params": params, "auth": auth, "headers": headers}
        )
        if self._raise is not None:
            raise self._raise
        return self._response


class AuditProxyRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_policy_state()
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: PlatformGatewaySettings(
            require_auth=True,
            audit_service_url="http://audit-service:8000",
            audit_client_id="platform-gateway",
            audit_client_secret="pg-secret",
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_policy_state()

    def _patch_identity(self, role: str):
        identity = _identity(role)

        async def fake_identity(settings, request, request_id):
            return identity

        return patch(
            "platform_gateway.api.routes.audit.resolve_request_identity",
            fake_identity,
        )

    def test_auditor_allowed_and_proxied(self) -> None:
        upstream = _FakeResponse(
            200, {"events": [{"event_id": "e1"}], "next_cursor": None}
        )
        fake = _FakeAsyncClient(response=upstream)
        with (
            self._patch_identity("auditor"),
            patch(
                "platform_gateway.api.routes.audit.httpx.AsyncClient",
                return_value=fake,
            ),
        ):
            response = self.client.get("/api/v1/audit/events")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["events"][0]["event_id"], "e1")
        # The proxy authenticates to the audit service with its own credential.
        self.assertEqual(fake.calls[0]["auth"], ("platform-gateway", "pg-secret"))
        self.assertEqual(
            fake.calls[0]["url"], "http://audit-service:8000/api/v1/audit/events"
        )

    def test_platform_admin_allowed(self) -> None:
        upstream = _FakeResponse(200, {"events": [], "next_cursor": None})
        fake = _FakeAsyncClient(response=upstream)
        with (
            self._patch_identity("platform-admin"),
            patch(
                "platform_gateway.api.routes.audit.httpx.AsyncClient",
                return_value=fake,
            ),
        ):
            response = self.client.get("/api/v1/audit/events")
        self.assertEqual(response.status_code, 200)

    def test_operator_denied_by_policy(self) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(200, {"events": []}))
        with (
            self._patch_identity("operator"),
            patch(
                "platform_gateway.api.routes.audit.httpx.AsyncClient",
                return_value=fake,
            ),
        ):
            response = self.client.get("/api/v1/audit/events")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["action"], "audit:read")
        # Denied before any upstream call is made.
        self.assertEqual(fake.calls, [])

    def test_observer_denied_by_policy(self) -> None:
        with self._patch_identity("read-only-observer"):
            response = self.client.get("/api/v1/audit/events")
        self.assertEqual(response.status_code, 403)

    def test_filters_forwarded_to_upstream(self) -> None:
        upstream = _FakeResponse(200, {"events": [], "next_cursor": None})
        fake = _FakeAsyncClient(response=upstream)
        with (
            self._patch_identity("auditor"),
            patch(
                "platform_gateway.api.routes.audit.httpx.AsyncClient",
                return_value=fake,
            ),
        ):
            response = self.client.get(
                "/api/v1/audit/events",
                params={
                    "username": "alice",
                    "event_type": "tool_invoked",
                    "outcome": "deny",
                    "limit": 10,
                },
            )
        self.assertEqual(response.status_code, 200)
        params = fake.calls[0]["params"]
        self.assertEqual(params["username"], "alice")
        self.assertEqual(params["event_type"], "tool_invoked")
        # SPEC-047 R-1: the additive outcome dimension rides through to
        # the upstream query; enum validation stays in the audit service.
        self.assertEqual(params["outcome"], "deny")
        self.assertEqual(params["limit"], 10)

    def test_missing_audit_url_returns_503(self) -> None:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: PlatformGatewaySettings(
            require_auth=True, audit_service_url=""
        )
        client = TestClient(app)
        with self._patch_identity("auditor"):
            response = client.get("/api/v1/audit/events")
        self.assertEqual(response.status_code, 503)

    def test_upstream_error_returns_502(self) -> None:
        import httpx

        fake = _FakeAsyncClient(raise_exc=httpx.ConnectError("unreachable"))
        with (
            self._patch_identity("auditor"),
            patch(
                "platform_gateway.api.routes.audit.httpx.AsyncClient",
                return_value=fake,
            ),
        ):
            response = self.client.get("/api/v1/audit/events")
        self.assertEqual(response.status_code, 502)


class AuditSummaryProxyTests(unittest.TestCase):
    """SPEC-046 R-3: GET /api/v1/audit/summary under the existing gate."""

    def setUp(self) -> None:
        reset_policy_state()
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: PlatformGatewaySettings(
            require_auth=True,
            audit_service_url="http://audit-service:8000",
            audit_client_id="platform-gateway",
            audit_client_secret="pg-secret",
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_policy_state()

    def _patch_identity(self, role: str):
        identity = _identity(role)

        async def fake_identity(settings, request, request_id):
            return identity

        return patch(
            "platform_gateway.api.routes.audit.resolve_request_identity",
            fake_identity,
        )

    def test_auditor_allowed_and_summary_passes_through_verbatim(self) -> None:
        summary_payload = {
            "total_events": 3,
            "window": {"event_type": "execution_completed"},
            "by_event_type": [{"name": "execution_completed", "count": 3}],
            "by_outcome": [{"name": "success", "count": 3}],
            "by_service": [{"name": "execution-runtime", "count": 3}],
            "top_actors": [{"name": "alice", "count": 3}],
            "decision_chain": {
                "confirmation_decided": 0,
                "execution_requested": 0,
                "execution_completed": 3,
                "execution_rejected": 0,
            },
        }
        fake = _FakeAsyncClient(response=_FakeResponse(200, summary_payload))
        with (
            self._patch_identity("auditor"),
            patch(
                "platform_gateway.api.routes.audit.httpx.AsyncClient",
                return_value=fake,
            ),
        ):
            response = self.client.get(
                "/api/v1/audit/summary",
                params={
                    "event_type": "execution_completed",
                    "username": "alice",
                    "outcome": "error",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), summary_payload)
        self.assertEqual(
            fake.calls[0]["url"], "http://audit-service:8000/api/v1/audit/summary"
        )
        self.assertEqual(fake.calls[0]["params"]["event_type"], "execution_completed")
        self.assertEqual(fake.calls[0]["params"]["username"], "alice")
        # SPEC-047 R-1: outcome reaches the summary leg too.
        self.assertEqual(fake.calls[0]["params"]["outcome"], "error")
        self.assertEqual(fake.calls[0]["auth"], ("platform-gateway", "pg-secret"))

    def test_operator_denied_by_policy(self) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(200, {}))
        with (
            self._patch_identity("operator"),
            patch(
                "platform_gateway.api.routes.audit.httpx.AsyncClient",
                return_value=fake,
            ),
        ):
            response = self.client.get("/api/v1/audit/summary")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["action"], "audit:read")
        self.assertEqual(fake.calls, [])

    def test_observer_denied_by_policy(self) -> None:
        with self._patch_identity("read-only-observer"):
            response = self.client.get("/api/v1/audit/summary")
        self.assertEqual(response.status_code, 403)

    def test_missing_audit_url_returns_503(self) -> None:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: PlatformGatewaySettings(
            require_auth=True, audit_service_url=""
        )
        client = TestClient(app)
        with self._patch_identity("auditor"):
            response = client.get("/api/v1/audit/summary")
        self.assertEqual(response.status_code, 503)

    def test_upstream_error_returns_502(self) -> None:
        import httpx

        fake = _FakeAsyncClient(raise_exc=httpx.ConnectError("unreachable"))
        with (
            self._patch_identity("auditor"),
            patch(
                "platform_gateway.api.routes.audit.httpx.AsyncClient",
                return_value=fake,
            ),
        ):
            response = self.client.get("/api/v1/audit/summary")
        self.assertEqual(response.status_code, 502)

    def test_upstream_client_error_passes_through(self) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(400, {}))
        with (
            self._patch_identity("auditor"),
            patch(
                "platform_gateway.api.routes.audit.httpx.AsyncClient",
                return_value=fake,
            ),
        ):
            response = self.client.get("/api/v1/audit/summary")
        self.assertEqual(response.status_code, 400)


class AuditExportProxyTests(unittest.TestCase):
    """SPEC-046 R-3: GET /api/v1/audit/export byte pass-through."""

    def setUp(self) -> None:
        reset_policy_state()
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: PlatformGatewaySettings(
            require_auth=True,
            audit_service_url="http://audit-service:8000",
            audit_client_id="platform-gateway",
            audit_client_secret="pg-secret",
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_policy_state()

    def _patch_identity(self, role: str):
        identity = _identity(role)

        async def fake_identity(settings, request, request_id):
            return identity

        return patch(
            "platform_gateway.api.routes.audit.resolve_request_identity",
            fake_identity,
        )

    def test_export_bytes_and_headers_forwarded(self) -> None:
        csv_body = b"occurred_at,event_type\r\n2026-08-31T12:00:00Z,tool_invoked\r\n"
        upstream = _FakeResponse(
            200,
            content=csv_body,
            headers={
                "content-type": "text/csv; charset=utf-8",
                "content-disposition": 'attachment; filename="audit-export-20260831T120000Z.csv"',
                "x-audit-export-truncated": "true",
                "x-audit-export-rows": "1",
                "x-internal-header": "must-not-forward",
            },
        )
        fake = _FakeAsyncClient(response=upstream)
        with (
            self._patch_identity("auditor"),
            patch(
                "platform_gateway.api.routes.audit.httpx.AsyncClient",
                return_value=fake,
            ),
        ):
            response = self.client.get("/api/v1/audit/export")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, csv_body)
        self.assertTrue(response.headers["content-type"].startswith("text/csv"))
        self.assertIn(
            "audit-export-20260831T120000Z.csv",
            response.headers["content-disposition"],
        )
        self.assertEqual(response.headers["x-audit-export-truncated"], "true")
        self.assertEqual(response.headers["x-audit-export-rows"], "1")
        self.assertNotIn("x-internal-header", response.headers)
        self.assertEqual(
            fake.calls[0]["url"], "http://audit-service:8000/api/v1/audit/export"
        )

    def test_export_filters_forwarded(self) -> None:
        fake = _FakeAsyncClient(
            response=_FakeResponse(200, content=b"h\r\n", headers={})
        )
        with (
            self._patch_identity("auditor"),
            patch(
                "platform_gateway.api.routes.audit.httpx.AsyncClient",
                return_value=fake,
            ),
        ):
            response = self.client.get(
                "/api/v1/audit/export",
                params={
                    "service": "execution-runtime",
                    "outcome": "deny",
                    "limit": 10,
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake.calls[0]["params"]["service"], "execution-runtime")
        # SPEC-047 R-1: outcome reaches the export leg too.
        self.assertEqual(fake.calls[0]["params"]["outcome"], "deny")
        # The export is server-capped upstream; the query-page limit knob
        # must not leak into the export leg.
        self.assertNotIn("limit", fake.calls[0]["params"])

    def test_operator_denied_by_policy(self) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(200, content=b""))
        with (
            self._patch_identity("operator"),
            patch(
                "platform_gateway.api.routes.audit.httpx.AsyncClient",
                return_value=fake,
            ),
        ):
            response = self.client.get("/api/v1/audit/export")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(fake.calls, [])

    def test_observer_denied_by_policy(self) -> None:
        with self._patch_identity("read-only-observer"):
            response = self.client.get("/api/v1/audit/export")
        self.assertEqual(response.status_code, 403)

    def test_missing_audit_url_returns_503(self) -> None:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: PlatformGatewaySettings(
            require_auth=True, audit_service_url=""
        )
        client = TestClient(app)
        with self._patch_identity("auditor"):
            response = client.get("/api/v1/audit/export")
        self.assertEqual(response.status_code, 503)

    def test_upstream_error_returns_502(self) -> None:
        import httpx

        fake = _FakeAsyncClient(raise_exc=httpx.ConnectError("unreachable"))
        with (
            self._patch_identity("auditor"),
            patch(
                "platform_gateway.api.routes.audit.httpx.AsyncClient",
                return_value=fake,
            ),
        ):
            response = self.client.get("/api/v1/audit/export")
        self.assertEqual(response.status_code, 502)


if __name__ == "__main__":
    unittest.main()
