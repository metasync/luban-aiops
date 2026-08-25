# Spike: In-Portal Help & Onboarding (review finding D6)

Status: spike complete — findings below; decision recorded, promotion parked
Date: 2026-08-25
Roadmap home: Exploration Backlog "In-portal help & onboarding" (portal enhancement spec)
Verified against: operator-portal web-ui at 0.11.1 (React 18 + antd 6.1 + Ant Design X 2.9)

## 1. Question

Would contextual help inside the portal (first-run tour, capability hints,
links into the operator guides) measurably reduce onboarding friction versus
the standalone `docs/guides/portal-user-guide.md`? The 2026-08-25 code/doc
review deferred this pending a UX spike against the SPEC-023 shell.

## 2. Findings — current shell state (verified)

- **No in-app help surface exists.** The SPEC-023 shell (`App.tsx`, seven
  views, role-gated sidebar) has no tour, no help drawer, and no links to
  any guide. The only hint affordances are three targeted tooltips
  (sign-in prompt, voice-API-unavailable, model-select) and the
  SPEC-023 R-3 empty-transcript note.
- **antd 6 ships `Tour` out of the box.** A first-run walkthrough needs no
  new dependency; steps can anchor to existing refs (sidebar brand,
  composer, session panel, evidence cards) and be filtered by role so a
  step never points at an entry the user's roles hide.
- **Guides are repo Markdown only.** `docs/guides/` (portal-user-guide.md
  206 lines, getting-started.md, approval-and-hitl.md, ...) is not served
  anywhere the portal runs; the nginx config serves only the SPA and
  proxies `/api/`. A "link to the guides" feature therefore has a real
  prerequisite: either a static `/guides/` location baked into the portal
  image (Markdown rendered with the portal's existing escape-first
  renderer) or a durable external URL.
- **Measurement surface is thin by design.** The platform has no analytics
  and the audit trail is deliberately agent/platform-event shaped. The only
  honest onboarding proxies available without new machinery are existing
  audit events (`chat_started`, `session_created` per user over time) plus
  — if added — one `help_opened`-style client event. "Measurably" can only
  mean a before/after comparison of those proxies across the small internal
  user base.

## 3. Options weighed

| Option | Shape | Cost | Risk | Verdict |
|---|---|---|---|---|
| A. Help entry + guide links | Sidebar-footer help icon opening a drawer with guide links (served via a static nginx `/guides/` location) | Small (nginx location + one drawer) | Low; static content only | Worthwhile, prerequisite for everything else |
| B. First-run antd Tour | Role-aware `Tour` on first signed-in visit (localStorage dismissal), 4–6 steps: navigation, chat, model select, evidence, confirmations | Small-medium | Low; pure UI, no backend | Worthwhile once A lands |
| C. Contextual capability hints | Per-view empty-state/first-use hints (audit filters, skills sources, confirmation cards) | Medium; grows with every view | Content-drift risk vs guides (two sources of truth) | Defer; duplicates the guide unless driven by real confusion reports |
| D. Full in-app guide renderer | Fetch and render guide Markdown inside the portal | Medium-high | Duplicates docs site concerns; version pinning vs deployed image | Reject for now — a link (A) gets 90% of the value |

## 4. Measurement plan (if/when promoted)

- Baseline: per-user `chat_started` latency from first sign-in and session
  counts over a fixed window, read from the existing audit query API.
- Treatment: same metrics after A+B ship, plus an opt-in `help_opened`
  audit event (reuses the SPEC-013 vocabulary-extension pattern; client
  emission through platform-gateway).
- Decision rule: if internal adoption is already complete before the
  baseline window fills, declare the need unproven and close the finding
  with A as the delivered floor.

## 5. Recommendation

The finding is resolved as **scoped and parked, not promoted yet**:

1. Option A (guide links) is the cheap floor and the prerequisite for any
   later tier; fold it into the next portal-enhancement slice whenever one
   opens, or deliver it standalone if onboarding complaints arrive first.
2. Option B (first-run tour) is decision-complete enough for a spec once A
   exists, but only earns its cost against real onboarding friction — the
   current user base is internal and already guided by
   `docs/guides/portal-user-guide.md`.
3. Options C and D stay rejected/deferred per the table above.

Promotion is deliberately **not** recommended now: the R4 policy surface
(SPEC-030 candidate) is the roadmap's next operator-visible capability, and
a help tier should follow observed confusion, not anticipate it. The
backlog row updates from "needs a UX spike" to "spiked; tiered scope and
measurement plan recorded; promote on first onboarding friction signal".

## 6. Addendum — Settings & Debug restoration

The SPEC-023 rebuild left the Settings view as a placeholder (recorded
only in a code comment, never in the spec), while `portal-user-guide.md`
documented it as live — drift now corrected in the guide. The old view's
durable value is its read-only correlation data (session id, request id,
identity claims); its gateway-URL/manual-user-ID debug inputs are obsolete
post-OIDC. Originally scheduled into this memo's future portal-enhancement
slice; at owner review (2026-08-25) it was moved forward and folded into
SPEC-030 as add-on requirement R-6 (read-only Session & Identity panel).
