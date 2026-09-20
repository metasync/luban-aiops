"""SPEC-057 R-4/R-5: a composition carries no authority, and adds no state.

SPEC-057 adds a third skill class, ``composition`` — an ordered ``sub_skills``
reference list that rides skills-hub's read path as grounded guidance. The
load-bearing safety property is that this vocabulary never reaches the
agent-platform trust path: a composition mints no token, unlocks no flow, and
auto-approves no gate (ADR-0011). Each sub-skill keeps its own HITL gate,
enforced by the shipped ``FlowContext.identity() == (skill_id, origin)`` guard
plus ADR-0007 re-park-on-rebind — machinery that predates this spec, is asserted
unchanged in ``test_flow_approvals.py`` / ``test_runtime_kernel.py``, and needs
no new gate here.

These are *purity* assertions, pinned by source scan + dataclass introspection
rather than by review, so a future change that wires ``sub_skills`` into the
trust path fails the suite instead of silently widening authority:

- R-4: ``sub_skills`` is absent from ``runtime_kernel.py``, ``flow_approvals.py``
  and ``execution_signing.py``, and is not a field on ``FlowContext`` /
  ``FlowApproval`` (the two stores the flow-unlock authority keys on).
- R-5: no composition-progress state store is introduced — the completed prefix
  of a stopped runbook stays derivable from the existing ``execution_records``
  signed receipts (swept at ``RETENTION_WINDOW_DAYS``), with no new table beside
  them and no rollback/compensation semantics.
"""

from __future__ import annotations

import dataclasses
import unittest
from pathlib import Path

from agent_service import runtime_kernel
from agent_service.services import execution_signing, flow_approvals
from agent_service.services.execution_records import RETENTION_WINDOW_DAYS

# The trust path a composition must never reach (SPEC-057 R-4). Located by module
# ``__file__`` so the scan follows the installed package, not a hardcoded path.
TRUST_PATH_MODULES = (
    runtime_kernel,
    flow_approvals,
    execution_signing,
)

# The composition vocabulary that must stay out of the trust path. ``sub_skill``
# is a substring of ``sub_skills``; both are asserted so a singular reference
# (``for sub_skill in ...``) is caught as readily as the field name.
COMPOSITION_VOCABULARY = ("sub_skills", "sub_skill", "SubSkillRef")

# A composition-progress store, were one introduced, would carry one of these
# names. R-5 forbids the lot: the completed prefix is derivable from receipts,
# so nothing may aggregate half-state per composition (OQ-3, Non-Goals).
PROGRESS_STORE_VOCABULARY = (
    "composition_progress",
    "composite_progress",
    "runbook_progress",
    "CompositionProgress",
    "RunbookProgress",
    "COMPOSITION_PROGRESS",
)

SERVICES_DIR = Path(flow_approvals.__file__).resolve().parent


def _source(module) -> str:
    return Path(module.__file__).resolve().read_text(encoding="utf-8")


class TrustPathPurityTests(unittest.TestCase):
    """R-4: ``sub_skills`` never reaches the kernel's flow-authority path."""

    def test_composition_vocabulary_is_absent_from_the_trust_path(self) -> None:
        for module in TRUST_PATH_MODULES:
            source = _source(module)
            for token in COMPOSITION_VOCABULARY:
                self.assertNotIn(
                    token,
                    source,
                    f"{token!r} leaked into {module.__name__} — a composition "
                    "carries no authority (SPEC-057 R-4 / ADR-0011)",
                )

    def test_sub_skills_is_not_a_flow_context_field(self) -> None:
        """The reflection of the gateway flow binding keys on ``(skill_id,
        origin)`` only; a composition's reference list is never recorded here,
        so a rebind between sub-skills still overwrites the single identity."""
        names = {f.name for f in dataclasses.fields(flow_approvals.FlowContext)}
        self.assertNotIn("sub_skills", names)
        self.assertIn("skill_id", names)
        self.assertIn("origin", names)

    def test_sub_skills_is_not_a_flow_approval_field(self) -> None:
        """The operator's flow-unlock authority is scoped to one approved
        ``(skill_id, origin)``; it never carries a sub-skill list that could
        pre-approve a segment the operator did not gate."""
        names = {f.name for f in dataclasses.fields(flow_approvals.FlowApproval)}
        self.assertNotIn("sub_skills", names)
        self.assertIn("skill_id", names)
        self.assertIn("origin", names)


class NoNewStateStoreTests(unittest.TestCase):
    """R-5: a stopped composition's progress is derived, never stored."""

    def test_no_composition_progress_store_in_services(self) -> None:
        for path in sorted(SERVICES_DIR.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            for token in PROGRESS_STORE_VOCABULARY:
                self.assertNotIn(
                    token,
                    source,
                    f"{token!r} in {path.name} — SPEC-057 R-5 forbids a "
                    "composition-progress store; the completed prefix derives "
                    "from execution_records receipts",
                )

    def test_reentry_window_is_the_receipt_retention_window(self) -> None:
        """The operator-doc re-entry claim is pinned to the code constant: the
        completed prefix of a stopped runbook is derivable exactly while its
        signed receipts survive (30 days); outside that window the operator
        restarts from the beginning (R-5). No composite-progress store widens
        or persists it."""
        self.assertEqual(RETENTION_WINDOW_DAYS, 30)


if __name__ == "__main__":
    unittest.main()
