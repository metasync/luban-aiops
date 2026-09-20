"""Per-source sync engine tests (SPEC-014 R-2).

A successful cycle swaps the source snapshot atomically; a failed cycle keeps
the previously served slice and records the error in the status registry.
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skills_hub.core.config import SkillsSettings, SourceSpec
from skills_hub.services import ingestion
from skills_hub.services import sync as sync_module
from skills_hub.services.skill_store import InMemorySkillStore
from skills_hub.services.sync import (
    SyncManager,
    _rejection_category,
    _with_token,
)

VALID_DOC = """---
title: KubePodNotReady
description: Pod not ready triage steps.
tags: [KubePodNotReady]
---

Check the pod events.
"""


def _run(coro):
    return asyncio.run(coro)


def _settings(*sources: SourceSpec) -> SkillsSettings:
    return SkillsSettings(sources=tuple(sources))


# SPEC-057 R-2 resolution fixtures: the single-target sub-skills a composition
# references. ``WRITE_SUB`` is a browser write web-check (risk_class: write);
# ``INFRA_WRITE_SUB`` is an infra write (risk_class: write, no web_target);
# ``READ_SUB`` is a read web-check (no risk_class); ``KNOWLEDGE_SUB`` is a plain
# knowledge doc. Each is single-target by construction (``web_target`` is scalar).
WRITE_SUB = """---
title: Reset Password
description: Reset a user's password in the admin portal.
web_target: https://admin.internal/login
risk_class: write
---

Reset the password.
"""

INFRA_WRITE_SUB = """---
title: Lock Unlock User
description: Lock or unlock a user account over the infra API.
risk_class: write
---

Toggle the account lock.
"""

READ_SUB = """---
title: Check Status
description: Check a user's status page.
web_target: https://admin.internal/status
---

Read the status.
"""

KNOWLEDGE_SUB = """---
title: Reference Doc
description: A plain knowledge document.
---

