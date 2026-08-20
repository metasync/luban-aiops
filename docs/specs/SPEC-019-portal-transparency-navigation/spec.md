# SPEC-019: Portal Transparency — Permission Matrix, Workspace Resources, and Navigation

## Status

- status: `delivered`
- owner: chi
- created: 2026-08-20
- release slice: post-R3 transparency slice (precedes R4 approval-gated actions)
- related ADRs: none (builds on SPEC-004 policy enforcement, SPEC-010 gateway split, SPEC-013 audit query pattern, SPEC-014 skills-hub, SPEC-007 tool framework)

## Summary

Give operators self-service visibility into what the platform allows and what their workspace provides: a live role × action permission matrix rendered from the enforced policy bundle, read-only Tools and Skills inventory views behind new platform-gateway proxies, and a sectioned sidebar (Chat / Control / Workspace) that scales for upcoming entries. Version display consolidates into the sidebar logo row.

## Motivation

- Today a 403 denial is unexplained: the role→action grants live only in `policy-default.yaml` behind a ConfigMap, and the durable audit trail records `policy_decision` outcomes without a place to see the rules that produced them. "Why was I denied?" should be self-service.
- Policy copies can drift (canonical, two packaged copies, overlay ConfigMap); a UI rendering the **live loaded bundle** makes drift visible instead of silent.
- Operators cannot inspect the resources granted to them (available tools, federated skills) without asking the agent; these inventories already exist server-side (tool-gateway `GET /api/v2/tools`, skills-hub `GET /skills`) but have no portal surface.
- The flat 4-item sidebar is at its limit; the roadmap (scheduled jobs, MCP server inventory, HITL surfaces) will grow it. Grouping by intent now is cheaper than restructuring later.
- The bottom version card duplicates the logo; consolidating version into the logo row removes the redundancy.

## Requirements

### R-1: Sectioned sidebar navigation and version consolidation

The operator-portal sidebar groups functions into a standalone **Chat** entry, a **Control** section (Incidents, Audit trail), and a **Workspace** section (Tools, Skills, Settings & Debug), and displays the platform version next to the logo instead of the bottom card.

Acceptance criteria:

- Chat remains the top standalone entry with its streaming dot; Control holds Incidents and Audit trail; Workspace holds Tools, Skills, and Settings & Debug, in that order.
- Section headers render as small muted labels; a section header hides automatically when every entry in it is hidden (Incidents and Audit trail stay role-gated; Permissions/Tools/Skills require a signed-in session, so a signed-out visitor sees no Control entries and the Control header hides).
- The platform version renders as a muted chip in the sidebar logo row; the bottom `.version-card` is removed; the user card stays pinned at the bottom.
- Existing role gating stays client-side convenience only (server re-enforcement unchanged); views remain hidden-not-destroyed; `styles.css`/`app.js` cache-busting query strings are bumped.

### R-2: Live permission matrix endpoint

platform-gateway serves `GET /api/v1/policy/matrix`, returning the effective role × action matrix evaluated from the currently loaded policy bundle through the existing policy engine, scoped server-side to the caller.

Acceptance criteria:

- The endpoint is protected by a new `policy:read` action granted to all five roles (`platform-admin`, `approver`, `operator`, `developer`, `read-only-observer`) in the canonical `policy-default.yaml`; deny-by-default semantics unchanged.
- The response is derived by evaluating the loaded bundle per (role × action) pair — priority, explicit-deny-wins, and disabled-rule semantics are reflected; it is never a hand-maintained table. The role list and action catalog are the unions of those referenced by the bundle's rules plus the gateway's protected route actions.
- `platform-admin` receives all rows with `"scope": "full"`; every other authenticated identity receives only rows for its granted roles with `"scope": "own"`. Filtering happens in the gateway, not the client.
- The response includes the bundle `version` and `source` distinguishing the configured policy path from the packaged-default fallback, so drift and degraded loads are visible.
- A new `shared/shared-contracts/schemas/policy-matrix.schema.json` binds the response shape; platform-gateway contract tests validate the model against the schema and cover scoping, deny-by-default, and fallback-source reporting.

### R-3: Portal Permissions view

The portal gains a **Permissions** entry in the Control section, visible to every signed-in user, rendering the matrix from R-2.

Acceptance criteria:

