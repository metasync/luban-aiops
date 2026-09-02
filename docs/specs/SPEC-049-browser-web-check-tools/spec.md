# SPEC-049: Browser-Based Web Application Check Tools

## Status

- status: `delivered`
- owner: luban-platform-team
- created: 2026-09-02
- approved: 2026-09-02
- delivered: 2026-09-02 (v0.31.0)
- release slice: R5 — Hardening and External Consumption (eleventh R5
  slice, target v0.31.0)
- related ADRs: none (lineage: drafted memo-free from the 2026-09-01/02
  operator design discussion per the SPEC-045/046 precedent; extends
  SPEC-007 tool execution framework, SPEC-014 skills and grounded
  guidance, SPEC-018 kernel middleware, SPEC-020 HITL confirmation
  bridging, SPEC-021 bounded mutating actions, SPEC-030 require-approval
  semantics)

## Summary

Operators need the agent to check web applications — including legacy
web apps — for healthness and troubleshooting: log in, click through to
a specific page, and verify what is shown there. The team encodes these
procedures as skills. This spec delivers a stateful browser connector in
tool-gateway (headless Chromium via Playwright) exposing a bounded
navigation/inspection tool surface, driven by skill-declared flows with
a URL allowlist, named credential sets, flow-level risk declaration,
one HITL gate per mutating flow, a deviation guard, and screenshots in
the existing evidence chain. It adds **no new policy actions and no new
audit event types**: browser tools ride the existing risk-tier admission,
`tools:invoke` / `tools:mutate` gates, SPEC-020 confirmation bridge, and
`tool_invoked` audit events.

## Motivation

- Today the platform reaches Kubernetes, Elastic, skills, and incidents
  through tool-gateway connectors, but has no way to interact with web
  applications — a large share of the systems operators actually run,
  including legacy apps whose health can only be verified through their
  UI (login, navigate, inspect a page).
- Operators already author skills describing these check procedures
  (log in, click a button, reach a page, verify). The skills are
  grounded guidance (SPEC-014) but the agent has no browser capability
  to execute them, so the guidance cannot be acted on.
- The AgentScope ecosystem covers the browser mechanics (Playwright,
  browser-use patterns); the gap is platform integration: policy
  enforcement, evidence, credential handling, and HITL governance. The
  direct-browser-in-agent-platform option is the same rejected option
  as direct K8s clients in the tool-gateway ADR lineage — it would
  bypass the policy engine and evidence chain.
- This release slice is the right time: R5's theme is broader adoption
  and stable reuse, and web-app checks are the most-requested external
  consumption surface after read-only K8s/Elastic access.

## Requirements

Each requirement is stable once the spec is `approved` and carries
testable acceptance criteria.

### R-1: Stateful browser connector in tool-gateway

tool-gateway gains a `BrowserConnector` behind an off-by-default flag,
holding stateful headless browser sessions keyed by the caller's chat
session id. The browser engine runs in a sidecar container inside the
tool-gateway pod; the connector drives it over CDP
(`GATEWAY_BROWSER_CDP_ENDPOINT`, default `ws://localhost:9222`), which
keeps the engine swappable at deployment level with zero connector
changes (see D-6):

- `GATEWAY_BROWSER_ENABLED` (default `false`) controls registration;
  when disabled, no browser tools appear in the registry and the
  browser runtime is never launched.
- Sessions are created on first use per chat session id, idle-expire
  after `GATEWAY_BROWSER_SESSION_TTL` (default 600 s), are capped at
  `GATEWAY_BROWSER_MAX_SESSIONS` (default 4) with oldest-idle eviction,
  and close their browser context on expiry/eviction.
- The connector follows the existing `BaseTool` / `ToolRegistry`
  pattern; every tool returns the standard `ToolResult` envelope.

Acceptance criteria:

- With the flag off, `GET /api/v2/tools` lists no `web.*` tools and no
  browser process is started.
- With the flag on, `web.*` tools are listed and invocable; a session
  reuses its browser context across calls within the TTL; after TTL or
  eviction the context is closed and resources released.
- Connector registration honors risk-tier admission (SPEC-021 R-1):
  with `GATEWAY_MUTATING_TOOLS_ENABLED=false`, the interaction tools
  are refused registration exactly like `k8s.delete_pod`.

### R-2: Bounded tool surface with a server-side URL allowlist

The connector registers a small, fixed tool surface with risk tiers
matching their effect on target systems:

- `web.navigate(url)` — read tier: open a URL in the session's browser,
  wait for load, return final URL and title.
- `web.snapshot()` — read tier: return a bounded accessibility-tree /
  text snapshot of the current page (interactive elements enumerated
  with refs usable by the interaction tools).
