# SPEC-049: Browser-Based Web Application Check Tools (v0.31.0)

**Date:** 2026-09-02
**Slice:** R5 — Hardening and External Consumption (eleventh R5 slice)
**Spec:** `docs/specs/SPEC-049-browser-web-check-tools/`

## What shipped

The platform could inspect Kubernetes state, logs, and audit trails, but
not the internal web applications operators actually check first: a login
page that renders blank, a status page behind a sign-in. SPEC-049 adds a
bounded, deny-by-default `web.*` tool surface so the agent can navigate,
read, and — behind the existing HITL gate — sign in and interact, with
every guard enforced server-side in tool-gateway:

1. **Stateful browser connector (R-1).** tool-gateway gains a
   `BrowserConnector` built on Playwright, connecting over CDP to an
   out-of-process browser — the image ships the library only, no
   browser binary. Sessions are pooled per chat session id, so a
   flow the owner binds on the read path survives the approver's
   HITL resume on the write path — the chat session id is stable
   across that identity switch, the subject is not. The id rides the
   invoke payload as a top-level correlation handle injected only by
   trusted internal callers (the agent-service kernel on the read
   path, the signed execution envelope on the write path), never from
   model-controlled parameters, and carries no authority: identity
   and authorization still derive solely from the verified bearer
   token and policy, with an identity-subject fallback for callers
   that forward no chat session. The connector registers its tools
   only when `GATEWAY_BROWSER_ENABLED=true` and a CDP endpoint is
   configured; otherwise the six tools are absent from discovery and
   invoke returns `TOOL_NOT_FOUND`.
2. **Bounded tool surface + origin allowlist (R-2).** Six tools:
   `web.navigate`, `web.snapshot`, `web.screenshot`,
   `web.fill_credential` (read tier) and `web.click`, `web.type`
   (write tier — they require `GATEWAY_MUTATING_TOOLS_ENABLED=true`
   and ride the SPEC-037 signed-execution + SPEC-038 worker-handoff
   posture). Element refs are minted only by `web.snapshot`;
   interactions resolve against the last snapshot.
   `GATEWAY_BROWSER_ALLOW_ORIGINS` is a server-side origin allowlist
   (empty = deny all): every navigation is re-checked gateway-side
   and off-allowlist origins are denied with
   `BROWSER_ORIGIN_NOT_ALLOWED`, regardless of what a skill or the
   model requests.
3. **Skill authoring fields (R-3).** skills-hub frontmatter gains
   optional `web_target` and `risk_class` fields, validated and
   carried through ingestion and search, so web-check runbooks
   declare their target origin and risk class.
4. **Flow binding, HITL gate, deviation guard (R-4).** A write-class
   check binds to its target origin for the whole flow; execution of
   the approved flow is the evidence of approval (`flow.approved`),
   one HITL approval covers the bound mutating flow, and any
   off-flow navigation or interaction is denied.
5. **Named credential sets (R-5).** `GATEWAY_BROWSER_CREDENTIAL_SETS`
   points at a secret-synced JSON file of named sets.
   `web.fill_credential` takes a set *name* only — usernames and
   passwords never enter the prompt, the tool arguments, or any
   snapshot, and filled values are masked (`value=***`) in every
   subsequent snapshot. Leak-asserted tests pin the redaction.
6. **Bounded screenshots (R-6).** `web.screenshot` returns a base64
   JPEG with an explicit size cap, so visual evidence cannot blow up
   a transcript.
7. **Packaging + dev posture (R-7).** The committed `browser-dev`
   runtime profile mirrors the `mutating-dev` precedent: it is wired
   into `dev-k8s` permanently, merges `GATEWAY_BROWSER_ENABLED=true`
   plus the dev allowlist into the ConfigMap, applies the
   strategic-merge patch adding a pod-local
   `chromedp/headless-shell` sidecar (CDP on 9222, no Service) to
   tool-gateway, and ships the `browser-check-target` sample app
   (static login + status pages) with the sample
   `platform-runbooks/web-checks/InventoryHealth.md` skill.
   `sync-browser-credentials.sh` provisions the credential-set
   secret (hooked into `make deploy`), and
   `shared/platform-ops/e2e/browser-check-demo.sh` exercises the
   full chain: 401 controls, deny-by-default when the flag is off,
   discovery with risk tiers, off-allowlist denial, allowed
   navigate/snapshot, and an opt-in HITL chat leg. The base stays
   byte-identical to the deny-by-default posture.

agent-platform's auto-allow list gains the four read-class web tools;
invariant tests pin that `web_click`/`web_type` can never satisfy the
read-only auto-allow contract, even if force-listed.

## Validation

- `make verify` green at 0.31.0: all product suites — including the
  new tool-gateway browser-connector tests (leak assertions,
  deviation guard, flow binding) and the agent-platform invariant
  tests — all four overlays (including `runtime-profiles/browser-dev`),
  policy validation, scenario guard, and version lockstep.
- Both `kustomize build` renders verified: `browser-dev` standalone
  (target app only) and `dev-k8s` full (sidecar + env merge present).
- Sample skill validated through the real ingestion path
  (`ingest_directory` → `platform-runbooks/web-checks/inventoryhealth`,
  web fields present).

## Parked

Real production browser pools, multi-step form flows beyond one
sign-in gate, and non-HTML target types remain outside the bounded
surface; those belong to a future slice if a concrete need appears.
