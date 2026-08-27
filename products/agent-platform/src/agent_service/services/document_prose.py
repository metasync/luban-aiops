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
_PROMPT_TEMPLATE = """\
You are writing an operational handover recap for a colleague.

Recap the facts in the JSON digest below for a teammate taking over. \
State only what the facts contain: summarize sessions, confirmation \
decisions, execution outcomes, and still-open items. Never invent \
details, causes, or recommendations that the facts do not support. \
Write plain prose in at most six short paragraphs. No headings, no \
markdown.

JSON digest:
{digest_json}
"""


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
) -> tuple[str | None, str]:
    """Generate the narrative; returns ``(prose, prose_status)``.

    ``prose_status`` is ``included`` on success and ``failed`` on any
    error (model build, transport, timeout, empty reply) — the caller
    persists the document digest-only in that case.
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
        return text, "included"
    except Exception as exc:  # noqa: BLE001 — fail-soft by contract
        LOGGER.warning("prose generation failed: %s", exc)
        return None, "failed"
