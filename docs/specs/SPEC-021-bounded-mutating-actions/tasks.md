# SPEC-021 Tasks: Bounded Mutating Actions — First Approval-Gated Write Tool

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-4: Policy bundle — `tools:mutate` action

- [x] Add `allow-operators-tools-mutate` rule (`platform-admin`, `operator`) with rationale comment; update the `allow-operators-tools` comment (risk-tier scoping retires the observer re-scope reservation) (`shared/shared-contracts/policies/policy-default.yaml`)
- [x] `make sync-policy` to refresh packaged copies (tool-gateway, platform-gateway) and the dev-k8s ConfigMap; `make validate-policy` green
- [x] Document `tools:mutate` grants in the authorization matrix (`docs/agentic-aiops-platform/authorization-matrix.md`)
- [x] Policy action constant + enforcement wiring where the gateway vocabulary is enumerated (platform-gateway/tool-gateway policy engines, route-inventory tests updated) (`products/*/tests`)

## R-1: Risk-tier admission at the tool-gateway

- [x] `GATEWAY_MUTATING_TOOLS_ENABLED` setting (default `false`) (`products/tool-gateway/src/tool_gateway/core/settings.py`)
- [x] Registry validates `risk_level` vocabulary at registration; non-read tools skipped when the gate is off (`products/tool-gateway/src/tool_gateway/tools/registry.py`, `tools/base.py`)
- [x] Invoke path selects the required action by risk tier (`tools:invoke` vs `tools:mutate`) through `enforce_policy`; structured 403 + metric on deny (`products/tool-gateway/src/tool_gateway/services/gateway_service.py`)
- [x] Risk-gate unit tests: read→invoke, write→mutate, observer 403, gate-off→`TOOL_NOT_FOUND` + absent from discovery, invalid risk level fails startup (`products/tool-gateway/tests/`)

## R-2: First bounded mutating tool — `k8s.delete_pod`

- [x] `DeletePodTool` (risk `write`, `name` required / `namespace` optional, single named pod only) with structured error mapping and evidence envelope (`products/tool-gateway/src/tool_gateway/tools/k8s_connector.py`)
- [x] Registration gated on `GATEWAY_K8S_ENABLED` + `GATEWAY_MUTATING_TOOLS_ENABLED` (`products/tool-gateway/src/tool_gateway/tools/k8s_connector.py`)
- [x] Unit tests against the fake k8s client: success path, 404/403 error mapping, evidence `risk_level: "write"` (`products/tool-gateway/tests/`)

## R-3: HITL confirmation invariant for mutating tools

- [x] Auto-allow check requires read risk: non-read tools ASK even when named in `AGENT_GATEWAY_TOOL_AUTO_ALLOW`; exclusion logged once (`products/agent-platform/src/agent_service/services/kernel_middleware.py`)
- [x] Bridging disabled (`AGENT_HITL_CONFIRM_TIMEOUT=0`) → non-read tools dropped from toolkit construction; honest no-mutating-tools posture (`products/agent-platform/src/agent_service/`)
- [x] `agent-stream-event.schema.json` v5 → v6: optional `risk_level` on `confirmation_request` pending calls; frame emission carries it (`shared/shared-contracts/schemas/agent-stream-event.schema.json`, `products/agent-platform/src/agent_service/runtime_kernel.py`)
- [x] Contract tests: v6 frame validity incl. optional `risk_level`, rejection of unknown fields; invariant tests (allow-listed write tool still parks; read behavior unchanged) (`products/agent-platform/tests/`)
- [x] Portal: `mutating` badge on confirmation cards with non-read pending calls; Tools inventory shows risk level and confirmation requirement; cache-busting bumped (`products/operator-portal/web-ui/app.js`, `styles.css`, `index.html`)

## R-5: Operator documentation — Approval and HITL Governance Guide

- [x] Write `docs/guides/approval-and-hitl.md`: four-layer approval model, auto-allow management (`AGENT_GATEWAY_TOOL_AUTO_ALLOW` semantics + read-only invariant), defining approval requirements via the policy bundle workflow (`sync-policy`/`validate-policy`/deploy), HITL knobs, policy-center/execution-runtime future mapping, role guidance + v1 self-confirmation caveat
- [x] Tool guide: `k8s.delete_pod` inventory row, `GATEWAY_MUTATING_TOOLS_ENABLED` activation checklist incl. opt-in RBAC, replace the all-read-only reservation with a guide pointer (`docs/guides/tool-configuration.md`)
- [x] Configuration reference: `GATEWAY_MUTATING_TOOLS_ENABLED` entry + mutating-capability dependency chain (`docs/guides/configuration-reference.md`)
- [x] Troubleshooting: absent mutating tool, mutating 403, no confirmation card when bridging disabled, RBAC-forbidden after approve (`docs/guides/troubleshooting.md`)
- [x] Index the new guide (`docs/guides/README.md`)

## R-6: Deployment, demo, and verification

- [x] Overlay: `GATEWAY_MUTATING_TOOLS_ENABLED=false` in tool-gateway runtime-config.env with opt-in docs; separate pod-delete RBAC manifest (pods `delete` only), applied only on opt-in (`shared/platform-ops/gitops/dev-k8s/`)
- [x] e2e demo `mutating-demo.sh`: gate-off discovery, observer 403, park with `risk_level: "write"`, deny leaves pod, approve deletes pod, audit chain (`confirmation_decided` + `tool_invoked` with confirmer identity) (`shared/platform-ops/e2e/`)
- [x] dev-k8s README activation path + guide cross-reference (`shared/platform-ops/gitops/dev-k8s/README.md`)
- [x] `make build` then `make verify` green (all suites, overlays render, policy + version gates)

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] living state docs updated (see spec `Impact` section): product READMEs (`tool-gateway`, `agent-platform`), delivery-roadmap R4 note
- [x] `CHANGELOG.md` entry added referencing the spec ID
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
