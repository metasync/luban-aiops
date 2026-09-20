# Skill Format (v3)

Convention for team-authored skill documents consumed by `skills-hub`
(SPEC-014 R-1). A skill is a Markdown file with YAML frontmatter; ingestion
validates every document against this contract and
[`schemas/skill.schema.json`](schemas/skill.schema.json). Invalid documents
are rejected with a reportable reason — never silently dropped.

v2 (SPEC-055 R-3) is **additive**: it adds an optional executable-flow class
(`kind` + a machine-readable `steps` replay list) and decouples `risk_class`
from `web_target`. A knowledge/guidance skill declares neither new key and
validates exactly as it did under v1.

v3 (SPEC-057 R-1) is likewise **additive**: it adds an optional composition
class (`kind: composition` + an ordered `sub_skills` reference list) that
carries **no authority of its own** (ADR-0011). A knowledge or executable-flow
skill declares neither new key and validates exactly as it did under v2, and a
v2 consumer that ignores `kind`/`sub_skills` still ingests a composition's
`body` as grounded guidance.

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
| `risk_class` | no | `read` or `write` — declared effect of the flow's interactive steps; treated as `read` when `web_target` is present without it. **No longer requires `web_target`** (SPEC-055 R-3), so a non-browser mutating skill (`k8s.*` steps) can declare `write`. A `composition` **never author-declares it** — it is derived for display only at sync (`write` when any resolved sub-skill is `write`, else `read`) and read by nothing in the deviation guard, identity guard, or policy engine (SPEC-057 R-1) |
| `flow_intent` | no | author-written plain sentence, ≤ 200 chars, describing what the flow's gated mutating step achieves; requires `web_target`; shown as the confirmation card's lead decision line and display-only — never a security input (SPEC-053) |
| `kind` | no | `knowledge` (default when absent), `executable_flow`, or `composition` — the skill class discriminator (SPEC-055 R-3; `composition` added by SPEC-057 R-1) |
| `steps` | no | ordered replay step list for an `executable_flow`; requires `kind: executable_flow` and `risk_class: write` (SPEC-055 R-3) |
| `sub_skills` | no | ordered sub-skill reference list for a `composition`; requires `kind: composition`, and a composition declares **no** `web_target`, **no** `steps`, and **no** author `risk_class` (SPEC-057 R-1) |

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

## Composition skills (v3)

A `composition` is an ordered, validated list of single-target sub-skill
references (SPEC-057 R-1). It expresses a multi-target *workflow* — query A,
health-check B, restart C — without widening any skill's authorization scope.
It carries **no authority of its own** (ADR-0011): it never mints tokens,
unlocks flows, or auto-approves gates. Each referenced sub-skill keeps its own
HITL gate, enforced by the shipped browser flow identity guard and per-action
infra gating — a composition adds no new gate machinery.

```markdown
---
title: Account Recovery Runbook
description: Reset a user's password, then re-enable their locked account.
kind: composition
sub_skills:
  - skill_id: samples/password-reset-resetacmepassword
    note: Reset the password on the admin portal first.
  - skill_id: samples/lock-unlock-user-lockunlockuser
    note: Then unlock the account via the infra API.
---

Runbook prose for the human reviewer, including the report-and-stop
convention (see below) ...
```

Each `sub_skills` item is a mapping with exactly these keys:

| Key | Required | Constraints |
| --- | --- | --- |
| `skill_id` | yes | the referenced sub-skill's namespaced id (`<source_id>/<slug>`, same pattern as a top-level `skill_id`) |
| `note` | no | string ≤ 200 chars — a display-only sentence describing this segment; never a security input, and a string that is never interpreted |

Order in the array **is** the runbook's declared sequence. Ingestion rules for
the class (all rejections are reportable, and a rejected composition is
**never** silently degraded to a knowledge skill):

- `kind: composition` **requires** a non-empty `sub_skills` list.
- A composition declares **no `web_target`**, **no `steps`**, and **no author
  `risk_class`** — its scope is the union of its sub-skills' scopes, and
  declaring any of the three would falsely imply a single authorization target
  or a platform interpreter that does not exist.
- Every `sub_skills[].skill_id` must **resolve** to a skill present in the
  served catalog that is **single-target** (one `web_target` or none) and is
  **not itself a `composition`** — no nesting in Phase 1, which removes cycles
  and unbounded depth by construction rather than by detection.
- **No duplicate** `skill_id` within one composition.
- The count is bounded by `SKILLS_COMPOSITION_MAX_SUB_SKILLS` (default **8**).
  The composite-wide worst case is `cap × GATEWAY_BROWSER_FLOW_MAX_STEPS`
  (8 × 20 = 160) unlocked browser writes per run, each still individually
  signed, audited and receipted, and each sub-skill still gated once.

Because sub-skill resolution needs the catalog, it happens at sync (a
store-consulting pass), not in the per-document draft pre-flight. Cross-source
compositions are therefore **eventually consistent**: a composition whose
sub-skill lives in a source that has not yet synced is rejected on this cycle
and accepted on a later one — an unresolvable reference is never served.

### No control flow (SPEC-057 R-3)

A composition expresses **sequence and nothing else**. The contract provides no
branch, loop, conditional, retry, or early-exit construct, and the item schema
is `additionalProperties: false`, so no such key can be written or smuggled in
via a `note` (a `note` is a string, never interpreted). The rationale is
deliberate: an interpreter would need loops, and a loop defeats
`GATEWAY_BROWSER_FLOW_MAX_STEPS`, currently the only bound on an unlocked
browser flow.

### Grounded guidance, not platform sequencing (SPEC-057 R-6)

A composition reaches the model through the existing SPEC-014 grounded-guidance
path: its `body` plus a rendered view of `sub_skills` in declared order, each
with its `note` and its sub-skill's own title and declared target (projected by
skills-hub's read path). The platform **never** pre-binds a sub-skill, never
issues `web.navigate` on the model's behalf, and never enforces the declared
order — order is guidance with the same standing as `steps[].expect`.

### Not a transaction (SPEC-057 R-5)

A composition is **not** a transaction. It has no rollback, no compensation and
no saga semantics: a run that stops part-way leaves every target it already
touched exactly as it is, and nothing claims otherwise. The convention is
**report-and-stop** — on a sub-skill failure the agent reports *which* sub-skill
failed and stops rather than continuing past a premise that no longer holds. The
authored `body` carries this instruction as grounded guidance (the R-8 sample's
body states it verbatim); it is a rendering property, not platform-enforced
control flow (there is none — see *No control flow* above).

**Re-entry derives from receipts, never from a new store.** There is no
composite-progress record and no persisted runbook half-state. The completed
prefix of a stopped run is reconstructable from the session's existing
`execution_records` signed receipts, which are swept at **30 days**
(`RETENTION_WINDOW_DAYS`, `execution_records.py:31`). Inside that window an
operator can see which sub-skills already ran and restart from the next one;
**outside it the operator restarts the runbook from the beginning.** Each
sub-skill still gates on its own authority when re-run (R-4), so a restart never
auto-signs a write the operator has not re-approved.

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
