"""policy-diff self-tests (SPEC-048 R-3): transition detection and error paths.

Runs `policy_diff.py` as a subprocess under this product's env. Fixture
bundles are derived from the canonical bundle with a single deliberate
mutation each, so every asserted transition is exact engine semantics,
never a re-implementation.
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


def _run_diff(candidate: Path, canonical: Path | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(DIFF), "--engine", "api", "--candidate", str(candidate)]
    if canonical is not None:
        cmd += ["--canonical", str(canonical)]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def _mutate_bundle(mutator) -> Path:
    bundle = yaml.safe_load(SHARED_BUNDLE.read_text())
    mutator(bundle)
    fixture = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    yaml.safe_dump(bundle, fixture)
    fixture.close()
    return Path(fixture.name)


class PolicyDiffTests(unittest.TestCase):
    def test_identical_candidate_reports_no_transitions(self) -> None:
        result = _run_diff(SHARED_BUNDLE)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no outcome transitions", result.stdout)

    def test_new_grant_detected(self) -> None:
        def mutate(bundle):
            rule = next(r for r in bundle["rules"] if r["id"] == "allow-auditors-audit-read")
            rule["match"]["actions_any"].append("chat")

        candidate = _mutate_bundle(mutate)
        try:
            result = _run_diff(candidate)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("auditor x chat: deny -> allow", result.stdout)
        finally:
            candidate.unlink()

    def test_removed_grant_detected(self) -> None:
        def mutate(bundle):
            rule = next(r for r in bundle["rules"] if r["id"] == "allow-operators-chat")
            rule["match"]["roles_any"].remove("developer")

        candidate = _mutate_bundle(mutate)
        try:
            result = _run_diff(candidate)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("developer x chat: allow -> deny", result.stdout)
        finally:
            candidate.unlink()

    def test_approval_tier_change_detected(self) -> None:
        def mutate(bundle):
            rule = next(
                r for r in bundle["rules"] if r["id"] == "require-approval-tools-mutate"
            )
            rule["decision"]["approval"]["tier"] = "tier_1"

        candidate = _mutate_bundle(mutate)
        try:
            result = _run_diff(candidate)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("require_approval (tier_2) -> require_approval (tier_1)",
                          result.stdout)
        finally:
            candidate.unlink()

    def test_missing_candidate_is_hard_error(self) -> None:
        result = _run_diff(CONTRACTS_DIR / "policies" / "does-not-exist.yaml")
        self.assertEqual(result.returncode, 1)
        self.assertIn("candidate bundle not found", result.stderr)

    def test_malformed_candidate_is_hard_error(self) -> None:
        fixture = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
        fixture.write("rules: [not valid yaml")
        fixture.close()
        candidate = Path(fixture.name)
        try:
            result = _run_diff(candidate)
            self.assertEqual(result.returncode, 1)
            self.assertIn("error", result.stderr)
        finally:
            candidate.unlink()
