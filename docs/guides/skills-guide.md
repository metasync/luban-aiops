# Skills and Guidance Operations Guide

Operator-facing guide for managing the skill content that powers grounded
guidance (SPEC-014): how to add, revise, and remove skills and skill sources,
how the content reaches the agent, and how to verify and troubleshoot it.

For deployment-level configuration (secrets, environment variables, the
retrieval chain), see the
[Configuration Reference](configuration-reference.md); for the agent-side
tools, see the [Tool and Connector Guide](tool-configuration.md).

## How skills reach the agent

```
team skill sources ──sync──► skills-hub ──store──► postgres (skills DB)
(local dirs / git repos)      (validate)                │
                                                        ▼
        agent ◄── skills.search / .get / .list ◄── tool-gateway
```

1. **Sources** are directories of Markdown skill documents — either `local`
   paths mounted into the skills-hub pod or `git` repositories the service
   clones. Each source has an operator-assigned `source_id`.
2. **skills-hub** syncs every source every `SKILLS_SYNC_INTERVAL_SECONDS`
   (default 300s), validates every document, and atomically replaces the
   source's slice in the store. A failed sync keeps the previous slice —
   bad content never poisons a source that used to work.
3. **The agent** reaches skills only through the tool-gateway's read-only
   tools (`skills.search`, `skills.get`, `skills.list`), inheriting policy,
   audit, and evidence-panel behavior. There is no write path from the agent.

Skill identity: `skill_id = <source_id>/<slug>`, where the slug is derived
from the file path (not frontmatter). See
[skill-format.md](../../shared/shared-contracts/skill-format.md) for the full
contract.

## The skill format in one minute

A skill is a Markdown file with YAML frontmatter:

```markdown
---
title: KubePodNotReady
description: Pod stuck in a not-ready state — triage and remediation steps.
tags: [kubernetes, pod, alerting, KubePodNotReady]
version: "1.0"
source_url: https://github.com/prometheus-operator/runbooks
---

Markdown body ...
```

Rules that matter for day-2 operations:

- `title` (≤ 200 chars) and `description` (≤ 500 chars) are **required**;
  `tags` (≤ 10), `version`, `source_url` are optional. Unknown keys are
  rejected.
- Body ≤ 64 KiB. Split long guides.
- Moving or renaming a file changes its `skill_id` — intentionally, so stale
  citations become visible. Duplicate slugs within one source are rejected;
  across sources they are fine (ids are namespaced).
- `README.md` and `NOTICE` files are skipped by ingestion.
- No secrets, hostnames, or customer data in skill bodies.
- Adapted open-source content must keep `source_url` pointing upstream and a
  `NOTICE` file in the source root (project, URL, license).

## Pre-flight validation

Always validate before publishing — the CLI uses the same code path as the
service:

```sh
# One-time setup: create the skills-hub venv
(cd products/skills-hub && uv sync)

# From the repo root, using that venv's interpreter:
products/skills-hub/.venv/bin/python -m skills_hub.validate \
  shared/platform-ops/skills/<source_id>
```

Exit code 0 means the source is safe to publish; otherwise each rejection is
reported as `(path, reason)`.

## Adding a skill to an existing source

The dev-k8s sample sources (`sre-alerting`, `platform-runbooks`) live under
`shared/platform-ops/skills/` and ship to the pod as ConfigMap volumes.

1. Create the Markdown file under the source directory (e.g.
   `shared/platform-ops/skills/sre-alerting/alerts/MyNewAlert.md`), with
   frontmatter as above. For alert runbooks, tag the skill with the alert
   name so alert → runbook lookups rank well.
2. Register the file in the GitOps overlay — ConfigMap keys cannot contain
   `/`, so keys are flattened `<dir>-<file>` and mapped back to nested paths
   in two places:
   - `shared/platform-ops/gitops/dev-k8s/base/kustomization.yaml` — add an
     entry under the source's ConfigMap, e.g.
     `alerts-MyNewAlert.md=../../../skills/sre-alerting/alerts/MyNewAlert.md`
   - `shared/platform-ops/gitops/dev-k8s/base/skills-hub/skills-hub-deployment.yaml`
     — add the matching `items:` entry mapping key `alerts-MyNewAlert.md` to
     path `alerts/MyNewAlert.md`
3. Validate, then deploy:

   ```sh
   python -m skills_hub.validate shared/platform-ops/skills/sre-alerting
   make build && make deploy
   ```

   The new pod re-syncs all sources at startup; otherwise changes appear
   within one sync interval (default 5 minutes). To force an immediate
   re-sync without other changes: `kubectl -n dev-luban-aiops rollout restart
   deployment/skills-hub`.