Background reading.
"""


def _composition_doc(sub_skill_ids: list[str]) -> str:
    """A ``kind: composition`` document referencing the given sub-skill ids."""
    items = "".join(
        f"  - skill_id: {skill_id}\n    note: Step {index}.\n"
        for index, skill_id in enumerate(sub_skill_ids, start=1)
    )
    return (
        "---\ntitle: Remediation Runbook\n"
        "description: Reset the password then unlock the account.\n"
        "kind: composition\n"
        f"sub_skills:\n{items}"
        "---\n\nOn failure, report which sub-skill failed and stop.\n"
    )


class SyncOnceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "alerts").mkdir()
        (self.root / "alerts" / "KubePodNotReady.md").write_text(VALID_DOC)
        self.store = InMemorySkillStore()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_successful_sync_swaps_snapshot(self) -> None:
        spec = SourceSpec(
            source_id="sre-alerting", type="local", path=str(self.root)
        )
        manager = SyncManager(_settings(spec), self.store)
        status = _run(manager.sync_once(spec))
        self.assertIsNone(status.last_error)
        self.assertEqual(status.accepted, 1)
        self.assertEqual(status.ref, "local")
        self.assertEqual(_run(self.store.count()), 1)
        self.assertIsNotNone(
            _run(self.store.get("sre-alerting/alerts/kubepodnotready"))
        )

    def test_rejections_are_reported_and_swapped(self) -> None:
        (self.root / "broken.md").write_text("no frontmatter")
        spec = SourceSpec(source_id="team-a", type="local", path=str(self.root))
        manager = SyncManager(_settings(spec), self.store)
        status = _run(manager.sync_once(spec))
        self.assertEqual(status.accepted, 1)
        self.assertEqual(len(status.rejections), 1)
        self.assertIn("frontmatter", status.rejections[0].reason)

    def test_failed_cycle_keeps_previous_snapshot(self) -> None:
        spec = SourceSpec(
            source_id="team-git",
            type="git",
            url="https://example.com/team.git",
            ref="main",
        )
        manager = SyncManager(_settings(spec), self.store)
        _run(self.store.replace_source("team-git", []))  # prior state

        with patch(
            "skills_hub.services.sync._git_checkout",
            side_effect=RuntimeError("clone failed"),
        ):
            status = _run(manager.sync_once(spec))
        self.assertIn("clone failed", status.last_error)
        # Store untouched by the failed cycle.
        self.assertEqual(_run(self.store.count()), 0)

        report = manager.status_report()
        self.assertEqual(report[0]["source_id"], "team-git")
        self.assertIn("clone failed", report[0]["last_error"])

    def test_failed_cycle_scrubs_git_token_from_error(self) -> None:
        """A failed clone quotes its argv (token URL included); the error
        reaches the auth-exempt status endpoint, so the credential must be
        scrubbed before it is stored."""
        spec = SourceSpec(
            source_id="team-git",
            type="git",
            url="https://example.com/team.git",
            ref="main",
        )
        settings = SkillsSettings(
            sources=(spec,), git_tokens={"team-git": "sekrit-token"}
        )
        manager = SyncManager(settings, self.store)
        with patch(
            "skills_hub.services.sync._git_checkout",
            side_effect=RuntimeError(
                "clone failed: https://x-access-token:sekrit-token@example.com"
            ),
        ):
            status = _run(manager.sync_once(spec))
        self.assertNotIn("sekrit-token", status.last_error)
        self.assertIn("***", status.last_error)
        report = manager.status_report()
        self.assertNotIn("sekrit-token", report[0]["last_error"])

    def test_git_source_ingests_from_configured_subpath(self) -> None:
        """Monorepo sources ingest only the configured subdirectory of the
        checkout, not the repo root."""
        spec = SourceSpec(
            source_id="team-git",
            type="git",
            url="https://example.com/team.git",
            ref="main",
            path="ops/skills",
        )
        settings = SkillsSettings(
            sources=(spec,), data_path=str(self.root / "data")
        )

        def fake_checkout(
            source_id: str, url: str, ref: str, dest: Path, token: str | None
        ):
            sub = dest / "ops" / "skills"
            sub.mkdir(parents=True)
            (sub / "KubePodNotReady.md").write_text(VALID_DOC)
            return "abc1234"

        manager = SyncManager(settings, self.store)
        with patch(
            "skills_hub.services.sync._git_checkout",
            side_effect=fake_checkout,
        ):
            status = _run(manager.sync_once(spec))
        self.assertIsNone(status.last_error)
        self.assertEqual(status.accepted, 1)
        self.assertEqual(status.ref, "abc1234")
        self.assertIsNotNone(
            _run(self.store.get("team-git/kubepodnotready"))
        )

    def test_git_source_reports_missing_subpath_clearly(self) -> None:
        spec = SourceSpec(
            source_id="team-git",
            type="git",
            url="https://example.com/team.git",
            ref="main",
            path="does/not/exist",
        )
        settings = SkillsSettings(
            sources=(spec,), data_path=str(self.root / "data")
        )
        manager = SyncManager(settings, self.store)
        with patch(
            "skills_hub.services.sync._git_checkout",
            return_value="abc1234",
        ):
            status = _run(manager.sync_once(spec))
        self.assertIn("does/not/exist", status.last_error)
        self.assertEqual(_run(self.store.count()), 0)

    def test_status_report_orders_sources_and_bounds_fields(self) -> None:
        spec_a = SourceSpec(source_id="b-src", type="local", path=str(self.root))
        spec_b = SourceSpec(source_id="a-src", type="local", path=str(self.root))
        manager = SyncManager(_settings(spec_a, spec_b), self.store)
        _run(manager.sync_once(spec_a))
        report = manager.status_report()
        self.assertEqual([s["source_id"] for s in report], ["a-src", "b-src"])
        self.assertEqual(report[1]["accepted"], 1)
        self.assertEqual(report[0]["last_sync_at"], None)

    # --- Usage audit trail (SPEC-029 R-4) -----------------------------------

    def test_successful_sync_emits_skills_synced_event(self) -> None:
        (self.root / "broken.md").write_text("no frontmatter")
        spec = SourceSpec(
            source_id="sre-alerting", type="local", path=str(self.root)
        )
        manager = SyncManager(_settings(spec), self.store)
        with patch("skills_hub.services.sync.emit_audit_event") as emit:
            _run(manager.sync_once(spec))
        emit.assert_called_once()
        event = emit.call_args.args[1]
        self.assertEqual(event["event_type"], "skills_synced")
        self.assertEqual(event["outcome"], "success")
        self.assertEqual(event["service"], "skills-hub")
        self.assertEqual(event["request_id"], "unknown")
        self.assertNotIn("actor", event)
        self.assertEqual(
            event["details"],
            {
                "source_id": "sre-alerting",
                "source_type": "local",
                "ref": "local",
                "accepted": 1,
                "rejected": 1,
            },
        )

    def test_failed_sync_emits_error_event_with_scrubbed_message(self) -> None:
        spec = SourceSpec(
            source_id="team-git",
            type="git",
            url="https://example.com/team.git",
            ref="main",
        )
        settings = SkillsSettings(
            sources=(spec,), git_tokens={"team-git": "sekrit-token"}
        )
        manager = SyncManager(settings, self.store)
        with (
            patch("skills_hub.services.sync.emit_audit_event") as emit,
            patch(
                "skills_hub.services.sync._git_checkout",
                side_effect=RuntimeError(
                    "clone failed: https://x-access-token:sekrit-token@example.com"
                ),
            ),
        ):
            _run(manager.sync_once(spec))
        event = emit.call_args.args[1]
        self.assertEqual(event["event_type"], "skills_synced")
        self.assertEqual(event["outcome"], "error")
        self.assertEqual(event["details"]["source_id"], "team-git")
        self.assertEqual(event["details"]["source_type"], "git")
        self.assertNotIn("sekrit-token", event["details"]["error"])
        self.assertIn("***", event["details"]["error"])


class CompositionResolutionTests(unittest.TestCase):
    """SPEC-057 R-2 resolution layer: the store-consulting pass in ``sync_once``
    that resolves each composition's ``sub_skills`` against the catalog, drops +
    rejects an unresolved or nested reference (never silently served, never
    degraded to knowledge), and derives + persists the surviving composition's
    display ``risk_class``. The structural layer is asserted in
    ``test_ingestion.py``; this covers only the facts that need the store.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = InMemorySkillStore()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, rel_path: str, content: str) -> None:
        target = self.root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def _manager(self, *specs: SourceSpec) -> SyncManager:
        return SyncManager(_settings(*specs), self.store)

    def _local_spec(self, source_id: str = "samples", root: Path | None = None):
        return SourceSpec(
            source_id=source_id, type="local", path=str(root or self.root)
        )

    def test_a_resolved_composition_persists_with_its_sub_skills(self) -> None:
        self._write("ResetPassword.md", WRITE_SUB)
        self._write("LockUnlockUser.md", INFRA_WRITE_SUB)
        self._write(
            "Runbook.md",
            _composition_doc(
                ["samples/resetpassword", "samples/lockunlockuser"]
            ),
        )
        spec = self._local_spec()
        status = _run(self._manager(spec).sync_once(spec))
        self.assertEqual(status.rejections, ())
        self.assertEqual(status.accepted, 3)
        runbook = _run(self.store.get("samples/runbook"))
        self.assertIsNotNone(runbook)
        self.assertEqual(runbook.kind, "composition")
        self.assertEqual(
            [ref.skill_id for ref in runbook.sub_skills],
            ["samples/resetpassword", "samples/lockunlockuser"],
        )

    def test_derived_risk_class_is_write_when_any_sub_skill_writes(self) -> None:
        # password-reset is a browser write, so the mixed composition derives
        # ``write`` — persisted, and carried to the badge by ``summary()``.
        self._write("ResetPassword.md", WRITE_SUB)
        self._write("CheckStatus.md", READ_SUB)
        self._write(
            "Runbook.md",
            _composition_doc(["samples/resetpassword", "samples/checkstatus"]),
        )
        spec = self._local_spec()
        status = _run(self._manager(spec).sync_once(spec))
        self.assertEqual(status.rejections, ())
        runbook = _run(self.store.get("samples/runbook"))
        self.assertEqual(runbook.risk_class, "write")
        self.assertEqual(runbook.summary()["risk_class"], "write")

    def test_derived_risk_class_is_read_when_no_sub_skill_writes(self) -> None:
        self._write("CheckStatus.md", READ_SUB)
        self._write("ReferenceDoc.md", KNOWLEDGE_SUB)
        self._write(
            "Runbook.md",
            _composition_doc(["samples/checkstatus", "samples/referencedoc"]),
        )
        spec = self._local_spec()
        status = _run(self._manager(spec).sync_once(spec))
        self.assertEqual(status.rejections, ())
        runbook = _run(self.store.get("samples/runbook"))
        self.assertEqual(runbook.risk_class, "read")

    def test_an_unresolved_sub_skill_is_dropped_and_rejected(self) -> None:
        self._write("Runbook.md", _composition_doc(["samples/does-not-exist"]))
        spec = self._local_spec()
        status = _run(self._manager(spec).sync_once(spec))
        # Dropped, not served and not degraded to a knowledge skill.
        self.assertEqual(status.accepted, 0)
        self.assertIsNone(_run(self.store.get("samples/runbook")))
        self.assertEqual(len(status.rejections), 1)
        self.assertIn("does not", status.rejections[0].reason)
        self.assertIn("samples/does-not-exist", status.rejections[0].reason)
        self.assertEqual(
            _rejection_category(status.rejections[0].reason), "composition"
        )

    def test_a_nested_composition_sub_skill_is_rejected(self) -> None:
        # The inner composition resolves (its own sub-skill is present), but the
        # outer one references a composition, which Phase 1 forbids — removing
        # cycles and unbounded depth by construction rather than by detection.
        self._write("ResetPassword.md", WRITE_SUB)
        self._write("Inner.md", _composition_doc(["samples/resetpassword"]))
        self._write("Outer.md", _composition_doc(["samples/inner"]))
        spec = self._local_spec()
        status = _run(self._manager(spec).sync_once(spec))
        # inner (resolved) + resetpassword accepted; outer rejected for nesting.
        self.assertEqual(status.accepted, 2)
        self.assertEqual(len(status.rejections), 1)
        self.assertIn("is itself a", status.rejections[0].reason)
        self.assertIn("samples/inner", status.rejections[0].reason)
        self.assertEqual(
            _rejection_category(status.rejections[0].reason), "composition"
        )
        self.assertIsNotNone(_run(self.store.get("samples/inner")))

    def test_a_cross_source_sub_skill_resolves_after_its_source_syncs(self) -> None:
        # Source A holds the composition; source B holds its sub-skill. On the
        # cycle before B has ever synced the reference is unresolved and A's
        # composition is rejected; after B syncs, a later A cycle resolves it
        # (eventual consistency — Resolved At Plan Time 4).
        a_root, b_root = self.root / "a", self.root / "b"
        a_root.mkdir()
        b_root.mkdir()
        (a_root / "Runbook.md").write_text(
            _composition_doc(["b-src/resetpassword"]), encoding="utf-8"
        )
        (b_root / "ResetPassword.md").write_text(WRITE_SUB, encoding="utf-8")
        spec_a = self._local_spec("a-src", a_root)
        spec_b = self._local_spec("b-src", b_root)
        manager = self._manager(spec_a, spec_b)

        # Cycle 1: A syncs before B -> unresolved -> rejected, never served.
        first = _run(manager.sync_once(spec_a))
        self.assertEqual(first.accepted, 0)
        self.assertEqual(len(first.rejections), 1)
        self.assertIn("does not", first.rejections[0].reason)

        # B syncs, publishing the sub-skill into the shared catalog.
        self.assertEqual(_run(manager.sync_once(spec_b)).accepted, 1)

        # Cycle 2: A syncs again -> the cross-source id now resolves from store.
        second = _run(manager.sync_once(spec_a))
        self.assertEqual(second.accepted, 1)
        self.assertEqual(second.rejections, ())
        runbook = _run(self.store.get("a-src/runbook"))
        self.assertIsNotNone(runbook)
        self.assertEqual(runbook.risk_class, "write")

    def test_a_composition_rejection_rides_the_skills_synced_event(self) -> None:
        # No new audit event type: the resolution rejection increments the
        # existing skills_synced rejected count and nothing else is emitted.
        self._write("Runbook.md", _composition_doc(["samples/does-not-exist"]))
        spec = self._local_spec()
        manager = self._manager(spec)
        with patch("skills_hub.services.sync.emit_audit_event") as emit:
            _run(manager.sync_once(spec))
        emit.assert_called_once()
        event = emit.call_args.args[1]
        self.assertEqual(event["event_type"], "skills_synced")
        self.assertEqual(event["outcome"], "success")
        self.assertEqual(event["details"]["accepted"], 0)
        self.assertEqual(event["details"]["rejected"], 1)


