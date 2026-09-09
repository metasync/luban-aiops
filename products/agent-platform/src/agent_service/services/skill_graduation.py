"""Deterministic graduation of an authoring trace (SPEC-055 R-4).

Contrast SPEC-044's ``skill_draft``: that service asks a model to synthesize
knowledge prose from a session's record, so it needs a bounded regeneration
loop and a facts-only skeleton to fall back to. Graduation has nothing to
synthesize — the trace *is* the flow. Every step in it was approved by a human
and signed by a key before it was captured (R-2's tier gate makes a parked,
denied or read-tier call structurally incapable of entering a trace), so the
draft is a rendering rather than a composition, and a rendering is
deterministic by construction: the same trace produces the same document on the
same UTC date — the provenance block's ``date:`` is the only wall-clock input —
and a step the trace does not contain can never appear in one.

Two functions, in the order the endpoint calls them:

``revalidate_blast_radius`` is the refusal. It re-applies at graduation the
guards the tool-gateway applies at *replay* (SPEC-051) — a step budget, an
origin allowlist, a write-class declaration, credentials resolved to named
sets — so the artifact an operator is handed is one that replays under those
same guards once a human completes it. Two are re-applied at a coarser grain
than the gateway's, deliberately. Corroboration is at *origin* level because
``flow_origin`` records an origin rather than a URL, so a same-origin path
drift is refused nowhere here and is bounded only by ``_path_under`` at bind
time. And the step list holds only *mutating* steps, because the two read-tier
calls a runnable flow also needs — ``web.navigate``, the only entry point to
``bind_flow``, and ``web.fill_credential`` — are never captured at all; the
runbook tells the operator to add both by hand. Running the guards here as well
as there is what makes a refusal legible: at replay the same failure is a
``BROWSER_FLOW_EXHAUSTED`` or ``BROWSER_FLOW_ORIGIN_DEVIATED`` denial part-way
through a mutation, and here it is a reason naming the step.

``build_executable_flow_draft`` is the rendering. It runs only on a trace the
re-validation passed, so it never has to defend against what the guards
already refused.

Nothing here persists. The endpoint flips the trace lifecycle to ``graduated``
and emits ``skill_graduated``; the draft itself is the response — ephemeral by
construction, for a human to review and merge into the team's Git skills repo.
The platform never auto-publishes an executable *mutating* skill (SPEC-044's
"the platform drafts, humans merge", preserved because this artifact is
higher-trust than a knowledge draft).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from agent_service.services.authoring_trace import origin_of_url
from agent_service.services.flow_approvals import BROWSER_WRITE_TOOLS
from agent_service.services.secret_params import TRACE_CREDENTIAL_PLACEHOLDER
from agent_service.services.skill_draft import (
    MAX_BODY_BYTES,
    REDACTION_VALUE_PATTERNS,
    postprocess,
    provenance_block,
    slug_from_title,
)

# The response ``mode``. Distinct from SPEC-044's ``generated`` /
# ``skeleton``: those describe how much of a draft a model managed to
# produce, this one says no model was involved at all, which is the property
# an operator reviewing an *executable* artifact most needs to see.
MODE_GRADUATED = "graduated"

EXECUTABLE_FLOW_KIND = "executable_flow"
WRITE_RISK_CLASS = "write"
BROWSER_TOOL_PREFIX = "web."
GRADUATION_TAGS = ("executable-flow", "graduated")

# Deliberate twin of the tool-gateway's ``DEFAULT_BROWSER_FLOW_MAX_STEPS``
# (``core/config.py``), which is the budget ``bind_flow`` arms a bound flow
# with and ``BROWSER_FLOW_EXHAUSTED`` enforces. Products never import each
# other, so the number is copied — and unlike the secret vocabularies it
# carries no drift guard, because a drift is safe in both directions: the
# gateway stays the authority at replay and fails closed regardless, so a
# bound here that is too high only defers a refusal the operator would still
# get, and one that is too low only refuses a trace that would have replayed.
# Both ends are operator-tunable (``AGENT_SKILL_GRADUATION_MAX_STEPS`` /
# ``GATEWAY_BROWSER_FLOW_MAX_STEPS``): this literal is the default
# ``RuntimeSettings`` registers for the former, and the graduation route
# passes that resolved value rather than the constant, so the twin moves with
# the gateway budget instead of silently falling behind it.
#
# This is the bound that decides graduality, not skills-hub's ingestion
# ceiling: ``MAX_STEPS`` there is 200, deliberately above both this and the
# R-1 trace cap so a resource limit is never the reason a flow cannot
# graduate. A flow longer than the replay budget would ingest cleanly and
# then die part-way through mutating, which is the failure R-4 exists to
# surface before an operator holds the artifact.
DEFAULT_MAX_GRADUATION_STEPS = 20

# Twin of skills-hub's ``ingestion.MAX_STEPS_BYTES`` — the serialized ceiling
# on the ``steps`` list, checked here so an oversize trace is a legible
# refusal rather than an ingestion rejection of a document the platform
# itself rendered. The twin is only as good as its *basis*: it is measured on
# the rendered payload list with ``json.dumps``' defaults exactly as ingestion
# measures it, because a UTF-8 byte count of the same list comes to roughly
# half of ingestion's ``\uXXXX``-escaped character count on non-ASCII
# arguments (see the measurement in ``revalidate_blast_radius``).
MAX_STEPS_BYTES = 65536

# Twin of skills-hub's ``ingestion.MAX_STEP_TOOL_CHARS``.
MAX_STEP_TOOL_CHARS = 128

# Where the target declaration sits relative to the first captured step. A
# report, never a gate: corroboration is the control, and a hard ordering gate
# would add friction without adding safety (stage-6a note in tasks.md).
DECLARATION_PRECEDED = "preceded"
DECLARATION_POSTDATED = "postdated"
DECLARATION_INDETERMINATE = "indeterminate"

# Body-side bound on one step's rendered arguments. The runbook restates the
# ``steps`` list for a human reader, and the frontmatter already carries the
# authoritative copy, so a huge argument is elided here rather than doubling
# it into the body's own 64 KiB cap.
_MAX_RENDERED_ARG_CHARS = 400


@dataclass(frozen=True)
class BlastRadius:
    """One trace's blast-radius re-validation outcome.

    ``refusals`` is a tuple of operator-facing reasons, not a single message:
    a trace can fail several guards at once, and reporting only the first
    would send the operator back for a second round-trip to discover the
    next. Each names the step it is about, because "not graduable" with no
    location is not actionable.

    ``unguarded_positions`` is *not* a refusal. A non-browser step (``k8s.*``)
    is outside the flow's origin guard by construction — the gateway binds a
    browser flow from ``web_target`` and has no non-browser binding yet
    (OQ-2's deferred slice) — so those steps replay under their own
    per-action approval, which fails safe. The draft says so out loud rather
    than implying an origin guard covers them.
    """

    graduable: bool
    refusals: tuple[str, ...]
    step_count: int
    max_steps: int
    web_target: str | None
    browser_steps: int
    unguarded_positions: tuple[int, ...]
    declaration: str


def _ordered(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The trace in replay order, on one basis for both callers.

    ``load_for_session`` already returns ``ORDER BY position ASC`` on both
    backends; sorting again is cheap insurance that the re-validation and the
    rendering cannot disagree about which step is "step 3", and the stable
    sort leaves a hand-built list in its given order.
    """
    return sorted(steps, key=lambda step: step.get("position") or 0)


def _hole_paths(value: Any, path: str = "args") -> Iterator[str]:
    """Every argument path still carrying R-2's unresolved credential hole.

    A substring test, matching skills-hub's ``_carries_credential_hole`` —
    the marker names no credential set, so a step carrying one could never
    authenticate at replay and ingestion rejects the document outright.
    """
    if isinstance(value, str):
        if TRACE_CREDENTIAL_PLACEHOLDER in value:
            yield path
        return
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _hole_paths(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _hole_paths(item, f"{path}[{index}]")


def _declaration_order(declared_at: Any, steps: list[dict[str, Any]]) -> str:
    """Whether the declaration preceded the first captured step.

    Both stamps arrive already canonicalized to **second** precision — the
    store renders ``captured_at`` through ``_iso`` and ``declared_at`` through
    ``_canonical_timestamp`` on both backends — so this comparison is on one
    basis everywhere, which is the hazard the stage-6a note flags: the
    Postgres columns hold microseconds and a mixed-precision comparison would
    disagree with the in-memory backend inside a sub-second window.

    Equal stamps therefore answer ``indeterminate`` rather than ``preceded``:
    the sub-second order is genuinely not knowable from what the store
    returns, and guessing would report an authorization scope as
    pre-declared when it may have been fitted to the trace. Nothing gates on
    this, so ``indeterminate`` costs the operator a fact, never a graduation.
    """
    if not declared_at or not steps:
        return DECLARATION_INDETERMINATE
    first = steps[0].get("captured_at")
    if not first:
        return DECLARATION_INDETERMINATE
    try:
        declared = datetime.fromisoformat(str(declared_at).replace("Z", "+00:00"))
        captured = datetime.fromisoformat(str(first).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return DECLARATION_INDETERMINATE
    if declared.tzinfo is None or captured.tzinfo is None:
        return DECLARATION_INDETERMINATE
    if declared < captured:
        return DECLARATION_PRECEDED
    if declared > captured:
        return DECLARATION_POSTDATED
    return DECLARATION_INDETERMINATE


def revalidate_blast_radius(
    steps: list[dict[str, Any]],
    *,
    target: str | None,
    declared_at: str | None = None,
    max_steps: int = DEFAULT_MAX_GRADUATION_STEPS,
) -> BlastRadius:
    """Re-validate a trace's blast radius before any draft is produced (R-4).

    The five guards spec.md R-4 names, each substantiated by evidence the
    trace actually carries rather than asserted about it:

    - **bounded step count** — against the replay budget, not the ingestion
      ceiling (see ``DEFAULT_MAX_GRADUATION_STEPS``).
    - **every target/origin allowlisted** — every *observed* origin compared
      against the *declared* target's origin. A step whose origin is NULL is
      **unverified and refuses**: NULL is produced by a result that did not
      succeed, by a payload over the evidence frame's size guard, by a gateway
      that reported no URL, and by every row written before R-4 — fabricating
      an origin for one would corroborate a mutation that may never have
      landed. The check applies to browser steps, because those are the only
      ones ``_observe_step_origin`` records an origin for; a non-browser step
      is reported as unguarded instead, which is the honest state.
    - **a consistent declared ``risk_class: write``** — the class declares
      ``write`` unconditionally, so consistency means the trace holds no
      read-tier step. R-2's tier gate already makes that impossible, and this
      is the check that would say so if the gate ever leaked: a read-tier
      ``web.*`` probe in a write-class flow would mean something entered a
      trace that should not have.
    - **all credentials resolved to credential-set references** — an
      unresolved hole refuses, naming the step and argument path.
    - **no argument shaped like a secret literal** — the serialized step is
      scanned against ``skill_draft.REDACTION_VALUE_PATTERNS`` and a match
      refuses, naming the step. This is the only guard whose inference is a
      *guess*: the other four read a fact the trace records, this one reads a
      shape and infers a meaning. It exists because R-2's capture-time
      parameterization is name-based and deliberately fails open, so a literal
      under a name the vocabulary does not know is stored verbatim and would
      otherwise ride into the one artifact a human merges into a repository.
      Being a guess, it over-catches — a ``web.select`` option reading
      ``Basic Authentication`` is refused too, and cannot be told apart from a
      real ``Authorization`` value at this layer. That is the accepted
      direction of error: a false refusal costs an operator a re-author, a
      false accept publishes a credential. The refusal says so rather than
      asserting the value *is* a secret.

    The credential guard is the one worth explaining, because it makes a
    common session un-graduable and that is deliberate. ``web.type.text`` and
    ``web.evaluate.expression`` are parameterized *unconditionally, by name*
    at capture (``secret_params.OPAQUE_VALUE_FIELDS``), so a trace holding
    either carries the marker whether or not the value was secret — and the
    marker records that something was withheld, not which credential set fills
    it, so there is nothing to resolve it *against*. Refusing beats the two
    alternatives: rendering the marker into the draft would hand the operator
    a document ingestion rejects (``_carries_credential_hole``), breaking
    SPEC-044's invariant that the operator always holds a format-valid file;
    and inventing a credential-set name would fabricate a reference the trace
    does not support, producing a flow that ingests and then fails closed at
    replay. The remedy is structural and is what R-2 built for, but it is worth
    being precise about *when* it applies, because it is not an in-session fix:
    nothing resolves a hole already in the trace. The operator authors the
    credential through ``web.fill_credential`` — the reference-only entry, and
    read-tier, so the trace never captures it — instead of typing it, and adds
    the credential step to the draft when merging it. That is why the refusal
    says "re-author" rather than "resolve".
    """
    ordered = _ordered(steps)
    declaration = _declaration_order(declared_at, ordered)
    if not ordered:
        return BlastRadius(
            graduable=False,
            refusals=(
                "the session has no captured authoring trace — a flow can only "
                "be graduated from mutating steps a human approved while the "
                "session ran",
            ),
            step_count=0,
            max_steps=max_steps,
            web_target=None,
            browser_steps=0,
            unguarded_positions=(),
            declaration=declaration,
        )

    refusals: list[str] = []
    step_count = len(ordered)
    if step_count > max_steps:
        refusals.append(
            f"{step_count} captured steps exceed the {max_steps}-step budget a "
            f"bound flow replays under, so the graduated flow would be refused "
            f"part-way through mutating"
        )

    target_origin = origin_of_url(target) if target else None
    browser_steps = 0
    unguarded: list[int] = []
    unverified: list[int] = []
    drifted: list[str] = []
    read_tier: list[str] = []
    holes: list[str] = []
    oversized: list[int] = []
    long_names: list[int] = []
    leaked: list[str] = []

    for step in ordered:
        position = step.get("position")
        tool_name = str(step.get("tool_name") or "")
        raw_args = step.get("args")
        args = raw_args if isinstance(raw_args, dict) else {}
        where = f"step {position} ({tool_name or 'unknown tool'})"

        holes.extend(f"{where} {path}" for path in _hole_paths(args))
        if len(tool_name) > MAX_STEP_TOOL_CHARS or not tool_name:
            long_names.append(position)
        try:
            encoded = json.dumps(
                {"tool": tool_name, "args": args}, ensure_ascii=False, sort_keys=True
            )
        except (TypeError, ValueError):
            # Not JSON-compatible, so it is not storable in the ``steps``
            # JSONB column either: refused here rather than rendered into a
            # document ingestion would then reject.
            oversized.append(position)
            continue
        if any(pattern.search(encoded) for pattern in REDACTION_VALUE_PATTERNS):
            # R-2's capture-time parameterization is *name*-based, so a
            # literal under an argument name the vocabulary does not know is
            # stored verbatim — and ``KNOWN_SAFE_FIELDS`` positively exempts
            # some names from placeholdering at all (``web.select.value``).
            # The frontmatter ``steps`` list is the authoritative replay copy
            # and is never scrubbed, because a redacted argument would replay
            # the wrong value, so the body's ``[REDACTED]`` copy cannot be the
            # control here: it would hide the leak from the reviewer while the
            # value itself rode into the artifact they merge. Refusing is the
            # posture the credential hole below already takes. Scanned on the
            # serialized step because that is the exact text the document
            # carries, and on the same shape vocabulary ``postprocess``
            # redacts the body with rather than a second notion of what a
            # secret looks like.
            leaked.append(where)

        if tool_name.startswith(BROWSER_TOOL_PREFIX):
            browser_steps += 1
            if tool_name not in BROWSER_WRITE_TOOLS:
                # Derived rather than listed: ``web.*`` is the whole browser
                # surface and ``BROWSER_WRITE_TOOLS`` its complete write
                # subset, so a ``web.*`` tool outside that set is read-tier by
                # construction.
                #
                # That deliberately includes ``web.fill_credential`` — the
                # credential-reference entry the hole refusal below names as
                # the remedy. It is auto-allowed read-tier
                # (``kernel_middleware.DEFAULT_AUTO_ALLOWED_TOOLS``), so R-2's
                # ``tools:mutate`` gate never captures it and a graduated flow's
                # trace never contains one; a human adds the reference step at
                # merge time instead. Seeing it here therefore means the tier
                # gate leaked, exactly as for any other read-tier step, and
                # refusing is the check that says so.
                read_tier.append(where)
            observed = step.get("flow_origin")
            observed_origin = origin_of_url(observed) if observed else None
            if observed_origin is None:
                unverified.append(position)
            elif target_origin is not None and observed_origin != target_origin:
                drifted.append(f"{where} landed on {observed_origin}")
        else:
            unguarded.append(position)

    # Measured on the exact list the document will carry, and on ingestion's
    # own basis — ``len(json.dumps(steps))`` over the whole list with the
    # default ``ensure_ascii`` — rather than summed per step in UTF-8 bytes.
    # The two differ by more than the list's own punctuation: ``ensure_ascii``
    # escapes a non-ASCII character to six ``\uXXXX`` characters where UTF-8
    # encodes a BMP character in three bytes, so a CJK-heavy trace measured in
    # bytes here can come to half of what skills-hub counts. That is not a
    # rounding difference but a window covering the upper half of the budget,
    # and the failure it produced was a misdiagnosis rather than a near miss:
    # the draft passed here, skills-hub rejected it, and the route reported a
    # 502 "renderer and ingestion disagree" platform fault for what was an
    # ordinary oversize trace. Skipped when a step was not JSON-compatible at
    # all — that refusal already names it, and there is no list to serialize.
    encoded_bytes = 0
    if not oversized:
        try:
            encoded_bytes = len(json.dumps(_steps_payload(ordered)))
        except (TypeError, ValueError):  # pragma: no cover - defensive
            # Unreachable today: every step's own ``{"tool", "args"}`` dump
            # succeeded above and ``_steps_payload`` builds the list from
            # exactly those two keys. Kept so a future change to the payload
            # shape degrades to the not-JSON-compatible refusal — which would
            # then be the accurate diagnosis — rather than raising inside the
            # endpoint.
            oversized.extend(step.get("position") for step in ordered)

    if browser_steps and target_origin is None:
        refusals.append(
            "the session's browser steps have no declared target to be "
            "corroborated against — declare one when opening a "
            "develop-as-you-go session"
        )
    if read_tier:
        refusals.append(
            "read-tier step(s) in a write-class trace: "
            + ", ".join(read_tier)
            + " — a read-tier call must not reach an authoring trace"
        )
    if long_names:
        refusals.append(
            f"step(s) {', '.join(str(p) for p in long_names)} carry a tool name "
            f"the skill contract cannot hold"
        )
    if unverified:
        refusals.append(
            "step(s) "
            + ", ".join(str(position) for position in unverified)
            + " have no observed origin, so nothing proves the mutation landed "
            "on the declared target — an unverified step is never treated as a "
            "corroborated one"
        )
    if drifted:
        refusals.append(
            "step(s) landed outside the declared target's origin: "
            + ", ".join(drifted)
        )
    if holes:
        refusals.append(
            "step(s) still carry an unresolved credential hole "
            f"({TRACE_CREDENTIAL_PLACEHOLDER}): "
            + ", ".join(holes)
            + " — the value was withheld at capture and the platform cannot "
            "know which credential set fills it, and nothing resolves a hole "
            "already in the trace; re-author these steps filling the "
            "credential through web.fill_credential rather than typing it, and "
            "add that reference step when you merge the draft"
        )
    if leaked:
        refusals.append(
            "step(s) carry an argument shaped like a secret literal — a "
            "private key block, a JWT, an Authorization header value or an AWS "
            "access key id: "
            + ", ".join(leaked)
            + ". It was captured under an argument name the credential "
            "vocabulary does not know, so it was stored verbatim instead of "
            "parameterized, and the rendered step list is never scrubbed "
            "because a redacted argument would replay the wrong value. If it "
            "is a credential, re-author these steps passing it through "
            "web.fill_credential rather than as an argument. The match is by "
            "shape, so a value that only looks like one is refused as well — a "
            "dropdown option reading 'Basic Authentication', which web.select "
            "stores verbatim by design, cannot be told apart from a real "
            "Authorization value here. That over-catch is deliberate and fails "
            "safe: a false refusal costs a re-author, a false accept publishes "
            "a credential into a repository and replays it live."
        )
    if encoded_bytes > MAX_STEPS_BYTES:
        refusals.append(
            f"the step list serializes to {encoded_bytes} bytes, over the "
            f"{MAX_STEPS_BYTES // 1024} KiB the skill contract allows"
        )
    if oversized:
        refusals.append(
            f"step(s) {', '.join(str(p) for p in oversized)} carry arguments "
            "that are not JSON-compatible, so they cannot be stored as a "
            "replay step"
        )

    return BlastRadius(
        graduable=not refusals,
        refusals=tuple(refusals),
        step_count=step_count,
        max_steps=max_steps,
        # Emitted only for a flow that actually has a browser step: a
        # ``web_target`` is what ``bind_flow`` binds a browser flow from, so
        # declaring one on a pure-infra flow would advertise a binding the
        # flow never uses. A declared target with no browser step is recorded
        # in the report and named in the body instead.
        web_target=target if browser_steps and target_origin is not None else None,
        browser_steps=browser_steps,
        unguarded_positions=tuple(unguarded),
        declaration=declaration,
    )


def _steps_payload(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The trace as the skill contract's replay step list.

    ``expect`` is deliberately never emitted: the trace records what ran, not
    what anyone expected to happen afterwards, and inventing a post-condition
    would be exactly the synthesis R-4 forbids. A human completing the draft
    may add one.
    """
    return [
        {
            "tool": str(step.get("tool_name") or ""),
            # Sorted keys: the store returns a JSONB object whose key order is
            # not part of its contract, and a draft that differed only in key
            # order between two graduations of the same trace would not be
            # deterministic in the sense R-4 means.
            "args": json.loads(
                json.dumps(
                    step.get("args") if isinstance(step.get("args"), dict) else {},
                    ensure_ascii=False,
                    sort_keys=True,
                )
            ),
        }
        for step in steps
    ]


def _yaml_frontmatter(frontmatter: dict[str, Any], steps: list[dict[str, Any]]) -> str:
    """Emit the v2 frontmatter as YAML, strings JSON-quoted.

    Hand-rolled like ``skill_draft._yaml_frontmatter`` rather than dumped,
    because agent-platform holds no YAML dependency — and every scalar is
    JSON-quoted, which is safe by construction: JSON is a subset of YAML, so
    a quoted string or a flow mapping always parses back to the value that
    was written, whatever it contains.
    """
    lines = [
        f"title: {json.dumps(frontmatter['title'], ensure_ascii=False)}",
        f"description: {json.dumps(frontmatter['description'], ensure_ascii=False)}",
    ]
    tags = frontmatter.get("tags")
    if tags:
        lines.append(
            "tags: ["
            + ", ".join(json.dumps(tag, ensure_ascii=False) for tag in tags)
            + "]"
        )
    web_target = frontmatter.get("web_target")
    if web_target:
        lines.append(f"web_target: {json.dumps(web_target, ensure_ascii=False)}")
    lines.append(f"risk_class: {WRITE_RISK_CLASS}")
    lines.append(f"kind: {EXECUTABLE_FLOW_KIND}")
    lines.append("steps:")
    for step in steps:
        lines.append(f"  - tool: {json.dumps(step['tool'], ensure_ascii=False)}")
        lines.append(
            "    args: " + json.dumps(step["args"], ensure_ascii=False, sort_keys=True)
        )
    return "\n".join(lines) + "\n"


def _render_args(args: dict[str, Any]) -> str:
    encoded = json.dumps(args, ensure_ascii=False, sort_keys=True)
    if len(encoded) > _MAX_RENDERED_ARG_CHARS:
        return encoded[:_MAX_RENDERED_ARG_CHARS] + " …"
    return encoded


def _declaration_sentence(report: BlastRadius) -> str:
    if report.declaration == DECLARATION_PRECEDED:
        return (
            "before the first captured step, so it is an authorization scope "
            "the session acted under"
        )
    if report.declaration == DECLARATION_POSTDATED:
        return (
            "**after** the first captured step — the scope was fitted to a "
            "trace that had already begun, so treat it as a claim about the "
            "past rather than an authorization"
        )
    return (
        "at an indeterminate point relative to the first captured step (both "
        "stamps are second-precision, so a same-second declaration cannot be "
        "ordered)"
    )


def build_executable_flow_draft(
    steps: list[dict[str, Any]],
    *,
    report: BlastRadius,
    session_id: str,
    title: str | None = None,
    declared_target: str | None = None,
) -> tuple[str, str]:
    """Render a re-validated trace into an executable-flow skill draft.

    Returns ``(markdown, slug)``. Deterministic over its inputs — no model
    call, and no step the trace does not contain — so graduating the same
    trace twice yields the same document *on the same UTC date*. The
    provenance block's ``date:`` is the one wall-clock input, and it is why a
    re-export across midnight differs in bytes while staying identical in
    meaning.

    The body is a runbook rather than a restatement of the frontmatter: the
    preview's rendered view strips the YAML fence (it is file metadata for the
    skills repo), so the step list a reviewer reads by default lives here.
    """
    ordered = _ordered(steps)
    payload = _steps_payload(ordered)
    target = report.web_target
    derived_title = (title or "").strip()
    if not derived_title:
        # Fall back to something that names the scope rather than a generic
        # string: the operator sees this as a filename and a reviewer as the
        # skill's identity in the repo.
        derived_title = (
            f"{origin_of_url(target) or origin_of_url(declared_target) or 'infra'} "
            "executable flow"
        )
    tools = [step["tool"] for step in payload]
    distinct = list(dict.fromkeys(tools))
    description = (
        f"Replays {report.step_count} approved mutating step(s) captured from "
        f"an operator session"
        + (f" against {target}" if target else "")
        + f": {', '.join(distinct[:6])}"
        + (" …" if len(distinct) > 6 else "")
        + "."
    )

    # ``postprocess`` is SPEC-044's public guardrail pair — it clamps
    # title/description/tags to the contract caps and redacts + truncates the
    # body — reused here so both draft producers scrub with one vocabulary
    # rather than one of them growing a second, divergent notion of "safe".
    # One call, over the real fields: the runbook is built first and handed in
    # as the body.
    safe, safe_body = postprocess(
        {
            "title": derived_title,
            "description": description,
            "tags": list(GRADUATION_TAGS),
        },
        _runbook(
            ordered,
            report=report,
            session_id=session_id,
            declared_target=declared_target,
        ),
    )
    frontmatter: dict[str, Any] = dict(safe)
    if target:
        frontmatter["web_target"] = target

    body = provenance_block(session_id, None, MODE_GRADUATED) + "\n\n" + safe_body

    markdown = (
        "---\n"
        + _yaml_frontmatter(frontmatter, payload)
        + "---\n\n"
        + body
        + "\n"
    )
    return markdown, slug_from_title(frontmatter["title"])


def _runbook(
    ordered: list[dict[str, Any]],
    *,
    report: BlastRadius,
    session_id: str,
    declared_target: str | None,
) -> str:
    """The human-readable replay runbook, pre-trimmed to the body's budget.

    Step arguments are elided past ``_MAX_RENDERED_ARG_CHARS`` and the whole
    runbook is trimmed to leave room for the provenance block the caller
    prepends, so a large argument cannot push the assembled body through its
    own 64 KiB cap — the authoritative copy is the frontmatter's ``steps``
    list either way. Redaction is the caller's ``postprocess`` call.
    """
    lines: list[str] = ["## Replay runbook", ""]
    lines.extend(
        [
            f"- Session: `{session_id}`",
            f"- Steps: {report.step_count} of a {report.max_steps}-step replay budget",
        ]
    )
    if report.web_target:
        lines.append(f"- Declared target: `{report.web_target}`")
    elif declared_target:
        lines.append(
            f"- Declared target: `{declared_target}` — not emitted as "
            "`web_target`, because this trace holds no browser step for a "
            "flow binding to guard"
        )
    else:
        lines.append("- Declared target: none (a non-browser flow needs none)")
    lines.append(f"- Target declared: {_declaration_sentence(report)}")
    if report.browser_steps:
        lines.append(
            f"- Origin guard: {report.browser_steps} browser step(s) "
            "corroborated against the declared target's origin"
        )
    if report.unguarded_positions:
        positions = ", ".join(str(p) for p in report.unguarded_positions)
        lines.append(
            f"- Outside the origin guard: step(s) {positions} are not browser "
            "interactions, so the flow's target does not bound them; each "
            "replays under its own per-action approval until a non-browser "
            "flow binding lands"
        )
    lines.extend(["", "### Steps", ""])
    for index, step in enumerate(ordered, start=1):
        args = step.get("args") if isinstance(step.get("args"), dict) else {}
        lines.append(
            f"{index}. `{step.get('tool_name')}` — `{_render_args(args)}`"
        )
    lines.extend(
        [
            "",
            "### Before you merge this",
            "",
            "- The platform does not publish it. Merge it into the team's Git "
            "skills repo, where ingestion validates it against the skill "
            "contract and it becomes replayable.",
            "- `risk_class: write` is unconditional for this class: replaying "
            "the flow binds a flow authority and parks exactly one "
            "confirmation card, after which every step is individually signed "
            "and gateway-guarded.",
            "- The step list holds only *mutating* steps, so it carries no "
            "binding step. `web.navigate` is read-tier and was never captured, "
            "yet it is the only call that binds a flow — and binding is what "
            "arms the origin guard and the step budget above. Add one as step "
            "1: `web.navigate` to the declared target carrying this skill's "
            "`skill_id` (`<source_id>/<slug>`, assigned when you merge it). "
            "Without it the flow never binds and every write parks its own "
            "confirmation card instead of the one described above.",
            "- Credentials resolve at replay from named credential sets. "
            "Graduation refuses a step still carrying a "
            "`<credential-reference>` hole, and a step whose argument is "
            "shaped like a secret literal (a private key block, a JWT, an "
            "Authorization value, an AWS access key id), but a literal under an "
            "argument name *and* shape the platform does not recognize is "
            "**not** detectable by either check — read the step arguments "
            "before merging. The frontmatter's `steps` list is the "
            "authoritative replay copy and is never scrubbed, since a redacted "
            "argument would replay the wrong value. Note that "
            "`web.fill_credential` is read-tier and is therefore **not** in "
            "the step list above — if the session filled a credential, add "
            "that reference step here, naming the set and the field, or the "
            "flow will not authenticate.",
            "- Every step listed above was approved by a human and signed "
            "before it ran. Nothing here was synthesized, and a step this "
            "session did not run cannot appear in it.",
        ]
    )
    # ``MAX_BODY_BYTES`` bounds the assembled body including the provenance
    # block the caller prepends, so leave it room rather than trusting the
    # step count to stay small. ``decode(…, "ignore")`` drops a partial
    # multi-byte character the byte slice may have cut in half.
    budget = MAX_BODY_BYTES - 512
    return "\n".join(lines).encode("utf-8")[:budget].decode("utf-8", "ignore")
