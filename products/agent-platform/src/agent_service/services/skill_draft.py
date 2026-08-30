"""Skill-draft generation from a session's durable facts (SPEC-044 R-1/R-6).

One route over the caller's own session assembles the generation input
deterministically — the same session-fact digest the shift-summary uses,
plus the validated triage report when the session is incident-linked —
runs one bounded LLM call, and returns a Markdown skill draft. The prompt
receives the digest bundle only (never raw transcripts, alert payloads, or
evidence payloads); facts are copied verbatim, the model only shapes them.

Content guardrails are deterministic, never model obedience: the model
proposes within a fenced ``skill-frontmatter`` contract, and the platform
parses, applies the gateway's redaction vocabulary, enforces the Skill
Format v1 caps, and validates the result on skills-hub's own code path.
Any generation or parse failure degrades to the facts-only skeleton, which
is always format-valid — generation never raises a 500.

The draft is ephemeral: this module builds the Markdown string and returns
it; nothing is persisted anywhere on the platform.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from agent_service.metadata import SERVICE_VERSION
from agent_service.services.incident_client import (
    IncidentClientError,
    fetch_incident_bundle,
)
from agent_service.services.shift_summary import (
    build_digest as build_session_digest,
)

LOGGER = logging.getLogger(__name__)

SKILL_DRAFT_TIMEOUT_SECONDS = 30.0

# Skill Format v1 caps (shared/shared-contracts/skill-format.md) — the same
# bounds skills-hub ingestion enforces; post-processing clamps to them
# regardless of model obedience.
MAX_TITLE_CHARS = 200
MAX_DESCRIPTION_CHARS = 500
MAX_TAG_CHARS = 64
MAX_TAGS = 10
MAX_VERSION_CHARS = 64
MAX_SOURCE_URL_CHARS = 2048
MAX_BODY_BYTES = 65536

REDACTION_MARKER = "[REDACTED]"

# The gateway's redaction vocabulary (tool_gateway/tools/redaction.py): the
# same shape-based, key-agnostic patterns tool output receives, applied to
# the model-written body before validation.
_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
    ),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9+/=._~-]{8,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)

# Incident-linked sessions follow the triage naming convention
# (incident-service triage.py): ``incident-<id>`` with a per-operator
# fallback suffix ``incident-<id>--<slug>``.
_INCIDENT_SESSION_PREFIX = "incident-"
_INCIDENT_ID_PATTERN = re.compile(r"^inc-[a-z0-9-]+$")

# The model emits one fenced ``skill-frontmatter`` JSON block plus the
# Markdown body (the SPEC-015 fenced-contract pattern).
_FRONTMATTER_FENCE = re.compile(r"```skill-frontmatter\s*\n(.*?)\n?\s*```", re.DOTALL)

_SEGMENT_CLEANUP = re.compile(r"[^a-z0-9]+")

MODE_GENERATED = "generated"
MODE_SKELETON = "skeleton"


class SkillFrontmatter(BaseModel):
    """Fenced-contract frontmatter, validated within Skill Format v1 caps."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS)
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_CHARS)
    tags: list[str] | None = Field(default=None, max_length=MAX_TAGS)
    version: str | None = Field(default=None, max_length=MAX_VERSION_CHARS)

    @field_validator("title", "description")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("tags")
    @classmethod
    def _tags_shape(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        for tag in value:
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError("tags must be non-empty strings")
            if len(tag) > MAX_TAG_CHARS:
                raise ValueError(f"tag exceeds {MAX_TAG_CHARS} chars")
        return value


def incident_id_from_session(session_id: str) -> str | None:
    """The covered incident id when the session is incident-linked."""
    if not session_id.startswith(_INCIDENT_SESSION_PREFIX):
        return None
    candidate = session_id[len(_INCIDENT_SESSION_PREFIX):].split("--", 1)[0]
    return candidate if _INCIDENT_ID_PATTERN.match(candidate) else None


async def build_skill_draft_bundle(
    settings: Any,
    user_id: str,
    session_id: str,
    request_id: str | None,
) -> tuple[dict[str, Any], str | None]:
    """Assemble the generation input: the session digest, digest-only.

    Reuses the shift-summary session-fact assembly (sessions,
    confirmations, executions, evidence counts, handover facts) and adds
    the validated triage report through the SPEC-043 incident client when
    the session is incident-linked. Raw transcripts, raw alert payloads,
    and evidence payloads never enter the bundle. Incident-leg failures
    degrade to the digest alone — the triage section is an enrichment,
    never a generation dependency.
    """
    digest, _ = build_session_digest(user_id, [session_id], can_view_foreign=False)
    bundle: dict[str, Any] = dict(digest)
    incident_id = incident_id_from_session(session_id)
    if incident_id is None:
        return bundle, None
    try:
        incident_bundle = await fetch_incident_bundle(
            settings, request_id, incident_id
        )
    except IncidentClientError as exc:
        LOGGER.warning(
            "skill-draft triage leg degraded for %s: %s", incident_id, exc
        )
        return bundle, incident_id
    envelope = {
        key: value
        for key, value in (incident_bundle.get("incident") or {}).items()
        if key != "triage_raw"  # raw alert payloads never reach the prompt
    }
    bundle["incident"] = {
        "envelope": envelope,
        "triage_report": incident_bundle.get("report"),
    }
    return bundle, incident_id


_PROMPT_TEMPLATE = """\
You are drafting a reusable operations skill for the team's skills \
repository from the record of one troubleshooting session. Write it for \
the colleague who meets the same problem next: plain, direct, procedural.

Output contract — two parts, in order:

1. Exactly one fenced code block tagged skill-frontmatter containing a \
single JSON object with the keys "title" (string, at most 200 characters), \
"description" (string, at most 500 characters), "tags" (list of at most 10 \
short strings), and optionally "version" (string). No other keys.

2. The Markdown body of the skill after the fenced block: when to use it, \
what to check, and what the record shows worked. Use short headings and \
lists; keep it under a few hundred lines.

Anchoring rules: state only facts present in the digest bundle; every \
claim must trace to the sessions, handover, or incident section. Never \
invent steps, causes, or numbers the record does not support. Never \
include secrets, credentials, tokens, hostnames, IP addresses, or \
customer-identifying data in the draft.

{retry_hint}\
JSON digest bundle:
{bundle_json}
"""


def build_skill_draft_prompt(
    bundle: dict[str, Any], rejection_reason: str | None = None
) -> str:
    """Build the digest-only prompt; the digest bundle is the sole input.

    On the bounded regeneration the rejection reason rides the prompt so
    the model can correct the specific contract violation.
    """
    retry_hint = ""
    if rejection_reason:
        retry_hint = (
            "The previous draft was rejected by the format validator with "
            f"reason: {rejection_reason}. Produce a corrected draft that "
            "satisfies the output contract.\n\n"
        )
    return _PROMPT_TEMPLATE.format(
        retry_hint=retry_hint,
        bundle_json=json.dumps(bundle, sort_keys=True, default=str),
    )


def parse_model_output(text: str) -> tuple[dict[str, Any], str] | None:
    """Parse the fenced contract; ``(frontmatter, body)`` or ``None``.

    Any deviation — missing fence, invalid JSON, unknown keys, out-of-
    bounds fields — degrades to the skeleton; parsing never raises.
    """
    match = _FRONTMATTER_FENCE.search(text or "")
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        frontmatter = SkillFrontmatter.model_validate(payload).model_dump(
            exclude_none=True
        )
    except ValidationError:
        return None
    after = text[match.end():].strip()
    before = text[: match.start()].strip()
    body = after or before
    if not body:
        return None
    return frontmatter, body


def _redact_text(text: str) -> str:
    for pattern in _VALUE_PATTERNS:
        text = pattern.sub(REDACTION_MARKER, text)
    return text


def _truncate_utf8(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def postprocess(frontmatter: dict[str, Any], body: str) -> tuple[dict[str, Any], str]:
    """Deterministic content guardrails (SPEC-044 R-6).

    The redaction vocabulary scrubs the model output and the Skill Format
    caps are clamped regardless of model obedience — safety is never a
    property of the model following instructions.
    """
    safe = {
        "title": str(frontmatter.get("title") or "").strip()[:MAX_TITLE_CHARS],
        "description": str(frontmatter.get("description") or "").strip()[
            :MAX_DESCRIPTION_CHARS
        ],
    }
    tags = frontmatter.get("tags")
    if isinstance(tags, list):
        cleaned = [tag.strip()[:MAX_TAG_CHARS] for tag in tags if str(tag).strip()]
        safe["tags"] = cleaned[:MAX_TAGS]
    version = frontmatter.get("version")
    if isinstance(version, str) and version.strip():
        safe["version"] = version.strip()[:MAX_VERSION_CHARS]
    scrubbed = _redact_text(body)
    return safe, _truncate_utf8(scrubbed, MAX_BODY_BYTES)


def slug_from_title(title: str) -> str:
    """The suggested filename slug (the slug-path identity rule)."""
    cleaned = _SEGMENT_CLEANUP.sub("-", (title or "").lower()).strip("-")
    return cleaned or "skill-draft"


def provenance_block(
    session_id: str, incident_id: str | None, mode: str
) -> str:
    """Deterministic HTML-comment provenance (SPEC-044 Q-5).

    Body content, not frontmatter — the team may keep or strip it on
    merge without breaking ingestion.
    """
    lines = [
        "<!--",
        "Skill draft generated by the Luban AIOps platform.",
        f"session: {session_id}",
    ]
    if incident_id:
        lines.append(f"incident: {incident_id}")
    lines.extend(
        [
            f"date: {datetime.now(UTC).strftime('%Y-%m-%d')}",
            f"platform_version: {SERVICE_VERSION}",
            f"mode: {mode}",
            "-->",
        ]
    )
    return "\n".join(lines)


def _yaml_frontmatter(frontmatter: dict[str, Any]) -> str:
    """Emit the five contract keys as YAML (strings JSON-quoted)."""
    lines = [
        f"title: {json.dumps(frontmatter['title'], ensure_ascii=False)}",
        f"description: {json.dumps(frontmatter['description'], ensure_ascii=False)}",
    ]
    tags = frontmatter.get("tags")
    if tags:
        lines.append(
            "tags: [" + ", ".join(json.dumps(tag, ensure_ascii=False) for tag in tags) + "]"
        )
    version = frontmatter.get("version")
    if version:
        lines.append(f"version: {json.dumps(version, ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


def assemble_markdown(
    frontmatter: dict[str, Any],
    body: str,
    session_id: str,
    incident_id: str | None,
    mode: str,
) -> tuple[str, str]:
    """Assemble the validated-ready draft; returns ``(markdown, slug)``.

    Post-processing runs here so every path — generated, regenerated, and
    skeleton — passes the identical guardrails before validation.
    """
    safe_frontmatter, safe_body = postprocess(frontmatter, body)
    safe_body = provenance_block(session_id, incident_id, mode) + "\n\n" + safe_body
    safe_body = _truncate_utf8(safe_body, MAX_BODY_BYTES)
    markdown = (
        "---\n"
        + _yaml_frontmatter(safe_frontmatter)
        + "---\n\n"
        + safe_body
        + "\n"
    )
    return markdown, slug_from_title(safe_frontmatter["title"])


# --- Facts-only skeleton (always format-valid) --------------------------------


def build_skeleton(bundle: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Deterministic facts-only draft; the degradation for any generation
    or parse failure. Contract frontmatter from session/incident facts,
    evidence/outcome tables copied verbatim from the digest bundle.
    """
    sessions = bundle.get("sessions") or []
    session = sessions[0] if sessions else {}
    incident = bundle.get("incident") or {}
    envelope = incident.get("envelope") or {}
    report = incident.get("triage_report") or {}

    title_seed = envelope.get("title") or session.get("title") or ""
    title = (
        f"Triage runbook: {title_seed}" if envelope.get("title") else title_seed
    ).strip()[:MAX_TITLE_CHARS] or "Session skill draft"

    description_seed = (
        report.get("summary") or envelope.get("summary") or ""
    )
    if description_seed:
        description = description_seed.strip()[:MAX_DESCRIPTION_CHARS]
    else:
        description = (
            "Facts-only skill draft assembled from the session record; no "
            "triage narrative was available."
        )

    tags: list[str] = ["triage"]
    severity = envelope.get("severity")
    if isinstance(severity, str) and severity.strip():
        tags.insert(0, severity.strip()[:MAX_TAG_CHARS])

    lines: list[str] = ["# " + title, ""]
    if envelope:
        lines.append("## Context")
        lines.append("")
        lines.append(
            f"- Incident: {envelope.get('incident_id', 'unknown')} "
            f"(severity: {envelope.get('severity', 'unknown')}, "
            f"status: {envelope.get('status', 'unknown')})"
        )
        lines.append("")
    if isinstance(report, dict) and report:
        hypotheses = report.get("hypotheses") or []
        next_steps = report.get("next_steps") or []
        if hypotheses:
            lines.append("## Hypotheses")
            lines.append("")
            for hypothesis in hypotheses:
                lines.append(f"- {hypothesis}")
            lines.append("")
        if next_steps:
            lines.append("## Next steps")
            lines.append("")
            for step in next_steps:
                step_title = step.get("title") if isinstance(step, dict) else step
                lines.append(f"- {step_title}")
            lines.append("")

    handover = bundle.get("handover") or {}
    lines.append("## Outcome")
    lines.append("")
    if handover.get("quiet"):
        lines.append("No recorded decisions or executions in this session.")
        lines.append("")
    else:
        decisions = handover.get("decisions") or []
        executions = handover.get("executions") or []
        if decisions:
            lines.append("| decision | action | outcome |")
            lines.append("| --- | --- | --- |")
            for row in decisions:
                lines.append(
                    f"| {row.get('confirm_id', '')} | {row.get('action', '')} "
                    f"| {row.get('decision', '')} |"
                )
            lines.append("")
        if executions:
            lines.append("| execution | tool | receipt |")
            lines.append("| --- | --- | --- |")
            for row in executions:
                lines.append(
                    f"| {row.get('execution_id', '')} | {row.get('tool_name', '')} "
                    f"| {row.get('receipt_status', '')} |"
                )
            lines.append("")

    transcript = session.get("transcript")
    evidence = session.get("evidence")
    if isinstance(transcript, dict) or isinstance(evidence, dict):
        lines.append("## Evidence record")
        lines.append("")
        if isinstance(transcript, dict):
            lines.append(f"- Transcript turns: {transcript.get('turn_count', 0)}")
        if isinstance(evidence, dict):
            lines.append(
                f"- Evidence frames: {evidence.get('total_frame_count', 0)}"
            )
        lines.append("")

    frontmatter = {"title": title, "description": description, "tags": tags}
    return frontmatter, "\n".join(lines).strip()


# --- Bounded generation ---------------------------------------------------------


async def generate_skill_draft(
    kernel: Any,
    bundle: dict[str, Any],
    rejection_reason: str | None = None,
) -> tuple[dict[str, Any], str] | None:
    """One bounded model call; ``(frontmatter, body)`` or ``None``.

    Mirrors the ``document_prose.generate_prose`` posture: the runtime's
    default model, a hard timeout, and fail-soft — any error yields
    ``None`` and the caller degrades to the skeleton, never a 500.
    """
    from agent_service.runtime_kernel import extract_text
    from agentscope.message import Msg, TextBlock

    try:
        model = kernel._build_model(None)
        prompt = build_skill_draft_prompt(bundle, rejection_reason)
        message = Msg(
            name="user",
            role="user",
            content=[TextBlock(type="text", text=prompt)],
        )
        response = await asyncio.wait_for(
            model([message]), timeout=SKILL_DRAFT_TIMEOUT_SECONDS
        )
        # A streaming-configured model yields an async generator; drain it
        # so the generation path behaves identically either way.
        if hasattr(response, "__aiter__"):
            content = None
            async for chunk in response:
                content = getattr(chunk, "content", content)
        else:
            content = getattr(response, "content", None)
        text = extract_text(content) if content is not None else ""
        text = (text or "").strip()
        if not text:
            raise RuntimeError("skill-draft generation returned an empty reply")
        return parse_model_output(text)
    except Exception as exc:  # noqa: BLE001 — fail-soft by contract
        LOGGER.warning("skill-draft generation failed: %s", exc)
        return None