- `web.screenshot()` — read tier: return a bounded screenshot (see R-6).
- `web.click(ref)` and `web.type(ref, text)` — write tier: act on the
  element identified by a snapshot ref.
- `web.fill_credential(field, credential_set)` — read tier: fill a
  username or password field from a named credential set (R-5); the
  value never appears in any result, snapshot, screenshot metadata, or
  log (SPEC-009 redaction posture).

`GATEWAY_BROWSER_ALLOW_ORIGINS` is a comma-separated origin allowlist
(patterns, e.g. `https://inventory.internal:8443`). Navigation to an
origin outside the allowlist returns a `denied` result
(`BROWSER_ORIGIN_NOT_ALLOWED`); redirects landing outside the allowlist
halt the session's page and return an error naming the offending origin.
An empty allowlist denies all navigation (deny-by-default).

Acceptance criteria:

- Each tool returns the standard `ToolResult` envelope with the
  evidence block (`risk_level`, `duration_ms`, `executed_at`,
  `source_system="browser"`).
- Navigate/snapshot/screenshot require only `tools:invoke`;
  click/type additionally require `tools:mutate` and the mutating
  admission flag.
- Out-of-allowlist navigation and out-of-allowlist redirect landings
  are denied/errored server-side regardless of skill or model input.

### R-3: Skill frontmatter declaration for web flows

skills-hub gains two optional frontmatter keys so a skill can declare
itself a web-check flow; skills without them are ingested unchanged:

- `web_target` (string, ≤2048 chars): the flow's entry URL.
- `risk_class` (string, one of `read` | `write`): the declared effect
  of the flow's interactive steps; defaults to `read` when `web_target`
  is present without `risk_class`.

Ingestion validates the keys on the existing code path
(`ALLOWED_KEYS`, `skills_hub.validate`); an invalid `risk_class` or a
malformed `web_target` is a rejection with the usual reason envelope.
The procedural steps stay in the markdown body exactly as today — no
new body format.

Acceptance criteria:

- A document with valid `web_target` + `risk_class` ingests and the
  fields are retrievable beside the existing frontmatter.
- A document with `risk_class: destroy` (or malformed `web_target`)
  is rejected at ingestion and by `python -m skills_hub.validate`.
- All existing skill documents ingest unchanged.

### R-4: Flow binding, one HITL gate per mutating flow, deviation guard

Interaction tools execute only inside a declared, approved flow — the
SPEC-037 precedent (signed plan bound at approval time) applied to
browser steps:

- Starting a flow binds the skill's declaration to the browser session:
  `web.navigate` to the declared `web_target` (or an allowlisted URL
  under it) opens the flow and records the bound `skill_id`, origin,
  and declared `risk_class`.
- `read`-class flows run under `tools:invoke` with no extra gate.
  `write`-class flows park one confirmation card at first interaction
  through the existing SPEC-020 bridge; the card names the skill,
  target origin, and declared steps. Approval unlocks the bound flow's
  interactions for that session; denial ends the flow (browser session
  preserved, interactions refused).
- Deviation guard: an interaction whose bound flow is absent, denied,
  or exhausted (beyond the declared step budget
  `GATEWAY_BROWSER_FLOW_MAX_STEPS`, default 20) never executes silently
  — it escalates to a per-action confirmation (ASK) naming the actual
  action, or is denied when HITL bridging is disabled. Deviations are
  auditable through the existing confirmation/`tool_invoked` events.

Acceptance criteria:

- A `write`-class flow parks exactly one confirmation card; after
  approval, the declared steps execute without further cards; after
  denial, further interactions are refused with a clear error.
- An interaction outside any bound flow, or past the step budget,
  parks its own per-action confirmation (or is denied when bridging is
  off) and never executes silently.
- The existing auto-allow invariant holds: browser interaction tools
  can never join any auto-allow list.

### R-5: Named credential sets, secrets out of skills

Login credentials are platform configuration, never skill content:

- `GATEWAY_BROWSER_CREDENTIAL_SETS` (path to a secret-mounted JSON
  file) maps set name → `{username, password}`. The connector resolves
  a set by name at `web.fill_credential` call time; unknown names are
  an error result, never a crash.
- A body-level credential-blocking heuristic (rejecting documents that
  contain password-looking literals) is deliberately **not** in scope;
  the operator guidance (skills-guide) states credentials never belong
  in skills, and the tool surface makes them unnecessary.
- Credential values are never echoed in tool results, snapshots,
  evidence frames, audit events, or logs; filled fields are masked in
  snapshots (`***`).

Acceptance criteria:

- A configured set fills a login form end-to-end; the password value
  appears in no response, snapshot, screenshot, log, or audit event.
