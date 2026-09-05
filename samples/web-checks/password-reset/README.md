# Password Reset via Browser Web-Check Tools

This sample demonstrates how to use the platform's browser-based web-check
tools (SPEC-049) to automate a password reset in a legacy admin panel. It
serves as a tutorial for authoring write-class skills with a single HITL
approval gate.

## What this sample contains

| Path | Purpose |
|---|---|
| `skill/ResetUserPassword.md` | The skill document — annotated with tutorial comments explaining write-class skill authoring patterns |
| `demo/demo.sh` | Standalone demo script that exercises the full flow: prerequisites → skill ingestion → tool verification → optional chat leg |

## Prerequisites

- A running dev-k8s cluster with the `browser-dev` runtime profile deployed
- The browser sidecar reachable (chromium-headless-shell in the tool-gateway pod)
- The `browser-check-target` nginx serving the admin pages
- The `admin-portal` credential set loaded via `sync-browser-credentials.sh`

## How it works

The skill encodes a seven-step flow:

1. **Navigate** to the admin panel login page (binds the flow)
2. **Snapshot** the page to enumerate interactive elements
3. **Fill username** from the `admin-portal` credential set (read-tier)
4. **Fill password** from the `admin-portal` credential set (read-tier) —
   the login form then auto-submits (legacy SSO) and redirects, so
   authentication needs no click
5. **Navigate** to the user's reset page with the new password as a URL
   parameter; the form pre-fills both fields but does not submit
6. **Click "Confirm reset"** — this is the single HITL gate (write-tier),
   landing on the destructive mutation itself
7. **Snapshot + screenshot** to verify the reset succeeded

The admin panel's reset page pre-fills the password fields from the URL
parameter but waits for the operator's click, so the "Confirm reset" action is
the flow's only write-tier interaction. This keeps the flow at exactly one HITL
gate — on the mutation the operator actually approves — satisfying the
one-gate-per-flow invariant (SPEC-049 R-4/D-3, enforced kernel-side by
SPEC-051).

## Key design decisions

### Why the reset is the HITL gate (not admin login)

The gate belongs on the action the operator actually means to approve — the
destructive mutation. Resetting a password is the mutation; signing in is not.
So authentication stays read-tier (`web.fill_credential` plus the page's legacy
SSO auto-submit) and the sole write-tier interaction is the "Confirm reset"
click. The confirmation card headlines the workflow intent ("reset a user's
password on <origin>") rather than a bare sign-in click (SPEC-051 R-6), and
leads with the skill's authored `flow_intent` — "Submit the password reset for
the target user, permanently changing their admin-portal credentials." — so the
operator reads what the gated mutation actually achieves before the demoted
DOM/technical detail (SPEC-053).

### Why `web.fill_credential` instead of `web.type`

`web.type` is write-tier — each call would park its own HITL card. Using
`web.fill_credential` (read-tier) for form filling keeps the HITL count at
one. Credentials also never appear in tool outputs or logs (SPEC-049 R-5).

### Why the new password is a URL parameter

Passing the new password as a URL parameter lets the admin panel pre-fill the
reset form through a read-tier `web.navigate`, avoiding a write-tier `web.type`
for the password fields. The form pre-fills but does not auto-submit, so the
"Confirm reset" click stays the flow's single gate. The gateway redacts the
`newpw` parameter from results, evidence, and audit (SPEC-049 R-5).

## Running the demo

```sh
# Install this sample's skill into the cluster (after `make deploy`):
make deploy-samples SAMPLE=web-checks/password-reset

# Deterministic legs only (no model interaction):
bash samples/web-checks/password-reset/demo/demo.sh

# Full flow including chat leg (requires a running agent):
RUN_CHAT_LEG=true bash samples/web-checks/password-reset/demo/demo.sh
```

`make deploy-samples` (no `SAMPLE=`) installs every sample; `make
undeploy-samples` removes them all again.

## Adapting for your own target

1. Copy this directory to `samples/web-checks/<your-sample>/`
2. Replace the admin panel HTML pages with your target's pages
3. Update the skill document's frontmatter (`web_target`, `risk_class`,
   and the optional `flow_intent` decision line for your gated step)
4. Update the credential set name in the skill and `sync-browser-credentials.sh`
5. Update the demo script's skill ID and target URLs
6. Install your skill with `make deploy-samples SAMPLE=web-checks/<your-sample>`
   — no base-overlay edits needed; the platform exposes one generic `samples`
   skill source that packs whatever `skill/*.md` your sample ships

## Infrastructure wiring

This sample is self-contained: its skill, demo, and docs live entirely under
`samples/`, and its skill is installed out-of-band by `make deploy-samples`
(which packs `skill/*.md` into the optional `skills-samples` ConfigMap that
skills-hub mounts read-only at `/skills/samples`). The platform base overlay
provides only a *generic* `samples` skill source — it never names this sample,
so the dependency arrow stays tutorial → platform.

The sample *drives* shared browser infrastructure that intentionally lives
outside `samples/`. It is also used by the SPEC-049 `browser-check-demo.sh`
smoke test, so it stays in platform space and the tutorial references it:

- **Admin pages**: `shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-check-target-pages.yaml`
- **Credential sync**: `shared/platform-ops/gitops/sync-browser-credentials.sh` (the `admin-portal` set)
- **Network policy**: `shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-sidecar-network-policy.yaml`
- **Generic skill-source hook**: the `samples` entry in `SKILLS_SOURCES` (`.../dev-k8s/base/skills-hub/runtime-config.env`) and the optional `/skills/samples` mount (`.../skills-hub/skills-hub-deployment.yaml`)
