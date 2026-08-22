# Spike: Portal Framework Rebuild (AI UI framework selection)

Status: spike complete — findings below; promotion to a spec (SPEC-023
candidate) is pending review
Date: 2026-08-22
Roadmap home: Exploration Backlog "Portal framework rebuild" (own spec after
SPEC-022; consumes SPEC-022 Appendix A UI contract)
Verified against: operator-portal web-ui at 0.8.1, stream schema v6,
candidate documentation as published 2026-08-22

## 1. Question

Should the operator portal be rebuilt on an AI UI framework (Ant Design X,
AgentScope Spark, or similar) to deliver the SPEC-022 deferred UI contract
(multi-session panel, switch/resume, delete-with-409, confirmation
anchoring, incident deep links, voice input) plus the future SPEC-024 model
dropdown — and if so, which framework, under what license, bundle, build
toolchain, and SSE contract-adapter conditions, while preserving the
click-gated HITL invariant?

## 2. Findings — current portal baseline (verified)

- **No framework, no build step.** `products/operator-portal/web-ui/` is
  vanilla HTML + CSS + JS: `app.js` (2,205 lines), `styles.css` (1,191
  lines), `index.html` (290 lines), served by nginx. Views: Chat, Control
  (audit / permissions / tools / skills), Workspace (incidents), with the
  SPEC-019 sidebar/drawer layout.
- **Auth**: Keycloak OIDC authorization-code flow driven from the browser
  (authorization URL redirect, refresh-token renewal, `Bearer` header per
  request). This is framework-agnostic and survives any rebuild unchanged.
- **Streaming**: the portal consumes chat with `fetch` +
  `response.body.getReader()` — **not** `EventSource` — which is what makes
  `POST` bodies and `Authorization` headers possible. Frames are dispatched
  by `eventType` (agent deltas, `tool_result` evidence,
  `confirmation_request` / `confirmation_result`, stream schema v6).
- **Serving**: nginx proxies `/api/` to platform-gateway with
  `proxy_buffering off` and long read timeouts for SSE; static assets are
  `no-store` with manual cache busters.

Conclusion: the rebuild risk is concentrated in two surfaces — the SSE
frame vocabulary and the view/view-gating logic. Auth and serving are
stable.

## 3. Findings — candidate evaluation

### 3.1 Ant Design X (`@ant-design/x`)

- React component library purpose-built for AI interfaces (Ant Group).
- **License**: MIT (Ant Design lineage). Clean for enterprise use.
- **Maturity**: active 2.x line with a public changelog and a large user
  base; components are iterated inside Ant Group's AI products.
- **Coverage against Appendix A**: `Conversations` maps to the session
  panel (list + switch); `Bubble` handles streaming markdown replies;
  `Sender` ships built-in voice input (`useSpeech`, Web Speech API) which
  satisfies the R-2 modality contract without any speech-to-text backend;
  `Think` / `ThoughtChain` fit evidence and triage rendering; `Sources`
  fits skill citations (SPEC-014); `CodeHighlighter` and `Mermaid` cover
  the markdown surface; `XProvider` covers theming/i18n.
- **Transport**: `useXAgent` / `useXChat` are transport-agnostic — the
  existing fetch/ReadableStream adapter stays the single owner of the wire
  protocol; the framework never speaks our schema directly.
- **Cost**: introduces a React + antd dependency tree (heavier bundle than
  today, mitigable via tree-shaking and route-level code splitting) and a
  Node build step where there is none today.

### 3.2 AgentScope Spark (`@agentscope-ai/design` + `@agentscope-ai/chat`)

- Alibaba Cloud Feitian Lab's UI system, built on Ant Design 5 + Tailwind /
  antd-style; the chat package ships Bubble / Sender / Conversations /
  ChatAnywhere with streaming, markdown + mermaid, and voice input.
- **License split**: `spark-design` is MIT but `spark-chat` is
  Apache-2.0 — workable, but two licenses to track versus one.
- **Maturity risk**: the npm packages carry the notice that they are
  "actively progressing towards open source" (external publication recent,
  fast-moving 1.1.x versions, documentation partly Chinese-first, community
  footprint small). Enterprise-critical patches would largely depend on
  upstream Alibaba priorities.
