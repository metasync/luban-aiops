# SPEC-049 Plan: Browser-Based Web Application Check Tools

## Approach

Browser capability enters exactly where every other infrastructure
capability enters: as a connector in tool-gateway. The connector owns
stateful headless browser sessions (Playwright Python driving a
chromium-headless-shell sidecar over CDP, engine swappable at
deployment level per spec D-6), registers a
small fixed tool surface through the existing `ToolRegistry` with the
existing risk-tier vocabulary, and adds three enforcement surfaces —
an origin allowlist, a skill-declared flow binding with a deviation
guard, and named credential sets. Everything downstream of the gateway
(agent toolkit wrapping, evidence frames, HITL confirmation bridge,
`tool_invoked` audit) is reused unchanged. Skills gain two optional
frontmatter keys validated on the existing ingestion path.

Implementation groups into five stages: connector core with session
pool (R-1, R-2), skills frontmatter extension (R-3), flow binding and
HITL gate (R-4), credentials and evidence handling (R-5, R-6), and
packaging/deployment/docs (R-7).

## Design Per Requirement

### R-1: Stateful browser connector in tool-gateway

- affected files / modules: new
  `products/tool-gateway/src/tool_gateway/tools/browser_connector.py`
  (+ a `browser_sessions.py` session-pool module beside it), settings
  in `tool_gateway/core/config.py`, registration in `app.py`
  `_build_tool_registry` (same conditional block as the k8s/elastic
  connectors).
- chosen approach: the connector connects to the pod's browser sidecar
  over CDP (`connect_over_cdp` against
  `GATEWAY_BROWSER_CDP_ENDPOINT`), establishing the connection eagerly
  when the flag is on so first-navigate latency is paid at pod start,
  not at first use. A `BrowserSessionPool` keyed by chat session id
  (forwarded to the gateway as a top-level `session_id` body field —
  a trusted correlation handle injected by the agent-service kernel
  on the read path and carried in the signed execution envelope on
  the write path, never model-supplied and carrying no authority;
  identity still rides the bearer token, with an identity-subject
  fallback for callers that forward no chat session) holds
  `(browser_context, page, flow_state, last_used)` entries — one warm
  browser process, sessions as contexts; an idle
  sweep closes contexts past TTL, and insertion past the cap evicts
  oldest-idle. With the flag off (or the sidecar absent), the
  connector never registers and never dials.
- alternatives considered and why rejected: bundled Chromium in the
  tool-gateway image (D-6 — image growth, memory contention with
  gateway dispatch, browser crash takes down all connectors); per-
  request browser launch (login state would not survive between tool
  calls — defeats the use case); a separate browser Deployment driven
  over CDP (parked — pays off only under concurrent multi-operator
  load); alternative engines Obscura/Lightpanda (parked with promotion
  triggers in the spec — the CDP boundary makes the swap sidecar-
  image-only).

### R-2: Bounded tool surface with a server-side URL allowlist

- affected files / modules: the connector's tool classes
  (`WebNavigateTool`, `WebSnapshotTool`, `WebScreenshotTool`,
  `WebClickTool`, `WebTypeTool`, `WebFillCredentialTool`), allowlist
  matching in `browser_connector.py`, settings knobs in `config.py`.
- chosen approach: each tool is a `BaseTool` subclass with a frozen
  `ToolDefinition` (risk tier, `category: "browser"`); snapshots use
  Playwright's accessibility tree plus interactive-element refs
  (stable per-page indices the model can address). The allowlist is
  checked before `page.goto` and re-checked on the post-navigation
  URL (redirect coverage); failures return `make_denied_result` /
  `make_error_result` — never an exception to the caller.
- alternatives considered and why rejected: CSS-selector-based tools
  (brittle on legacy UIs and push selector authoring into skills —
  the accessibility-ref posture keeps skills procedural and lets the
  model resolve elements from what it sees); an LLM-visible origin
  check only (the allowlist is server-side by construction).

### R-3: Skill frontmatter declaration for web flows

- affected files / modules:
  `products/skills-hub/src/skills_hub/services/ingestion.py`
  (`ALLOWED_KEYS` + validation), the `validate` CLI shares the path;
  retrieval surfaces expose the new keys beside existing frontmatter.
- chosen approach: two optional keys — `web_target` (URL, ≤2048
  chars, scheme restricted to http/https) and `risk_class`
  (`read` | `write`, default `read` when `web_target` present).
  Validation failures reuse the existing `Rejection` envelope;
  documents without the keys are untouched.
- alternatives considered and why rejected: a structured `steps`
  frontmatter list (pushes flow structure out of the markdown body,
  doubles the authoring surface, and the deviation guard only needs a
  step budget, not a parsed step list); a separate skill category
  (frontmatter keys keep Git-managed skills the single artifact of
  record per SPEC-014).

### R-4: Flow binding, one HITL gate per mutating flow, deviation guard

- affected files / modules: the connector's flow-state record inside
  the session pool entry; agent-platform's
  `GatewayPermissionMiddleware` interaction unchanged (write-tier
  browser tools are ASK-gated by the existing SPEC-020 hardening);
  flow-approval bookkeeping on the gateway side (bound `skill_id`,
  origin, step counter, approved flag) with the confirmation card
  carrying the flow description.
