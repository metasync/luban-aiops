"""SPEC-039 R-3: shift-summary digest assembly.

Covers the two-tier coverage model (owner-full vs foreign
metadata-only behind approvals:list), bounded-input validation,
structural rejection of unknown ids, per-source degradation, the
provenance block that anchors every cited record id, and the
deterministic handover section (SPEC-040 R-1).
"""

from __future__ import annotations

import pytest

from agent_service.services import shift_summary
from agent_service.services.confirmation_records import (
    InMemoryConfirmationRecordStore,
    make_record,
)
from agent_service.services.evidence_store import InMemoryEvidenceStore
from agent_service.services.execution_records import (
    InMemoryExecutionRecordStore,
    make_execution_record,
)
from agent_service.services.session_store import InMemorySessionStore
from agent_service.services.shift_summary import (
    MAX_SESSION_IDS,
    UNAVAILABLE,
    DigestInputError,
    ForeignSessionDenied,
    UnknownSessionError,
    build_digest,
    document_summary,
)


def _execution_request(
    session_id: str = "ses-alice",
    confirm_id: str = "cf-1",
    call_id: str = "call-1",
) -> dict:
    return {
        "execution_id": f"exec-{call_id}",
        "confirm_id": confirm_id,
        "call_id": call_id,
        "session_id": session_id,
        "tool_name": "k8s.restart_service",
        "requested_at": "2026-08-27T10:00:00Z",
    }


@pytest.fixture()
def stores(monkeypatch):
    """Fresh in-memory stores wired into the assembler's namespace."""
    sessions = InMemorySessionStore()
    confirmations = InMemoryConfirmationRecordStore()
    executions = InMemoryExecutionRecordStore()
    evidence = InMemoryEvidenceStore()
    monkeypatch.setattr(shift_summary, "SESSION_STORE", sessions)
    monkeypatch.setattr(shift_summary, "CONFIRMATION_RECORD_STORE", confirmations)
    monkeypatch.setattr(shift_summary, "EXECUTION_RECORD_STORE", executions)
    monkeypatch.setattr(shift_summary, "EVIDENCE_STORE", evidence)
    return {
        "sessions": sessions,
        "confirmations": confirmations,
        "executions": executions,
        "evidence": evidence,
    }


def _seed_owner_session(stores) -> str:
    record = stores["sessions"].create_session(user_id="alice", session_id="ses-alice")
    stores["sessions"].set_session_title(record.session_id, "restart investigation")
    stores["confirmations"].save_parked(
        make_record(
            "cf-1",
            record.session_id,
            "alice",
            [{"call_id": "call-1", "tool_name": "k8s.restart_service"}],
            "tools:mutate",
        )
    )
    stores["confirmations"].mark_resolved(
        record.session_id, "cf-1", "approved", "alice", "approve"
    )
    stores["confirmations"].save_parked(
        make_record(
            "cf-2",
            record.session_id,
            "alice",
            [{"call_id": "call-9", "tool_name": "k8s.scale_deployment"}],
            "tools:mutate",
        )
    )
    stores["executions"].save_request(
        make_execution_record(_execution_request(session_id=record.session_id))
    )
    stores["evidence"].save_turn(
        record.session_id,
        "req-1",
        1,
        [{"kind": "tool_call"}, {"kind": "tool_result"}],
        session_max_bytes=10_000_000,
    )
    return record.session_id


def _seed_foreign_session(stores) -> str:
    record = stores["sessions"].create_session(user_id="carol", session_id="ses-carol")
    stores["sessions"].set_session_title(record.session_id, "carol private title")
    stores["confirmations"].save_parked(
        make_record(
            "cf-f1",
            record.session_id,
            "carol",
            [{"call_id": "call-f", "tool_name": "k8s.restart_service"}],
            "tools:mutate",
        )
    )
    stores["confirmations"].mark_resolved(
        record.session_id, "cf-f1", "denied", "bob", "deny"
    )
    stores["executions"].save_request(
        make_execution_record(
            _execution_request(session_id=record.session_id, confirm_id="cf-f1", call_id="call-f")
        )
    )
    return record.session_id