- An unknown credential set returns a structured error result.
- No configuration knob accepts inline credential values (file path
  only, secret-mounted).

### R-6: Screenshots and evidence within existing caps

- Screenshots are JPEG, downscaled/compressed to fit
  `GATEWAY_BROWSER_SCREENSHOT_MAX_BYTES` (default 65536), and carried
  base64 in the result `data` beside plain-text `title`/`url` fields.
- Snapshot text is truncated per the existing tool-data caps before it
  leaves the gateway.
- Agent-side evidence entry caps (`AGENT_EVIDENCE_ENTRY_MAX_CHARS`)
  apply unchanged; no new evidence frame type is introduced — browser
  tools emit the standard `tool_call`/`tool_result` frames.
- Audit rides existing `tool_invoked` events with `source_system`
  visible in the evidence block; flow approvals/denials ride the
  existing `confirmation_decided` events. **No new audit event types.**

Acceptance criteria:

- A screenshot exceeding the cap is compressed/trimmed to fit and the
  result envelope stays schema-valid.
- Evidence cards in the portal render browser tool results the same
  way as any other gateway tool; screenshots render from the base64
  payload.

### R-7: Packaging, deployment, and living docs

- tool-gateway's image gains only the Playwright Python dependency
  (lockfile + `make verify`); the browser engine rides a
  chromium-headless-shell sidecar container declared in the
  `browser-dev` overlay patch with its own resource limits — no
  browser binary in the gateway image.
- dev-k8s keeps the connector disabled by default; an opt-in
  `browser-dev` overlay patch (the `mutating-dev` pattern) enables it
  with a sample allowlisted target and one sample web-check skill, and
  a `browser-check-demo.sh` e2e script exercises the
  login → navigate → verify leg on the canonical deployment.
- Living docs: tool-configuration.md (knobs + allowlist + credential
  sets), skills-guide.md (authoring web-check skills, never embedding
  credentials), tool-gateway README, CHANGELOG v0.31.0 entry +
  release note + release-notes index.

Acceptance criteria:

- Default deployment (no opt-in) exposes no browser tools and starts
  no browser runtime.
- The opt-in profile runs the demo script green end-to-end, including
  the single HITL gate for a `write`-class flow.
- `make verify` green before and after `make build`.

## Design Decisions

Resolved in the draft from the 2026-09-01/02 operator design
discussion:

- **D-1: Where the browser lives.** Resolved: a connector inside
  tool-gateway. Rejected: Playwright wired directly into
  agent-platform's toolkit (bypasses policy enforcement, evidence, and
  audit — the same rejected option as direct K8s clients); rejected: a
  new product service (premature — one connector, one deployment).
- **D-2: Automation layer.** Resolved: Playwright (Python) inside the
  connector. The Playwright-MCP-server shape is parked with the
  exploration backlog's MCP-exposure candidate — when connectors can be
  served as MCP endpoints without bypassing policy, the browser
  connector is a natural first candidate.
- **D-3: Risk granularity.** Resolved: per-flow declaration
  (R-3/R-4), not per-tool. `web.click` is one tool serving both
  harmless and destructive targets, so tool-level risk would force
  either a confirmation per click or no gate at all; the flow-level
  declaration plus deviation guard preserves the SPEC-021/030 posture
  with one operator decision per mutating flow.
- **D-4: Credentials.** Resolved: named credential sets from a
  secret-mounted file (R-5). Rejected: credentials in skills
  (git-federated, readable, wrong trust domain) and per-user delegated
  tokens for form login (the delegation chain covers OIDC-to-API, not
  arbitrary legacy login forms).
- **D-5: Version target.** Resolved: v0.31.0 (minor) — new platform
  capability, additive surfaces only; SPEC-048 owns the v0.30.0 train.
- **D-6: Browser engine and execution shape.** Resolved 2026-09-02
  after the agent-browser survey: a chromium-headless-shell sidecar
  container in the tool-gateway pod — one warm browser process,
  sessions as contexts, pre-warmed when the flag is on — driven over
  CDP, so the engine is swappable at deployment level with zero
  connector changes. Rejected: bundled Chromium in the gateway image
  (image growth, memory contends with gateway dispatch, a browser
  crash would take down all connectors); vercel `agent-browser`
  (CLI/shell-out shape misfits an in-process connector; still Chrome
  underneath); ego-lite (desktop human+agent session-sharing model
  inverts the credential/isolation posture); hosted SaaS browsers —
  Browserbase/Anchor/Hyperbrowser/Kernel (data residency); Steel /
  Browserless (Chrome footprint unchanged, scraping-shaped features).
  AgentScope/browser-use ship orchestration only and never a browser
  binary, so the engine decision is platform-owned either way.

