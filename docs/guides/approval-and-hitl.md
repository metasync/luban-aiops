# Approval and HITL Governance Guide

How tool execution is approved on the Luban AIOps platform: which layers decide,
how to manage them, and where the model is heading. Written for operators and
platform administrators (SPEC-021).

## Overview

Every tool invocation crosses four independent approval layers, each enforced at a
different point and each failing closed on its own. A mutating action
(`k8s.delete_pod` today) only executes when all four line up:

```
operator chat ──► agent-platform ──► tool-gateway ──► Kubernetes
                  │                   │
                  │ (c) auto-allow    │ (b) risk-tier admission
                  │     list check    │     tools:mutate check
                  │ (d) HITL          │ (a) policy bundle
                  │     confirmation  │     deny-by-default
                  └────── park ───────┘
```

There is no configuration path that auto-runs a mutating tool.

## The Four-Layer Approval Model

### Layer 1 — Deny-by-default policy bundle actions

- **Enforcement point:** policy engines in platform-gateway and tool-gateway,
  evaluating the shared bundle (`shared/shared-contracts/policies/policy-default.yaml`)
  on every request.
- **Configuration surface:** the policy bundle YAML, deployed as a ConfigMap.
- **What it does:** grants named actions (`chat`, `tools:invoke`, `tools:mutate`,
  `chat:confirm`, …) to named roles. No matching rule ⇒ `deny`.
- **What it does NOT protect against:** it authorizes *who may do what class of
  thing* — it does not see individual tool calls, does not pause execution for a
  human, and cannot distinguish one pod from another.

### Layer 2 — Tool risk tiers and the `tools:mutate` admission gate

- **Enforcement point:** tool-gateway registry (startup) and invoke path
  (every call), SPEC-021 R-1.
- **Configuration surface:** `GATEWAY_MUTATING_TOOLS_ENABLED` (default `false`;
  dev-k8s opts in via the committed `runtime-profiles/mutating-dev` profile,
  SPEC-022 R-3) plus the `tools:mutate` grants in the policy bundle.
- **What it does:** every tool declares `risk_level` (`read` | `write` | `admin`).
  With the flag off, write/admin tools are never registered — they are absent from
  discovery and invoke answers `TOOL_NOT_FOUND`. With the flag on, invoking a
  non-read tool additionally requires `tools:mutate` (granted by default only to
  `platform-admin` and `operator`); read tools keep requiring only `tools:invoke`.
- **What it does NOT protect against:** it gates the execution boundary, not the
  agent's behavior — an agent can still *propose* a tool the caller cannot run,
  and the gateway gate does not itself pause for a human.

### Layer 3 — The agent auto-allow list

- **Enforcement point:** agent-platform permission middleware
  (`GatewayPermissionMiddleware`), before any tool call leaves the kernel.
- **Configuration surface:** `AGENT_GATEWAY_TOOL_AUTO_ALLOW` (comma-separated
  dotted tool names; unset = built-in vetted read-only list; empty string =
  auto-approve nothing).
- **What it does:** decides which read-only tools run without asking the operator.
  Anything not auto-approved parks for confirmation (Layer 4).
- **What it does NOT protect against:** it is a kernel-local convenience for read
  diagnostics. It is **read-only by construction**: naming a mutating tool in the
  list cannot grant auto-execution — the middleware only auto-approves tools that
  are both listed *and* `is_read_only`, and such an entry is logged as a
  misconfiguration at toolkit construction.

### Layer 4 — HITL confirmation

- **Enforcement point:** agent-platform runtime kernel bridging AgentScope's ASK
  permission decision to the operator portal (SPEC-020), confirmed through
  platform-gateway's `POST /api/v1/chat/confirm`.
- **Configuration surface:** `AGENT_HITL_CONFIRM_TIMEOUT` (seconds; `0` disables
  bridging) and the `chat:confirm` policy grants.
- **What it does:** a non-auto-approved tool call parks the reply, surfaces a
  confirmation card (with a visible `mutating` badge when any parked call is
  non-read), and executes only after an explicit approve. Deny and expiry feed a
  refusal/interrupt back to the agent; nothing runs silently.
- **What it does NOT protect against:** it confirms the *session owner's* intent —
  see the v1 caveat below. It also does not replace the gateway gates: an approved
  call is still checked against `tools:mutate` and RBAC when it reaches the
  tool-gateway.

## Managing the Auto-Allow List

`AGENT_GATEWAY_TOOL_AUTO_ALLOW` controls Layer 3 only.

Semantics:

- **Unset** → the built-in vetted list (the read tools shipped with the platform:
  `k8s.list_pods`, `k8s.get_pod`, `k8s.get_events`, `k8s.get_pod_logs`,
  `skills.search`, `skills.get`, `skills.list`, `incidents.list`, `incidents.get`).
- **Empty string** → auto-approve nothing; every gateway tool parks for confirmation.
- **Comma-separated dotted names** → replaces the default entirely. Names are
  normalized to AgentScope's sanitized form (`k8s.get_pod` → `k8s_get_pod`).
  Unknown names are harmless (they simply match nothing).

To admit a read tool to auto-approval per environment, set the variable in that
environment's agent-service runtime config, e.g.:

```bash
# dev-k8s base/agent-service/runtime-config.env
AGENT_GATEWAY_TOOL_AUTO_ALLOW=k8s.list_pods,k8s.get_pod,elastic.search_logs
```

**Invariant:** mutating tools are never auto-approved regardless of this setting.
If a write/admin tool appears in the list, agent-platform logs a warning at toolkit
construction and the tool still parks for confirmation.

## Defining Approval Requirements Today

Approval requirements are defined in the **policy bundle** plus the HITL knobs —
there is no separate approval service yet.

