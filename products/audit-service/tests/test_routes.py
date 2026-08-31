"""HTTP route tests for audit-service (SPEC-013 R-3/R-4).

Drives the real FastAPI app with an in-memory store through TestClient. The
ingest/query handlers read settings via the lru-cached ``get_settings``, so the
environment is patched and the cache cleared around each test.
"""

from __future__ import annotations

import base64
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from audit_service.app import create_app
from audit_service.core.config import get_settings

INGEST_CLIENTS = "tool-gateway=tg-secret,platform-gateway=pg-secret"


def _basic(client_id: str, secret: str) -> str:
    raw = f"{client_id}:{secret}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _event_payload(event_id: str, **overrides) -> dict:
    event = {
        "event_id": event_id,
        "occurred_at": "2026-08-01T12:00:00+00:00",
        "event_type": "tool_invoked",
        "service": "tool-gateway",
        "request_id": f"req-{event_id}",
        "outcome": "success",
        "details": {"tool_name": "k8s.list_pods"},
    }
    event.update(overrides)
    return event


class AuditRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._patcher = patch.dict(
            os.environ,
            {
                "AUDIT_STORE_BACKEND": "memory",
                "AUDIT_INGEST_CLIENTS": INGEST_CLIENTS,
                "AUDIT_MAX_BATCH": "3",
            },
        )
        self._patcher.start()
        get_settings.cache_clear()
        self._client_cm = TestClient(create_app())
        self.client = self._client_cm.__enter__()

    def tearDown(self) -> None:
        self._client_cm.__exit__(None, None, None)
        get_settings.cache_clear()
        self._patcher.stop()

    @property
    def auth(self) -> dict[str, str]:
        return {"authorization": _basic("tool-gateway", "tg-secret")}

    # --- Ingest -----------------------------------------------------------

    def test_ingest_accepts_valid_batch(self) -> None:
        response = self.client.post(
            "/api/v1/audit/events",
            json={"events": [_event_payload("e1"), _event_payload("e2")]},
            headers=self.auth,
        )
        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body["accepted"], 2)
        self.assertEqual(body["inserted"], 2)

    def test_ingest_requires_auth(self) -> None:
        response = self.client.post(
            "/api/v1/audit/events",
            json={"events": [_event_payload("e1")]},
        )
        self.assertEqual(response.status_code, 401)

    def test_ingest_rejects_bad_credential(self) -> None:
        response = self.client.post(
            "/api/v1/audit/events",
            json={"events": [_event_payload("e1")]},
            headers={"authorization": _basic("tool-gateway", "wrong")},
        )
        self.assertEqual(response.status_code, 401)

    def test_ingest_rejects_empty_batch(self) -> None:
        response = self.client.post(
            "/api/v1/audit/events",
            json={"events": []},
            headers=self.auth,
        )
        self.assertEqual(response.status_code, 400)

    def test_ingest_rejects_malformed_event(self) -> None:
        bad = _event_payload("e1")
        del bad["event_type"]  # required field missing
        response = self.client.post(
            "/api/v1/audit/events",
            json={"events": [bad]},
            headers=self.auth,
        )
        self.assertEqual(response.status_code, 400)

    def test_ingest_rejects_unknown_event_type(self) -> None:
        response = self.client.post(
            "/api/v1/audit/events",
            json={"events": [_event_payload("e1", event_type="not_a_type")]},
            headers=self.auth,
        )
        self.assertEqual(response.status_code, 400)

    def test_ingest_rejects_oversized_batch(self) -> None:
        events = [_event_payload(f"e{i}") for i in range(5)]  # max_batch=3
        response = self.client.post(
            "/api/v1/audit/events", json={"events": events}, headers=self.auth
        )
        self.assertEqual(response.status_code, 400)

    def test_skills_usage_event_round_trips(self) -> None:
        # SPEC-029 R-1: skills vocabulary is accepted and queryable.
        event = _event_payload(
            "sk1",
            event_type="skill_searched",
            service="skills-hub",
            actor="tool-gateway",
            details={
                "query": "crashloop runbook",
                "limit": 5,
                "result_count": 2,
                "skill_ids": ["sre-alerting/alerts/KubePodCrashLooping"],
            },
        )
        response = self.client.post(
            "/api/v1/audit/events", json={"events": [event]}, headers=self.auth
        )
        self.assertEqual(response.status_code, 202)
        page = self.client.get(
            "/api/v1/audit/events?event_type=skill_searched", headers=self.auth
        ).json()
        self.assertEqual([e["event_id"] for e in page["events"]], ["sk1"])
        self.assertEqual(
            page["events"][0]["details"]["query"], "crashloop runbook"
        )

    def test_ingest_dedupes_repeated_event_id(self) -> None:
        self.client.post(
            "/api/v1/audit/events",
            json={"events": [_event_payload("e1")]},
            headers=self.auth,
        )
        response = self.client.post(
            "/api/v1/audit/events",
            json={"events": [_event_payload("e1")]},
            headers=self.auth,
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["inserted"], 0)

    # --- Query ------------------------------------------------------------

    def _seed(self, *events: dict) -> None:
        response = self.client.post(
            "/api/v1/audit/events", json={"events": list(events)}, headers=self.auth
        )
        assert response.status_code == 202, response.text

    def test_query_returns_ingested_events_verbatim(self) -> None:
        self._seed(
            _event_payload("e1", username="alice", session_id="ses-1"),
        )
        response = self.client.get("/api/v1/audit/events", headers=self.auth)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["events"]), 1)
        event = body["events"][0]
        self.assertEqual(event["event_id"], "e1")
        self.assertEqual(event["username"], "alice")
        self.assertEqual(event["details"]["tool_name"], "k8s.list_pods")
        self.assertIsNone(body["next_cursor"])

    def test_query_filters_by_username_and_event_type(self) -> None:
        self._seed(
            _event_payload("e1", username="alice"),
            _event_payload("e2", username="bob"),
            _event_payload("e3", username="alice", event_type="policy_decision"),
        )
        response = self.client.get(
            "/api/v1/audit/events?username=alice", headers=self.auth
        )
        ids = {e["event_id"] for e in response.json()["events"]}
        self.assertEqual(ids, {"e1", "e3"})

        response = self.client.get(
            "/api/v1/audit/events?event_type=policy_decision", headers=self.auth
        )
        ids = {e["event_id"] for e in response.json()["events"]}
        self.assertEqual(ids, {"e3"})

    def test_query_filters_by_outcome(self) -> None:
        # SPEC-047 R-1: the additive outcome dimension filters the events
        # query verbatim against the envelope column.
        self._seed(
            _event_payload("e1", username="alice"),
            _event_payload("e2", username="bob", outcome="deny"),
            _event_payload("e3", username="carol", outcome="error"),
        )
        response = self.client.get(
            "/api/v1/audit/events?outcome=deny", headers=self.auth
        )
        ids = {e["event_id"] for e in response.json()["events"]}
        self.assertEqual(ids, {"e2"})

    def test_query_rejects_invalid_outcome(self) -> None:
        # SPEC-047 R-1: values outside the shared schema enum are a 422.
        response = self.client.get(
            "/api/v1/audit/events?outcome=exploded", headers=self.auth
        )
        self.assertEqual(response.status_code, 422)

    def test_query_paginates_with_cursor(self) -> None:
        self._seed(
            *[
                _event_payload(
                    f"e{i}",
                    occurred_at=f"2026-08-01T12:{i:02d}:00+00:00",
                )
                for i in range(3)
            ]
        )
        first = self.client.get(
            "/api/v1/audit/events?limit=2", headers=self.auth
        ).json()
        self.assertEqual(len(first["events"]), 2)
        self.assertIsNotNone(first["next_cursor"])

        second = self.client.get(
            f"/api/v1/audit/events?limit=2&cursor={first['next_cursor']}",
            headers=self.auth,
        ).json()
        self.assertEqual(len(second["events"]), 1)
        self.assertIsNone(second["next_cursor"])

    def test_query_rejects_invalid_cursor(self) -> None:
        response = self.client.get(
            "/api/v1/audit/events?cursor=not-a-cursor", headers=self.auth
        )
        self.assertEqual(response.status_code, 400)

    def test_query_requires_auth(self) -> None:
        response = self.client.get("/api/v1/audit/events")
        self.assertEqual(response.status_code, 401)

    def test_query_rejects_out_of_range_limit(self) -> None:
        response = self.client.get(
            "/api/v1/audit/events?limit=0", headers=self.auth
        )
        self.assertEqual(response.status_code, 422)

    # --- Health -----------------------------------------------------------

    def test_health_live(self) -> None:
        response = self.client.get("/health/live")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_health_ready_reports_store(self) -> None:
        self._seed(_event_payload("e1"))
        response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["store_ready"])
        self.assertEqual(body["event_count"], 1)
        self.assertEqual(body["store_backend"], "memory")


if __name__ == "__main__":
    unittest.main()
