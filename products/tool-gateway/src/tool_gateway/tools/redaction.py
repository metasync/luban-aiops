"""Tool output redaction (SPEC-009 R-1/R-2).

Code-owned, deterministic redaction applied to every tool result before it
leaves the gateway (the single choke point is ``invoke_tool``). Two layers:

- value patterns: shape-based, key-agnostic matchers for unambiguous
  credential formats (PEM private keys, JWTs, Bearer/Basic values, AWS-style
  access key IDs)
- explicit key list: bounded, exact-name match on sensitive string fields
  (password/secret/token family); the key stays visible, its value is replaced

There is deliberately no operator-editable configuration of the pattern set;
the only knobs are the enable switch and the fail-closed overflow fraction.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from tool_gateway.tools.base import ToolResult

REDACTION_MARKER = "[REDACTED]"

# Value patterns, applied in order (most specific first) so overlapping
# shapes are not double-counted.
_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # PEM private key blocks (spanning lines).
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
    ),
    # JWTs: three base64url segments.
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    # Bearer/Basic credential values.
    re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9+/=._~-]{8,}\b"),
    # AWS-style access key IDs.
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)

# Bounded explicit key list (Q-3 resolution: exact, case-insensitive key-name
# match on string values only). A generic substring matcher was rejected as
# untestable and over-redaction-prone.
_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "api_key",
        "apikey",
        "token",
        "access_key",
        "client_secret",
        "private_key",
        "authorization",
    }
)


@dataclass(frozen=True)
class RedactionStats:
    """Outcome of redacting one tool result payload."""

    spans: int
    original_chars: int
    redacted_chars: int

    def overflow(self, fraction: float) -> bool:
        """Fail-closed: too much of the payload would be redacted (R-2)."""
        if self.original_chars <= 0:
            return False
        return (self.redacted_chars / self.original_chars) > fraction


def _redact_text(text: str) -> tuple[str, int, int]:
    """Apply value patterns to a string. Returns (text, spans, chars)."""
    spans = 0
    redacted_chars = 0
    for pattern in _VALUE_PATTERNS:
        for match in pattern.finditer(text):
            spans += 1
            redacted_chars += len(match.group(0))
        text = pattern.sub(REDACTION_MARKER, text)
    return text, spans, redacted_chars


def _redact_node(node: object) -> tuple[object, int, int]:
    """Recursively redact a JSON-like structure. Returns (node, spans, chars)."""
    spans = 0
    redacted_chars = 0

    if isinstance(node, dict):
        redacted: dict = {}
        for key, value in node.items():
            if (
                isinstance(key, str)
                and key.lower() in _SENSITIVE_KEYS
                and isinstance(value, str)
            ):
                redacted[key] = REDACTION_MARKER
                spans += 1
                redacted_chars += len(value)
            else:
                child, child_spans, child_chars = _redact_node(value)
                redacted[key] = child
                spans += child_spans
                redacted_chars += child_chars
        return redacted, spans, redacted_chars

    if isinstance(node, list):
        items = []
        for item in node:
            child, child_spans, child_chars = _redact_node(item)
            items.append(child)
            spans += child_spans
            redacted_chars += child_chars
        return items, spans, redacted_chars

    if isinstance(node, str):
        text, text_spans, text_chars = _redact_text(node)
        return text, text_spans, text_chars

    return node, 0, 0


def redact_result(result: ToolResult) -> tuple[ToolResult, RedactionStats]:
    """Redact a tool result payload in place of release.

    Walks the serialized envelope (data, evidence, error) and returns a new
    ToolResult plus stats. Clean output passes through structurally
    unchanged.
    """
    payload = result.to_dict()
    original_chars = len(json.dumps(payload))
    redacted_payload, spans, redacted_chars = _redact_node(payload)
    stats = RedactionStats(
        spans=spans,
        original_chars=original_chars,
        redacted_chars=redacted_chars,
    )
    if spans == 0:
        return result, stats
    redacted_result = ToolResult(
        tool_name=redacted_payload["tool_name"],
        status=redacted_payload["status"],
        evidence=redacted_payload.get("evidence", {}),
        data=redacted_payload.get("data"),
        error=redacted_payload.get("error"),
    )
    return redacted_result, stats
