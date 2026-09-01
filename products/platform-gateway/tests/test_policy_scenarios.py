"""Scenario-harness self-tests (SPEC-048 R-2): the guard must catch drift.

Runs `validate_policy_scenarios.py` as a subprocess under this product's
env — identical canonical bundle exits zero; a deliberately flipped grant
in a fixture bundle exits non-zero.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = REPO_ROOT / "shared" / "shared-contracts"
HARNESS = CONTRACTS_DIR / "scripts" / "validate_policy_scenarios.py"
SHARED_BUNDLE = CONTRACTS_DIR / "policies" / "policy-default.yaml"


def _run_harness(bundle: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HARNESS), "--engine", "api", "--bundle", str(bundle)],
        capture_output=True,
        text=True,
        timeout=120,
    )


class ScenarioHarnessSelfTests(unittest.TestCase):
    def test_canonical_bundle_passes(self) -> None:
        result = _run_harness(SHARED_BUNDLE)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK:", result.stdout)

    def test_flipped_grant_fails(self) -> None:
        # Grant auditor chat: contradicts the named-denial expectation and
        # leaves a granted pair with no scenario — either alone must fail.
        bundle = yaml.safe_load(SHARED_BUNDLE.read_text())
        rule = next(r for r in bundle["rules"] if r["id"] == "allow-operators-chat")
        rule["match"]["roles_any"].append("auditor")
        with tempfile.NamedTemporaryFile(
            "w", suffix=".yaml", delete=False
        ) as fixture:
            yaml.safe_dump(bundle, fixture)
            fixture_path = Path(fixture.name)
        try:
            result = _run_harness(fixture_path)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("FAIL:", result.stdout)
        finally:
            fixture_path.unlink()

    def test_missing_bundle_fails(self) -> None:
        result = _run_harness(CONTRACTS_DIR / "policies" / "does-not-exist.yaml")
        self.assertEqual(result.returncode, 1)
        self.assertIn("bundle not found", result.stderr)
