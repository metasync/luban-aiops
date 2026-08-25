"""Triage orchestration unit tests (SPEC-015 R-3).

Covers the prompt template, fenced-block extraction, and report validation
fallbacks; the agent call itself is exercised through a fake double in the
route tests and through an httpx MockTransport for the session/chat dance.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import httpx

from incident_service.core.config import IncidentSettings
from incident_service.schemas.incident import (
    Incident,
    IncidentSource,
    IncidentStatus,
)
from incident_service.services import triage
from incident_service.services.triage import (
    TriageError,
    _call_agent,
    build_triage_prompt,
    extract_triage_block,
    parse_triage_report,
    session_candidates_for,
    session_id_for,
)

NOW = datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc)


def _incident(incident_id: str = "inc-aaa111") -> Incident:
    return Incident(
        incident_id=incident_id,
        fingerprint="fp-1",
        source=IncidentSource.ALERTMANAGER,
        severity="warning",
        status=IncidentStatus.NEW,
        title="Pod stuck not ready",
        summary="Pod default/web-1 not ready.",
        labels={"alertname": "KubePodNotReady", "severity": "warning"},
        created_at=NOW,
        updated_at=NOW,
    )


def _report_block(**overrides) -> str:
    payload = {
        "incident_id": "inc-aaa111",
        "summary": "Node pressure is evicting pods.",
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
        "session_id": "incident-inc-aaa111",
        "generated_at": NOW.isoformat(),
        "generated_by": "alice",
    }
    payload.update(overrides)
    return f"Here is my analysis.\n\n```triage-report\n{json.dumps(payload)}\n```\n"


class PromptTests(unittest.TestCase):
    def test_session_id_is_dedicated_per_incident(self) -> None:
        self.assertEqual(session_id_for("inc-aaa111"), "incident-inc-aaa111")

    def test_session_candidates_prefer_shared_then_per_operator(self) -> None:
        candidates = session_candidates_for("inc-aaa111", "alice")
        self.assertEqual(
            candidates, ["incident-inc-aaa111", "incident-inc-aaa111--alice"]
        )

    def test_session_candidates_sanitize_operator(self) -> None:
        candidates = session_candidates_for("inc-aaa111", "Alice Smith/ops")
        self.assertEqual(
            candidates[1], "incident-inc-aaa111--Alice-Smith-ops"
        )

    def test_prompt_carries_incident_context_and_format(self) -> None:
        prompt = build_triage_prompt(
            _incident(), "alice", "incident-inc-aaa111"
        )
        self.assertIn("inc-aaa111", prompt)
        self.assertIn("Pod stuck not ready", prompt)
        self.assertIn("alertname=KubePodNotReady", prompt)
        self.assertIn("```triage-report", prompt)
        self.assertIn("alice", prompt)
        # Advisory discipline: no execution.
        self.assertIn("advisory", prompt)
        # Mutating tools are banned outright (SPEC-030-era clusters register
        # k8s.delete_pod; a parked mutating call would swallow the turn).
        self.assertIn("Never call mutating tools", prompt)
        self.assertIn("k8s.delete_pod", prompt)

    def test_prompt_renders_missing_labels_and_summary(self) -> None:
        incident = _incident().model_copy(update={"labels": {}, "summary": ""})
        prompt = build_triage_prompt(incident, "alice", "incident-inc-aaa111")
        self.assertIn("(none)", prompt)


class ExtractionTests(unittest.TestCase):
    def test_extracts_fenced_block(self) -> None:
        block = extract_triage_block(_report_block())
        self.assertEqual(json.loads(block)["incident_id"], "inc-aaa111")

    def test_last_block_wins_when_agent_repeats_itself(self) -> None:
        text = _report_block(summary="first") + _report_block(summary="second")
        block = extract_triage_block(text)
        self.assertEqual(json.loads(block)["summary"], "second")

    def test_no_block_returns_none(self) -> None:
        self.assertIsNone(extract_triage_block("plain prose only"))
        self.assertIsNone(extract_triage_block(""))

    def test_other_fences_are_ignored(self) -> None:
        self.assertIsNone(extract_triage_block("```json\n{}\n```"))


class ParseTests(unittest.TestCase):
    SESSION = "incident-inc-aaa111"

    def test_valid_reply_parses(self) -> None:
        report = parse_triage_report(
            _report_block(), _incident(), "alice", self.SESSION
        )
        self.assertEqual(report.incident_id, "inc-aaa111")
        self.assertEqual(report.severity_assessment.value, "critical")

    def test_missing_emitter_fields_are_filled(self) -> None:
        block = _report_block()
        payload = json.loads(extract_triage_block(block))
        del payload["generated_at"]
        del payload["generated_by"]
        del payload["incident_id"]
        text = f"```triage-report\n{json.dumps(payload)}\n```"
        report = parse_triage_report(text, _incident(), "alice", self.SESSION)
        self.assertEqual(report.generated_by, "alice")
        self.assertEqual(report.incident_id, "inc-aaa111")

    def test_agent_supplied_attribution_is_overridden(self) -> None:
        # Attribution is server-minted: prompt injection via the incident
        # content must not spoof identity on the durable audit trail.
        report = parse_triage_report(
            _report_block(
                incident_id="inc-other999",
                session_id="incident-inc-other999",
                generated_at="1970-01-01T00:00:00+00:00",
                generated_by="mallory",
            ),
            _incident(),
            "alice",
            self.SESSION,
        )
        self.assertEqual(report.incident_id, "inc-aaa111")
        self.assertEqual(report.session_id, self.SESSION)
        self.assertEqual(report.generated_by, "alice")
        self.assertNotEqual(
            report.generated_at.isoformat(), "1970-01-01T00:00:00+00:00"
        )

    def test_missing_block_raises(self) -> None:
        with self.assertRaises(TriageError):
            parse_triage_report(
                "no block here", _incident(), "alice", self.SESSION
            )

    def test_invalid_json_raises(self) -> None:
        with self.assertRaises(TriageError):
            parse_triage_report(
                "```triage-report\n{not json}\n```",
                _incident(),
                "alice",
                self.SESSION,
            )

    def test_non_object_block_raises(self) -> None:
        with self.assertRaises(TriageError):
            parse_triage_report(
                '```triage-report\n["list"]\n```',
                _incident(),
                "alice",
                self.SESSION,
            )

    def test_schema_violation_raises(self) -> None:
        with self.assertRaises(TriageError):
            parse_triage_report(
                _report_block(severity_assessment="catastrophic"),
                _incident(),
                "alice",
                self.SESSION,
            )


def _mock_async_client(handler) -> object:
    """Patch target: route the agent calls through an httpx MockTransport."""
    real_client = httpx.AsyncClient

    def factory(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), timeout=1.0)

    return factory


class CallAgentTests(unittest.IsolatedAsyncioTestCase):
    """The agent dance: establish the dedicated session, then one chat turn."""

    PRIMARY = "incident-inc-aaa111"
    FALLBACK = "incident-inc-aaa111--alice"

    def _settings(self) -> IncidentSettings:
        return IncidentSettings(
            agent_service_url="http://agent-service:8000",
            triage_timeout_seconds=5.0,
        )

    async def _run(self, handler):
        with patch.object(triage.httpx, "AsyncClient", _mock_async_client(handler)):
            return await _call_agent(
                self._settings(),
                _incident(),
                "alice",
                "delegated-token",
                "req-1",
            )

    async def test_creates_dedicated_session_before_chat(self) -> None:
        calls: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(
                {"path": request.url.path, "body": json.loads(request.read())}
            )
            if request.url.path == "/api/v2/sessions":
                return httpx.Response(201, json={"session_id": self.PRIMARY})
            return httpx.Response(
                200,
                json={
                    "session_id": self.PRIMARY,
                    "request_id": "req-1",
                    "content": "agent reply",
                },
            )

        content, structured_output, session_used = await self._run(handler)
        self.assertEqual(content, "agent reply")
        self.assertIsNone(structured_output)
        self.assertEqual(session_used, self.PRIMARY)
        self.assertEqual(
            [call["path"] for call in calls],
            ["/api/v2/sessions", "/api/v2/chat"],
        )
        self.assertEqual(calls[0]["body"], {"session_id": self.PRIMARY})
        self.assertEqual(calls[1]["body"]["session_id"], self.PRIMARY)
        self.assertIn("inc-aaa111", calls[1]["body"]["message"])
        # SPEC-017 R-2: the triage turn requests kernel-validated
        # structured output via the triage report JSON schema.
        schema = calls[1]["body"]["response_schema"]
        self.assertIn("incident_id", schema["properties"])
        self.assertIn("severity_assessment", schema["properties"])
        # Triage turns run read-only: agent-platform strips mutating tools
        # from the turn's toolkit so nothing can execute or park here.
        self.assertTrue(calls[1]["body"]["read_only"])

    async def test_falls_back_to_per_operator_session(self) -> None:
        # The shared incident session owned by another operator answers 404;
        # re-triage must continue in the per-operator fallback session.
        calls: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.read())
            calls.append({"path": request.url.path, "body": body})
            if request.url.path == "/api/v2/sessions":
                if body["session_id"] == self.PRIMARY:
                    return httpx.Response(
                        404, json={"detail": "session not found"}
                    )
                return httpx.Response(201, json=body)
            return httpx.Response(
                200, json={"session_id": body["session_id"], "content": "reply"}
            )

        content, _, session_used = await self._run(handler)
        self.assertEqual(content, "reply")
        self.assertEqual(session_used, self.FALLBACK)
        self.assertEqual(
            [call["path"] for call in calls],
            ["/api/v2/sessions", "/api/v2/sessions", "/api/v2/chat"],
        )
        self.assertEqual(calls[2]["body"]["session_id"], self.FALLBACK)

    async def test_session_create_failure_raises_triage_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            # 404 for every candidate: both the shared and the fallback
            # session are owned elsewhere (or the platform is misbehaving).
            return httpx.Response(404, json={"detail": "session not found"})

        with self.assertRaises(TriageError):
            await self._run(handler)

    async def test_unexpected_session_status_aborts_without_fallback(self) -> None:
        calls: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append({"path": request.url.path})
            return httpx.Response(500, json={"detail": "boom"})

        with self.assertRaises(TriageError):
            await self._run(handler)
        # A non-404 failure is not an ownership signal: no second attempt.
        self.assertEqual([call["path"] for call in calls], ["/api/v2/sessions"])

    async def test_structured_output_is_relayed_when_present(self) -> None:
        structured = {"incident_id": "inc-aaa111", "summary": "kernel output"}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v2/sessions":
                return httpx.Response(201, json={"session_id": self.PRIMARY})
            return httpx.Response(
                200,
                json={
                    "session_id": self.PRIMARY,
                    "content": "agent reply",
                    "structured_output": structured,
                },
            )

        content, structured_output, session_used = await self._run(handler)
        self.assertEqual(content, "agent reply")
        self.assertEqual(structured_output, structured)
        self.assertEqual(session_used, self.PRIMARY)

    async def test_non_object_structured_output_is_discarded(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v2/sessions":
                return httpx.Response(201, json={"session_id": self.PRIMARY})
            return httpx.Response(
                200,
                json={
                    "session_id": self.PRIMARY,
                    "content": "agent reply",
                    "structured_output": ["not", "an", "object"],
                },
            )

        _, structured_output, _ = await self._run(handler)
        self.assertIsNone(structured_output)


class _FakeStore:
    """Minimal in-memory double for the incident store in run_triage."""

    def __init__(self) -> None:
        self.saved: list[Incident] = []
        self.report = None

    async def save(self, incident: Incident) -> Incident:
        self.saved.append(incident)
        return incident

    async def set_report(self, incident_id: str, report) -> None:
        self.report = report


class RunTriageStructuredTests(unittest.IsolatedAsyncioTestCase):
    """SPEC-017 R-2: kernel-validated structured output is preferred."""

    SESSION = "incident-inc-aaa111"

    def _settings(self) -> IncidentSettings:
        return IncidentSettings(
            agent_service_url="http://agent-service:8000",
            triage_timeout_seconds=5.0,
        )

    def _structured_payload(self, **overrides) -> dict:
        payload = {
            "incident_id": "inc-aaa111",
            "summary": "Structured kernel assessment.",
            "severity_assessment": "warning",
            "evidence": [
                {"source": "k8s.get_pod", "description": "CrashLoopBackOff"}
            ],
            "hypotheses": ["Failing readiness probe"],
            "next_steps": [
                {
                    "title": "Inspect probe config",
                    "rationale": "Crash loop evidence",
                    "priority": "medium",
                }
            ],
            "skills_cited": [],
            "session_id": self.SESSION,
            "generated_at": NOW.isoformat(),
            "generated_by": "alice",
        }
        payload.update(overrides)
        return payload

    async def _run(self, structured_output, raw_text="prose only") -> tuple:
        async def fake_call_agent(settings, incident, operator, token, req):
            return raw_text, structured_output, self.SESSION

        store = _FakeStore()
        with patch.object(triage, "_call_agent", fake_call_agent):
            incident, report = await triage.run_triage(
                self._settings(),
                store,
                _incident(),
                "alice",
                "delegated-token",
                "req-1",
            )
        return incident, report, store

    async def test_structured_output_preferred_over_fence(self) -> None:
        # The raw text carries no fenced block at all: success can only
        # come from the structured path.
        incident, report, store = await self._run(self._structured_payload())
        self.assertEqual(incident.status.value, "triaged")
        self.assertIsNotNone(report)
        self.assertEqual(report.summary, "Structured kernel assessment.")
        self.assertEqual(store.report, report)

    async def test_structured_attribution_is_server_minted(self) -> None:
        payload = self._structured_payload(
            incident_id="inc-other999",
            generated_by="mallory",
        )
        _, report, _ = await self._run(payload)
        self.assertEqual(report.incident_id, "inc-aaa111")
        self.assertEqual(report.generated_by, "alice")

    async def test_invalid_structured_payload_fails_triage(self) -> None:
        incident, report, _ = await self._run(
            self._structured_payload(severity_assessment="catastrophic")
        )
        self.assertEqual(incident.status.value, "triage_failed")
        self.assertIsNone(report)

    async def test_fence_fallback_used_when_structured_absent(self) -> None:
        incident, report, _ = await self._run(None, raw_text=_report_block())
        self.assertEqual(incident.status.value, "triaged")
        self.assertEqual(report.summary, "Node pressure is evicting pods.")


if __name__ == "__main__":
    unittest.main()
