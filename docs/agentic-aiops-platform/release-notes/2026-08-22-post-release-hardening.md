# v0.8.1 — Post-v0.8.0 Code-Review Hardening

Date: 2026-08-22
Release type: patch (no API, contract, or deployment-shape changes)

## Summary

v0.8.1 closes the code and documentation review that followed the SPEC-022
(v0.8.0) delivery. All six review findings — one major, three minor, two
nits — are remediated. The reviewer verdict on v0.8.0 was "safe to remain
shipped"; this patch hardens the session workspace internals without
changing any operator-visible behavior.

## Change Set

### Fixed

- **Atomic set-once session titles in Redis (major)**: titles now live in
  a dedicated `session:title:{id}` key minted with `SET ... NX`, so the
  `touch_session` blob rewrite can no longer clobber a minted title and
  two concurrent first turns cannot both win. `get`/`list` overlay the
  title key at read time, `delete` removes it, and `len` excludes title
  keys. The Postgres backend was already atomic via its
  `title IS NULL` guard.
- **Gateway session-list proxy error posture (minor)**: upstream `4xx`
  on `GET /api/v1/sessions` now passes through unchanged (matching the
  get/delete proxies) instead of surfacing as `502`; `5xx`/transport
  errors still map to `502`.
- **Store test coverage (minor)**: nine new Redis bookkeeping tests
  (touch/title mint, set-once, touch-never-clobbers regression, orphan
  and cleanup semantics) plus two Postgres SQL-shape tests and one
  gateway proxy passthrough test.

### Changed

- `is_parked` delegates to `has_pending` in the HITL confirmation store
  (deduplication; behavior unchanged).
- `select-runtime-profile.sh` rejects `mutating-dev` as an argument
  (exit 1): it is the committed dev posture, not a switchable LLM
  runtime profile.

### Documented

- The delete-vs-in-flight-turn limitation (a chat turn still streaming
  during delete may park a confirmation and re-snapshot state after the
  delete) is documented on the delete route docstring and in the
  agent-platform README; a conditional-delete design is tracked as
  follow-up hardening.

## Validation

- `make verify` green: 1,052 tests across all products (+12 over v0.8.0),
  all kustomize overlays render, policy bundle validates, version
  lockstep at 0.8.1.
- `make build` + `make deploy` green; dev-k8s redeployed with the
  hardened images and all deployments healthy.
- L3 deep security review on the hardening commits: no findings.

## Known Limitations

- Delete-vs-in-flight-turn race remains by design (documented above);
  conditional delete is a follow-up.
- Operator portal is unchanged in this patch; the single-session chat
  flow remains until the session workspace UI spec lands.

## Related Documents

- `2026-08-22-multi-session-operator-workspace.md` (v0.8.0, SPEC-022)
- `docs/specs/SPEC-022-multi-session-operator-workspace/`
- `CHANGELOG.md` — `0.8.1 — 2026-08-22` section