- **Fit**: strong conceptual fit (same AgentScope lineage as our runtime
  kernel, AGUI components) but the adapter work is the same as for Ant
  Design X — no protocol-level integration with our stream schema exists.

### 3.3 Alternatives considered, not deep-dived

- **assistant-ui / CopilotKit**: capable React chat frameworks, but their
  strongest value is coupling to their own runtimes/clouds; against our
  platform-owned SSE contract they reduce to the same adapter problem with
  weaker enterprise licensing clarity.
- **Extend the vanilla portal**: rejected by the SPEC-022 decision itself —
  session-panel work in hand-rolled `app.js` would be throwaway once a
  framework lands, and `app.js` at 2.2k lines is already at the size where
  component structure pays for itself.

## 4. The SSE contract adapter (primary integration risk)

Neither candidate speaks stream schema v6; both are presentation layers.
The rebuild must keep one thin, framework-facing adapter module that:

1. Owns transport: `fetch` + `ReadableStream` (never `EventSource`), POST
   body and `Bearer` header included.
2. Translates frame vocabulary into framework models: agent deltas →
   streaming bubble content; `tool_result` → evidence/thought-chain items;
   `confirmation_request` → anchored confirmation card; stream close /
   truncation → explicit terminal states (the current portal already locks
   cards on truncated streams — that behavior must survive verbatim).
3. Consumes SPEC-022 session API: `GET /api/v1/sessions` (cap-50,
   `pending_confirmation` badges), `GET/DELETE /api/v1/sessions/{id}` with
   404 anti-enumeration and 409-parked delete handling, 30s refresh +
   lifecycle-event refresh of the panel.

This adapter is the only module allowed to know about frame types; every
view consumes typed models. That boundary is what makes the framework
swappable later and keeps stream schema v6 (and future v7) changes
one-file fixes.

## 5. Invariants the rebuild must preserve

- **Click-gated HITL (SPEC-022 R-2 Invariant II)**: voice input may compose
  chat turns (`input_modality: "voice"`) but can never approve or deny a
  confirmation; confirmation cards stay button-only.
- **Deny-by-default view gating**: role-scoped views (auditor, operator,
  platform-admin) keep their policy-gated endpoints; the router hides what
  the token cannot read.
- **Evidence anchoring (SPEC-011 R-4)**: provenance stays inline next to
  the answer it grounds, collapsed by default.
- **No fabricated history**: `transcript_available=false` renders the
  explicit "history unavailable" state.

## 6. Build toolchain and deployment consequences

- Adds a Node build stage to `products/operator-portal/Dockerfile`
  (multi-stage: node build → nginx runtime); the runtime image stays
  nginx-static, so serving, probes, and the `/api/` proxy are unchanged.
- `PLATFORM_VERSION` injection and cache-busting become build-time
  content-hashing (better than manual busters); `make validate-version`
  keeps asserting the version constant at its new home.
- No backend changes are required by the rebuild itself; SPEC-024 (model
  dropdown) remains its own backend slice with UI landing here.

## 7. Recommendation

**Adopt Ant Design X on React (TypeScript, Vite build) for the rebuild.**

Rationale: single MIT license, mature and actively maintained with a large
community, component inventory maps almost one-to-one onto the SPEC-022
Appendix A contract plus our evidence/citations surfaces, and its
transport-agnostic hooks let the platform-owned SSE adapter remain the only
wire-protocol owner. AgentScope Spark is the runner-up with a strong
conceptual fit, but its open-source maturity, license split, and small
external community make it the riskier enterprise bet; revisit it only if
upstream stabilizes and the adapter boundary proves costly.

## 8. Open questions for the spec

- Migration phasing: chat-first rebuild with Control/Workspace views
  migrated after, or big-bang? (Recommendation: chat-first; the session
  workspace is the value driver.)
- Dark-theme token mapping from the current `:root` CSS variables into
  antd design tokens.
- SPA routing vs the current single-page view switching (nginx `try_files`
  fallback already supports it).
- Whether `Conversations` virtualization is needed at the cap-50 list size
  (almost certainly not; keep it simple).

## 9. Promotion

Findings land here per the roadmap promotion rule; on approval, the item
promotes to `SPEC-023-portal-framework-rebuild` drafting, carrying SPEC-022
Appendix A as its UI contract and this memo's adapter boundary (section 4)
as its core architecture requirement.
