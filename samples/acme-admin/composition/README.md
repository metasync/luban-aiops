# ACME Admin Account Recovery (`kind: composition`, two cards)

Rung 5 of the `acme-admin` ladder (SPEC-057 R-8). A **composition**: one
`kind: composition` document that names two skills this suite already ships, in
a declared order, and carries **no authority of its own** (ADR-0011).

Rungs 1–4 each park 0 or 1 card. This rung composes rung 4 (`password-reset`, a
bound browser flow → one `flow` card) and rung 3 (`lock-unlock-user`, one
`http.post` → one `action` card) into a single recovery runbook, and makes the
claim a composition has to earn: **ordering two mutating skills does not merge
their gates.** The runbook parks **two** cards — one per mutating sub-skill —
never one card that "covers" the other.

## What this sample contains

| Path | Purpose |
|---|---|
| `skill/RecoverAcmeAccount.md` | The composition document — `kind: composition`, an ordered `sub_skills` list of the two published skills, each with a `note`; the body carries the report-and-stop guidance and declares no `web_target`, no `steps` and no `risk_class` |
| `demo/demo.sh` | Standalone demo: five read-only legs against skills-hub (mounted + no authority → resolves → no nesting → structural pre-flight fails closed → the two-layer split) plus an optional chat leg that parks two cards on one session |
| `WALKTHROUGH.md` | The same story driven by hand through the operator portal's **Chat**, with two approvals by a second identity |

Skill id: **`samples/composition-recoveracmeaccount`**.

## Prerequisites

| Requirement | Why this rung needs it |
|---|---|
| `make deploy` | skills-hub, tool-gateway and agent-platform must be up |
| `make deploy-sample-app` | the runbook's two sub-skills both mutate the `acme-admin` store |
| `make deploy-samples` | packs **this composition and both sub-skills** into the one `samples` source, so they resolve within a single sync cycle |
| `make deploy` with the `browser-dev` + `mutating-dev` profiles | the reset needs the browser surface; the unlock needs `http.post` registered write (chat leg only) |
| `AGENT_HITL_CONFIRM_TIMEOUT` greater than `0` on agent-platform | otherwise write-tier tools are excluded and no card can appear (chat leg only) |
| A **designated approver** distinct from the operator | SPEC-030 R-4: two mutating sub-skills means two approvals, and the requester cannot decide either |
| identity-service port-forward on `18081`; platform-gateway on `18083` for the chat leg | the demo issues its own tokens for both identities |

The five **deterministic** legs need only skills-hub — they never touch the app
or the gateway, because what a composition *is* is a fact about the catalog, not
about a mutation. Only the opt-in chat leg needs the full mutating stack.

## How it works

A composition is an **ordered reference list**, delivered to the agent as
grounded guidance. Its frontmatter is the whole mechanism:

```yaml
kind: composition
sub_skills:
  - skill_id: samples/password-reset-resetacmepassword
    note: "Reset the account's password through the console UI. A bound browser flow; parks one flow card the approver decides."
  - skill_id: samples/lock-unlock-user-lockunlockuser
    note: "Clear the lock over the JSON API (unlock direction). Parks one action card. Run after the reset so the user can sign in with the new password."
```

skills-hub validates that structure at ingestion, then **resolves** each
reference against the catalog at sync: a sub-skill that does not resolve, or is
itself a composition, drops the whole document into a rejection bucket. A
surviving composition gets a **derived** `risk_class` — `write` here, because a
resolved sub-skill is `write` — persisted for display only. On the read path,
`get_skill` projects each item with its sub-skill's own `resolved_title` and
`resolved_web_target`, so the agent (and the portal's Skills viewer) sees which
target each segment is scoped to. Nothing about the order is enforced and no
sub-skill is pre-bound: the platform provides guidance, never sequencing.

## Key design decisions

### Why a composition carries no authority

A `kind: composition` document mints no token, unlocks no flow and auto-approves
no gate (ADR-0011). Each sub-skill keeps its **own** HITL gate, enforced exactly
as it is when the sub-skill runs alone — the browser flow's identity guard and
the infra write's action card. So the runbook's gate count is the **sum** of its
sub-skills' gates. The demo asserts this live in the chat leg (two durable cards
of two kinds on one session) and at the unit level in agent-platform
(`test_runtime_kernel.py::TestCompositionGateCount`).

### Why no `web_target`, no `steps`, no authored `risk_class`

Declaring a `web_target` would imply the composition binds a browser flow of its
own; declaring `steps` would imply a platform interpreter replays it; declaring a
`risk_class` would imply an author knows the composite's blast radius better than
the union of its parts. skills-hub **rejects all three** on a composition, so the
runbook cannot claim a scope it does not have. Leg 1 asserts the mounted document
declares none of them; leg 4 asserts the pre-flight rejects a document that tries.

