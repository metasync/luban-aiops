# Skill Format (v2)

Convention for team-authored skill documents consumed by `skills-hub`
(SPEC-014 R-1). A skill is a Markdown file with YAML frontmatter; ingestion
validates every document against this contract and
[`schemas/skill.schema.json`](schemas/skill.schema.json). Invalid documents
are rejected with a reportable reason — never silently dropped.

v2 (SPEC-055 R-3) is **additive**: it adds an optional executable-flow class
(`kind` + a machine-readable `steps` replay list) and decouples `risk_class`
from `web_target`. A knowledge/guidance skill declares neither new key and
validates exactly as it did under v1.

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
| `risk_class` | no | `read` or `write` — declared effect of the flow's interactive steps; treated as `read` when `web_target` is present without it. **No longer requires `web_target`** (SPEC-055 R-3), so a non-browser mutating skill (`k8s.*` steps) can declare `write` |
| `flow_intent` | no | author-written plain sentence, ≤ 200 chars, describing what the flow's gated mutating step achieves; requires `web_target`; shown as the confirmation card's lead decision line and display-only — never a security input (SPEC-053) |
| `kind` | no | `knowledge` (default when absent) or `executable_flow` — the skill class discriminator (SPEC-055 R-3) |
| `steps` | no | ordered replay step list for an `executable_flow`; requires `kind: executable_flow` and `risk_class: write` (SPEC-055 R-3) |

Unknown keys are rejected: frontmatter must contain only the keys above.
The `web_target` / `risk_class` pair is additive (SPEC-049 R-3): documents
without them ingest unchanged, and the procedural steps stay in the markdown
body — there is no separate step format. `flow_intent` is likewise additive
(SPEC-053 R-1): it is display-only context for the confirmation card and never
a security input — the deviation guard and signed execution do not read it.
Credentials never belong in skills (including in `flow_intent`); the browser
tool surface resolves them from platform-managed credential sets.

## Executable-flow skills (v2)

A `knowledge` skill grounds an answer and never executes. An
`executable_flow` skill additionally carries a machine-readable replay list —
what SPEC-055 graduation produces from a session's approved authoring trace
(R-4), and what replay will drive (R-5, stage 7, *planned*). Ingestion,
storage and the graduation that feeds them are shipped; the replay that
consumes them is not.

```markdown
---
title: Reset User Password
description: Reset a user's password on the admin portal.
kind: executable_flow
web_target: https://admin.internal/login
risk_class: write
flow_intent: Submit the password reset for the user.
steps:
  - tool: web.navigate
    args: {url: "https://admin.internal/login"}
  - tool: web.fill_credential
    args: {ref: 1, credential_set: admin-portal, field: password}
  - tool: web.click
    args: {selector: "#submit"}
    expect: the user list renders
---

Replay runbook prose for the human reviewer ...
```

Each step is a mapping with exactly these keys:

| Key | Required | Constraints |
| --- | --- | --- |
| `tool` | yes | non-empty string ≤ 128 chars — the canonical dotted gateway tool name |
| `args` | yes | mapping of JSON-compatible values (mappings, lists, strings, numbers, booleans, null) |
| `expect` | no | string ≤ 500 chars — a post-condition the step asserts; a display/replay aid, never a security input |

Ingestion rules for the class (all rejections are reportable):

- `steps` requires `kind: executable_flow` — the class is **declared, never
  inferred**, and a `knowledge` skill must not carry a step list.
- `kind: executable_flow` requires a **non-empty** `steps` list and
  **`risk_class: write`**. The write declaration is unconditional for the
  class: a step list is a replay of *approved mutations*, and skills-hub holds
  no per-tool risk vocabulary to check a `read` claim against, so it fails
  closed on the declaration. A read-only browser flow needs no step list —
  `web_target` + `risk_class: read` already serves it.
- Any `web.*` step requires a `web_target`: the gateway binds the flow — and
  with it the origin guard and the step budget — from the declared target.
  Non-browser flows (`k8s.*`) need none, which is what decoupling
  `risk_class` from `web_target` buys.
- **Credential values are references, never literals.** A
  `web.fill_credential` step must name the set (`credential_set`) and the
  `field` it fills; the gateway resolves the value from platform-managed
  configuration at replay time. A step argument still carrying the unresolved
  hole marker `<credential-reference>` — what SPEC-055 R-2 writes in place of a
  literal credential it withheld at capture — is rejected: a hole names no set,
  so the flow could never authenticate. The marker is a deliberate second copy
  of agent-platform's `secret_params.TRACE_CREDENTIAL_PLACEHOLDER` (products
  never import each other), pinned by the `validate-secret-vocabulary` leg of
  `make verify` so the two cannot drift silently.

  This check is structural, not lexical: skills-hub cannot see the gateway's
  credential store, so it verifies that a credential-filling step *names* a set
  and that no argument carries R-2's marker. It detects no literal secret at
  all — not by name and not by shape.

  The lexical check lives upstream, at graduation: SPEC-055 R-4 re-validates
  every captured step and **refuses** (409, naming each position) a step
  argument shaped like a secret literal — a PEM private key block, a JWT, an
  `Authorization` header value or an AWS access key id. It refuses rather than
  redacts because the frontmatter `steps` list is the authoritative replay copy
  and a scrubbed argument would replay the wrong value. The match over-catches
  by design — a `web.select` option reading `Basic Authentication` is refused
  too — and that direction of error is the deliberate one: a false refusal
  costs an operator a re-author, a false accept publishes a credential. What
  survives both checks is therefore a literal matching neither R-2's
  capture-time *name* vocabulary nor R-4's recognized *shapes* — narrower than
  either alone, and recorded in the SPEC-055 stage-4 and stage-6b notes.

  Because `web.fill_credential` is read-tier, auto-allowed and absent from the
  browser write set, a graduated flow's trace never contains one under default
  configuration; this rule therefore fires for a hand-authored flow, or for a
  graduated draft a human completed with the credential reference at merge
  time (SPEC-055 R-4).

## Size caps

- body ≤ 64 KiB
- description ≤ 500 chars
- ≤ 10 tags
- ≤ 200 `steps`, and ≤ 64 KiB serialized for the whole list

The step caps are resource ceilings (one JSONB column, and `steps` rides list
responses), not the policy bound. The count that decides how far a flow may
replay is the gateway's flow step budget (`GATEWAY_BROWSER_FLOW_MAX_STEPS`,
default 20), and graduation's blast-radius re-validation (SPEC-055 R-4)
re-checks that same bound before an operator ever holds the artifact — as a
deliberate twin (`AGENT_SKILL_GRADUATION_MAX_STEPS`, also 20) with no drift
guard, because the gateway stays the authority at replay and fails closed
either way, so a drift only moves where the refusal surfaces. `200` sits above
both so a default-configured graduation is never rejected by the ceiling; the
authoring-trace cap (`AGENT_AUTHORING_TRACE_MAX_STEPS`, default 100) is
operator-tunable, so that ordering is a coupling to preserve rather than an
invariant.

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
