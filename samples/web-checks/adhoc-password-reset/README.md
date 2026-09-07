# Ad-Hoc Password Reset via Per-Action Browser Approval

This sample demonstrates the **unbound, per-action** HITL approval model
SPEC-054 makes reachable: an interactive browser session that logs into a
legacy admin panel and mutates it **without declaring a flow**, so every
write-tier action parks its own change-request confirmation card.

It is the deliberate counterpart to
[`web-checks/password-reset`](../password-reset/), which performs the *same*
admin password reset as a **bound flow** that collapses to a single HITL gate
(SPEC-051). Run both to see the two approval models side by side.

## What this sample contains

| Path | Purpose |
|---|---|
| `skill/ResetPasswordAdHoc.md` | A browser **runbook** that declares **no `web_target`** — annotated with tutorial comments explaining the ad-hoc / per-action authoring pattern |
| `demo/demo.sh` | Standalone demo script: prerequisites → runbook ingestion → tool verification → optional chat leg asserting per-action cards |
| `WALKTHROUGH.md` | Live, click-by-click walkthrough against your running cluster |

## Prerequisites

- A running dev-k8s cluster with the `browser-dev` runtime profile deployed
- The browser sidecar reachable (chromium-headless-shell in the tool-gateway pod)
- The `browser-check-target` nginx serving the admin pages
- The `admin-portal` credential set loaded via `sync-browser-credentials.sh`

These are the same platform prerequisites `web-checks/password-reset` uses —
this sample ships no infrastructure of its own.

## How it works

The runbook drives an eight-step **unbound** flow:

1. **Navigate** to the admin login page with **no `skill_id`** — nothing binds
2. **Snapshot** the login form
3. **Fill username** from the `admin-portal` credential set (read-tier, by reference)
4. **Fill password** from the `admin-portal` credential set (read-tier, by reference) —
   the login form then auto-submits (legacy SSO) and redirects
5. **Locate** the target user in the user list
6. **Navigate** to the reset page with the new password as a URL parameter
   (read-tier; the form pre-fills but does not submit)
7. **Click "Confirm reset"** — a write-tier interaction with **no bound flow**,
   so it parks a **per-action** card (`approval_kind: "action"`) carrying a
   **change-request projection**
8. **Snapshot + screenshot** to verify the reset succeeded

Because no flow is ever bound, step 7 does **not** ride a one-gate flow
authority: it is approved on its own merits. Had the procedure performed N
writes, it would park N cards — there is no flow-unlock for unbound writes.

## Key design decisions

### Why the runbook declares no `web_target`

`web_target` is what lets `web.navigate(skill_id=…)` bind a flow, and a bound
`write`-class flow collapses to one HITL gate. This sample wants the opposite:
the unbound, per-action path SPEC-054 R-2 introduces. Omitting `web_target`
**guarantees** it — the gateway cannot bind a flow that was never declared, so
`web.navigate(skill_id=…)` for this runbook fails `SKILL_NOT_WEB_FLOW` and the
per-action model is enforced platform-side regardless of how the model
sequences the steps. The runbook is still a normal, ingestable skill document
(a plain runbook), so `make deploy-samples` installs it like any other.

### Why credential entry is by reference (`web.fill_credential`)

Before SPEC-054, unbound login was blocked at the **read** tier:
`web.fill_credential` inherited the flow-binding precondition and was denied
`BROWSER_FLOW_NOT_BOUND`, so the only way to enter a credential unbound was
`web.type` with the **literal secret as a tool argument** — which then landed
in the parked payload, the confirmation card, and the audit trail. SPEC-054 R-2
relaxes the precondition for read-tier ref-addressed interactions, so
`web.fill_credential` (`credential_set` + `field`) now works unbound and the
secret never appears anywhere. This is what makes "log in, then mutate"
reachable ad hoc.

### Why the new password is a URL parameter

Passing the new password as a URL parameter lets the panel pre-fill the reset
form through a read-tier `web.navigate`, avoiding a write-tier `web.type` of
the secret. The gateway redacts the `newpw` parameter from results, evidence,
and audit (SPEC-049 R-5). The form pre-fills but does not auto-submit, so the
"Confirm reset" click is the flow's single write-tier interaction.

### What the approver sees (the change-request card)

Instead of a bare tool name and a collapsed "Technical details" expander, an
`action` card leads with a **change request** (SPEC-054 R-3): a plain-language
`summary` of the mutation plus the decision-relevant fields promoted into the
approval intention, with secret values masked to `***` by the same vocabulary
the gateway redacts with. The projection is **display-only** — it rides beside
`parameters`, never inside it, so the signed `args_digest` is byte-identical
with or without it. The card also states its own `approval_kind` and persists
its top-line `message` (R-1/R-4), so the live card, the durable record, the
approver inbox, and a re-login all render the same thing.

## Running the demo

```sh
# Install this sample's runbook into the cluster (after `make deploy`):
make deploy-samples SAMPLE=web-checks/adhoc-password-reset

# Deterministic legs only (no model interaction):
bash samples/web-checks/adhoc-password-reset/demo/demo.sh

# Full flow including the chat leg (requires a running agent):
RUN_CHAT_LEG=true bash samples/web-checks/adhoc-password-reset/demo/demo.sh
```

`make deploy-samples` (no `SAMPLE=`) installs every sample; `make
undeploy-samples` removes them all again.

> **Note:** the chat leg is opt-in because it depends on the model choosing
> tools, exactly like the `password-reset` demo. Its assertions are
> **count-agnostic and tool-agnostic**: every parked card must be
> `approval_kind: "action"` with a change-request projection and no
> `flow_summary`, and every resulting execution must carry a signed receipt —
> whether the model performs one write or several.

## Adapting for your own target

1. Copy this directory to `samples/web-checks/<your-sample>/`
2. Replace the admin panel HTML pages with your target's pages (or point at
   your own allowlisted origin)
3. Keep the skill document **free of `web_target`/`risk_class`** to stay on the
   per-action path — add them only if you want to graduate to a one-gate flow
4. Update the credential set name in the runbook and `sync-browser-credentials.sh`
5. Update the demo script's target URLs and skill ID
6. Install your runbook with `make deploy-samples SAMPLE=web-checks/<your-sample>`

## Infrastructure wiring

This sample is self-contained: its runbook, demo, and docs live entirely under
`samples/`, and its runbook is installed out-of-band by `make deploy-samples`
(which packs `skill/*.md` into the optional `skills-samples` ConfigMap that
skills-hub mounts read-only at `/skills/samples`). The platform base overlay
provides only a *generic* `samples` skill source — it never names this sample,
so the dependency arrow stays tutorial → platform.

The sample *drives* shared browser infrastructure that intentionally lives
outside `samples/` (it is the same infra `web-checks/password-reset` and the
SPEC-049 `browser-check-demo.sh` smoke test use):

- **Admin pages**: `shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-check-target-pages.yaml`
- **Credential sync**: `shared/platform-ops/gitops/sync-browser-credentials.sh` (the `admin-portal` set)
- **Network policy**: `shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-sidecar-network-policy.yaml`
- **Generic skill-source hook**: the `samples` entry in `SKILLS_SOURCES` (`.../dev-k8s/base/skills-hub/runtime-config.env`) and the optional `/skills/samples` mount (`.../skills-hub/skills-hub-deployment.yaml`)
