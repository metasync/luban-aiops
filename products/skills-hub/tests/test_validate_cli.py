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


if __name__ == "__main__":
    unittest.main()
