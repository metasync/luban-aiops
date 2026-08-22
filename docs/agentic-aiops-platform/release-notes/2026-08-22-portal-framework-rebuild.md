# Release Notes: 2026-08-22 — Portal Framework Rebuild (SPEC-023, v0.9.0)

## Summary

SPEC-023 rebuilds the operator portal on a maintained component framework:
a Vite + React 18 + TypeScript SPA on antd 6 and Ant Design X replaces the
single-file vanilla UI, consumes the SPEC-022 session workspace contract
(Appendix A), and adds browser voice composition — without changing any
policy-gated behavior, contract, or deployment shape beyond the portal
image itself.

The rebuild shipped in stages behind a coexistence mount (`/next/`) so the
legacy portal stayed live while parity was rebuilt and tested; delivery
flips the nginx runtime root to the hashed bundle and removes the vanilla
trio (`app.js`, `styles.css`, legacy `index.html`). The platform keeps
owning the stream contract: a dedicated SSE adapter decodes schema v6
frames into typed models, and HITL remains click-gated end to end
(Invariant II is test-pinned in the new stack).

## Change Set 1: Framework foundation and build toolchain (R-1)

### Highlights

- New SPA tree under `products/operator-portal/web-ui/app/` (React 18,
  TypeScript strict, Vitest), with the dark theme seeded 1:1 from the
  legacy CSS variables into antd/XProvider tokens and a `:root` variable
  mirror.
- Multi-stage Dockerfile: a Node stage compiles the bundle with the root
  `VERSION` injected as `PLATFORM_VERSION`; the nginx-unprivileged runtime
  serves hashed `/assets/*` with `Cache-Control: immutable` and the SPA
  shell `no-store`, keeping the `/api/` proxy to platform-gateway.
- `make validate-version` asserts the injection wiring (VERSION read +
  define) in `vite.config.ts`; the legacy `PLATFORM_VERSION` literal check
  retires with the vanilla tree.
- OIDC shell ported unchanged in behavior: Keycloak login/logout, silent
  refresh ~60s before expiry, per-request Bearer.

### Why It Matters

Component structure and typed models replace ~2,200 lines of DOM
manipulation, giving the SPEC-024 model dropdown and future workspace
features a sustainable home. Hashed asset filenames remove cache-busting
query strings: deploys roll over on the next `index.html` fetch.

## Change Set 2: Platform-owned SSE contract adapter (R-2)

### Highlights

- `transport.ts`: `fetch` + `ReadableStream` with abort-controller
  lifecycle; `decoder.ts`: schema v6 frames → typed models, ported 1:1
  from the vanilla dispatch including the truncation-locked confirmation
  card; `useChatStream()`: typed hook with per-session turn caches.
- Fixture tests cover every schema v6 event type (deltas, tool call/result
  pairing, confirmation request/result, error frames, stream truncation).

### Why It Matters

The portal no longer re-implements stream parsing inside rendering code:
decoding, anchoring, and terminal-state rules are unit-tested in
isolation, and session switching can abort/repoint streams safely.

## Change Set 3: Multi-session workspace UI (R-3)

### Highlights

- Session panel: titles, relative last-active (dayjs), amber *awaiting
  approval* badges, 30s poll plus lifecycle refreshes.
- Switch/resume: previous stream closed, transcript loaded with an
  explicit `transcript_available=false` note, per-tab active-session
  persistence, per-session turn caches so in-flight state survives
  switches.
- Delete with in-UI confirm; 409 parked refusal and neutral 404 surface
  exactly as SPEC-022 prescribes.
- Confirmation anchoring: cards stay bound to the parking session;
  approve/deny resumes that session's stream via `POST /api/v1/chat/confirm`.
