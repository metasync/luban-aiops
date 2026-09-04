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

The skill encodes a six-step flow:

1. **Navigate** to the admin panel login page (binds the flow)
2. **Snapshot** the page to enumerate interactive elements
3. **Fill username** from the `admin-portal` credential set
4. **Fill password** from the `admin-portal` credential set
5. **Click "Sign In"** — this is the single HITL gate (write-tier)
6. **Navigate** to the user's reset page with the new password as a URL parameter

The admin panel's reset page auto-fills the password fields from the URL
parameter and auto-submits, so no second `web.click` is needed. This keeps
the flow at exactly one HITL gate (the sign-in click), satisfying the
one-gate-per-flow invariant (SPEC-049 D-3).

## Key design decisions

### Why admin login is the HITL gate (not the reset)

The sign-in click is the access control boundary. Once the operator approves
"sign in as admin", the subsequent navigation and auto-submit are read-tier
operations that don't need additional gates.

### Why `web.fill_credential` instead of `web.type`

`web.type` is write-tier — each call parks its own HITL card. Using
`web.fill_credential` (read-tier) for form filling keeps the HITL count at
one. Credentials also never appear in tool outputs or logs (SPEC-049 R-5).

### Why the new password is a URL parameter

Passing the new password as a URL parameter lets the admin panel auto-fill
and auto-submit the reset form. This avoids a second `web.click` (which would
be a second HITL gate) and a `web.type` (which would be write-tier).

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
3. Update the skill document's frontmatter (`web_target`, `risk_class`)
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
