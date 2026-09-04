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
| [web-checks/password-reset](web-checks/password-reset/) | Automate a password reset in a legacy admin panel using browser web-check tools with a single HITL gate |

## Directory structure

Each sample follows this layout:

```
samples/
└── <category>/
    └── <sample-name>/
        ├── README.md           # Tutorial walkthrough
        ├── skill/              # Skill document(s) — installed by `make deploy-samples`
        ├── demo/               # Demo/test script(s)
        └── target/             # Sample-specific target infrastructure (optional)
```

Not every sample needs all subdirectories. Infrastructure shared with the
platform or other samples (browser target pages, NetworkPolicy, credential
sets) lives in the platform's GitOps directory and is referenced from the
sample's README — the dependency arrow is always tutorial → platform, never
the reverse. Sample skills need no GitOps wiring at all: `make deploy-samples`
installs them into a generic `samples` source (see below).

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
3. Add the skill document under `skill/`
4. Add a demo script under `demo/`
5. If your sample needs its own target infrastructure, add it under `target/`
   (shared infra used by more than one consumer stays in platform GitOps)
6. Install it into your cluster with
   `make deploy-samples SAMPLE=<category>/<sample-name>` — no GitOps edits
   needed; the platform exposes one generic `samples` skill source
