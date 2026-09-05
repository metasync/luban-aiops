# Skill Transparency and Approval-Card Legibility (v0.34.0)

Date: 2026-09-05

A release train closing the 2026-09-05 post-live-test feedback on the
browser-flow approval experience: two R5 spec slices plus two UX quick
wins, all aimed at making the single HITL gate a `write`-class browser
flow parks legible enough to decide on. SPEC-052 lets an operator read the
skill behind a flow; SPEC-053 lets that skill author the plain-language
line the card leads with; the two quick wins humanize the card's per-call
detail and clarify that work continues after approval. Backend, contracts,
portal, guides, and one sample touched; no new policy actions, no new audit
event types.

## SPEC-052: Skill content viewer (fourteenth R5 slice)

- The portal Skills view (SPEC-019 R-4) listed ingested skills but showed
  only envelope metadata (id, title, source, risk class) — the list payload
  omits `body` by contract — so an operator could not read a skill to
  validate where its single HITL gate lands (the transparency goal
  motivating SPEC-049/051).
- A read-only rendered/raw viewer reusing the SPEC-045 R-5 preview pattern
  (rendered Markdown ⇄ raw source toggle, mode badge) opens from each
  Skills-table row and lazily fetches the full record on click.
- Because the list omits `body`, the viewer reads it through a new
  platform-gateway single-skill detail proxy
  (`GET /api/v1/skills/{skill_id:path}`) that reuses the existing
  `skills:read` action and skills-hub's existing `get_skill` endpoint
  (which already returns `body` and emits `skill_retrieved`). Nothing is
  persisted; no download/discard; skills-hub is unchanged and there is no
  shared-contract change.

## SPEC-053: Skill-declared step intent (fifteenth R5 slice)

- Realizes the per-step-intent follow-up SPEC-051 R-6 explicitly deferred
  ("structured per-step plan rendering … needs a skill-format change
  touching the skills contract and ingestion path"). The card led with
  parsed DOM/technical detail instead of an authored "what this achieves"
  line.
- One additive optional frontmatter key, `flow_intent` (≤ 200 chars,
  requires `web_target`), authors in plain language what the flow's single
  gated mutating step achieves. Because SPEC-051 R-1 collapses a mutating
  flow to exactly one gate, a single card-level intent maps 1:1 to the card
  — no brittle per-click matching.
- It rides the existing SPEC-051 R-6 `flow_summary` path verbatim and under
  the same name: skill record → gateway `bind_flow`/`FlowState` →
  `web.navigate` `data["flow"]` → kernel `FlowContext.summary()` →
  `confirmation_request` frame + durable `ConfirmationRecordModel` → portal
  `ConfirmationCardView`, which renders it as a plain-text decision line
  above the demoted DOM/technical detail.
- Display-only and never a security input: the deviation guard and SPEC-037
  signed execution are unchanged, and skills that omit `flow_intent` render
  exactly as today. Additive contract change (`skill.schema.json` plus the
  two `flow_summary` schemas; stream contract v9 → v10) touching the
  skills-hub ingestion/store path. The password-reset sample skill declares
  a `flow_intent` so the demo card leads with the plain decision line.

## Post-live-test UX quick wins

- **Humanized browser approval card** — the per-call block keeps the tool
  name and risk tier but renders the parsed DOM element label as prose
  (`.confirm-call-hint`) instead of a raw code block, and folds the raw
  argument JSON behind a native "Technical details" expander mirroring the
  evidence card's "Parameters" expander. Nothing is dropped: the full
  parameters stay one click away and still travel to the audit trail
  unchanged.
- **Clarified post-approval progress** — the post-approval activity
  indicator moves from a bare animated-dots bubble below the evidence to a
  labelled spinner row ("Agent is working…") rendered under the reply and
  above the tool-evidence panel, so the operator reads "work is continuing"
  ahead of the still-growing evidence.
- **DocumentsView parallel-suite flake** — the test `flush()` helper now
  awaits its timer inside `act()`, draining the pending promise, the
  scheduler hop, and the commit so post-flush assertions read the settled
  tree regardless of worker load. Test-only.

## Untouched / guarantees

No new policy actions and no new audit event types. `flow_intent` is
display-only — the HITL gate, the deviation guard, and the SPEC-037 signed
execution path never read it. Browser write tools still never join any
auto-allow list. The quick wins are portal-only with no stream-contract
change. The skill content viewer is read-only and persists nothing.

## Verification

Version lockstep 0.34.0 validated across all products and the portal.
`make verify` green (all product pytest, kustomize overlays, policy rules
and scenarios, version lockstep); skills-hub 57, tool-gateway browser
connector 96, agent-platform 798, portal 283 all green; `npm run build`
clean.