class GitUrlTests(unittest.TestCase):
    def test_token_injected_into_https_url(self) -> None:
        url = _with_token("https://github.com/team/repo.git", "tok")
        self.assertEqual(
            url, "https://x-access-token:tok@github.com/team/repo.git"
        )

    def test_no_token_leaves_url_untouched(self) -> None:
        self.assertEqual(
            _with_token("https://github.com/team/repo.git", None),
            "https://github.com/team/repo.git",
        )

    def test_non_https_url_never_gets_token(self) -> None:
        self.assertEqual(
            _with_token("git@github.com:team/repo.git", "tok"),
            "git@github.com:team/repo.git",
        )


class SyncSpanTests(unittest.TestCase):
    """The sync loop emits bounded spans (no-op unless a provider is set)."""

    def setUp(self) -> None:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "KubePodNotReady.md").write_text(VALID_DOC)
        self.store = InMemorySkillStore()
        self.exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.tracer = provider.get_tracer("skills_hub.sync")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _by_name(self, name: str):
        return [s for s in self.exporter.get_finished_spans() if s.name == name]

    def test_successful_sync_emits_span_with_result_ok(self) -> None:
        spec = SourceSpec(
            source_id="sre-alerting", type="local", path=str(self.root)
        )
        manager = SyncManager(_settings(spec), self.store)
        with patch.object(sync_module, "TRACER", self.tracer):
            _run(manager.sync_once(spec))
        spans = self._by_name("skills.sync")
        self.assertEqual(len(spans), 1)
        attrs = spans[0].attributes
        self.assertEqual(attrs["source.id"], "sre-alerting")
        self.assertEqual(attrs["source.type"], "local")
        self.assertEqual(attrs["result"], "ok")
        self.assertEqual(attrs["accepted"], 1)

    def test_failed_sync_emits_span_with_result_error(self) -> None:
        spec = SourceSpec(
            source_id="team-git",
            type="git",
            url="https://example.com/team.git",
            ref="main",
        )
        manager = SyncManager(_settings(spec), self.store)
        with patch.object(sync_module, "TRACER", self.tracer), patch(
            "skills_hub.services.sync._git_checkout",
            side_effect=RuntimeError("clone failed"),
        ):
            _run(manager.sync_once(spec))
        spans = self._by_name("skills.sync")
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].attributes["result"], "error")

    def test_git_checkout_span_scrubs_token_from_error_event(self) -> None:
        dest = self.root / "checkout"
        with patch.object(sync_module, "TRACER", self.tracer), patch(
            "skills_hub.services.sync._git",
            side_effect=RuntimeError(
                "clone failed: https://x-access-token:sekrit@example.com"
            ),
        ):
            with self.assertRaises(RuntimeError):
                sync_module._git_checkout(
                    "team-git",
                    "https://example.com/team.git",
                    "main",
                    dest,
                    "sekrit",
                )
        spans = self._by_name("skills.git.checkout")
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.attributes["source.id"], "team-git")
        self.assertEqual(span.attributes["source.ref"], "main")
        messages = [
            ev.attributes.get("message", "")
            for ev in span.events
            if ev.name == "checkout.error"
        ]
        self.assertEqual(len(messages), 1)
        self.assertNotIn("sekrit", messages[0])
        self.assertIn("***", messages[0])