## Invariants preserved

- Deny-by-default: empty allowlist denies all navigation; unregistered
  tools never exist; interaction tools can never be auto-allowed.
- No new policy actions (`tools:invoke` / `tools:mutate` cover the
  whole surface) and no new audit event types.
- The `ToolResult` envelope and `tool-result.schema.json` are
  unchanged; the `tool-invocation.schema.json` request shape is
  unchanged.
- HITL stays click-gated; the single-flow approval rides the existing
  confirmation bridge, no new approval semantics.
- Skills remain Git-managed team knowledge; this spec adds two optional
  frontmatter keys, never a new body format.

## Impact

- products touched:
  - `products/tool-gateway` — browser connector (CDP client), session
    pool, allowlist + credential-set config, lockfile (Playwright
    Python dependency), tests.
  - `products/skills-hub` — two optional frontmatter keys, validation,
    tests.
  - `products/agent-platform` — no code change expected (browser tools
    flow through existing discovery/toolkit wrapping); verify auto-allow
    exclusion in tests.
  - `shared/platform-ops` — `browser-dev` overlay patch (including the
    chromium-headless-shell sidecar container with its own resource
    limits), sample target
    page + sample web-check skill, `browser-check-demo.sh`, secrets
    sync script entry for the credential-set secret.
- contracts touched: none changed — `tool-result.schema.json`,
  `tool-invocation.schema.json`, and the skill frontmatter contract
  (two additive optional keys, validation in skills-hub's own path).
- identity / policy / audit / execution safety impact: policy unchanged
  (existing actions), audit unchanged (existing event types), execution
  safety strengthened (allowlist + deviation guard + single HITL gate);
  browser credentials stay pod-local secrets, never cross a service
  boundary.
- living state docs to update on delivery: tool-gateway README,
  `docs/guides/tool-configuration.md`, `docs/guides/skills-guide.md`,
  dev-k8s README, `CHANGELOG.md`, release notes + index,
  architecture-overview.md connector list.

## Open Questions

None — Q-1 (browser runtime packaging) resolved 2026-09-02 by the
agent-browser survey as D-6; Q-2 resolved: the flow gate inherits the
existing `tools:mutate` tier_2 designated-approver rule (no new
approval semantics); Q-3 resolved: inline base64 JPEG under the
64 KiB cap for portal parity (file references parked).

## Parked / promotion triggers

- **Obscura engine (Apache-2.0, Rust + V8)** — CDP drop-in for
  Playwright, ~57 MB image, instant startup; parked 2026-09-02 as the
  highest-priority alternative engine: promote when a target legacy
  app passes a smoke check against it **and** its screenshot fidelity
  is accepted as audit evidence. The swap is sidecar-image-only; if
  promoted, note its private-network default-deny needs explicit
  opt-in (the connector's origin allowlist stays the enforcement
  layer).
- **Lightpanda engine** — parked behind Obscura; promote on stable
  web-standards coverage plus full screenshot support.
- **File-reference screenshots** — the Q-3 alternative; promote if the
  64 KiB inline cap proves too lossy in live checks.
- **Separate browser Deployment** — promote on concurrent
  multi-operator load outgrowing the per-pod sidecar.
- **Playwright MCP exposure** — promote with the exploration backlog's
  MCP-exposure candidate; the browser connector is the first candidate
  to serve as MCP.
- **Plain HTTP health-probe tool** (`web.http_check`-style, no
  browser) — cheaper coverage for non-JS endpoints; promote on the
  first ask for browserless checks.
- **Vision-model navigation** (screenshot-driven element picking beyond
  accessibility snapshots) — promote on the first legacy app the
  snapshot approach cannot drive.
- **Recording / replay of flows** (author flows by recording a human
  session) — promote on the first skill-authoring friction signal.
- **Headful mode / multi-browser** — no operational need identified.

## Changelog

- 2026-09-02: drafted memo-free from the 2026-09-01/02 operator design
  discussion (browser support for web-app health checks driven by
  skills; per-flow risk declaration reusing the HITL bridge), pending
  operator approval.
- 2026-09-02: operator confirmed the Q-2 (tier_2 inheritance) and Q-3
  (inline base64) leanings; the agent-browser survey (vercel
  agent-browser, ego-lite, Steel, Browserless, hosted SaaS, Lightpanda,
  Obscura) resolved Q-1 as D-6 — chromium-headless-shell sidecar with
  the engine swappable over CDP; Obscura and Lightpanda parked with
  promotion triggers. Open Questions emptied; draft ready for
  approval.
- 2026-09-02: operator approved the draft (`draft` → `approved`) with
  no requirement changes; delivery proceeds under the house train as
  v0.31.0.