- chosen approach: `web.navigate` to a declared `web_target` binds the
  flow (skill id resolved from the caller's flow parameters — the
  agent passes the retrieved skill's id, validated against skills-hub
  on the gateway side). For `write`-class flows, the first interaction
  parks through the existing confirmation bridge with a card naming
  skill, origin, and declared step budget; approval sets the session's
  approved flag, denial clears the binding. Every interaction checks
  (bound flow present) ∧ (approved) ∧ (steps < budget); any failure
  escalates to a per-action ASK (or denial when bridging is disabled)
  — the "silently never runs" posture of SPEC-020.
- alternatives considered and why rejected: per-click confirmation
  (confirmation fatigue makes operators rubber-stamp — worse than the
  gate it replaces); fully free interaction after one approval (no
  deviation guard against misclicks and prompt-injected pages).

### R-5: Named credential sets, secrets out of skills

- affected files / modules: `config.py` (path-only knob), a
  `credential_sets.py` loader in the connector package, the
  `WebFillCredentialTool`, masking in the snapshot builder.
- chosen approach: the loader parses the secret-mounted JSON file
  once at connector init and on mtime change; values are injected via
  Playwright fill and immediately masked in all downstream
  representations. Secret sync follows the existing dev-k8s
  `sync-skills-secrets.sh` idempotent pattern for the demo credential
  set.
- alternatives considered and why rejected: inline env credentials
  (no multi-app story, leaks into pod env dumps); extending the
  identity-broker delegation chain to form login (the chain is
  OIDC-to-API by design; legacy login forms are per-app and
  per-tenant, which is exactly what credential sets model).

### R-6: Screenshots and evidence within existing caps

- affected files / modules: `WebScreenshotTool` (Pillow-free JPEG
  re-encode via Playwright's screenshot options + a downscale loop to
  the byte cap), snapshot truncation reusing the gateway's existing
  output-cap helpers.
- chosen approach: base64 JPEG in `data.screenshot` beside `title`/
  `url`; agent-platform needs no changes — the evidence middleware
  already frames `tool_result` payloads and applies the entry caps.
- alternatives considered and why rejected: file-reference screenshots
  (needs a serving surface and a portal fetch path; parked as Q-3's
  alternative), PNG (byte budget blows it).

### R-7: Packaging, deployment, and living docs

- affected files / modules: `products/tool-gateway/Dockerfile` /
  `pyproject.toml` + lockfile (Playwright Python dependency only — no
  browser binary in the gateway image), `shared/platform-ops/gitops/
  dev-k8s` `browser-dev` overlay patch (enables the connector **and**
  adds the chromium-headless-shell sidecar container with its own
  resource limits), sample target page (static nginx page with a login
  form + a status panel), sample web-check skill in
  `shared/platform-ops/skills/`, `shared/platform-ops/e2e/
  browser-check-demo.sh`, guides + CHANGELOG + release notes.
- chosen approach: the `mutating-dev` opt-in pattern — default
  overlays render unchanged; `make verify` asserts the default posture
  has no `web.*` tools.
- alternatives considered and why rejected: a separate
  browser-gateway image (D-1).

## Sequencing And Dependencies

1. Connector core: session pool + read tools + allowlist (R-1, R-2) —
   depends on nothing.
2. Skills frontmatter keys (R-3) — independent of stage 1, can land in
   the same wave.
3. Flow binding + HITL gate + deviation guard (R-4) — depends on
   stages 1–2.
4. Credential sets + screenshot/evidence handling (R-5, R-6) — depends
   on stage 1; can parallel stage 3.
5. Packaging, overlay, demo skill, docs, release train (R-7) — depends
   on stages 1–4.

## Test Strategy

- unit tests:
  - tool-gateway: session pool lifecycle (TTL, cap, eviction) with a
    fake Playwright layer; allowlist matching incl. redirect cases and
    empty-allowlist deny; tool surface registration under both
    mutating-admission states; credential loader (unknown set, mtime
    reload) and a leak assertion — a configured password literal must
    appear in no result/snapshot/log string; deviation-guard state
    machine (unbound, denied, exhausted, bridging-off).
  - skills-hub: ingestion acceptance/rejection matrix for the new
    keys; regression that every existing sample document still
    ingests.
  - agent-platform: browser interaction tools never land in any
    auto-allow list (the SPEC-021 invariant test, extended).
- contract tests: `ToolResult` envelope conformance for every browser
  tool incl. the base64 screenshot payload; skill frontmatter contract
  test with the additive keys.
- integration / overlay validation: `kustomize build` renders for all
  overlays incl. the new `browser-dev` patch (default overlays
  unchanged); `make verify` gate green; `browser-check-demo.sh` runs
  the full login → navigate → verify leg with the single HITL gate
  against the sample target on the canonical deployment.

## Rollout And Migration

- deployment or configuration changes: opt-in `browser-dev` overlay
  patch (connector flag + sidecar container) + one new secret
  (credential sets file); default deployments change nothing. The
  browser's memory budget lives on the sidecar container's own
  resource limits — isolated from the gateway's dispatch budget; a
  browser crash degrades only `web.*` tools. Sidecar image is the
  engine switch point (D-6, Obscura promotion trigger).
- backward compatibility notes: purely additive — new optional
  frontmatter keys, new tools that only appear when enabled, unchanged
  contracts and policy bundle.
- rollback approach: unset `GATEWAY_BROWSER_ENABLED` and drop the
  sidecar container (tools vanish from discovery on restart, contexts
  close); skills carrying the new keys stay valid documents either
  way.