class RejectionCategoryTests(unittest.TestCase):
    """The rejection counter's label is a bounded observability bucket.

    SPEC-055 R-3 added a second size-bounded artifact (the step list), so its
    two resource ceilings join the body's in ``size`` — while the neighbouring
    per-field and tag-count bounds stay ``frontmatter``, which is what keeps
    the bucket meaning "the document was too big" rather than "a number in it
    was".

    Reason strings are derived from ingestion's own constants wherever
    ingestion derives them, so a cap change moves these with it; the two that
    ingestion renders as literals stay literal here too, rather than being
    "derived" into strings ingestion never emits. The wording itself is pinned
    end to end in ``test_ingestion.py``, which asserts the bucket on the reason
    a real oversize document actually produced.
    """

    def test_artifact_size_ceilings_are_bucketed_as_size(self) -> None:
        for reason in (
            "body exceeds 64 KiB",
            f"steps exceed {ingestion.MAX_STEPS_BYTES // 1024} KiB",
            f"more than {ingestion.MAX_STEPS} steps",
        ):
            with self.subTest(reason=reason):
                self.assertEqual(_rejection_category(reason), "size")

    def test_field_and_tag_bounds_stay_frontmatter(self) -> None:
        # "more than N tags" shares its prefix with "more than N steps"; the
        # ``steps`` gate is what keeps the two apart.
        for reason in (
            f"more than {ingestion.MAX_TAGS} tags",
            "tag exceeds 64 chars",
            f"step 1: tool exceeds {ingestion.MAX_STEP_TOOL_CHARS} chars",
            "step 2: expect must be a string \u2264 "
            f"{ingestion.MAX_STEP_EXPECT_CHARS} chars",
            f"steps requires kind: {ingestion.EXECUTABLE_FLOW_KIND}",
            f"kind: {ingestion.EXECUTABLE_FLOW_KIND} requires risk_class: write",
            f"kind: {ingestion.EXECUTABLE_FLOW_KIND} requires a non-empty "
            "steps list",
            "a web.* step requires a web_target declaration",
        ):
            with self.subTest(reason=reason):
                self.assertEqual(
                    _rejection_category(reason), "frontmatter", reason
                )

    def test_the_other_labels_are_unchanged(self) -> None:
        # Reason strings as ingestion actually renders them.
        self.assertEqual(
            _rejection_category(
                "duplicate slug 'alerts/x' (already defined by alerts/x.md)"
            ),
            "duplicate_slug",
        )
        self.assertEqual(
            _rejection_category(
                "unreadable document: 'utf-8' codec can't decode byte 0xff"
            ),
            "unreadable",
        )
        self.assertEqual(
            _rejection_category("path does not produce a slug"), "path"
        )
        self.assertEqual(
            _rejection_category("source directory not found: /srv/skills"),
            "missing_source",
        )

    def test_composition_resolution_rejections_get_their_own_bucket(self) -> None:
        # SPEC-057 R-2: the resolution-layer rejections sync renders are a
        # distinct failure mode from a structural frontmatter error.
        for reason in (
            "composition sub_skill 'samples/x' does not resolve to a "
            "published skill",
            "composition sub_skill 'samples/x' is itself a composition "
            "(no nesting in Phase 1)",
        ):
            with self.subTest(reason=reason):
                self.assertEqual(_rejection_category(reason), "composition")

    def test_structural_composition_rejections_stay_frontmatter(self) -> None:
        # The structural composition rejections ingestion renders never start
        # with "composition", so they stay in the frontmatter bucket beside the
        # other per-field bounds (tasks.md R-2: structural stays frontmatter).
        for reason in (
            "sub_skills requires kind: composition",
            "a composition declares no web_target (kind: composition)",
            "a composition declares no risk_class (kind: composition)",
            "kind: composition requires a non-empty sub_skills list",
            "more than 8 sub_skills",
            "sub_skill 1: unknown sub_skill keys: on_fail",
            "sub_skill 1: duplicate skill_id 'samples/x'",
        ):
            with self.subTest(reason=reason):
                self.assertEqual(
                    _rejection_category(reason), "frontmatter", reason
                )


if __name__ == "__main__":
    unittest.main()
