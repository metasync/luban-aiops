"""Self-tests for the cross-product secret-literal lockstep leg.

``shared/shared-contracts/scripts/validate_secret_vocabulary.py`` textually
compares two pairs of deliberate second copies, each pair spanning products
that never import each other, so the comparison is by source extraction:

1. the agent-platform ``SECRET_PARAM_SUBSTRINGS`` tuple against its
   tool-gateway twin ``_SECRET_QUERY_PARAMS`` (SPEC-054 R-3 / SPEC-049 R-5);
2. the agent-platform ``TRACE_CREDENTIAL_PLACEHOLDER`` marker against its
   skills-hub twin ``CREDENTIAL_HOLE`` (SPEC-055 R-2 writes it, R-3 refuses it).

Any drift fails the ``make verify`` build.

These tests run the script as a subprocess against (a) the real repo, which
must agree, and (b) synthetic trees that agree and diverge, proving the leg
passes on lockstep and fails — in both directions, for both couplings — on
divergence.
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
SKILLS_HUB_REL = Path("products/skills-hub/src/skills_hub/services/ingestion.py")

# The shipped marker, used as the synthetic default so the vocabulary tests
# exercise one coupling at a time.
HOLE = "<credential-reference>"


def _run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(root)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _write_tree(
    root: Path,
    agent_entries: tuple[str, ...],
    gateway_entries: tuple[str, ...],
    *,
    agent_hole: str | None = HOLE,
    hub_hole: str | None = HOLE,
) -> None:
    """Materialize a minimal repo tree carrying both twin pairs.

    A hole marker passed as ``None`` writes the file *without* the literal, so
    the "literal not found" path is exercised distinctly from the "missing
    file" path (``test_missing_source_file_fails`` covers that one).
    """

    def _module(var: str, entries: tuple[str, ...]) -> str:
        body = ", ".join(f'"{e}"' for e in entries)
        return f"{var}: tuple[str, ...] = (\n    {body},\n)\n"

    agent_path = root / AGENT_REL
    gateway_path = root / GATEWAY_REL
    hub_path = root / SKILLS_HUB_REL
    agent_path.parent.mkdir(parents=True, exist_ok=True)
    gateway_path.parent.mkdir(parents=True, exist_ok=True)
    hub_path.parent.mkdir(parents=True, exist_ok=True)

    agent_src = _module("SECRET_PARAM_SUBSTRINGS", agent_entries)
    if agent_hole is not None:
        agent_src += f'TRACE_CREDENTIAL_PLACEHOLDER = "{agent_hole}"\n'
    agent_path.write_text(agent_src, encoding="utf-8")
    gateway_path.write_text(
        _module("_SECRET_QUERY_PARAMS", gateway_entries), encoding="utf-8"
    )
    if hub_hole is not None:
        hub_path.write_text(
            f'CREDENTIAL_HOLE = "{hub_hole}"\n', encoding="utf-8"
        )
    else:
        # The module exists but no longer declares the marker — a rename on
        # this side, rather than a deleted file.
        hub_path.write_text(
            "# CREDENTIAL_HOLE deliberately absent\n", encoding="utf-8"
        )


def test_real_repo_vocabularies_agree() -> None:
    """Both shipped twin pairs are in lockstep, so the leg passes on the repo."""
    result = _run(REPO_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("OK:")
    assert "credential-hole markers agree" in result.stdout


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
        'SECRET_PARAM_SUBSTRINGS: tuple[str, ...] = (\n    "password",\n)\n'
        f'TRACE_CREDENTIAL_PLACEHOLDER = "{HOLE}"\n',
        encoding="utf-8",
    )
    # Both the tool-gateway vocabulary twin and the skills-hub marker twin are
    # deliberately absent.
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "missing file" in result.stdout


def test_credential_hole_markers_agree(tmp_path: Path) -> None:
    """Identical markers pass, and are reported on their own line."""
    entries = ("password",)
    _write_tree(tmp_path, entries, entries)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "credential-hole markers agree" in result.stdout
    assert HOLE in result.stdout


def test_credential_hole_drift_fails_both_directions(tmp_path: Path) -> None:
    """A renamed marker on either side fails and names both literals.

    This is the drift documentation alone could not catch: renaming the
    agent-platform placeholder would silently disable skills-hub's ingestion
    check — a flow carrying an unresolved hole would ingest instead of being
    rejected — without failing anything. The agent-platform direction is the
    likelier one, since that is where the marker is written.
    """
    entries = ("password",)
    for label, kwargs in (
        ("skills-hub renamed", {"hub_hole": "<secret-ref>"}),
        ("agent-platform renamed", {"agent_hole": "<secret-ref>"}),
    ):
        tree = tmp_path / label.replace(" ", "-")
        tree.mkdir()
        _write_tree(tree, entries, entries, **kwargs)
        result = _run(tree)
        assert result.returncode == 1, label
        assert result.stdout.startswith("FAIL:"), label
        assert "credential-hole marker differs" in result.stdout, label
        assert HOLE in result.stdout, label
        assert "<secret-ref>" in result.stdout, label


def test_a_missing_credential_hole_marker_fails(tmp_path: Path) -> None:
    """An absent marker is a hard failure, not a skip (fail-closed)."""
    entries = ("password",)
    for label, kwargs in (
        ("hub", {"hub_hole": None}),
        ("agent", {"agent_hole": None}),
    ):
        tree = tmp_path / label
        tree.mkdir()
        _write_tree(tree, entries, entries, **kwargs)
        result = _run(tree)
        assert result.returncode == 1, label
        assert "literal not found" in result.stdout, result.stdout


def test_a_triple_quoted_marker_is_not_read_as_empty(tmp_path: Path) -> None:
    """The extractor stops at the first quote, so a triple-quoted assignment
    yields the empty string. That is treated as absent rather than as a value:
    if both sides were converted that way, a later divergence would compare
    empty against empty and the gate would pass vacuously. An empty marker is
    a bug in its own right — the empty string is a substring of every string,
    so the ingestion check would reject every document."""
    entries = ("password",)
    _write_tree(tmp_path, entries, entries)
    hub_path = tmp_path / SKILLS_HUB_REL
    hub_path.write_text(
        f'CREDENTIAL_HOLE = """{HOLE}"""\n', encoding="utf-8"
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "CREDENTIAL_HOLE literal not found" in result.stdout


def test_an_fstring_marker_is_not_extracted(tmp_path: Path) -> None:
    """A computed marker has no literal to compare, so it fails closed rather
    than being matched against whatever the interpolation renders at import."""
    entries = ("password",)
    _write_tree(tmp_path, entries, entries)
    hub_path = tmp_path / SKILLS_HUB_REL
    hub_path.write_text(
        'CREDENTIAL_HOLE = f"<{"credential"}-reference>"\n', encoding="utf-8"
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "CREDENTIAL_HOLE literal not found" in result.stdout


def test_a_prose_mention_is_not_read_as_the_assignment(tmp_path: Path) -> None:
    """The extractor is line-anchored, so a comment naming the constant on the
    other side — as both shipped modules do — cannot satisfy the check."""
    entries = ("password",)
    _write_tree(tmp_path, entries, entries, hub_hole=None)
    hub_path = tmp_path / SKILLS_HUB_REL
    hub_path.write_text(
        "# twin of secret_params.TRACE_CREDENTIAL_PLACEHOLDER\n"
        "CREDENTIAL_HOLE_RENAMED = \"<secret-ref>\"\n",
        encoding="utf-8",
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "CREDENTIAL_HOLE literal not found" in result.stdout
