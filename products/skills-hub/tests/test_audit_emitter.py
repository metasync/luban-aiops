"""Audit emitter tests (SPEC-029 R-2, SPEC-013 pattern).

Guarantees the fire-and-forget contract: an unset audit URL keeps behavior a
byte-for-byte no-op (no thread spawned), delivery failures are swallowed and
counted, and the built envelope validates against the shared audit-event
contract.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import jsonschema

from skills_hub.core.config import SkillsSettings
from skills_hub.services import audit_emitter

SCHEMAS_DIR = (
    Path(__file__).resolve().parents[3] / "shared" / "shared-contracts" / "schemas"
)


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / name).read_text())


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeClient:
    """Stand-in for httpx.Client capturing the post() call."""

    def __init__(self, response=None, raise_exc=None) -> None:
        self._response = response
        self._raise = raise_exc
        self.calls: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *args) -> bool:
        return False

    def post(self, url, json=None, auth=None):
        self.calls.append({"url": url, "json": json, "auth": auth})
        if self._raise is not None:
            raise self._raise
        return self._response


def _settings(**overrides) -> SkillsSettings:
    defaults = {
        "audit_service_url": "http://audit-service:8000",
        "audit_client_id": "skills-hub",
        "audit_client_secret": "sh-secret",
    }
    defaults.update(overrides)
    return SkillsSettings(**defaults)


class BuildAuditEventTests(unittest.TestCase):
    def test_envelope_validates_against_contract(self) -> None:
        event = audit_emitter.build_audit_event(
            "skill_searched",
            "req-1",
            "success",
            details={"query": "crashloop", "limit": 5, "result_count": 2},
            actor="tool-gateway",
        )
        jsonschema.validate(event, _load_schema("audit-event.schema.json"))
        self.assertEqual(event["service"], "skills-hub")
        self.assertEqual(event["request_id"], "req-1")

    def test_optional_fields_omitted_when_absent(self) -> None:
        event = audit_emitter.build_audit_event("skills_synced", "req-1", "error")
        for key in ("subject", "username", "actor", "roles", "session_id"):
            self.assertNotIn(key, event)
        jsonschema.validate(event, _load_schema("audit-event.schema.json"))

    def test_missing_request_id_falls_back_to_unknown(self) -> None:
        event = audit_emitter.build_audit_event("skills_synced", None, "success")
        self.assertEqual(event["request_id"], "unknown")


class EmitAuditEventTests(unittest.TestCase):
    def test_noop_when_url_unset_spawns_no_thread(self) -> None:
        settings = _settings(audit_service_url="")
        event = audit_emitter.build_audit_event("skill_searched", "req-1", "success")
        with patch.object(audit_emitter.threading, "Thread") as thread_mock:
            audit_emitter.emit_audit_event(settings, event)
        thread_mock.assert_not_called()

    def test_spawns_thread_when_url_set(self) -> None:
        settings = _settings()
        event = audit_emitter.build_audit_event("skill_searched", "req-1", "success")
        with patch.object(audit_emitter.threading, "Thread") as thread_mock:
            audit_emitter.emit_audit_event(settings, event)
        thread_mock.assert_called_once()


class DeliverTests(unittest.TestCase):
    def test_deliver_success_records_ok(self) -> None:
        settings = _settings()
        event = audit_emitter.build_audit_event("skill_searched", "req-1", "success")
        fake = _FakeClient(response=_FakeResponse(202))
        with (
            patch.object(audit_emitter.httpx, "Client", return_value=fake),
            patch.object(audit_emitter, "record_audit_emit") as record,
        ):
            audit_emitter._deliver(settings, event)
        record.assert_called_once_with("ok")
        self.assertEqual(
            fake.calls[0]["url"], "http://audit-service:8000/api/v1/audit/events"
        )
        self.assertEqual(fake.calls[0]["json"], {"events": [event]})
        self.assertEqual(fake.calls[0]["auth"], ("skills-hub", "sh-secret"))

    def test_deliver_non_2xx_records_error(self) -> None:
        settings = _settings()
        event = audit_emitter.build_audit_event("skill_searched", "req-1", "success")
        fake = _FakeClient(response=_FakeResponse(401))
        with (
            patch.object(audit_emitter.httpx, "Client", return_value=fake),
            patch.object(audit_emitter, "record_audit_emit") as record,
        ):
            audit_emitter._deliver(settings, event)
        record.assert_called_once_with("error")

    def test_deliver_transport_error_swallowed_and_counted(self) -> None:
        settings = _settings()
        event = audit_emitter.build_audit_event("skill_searched", "req-1", "success")
        fake = _FakeClient(raise_exc=httpx.ConnectError("unreachable"))
        with (
            patch.object(audit_emitter.httpx, "Client", return_value=fake),
            patch.object(audit_emitter, "record_audit_emit") as record,
        ):
            audit_emitter._deliver(settings, event)  # must not raise
        record.assert_called_once_with("error")


if __name__ == "__main__":
    unittest.main()
