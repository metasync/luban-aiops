# v0.51.1 — Dependency Refresh (agentscope 2.0.11)

Date: 2026-10-31
Release type: patch (dependency-only — no new routes, actions, event types,
contracts, schemas, audit changes, or execution paths)

## Summary

A routine re-lock of the agent-platform inside its declared ranges at latest
stable, prompted by the AgentScope 2.0.11 release, plus a PyJWT harmonization
across all eight backend products. The adoption posture is unchanged from
SPEC-042: **latest stable only** — no alpha, beta, RC, or dev builds — with the
OpenTelemetry instrumentation packages staying on their permanent `0.xb` channel
paired with the locked SDK. No manifest range changed in this patch; every bump
lands inside an existing caret-capped range, so this is a lockfile refresh rather
than a contract change.

## Backend re-lock

| Package | Products | From | To |
|---|---|---|---|
| agentscope | agent-platform | 2.0.8 | **2.0.11** |
| mcp (transitive) | agent-platform | 1.29.1 | **2.3.0** |
| mcp-types (transitive, new) | agent-platform | — | 2.3.0 |
| pyjwt | all eight | 2.13.0 (2.15.1 in execution-runtime) | **2.15.1** |
| certifi (transitive) | agent-platform | 2026.7.22 | 2026.10.23 |

- **agentscope 2.0.11** is the runtime kernel per ADR-0002, so the bump carries
  the kernel-verification leg (full gate below). `agentscope-runtime` stays at
  **1.1.6.post2** — still the latest published runtime — and co-resolves cleanly
  with agentscope 2.0.11: its `mcp>=1.13` and `agentscope>=1.0.14` requirements
  carry no upper bound, so no version conflict arises.
- **MCP 1.x → 2.x (transitive).** agentscope 2.0.11 moves its MCP dependency to
  `mcp>=2.0.0`, so agent-platform's transitive `mcp` bumps 1.29.1 → 2.3.0 and
  adds `mcp-types` 2.3.0. This converges on the version tool-gateway already pins
  directly (`mcp>=2.3,<3.0`, locked 2.3.0). agent-platform imports `mcp` nowhere
  directly — only agentscope does, and 2.0.11 handles protocol negotiation
  internally while retaining its `MCPClient` interface — so the bump is
  transparent to platform code.
- **PyJWT harmonization.** execution-runtime already resolved 2.15.1 while the
  other seven products sat at 2.13.0 under the same `<3.0` cap — intra-repo drift
  from lockfiles generated at different times. All eight now pin **2.15.1**.
- **Everything else was already current**: fastapi 0.141.1, pydantic 2.13.5,
  cryptography 50.0.1, httpx 0.28.1, psycopg 3.3.4, uvicorn 0.52.4, redis 6.4.0,
  jsonschema 4.26.0, and the OTel SDK 1.44.0 all sit at their latest stable within
  range.
- **Caps left parked (deliberate)**: Redis client `<7.0` (deployed server 7.2;
  client majors 7/8 were API-removal releases), Elasticsearch client `<9.0`
  (client major follows the deployed server major), tool-gateway Kubernetes client
  `<33.0` (locked 32.0.1), and `cryptography <51.0` (50.0.1 is the current stable;
  51.0.0 is unreleased, at `-dev1`).

## AgentScope 2.0.9–2.0.11 — what the platform does and does not adopt

AgentScope 2.0.9 (2026-09-28), 2.0.10 (2026-10-12), and 2.0.11 (2026-10-27) add
several new agent-facing surfaces. Consistent with the "prefer out-of-box
features, but pass the four-point adoption gate" discipline recorded in
`docs/workspace/agentscope-utilization-audit.md`, this patch adopts **none** of
the new capabilities — it only moves the pinned kernel version:

- **`ModelRouterMiddleware` + `agentscope.classifier`** (2.0.9/2.0.10) — *not
  adopted*. Automatic per-input model routing is a genuine candidate that would
  extend the existing `MODEL_CATALOG` + per-turn `model_id` selection and the
  SPEC-065 token-cost direction; deferred for an adoption-gate spike.
- **`AskUser` tool** (2.0.9) — *not adopted*. Agent-initiated multiple-choice
  prompts complement the gateway-permission HITL confirmation cards; deferred
  (needs a new v2 stream frame plus a resume path).
- **`agentscope.sop` (Standard Operating Procedures)** (2.0.9) — *not adopted*.
  Ordered, verified, resumable milestones overlap the executable-flow runbook
  rendering; deferred for an evaluation memo (must preserve the gateway, HITL, and
  evidence guarantees).
- **`TeamPipeline`** (2.0.9), **`A2AAgent`**, **realtime voice**, **ASR**,
  **`agentscope.tui`**, **RAG LLM reranking** — *not adopted*; out of scope for the
  single-agent, headless, read-only operational posture (see the utilization
  audit's decision matrix for channels/hub, sandboxes, and RAG).
- **Agent-driven context compression (`CompressContext`)** — already adopted under
  SPEC-064 R-2 (`compression_tool_enabled`, default off); unchanged here.

The `Toolkit.tool_groups` internal surface that the utilization audit flags for
re-verification on every agentscope upgrade is re-pinned by the agent-platform
suite under 2.0.11 and passes, alongside the kernel-middleware, HITL
confirmation, gateway-tool, evidence-store, and entrypoint tests.

## Verification

Full root `make verify` gate at 0.51.1, all legs green (exit 0):

- All eight product suites under frozen sync after the re-lock: agent-platform
  1633, tool-gateway 1066, platform-gateway 473, skills-hub 291, audit-service
  147, incident-service 138, execution-runtime 94, identity-broker 63
  (**3905 passed**).
- Kustomize overlays render; dashboard, policy + policy-scenario,
  version-lockstep (`VERSION=0.51.1`), secret-vocabulary, and password-policy
  validations pass; the local secret-delivery demo runs.
- Operator-portal vitest suite (**537 passed**) and the typechecked production
  build (vite 8.2.2) are green.
- Docker-backed integration legs: audit-contract Postgres proof (2.4s),
  delegated-custody (30.2s), delegated-runtime p5b, delegated-multiproc p5c, and
  delegated-edge p6 all pass.
- SPEC-063 execution-failure campaign: **795 passed, 2 deselected** in 37:12, exit
  0, on a responsive Docker daemon — the environmental wedge recorded during the
  v0.43.x campaign did not recur.
- agentscope 2.0.11 kernel leg: the agent-platform suite (including the
  `tool_groups` internals pinning tests and the kernel-middleware tests) passes
  against the upgraded kernel.

## Posture

No behavior, contract, policy, audit, schema, or execution change. Routes,
actions, event types, and execution paths are untouched; identity, policy, audit,
and execution safety semantics are unchanged. The only functional delta is the
upgraded dependency set itself. AAP compatibility remains unverified and DI-070 is
unchanged.
