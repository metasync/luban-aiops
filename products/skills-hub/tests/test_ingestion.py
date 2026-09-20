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
    MAX_STEPS,
    MAX_STEPS_BYTES,
    MAX_SUB_SKILLS,
    ingest_directory,
    slug_from_path,
    validate_document,
)
from skills_hub.services.sync import _rejection_category

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

    def test_risk_class_without_web_target_ingests(self) -> None:
        # SPEC-055 R-3 relaxes the pairing: a non-browser mutating skill
        # (a ``k8s.*`` flow) has no entry URL to declare, so ``risk_class``
        # stands alone. Safe on the consuming side because the gateway's flow
        # binding already fails closed on a missing target
        # (``SKILL_NOT_WEB_FLOW``) — this cannot smuggle in a browser flow.
        # Replaces test_risk_class_without_web_target_rejected.
        _write(
            self.root, "infra/RestartService.md", self._doc("risk_class: write\n")
        )
        result = self._ingest()
        self.assertEqual(result.rejections, [])
        (skill,) = result.records
        self.assertEqual(skill.risk_class, "write")
        self.assertIsNone(skill.web_target)
        self.assertEqual(skill.summary()["risk_class"], "write")

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


# SPEC-055 R-3: an executable-flow replay list as authored in frontmatter.
# Credential values are *references* to a named credential set, never literals
# — the gateway resolves a set from platform configuration at replay time.
FLOW_STEPS_YAML = (
    "steps:\n"
    "  - tool: web.navigate\n"
    '    args: {url: "https://admin.internal/login"}\n'
    "  - tool: web.fill_credential\n"
    "    args: {ref: 1, credential_set: admin-portal, field: password}\n"
    "  - tool: web.click\n"
    '    args: {selector: "#submit"}\n'
    "    expect: the user list renders\n"
)
FLOW_DECLARATION = (
    "kind: executable_flow\n"
    "web_target: https://admin.internal/login\n"
    "risk_class: write\n"
)


