# Spike: AgentKernel Decomposition (code-modularity finding C-1)

Status: proposal — read-only assessment plus a staged, behavior-preserving plan. **Stage 1 authorized to begin 2026-11-15** by the operator as an internal refactor (no contract, schema, policy, audit, or trust-model change). This memo authorizes no feature work and no spec promotion.
Date: 2026-11-15
Roadmap home: code-modularity track opened by the v0.58.1 code & document review (finding C-1); no Exploration Backlog row yet — promote to one only if the refactor is scheduled beyond Stage 1
Verified against: `products/agent-platform/src/agent_service/runtime_kernel.py` at v0.58.1 (static inspection: 3,393 LOC; `AgentKernel` spans L246→EOF, 76 methods); the extraction pattern in `services/kernel_middleware.py`; the agent-platform suite (1,793 tests) and the SPEC-063 `execution-failure-test` campaign (795)

## 1. Question

`AgentKernel` is the largest single concentration of responsibility in the platform — a ~3,150-line class with 76 methods, roughly 13% of the 24k-LOC agent-platform product in one type. Should it be decomposed; if so, along which seams, in what order, and behind what safety gate?

## 2. Findings — measured state (verified)

- **It is an orchestration concentration, not a state god-object.** `__init__` (L247) holds only three in-memory caches (`_agents`, `_toolkits`, `_generated_literals`), two `asyncio.Lock`s, and `settings` / `_provider` / `_last_error` / `_mutating_tools_excluded` / `_recovery`. All durable persistence is already delegated to eight module-level store/registry singletons (`AGENT_STATE_STORE`, `EVIDENCE_STORE`, `CONFIRMATION_REGISTRY`, `EXECUTION_RECORD_STORE`, `AUTHORING_TRACE_STORE`, `CONFIRMATION_RECORD_STORE`, `FLOW_APPROVALS`, `FLOW_CONTEXTS`). Decomposition means splitting *coordination* responsibilities, not untangling state.
- **The extraction pattern is already proven in-tree.** `services/kernel_middleware.py` pulls the cross-cutting concerns (permission gating, tool-evidence, target-authorization, token usage) out as agentscope `MiddlewareBase` subclasses; the kernel only *assembles* them (`_build_middlewares`, L733). New collaborators should follow the same "kernel assembles, collaborator executes" shape.
- **`_ensure_toolkit` (L502) is already a named seam** — SPEC-073/076 narrow the toolkit "at the `_ensure_toolkit(read_only=True)` seam," so a `ToolkitAssembler` extraction formalizes a boundary the specs already name.
- **Two monster methods are ~20% of the file:** `_resume_confirmation` (L2965–3322, ~357 lines) and `stream_events` (L1407–1724, ~317 lines); then `_build_confirmation_frame` (~173), `_sign_flow_execution` (~148), `_prepare_executions` (~140). Splitting a 350-line method is a readability/testability win even before any class extraction.

## 3. Responsibility clusters (76 methods → 11 groups)

| Cluster | ~Methods | Owns (instance state) | Seam / risk |
|---|---|---|---|
| Runtime status & metadata | 12 | `_last_error` | public API via `api/v2/routes.py`; low risk |
| Model resolution | 6 | `_provider` | SPEC-024/026/027/071 |
| Toolkit assembly & narrowing | 8 | `_toolkits`, `_toolkit_lock`, `_mutating_tools_excluded` | **named seam** (SPEC-073/076) |
| Middleware & config assembly | 2 | — | already delegates to `kernel_middleware` |
| Agent lifecycle & cache | 11 | `_agents`, `_agent_lock`, `_recovery` | build / ensure / restore / snapshot |
| Prose-redaction wiring | 1 | `_generated_literals` | thin delegate |
| Evidence & authoring capture | 3 | — | delegates to stores |
| Turn streaming & reply | 12 | — | **`stream_events` ~317 LOC**; SSE contract adapter |
| HITL confirmation | 10 | — | **`_resume_confirmation` ~357 LOC**; SPEC-020/030/031 |
| Execution signing & dispatch | 7 | `_recovery` | SPEC-037/063/077; byte-parity critical |
| Bound-flow / browser flow-context | 4 | — | SPEC-057; delegates to `flow_approvals` |

## 4. Options weighed

| Option | Shape | Cost | Risk | Verdict |
|---|---|---|---|---|
| A. Do nothing | status quo | none | growing maintainability drag; two methods = ~20% of the file | baseline |
| B. Split the monster methods in place | break `_resume_confirmation` / `stream_events` into named private helpers; no class moves | low | low — same class, same contextvars, byte-identical output | cheap 80/20; fold into Stage 4 or run standalone |
| C. Staged collaborator extraction | pull cohesive clusters into collaborators behind thin delegators | medium, multi-stage | medium — contextvar propagation + signature-path parity | **recommended; Stage 1 authorized** |
| D. Rewrite the kernel | clean-slate redesign | high | high — highest blast radius, no incremental safety | rejected |

## 5. Recommended plan — staged, behavior-preserving, verify-gated

Every stage is one commit, keeps behavior byte-identical, and runs the full agent-platform suite plus `make verify` (incl. the 795-test SPEC-063 campaign) before landing.

- **Stage 0 (prerequisite) — characterization gate.** Confirm the status / toolkit / stream / confirmation / execution paths are pinned by golden-output characterization tests; add focused ones where the existing suite leaves a gap. No refactor proceeds without this.
- **Stage 1 (low risk) — `KernelStatus` + `ToolkitAssembler`.** Extract the 12 read-only status projections and the 8 toolkit-assembly / role-narrowing methods into collaborators; keep thin delegating methods on `AgentKernel` so the public surface consumed by `api/v2/routes.py` is unchanged.
- **Stage 2 (med) — `ModelResolver` + `AgentRegistry`.** Model selection (SPEC-024/026/027/071) and the agent build / cache / restore / snapshot lifecycle (owns `_agents` + `_agent_lock`).
- **Stage 3 (med-high) — `ExecutionDispatcher`.** The signed-request / receipt / ledger path (SPEC-037/063/077). Signature canonicalization must stay byte-identical or execution-runtime verification breaks; golden-output parity is mandatory.
- **Stage 4 (high) — `ConfirmationCoordinator` + `TurnStreamer`.** The HITL park/resume (SPEC-020/030/031) and the reply/SSE path. Do the in-place monster-method split (Option B) first, then move.

## 6. Invariants that must not move

- `agent-stream-event` / `execution-request` / `execution-receipt` stay **byte-unchanged** — the cross-product contract invariant every recent SPEC held.
- The SPEC-074 agent-role axis stays **ready-but-inert**; no extraction may accidentally thread a non-`None` agent-role.
- **Contextvar propagation** across `await` boundaries (`DELEGATED_TOKEN`, `CURRENT_PROSE_REDACTOR`, `CURRENT_AUTHORIZATION_TURN`, `AGENT_ROLE`) is the principal hidden hazard when code moves into a collaborator; each stage must prove the contextvars still resolve identically.

## 7. Backlog update

Recorded as the code-modularity track's first candidate. Stage 1 (characterization gate + `KernelStatus` / `ToolkitAssembler` extraction) authorized to begin 2026-11-15; Stages 2–4 remain proposal-only, each needing its own operator go-ahead. No spec number is assigned; promote to a spec only if the refactor is scheduled beyond Stage 1.
