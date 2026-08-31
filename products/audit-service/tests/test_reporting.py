"""Reporting route tests for audit-service (SPEC-046 R-1/R-2).

Drives the real FastAPI app with an in-memory store through TestClient:
the summary aggregate endpoint (deterministic sections, window echo,
decision chain) and the bounded CSV export (fixed columns, RFC-4180
quoting, cap truncation, always-present headers).
"""

from __future__ import annotations

import base64
import csv
import io
import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from audit_service.app import create_app
from audit_service.core.config import get_settings

INGEST_CLIENTS = "platform-gateway=pg-secret"


def _basic(client_id: str, secret: str) -> str:
    raw = f"{client_id}:{secret}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _event_payload(event_id: str, **overrides) -> dict:
    event = {
        "event_id": event_id,
        "occurred_at": "2026-08-31T12:00:00+00:00",
        "event_type": "tool_invoked",
        "service": "tool-gateway",
        "request_id": f"req-{event_id}",
        "outcome": "success",
        "details": {"tool_name": "k8s.list_pods"},
    }
    event.update(overrides)
    return event


class ReportingRouteTests(unittest.TestCase):
    env: dict[str, str] = {}

    def setUp(self) -> None:
        env = {
            "AUDIT_STORE_BACKEND": "memory",
            "AUDIT_INGEST_CLIENTS": INGEST_CLIENTS,
        }
        env.update(self.env)
        self._patcher = patch.dict(os.environ, env)
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
        return {"authorization": _basic("platform-gateway", "pg-secret")}

    def _seed(self, *events: dict) -> None:
        response = self.client.post(
            "/api/v1/audit/events", json={"events": list(events)}, headers=self.auth
        )
        assert response.status_code == 202, response.text

    # --- Summary (R-1) ------------------------------------------------------

    def test_summary_aggregates_and_projects_decision_chain(self) -> None:
        self._seed(
            _event_payload("t1", username="alice"),
            _event_payload("t2", username="alice"),
            _event_payload("t3", username="bob", outcome="deny"),
            _event_payload(
                "c1", username="alice", event_type="confirmation_decided",
                service="platform-gateway",
            ),
            _event_payload(
                "x1", event_type="execution_requested",
                service="execution-runtime",
            ),
            _event_payload(
                "x2", event_type="execution_completed",
                service="execution-runtime",
            ),
        )
        response = self.client.get("/api/v1/audit/summary", headers=self.auth)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_events"], 6)
        self.assertEqual(body["window"], {})
        self.assertEqual(
            body["by_event_type"],
            [
                {"name": "tool_invoked", "count": 3},
                {"name": "confirmation_decided", "count": 1},
                {"name": "execution_completed", "count": 1},
                {"name": "execution_requested", "count": 1},
            ],
        )
        self.assertEqual(
            body["top_actors"],
            [{"name": "alice", "count": 3}, {"name": "bob", "count": 1}],
        )
        self.assertEqual(
            body["decision_chain"],
            {
                "confirmation_decided": 1,
                "execution_requested": 1,
                "execution_completed": 1,
                "execution_rejected": 0,
            },
        )

    def test_summary_filters_and_echoes_window(self) -> None:
        self._seed(
            _event_payload("t1", username="alice"),
            _event_payload("t2", username="bob"),
        )
        response = self.client.get(
            "/api/v1/audit/summary?username=alice&event_type=tool_invoked",
            headers=self.auth,
        )
        body = response.json()
        self.assertEqual(body["total_events"], 1)
        self.assertEqual(
            body["window"],
            {"username": "alice", "event_type": "tool_invoked"},
        )
        self.assertEqual(body["by_event_type"], [{"name": "tool_invoked", "count": 1}])

    def test_summary_outcome_filter_narrows_and_echoes(self) -> None:
        # SPEC-047 R-1: the additive outcome dimension reaches the
        # aggregate and echoes in the window like the other filters.
        self._seed(
            _event_payload("t1", username="alice"),
            _event_payload("t2", username="bob", outcome="deny"),
            _event_payload("t3", username="carol", outcome="error"),
        )
        response = self.client.get(
            "/api/v1/audit/summary?outcome=deny", headers=self.auth
        )
        body = response.json()
        self.assertEqual(body["total_events"], 1)
        self.assertEqual(body["window"], {"outcome": "deny"})
        self.assertEqual(
            body["by_outcome"], [{"name": "deny", "count": 1}]
        )

    def test_summary_rejects_invalid_outcome(self) -> None:
        # SPEC-047 R-1: values outside the shared schema enum are a 422
        # under the existing validation posture.
        response = self.client.get(
            "/api/v1/audit/summary?outcome=exploded", headers=self.auth
        )
        self.assertEqual(response.status_code, 422)

    def test_summary_empty_window_answers_zeros(self) -> None:
        response = self.client.get(
            "/api/v1/audit/summary?username=nobody", headers=self.auth
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_events"], 0)
        self.assertEqual(body["by_event_type"], [])
        self.assertEqual(body["decision_chain"]["confirmation_decided"], 0)

    def test_summary_requires_auth(self) -> None:
        response = self.client.get("/api/v1/audit/summary")
        self.assertEqual(response.status_code, 401)

    # --- Export (R-2) ---------------------------------------------------------

    def test_export_writes_fixed_columns_newest_first(self) -> None:
        self._seed(
            _event_payload(
                "old", occurred_at="2026-08-31T11:00:00+00:00", username="alice"
            ),
            _event_payload(
                "new", occurred_at="2026-08-31T13:00:00+00:00", username="bob"
            ),
        )
        response = self.client.get("/api/v1/audit/export", headers=self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"].split(";")[0], "text/csv")
        self.assertEqual(response.headers["x-audit-export-truncated"], "false")
        self.assertEqual(response.headers["x-audit-export-rows"], "2")
        disposition = response.headers["content-disposition"]
        self.assertTrue(disposition.startswith("attachment; filename=\"audit-export-"))
        self.assertTrue(disposition.endswith(".csv\""))

        rows = list(csv.reader(io.StringIO(response.text)))
        self.assertEqual(
            rows[0],
            [
                "occurred_at", "event_type", "service", "outcome", "username",
                "actor", "subject", "session_id", "request_id", "details",
            ],
        )
        self.assertEqual(len(rows), 3)
        # Newest first; RFC-3339 UTC timestamps.
        self.assertEqual(rows[1][0], "2026-08-31T13:00:00Z")
        self.assertEqual(rows[2][0], "2026-08-31T11:00:00Z")
        self.assertEqual(rows[1][4], "bob")
        # Sorted-key deterministic details JSON.
        self.assertEqual(
            json.loads(rows[1][9]), {"tool_name": "k8s.list_pods"}
        )

    def test_export_quotes_commas_quotes_and_newlines(self) -> None:
        self._seed(
            _event_payload(
                "tricky",
                details={"message": 'say "hi", then\nbreak'},
            )
        )
        response = self.client.get("/api/v1/audit/export", headers=self.auth)
        rows = list(csv.reader(io.StringIO(response.text)))
        self.assertEqual(len(rows), 2)
        parsed = json.loads(rows[1][9])
        self.assertEqual(parsed["message"], 'say "hi", then\nbreak')

    def test_export_respects_filters(self) -> None:
        self._seed(
            _event_payload("a", username="alice"),
            _event_payload("b", username="bob"),
        )
        response = self.client.get(
            "/api/v1/audit/export?username=alice", headers=self.auth
        )
        self.assertEqual(response.headers["x-audit-export-rows"], "1")
        rows = list(csv.reader(io.StringIO(response.text)))
        self.assertEqual(rows[1][4], "alice")

    def test_export_respects_outcome_filter(self) -> None:
        # SPEC-047 R-1: the outcome dimension reaches the export leg
        # through the same shared store filters.
        self._seed(
            _event_payload("a", username="alice"),
            _event_payload("b", username="bob", outcome="deny"),
        )
        response = self.client.get(
            "/api/v1/audit/export?outcome=deny", headers=self.auth
        )
        self.assertEqual(response.headers["x-audit-export-rows"], "1")
        rows = list(csv.reader(io.StringIO(response.text)))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][3], "deny")

    def test_export_rejects_invalid_outcome(self) -> None:
        response = self.client.get(
            "/api/v1/audit/export?outcome=exploded", headers=self.auth
        )
        self.assertEqual(response.status_code, 422)

    def test_export_requires_auth(self) -> None:
        response = self.client.get("/api/v1/audit/export")
        self.assertEqual(response.status_code, 401)


class ExportTruncationTests(ReportingRouteTests):
    env = {"AUDIT_EXPORT_MAX_ROWS": "2"}

    def test_cap_truncates_and_sets_headers(self) -> None:
        self._seed(
            *[
                _event_payload(
                    f"e{i}",
                    occurred_at=f"2026-08-31T12:{i:02d}:00+00:00",
                )
                for i in range(3)
            ]
        )
        response = self.client.get("/api/v1/audit/export", headers=self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-audit-export-truncated"], "true")
        self.assertEqual(response.headers["x-audit-export-rows"], "2")
        rows = list(csv.reader(io.StringIO(response.text)))
        # Header row plus exactly two rows, the two newest.
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1][9], json.dumps({"tool_name": "k8s.list_pods"},
                                                sort_keys=True, separators=(",", ":")))
        self.assertEqual(rows[1][0], "2026-08-31T12:02:00Z")
        self.assertEqual(rows[2][0], "2026-08-31T12:01:00Z")


if __name__ == "__main__":
    unittest.main()
