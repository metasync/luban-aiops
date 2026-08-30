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

The same validation code path is also exposed as a read-only service route —
`POST /api/v1/skills/validate` on skills-hub, behind the Basic
query-credential registry (`SKILLS_QUERY_CLIENTS`). The agent service calls
it to validate generated skill drafts before they reach an operator
(SPEC-044); you can use it in CI the same way, sending
`{"document": "<raw markdown>"}` and reading `{"valid": true}` or
`{"valid": false, "reason": ...}`.

## Authoring a skill from a session record (SPEC-044)

The platform can draft a skill from the durable record of one of your own
sessions, so a good triage run becomes reusable guidance without a blank
page.

1. Open the session in the portal chat view and press **Draft as skill**
   (visible to `platform-admin`, `approver`, and `operator`). The agent
   service assembles the session's digest — plus the validated triage
   report when the session is incident-linked — and shapes it into Skill
   Format v1; raw transcripts and alert payloads never enter the draft.
2. The draft is validated on skills-hub's own ingestion code path before
   it is returned — an unvalidated draft is never handed out. If
   validation cannot run (dependency not configured or unreachable) the
   request fails closed with 503/502 instead.
3. The draft opens in a read-only **preview modal** (SPEC-045): a
   rendered view plus a **Raw** toggle showing the full markdown
   (including the provenance block), a mode badge, the validation
   status, and the suggested filename. **Download .md** hands over
   `<suggested-slug>.md`; **Discard** drops the draft without
   downloading. The badge tells you whether you hold a **generated**
   draft or the facts-only **skeleton** (the honest degradation for
   quiet sessions or generation failures — always format-valid).
4. Review, edit, and merge the draft into a skill source as usual
   ([Adding a skill to an existing source](#adding-a-skill-to-an-existing-source)).
   Every draft carries an HTML-comment provenance block (session, covered
   incident when present, date, platform version, mode) — body content
   you may keep or strip without breaking ingestion. Nothing about the
   draft is persisted on the platform: it exists only in your download.

Content guardrails are deterministic, not model obedience: the gateway's
redaction vocabulary scrubs the generated body and the Skill Format caps
are enforced by post-processing regardless of what the model emitted.

## Authoring a skill from an incident's validated triage (SPEC-045)

A triaged incident is team property — anyone holding the grant can turn
its validated triage into a skill draft, no matter who ran the triage
session:

1. Open the incident in the portal Incidents view and press **Draft as
   skill** beside **Run/Re-run triage** and **Continue in chat**
   (visible to `platform-admin`, `approver`, and `operator`; the gateway
   checks both `incident:skill_draft` and `incident:read` on every
   request).
2. The draft is generated from the incident envelope (minus the raw
   failed-triage output) and the validated triage report only — never
   from anyone's session — validated on the same skills-hub code path,
   with the same fail-closed 503/502 postures and the same skeleton
   degradation.
3. An incident without a validated triage report (new, triaging, or
   failed triage) returns a deterministic **409** — the toast names the
   precondition: run triage first, then draft the skill. The platform
   never guesses.
4. The same read-only preview modal opens; the provenance block carries
   the incident id and no session line. Download or discard as above.

Each generation — session- or incident-anchored, downloaded or discarded
— is recorded once in the audit trail (`skill_draft_generated` /
`incident_skill_draft_generated`); the audit event is the platform's only
trace of an ephemeral draft.

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
  {"source_id":"payments","type":"git","url":"https://git.example/payments/skills.git","ref":"main","path":"runbooks"}
  ```

  Fields: `url` (https clone URL), `ref` (branch/tag to track, default
  `HEAD`), and optional `path` — the subdirectory within the checkout to
  ingest. Real team repos keep skills next to other code, so `path` scopes
  ingestion (a missing subpath fails the sync with a clear error instead of
  ingesting the whole tree).

  Production-parity secret split (the dev-k8s overlay follows it with the
  `platform-skills` source pointed at this repository):

  - **Non-secret** federation config (`url`/`ref`/`path`) lives in the
    ConfigMap (`SKILLS_SOURCES` in `runtime-config.env`).
  - **Secret** material lives only in the `skills-hub-runtime-secrets`
    Secret: add `"payments": "<read-only-token>"` to `SKILLS_GIT_TOKENS`
    (JSON map source_id → token, injected into the clone URL as
    `x-access-token`). In dev-k8s, export the PAT and run the provisioning
    script — the token is never echoed or committed:

    ```sh
    SKILLS_GIT_TOKEN=<pat> shared/platform-ops/gitops/sync-skills-secrets.sh
    ```

    In production the same Secret comes from your secret manager.

  The service clones into `SKILLS_DATA_PATH` and re-syncs on the interval.
  Resilience: a failing git source (unreachable URL, expired token, missing
  subpath) keeps serving its previous snapshot, reports a scrubbed error on
  the status endpoint, and never affects other sources.

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
When a `skills.*` tool succeeds, the portal's tool-evidence card shows the
matched skills as **Cited guidance** chips (title + namespaced id), so the
guidance behind an answer is visible without expanding the data summary.
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
| Git source errors mention auth, others healthy | `SKILLS_GIT_TOKENS` missing the source's token | Re-run `sync-skills-secrets.sh` with `SKILLS_GIT_TOKEN` exported (dev) or update the Secret (prod) |
| Git source errors mention a subpath | Configured `path` absent from the repo checkout | Fix `path` in `SKILLS_SOURCES` or move the skills directory |
| Search returns no matches | Query words co-occur nowhere, or source never synced | Try `skills.list` / the catalog endpoint to confirm the skill exists; check status |
| `kustomize build` fails | ConfigMap entry points at a deleted/renamed file | Align `kustomization.yaml` keys with the files under `shared/platform-ops/skills/` |
| Agent claims no skills exist | skills connector not registered | Check `GATEWAY_SKILLS_SERVICE_URL` and the query-secret match (see [Configuration Reference](configuration-reference.md)) |

For deployment-level symptoms (CrashLoopBackOff, ErrImagePull, secrets),
see [Troubleshooting](troubleshooting.md).
