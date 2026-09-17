# HTTP Service Checks and the ACME Admin Skill Suite

- Date: 2026-09-17
- Version: v0.38.0
- Specs: [SPEC-058](../../specs/SPEC-058-http-service-check-tools/spec.md),
  [SPEC-059](../../specs/SPEC-059-acme-admin-sample-app-and-skill-suite/spec.md)

## Summary

This train delivers the HTTP service-check tools and their real sample target
together. SPEC-059 moves into v0.38.0 with its SPEC-058 dependency; SPEC-057
remains targeted at v0.40.0. The existing static browser target and samples are
retained. There is no new policy action, audit event type, stream contract,
shared schema, or database migration.

## Delivered capabilities

- `http.get` is a read-tier tool for status, projected headers and bounded
  JSON/text results. An upstream 4xx/5xx remains a successful tool result
  carrying the upstream status. Binary bodies are omitted.
- `http.post` sends a bounded JSON object and uses the existing signed,
  per-action approval path. Its curated card names the destination and body
  fields, masks secret fields, and keeps the raw body masked. A non-2xx
  response carries `mutation_confirmed: false`.
- Both tools are disabled by default, require an allowlisted origin, reject
  forbidden schemes, URL userinfo and loopback/link-local/multicast literals,
  and resolve authentication through named server-side credential sets. Neither
  exposes a request `headers` parameter.
- GET follows at most three validated redirects. POST follows none, preserving
  the destination shown on the approval card. Projected `url` and `location`
  values use the shared query-redaction helper.
- `http.get` joins the kernel's default read-tool auto-allow list. Read-tier
  registration alone is not an auto-allow grant; a custom list can still cause
  a read to park. `http.post` cannot be auto-allowed as a write-tier tool.
- `acme-admin` is a stand-alone FastAPI application with one in-memory store
  exposed through JSON and HTML. Real authentication, 404/409 responses,
  revision increments, and store-backed confirmation pages make mutations
  observable across both surfaces. Its image stays outside the platform build
  loop; its application version is independent of the platform release.

The four installed skills demonstrate the approval model:

| Sample | Surface | Effect | Cards |
|---|---|---|---|
| `health-check` | `http.get` | read | 0 |
| `user-status` | bound browser | read | 0 |
| `lock-unlock-user` | `http.post` | write | 1 action |
| `password-reset` | bound browser | write | 1 flow |

See the [sample README](../../../samples/acme-admin/README.md) for deployment,
endpoints, seed data, credential synchronization, and all four walkthroughs.

## Review and live-test corrections

The code-and-documentation review found two connector gaps: a projected
`location` header could expose a secret query, and a POST redirect could move a
mutation to a path absent from its approval card. Both are fixed and covered by
regression tests, including all five redirect statuses (301/302/303/307/308).

Live testing also exposed the missing kernel `http.get` auto-allow entry and
several demo assertion defects: discovery output mixed with progress text,
JSON bodies decoded twice, redirects checked in an empty body rather than the
Location header, and a denied NetworkPolicy probe mislabeled as reachable.
The demos and docs now reflect the observed behavior. Documentation also fixes
permission names, six installed skill documents (two existing plus four new),
requirement references, and the narrower scope of the reseed restriction.

## Validation

- `make verify`: passed after review fixes — 2,681 backend product tests,
  four overlay renders, 18 policy rules, 137 API and 19 tool-policy scenarios,
  version lockstep at 0.38.0, and all three secret-vocabulary checks.
- `make build` completed for all nine platform images, including the portal.
  All 110 sample-app tests and shell syntax checks passed after review fixes.
- Earlier delivery validation: the deterministic four-rung suite plus cross-skill
  check passed, opt-in chat legs asserted 0 / 0 / 1 / 1 cards, and `make e2e`
  passed all five registered scripts.
- Live browser walkthrough testing covered all four rungs. The final flow test
  used identity switching in one tab because the harness could not control a
  second window. Its evidence was text-level DOM assertions, not screenshots.
  It verified that an operator cannot self-approve and that asking the
  confirmation page about `dave` still reports the actual reset of `alice`.
- The browser pass preceded the two connector review fixes. Their regression
  tests pass; the release build/deploy and post-deploy smoke check are separate
  handoff steps, not claimed as completed by this note.
- The optional source-mutation spot checks remain unchecked in SPEC-058's
  task list; normal negative-path and vocabulary regression tests pass.

## Deploy and live-test notes

```sh
make build
make deploy
make deploy-sample-app
make deploy-samples
```

The `browser-dev` profile enables the HTTP connector and allowlists the sample
origin. Credential synchronization populates both the gateway credential set
and the application secret. `make deploy-samples` without `SAMPLE=` installs
all six skill documents. Start fresh Chat sessions for the walkthroughs.

The sample uses one replica with `Recreate`; restarting it resets its in-memory
data. Do not use it as a production administration service. Its header-gated
reseed endpoint is unreachable through these HTTP tools, not through every
agent capability: approved browser JavaScript may send custom headers.
NetworkPolicy enforcement depends on the cluster CNI. A POST redirect refusal
cannot roll back the initial request; inspect state before retrying.
