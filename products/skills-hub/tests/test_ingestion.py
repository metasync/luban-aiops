"""Ingestion validation matrix (SPEC-014 R-1/R-2).

Each validation rule has a dedicated failure case; valid documents must
round-trip into envelopes with path-derived slugs.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from skills_hub.services.ingestion import (
    ingest_directory,
    slug_from_path,
    validate_document,
)

NOW = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)

VALID_DOC = """---
title: KubePodNotReady
description: Pod not ready triage steps.
tags: [kubernetes, KubePodNotReady]
version: "1.0"
source_url: https://example.com/upstream
---

Check the pod events first.
"""


def _write(root: Path, rel_path: str, content: str) -> None:
    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


class SlugTests(unittest.TestCase):
    def test_simple_path(self) -> None:
        self.assertEqual(slug_from_path("KubePodNotReady.md"), "kubepodnotready")

    def test_nested_path(self) -> None:
        self.assertEqual(
            slug_from_path("alerts/KubePodNotReady.md"), "alerts/kubepodnotready"
        )

    def test_runs_of_special_characters_collapse(self) -> None:
        self.assertEqual(slug_from_path("My_Doc (v2).md"), "my-doc-v2")

    def test_empty_segment_yields_none(self) -> None:
        self.assertIsNone(slug_from_path("__.md"))


class IngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _ingest(self):
        return ingest_directory("team-a", self.root, "local", NOW)

    def test_valid_document_round_trips(self) -> None:
        _write(self.root, "alerts/KubePodNotReady.md", VALID_DOC)
        result = self._ingest()
        self.assertEqual(result.rejections, [])
        (skill,) = result.records
        self.assertEqual(skill.skill_id, "team-a/alerts/kubepodnotready")
        self.assertEqual(skill.source_path, "alerts/KubePodNotReady.md")
        self.assertEqual(skill.source_ref, "local")
        self.assertEqual(skill.tags, ["kubernetes", "KubePodNotReady"])
        self.assertEqual(skill.source_url, "https://example.com/upstream")
        self.assertIn("Check the pod events", skill.body)

    def test_kubernetes_configmap_artifacts_skipped(self) -> None:
        # ConfigMap volumes keep canonical content in a timestamped directory
        # exposed via a ..data symlink, with a symlink farm at the top level.
        timestamped = "..2026_08_15_05_59_34.171108893"
        _write(self.root, f"{timestamped}/alerts/KubePodNotReady.md", VALID_DOC)
        (self.root / "..data").symlink_to(self.root / timestamped)
        (self.root / "alerts").symlink_to(self.root / "..data" / "alerts")
        result = self._ingest()
        self.assertEqual(result.rejections, [])
        (skill,) = result.records
        self.assertEqual(skill.skill_id, "team-a/alerts/kubepodnotready")
        self.assertEqual(skill.source_path, "alerts/KubePodNotReady.md")

    def test_missing_frontmatter_rejected(self) -> None:
        _write(self.root, "bare.md", "no frontmatter here")
        result = self._ingest()
        self.assertEqual(len(result.rejections), 1)
        self.assertIn("frontmatter", result.rejections[0].reason)

    def test_missing_title_rejected(self) -> None:
        _write(
            self.root,
            "a.md",
            "---\ndescription: only a description\n---\nbody\n",
        )
        result = self._ingest()
        self.assertIn("'title' is required", result.rejections[0].reason)

    def test_missing_description_rejected(self) -> None:
        _write(self.root, "a.md", "---\ntitle: Only Title\n---\nbody\n")
        result = self._ingest()
        self.assertIn("'description' is required", result.rejections[0].reason)

    def test_oversize_description_rejected(self) -> None:
        _write(
            self.root,
            "a.md",
            f"---\ntitle: T\ndescription: {'x' * 501}\n---\nbody\n",
        )
        result = self._ingest()
        self.assertIn("description exceeds", result.rejections[0].reason)

    def test_too_many_tags_rejected(self) -> None:
        tags = ", ".join(f"t{i}" for i in range(11))
        _write(
            self.root,
            "a.md",
            f"---\ntitle: T\ndescription: D\ntags: [{tags}]\n---\nbody\n",
        )
        result = self._ingest()
        self.assertIn("more than 10 tags", result.rejections[0].reason)

    def test_unknown_frontmatter_key_rejected(self) -> None:
        _write(
            self.root,
            "a.md",
            "---\ntitle: T\ndescription: D\nauthor: alice\n---\nbody\n",
        )
        result = self._ingest()
        self.assertIn("unknown frontmatter keys", result.rejections[0].reason)

    def test_non_mapping_frontmatter_rejected(self) -> None:
        _write(self.root, "a.md", "---\n- just\n- a list\n---\nbody\n")
        result = self._ingest()
        self.assertIn("mapping", result.rejections[0].reason)

    def test_oversize_body_rejected(self) -> None:
        _write(
            self.root,
            "a.md",
            f"---\ntitle: T\ndescription: D\n---\n{'x' * 70000}\n",
        )
        result = self._ingest()
        self.assertIn("body exceeds", result.rejections[0].reason)

    def test_duplicate_slug_within_source_rejected(self) -> None:
        # Both paths sanitize to the same slug (runbooks/my-doc).
        _write(self.root, "runbooks/My_Doc.md", VALID_DOC)
        _write(self.root, "runbooks/My-Doc.md", VALID_DOC)
        result = self._ingest()
        self.assertEqual(len(result.records), 1)
        self.assertEqual(len(result.rejections), 1)
        self.assertIn("duplicate slug", result.rejections[0].reason)

    def test_readme_is_skipped(self) -> None:
        _write(self.root, "README.md", "# not a skill")
        _write(self.root, "a.md", VALID_DOC)
        result = self._ingest()
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.rejections, [])

    def test_missing_directory_reported(self) -> None:
        result = ingest_directory(
            "team-a", self.root / "does-not-exist", "local", NOW
        )
        self.assertEqual(len(result.rejections), 1)
        self.assertIn("not found", result.rejections[0].reason)

    def test_partial_acceptance(self) -> None:
        _write(self.root, "good.md", VALID_DOC)
        _write(self.root, "bad.md", "no frontmatter")
        result = self._ingest()
        self.assertEqual(len(result.records), 1)
        self.assertEqual(len(result.rejections), 1)


class WebFlowDeclarationTests(unittest.TestCase):
    """SPEC-049 R-3: optional web_target / risk_class frontmatter keys."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _ingest(self):
        return ingest_directory("team-a", self.root, "local", NOW)

    @staticmethod
    def _doc(extra_frontmatter: str) -> str:
        return (
            "---\ntitle: Inventory Health Check\ndescription: Verify the "
            "inventory app status page.\n"
            f"{extra_frontmatter}---\n\nLog in and open the status page.\n"
        )

    def test_valid_declaration_round_trips(self) -> None:
        _write(
            self.root,
            "web/InventoryHealth.md",
            self._doc(
                "web_target: https://inventory.internal:8443/login\n"
                "risk_class: write\n"
            ),
        )
        result = self._ingest()
        self.assertEqual(result.rejections, [])
        (skill,) = result.records
        self.assertEqual(skill.web_target, "https://inventory.internal:8443/login")
        self.assertEqual(skill.risk_class, "write")
        # The declaration rides beside the existing frontmatter fields.
        summary = skill.summary()
        self.assertEqual(summary["web_target"], "https://inventory.internal:8443/login")
        self.assertEqual(summary["risk_class"], "write")

    def test_web_target_without_risk_class_defaults_read_semantics(self) -> None:
        # The envelope stores the declaration verbatim (risk_class absent);
        # consumers treat a web_target without risk_class as read-class.
        _write(
            self.root,
            "web/StatusCheck.md",
            self._doc("web_target: https://status.internal/health\n"),
        )
        result = self._ingest()
        self.assertEqual(result.rejections, [])
        (skill,) = result.records
        self.assertEqual(skill.web_target, "https://status.internal/health")
        self.assertIsNone(skill.risk_class)
        self.assertNotIn("risk_class", skill.summary())

    def test_invalid_risk_class_rejected(self) -> None:
        _write(
            self.root,
            "web/Bad.md",
            self._doc(
                "web_target: https://inventory.internal/login\n"
                "risk_class: destroy\n"
            ),
        )
        result = self._ingest()
        self.assertEqual(len(result.rejections), 1)
        self.assertIn("risk_class must be one of", result.rejections[0].reason)

    def test_risk_class_without_web_target_rejected(self) -> None:
        _write(self.root, "web/Bad.md", self._doc("risk_class: write\n"))
        result = self._ingest()
        self.assertEqual(len(result.rejections), 1)
        self.assertIn("risk_class requires a web_target", result.rejections[0].reason)

    def test_malformed_web_target_rejected(self) -> None:
        for bad_target in (
            "not a url",
            "ftp://inventory.internal/login",
            "https://",
        ):
            with self.subTest(target=bad_target):
                _write(
                    self.root,
                    "web/Bad.md",
                    self._doc(f"web_target: \"{bad_target}\"\n"),
                )
                result = self._ingest()
                self.assertEqual(len(result.rejections), 1)
                self.assertIn("web_target", result.rejections[0].reason)

    def test_oversize_web_target_rejected(self) -> None:
        long_path = "x" * 2048
        _write(
            self.root,
            "web/Bad.md",
            self._doc(f"web_target: https://inventory.internal/{long_path}\n"),
        )
        result = self._ingest()
        self.assertEqual(len(result.rejections), 1)
        self.assertIn("≤ 2048 chars", result.rejections[0].reason)

    def test_documents_without_declaration_ingest_unchanged(self) -> None:
        _write(self.root, "alerts/KubePodNotReady.md", VALID_DOC)
        result = self._ingest()
        self.assertEqual(result.rejections, [])
        (skill,) = result.records
        self.assertIsNone(skill.web_target)
        self.assertIsNone(skill.risk_class)


