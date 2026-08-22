# SPEC-023: Portal Framework Rebuild — Multi-Session Workspace UI on Ant Design X

## Status

- status: `draft`
- owner: chi
- created: 2026-08-22
- release slice: R5 operator workspace — second slice (0.9.0 train)
- related ADRs: none new; consumes SPEC-022 Appendix A (deferred portal UI
  contract) verbatim, re-asserts SPEC-020 (click-gated HITL) and SPEC-022
  R-2 invariants, and adopts the findings of the portal framework rebuild
  spike memo (`docs/workspace/portal-framework-rebuild-spike.md`)

## Summary

Rebuild the operator portal on React + Ant Design X (TypeScript, Vite
build) behind a single platform-owned SSE contract adapter, delivering the
SPEC-022 deferred UI contract verbatim: the multi-session workspace (panel
with titles, recency, and parked-confirmation badges; switch/resume;
new/delete with 409 handling; confirmation anchoring; incident deep links),
voice input as an `input_modality: "voice"` composition surface, and the
migration of all existing portal views (chat, control, workspace) with
role-scoped visibility preserved. Backend contracts, policy actions, and
audit behavior are unchanged; the rebuild is presentation-layer only.

## Motivation

- SPEC-022 shipped the session workspace API (list cap-50 with
  `pending_confirmation` flags, get-with-transcript, owner-only delete with
  404 anti-enumeration and 409 parked refusal) but deliberately deferred the
  portal UI because the hand-rolled vanilla-JS portal was a rebuild
  candidate; its Appendix A preserved the UI requirements verbatim as this
  spec's handoff contract. Operators currently cannot see, switch between,
  or manage their sessions in the portal.
- The portal's single-file UI (`app.js` at ~2,200 lines) has reached the
  size where component structure pays for itself, and the next two roadmap
  items — this session workspace and the SPEC-024 model dropdown — both
  need richer componentry than vanilla DOM manipulation can sustainably
  provide.
- The spike memo (2026-08-22) evaluated Ant Design X, AgentScope Spark,
  assistant-ui/CopilotKit, and extending vanilla; it recommends Ant Design X
  on React for license clarity (single MIT), maturity, and near one-to-one
  component mapping onto Appendix A, with a platform-owned SSE contract
  adapter as the core architecture requirement. This spec implements that
  recommendation.
- Voice-readiness (SPEC-022 R-2) landed as metadata only; the framework's
  built-in voice input (`Sender` `useSpeech`, Web Speech API) makes voice
  composition UI-only work with no STT backend, while Invariant II keeps
  approvals click-gated.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable
acceptance criteria.

### R-1: Framework foundation and build toolchain

The portal adopts React + Ant Design X + TypeScript built by Vite, shipped
through the existing nginx-static serving model.

Acceptance criteria:

- `products/operator-portal/web-ui/` hosts the new source tree; `npm ci` +
  `npm run build` produce static assets, and `products/operator-portal/Dockerfile`
  gains a multi-stage Node build stage whose runtime stage remains the
  current nginx image pattern (no runtime Node dependency).
- Built assets carry content-hash filenames; `index.html` is served
  `no-store` (existing nginx behavior) and hashed assets may be cached
  immutably; manual cache busters are removed.
- `PLATFORM_VERSION` is injected at build time from the root `VERSION`
  file's value and remains asserted by `make validate-version` (the
  validator follows the constant to its new home); the sidebar version
  chip keeps rendering it.
- `nginx.conf` keeps the `/api/` → platform-gateway proxy with
  `proxy_buffering off` and long read timeouts; SPA fallback is served by
  the existing `try_files ... /index.html` rule.
- The dark theme is rebuilt from the current `:root` CSS custom properties
  into Ant Design design tokens (`XProvider` theme), preserving the slate
  palette, `color-scheme: dark`, and the sidebar/drawer layout language of
  SPEC-019.

### R-2: Platform-owned SSE contract adapter

One adapter module owns the wire protocol; every view consumes typed models.

Acceptance criteria:

- Chat transport stays `fetch` + `ReadableStream` (never `EventSource`),
  sending the POST body and the caller's `Bearer` token exactly as today;
  no framework component performs its own network call against the chat
  endpoint.
- The adapter translates stream schema v6 frames into typed models: agent
  deltas → streaming message content; `tool_result` → evidence items with
  the full-output expander (SPEC-011 R-4, including the
  `AGENT_TOOL_DATA_MAX_CHARS` truncation notice); `confirmation_request` →
  confirmation card model; `confirmation_result` → decision resolution;
  stream close/truncation → explicit terminal states, and a confirmation
  card left without a `confirmation_result` stays locked (parity with the
  current portal).
- Frame-type knowledge lives only in the adapter; views import typed models
  only. A stream-schema change (v6 → v7) must be fixable in the adapter
  module alone; pinned by a unit test that renders fixture frames through
  the adapter and asserts the emitted models.
- Evidence and audit rendering keep provenance inline next to the answer it
  grounds, collapsed by default (SPEC-011 R-4).

### R-3: Multi-session workspace UI (SPEC-022 Appendix A, verbatim contract)

The chat view becomes session-aware through the existing gateway endpoints
(`GET /api/v1/sessions`, `GET /api/v1/sessions/{id}`,
`DELETE /api/v1/sessions/{id}`, existing create path).

Acceptance criteria:

- **Session panel**: the chat view lists the operator's sessions with title,
  relative last-active time, and an amber *awaiting approval* badge when
  `pending_confirmation` is true; the panel refreshes on session lifecycle
  events and at most every 30 seconds otherwise.
