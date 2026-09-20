"""SPEC-057 R-4/R-6: the gateway deviation guard never reads ``sub_skills``.

A composition is an ordered ``sub_skills`` reference list that carries no
authority (ADR-0011). Two gateway invariants follow, pinned here by source scan
so a future change that teaches the gateway to interpret a composition fails the
suite rather than silently widening the bound-flow contract:

- R-4: the browser deviation guard (``browser_connector.py``) and the flow-binding
  state machine (``browser_sessions.py``) never read ``sub_skills``. A bound flow
  is still identified by exactly ``(skill_id, origin)`` and bounded by the origin
  allowlist, ``risk_class`` and the step budget — byte-for-byte the shipped
  behavior the rest of ``test_browser_connector.py`` asserts. A composition adds
  no gateway-side gate and no pre-binding of a sub-skill.
- R-6: the skills connectors pass a record through verbatim
  (``ToolResult(data=response.json())``), so the resolved ``sub_skills`` view
  skills-hub projects on ``get_skill`` reaches the model over the existing
  SPEC-014 grounded-guidance path without the gateway parsing or re-rendering it.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from tool_gateway.tools import browser_connector, browser_sessions, skills_connector

# The composition vocabulary that must stay out of the gateway. ``sub_skill`` is
# a substring of ``sub_skills``; both are asserted so a singular loop variable is
# caught as readily as the field name.
COMPOSITION_VOCABULARY = ("sub_skills", "sub_skill", "SubSkillRef")

# The deviation guard + flow-binding state machine (R-4): these gate a bound
# browser flow and must never consult a composition's reference list.
GUARD_MODULES = (browser_connector, browser_sessions)


def _source(module) -> str:
    return Path(module.__file__).resolve().read_text(encoding="utf-8")


class DeviationGuardPurityTests(unittest.TestCase):
    """R-4: the bound-flow deviation guard is composition-agnostic."""

    def test_guard_never_reads_sub_skills(self) -> None:
        for module in GUARD_MODULES:
            source = _source(module)
            for token in COMPOSITION_VOCABULARY:
                self.assertNotIn(
                    token,
                    source,
                    f"{token!r} leaked into {module.__name__} — the deviation "
                    "guard must gate a flow by (skill_id, origin), never by a "
                    "composition's sub-skill list (SPEC-057 R-4 / ADR-0011)",
                )

    def test_skills_connector_passes_records_through_verbatim(self) -> None:
        """R-6: the connector returns ``response.json()`` and never parses
        ``sub_skills``, so skills-hub's projected view is not re-rendered or
        dropped at the gateway boundary."""
        source = _source(skills_connector)
        for token in COMPOSITION_VOCABULARY:
            self.assertNotIn(
                token,
                source,
                f"{token!r} in {skills_connector.__name__} — the skills "
                "connectors are pure passthrough (SPEC-057 R-6)",
            )
        self.assertIn("data=response.json()", source)


if __name__ == "__main__":
    unittest.main()
