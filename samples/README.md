# Samples

Self-contained tutorial samples for the Luban AIOps platform. Each sample
demonstrates a complete automation pattern — skill document, demo script, and
any sample-specific target infrastructure — so you can discover, run, and
adapt it for your own use case. Sample skills install into a running cluster
with `make deploy-samples`; the platform never hard-wires a specific sample.

## Available samples

### Web checks

| Sample | Description |
|---|---|
| [web-checks/password-reset](web-checks/password-reset/) | Automate a password reset in a legacy admin panel using browser web-check tools with a single HITL gate (a **bound flow**, `approval_kind: flow`) |
| [web-checks/adhoc-password-reset](web-checks/adhoc-password-reset/) | The same admin reset driven **ad-hoc with no bound flow**, so each mutating browser action parks its own per-action change-request card (`approval_kind: action`) — the unbound counterpart to `password-reset`, demonstrating SPEC-054 |
| [web-checks/skill-graduation](web-checks/skill-graduation/) | Author that same reset **ad hoc**, then **graduate** the approved mutations into an executable-flow skill and replay it under one gate — N `action` cards to author, 1 `flow` card thereafter, demonstrating SPEC-055. Ships **no `skill/`**: the skill is the artifact the demo produces |

All three target `browser-check-target`, a static page bundle in platform GitOps.
It can render a form, but it cannot answer "did that actually change anything?".

### ACME Admin

| Sample | Description |
|---|---|
| [acme-admin/health-check](acme-admin/health-check/) | Read `/healthz` over the `http.get` service-check surface — **0 cards**, the repository's first genuinely card-free skill (SPEC-058) |
| [acme-admin/user-status](acme-admin/user-status/) | Read a user's status off the rendered console through a **bound read-class browser flow** — still **0 cards**, which is the observation this rung exists to produce |
| [acme-admin/lock-unlock-user](acme-admin/lock-unlock-user/) | Lock or unlock an account with one `http.post` — **1 card**, `approval_kind: action`, decided by a second identity |
| [acme-admin/password-reset](acme-admin/password-reset/) | Reset a password through the console UI — **1 card**, `approval_kind: flow`, headed by the skill's authored `flow_intent` |

These four are one suite against one application, and read together they make a
claim none of them makes alone: **the card count tracks the *effect* of a skill,
not the surface it uses.** Rungs 1 and 3 both talk to the JSON API and differ;
rungs 2 and 4 both drive a browser and differ. See
[acme-admin/README.md](acme-admin/README.md).

`acme-admin` is the **first sample to own a container image**, and the first
category to hold infrastructure shared by all its samples rather than one:

```
samples/acme-admin/
├── README.md          # the app's own operator-facing document
├── app/               # the FastAPI application (image, tests, its own Makefile)
├── deploy/            # kustomization, deployment, service, networkpolicy
├── deploy.sh          # build + apply + ASSERT (make deploy-sample-app)
├── demo-lib.sh        # plumbing all four demos source
├── demo-suite.sh      # the four in ladder order + the cross-skill leg
├── health-check/      # ┐
├── user-status/       # │ the usual per-sample layout:
├── lock-unlock-user/  # │ README, WALKTHROUGH, skill/, demo/
└── password-reset/    # ┘
```

Deploy it out-of-band, after the platform:

```sh
make deploy-sample-app     # build the image, apply deploy/, then assert it works
make deploy-samples        # install the four skill documents
make undeploy-sample-app   # remove it again
```

**Both targets exist and both stay shipped.** `browser-check-target` still
serves the three `web-checks` samples; `acme-admin` serves these four. Rebasing
the older three onto the app — and deciding whether the static target is then
retired — is a separate slice (SPEC-060), deliberately unbundled from this one
so that neither change is unreviewable.

## Directory structure

Each sample follows this layout:

```
samples/
└── <category>/
    └── <sample-name>/
        ├── README.md           # Tutorial walkthrough
        ├── WALKTHROUGH.md      # Live, click-by-click run against a cluster (optional)
        ├── skill/              # Skill document(s) — installed by `make deploy-samples`
        ├── demo/               # Demo/test script(s)
        └── target/             # Sample-specific target infrastructure (optional)
```

Not every sample needs all subdirectories. `skill/` may even be absent by
design: `web-checks/skill-graduation` ships none because its skill is the
artifact the demo *produces*, and `deploy-samples.sh` discovers samples by
`find -type d -name skill`, so such a sample is simply invisible to the
installer (and `SAMPLE=<that-sample>` exits non-zero saying so). A category may
also hold more than samples: `acme-admin/` carries the application, its deploy
manifests and the shared demo plumbing its four samples all use, because they
are one suite against one store rather than four independent stories.

Infrastructure shared with the platform or other samples (browser target pages,
NetworkPolicy, credential sets) lives in the platform's GitOps directory and is
referenced from the sample's README — the dependency arrow is always tutorial →
platform, never the reverse. Sample skills need no GitOps wiring at all:
`make deploy-samples` installs them into a generic `samples` source (see below).

## Relationship to platform skills

Platform skills (under `shared/platform-ops/skills/`) are built-in runbooks
shipped with the platform — SRE alert handlers, Kubernetes troubleshooting
guides, and the like — ingested from the base overlay's ConfigMap mounts and
the platform git source. Sample skills are separate: they install out-of-band
via `make deploy-samples` into a dedicated `samples` source, so a tutorial can
be added or removed without touching platform GitOps. Samples are also richer:
they bundle the skill with the demo script (and any sample-specific target)
needed to run the pattern end-to-end.

## Installing samples into a cluster

Sample skills are **not** part of `make deploy` — the platform base overlay
ships no tutorial content. After the cluster is up, install samples with:

```sh
make deploy-samples                                    # install every sample
make deploy-samples SAMPLE=web-checks/password-reset   # install just one
make undeploy-samples                                  # remove them all again
```

`deploy-samples` packs the selected samples' `skill/*.md` files into the
optional `skills-samples` ConfigMap that skills-hub mounts read-only at
`/skills/samples` (source id `samples`), then restarts skills-hub to
re-ingest. Each skill's id becomes `samples/<slug>` (the mounted file name,
lowercased, non-alphanumerics collapsed to `-`). The ConfigMap is declarative
— it always holds exactly the selected set — and is not base-managed, so it
survives subsequent `make deploy` runs.

## Adding a new sample

1. Create a directory under the appropriate category
2. Add a `README.md` explaining the automation pattern
3. Add the skill document under `skill/` — unless the sample's point is that
   the platform produces it, in which case say so in the README
4. Add a demo script under `demo/`, mode `755`
5. If your sample needs its own target infrastructure, add it under `target/`
   (shared infra used by more than one consumer stays in platform GitOps)
6. Install it into your cluster with
   `make deploy-samples SAMPLE=<category>/<sample-name>` — no GitOps edits
   needed; the platform exposes one generic `samples` skill source

Two things that do not happen automatically:

- **`make e2e` has a hardcoded script list.** A new `demo.sh` does not join it
  by existing; add the path to the `e2e` target's loop in the root `Makefile`.
- **Skill ids are derived from the mounted file name**, which
  `deploy-samples.sh` builds as `<sample-dir>-<file-name>.md`. Two samples whose
  derived names collide silently re-id each other — `acme-admin/password-reset`
  names its document `ResetAcmePassword.md` for exactly this reason, since
  `web-checks/password-reset` already ships `ResetUserPassword.md`.
