"""HTTP route tests for incident-service (SPEC-015 R-2/R-3/R-5).

Drives the real FastAPI app through TestClient with the in-memory store.
The agent turn is replaced with a fake double (patched ``_call_agent``) and
the audit connector is exercised through an httpx MockTransport.
"""

from __future__ import annotations

import base64
import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from incident_service.app import create_app
from incident_service.core.config import get_settings
from incident_service.services import audit_emitter, triage

WEBHOOK_TOKEN = "hook-secret"
QUERY_CLIENTS = "platform-gateway=pg-secret,tool-gateway=tg-secret"

NOW = datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc)


def _basic(client_id: str, secret: str) -> str:
    raw = f"{client_id}:{secret}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _webhook_payload(**overrides) -> dict:
    payload = {
        "version": "4",
        "groupKey": "{}:{alertname=KubePodNotReady}",
        "status": "firing",
        "commonLabels": {"alertname": "KubePodNotReady", "severity": "critical"},
        "commonAnnotations": {
            "summary": "Pod stuck not ready",
            "description": "Pod default/web-1 not ready for 15m.",
        },
    }
    payload.update(overrides)
    return payload


def _report_block(incident_id: str, summary: str = "assessment") -> str:
    payload = {
        "incident_id": incident_id,
        "summary": summary,
        "severity_assessment": "critical",
        "evidence": [
            {"source": "k8s.list_events", "description": "Evictions on worker-2"}
        ],
        "hypotheses": ["Node memory pressure"],
        "next_steps": [
            {
                "title": "Inspect worker-2",
                "rationale": "Eviction evidence",
                "priority": "high",
            }
        ],
        "skills_cited": ["sre-alerting/kubepodnotready"],
        "session_id": f"incident-{incident_id}",
        "generated_at": NOW.isoformat(),
        "generated_by": "alice",
    }
    return f"```triage-report\n{json.dumps(payload)}\n```"


class IncidentRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._patcher = patch.dict(
            os.environ,
            {
                "INCIDENT_STORE_BACKEND": "memory",
                "INCIDENT_WEBHOOK_TOKEN": WEBHOOK_TOKEN,
                "INCIDENT_QUERY_CLIENTS": QUERY_CLIENTS,
                "INCIDENT_AUDIT_SERVICE_URL": "http://audit-service:8000",
            },
        )
        self._patcher.start()
        get_settings.cache_clear()
        self._audit_calls: list[dict] = []
        self._audit_patcher = patch.object(
            audit_emitter.httpx,
            "AsyncClient",
            self._mock_audit_client(),
        )
        self._audit_patcher.start()
        self._client_cm = TestClient(create_app())
        self.client = self._client_cm.__enter__()

    def tearDown(self) -> None:
        self._client_cm.__exit__(None, None, None)
        self._audit_patcher.stop()
        get_settings.cache_clear()
        self._patcher.stop()

    def _mock_audit_client(self):
        calls = self._audit_calls
        real_client = httpx.AsyncClient

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(
                {"url": str(request.url), "body": json.loads(request.read())}
            )
            return httpx.Response(202, json={"accepted": 1, "inserted": 1})

        def factory(**kwargs):
            return real_client(
                transport=httpx.MockTransport(handler), timeout=1.0
            )

        return factory

    @property
    def auth(self) -> dict[str, str]:
        return {"authorization": _basic("platform-gateway", "pg-secret")}

    @property
    def webhook_auth(self) -> dict[str, str]:
        return {"authorization": f"Bearer {WEBHOOK_TOKEN}"}

    def _fire_webhook(self, **overrides) -> dict:
        response = self.client.post(
            "/api/v1/webhooks/alertmanager",
            json=_webhook_payload(**overrides),
            headers=self.webhook_auth,
        )
        return response.json()

    def _create_manual(self, **headers) -> dict:
        response = self.client.post(
            "/api/v1/incidents",
            json={
                "title": "Checkout latency spike",
                "summary": "p99 latency over 2s since 12:00.",
                "severity": "warning",
                "labels": {"team": "payments"},
            },
            headers={**self.auth, **headers},
        )
        return response.json()

    def _fake_agent(self, text_for: dict[str, str]):
        """Patch double relaying replies per session id and recording calls."""
        seen: list[dict] = []

        async def fake_call_agent(
            settings, incident, operator, bearer_token, request_id
        ) -> tuple[str, dict | None, str]:
            session_id = triage.session_id_for(incident.incident_id)
            seen.append(
                {
                    "session_id": session_id,
                    "operator": operator,
                    "bearer_token": bearer_token,
                    "incident_id": incident.incident_id,
                }
            )
            # No structured output: exercises the fenced-block fallback path.
            return text_for[session_id], None, session_id

        return fake_call_agent, seen

    # --- Webhook intake ----------------------------------------------------

    def test_webhook_requires_token(self) -> None:
        response = self.client.post(
            "/api/v1/webhooks/alertmanager", json=_webhook_payload()
        )
        self.assertEqual(response.status_code, 401)
        response = self.client.post(
            "/api/v1/webhooks/alertmanager",
            json=_webhook_payload(),
            headers={"authorization": "Bearer wrong-token"},
        )
        self.assertEqual(response.status_code, 401)

    def test_webhook_non_ascii_token_is_rejected_not_errored(self) -> None:
        # compare_digest on str raises TypeError for non-ASCII; the check
        # must return False (401), not raise (500). ASGI servers decode
        # header values as latin-1, so non-ASCII can reach the route.
        from types import SimpleNamespace

        from incident_service.api.routes.webhooks import _check_webhook_token

        request = SimpleNamespace(
            headers={"authorization": "Bearer tokén"}
        )
        self.assertFalse(_check_webhook_token(request, get_settings()))

    def test_webhook_fails_closed_without_configured_token(self) -> None:
        with patch.dict(os.environ, {"INCIDENT_WEBHOOK_TOKEN": ""}):
            get_settings.cache_clear()
            response = self.client.post(
                "/api/v1/webhooks/alertmanager", json=_webhook_payload()
            )
        get_settings.cache_clear()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["error"]["code"], "WEBHOOK_NOT_CONFIGURED"
        )

    def test_webhook_rejects_malformed_json(self) -> None:
        response = self.client.post(
            "/api/v1/webhooks/alertmanager",
            content=b"not-json",
            headers={**self.webhook_auth, "content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 400)

    def test_webhook_rejects_unnormalizable_payload(self) -> None:
        response = self.client.post(
            "/api/v1/webhooks/alertmanager",
            json={"status": "firing"},
            headers=self.webhook_auth,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_PAYLOAD")

    def test_webhook_creates_incident(self) -> None:
        response = self.client.post(
            "/api/v1/webhooks/alertmanager",
            json=_webhook_payload(),
            headers=self.webhook_auth,
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["action"], "created")
        self.assertTrue(body["incident_id"].startswith("inc-"))

        detail = self.client.get(
            f"/api/v1/incidents/{body['incident_id']}", headers=self.auth
        ).json()
        incident = detail["incident"]
        self.assertEqual(incident["source"], "alertmanager")
        self.assertEqual(incident["status"], "new")
        self.assertEqual(incident["severity"], "critical")
        self.assertEqual(incident["title"], "Pod stuck not ready")
        self.assertNotIn("reported_by", incident)

    def test_webhook_dedupes_on_fingerprint(self) -> None:
        first = self._fire_webhook()
        second = self._fire_webhook(
            commonAnnotations={
                "summary": "Pod stuck not ready",
                "description": "Still not ready for 30m.",
            }
        )
        self.assertEqual(first["incident_id"], second["incident_id"])
        self.assertEqual(second["action"], "updated")

        listing = self.client.get("/api/v1/incidents", headers=self.auth).json()
        self.assertEqual(listing["total"], 1)
        detail = self.client.get(
            f"/api/v1/incidents/{first['incident_id']}", headers=self.auth
        ).json()
        self.assertEqual(detail["incident"]["summary"], "Still not ready for 30m.")

    def test_webhook_resolution_closes_open_incident(self) -> None:
        created = self._fire_webhook()
        response = self.client.post(
            "/api/v1/webhooks/alertmanager",
            json=_webhook_payload(status="resolved"),
            headers=self.webhook_auth,
        )
        body = response.json()
        self.assertEqual(body["action"], "resolved")
        self.assertEqual(body["incident_id"], created["incident_id"])
        detail = self.client.get(
            f"/api/v1/incidents/{created['incident_id']}", headers=self.auth
        ).json()
        self.assertEqual(detail["incident"]["status"], "resolved")
        self.assertIn("resolved_at", detail["incident"])

    def test_webhook_resolution_for_unknown_fingerprint_is_noop(self) -> None:
        response = self.client.post(
            "/api/v1/webhooks/alertmanager",
            json=_webhook_payload(status="resolved"),
            headers=self.webhook_auth,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["action"], "ignored")
        self.assertIsNone(body["incident_id"])

    # --- Manual intake -------------------------------------------------------

    def test_manual_intake_requires_auth(self) -> None:
        response = self.client.post(
            "/api/v1/incidents", json={"title": "broken"}
        )
        self.assertEqual(response.status_code, 401)

    def test_manual_intake_creates_incident(self) -> None:
        response = self.client.post(
            "/api/v1/incidents",
            json={
                "title": "Checkout latency spike",
                "summary": "p99 latency over 2s.",
                "labels": {"team": "payments"},
            },
            headers={**self.auth, "X-Reported-By": "alice"},
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["source"], "manual")
        self.assertEqual(body["status"], "new")
        self.assertEqual(body["severity"], "warning")
        self.assertEqual(body["reported_by"], "alice")
        self.assertTrue(body["fingerprint"].startswith("manual:"))

    def test_manual_intake_falls_back_to_caller_identity(self) -> None:
        body = self._create_manual()
        self.assertEqual(body["reported_by"], "platform-gateway")

    def test_manual_intake_always_creates(self) -> None:
        first = self._create_manual()
        second = self._create_manual()
        self.assertNotEqual(first["incident_id"], second["incident_id"])

    def test_manual_intake_rejects_missing_title(self) -> None:
        response = self.client.post(
            "/api/v1/incidents",
            json={"summary": "no title"},
            headers=self.auth,
        )
        self.assertEqual(response.status_code, 400)

    def test_manual_intake_rejects_unknown_fields(self) -> None:
        response = self.client.post(
            "/api/v1/incidents",
            json={"title": "x", "unexpected": True},
            headers=self.auth,
        )
        self.assertEqual(response.status_code, 400)

    def test_manual_intake_rejects_bad_severity(self) -> None:
        response = self.client.post(
            "/api/v1/incidents",
            json={"title": "x", "severity": "apocalyptic"},
            headers=self.auth,
        )
        self.assertEqual(response.status_code, 400)

    # --- Query API -----------------------------------------------------------

    def test_list_requires_auth(self) -> None:
        response = self.client.get("/api/v1/incidents")
        self.assertEqual(response.status_code, 401)

    def test_list_returns_entries_without_summary_newest_first(self) -> None:
        self._fire_webhook()
        self._create_manual()
        body = self.client.get("/api/v1/incidents", headers=self.auth).json()
        self.assertEqual(body["total"], 2)
        self.assertEqual(body["incidents"][0]["source"], "manual")
        for entry in body["incidents"]:
            self.assertNotIn("summary", entry)

    def test_list_filters(self) -> None:
        self._fire_webhook()
        self._create_manual()
        body = self.client.get(
            "/api/v1/incidents?source=alertmanager", headers=self.auth
        ).json()
        self.assertEqual(body["total"], 1)
        body = self.client.get(
            "/api/v1/incidents?status=new&severity=critical", headers=self.auth
        ).json()
        self.assertEqual(body["total"], 1)

    def test_list_rejects_bad_parameters(self) -> None:
        for query in ("limit=0", "limit=101", "offset=-1", "status=closed"):
            response = self.client.get(
                f"/api/v1/incidents?{query}", headers=self.auth
            )
            self.assertEqual(response.status_code, 400, query)

    def test_get_unknown_incident_returns_404(self) -> None:
        response = self.client.get("/api/v1/incidents/inc-nope", headers=self.auth)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "INCIDENT_NOT_FOUND")

    def test_report_endpoint_404s_without_report(self) -> None:
        created = self._fire_webhook()
        response = self.client.get(
            f"/api/v1/incidents/{created['incident_id']}/report",
            headers=self.auth,
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "REPORT_NOT_FOUND")
        response = self.client.get(
            "/api/v1/incidents/inc-nope/report", headers=self.auth
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "INCIDENT_NOT_FOUND")

    # --- Triage ----------------------------------------------------------------

    def _triage_headers(self, **overrides) -> dict[str, str]:
        headers = {
            **self.auth,
            "X-User-ID": "alice",
            "X-Delegated-Token": "delegated-bearer",
        }
        headers.update(overrides)
        return headers

    def test_triage_requires_auth_and_relayed_identity(self) -> None:
        created = self._fire_webhook()
        url = f"/api/v1/incidents/{created['incident_id']}/triage"
        response = self.client.post(url)
        self.assertEqual(response.status_code, 401)
        response = self.client.post(url, headers=self.auth)
        self.assertEqual(response.status_code, 400)
        response = self.client.post(
            url, headers={**self.auth, "X-User-ID": "alice"}
        )
        self.assertEqual(response.status_code, 400)

    def test_triage_unknown_incident_returns_404(self) -> None:
        response = self.client.post(
            "/api/v1/incidents/inc-nope/triage", headers=self._triage_headers()
        )
        self.assertEqual(response.status_code, 404)

    def test_triage_happy_path_stores_report_and_dispatches(self) -> None:
        created = self._fire_webhook()
        incident_id = created["incident_id"]
        fake_agent, calls = self._fake_agent(
            {f"incident-{incident_id}": _report_block(incident_id)}
        )
        with patch.object(triage, "_call_agent", fake_agent):
            response = self.client.post(
                f"/api/v1/incidents/{incident_id}/triage",
                headers=self._triage_headers(),
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["incident"]["status"], "triaged")
        self.assertEqual(body["incident"]["session_id"], f"incident-{incident_id}")
        self.assertEqual(body["report"]["incident_id"], incident_id)
        self.assertEqual(body["report"]["severity_assessment"], "critical")
        (dispatch,) = body["dispatches"]
        self.assertEqual(dispatch["connector"], "audit")
        self.assertEqual(dispatch["status"], "delivered")

        # The agent ran in the dedicated session under the operator identity.
        (call,) = calls
        self.assertEqual(call["session_id"], f"incident-{incident_id}")
        self.assertEqual(call["operator"], "alice")
        self.assertEqual(call["bearer_token"], "delegated-bearer")
        self.assertEqual(call["incident_id"], incident_id)

        # The audit connector delivered a structured incident_triaged event.
        (audit_call,) = self._audit_calls
        event = audit_call["body"]["events"][0]
        self.assertEqual(event["event_type"], "incident_triaged")
        self.assertEqual(event["details"]["incident"]["incident_id"], incident_id)

    def test_triage_failure_preserves_raw_text(self) -> None:
        created = self._fire_webhook()
        incident_id = created["incident_id"]
        fake_agent, _ = self._fake_agent(
            {f"incident-{incident_id}": "I could not find a conclusive block."}
        )
        with patch.object(triage, "_call_agent", fake_agent):
            response = self.client.post(
                f"/api/v1/incidents/{incident_id}/triage",
                headers=self._triage_headers(),
            )
        body = response.json()
        self.assertEqual(body["incident"]["status"], "triage_failed")
        self.assertIn("could not find", body["incident"]["triage_raw"])
        self.assertIsNone(body["report"])
        self.assertEqual(body["dispatches"], [])
        # No connector dispatch happened for a failed triage.
        self.assertEqual(self._audit_calls, [])

    def test_retriage_latest_report_wins(self) -> None:
        created = self._fire_webhook()
        incident_id = created["incident_id"]
        session_id = f"incident-{incident_id}"
        fake_agent, _ = self._fake_agent(
            {session_id: _report_block(incident_id, summary="first pass")}
        )
        with patch.object(triage, "_call_agent", fake_agent):
            self.client.post(
                f"/api/v1/incidents/{incident_id}/triage",
                headers=self._triage_headers(),
            )
        fake_agent, _ = self._fake_agent(
            {session_id: _report_block(incident_id, summary="second pass")}
        )
        with patch.object(triage, "_call_agent", fake_agent):
            response = self.client.post(
                f"/api/v1/incidents/{incident_id}/triage",
                headers=self._triage_headers(),
            )
        self.assertEqual(response.json()["report"]["summary"], "second pass")
        report = self.client.get(
            f"/api/v1/incidents/{incident_id}/report", headers=self.auth
        ).json()
        self.assertEqual(report["summary"], "second pass")

    # --- Health ----------------------------------------------------------------

    def test_health_live(self) -> None:
        response = self.client.get("/health/live")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_health_ready_reports_store_and_connectors(self) -> None:
        self._fire_webhook()
        response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["store_backend"], "memory")
        self.assertEqual(body["connectors"], ["audit"])
        self.assertEqual(body["incident_count"], 1)


if __name__ == "__main__":
    unittest.main()