- **Switch/resume**: switching loads the target session's transcript (or an
  explicit "history unavailable" state when `transcript_available` is
  false), repoints the active stream and confirm endpoints at that session,
  persists the active session id per browser tab, and closes any in-flight
  stream of the previous session.
- **New/delete**: *New session* uses the existing create path; *Delete*
  requires an in-UI confirmation and is refused (client- and server-side,
  HTTP 409) for sessions with a parked confirmation; 404 responses never
  reveal ownership.
- **Confirmation anchoring**: confirmation cards remain anchored to the
  session that parked them; approving/denying from a switched-into session
  resumes that session's stream exactly as today (`POST /api/v1/chat/confirm`
  unchanged).
- **Incident deep links**: the incident view's `incident-<id>` session
  pinning opens as another session in the panel rather than replacing the
  active one.

### R-4: Voice input

Acceptance criteria:

- The chat composer ships a voice input affordance (Ant Design X `Sender`
  speech input via the Web Speech API); voice-composed turns send ordinary
  chat requests with `input_modality: "voice"` and text turns keep
  `input_modality: "text"` (default).
- Invariant II re-asserted and pinned by test: no voice-driven path can
  approve or deny a confirmation — `POST /api/v1/chat/confirm` remains the
  only decision surface and confirmation cards render buttons only.
- Voice input degrades gracefully (affordance hidden or disabled with an
  explanation) when the browser lacks the Web Speech API; no STT backend,
  audio capture pipeline, or transport is introduced.
- Recognition language is an explicit operator choice: the composer offers
  a language selector (at minimum English `en-US` and Mandarin `zh-CN`)
  whose selection drives the recognizer's `lang`; it defaults to the
  browser locale when it matches a supported language and otherwise falls
  back to `en-US`; the choice persists per browser. The selector affects
  transcription only — it is never sent to the backend and never influences
  policy, modality metadata, or HITL behavior.
- The Approval and HITL guide's voice-readiness subsection is updated to
  state that the portal now offers voice composition under these invariants.

### R-5: View migration and role-scoped visibility

All existing portal views migrate to the rebuilt app; nothing is dropped.

Acceptance criteria:

- Chat, Control (audit / permissions / tools / skills), and Workspace
  (incidents) views are rebuilt with component parity: audit filters and
  cursor pagination, permission matrix, tools and skills inventories,
  incidents list/detail/triage (including connector outcomes and the
  session-pinning deep link).
- Sectioned navigation (SPEC-019) is preserved: sections auto-hide when the
  caller's token lacks the matching policy actions (deny-by-default; the
  router hides what the token cannot read), and the audit view stays
  auditor/platform-admin only.
- Keycloak OIDC login/logout, token refresh, and per-request `Bearer`
  behavior are unchanged (same gateway endpoints, same session-storage
  posture).
- Migration is chat-first: R-1..R-4 ship with the rebuilt chat experience;
  Control/Workspace views may land in a following stage of the same
  release, but the delivery closes only when every view above is present
  and the vanilla app is removed.

### R-6: Documentation and living state

Acceptance criteria:

- Operator portal README, guides (operator guide, configuration reference,
  troubleshooting), and the dev-k8s README reflect the rebuilt portal
  (build step, cache behavior, voice availability) and drop stale
  single-session language.
- CHANGELOG, spec index, and roadmap updated at delivery; release note
  follows the established structure; the roadmap Exploration Backlog rows
  record SPEC-023 delivered and clear the model-dropdown UI dependency note
  for SPEC-024.

## Non-Goals

- Runtime LLM model switching: backend slice and dropdown UI stay owned by
  the SPEC-024 candidate (its UI lands in this rebuilt shell; this spec
  only ensures the composer area leaves room for a model selector).
- Speech-to-text engines, audio capture pipelines, or audio transport
  (SPEC-022 non-goal, unchanged).
- Any backend, shared-contract, or policy-bundle change: the session API,
  chat contract, policy actions, and audit events are all already shipped.
- AgentScope Spark adoption (spike runner-up; revisit only if the adapter
  boundary proves costly and upstream stabilizes).
- Light-mode theming or i18n beyond the current single dark theme.

## Impact

- products touched: `products/operator-portal/` (web-ui rebuild,
  Dockerfile build stage, nginx.conf cache headers), docs under
  `docs/guides/` and product READMEs
- contracts touched: none (consumes existing chat/session/audit contracts
  unchanged)
- identity / policy / audit / execution safety impact: none new — the
  rebuild must not change any policy-gated behavior; Invariant II
  (click-gated HITL) is re-asserted and test-pinned
- living state docs to update on delivery: root README, operator-portal
  README, operator guide, configuration reference, troubleshooting guide,
  dev-k8s README, CHANGELOG, spec index, roadmap backlog

## Open Questions

- none — the spike's open questions are resolved by this draft: chat-first
  phasing (R-5), antd design tokens mapped from the current `:root`
  variables (R-1), SPA routing via the existing nginx `try_files` fallback
  (R-1), and no list virtualization at the cap-50 session size (R-3)

## Changelog

- 2026-08-22: created as `draft`, promoted from
  `docs/workspace/portal-framework-rebuild-spike.md` (approved 2026-08-22)
- 2026-08-22: R-4 gains explicit recognition-language selection (default
  browser locale, `en-US`/`zh-CN` minimum set, per-browser persistence)
