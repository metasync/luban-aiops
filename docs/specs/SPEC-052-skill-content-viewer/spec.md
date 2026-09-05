# SPEC-052: Skill Content Viewer — Reading Ingested Skills in the Operator Portal

## Status

- status: `approved`
- owner: luban-platform-team
- created: 2026-09-05
- approved: 2026-09-05
- release slice: R5 — Hardening and External Consumption (fourteenth R5
  slice)
- related ADRs: ADR-0008 (spec delivery traceability gate); lineage:
  extends SPEC-014 (skills and grounded guidance — the skill envelope and
  its `body` field), SPEC-019 R-4 (portal skills inventory), and reuses the
  SPEC-045 R-5 read-only rendered/raw preview pattern; motivated by the
  SPEC-049/051 browser-flow transparency work (operators must be able to
  read a skill to validate where its single HITL gate lands)

## Summary

The portal Skills view (SPEC-019 R-4) lists ingested skills but shows only
inventory metadata — title, source, tags, version, updated — with no way to
read what a skill actually *does*. The skill body (its declared steps and
narrative) is deliberately omitted from the list payload by contract
(`skill.schema.json`: "list and search responses omit or excerpt it") and is
served only in the full-record `GET` by id. This spec adds a read-only
**skill content viewer**: a per-row **View** action in the Skills table that
lazily fetches the single-skill record through a new platform-gateway detail
proxy and opens it in a rendered/raw modal mirroring the SPEC-045 draft
preview. It adds **no new policy action, no new audit event type, and no
shared-contract change** — the gateway proxy reuses the existing `skills:read`
gate and skills-hub's existing `get_skill` endpoint (which already emits
`skill_retrieved` and already returns `body`).

## Motivation

- A live browser-flow test on v0.33.x surfaced the gap directly: trying to
  understand what the "reset password" skill does — and therefore whether the
  single SPEC-051 HITL gate lands on the correct destructive step — the
  operator could not read the skill content anywhere in the portal. The Skills
  page showed only its name and tags.
- The platform already renders skill markdown read-only for *drafted* skills
  (SPEC-044/045 `SkillDraftPreviewModal`, escape-first renderer, rendered/raw
  toggle). *Ingested* skills — the ones actually driving tool behaviour and
  HITL gates — have no equivalent transparency surface.
- skills-hub already exposes the content: `GET /api/v1/skills/{skill_id:path}`
  returns the full record including `body`. The only missing hop is the
  platform-gateway pass-through (it proxies the list, not the detail) and the
  portal affordance. This is a small, additive, low-risk transparency win that
  belongs in the current hardening slice alongside the browser-flow work it
  helps operators validate.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable
acceptance criteria.

### R-1: Single-skill detail proxy (platform-gateway)

The platform-gateway gains an additive read-only pass-through
`GET /api/v1/skills/{skill_id:path}` that forwards to skills-hub's existing
`get_skill` and returns the full skill record (including `body`). It is gated
by the **same** `skills:read` action as the list route (no new policy action),
speaks to skills-hub with the gateway-held Basic query credential — the user's
bearer token is never forwarded — and mirrors the list proxy's error posture.

Acceptance criteria:

- `GET /api/v1/skills/{id}` from a caller holding `skills:read` returns the
  skills-hub full record for that id, including a non-empty `body` for a skill
  that has one; a caller without `skills:read` is denied at the edge before any
  upstream call is made.
- The gateway authenticates to skills-hub with its own Basic credential
  (`skills_client_id`/`skills_client_secret`), never the user token; a test
  asserts the upstream request carries the gateway credential.
- Error mapping matches the list proxy: unknown id → `404` passthrough;
  skills-hub unconfigured or delegation absent → `503`; transport error or
  upstream `5xx` → `502`; upstream `4xx` passes through.
- `{skill_id:path}` accepts the namespaced `<source_id>/<slug>` form (embedded
  slashes) without truncation.
- The route is added to the gateway route-inventory test, and skills-hub is
  **unchanged** (the endpoint, its `skill_retrieved` audit emission, and the
  `skill.schema.json` envelope all already exist).

### R-2: Portal View action with lazy detail fetch

Each row in the portal Skills table gains a **View** affordance that opens the
skill's content. The single-skill detail is fetched only when View is invoked
(not eagerly for every listed row), reusing the existing `requestJson` client
and the SkillsView error-handling pattern.

Acceptance criteria:

- Every skill row exposes a View control with an accessible label naming the
  skill (e.g. `aria-label="View <title or skill_id>"`).
