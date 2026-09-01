"""policy-diff self-tests for the tools engine (SPEC-048 R-3).

The tool-gateway counterpart of the platform-gateway diff tests. The
asserted transition demonstrates the deliberate engine non-parity:
removing the operator grant from allow-operators-tools-mutate flips
operator x tools:mutate to deny here (require_approval rules are
skipped at load, SPEC-030 R-2).
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = REPO_ROOT / "shared" / "shared-contracts"
DIFF = CONTRACTS_DIR / "scripts" / "policy_diff.py"
SHARED_BUNDLE = CONTRACTS_DIR / "policies" / "policy-default.yaml"


def _run_diff(candidate: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DIFF), "--engine", "tools", "--candidate", str(candidate)],
        capture_output=True,
        text=True,
        timeout=120,
    )


class PolicyDiffTests(unittest.TestCase):
    def test_identical_candidate_reports_no_transitions(self) -> None:
        result = _run_diff(SHARED_BUNDLE)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no outcome transitions", result.stdout)

    def test_removed_grant_detected(self) -> None:
        bundle = yaml.safe_load(SHARED_BUNDLE.read_text())
        rule = next(r for r in bundle["rules"] if r["id"] == "allow-operators-tools-mutate")
        rule["match"]["roles_any"].remove("operator")
        fixture = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
        yaml.safe_dump(bundle, fixture)
        fixture.close()
        candidate = Path(fixture.name)
        try:
            result = _run_diff(candidate)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("operator x tools:mutate: allow -> deny", result.stdout)
        finally:
            candidate.unlink()
