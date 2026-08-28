"""Optional clearly-labeled prose layer for operations documents (SPEC-039 R-4).

When requested, an LLM narrative accompanies the document's digest. The
prompt contract feeds the model the digest JSON only — never raw
transcripts, evidence payloads, or argument bodies — so the prose can
only paraphrase verified facts. Generation is fail-soft: any model
error or timeout yields ``prose_status=failed`` and the document ships
digest-only; prose generation never fails document creation.

The narrative uses the runtime's default model (no per-document model
selection surface) through the same provider path as chat turns, with
a hard timeout so a hung model can never hold the create route.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

LOGGER = logging.getLogger(__name__)

PROSE_TIMEOUT_SECONDS = 30.0

# The guardrail is the prompt contract: the only input the model ever
# sees is the assembled digest JSON, so it can paraphrase facts but
# cannot fabricate from conversation content that never reaches it.
# SPEC-040 R-2 tightens the contract with explicit anchoring rules:
# every statement must trace to a digest section, and nothing absent
# from the input (record ids, causes, recommendations) may appear.
# The v0.23.3 tuning keeps those guardrails but asks for a human
# handover voice — precise yet concise — and a first-line SUMMARY
# marker that parse_blurb extracts as the document's one-liner.
_PROMPT_TEMPLATE = """\
You are writing shift-handover notes for the colleague taking over \
the next shift. Write like an experienced operator briefing a peer: \
plain, direct, and human — not like a status report.

Start with exactly one line beginning with "SUMMARY:" — a single \
sentence of at most thirty words capturing the shift's overall story \
at a glance.

Then write the recap itself in at most three short paragraphs (about \
150 words in total). Lead with what matters most to the relieving \
operator: what happened, what was decided and executed, and what \
they inherit. Prefer the handover section when present, then the \
sessions. Weave counts in only where they carry meaning — never \
enumerate every number.

Anchoring rules: state only facts present in the digest; tie each \
statement to the digest section it comes from (handover, sessions, \
confirmations, executions, open items); never introduce record ids, \
causes, recommendations, or any detail the digest does not contain. \
If the handover section reports quiet=true, say plainly that the \
shift had no recorded decisions or executions. No headings, no \
markdown.

JSON digest:
{digest_json}
"""

# The blurb is bounded: a runaway first line can never bloat the
# envelope listing or the detail card.
BLURB_MAX_CHARS = 240

_SUMMARY_MARKER = "SUMMARY:"


def parse_blurb(text: str) -> tuple[str | None, str]:
    """Split the model reply into ``(blurb, prose)``.

    The prompt contract asks for a first line starting with the
    ``SUMMARY:`` marker; the rest is the narrative. Parsing is
    forgiving — a reply without the marker (or with it anywhere but
    the first non-empty line) leaves the whole text as prose and no
    blurb, so the fail-soft posture never worsens.
    """
    stripped = (text or "").strip()
    if not stripped:
        return None, ""
    lines = stripped.splitlines()
    for index, line in enumerate(lines):
        candidate = line.strip()
        if not candidate:
            continue
        if candidate.upper().startswith(_SUMMARY_MARKER):
            blurb = candidate[len(_SUMMARY_MARKER):].strip()
            blurb = blurb[:BLURB_MAX_CHARS].strip() or None
            remainder = "\n".join(lines[index + 1:]).strip()
            # Nothing after the marker: the one-liner stands as the
            # prose (without the marker) so the narrative panel never
            # renders empty.
            return blurb, remainder or blurb or stripped
        return None, stripped
    return None, stripped


def build_prose_prompt(document_type: str, digest: dict[str, Any]) -> str:
    """Build the digest-only prompt; the digest is the sole input.

    ``document_type`` rides the prompt so the recap framing can adapt
    per type later without changing the prompt contract (digest-only).
    """
    return _PROMPT_TEMPLATE.format(
        digest_json=json.dumps(
            {"document_type": document_type, "digest": digest},
            sort_keys=True,
            default=str,
        )
    )


async def generate_prose(
    kernel: Any,
    document_type: str,
    digest: dict[str, Any],
) -> tuple[str | None, str | None, str]:
    """Generate the narrative; returns ``(prose, blurb, prose_status)``.

    ``prose_status`` is ``included`` on success and ``failed`` on any
    error (model build, transport, timeout, empty reply) — the caller
    persists the document digest-only in that case. ``blurb`` is the
    one-line SUMMARY extraction (``None`` when the model skipped the
    marker); it never fails the generation on its own.
    """
    from agent_service.runtime_kernel import extract_text
    from agentscope.message import Msg, TextBlock

    try:
        model = kernel._build_model(None)
        prompt = build_prose_prompt(document_type, digest)
        message = Msg(
            name="user",
            role="user",
            content=[TextBlock(type="text", text=prompt)],
        )
        response = await asyncio.wait_for(
            model([message]), timeout=PROSE_TIMEOUT_SECONDS
        )
        # A streaming-configured model yields an async generator; drain
        # it so the prose path behaves identically either way.
        if hasattr(response, "__aiter__"):
            content = None
            async for chunk in response:
                content = getattr(chunk, "content", content)
        else:
            content = getattr(response, "content", None)
        text = extract_text(content) if content is not None else ""
        text = (text or "").strip()
        if not text:
            raise RuntimeError("prose generation returned an empty reply")
        blurb, prose = parse_blurb(text)
        return prose, blurb, "included"
    except Exception as exc:  # noqa: BLE001 — fail-soft by contract
        LOGGER.warning("prose generation failed: %s", exc)
        return None, None, "failed"
