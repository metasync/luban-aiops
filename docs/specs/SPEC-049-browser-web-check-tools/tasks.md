# SPEC-049 Tasks: Browser-Based Web Application Check Tools

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to
requirement IDs.

## R-1: Stateful browser connector in tool-gateway

- [x] Add browser settings knobs (`GATEWAY_BROWSER_ENABLED`,
  `GATEWAY_BROWSER_CDP_ENDPOINT`,
  `GATEWAY_BROWSER_SESSION_TTL`, `GATEWAY_BROWSER_MAX_SESSIONS`,
  `GATEWAY_BROWSER_ALLOW_ORIGINS`, `GATEWAY_BROWSER_FLOW_MAX_STEPS`,
  `GATEWAY_BROWSER_CREDENTIAL_SETS`,
  `GATEWAY_BROWSER_SCREENSHOT_MAX_BYTES`)
  (`products/tool-gateway/src/tool_gateway/core/config.py`)
- [x] Implement `BrowserSessionPool` keyed by chat session id with
  idle TTL sweep, cap eviction, and eager CDP connection to the
  sidecar (`connect_over_cdp`) when the flag is on
  (`products/tool-gateway/src/tool_gateway/tools/browser_sessions.py`)
- [x] Implement `BrowserConnector` skeleton with conditional
  registration in `_build_tool_registry` incl. risk-tier admission for
  write-tier tools
  (`products/tool-gateway/src/tool_gateway/tools/browser_connector.py`,
  `products/tool-gateway/src/tool_gateway/app.py`)
- [x] Tests: pool lifecycle (create/reuse/TTL/eviction), disabled
  posture registers nothing, mutating-admission refusal parity
  (`products/tool-gateway/tests/`)

## R-2: Bounded tool surface with a server-side URL allowlist

- [x] Implement `web.navigate`, `web.snapshot`, `web.screenshot`
  (read tier) and `web.click`, `web.type` (write tier) as `BaseTool`
  subclasses with standard `ToolResult` envelopes and
  `source_system="browser"` evidence
  (`products/tool-gateway/src/tool_gateway/tools/browser_connector.py`)
- [x] Implement the origin allowlist check pre-navigation and
  post-redirect, with denied/error results and empty-allowlist deny
  (`products/tool-gateway/src/tool_gateway/tools/browser_connector.py`)
- [x] Tests: allowlist matrix (in/out/redirect/empty), snapshot ref
  stability, result-envelope conformance
  (`products/tool-gateway/tests/`)

## R-3: Skill frontmatter declaration for web flows

- [x] Extend `ALLOWED_KEYS` with optional `web_target` and
  `risk_class`, validation rules, and rejection envelopes
  (`products/skills-hub/src/skills_hub/services/ingestion.py`)
- [x] Expose the new keys on retrieval surfaces beside existing
  frontmatter (`products/skills-hub/src/skills_hub/`)
- [x] Tests: acceptance/rejection matrix for the new keys, regression
  that all existing sample documents still ingest
  (`products/skills-hub/tests/`)

## R-4: Flow binding, one HITL gate per mutating flow, deviation guard

- [x] Implement flow binding on `web.navigate` to a declared
  `web_target` (skill id validated against skills-hub), the single
  confirmation gate for `write`-class flows through the existing
  bridge, and the deviation guard (unbound / denied / exhausted /
  bridging-off escalation paths)
  (`products/tool-gateway/src/tool_gateway/tools/browser_connector.py`)
- [x] Extend the agent-platform auto-allow invariant test to cover
  browser interaction tools
  (`products/agent-platform/tests/`)
- [x] Tests: flow state machine — exactly one card per write-class
  flow, approval unlocks steps, denial refuses, exhaustion escalates
  (`products/tool-gateway/tests/`)

## R-5: Named credential sets, secrets out of skills

- [x] Implement the credential-set loader (secret-mounted JSON path
  only, mtime reload) and `web.fill_credential` with snapshot masking
  (`products/tool-gateway/src/tool_gateway/tools/browser_connector.py`)
- [x] Tests: unknown-set error result, leak assertion (configured
  password literal absent from every result/snapshot/log string)
  (`products/tool-gateway/tests/`)

## R-6: Screenshots and evidence within existing caps

- [x] Implement JPEG screenshot compression loop to the byte cap and
  base64 payload beside `title`/`url`
  (`products/tool-gateway/src/tool_gateway/tools/browser_connector.py`)
- [x] Tests: oversize screenshot is compressed to cap with a
  schema-valid envelope (`products/tool-gateway/tests/`)

## R-7: Packaging, deployment, and living docs

- [x] Add Playwright Python dependency + lockfile (no browser binary
  in the gateway image) (`products/tool-gateway/pyproject.toml`)
- [x] Create the `browser-dev` overlay patch (connector flag plus the
  chromium-headless-shell sidecar container with its own resource
  limits), credential-set secret
  sync entry, sample login/status target page, and sample web-check
  skill (`shared/platform-ops/gitops/dev-k8s/`,
  `shared/platform-ops/skills/`, `sync-skills-secrets.sh`)
- [x] Author `browser-check-demo.sh` exercising the
  login → navigate → verify leg with the single HITL gate
  (`shared/platform-ops/e2e/`)
- [x] Update `docs/guides/tool-configuration.md`,
  `docs/guides/skills-guide.md`, tool-gateway README, dev-k8s README,
  and architecture-overview.md connector list
- [x] CHANGELOG v0.31.0 entry + release note + release-notes index,
  version lockstep

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] living state docs updated (see spec `Impact` section)
- [x] `CHANGELOG.md` entry added referencing the spec ID
- [x] spec index in `docs/specs/README.md` updated
- [x] delivery-roadmap backlog row updated
- [x] spec status set to `delivered`