- The view shows a role × action table with allow/deny badges consistent with existing status-badge styling, plus the response `scope`, bundle `version`, and `source`.
- Non-admin users see only their own role rows (as returned by the server); unsigned-out state shows the standard sign-in prompt rather than an empty matrix.
- A gateway error (403/502) renders as an error status line, matching the audit/incidents views' error conventions.

### R-4: Workspace resource views — Tools catalog and Skills inventory

platform-gateway proxies read-only inventory endpoints and the portal renders them as Workspace views.

Acceptance criteria:

- `GET /api/v1/tools` enforces the existing `tools:list` action and proxies tool-gateway `GET /api/v2/tools`, carrying a delegated operator token obtained through the identity-broker exchange (delegation-client pattern); unset configuration returns 503, upstream outages 502, upstream 4xx passes through.
- `GET /api/v1/skills` enforces a new `skills:read` action (granted to all five roles) and proxies skills-hub `GET /skills`, authenticating to skills-hub with the existing skills query-credential contract (new platform-gateway settings wired from the already-provisioned dev-k8s skills secret).
- The portal renders read-only lists: tools show name/title/description; skills show id/title/tags/source. List styling follows the existing audit/incidents results conventions; empty and error states match existing patterns.
- No new write capability is introduced anywhere; both proxies are strictly read-through.

### R-5: Policy, documentation, and verification sync

The new actions, settings, and views are synchronized through the platform's policy/docs discipline and verified end-to-end.

Acceptance criteria:

- `policy-default.yaml` gains the `policy:read` and `skills:read` rules; `make sync-policy` refreshes the packaged copies and the dev-k8s ConfigMap; `make validate-policy` passes with the new rules.
- `docs/agentic-aiops-platform/authorization-matrix.md` documents the new actions and notes that the portal Permissions view renders the live enforced matrix.
- `docs/guides/configuration-reference.md` documents the new platform-gateway settings (tool-gateway URL, skills-hub URL, skills query secret) and the dev-k8s wiring.
- `make verify` is green: all product suites (including new platform-gateway tests for R-2/R-4), all overlays render, policy and version gates pass.

## Non-Goals

- Scheduled-jobs view and MCP server inventory — no backing services exist yet; tracked in the delivery-roadmap Exploration Backlog and revisited when those capabilities land.
- Renaming "Settings & Debug" — deferred until real user-facing settings exist; today's content is diagnostics and the current name stays honest.
- Policy editing or mutation from the portal — the matrix is strictly read-only; policy remains git-managed and synced via `make sync-policy`.
- HITL confirmation and approval surfaces — belong to the upcoming HITL bridging spec, which must precede any write tool.
- Agent-side changes — no kernel, toolkit, or stream-contract changes; `agent-stream-event.schema.json` is untouched.

## Impact

- products touched: `products/platform-gateway` (new routes, settings, delegation use), `products/operator-portal/web-ui` (index.html/app.js/styles.css), `products/tool-gateway` (none — consumed read-only), `products/skills-hub` (none — consumed read-only)
- contracts touched: new `shared/shared-contracts/schemas/policy-matrix.schema.json`; `shared/shared-contracts/policies/policy-default.yaml` gains two rules
- identity / policy / audit / execution safety impact: two new read actions under deny-by-default; server-side row scoping; no new write or execution surface; matrix queries ride the standard `enforce_policy` decision logging
- living state docs to update on delivery: `CHANGELOG.md`, `docs/specs/README.md` index, `docs/agentic-aiops-platform/authorization-matrix.md`, `docs/guides/configuration-reference.md`, `products/operator-portal/README.md`, dev-k8s overlay README if env changes land

## Open Questions

- none (decisions captured in draft discussion 2026-08-20: admin-only full scope; `policy:read`/`skills:read` granted to all roles; list-only skills view without search in v1; matrix queries rely on `enforce_policy` logging without a new audit event type)

## Changelog

- 2026-08-20: created as `draft`
- 2026-08-20: approved by owner; `plan.md` written, implementation starting
- 2026-08-20: status `in-progress`; R-1 auto-hide wording aligned with the signed-in gating of Permissions/Tools/Skills (Permissions is granted to all roles, so the entry hides only when signed out)
- 2026-08-20: delivered — all requirements implemented; `make verify` green (platform-gateway 137 tests incl. new matrix/proxy suites, all overlays render, 10 policy rules validated, version gate passes); route fix folded in during delivery: the matrix route maps `PolicyLoadError` from `enforce_policy`'s bundle load to 503 (not just the matrix build), keeping degraded-bundle behavior fail-closed and observable
