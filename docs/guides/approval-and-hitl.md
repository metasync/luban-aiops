# Approval and HITL Governance Guide

How tool execution is approved on the Luban AIOps platform: which layers decide,
how to manage them, and where the model is heading. Written for operators and
platform administrators (SPEC-021, approval tiers per SPEC-030).

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
  non-read tool additionally requires `tools:mutate` (granted by default to
  `platform-admin`, `approver`, and `operator` — the approver grant carries
  tier_2-approved executions, which resume under the confirmer's delegated
  token; see the SPEC-030 R-3 note under Role Guidance below); read tools
  keep requiring only `tools:invoke`.
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
  refusal/interrupt back to the agent; nothing runs silently. Since SPEC-030 the
  card also carries an approval-tier badge, and the gateway bridge enforces who
  may decide: batches parked under a `require_approval` rule may need a
  designated approver distinct from the requester (see the approval-tier
  section below).
- **What it does NOT protect against:** it does not replace the gateway gates:
  an approved call is still checked against `tools:mutate` and RBAC when it
  reaches the tool-gateway.

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
`tools:mutate` gates the *execution*. A tier_2-approved call resumes under
the confirmer's delegated token (SPEC-030 R-3), so the shipped bundle
grants `approver` the execution actions — otherwise the approved execution
would fail closed at admission. Two-person control is enforced at the
decision gate instead: an approver's own parked call still needs a distinct
designated approver, because tier_2 blocks self-approval.

### Approval tiers: `require_approval` on the confirm path (SPEC-030)

`require_approval` is now a first-class policy outcome on the confirm path,
with two tiers:

- **`tier_1` — operator confirmation.** The session operator confirms their
  own parked card (destructive-but-routine actions). This is the default
  behavior for parked calls with no `require_approval` rule.
- **`tier_2` — designated approver.** Only roles named in `decided_by_roles`
  may approve, and self-approval is blocked by default: the requester cannot
  approve their own parked call. Deny stays open to every `chat:confirm`
  holder, so a requester can always cancel their own parked call.

The shipped bundle rule is `require-approval-tools-mutate`:

```yaml
- id: require-approval-tools-mutate
  domain: action_authz
  description: Mutating tool execution requires tier-2 approval by a designated approver distinct from the requester.
  priority: 200
  enabled: true
  match:
    roles_any: ["platform-admin", "approver", "operator", "developer"]
    actions_any: ["tools:mutate"]
  decision:
    outcome: require_approval
    approval:
      tier: tier_2
      decided_by_roles: ["approver", "platform-admin"]
```

The gateway enforces the tier on `POST /api/v1/chat/confirm`: non-deciders and
self-approvals receive a structured 403 naming the reason
(`not_a_designated_approver` / `self_approval`), the attempt is audited as a
blocked `confirmation_decided`, and the parked call stays parked. Author a
`tier_1` rule the same way (`tier: tier_1`, omit `decided_by_roles`) for
destructive-but-routine actions added later; `require_approval` rules are only
valid on bridged actions (`tools:mutate` today) — the engine rejects others at
bundle load.

### Approval inbox and durable confirmation cards (SPEC-031)

Every parked confirmation is recorded durably (Postgres in deployed
environments, on the shared `AGENT_STATE_DB_URL` posture) together with its
resolution — status, decider, decision, and timestamps. Two surfaces build on
the record store:

- **Owner transcript cards.** The session detail carries an additive
  `confirmations` array, so a card survives re-login, pod restarts, and
  replica boundaries. Decided cards render read-only with decider
  attribution; pending cards stay actionable in the chat. While a card is
  pending, the owner's open chat view polls the session detail on a short,
  bounded interval (SPEC-032), so a decision made from the inbox or another
  window flips the card and surfaces the resumed turn without a refresh —
  the resolution frame only rides the answering stream, and this poll is
  the owner's sync path for every other decision.
- **Approver inbox.** `GET /api/v1/approvals/inbox` (portal Approvals view,
  decider roles only) lists pending confirmations across all sessions plus
  decisions from the last 30 days, most recent first. Items are
  **metadata only** — session id/title, owner, parked calls, outcome — and
  never carry the owner's transcript text. Records are bounded (most recent
  50 per session, cascade-deleted with the session), and on startup a
  pending row older than the HITL confirmation TTL flips to expired
  (a parked kernel reply never survives its process, and a park past its
  TTL answers no confirmation on any replica — younger rows stay
  pending).

Inbox access is the `approvals:list` policy action (bundle rule
`allow-approvers-approvals-list`), granted to `approver` and
`platform-admin`; everyone else receives the standard audited policy 403.