class TestInputValidation:
    def test_empty_input_rejected(self, stores) -> None:
        with pytest.raises(DigestInputError):
            build_digest("alice", [], can_view_foreign=True)

    def test_over_cap_rejected(self, stores) -> None:
        with pytest.raises(DigestInputError, match=str(MAX_SESSION_IDS)):
            build_digest(
                "alice",
                [f"ses-{index}" for index in range(MAX_SESSION_IDS + 1)],
                can_view_foreign=True,
            )

    def test_blank_id_rejected(self, stores) -> None:
        with pytest.raises(DigestInputError):
            build_digest("alice", ["ses-1", "   "], can_view_foreign=True)

    def test_unknown_ids_rejected_without_leaking(self, stores) -> None:
        _seed_owner_session(stores)
        with pytest.raises(UnknownSessionError) as exc:
            build_digest("alice", ["ses-alice", "nope-1", "nope-2"], True)
        assert exc.value.session_ids == ["nope-1", "nope-2"]

    def test_duplicate_ids_deduplicated(self, stores) -> None:
        session_id = _seed_owner_session(stores)
        digest, provenance = build_digest(
            "alice", [session_id, session_id], can_view_foreign=False
        )
        assert digest["session_count"] == 1
        assert len(provenance["sessions"]) == 1


class TestForeignGating:
    def test_foreign_without_approvals_list_rejected_before_assembly(
        self, stores, monkeypatch
    ) -> None:
        _seed_owner_session(stores)
        foreign_id = _seed_foreign_session(stores)

        def _explode(*args, **kwargs):
            raise AssertionError("foreign facts must never be read")

        monkeypatch.setattr(stores["confirmations"], "load_for_session", _explode)
        with pytest.raises(ForeignSessionDenied) as exc:
            build_digest("alice", [foreign_id], can_view_foreign=False)
        assert exc.value.session_ids == [foreign_id]


class TestOwnerTier:
    def test_owner_digest_full_coverage(self, stores) -> None:
        session_id = _seed_owner_session(stores)
        digest, provenance = build_digest("alice", [session_id], False)
        assert digest["requester_user_id"] == "alice"
        entry = digest["sessions"][0]
        assert entry["coverage"] == "owner"
        assert entry["title"] == "restart investigation"
        assert entry["evidence"]["total_frame_count"] == 2
        assert entry["evidence"]["turns"][0]["frame_count"] == 2
        # Confirmations carry the owner-tier extras and verbatim decisions.
        confirmations = entry["confirmations"]
        assert [row["confirm_id"] for row in confirmations] == ["cf-1", "cf-2"]
        assert confirmations[0]["status"] == "approved"
        assert confirmations[0]["decision"] == "approve"
        assert confirmations[0]["pending_call_count"] == 1
        assert confirmations[1]["status"] == "pending"
        # Executions ride the receipt-bound shape.
        executions = entry["executions"]
        assert executions[0]["execution_id"] == "exec-call-1"
        assert executions[0]["status"] == "requested"
        # Still-pending items are surfaced for the handover reader.
        assert entry["open_items"] == {
            "pending_confirmations": 1,
            "requested_executions": 1,
        }
        # Transcript section reports counts only, never content.
        assert set(entry["transcript"]) == {
            "available",
            "turn_count",
            "user_turn_count",
        }
        # Provenance anchors every cited record id.
        prov = provenance["sessions"][0]
        assert prov["coverage"] == "owner"
        assert set(prov["cited_record_ids"]) == {"cf-1", "cf-2", "exec-call-1"}


