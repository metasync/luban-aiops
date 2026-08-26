# v0.18.1 — Live-Check Patch: Markdown Lists, Reveal Revert, Log Quoting

Date: 2026-08-26
Release type: patch (portal rendering and reply-formatting fixes from
the v0.18.0 live check; no contract or policy changes)

## Summary

v0.18.1 ships the three findings from the v0.18.0 live check. The
chat markdown renderer dropped indented sub-bullets to literal
"- text" paragraphs (rendered at the left edge, without bullets or
indentation) and never wrapped ordered items in `<ol>`, so numbered
lists lost their markers. The operator decided, after living with it,
that the cold-seeded transcript typewriter introduced by SPEC-036 R-1
is not a good fit: the reveal is reverted, and the typewriter stays
reserved for live arrivals. And pod-log excerpts quoted in agent
replies landed as one JSON-serialized string — the model now quotes
log lines in fenced code blocks, which the portal renders in a
fixed-height scrollable box.

## Change Set

### Fixed

- **Nested and ordered list rendering.** The escape-first renderer's
  legacy list passes matched bullets only at column 0 and wrapped
  unordered items before converting ordered ones — so indented
  sub-bullets fell through every pass and rendered as literal `- text`
  paragraphs, and ordered items became bare `<li>` with no numbering.
  A single nesting-aware block pass replaces them: consecutive list
  lines form one list, an item indented under a previous item nests
  inside it (each level remembers its own first indent, so an entirely
  indented block still renders as one flat list), ordered and unordered
  markers may mix with each level choosing its container, and
  over-indentation never opens empty wrappers. Escaping is untouched —
  item content passes through the same escape-first pipeline, pinned
  by new regression tests.
- **Pod-log excerpts in replies.** `k8s.get_pod_logs` returns its
  payload as JSON (and stays that way — the evidence card is the
  audit-grade surface), but the model used to quote the `logs` field
  verbatim, landing one serialized string with escaped `\n` sequences
  in the reply. The default system prompt now instructs the model to
  quote log lines and command output in fenced code blocks with real
  line breaks — raw lines, never the JSON serialization, trimmed to
  the lines that matter — and the portal bounds every fenced block in
  the reply to a fixed-height (280px, the evidence-expander bound)
  scrollable box so a long excerpt never pushes the transcript out of
  view. The prompt guidance is pinned by a settings test.

### Reverted

- **Seeded-transcript reveal (SPEC-036 R-1).** Live feedback: opening
  a session re-typed its history instead of showing it, which read as
  delay rather than polish. The cascade state, per-turn stagger
  helpers, and their tests are removed; cold-seeded transcripts render
  at once again. The SPEC-035 arrival typewriter (live content landing
  on an open session) is unchanged — that is now the only surface the
  typewriter applies to.

### Changed

- Version lockstep bumped to 0.18.1 (VERSION, pyproject, metadata,
  `__version__`) and per-product `uv.lock` files refreshed.
- SPEC-036 spec changelog, roadmap narrative, and the v0.18.0 release
  notes carry the revert note.

## Validation

- Six new markdown regression tests (flat bullets, nested sub-bullets,
  indented-block bullets, `<ol>` wrapping, mixed nesting, escape
  preservation); the seed-reveal unit tests are removed with the code;
  the log-quoting prompt guidance is pinned by a settings test.
- Portal vitest 158 passed; `tsc --noEmit` clean; agent-platform suite
  green.
- `make verify` green at lockstep 0.18.1.

## Upgrade Notes

- No breaking changes; no new knobs. Rebuild and redeploy to pick up
  the fixes — clusters on the v0.18.0 image keep working but retain
  the flattened sub-bullets, the seeded-transcript typewriter, and the
  serialized log excerpts in replies.
