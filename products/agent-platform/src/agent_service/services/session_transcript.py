"""Best-effort session transcript reconstruction (SPEC-022 R-1).

The SPEC-017 kernel state snapshot persists the agent's conversation memory
(``AgentState.context``: an ordered list of messages with ``role`` and
block-structured ``content``). The session read path extracts ordered
chat-text turns from that snapshot so any workspace UI can resume a session
without replaying a live stream.

Reconstruction is best-effort by design: a missing snapshot, corrupt JSON,
or an unknown shape degrades to ``transcript_available: false`` with an
empty transcript — never a 500 and never a fabricated turn. Tool/evidence
frames stay out of scope for v1 transcripts (chat text only); the evidence
panel remains live-stream-scoped.
"""

from __future__ import annotations

import json
import logging

from agent_service.services.agent_state_store import AGENT_STATE_STORE

LOGGER = logging.getLogger(__name__)

# System messages are deployment configuration, not conversation; tool
# frames are out of scope for v1 transcripts.
_TRANSCRIPT_ROLES = frozenset({"user", "assistant"})


def extract_transcript(session_id: str) -> tuple[bool, list[dict[str, str]]]:
    """Return ``(transcript_available, turns)`` for a session.

    Each turn is ``{"role", "content"}`` plus ``created_at`` when the
    snapshot carries one, in conversation order.
    """
    try:
        raw = AGENT_STATE_STORE.load_state(session_id)
        if raw is None:
            return False, []
        state = json.loads(raw)
        messages = state.get("context") if isinstance(state, dict) else None
        if not isinstance(messages, list):
            return False, []
        turns: list[dict[str, str]] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            if role not in _TRANSCRIPT_ROLES:
                continue
            text = _extract_text(message.get("content"))
            if not text:
                continue
            turn: dict[str, str] = {"role": role, "content": text}
            created_at = message.get("created_at")
            if isinstance(created_at, str) and created_at:
                turn["created_at"] = created_at
            turns.append(turn)
        return True, turns
    except Exception as exc:
        LOGGER.warning(
            "transcript extraction failed for session %s: %s", session_id, exc
        )
        return False, []


def _extract_text(content: object) -> str:
    """Flatten a Msg content payload into plain chat text.

    Accepts the legacy string shape and the block list shape; only ``text``
    blocks contribute (thinking/tool blocks are skipped).
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "".join(part for part in parts if part)
    return ""