class TestForeignTier:
    def test_foreign_digest_metadata_only(self, stores) -> None:
        foreign_id = _seed_foreign_session(stores)
        digest, provenance = build_digest("alice", [foreign_id], True)
        entry = digest["sessions"][0]
        assert entry["coverage"] == "foreign"
        # The metadata-only posture: no title, transcript, or evidence.
        assert "title" not in entry
        assert "transcript" not in entry
        assert "evidence" not in entry
        decisions = entry["confirmation_decisions"]
        assert decisions[0]["status"] == "denied"
        assert decisions[0]["decider_user_id"] == "bob"
        # Foreign entries never carry owner-tier call details.
        assert "pending_call_count" not in decisions[0]
        assert entry["record_counts"] == {"confirmations": 1, "executions": 1}
        assert provenance["sessions"][0]["coverage"] == "foreign"

    def test_mixed_coverage_preserves_input_order(self, stores) -> None:
        own_id = _seed_owner_session(stores)
        foreign_id = _seed_foreign_session(stores)
        digest, _ = build_digest("alice", [foreign_id, own_id], True)
        assert [entry["session_id"] for entry in digest["sessions"]] == [
            foreign_id,
            own_id,
        ]


class TestDegradation:
    def test_unreadable_store_reports_unavailable_per_source(
        self, stores, monkeypatch
    ) -> None:
        session_id = _seed_owner_session(stores)

        def _explode(*args, **kwargs):
            raise RuntimeError("evidence store unreachable")

        monkeypatch.setattr(stores["evidence"], "load_turns", _explode)
        digest, _ = build_digest("alice", [session_id], False)
        entry = digest["sessions"][0]
        assert entry["evidence"] == UNAVAILABLE
        # Sibling sections stay intact — degradation is per-source.
        assert entry["confirmations"] != UNAVAILABLE
        assert entry["executions"] != UNAVAILABLE
        assert entry["transcript"] != UNAVAILABLE

    def test_unreadable_confirmation_store_degrades_open_items(
        self, stores, monkeypatch
    ) -> None:
        session_id = _seed_owner_session(stores)

        def _explode(*args, **kwargs):
            raise RuntimeError("confirmation store unreachable")

        monkeypatch.setattr(
            stores["confirmations"], "load_for_session", _explode
        )
        digest, provenance = build_digest("alice", [session_id], False)
        entry = digest["sessions"][0]
        assert entry["confirmations"] == UNAVAILABLE
        assert entry["open_items"]["pending_confirmations"] is None
        # Executions unaffected.
        assert entry["open_items"]["requested_executions"] == 1
        # No cited confirmation ids leak into provenance.
        assert provenance["sessions"][0]["cited_record_ids"] == ["exec-call-1"]


class TestHandoverSection:
    """SPEC-040 R-1: the deterministic shift-story skeleton."""

    def test_handover_carries_own_decisions_and_executions(self, stores) -> None:
        session_id = _seed_owner_session(stores)
        digest, _ = build_digest("alice", [session_id], False)
        handover = digest["handover"]
        assert handover["covered_session_count"] == 1
        assert handover["own_session_count"] == 1
        assert handover["foreign_session_count"] == 0
        # cf-1 was approved; cf-2 stays pending and rides open items.
        assert handover["decision_count"] == 1
        [decision] = handover["decisions"]
        assert decision == {
            "session_id": session_id,
            "confirm_id": "cf-1",
            "action": "tools:mutate",
            "decision": "approve",
            "decider_user_id": "alice",
            "decided_at": decision["decided_at"],
        }
        assert handover["execution_count"] == 1
        [execution] = handover["executions"]
        assert execution["execution_id"] == "exec-call-1"
        assert execution["tool_name"] == "k8s.restart_service"
        assert handover["open_items"] == {
            "pending_confirmations": 1,
            "requested_executions": 1,
        }
        assert handover["open_sessions"] == [session_id]
        assert handover["quiet"] is False

    def test_handover_is_deterministic(self, stores) -> None:
        session_id = _seed_owner_session(stores)
        first, _ = build_digest("alice", [session_id], False)
        second, _ = build_digest("alice", [session_id], False)
        # Same store state -> byte-identical handover skeleton.
        assert first["handover"] == second["handover"]

    def test_foreign_sessions_contribute_counts_only(self, stores) -> None:
        own_id = _seed_owner_session(stores)
        foreign_id = _seed_foreign_session(stores)
        digest, _ = build_digest("alice", [own_id, foreign_id], True)
        handover = digest["handover"]
        assert handover["covered_session_count"] == 2
        assert handover["foreign_session_count"] == 1
        # Foreign denied decision and execution receipt count in the
        # totals but never surface session-level details.
        assert handover["decision_count"] == 2
        assert handover["execution_count"] == 2
        for row in handover["decisions"] + handover["executions"]:
            assert row["session_id"] == own_id
        # The foreign session never appears in open_sessions details.
        assert foreign_id not in handover["open_sessions"]

    def test_quiet_shift_reports_honest_empty_state(self, stores) -> None:
        record = stores["sessions"].create_session(
            user_id="alice", session_id="ses-quiet"
        )
        digest, _ = build_digest("alice", [record.session_id], False)
        handover = digest["handover"]
        assert handover["quiet"] is True
        assert handover["decision_count"] == 0
        assert handover["execution_count"] == 0
        assert handover["decisions"] == []
        assert handover["executions"] == []
        assert handover["open_items"] == {
            "pending_confirmations": 0,
            "requested_executions": 0,
        }

    def test_degraded_source_keeps_handover_assembled(
        self, stores, monkeypatch
    ) -> None:
        session_id = _seed_owner_session(stores)

        def _explode(*args, **kwargs):
            raise RuntimeError("confirmation store unreachable")

        monkeypatch.setattr(
            stores["confirmations"], "load_for_session", _explode
        )
        digest, _ = build_digest("alice", [session_id], False)
        # The unavailable confirmation section contributes nothing, but
        # the handover section still assembles from the rest.
        handover = digest["handover"]
        assert handover["execution_count"] == 1
        assert handover["decisions"] == []


