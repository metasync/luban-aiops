"""Validator CLI tests (SPEC-014 R-2).

The pre-flight command must reuse the service validation path and report
rejections with a non-zero exit code.
"""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from skills_hub.validate import main

VALID_DOC = """---
title: Example Skill
description: A valid example.
---

Body text.
"""

# SPEC-057 R-2: the CLI resolves the configured composition cap and rides the
# same structural layer sync does, so a composition is accepted or rejected at
# the pre-flight exactly as it is at ingestion.
COMPOSITION_DOC = """---
title: Reset And Unlock
description: Reset the password then unlock the user.
kind: composition
sub_skills:
  - skill_id: samples/password-reset-resetacmepassword
    note: Reset the password first.
  - skill_id: samples/lock-unlock-user-lockunlockuser
    note: Then unlock the account.
---

On failure, report which sub-skill failed and stop.
"""


class ValidateCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run_cli(self) -> int:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([str(self.root), "--source-id", "team-a"])
        return code

    def test_clean_directory_passes(self) -> None:
        (self.root / "example.md").write_text(VALID_DOC)
        self.assertEqual(self._run_cli(), 0)

    def test_rejection_fails_with_reason(self) -> None:
        (self.root / "broken.md").write_text("no frontmatter")
        self.assertEqual(self._run_cli(), 1)

    def test_empty_directory_passes(self) -> None:
        self.assertEqual(self._run_cli(), 0)

    def test_valid_composition_passes(self) -> None:
        (self.root / "composition.md").write_text(COMPOSITION_DOC)
        self.assertEqual(self._run_cli(), 0)

    def test_composition_sequencing_key_fails(self) -> None:
        # R-3: a control-flow key on a sub_skills item is an unknown key, so the
        # pre-flight rejects it with the same reason sync would.
        (self.root / "composition.md").write_text(
            COMPOSITION_DOC.replace(
                "    note: Then unlock the account.\n",
                "    note: Then unlock the account.\n    on_fail: rollback\n",
            )
        )
        self.assertEqual(self._run_cli(), 1)

    def test_composition_over_cap_fails(self) -> None:
        # The CLI resolves the configured cap (default 8), so a 9-item list
        # exceeds it and the pre-flight matches sync's rejection.
        items = "".join(
            f"  - skill_id: samples/skill-{index}\n" for index in range(9)
        )
        doc = (
            "---\ntitle: Big Runbook\ndescription: Too many sub-skills.\n"
            "kind: composition\nsub_skills:\n" + items + "---\n\nBody.\n"
        )
        (self.root / "composition.md").write_text(doc)
        self.assertEqual(self._run_cli(), 1)


if __name__ == "__main__":
    unittest.main()
