# Release Notes: 2026-08-21 — Durable OTLP Ingest Credential Provisioning

## Summary

A live observability check found five of the seven platform services
(audit-service, identity-service, incident-service, platform-gateway,
skills-hub) failing every OTLP export with `401 Unauthorized` while
agent-service and tool-gateway pushed cleanly. Root cause: the sibling
secret-sync scripts (`sync-delegation-secrets.sh`,
`sync-audit-secrets.sh`, `sync-skills-secrets.sh`) rewrite their
`runtime-secrets.env` files wholesale and re-apply their Secrets from
those files, which wiped the `OTEL_EXPORTER_OTLP_HEADERS` ingest
credential previously provisioned by `sync-otel-secrets.sh`. Any
`make deploy` run without the OpenObserve root credentials exported
re-introduced the anonymous-push state.

The patch restores authenticated telemetry push and makes the
provisioning durable: `sync-otel-secrets.sh` now merges the header
cluster-side via `kubectl patch` (touching only the OTEL key), and the
sibling scripts preserve an existing header line across their env-file
rewrites. Re-provisioning against dev-k8s was verified live: all seven
`*-runtime-secrets` Secrets carry the header and all services export
traces, metrics, and logs to OpenObserve with zero 401s.

`make verify` is green (all product suites, all four Kustomize
overlays, the eleven-rule policy bundle, and version lockstep). This
slice closes release **0.6.1** (PATCH bump: operational fix, no API or
behavior change).

## Change Set: Secret-sync durability

### Highlights

- **`sync-otel-secrets.sh` merges cluster-side.** The six service
  Secrets receive the OTLP header through `kubectl patch --type merge`
  (OTEL key only; all other keys preserved). A missing Secret is
  created with just the header so sibling scripts can fill in the
  remaining keys on their next run. Provisioning no longer depends on
  the local env-file lifecycle.
- **Agent-platform profile path retained.** The active runtime profile
  file stays authoritative for `agent-platform-runtime-secrets` (its
  model/API keys only exist there); the header is upserted before the
  secret is re-applied, and the cluster-side merge remains the fallback
  when no local profile file exists.
- **Sibling scripts preserve the header.** The `cat >` env-file
  rewrites in `sync-delegation-secrets.sh` (platform-gateway,
  identity-broker), `sync-audit-secrets.sh` (audit-service), and
  `sync-skills-secrets.sh` (skills-hub) now capture any existing
  `OTEL_EXPORTER_OTLP_HEADERS` line and re-append it, so a
  credential-less `make deploy` can no longer resurrect the
  headerless state.
- **Best-effort local mirror.** Existing local env files are mirrored
  with the header so later file-based syncs start from a consistent
  state.

## Validation

- `sh -n` syntax check across all four modified scripts.
- Live re-provisioning against dev-k8s: all seven Secrets patched,
  seven deployments rolled out, and post-restart pod logs show zero
  `401` / `Failed to export` lines across every service.
- `make verify` gate green at 0.6.1 lockstep.

## Known Limitations

- Fresh clusters still need the OpenObserve root credentials exported
  at least once for the header to exist; until then push fails open
  (anonymous, 401s) by design.
- The merged header value lives in cluster Secrets only when no local
  env file exists; local file regeneration relies on the preservation
  hooks, not on a cluster read-back.

## Related Documents

- `shared/shared-contracts/observability-conventions.md` — OTel switch
  semantics and OTLP log bridge behavior
- `docs/guides/configuration-reference.md` — telemetry configuration
  reference