**Race semantics.** A confirmation resolves exactly once — the outcome is
persisted at claim time, so a racing approver gets a structured result even
while the winner's resumed turn still streams. A decision against
an already-resolved confirmation answers `409 already_resolved` with the
winner's outcome (status, decider, decision, decided-at), and the portal
flips the loser's card to that outcome instead of offering a doomed retry.
Unknown confirm ids still answer 404.

### Voice-readiness: modality is never privilege (SPEC-022 R-2, SPEC-023 R-4)

Chat requests may carry an optional `input_modality` (`text` | `voice`,
default `text`). The operator portal composes voice turns itself: the chat
composer offers a microphone affordance backed by the browser's Web Speech
API (speech-to-text only — no audio is captured, stored, or transmitted),
with an explicit recognition-language selector (`en-US` / `zh-CN`,
client-side only). The transcribed text enters the draft like typing, and
the submitted turn is tagged `input_modality: "voice"`. The modality is
**metadata only**:

- It is forwarded to agent-platform, recorded in the chat log event, and
  mirrored into the `chat_started` audit details.
- It never influences policy evaluation, tool risk tiers, auto-allow
  matching, or HITL confirmation — a voice-originated request passes through
  exactly the same four layers as a typed one.
- Confirmations stay click-gated: `POST /api/v1/chat/confirm` has no
  modality field and its schema is unchanged. Confirmation cards render
  Approve/Deny buttons as the only decision surface — a voice-composed
  turn can park a confirmation, but no voice path can decide it
  (SPEC-023 invariant II, pinned by adapter tests).
- Browsers without the Web Speech API degrade gracefully: the affordance
  is disabled with an explanation and typing remains the input path.

Invalid modalities are rejected with `422` before any upstream call.

## The Road Ahead

Today's layers map onto the Tier-1
[Policy specification](../agentic-aiops-platform/policy-specification.md) as
follows:

| Today (SPEC-020/SPEC-021/SPEC-030/SPEC-031) | Tomorrow (policy specification) |
|---|---|
| Bundle `allow`/`deny` per action | `allow` / `deny` outcomes, unchanged |
| HITL confirmation (kernel ASK park) with `require_approval` tiers on the confirm path, durable records + approver inbox | `require_approval` with a dedicated approval queue, persistence, and notification surfaces (policy-center) |
| Risk-tier gate + activation flags | `allow_with_conditions` (ticket reference, change window, environment scope) |

Two extraction targets already exist as boundary stubs:

- **policy-center** — policy evaluation plus approval routing (`require_approval`,
  approval queue, separation of duties).
- **execution-runtime** — signed, bounded execution of approved actions.

**Kernel ASK confirmation and policy-level approval are different layers.** The
HITL confirmation card answers "does the session owner want the agent to run this
call now?" at the kernel. Policy-level approval answers "is this class of action
approved for this role in this environment, by a possibly different person?" at
the policy engine. Since SPEC-030 the two meet on the confirm path: the gateway
bridge evaluates the parked batch's policy action and enforces `tier_1` /
`tier_2` approval requirements before the kernel resumes. The queue, persistence,
notification surfaces, and condition-bearing approvals still arrive with the
policy-center slice.

## Role Guidance and Caveats

| Role | `tools:mutate` | `chat:confirm` | Guidance |
|---|---|---|---|
| `platform-admin` | granted | granted | Full execution capability; also a designated tier_2 approver — prefer a separate operational role for day-to-day work |
| `operator` | granted | granted | Execution role — matches the authorization matrix's `restart-service` example; cannot self-approve tier_2 batches |
| `approver` | granted | granted | Designated approver: decides tier_2 cards and works the cross-session Approvals inbox (`approvals:list`); the execution grant carries approved calls (resumed under the confirmer's token) — two-person control is enforced at the approval gate, not admission |
| `developer` | denied | granted | Can confirm tier_1 cards; tier_2 approvals need a designated approver |
| `read-only-observer` | denied | denied | Observation only; confirming is an act-on-the-system action |
| `auditor` | denied | denied | Read the trail; `confirmation_decided` + `tool_invoked` events carry the full chain |

**Separation of duties (SPEC-030).** With the shipped `tier_2` rule on
`tools:mutate`, the user whose chat turn parked a mutating batch cannot approve
it — a designated approver (`approver` or `platform-admin`) must. The
confirmer's identity rides the delegated token into the invocation and the audit
trail, blocked attempts included (`confirmation_decided` with `blocked: true`),
so every decision is attributable. Approval queues, tier 3 governance, and
condition-bearing approvals belong to the policy-center slice; until then,
treat `k8s.delete_pod` as a bounded, reversible-by-controller diagnostic action
and rely on review of the `confirmation_decided` audit events.

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