- Invoking View issues exactly one `GET /api/v1/skills/{id}`; rows that are not
  opened issue no detail request (asserted by counting client calls).
- While the detail is loading, the control shows a pending/disabled state; on
  error the message surfaces inline (Alert) and the viewer does not open with
  empty content.
- The list payload and its rendering are otherwise unchanged (metadata columns,
  filters, and totals behave exactly as before).

### R-3: Read-only rendered/raw skill content viewer

Opening a skill presents its body in a modal that mirrors the SPEC-045
`SkillDraftPreviewModal` UX — a Rendered/Raw `Segmented` toggle over a bounded
scroll pane — adapted for an *ingested* skill. The rendered view uses the
existing escape-first `renderMarkdown` (the XSS-safe path shared with chat and
draft previews); the raw view shows the markdown body in a `<pre>`. The header
carries skill metadata rather than draft-generation state, and the surface is
strictly read-only.

Acceptance criteria:

- The modal opens on the **Rendered** view by default; the `Segmented` control
  switches between Rendered and Raw; the rendered body is produced solely by the
  shared escape-first renderer (no new HTML-producing path).
- The header shows the skill's title, `source_id`, `version`, and `tags`, and
  `web_target` when present (browser skills); it shows **no** draft-only
  concepts (mode badge, validation status, "suggested filename").
- The body pane is read-only and bounded (`max-height` with scroll), reusing the
  `md-content` / `evidence-pre` styling; the contract's 64 KiB `body` cap bounds
  the payload.
- There is no download-as-contribution or discard-draft action and nothing is
  persisted; a single Close control dismisses the viewer. (Viewing an ingested
  skill is distinct from the SPEC-044/045 authoring export flow, which remains
  the only path that hands over raw markdown for contribution.)
- The viewer is a sibling read-only component that reuses `renderMarkdown` and
  the Segmented pattern; it does not alter `SkillDraftPreviewModal` or the draft
  export behaviour.

## Non-Goals

- **No skill editing or authoring from the portal.** Ingested skills are
  read-only here; authoring/contribution stays on the SPEC-044/045 draft-export
  path (edit in the team's Git skills repo).
- **No new policy action and no new audit event type.** The detail proxy reuses
  `skills:read`; skills-hub's existing `skill_retrieved` emission already covers
  detail fetches (SPEC-029).
- **No shared-contract change.** `skill.schema.json` already defines `body` and
  already scopes it to full-record responses; the portal adds only a local
  TypeScript interface for the detail shape.
- **No change to the skills list payload**, search, ingestion, sync, or the
  skills-hub service.
- **No in-content search, cross-skill diffing, version history, or annotation.**
- **Per-action browser intent (#2b from the same live test) is out of scope** —
  it is a contract- and runtime-touching change tracked separately as SPEC-053.

## Impact

- products touched:
  - `products/platform-gateway` — new `GET /api/v1/skills/{skill_id:path}`
    route in `api/routes/skills.py`, a `get_skill` function in
    `services/skills_hub_client.py`, and tests (`test_route_inventory.py`,
    `test_workspace_proxies.py`).
  - `products/operator-portal/web-ui/app` — a View action + lazy detail fetch in
    `src/views/control/SkillsView.tsx`, a new read-only `SkillContentViewer`
    modal under `src/chat/` (beside `SkillDraftPreview.tsx`, reusing
    `renderMarkdown`), an api-client helper, and component tests.
  - `products/skills-hub` — **no change** (the endpoint and its audit emission
    already exist).
- contracts touched: none (`shared/shared-contracts/schemas/skill.schema.json`
  already defines `body`; no schema edit).
- identity / policy / audit / execution safety impact: none new. Reuses the
  `skills:read` action and the gateway-Basic-credential posture (user token
  never forwarded); read-only, no execution or mutation surface; skills-hub
  continues to emit `skill_retrieved` on detail fetch. The rendered view reuses
  the escape-first renderer, so no new XSS surface is introduced.
- living state docs to update on delivery: root `CHANGELOG.md`, the spec index
  in `docs/specs/README.md`, the operator guide's Skills/transparency section
  (`docs/product-guides/`), and the affected RepoWiki pages (portal workspace
  views; gateway routing).

## Open Questions

- none

## Changelog

- 2026-09-05: created as `draft` from the 2026-09-05 post-live-test feedback
  (suggestion #1 — operators cannot read skill content on the Skills page).
- 2026-09-05: approved as drafted (no scope changes) by the operator; plan.md
  and tasks.md follow, then implementation bundled into the next release with
  the two v0.33.x UX commits already on `main`.