### Policy bundle workflow

1. Edit the canonical bundle: `shared/shared-contracts/policies/policy-default.yaml`.
2. `make sync-policy` — refreshes the consumer copies (tool-gateway,
   platform-gateway packaged bundles) and the dev-k8s ConfigMap source.
3. `make validate-policy` — validates every rule against
   `policy-rule.schema.json` (also runs inside `make verify`).
4. Commit and deploy; the ConfigMap is mounted at `GATEWAY_POLICY_PATH` /
   `PLATFORM_GATEWAY_POLICY_PATH`.

### Granting or revoking `tools:mutate`

The shipped rule is `allow-operators-tools-mutate`:

```yaml
- id: allow-operators-tools-mutate
  domain: action_authz
  description: Platform admins and operators may execute mutating (write/admin risk) tools.
  priority: 100
  enabled: true
  match:
    roles_any: ["platform-admin", "operator"]
    actions_any: ["tools:mutate"]
  decision:
    outcome: allow
```

- **Grant to another role** (e.g. `developer`): add the role to `roles_any`,
  sync, validate, deploy. This is a deliberate, reviewable bundle edit — the rule
  comment should record the rationale.
- **Revoke for everyone**: set `enabled: false` (or remove the rule); deny-by-
  default closes the gate. The tool stays registered and visible in discovery but
  every invocation 403s.
- **Verify the live result**: `GET /api/v1/policy/matrix` (portal Permissions
  view) is evaluated from the enforced bundle, not hand-maintained.

### `chat:confirm` grants and the HITL knobs

- `chat:confirm` (rule `allow-chat-confirm`) decides who may approve or deny a
  parked card; granted by default to `platform-admin`, `approver`, `operator`,
  `developer`; `read-only-observer` excluded.
- `AGENT_HITL_CONFIRM_TIMEOUT`: seconds a parked batch waits before expiry.
  `0` disables bridging entirely — with bridging disabled, agent-platform also
  **excludes mutating tools from the agent toolkit**, so a mutating action can
  never silently park and never silently runs.

Note the deliberate asymmetry: `chat:confirm` gates the *decision*, while
`tools:mutate` gates the *execution*. An `approver` can confirm a card but cannot
execute the tool themselves; an `operator` can do both.

### Voice-readiness: modality is never privilege (SPEC-022 R-2)

Chat requests may carry an optional `input_modality` (`text` | `voice`,
default `text`) in anticipation of voice input. The modality is **metadata
only**:

- It is forwarded to agent-platform, recorded in the chat log event, and
  mirrored into the `chat_started` audit details.
- It never influences policy evaluation, tool risk tiers, auto-allow
  matching, or HITL confirmation — a voice-originated request passes through
  exactly the same four layers as a typed one.
- Confirmations stay click-gated: `POST /api/v1/chat/confirm` has no
  modality field and its schema is unchanged.

Invalid modalities are rejected with `422` before any upstream call.

## The Road Ahead

Today's layers map onto the Tier-1
[Policy specification](../agentic-aiops-platform/policy-specification.md) as
follows:

| Today (SPEC-020/SPEC-021) | Tomorrow (policy specification) |
|---|---|
| Bundle `allow`/`deny` per action | `allow` / `deny` outcomes, unchanged |
| HITL confirmation (kernel ASK park) | `require_approval` as a first-class policy outcome with an approval queue |
| Risk-tier gate + activation flags | `allow_with_conditions` (ticket reference, change window, environment scope) |

Two extraction targets already exist as boundary stubs:

- **policy-center** — policy evaluation plus approval routing (`require_approval`,
  approval queue, separation of duties).
- **execution-runtime** — signed, bounded execution of approved actions.

**Kernel ASK confirmation and policy-level approval are different layers.** The
HITL confirmation card answers "does the session owner want the agent to run this
call now?" at the kernel. Policy-level approval will answer "is this class of
action approved for this role in this environment, by a possibly different person,
with attached conditions?" at the policy engine. The former exists today; the
latter arrives with the policy-center slice. The guide will be updated when they
merge into one approval surface.

## Role Guidance and Caveats

| Role | `tools:mutate` | `chat:confirm` | Guidance |
|---|---|---|---|
| `platform-admin` | granted | granted | Full execution capability; prefer a separate operational role for day-to-day work |
| `operator` | granted | granted | Execution role — matches the authorization matrix's `restart-service` example |
| `approver` | denied | granted | Approve-only: can decide on cards without execution rights |
| `developer` | denied | granted | Can confirm cards; execution stays with operators |
| `read-only-observer` | denied | denied | Observation only; confirming is an act-on-the-system action |
| `auditor` | denied | denied | Read the trail; `confirmation_decided` + `tool_invoked` events carry the full chain |

**v1 caveat — self-confirmation.** The confirmer is the session owner: the same
user whose chat turn proposed the action approves it. The confirmer's identity
rides the delegated token into the invocation and the audit trail, so the act is
attributable, but there is no separation of duties yet. Two-person rules,
self-approval prevention, and approval queues belong to the policy-center slice;
until then, treat `k8s.delete_pod` as a bounded, reversible-by-controller
diagnostic action and rely on review of the `confirmation_decided` audit events.

## Related Documentation

- [Tool and Connector Guide](tool-configuration.md) — tool inventory and the
  `k8s.delete_pod` activation checklist
- [Configuration Reference](configuration-reference.md) — mutating action
  approval chain and per-service variables
- [Authorization Matrix](../agentic-aiops-platform/authorization-matrix.md) —
  role-to-action mapping design
- [Policy Specification](../agentic-aiops-platform/policy-specification.md) —
  full policy model including approval outcomes
- [Troubleshooting](troubleshooting.md) — mutating-tool symptoms
