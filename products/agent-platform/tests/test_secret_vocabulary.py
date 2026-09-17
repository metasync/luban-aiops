"""Self-tests for the cross-product secret-literal lockstep leg.

``shared/shared-contracts/scripts/validate_secret_vocabulary.py`` textually
compares three pairs of deliberate second copies, each pair spanning products
that never import each other, so the comparison is by source extraction:

1. the agent-platform ``SECRET_PARAM_SUBSTRINGS`` tuple against its
   tool-gateway twin ``SECRET_QUERY_PARAMS`` in ``url_redaction`` (SPEC-054
   R-3 / SPEC-049 R-5; SPEC-058 R-6 moved it out of ``browser_connector``);
2. the agent-platform ``TRACE_CREDENTIAL_PLACEHOLDER`` marker against its
   skills-hub twin ``CREDENTIAL_HOLE`` (SPEC-055 R-2 writes it, R-3 refuses it);
3. the agent-platform ``REDACTION_VALUE_PATTERNS`` shape tuple against its
   tool-gateway twin ``_VALUE_PATTERNS`` (the gateway redacts tool output with
   it, ``skill_draft.postprocess`` a draft body, and SPEC-055 R-4 graduation
   *refuses* a step argument matching one).

Any drift fails the ``make verify`` build.

The third coupling is compared as an **ordered** list while the first is a set:
both shape copies document their order as meaningful ("most specific first" so
overlapping shapes are not double-counted), so a re-ordering is a divergence a
set comparison would pass silently. ``test_reordered_shapes_fail`` pins that
difference rather than leaving it to the docstring.

These tests run the script as a subprocess against (a) the real repo, which
must agree, and (b) synthetic trees that agree and diverge, proving the leg
passes on lockstep and fails — in both directions, for all three couplings — on
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
GATEWAY_REL = Path("products/tool-gateway/src/tool_gateway/tools/url_redaction.py")
SKILLS_HUB_REL = Path("products/skills-hub/src/skills_hub/services/ingestion.py")
SKILL_DRAFT_REL = Path("products/agent-platform/src/agent_service/services/skill_draft.py")
REDACTION_REL = Path("products/tool-gateway/src/tool_gateway/tools/redaction.py")

# The shipped marker, used as the synthetic default so the vocabulary tests
# exercise one coupling at a time.
HOLE = "<credential-reference>"

# Synthetic shape vocabulary, as regex *source text* — the extractor compares
# the raw-string literals verbatim, backslashes included, so these are what the
# generated modules must contain between the quotes. Two is enough to make an
# ordering divergence distinguishable from a membership one.
SHAPES: tuple[str, ...] = (
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b",
)
EXTRA_SHAPE = r"\bghp_[A-Za-z0-9]{36}\b"


def _run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(root)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _shapes_module(var: str, shapes: tuple[str, ...]) -> str:
    """A synthetic shape-vocabulary module.

    The closing paren sits at column zero on its own line, which is what the
    extractor keys on: unlike the substring tuples, these bodies contain parens
    of their own (regex groups), so the block cannot be captured to the first
    ``)``. An empty ``shapes`` renders a tuple with no literals, exercising the
    "found the block, extracted nothing" path distinctly from "block absent".
    """
    body = "".join(f'    re.compile(r"{shape}"),\n' for shape in shapes)
    return f"{var}: tuple[re.Pattern[str], ...] = (\n{body})\n"


def _write_tree(
    root: Path,
    agent_entries: tuple[str, ...],
    gateway_entries: tuple[str, ...],
    *,
    agent_hole: str | None = HOLE,
    hub_hole: str | None = HOLE,
    agent_shapes: tuple[str, ...] | None = SHAPES,
    gateway_shapes: tuple[str, ...] | None = SHAPES,
) -> None:
    """Materialize a minimal repo tree carrying all three twin pairs.

    A hole marker or a shape tuple passed as ``None`` writes the file *without*
    the literal, so the "literal not found" path is exercised distinctly from
    the "missing file" path (``test_missing_source_file_fails`` covers that
    one).
    """

    def _module(var: str, entries: tuple[str, ...]) -> str:
        body = ", ".join(f'"{e}"' for e in entries)
        return f"{var}: tuple[str, ...] = (\n    {body},\n)\n"

    agent_path = root / AGENT_REL
    gateway_path = root / GATEWAY_REL
    hub_path = root / SKILLS_HUB_REL
    draft_path = root / SKILL_DRAFT_REL
    redaction_path = root / REDACTION_REL
    for path in (agent_path, gateway_path, hub_path, draft_path, redaction_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    agent_src = _module("SECRET_PARAM_SUBSTRINGS", agent_entries)
    if agent_hole is not None:
        agent_src += f'TRACE_CREDENTIAL_PLACEHOLDER = "{agent_hole}"\n'
    agent_path.write_text(agent_src, encoding="utf-8")
    gateway_path.write_text(
        _module("SECRET_QUERY_PARAMS", gateway_entries), encoding="utf-8"
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
    if agent_shapes is not None:
        draft_path.write_text(
            _shapes_module("REDACTION_VALUE_PATTERNS", agent_shapes),
            encoding="utf-8",
        )
    else:
        draft_path.write_text(
            "# REDACTION_VALUE_PATTERNS deliberately absent\n", encoding="utf-8"
        )
    if gateway_shapes is not None:
        redaction_path.write_text(
            _shapes_module("_VALUE_PATTERNS", gateway_shapes), encoding="utf-8"
        )
    else:
        redaction_path.write_text(
            "# _VALUE_PATTERNS deliberately absent\n", encoding="utf-8"
        )


def test_real_repo_vocabularies_agree() -> None:
    """All three shipped twin pairs are in lockstep, so the leg passes."""
    result = _run(REPO_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("OK:")
    assert "credential-hole markers agree" in result.stdout
    assert "secret-shape vocabularies agree" in result.stdout


def test_synthetic_tree_agrees(tmp_path: Path) -> None:
    """Identical tuples (order-insensitive) pass and report the shared count."""
    entries = ("password", "token", "secret")
    _write_tree(tmp_path, entries, entries)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "agree (3 substrings)" in result.stdout
    assert f"agree ({len(SHAPES)} patterns, in order)" in result.stdout


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
    # The four other source files — the tool-gateway substring twin, the
    # skills-hub marker twin, and both shape modules — are deliberately absent.
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


def test_shape_drift_fails_both_directions(tmp_path: Path) -> None:
    """A shape one side knows and the other does not fails and names the side.

    The consequential direction is the gateway growing a shape
    agent-platform does not mirror: the new shape would still be redacted out
    of tool output and out of a draft's readable body, while the value itself
    rode unrefused into the frontmatter a human merges — the one copy that is
    never scrubbed. Neither direction may pass silently.
    """
    entries = ("password",)
    for label, kwargs, expected_side in (
        (
            "gateway-only",
            {"gateway_shapes": SHAPES + (EXTRA_SHAPE,)},
            "tool-gateway only",
        ),
        (
            "agent-only",
            {"agent_shapes": SHAPES + (EXTRA_SHAPE,)},
            "agent-platform only",
        ),
    ):
        tree = tmp_path / label
        tree.mkdir()
        _write_tree(tree, entries, entries, **kwargs)
        result = _run(tree)
        assert result.returncode == 1, label
        assert result.stdout.startswith("FAIL:"), label
        assert "secret-shape vocabulary differs" in result.stdout, label
        # Names the side that grew the shape, and the shape itself: a build
        # failure that does not say which copy to fix is a build failure that
        # gets worked around. Printed as a ``repr``, like the substring
        # vocabulary's failures, so the backslashes in a regex source text are
        # visible rather than interpreted.
        assert expected_side in result.stdout, label
        assert repr(EXTRA_SHAPE) in result.stdout, label


def test_reordered_shapes_fail(tmp_path: Path) -> None:
    """The same shapes in a different order fail — the ordered/set distinction.

    Both copies document their order as meaningful ("most specific first" so
    overlapping shapes are not double-counted), and this coupling is compared
    as a list while the substring vocabulary above is compared as a set. A set
    comparison would pass a re-ordering silently, so the distinction is pinned
    here rather than left to the docstring.
    """
    entries = ("password",)
    reordered = tuple(reversed(SHAPES))
    assert set(reordered) == set(SHAPES), "the premise: membership is unchanged"
    _write_tree(tmp_path, entries, entries, agent_shapes=reordered)
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "secret-shape vocabulary differs" in result.stdout
    assert "different order" in result.stdout
    # Neither side holds a shape the other lacks, so the membership wording
    # must not appear — the message has to say what actually diverged.
    assert "only:" not in result.stdout


def test_a_missing_shape_tuple_fails(tmp_path: Path) -> None:
    """A shape constant renamed away on either side fails closed.

    The likelier drift is not a changed pattern but a refactor that makes the
    tuple private again or renames it — the extraction then finds nothing, and
    a check that skipped on "not found" would pass with one side unpinned.
    """
    entries = ("password",)
    for label, kwargs in (
        ("agent", {"agent_shapes": None}),
        ("gateway", {"gateway_shapes": None}),
    ):
        tree = tmp_path / label
        tree.mkdir()
        _write_tree(tree, entries, entries, **kwargs)
        result = _run(tree)
        assert result.returncode == 1, label
        assert "tuple not found" in result.stdout, result.stdout


def test_an_empty_shape_tuple_is_not_read_as_agreement(tmp_path: Path) -> None:
    """Two empty vocabularies must not compare equal and pass vacuously.

    The same trap as ``test_a_triple_quoted_marker_is_not_read_as_empty``: if
    an extraction that found the block but no literals returned ``()``, a
    quoting-style refactor on both sides would leave the coupling green while
    pinning nothing — and graduation would refuse no shape at all.
    """
    entries = ("password",)
    _write_tree(tmp_path, entries, entries, agent_shapes=(), gateway_shapes=())
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "no raw-string patterns" in result.stdout
