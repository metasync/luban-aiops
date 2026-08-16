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
from skills_hub.services.skill_store import InMemorySkillStore
from skills_hub.services.sync import SyncManager, _with_token

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

    def test_status_report_orders_sources_and_bounds_fields(self) -> None:
        spec_a = SourceSpec(source_id="b-src", type="local", path=str(self.root))
        spec_b = SourceSpec(source_id="a-src", type="local", path=str(self.root))
        manager = SyncManager(_settings(spec_a, spec_b), self.store)
        _run(manager.sync_once(spec_a))
        report = manager.status_report()
        self.assertEqual([s["source_id"] for s in report], ["a-src", "b-src"])
        self.assertEqual(report[1]["accepted"], 1)
        self.assertEqual(report[0]["last_sync_at"], None)


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


if __name__ == "__main__":
    unittest.main()
