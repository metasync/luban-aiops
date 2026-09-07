"""Self-tests for the SPEC-054 Stage 6 redaction-vocabulary lockstep leg.

``shared/shared-contracts/scripts/validate_secret_vocabulary.py`` textually
compares the agent-platform ``SECRET_PARAM_SUBSTRINGS`` tuple against its
tool-gateway twin ``_SECRET_QUERY_PARAMS`` and fails the ``make verify`` build
on any drift (the two copies live in products that never import each other, so
the comparison is by source extraction, not import).

These tests run the script as a subprocess against (a) the real repo, which
must agree, and (b) synthetic trees that agree and diverge, proving the leg
passes on lockstep and fails — in both directions — on divergence.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    REPO_ROOT
    / "shared"
    / "shared-contracts"
    / "scripts"
    / "validate_secret_vocabulary.py"
)

AGENT_REL = Path("products/agent-platform/src/agent_service/services/secret_params.py")
GATEWAY_REL = Path("products/tool-gateway/src/tool_gateway/tools/browser_connector.py")


def _run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(root)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _write_tree(
    root: Path, agent_entries: tuple[str, ...], gateway_entries: tuple[str, ...]
) -> None:
    """Materialize a minimal repo tree carrying the two vocabulary tuples."""

    def _module(var: str, entries: tuple[str, ...]) -> str:
        body = ", ".join(f'"{e}"' for e in entries)
        return f"{var}: tuple[str, ...] = (\n    {body},\n)\n"

    agent_path = root / AGENT_REL
    gateway_path = root / GATEWAY_REL
    agent_path.parent.mkdir(parents=True, exist_ok=True)
    gateway_path.parent.mkdir(parents=True, exist_ok=True)
    agent_path.write_text(
        _module("SECRET_PARAM_SUBSTRINGS", agent_entries), encoding="utf-8"
    )
    gateway_path.write_text(
        _module("_SECRET_QUERY_PARAMS", gateway_entries), encoding="utf-8"
    )


def test_real_repo_vocabularies_agree() -> None:
    """The two shipped copies are in lockstep, so the leg passes on the repo."""
    result = _run(REPO_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("OK:")


def test_synthetic_tree_agrees(tmp_path: Path) -> None:
    """Identical tuples (order-insensitive) pass and report the shared count."""
    entries = ("password", "token", "secret")
    _write_tree(tmp_path, entries, entries)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "agree (3 substrings)" in result.stdout


def test_divergent_tree_fails_both_directions(tmp_path: Path) -> None:
    """Each side holding a substring the other lacks fails and names both."""
    _write_tree(
        tmp_path,
        ("password", "token", "secret"),  # agent-platform carries 'secret'
        ("password", "token", "signature"),  # tool-gateway carries 'signature'
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    assert result.stdout.startswith("FAIL:")
    assert "agent-platform only" in result.stdout
    assert "'secret'" in result.stdout
    assert "tool-gateway only" in result.stdout
    assert "'signature'" in result.stdout


def test_missing_source_file_fails(tmp_path: Path) -> None:
    """An absent twin is a hard failure, not a silent pass (fail-closed)."""
    agent_path = tmp_path / AGENT_REL
    agent_path.parent.mkdir(parents=True, exist_ok=True)
    agent_path.write_text(
        'SECRET_PARAM_SUBSTRINGS: tuple[str, ...] = (\n    "password",\n)\n',
        encoding="utf-8",
    )
    # The tool-gateway twin is deliberately absent.
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "missing file" in result.stdout