### Why there is no control flow

A `sub_skills` item is `{ skill_id, note }` and nothing else — no `if`, `loop`,
`retry` or `on_fail`. The `note` is a sentence, never interpreted. Leg 4 asserts
a smuggled `on_fail` key is rejected: an interpreter would need loops, and a loop
defeats `GATEWAY_BROWSER_FLOW_MAX_STEPS`, the only bound on an unlocked browser
flow (SPEC-057 R-3).

### Why the validation is two layers

The structural facts a single document proves alone (the item shape, the count
cap, the no-authority keys) are checked by `_validate_composition` in ingestion,
which the operator-facing `/skills/validate` pre-flight and the `validate` CLI
share. The **cross-skill** facts (does each reference resolve, is it itself a
composition) need the catalog and are checked by `_resolve_compositions` at sync.
Leg 5 demonstrates the split honestly: the catalog-blind pre-flight **passes** a
nested reference, which is exactly why nesting is a resolution-layer rejection
(leg 3 asserts it holds for the deployed composition; skills-hub's `test_sync.py`
asserts the negative).

### Why it is not a transaction

There is no rollback and no compensation. If the second sub-skill fails, the
first sub-skill's change **stays made**. The runbook's instruction is
report-and-stop: name the sub-skill that failed and stop; never retry around a
denial. The completed prefix is recoverable from the platform's signed execution
receipts for **30 days** (`execution_records.py:31`); outside that window,
restart from the beginning. Each sub-skill re-gates on re-entry.

## Running the demo

```sh
make deploy-samples   # packs the composition + both sub-skills into `samples`

# Deterministic legs only (read-only against skills-hub; no model, no approval):
sh samples/acme-admin/composition/demo/demo.sh

# Including the chat leg: one session follows the runbook and parks two cards
# (a flow + an action), each approved by a second identity:
RUN_CHAT_LEG=true sh samples/acme-admin/composition/demo/demo.sh
```

Overrides: `TARGET_USER` (default `dave`, the seed's pre-locked user — the
locked-out account this runbook recovers), `NEW_PASSWORD` (default
`TempPass-2026!`, a one-time value that is masked everywhere and never stored).

The chat leg's prompt names the runbook skill, the credential set, the target and
the one-time value for **determinism** — the leg asserts an exact two-card count,
so it removes the one non-deterministic step (whether the model picks the runbook
you meant). In regular use none of that is required: "dave's locked out of
acme-admin — reset his password and unlock him" is enough, and the agent finds the
runbook through `skills.search`. See
[Asking for a runbook without naming it](../../../docs/guides/skills-guide.md#asking-for-a-runbook-without-naming-it)
and [WALKTHROUGH Step 4](WALKTHROUGH.md#step-4-ask-for-the-recovery).

## Where this rung sits

| rung | sample | surface | tier | cards |
|---|---|---|---|---|
| 1 | [`../health-check/`](../health-check/) | `http.get` | read | 0 |
| 2 | [`../user-status/`](../user-status/) | bound browser flow | read | 0 |
| 3 | [`../lock-unlock-user/`](../lock-unlock-user/) | `http.post` | write | 1 (`action`) |
| 4 | [`../password-reset/`](../password-reset/) | bound browser flow | write | 1 (`flow`) |
| **5** | **`composition/` (this one)** | **runbook (4 then 3)** | **write (derived)** | **2 (`flow` + `action`)** |

[`../demo-suite.sh`](../demo-suite.sh) runs all five in order and then the
cross-skill verification leg. The composition is the first end-to-end
multi-binding assertion in the suite: two sub-skills, two gates, one runbook.

## Adapting for your own runbook

1. Copy this directory to `samples/<your-category>/<your-sample>/`.
2. Author a `kind: composition` document whose `sub_skills` reference
   **existing published** single-target skills by their `<source_id>/<slug>` ids,
   in the order you want the model to attempt them, each with a plain-language
   `note`.
3. Declare **no** `web_target`, **no** `steps` and **no** `risk_class` — the
   first two are rejected outright and the third is derived for you.
4. Keep every sub-skill in the **same source** as the composition if you want it
   to resolve in one sync cycle; a cross-source reference resolves only after its
   own source has synced (eventual consistency).
5. Do not nest: a sub-skill must be a `knowledge` or `executable_flow` skill,
   never another composition (no nesting in Phase 1).
6. Keep the list within `SKILLS_COMPOSITION_MAX_SUB_SKILLS` (default `8`).
7. Put the report-and-stop instruction in the body, and let each sub-skill keep
   its own verification so the runbook never becomes the place a reader has to
   trust.
