---
kind: design
name: Support git sources with per-source PAT and subpath in skills-hub
source: session
category: adr
---

# Support git sources with per-source PAT and subpath in skills-hub

_Source: coding plans from commit period b72785d → 73c4b61 — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
The skills-hub service needs to federate skills from private GitHub repositories in-cluster, mirroring production. Two defects blocked this: the `base-uv` image has no `git` binary (so `sync.py` shelling out fails), and `SourceSpec` had no way to point a git source at a subdirectory of a monorepo, which is how real teams store skills.

## Decision drivers
- production parity for private repo federation
- keep non-secret config in ConfigMap and secrets only in Secret
- isolate failures so a missing/invalid PAT does not break local sources
- avoid bloating shared base images

## Considered options
- **Install git in the shared base image (`base-uv`) for all services** _(rejected)_ — pros: simplest change; any future service that needs git gets it; cons: bloates every service image; most services never call git
- **Use a Python git library instead of shelling out** _(rejected)_ — pros: no OS dependency; cons: adds another runtime dependency; shelling out to `git` is already the established pattern and avoids vendored lib maintenance
- **Clone the monorepo root and filter on ingest** _(rejected)_ — pros: no schema change; cons: wastes bandwidth/time cloning everything; rejects whole trees; defeats monorepo skill layout

## Decision
Add `git-minimal` only to the `skills-hub` Dockerfile, extend `SourceSpec` with an optional `path` field for git sources so ingestion roots into a subdirectory, and wire dev-k8s to read per-source PATs from `SKILLS_GIT_TOKENS` in the `skills-hub-runtime-secrets` Secret while keeping `SKILLS_SOURCES` in ConfigMap. A failing git source reports a scrubbed auth error but leaves prior snapshots and other sources intact.

## Consequences
Skills can now be sourced from private GitHub repos tracked by ref and ingested from a subpath. The image grows by ~10–20 MB for `git-minimal`; the secret sync script must be run whenever a new source_id→token mapping is added. Portal renders cited-skill chips from tool results so users can see which skill matched.