class ExecutableFlowTests(unittest.TestCase):
    """SPEC-055 R-3: the ``kind`` / ``steps`` executable-flow class.

    Strictly additive over v1 — a knowledge skill declares neither key and
    validates exactly as before — and enforced on the same
    ``_validate_frontmatter`` path SPEC-044's draft check rides, so a
    malformed flow is rejected identically at sync time and at draft time.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _ingest(self):
        return ingest_directory("team-a", self.root, "local", NOW)

    def _ingest_one(self, extra_frontmatter: str):
        _write(self.root, "flow/Reset.md", self._doc(extra_frontmatter))
        return self._ingest()

    @staticmethod
    def _doc(extra_frontmatter: str) -> str:
        return (
            "---\ntitle: Reset User Password\ndescription: Reset a password.\n"
            f"{extra_frontmatter}---\n\nReplay the reset.\n"
        )

    def test_a_valid_executable_flow_round_trips(self) -> None:
        result = self._ingest_one(FLOW_DECLARATION + FLOW_STEPS_YAML)
        self.assertEqual(result.rejections, [])
        (skill,) = result.records
        self.assertEqual(skill.kind, "executable_flow")
        # Order is the replay contract, so it survives as authored.
        self.assertEqual(
            [step.tool for step in skill.steps],
            ["web.navigate", "web.fill_credential", "web.click"],
        )
        self.assertEqual(
            skill.steps[1].args,
            {"ref": 1, "credential_set": "admin-portal", "field": "password"},
        )
        self.assertEqual(skill.steps[2].expect, "the user list renders")
        summary = skill.summary()
        self.assertEqual(summary["kind"], "executable_flow")
        self.assertEqual(len(summary["steps"]), 3)

    def test_a_non_browser_flow_declares_write_without_a_web_target(self) -> None:
        # The decoupling R-3 exists for: an infra flow has no entry URL to
        # declare and still has to be able to say that it mutates.
        result = self._ingest_one(
            "kind: executable_flow\n"
            "risk_class: write\n"
            "steps:\n"
            "  - tool: k8s.restart_service\n"
            "    args: {namespace: inventory, name: api}\n"
        )
        self.assertEqual(result.rejections, [])
        (skill,) = result.records
        self.assertIsNone(skill.web_target)
        self.assertEqual(skill.steps[0].tool, "k8s.restart_service")

    def test_a_browser_step_without_a_web_target_is_rejected(self) -> None:
        # R-3 decouples ``risk_class`` from ``web_target``, not browser replay
        # from it: the gateway binds the flow — origin guard and step budget
        # included — from the declared target, so a ``web.*`` step with none
        # declares a flow that cannot be bound or bounded.
        result = self._ingest_one(
            "kind: executable_flow\nrisk_class: write\n" + FLOW_STEPS_YAML
        )
        self.assertEqual(len(result.rejections), 1)
        self.assertIn(
            "web.* step requires a web_target", result.rejections[0].reason
        )

    def test_a_flow_that_does_not_declare_write_is_rejected(self) -> None:
        # Unconditional for the class: a step list is a replay of approved
        # mutations (R-2's tier gate keeps read-tier calls out of a trace),
        # and skills-hub holds no per-tool risk vocabulary to check a ``read``
        # claim against. Fail closed on the declaration instead.
        for declared in ("", "risk_class: read\n"):
            with self.subTest(risk_class=declared or "absent"):
                result = self._ingest_one(
                    "kind: executable_flow\n"
                    "web_target: https://admin.internal/login\n"
                    f"{declared}{FLOW_STEPS_YAML}"
                )
                self.assertEqual(len(result.rejections), 1)
                self.assertIn(
                    "requires risk_class: write", result.rejections[0].reason
                )

    def test_a_flow_without_a_step_list_is_rejected(self) -> None:
        for steps_yaml in ("", "steps: []\n", "steps: not-a-list\n"):
            with self.subTest(steps=steps_yaml or "absent"):
                result = self._ingest_one(FLOW_DECLARATION + steps_yaml)
                self.assertEqual(len(result.rejections), 1)
                self.assertIn(
                    "non-empty steps list", result.rejections[0].reason
                )

    def test_steps_without_the_discriminator_are_rejected(self) -> None:
        # The class is declared, never inferred: a step list on an ordinary
        # knowledge document would otherwise make it executable by accident.
        for kind in ("", "kind: knowledge\n"):
            with self.subTest(kind=kind or "absent"):
                result = self._ingest_one(
                    "web_target: https://admin.internal/login\n"
                    "risk_class: write\n"
                    f"{kind}{FLOW_STEPS_YAML}"
                )
                self.assertEqual(len(result.rejections), 1)
                self.assertIn("steps requires kind", result.rejections[0].reason)

    def test_an_unknown_kind_is_rejected(self) -> None:
        result = self._ingest_one("kind: runbook\n")
        self.assertEqual(len(result.rejections), 1)
        self.assertIn("kind must be one of", result.rejections[0].reason)

    def test_malformed_steps_are_rejected(self) -> None:
        cases = {
            "not a mapping": "steps:\n  - web.navigate\n",
            "unknown key": "steps:\n  - tool: web.navigate\n    args: {}\n    retry: 3\n",
            "missing tool": "steps:\n  - args: {}\n",
            "blank tool": 'steps:\n  - tool: "  "\n    args: {}\n',
            "missing args": "steps:\n  - tool: web.navigate\n",
            "args not a mapping": "steps:\n  - tool: web.navigate\n    args: []\n",
            "non-string expect": (
                "steps:\n  - tool: web.navigate\n    args: {}\n    expect: 3\n"
            ),
        }
        for label, steps_yaml in cases.items():
            with self.subTest(case=label):
                result = self._ingest_one(FLOW_DECLARATION + steps_yaml)
                self.assertEqual(len(result.rejections), 1, label)
                self.assertIn("step 1", result.rejections[0].reason)

    def test_an_oversize_tool_or_expect_is_rejected(self) -> None:
        result = self._ingest_one(
            FLOW_DECLARATION + f"steps:\n  - tool: {'t' * 129}\n    args: {{}}\n"
        )
        self.assertEqual(len(result.rejections), 1)
        self.assertIn("tool exceeds 128 chars", result.rejections[0].reason)

        result = self._ingest_one(
            FLOW_DECLARATION
            + "steps:\n  - tool: web.navigate\n    args: {}\n"
            f"    expect: {'e' * 501}\n"
        )
        self.assertEqual(len(result.rejections), 1)
        self.assertIn("expect must be a string", result.rejections[0].reason)

    def test_a_credential_step_must_name_a_set(self) -> None:
        # "Credential references resolve to named credential sets" is
        # structural at this boundary: skills-hub cannot see the gateway's
        # platform-managed store, so what it requires is that the step *names*
        # a set and a field instead of carrying a value.
        for label, args in (
            ("no set", "{ref: 1, field: password}"),
            ("blank set", '{ref: 1, credential_set: "  ", field: password}'),
            ("no field", "{ref: 1, credential_set: admin-portal}"),
        ):
            with self.subTest(case=label):
                result = self._ingest_one(
                    FLOW_DECLARATION
                    + "steps:\n  - tool: web.fill_credential\n"
                    f"    args: {args}\n"
                )
                self.assertEqual(len(result.rejections), 1, label)
                self.assertIn(
                    "web.fill_credential", result.rejections[0].reason
                )

    def test_an_unresolved_credential_hole_is_rejected(self) -> None:
        # R-2 replaces a literal credential with ``<credential-reference>``
        # and R-4 refuses to graduate a trace still carrying one. Ingestion is
        # the third line: a hole names no set, so a document reaching the
        # catalog with one would be an executable flow whose credential can
        # never be resolved at replay.
        for label, args in (
            ("top level", '{selector: "#pw", text: "<credential-reference>"}'),
            ("nested", '{form: {text: "<credential-reference>"}}'),
            # ``args`` values may be lists, so the walker's list branch is a
            # live path and a hole hidden in one must not slip past.
            ("in a list", '{values: ["<credential-reference>"]}'),
        ):
            with self.subTest(case=label):
                result = self._ingest_one(
                    FLOW_DECLARATION
                    + "steps:\n  - tool: web.type\n"
                    f"    args: {args}\n"
                )
                self.assertEqual(len(result.rejections), 1, label)
                self.assertIn(
                    "unresolved credential hole", result.rejections[0].reason
                )

    def test_a_yaml_date_in_args_is_rejected(self) -> None:
        # YAML parses an unquoted date into ``datetime.date``, which no JSON
        # encoder accepts. Without this check the document would ingest and
        # then fail the ``steps`` JSONB write at sync time — turning a
        # reportable rejection into a broken source.
        result = self._ingest_one(
            FLOW_DECLARATION
            + "steps:\n  - tool: web.navigate\n    args: {until: 2026-09-08}\n"
        )
        self.assertEqual(len(result.rejections), 1)
        self.assertIn("JSON-compatible", result.rejections[0].reason)

    def test_an_unbounded_step_list_is_rejected(self) -> None:
        too_many = "".join(
            f"  - tool: web.navigate\n    args: {{n: {index}}}\n"
            for index in range(MAX_STEPS + 1)
        )
        result = self._ingest_one(FLOW_DECLARATION + f"steps:\n{too_many}")
        self.assertEqual(len(result.rejections), 1)
        self.assertIn(f"more than {MAX_STEPS} steps", result.rejections[0].reason)
        # End to end, on the reason ingestion actually rendered rather than a
        # transcription of it: both step ceilings must reach the rejection
        # counter's ``size`` bucket, which is what fails if the wording moves.
        self.assertEqual(_rejection_category(result.rejections[0].reason), "size")

        # The byte ceiling is the other half of the bound: ``steps`` is the
        # first frontmatter key the per-key char caps do not size, and it
        # lands in one JSONB column and rides every list response. The count
        # is a literal rather than a derived one: it only has to be comfortably
        # past the ceiling at ~4 KiB a step, and deriving it from the cap would
        # tie the fixture to the pad width for no gain.
        pad = "p" * 4000
        wide = "".join(
            f'  - tool: web.navigate\n    args: {{pad: "{pad}"}}\n'
            for _ in range(20)
        )
        result = self._ingest_one(FLOW_DECLARATION + f"steps:\n{wide}")
        self.assertEqual(len(result.rejections), 1)
        self.assertIn(
            f"steps exceed {MAX_STEPS_BYTES // 1024} KiB",
            result.rejections[0].reason,
        )
        self.assertEqual(_rejection_category(result.rejections[0].reason), "size")

    def test_a_knowledge_skill_validates_exactly_as_before(self) -> None:
        # No regression: the v1 document ingests unchanged and its envelope
        # carries neither new key (``summary()`` excludes None), so no
        # consumer sees a field it did not ask for.
        _write(self.root, "alerts/KubePodNotReady.md", VALID_DOC)
        result = self._ingest()
        self.assertEqual(result.rejections, [])
        (skill,) = result.records
        self.assertIsNone(skill.kind)
        self.assertIsNone(skill.steps)
        self.assertNotIn("kind", skill.summary())
        self.assertNotIn("steps", skill.summary())
        self.assertEqual(validate_document(VALID_DOC), (True, None))

    def test_validate_document_parity(self) -> None:
        # SPEC-044's draft check shares ``_validate_frontmatter``, so a
        # graduation draft is refused by the same rules — and with the same
        # reason vocabulary — it would be ingested under.
        self.assertEqual(
            validate_document(self._doc(FLOW_DECLARATION + FLOW_STEPS_YAML)),
            (True, None),
        )
        valid, reason = validate_document(
            self._doc(
                "kind: executable_flow\n"
                "web_target: https://admin.internal/login\n"
                f"{FLOW_STEPS_YAML}"  # no risk_class: write
            )
        )
        self.assertFalse(valid)
        self.assertIn("requires risk_class: write", reason or "")


# SPEC-057 R-1: a composition's ordered sub-skill reference list as authored in
# frontmatter. Each item is ``{ skill_id (required), note (optional ≤ 200) }``;
# ``additionalProperties: false`` on the item is what makes R-3 (no control flow)
# true by construction — any sequencing key is an unknown key. The ids are the
# two published single-target skills R-8's demo composes.
COMPOSITION_SUB_SKILLS_YAML = (
    "sub_skills:\n"
    "  - skill_id: samples/password-reset-resetacmepassword\n"
    "    note: Reset the password first.\n"
    "  - skill_id: samples/lock-unlock-user-lockunlockuser\n"
    "    note: Then unlock the account.\n"
)
COMPOSITION_DECLARATION = "kind: composition\n"


class CompositionStructuralTests(unittest.TestCase):
    """SPEC-057 R-1/R-2/R-3: the ``kind: composition`` class's *structural*
    layer — the facts a single document proves alone (reference-list shape, the
    item key set, the count cap, no-duplicate, and "a composition declares no
    web_target/steps/risk_class"). The cross-skill facts (does each sub-skill
    resolve, is it single-target, is it itself a composition) need the catalog
    and are asserted in ``test_sync.py``. Strictly additive over v2 — a knowledge
    or executable_flow skill declares no ``sub_skills`` and validates exactly as
    before — and enforced on the same ``_validate_frontmatter`` path the draft
    check and the ``validate`` CLI ride, so a malformed composition is rejected
    identically at sync, draft, and pre-flight time.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _ingest(self):
        return ingest_directory("team-a", self.root, "local", NOW)

    def _ingest_one(self, extra_frontmatter: str):
        _write(
            self.root,
            "composition/ResetAndUnlock.md",
            self._doc(extra_frontmatter),
        )
        return self._ingest()

    @staticmethod
    def _doc(extra_frontmatter: str) -> str:
        return (
            "---\ntitle: Reset And Unlock\ndescription: Reset then unlock.\n"
            f"{extra_frontmatter}---\n\n"
            "On failure, report which sub-skill failed and stop.\n"
        )

    def test_a_valid_composition_round_trips(self) -> None:
        result = self._ingest_one(
            COMPOSITION_DECLARATION + COMPOSITION_SUB_SKILLS_YAML
        )
        self.assertEqual(result.rejections, [])
        (skill,) = result.records
        self.assertEqual(skill.skill_id, "team-a/composition/resetandunlock")
        self.assertEqual(skill.kind, "composition")
        # Order in the array IS the runbook's declared sequence, so it survives
        # as authored.
        self.assertEqual(
            [ref.skill_id for ref in skill.sub_skills],
            [
                "samples/password-reset-resetacmepassword",
                "samples/lock-unlock-user-lockunlockuser",
            ],
        )
        self.assertEqual(skill.sub_skills[0].note, "Reset the password first.")
        # A composition declares no authorization target, no interpreter input,
        # and no author risk_class (its risk_class is derived at sync, R-1).
        self.assertIsNone(skill.web_target)
        self.assertIsNone(skill.steps)
        self.assertIsNone(skill.risk_class)
        summary = skill.summary()
        self.assertEqual(summary["kind"], "composition")
        self.assertEqual(len(summary["sub_skills"]), 2)

    def test_a_sub_skill_note_is_optional(self) -> None:
        result = self._ingest_one(
            COMPOSITION_DECLARATION
            + "sub_skills:\n"
            "  - skill_id: samples/password-reset-resetacmepassword\n"
        )
        self.assertEqual(result.rejections, [])
        (skill,) = result.records
        self.assertIsNone(skill.sub_skills[0].note)
        # summary() excludes None, so an un-noted item carries just its id.
        self.assertNotIn("note", skill.summary()["sub_skills"][0])

    def test_sub_skills_without_the_discriminator_are_rejected(self) -> None:
        # The class is declared, never inferred (the ``steps`` rule's twin): a
        # reference list on an ordinary knowledge document is malformed rather
        # than an implicit composition.
        for kind in ("", "kind: knowledge\n"):
            with self.subTest(kind=kind or "absent"):
                result = self._ingest_one(kind + COMPOSITION_SUB_SKILLS_YAML)
                self.assertEqual(len(result.rejections), 1)
                self.assertIn(
                    "sub_skills requires kind: composition",
                    result.rejections[0].reason,
                )

    def test_a_composition_without_sub_skills_is_rejected(self) -> None:
        for sub_skills_yaml in (
            "",
            "sub_skills: []\n",
            "sub_skills: not-a-list\n",
        ):
            with self.subTest(sub_skills=sub_skills_yaml or "absent"):
                result = self._ingest_one(
                    COMPOSITION_DECLARATION + sub_skills_yaml
                )
                self.assertEqual(len(result.rejections), 1)
                self.assertIn(
                    "non-empty sub_skills list", result.rejections[0].reason
                )

    def test_a_composition_declaring_its_own_web_target_is_rejected(self) -> None:
        # Its scope is the union of its sub-skills' scopes; declaring one would
        # falsely imply a single authorization target SPEC-055 R-4 could not
        # re-validate.
        result = self._ingest_one(
            COMPOSITION_DECLARATION
            + "web_target: https://admin.internal/login\n"
            + COMPOSITION_SUB_SKILLS_YAML
        )
        self.assertEqual(len(result.rejections), 1)
        self.assertIn(
            "a composition declares no web_target", result.rejections[0].reason
        )

    def test_a_composition_declaring_its_own_risk_class_is_rejected(self) -> None:
        # The display risk_class is derived at sync, never author-declared.
        result = self._ingest_one(
            COMPOSITION_DECLARATION
            + "risk_class: write\n"
            + COMPOSITION_SUB_SKILLS_YAML
        )
        self.assertEqual(len(result.rejections), 1)
        self.assertIn(
            "a composition declares no risk_class", result.rejections[0].reason
        )

    def test_a_composition_declaring_its_own_steps_is_rejected(self) -> None:
        # ``_validate_steps`` runs first and rejects a step list on any kind but
        # ``executable_flow``, so a composition carrying ``steps`` fails there;
        # ``_validate_composition``'s own no-steps rule is the defensive twin.
        # Either way the document is rejected — never silently degraded.
        result = self._ingest_one(
            COMPOSITION_DECLARATION
            + "steps:\n  - tool: web.navigate\n    args: {}\n"
            + COMPOSITION_SUB_SKILLS_YAML
        )
        self.assertEqual(len(result.rejections), 1)
        self.assertIn("steps requires kind", result.rejections[0].reason)

    def test_a_duplicate_sub_skill_id_is_rejected(self) -> None:
        result = self._ingest_one(
            COMPOSITION_DECLARATION
            + "sub_skills:\n"
            "  - skill_id: samples/password-reset-resetacmepassword\n"
            "  - skill_id: samples/password-reset-resetacmepassword\n"
        )
        self.assertEqual(len(result.rejections), 1)
        self.assertIn("duplicate skill_id", result.rejections[0].reason)

    def test_an_over_cap_sub_skill_list_is_rejected(self) -> None:
        too_many = "".join(
            f"  - skill_id: samples/skill-{index}\n"
            for index in range(MAX_SUB_SKILLS + 1)
        )
        result = self._ingest_one(
            COMPOSITION_DECLARATION + f"sub_skills:\n{too_many}"
        )
        self.assertEqual(len(result.rejections), 1)
        self.assertIn(
            f"more than {MAX_SUB_SKILLS} sub_skills", result.rejections[0].reason
        )

    def test_the_configured_cap_is_threaded_through_ingestion(self) -> None:
        # The operator knob (SKILLS_COMPOSITION_MAX_SUB_SKILLS) is threaded
        # through ingest_directory, so a cap of 2 rejects a 3-item list the
        # default cap of 8 accepts — the pre-flight matches sync (R-2).
        three = "".join(
            f"  - skill_id: samples/skill-{index}\n" for index in range(3)
        )
        _write(
            self.root,
            "composition/ResetAndUnlock.md",
            self._doc(COMPOSITION_DECLARATION + f"sub_skills:\n{three}"),
        )
        self.assertEqual(
            ingest_directory("team-a", self.root, "local", NOW, 8).rejections, []
        )
        result = ingest_directory("team-a", self.root, "local", NOW, 2)
        self.assertEqual(len(result.rejections), 1)
        self.assertIn("more than 2 sub_skills", result.rejections[0].reason)

    def test_a_malformed_sub_skill_item_is_rejected(self) -> None:
        cases = {
            "not a mapping": (
                "sub_skills:\n  - samples/password-reset-resetacmepassword\n"
            ),
            "missing skill_id": "sub_skills:\n  - note: no id here\n",
            "bad skill_id pattern": "sub_skills:\n  - skill_id: NotNamespaced\n",
            "single-segment skill_id": "sub_skills:\n  - skill_id: nosource\n",
        }
        for label, sub_skills_yaml in cases.items():
            with self.subTest(case=label):
                result = self._ingest_one(
                    COMPOSITION_DECLARATION + sub_skills_yaml
                )
                self.assertEqual(len(result.rejections), 1, label)
                self.assertIn("sub_skill 1", result.rejections[0].reason)

    def test_an_oversize_sub_skill_note_is_rejected(self) -> None:
        result = self._ingest_one(
            COMPOSITION_DECLARATION
            + "sub_skills:\n"
            "  - skill_id: samples/password-reset-resetacmepassword\n"
            f"    note: {'n' * 201}\n"
        )
        self.assertEqual(len(result.rejections), 1)
        self.assertIn("note must be a string", result.rejections[0].reason)

    def test_a_sequencing_key_on_an_item_is_rejected(self) -> None:
        # R-3: there is no control-flow vocabulary. ``additionalProperties:
        # false`` on the item forbids every key but skill_id/note, so a
        # sequencing construct cannot be written and cannot be smuggled in via a
        # note (a note is a string, never interpreted).
        for key in ("if", "loop", "retry", "on_fail"):
            with self.subTest(key=key):
                result = self._ingest_one(
                    COMPOSITION_DECLARATION
                    + "sub_skills:\n"
                    "  - skill_id: samples/password-reset-resetacmepassword\n"
                    f"    {key}: something\n"
                )
                self.assertEqual(len(result.rejections), 1)
                self.assertIn(
                    "unknown sub_skill keys", result.rejections[0].reason
                )

    def test_existing_classes_validate_exactly_as_before(self) -> None:
        # No regression: neither shipped class declares sub_skills, and both
        # ingest unchanged — the composition kind is added, the two that shipped
        # are untouched (R-1 additivity).
        _write(self.root, "alerts/KubePodNotReady.md", VALID_DOC)
        _write(
            self.root,
            "flow/Reset.md",
            "---\ntitle: Reset User Password\n"
            "description: Reset a password.\n"
            + FLOW_DECLARATION
            + FLOW_STEPS_YAML
            + "---\n\nReplay the reset.\n",
        )
        result = self._ingest()
        self.assertEqual(result.rejections, [])
        by_id = {skill.skill_id: skill for skill in result.records}
        knowledge = by_id["team-a/alerts/kubepodnotready"]
        self.assertIsNone(knowledge.sub_skills)
        self.assertNotIn("sub_skills", knowledge.summary())
        flow = by_id["team-a/flow/reset"]
        self.assertEqual(flow.kind, "executable_flow")
        self.assertIsNone(flow.sub_skills)
        self.assertNotIn("sub_skills", flow.summary())

    def test_validate_document_parity(self) -> None:
        # The draft check shares ``_validate_frontmatter``, so a composition
        # draft is refused by the same structural rules — and the same reason
        # vocabulary — it would be ingested under.
        self.assertEqual(
            validate_document(
                self._doc(COMPOSITION_DECLARATION + COMPOSITION_SUB_SKILLS_YAML)
            ),
            (True, None),
        )
        valid, reason = validate_document(
            self._doc(
                COMPOSITION_DECLARATION
                + "sub_skills:\n"
                "  - skill_id: samples/password-reset-resetacmepassword\n"
                "  - skill_id: samples/password-reset-resetacmepassword\n"
            )
        )
        self.assertFalse(valid)
        self.assertIn("duplicate skill_id", reason or "")


if __name__ == "__main__":
    unittest.main()