4. Verify (see [Verification](#verification)).

> **Git-based sources skip steps 2–3**: the service clones the repository
> itself, so merging to the tracked `ref` is enough — the next sync picks it
> up. The ConfigMap wiring applies only to `local` sources.

## Revising a skill

Edit the file in place and re-validate. Same propagation path as adding:
ConfigMap-backed sources require `make build && make deploy` (the ConfigMap
content is baked at render time); git sources propagate on the next sync
after merge.

Keep the file path stable unless you intend to change the `skill_id` —
citations in past agent answers reference the old id, and a path change makes
that visible rather than silently breaking it.

## Removing a skill

1. Delete the Markdown file from the source.
2. For ConfigMap-backed local sources, remove the corresponding entries in
   `kustomization.yaml` and `skills-hub-deployment.yaml` (a ConfigMap entry
   pointing at a deleted file breaks `kustomize build`).
3. `make build && make deploy`. The next sync atomically replaces the
   source's slice, and the skill disappears from search, list, and get.

Git sources: merge the deletion; the next sync picks it up.

## Adding a new skill source

Choose the source type:

- **`local`** (dev-k8s sample pattern): commit the documents under
  `shared/platform-ops/skills/<source_id>/` with a `README.md` (the team
  contribution template) and a `NOTICE` if content is adapted. Then wire the
  ConfigMap (`kustomization.yaml`), the volume + mount + `items`
  (`skills-hub-deployment.yaml`), and append the source entry to
  `SKILLS_SOURCES` in
  `shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env`:

  ```json
  {"source_id":"my-team","type":"local","path":"/skills/my-team"}
  ```

- **`git`** (production pattern — each team owns its repo): append an entry
  to `SKILLS_SOURCES`:

  ```json
  {"source_id":"payments","type":"git","url":"https://git.example/payments/skills.git","ref":"main"}
  ```

  For private repositories, add `"payments": "<read-only-token>"` to
  `SKILLS_GIT_TOKENS` (JSON map, via the skills-hub runtime secrets). The
  service clones into `SKILLS_DATA_PATH` and re-syncs on the interval.

Rules for both: `source_id` must match `[a-z0-9][a-z0-9-]*` and be unique;
unknown types or missing type-specific fields fail fast at startup. A failed
source sync never affects other sources.

## Removing a source

1. Remove its entry from `SKILLS_SOURCES` (and `SKILLS_GIT_TOKENS` if any).
2. For local sources, remove the ConfigMap, volume, and mount wiring.
3. `make build && make deploy`. At startup skills-hub prunes records whose
   source is no longer configured, so the removed source's skills stop
   appearing in search, list, and get immediately.

## Using skills

**Through the agent** (the intended path): the agent consults skills
automatically for procedure/remediation questions and cites what it uses.
Operators can ask directly:

- *"What guidance do we have for KubePodNotReady?"* → `skills.search`
- *"List all the skills we have"* → `skills.list`
- *"Show me the full runbook for sre-alerting/alerts/kubepodnotready"* →
  `skills.get`

**Directly against the API** (for debugging and content checks; requires the
query credential from `skills-hub-runtime-secrets`):

```sh
QUERY_CLIENTS=$(kubectl -n dev-luban-aiops get secret skills-hub-runtime-secrets \
  -o jsonpath='{.data.SKILLS_QUERY_CLIENTS}' | base64 -d)
QUERY_SECRET="${QUERY_CLIENTS#tool-gateway=}"

# Catalog (what skills.list sees)
kubectl -n dev-luban-aiops exec deployment/skills-hub -- \
  curl -fsS -u "tool-gateway:${QUERY_SECRET}" \
  "http://localhost:8000/api/v1/skills?limit=100"

# Search (multi-word queries match OR-wise; the shared scorer ranks them)
kubectl -n dev-luban-aiops exec deployment/skills-hub -- \
  curl -fsS -u "tool-gateway:${QUERY_SECRET}" \
  "http://localhost:8000/api/v1/skills/search?q=kubernetes%20incident"

# One full record
kubectl -n dev-luban-aiops exec deployment/skills-hub -- \
  curl -fsS -u "tool-gateway:${QUERY_SECRET}" \
  "http://localhost:8000/api/v1/skills/sre-alerting/alerts/kubepodnotready"
```

**End-to-end smoke test** after any content change:

```sh
sh shared/platform-ops/e2e/skills-demo.sh   # set SKIP_CHAT_LEG=true to skip the chat leg
```

## Verification

The status endpoint is auth-exempt and reports per-source sync outcomes:

```sh
kubectl -n dev-luban-aiops exec deployment/skills-hub -- \
  curl -fsS http://localhost:8000/api/v1/skills/status
```

Check per source: `accepted` counts match your file counts, `rejections` is
empty, and `last_error` is `null`.

Prometheus metrics on `/metrics`:

| Metric | Meaning |
|---|---|
| `skills_syncs_total{source,result}` | sync cycles by outcome; watch `result="error"` |
| `skills_ingest_rejected_total{reason}` | documents rejected at validation |
| `skills_store_skills{source}` | currently served skills (per source) |
| `skills_searches_total` | search traffic |

## Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| New/revised skill not visible | Sync not yet run, or ConfigMap wiring missed a file | Wait one interval or `kubectl rollout restart deployment/skills-hub`; check kustomization + deployment `items` |
| Source reports rejections | Document violates the format contract | Read the `rejections` reasons in `/api/v1/skills/status`; fix and re-validate |
| Source reports `last_error` | Unreachable git URL / bad token / unreadable path | Fix credentials or path; the previous slice keeps serving until then |
| Search returns no matches | Query words co-occur nowhere, or source never synced | Try `skills.list` / the catalog endpoint to confirm the skill exists; check status |
| `kustomize build` fails | ConfigMap entry points at a deleted/renamed file | Align `kustomization.yaml` keys with the files under `shared/platform-ops/skills/` |
| Agent claims no skills exist | skills connector not registered | Check `GATEWAY_SKILLS_SERVICE_URL` and the query-secret match (see [Configuration Reference](configuration-reference.md)) |

For deployment-level symptoms (CrashLoopBackOff, ErrImagePull, secrets),
see [Troubleshooting](troubleshooting.md).