- Incident deep links: *Continue in chat* pins `incident-<id>` (or the
  incident's real session id) into the panel and opens the chat view.

### Why It Matters

Operators can now run parallel investigations without losing parked HITL
decisions: the SPEC-022 backend-first contract reaches its UI completion.

## Change Set 4: Voice input (R-4)

### Highlights

- Composer microphone performs browser speech-to-text via the Web Speech
  API (final results only; no audio is stored or transmitted to the
  platform); recognized text composes into the draft and submits with
  `input_modality=voice`.
- Recognition-language selector (en-US / zh-CN minimum): defaults from
  the browser locale with an `en-US` fallback, persists in `localStorage`,
  and drives the recognizer `lang` only — never sent to the backend.
- Unsupported browsers show a disabled microphone with a tooltip;
  recognition errors map 1:1 to browser error codes above the composer.
- Invariant II pinned by test: a voice-contributed turn's confirmation
  decision posts exactly `{session_id, confirm_id, decision}`.

### Why It Matters

Voice is additive metadata (audited on `chat_started` as
`input_modality: voice`); no policy, auto-allow, or HITL behavior keys
off it, keeping approval strictly click-gated.

## Change Set 5: View migration parity and delivery close (R-5, R-6)

### Highlights

- Audit trail view (auditor/platform-admin gate): username/type/service/
  since/until filters, cursor pagination with "Load more", expandable
  verbatim envelopes.
- Permissions matrix (live `GET /api/v1/policy/matrix` with bundle
  provenance), Tools catalog (risk-tiered confirmation column), and Skills
  inventory (source/tag filters) rebuilt on antd primitives.
- Incidents: filterable list with the legacy 15s auto-refresh, manual
  intake form with key=value label parsing, detail with the full triage
  report (evidence, hypotheses, ranked advisory next steps, cited
  guidance), connector dispatch outcomes, and Run/Re-run triage states.
- Role-scoped navigation auto-hide preserved (SPEC-019 parity).
- Vanilla trio removed; nginx serves the bundle at `/`; operator portal
  README, operator guide checklist, configuration reference, and
  troubleshooting guide updated (cache behavior, voice availability,
  stale-tab and microphone symptoms).

## Validation

- Frontend: 56 Vitest unit tests green (stream decoder/transport/hook,
  transcript mapping, markdown escaping, voice language resolution, labels
  parsing), `tsc` strict green, production build green.
- `make verify` green: all product suites, overlay rendering, policy
  schema validation, and 0.9.0 version lockstep.
- `make build` + `make deploy` green on dev-k8s; live walkthrough:
  login → multi-session create/switch/resume → incident deep link →
  per-role visibility (operator, auditor, observer), tools/skills/
  permissions tables, and the audit entry hidden for non-auditor roles.
- In-release walkthrough fix: a live stream capture showed the kernel
  can close a stream right after the last delta with empty
  `message_delta` frames and no `message_end`; the hook now completes
  the turn on a natural (and abort-closed) stream end — parity with the
  legacy renderer, which never gated the final render on the terminal
  frame — pinned by a new fixture test.

## Known Limitations

- The production bundle is a single chunk (~1 MB / ~340 KB gzip); route-
  level code splitting is a follow-up optimization, not a correctness gap.
- Voice input requires a browser with Web Speech API support (Chrome,
  Edge); other browsers degrade to typing with a tooltip explanation.
- Settings & Debug remains a placeholder view in the rebuilt shell.
- Starting login from an origin other than the configured OIDC redirect
  hostname (e.g. a `localhost` port-forward) cannot complete the PKCE
  round-trip because the callback lands on the portal hostname; use the
  deployed hostname (or its DNS alias) for sign-in. This behavior is
  unchanged from the legacy portal.

## Related Documents

- `docs/specs/SPEC-023-portal-framework-rebuild/` (spec, plan, tasks)
- `docs/specs/SPEC-022-multi-session-operator-workspace/` (backend
  contract consumed, Appendix A satisfied)
- `docs/guides/approval-and-hitl.md` (voice-readiness subsection)
- `docs/guides/troubleshooting.md` (stale-UI and microphone symptoms)
