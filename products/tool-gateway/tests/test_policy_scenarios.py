"""Scenario-harness self-tests for the tools engine (SPEC-048 R-2).

The tool-gateway counterpart of the platform-gateway self-tests: the
harness must pass on the identical canonical bundle and fail on a
deliberately flipped grant, under this engine's non-parity semantics
(require_approval rules skipped at load, SPEC-030 R-2).
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
        [sys.executable, str(HARNESS), "--engine", "tools", "--bundle", str(bundle)],
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
        # Grant auditor tools:invoke: contradicts the named-denial
        # expectation and leaves a granted pair with no scenario.
        bundle = yaml.safe_load(SHARED_BUNDLE.read_text())
        rule = next(r for r in bundle["rules"] if r["id"] == "allow-operators-tools")
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
