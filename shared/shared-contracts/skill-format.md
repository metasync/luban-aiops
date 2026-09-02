# Skill Format (v1)

Convention for team-authored skill documents consumed by `skills-hub`
(SPEC-014 R-1). A skill is a Markdown file with YAML frontmatter; ingestion
validates every document against this contract and
[`schemas/skill.schema.json`](schemas/skill.schema.json). Invalid documents
are rejected with a reportable reason — never silently dropped.

## Document layout

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

Everything between the first two `---` lines is frontmatter (parsed as a YAML
mapping); the rest is the body.

## Frontmatter keys

| Key | Required | Constraints |
| --- | --- | --- |
| `title` | yes | non-empty string, ≤ 200 chars |
| `description` | yes | non-empty string, ≤ 500 chars; used for search excerpts and citations |
| `tags` | no | list of strings, ≤ 10 items, each ≤ 64 chars |
| `version` | no | string ≤ 64 chars; author-managed marker |
| `source_url` | no | upstream attribution link for adapted open-source content |
| `web_target` | no | web-check flow entry URL: absolute `http(s)` URL, ≤ 2048 chars; declares the skill a browser-driven check flow (SPEC-049) |
| `risk_class` | no | `read` or `write` — declared effect of the flow's interactive steps; requires `web_target`; treated as `read` when `web_target` is present without it |

Unknown keys are rejected: frontmatter must contain only the keys above.
The `web_target` / `risk_class` pair is additive (SPEC-049 R-3): documents
without them ingest unchanged, and the procedural steps stay in the markdown
body — there is no separate step format. Credentials never belong in skills;
the browser tool surface resolves them from platform-managed credential sets.

## Size caps

- body ≤ 64 KiB
- description ≤ 500 chars
- ≤ 10 tags

## Identity rules

- **`skill_id` = `<source_id>/<slug>`** — `source_id` is the operator-assigned
  name of the source entry (`SKILLS_SOURCES`), not the repository URL, so ids
  survive repo renames and migrations.
- **The slug is derived from the file path, not from frontmatter**: relative
  path minus the `.md` extension, segments joined by `/`, each segment
  normalized to `[a-z0-9-]` (lowercase; runs of other characters collapse to
  `-`). Moving or renaming a file therefore changes its `skill_id` —
  intentionally, so stale citations become visible.
- Duplicate slugs **within one source** are a validation error; duplicates
  **across sources** are legal because ids are namespaced by `source_id`.
- `README.md` and `NOTICE` files are not skills and are skipped by ingestion.

## Validation pre-flight

Team repositories can lint locally with the same code path the service uses:

```sh
python -m skills_hub.validate <directory>
```

The command walks the directory, validates every `.md` document against this
contract, and reports `(path, reason)` for each rejection; exit code 0 means
the directory is safe to publish.

## Where to find open-source skills

Teams starting a new skill source rarely need to write from scratch; adapt
community-trusted content and add frontmatter + attribution:

- [`prometheus-operator/runbooks`](https://github.com/prometheus-operator/runbooks)
  (Apache-2.0) — runbooks for kube-prometheus-stack alerts, keyed by alert
  name; tag each skill with its alert name so alert → runbook lookups work.
- [Kubernetes troubleshooting guides](https://kubernetes.io/docs/tasks/debug/debug-application/)
  (CC-BY-4.0, `kubernetes/website`) — authoritative pod/node debugging
  procedures.

Attribution rules for adapted content: keep `source_url` pointing at the
upstream document, and carry a `NOTICE` file in the source root recording the
upstream project, URL, and license.