class TestDocumentSummary:
    """SPEC-041 R-4: deterministic counts-only list summary."""

    def test_busy_shift_summary_carries_counts_and_open_items(
        self, stores
    ) -> None:
        session_id = _seed_owner_session(stores)
        digest, _ = build_digest("alice", [session_id], False)
        # 1 decided confirmation, 1 execution, 1 pending + 1 requested open.
        assert (
            document_summary(digest)
            == "1 session \u00b7 1 decision \u00b7 1 execution \u00b7 2 open items"
        )

    def test_summary_is_counts_only(self, stores) -> None:
        session_id = _seed_owner_session(stores)
        digest, _ = build_digest("alice", [session_id], False)
        summary = document_summary(digest) or ""
        # Never titles, record ids, outcomes, or session ids.
        assert "restart investigation" not in summary
        assert "cf-" not in summary and "exec-" not in summary
        assert "approved" not in summary
        assert session_id not in summary

    def test_summary_is_deterministic(self, stores) -> None:
        session_id = _seed_owner_session(stores)
        first, _ = build_digest("alice", [session_id], False)
        second, _ = build_digest("alice", [session_id], False)
        assert document_summary(first) == document_summary(second)

    def test_quiet_shift_summary_uses_plain_phrasing(self, stores) -> None:
        record = stores["sessions"].create_session(
            user_id="alice", session_id="ses-quiet"
        )
        digest, _ = build_digest("alice", [record.session_id], False)
        assert (
            document_summary(digest)
            == "Quiet shift \u2014 no recorded decisions or executions."
        )

    def test_missing_handover_degrades_to_none(self) -> None:
        # Pre-SPEC-040 digests carry no handover section.
        assert document_summary({"sessions": []}) is None
        assert document_summary({"handover": "corrupted"}) is None

    def test_open_suffix_dropped_when_nothing_open(self, stores) -> None:
        session_id = _seed_owner_session(stores)
        # Resolve the parked confirmation and complete the execution so
        # nothing stays open.
        stores["confirmations"].mark_resolved(
            session_id, "cf-2", "approved", "alice", "approve"
        )
        stores["executions"].save_receipt(
            "cf-1",
            "call-1",
            {"status": "succeeded", "completed_at": "2026-08-28T10:00:00Z"},
            True,
        )
        digest, _ = build_digest("alice", [session_id], False)
        assert (
            document_summary(digest)
            == "1 session \u00b7 2 decisions \u00b7 1 execution"
        )