class FlowIntentDeclarationTests(unittest.TestCase):
    """SPEC-053 R-1: optional flow_intent frontmatter key — a card-level,
    display-only intent line that requires web_target and is ≤ 200 chars."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _ingest(self):
        return ingest_directory("team-a", self.root, "local", NOW)

    @staticmethod
    def _doc(extra_frontmatter: str) -> str:
        return (
            "---\ntitle: Reset User Password\ndescription: Reset a password.\n"
            f"{extra_frontmatter}---\n\nConfirm the reset.\n"
        )

    def test_valid_flow_intent_round_trips(self) -> None:
        _write(
            self.root,
            "web/ResetPassword.md",
            self._doc(
                "web_target: https://admin.internal/login\n"
                "risk_class: write\n"
                "flow_intent: Submit the password reset for the user.\n"
            ),
        )
        result = self._ingest()
        self.assertEqual(result.rejections, [])
        (skill,) = result.records
        self.assertEqual(
            skill.flow_intent, "Submit the password reset for the user."
        )
        # The intent rides beside the other flow-declaration fields, and
        # summary() (the list/search shape, body omitted) carries it.
        summary = skill.summary()
        self.assertEqual(
            summary["flow_intent"], "Submit the password reset for the user."
        )

    def test_flow_intent_allowed_without_write_risk_class(self) -> None:
        # flow_intent requires web_target but not risk_class: write — a
        # read-declared flow may still author an intent line.
        _write(
            self.root,
            "web/StatusCheck.md",
            self._doc(
                "web_target: https://status.internal/health\n"
                "flow_intent: Refresh the health dashboard for the region.\n"
            ),
        )
        result = self._ingest()
        self.assertEqual(result.rejections, [])
        (skill,) = result.records
        self.assertEqual(
            skill.flow_intent, "Refresh the health dashboard for the region."
        )
        self.assertIsNone(skill.risk_class)

    def test_flow_intent_without_web_target_rejected(self) -> None:
        _write(
            self.root,
            "web/Bad.md",
            self._doc("flow_intent: Do the mutating thing.\n"),
        )
        result = self._ingest()
        self.assertEqual(len(result.rejections), 1)
        self.assertIn(
            "flow_intent requires a web_target", result.rejections[0].reason
        )

    def test_oversize_flow_intent_rejected(self) -> None:
        long_intent = "x" * 201
        _write(
            self.root,
            "web/Bad.md",
            self._doc(
                "web_target: https://admin.internal/login\n"
                f"flow_intent: {long_intent}\n"
            ),
        )
        result = self._ingest()
        self.assertEqual(len(result.rejections), 1)
        self.assertIn("≤ 200 chars", result.rejections[0].reason)

    def test_non_string_flow_intent_rejected(self) -> None:
        for bad in ("[a, b]", "123"):
            with self.subTest(value=bad):
                _write(
                    self.root,
                    "web/Bad.md",
                    self._doc(
                        "web_target: https://admin.internal/login\n"
                        f"flow_intent: {bad}\n"
                    ),
                )
                result = self._ingest()
                self.assertEqual(len(result.rejections), 1)
                self.assertIn(
                    "flow_intent must be a non-empty string",
                    result.rejections[0].reason,
                )

    def test_blank_flow_intent_rejected(self) -> None:
        _write(
            self.root,
            "web/Bad.md",
            self._doc(
                "web_target: https://admin.internal/login\n"
                'flow_intent: "   "\n'
            ),
        )
        result = self._ingest()
        self.assertEqual(len(result.rejections), 1)
        self.assertIn(
            "flow_intent must be a non-empty string",
            result.rejections[0].reason,
        )

    def test_documents_without_flow_intent_ingest_unchanged(self) -> None:
        _write(
            self.root,
            "web/NoIntent.md",
            self._doc("web_target: https://admin.internal/login\n"),
        )
        result = self._ingest()
        self.assertEqual(result.rejections, [])
        (skill,) = result.records
        self.assertIsNone(skill.flow_intent)
        self.assertNotIn("flow_intent", skill.summary())

    def test_validate_document_parity(self) -> None:
        # validate_document shares _validate_frontmatter (SPEC-044 R-2), so it
        # accepts a valid flow_intent and rejects a bad one with the same
        # reason vocabulary the ingestion report uses.
        good = self._doc(
            "web_target: https://admin.internal/login\n"
            "flow_intent: Submit the reset.\n"
        )
        self.assertEqual(validate_document(good), (True, None))
        bad = self._doc("flow_intent: Submit the reset.\n")  # no web_target
        valid, reason = validate_document(bad)
        self.assertFalse(valid)
        self.assertIn("flow_intent requires a web_target", reason or "")


if __name__ == "__main__":
    unittest.main()
