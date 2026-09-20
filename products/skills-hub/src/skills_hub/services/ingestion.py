"""Federated source ingestion: document parsing and validation (SPEC-014 R-1/R-2).

Walks a checked-out source directory, parses and validates every Markdown
document against the skill contract (``shared/shared-contracts/skill-format.md``),
and returns the validated records plus a per-document rejection list. A source
with zero valid documents still produces an (empty) snapshot — "reject the
document, keep the source healthy".

SPEC-055 R-3 advances the contract to Skill v2: an optional ``kind``
discriminator plus a machine-readable ``steps`` replay list, and ``risk_class``
decoupled from ``web_target`` so a non-browser mutating skill (e.g. ``k8s.*``)
can declare ``write``. Both additions are strictly additive — a knowledge skill
carries neither key and validates exactly as it did under v1.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import yaml

from skills_hub.schemas.skill import Skill

LOGGER = logging.getLogger(__name__)

MAX_BODY_BYTES = 65536
MAX_TITLE_CHARS = 200
MAX_DESCRIPTION_CHARS = 500
MAX_TAG_CHARS = 64
MAX_TAGS = 10
MAX_VERSION_CHARS = 64
MAX_SOURCE_URL_CHARS = 2048
MAX_WEB_TARGET_CHARS = 2048
MAX_FLOW_INTENT_CHARS = 200
# SPEC-055 R-3: executable-flow step-list bounds. ``MAX_STEPS`` is a resource
# ceiling, not the policy bound. It sits above the step counts that decide
# anything — the R-1 authoring-trace cap (``AGENT_AUTHORING_TRACE_MAX_STEPS``,
# default 100) and the gateway's per-flow budget
# (``DEFAULT_BROWSER_FLOW_MAX_STEPS``, default 20), which R-4's blast-radius
# bound copies as a deliberate twin (``AGENT_SKILL_GRADUATION_MAX_STEPS``,
# also 20) — so a draft graduated from a default-configured trace is never
# rejected by it. Those are all operator-tunable and this one is not, so the
# ordering is a coupling to preserve rather than an invariant: raising the
# trace cap past 200 would make a long trace un-graduable here (it fails safe
# — the draft is rejected, not truncated). Graduality is a policy decision;
# this is only the resource limit.
# ``MAX_STEPS_BYTES`` matches the body cap — ``steps`` is the first frontmatter
# key whose size the per-key char caps do not already bound, and it lands in
# one JSONB column and rides list responses.
MAX_STEPS = 200
MAX_STEPS_BYTES = 65536
MAX_STEP_TOOL_CHARS = 128
MAX_STEP_EXPECT_CHARS = 500
# A credential hole left by R-2's capture-time parameterization. A hole records
# that a credential was withheld, not which named set fills it, so it is *not* a
# credential-set reference and this document is the boundary where the artifact
# becomes executable. Twin of agent-platform's
# ``secret_params.TRACE_CREDENTIAL_PLACEHOLDER`` — a deliberate second copy, as
# products never import each other. The copy is *enforced*, not just
# documented: the ``validate-secret-vocabulary`` leg of ``make verify``
# extracts both literals and fails the build on divergence
# (``shared/shared-contracts/scripts/validate_secret_vocabulary.py``), and the
# contract in ``shared/shared-contracts/skill-format.md`` names both sides.
CREDENTIAL_HOLE = "<credential-reference>"
CREDENTIAL_FILL_TOOL = "web.fill_credential"
BROWSER_TOOL_PREFIX = "web."
EXECUTABLE_FLOW_KIND = "executable_flow"
# SPEC-057 R-1: the third skill class — an ordered list of single-target
# sub-skill references that carries no authority of its own (ADR-0011).
COMPOSITION_KIND = "composition"
VALID_KINDS = ("knowledge", EXECUTABLE_FLOW_KIND, COMPOSITION_KIND)
STEP_KEYS = {"tool", "args", "expect"}
ALLOWED_KEYS = {
    "title",
    "description",
    "tags",
    "version",
    "source_url",
    # SPEC-049 R-3: optional web-check flow declaration. ``web_target`` is
    # the flow's entry URL; ``risk_class`` declares the effect of the
    # flow's interactive steps (defaults to ``read`` when absent).
    "web_target",
    "risk_class",
    # SPEC-053 R-1: optional author-written intent for the flow's gated
    # mutating step, shown as the confirmation card's lead decision line.
    "flow_intent",
    # SPEC-055 R-3: optional executable-flow class — a ``kind`` discriminator
    # and the machine-readable replay step list it carries.
    "kind",
    "steps",
    # SPEC-057 R-1: optional composition class — the ordered ``sub_skills``
    # reference list a ``kind: composition`` skill carries.
    "sub_skills",
}
VALID_RISK_CLASSES = ("read", "write")
SKIPPED_BASENAMES = {"readme.md", "notice", "notice.md"}
_SEGMENT_CLEANUP = re.compile(r"[^a-z0-9]+")
# SPEC-057 R-1/R-2: composition sub-skill reference bounds. ``MAX_SUB_SKILLS``
# is the module default for the composite-wide cap; sync/draft/CLI thread the
# operator-configured ``SKILLS_COMPOSITION_MAX_SUB_SKILLS`` through so the
# pre-flight matches sync. The item key set is what makes R-3 (no control flow)
# true by construction: only ``skill_id`` + ``note`` are recognized, so any
# sequencing key (``if``/``loop``/``retry``/``on_fail``) is an unknown key.
MAX_SUB_SKILLS = 8
MAX_SUB_SKILL_NOTE_CHARS = 200
SUB_SKILL_ITEM_KEYS = {"skill_id", "note"}
# Same namespaced ``<source_id>/<slug>`` pattern the contract's top-level
# ``skill_id`` and a ``sub_skills[].skill_id`` reference both use.
SKILL_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*(/[a-z0-9][a-z0-9-]*)+$")


@dataclass(frozen=True)
class Rejection:
    """One validation failure, exposed verbatim via the status endpoint."""

    source_id: str
    path: str
    reason: str


@dataclass
class IngestResult:
    records: list[Skill] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)


def slug_from_path(rel_path: str) -> str | None:
    """Derive the slug from the document's relative path.

    ``alerts/KubePodNotReady.md`` -> ``alerts/kubepodnotready``. Segments are
    lowercased and every run of non-alphanumeric characters collapses to a
    single ``-``; a segment that sanitizes to nothing invalidates the path.
    """
    rel = rel_path[:-3] if rel_path.lower().endswith(".md") else rel_path
    segments: list[str] = []
    for part in rel.split("/"):
        cleaned = _SEGMENT_CLEANUP.sub("-", part.lower()).strip("-")
        if not cleaned:
            return None
        segments.append(cleaned)
    return "/".join(segments) if segments else None


def split_frontmatter(text: str) -> tuple[str, str] | None:
    """Split a document into (frontmatter_yaml, body).

    Returns None when the document does not open with a ``---`` fence or the
    fence is never closed — both are validation failures.
    """
    if not text.startswith("---"):
        return None
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1 :])
    return None


def _validate_frontmatter(
    source_id: str, rel_path: str, raw: str, max_sub_skills: int = MAX_SUB_SKILLS
) -> tuple[dict, str] | Rejection:
    """Validate the frontmatter mapping; return fields or a rejection."""
    parts = split_frontmatter(raw)
    if parts is None:
        return Rejection(source_id, rel_path, "missing or unterminated frontmatter")
    frontmatter_raw, body = parts
    try:
        frontmatter = yaml.safe_load(frontmatter_raw)
    except yaml.YAMLError as exc:
        return Rejection(source_id, rel_path, f"frontmatter is not valid YAML: {exc}")
    if not isinstance(frontmatter, dict):
        return Rejection(source_id, rel_path, "frontmatter must be a YAML mapping")

    unknown = sorted(set(frontmatter) - ALLOWED_KEYS)
    if unknown:
        return Rejection(
            source_id, rel_path, f"unknown frontmatter keys: {', '.join(unknown)}"
        )

    title = frontmatter.get("title")
    if not isinstance(title, str) or not title.strip():
        return Rejection(source_id, rel_path, "frontmatter 'title' is required")
    if len(title) > MAX_TITLE_CHARS:
        return Rejection(source_id, rel_path, "title exceeds 200 chars")

    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        return Rejection(source_id, rel_path, "frontmatter 'description' is required")
    if len(description) > MAX_DESCRIPTION_CHARS:
        return Rejection(source_id, rel_path, "description exceeds 500 chars")

    tags = frontmatter.get("tags")
    if tags is not None:
        if not isinstance(tags, list) or not all(
            isinstance(tag, str) and tag.strip() for tag in tags
        ):
            return Rejection(
                source_id, rel_path, "tags must be a list of non-empty strings"
            )
        if len(tags) > MAX_TAGS:
            return Rejection(source_id, rel_path, f"more than {MAX_TAGS} tags")
        if any(len(tag) > MAX_TAG_CHARS for tag in tags):
            return Rejection(source_id, rel_path, "tag exceeds 64 chars")

    version = frontmatter.get("version")
    if version is not None and (
        not isinstance(version, str) or len(version) > MAX_VERSION_CHARS
    ):
        return Rejection(source_id, rel_path, "version must be a string ≤ 64 chars")

    source_url = frontmatter.get("source_url")
    if source_url is not None and (
        not isinstance(source_url, str) or len(source_url) > MAX_SOURCE_URL_CHARS
    ):
        return Rejection(
            source_id, rel_path, "source_url must be a string ≤ 2048 chars"
        )

    # SPEC-049 R-3: web-check flow declaration (both keys optional; skills
    # without them ingest unchanged).
    web_target = frontmatter.get("web_target")
    if web_target is not None:
        if (
            not isinstance(web_target, str)
            or not web_target.strip()
            or len(web_target) > MAX_WEB_TARGET_CHARS
        ):
            return Rejection(
                source_id, rel_path, "web_target must be a non-empty string ≤ 2048 chars"
            )
        parsed = urlparse(web_target.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return Rejection(
                source_id,
                rel_path,
                "web_target must be an absolute http(s) URL (scheme + host)",
            )

    risk_class = frontmatter.get("risk_class")
    if risk_class is not None and (
        not isinstance(risk_class, str) or risk_class not in VALID_RISK_CLASSES
    ):
        return Rejection(
            source_id,
            rel_path,
            "risk_class must be one of: read, write",
        )
    # SPEC-055 R-3: ``risk_class`` no longer requires a ``web_target``. The
    # pairing was a browser-flow assumption, and a non-browser mutating skill
    # (``k8s.*`` steps) has no entry URL to declare. Relaxing it is safe on the
    # consuming side because the gateway's flow binding already fails closed on
    # a missing target (``SKILL_NOT_WEB_FLOW``), so such a skill simply cannot
    # bind a browser flow — it is served for grounding and replays per action.

    # SPEC-053 R-1: optional author-written intent for the flow's gated
    # mutating step (card-level, display-only). Requires ``web_target`` like
    # the other flow-declaration keys, but not ``risk_class: write``.
    flow_intent = frontmatter.get("flow_intent")
    if flow_intent is not None:
        if (
            not isinstance(flow_intent, str)
            or not flow_intent.strip()
            or len(flow_intent) > MAX_FLOW_INTENT_CHARS
        ):
            return Rejection(
                source_id,
                rel_path,
                "flow_intent must be a non-empty string ≤ 200 chars",
            )
        if web_target is None:
            return Rejection(
                source_id, rel_path, "flow_intent requires a web_target declaration"
            )

    # SPEC-055 R-3: the executable-flow class. Validated against the whole
    # frontmatter because it is a *set* of declarations that have to agree —
    # ``kind`` + ``steps`` + the ``risk_class``/``web_target`` they imply.
    rejection = _validate_steps(source_id, rel_path, frontmatter)
    if rejection is not None:
        return rejection

    # SPEC-057 R-2: the composition class's *structural* facts — the ones a
    # single document can prove alone. The cross-skill facts (does each
    # sub-skill resolve, is it single-target, is it itself a composition) need
    # the catalog and are checked in sync's store-consulting resolution pass.
    rejection = _validate_composition(
        source_id, rel_path, frontmatter, max_sub_skills
    )
    if rejection is not None:
        return rejection

    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        return Rejection(source_id, rel_path, "body exceeds 64 KiB")

    return frontmatter, body


def _carries_credential_hole(value: object) -> bool:
    """True when a step argument still holds an unresolved credential hole."""
    if isinstance(value, str):
        return CREDENTIAL_HOLE in value
    if isinstance(value, dict):
        return any(_carries_credential_hole(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_carries_credential_hole(item) for item in value)
    return False


def _validate_step(
    source_id: str, rel_path: str, index: int, step: object
) -> Rejection | None:
    """Validate one replay step; None when it is well formed.

    Mirrors ``schemas/skill.py``'s ``SkillStep`` (``extra="forbid"``) and the
    contract's step object (``additionalProperties: false``), so a document the
    contract accepts is a document the envelope can carry.
    """
    where = f"step {index}"
    if not isinstance(step, dict):
        return Rejection(source_id, rel_path, f"{where} must be a mapping")
    unknown = sorted(str(key) for key in set(step) - STEP_KEYS)
    if unknown:
        return Rejection(
            source_id, rel_path, f"{where}: unknown step keys: {', '.join(unknown)}"
        )

    tool = step.get("tool")
    if not isinstance(tool, str) or not tool.strip():
        return Rejection(source_id, rel_path, f"{where}: 'tool' is required")
    if len(tool) > MAX_STEP_TOOL_CHARS:
        return Rejection(
            source_id, rel_path, f"{where}: tool exceeds {MAX_STEP_TOOL_CHARS} chars"
        )

    args = step.get("args")
    if not isinstance(args, dict):
        return Rejection(
            source_id, rel_path, f"{where}: 'args' is required and must be a mapping"
        )
    # ``json.dumps`` is the exact encoding the ``steps`` JSONB column applies,
    # so validating with it means "accepted here" and "storable there" cannot
    # diverge. It is not a formality: YAML parses an unquoted date into a
    # ``datetime.date``, which no JSON encoder accepts — without this check the
    # document would ingest and then fail the Postgres write at sync time.
    try:
        json.dumps(args)
    except (TypeError, ValueError):
        return Rejection(
            source_id,
            rel_path,
            f"{where}: args must be JSON-compatible "
            "(mappings, lists, strings, numbers, booleans, null)",
        )

    expect = step.get("expect")
    if expect is not None and (
        not isinstance(expect, str) or len(expect) > MAX_STEP_EXPECT_CHARS
    ):
        return Rejection(
            source_id,
            rel_path,
            f"{where}: expect must be a string ≤ {MAX_STEP_EXPECT_CHARS} chars",
        )

    # Credential values are credential-set *references*, never literals
    # (SPEC-055 R-3). Both checks are vocabulary-free — skills-hub cannot see
    # the gateway's platform-managed credential store, so "resolves to a named
    # credential set" is structural here: a step that fills a credential must
    # *name* the set and the field, and no argument may still carry R-2's
    # unresolved-hole marker (a hole names nothing).
    if tool == CREDENTIAL_FILL_TOOL:
        set_name = args.get("credential_set")
        if not isinstance(set_name, str) or not set_name.strip():
            return Rejection(
                source_id,
                rel_path,
                f"{where}: {CREDENTIAL_FILL_TOOL} must reference a named "
                "'credential_set'",
            )
        field_name = args.get("field")
        if not isinstance(field_name, str) or not field_name.strip():
            return Rejection(
                source_id, rel_path, f"{where}: {CREDENTIAL_FILL_TOOL} needs a 'field'"
            )
    if _carries_credential_hole(args):
        return Rejection(
            source_id,
            rel_path,
            f"{where}: args carry an unresolved credential hole "
            f"({CREDENTIAL_HOLE}); a step must reference a named credential set",
        )
    return None


def _validate_steps(
    source_id: str, rel_path: str, frontmatter: dict
) -> Rejection | None:
    """Validate the executable-flow class (SPEC-055 R-3); None when valid.

    Additive by construction: a document with neither ``kind`` nor ``steps``
    returns None immediately and validates exactly as it did under v1.

    An ``executable_flow`` must declare ``risk_class: write`` unconditionally.
    That is the fail-closed reading of "write when any step mutates": a step
    list is a replay of *approved mutations* (R-2's tier gate makes a read-tier
    call structurally incapable of entering a trace), so for every flow the
    platform produces the conditional and the unconditional rule coincide — and
    for a hand-authored one, skills-hub holds no per-tool risk vocabulary to
    check a ``read`` claim against, while declaring ``write`` costs only that
    the flow replays under R-5's single gate and the gateway's write-class
    guard. A read-only browser flow needs no step list: the SPEC-049
    ``web_target`` + ``risk_class: read`` class already serves it.
    """
    kind = frontmatter.get("kind")
    steps = frontmatter.get("steps")
    if kind is not None and (not isinstance(kind, str) or kind not in VALID_KINDS):
        return Rejection(
            source_id,
            rel_path,
            f"kind must be one of: {', '.join(VALID_KINDS)}",
        )
    if steps is not None and kind != EXECUTABLE_FLOW_KIND:
        # ``steps`` is the executable-flow replay list, so a step list without
        # the discriminator is a malformed document rather than an implicit
        # executable flow — the class is declared, never inferred.
        return Rejection(
            source_id, rel_path, f"steps requires kind: {EXECUTABLE_FLOW_KIND}"
        )
    if kind != EXECUTABLE_FLOW_KIND:
        # Absent or ``knowledge``: no replay list to check. A ``steps`` key
        # reaching here without the discriminator was rejected above, so a
        # knowledge skill can never smuggle one in.
        return None

    if not isinstance(steps, list) or not steps:
        return Rejection(
            source_id,
            rel_path,
            f"kind: {EXECUTABLE_FLOW_KIND} requires a non-empty steps list",
        )
    if len(steps) > MAX_STEPS:
        return Rejection(source_id, rel_path, f"more than {MAX_STEPS} steps")
    if frontmatter.get("risk_class") != "write":
        return Rejection(
            source_id,
            rel_path,
            f"kind: {EXECUTABLE_FLOW_KIND} requires risk_class: write",
        )

    browser_step = False
    for index, step in enumerate(steps, start=1):
        rejection = _validate_step(source_id, rel_path, index, step)
        if rejection is not None:
            return rejection
        if str(step["tool"]).startswith(BROWSER_TOOL_PREFIX):
            browser_step = True
    if browser_step and frontmatter.get("web_target") is None:
        # R-3 decouples ``risk_class`` from ``web_target``, not browser replay
        # from it: the gateway binds a flow — and with it the origin guard and
        # the step budget — from the declared target, so a ``web.*`` step with
        # no target declares a flow that cannot be bound or bounded.
        return Rejection(
            source_id, rel_path, "a web.* step requires a web_target declaration"
        )
    try:
        encoded_steps = json.dumps(steps)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        # Unreachable today: every step was JSON-checked above. Kept so a
        # future step-shape change degrades to a rejection rather than raising
        # inside the sync loop (same posture as the frontmatter YAML guard).
        return Rejection(source_id, rel_path, "steps must be JSON-compatible")
    # Measured on the authored list, which is a close proxy for the stored one
    # rather than a byte-identical twin: ``model_dump`` materializes an
    # ``expect: null`` the author may have omitted (~16 bytes a step). The
    # served list response is smaller again, since ``summary()`` excludes None.
    if len(encoded_steps) > MAX_STEPS_BYTES:
        return Rejection(
            source_id, rel_path, f"steps exceed {MAX_STEPS_BYTES // 1024} KiB"
        )
    return None


def _validate_composition(
    source_id: str, rel_path: str, frontmatter: dict, max_sub_skills: int
) -> Rejection | None:
    """Validate the composition class's *structural* facts (SPEC-057 R-2/R-3).

    Additive by construction: a document with neither ``kind: composition`` nor
    ``sub_skills`` returns None immediately and validates exactly as before.
    This pure layer covers only what a single document can prove alone — the
    reference-list shape, the item key set, the count cap, the no-duplicate
    rule, and the "a composition declares no web_target/steps/risk_class"
    invariant — so ``validate_document`` (the draft path) and the
    ``python -m skills_hub.validate`` CLI, which have no catalog, enforce it
    too. The cross-skill facts (does each sub-skill resolve, is it single-target,
    is it itself a composition) need the store and are checked in sync's
    ``_resolve_compositions`` pass; a composition is *never* silently degraded
    to a knowledge skill — a failure here rejects the document.
    """
    kind = frontmatter.get("kind")
    sub_skills = frontmatter.get("sub_skills")

    if sub_skills is not None and kind != COMPOSITION_KIND:
        # ``sub_skills`` is the composition's reference list, so a list without
        # the discriminator is a malformed document rather than an implicit
        # composition — the class is declared, never inferred (the ``steps``
        # rule's twin).
        return Rejection(
            source_id, rel_path, f"sub_skills requires kind: {COMPOSITION_KIND}"
        )
    if kind != COMPOSITION_KIND:
        return None

    # A composition declares no authorization target, no interpreter input, and
    # no author risk_class: its scope is the union of its sub-skills' scopes and
    # its display risk_class is derived at sync (SPEC-057 R-1/R-2). Declaring
    # any of the three would falsely imply a single gated target or a platform
    # sequencer that does not exist.
    for forbidden in ("web_target", "steps", "risk_class"):
        if frontmatter.get(forbidden) is not None:
            return Rejection(
                source_id,
                rel_path,
                f"a composition declares no {forbidden} "
                f"(kind: {COMPOSITION_KIND})",
            )

    if not isinstance(sub_skills, list) or not sub_skills:
        return Rejection(
            source_id,
            rel_path,
            f"kind: {COMPOSITION_KIND} requires a non-empty sub_skills list",
        )
    if len(sub_skills) > max_sub_skills:
        return Rejection(
            source_id, rel_path, f"more than {max_sub_skills} sub_skills"
        )

    seen: set[str] = set()
    for index, item in enumerate(sub_skills, start=1):
        where = f"sub_skill {index}"
        if not isinstance(item, dict):
            return Rejection(source_id, rel_path, f"{where} must be a mapping")
        unknown = sorted(str(key) for key in set(item) - SUB_SKILL_ITEM_KEYS)
        if unknown:
            # R-3: this is what rejects a sequencing key (``if`` / ``loop`` /
            # ``retry`` / ``on_fail``) — there is no control-flow vocabulary, so
            # any key but the two allowed is unknown and the document fails.
            return Rejection(
                source_id,
                rel_path,
                f"{where}: unknown sub_skill keys: {', '.join(unknown)}",
            )
        skill_id = item.get("skill_id")
        if not isinstance(skill_id, str) or not SKILL_ID_PATTERN.match(skill_id):
            return Rejection(
                source_id,
                rel_path,
                f"{where}: 'skill_id' is required and must be a namespaced "
                "<source_id>/<slug> id",
            )
        if skill_id in seen:
            return Rejection(
                source_id, rel_path, f"{where}: duplicate skill_id '{skill_id}'"
            )
        seen.add(skill_id)
        note = item.get("note")
        if note is not None and (
            not isinstance(note, str)
            or len(note) > MAX_SUB_SKILL_NOTE_CHARS
        ):
            return Rejection(
                source_id,
                rel_path,
                f"{where}: note must be a string "
                f"≤ {MAX_SUB_SKILL_NOTE_CHARS} chars",
            )
    return None


def validate_document(
    raw: str, max_sub_skills: int = MAX_SUB_SKILLS
) -> tuple[bool, str | None]:
    """Validate one candidate skill document against the skill contract.

    Same code path ``ingest_directory`` uses at sync time (single source of
    truth for Skill Format v1 — SPEC-044 R-2). Returns ``(valid, reason)``
    where ``reason`` uses the ingestion report vocabulary verbatim.
    ``max_sub_skills`` defaults to the module cap; the draft route threads the
    operator-configured ``SKILLS_COMPOSITION_MAX_SUB_SKILLS`` so the pre-flight
    matches sync (SPEC-057 R-2).
    """
    validated = _validate_frontmatter(
        "validate", "draft.md", raw, max_sub_skills
    )
    if isinstance(validated, Rejection):
        return False, validated.reason
    return True, None


def ingest_directory(
    source_id: str,
    root: Path,
    source_ref: str,
    updated_at: datetime,
    max_sub_skills: int = MAX_SUB_SKILLS,
) -> IngestResult:
    """Validate every skill document under ``root`` into one snapshot.

    Deterministic by construction: files are visited in sorted path order, so
    duplicate-slug resolution (first occurrence wins) is stable across runs.
    """
    result = IngestResult()
    if not root.is_dir():
        result.rejections.append(
            Rejection(source_id, ".", f"source directory not found: {root}")
        )
        return result
    projected = root / "..data"
    if projected.is_dir():
        # Kubernetes projected volumes (ConfigMap/Secret mounts) keep the
        # canonical content in a timestamped directory exposed through a
        # ``..data`` symlink; walk that directly instead of the symlink farm.
        root = projected
    seen_slugs: dict[str, str] = {}
    for path in sorted(root.rglob("*.md")):
        rel_path = path.relative_to(root).as_posix()
        # Skip hidden path segments: Kubernetes ConfigMap/Secret volumes expose
        # atomic-writer artifacts (..data symlink, ..<timestamp> dirs) that
        # would otherwise be ingested with polluted slugs.
        if any(part.startswith(".") for part in rel_path.split("/")):
            continue
        if path.name.lower() in SKIPPED_BASENAMES:
            continue
        slug = slug_from_path(rel_path)
        if slug is None:
            result.rejections.append(
                Rejection(source_id, rel_path, "path does not produce a slug")
            )
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            result.rejections.append(
                Rejection(source_id, rel_path, f"unreadable document: {exc}")
            )
            continue
        validated = _validate_frontmatter(
            source_id, rel_path, raw, max_sub_skills
        )
        if isinstance(validated, Rejection):
            result.rejections.append(validated)
            continue
        frontmatter, body = validated
        if slug in seen_slugs:
            result.rejections.append(
                Rejection(
                    source_id,
                    rel_path,
                    f"duplicate slug '{slug}' (already defined by "
                    f"{seen_slugs[slug]})",
                )
            )
            continue
        seen_slugs[slug] = rel_path
        result.records.append(
            Skill(
                skill_id=f"{source_id}/{slug}",
                source_id=source_id,
                source_path=rel_path,
                source_ref=source_ref,
                title=frontmatter["title"].strip(),
                description=frontmatter["description"].strip(),
                tags=frontmatter.get("tags"),
                version=frontmatter.get("version"),
                source_url=frontmatter.get("source_url"),
                web_target=frontmatter.get("web_target"),
                risk_class=frontmatter.get("risk_class"),
                flow_intent=frontmatter.get("flow_intent"),
                kind=frontmatter.get("kind"),
                steps=frontmatter.get("steps"),
                sub_skills=frontmatter.get("sub_skills"),
                updated_at=updated_at,
                body=body.lstrip("\n"),
            )
        )
    return result
